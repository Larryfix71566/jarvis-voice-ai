import XCTest
@testable import MortimerHost
@testable import JarvisKit

@MainActor
private func flushTranscriptDelivery() async {
    // The stub transport, JarvisClient, and app router each cross a main-actor
    // task boundary. Yield repeatedly so tests observe completed delivery,
    // rather than assuming a fixed two-task scheduling order.
    for _ in 0..<100 { await Task.yield() }
}

private final class HostTranscriptTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?

    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}

    func emit(_ type: String, text: String? = nil, final: Bool? = nil) throws {
        var payload: [String: Any] = ["type": type]
        if let text {
            var data: [String: Any] = ["text": text]
            if let final { data["final"] = final }
            payload["data"] = data
        }
        try emitPayload(payload)
    }

    func emitPayload(_ payload: [String: Any]) throws {
        let envelope: [String: Any] = [
            "id": UUID().uuidString,
            "label": "rtvi-ai",
            "type": "server-message",
            "data": payload,
        ]
        let frame = try JSONSerialization.data(withJSONObject: envelope)
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class LiveVoiceResponseStreamTests: XCTestCase {
    /// Sets a standard-defaults key for one test and restores it afterwards.
    private func override(_ key: String, _ value: Any) -> () -> Void {
        let defaults = UserDefaults.standard
        let previous = defaults.object(forKey: key)
        defaults.set(value, forKey: key)
        return {
            if let previous { defaults.set(previous, forKey: key) }
            else { defaults.removeObject(forKey: key) }
        }
    }

    /// Pre-CC7a behaviour, kept behind the conversation-thread switch.
    func testRTVIChunksReachTheExistingSingleResponseResult() async throws {
        let restoreLayout = override("mortimer.interface.layoutVersion", 2)
        let restoreThread = override(ConversationThread.flagKey, false)
        defer { restoreLayout(); restoreThread() }

        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        let transport = HostTranscriptTransport()
        let client = JarvisClient(config: config, stubTransport: transport)
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let conversation = ConversationStore()
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(),
                     displayResults: DisplayResultStore(), displayWindow: display,
                     workspace: workspace, conversation: conversation)

        try transport.emit("user-transcription", text: "Tell me the result", final: true)
        await flushTranscriptDelivery()
        try transport.emit("bot-llm-started")
        await flushTranscriptDelivery()
        try transport.emit("bot-llm-text", text: "A single ")
        await flushTranscriptDelivery()

        let firstID = try XCTUnwrap(workspace.activeResult?.id)
        XCTAssertEqual(workspace.results.count, 1)
        XCTAssertEqual(workspace.activeResult?.payload.body, "A single")
        XCTAssertEqual(conversation.latestCaptions.last?.text, "A single ")

        try transport.emit("bot-llm-text", text: "streamed answer.")
        await flushTranscriptDelivery()
        try transport.emit("bot-llm-stopped")
        await flushTranscriptDelivery()

        XCTAssertEqual(workspace.results.count, 1)
        XCTAssertEqual(workspace.activeResult?.id, firstID)
        XCTAssertEqual(workspace.activeResult?.payload.body, "A single streamed answer.")
        XCTAssertEqual(display.panels.count, 1)
        XCTAssertEqual(conversation.latestCaptions.last?.text, "A single streamed answer.")
        router.stop()
    }

    /// CC7a.1 (WS-17): with the thread on (the default), a streamed spoken
    /// answer stays in the conversation at full length and creates no
    /// workspace result or supporting-display panel.
    func testThreadKeepsSpokenAnswersOutOfResultsAndDisplay() async throws {
        let restoreLayout = override("mortimer.interface.layoutVersion", 2)
        let restoreThread = override(ConversationThread.flagKey, true)
        defer { restoreLayout(); restoreThread() }

        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        let transport = HostTranscriptTransport()
        let client = JarvisClient(config: config, stubTransport: transport)
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let conversation = ConversationStore()
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(),
                     displayResults: DisplayResultStore(), displayWindow: display,
                     workspace: workspace, conversation: conversation)
        let revision = workspace.consoleRevision
        let long = String(repeating: "Radar shows a line of storms west of Charleston. ", count: 6)

        try transport.emit("user-transcription", text: "What's the weather?", final: true)
        await flushTranscriptDelivery()
        try transport.emit("bot-llm-started")
        await flushTranscriptDelivery()
        try transport.emit("bot-llm-text", text: long)
        await flushTranscriptDelivery()
        try transport.emit("bot-llm-stopped")
        await flushTranscriptDelivery()

        XCTAssertTrue(workspace.results.isEmpty, "A spoken answer must not create a result.")
        XCTAssertTrue(display.panels.isEmpty, "A spoken answer must not reach the supporting display.")
        XCTAssertEqual(workspace.consoleRevision, revision)
        XCTAssertTrue(workspace.showsConversation)
        let rows = ConversationThread.rows(conversation.entries)
        XCTAssertEqual(rows.map(\.isUser), [true, false])
        XCTAssertEqual(rows.first?.text, "What's the weather?")
        XCTAssertGreaterThan(long.count, 160)
        XCTAssertEqual(rows.last?.text, long.trimmingCharacters(in: .whitespacesAndNewlines),
                       "The thread keeps the full answer, not a 160-character caption.")
        router.stop()
    }

    func testProtectedWindowDisplayStaysInMainWorkspaceAndNeverEntersSupportingDisplay() async throws {
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        let transport = HostTranscriptTransport()
        let client = JarvisClient(config: config, stubTransport: transport)
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let displayResults = DisplayResultStore()
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(),
                     displayResults: displayResults, displayWindow: display,
                     workspace: workspace)

        let privateBody = "PRIVATE ROUTER CANARY: local-only specialist answer"
        try transport.emitPayload([
            "type": "display",
            "display": [
                "kind": "markdown",
                "title": "Protected local result",
                "body": privateBody,
                "surface": "window",
                "tool": "protected_result",
                "data_policy": "local_only",
                "opaque_ref": "private-result-opaque-id",
            ],
        ])
        await flushTranscriptDelivery()

        XCTAssertEqual(workspace.results.count, 1)
        XCTAssertEqual(workspace.activeResult?.payload.body, privateBody,
                       "the protected answer must remain available in the main workspace")
        XCTAssertTrue(workspace.activeResult?.payload.isProtectedLocal == true)
        XCTAssertTrue(display.panels.isEmpty,
                      "protected payload must be rejected before entering supporting-display state")
        XCTAssertTrue(displayResults.results.isEmpty,
                      "protected payload must not enter the Output display store either")
        XCTAssertNil(workspace.supportingContent)
        XCTAssertFalse(String(describing: display.panels).contains(privateBody))
        XCTAssertFalse(String(describing: display.panels).contains("private-result-opaque-id"))
        router.stop()
    }
}
