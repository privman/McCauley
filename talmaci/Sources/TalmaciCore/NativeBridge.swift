import Foundation

#if canImport(Glibc)
import Glibc
#endif

/// Errors from the native (whisper/CTranslate2) layer.
public enum NativeError: Error, CustomStringConvertible {
    case libraryNotFound(searched: [String])
    case symbolMissing(String)
    case loadFailed(String)
    case callFailed(String)

    public var description: String {
        switch self {
        case .libraryNotFound(let searched):
            return "native library not found; searched: \(searched.joined(separator: ", "))"
        case .symbolMissing(let s): return "native library is missing symbol \(s)"
        case .loadFailed(let m): return m
        case .callFailed(let m): return m
        }
    }
}

/// dlopen-based binding to libtalmaci_native. Keeping this dynamic means the
/// Swift package builds with no native dependencies at all; the library is
/// only required at runtime.
public final class NativeLib {
    public static var libraryFileName: String {
        #if os(macOS)
        return "libtalmaci_native.dylib"
        #else
        return "libtalmaci_native.so"
        #endif
    }

    /// Locations tried by `open(searchPaths:)`, in order. `extra` come first.
    public static func defaultSearchPaths(extra: [String] = []) -> [String] {
        var paths = extra
        if let env = ProcessInfo.processInfo.environment["TALMACI_NATIVE_LIB"], !env.isEmpty {
            paths.append(env)
        }
        let name = libraryFileName
        if let exe = Bundle.main.executableURL {
            // App bundle layout: Talmaci.app/Contents/MacOS/Talmaci,
            // library in Talmaci.app/Contents/Frameworks/.
            let frameworks = exe.deletingLastPathComponent().deletingLastPathComponent()
                .appendingPathComponent("Frameworks").appendingPathComponent(name)
            paths.append(frameworks.path)
            // Development: next to the executable.
            paths.append(exe.deletingLastPathComponent().appendingPathComponent(name).path)
        }
        // Development: from a checkout, cwd = talmaci/.
        paths.append("native/build/\(name)")
        return paths
    }

    let handle: UnsafeMutableRawPointer
    public let path: String

    typealias VersionFn = @convention(c) () -> UnsafePointer<CChar>?
    typealias SttLoadFn = @convention(c) (UnsafePointer<CChar>?, Int32, UnsafeMutablePointer<CChar>?, Int32) -> OpaquePointer?
    typealias SttFreeFn = @convention(c) (OpaquePointer?) -> Void
    typealias SttTranscribeFn = @convention(c) (OpaquePointer?, UnsafePointer<Float>?, Int32, UnsafePointer<CChar>?, Int32, UnsafeMutablePointer<CChar>?, Int32) -> UnsafeMutablePointer<CChar>?
    typealias MtLoadFn = @convention(c) (UnsafePointer<CChar>?, UnsafeMutablePointer<CChar>?, Int32) -> OpaquePointer?
    typealias MtFreeFn = @convention(c) (OpaquePointer?) -> Void
    typealias MtTranslateFn = @convention(c) (OpaquePointer?, UnsafePointer<CChar>?, Int32, UnsafeMutablePointer<CChar>?, Int32) -> UnsafeMutablePointer<CChar>?
    typealias StrFreeFn = @convention(c) (UnsafeMutablePointer<CChar>?) -> Void

    let fnVersion: VersionFn
    let fnSttLoad: SttLoadFn
    let fnSttFree: SttFreeFn
    let fnSttTranscribe: SttTranscribeFn
    let fnMtLoad: MtLoadFn
    let fnMtFree: MtFreeFn
    let fnMtTranslate: MtTranslateFn
    let fnStrFree: StrFreeFn

    public var version: String {
        guard let p = fnVersion() else { return "unknown" }
        return String(cString: p)
    }

    public static func open(searchPaths: [String]? = nil) throws -> NativeLib {
        let paths = searchPaths ?? defaultSearchPaths()
        for p in paths where FileManager.default.fileExists(atPath: p) {
            return try NativeLib(path: p)
        }
        throw NativeError.libraryNotFound(searched: paths)
    }

