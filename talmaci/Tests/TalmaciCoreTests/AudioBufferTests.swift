import Foundation
import XCTest
@testable import TalmaciCore

final class SampleBufferTests: XCTestCase {
    func testAbsoluteIndexing() {
        let b = SampleBuffer(retainSamples: 100)
        b.append([1, 2, 3])
        b.append([4, 5])
        XCTAssertEqual(b.count, 5)
        XCTAssertEqual(b.samples(from: 1, to: 4), [2, 3, 4])
    }

    func testRetentionDropsOldButKeepsIndexing() {
        let b = SampleBuffer(retainSamples: 4)
        b.append([1, 2, 3, 4, 5, 6])
        XCTAssertEqual(b.count, 6)
        // Oldest two dropped; asking for them returns only what's retained.
        XCTAssertEqual(b.samples(from: 0, to: 6), [3, 4, 5, 6])
        XCTAssertEqual(b.samples(from: 4, to: 6), [5, 6])
    }

    func testEmptyRange() {
        let b = SampleBuffer()
        XCTAssertEqual(b.samples(from: 0, to: 0), [])
        b.append([1])
        XCTAssertEqual(b.samples(from: 5, to: 9), [])
    }
}

final class DualSourceMixerTests: XCTestCase {
    func testSingleSourcePassThrough() {
        let m = DualSourceMixer(aActive: true, bActive: false)
        m.pushA([0.1, 0.2])
        m.pushB([9, 9]) // inactive source ignored
        XCTAssertEqual(m.pull(), [0.1, 0.2])
        XCTAssertEqual(m.pull(), [])
    }

    func testBothSourcesSumOverlap() {
        let m = DualSourceMixer(aActive: true, bActive: true)
        m.pushA([0.1, 0.1, 0.1])
        m.pushB([0.2, 0.2])
        let out = m.pull()
        XCTAssertEqual(out.count, 2)
        XCTAssertEqual(out[0], 0.3, accuracy: 1e-6)
        // Third A sample waits for more B.
        m.pushB([0.3])
        let out2 = m.pull()
        XCTAssertEqual(out2.count, 1)
        XCTAssertEqual(out2[0], 0.4, accuracy: 1e-6)
    }

    func testClipping() {
        let m = DualSourceMixer(aActive: true, bActive: true)
        m.pushA([0.9])
        m.pushB([0.9])
        XCTAssertEqual(m.pull(), [1.0])
    }

    func testStalledSourceFlushesLeader() {
        let m = DualSourceMixer(aActive: true, bActive: true, maxSkew: 10)
        m.pushA([Float](repeating: 0.5, count: 30))
        // B stalled: nothing mixable, but once A exceeds maxSkew its samples
        // flush through so the stream doesn't freeze.
        let out = m.pull()
        XCTAssertEqual(out.count, 30)
    }
}

final class AudioMathTests: XCTestCase {
    func testRMS() {
        XCTAssertEqual(AudioMath.rms([Float]()), 0)
        XCTAssertEqual(AudioMath.rms([0.5, -0.5, 0.5, -0.5]), 0.5, accuracy: 1e-6)
    }

    func testResampleHalvesCount() {
        let input = [Float](repeating: 1, count: 32000)
        let out = AudioMath.resampleLinear(input, from: 32000, to: 16000)
        XCTAssertEqual(out.count, 16000)
        XCTAssertEqual(out[100], 1, accuracy: 1e-6)
    }
}

// MARK: - StreamingEngine with fake services

private final class FakeSTT: TranscribingService {
    var script: [String] = []
    private var i = 0
    func transcribe(samples: [Float], language: String) throws -> SttResult {
        let text = i < script.count ? script[i] : (script.last ?? "")
        i += 1
        // One segment spanning the window.
        let ms = Int64(samples.count * 1000 / StreamingEngine.sampleRate)
        return SttResult(segments: [SttSegment(t0: 0, t1: ms, text: text)], elapsedMs: 1)
    }
}

private final class FakeMT: TranslatingService {
    private(set) var calls: [String] = []
    func translate(_ text: String) throws -> String {
        calls.append(text)
        return "T[\(text)]"
    }
}

final class StreamingEngineTests: XCTestCase {
    private let sr = StreamingEngine.sampleRate

