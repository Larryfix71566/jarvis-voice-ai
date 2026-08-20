// ShellWebView.swift
// NSViewRepresentable wrapping WKWebView, one shared WKProcessPool/
// WKWebsiteDataStore (B0), the window.mortimerShell injection + message
// handler (B2), and the WKUIDelegate media-capture grant for the mic
// spike (B0 question 1).

import SwiftUI
import WebKit

/// B2 — injected at documentStart into every frame of every shell
/// webview. popoutWindow.ts's open() checks for window.mortimerShell and,
/// when present, posts {cmd:"openWindow", name} through
/// webkit.messageHandlers.mortimer instead of calling window.open() —
/// see ShellBridge below for the native side of that channel.
private let shellDetectionScript = """
window.mortimerShell = { version: 1 };
// Larry 2026-08-18 — vibrancy handshake. WindowVibrancy.swift makes the
// AUXILIARY windows non-opaque with an NSVisualEffectView behind the
// webview; the page must then stop painting its own dark wash, or it
// covers the very material it is meant to sit on. Marking the document
// here (rather than letting the CSS assume) means a plain browser tab,
// where no such window exists, keeps its opaque background and stays
// readable. Console is excluded for the same reason it is on the native
// side: nothing useful is behind it.
if (/display\\.html|drawer\\.html/.test(location.pathname)) {
  document.documentElement.classList.add("shell-vibrancy");
}
"""

/// B0 fallback (item 2, predecided): if native BroadcastChannel does NOT
/// cross window boundaries even with a shared process pool, this script
/// (currently unused — swap it in via ShellWebView.useBroadcastRelayFallback
/// if the spike fails) would wrap the constructor and mirror traffic
/// through webkit.messageHandlers.mortimerRelay, with the native side
/// rebroadcasting into every other webview's document. popoutWindow.ts
/// is written against the standard BroadcastChannel API either way, so
/// enabling this fallback requires zero web-side changes — only this
/// injected shim plus a matching native relay handler.
private let broadcastRelayFallbackScript = """
// (inactive placeholder — see comment above; wire up only if the B0
// spike shows native BroadcastChannel does not cross WKWebViews)
"""

struct ShellWebView: NSViewRepresentable {
    let url: URL
    let dataStore: WKWebsiteDataStore
    let controller: ShellController
    let openWindow: OpenWindowAction

    /// Flip to true only if the B0 spike shows native BroadcastChannel
    /// does not cross window boundaries — see broadcastRelayFallbackScript.
    static let useBroadcastRelayFallback = false

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = dataStore

        let userContent = WKUserContentController()
        let bridge = ShellBridge(controller: controller, openWindow: openWindow)
        userContent.add(bridge, name: "mortimer")
        context.coordinator.bridge = bridge // retain: WKUserContentController holds it weakly on some OS versions

        userContent.addUserScript(
            WKUserScript(
                source: shellDetectionScript,
                injectionTime: .atDocumentStart,
                forMainFrameOnly: false
            )
        )
        if Self.useBroadcastRelayFallback {
            userContent.addUserScript(
                WKUserScript(
                    source: broadcastRelayFallbackScript,
                    injectionTime: .atDocumentStart,
                    forMainFrameOnly: false
                )
            )
        }
        config.userContentController = userContent

        // B0 question 1 — WebRTC mic capture inside WKWebView needs the
        // media-capture permission callback below to grant this app's
        // own origin, on top of the audio-input entitlement and
        // NSMicrophoneUsageDescription (see templates/*.template).
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.uiDelegate = context.coordinator
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        // Nothing to update per-render; navigation happens once at
        // makeNSView. A future reachability-triggered reload (B4) posts
        // through the coordinator instead of relying on SwiftUI diffing.
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKUIDelegate {
        var bridge: ShellBridge?

        // B0 question 1's actual grant point. `.grant` for this app's own
        // origin is what a PASS verdict requires — a live voice turn
        // (connect, speak, hear TTS) inside the shell window is the test.
        func webView(
            _ webView: WKWebView,
            requestMediaCapturePermissionFor origin: WKSecurityOrigin,
            initiatedByFrame frame: WKFrameInfo,
            type: WKMediaCaptureType,
            decisionHandler: @escaping (WKPermissionDecision) -> Void
        ) {
            decisionHandler(.grant)
        }
    }
}
