import XCTest
import JarvisKit
@testable import MortimerHost

/// CC7a.4: the retained native result is the only weather cache. Synthetic
/// source JSON is never fetched from a provider or persisted by these tests.
@MainActor
final class CC7a4ReuseTests: XCTestCase {
    private let aKey = "weather:named:folly beach"
    private let bKey = "weather:named:atlanta"

    private func source(days: Int = 7, units: String = "imperial", radar: Bool = true) -> [String: Any] {
        var value: [String: Any] = [
            "weather": ["city": "Folly Beach", "units": units,
                        "current": ["temperature_f": 82],
                        "daily": (0..<days).map { ["day": $0, "high_f": 84] }],
            "place": ["label": "Folly Beach", "source": "device"],
            "subject_aliases": ["folly beach"],
        ]
        if radar { value["radar"] = ["tiles": ["https://example.test/radar/1.png"]] }
        return value
    }

    private func weather(_ key: String? = nil, ts: Double = 1_000, expiry: Double? = nil,
                         policy: String? = "approved_external", original: [String: Any]? = nil,
                         title: String = "Weather", extra: [String: Any] = [:]) -> WorkspaceResult {
        var fields: [String: Any] = ["kind": "weather", "tool": "weather_report",
                                   "title": title, "body": "Legacy weather body", "ts": ts,
                                   "subject_key": key ?? aKey, "fresh_until": expiry ?? ts + 900,
                                   "weather_source": original ?? source()]
        if let policy { fields["data_policy"] = policy }
        fields.merge(extra) { _, replacement in replacement }
        let data = try! JSONSerialization.data(withJSONObject: fields)
        return WorkspaceResult(payload: try! JSONDecoder().decode(DisplayPayload.self, from: data),
                               receivedAt: Date(timeIntervalSince1970: ts))
    }

    private func query(_ store: WorkspaceStore, _ item: WorkspaceResult, key: String? = nil,
                       tool: String = "get_weather", days: Int = 7, units: String = "imperial",
                       now: Double = 1_100, ordinary: Bool = true,
                       answersCurrentRequest: Bool = false) -> WeatherReuseReply {
        store.queryWeatherReuse(target: item.id, subjectKey: key ?? aKey, tool: tool, days: days,
                                units: units, now: Date(timeIntervalSince1970: now), ordinaryTurn: ordinary,
                                answersCurrentRequest: answersCurrentRequest)
    }

    func testWeatherAtlantaWeatherHitKeepsTwoCardsAndReadingFocus() {
        let store = WorkspaceStore()
        let a = weather(title: "Folly Beach")
        let b = weather(bKey, title: "Atlanta")
        store.receive(a, quietly: true)
        store.receive(b, quietly: true)
        store.select(b.id)
        let revision = store.consoleRevision
        let reply = query(store, a, answersCurrentRequest: true)
        XCTAssertEqual(reply, .hit(source: a.payload.weatherSource!, ts: 1_000,
                                   freshUntil: 1_900, revision: store.consoleRevision))
        XCTAssertGreaterThan(store.consoleRevision, revision)
        XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(store.activeID, b.id)
        XCTAssertEqual(store.arrivalNoticeID, a.id)
        XCTAssertTrue(store.unreadIDs.contains(a.id))
        XCTAssertEqual(store.results[0].payload, a.payload, "A hit does not fabricate another fetch timestamp")
    }

