#if os(macOS)
import AudioToolbox
import AVFoundation
import CoreAudio
import Foundation
import TalmaciCore

/// Captures everything the Mac plays (a global process tap mixed down to
/// stereo), delivering 16 kHz mono Float32. Requires macOS 14.4+ and the
/// "System Audio Recording" permission (prompted on first start).
///
/// Mechanism: CATapDescription -> AudioHardwareCreateProcessTap, wrapped in a
/// private aggregate device whose IO proc receives the tapped buffers.
final class SystemAudioCapture {
    private var tapID: AudioObjectID = kAudioObjectUnknown
    private var aggregateID: AudioObjectID = kAudioObjectUnknown
    private var ioProcID: AudioDeviceIOProcID?
    private let queue = DispatchQueue(label: "talmaci.systemtap", qos: .userInitiated)
    private var converter: StreamConverter?
    private var tapFormat: AVAudioFormat?
    private let onSamples: ([Float]) -> Void

    init(onSamples: @escaping ([Float]) -> Void) {
        self.onSamples = onSamples
    }

    func start() throws {
        // Tap every process's output (empty exclude list), stereo mixdown.
        let desc = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        desc.uuid = UUID()
        desc.muteBehavior = .unmuted
        desc.name = "Talmaci system audio tap"
        desc.isPrivate = true

        var newTapID: AudioObjectID = kAudioObjectUnknown
        var err = AudioHardwareCreateProcessTap(desc, &newTapID)
        guard err == noErr else {
            throw NativeError.callFailed(Self.explainTapError(err))
        }
        tapID = newTapID

        // The tap's stream format (typically float32 stereo at device rate).
        var asbd = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        var addr = AudioObjectPropertyAddress(mSelector: kAudioTapPropertyFormat,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        err = AudioObjectGetPropertyData(tapID, &addr, 0, nil, &size, &asbd)
        guard err == noErr, let tapFormat = AVAudioFormat(streamDescription: &asbd) else {
            stop()
            throw NativeError.callFailed("could not read system tap format (error \(err))")
        }
        self.tapFormat = tapFormat
        converter = StreamConverter(from: tapFormat)

        // Aggregate device hosting the tap. Clocked off the default output
        // device so tap timestamps track what's actually playing.
        let outputUID = (try? Self.defaultOutputDeviceUID()) ?? ""
        var description: [String: Any] = [
            kAudioAggregateDeviceNameKey as String: "Talmaci tap aggregate",
            kAudioAggregateDeviceUIDKey as String: UUID().uuidString,
            kAudioAggregateDeviceIsPrivateKey as String: true,
            kAudioAggregateDeviceIsStackedKey as String: false,
            kAudioAggregateDeviceTapAutoStartKey as String: true,
            kAudioAggregateDeviceTapListKey as String: [
                [
                    kAudioSubTapUIDKey as String: desc.uuid.uuidString,
                    kAudioSubTapDriftCompensationKey as String: true,
                ]
            ],
        ]
        if !outputUID.isEmpty {
            description[kAudioAggregateDeviceMainSubDeviceKey as String] = outputUID
            description[kAudioAggregateDeviceSubDeviceListKey as String] = [
                [kAudioSubDeviceUIDKey as String: outputUID]
            ]
        }

        var newAggregateID: AudioObjectID = kAudioObjectUnknown
        err = AudioHardwareCreateAggregateDevice(description as CFDictionary, &newAggregateID)
        guard err == noErr else {
            stop()
            throw NativeError.callFailed("could not create aggregate device (error \(err))")
        }
        aggregateID = newAggregateID

        err = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateID, queue) {
            [weak self] _, inInputData, _, _, _ in
            self?.handle(bufferList: inInputData)
        }
        guard err == noErr else {
            stop()
            throw NativeError.callFailed("could not create IO proc (error \(err))")
        }
        err = AudioDeviceStart(aggregateID, ioProcID)
        guard err == noErr else {
            stop()
            throw NativeError.callFailed("could not start aggregate device (error \(err))")
        }
    }

    private func handle(bufferList: UnsafePointer<AudioBufferList>) {
        guard let converter, let tapFormat,
              let pcm = AVAudioPCMBuffer(pcmFormat: tapFormat,
                                         bufferListNoCopy: bufferList, deallocator: nil) else {
            return
        }
        let samples = converter.convert(pcm)
        if !samples.isEmpty {
            onSamples(samples)
        }
    }

    func stop() {
        if aggregateID != kAudioObjectUnknown {
            if let ioProcID {
                AudioDeviceStop(aggregateID, ioProcID)
                AudioDeviceDestroyIOProcID(aggregateID, ioProcID)
                self.ioProcID = nil
            }
            AudioHardwareDestroyAggregateDevice(aggregateID)
            aggregateID = kAudioObjectUnknown
        }
        if tapID != kAudioObjectUnknown {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = kAudioObjectUnknown
        }
        converter = nil
        tapFormat = nil
    }

    deinit { stop() }

    private static func defaultOutputDeviceUID() throws -> String {
        var deviceID = AudioDeviceID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultOutputDevice,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        var err = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &deviceID)
        guard err == noErr, deviceID != kAudioObjectUnknown else {
            throw NativeError.callFailed("no default output device (error \(err))")
        }
        var uid: CFString = "" as CFString
        size = UInt32(MemoryLayout<CFString>.size)
        addr.mSelector = kAudioDevicePropertyDeviceUID
        err = withUnsafeMutablePointer(to: &uid) { ptr in
            AudioObjectGetPropertyData(deviceID, &addr, 0, nil, &size, ptr)
        }
        guard err == noErr else {
            throw NativeError.callFailed("could not read output device UID (error \(err))")
        }
        return uid as String
    }

    private static func explainTapError(_ err: OSStatus) -> String {
        if err == OSStatus(0x21706572) /* '!per' perm denied */ || err == kAudioHardwareIllegalOperationError {
            return "System audio permission denied. Allow Talmaci under "
                + "System Settings → Privacy & Security → Screen & System Audio Recording, then retry."
        }
        return "could not create system audio tap (error \(err)). "
            + "Check System Settings → Privacy & Security → Screen & System Audio Recording."
    }
}
#endif
