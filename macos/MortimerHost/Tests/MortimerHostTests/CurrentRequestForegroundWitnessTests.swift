import XCTest
@testable import JarvisKit
@testable import MortimerHost

/// The same public synthetic test compiles against baseline and candidate.
/// It exercises real SDK decoding/router/store calls, without provider/audio.
private final class ForegroundWitnessTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws { XCTFail("No connection is permitted") }
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ message: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: [
            "id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": message])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class CurrentRequestForegroundWitnessTests: XCTestCase {
    func testSecondRequestedCityOpensFromTheFirstResultThroughActualCallerChain() async throws {
        let transport = ForegroundWitnessTransport()
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:9")!,
            adminURL: URL(string: "http://127.0.0.1:9")!, wakeWordURL: URL(string: "ws://127.0.0.1:9/ws")!,
            token: nil), stubTransport: transport)
        let workspace = WorkspaceStore(); workspace.quietArrivals = true
        let router = AppMessageRouter(), conversation = ConversationStore()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: DisplayResultStore(),
            displayWindow: DisplayWindowStore(), workspace: workspace, conversation: conversation)
        defer { router.stop() }
        let session = UUID(), generation = UUID()
        client.setConsoleIdentity(sessionID: session, generation: generation)

        func settle(_ condition: @MainActor () -> Bool) async throws {
            let deadline = Date().addingTimeInterval(4)
            while !condition() {
                guard Date() < deadline else { return XCTFail("Actual caller chain did not receive the synthetic event") }
                try await Task.sleep(for: .milliseconds(10))
            }
        }
        func answer(_ city: String, sequence: Int) throws {
            let origin = UUID(), timestamp = "synthetic-city-\(sequence)"
            try transport.emit(["type": "user-transcription", "data": ["text": "Weather in \(city)",
                "final": true, "timestamp": timestamp, "user_id": "synthetic-user"]])
            try transport.emit(["type": "console/turn", "version": 1, "session_id": session.uuidString,
                "generation": generation.uuidString, "request_id": origin.uuidString,
                "sequence": sequence, "state": "started", "input_timestamp": timestamp,
                "input_user_id": "synthetic-user"])
            try transport.emit(["type": "display", "display": ["kind": "weather", "tool": "weather_report",
                "title": "Weather — \(city)", "surface": "window", "origin_request_id": origin.uuidString,
                "weather": ["schema": 1, "place": ["label": city, "source": "device", "approximate": false],
                    "units": "imperial", "now": ["temp": "70°", "condition": "Clear", "symbol": "sun.max"],
                    "alerts": [], "summary": "Public synthetic weather", "attribution": "Synthetic"]]])
        }
        try answer("Spartanburg", sequence: 1)
        try await settle { workspace.results.count == 1 }
        let first = try XCTUnwrap(workspace.results.first)
        XCTAssertEqual(workspace.activeID, first.id); XCTAssertFalse(workspace.showsConversation)
        try answer("Atlanta", sequence: 2)
        try await settle { workspace.results.count == 2 }
        let second = try XCTUnwrap(workspace.results.last)
        XCTAssertNotEqual(first.id, second.id)
        XCTAssertEqual(workspace.activeID, second.id, "The still-current request opens while the first result is being read.")
        XCTAssertFalse(workspace.unreadIDs.contains(second.id), "The current answer has actually opened.")
        XCTAssertEqual(conversation.entries.filter { $0.role == "user" }.count, 2)
    }
}
