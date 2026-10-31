// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "MortimerPhoneCore",
    platforms: [.macOS(.v13), .iOS(.v17)],
    products: [
        .library(name: "MortimerPhoneCore", targets: ["MortimerPhoneCore"]),
    ],
    targets: [
        .target(name: "MortimerPhoneCore"),
        .testTarget(name: "MortimerPhoneCoreTests", dependencies: ["MortimerPhoneCore"]),
    ]
)
