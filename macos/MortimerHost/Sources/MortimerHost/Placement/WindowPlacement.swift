import AppKit
import JarvisKit

/// Opens/closes scenes and updates drawer ownership. ScreenPlacement owns
/// debouncing, display recovery and placement policy; this adapter does not
/// manipulate frames or duplicate the topology observer.
@MainActor
final class WindowPlacement {
    private let drawer: DrawerState
    private let windows: WindowActions
    private let contentWindows: ContentWindowRegistry?

    init(drawer: DrawerState, windows: WindowActions,
         contentWindows: ContentWindowRegistry? = nil) {
        self.drawer = drawer
        self.windows = windows
        self.contentWindows = contentWindows
        ScreenPlacement.shared.startObserving()
        ScreenPlacement.shared.setDisplayLostHandler { [weak self] in
            self?.closeDisplay()
        }
    }

    /// The display toggle's call (TopBarView) and display_popout's (P15).
    func openDisplay() {
        windows.open("display")
        // The window needs a runloop turn to exist before placement can
        // find it by identifier (same deferral the spike used).
        ScreenPlacement.shared.scheduleReposition()
    }

    /// The toolbar pop-out button's call and drawer_popout's (P15).
    func popOutDrawer() {
        drawer.isOpen = false
        drawer.isPoppedOut = true
        windows.open("drawer")
        ScreenPlacement.shared.scheduleReposition()
    }

    /// The topbar ↩︎ pop-in button's call and drawer_popin's — the same
    /// close path in both directions (App.tsx:318-322).
    func popInDrawer() {
        ScreenPlacement.shared.noteClosed(.drawer)
        windows.dismiss("drawer")
        drawer.isPoppedOut = false
        drawer.isOpen = true
    }

    /// The topbar ↩︎ display pop-in / display_close.
    func closeDisplay() {
        ScreenPlacement.shared.noteClosed(.display)
        windows.dismiss("display")
    }

    /// Opens the diagnostic tuning window through the same app-owned window
    /// action seam as every other native panel.
    func openWaveTuning() {
        windows.open("wave-tuning")
    }

    /// CC4 — value-addressed panel windows. The scene is opened by its
    /// stable ConsolePanel value; topology placement remains owned by the
    /// shared ScreenPlacement policy after the window is created.
    func openPanel(_ panel: ConsolePanel, screenID: String? = nil) {
        windows.openPanel(panel)
        ScreenPlacement.shared.scheduleReposition()
        guard let screenID, let contentWindows else { return }
        let windowID = "panel-\(panel.rawValue)"
        DispatchQueue.main.asyncAfter(deadline: .now() + ScreenPlacement.debounceSeconds) {
            guard let window = contentWindows.window(id: windowID) else { return }
            ScreenPlacement.shared.placeDetachedPanel(window, id: windowID, on: screenID)
        }
    }

    func dismissPanel(_ panel: ConsolePanel) {
        ScreenPlacement.shared.unregisterDetachedPanel(id: "panel-\(panel.rawValue)")
        windows.dismissPanel(panel)
    }

    func dismissAllPanels() {
        for panel in ConsolePanel.allCases {
            ScreenPlacement.shared.unregisterDetachedPanel(id: "panel-\(panel.rawValue)")
        }
        windows.dismissAllPanels()
    }

    /// CC4 dynamic content panels use a UUID value rather than a title or
    /// legacy enum. Placement remains owned by ScreenPlacement.
    func openContentPanel(_ id: ContentPanelID, screenID: String? = nil) {
        windows.openContentPanel(id)
        ScreenPlacement.shared.scheduleReposition()
        guard let screenID, let contentWindows else { return }
        let windowID = "content-panel-\(id.rawValue.uuidString)"
        DispatchQueue.main.asyncAfter(deadline: .now() + ScreenPlacement.debounceSeconds) {
            guard let window = contentWindows.window(id: windowID) else { return }
            ScreenPlacement.shared.placeDetachedPanel(window, id: windowID, on: screenID)
        }
    }

    func registerContentPanel(_ id: ContentPanelID, screenID: String? = nil) {
        let windowID = "content-panel-\(id.rawValue.uuidString)"
        guard let contentWindows, let window = contentWindows.window(id: windowID) else { return }
        ScreenPlacement.shared.registerDetachedPanel(window, id: windowID, screenID: screenID)
    }

    func dismissContentPanel(_ id: ContentPanelID) {
        let windowID = "content-panel-\(id.rawValue.uuidString)"
        ScreenPlacement.shared.unregisterDetachedPanel(id: windowID)
        windows.dismissContentPanel(id)
    }

    func dismissAllContentPanels() {
        windows.dismissAllContentPanels()
    }
}
