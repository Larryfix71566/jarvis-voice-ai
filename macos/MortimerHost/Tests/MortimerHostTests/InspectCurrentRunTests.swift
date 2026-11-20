import XCTest
import SwiftUI
import AppKit
@testable import JarvisKit
@testable import MortimerHost

/// docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md, Phase 3 slice 2:
/// the working line's Inspect lands on the current run, and the Agents tab
/// keeps finished runs in a collapsed History.
private final class AgentTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ payload: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: ["id": UUID().uuidString, "label": "rtvi-ai",
            "type": "server-message", "data": payload])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class InspectCurrentRunTests: XCTestCase {
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

    private func run(_ id: Int, name: String = "developer", display: String = "Developer",
                     tools: [String] = [], started: Double, done: Double? = nil) -> AgentRun {
        AgentRun(id: id, name: name, displayName: display, runId: "run-\(id)", task: "private task words",
                 tools: tools, activity: [], stage: 0, startedAt: Date(timeIntervalSince1970: started),
                 doneAt: done.map(Date.init(timeIntervalSince1970:)), ok: false, detail: "",
                 model: "", modelFallback: false, modelUnusable: false, modelUnusableDetail: "",
                 plannerModel: "")
    }

    // MARK: focusRun

    func testFocusRunOpensAgentsOnThatRun() {
        let drawer = DrawerState()
        drawer.setTab("repo"); drawer.isOpen = false
        drawer.focusRun(7)
        XCTAssertEqual(drawer.activeTab, "agents")
        XCTAssertTrue(drawer.isOpen)
        XCTAssertEqual(drawer.focusedRunID, 7)
        XCTAssertTrue(drawer.consumeRunFocusScroll())
        XCTAssertFalse(drawer.consumeRunFocusScroll(), "the scroll is one-shot")
    }

    func testFocusRunWithNoRunStillOpensAgents() {
        let drawer = DrawerState()
        drawer.setTab("repo"); drawer.isOpen = false
        drawer.focusRun(nil)
        XCTAssertEqual(drawer.activeTab, "agents")
        XCTAssertTrue(drawer.isOpen)
        XCTAssertNil(drawer.focusedRunID)
    }

    func testFocusRunWhilePoppedOutDoesNotOpenTheDockedDrawer() {
        let drawer = DrawerState()
        drawer.isPoppedOut = true; drawer.isOpen = false
        drawer.focusRun(1)
        XCTAssertFalse(drawer.isOpen)
        XCTAssertEqual(drawer.activeTab, "agents")
    }

    // MARK: Current and History

    func testCurrentHoldsLiveRunsAndHistoryHoldsFinishedOnes() {
        let runs = [run(1, started: 1, done: 5), run(2, started: 2), run(3, started: 3)]
        let split = AgentsTabSections.split(runs: runs, focusedRunID: nil)
        XCTAssertEqual(split.current.map(\.id), [3, 2])
        XCTAssertEqual(split.history.map(\.id), [1])
    }

    func testFocusedRunComesFirstAndStaysCurrentAfterItFinishes() {
        var runs = [run(1, started: 1, done: 5), run(2, started: 2), run(3, started: 3)]
        XCTAssertEqual(AgentsTabSections.split(runs: runs, focusedRunID: 2).current.map(\.id), [2, 3])

        runs[1] = run(2, started: 2, done: 6)
        let finished = AgentsTabSections.split(runs: runs, focusedRunID: 2)
        XCTAssertEqual(finished.current.first?.id, 2)
        XCTAssertEqual(finished.current.map(\.id), [2, 3])
        XCTAssertEqual(finished.history.map(\.id), [1])

        let gone = AgentsTabSections.split(runs: runs, focusedRunID: 99)
        XCTAssertEqual(gone.current.map(\.id), [3])
    }

    // MARK: Nothing opens by itself

    func testNothingOpensByItself() async throws {
        let drawer = DrawerState()
        drawer.setTab("repo"); drawer.isOpen = false
        let transport = AgentTransport()
        let client = JarvisClient(config: config(), stubTransport: transport)
        let agentRuns = AgentRunStore()
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: agentRuns, displayResults: DisplayResultStore(),
                     displayWindow: DisplayWindowStore(), workspace: WorkspaceStore(), drawer: drawer)
        defer { router.stop() }

        func assertUntouched(_ note: String) {
            XCTAssertFalse(drawer.isOpen, note)
            XCTAssertEqual(drawer.activeTab, "repo", note)
            XCTAssertNil(drawer.focusedRunID, note)
            XCTAssertEqual(drawer.runFocusRequest, 0, note)
        }

        try transport.emit(["type": "agent", "state": "working", "name": "analyst", "run_id": "r1", "task": "t"])
        for _ in 0..<200 { await Task.yield() }
        XCTAssertEqual(agentRuns.runs.count, 1, "the message was delivered")
        assertUntouched("a run starting must not open or steer the drawer")

        try transport.emit(["type": "agent", "state": "done", "name": "analyst", "run_id": "r1", "ok": true])
        for _ in 0..<200 { await Task.yield() }
        assertUntouched("a run finishing must not open or steer the drawer")
    }

    // MARK: History is collapsed until asked

    private func accessible(_ root: Any) -> (text: [String], controls: [String: NSObject]) {
        var seen = Set<ObjectIdentifier>()
        var text: [String] = []
        var controls: [String: NSObject] = [:]
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            for name in ["accessibilityLabel", "accessibilityValue", "accessibilityTitle"] {
                let selector = NSSelectorFromString(name)
                guard object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue() else { continue }
                let string = (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
                if !string.isEmpty { text.append(string); if controls[string] == nil { controls[string] = object } }
            }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(root)
        return (text, controls)
    }

    private func press(_ control: NSObject) -> Bool {
        let selector = NSSelectorFromString("accessibilityPerformPress")
        guard control.responds(to: selector) else { return false }
        typealias Press = @convention(c) (AnyObject, Selector) -> Bool
        return unsafeBitCast(control.method(for: selector), to: Press.self)(control, selector)
    }

    func testHistoryIsCollapsedUntilAsked() throws {
        func message(_ json: String) throws -> AppMessage {
            try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        }
        let store = AgentRunStore()
        store.apply(try message("""
        {"type":"agent","name":"developer","display_name":"Developer","state":"working","run_id":"d1","task":"fix"}
        """))
        store.apply(try message("""
        {"type":"agent","state":"done","name":"developer","run_id":"d1","ok":true}
        """))
        store.apply(try message("""
        {"type":"agent","name":"analyst","display_name":"Analyst","state":"working","run_id":"a1","task":"compare"}
        """))
        XCTAssertEqual(store.runs.count, 2)

        let suite = "InspectCurrentRunTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: AgentsTab(council: nil)
            .defaultAppStorage(defaults)
            .environment(store).environment(DrawerState()).environment(DrawerModels())
            .environment(\.mortimerReduceMotion, true).preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 420, height: 700)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))

        let collapsed = accessible(view)
        XCTAssertTrue(collapsed.text.contains("Analyst"))
        XCTAssertTrue(collapsed.text.contains("History"))
        XCTAssertFalse(collapsed.text.contains("Developer"), "a finished run is behind History")

        let toggle = try XCTUnwrap(collapsed.controls["History"])
        XCTAssertTrue(press(toggle))
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        XCTAssertTrue(accessible(view).text.contains("Developer"))
    }
}
