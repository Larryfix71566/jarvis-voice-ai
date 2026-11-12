import Foundation

/// Layouts 0 and 1 have been retired. Persisted preferences are migrated to
/// the sole Command Console composition; views never branch on this value.
enum InterfaceLayoutVersion {
    static let current = 2
    static let preferenceKey = "mortimer.interface.layoutVersion"

    static func migrate(_ defaults: UserDefaults = .standard) {
        defaults.set(current, forKey: preferenceKey)
    }
}
