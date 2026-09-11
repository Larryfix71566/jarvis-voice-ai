import AppKit
import JarvisKit

/// Opens/closes scenes and updates drawer ownership. ScreenPlacement owns
/// debouncing, display recovery and placement policy; this adapter does not
/// manipulate frames or duplicate the topology observer.
@MainActor
final class WindowPlacement {
    private let drawer: DrawerState
    private let windows: WindowActions

    init(drawer: DrawerState, windows: WindowActions) {
        self.drawer = drawer
        self.windows = windows
        ScreenPlacement.shared.startObserving()
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
}
