#if os(macOS)
import Foundation
import SwiftUI
import TalmaciCore

/// Persisted settings, shared between the UI (@AppStorage bindings) and the
/// session controller (reads a snapshot at start).
enum Prefs {
    static let sourceLanguage = "sourceLanguage"
    static let useMicrophone = "useMicrophone"
    static let useSystemAudio = "useSystemAudio"
    static let whisperModel = "whisperModel"
    static let useGPU = "useGPU"
    static let threads = "threads"
    static let beamSize = "beamSize"
    static let tickMs = "tickMs"

    struct Snapshot {
        var sourceLanguage: Lang
        var useMicrophone: Bool
        var useSystemAudio: Bool
        var whisperModel: String
        var useGPU: Bool
        var threads: Int32
        var beamSize: Int32
        var tickMs: Int

        static func read() -> Snapshot {
            let d = UserDefaults.standard
            return Snapshot(
                sourceLanguage: Lang(rawValue: d.string(forKey: Prefs.sourceLanguage) ?? "") ?? .romanian,
                useMicrophone: d.object(forKey: Prefs.useMicrophone) as? Bool ?? true,
                useSystemAudio: d.object(forKey: Prefs.useSystemAudio) as? Bool ?? false,
                whisperModel: d.string(forKey: Prefs.whisperModel) ?? ModelStore.defaultWhisperModel,
                useGPU: d.object(forKey: Prefs.useGPU) as? Bool ?? true,
                threads: Int32(max(1, d.object(forKey: Prefs.threads) as? Int ?? 4)),
                beamSize: Int32(max(1, d.object(forKey: Prefs.beamSize) as? Int ?? 2)),
                tickMs: max(200, d.object(forKey: Prefs.tickMs) as? Int ?? 600))
        }
    }
}

/// Owns a live transcription session: audio sources -> mixer -> engine ->
/// published UI state.
@MainActor
final class SessionController: ObservableObject {
    enum State: Equatable {
        case idle
        case starting
        case running
        case error(String)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var transcript = PaneText()
    @Published private(set) var translation = PaneText()
    @Published private(set) var stats = LatencyStats()
    @Published private(set) var windowSeconds: Double = 0
    @Published private(set) var setupProblem: String?
    /// Language the running session was started with (UI may change prefs
    /// while running; panes should label what's actually happening).
    @Published private(set) var activeLanguage: Lang = .romanian

    private var engine: StreamingEngine?
    private var mixer: DualSourceMixer?
    private var mic: MicCapture?
    private var systemAudio: SystemAudioCapture?
    private var tickTask: Task<Void, Never>?

    var isRunning: Bool { state == .running || state == .starting }

    func refreshSetupStatus() {
        let cfg = Prefs.Snapshot.read()
        setupProblem = ModelStore.validate(whisperModel: cfg.whisperModel, from: cfg.sourceLanguage)
    }

    func start() {
        guard !isRunning else { return }
        let cfg = Prefs.Snapshot.read()
        guard cfg.useMicrophone || cfg.useSystemAudio else {
            state = .error("Select at least one audio source.")
            return
        }
        if let problem = ModelStore.validate(whisperModel: cfg.whisperModel, from: cfg.sourceLanguage) {
            state = .error(problem)
            return
        }
        state = .starting
        activeLanguage = cfg.sourceLanguage
        transcript = PaneText()
        translation = PaneText()
        stats = LatencyStats()

        Task { await self.startAsync(cfg) }
    }

    private func startAsync(_ cfg: Prefs.Snapshot) async {
        if cfg.useMicrophone {
            guard await MicCapture.requestPermission() else {
                fail("Microphone access denied. Allow Talmaci under "
                    + "System Settings → Privacy & Security → Microphone.")
                return
            }
        }

        // Model loading takes seconds for the larger whisper models; keep it
        // off the main actor.
        let lang = cfg.sourceLanguage
        let result: Result<StreamingEngine, Error> = await Task.detached(priority: .userInitiated) {
            do {
                let lib = try NativeLib.open()
                let stt = try WhisperService(
                    lib: lib,
                    modelPath: ModelStore.whisperModelPath(cfg.whisperModel).path,
                    useGPU: cfg.useGPU, threads: cfg.threads)
                let mt = try OpusMTService(
                    lib: lib,
                    modelDir: ModelStore.mtModelDir(from: lang).path,
                    beamSize: cfg.beamSize)
                return .success(StreamingEngine(stt: stt, mt: mt, language: lang.rawValue))
            } catch {
                return .failure(error)
            }
        }.value

        guard case .success(let engine) = result else {
            if case .failure(let error) = result {
                fail("Could not load models: \(error)")
            }
            return
        }
        guard state == .starting else { return } // user hit Stop while loading
        self.engine = engine

        let mixer = DualSourceMixer(aActive: cfg.useMicrophone, bActive: cfg.useSystemAudio)
        self.mixer = mixer

        if cfg.useMicrophone {
            let mic = MicCapture { samples in mixer.pushA(samples) }
            do {
                try mic.start()
                self.mic = mic
            } catch {
                fail("Microphone start failed: \(error)")
                return
            }
        }
        if cfg.useSystemAudio {
            let sys = SystemAudioCapture { samples in mixer.pushB(samples) }
            do {
                try sys.start()
                self.systemAudio = sys
            } catch {
                fail("\(error)")
                return
            }
        }

        state = .running
        let tick = Duration.milliseconds(cfg.tickMs)
        tickTask = Task.detached(priority: .userInitiated) { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: tick)
                if Task.isCancelled { return }
                engine.ingest(mixer.pull())
                if let update = engine.tick() {
                    await self?.publish(update)
                }
            }
        }
    }

    func stop() {
        tickTask?.cancel()
        tickTask = nil
        stopCapture()
        if let engine {
            publish(engine.finish())
        }
        engine = nil
        mixer = nil
        if case .error = state {} else { state = .idle }
    }

    func clearTranscript() {
        transcript = PaneText()
        translation = PaneText()
    }

    func dismissError() {
        if case .error = state { state = .idle }
    }

    private func stopCapture() {
        mic?.stop()
        mic = nil
        systemAudio?.stop()
        systemAudio = nil
    }

    private func fail(_ message: String) {
        stopCapture()
        tickTask?.cancel()
        tickTask = nil
        engine = nil
        state = .error(message)
    }

    private func publish(_ update: EngineUpdate) {
        transcript = update.transcript
        translation = update.translation
        stats = update.stats
        windowSeconds = update.windowSeconds
    }
}
#endif
