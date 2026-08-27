// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "JarvisKit",
    platforms: [.macOS(.v26), .iOS(.v26)],
    products: [
        .library(name: "JarvisKit", targets: ["JarvisKit"]),
    ],
    dependencies: [
        // BRANCH B (default). Replace this block per §5 step 6 only if the
        // probe in step 2 passed. Do not have both.
        .package(url: "https://github.com/stasel/WebRTC.git", from: "120.0.0"),
    ],
    targets: [
        .target(
            name: "JarvisKit",
            dependencies: [.product(name: "WebRTC", package: "WebRTC")]
            // Swift 5 language mode (tools 6.0 default). NOT .swiftLanguageMode(.v6):
            // review F5 — the implementer cannot compile here (§0.3), and strict
            // concurrency under .v6 would force design decisions this plan does not
            // contain (a non-isolated deinit calling a @MainActor method; Sendable
            // on protocols whose conformers hold RTCPeerConnection). The package
            // builds with concurrency *warnings*, not errors. A later plan that can
            // compile may adopt .v6 and resolve them; that is not this plan's risk.
        ),
        .testTarget(
            name: "JarvisKitTests",
            dependencies: ["JarvisKit"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
