#if os(macOS)
import SwiftUI

@main
struct TalmaciApp: App {
    @StateObject private var session = SessionController()

    var body: some Scene {
        WindowGroup("Talmaci") {
            ContentView()
                .environmentObject(session)
                .frame(minWidth: 720, minHeight: 440)
        }
        .windowResizability(.contentSize)

        Settings {
            SettingsView()
                .environmentObject(session)
        }
    }
}
#else
// The SwiftUI app only exists on macOS; this stub keeps `swift build`
// working on Linux, where only TalmaciCore (and its tests) matter.
@main
struct TalmaciLinuxStub {
    static func main() {
        print("Talmaci is a macOS app. On Linux, use talmaci-cli (see native/).")
    }
}
#endif
