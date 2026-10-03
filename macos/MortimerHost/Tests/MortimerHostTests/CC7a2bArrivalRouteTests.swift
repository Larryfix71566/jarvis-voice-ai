import XCTest
@testable import JarvisKit
@testable import MortimerHost

/// CC7a.2b (Larry, 10-03; Codex review of PR #169): through the real
/// AppMessageRouter, a result opens on the conversation only when it
/// answers what Larry just asked and the main stage is where it renders.
private final class ArrivalTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ data: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: [
            "id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": data])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class CC7a2bArrivalRouteTests: XCTestCase {
    private struct Fixture {
        let transport: ArrivalTransport
        let workspace: WorkspaceStore
        let conversation: ConversationStore
        let display: DisplayWindowStore
        let router: AppMessageRouter
    }

    private func fixture(displayOpen: Bool = false) -> Fixture {
        let transport = ArrivalTransport()
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!, adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil), stubTransport: transport)
        let workspace = WorkspaceStore()
        workspace.quietArrivals = true                  // the layout-2 thread is showing
        let conversation = ConversationStore()
        let display = DisplayWindowStore()
        display.setWindowOpen(displayOpen)
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: DisplayResultStore(),
                     displayWindow: display, workspace: workspace, conversation: conversation,
                     drawer: DrawerState())
        return Fixture(transport: transport, workspace: workspace, conversation: conversation,
                       display: display, router: router)
    }

    /// Larry spoke at `secondsAgo`; set after `start`, whose transcript sink
    /// first mirrors the client's empty transcript.
    private func larrySpoke(_ f: Fixture, secondsAgo: Double = 2) throws {
        let entry = try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject: [
            "id": "u-\(UUID().uuidString)", "role": "user", "text": "What's the weather?",
            "createdAt": Date().timeIntervalSince1970 - secondsAgo]))
        f.conversation.set([entry])
    }

    private func settle() async { for _ in 0..<200 { await Task.yield() } }

    private func runStarted(_ f: Fixture, _ runID: String) async throws {
        try f.transport.emit(["type": "agent", "state": "working", "name": "analyst",
                              "run_id": runID, "task": "weather"])
        await settle()
    }

    private func weather(runID: String) -> [String: Any] {
        ["kind": "weather", "title": "Weather", "surface": "window", "tool": "weather_report", "run_id": runID,
         "weather": ["schema": 1, "place": ["label": "Folly Beach", "source": "device", "approximate": false],
                     "units": "imperial", "now": ["temp": "82°", "condition": "Sunny", "symbol": "sun.max"],
                     "alerts": [], "summary": "Sunny", "attribution": "NWS"]]
    }

    private func deliver(_ f: Fixture, _ payload: [String: Any]) async throws -> WorkspaceResult {
        try f.transport.emit(["type": "display", "display": payload])
        await settle()
        return try XCTUnwrap(f.workspace.results.last)
    }

    func testWeatherAskedForFromTheConversationOpens() async throws {
        let f = fixture()
        defer { f.router.stop() }
        try larrySpoke(f)
        try await runStarted(f, "r-weather")
        let result = try await deliver(f, weather(runID: "r-weather"))
        XCTAssertFalse(f.workspace.showsConversation, "Larry, 10-03: the weather he asked for opens.")
        XCTAssertEqual(f.workspace.activeID, result.id)
        XCTAssertNil(f.workspace.arrivalNoticeID)
    }

    func testABackgroundResearchCompletionStaysACard() async throws {
        let f = fixture()
        defer { f.router.stop() }
        try larrySpoke(f)                                // he is talking about something else
        let result = try await deliver(f, ["kind": "markdown", "title": "Site comparison", "body": "Done",
                                           "surface": "window", "tool": "research_report"])
        XCTAssertTrue(f.workspace.showsConversation, "A finished background job does not take the stage.")
        XCTAssertTrue(f.workspace.unreadIDs.contains(result.id))
        XCTAssertNil(f.workspace.arrivalNoticeID)
    }

    func testARunStartedBeforeLarrysLatestTurnStaysACard() async throws {
        let f = fixture()
        defer { f.router.stop() }
        try await runStarted(f, "r-detached")            // started earlier, still running
        try larrySpoke(f, secondsAgo: -1)                // then he spoke again (after the run started)
        let result = try await deliver(f, weather(runID: "r-detached"))
        XCTAssertTrue(f.workspace.showsConversation, "A detached run finishing later is not the answer just asked.")
        XCTAssertTrue(f.workspace.unreadIDs.contains(result.id))
    }

    func testAWindowResultOwnedByAnOpenSupportingDisplayKeepsTheConversation() async throws {
        let f = fixture(displayOpen: true)
        defer { f.router.stop() }
        try larrySpoke(f)
        try await runStarted(f, "r-search")
        let result = try await deliver(f, ["kind": "markdown", "title": "Search", "body": "Results",
                                           "surface": "window", "tool": "web_search", "run_id": "r-search"])
        XCTAssertTrue(f.workspace.showsConversation,
                      "Codex review of #169: the main stage keeps the conversation, not a placeholder.")
        XCTAssertEqual(f.workspace.supportingContent, SupportingDisplayContent.result(result.id), "The supporting display renders it.")
        XCTAssertTrue(f.workspace.containsResult(result.id), "Its card is in the thread.")
    }

    func testTheSameWindowResultOpensWhenNoSupportingDisplayIsOpen() async throws {
        let f = fixture(displayOpen: false)
        defer { f.router.stop() }
        try larrySpoke(f)
        try await runStarted(f, "r-search")
        let result = try await deliver(f, ["kind": "markdown", "title": "Search", "body": "Results",
                                           "surface": "window", "tool": "web_search", "run_id": "r-search"])
        XCTAssertFalse(f.workspace.showsConversation)
        XCTAssertEqual(f.workspace.activeID, result.id)
    }

    func testAnUnattributedResultLongAfterLarrySpokeStaysACard() async throws {
        let f = fixture()
        defer { f.router.stop() }
        try larrySpoke(f, secondsAgo: ArrivalIntent.directWindow + 60)
        let result = try await deliver(f, ["kind": "markdown", "title": "Graph", "body": "Memory",
                                           "surface": "drawer", "tool": "memory_graph_view"])
        XCTAssertTrue(f.workspace.showsConversation)
        XCTAssertTrue(f.workspace.unreadIDs.contains(result.id))
    }
}
