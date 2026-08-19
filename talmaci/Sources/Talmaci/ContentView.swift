#if os(macOS)
import SwiftUI
import TalmaciCore

struct ContentView: View {
    @EnvironmentObject private var session: SessionController

    @AppStorage(Prefs.sourceLanguage) private var sourceLanguageRaw = Lang.romanian.rawValue
    @AppStorage(Prefs.useMicrophone) private var useMicrophone = true
    @AppStorage(Prefs.useSystemAudio) private var useSystemAudio = false

    private var sourceLanguage: Lang { Lang(rawValue: sourceLanguageRaw) ?? .romanian }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            if let problem = session.setupProblem, !session.isRunning {
                setupBanner(problem)
            }
            panes
            Divider()
            footer
        }
        .onAppear { session.refreshSetupStatus() }
        .alert("Talmaci", isPresented: errorBinding) {
            Button("OK") { session.dismissError() }
        } message: {
            if case .error(let message) = session.state {
                Text(message)
            }
        }
    }

    private var errorBinding: Binding<Bool> {
        Binding(
            get: {
                if case .error = session.state { return true }
                return false
            },
            set: { if !$0 { session.dismissError() } }
        )
    }

    private var toolbar: some View {
        HStack(spacing: 16) {
            Picker("Audio language", selection: $sourceLanguageRaw) {
                ForEach(Lang.allCases) { lang in
                    Text(lang.displayName).tag(lang.rawValue)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
            .disabled(session.isRunning)
            .help("Language being spoken in the audio")

            Image(systemName: "arrow.right")
                .foregroundStyle(.secondary)

            Text(sourceLanguage.other.displayName)
                .font(.headline)
                .frame(width: 90, alignment: .leading)
                .help("Translation language")

            Spacer()

            Toggle(isOn: $useMicrophone) {
                Label("Microphone", systemImage: "mic")
            }
            .toggleStyle(.checkbox)
            .disabled(session.isRunning)

            Toggle(isOn: $useSystemAudio) {
                Label("System audio", systemImage: "speaker.wave.2")
            }
            .toggleStyle(.checkbox)
            .disabled(session.isRunning)
            .help("Everything the Mac plays (requires System Audio Recording permission)")

            Button(action: toggleRun) {
                Label(session.isRunning ? "Stop" : "Start",
                      systemImage: session.isRunning ? "stop.fill" : "record.circle")
                    .frame(width: 70)
            }
            .keyboardShortcut(.space, modifiers: [.command])
            .buttonStyle(.borderedProminent)
            .tint(session.isRunning ? .red : .accentColor)
            .disabled(session.state == .starting)
        }
        .padding(12)
    }

    private func toggleRun() {
        if session.isRunning {
            session.stop()
        } else {
            session.start()
        }
    }

    private func setupBanner(_ problem: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)
            Text(problem)
                .font(.callout)
                .textSelection(.enabled)
            Spacer()
            Button("Re-check") { session.refreshSetupStatus() }
        }
        .padding(10)
        .background(.yellow.opacity(0.12))
    }

    private var panes: some View {
        HSplitView {
            TranscriptPane(
                title: "Transcript — \(activeSourceLang.displayName)",
                pane: session.transcript,
                placeholder: session.isRunning ? "Listening…" : "Press Start to begin")
            TranscriptPane(
                title: "Translation — \(activeSourceLang.other.displayName)",
                pane: session.translation,
                placeholder: "")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// While running, label panes with the session's language even if the
    /// picker was changed; otherwise follow the picker.
    private var activeSourceLang: Lang {
        session.isRunning ? session.activeLanguage : sourceLanguage
    }

    private var footer: some View {
        HStack(spacing: 16) {
            switch session.state {
            case .running:
                Label("Live", systemImage: "waveform")
                    .foregroundStyle(.green)
            case .starting:
                ProgressView().controlSize(.small)
                Text("Loading models…")
            case .idle, .error:
                Label("Idle", systemImage: "pause.circle")
                    .foregroundStyle(.secondary)
            }

            if session.stats.hasData {
                Text(String(format: "STT %.0f ms · MT %.0f ms · total %.0f ms",
                            session.stats.sttMs, session.stats.mtMs, session.stats.totalMs))
                    .monospacedDigit()
                    .foregroundStyle(session.stats.totalMs <= 500 ? Color.secondary : Color.orange)
                    .help("Processing time per update (target: under 500 ms). Pick a smaller model in Settings if this runs high.")
                Text(String(format: "window %.1f s", session.windowSeconds))
                    .monospacedDigit()
                    .foregroundStyle(.tertiary)
            }

            Spacer()

            Button {
                copyToPasteboard(session.transcript.full)
            } label: {
                Label("Copy transcript", systemImage: "doc.on.doc")
            }
            .disabled(session.transcript.isEmpty)

            Button {
                copyToPasteboard(session.translation.full)
            } label: {
                Label("Copy translation", systemImage: "doc.on.doc.fill")
            }
            .disabled(session.translation.isEmpty)

            Button {
                session.clearTranscript()
            } label: {
                Label("Clear", systemImage: "trash")
            }
            .disabled(session.transcript.isEmpty && session.translation.isEmpty)
        }
        .font(.caption)
        .labelStyle(.titleAndIcon)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private func copyToPasteboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

/// One scrolling text pane: committed text in primary color, the confirmed
/// (stable) tail in primary, and the tentative tail dimmed + italic.
struct TranscriptPane: View {
    let title: String
    let pane: PaneText
    let placeholder: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title)
                .font(.caption.smallCaps())
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    (Text(pane.committed)
                        + Text(pane.committed.isEmpty || pane.confirmed.isEmpty ? "" : " ")
                        + Text(pane.confirmed)
                        + Text((pane.committed.isEmpty && pane.confirmed.isEmpty) || pane.tentative.isEmpty ? "" : " ")
                        + Text(pane.tentative).italic().foregroundStyle(.secondary))
                        .font(.system(size: 16))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                    if pane.isEmpty && !placeholder.isEmpty {
                        Text(placeholder)
                            .foregroundStyle(.tertiary)
                            .padding(12)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .onChange(of: pane) { _, _ in
                    withAnimation(.easeOut(duration: 0.15)) {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
            }
        }
        .frame(minWidth: 240, maxWidth: .infinity, maxHeight: .infinity)
    }
}
#endif
