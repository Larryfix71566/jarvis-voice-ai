import XCTest
@testable import JarvisKit

/// Against a stub URLProtocol recording the outgoing request — asserts
/// URL, method, header, and (for the two POSTs) request-body key names,
/// not response shape (responses are JSONValue, N14).
final class AdminAPITests: XCTestCase {
    override func setUp() {
        super.setUp()
        StubURLProtocol.reset()
        URLProtocol.registerClass(StubURLProtocol.self)
    }

    override func tearDown() {
        URLProtocol.unregisterClass(StubURLProtocol.self)
        super.tearDown()
    }

    private func makeAPI(token: String? = "jvt") -> AdminAPI {
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: token
        )
        return AdminAPI(config: config)
    }

    /// The exact path + HTTP verb in N14's table; seventeen requests
    /// observed (this is the test that would have caught the 14-vs-17
    /// miscount, review F10).
    func testAdminRoutesBuildExpectedURLs() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data("{}".utf8)

        var seen: [(String, String)] = []
        func record() {
            guard let req = StubURLProtocol.lastRequest else { return }
            seen.append((req.httpMethod ?? "", req.url?.path ?? ""))
        }

        _ = try await api.gitStatus(); record()
        _ = try await api.selfeditModels(); record()
        _ = try await api.selfeditStatus(); record()
        _ = try await api.selfeditRun(goal: "x", profile: nil, plan: nil, stagingId: nil); record()
        _ = try await api.memory(); record()
        _ = try await api.deleteFact(key: "k"); record()
        _ = try await api.memoryReviews(); record()
        _ = try await api.resolveReview(id: 7, action: "approve", rewriteContent: nil); record()
        _ = try await api.knowledge(); record()
        _ = try await api.runs(); record()
        _ = try await api.run(id: "run-1"); record()
        _ = try await api.ambient(); record()
        _ = try await api.councilJob(); record()
        _ = try await api.councilRounds(); record()
        _ = try await api.councilRound(id: "c1"); record()
        _ = try await api.planJob(); record()
        _ = try await api.health(); record()

        XCTAssertEqual(seen.count, 17)
        XCTAssertEqual(StubURLProtocol.requestCount, 17)

        let expected: [(String, String)] = [
            ("GET", "/api/git/status"),
            ("GET", "/api/selfedit/models"),
            ("GET", "/api/selfedit/status"),
            ("POST", "/api/selfedit/run"),
            ("GET", "/api/memory"),
            ("DELETE", "/api/memory/fact/k"),
            ("GET", "/api/memory/reviews"),
            ("POST", "/api/memory/reviews/7/resolve"),
            ("GET", "/api/knowledge"),
            ("GET", "/api/runs"),
            ("GET", "/api/runs/run-1"),
            ("GET", "/api/ambient"),
            ("GET", "/api/council/job"),
            ("GET", "/api/council/rounds"),
            ("GET", "/api/council/round/c1"),
            ("GET", "/api/plan/job"),
            ("GET", "/api/health"),
        ]
        for (index, pair) in expected.enumerated() {
            XCTAssertEqual(seen[index].0, pair.0, "method mismatch at index \(index)")
            XCTAssertEqual(seen[index].1, pair.1, "path mismatch at index \(index)")
        }
    }

    func testSelfeditRunEncodesGoalInKeys() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data("{}".utf8)
        _ = try await api.selfeditRun(goal: "x", profile: nil, plan: nil, stagingId: "s1", runID: "action-123")
        let body = try XCTUnwrap(StubURLProtocol.lastRequest?.httpBodyOrStreamData())
        let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(Set(obj.keys), ["goal", "staging_id", "run_id"])   // nils omitted, no camelCase (GoalIn)
        XCTAssertEqual(obj["goal"] as? String, "x")
        XCTAssertEqual(obj["staging_id"] as? String, "s1")
        XCTAssertEqual(obj["run_id"] as? String, "action-123")
    }

    func testResolveReviewUsesIntIdAndBodyKeys() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data("{}".utf8)
        _ = try await api.resolveReview(id: 7, action: "approve", rewriteContent: nil)
        XCTAssertEqual(StubURLProtocol.lastRequest?.url?.path, "/api/memory/reviews/7/resolve")
        let body = try XCTUnwrap(StubURLProtocol.lastRequest?.httpBodyOrStreamData())
        let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(obj["action"] as? String, "approve")   // MemoryReviewResolveIn
    }

    func testBearerHeaderOnAdminRoute() async throws {
        let api = makeAPI(token: "jvt")
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data("{}".utf8)
        _ = try await api.runs()
        XCTAssertEqual(StubURLProtocol.lastRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer jvt")
        _ = try await api.memory()
        XCTAssertEqual(StubURLProtocol.lastRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer jvt")
    }

    func testSkillsActivityRoutesAreBoundedAndTyped() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data(
            "{\"schema_version\":1,\"runs\":[],\"next_cursor\":null}".utf8
        )
        let runs = try await api.skillRuns(id: "demo-skill", limit: 10)
        XCTAssertEqual(runs.schemaVersion, 1)
        XCTAssertEqual(StubURLProtocol.lastRequest?.url?.path,
                       "/api/skills/demo-skill/runs")
        XCTAssertEqual(URLComponents(url: try XCTUnwrap(StubURLProtocol.lastRequest?.url),
                                      resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "limit" })?.value,
                       "10")

        StubURLProtocol.responseBody = Data(
            "{\"schema_version\":1,\"trace_status\":\"unavailable\",\"events\":[],\"after_seq\":3,\"next_after_seq\":3,\"has_more\":false,\"truncated\":false}".utf8
        )
        let activity = try await api.skillActivity(runID: "run_1", afterSeq: 3)
        XCTAssertEqual(activity.nextAfterSeq, 3)
        XCTAssertEqual(StubURLProtocol.lastRequest?.url?.path,
                       "/api/skills/runs/run_1/events")
        XCTAssertEqual(URLComponents(url: try XCTUnwrap(StubURLProtocol.lastRequest?.url),
                                      resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "after_seq" })?.value,
                       "3")
    }

    func testSkillsActivityRejectsInvalidIdentifiersAndBounds() async throws {
        let api = makeAPI()
        do {
            _ = try await api.skillRuns(id: "../bad")
            XCTFail("invalid skill id should be rejected")
        } catch { }
        do {
            _ = try await api.skillActivity(runID: "run/1")
            XCTFail("invalid run id should be rejected")
        } catch { }
        do {
            _ = try await api.skillActivity(runID: "run-1", afterSeq: -1)
            XCTFail("negative cursor should be rejected")
        } catch { }
        XCTAssertEqual(StubURLProtocol.requestCount, 0)
    }

    func testSkillsActivityRejectsStaleOrMalformedPageCursorsAndOrdering() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200

        // The server must echo the requested cursor, including for an
        // unavailable legacy trace; a stale page cannot reset pagination.
        StubURLProtocol.responseBody = Data(
            #"{"schema_version":1,"trace_status":"unavailable","events":[],"after_seq":0,"next_after_seq":0,"has_more":false,"truncated":false}"#.utf8
        )
        do {
            _ = try await api.skillActivity(runID: "run_1", afterSeq: 9)
            XCTFail("a page from a different cursor must not be accepted")
        } catch let error as JarvisError {
            guard case .decoding = error else { return XCTFail("unexpected error: \(error)") }
        }

        // A page cannot mix run IDs or sequence ordering even when its
        // top-level cursor is otherwise valid.
        StubURLProtocol.responseBody = Data(
            #"{"schema_version":1,"trace_status":"recorded","events":[{"event_id":"e1","run_id":"other_run","request_id":"req","seq":10,"schema_version":1,"occurred_at":"2026-09-28T12:00:00Z","skill_id":"demo","skill_revision":null,"step_id":null,"attempt_id":null,"type":"run_started","status":"started","evidence_refs":[]}],"after_seq":9,"next_after_seq":10,"has_more":false,"truncated":false}"#.utf8
        )
        do {
            _ = try await api.skillActivity(runID: "run_1", afterSeq: 9)
            XCTFail("an event from another run must not be accepted")
        } catch let error as JarvisError {
            guard case .decoding = error else { return XCTFail("unexpected error: \(error)") }
        }

        StubURLProtocol.responseBody = Data(
            #"{"schema_version":1,"trace_status":"recorded","events":[{"event_id":"e1","run_id":"run_1","request_id":"req","seq":11,"schema_version":1,"occurred_at":"2026-09-28T12:00:00Z","skill_id":"demo","skill_revision":null,"step_id":null,"attempt_id":null,"type":"run_started","status":"started","evidence_refs":[]},{"event_id":"e2","run_id":"run_1","request_id":"req","seq":10,"schema_version":1,"occurred_at":"2026-09-28T12:00:01Z","skill_id":"demo","skill_revision":null,"step_id":null,"attempt_id":null,"type":"run_finished","status":"completed","evidence_refs":[]}],"after_seq":9,"next_after_seq":10,"has_more":false,"truncated":false}"#.utf8
        )
        do {
            _ = try await api.skillActivity(runID: "run_1", afterSeq: 9)
            XCTFail("out-of-order events must not be accepted")
        } catch let error as JarvisError {
            guard case .decoding = error else { return XCTFail("unexpected error: \(error)") }
        }
    }

    func testSkillsActivityRejectsImpossibleLifecycleClaims() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200

        let invalidEvents = [
            // A successful step must be backed by a host check receipt.
            #"{"event_id":"e1","run_id":"run_1","request_id":"req","seq":1,"schema_version":1,"occurred_at":"2026-09-28T12:00:00Z","skill_id":"demo","skill_revision":null,"step_id":"step-one","attempt_id":"tool-1","type":"skill_step_finished","status":"passed","evidence_refs":[{"kind":"tool_call_id","id":"tool-1"}]}"#,
            // A finished event cannot claim the started/running status.
            #"{"event_id":"e1","run_id":"run_1","request_id":"req","seq":1,"schema_version":1,"occurred_at":"2026-09-28T12:00:00Z","skill_id":"demo","skill_revision":null,"step_id":"step-one","attempt_id":"tool-1","type":"skill_step_finished","status":"running","evidence_refs":[]}"#,
            // Protected rows are lifecycle-only and must not expose skill IDs.
            #"{"event_id":"e1","run_id":"run_1","request_id":"req","seq":1,"schema_version":1,"occurred_at":"2026-09-28T12:00:00Z","skill_id":"demo","skill_revision":null,"step_id":null,"attempt_id":null,"type":"protected_activity","status":"unknown","evidence_refs":[]}"#,
        ]

        for event in invalidEvents {
            StubURLProtocol.responseBody = Data(
                "{\"schema_version\":1,\"trace_status\":\"recorded\",\"events\":[\(event)],\"after_seq\":0,\"next_after_seq\":1,\"has_more\":false,\"truncated\":false}".utf8
            )
            do {
                _ = try await api.skillActivity(runID: "run_1")
                XCTFail("impossible activity claims must be rejected")
            } catch let error as JarvisError {
                guard case .decoding = error else { return XCTFail("unexpected error: \(error)") }
            }
        }
    }

    func testSkillExamplePreviewUsesDeclaredReadRouteAndDecodesSyntheticResult() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data(
            #"{"schema_version":1,"skill_id":"demo-skill","example_id":"weather-positive","synthetic":true,"request":"What's the weather in Paris?","expect_selected":true}"#.utf8
        )

        let result = try await api.skillExamplePreview(id: "demo-skill", exampleID: "weather-positive")

        XCTAssertEqual(StubURLProtocol.lastRequest?.httpMethod, "GET")
        XCTAssertEqual(StubURLProtocol.lastRequest?.url?.path,
                       "/api/skills/demo-skill/examples/weather-positive")
        XCTAssertEqual(StubURLProtocol.lastRequest?.value(forHTTPHeaderField: "Authorization"),
                       "Bearer jvt")
        XCTAssertEqual(result["skill_id"]?.stringValue, "demo-skill")
        XCTAssertEqual(result["example_id"]?.stringValue, "weather-positive")
        XCTAssertEqual(result["synthetic"]?.boolValue, true)
        XCTAssertEqual(result["expect_selected"]?.boolValue, true)
        XCTAssertEqual(result["request"]?.stringValue, "What's the weather in Paris?")
    }

    func testSkillExamplePreviewRejectsInvalidIdentifiersBeforeNetworkRequest() async throws {
        let api = makeAPI()
        for (skillID, exampleID) in [("../skill", "valid"), ("valid", "../example"),
                                     ("valid", "Uppercase"), ("", "valid")] {
            do {
                _ = try await api.skillExamplePreview(id: skillID, exampleID: exampleID)
                XCTFail("invalid example target should be rejected")
            } catch { }
        }
        XCTAssertEqual(StubURLProtocol.requestCount, 0)
    }

    func testSkillDraftRequestUsesVersionedSnakeCaseBodyAndBearerAuth() async throws {
        let api = makeAPI()
        StubURLProtocol.statusCode = 202
        StubURLProtocol.responseBody = Data("{\"schema_version\":1,\"request_id\":\"abc\",\"state\":\"queued\"}".utf8)
        let request = SkillAuthoringRequest(
            operation: "draft", requestID: "abc",
            expectedCatalogRevision: String(repeating: "a", count: 64),
            skillID: "demo-skill", botSessionID: "00000000-0000-0000-0000-000000000001",
            taskBrief: "A transient draft brief"
        )
        _ = try await api.createSkillRequest(request)
        let last = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(last.httpMethod, "POST")
        XCTAssertEqual(last.url?.path, "/api/skills/requests")
        XCTAssertEqual(last.value(forHTTPHeaderField: "Authorization"), "Bearer jvt")
        let body = try XCTUnwrap(last.httpBodyOrStreamData())
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(object["operation"] as? String, "draft")
        XCTAssertEqual(object["request_id"] as? String, "abc")
        XCTAssertEqual(object["skill_id"] as? String, "demo-skill")
        XCTAssertEqual(object["bot_session_id"] as? String, "00000000-0000-0000-0000-000000000001")
        XCTAssertEqual(object["task_brief"] as? String, "A transient draft brief")
        XCTAssertNil(object["taskBrief"])
    }
}

private extension URLRequest {
    /// URLProtocol delivers the body via httpBodyStream when the request
    /// was built with `.httpBody` and then passed through URLSession —
    /// httpBody itself is often nil by the time StubURLProtocol observes
    /// it, so read whichever is present.
    func httpBodyOrStreamData() -> Data? {
        if let body = httpBody { return body }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: bufferSize)
            if read > 0 { data.append(buffer, count: read) } else { break }
        }
        return data
    }
}
