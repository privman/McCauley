#if os(macOS)
import AVFoundation
import Foundation

/// Streaming conversion of arbitrary-format PCM buffers to 16 kHz mono
/// Float32 arrays, preserving resampler state across calls.
final class StreamConverter {
    static let targetFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                            sampleRate: 16000, channels: 1,
                                            interleaved: false)!
    private let converter: AVAudioConverter
    private let ratio: Double

    init?(from format: AVAudioFormat) {
        guard format.sampleRate > 0,
              let c = AVAudioConverter(from: format, to: Self.targetFormat) else { return nil }
        self.converter = c
        self.ratio = 16000.0 / format.sampleRate
    }

    func convert(_ buffer: AVAudioPCMBuffer) -> [Float] {
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 16
        guard capacity > 0,
              let out = AVAudioPCMBuffer(pcmFormat: Self.targetFormat, frameCapacity: capacity) else {
            return []
        }
        var fed = false
        var convError: NSError?
        converter.convert(to: out, error: &convError) { _, status in
            if fed {
                status.pointee = .noDataNow
                return nil
            }
            fed = true
            status.pointee = .haveData
            return buffer
        }
        guard convError == nil, out.frameLength > 0, let ch = out.floatChannelData else { return [] }
        return Array(UnsafeBufferPointer(start: ch[0], count: Int(out.frameLength)))
    }
}
#endif
