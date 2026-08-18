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

    private var checkTimer: Timer?

    init() {
        checkReachability()
        checkTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.checkReachability() }
        }
    }

    // B4 — the shell always loads http://127.0.0.1:5173 (the console dev
    // server ./scripts/mortimer.sh starts). Unreachable shows a native
    // retry screen rather than a WKWebView error page.
    private func checkReachability() {
        var request = URLRequest(url: MortimerShellApp.consoleURL)
        request.timeoutInterval = 2.0
        request.httpMethod = "HEAD"
        URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
            let ok = error == nil && (response as? HTTPURLResponse)?.statusCode.map { $0 < 500 } ?? false
            Task { @MainActor in
                self?.consoleReachable = ok
                self?.lastReachabilityCheck = Date()
            }
        }.resume()
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
        guard let kind = ShellWindowKind(rawValue: name) else { return }
        environment(id: kind.rawValue)
        // Bring it forward even if it was already open.
        for window in NSApp.windows where window.identifier?.rawValue == kind.rawValue {
            window.makeKeyAndOrderFront(nil)
        }
        ScreenPlacement.shared.reposition()
    }
}
