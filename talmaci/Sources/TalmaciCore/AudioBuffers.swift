import Foundation

/// Append-only mono sample buffer with absolute indexing (sample 0 = stream
/// start) and a bounded retention window. Thread-safe.
public final class SampleBuffer {
    private let lock = NSLock()
    private var storage: [Float] = []
    /// Absolute index of storage[0].
    private var base: Int = 0
    private let retain: Int

    /// - Parameter retainSamples: how many trailing samples to keep reachable.
    public init(retainSamples: Int = 16000 * 90) {
        self.retain = retainSamples
    }

    /// Total samples ever written (== absolute index one past the newest).
    public var count: Int {
        lock.lock(); defer { lock.unlock() }
        return base + storage.count
    }

    public func append(_ samples: [Float]) {
        guard !samples.isEmpty else { return }
        lock.lock(); defer { lock.unlock() }
        storage.append(contentsOf: samples)
        if storage.count > retain {
            let drop = storage.count - retain
            storage.removeFirst(drop)
            base += drop
        }
    }

    /// Samples in the absolute range [from, to), clamped to what is retained.
    public func samples(from: Int, to: Int) -> [Float] {
        lock.lock(); defer { lock.unlock() }
        let lo = max(from - base, 0)
        let hi = min(to - base, storage.count)
        guard lo < hi else { return [] }
        return Array(storage[lo..<hi])
    }

    public func removeAll() {
        lock.lock(); defer { lock.unlock() }
        storage.removeAll()
        base = 0
    }
}

/// Merges up to two live sample streams (microphone / system audio) into one
/// mono stream. Sources push independently; `pull()` returns the next mixed
/// chunk. When both sources are active the overlap is summed; if one source
/// runs ahead by more than `maxSkew` samples (stalled device, clock drift),
/// the leader is trimmed so the stream keeps flowing.
public final class DualSourceMixer {
    private let lock = NSLock()
    private var pendingA: [Float] = []
    private var pendingB: [Float] = []
    public private(set) var aActive: Bool
    public private(set) var bActive: Bool
    private let maxSkew: Int

    public init(aActive: Bool, bActive: Bool, maxSkew: Int = 16000 / 2) {
        self.aActive = aActive
        self.bActive = bActive
        self.maxSkew = maxSkew
    }

    public func pushA(_ samples: [Float]) {
        lock.lock(); defer { lock.unlock() }
        guard aActive else { return }
        pendingA.append(contentsOf: samples)
    }

    public func pushB(_ samples: [Float]) {
        lock.lock(); defer { lock.unlock() }
        guard bActive else { return }
        pendingB.append(contentsOf: samples)
    }

    public func pull() -> [Float] {
        lock.lock(); defer { lock.unlock() }
        switch (aActive, bActive) {
        case (true, false):
            let out = pendingA; pendingA = []
            return out
        case (false, true):
            let out = pendingB; pendingB = []
            return out
        case (false, false):
            return []
        case (true, true):
            let n = min(pendingA.count, pendingB.count)
            var out = [Float](repeating: 0, count: n)
            for i in 0..<n {
                out[i] = max(-1.0, min(1.0, pendingA[i] + pendingB[i]))
            }
            pendingA.removeFirst(n)
            pendingB.removeFirst(n)
            // Anti-stall: if the leader is too far ahead, flush its excess
            // unmixed rather than letting latency build up unboundedly.
            if pendingA.count > maxSkew {
                out.append(contentsOf: pendingA)
                pendingA = []
            } else if pendingB.count > maxSkew {
                out.append(contentsOf: pendingB)
                pendingB = []
            }
            return out
        }
    }
}

public enum AudioMath {
    /// Root mean square of a sample slice; 0 for empty input.
    public static func rms<C: Collection>(_ samples: C) -> Float where C.Element == Float {
        guard !samples.isEmpty else { return 0 }
        var acc: Float = 0
        for s in samples { acc += s * s }
        return (acc / Float(samples.count)).squareRoot()
    }

    /// Naive linear resampler; fine for speech feature extraction.
    public static func resampleLinear(_ input: [Float], from srcRate: Double, to dstRate: Double) -> [Float] {
        guard srcRate != dstRate, !input.isEmpty else { return input }
        let ratio = dstRate / srcRate
        let outCount = Int(Double(input.count) * ratio)
        guard outCount > 0 else { return [] }
        var out = [Float](repeating: 0, count: outCount)
        for i in 0..<outCount {
            let src = Double(i) / ratio
            let i0 = Int(src)
            let i1 = Swift.min(i0 + 1, input.count - 1)
            let frac = Float(src - Double(i0))
            out[i] = input[i0] * (1 - frac) + input[i1] * frac
        }
        return out
    }
}
