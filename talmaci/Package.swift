// swift-tools-version: 5.9
import PackageDescription

// TalmaciCore is pure Foundation (builds and tests on Linux too — CI runs the
// logic tests there). The Talmaci executable target is the macOS SwiftUI app;
// its sources are wrapped in #if os(macOS) so `swift build`/`swift test` still
// succeed on Linux.
let package = Package(
    name: "Talmaci",
    platforms: [
        .macOS(.v14)
    ],
    targets: [
        .target(name: "TalmaciCore"),
        .executableTarget(
            name: "Talmaci",
            dependencies: ["TalmaciCore"]
        ),
        .testTarget(
            name: "TalmaciCoreTests",
            dependencies: ["TalmaciCore"]
        ),
    ]
)
