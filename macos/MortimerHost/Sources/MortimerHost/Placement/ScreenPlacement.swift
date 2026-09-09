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
//   - 2026-09-05: a window the USER has moved or resized since we last
//     placed it is left alone by every later reposition() — opening the
//     other auxiliary window (or a screens-changed notification) used to
//     snap a hand-sized display window back to its 60% slot ("the
//     popped-out window snaps back to slot size", Larry, live). The
//     placed frame is remembered per window; a mismatch means the user
//     adjusted it and now owns it.

import AppKit
import os

private let logger = Logger(subsystem: "com.mortimer.host", category: "screen-placement")

@MainActor
final class ScreenPlacement {
    static let shared = ScreenPlacement()

    private var observing = false
    /// The frame WE last gave each window. Compared against the live frame
    /// on the next reposition: equal (within `frameTolerance`) means still
    /// ours to move; different means the user took over.
    private var placedFrames: [HostWindowKind: NSRect] = [:]

    private init() {}

    /// Pure: whether a live window frame still matches the one placement
    /// set (AppKit can round by a point when a screen's scale changes).
    /// nonisolated: no actor state involved, and a default argument is
    /// evaluated in the CALLER's context — an isolated `frameTolerance`
    /// there is a Swift 6 error.
    nonisolated static func isUserAdjusted(live: NSRect, placed: NSRect?, tolerance: CGFloat = frameTolerance) -> Bool {
        guard let placed else { return false }
        return abs(live.minX - placed.minX) > tolerance
            || abs(live.minY - placed.minY) > tolerance
            || abs(live.width - placed.width) > tolerance
            || abs(live.height - placed.height) > tolerance
    }
    nonisolated static let frameTolerance: CGFloat = 2

    /// A window that is no longer on screen forgets its placement, so the
    /// next open is placed fresh rather than treated as user-adjusted.
    private func forgetClosed() {
        for kind in placedFrames.keys where window(kind: kind) == nil {
            placedFrames[kind] = nil
        }
    }

    private func place(_ window: NSWindow, kind: HostWindowKind, frame: NSRect, label: String) {
        if Self.isUserAdjusted(live: window.frame, placed: placedFrames[kind]) {
            logger.debug("reposition: \(kind.rawValue, privacy: .public) is user-adjusted — leaving it (\(label, privacy: .public))")
            return
        }
        window.setFrame(frame, display: true)
        placedFrames[kind] = window.frame   // what AppKit actually applied
    }

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

    private func fill(_ window: NSWindow, kind: HostWindowKind, on screen: NSScreen) {
        place(window, kind: kind, frame: screen.visibleFrame, label: "fill")
    }

    private func slot(_ window: NSWindow, kind: HostWindowKind, on screen: NSScreen, left: Bool) {
        let f = screen.visibleFrame
        let width = f.width * (left ? 0.6 : 0.4)
        let x = left ? f.minX : f.minX + f.width * 0.6
        place(window, kind: kind,
              frame: NSRect(x: x, y: f.minY, width: width, height: f.height),
              label: left ? "slot-left" : "slot-right")
    }

    /// Called on every openWindow (so opening a second window
    /// repositions the first) and on a screens-changed notification.
    /// A user-adjusted window is skipped (see the header note).
    func reposition() {
        forgetClosed()
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
            fill(d, kind: .display, on: ext[0])
        case let (nil, .some(dr)):
            logger.debug("reposition: filling drawer-only onto \(ext.count) extended screen(s)")
            fill(dr, kind: .drawer, on: ext[0])
        case let (.some(d), .some(dr)):
            if ext.count >= 2 {
                logger.debug("reposition: two+ extended screens — display and drawer each fill one")
                fill(d, kind: .display, on: ext[0])
                fill(dr, kind: .drawer, on: ext[1])
            } else {
                logger.debug("reposition: one extended screen — splitting display 60% / drawer 40%")
                slot(d, kind: .display, on: ext[0], left: true)
                slot(dr, kind: .drawer, on: ext[0], left: false)
            }
        }
    }
}
