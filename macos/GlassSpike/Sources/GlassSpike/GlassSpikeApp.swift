// GlassSpikeApp.swift
// T1.1 — two WindowGroups so S2 (regular vs clear side by side), S4-S6
// (two-display placement, one-display split, hot-plug) are all
// exercisable from one throwaway target. Deleted after G1(a) (§5 step 15).

import SwiftUI

@main
struct GlassSpikeApp: App {
    @Environment(\.openWindow) private var openWindow

    init() {
        SpikeScreenPlacement.shared.startObserving()
    }

    var body: some Scene {
        WindowGroup(id: "panelA") {
            GlassPanelView(label: "Panel A")
                .onAppear {
                    openWindow(id: "panelB")
                    // Give panelB a runloop turn to exist before placing both.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                        SpikeScreenPlacement.shared.reposition()
                    }
                }
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)

        WindowGroup(id: "panelB") {
            GlassPanelView(label: "Panel B")
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
    }
}
