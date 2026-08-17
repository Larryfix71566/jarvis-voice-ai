// MortimerShellApp.swift
// MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md B1: three scenes,
// reusing the three Vite entries that already exist and already speak
// the presence/relay protocol (console "/", display "/display.html",
// drawer "/drawer.html"). The shell owns window chrome — native
// titlebars, resize, fullscreen, per-screen placement (B3); the web
// pages' own pop-out machinery keeps working unmodified in plain
// browsers, since nothing web-side was removed, only short-circuited
// when window.mortimerShell is present (see ShellWebView.swift).

import SwiftUI

@main
struct MortimerShellApp: App {
    // B4 — the console dev server ./scripts/mortimer.sh already starts.
    // Production packaging/bundled static assets are an explicit
    // NON-GOAL of this plan (B4) — the shell always talks to the same
    // localhost dev server a browser tab would.
    static let consoleURL = URL(string: "http://127.0.0.1:5173")!
    static let displayURL = URL(string: "http://127.0.0.1:5173/display.html")!
    static let drawerURL = URL(string: "http://127.0.0.1:5173/drawer.html")!

    // B0: one shared WKProcessPool + the default WKWebsiteDataStore across
    // every WKWebView in the shell — required for BroadcastChannel to
    // reach across windows (spike question 2) and for the console/
    // display/drawer webviews to share one origin's storage.
    @StateObject private var shell = ShellController()

    var body: some Scene {
        // Console — the only window with a persistent chrome the user
        // opens by launching the app. Named so ShellController can find
        // it again when a WKUserScript-originated "openWindow" command
        // arrives from a webview that isn't the console's own.
        WindowGroup("Mortimer", id: "console") {
            ShellRootView(kind: .console, shell: shell)
                .frame(minWidth: 900, minHeight: 600)
        }
        .defaultSize(width: 1280, height: 800)
        .commands { SidebarCommands() }

        // Display and Drawer are auxiliary windows the shell opens/closes
        // itself in response to the injected message channel (B2) — they
        // do NOT need a WindowGroup the user can create arbitrarily many
        // of, so they are modeled as single named Windows the controller
        // toggles visible/hidden rather than opening a fresh scene
        // instance per request.
        Window("Mortimer Display", id: "display") {
            ShellRootView(kind: .display, shell: shell)
                .frame(minWidth: 480, minHeight: 320)
        }
        .defaultSize(width: 900, height: 600)

        Window("Mortimer Drawer", id: "drawer") {
            ShellRootView(kind: .drawer, shell: shell)
                .frame(minWidth: 360, minHeight: 400)
        }
        .defaultSize(width: 420, height: 800)
    }
}
