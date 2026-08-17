// RetryView.swift
// B4 — the shell always loads http://127.0.0.1:5173. When it's
// unreachable, this native screen replaces the webview rather than
// showing a WKWebView connection-error page, with a Retry button that
// re-checks reachability.

import SwiftUI

struct RetryView: View {
    let onRetry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Mortimer stack isn't running")
                .font(.title2.bold())
            Text("Start it with ./scripts/mortimer.sh, then retry.")
                .foregroundStyle(.secondary)
            Button("Retry", action: onRetry)
                .buttonStyle(.borderedProminent)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
