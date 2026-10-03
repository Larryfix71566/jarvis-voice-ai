// CC7a.2 regression probes from Codex's review of PR #164 (10-02, CX-15),
// added unchanged except for the class name and its defaults-suite prefix.
// On 5b1b91f they reproduced two P2 findings: a layout switch left quiet
// arrivals off with the thread showing, and the New count missed a reply
// inserted before a tool-first card (and counted rows as new when the last
// card closed).

import XCTest
import SwiftUI
import AppKit
@testable import JarvisKit
@testable import MortimerHost

private final class ReviewTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ payload: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: ["id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": ["type": "display", "display": payload]])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor final class CC7a2ReviewRegressionTests: XCTestCase {
    private func config() -> JarvisConfig {
        JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!, adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil)
    }
    func testReplyInsertedBeforeToolFirstCardCountsAsNew() {
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "card-x"], to: ["u1", "a1", "card-x"]), 1)
    }
    func testClosingTailCardDoesNotInventNewTurns() {
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "a1", "card-x"], to: ["u1", "a1"]), 0)
    }
    func testActualArrivalRoutesWithThreadSettingOnAndOff() async throws {
        let payloads: [[String: Any]] = [
            ["kind": "markdown", "title": "Window", "body": "Result", "surface": "window"],
            ["kind": "markdown", "title": "Protected", "body": "Private", "surface": "window", "data_policy": "local_only"],
            ["kind": "markdown", "title": "Drawer", "body": "Result", "surface": "drawer"],
            ["kind": "weather", "title": "Weather", "surface": "window", "weather": ["schema": 1, "place": ["label": "Folly Beach", "source": "device", "approximate": false], "units": "imperial", "now": ["temp": "82°", "condition": "Sunny", "symbol": "sun.max"], "alerts": [], "summary": "Sunny", "attribution": "NWS"]]
        ]
        for quiet in [true, false] {
            for payload in payloads {
                for initial in ["conversation", "result", "atlas"] {
                    let transport = ReviewTransport()
                    let client = JarvisClient(config: config(), stubTransport: transport)
                    let workspace = WorkspaceStore()
                    workspace.quietArrivals = quiet
                    if initial == "result" {
                        let old = WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self, from: Data("{\"title\":\"Old\",\"body\":\"Old body\"}".utf8)))
                        workspace.receive(old); workspace.select(old.id)
                    } else if initial == "atlas" { workspace.openAtlas() }
                    let oldID = workspace.activeID
                    let display = DisplayWindowStore()
                    let output = DisplayResultStore()
                    let drawer = DrawerState()
                    let router = AppMessageRouter()
                    router.start(client: client, agentRuns: AgentRunStore(), displayResults: output, displayWindow: display, workspace: workspace, drawer: drawer)
                    try transport.emit(payload)
                    for _ in 0..<200 { await Task.yield() }
                    XCTAssertEqual(workspace.results.count, initial == "result" ? 2 : 1, "Delivery: \(payload["title"]!)")
                    let result = try XCTUnwrap(workspace.results.last)
                    if quiet {
                        XCTAssertEqual(workspace.showsConversation, initial == "conversation")
                        XCTAssertEqual(workspace.showsAtlas, initial == "atlas")
                        if let oldID { XCTAssertEqual(workspace.activeID, oldID) }
                        XCTAssertTrue(workspace.unreadIDs.contains(result.id))
                        XCTAssertEqual(workspace.arrivalNoticeID, initial == "conversation" ? nil : result.id)
                    } else {
                        XCTAssertNil(workspace.arrivalNoticeID)
                        let weather = payload["kind"] as? String == "weather"
                        XCTAssertEqual(workspace.showsAtlas, initial == "atlas" && !weather)
                        XCTAssertFalse(workspace.showsConversation)
                        XCTAssertEqual(workspace.activeID, weather ? result.id : (oldID ?? result.id))
                    }
                    if payload["surface"] as? String == "drawer" {
                        XCTAssertTrue(drawer.isOpen); XCTAssertEqual(drawer.activeTab, "output")
                    }
                    if payload["data_policy"] as? String == "local_only" {
                        XCTAssertTrue(display.panels.isEmpty); XCTAssertNil(workspace.supportingContent)
                    }
                    router.stop()
                }
            }
        }
    }
    func testRealConsoleLayoutAndFlagTransitionsKeepQuietArrivalsInSync() throws {
        _ = NSApplication.shared
        let suite = "CC7a2-review-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(1, forKey: "mortimer.interface.layoutVersion")
        defaults.set(true, forKey: ConversationThread.flagKey)
        let workspace = WorkspaceStore()
        let client = JarvisClient(config: config(), stubTransport: ReviewTransport())
        let view = NSHostingView(rootView: ConsoleView()
            .defaultAppStorage(defaults).environment(workspace).environmentObject(client)
            .environment(AgentRunStore()).environment(DrawerState()).environment(DrawerModels()).environment(DisplayResultStore())
            .environment(ConversationStore()).environment(ConsoleNoticeState())
            .environment(DisplayWindowStore()).environment(ShareCoordinator()).environment(AttachmentStore())
            .environment(\.mortimerReduceMotion, true).preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 1000, height: 800)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        func settle() { window.layoutIfNeeded(); view.layoutSubtreeIfNeeded(); RunLoop.main.run(until: Date().addingTimeInterval(0.3)) }
        settle(); XCTAssertFalse(workspace.quietArrivals)
        var previousLayout = 1
        for layout in [2, 1, 2, 0, 2] {
            defaults.set(layout, forKey: "mortimer.interface.layoutVersion")
            settle(); print("REVIEW transition \(previousLayout) -> \(layout), quiet=\(workspace.quietArrivals)")
            XCTAssertEqual(workspace.quietArrivals, layout == 2, "Layout \(previousLayout) -> \(layout)")
            previousLayout = layout
        }
        defaults.set(false, forKey: ConversationThread.flagKey)
        settle(); XCTAssertFalse(workspace.quietArrivals)
        defaults.set(true, forKey: ConversationThread.flagKey)
        settle(); XCTAssertTrue(workspace.quietArrivals)
    }
}
