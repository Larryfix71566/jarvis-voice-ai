// ScreenPlacement.swift
// B3 — the shell observes NSScreen.screens + didChangeScreenParameters-
// Notification and applies DP8's exact semantics natively (ported from
// web/src/popoutWindow.ts's repositionAll/wireScreensChange, which this
// file supersedes for shell-hosted windows — the web-side Window
// Management API path short-circuits when window.mortimerShell exists,
// see popoutWindow.ts's B3 comment, so double-placement is impossible by
// construction rather than by convention):
//   - one auxiliary window (display OR drawer alone) -> fills the first
//     non-console screen
//   - both display and drawer open, one extended screen -> display left
//     60% / drawer right 40%
//   - both open, two-or-more extended screens -> each fills its own
//   - a monitor plugged in later relocates live windows (screens-changed
//     notification)
//   - no extended screen -> windows stay wherever AppKit placed them
//     beside the console (no explicit repositioning needed)

import AppKit

@MainActor
final class ScreenPlacement {
    static let shared = ScreenPlacement()

    private var observing = false

    private init() {}

    func startObserving() {
        guard !observing else { return }
        observing = true
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.reposition()
        }
    }

    /// Every screen that does not host the console window, in NSScreen's
    /// stable order (mirrors popoutWindow.ts's extendedScreens()).
    private func extendedScreens() -> [NSScreen] {
        guard let consoleScreen = consoleWindow()?.screen else { return Array(NSScreen.screens.dropFirst()) }
        return NSScreen.screens.filter { $0 != consoleScreen }
    }

    private func window(kind: ShellWindowKind) -> NSWindow? {
        NSApp.windows.first { $0.identifier?.rawValue == kind.rawValue && $0.isVisible }
    }

    private func consoleWindow() -> NSWindow? {
        window(kind: .console)
    }

    private func fill(_ window: NSWindow, on screen: NSScreen) {
        window.setFrame(screen.visibleFrame, display: true)
    }

    private func slot(_ window: NSWindow, on screen: NSScreen, left: Bool) {
        let f = screen.visibleFrame
        let width = f.width * (left ? 0.6 : 0.4)
        let x = left ? f.minX : f.minX + f.width * 0.6
        window.setFrame(NSRect(x: x, y: f.minY, width: width, height: f.height), display: true)
    }

    /// Called on every openWindow (so opening a second window
    /// repositions the first) and on a screens-changed notification.
    func reposition() {
        let ext = extendedScreens()
        guard !ext.isEmpty else { return } // no extra monitor — leave as AppKit placed it

        let display = window(kind: .display)
        let drawer = window(kind: .drawer)

        switch (display, drawer) {
        case (nil, nil):
            return
        case let (.some(d), nil):
            fill(d, on: ext[0])
        case let (nil, .some(dr)):
            fill(dr, on: ext[0])
        case let (.some(d), .some(dr)):
            if ext.count >= 2 {
                fill(d, on: ext[0])
                fill(dr, on: ext[1])
            } else {
                slot(d, on: ext[0], left: true)
                slot(dr, on: ext[0], left: false)
            }
        }
    }
}
