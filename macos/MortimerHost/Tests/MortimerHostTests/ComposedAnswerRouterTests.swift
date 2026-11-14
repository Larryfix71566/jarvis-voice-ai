import XCTest
@testable import JarvisKit
@testable import MortimerHost

private final class ComposedRouterTransport: RTVITransport {
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
final class ComposedAnswerRouterTests: XCTestCase {
    private struct Fixture {
        let transport: ComposedRouterTransport
        let client: JarvisClient
        let workspace: WorkspaceStore
        let conversation: ConversationStore
        let display: DisplayWindowStore
        let drawer: DisplayResultStore
        let router: AppMessageRouter
        let requestID: UUID
    }

    private func fixture() -> Fixture {
        let transport = ComposedRouterTransport()
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!, adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil), stubTransport: transport)
        let workspace = WorkspaceStore()
        workspace.quietArrivals = true
        let conversation = ConversationStore(), display = DisplayWindowStore(), drawer = DisplayResultStore()
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: drawer,
                     displayWindow: display, workspace: workspace, conversation: conversation, drawer: DrawerState())
        let session = UUID(), generation = UUID(), request = UUID()
        try! transport.emit(["type": "console/hello", "version": 1,
            "session_id": session.uuidString, "generation": generation.uuidString, "actions": [], "input_types": []])
        try! transport.emit(["type": "user-started-speaking"])
        try! transport.emit(["type": "user-transcription", "data": ["text": "Show results", "final": true,
            "timestamp": "composed-input", "user_id": "synthetic-user"]])
        try! transport.emit(["type": "console/turn", "version": 1,
            "session_id": session.uuidString, "generation": generation.uuidString,
            "request_id": request.uuidString, "sequence": 1, "state": "started",
            "input_timestamp": "composed-input", "input_user_id": "synthetic-user"])
        return Fixture(transport: transport, client: client, workspace: workspace,
                       conversation: conversation, display: display, drawer: drawer, router: router, requestID: request)
    }

    private func payload(_ answer: UUID, revision: Int, body: String = "Answer", complete: Bool = false,
                         surface: String = "window", layout: Bool = true) -> [String: Any] {
        var value: [String: Any] = ["kind": "markdown", "title": "Answer", "body": body,
            "surface": surface, "tool": "composed_answer", "answer_id": answer.uuidString, "answer_revision": revision]
        if layout {
            value["layout"] = ["version": 1, "revision": revision, "template": "text", "title": "Answer",
                "summary": "Summary", "complete": complete,
                "blocks": [["id": "body", "type": "text", "format": "plain", "text": body]]]
        }
        return value
    }

    private func deliver(_ f: Fixture, _ payload: [String: Any]) async throws {
        var payload = payload
        payload["origin_request_id"] = f.requestID.uuidString
        try f.transport.emit(["type": "display", "display": payload])
        for _ in 0..<200 { await Task.yield() }
    }

    func testHigherRevisionKeepsMainReaderAndDoesNotAddTranscript() async throws {
        let f = fixture(), answer = UUID()
        defer { f.router.stop() }
        try await deliver(f, payload(answer, revision: 1))
        let first = try XCTUnwrap(f.workspace.results.first)
        f.workspace.select(first.id)
        XCTAssertTrue(f.workspace.pin(first.id))
        f.workspace.rememberScroll(240, for: first.id)
        let entries = f.conversation.entries, references = f.conversation.cachedReferences
        let panelID = try XCTUnwrap(f.display.panels.first).id
        try await deliver(f, payload(answer, revision: 2, body: "Revised", layout: false))
        XCTAssertEqual(f.workspace.results.map(\.id), [first.id])
        XCTAssertEqual(f.workspace.results.first?.receivedAt, first.receivedAt)
        XCTAssertEqual(f.workspace.results.first?.payload.answerRevision, 2)
        XCTAssertNil(f.workspace.results.first?.payload.layout)
        XCTAssertEqual(f.workspace.activeID, first.id)
        XCTAssertFalse(f.workspace.showsConversation)
        XCTAssertEqual(f.workspace.scrollOffsets[first.id], 240)
        XCTAssertTrue(f.workspace.pinnedIDs.contains(first.id))
        XCTAssertEqual(f.display.panels.map(\.id), [panelID])
        XCTAssertEqual(f.display.panels.first?.payload.body, "Revised")
        XCTAssertEqual(f.conversation.entries, entries)
        XCTAssertEqual(f.conversation.cachedReferences, references)
        XCTAssertTrue(f.workspace.updatedIDs.isEmpty)
    }

    func testRevisionKeepsSupportingOwnerAndDoesNotRerouteSurface() async throws {
        let f = fixture(), answer = UUID()
        defer { f.router.stop() }
        f.display.setWindowOpen(true)
        try await deliver(f, payload(answer, revision: 1))
        let first = try XCTUnwrap(f.workspace.results.first)
        XCTAssertTrue(f.workspace.sendToDisplay(.result(first.id)))
        f.workspace.returnToConversation()
        let panel = try XCTUnwrap(f.display.panels.first)
        let references = f.conversation.cachedReferences, entries = f.conversation.entries
        try await deliver(f, payload(answer, revision: 2, body: "Updated", surface: "drawer"))
        XCTAssertEqual(f.workspace.supportingContent, .result(first.id))
        XCTAssertTrue(f.workspace.showsConversation)
        XCTAssertEqual(f.workspace.results.map(\.id), [first.id])
        XCTAssertEqual(f.display.panels.map(\.id), [panel.id])
        XCTAssertEqual(f.display.panels.first?.workspaceID, panel.workspaceID)
        XCTAssertEqual(f.display.panels.first?.payload.answerRevision, 2)
        XCTAssertTrue(f.drawer.results.isEmpty, "A revision cannot create a second owner when its surface changes.")
        XCTAssertEqual(f.conversation.entries, entries)
        XCTAssertEqual(f.conversation.cachedReferences, references)
    }

    func testReplayAndOutOfOrderHaveNoObservableSideEffects() async throws {
        let f = fixture(), answer = UUID()
        defer { f.router.stop() }
        try await deliver(f, payload(answer, revision: 2, surface: "drawer"))
        let first = try XCTUnwrap(f.workspace.results.first)
        f.workspace.select(first.id)
        f.workspace.rememberScroll(125, for: first.id)
        let inventory = f.workspace.consoleRevision, results = f.drawer.results
        let entries = f.conversation.entries, references = f.conversation.cachedReferences
        let unread = f.workspace.unreadIDs, notice = f.workspace.arrivalNoticeID
        for revision in [2, 1, 1] {
            try await deliver(f, payload(answer, revision: revision, body: "Stale", surface: "window"))
        }
        XCTAssertEqual(f.workspace.consoleRevision, inventory)
        XCTAssertEqual(f.workspace.results.map(\.id), [first.id])
        XCTAssertEqual(f.workspace.results.first?.payload.body, "Answer")
        XCTAssertEqual(f.workspace.activeID, first.id)
        XCTAssertEqual(f.workspace.scrollOffsets[first.id], 125)
        XCTAssertEqual(f.workspace.unreadIDs, unread)
        XCTAssertEqual(f.workspace.arrivalNoticeID, notice)
        XCTAssertTrue(f.workspace.updatedIDs.isEmpty)
        XCTAssertEqual(f.drawer.results, results)
        XCTAssertTrue(f.display.panels.isEmpty)
        XCTAssertEqual(f.conversation.entries, entries)
        XCTAssertEqual(f.conversation.cachedReferences, references)
    }

    func testCompletionOnlyRevisionDoesNotMarkInactiveAnswerUpdated() async throws {
        let f = fixture(), answer = UUID()
        defer { f.router.stop() }
        try await deliver(f, payload(answer, revision: 1, surface: "drawer"))
        let first = try XCTUnwrap(f.workspace.results.first)
        try await deliver(f, payload(UUID(), revision: 1, body: "Another", surface: "drawer"))
        f.workspace.select(try XCTUnwrap(f.workspace.results.last).id)
        let active = f.workspace.activeID, order = f.workspace.results.map(\.id)
        let entries = f.conversation.entries, references = f.conversation.cachedReferences
        try await deliver(f, payload(answer, revision: 2, complete: true, surface: "drawer"))
        XCTAssertEqual(f.workspace.results.map(\.id), order)
        XCTAssertEqual(f.workspace.activeID, active)
        XCTAssertEqual(f.workspace.results.first?.payload.layout?.complete, true)
        XCTAssertFalse(f.workspace.updatedIDs.contains(first.id))
        XCTAssertEqual(f.drawer.results.first(where: { $0.payload.answerID == answer })?.payload.answerRevision, 2)
        XCTAssertEqual(f.conversation.entries, entries)
        XCTAssertEqual(f.conversation.cachedReferences, references)
        try await deliver(f, payload(answer, revision: 3, body: "Actually changed", complete: true, surface: "drawer"))
        XCTAssertTrue(f.workspace.updatedIDs.contains(first.id))
    }
}
