// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "GlassSpike",
    platforms: [.macOS(.v26)],
    targets: [
        .executableTarget(
            name: "GlassSpike"
        ),
    ]
)