    func testExpiredRefreshRetainsIdentityPinComparisonInspectorScrollAndOutputPointer() {
        let store = WorkspaceStore()
        let a = weather(title: "Folly Beach")
        let b = weather(bKey, title: "Atlanta")
        store.receive(a, quietly: true); store.receive(b, quietly: true)
        store.select(b.id)
        XCTAssertTrue(store.pin(a.id)); XCTAssertTrue(store.compare(with: a.id))
        store.rememberScroll(240, for: a.id)
        let presentation = store.presentation(for: a)
        presentation.mode = .sources; presentation.showsInspector = true; presentation.selectedSource = 1
        XCTAssertTrue(store.sendToDisplay(.result(a.id)))
        let revision = store.consoleRevision
        XCTAssertEqual(query(store, a, now: 1_900), .miss("cache_expired"))
        XCTAssertEqual(store.consoleRevision, revision)
        let refreshed = weather(ts: 2_000, title: "Folly Beach refreshed")
        XCTAssertEqual(store.reuseExistingIdentity(for: refreshed.payload), a.id)
        XCTAssertEqual(store.receive(refreshed, quietly: true, answersCurrentRequest: true), a.id)
        XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(store.results[0].payload.ts, 2_000)
        XCTAssertEqual(store.results[0].receivedAt, a.receivedAt)
        XCTAssertTrue(store.pinnedIDs.contains(a.id))
        XCTAssertEqual(store.activeID, b.id); XCTAssertEqual(store.comparisonID, a.id)
        XCTAssertEqual(store.supportingContent, .result(a.id))
        XCTAssertEqual(store.scrollOffsets[a.id], 240)
        XCTAssertTrue(store.presentation(for: store.results[0]) === presentation)
        XCTAssertEqual(presentation.mode, .sources); XCTAssertTrue(presentation.showsInspector)
        XCTAssertEqual(presentation.selectedSource, 1)
        XCTAssertEqual(store.arrivalNoticeID, a.id)
    }

    func testRequestedHitOpensFromConversationAndReturnsPostSelectionRevision() {
        let store = WorkspaceStore(); let a = weather()
        store.receive(a, quietly: true); store.returnToConversation()
        XCTAssertEqual(query(store, a, answersCurrentRequest: true), .hit(source: a.payload.weatherSource!, ts: 1_000,
                                           freshUntil: 1_900, revision: store.consoleRevision))
        XCTAssertEqual(store.activeID, a.id); XCTAssertFalse(store.showsConversation)
        XCTAssertFalse(store.unreadIDs.contains(a.id))
    }

    func testHitDoesNotDuplicateSupportingRendererOrInterruptAnotherView() {
        let store = WorkspaceStore(); let a = weather()
        store.receive(a, quietly: true); store.returnToConversation()
        XCTAssertTrue(store.sendToDisplay(.result(a.id)))
        _ = query(store, a, answersCurrentRequest: true)
        XCTAssertTrue(store.showsConversation)
        XCTAssertEqual(store.supportingContent, .result(a.id))
        store.openSkills()
        _ = query(store, a, answersCurrentRequest: true)
        XCTAssertTrue(store.showsSkills); XCTAssertFalse(store.showsConversation)
        XCTAssertEqual(store.arrivalNoticeID, a.id)
    }

    func testLateOrReplacedRequestHitKeepsConversationAndOriginalIdentity() throws {
        let store = WorkspaceStore(); let a = weather(); let b = weather(bKey)
        store.receive(a, quietly: true); store.receive(b, quietly: true)
        store.select(b.id); store.returnToConversation()
        // Neither the store nor a standalone coordinator guesses current
        // request ownership merely because the conversation is on stage.
        XCTAssertEqual(query(store, a), .hit(source: a.payload.weatherSource!, ts: 1_000,
                                           freshUntil: 1_900, revision: store.consoleRevision))
        let client = JarvisClient(); client.setConsoleIdentity(sessionID: UUID(), generation: UUID())
        let reply = try XCTUnwrap(coordinator(store, client: client).executeWeatherReuse(
            request(store, a, client: client), now: Date(timeIntervalSince1970: 1_100)))
        XCTAssertEqual(reply.code, "cache_hit")
        XCTAssertEqual(reply.data?["weather_source"], a.payload.weatherSource)
        XCTAssertEqual(reply.data?["ts"], .number(1_000)); XCTAssertEqual(reply.data?["fresh_until"], .number(1_900))
        XCTAssertTrue(store.showsConversation); XCTAssertEqual(store.activeID, b.id)
        XCTAssertTrue(store.unreadIDs.contains(a.id)); XCTAssertNil(store.arrivalNoticeID)
        XCTAssertEqual(store.results.map(\.id), [a.id, b.id])
        XCTAssertEqual(store.results[0].payload, a.payload)
    }

    func testClosedOrWrongKeyTargetRefusesAndNeverMutates() {
        let store = WorkspaceStore(); let a = weather()
        store.receive(a, quietly: true)
        let revision = store.consoleRevision
        XCTAssertEqual(query(store, a, key: bKey), .refused("stale_selection"))
        XCTAssertEqual(query(store, a, ordinary: false), .refused("protected_turn"))
        XCTAssertEqual(store.consoleRevision, revision)
        store.close(a.id)
        let afterClose = store.consoleRevision
        XCTAssertEqual(query(store, a), .refused("result_unavailable"))
        XCTAssertEqual(store.consoleRevision, afterClose)
        XCTAssertTrue(store.results.isEmpty)
    }

