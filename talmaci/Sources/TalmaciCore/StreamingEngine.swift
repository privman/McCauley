import Foundation

/// Abstractions over the native services so the engine is testable without
/// real models.
public protocol TranscribingService {
    func transcribe(samples: [Float], language: String) throws -> SttResult
}

public protocol TranslatingService {
    func translate(_ text: String) throws -> String
}

/// Snapshot pushed to the UI after each engine tick.
public struct EngineUpdate: Equatable, Sendable {
    public var transcript: PaneText
    public var translation: PaneText
    public var stats: LatencyStats
    public var windowSeconds: Double
    public var lastError: String?
}

/// The near-real-time pipeline: audio samples in, stabilized transcript +
/// translation out.
///
/// Pure orchestration — no timers, no audio devices, no UI. The owner feeds
/// samples with `ingest(_:)` (any thread) and calls `tick()` periodically from
/// a single worker; each tick re-transcribes the open audio window, stabilizes
/// the hypothesis (LocalAgreement-2), commits the window on silence/overflow,
/// and (re)translates what changed.
public final class StreamingEngine {
    public static let sampleRate = 16000

    private let stt: TranscribingService
    private let mt: TranslatingService?
    private let policy: WindowPolicy
    private let language: String

    private let buffer = SampleBuffer()
    private var windowStart = 0
    private var tracker = HypothesisTracker()
    private var transcript = PaneText()
    private var translation = PaneText()
    private var stats = LatencyStats()
    private var translationCache: [String: String] = [:]
    private var lastOpenTranslated = ""
    private var lastError: String?

    public init(stt: TranscribingService, mt: TranslatingService?,
                policy: WindowPolicy = WindowPolicy(), language: String) {
        self.stt = stt
        self.mt = mt
        self.policy = policy
        self.language = language
    }

    /// Thread-safe; call from audio callbacks.
    public func ingest(_ samples: [Float]) {
        buffer.append(samples)
    }

    /// Run one pipeline step. Call from a single worker thread/queue.
    /// Returns nil when there was nothing to do (e.g. too little new audio).
    public func tick() -> EngineUpdate? {
        let sr = Self.sampleRate
        let total = buffer.count
        let windowSeconds = Double(total - windowStart) / Double(sr)
        guard windowSeconds >= 0.35 else { return nil }

        let window = buffer.samples(from: windowStart, to: total)

        // Skip whisper entirely while the window contains no speech at all,
        // and keep the window from growing over dead air.
        let speechSeen = containsSpeech(window)
        if !speechSeen {
            let keep = min(window.count, sr)
            windowStart = total - keep
            return currentUpdate(windowSeconds: Double(keep) / Double(sr))
        }

        let result: SttResult
        let t0 = DispatchTime.now()
        do {
            result = try stt.transcribe(samples: window, language: language)
        } catch {
            lastError = String(describing: error)
            return currentUpdate(windowSeconds: windowSeconds)
        }
        let wallMs = Double(DispatchTime.now().uptimeNanoseconds - t0.uptimeNanoseconds) / 1e6
        stats.recordStt(wallMs)

        let hypothesis = result.text
        let (confirmed, tentative) = tracker.update(hypothesis: hypothesis)

        let tailRMS = AudioMath.rms(window.suffix(sr / 2))
        switch policy.decide(windowSeconds: windowSeconds, trailingRMS: tailRMS, speechSeen: speechSeen) {
        case .commitAll:
            appendCommitted(hypothesis)
            transcript.confirmed = ""
            transcript.tentative = ""
            tracker.reset()
            windowStart = total
        case .commitOverflow:
            if result.segments.count > 1 {
                // Keep the last segment in the window; finalize the rest.
                let head = SttResult(segments: Array(result.segments.dropLast()), elapsedMs: 0).text
                let last = result.segments[result.segments.count - 1]
                appendCommitted(head)
                transcript.confirmed = ""
                transcript.tentative = last.text.trimmingCharacters(in: .whitespaces)
                windowStart += Int(last.t0) * sr / 1000
            } else {
                appendCommitted(hypothesis)
                transcript.confirmed = ""
                transcript.tentative = ""
                windowStart = total
            }
            tracker.reset()
        case .keepOpen:
            transcript.confirmed = confirmed
            transcript.tentative = tentative
        }

        refreshTranslation()
        return currentUpdate(windowSeconds: Double(total - windowStart) / Double(sr))
    }

    /// Commit whatever is still open (call on Stop).
    public func finish() -> EngineUpdate {
        let hypothesis = tracker.currentHypothesis
        if !hypothesis.isEmpty {
            appendCommitted(hypothesis)
        }
        transcript.confirmed = ""
        transcript.tentative = ""
        tracker.reset()
        windowStart = buffer.count
        refreshTranslation()
        return currentUpdate(windowSeconds: 0)
    }

    private func appendCommitted(_ text: String) {
        let t = text.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return }
        transcript.committed = transcript.committed.isEmpty
            ? t : transcript.committed + " " + t
    }

    /// Any 100 ms block above the silence threshold counts as speech.
    private func containsSpeech(_ window: [Float]) -> Bool {
        let block = Self.sampleRate / 10
        var i = 0
        while i < window.count {
            let end = min(i + block, window.count)
            if AudioMath.rms(window[i..<end]) >= policy.silenceRMS { return true }
            i = end
        }
        return false
    }

    private func refreshTranslation() {
        guard let mt else { return }

        // Committed text: translate sentence by sentence, cached, so already
        // translated sentences are never recomputed (and never flicker).
        let (sentences, remainder) = SentenceSplitter.split(transcript.committed)
        var units = sentences
        if !remainder.isEmpty { units.append(remainder) }
        var committedOut: [String] = []
        for unit in units {
            if let hit = translationCache[unit] {
                committedOut.append(hit)
                continue
            }
            let t0 = DispatchTime.now()
            guard let out = try? mt.translate(unit) else {
                lastError = "translation failed"
                continue
            }
            stats.recordMt(Double(DispatchTime.now().uptimeNanoseconds - t0.uptimeNanoseconds) / 1e6)
            translationCache[unit] = out
            committedOut.append(out)
        }
        translation.committed = committedOut.joined(separator: " ")

        // Open-window text: translate as one tentative blob, only when changed.
        let open = [transcript.confirmed, transcript.tentative]
            .filter { !$0.isEmpty }.joined(separator: " ")
        if open.isEmpty {
            translation.confirmed = ""
            translation.tentative = ""
            lastOpenTranslated = ""
        } else if open != lastOpenTranslated {
            let t0 = DispatchTime.now()
            if let out = try? mt.translate(open) {
                stats.recordMt(Double(DispatchTime.now().uptimeNanoseconds - t0.uptimeNanoseconds) / 1e6)
                translation.tentative = out
                lastOpenTranslated = open
            }
        }
    }

    private func currentUpdate(windowSeconds: Double) -> EngineUpdate {
        EngineUpdate(transcript: transcript, translation: translation,
                     stats: stats, windowSeconds: windowSeconds, lastError: lastError)
    }
}
