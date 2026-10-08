import XCTest
import AppKit
import SwiftUI
@testable import JarvisKit
@testable import MortimerHost

/// Public synthetic messages through the real SDK decoder/router. The
/// transport cannot connect, and sharing writes only to a test-owned probe.
private final class ReuseIntegrationTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    private(set) var sent: [Data] = []
    private(set) var connectionAttempts = 0
    func connect(config: JarvisConfig) async throws {
        connectionAttempts += 1
        throw NSError(domain: "ReuseIntegrationTransport.NoNetwork", code: 1)
    }
    func disconnect() async {}
    func send(_ data: Data) throws { sent.append(data) }
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ message: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: [
            "id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": message,
        ])
        delegate?.transport(didReceiveFrame: frame)
    }
    var results: [ConsoleResult] {
        sent.compactMap { data in
            guard (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["type"] as? String == "console/result" else { return nil }
            return try? JSONDecoder().decode(ConsoleResult.self, from: data)
        }
    }
    var inventories: [ConsoleInventory] {
        sent.compactMap { data in
            guard (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["type"] as? String == "console/inventory" else { return nil }
            return try? JSONDecoder().decode(ConsoleInventory.self, from: data)
        }
    }
}

@MainActor
final class CC7a4ConversationIntegrationTests: XCTestCase {
    private static let sourceCanary = "PUBLIC SYNTHETIC RAW WEATHER SOURCE CANARY"
    private let aKey = "weather:named:folly beach"
    private let bKey = "weather:named:atlanta"

    private final class Probe { var copies: [String] = [] }
    private struct Fixture {
        let transport: ReuseIntegrationTransport
        let client: JarvisClient
        let session: UUID
        let generation: UUID
        let router: AppMessageRouter
        let workspace: WorkspaceStore
        let conversation: ConversationStore
        let output: DisplayResultStore
        let coordinator: ConsoleActionCoordinator
        let sharing: ShareCoordinator
        let probe: Probe
    }

    private func configureDefaults() throws -> () -> Void {
        guard Bundle.main.bundleIdentifier != "com.mortimer.host",
              ProcessInfo.processInfo.processName != "MortimerHost" else {
            throw NSError(domain: "CC7a4ConversationIntegrationTests.LiveProcess", code: 1)
        }
        let defaults = UserDefaults.standard
        let keys = ["mortimer.interface.layoutVersion", ConversationThread.flagKey]
        let previous = keys.map { defaults.object(forKey: $0) }
        defaults.set(2, forKey: keys[0]); defaults.set(true, forKey: keys[1])
        return {
            for (key, value) in zip(keys, previous) {
                if let value { defaults.set(value, forKey: key) }
                else { defaults.removeObject(forKey: key) }
            }
        }
    }

    private func fixture() async throws -> Fixture {
        _ = NSApplication.shared
        let transport = ReuseIntegrationTransport()
        let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:9")!,
            adminURL: URL(string: "http://127.0.0.1:9")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:9/ws")!, token: nil)
        let client = JarvisClient(config: config, stubTransport: transport, tokenProvider: { _ in nil })
        let workspace = WorkspaceStore(); workspace.quietArrivals = true
        let conversation = ConversationStore(), output = DisplayResultStore(), display = DisplayWindowStore()
        let drawer = DrawerState(), probe = Probe()
        let sharing = ShareCoordinator(clipboardWriter: { probe.copies.append($0); return true })
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: display,
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()), drawer: drawer,
            sharing: sharing, client: client, screens: { [] })
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: output,
            displayWindow: display, workspace: workspace, conversation: conversation,
            drawer: drawer, consoleCoordinator: coordinator)
        let session = UUID(), generation = UUID()
        try transport.emit(["type": "console/hello", "version": 1,
            "session_id": session.uuidString, "generation": generation.uuidString,
            "actions": ConsoleAction.allCases.map(\.rawValue), "input_types": []])
        try await wait("negotiated console identity") {
            client.consoleSessionID == session && client.consoleGeneration == generation && !transport.inventories.isEmpty
        }
        return Fixture(transport: transport, client: client, session: session, generation: generation,
            router: router, workspace: workspace, conversation: conversation, output: output,
            coordinator: coordinator, sharing: sharing, probe: probe)
    }

    private func wait(_ reason: String, _ condition: @MainActor () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(4)
        while !condition() {
            guard Date() < deadline else {
                XCTFail("Timed out: \(reason)")
                throw NSError(domain: "CC7a4ConversationIntegrationTests.Timeout", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: reason])
            }
            try await Task.sleep(for: .milliseconds(10))
        }
    }

    private func user(_ f: Fixture, _ text: String) async throws {
        let before = f.conversation.entries.count
        try f.transport.emit(["type": "user-transcription", "data": ["text": text, "final": true]])
        try await wait("user transcript") { f.conversation.entries.count == before + 1 }
    }

    private func run(_ f: Fixture, _ id: String) async throws {
        try f.transport.emit(["type": "agent", "state": "working", "name": "analyst", "run_id": id, "task": "weather"])
        // This event precedes subsequent requests on the same real stream.
        for _ in 0..<100 { await Task.yield() }
    }

    private func weather(_ key: String, city: String, ts: Double, structured: Bool = true,
                         runID: String? = nil, body: String = "Public weather summary") -> [String: Any] {
        var fields: [String: Any] = ["kind": structured ? "weather" : "markdown", "title": "Weather \(city)",
            "body": body, "tool": structured ? "weather_report" : "get_weather", "surface": "drawer",
            "data_policy": "approved_external", "subject_key": key, "ts": ts, "fresh_until": ts + 900,
            "weather_source": ["weather": ["city": city, "units": "imperial",
                "current": ["temperature_f": 82], "daily": (0..<7).map { ["day": $0, "max_f": 84] },
                "source_canary": Self.sourceCanary], "radar": ["tiles": ["https://example.test/radar.png"]],
                "subject_aliases": [city.lowercased()]]]
        if structured {
            fields["weather"] = ["schema": 1, "place": ["label": city, "source": "device", "approximate": false],
                "units": "imperial", "now": ["temp": "82°", "condition": "Sunny", "symbol": "sun.max"],
                "alerts": [], "summary": "Sunny", "attribution": "NWS"]
        }
        if let runID { fields["run_id"] = runID }
        return fields
    }

    @discardableResult
    private func deliver(_ f: Fixture, _ fields: [String: Any]) async throws -> WorkspaceResult {
        let key = fields["subject_key"] as! String
        let ts = fields["ts"] as! Double
        try f.transport.emit(["type": "display", "display": fields])
        try await wait("retained display payload") { f.workspace.results.contains { $0.payload.subjectKey == key && $0.payload.ts == ts } }
        let result = try XCTUnwrap(f.workspace.results.first { $0.payload.subjectKey == key })
        try await wait("published weather identity/freshness") {
            f.transport.inventories.last?.revision == f.workspace.consoleRevision
                && f.transport.inventories.last?.data["results"]?.arrayValue?.contains {
                    $0["id"]?.stringValue == result.id.uuidString && $0["subject_key"]?.stringValue == key
                } == true
        }
        return result
    }

    private func action(_ f: Fixture, _ action: ConsoleAction, target: UUID,
                        args: [String: JSONValue] = [:]) async throws -> ConsoleResult {
        let observed = try XCTUnwrap(f.transport.inventories.last)
        let request = ConsoleRequest(sessionID: f.session, generation: f.generation,
            requestID: UUID(), revision: observed.revision, action: action, target: target.uuidString, args: args)
        let data = try JSONEncoder().encode(request)
        try f.transport.emit(try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any]))
        try await wait("native action reply") { f.transport.results.contains { $0.requestID == request.requestID } }
        return try XCTUnwrap(f.transport.results.first { $0.requestID == request.requestID })
    }

    private func reuse(_ f: Fixture, key: String, runID: String? = nil,
                       tool: String = "get_weather") async throws -> ConsoleResult {
        let row = try XCTUnwrap(f.transport.inventories.last?.data["results"]?.arrayValue?.first {
            $0["subject_key"]?.stringValue == key
        })
        let target = try XCTUnwrap(row["id"]?.stringValue.flatMap(UUID.init(uuidString:)))
        var args: [String: JSONValue] = ["subject_key": .string(key), "tool": .string(tool),
            "days": .number(7), "units": .string("imperial"), "ordinary_turn": .bool(true)]
        if let runID { args["run_id"] = .string(runID) }
        return try await action(f, .weatherReuse, target: target, args: args)
    }

    func testWeatherAtlantaWeatherUsesPublishedIdentityAndOneOrderedReference() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let fetched = Date().timeIntervalSince1970 - 90
        try await user(f, "Weather for Folly Beach")
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fetched))
        f.workspace.returnToConversation(); f.coordinator.publishInventory()
        try await user(f, "Weather for Atlanta")
        let b = try await deliver(f, weather(bKey, city: "Atlanta", ts: fetched + 1))
        f.workspace.returnToConversation(); f.coordinator.publishInventory()
        try await user(f, "Folly Beach again")
        try await run(f, "current-reuse")
        let reply = try await reuse(f, key: aKey, runID: "current-reuse")
        XCTAssertEqual(reply.code, "cache_hit"); XCTAssertEqual(reply.data?["weather_source"], a.payload.weatherSource)
        XCTAssertEqual(reply.data?["ts"], .number(fetched)); XCTAssertEqual(reply.data?["fresh_until"], .number(fetched + 900))
        XCTAssertEqual(f.workspace.results.map(\.id), [a.id, b.id]); XCTAssertEqual(f.workspace.activeID, a.id)
        XCTAssertFalse(f.workspace.showsConversation)
        XCTAssertEqual(f.conversation.cachedReferences.count, 1)
        let reference = try XCTUnwrap(f.conversation.cachedReferences.first)
        XCTAssertEqual(reference.resultID, a.id); XCTAssertEqual(reference.runID, "current-reuse")
        let items = ConversationThread.items(rows: ConversationThread.rows(f.conversation.entries),
            cards: f.workspace.results.map(ConversationThread.card), references: f.conversation.cachedReferences)
        XCTAssertEqual(items.filter { if case .card = $0 { return true }; return false }.count, 2)
        XCTAssertEqual(items.last, .cachedReference(reference))
        XCTAssertFalse(f.conversation.entries.map(\.text).joined().contains(Self.sourceCanary))
        XCTAssertFalse(f.client.transcript.map(\.text).joined().contains(Self.sourceCanary))
        XCTAssertFalse(reference.text.contains(Self.sourceCanary)); XCTAssertEqual(f.transport.connectionAttempts, 0)
    }

    func testDirectCacheHitWhileReadingPreservesFocusAndShowsNew() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let fetched = Date().timeIntervalSince1970 - 30
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fetched))
        let b = try await deliver(f, weather(bKey, city: "Atlanta", ts: fetched))
        f.workspace.select(b.id); f.coordinator.publishInventory()
        try await user(f, "Folly Beach again")
        let reply = try await reuse(f, key: aKey)
        XCTAssertEqual(reply.code, "cache_hit"); XCTAssertEqual(f.workspace.activeID, b.id)
        XCTAssertEqual(f.workspace.arrivalNoticeID, a.id); XCTAssertTrue(f.workspace.unreadIDs.contains(a.id))
        XCTAssertEqual(f.conversation.cachedReferences.count, 1)
        XCTAssertEqual(f.workspace.results.map(\.id), [a.id, b.id]); XCTAssertEqual(f.transport.connectionAttempts, 0)
    }

    func testReplacedRunCacheHitKeepsConversationAndRetainedSource() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let fetched = Date().timeIntervalSince1970 - 30
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fetched))
        let b = try await deliver(f, weather(bKey, city: "Atlanta", ts: fetched))
        f.workspace.select(b.id); f.workspace.returnToConversation(); f.coordinator.publishInventory()
        try await user(f, "Earlier weather question"); try await run(f, "old-weather-run")
        try await Task.sleep(for: .milliseconds(10))
        try await user(f, "A new question"); try await run(f, "replacement-weather-run")
        let reply = try await reuse(f, key: aKey, runID: "old-weather-run")
        XCTAssertEqual(reply.code, "cache_hit"); XCTAssertEqual(reply.data?["ts"], .number(fetched))
        XCTAssertTrue(f.workspace.showsConversation); XCTAssertEqual(f.workspace.activeID, b.id)
        XCTAssertTrue(f.workspace.unreadIDs.contains(a.id)); XCTAssertEqual(f.workspace.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(f.conversation.cachedReferences.first?.resultID, a.id)
    }

    func testWeatherAndRadarInOneOriginatingRunAppendOnlyOneReference() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let fetched = Date().timeIntervalSince1970 - 250
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fetched))
        try await user(f, "Weather and radar again"); try await run(f, "paired-reuse")
        let weatherReply = try await reuse(f, key: aKey, runID: "paired-reuse")
        let radarReply = try await reuse(f, key: aKey, runID: "paired-reuse", tool: "get_weather_radar")
        XCTAssertEqual(weatherReply.code, "cache_hit"); XCTAssertEqual(radarReply.code, "cache_hit")
        XCTAssertEqual(f.conversation.cachedReferences.count, 1)
        XCTAssertEqual(f.conversation.cachedReferences.first?.resultID, a.id)
        XCTAssertEqual(f.workspace.results.count, 1); XCTAssertEqual(f.workspace.results[0].payload.ts, fetched)
        let originalReference = try XCTUnwrap(f.conversation.cachedReferences.first)
        XCTAssertTrue(originalReference.text.contains(Date(timeIntervalSince1970: fetched).formatted(date: .omitted, time: .shortened)))
        let newerFetch = Date().timeIntervalSince1970 - 125
        let refreshed = try await deliver(f, weather(aKey, city: "Folly Beach", ts: newerFetch,
            runID: "paired-reuse", body: "Genuinely refreshed public weather"))
        let updatedReference = try XCTUnwrap(f.conversation.cachedReferences.first)
        XCTAssertEqual(f.conversation.cachedReferences.count, 1)
        XCTAssertEqual(updatedReference.id, originalReference.id); XCTAssertEqual(updatedReference.time, originalReference.time)
        XCTAssertEqual(updatedReference.resultID, a.id); XCTAssertEqual(refreshed.id, a.id)
        XCTAssertTrue(updatedReference.text.contains("Updated"))
        XCTAssertTrue(updatedReference.text.contains(Date(timeIntervalSince1970: newerFetch).formatted(date: .omitted, time: .shortened)))
        XCTAssertFalse(updatedReference.text.contains(Self.sourceCanary))
        XCTAssertEqual(f.workspace.results.count, 1); XCTAssertEqual(f.workspace.results[0].payload.ts, newerFetch)
    }

    func testClosedWeatherCardCannotResurrectCacheAndOutputKeepsHistory() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let fetched = Date().timeIntervalSince1970 - 30
        // Legacy markdown weather follows the real drawer/Output route.
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fetched, structured: false))
        try await user(f, "Folly Beach again")
        let hit = try await reuse(f, key: aKey)
        XCTAssertEqual(hit.code, "cache_hit")
        let output = f.output.results
        XCTAssertEqual(output.count, 1); XCTAssertEqual(output[0].workspaceID, a.id)
        let closed = try await action(f, .resultClose, target: a.id)
        XCTAssertEqual(closed.code, "applied")
        XCTAssertFalse(f.workspace.containsResult(a.id)); XCTAssertEqual(f.output.results, output)
        let reply = try await action(f, .weatherReuse, target: a.id, args: ["subject_key": .string(aKey),
            "tool": .string("get_weather"), "days": .number(7), "units": .string("imperial"), "ordinary_turn": .bool(true)])
        XCTAssertEqual(reply.code, "result_unavailable"); XCTAssertNil(reply.data)
        XCTAssertTrue(f.workspace.results.isEmpty); XCTAssertEqual(f.conversation.cachedReferences.count, 1)
        let cards = ConversationThread.items(rows: ConversationThread.rows(f.conversation.entries),
            cards: f.workspace.results.map(ConversationThread.card), references: f.conversation.cachedReferences)
        XCTAssertFalse(cards.contains { if case .card = $0 { return true }; return false })
        XCTAssertEqual(f.output.results, output)
    }

    func testStaleRefreshThroughRouterRetainsReaderStateAndOutputOwnership() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let oldFetch = Date().timeIntervalSince1970 - 1_000
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: oldFetch, structured: false))
        let b = try await deliver(f, weather(bKey, city: "Atlanta", ts: Date().timeIntervalSince1970 - 30, structured: false))
        f.workspace.select(b.id); XCTAssertTrue(f.workspace.pin(a.id)); XCTAssertTrue(f.workspace.compare(with: a.id))
        f.workspace.rememberScroll(240, for: a.id)
        let presentation = f.workspace.presentation(for: a); presentation.mode = .sources; presentation.showsInspector = true
        let oldOutput = f.output.results
        f.coordinator.publishInventory()
        let expired = try await reuse(f, key: aKey)
        XCTAssertEqual(expired.code, "cache_expired")
        XCTAssertTrue(f.conversation.cachedReferences.isEmpty)
        try await user(f, "Refresh stale Folly Beach"); try await run(f, "stale-refresh-origin")
        // Fetch time deliberately differs from arrival by multiple minutes,
        // so substituting the display-arrival clock cannot satisfy D2.
        let fresh = Date().timeIntervalSince1970 - 125
        let refreshed = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fresh, structured: false,
            runID: "stale-refresh-origin", body: "Refreshed public weather"))
        XCTAssertEqual(refreshed.id, a.id); XCTAssertEqual(f.workspace.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(f.workspace.activeID, b.id); XCTAssertEqual(f.workspace.comparisonID, a.id)
        XCTAssertTrue(f.workspace.pinnedIDs.contains(a.id)); XCTAssertEqual(f.workspace.scrollOffsets[a.id], 240)
        XCTAssertTrue(f.workspace.presentation(for: refreshed) === presentation)
        XCTAssertEqual(presentation.mode, .sources); XCTAssertTrue(presentation.showsInspector)
        XCTAssertEqual(f.output.results.count, oldOutput.count + 1)
        XCTAssertEqual(f.output.results.first?.workspaceID, a.id); XCTAssertEqual(Array(f.output.results.dropFirst()), oldOutput)
        XCTAssertEqual(f.output.results.first?.payload.ts, fresh); XCTAssertEqual(f.workspace.arrivalNoticeID, a.id)
        XCTAssertEqual(f.conversation.cachedReferences.count, 1, "D2: stale refresh adds one Updated reference")
        for reference in f.conversation.cachedReferences {
            XCTAssertEqual(reference.resultID, a.id); XCTAssertEqual(reference.runID, "stale-refresh-origin")
            XCTAssertTrue(reference.text.contains("Updated"))
            XCTAssertTrue(reference.text.contains(Date(timeIntervalSince1970: fresh).formatted(date: .omitted, time: .shortened)),
                          "Reference uses the actual source-fetch time")
            XCTAssertFalse(reference.text.contains(Self.sourceCanary))
        }
        // A second valid arrival from this originating run still has only
        // its one ordered reference; it never retargets the reader.
        _ = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fresh + 1, structured: false,
            runID: "stale-refresh-origin", body: "Same-run refreshed weather"))
        XCTAssertEqual(f.conversation.cachedReferences.count, 1)
        XCTAssertEqual(f.workspace.activeID, b.id); XCTAssertEqual(f.workspace.comparisonID, a.id)
        XCTAssertEqual(f.workspace.scrollOffsets[a.id], 240)
        XCTAssertTrue(f.workspace.presentation(for: f.workspace.results[0]) === presentation)
        XCTAssertEqual(Array(f.output.results.suffix(oldOutput.count)), oldOutput)
    }

    func testRoutedReplayAndIneligibleWeatherRefreshDoNotAddUpdatedReferences() async throws {
        let restore = try configureDefaults(); defer { restore() }
        func exercise(_ scenario: String, replayOffset: Double? = nil, policy: String = "approved_external",
                      invalidSource: Bool = false, providerFailure: [String: Any]? = nil,
                      radarOnlyFailure: Bool = false) async throws {
            let f = try await fixture(); defer { f.router.stop() }
            let originalFetch = Date().timeIntervalSince1970 - 1_000
            let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: originalFetch, structured: false))
            try await user(f, "Refresh weather"); try await run(f, "negative-refresh-origin")
            let nextFetch = replayOffset.map { originalFetch + $0 } ?? Date().timeIntervalSince1970 - 125
            var fields = weather(aKey, city: "Folly Beach", ts: nextFetch, structured: false,
                runID: "negative-refresh-origin", body: "Synthetic \(scenario) body")
            fields["data_policy"] = policy
            if invalidSource { fields["weather_source"] = ["weather": "invalid cache source"] }
            if let providerFailure {
                var source = fields["weather_source"] as! [String: Any]
                let field = radarOnlyFailure ? "radar" : "weather"
                var part = source[field] as! [String: Any]
                part.merge(providerFailure) { _, failure in failure }; source[field] = part
                if radarOnlyFailure { source.removeValue(forKey: "weather") }
                fields["weather_source"] = source
            }
            try f.transport.emit(["type": "display", "display": fields])
            try await wait("routed \(scenario) arrival") {
                f.workspace.results.contains { $0.payload.body == "Synthetic \(scenario) body" }
            }
            XCTAssertTrue(f.conversation.cachedReferences.isEmpty, "\(scenario) is not evidence of a new public fetch")
            XCTAssertFalse(f.conversation.entries.map(\.text).joined().contains(Self.sourceCanary))
            if policy != "approved_external" {
                XCTAssertEqual(f.workspace.results.first { $0.id == a.id }?.payload.ts, originalFetch,
                               "Private/unknown provenance must not overwrite the public identity")
            }
        }
        try await exercise("same timestamp", replayOffset: 0)
        try await exercise("older timestamp", replayOffset: -1)
        try await exercise("private policy", policy: "local_only")
        try await exercise("unknown policy", policy: "unknown_policy")
        try await exercise("invalid source", invalidSource: true)
        try await exercise("weather ok false", providerFailure: ["ok": false])
        try await exercise("weather provider error", providerFailure: ["error": "synthetic_provider_failure"])
        try await exercise("radar ok false", providerFailure: ["ok": false], radarOnlyFailure: true)
        try await exercise("radar provider error", providerFailure: ["error": "synthetic_provider_failure"], radarOnlyFailure: true)
    }

    private func accessibilityObjects(_ root: NSView) -> [NSObject] {
        var objects: [NSObject] = [], seen = Set<ObjectIdentifier>()
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            objects.append(object)
            let selector = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: selector), let children = object.perform(selector)?.takeUnretainedValue() as? [Any] {
                children.forEach(visit)
            }
        }
        visit(root); return objects
    }

    private func label(_ object: NSObject) -> String {
        for name in ["accessibilityLabel", "accessibilityTitle", "accessibilityValue"] {
            let selector = NSSelectorFromString(name)
            if object.responds(to: selector), let value = object.perform(selector)?.takeUnretainedValue() {
                if let text = value as? String, !text.isEmpty { return text }
                if let text = value as? NSAttributedString, !text.string.isEmpty { return text.string }
            }
        }
        return ""
    }

    func testActualCachedReferenceButtonReopensCanonicalResultAndRawSourceNeverLeaksToShare() async throws {
        let restore = try configureDefaults(); defer { restore() }
        let f = try await fixture(); defer { f.router.stop() }
        let fetched = Date().timeIntervalSince1970 - 90
        let a = try await deliver(f, weather(aKey, city: "Folly Beach", ts: fetched))
        let b = try await deliver(f, weather(bKey, city: "Atlanta", ts: fetched))
        try await user(f, "Folly Beach again"); _ = try await reuse(f, key: aKey)
        f.workspace.select(b.id); f.workspace.returnToConversation()
        let reference = try XCTUnwrap(f.conversation.cachedReferences.first)
        let app = NSApplication.shared
        app.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let root = AnyView(ConversationThreadView(coordinator: f.coordinator).environment(f.workspace)
            .environment(f.conversation).environment(\.mortimerReduceMotion, true)
            .padding(4).background(AppTheme.bg).foregroundStyle(AppTheme.text).preferredColorScheme(.dark))
        let view = NSHostingView(rootView: root); view.frame = NSRect(x: 0, y: 0, width: 900, height: 600)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view
        if let screen = NSScreen.main ?? NSScreen.screens.first {
            window.setFrameOrigin(NSPoint(x: screen.visibleFrame.midX - 450, y: screen.visibleFrame.midY - 300))
        }
        window.level = .floating
        window.makeKeyAndOrderFront(nil); window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        defer { closeRenderingFixtureWindow(window) }
        let pressSelector = NSSelectorFromString("accessibilityPerformPress")
        try await wait("actual cached reference button") {
            self.accessibilityObjects(view).contains { self.label($0) == reference.text && $0.responds(to: pressSelector) }
        }
        let control = try XCTUnwrap(accessibilityObjects(view).first { label($0) == reference.text && $0.responds(to: pressSelector) })
        typealias Press = @convention(c) (AnyObject, Selector) -> Bool
        let press = unsafeBitCast(control.method(for: pressSelector), to: Press.self)
        XCTAssertTrue(press(control, pressSelector))
        try await wait("canonical reference selection") { f.workspace.activeID == a.id && !f.workspace.showsConversation }
        XCTAssertEqual(f.workspace.results.map(\.id), [a.id, b.id]); XCTAssertEqual(f.workspace.results[0].payload.ts, fetched)
        XCTAssertFalse(accessibilityObjects(view).map(label).joined().contains(Self.sourceCanary))
        XCTAssertEqual(f.coordinator.executePointer(.sharePreview, target: a.id.uuidString), .applied)
        XCTAssertEqual(f.sharing.preview?.resultID, a.id); XCTAssertFalse(f.sharing.preview?.text.contains(Self.sourceCanary) ?? true)
        XCTAssertEqual(f.coordinator.executePointer(.shareCopy), .applied)
        XCTAssertEqual(f.probe.copies.count, 1); XCTAssertFalse(f.probe.copies[0].contains(Self.sourceCanary))
        XCTAssertFalse(f.conversation.entries.map(\.text).joined().contains(Self.sourceCanary))
        XCTAssertEqual(f.conversation.cachedReferences.count, 1); XCTAssertEqual(f.transport.connectionAttempts, 0)
    }

    func testConversationOwnerBoundsDedupeAndClearingReferences() throws {
        let now = Date(), fetched = now.timeIntervalSince1970 - 30
        let decode: ([String: Any]) throws -> DisplayPayload = {
            try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: $0))
        }
        let a = WorkspaceResult(payload: try decode(weather(aKey, city: "Folly Beach", ts: fetched)))
        let b = WorkspaceResult(payload: try decode(weather(bKey, city: "Atlanta", ts: fetched)))
        let store = ConversationStore(), requestID = UUID()
        store.recordCachedResult(a, fetchedAt: fetched, requestID: requestID, runID: "one-origin", now: now)
        store.recordCachedResult(a, fetchedAt: fetched, requestID: requestID, runID: "one-origin", now: now)
        store.recordCachedResult(b, fetchedAt: fetched, requestID: UUID(), runID: "one-origin", now: now)
        XCTAssertEqual(store.cachedReferences.count, 1, "One ordered reference per originating run")
        for _ in 0...AppTuning.maxConversationEntries {
            store.recordCachedResult(a, fetchedAt: fetched, requestID: UUID(), runID: nil, now: now)
        }
        XCTAssertEqual(store.cachedReferences.count, AppTuning.maxConversationEntries)
        store.set([]); XCTAssertTrue(store.cachedReferences.isEmpty)
        store.recordCachedResult(a, fetchedAt: fetched, requestID: UUID(), runID: nil, now: now)
        store.clear(); XCTAssertTrue(store.cachedReferences.isEmpty); XCTAssertTrue(store.entries.isEmpty)
    }
}