    func testRequestedUnitsDaysAndRadarCapabilitiesAreRequired() {
        let store = WorkspaceStore(); let a = weather(original: source(days: 3, radar: false))
        store.receive(a, quietly: true)
        let revision = store.consoleRevision
        XCTAssertEqual(query(store, a, days: 4), .miss("cache_incomplete"))
        XCTAssertEqual(query(store, a, days: 3, units: "metric"), .miss("cache_incomplete"))
        XCTAssertEqual(query(store, a, tool: "get_weather_radar", days: 3), .miss("cache_incomplete"))
        XCTAssertEqual(store.consoleRevision, revision)
        if case .hit = query(store, a, tool: "local_weather", days: 3) {} else { XCTFail("Complete weather should hit") }
    }

    func testRadarOnlySourceCanAnswerRadarButNotWeather() {
        let store = WorkspaceStore()
        let a = weather(original: ["radar": ["tiles": ["https://example.test/radar.png"]]])
        store.receive(a, quietly: true)
        XCTAssertEqual(query(store, a), .miss("cache_incomplete"))
        if case .hit = query(store, a, tool: "get_weather_radar", units: "metric") {} else { XCTFail("Radar should hit") }
    }

    func testFailedWeatherAndRadarSourcesCannotMutateArrivalOrReturnData() {
        let failures: [[String: Any]] = [["ok": false], ["error": "provider_failure"]]
        for field in ["weather", "radar"] {
            for failure in failures {
                var original = source()
                var part = original[field] as! [String: Any]
                part.merge(failure) { _, replacement in replacement }; original[field] = part
                let store = WorkspaceStore(); let a = weather(original: original); let b = weather(bKey)
                store.receive(a, quietly: true); store.receive(b, quietly: true); store.select(b.id)
                store.dismissArrivalNotice()
                let revision = store.consoleRevision
                let tool = field == "weather" ? "get_weather" : "get_weather_radar"
                XCTAssertEqual(query(store, a, tool: tool), .miss("cache_incomplete"))
                let client = JarvisClient(); client.setConsoleIdentity(sessionID: UUID(), generation: UUID())
                let reply = coordinator(store, client: client).executeWeatherReuse(
                    request(store, a, client: client, overrides: ["tool": .string(tool)]),
                    now: Date(timeIntervalSince1970: 1_100))
                XCTAssertEqual(reply?.code, "cache_incomplete"); XCTAssertNil(reply?.data)
                XCTAssertEqual(store.activeID, b.id); XCTAssertNil(store.arrivalNoticeID)
                XCTAssertEqual(store.consoleRevision, revision)
                XCTAssertEqual(store.results[0].payload, a.payload)
            }
        }
    }

    func testLegacyPolicyCannotReuseSourceButCanBeSafelyRefreshed() {
        let store = WorkspaceStore(); let legacy = weather(policy: nil)
        store.receive(legacy, quietly: true)
        XCTAssertEqual(query(store, legacy), .miss("cache_missing"))
        let refreshed = weather(ts: 1_050)
        XCTAssertEqual(store.receive(refreshed, quietly: true), legacy.id)
        XCTAssertEqual(store.results.count, 1)
        if case .hit = query(store, legacy) {} else { XCTFail("Fresh explicitly public source should hit") }
        let downgrade = weather(ts: 1_060, policy: nil)
        XCTAssertNil(store.reuseExistingIdentity(for: downgrade.payload))
        XCTAssertEqual(store.receive(downgrade, quietly: true), downgrade.id)
        XCTAssertEqual(store.results.count, 2)
        XCTAssertEqual(store.results[0].payload, refreshed.payload, "Legacy provenance cannot replace an approved identity")
    }

