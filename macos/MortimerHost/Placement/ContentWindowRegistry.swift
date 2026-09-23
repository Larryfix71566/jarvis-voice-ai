import AppKit

/// Value-addressed window registry. Content identity is independent of the
/// current display, so unplug/reconnect can recover the same panel.
@MainActor
final class ContentWindowRegistry {
    private var windows: [String: NSWindow] = [:]

    func register(_ window: NSWindow, id: String) { windows[id] = window }
    func unregister(id: String) { windows.removeValue(forKey: id) }
    func window(id: String) -> NSWindow? { windows[id] }
    func closeAll() { windows.values.forEach { $0.orderOut(nil) }; windows.removeAll() }
}
