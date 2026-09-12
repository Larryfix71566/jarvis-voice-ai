import XCTest
@testable import JarvisKit

final class MemoryGraphAPITests: XCTestCase {
    private func makeAPI(token: String) -> AdminAPI {
        let configuration = JarvisHTTP.transientConfiguration()
        configuration.protocolClasses = [StubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        addTeardownBlock { session.invalidateAndCancel() }
        return AdminAPI(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: token),
            graphSession: session)
    }

    private func data(nodeCount: Int = 3, edgeCount: Int = 2, focus: String? = nil) throws -> Data {
        let nodes: [[String: Any]] = (0..<nodeCount).map {
            ["id": "fact:\($0)", "type": $0 == 0 ? "future_type" : "fact", "label": "Node \($0)", "attrs": ["provenance": NSNull()]]
        }
        let edges: [[String: Any]] = (0..<edgeCount).map {
            ["from": "fact:\($0 % nodeCount)", "to": "fact:\(($0 + 1) % nodeCount)", "type": "child_of", "attrs": [:]]
        }
        return try JSONSerialization.data(withJSONObject: ["ok": true, "graph": "memory", "focus": focus as Any? ?? NSNull(), "depth": 2,
            "edge_types": ["child_of"], "node_count": nodeCount, "edge_count": edgeCount, "truncated": false, "truncated_reason": "",
            "nodes": nodes, "edges": edges, "legend": ["node_types": ["fact": "#5ec8ff"], "edge_types": ["child_of": "solid"]]])
    }

    func testUnknownTypesAndAbsentProvenanceRemainHonest() throws {
        let response = try JSONDecoder().decode(MemoryGraphResponse.self, from: data())
        XCTAssertEqual(response.nodes.first?.type, "future_type")
        XCTAssertEqual(response.nodes.first?.attrs["provenance"], .null)
        XCTAssertNil(response.legend.nodeTypes["future_type"])
    }

    func testNodeLimitKeepsRequestedFocusAndDisclosesPartialView() throws {
        let response = try JSONDecoder().decode(MemoryGraphResponse.self, from: data(nodeCount: 501, edgeCount: 500, focus: "fact:500"))
        XCTAssertEqual(response.nodes.count, 500)
        XCTAssertTrue(response.nodes.contains { $0.id == "fact:500" })
        XCTAssertTrue(response.truncated)
        XCTAssertTrue(response.truncatedReason.contains("Display limit"))
        let ids = Set(response.nodes.map(\.id))
        XCTAssertTrue(response.edges.allSatisfy { ids.contains($0.from) && ids.contains($0.to) })
    }

    func testEdgeLimitIsDisclosed() throws {
        let response = try JSONDecoder().decode(MemoryGraphResponse.self, from: data(edgeCount: 2001))
        XCTAssertEqual(response.edges.count, 2000)
        XCTAssertEqual(response.edgeCount, 2001)
        XCTAssertTrue(response.truncated)
    }

