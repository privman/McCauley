#if os(macOS)
import AVFoundation
import Foundation
import TalmaciCore

/// Microphone capture via AVAudioEngine, delivering 16 kHz mono Float32.
final class MicCapture {
    private let engine = AVAudioEngine()
    private var converter: StreamConverter?
    private let onSamples: ([Float]) -> Void

    init(onSamples: @escaping ([Float]) -> Void) {
        self.onSamples = onSamples
    }

    static func requestPermission() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .audio)
        default: return false
        }
    }

    func start() throws {
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, let converter = StreamConverter(from: inFormat) else {
            throw NativeError.callFailed("microphone reports invalid format — is an input device connected?")
        }
        self.converter = converter

        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { [weak self] buffer, _ in
            guard let self, let converter = self.converter else { return }
            let samples = converter.convert(buffer)
            if !samples.isEmpty {
                self.onSamples(samples)
            }
        }

        engine.prepare()
        try engine.start()
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
    }
}
#endif
