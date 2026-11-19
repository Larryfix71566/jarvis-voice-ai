import XCTest
import SwiftUI
import AppKit
@testable import JarvisKit
@testable import MortimerHost

/// WS-37, docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md open
/// decision 3, answered by Larry on 2026-11-19 ("light a dot"): a result
/// routed to the drawer never opens it. It lights the existing dot on the
/// Inspect button and the Output tab, and the drawer starts closed unless
/// the user opened it.
private final class DotTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ payload: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: ["id": UUID().uuidString, "label": "rtvi-ai",
            "type": "server-message", "data": ["type": "display", "display": payload]])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class InspectDotTests: XCTestCase {
    private static let keys = ["mortimer.drawer.tab", "mortimer.drawer.open", "mortimer.drawer.width",
                               DrawerState.openResetKey]
    private var saved: [(String, Any?)] = []

    override func setUp() {
        super.setUp()
        saved = Self.keys.map { ($0, UserDefaults.standard.object(forKey: $0)) }
    }

    override func tearDown() {
        for (key, value) in saved {
            if let value { UserDefaults.standard.set(value, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }
        super.tearDown()
    }

    private func config() -> JarvisConfig {
        JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!, adminURL: URL(string: "http://127.0.0.1:7861")!,
                     wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil)
    }

    /// Delivers one drawer-routed result through the real router.
    private func deliverDrawerResult(to drawer: DrawerState) async throws {
        let transport = DotTransport()
        let client = JarvisClient(config: config(), stubTransport: transport)
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: DisplayResultStore(),
                     displayWindow: DisplayWindowStore(), workspace: WorkspaceStore(), drawer: drawer)
        defer { router.stop() }
        try transport.emit(["kind": "markdown", "title": "Drawer", "body": "Result", "surface": "drawer"])
        for _ in 0..<200 { await Task.yield() }
    }

    // MARK: A result never opens the drawer

    func testResultWhileClosedLightsTheDotAndLeavesTheDrawerClosed() async throws {
        let drawer = DrawerState()
        drawer.setTab("repo"); drawer.isOpen = false; drawer.outputDot = false
        try await deliverDrawerResult(to: drawer)
        XCTAssertFalse(drawer.isOpen, "a result must not open the drawer")
        XCTAssertEqual(drawer.activeTab, "repo", "a result must not change the tab")
        XCTAssertTrue(drawer.outputDot, "the Inspect/Output dot lights instead")
        XCTAssertEqual(UserDefaults.standard.string(forKey: "mortimer.drawer.open"), "false",
                       "the saved open state stays the user's choice")
        XCTAssertFalse(DrawerState().isOpen, "the next launch starts closed")
    }

    func testResultWhileOpenOnAnotherTabLightsTheDot() async throws {
        let drawer = DrawerState()
        drawer.setTab("agents"); drawer.isOpen = true; drawer.outputDot = false
        try await deliverDrawerResult(to: drawer)
        XCTAssertTrue(drawer.isOpen)
        XCTAssertEqual(drawer.activeTab, "agents")
        XCTAssertTrue(drawer.outputDot)
    }

    func testResultWhileOutputIsShowingNeedsNoDot() async throws {
        let docked = DrawerState()
        docked.setTab("output"); docked.isOpen = true; docked.outputDot = false
        try await deliverDrawerResult(to: docked)
        XCTAssertTrue(docked.isOpen)
        XCTAssertFalse(docked.outputDot, "the result is already on screen")

        let popped = DrawerState()
        popped.isOpen = false; popped.isPoppedOut = true; popped.setTab("output"); popped.outputDot = false
        XCTAssertFalse(AppMessageRouter.drawerResultNeedsDot(popped))
        popped.setTab("runs")
        XCTAssertTrue(AppMessageRouter.drawerResultNeedsDot(popped))
    }

    func testViewingOutputClearsTheDot() {
        let drawer = DrawerState()
        drawer.setTab("repo"); drawer.isOpen = false
        drawer.outputDot = true
        drawer.isOpen = true
        XCTAssertTrue(drawer.outputDot, "opening on another tab keeps the Output tab's dot")
        drawer.setTab("output")
        XCTAssertFalse(drawer.outputDot)
    }

    // MARK: Closed by default

    func testSavedOpenStateFromBeforeThisBuildIsResetOnce() {
        UserDefaults.standard.removeObject(forKey: DrawerState.openResetKey)
        UserDefaults.standard.set("true", forKey: "mortimer.drawer.open")
        XCTAssertFalse(DrawerState().isOpen, "an open state saved by the old auto-open is not trusted")
        XCTAssertTrue(UserDefaults.standard.bool(forKey: DrawerState.openResetKey))

        let opened = DrawerState()
        opened.isOpen = true
        XCTAssertTrue(DrawerState().isOpen, "after the reset, a drawer the user opens comes back open")
        opened.isOpen = false
        XCTAssertFalse(DrawerState().isOpen)
    }

    // MARK: The dot on Inspect

    func testInspectButtonSpeaksTheDot() throws {
        let drawer = DrawerState()
        drawer.setTab("repo"); drawer.isOpen = false; drawer.outputDot = false
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let client = JarvisClient(config: config(), stubTransport: DotTransport())
        let view = NSHostingView(rootView: TopBarView()
            .environmentObject(client).environment(AgentRunStore()).environment(DisplayResultStore())
            .environment(drawer).environment(DisplayWindowStore())
            .environment(WorkspaceStore()).environment(ShareCoordinator()).environment(ConsoleNoticeState())
            .environment(\.mortimerReduceMotion, true).preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 1280, height: 80)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        XCTAssertEqual(inspectValue(in: view), "")

        drawer.outputDot = true
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        XCTAssertEqual(inspectValue(in: view), "New output")
    }

    /// The accessibility value of the element identified console.inspect.
    private func inspectValue(in root: Any) -> String? {
        var seen = Set<ObjectIdentifier>()
        func visit(_ value: Any) -> String?? {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return nil }
            let ident = NSSelectorFromString("accessibilityIdentifier")
            if object.responds(to: ident),
               object.perform(ident)?.takeUnretainedValue() as? String == "console.inspect" {
                let selector = NSSelectorFromString("accessibilityValue")
                guard object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue()
                else { return .some("") }
                return .some((raw as? String) ?? (raw as? NSAttributedString)?.string ?? "")
            }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children),
               let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                for child in values { if let found = visit(child) { return found } }
            }
            return nil
        }
        return visit(root) ?? nil
    }
}
