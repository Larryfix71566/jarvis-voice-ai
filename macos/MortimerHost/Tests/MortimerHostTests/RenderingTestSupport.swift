import AppKit

/// Rendering fixtures keep windows open (`isReleasedWhenClosed = false`) so
/// tests can inspect their accessibility tree and geometry. Detach the hosted
/// tree before closing so repeat-forever SwiftUI animations are cancelled and
/// the fixture does not leak animation drivers into later XCTest cases.
@MainActor
func closeRenderingFixtureWindow(_ window: NSWindow) {
    window.orderOut(nil)
    window.contentView = nil
    window.close()
}