    func testPrivateCollisionCannotOverwriteOrSupplyPublicCache() {
        let store = WorkspaceStore(); let secret = weather(policy: "local_only", title: "PRIVATE")
        store.receive(secret, quietly: true)
        let publicResult = weather()
        XCTAssertNil(store.reuseExistingIdentity(for: publicResult.payload))
        XCTAssertEqual(store.receive(publicResult, quietly: true), publicResult.id)
        XCTAssertEqual(store.results.count, 2)
        XCTAssertEqual(store.results[0].payload, secret.payload)
        XCTAssertEqual(query(store, secret), .refused("protected_result"))
        let laterSecret = weather(ts: 1_050, policy: "unknown_policy")
        XCTAssertNil(store.reuseExistingIdentity(for: laterSecret.payload))
        store.receive(laterSecret, quietly: true)
        XCTAssertEqual(store.results.count, 3)
        XCTAssertEqual(store.results[1].payload, publicResult.payload)
    }

    func testMalformedOversizedCacheFallsBackToBodyAndSameKeyUpsert() {
        let store = WorkspaceStore(); let original = weather()
        store.receive(original, quietly: true)
        let oversized = weather(extra: ["weather_source": ["weather": ["padding": String(repeating: "é", count: 9_000)]]])
        XCTAssertNil(oversized.payload.weatherSource); XCTAssertEqual(oversized.payload.body, "Legacy weather body")
        XCTAssertEqual(store.receive(oversized, quietly: true), original.id)
        XCTAssertEqual(query(store, original), .miss("cache_missing"))
        let malformed = weather(expiry: 1_901)
        XCTAssertNil(malformed.payload.freshUntil)
        XCTAssertEqual(store.receive(malformed, quietly: true), original.id)
        XCTAssertEqual(query(store, original), .miss("cache_missing"))
        XCTAssertEqual(store.results.count, 1)
    }

    func testFetchZeroAndExpiryAreUnchangedAcrossHitsAndBoundaryExpires() {
        let store = WorkspaceStore(); let a = weather(ts: 0)
        store.receive(a, quietly: true)
        XCTAssertEqual(query(store, a, now: 1), .hit(source: a.payload.weatherSource!, ts: 0,
                                                  freshUntil: 900, revision: store.consoleRevision))
        XCTAssertEqual(query(store, a, now: 899), .hit(source: a.payload.weatherSource!, ts: 0,
                                                    freshUntil: 900, revision: store.consoleRevision))
        XCTAssertEqual(query(store, a, now: 900), .miss("cache_expired"))
        XCTAssertEqual(store.results[0].payload.ts, 0); XCTAssertEqual(store.results[0].payload.freshUntil, 900)
    }

    func testFutureFetchRefusesAndInvalidExpiryNeverSuppliesSource() {
        let store = WorkspaceStore(); let a = weather(ts: 1_101)
        store.receive(a, quietly: true)
        XCTAssertEqual(query(store, a), .refused("invalid_request"))
        let backwards = weather(expiry: 999)
        XCTAssertNil(backwards.payload.weatherSource)
        store.receive(backwards, quietly: true)
        XCTAssertEqual(query(store, a), .miss("cache_missing"))
    }

    func testInventoryIncludesOnlyPublicSubjectAndFreshnessMetadata() throws {
        let store = WorkspaceStore(); let a = weather()
        store.receive(a, quietly: true); store.receive(weather(bKey, policy: "local_only"), quietly: true)
        let rows = try XCTUnwrap(store.consoleInventoryJSON["results"]?.arrayValue)
        XCTAssertEqual(rows.count, 1); XCTAssertEqual(rows[0]["subject_key"], .string(aKey))
        XCTAssertEqual(rows[0]["fresh_until"], .number(1_900))
        XCTAssertNil(rows[0]["weather_source"]); XCTAssertNil(rows[0]["subject_aliases"])
        let text = String(decoding: try JSONEncoder().encode(store.consoleInventoryJSON), as: UTF8.self)
        XCTAssertFalse(text.contains("temperature_f")); XCTAssertFalse(text.contains("Legacy weather body"))
        XCTAssertFalse(text.contains(bKey)); XCTAssertFalse(text.contains("subject_aliases"))
    }

    private func coordinator(_ store: WorkspaceStore, client: JarvisClient? = nil) -> ConsoleActionCoordinator {
        let drawer = DrawerState()
        return ConsoleActionCoordinator(workspace: store, display: DisplayWindowStore(),
                                        placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
                                        client: client, screens: { [] })
    }

