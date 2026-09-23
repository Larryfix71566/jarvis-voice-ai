import Foundation

/// Closed layout contract shared by every native window. Unknown persisted
/// values fail safe to the adaptive layout instead of accidentally selecting
/// a newer composition.
enum InterfaceLayoutVersion {
    static func resolve(_ raw: Int) -> Int {
        switch raw {
        case 0, 1, 2: return raw
        default: return 1
        }
    }
}
