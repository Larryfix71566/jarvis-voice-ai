// ShellRootView.swift
// Ties one window's content (console, display, or drawer) to the shared
// ShellController: picks the right URL, shows RetryView instead of the
// webview when the console is unreachable (B4), and starts native
// screen-placement observation once, from wherever the app happens to
// create its first window.

import AppKit
import SwiftUI

struct ShellRootView: View {
    let kind: ShellWindowKind
    @ObservedObject var shell: ShellController
    @Environment(\.openWindow) private var openWindow

    private var url: URL {
        switch kind {
        case .console: return MortimerShellApp.consoleURL
        case .display: return MortimerShellApp.displayURL
        case .drawer: return MortimerShellApp.drawerURL
        }
    }

    var body: some View {
        Group {
            if shell.consoleReachable {
                ShellWebView(
                    url: url,
                    dataStore: shell.dataStore,
                    controller: shell,
                    openWindow: openWindow
                )
            } else {
                RetryView(onRetry: shell.retryNow)
            }
        }
        // Larry 2026-08-18 — real see-through for the auxiliary windows.
        // The CONSOLE is deliberately excluded: it is a full-bleed app
        // window with nothing useful behind it, and blurring the desktop
        // under the wave would fight the one element allowed to move.
        .background(kind == .console ? nil : VibrantWindow())
        .onAppear {
            ScreenPlacement.shared.startObserving()
            // Larry 2026-08-18: device location for the ambient weather
            // chip. Idempotent.
            ShellLocation.shared.start()

            guard kind != .console else { return }
            // The webview is usually not mounted on the first pass, and
            // applyVibrancy's step 3 needs it — so retry briefly. Both
            // calls are idempotent (the effect view is installed once),
            // so a redundant pass costs nothing and a missed one shows
            // as an opaque window.
            for delay in [0.0, 0.15, 0.6] {
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                    applyVibrancy(to: NSApplication.shared.keyWindow
                        ?? NSApplication.shared.windows.last)
                }
            }
        }
    }
}
