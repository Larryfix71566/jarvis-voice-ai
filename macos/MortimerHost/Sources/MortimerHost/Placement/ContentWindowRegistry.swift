import AppKit

/// Value-addressed registry for detachable content windows. Content identity
/// is independent of title or screen, so reconnect/recovery can target the
/// same panel without creating a second renderer.
@MainActor
final class ContentWindowRegistry {
    private(set) var windows: [String: NSWindow] = [:]

    func register(_ window: NSWindow, id: String) {
        guard !id.isEmpty else { return }
        windows[id] = window
    }

    func unregister(id: String) {
        windows.removeValue(forKey: id)
    }

    func window(id: String) -> NSWindow? { windows[id] }

    func closeAll() {
        for window in windows.values { window.orderOut(nil) }
        windows.removeAll()
    }
}
