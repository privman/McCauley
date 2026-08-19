import Foundation

/// LocalAgreement-2 hypothesis stabilization: text that two consecutive
/// re-transcriptions of the (still open) audio window agree on is shown as
/// "confirmed"; the rest is a tentative tail that may still change.
///
/// Confirmed text is monotonic — it never shrinks and never changes — which is
/// what makes the live transcript readable instead of flickering.
public struct HypothesisTracker {
    private var previousWords: [String] = []
    private var confirmedCount: Int = 0

    public init() {}

    /// Feed the newest full-window hypothesis; get back the stable prefix and
    /// the still-changing tail.
    public mutating func update(hypothesis: String) -> (confirmed: String, tentative: String) {
        let words = Self.words(hypothesis)
        var agree = 0
        while agree < min(words.count, previousWords.count),
              Self.normalized(words[agree]) == Self.normalized(previousWords[agree]) {
            agree += 1
        }
        // Monotonic: once confirmed, stays confirmed (even if a later decode
        // disagrees — flicker is worse than a rare stale word).
        confirmedCount = max(confirmedCount, agree)
        confirmedCount = min(confirmedCount, words.count)
        previousWords = words
        let confirmed = words.prefix(confirmedCount).joined(separator: " ")
        let tentative = words.dropFirst(confirmedCount).joined(separator: " ")
        return (confirmed, tentative)
    }

    /// The full current hypothesis (used when the window is committed).
    public var currentHypothesis: String {
        previousWords.joined(separator: " ")
    }

    public mutating func reset() {
        previousWords = []
        confirmedCount = 0
    }

    static func words(_ s: String) -> [String] {
        s.split(whereSeparator: { $0.isWhitespace }).map(String.init)
    }

    /// Case/punctuation-insensitive comparison so "Hello," vs "hello" counts
    /// as agreement — whisper often flips those between decodes.
    static func normalized(_ w: String) -> String {
        w.lowercased().trimmingCharacters(in: .punctuationCharacters)
    }
}

/// Splits text into completed sentences plus an unfinished remainder.
public enum SentenceSplitter {
    static let enders: Set<Character> = [".", "!", "?", "…"]

    public static func split(_ text: String) -> (complete: [String], remainder: String) {
        var complete: [String] = []
        var current = ""
        var i = text.startIndex
        while i < text.endIndex {
            let c = text[i]
            current.append(c)
            if enders.contains(c) {
                let next = text.index(after: i)
                if next == text.endIndex || text[next].isWhitespace {
                    let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty { complete.append(trimmed) }
                    current = ""
                }
            }
            i = text.index(after: i)
        }
        return (complete, current.trimmingCharacters(in: .whitespacesAndNewlines))
    }
}

/// The live transcript (or translation) as shown in one pane.
public struct PaneText: Equatable, Sendable {
    /// Finalized text — the audio behind it has been committed.
    public var committed: String = ""
    /// Stable-but-not-final text for the open window.
    public var confirmed: String = ""
    /// Latest hypothesis tail; may still change. Rendered dimmed.
    public var tentative: String = ""

    public init() {}

    public init(committed: String, confirmed: String, tentative: String) {
        self.committed = committed
        self.confirmed = confirmed
        self.tentative = tentative
    }

    public var full: String {
        [committed, confirmed, tentative]
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    public var isEmpty: Bool { committed.isEmpty && confirmed.isEmpty && tentative.isEmpty }

    /// Fold the open-window text into `committed` (window was finalized).
    public mutating func commitOpenText() {
        let open = [confirmed, tentative].filter { !$0.isEmpty }.joined(separator: " ")
        if !open.isEmpty {
            committed = committed.isEmpty ? open : committed + " " + open
        }
        confirmed = ""
        tentative = ""
    }
}

/// Decides when the open audio window should be committed and restarted.
public struct WindowPolicy: Sendable {
    /// Commit after this much trailing silence (seconds).
    public var silenceDuration: Double = 0.8
    /// RMS below this counts as silence.
    public var silenceRMS: Float = 0.008
    /// Hard cap on window length (seconds); beyond it we commit regardless.
    public var maxWindow: Double = 12.0
    /// Don't bother committing windows shorter than this (seconds).
    public var minWindow: Double = 1.0

    public init() {}

    public enum Decision: Equatable, Sendable {
        case keepOpen
        /// Speech paused — commit everything and restart the window.
        case commitAll
        /// Window hit the length cap mid-speech — commit and slide.
        case commitOverflow
    }

    public func decide(windowSeconds: Double, trailingRMS: Float, speechSeen: Bool) -> Decision {
        if windowSeconds >= maxWindow { return .commitOverflow }
        guard windowSeconds >= minWindow, speechSeen else { return .keepOpen }
        if trailingRMS < silenceRMS { return .commitAll }
        return .keepOpen
    }
}

/// Rolling latency statistics (exponential moving average, milliseconds).
public struct LatencyStats: Equatable, Sendable {
    public private(set) var sttMs: Double = 0
    public private(set) var mtMs: Double = 0
    private var haveStt = false
    private var haveMt = false
    private let alpha = 0.3

    public init() {}

    public mutating func recordStt(_ ms: Double) {
        sttMs = haveStt ? alpha * ms + (1 - alpha) * sttMs : ms
        haveStt = true
    }

    public mutating func recordMt(_ ms: Double) {
        mtMs = haveMt ? alpha * ms + (1 - alpha) * mtMs : ms
        haveMt = true
    }

    /// End-to-end processing latency estimate for one update.
    public var totalMs: Double { sttMs + mtMs }
    public var hasData: Bool { haveStt }
}
