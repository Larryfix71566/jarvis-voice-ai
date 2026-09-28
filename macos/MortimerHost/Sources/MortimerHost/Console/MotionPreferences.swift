import SwiftUI

/// Optional app-level override for deterministic rendering and accessibility
/// tests. Normal app views leave this unset and follow the system preference.
private struct MortimerReducedMotionOverrideKey: EnvironmentKey {
    static let defaultValue: Bool? = nil
}

extension EnvironmentValues {
    /// Mortimer's effective motion policy. Views inherit the system setting
    /// unless a host explicitly supplies an app-level override.
    var mortimerReduceMotion: Bool {
        get { self[MortimerReducedMotionOverrideKey.self] ?? accessibilityReduceMotion }
        set { self[MortimerReducedMotionOverrideKey.self] = newValue }
    }

}
