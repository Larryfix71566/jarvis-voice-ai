// ShellRootView.swift
// Ties one window's content (console, display, or drawer) to the shared
// ShellController: picks the right URL, shows RetryView instead of the
// webview when the console is unreachable (B4), and starts native
// screen-placement observation once, from wherever the app happens to
// create its first window.

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
        .onAppear {
            ScreenPlacement.shared.startObserving()
            // Larry 2026-08-18: device location for the ambient weather
            // chip. Idempotent.
            ShellLocation.shared.start()
        }
    }
}
