import XCTest
@testable import TalmaciCore

final class HypothesisTrackerTests: XCTestCase {
    func testAgreementGrowsWithConsistentPrefix() {
        var t = HypothesisTracker()
        var r = t.update(hypothesis: "buna dimineata")
        XCTAssertEqual(r.confirmed, "")
        XCTAssertEqual(r.tentative, "buna dimineata")

        r = t.update(hypothesis: "buna dimineata tuturor")
        XCTAssertEqual(r.confirmed, "buna dimineata")
        XCTAssertEqual(r.tentative, "tuturor")

        r = t.update(hypothesis: "buna dimineata tuturor celor")
        XCTAssertEqual(r.confirmed, "buna dimineata tuturor")
        XCTAssertEqual(r.tentative, "celor")
    }

    func testConfirmedIsMonotonic() {
        var t = HypothesisTracker()
        _ = t.update(hypothesis: "one two three")
        _ = t.update(hypothesis: "one two three four")
        // A later decode disagreeing with confirmed words must not shrink them.
        let r = t.update(hypothesis: "one two DIFFERENT")
        XCTAssertEqual(r.confirmed, "one two DIFFERENT")
    }

    func testPunctuationAndCaseCountAsAgreement() {
        var t = HypothesisTracker()
        _ = t.update(hypothesis: "hello world")
        let r = t.update(hypothesis: "Hello, world today")
        XCTAssertEqual(r.confirmed, "Hello, world")
        XCTAssertEqual(r.tentative, "today")
    }

    func testResetClearsState() {
        var t = HypothesisTracker()
        _ = t.update(hypothesis: "a b c")
        _ = t.update(hypothesis: "a b c d")
        t.reset()
        let r = t.update(hypothesis: "x y")
        XCTAssertEqual(r.confirmed, "")
        XCTAssertEqual(r.tentative, "x y")
        XCTAssertEqual(t.currentHypothesis, "x y")
    }
}

final class SentenceSplitterTests: XCTestCase {
    func testSplitsCompletedSentences() {
        let (complete, rest) = SentenceSplitter.split("Buna ziua. Ce mai faci? Eu sunt")
        XCTAssertEqual(complete, ["Buna ziua.", "Ce mai faci?"])
        XCTAssertEqual(rest, "Eu sunt")
    }

    func testNoTerminatorMeansAllRemainder() {
        let (complete, rest) = SentenceSplitter.split("doar un fragment")
        XCTAssertTrue(complete.isEmpty)
        XCTAssertEqual(rest, "doar un fragment")
    }

    func testAbbreviationMidSentenceNotSplitWithoutSpace() {
        let (complete, rest) = SentenceSplitter.split("Costa 3.50 lei azi")
        XCTAssertTrue(complete.isEmpty)
        XCTAssertEqual(rest, "Costa 3.50 lei azi")
    }

    func testEllipsisEndsSentence() {
        let (complete, rest) = SentenceSplitter.split("Pai… nu stiu")
        XCTAssertEqual(complete, ["Pai…"])
        XCTAssertEqual(rest, "nu stiu")
    }
}

final class PaneTextTests: XCTestCase {
    func testCommitOpenText() {
        var p = PaneText(committed: "Done.", confirmed: "stable part", tentative: "maybe")
        p.commitOpenText()
        XCTAssertEqual(p.committed, "Done. stable part maybe")
        XCTAssertEqual(p.confirmed, "")
        XCTAssertEqual(p.tentative, "")
    }

    func testFullJoinsNonEmpty() {
        let p = PaneText(committed: "a", confirmed: "", tentative: "c")
        XCTAssertEqual(p.full, "a c")
    }
}

final class WindowPolicyTests: XCTestCase {
    func testCommitOnSilenceAfterSpeech() {
        let p = WindowPolicy()
        XCTAssertEqual(p.decide(windowSeconds: 3, trailingRMS: 0.001, speechSeen: true), .commitAll)
    }

    func testKeepOpenWhileLoud() {
        let p = WindowPolicy()
        XCTAssertEqual(p.decide(windowSeconds: 3, trailingRMS: 0.1, speechSeen: true), .keepOpen)
    }

    func testOverflowCommitsRegardless() {
        let p = WindowPolicy()
        XCTAssertEqual(p.decide(windowSeconds: 12.5, trailingRMS: 0.1, speechSeen: true), .commitOverflow)
    }

    func testShortWindowNeverCommits() {
        let p = WindowPolicy()
        XCTAssertEqual(p.decide(windowSeconds: 0.5, trailingRMS: 0.0, speechSeen: true), .keepOpen)
    }
}

final class LatencyStatsTests: XCTestCase {
    func testEmaAndTotal() {
        var s = LatencyStats()
        XCTAssertFalse(s.hasData)
        s.recordStt(100)
        s.recordMt(50)
        XCTAssertTrue(s.hasData)
        XCTAssertEqual(s.totalMs, 150, accuracy: 0.001)
        s.recordStt(200) // EMA: 0.3*200 + 0.7*100 = 130
        XCTAssertEqual(s.sttMs, 130, accuracy: 0.001)
    }
}
