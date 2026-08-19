#if os(macOS)
import Foundation
import TalmaciCore

/// The two supported speech/translation languages.
enum Lang: String, CaseIterable, Identifiable {
    case romanian = "ro"
    case english = "en"

    var id: String { rawValue }
    var displayName: String {
        switch self {
        case .romanian: return "Romanian"
        case .english: return "English"
        }
    }
    var other: Lang { self == .romanian ? .english : .romanian }
    /// OPUS-MT model directory name for translating from this language.
    var mtModelDirName: String { "opus-mt-\(rawValue)-\(other.rawValue)" }
}

/// Locates model files and the native library on disk.
struct ModelStore {
    /// Default: ~/Library/Application Support/Talmaci/models
    /// Override with TALMACI_MODELS_DIR (used by CI and development).
    static var modelsDir: URL {
        if let env = ProcessInfo.processInfo.environment["TALMACI_MODELS_DIR"], !env.isEmpty {
            return URL(fileURLWithPath: env)
        }
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Talmaci/models", isDirectory: true)
    }

    /// Installed whisper models (ggml-*.bin), sorted with the recommended
    /// default first if present.
    static func installedWhisperModels() -> [String] {
        let fm = FileManager.default
        let names = (try? fm.contentsOfDirectory(atPath: modelsDir.path)) ?? []
        var models = names.filter { $0.hasPrefix("ggml-") && $0.hasSuffix(".bin") }.sorted()
        if let i = models.firstIndex(of: defaultWhisperModel) {
            models.remove(at: i)
            models.insert(defaultWhisperModel, at: 0)
        }
        return models
    }

    static let defaultWhisperModel = "ggml-small.bin"

    static func whisperModelPath(_ name: String) -> URL {
        modelsDir.appendingPathComponent(name)
    }

    static func mtModelDir(from lang: Lang) -> URL {
        modelsDir.appendingPathComponent(lang.mtModelDirName, isDirectory: true)
    }

    static func mtModelInstalled(from lang: Lang) -> Bool {
        FileManager.default.fileExists(atPath: mtModelDir(from: lang).appendingPathComponent("model.bin").path)
            && FileManager.default.fileExists(atPath: mtModelDir(from: lang).appendingPathComponent("source.spm").path)
    }

    /// Everything the current configuration needs, or a user-facing
    /// description of what's missing.
    static func validate(whisperModel: String, from lang: Lang) -> String? {
        var missing: [String] = []
        if (try? NativeLib.open()) == nil {
            missing.append("native library (\(NativeLib.libraryFileName))")
        }
        if !FileManager.default.fileExists(atPath: whisperModelPath(whisperModel).path) {
            missing.append("whisper model \(whisperModel)")
        }
        if !mtModelInstalled(from: lang) {
            missing.append("translation model \(lang.mtModelDirName)")
        }
        guard !missing.isEmpty else { return nil }
        return "Missing: " + missing.joined(separator: ", ")
            + ".\nRun scripts/setup.sh (see README) to install into\n\(modelsDir.path)"
    }
}

/// Adapters connecting the native services to the engine's protocols.
final class WhisperService: TranscribingService {
    private let stt: SpeechToText
    private let threads: Int32

    init(lib: NativeLib, modelPath: String, useGPU: Bool, threads: Int32) throws {
        self.stt = try SpeechToText(lib: lib, modelPath: modelPath, useGPU: useGPU)
        self.threads = threads
    }

    func transcribe(samples: [Float], language: String) throws -> SttResult {
        try stt.transcribe(samples: samples, language: language, threads: threads)
    }
}

final class OpusMTService: TranslatingService {
    private let translator: Translator
    private let beamSize: Int32

    init(lib: NativeLib, modelDir: String, beamSize: Int32) throws {
        self.translator = try Translator(lib: lib, modelDir: modelDir)
        self.beamSize = beamSize
    }

    func translate(_ text: String) throws -> String {
        try translator.translate(text, beamSize: beamSize)
    }
}
#endif
