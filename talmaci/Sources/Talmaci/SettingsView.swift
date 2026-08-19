#if os(macOS)
import SwiftUI
import TalmaciCore

struct SettingsView: View {
    @EnvironmentObject private var session: SessionController

    @AppStorage(Prefs.whisperModel) private var whisperModel = ModelStore.defaultWhisperModel
    @AppStorage(Prefs.useGPU) private var useGPU = true
    @AppStorage(Prefs.threads) private var threads = 4
    @AppStorage(Prefs.beamSize) private var beamSize = 2
    @AppStorage(Prefs.tickMs) private var tickMs = 600

    @State private var installedModels: [String] = []

    var body: some View {
        Form {
            Section("Speech recognition") {
                Picker("Whisper model", selection: $whisperModel) {
                    ForEach(installedModels, id: \.self) { name in
                        Text(label(for: name)).tag(name)
                    }
                    if !installedModels.contains(whisperModel) {
                        Text("\(whisperModel) (missing)").tag(whisperModel)
                    }
                }
                .help("Larger models are more accurate but slower. Watch the latency readout in the footer; keep total under 500 ms.")

                Toggle("Use GPU (Metal)", isOn: $useGPU)
                Stepper("CPU threads: \(threads)", value: $threads, in: 1...16)
            }

            Section("Translation") {
                Stepper("Beam size: \(beamSize)", value: $beamSize, in: 1...5)
                    .help("1 is fastest; larger values can read slightly better.")
            }

            Section("Streaming") {
                Stepper("Update interval: \(tickMs) ms", value: $tickMs, in: 200...2000, step: 100)
                    .help("How often the transcript refreshes. Smaller = snappier but more CPU.")
            }

            Section("Models") {
                LabeledContent("Folder", value: ModelStore.modelsDir.path)
                HStack {
                    Button("Reveal in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting([ModelStore.modelsDir])
                    }
                    Button("Rescan") { rescan() }
                }
                Text("Install or update models with scripts/setup.sh — see the README. Changes apply on the next Start.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 480)
        .onAppear { rescan() }
    }

    private func rescan() {
        installedModels = ModelStore.installedWhisperModels()
        session.refreshSetupStatus()
    }

    private func label(for model: String) -> String {
        var name = model
        name.trimPrefix("ggml-")
        if name.hasSuffix(".bin") { name.removeLast(4) }
        return model == ModelStore.defaultWhisperModel ? "\(name) (default)" : name
    }
}
#endif
