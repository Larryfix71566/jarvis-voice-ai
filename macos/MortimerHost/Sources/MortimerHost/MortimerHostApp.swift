// MortimerHostApp.swift
// G1(b) harness (§3 N2) — deliberately ugly, one window, default system
// materials. Proves JarvisKit holds a live voice session against the
// unchanged bot with barge-in working; a view layer would only add ways
// for that test to fail for unrelated reasons.

import SwiftUI
import JarvisKit

@main
struct MortimerHostApp: App {
    // Owned by the app, not a view (N5) — disconnect() does not depend
    // on a view's lifetime.
    @StateObject private var client = JarvisClient()

    var body: some Scene {
        WindowGroup("MortimerHost") {
            HostView(client: client)
        }
    }
}
