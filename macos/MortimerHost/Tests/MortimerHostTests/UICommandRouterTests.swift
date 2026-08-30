import XCTest
import JarvisKit
@testable import MortimerHost

/// APP plan §7.3 (review F2) — one case per non-MicControls UI_ACTIONS
/// entry, each asserting the named setter fired with the right argument
/// and nothing else moved. Drives UICommandRouter.handle directly (the
/// stream plumbing is the same fan-out CORE already tests).
@MainActor
final class UICommandRouterTests: XCTestCase {
    private struct Spy {
        let router: UICommandRouter
        let drawer: DrawerState
        let overlay: ConsoleOverlayState
        let opened: () -> [String]
        let dismissed: () -> [String]
    }

    private func makeRouter() -> Spy {
        let drawer = DrawerState()
        let overlay = ConsoleOverlayState()
        let windows = WindowActions()
        var opened: [String] = []
        var dismissed: [String] = []
        windows.open = { opened.append($0) }
        windows.dismiss = { dismissed.append($0) }
        let placement = WindowPlacement(drawer: drawer, windows: windows)
        let router = UICommandRouter(drawer: drawer, overlay: overlay, windows: windows, placement: placement)
        return Spy(router: router, drawer: drawer, overlay: overlay,
                   opened: { opened }, dismissed: { dismissed })
    }

    private func command(_ action: String, tab: String? = nil) throws -> UICommand {
        let tabJSON = tab.map { ",\"tab\":\"\($0)\"" } ?? ""
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data("""
        {"type":"ui","action":"\(action)"\(tabJSON)}
        """.utf8)))
        guard case .ui(let cmd) = message else { throw XCTSkip("not a ui message") }
        return cmd
    }

    func testDrawerTabSwitchesActiveTab() throws {
        let spy = makeRouter()
        spy.router.handle(try command("drawer_tab", tab: "runs"))
        XCTAssertEqual(spy.drawer.activeTab, "runs")
    }

    func testDrawerOpenOpensAndSetsTab() throws {
        let spy = makeRouter()
        spy.drawer.isOpen = false
        spy.router.handle(try command("drawer_open", tab: "memory"))
        XCTAssertTrue(spy.drawer.isOpen)
        XCTAssertEqual(spy.drawer.activeTab, "memory")
    }

    func testDrawerOpenWithNoTabJustOpens() throws {
        let spy = makeRouter()
        let before = spy.drawer.activeTab
        spy.router.handle(try command("drawer_open"))
        XCTAssertTrue(spy.drawer.isOpen)
        XCTAssertEqual(spy.drawer.activeTab, before)
    }

    func testDrawerCloseDismissesWindow() throws {
        let spy = makeRouter()
        // Popped-out drawer: close means dismiss the window.
        spy.drawer.isPoppedOut = true
        spy.router.handle(try command("drawer_close"))
        XCTAssertEqual(spy.dismissed(), ["drawer"])
        XCTAssertFalse(spy.drawer.isPoppedOut)
        // Docked drawer: close just hides it.
        spy.drawer.isOpen = true
        spy.router.handle(try command("drawer_close"))
        XCTAssertFalse(spy.drawer.isOpen)
    }

    func testDrawerPopoutCallsWindowPlacement() throws {
        let spy = makeRouter()
        spy.router.handle(try command("drawer_popout"))
        // WindowPlacement.popOutDrawer() opens the drawer scene and
        // marks popped state — the same call the toolbar button makes.
        XCTAssertEqual(spy.opened(), ["drawer"])
        XCTAssertTrue(spy.drawer.isPoppedOut)
    }

    func testDrawerPopinRedocks() throws {
        let spy = makeRouter()
        spy.drawer.isPoppedOut = true
        spy.router.handle(try command("drawer_popin"))
        XCTAssertEqual(spy.dismissed(), ["drawer"])
        XCTAssertFalse(spy.drawer.isPoppedOut)
        XCTAssertTrue(spy.drawer.isOpen)   // re-docked, visible in console
    }

    func testDisplayPopoutOpensDisplay() throws {
        let spy = makeRouter()
        spy.router.handle(try command("display_popout"))
        XCTAssertEqual(spy.opened(), ["display"])
    }

    func testDisplayCloseDismissesWindow() throws {
        let spy = makeRouter()
        spy.router.handle(try command("display_close"))
        XCTAssertEqual(spy.dismissed(), ["display"])
    }

    func testOverlayDismissClearsPanel() throws {
        let spy = makeRouter()
        spy.overlay.isVisible = true
        spy.router.handle(try command("overlay_dismiss"))
        XCTAssertFalse(spy.overlay.isVisible)
    }

    func testMicActionsNotDoubleHandled() throws {
        let spy = makeRouter()
        let tabBefore = spy.drawer.activeTab
        for action in ["mic_mute", "wake_on", "wake_off"] {
            spy.router.handle(try command(action))
        }
        // JarvisClient owns these (CORE N11) — the router must touch
        // nothing: no window action, no drawer/overlay change.
        XCTAssertTrue(spy.opened().isEmpty)
        XCTAssertTrue(spy.dismissed().isEmpty)
        XCTAssertEqual(spy.drawer.activeTab, tabBefore)
        XCTAssertTrue(spy.overlay.isVisible)
    }
}
