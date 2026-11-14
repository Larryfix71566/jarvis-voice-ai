import XCTest
@testable import JarvisKit
@testable import MortimerHost

private final class CarouselReuseTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ data: [String: Any]) throws {
        delegate?.transport(didReceiveFrame: try JSONSerialization.data(withJSONObject: [
            "id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": data]))
    }
}

@MainActor
final class ResultCarouselReuseTests: XCTestCase {
    private let folly = "weather:named:folly beach"
    private let atlanta = "weather:named:atlanta"

    private func weather(_ key: String, fetched: Double = 1_000, answer: UUID? = nil) throws -> WorkspaceResult {
        var fields: [String: Any] = ["kind": "weather", "tool": "weather_report", "title": key,
            "body": "Retained weather", "ts": fetched, "subject_key": key,
            "fresh_until": fetched + 900, "data_policy": "approved_external",
            "weather_source": ["weather": ["city": key, "units": "imperial",
                "current": ["temperature_f": 82], "daily": [["day": 0, "high_f": 84]]]]]
        if let answer { fields["answer_id"] = answer.uuidString; fields["answer_revision"] = 1 }
        return WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: fields)), receivedAt: Date(timeIntervalSince1970: fetched))
    }

    private func query(_ store: WorkspaceStore, target: UUID, now: Double) -> WeatherReuseReply {
        store.queryWeatherReuse(target: target, subjectKey: folly, tool: "get_weather", days: 1,
            units: "imperial", now: Date(timeIntervalSince1970: now), ordinaryTurn: true, answersCurrentRequest: true)
    }

    func testFollyAtlantaFollyWithinFifteenMinutesReopensOriginalCarouselCard() throws {
        let store = WorkspaceStore(), a = try weather(folly), b = try weather(atlanta)
        store.receive(a, quietly: true); store.receive(b, quietly: true)
        XCTAssertTrue(store.pin(a.id)); store.rememberScroll(240, for: a.id); store.select(b.id)
        let presentation = store.presentation(for: a)
        for now in [1_100.0, 1_899.0] {
            guard case .hit(let source, let ts, let expiry, _) = query(store, target: a.id, now: now) else {
                return XCTFail("Expected original retained weather before the 15-minute expiry")
            }
            XCTAssertEqual(source, a.payload.weatherSource); XCTAssertEqual(ts, 1_000); XCTAssertEqual(expiry, 1_900)
            XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
            XCTAssertEqual(Set(store.carouselResults.map(\.id)), Set([a.id, b.id]))
            XCTAssertEqual(store.carouselFrontResult?.id, a.id)
            XCTAssertEqual(store.results[0].payload, a.payload)
            XCTAssertEqual(store.results[0].receivedAt, a.receivedAt)
            XCTAssertTrue(store.pinnedIDs.contains(a.id)); XCTAssertEqual(store.scrollOffsets[a.id], 240)
            XCTAssertTrue(store.presentation(for: store.results[0]) === presentation)
        }
    }

    func testExpiredRefreshWithNewComposerIdentityReusesSemanticWeatherCard() throws {
        for composed in [false, true] {
            let store = WorkspaceStore()
            let a = try weather(folly, answer: composed ? UUID() : nil)
            let b = try weather(atlanta, answer: composed ? UUID() : nil)
            store.receive(a, quietly: true); store.receive(b, quietly: true); store.select(b.id)
            XCTAssertTrue(store.pin(a.id)); store.rememberScroll(300, for: a.id)
            let presentation = store.presentation(for: a)
            XCTAssertEqual(query(store, target: a.id, now: 1_900), .miss("cache_expired"))
            let refreshed = try weather(folly, fetched: 2_000, answer: composed ? UUID() : nil)
            XCTAssertEqual(store.reuseExistingIdentity(for: refreshed.payload), a.id)
            XCTAssertEqual(store.receive(refreshed, quietly: true, answersCurrentRequest: true), a.id)
            XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
            XCTAssertEqual(store.carouselResults.count, 2)
            XCTAssertEqual(store.carouselFrontResult?.id, a.id)
            XCTAssertEqual(store.results[0].payload.ts, 2_000)
            XCTAssertEqual(store.results[0].receivedAt, a.receivedAt)
            XCTAssertEqual(store.results[0].payload.answerID, refreshed.payload.answerID)
            XCTAssertTrue(store.pinnedIDs.contains(a.id)); XCTAssertEqual(store.scrollOffsets[a.id], 300)
            XCTAssertTrue(store.presentation(for: store.results[0]) === presentation)
        }
    }

    func testRealCoordinatorCacheHitDoesNotCreateFetchOrCarouselCard() throws {
        let store = WorkspaceStore(), a = try weather(folly, answer: UUID()), b = try weather(atlanta, answer: UUID())
        store.receive(a, quietly: true); store.receive(b, quietly: true); store.select(b.id)
        let client = JarvisClient(); client.setConsoleIdentity(sessionID: UUID(), generation: UUID())
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(workspace: store, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()), client: client, screens: { [] })
        let request = ConsoleRequest(sessionID: client.consoleSessionID!, generation: client.consoleGeneration!,
            requestID: UUID(), revision: store.consoleRevision, action: .weatherReuse, target: a.id.uuidString,
            args: ["subject_key": .string(folly), "tool": .string("get_weather"), "days": .number(1),
                   "units": .string("imperial"), "ordinary_turn": .bool(true)])
        let reply = try XCTUnwrap(coordinator.executeWeatherReuse(request,
            now: Date(timeIntervalSince1970: 1_100), answersCurrentRequest: true))
        XCTAssertEqual(reply.code, "cache_hit")
        XCTAssertEqual(reply.data?["ts"], .number(1_000))
        XCTAssertEqual(reply.data?["weather_source"], a.payload.weatherSource)
        XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(store.carouselResults.count, 2)
        XCTAssertEqual(store.carouselFrontResult?.id, a.id)
        XCTAssertEqual(store.results[0].payload, a.payload)
    }
    func testRouterReuseAddsOneReferenceWithoutSummaryOrCardDuplicate() async throws {
        let store = WorkspaceStore(), transport = CarouselReuseTransport()
        let now = Date().timeIntervalSince1970
        let a = try weather(folly, fetched: now - 100, answer: UUID())
        let b = try weather(atlanta, fetched: now - 50, answer: UUID())
        store.receive(a, quietly: true); store.receive(b, quietly: true); store.select(b.id)
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil), stubTransport: transport)
        let drawer = DrawerState(), display = DisplayWindowStore(), conversation = ConversationStore()
        let coordinator = ConsoleActionCoordinator(workspace: store, display: display,
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()), client: client, screens: { [] })
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: DisplayResultStore(),
            displayWindow: display, workspace: store, conversation: conversation, drawer: drawer,
            consoleCoordinator: coordinator)
        defer { router.stop() }
        let session = UUID(), generation = UUID(), origin = UUID()
        try transport.emit(["type": "console/hello", "version": 1, "session_id": session.uuidString,
            "generation": generation.uuidString, "actions": [], "input_types": []])
        try transport.emit(["type": "user-started-speaking"])
        try transport.emit(["type": "user-transcription", "data": ["text": "Folly Beach again", "final": true,
            "timestamp": "reuse-input", "user_id": "synthetic-user"]])
        try transport.emit(["type": "console/turn", "version": 1, "session_id": session.uuidString,
            "generation": generation.uuidString, "request_id": origin.uuidString, "sequence": 1, "state": "started",
            "input_timestamp": "reuse-input", "input_user_id": "synthetic-user"])
        for _ in 0..<200 { await Task.yield() }
        let transcript = conversation.entries
        try transport.emit(["type": "console/request", "version": 1, "session_id": session.uuidString,
            "generation": generation.uuidString, "request_id": UUID().uuidString, "revision": store.consoleRevision,
            "action": "weather_reuse", "target": a.id.uuidString,
            "args": ["subject_key": folly, "tool": "get_weather", "days": 1, "units": "imperial",
                     "ordinary_turn": true, "origin_request_id": origin.uuidString]])
        for _ in 0..<200 { await Task.yield() }
        XCTAssertEqual(store.carouselFrontResult?.id, a.id)
        XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(store.carouselResults.count, 2)
        XCTAssertEqual(store.results[0].payload, a.payload)
        XCTAssertEqual(conversation.entries, transcript, "Reuse must not insert a fabricated summary into the transcript")
        XCTAssertEqual(conversation.cachedReferences.count, 1)
        XCTAssertEqual(conversation.cachedReferences.first?.resultID, a.id)
        XCTAssertTrue(conversation.cachedReferences.first?.text.hasPrefix("Reopened ") == true)
    }

}
