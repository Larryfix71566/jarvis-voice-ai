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
        _ = try await api.selfeditRun(goal: "x", profile: nil, plan: nil, stagingId: "s1")
        let body = try XCTUnwrap(StubURLProtocol.lastRequest?.httpBodyOrStreamData())
        let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(Set(obj.keys), ["goal", "staging_id"])   // nils omitted, no camelCase (GoalIn)
        XCTAssertEqual(obj["goal"] as? String, "x")
        XCTAssertEqual(obj["staging_id"] as? String, "s1")
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
