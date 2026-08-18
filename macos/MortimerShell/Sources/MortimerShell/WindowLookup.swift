// WindowLookup.swift
// S2 (MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md): shared, robust
// NSWindow lookup by ShellWindowKind — one implementation used by BOTH
// ShellController (focus-on-open) and ScreenPlacement (positioning), so a
// lookup bug can no longer exist in only one of them (same discipline the
// shell already applies to WindowLookup's sibling concerns).
//
// The previous lookup (`window.identifier?.rawValue == kind.rawValue`,
// exact equality) was the prime suspect for why placement and hot-plug
// relocation did nothing even after S1's name-contract fix: SwiftUI's
// WindowGroup/Window scenes do not reliably hand NSWindow.identifier the
// bare scene id verbatim on every macOS version — it can come back
// decorated (observed shape varies; see the logged fallback-rule below,
// which the first real run should confirm or correct). Three rules are
// tried in order, from most to least specific, and every lookup logs
// which rule (if any) matched — S3's silent-failure fix — so a future
// mismatch is a one-line Console.app diagnosis instead of another
// multi-hour investigation.

import AppKit
import os

private let logger = Logger(subsystem: "com.mortimer.shell", category: "window-lookup")

private let windowTitles: [ShellWindowKind: String] = [
    .console: "Mortimer",
    .display: "Mortimer Display",
    .drawer: "Mortimer Drawer",
]

/// Finds the live (visible) NSWindow for a given shell window kind, or nil
/// if none is currently open. Logs which matching rule succeeded (or that
/// none did) at debug level.
func findShellWindow(kind: ShellWindowKind) -> NSWindow? {
    let windows = NSApp.windows

    // Rule 1: exact identifier match (the ideal, documented case).
    if let w = windows.first(where: { $0.identifier?.rawValue == kind.rawValue && $0.isVisible }) {
        logger.debug("findShellWindow(\(kind.rawValue, privacy: .public)): matched by exact identifier")
        return w
    }

    // Rule 2: identifier prefix match — covers a decorated identifier
    // such as "display-AppWindow-1" that SwiftUI may hand back instead of
    // the bare scene id.
    if let w = windows.first(where: {
        ($0.identifier?.rawValue.hasPrefix(kind.rawValue + "-") ?? false) && $0.isVisible
    }) {
        logger.debug("findShellWindow(\(kind.rawValue, privacy: .public)): matched by identifier prefix")
        return w
    }

    // Rule 3: window title match — the scene's own title (MortimerShellApp
    // .swift's WindowGroup/Window titles), a stable fallback that does not
    // depend on identifier formatting at all.
    if let title = windowTitles[kind],
       let w = windows.first(where: { $0.title == title && $0.isVisible }) {
        logger.debug("findShellWindow(\(kind.rawValue, privacy: .public)): matched by title")
        return w
    }

    logger.debug("findShellWindow(\(kind.rawValue, privacy: .public)): no match (window not open?)")
    return nil
}
