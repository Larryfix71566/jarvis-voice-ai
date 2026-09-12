// swift-tools-version: 6.2
import PackageDescription

// MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md §3.3 / §7 — the Voice Processing
// I/O echo bench. A debug-only tool (it imports JarvisKit @testable to
// reach AudioEngineIO), run on the deployment Mac:
//
//   swift run --package-path macos/VPIOBench vpio-bench [--seconds 8] [--wake] [--out DIR]
//
// Never shipped, never part of the app or the sandbox checks.
let package = Package(
    name: "VPIOBench",
    platforms: [.macOS(.v26)],
    dependencies: [
        .package(path: "../JarvisKit"),
    ],
    targets: [
        .executableTarget(
            name: "vpio-bench",
            dependencies: [.product(name: "JarvisKit", package: "JarvisKit")],
            path: "Sources/VPIOBench",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