    private func loudSamples(seconds: Double) -> [Float] {
        // 440 Hz sine, comfortably above the silence threshold.
        let n = Int(seconds * Double(sr))
        return (0..<n).map { 0.3 * sin(Float($0) * 2 * .pi * 440 / Float(sr)) }
    }

    private func silence(seconds: Double) -> [Float] {
        [Float](repeating: 0, count: Int(seconds * Double(sr)))
    }

    func testTentativeThenConfirmedFlow() {
        let stt = FakeSTT()
        stt.script = ["buna dimineata", "buna dimineata tuturor"]
        let engine = StreamingEngine(stt: stt, mt: FakeMT(), language: "ro")

        engine.ingest(loudSamples(seconds: 1.0))
        let u1 = engine.tick()
        XCTAssertEqual(u1?.transcript.tentative, "buna dimineata")
        XCTAssertEqual(u1?.transcript.confirmed, "")

        engine.ingest(loudSamples(seconds: 1.0))
        let u2 = engine.tick()
        XCTAssertEqual(u2?.transcript.confirmed, "buna dimineata")
        XCTAssertEqual(u2?.transcript.tentative, "tuturor")
    }

    func testSilenceCommitsWindow() {
        let stt = FakeSTT()
        stt.script = ["buna dimineata.", "buna dimineata."]
        let mt = FakeMT()
        let engine = StreamingEngine(stt: stt, mt: mt, language: "ro")

        engine.ingest(loudSamples(seconds: 2.0))
        _ = engine.tick()
        engine.ingest(silence(seconds: 1.0))
        let u = engine.tick()
        XCTAssertEqual(u?.transcript.committed, "buna dimineata.")
        XCTAssertEqual(u?.transcript.tentative, "")
        // Committed sentence got translated (cached form).
        XCTAssertEqual(u?.translation.committed, "T[buna dimineata.]")
    }

    func testCommittedTranslationIsCached() {
        let stt = FakeSTT()
        stt.script = ["primul.", "primul.", "primul.", "al doilea"]
        let mt = FakeMT()
        let engine = StreamingEngine(stt: stt, mt: mt, language: "ro")

        engine.ingest(loudSamples(seconds: 2.0))
        _ = engine.tick()
        engine.ingest(silence(seconds: 1.0))
        _ = engine.tick() // commits "primul."
        let callsAfterCommit = mt.calls.filter { $0 == "primul." }.count

        engine.ingest(loudSamples(seconds: 1.0))
        _ = engine.tick() // new speech; "primul." must come from cache
        XCTAssertEqual(mt.calls.filter { $0 == "primul." }.count, callsAfterCommit)
    }

    func testPureSilenceProducesNoTranscript() {
        let stt = FakeSTT()
        stt.script = ["ghost text"]
        let engine = StreamingEngine(stt: stt, mt: nil, language: "en")
        engine.ingest(silence(seconds: 3.0))
        let u = engine.tick()
        // Whisper never ran: no text, and window trimmed to ~1s.
        XCTAssertEqual(u?.transcript.full ?? "", "")
        XCTAssertLessThanOrEqual(u?.windowSeconds ?? 99, 1.01)
    }

    func testFinishCommitsOpenText() {
        let stt = FakeSTT()
        stt.script = ["pe curand"]
        let mt = FakeMT()
        let engine = StreamingEngine(stt: stt, mt: mt, language: "ro")
        engine.ingest(loudSamples(seconds: 1.0))
        _ = engine.tick()
        let u = engine.finish()
        XCTAssertEqual(u.transcript.committed, "pe curand")
        XCTAssertEqual(u.transcript.tentative, "")
        XCTAssertEqual(u.translation.committed, "T[pe curand]")
    }

    func testOverflowCommitsAndSlides() {
        let stt = FakeSTT()
        stt.script = Array(repeating: "unu doi trei patru cinci", count: 40)
        let engine = StreamingEngine(stt: stt, mt: nil, language: "ro")
        // 13s of loud audio in one go -> window over the 12s cap.
        engine.ingest(loudSamples(seconds: 13.0))
        let u = engine.tick()
        XCTAssertFalse(u?.transcript.committed.isEmpty ?? true)
        // Window restarted (single segment case commits everything).
        XCTAssertLessThan(u?.windowSeconds ?? 99, 1.0)
    }
}
