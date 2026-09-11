// WindowLookup.swift
// Resolves the console, display and drawer scenes for placement and recovery.
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

enum HostWindowKind: String, Codable, CaseIterable, Sendable {
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
///
/// @MainActor: NSApp/NSWindow are main-actor-isolated in the macOS 26
/// SDK, and every caller (ScreenPlacement) is already on the main actor.
/// The MortimerShell original predates that annotation appearing in the
/// SDK; without it here, `swift build` emits eight isolation warnings.
@MainActor
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