    private func request(_ store: WorkspaceStore, _ item: WorkspaceResult, client: JarvisClient,
                         action: ConsoleAction = .weatherReuse, overrides: [String: JSONValue] = [:],
                         revision: Int? = nil, session: UUID? = nil, generation: UUID? = nil) -> ConsoleRequest {
        var args: [String: JSONValue] = ["subject_key": .string(aKey), "tool": .string("get_weather"),
                                      "days": .number(7), "units": .string("imperial"), "ordinary_turn": .bool(true)]
        args.merge(overrides) { _, replacement in replacement }
        return ConsoleRequest(sessionID: session ?? client.consoleSessionID!, generation: generation ?? client.consoleGeneration!,
                              requestID: UUID(), revision: revision ?? store.consoleRevision,
                              action: action, target: item.id.uuidString, args: action == .weatherReuse ? args : [:])
    }

    func testCoordinatorRequiresSessionAttestationRevisionAndClosedTypedArgs() throws {
        let store = WorkspaceStore(); let a = weather(); store.receive(a, quietly: true)
        let client = JarvisClient(); client.setConsoleIdentity(sessionID: UUID(), generation: UUID())
        let coordinator = coordinator(store, client: client)
        let now = Date(timeIntervalSince1970: 1_100)
        let ineligible: [[String: JSONValue]] = [["ordinary_turn": .bool(false)], ["ordinary_turn": .string("true")]]
        for overrides in ineligible {
            XCTAssertEqual(coordinator.executeWeatherReuse(request(store, a, client: client, overrides: overrides), now: now)?.code, "protected_turn")
        }
        let invalid: [[String: JSONValue]] = [["days": .number(1.5)], ["days": .bool(true)], ["unknown": .bool(true)]]
        for overrides in invalid {
            XCTAssertEqual(coordinator.executeWeatherReuse(request(store, a, client: client, overrides: overrides), now: now)?.code, "invalid_request")
        }
        XCTAssertEqual(coordinator.executeWeatherReuse(request(store, a, client: client, session: UUID()), now: now)?.code, "stale_selection")
        XCTAssertEqual(coordinator.executeWeatherReuse(request(store, a, client: client, generation: UUID()), now: now)?.code, "stale_selection")
        XCTAssertEqual(coordinator.executeWeatherReuse(request(store, a, client: client, revision: store.consoleRevision - 1), now: now)?.code, "stale_selection")
        XCTAssertEqual(self.coordinator(store).executeWeatherReuse(request(store, a, client: client), now: now)?.code, "not_ready")
        let result = try XCTUnwrap(coordinator.executeWeatherReuse(request(store, a, client: client), now: now,
                                                                 answersCurrentRequest: true))
        XCTAssertEqual(result.status, "ok"); XCTAssertEqual(result.code, "cache_hit")
        XCTAssertEqual(result.data?["revision"], .number(Double(store.consoleRevision)))
        XCTAssertEqual(result.data?["weather_source"], a.payload.weatherSource)
        XCTAssertFalse(store.showsConversation)
    }

    func testMissingAttestationAndPointerReuseCannotMutateWhileExplicitReopenCan() {
        let store = WorkspaceStore(); let a = weather(); store.receive(a, quietly: true); store.openSkills()
        let client = JarvisClient(); client.setConsoleIdentity(sessionID: UUID(), generation: UUID())
        let coordinator = coordinator(store, client: client)
        let request = ConsoleRequest(sessionID: client.consoleSessionID!, generation: client.consoleGeneration!,
                                     requestID: UUID(), revision: store.consoleRevision, action: .weatherReuse,
                                     target: a.id.uuidString, args: [:])
        let revision = store.consoleRevision
        XCTAssertEqual(coordinator.executeWeatherReuse(request)?.code, "protected_turn")
        XCTAssertEqual(coordinator.executePointer(.weatherReuse, target: a.id.uuidString), .unsupported)
        XCTAssertEqual(store.consoleRevision, revision); XCTAssertTrue(store.showsSkills)
        XCTAssertEqual(coordinator.executePointer(.resultReopen, target: a.id.uuidString), .applied)
        XCTAssertEqual(store.activeID, a.id); XCTAssertFalse(store.showsSkills)
        XCTAssertEqual(store.results[0].payload.ts, 1_000, "Explicit reopen performs no fetch")
    }
}
