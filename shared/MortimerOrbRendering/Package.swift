// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "MortimerOrbRendering",
    platforms: [.macOS(.v13), .iOS(.v17)],
    products: [.library(name: "MortimerOrbRendering", targets: ["MortimerOrbRendering"])],
    targets: [
        .target(name: "MortimerOrbRendering", swiftSettings: [.swiftLanguageMode(.v5)]),
        .testTarget(name: "MortimerOrbRenderingTests", dependencies: ["MortimerOrbRendering"]),
    ]
)
