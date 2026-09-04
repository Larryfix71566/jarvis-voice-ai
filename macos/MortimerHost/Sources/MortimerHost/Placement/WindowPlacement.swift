import AppKit
import JarvisKit

/// APP plan §3 P11, §5 step 2 — a thin caller of MortimerHost's ported
/// ScreenPlacement (DP8 semantics, CORE §3 N15). NO new placement math:
/// this opens a scene, marks drawer popped-state, and asks ScreenPlacement
/// to reposition; the 60/40 split, visibleFrame choice, and hot-plug
/// observer all live in ScreenPlacement, unchanged.
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
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            ScreenPlacement.shared.reposition()
        }
    }

    /// The toolbar pop-out button's call and drawer_popout's (P15).
    func popOutDrawer() {
        drawer.isOpen = false
        drawer.isPoppedOut = true
        windows.open("drawer")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            ScreenPlacement.shared.reposition()
        }
    }

    /// The topbar ↩︎ pop-in button's call and drawer_popin's — the same
    /// close path in both directions (App.tsx:318-322).
    func popInDrawer() {
        windows.dismiss("drawer")
        drawer.isPoppedOut = false
        drawer.isOpen = true
    }

    /// The topbar ↩︎ display pop-in / display_close.
    func closeDisplay() {
        windows.dismiss("display")
    }
}
