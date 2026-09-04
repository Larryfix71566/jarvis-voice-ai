// swift-tools-version: 6.2
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
            dependencies: [.product(name: "WebRTC", package: "WebRTC")],
            // Swift 5 language mode, stated EXPLICITLY. Tools version 6.2 is
            // required for the .v26 platform literals above, and 6.x defaults
            // the language mode to .v6 — so this setting is not a no-op, it is
            // the thing keeping review F5 true.
            //
            // Review F5: strict concurrency under .v6 turns three unavoidable
            // situations into errors the implementer would have to design
            // around — a non-isolated `deinit` touching @MainActor state; a
            // `var delegate` requirement on a protocol whose conformer holds
            // non-Sendable RTCPeerConnection/RTCDataChannel; and passing that
            // conformer across an actor boundary in connect()/disconnect().
            // Swift 5 mode reduces all three to warnings, so the declarations
            // this package was written against compile as written. A later
            // plan that can compile may adopt .v6 and resolve them properly.
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "JarvisKitTests",
            dependencies: ["JarvisKit"],
            resources: [
                .copy("Fixtures"),        // CORE §7's eleven AppMessage frames
                .copy("admin-fixtures"),  // APP §8 V0's captured sidecar bodies
                // (not "fixtures" — APFS is case-insensitive and the two
                // names collide inside the test bundle)
            ],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