    func testDuplicateNodesAndDanglingEdgesAreRejected() throws {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data()) as? [String: Any])
        var nodes = try XCTUnwrap(object["nodes"] as? [[String: Any]])
        nodes[1]["id"] = "fact:0"; object["nodes"] = nodes
        XCTAssertThrowsError(try JSONDecoder().decode(MemoryGraphResponse.self, from: JSONSerialization.data(withJSONObject: object)))
        object = try XCTUnwrap(JSONSerialization.jsonObject(with: data()) as? [String: Any])
        var edges = try XCTUnwrap(object["edges"] as? [[String: Any]])
        edges[0]["to"] = "missing"; object["edges"] = edges
        XCTAssertThrowsError(try JSONDecoder().decode(MemoryGraphResponse.self, from: JSONSerialization.data(withJSONObject: object)))
    }

    func testDisabledGraphPreservesServerExplanation() {
        XCTAssertThrowsError(try JSONDecoder().decode(MemoryGraphResponse.self, from: Data(#"{"ok":false,"error":"graphs are disabled"}"#.utf8))) {
            XCTAssertEqual($0 as? MemoryGraphError, .unavailable("graphs are disabled"))
        }
    }

    func testAuthenticatedReadEncodesFocusAsOneQueryValue() async throws {
        StubURLProtocol.reset(); URLProtocol.registerClass(StubURLProtocol.self)
        defer { URLProtocol.unregisterClass(StubURLProtocol.self); StubURLProtocol.reset() }
        StubURLProtocol.statusCode = 200; StubURLProtocol.responseBody = try data()
        let api = makeAPI(token: "synthetic-graph-token")
        let focus = "fact:a/b?x=1&depth=99 #notes"
        _ = try await api.memoryGraph(MemoryGraphQuery(focus: focus, depth: 99, edgeTypes: ["child_of", "became"], since: "2026-01-01"))
        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-graph-token")
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
        XCTAssertEqual(request.url?.path, "/api/graph/memory")
        let items = try XCTUnwrap(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems)
        XCTAssertEqual(items.filter { $0.name == "focus" }.map(\.value), [focus])
        XCTAssertEqual(items.filter { $0.name == "depth" }.map(\.value), ["4"])
        XCTAssertEqual(items.first { $0.name == "edge_types" }?.value, "child_of,became")
    }
    func testGraphReadBypassesAndDoesNotReplaceSharedCachedContent() async throws {
        StubURLProtocol.reset(); URLProtocol.registerClass(StubURLProtocol.self)
        defer { URLProtocol.unregisterClass(StubURLProtocol.self); StubURLProtocol.reset() }
        let api = makeAPI(token: "synthetic-cache-token")
        let query = MemoryGraphQuery(focus: "cache-fixture-" + UUID().uuidString)
        let request = api.memoryGraphRequest(query)
        let stale = Data("cached private response must not be read".utf8)
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                       headerFields: ["Cache-Control": "max-age=3600", "Content-Type": "application/json"])!
        URLCache.shared.storeCachedResponse(CachedURLResponse(response: response, data: stale), for: request)
        defer { URLCache.shared.removeCachedResponse(for: request) }
        XCTAssertEqual(URLCache.shared.cachedResponse(for: request)?.data, stale)
        StubURLProtocol.responseBody = try data()
        let graph = try await api.memoryGraph(query)
        XCTAssertEqual(graph.nodes.count, 3)
        XCTAssertEqual(StubURLProtocol.requestCount, 1)
        XCTAssertEqual(URLCache.shared.cachedResponse(for: request)?.data, stale)
    }

    func testGraphSessionDoesNotUseSharedPersistenceStores() {
        let configuration = JarvisHTTP.transientConfiguration()
        XCTAssertNil(configuration.urlCache)
        XCTAssertNil(configuration.httpCookieStorage)
        XCTAssertNil(configuration.urlCredentialStorage)
        XCTAssertEqual(configuration.requestCachePolicy, .reloadIgnoringLocalCacheData)
    }

    func testImageFallbackUsesAuthenticatedConfiguredOriginAndQuery() async throws {
        StubURLProtocol.reset(); URLProtocol.registerClass(StubURLProtocol.self)
        defer { URLProtocol.unregisterClass(StubURLProtocol.self); StubURLProtocol.reset() }
        let png = Data(base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1cAAAAASUVORK5CYII=")!
        StubURLProtocol.responseBody = png
        StubURLProtocol.responseHeaders = ["Content-Type": "image/png"]
        let api = makeAPI(token: "synthetic-image-token")
        let focus = "fact:notes&depth=99"
        let result = try await api.memoryGraphImage(MemoryGraphQuery(focus: focus, depth: 3))
        XCTAssertEqual(result, png)
        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(request.url?.host, "127.0.0.1")
        XCTAssertEqual(request.url?.port, 7861)
        XCTAssertEqual(request.url?.path, "/api/graph/memory/image.png")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-image-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "image/png")
        XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
        let items = try XCTUnwrap(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems)
        XCTAssertEqual(items.filter { $0.name == "focus" }.map(\.value), [focus])
        XCTAssertEqual(items.filter { $0.name == "depth" }.map(\.value), ["3"])
        StubURLProtocol.statusCode = 401
        do { _ = try await api.memoryGraphImage(); XCTFail("Unauthorized image must fail") }
        catch { XCTAssertEqual(error as? JarvisError, .unauthorized) }
        StubURLProtocol.statusCode = 403
        do { _ = try await api.memoryGraphImage(); XCTFail("Forbidden image must fail") }
        catch { XCTAssertEqual(error as? JarvisError, .forbidden) }
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data("not an image".utf8)
        do { _ = try await api.memoryGraphImage(); XCTFail("Invalid image must fail") }
        catch { XCTAssertNotNil(error as? MemoryGraphError) }
    }

}
