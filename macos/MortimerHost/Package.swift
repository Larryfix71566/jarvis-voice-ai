// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MortimerHost",
    platforms: [.macOS(.v26)],
    dependencies: [
        .package(path: "../JarvisKit"),
    ],
    targets: [
        .executableTarget(
            name: "MortimerHost",
            dependencies: ["JarvisKit"]
        ),
    ]
)
