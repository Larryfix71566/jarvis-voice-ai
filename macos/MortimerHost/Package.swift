// swift-tools-version: 6.2
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
            dependencies: ["JarvisKit"],
            // Swift 5 language mode, explicit — same reasoning as
            // JarvisKit's Package.swift (CORE review F5): tools 6.x
            // defaults to Swift 6 strict concurrency, which this tree
            // was not written under.
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "MortimerHostTests",
            dependencies: ["MortimerHost"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
