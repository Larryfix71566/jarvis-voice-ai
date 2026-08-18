// ShellController.swift
// Shared state across all three windows (B0-B3): one WKProcessPool/
// WKWebsiteDataStore so BroadcastChannel and localStorage are shared
// (spike question 2), the reachability check driving the retry screen
// (B4), and window open/focus/placement in response to the injected
// message channel (B2/B3).

import AppKit
import Combine
import SwiftUI
import WebKit
import os

private let logger = Logger(subsystem: "com.mortimer.shell", category: "controller")

enum ShellWindowKind: String {
    case console, display, drawer
}

/// B0 fallback bookkeeping: if the spike's mic-in-WKWebView question
/// fails on Larry's machine, flip this to false and the console window
/// stops loading "/" — see README.md's "If the mic spike fails" section.
/// Left true here since the question is unresolved without a real
/// macOS run; this is the ONE line the fallback touches.
let micCaptureAssumedWorking = true

@MainActor
final class ShellController: ObservableObject {
    /// B0 — WKProcessPool is deprecated since macOS 12: every WKWebView in
    /// an app now shares one web-content process space automatically, which
    /// is exactly the property spike question 2 (BroadcastChannel across
    /// webviews) depends on. Sharing the default WKWebsiteDataStore below
    /// keeps storage/origin state common across the three windows. If the
    /// spike still shows BroadcastChannel NOT crossing WKWebViews, the
    /// predecided fallback (plan B0 item 2) is a WKUserScript-based relay
    /// through WKScriptMessageHandler — see
    /// ShellWebView.useBroadcastRelayFallback, currently inactive.
    let dataStore = WKWebsiteDataStore.default()

    @Published var consoleReachable: Bool = true
    @Published var lastReachabilityCheck: Date = .init()

    private var checkTask: Task<Void, Never>?

    init() {
        checkReachability()
        // A Task created from this @MainActor context inherits the main
        // actor, so self access inside is legal without hopping — cleaner
        // under strict concurrency than Timer + nested Task closures.
        checkTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                self?.checkReachability()
            }
        }
    }

    deinit {
        checkTask?.cancel()
    }

    // B4 — the shell always loads http://127.0.0.1:5173 (the console dev
    // server ./scripts/mortimer.sh starts). Unreachable shows a native
    // retry screen rather than a WKWebView error page.
    private func checkReachability() {
        var request = URLRequest(url: MortimerShellApp.consoleURL)
        request.timeoutInterval = 2.0
        request.httpMethod = "HEAD"
        Task { [weak self] in
            var ok = false
            if let (_, response) = try? await URLSession.shared.data(for: request) {
                let status = (response as? HTTPURLResponse)?.statusCode ?? 500
                ok = status < 500
            }
            self?.consoleReachable = ok
            self?.lastReachabilityCheck = Date()
        }
    }

    func retryNow() {
        checkReachability()
    }

    // B2 — dispatched from ShellBridge (the WKScriptMessageHandler) when
    // a webview posts {cmd: "openWindow", name: "display"|"drawer"}
    // through window.mortimerShell's injected channel. Opening/focusing
    // is native window management; the web page never gets a Window ref
    // (see popoutWindow.ts's shell branch — it returns null and relies
    // on the existing heartbeat-based presence check instead).
    func openWindow(named name: String, environment: OpenWindowAction) {
        // S3 — log every bridge message, including a rejected one. This
        // is the exact spot S1's bug (the web side sending the browser
        // window name instead of the bare role) failed silently before.
        guard let kind = ShellWindowKind(rawValue: name) else {
            logger.error("openWindow: rejected unrecognized name '\(name, privacy: .public)' (expected console/display/drawer)")
            return
        }
        logger.debug("openWindow: opening/focusing \(kind.rawValue, privacy: .public)")
        environment(id: kind.rawValue)
        // S2: shared robust lookup, not exact identifier equality.
        if let window = findShellWindow(kind: kind) {
            window.makeKeyAndOrderFront(nil)
        } else {
            logger.error("openWindow: environment(id:) returned but findShellWindow found nothing for \(kind.rawValue, privacy: .public) — focus skipped")
        }
        ScreenPlacement.shared.reposition()
    }

    // Close-path mirror of openWindow (2026-08-18): dispatched from
    // ShellBridge on {cmd:"closeWindow", name:"display"|"drawer"}. The
    // web side can't close a native window itself, which made the
    // console's pop-in control silently fail inside the shell. The
    // console window is deliberately refused: web code must never be
    // able to close the app's main window.
    func closeWindow(named name: String) {
        guard let kind = ShellWindowKind(rawValue: name) else {
            logger.error("closeWindow: rejected unrecognized name '\(name, privacy: .public)' (expected display/drawer)")
            return
        }
        guard kind != .console else {
            logger.error("closeWindow: refusing to close the console window")
            return
        }
        guard let window = findShellWindow(kind: kind) else {
            logger.error("closeWindow: no live window found for \(kind.rawValue, privacy: .public) — nothing to close")
            return
        }
        logger.debug("closeWindow: closing \(kind.rawValue, privacy: .public)")
        window.close()
    }
}
