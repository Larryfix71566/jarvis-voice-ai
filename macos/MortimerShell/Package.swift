// swift-tools-version: 5.9
// Mortimer shell (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part B).
//
// Swift Package Manager executable target, not a hand-authored .xcodeproj:
// Xcode opens a folder containing Package.swift as a first-class project
// (File > Open... on this directory, or `open Package.swift`), which is a
// far more reliable way to hand this off than authoring a .pbxproj by hand
// outside Xcode itself — this file was written and reviewed on a Linux
// sandbox with no Xcode available to validate a project file's XML/plist
// syntax. See README.md for the B0 spike this must pass before Part B
// proper (native placement, self-edit deny-list) is trusted.
import PackageDescription

// Info.plist keys (NSMicrophoneUsageDescription) and entitlements
// (com.apple.security.device.audio-input, network client) are NOT set via
// this file — SPM executables don't have a physical-file Info.plist
// mechanism Xcode will honor automatically. See README.md's "First open
// in Xcode" section for the two settings to apply by hand in the target's
// Signing & Capabilities / Info tabs before the B0 mic-capture question
// can even be tested. templates/Info.plist.template and
// templates/MortimerShell.entitlements.template document the exact keys.
let package = Package(
    name: "MortimerShell",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "MortimerShell",
            path: "Sources/MortimerShell"
        )
    ]
)