    public init(path: String) throws {
        guard let h = dlopen(path, RTLD_NOW) else {
            let msg = dlerror().map { String(cString: $0) } ?? "dlopen failed"
            throw NativeError.loadFailed("\(path): \(msg)")
        }
        self.handle = h
        self.path = path

        func sym<T>(_ name: String, as type: T.Type) throws -> T {
            guard let s = dlsym(h, name) else { throw NativeError.symbolMissing(name) }
            return unsafeBitCast(s, to: T.self)
        }
        fnVersion = try sym("tn_version", as: VersionFn.self)
        fnSttLoad = try sym("tn_stt_load", as: SttLoadFn.self)
        fnSttFree = try sym("tn_stt_free", as: SttFreeFn.self)
        fnSttTranscribe = try sym("tn_stt_transcribe", as: SttTranscribeFn.self)
        fnMtLoad = try sym("tn_mt_load", as: MtLoadFn.self)
        fnMtFree = try sym("tn_mt_free", as: MtFreeFn.self)
        fnMtTranslate = try sym("tn_mt_translate", as: MtTranslateFn.self)
        fnStrFree = try sym("tn_str_free", as: StrFreeFn.self)
    }
}

/// One segment of transcribed speech, times in milliseconds relative to the
/// start of the analyzed window.
public struct SttSegment: Codable, Equatable, Sendable {
    public let t0: Int64
    public let t1: Int64
    public let text: String

    public init(t0: Int64, t1: Int64, text: String) {
        self.t0 = t0
        self.t1 = t1
        self.text = text
    }
}

public struct SttResult: Codable, Equatable, Sendable {
    public let segments: [SttSegment]
    public let elapsedMs: Int64

    enum CodingKeys: String, CodingKey {
        case segments
        case elapsedMs = "elapsed_ms"
    }

    public init(segments: [SttSegment], elapsedMs: Int64) {
        self.segments = segments
        self.elapsedMs = elapsedMs
    }

    /// All segment texts joined, whitespace-normalized.
    public var text: String {
        segments.map { $0.text.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }
}

/// Whisper speech-to-text over the native bridge.
public final class SpeechToText {
    private let lib: NativeLib
    private let handle: OpaquePointer

    public init(lib: NativeLib, modelPath: String, useGPU: Bool) throws {
        var err = [CChar](repeating: 0, count: 512)
        guard let h = modelPath.withCString({ mp in
            lib.fnSttLoad(mp, useGPU ? 1 : 0, &err, 512)
        }) else {
            throw NativeError.loadFailed(String(cString: err))
        }
        self.lib = lib
        self.handle = h
    }

    deinit { lib.fnSttFree(handle) }

    /// `samples` must be 16 kHz mono float32.
    public func transcribe(samples: [Float], language: String, threads: Int32) throws -> SttResult {
        var err = [CChar](repeating: 0, count: 512)
        let jsonPtr = samples.withUnsafeBufferPointer { buf in
            language.withCString { lang in
                lib.fnSttTranscribe(handle, buf.baseAddress, Int32(buf.count), lang, threads, &err, 512)
            }
        }
        guard let jsonPtr else { throw NativeError.callFailed(String(cString: err)) }
        defer { lib.fnStrFree(jsonPtr) }
        let data = Data(bytes: jsonPtr, count: strlen(jsonPtr))
        do {
            return try JSONDecoder().decode(SttResult.self, from: data)
        } catch {
            throw NativeError.callFailed("bad JSON from native layer: \(error)")
        }
    }
}

/// OPUS-MT translation over the native bridge.
public final class Translator {
    private let lib: NativeLib
    private let handle: OpaquePointer

    public init(lib: NativeLib, modelDir: String) throws {
        var err = [CChar](repeating: 0, count: 512)
        guard let h = modelDir.withCString({ md in
            lib.fnMtLoad(md, &err, 512)
        }) else {
            throw NativeError.loadFailed(String(cString: err))
        }
        self.lib = lib
        self.handle = h
    }

    deinit { lib.fnMtFree(handle) }

    public func translate(_ text: String, beamSize: Int32 = 2) throws -> String {
        var err = [CChar](repeating: 0, count: 512)
        let outPtr = text.withCString { t in
            lib.fnMtTranslate(handle, t, beamSize, &err, 512)
        }
        guard let outPtr else { throw NativeError.callFailed(String(cString: err)) }
        defer { lib.fnStrFree(outPtr) }
        return String(cString: outPtr)
    }
}
