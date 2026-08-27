// WindowLookup.swift
// Ported from macos/MortimerShell/Sources/MortimerShell/WindowLookup.swift
// (§3 N15) — mechanical rename only: ShellWindowKind -> HostWindowKind,
// findShellWindow -> findHostWindow. MortimerHost opens only ONE window
// in this plan (N2), so this port is currently unused by
// MortimerHostApp/HostView; it lives here because this is the tree
// T1.3 grows from, and porting it twice (once here, once later into the
// real app) is how the two copies would diverge. The original three-rule
// lookup and its reasoning are preserved verbatim below.
//
// The previous lookup (`window.identifier?.rawValue == kind.rawValue`,
// exact equality) was the prime suspect for why placement and hot-plug
// relocation did nothing even after a name-contract fix: SwiftUI's
// WindowGroup/Window scenes do not reliably hand NSWindow.identifier the
// bare scene id verbatim on every macOS version — it can come back
// decorated. Three rules are tried in order, from most to least
// specific, and every lookup logs which rule (if any) matched, so a
// future mismatch is a one-line Console.app diagnosis.

import AppKit
import os

private let logger = Logger(subsystem: "com.mortimer.host", category: "window-lookup")

enum HostWindowKind: String {
    case console, display, drawer
}

private let windowTitles: [HostWindowKind: String] = [
    .console: "Mortimer",
    .display: "Mortimer Display",
    .drawer: "Mortimer Drawer",
]

/// Finds the live (visible) NSWindow for a given host window kind, or nil
/// if none is currently open. Logs which matching rule succeeded (or that
/// none did) at debug level.
func findHostWindow(kind: HostWindowKind) -> NSWindow? {
    let windows = NSApp.windows

    // Rule 1: exact identifier match (the ideal, documented case).
    if let w = windows.first(where: { $0.identifier?.rawValue == kind.rawValue && $0.isVisible }) {
        logger.debug("findHostWindow(\(kind.rawValue, privacy: .public)): matched by exact identifier")
        return w
    }

    // Rule 2: identifier prefix match — covers a decorated identifier
    // such as "display-AppWindow-1" that SwiftUI may hand back instead of
    // the bare scene id.
    if let w = windows.first(where: {
        ($0.identifier?.rawValue.hasPrefix(kind.rawValue + "-") ?? false) && $0.isVisible
    }) {
        logger.debug("findHostWindow(\(kind.rawValue, privacy: .public)): matched by identifier prefix")
        return w
    }

    // Rule 3: window title match — the scene's own title, a stable
    // fallback that does not depend on identifier formatting at all.
    if let title = windowTitles[kind],
       let w = windows.first(where: { $0.title == title && $0.isVisible }) {
        logger.debug("findHostWindow(\(kind.rawValue, privacy: .public)): matched by title")
        return w
    }

    logger.debug("findHostWindow(\(kind.rawValue, privacy: .public)): no match (window not open?)")
    return nil
}
