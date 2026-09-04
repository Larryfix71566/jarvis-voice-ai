// SpikeScreenPlacement.swift
// T1.1 — the DP8 placement algorithm (§3 N15), exercised here with the
// spike's two windows treated as (display, drawer) so both the 60/40
// split rule and the one-per-screen rule get exercised. This is the
// SAME algorithm MortimerHost's ScreenPlacement.swift ports for real —
// this copy is throwaway (deleted with the rest of GlassSpike after
// G1(a); §5 step 15), so nothing here is meant to survive.

import AppKit
import os

private let logger = Logger(subsystem: "com.mortimer.glassspike", category: "screen-placement")

enum SpikeWindowKind: String {
    case panelA, panelB
}

@MainActor
final class SpikeScreenPlacement {
    static let shared = SpikeScreenPlacement()

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
                SpikeScreenPlacement.shared.reposition()
            }
        }
    }

    /// Every screen, in NSScreen's stable order. The spike has no
    /// console window to exclude, unlike MortimerHost's port.
    private func extendedScreens() -> [NSScreen] {
        NSScreen.screens
    }

    private static let titles: [SpikeWindowKind: String] = [
        .panelA: "Panel A", .panelB: "Panel B",
    ]

    /// Exact identifier match first (the documented, ideal case); a
    /// title fallback second — SwiftUI's WindowGroup does not reliably
    /// hand NSWindow.identifier the bare scene id verbatim on every
    /// macOS version (the same caveat MortimerHost's WindowLookup.swift,
    /// N15, documents at length for the real port).
    private func window(kind: SpikeWindowKind) -> NSWindow? {
        if let w = NSApp.windows.first(where: { $0.identifier?.rawValue == kind.rawValue && $0.isVisible }) {
            return w
        }
        if let title = Self.titles[kind] {
            return NSApp.windows.first { $0.title == title && $0.isVisible }
        }
        return nil
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

    /// Called after both windows open and on a screens-changed
    /// notification (§8 S4-S6).
    func reposition() {
        let screens = extendedScreens()
        guard !screens.isEmpty else { return }

        let a = window(kind: .panelA)
        let b = window(kind: .panelB)

        switch (a, b) {
        case (nil, nil):
            return
        case let (.some(w), nil):
            fill(w, on: screens[0])
        case let (nil, .some(w)):
            fill(w, on: screens[0])
        case let (.some(wa), .some(wb)):
            if screens.count >= 2 {
                logger.debug("reposition: two+ screens — one window per screen (S4)")
                fill(wa, on: screens[0])
                fill(wb, on: screens[1])
            } else {
                logger.debug("reposition: one screen — 60/40 split (S5)")
                slot(wa, on: screens[0], left: true)
                slot(wb, on: screens[0], left: false)
            }
        }
    }
}
