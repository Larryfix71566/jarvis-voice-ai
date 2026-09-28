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
    func testRTVIChunksReachTheExistingSingleResponseResult() async throws {
        let defaults = UserDefaults.standard
        let key = "mortimer.interface.layoutVersion"
        let previousLayout = defaults.object(forKey: key)
        defaults.set(2, forKey: key)
        defer {
            if let previousLayout { defaults.set(previousLayout, forKey: key) }
            else { defaults.removeObject(forKey: key) }
        }

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
