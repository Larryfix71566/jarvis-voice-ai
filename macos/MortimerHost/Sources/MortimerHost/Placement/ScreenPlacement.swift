// ScreenPlacement.swift
// Ported from macos/MortimerShell/Sources/MortimerShell/ScreenPlacement.swift
// (§3 N15) — DP8 semantics UNCHANGED, two mechanical edits:
// ShellWindowKind -> HostWindowKind, findShellWindow -> findHostWindow
// (WindowLookup.swift, this directory). MortimerHost opens only ONE
// window in this plan (N2), so this port is not wired into
// MortimerHostApp/HostView yet — it lives here because this is the tree
// T1.3 grows from, and the 60/40 split, the visibleFrame (not frame)
// choice, and the "no extended screen -> do nothing" rule are each a
// decision Larry already lives with in MortimerShell and should not be
// re-derived later.
//
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
import os

private let logger = Logger(subsystem: "com.mortimer.host", category: "screen-placement")

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
        ) { _ in
            Task { @MainActor in
                ScreenPlacement.shared.reposition()
            }
        }
    }

    /// Every screen that does not host the console window, in NSScreen's
    /// stable order.
    private func extendedScreens() -> [NSScreen] {
        guard let consoleScreen = consoleWindow()?.screen else { return Array(NSScreen.screens.dropFirst()) }
        return NSScreen.screens.filter { $0 != consoleScreen }
    }

    private func window(kind: HostWindowKind) -> NSWindow? {
        findHostWindow(kind: kind)
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
        guard !ext.isEmpty else {
            logger.debug("reposition: no extended screen detected — leaving windows as placed")
            return
        }

        let display = window(kind: .display)
        let drawer = window(kind: .drawer)

        switch (display, drawer) {
        case (nil, nil):
            logger.debug("reposition: extended screen present but neither display nor drawer found")
            return
        case let (.some(d), nil):
            logger.debug("reposition: filling display-only onto \(ext.count) extended screen(s)")
            fill(d, on: ext[0])
        case let (nil, .some(dr)):
            logger.debug("reposition: filling drawer-only onto \(ext.count) extended screen(s)")
            fill(dr, on: ext[0])
        case let (.some(d), .some(dr)):
            if ext.count >= 2 {
                logger.debug("reposition: two+ extended screens — display and drawer each fill one")
                fill(d, on: ext[0])
                fill(dr, on: ext[1])
            } else {
                logger.debug("reposition: one extended screen — splitting display 60% / drawer 40%")
                slot(d, on: ext[0], left: true)
                slot(dr, on: ext[0], left: false)
            }
        }
    }
}
