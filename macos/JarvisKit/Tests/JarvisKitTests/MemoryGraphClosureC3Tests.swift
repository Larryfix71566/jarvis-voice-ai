import XCTest
@testable import JarvisKit

/// Closure plan C3.3 / C3.4 (gaps G13, G14).
final class MemoryGraphClosureC3Tests: XCTestCase {
    private func makeAPI(token: String = "synthetic") -> AdminAPI {
        let configuration = JarvisHTTP.transientConfiguration()
        configuration.protocolClasses = [StubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        addTeardownBlock { session.invalidateAndCancel() }
        return AdminAPI(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: token),
            graphSession: session)
    }

    /// The exact envelope `jarvis/graphs/model.py::Graph.to_json` produces for
    /// the memory graph, with the legend `render.legend_for("memory")` emits
    /// (node type → hex, edge type → style). Synthetic content only.
    private func serverShapedResponse(legend: Any? = nil) throws -> Data {
        var object: [String: Any] = [
            "ok": true, "graph": "memory", "focus": NSNull(), "depth": 2,
            "edge_types": ["child_of", "became", "stated_in", "restated"],
            "node_count": 4, "edge_count": 4, "truncated": false, "truncated_reason": "",
            "nodes": [
                ["id": "fact:project.alpha", "type": "fact", "label": "project.alpha", "attrs": ["archived": false]],
                ["id": "prefix:project", "type": "prefix", "label": "project", "attrs": [:]],
                ["id": "turn:7", "type": "turn", "label": "7", "attrs": ["role": "user"]],
                ["id": "archive:merged-missing", "type": "archive", "label": "merged-missing", "attrs": [:]],
            ],
            "edges": [
                ["from": "fact:project.alpha", "to": "prefix:project", "type": "child_of", "attrs": [:]],
                ["from": "fact:project.alpha", "to": "turn:7", "type": "stated_in", "attrs": [:]],
                ["from": "fact:project.alpha", "to": "turn:7", "type": "restated", "attrs": ["outcome": "kept"]],
                ["from": "fact:project.alpha", "to": "archive:merged-missing", "type": "became", "attrs": ["archived_at": "2026-09-01T00:00:00Z"]],
            ],
        ]
        if let legend { object["legend"] = legend }
        return try JSONSerialization.data(withJSONObject: object)
    }

    func testServerShapedLegendDecodesAndDefinesDirectionalTypes() throws {
        let legend: [String: Any] = [
            "node_types": ["fact": "#5ec8ff", "prefix": "#a78bfa", "turn": "#9aa5b1", "archive": "#6b7280", "workflow": "#f59e0b"],
            "edge_types": ["child_of": "solid", "became": "dashed", "stated_in": "dashed", "restated": "dotted"],
        ]
        let response = try JSONDecoder().decode(MemoryGraphResponse.self, from: serverShapedResponse(legend: legend))
        XCTAssertEqual(response.legend.edgeTypes["restated"], "dotted")
        XCTAssertEqual(response.legend.directionalEdgeTypes, ["child_of", "became", "stated_in", "restated"])
        XCTAssertEqual(response.edges.count, 4)
    }

    func testAbsentOrPartialLegendStillDecodes() throws {
        let absent = try JSONDecoder().decode(MemoryGraphResponse.self, from: serverShapedResponse(legend: nil))
        XCTAssertTrue(absent.legend.nodeTypes.isEmpty)
        XCTAssertEqual(absent.legend.directionalEdgeTypes, MemoryGraphLegend.memoryDirectionalEdgeTypes,
                       "without a legend the documented memory-graph set is the fallback")
        let partial = try JSONDecoder().decode(MemoryGraphResponse.self, from: serverShapedResponse(legend: ["edge_types": ["became": "dashed"]]))
        XCTAssertEqual(partial.legend.directionalEdgeTypes, ["became"], "the server's declared vocabulary wins when present")
        XCTAssertTrue(partial.legend.nodeTypes.isEmpty)
    }

    func testDepthIsOmittedUnlessTheUserChoseOne() async throws {
        StubURLProtocol.reset(); URLProtocol.registerClass(StubURLProtocol.self)
        defer { URLProtocol.unregisterClass(StubURLProtocol.self); StubURLProtocol.reset() }
        StubURLProtocol.statusCode = 200; StubURLProtocol.responseBody = try serverShapedResponse(legend: ["node_types": [:], "edge_types": [:]])
        let api = makeAPI()
        _ = try await api.memoryGraph(MemoryGraphQuery())
        var items = URLComponents(url: try XCTUnwrap(StubURLProtocol.lastRequest?.url), resolvingAgainstBaseURL: false)?.queryItems ?? []
        XCTAssertTrue(items.filter { $0.name == "depth" }.isEmpty, "server default depth must apply when unspecified")
        var chosen = MemoryGraphQuery()
        chosen.setDepth(3)
        _ = try await api.memoryGraph(chosen)
        items = URLComponents(url: try XCTUnwrap(StubURLProtocol.lastRequest?.url), resolvingAgainstBaseURL: false)?.queryItems ?? []
        XCTAssertEqual(items.filter { $0.name == "depth" }.map(\.value), ["3"])
        XCTAssertEqual(MemoryGraphQuery(depth: 99).depth, 4, "explicit depth still clamps to the server maximum")
        XCTAssertTrue(MemoryGraphQuery(depth: 99).depthSpecified)
    }

    func testPersistedQueriesWithoutTheNewFieldStillDecode() throws {
        let legacy = Data(#"{"focus":"fact:x","depth":3,"edgeTypes":["child_of"],"since":null}"#.utf8)
        let query = try JSONDecoder().decode(MemoryGraphQuery.self, from: legacy)
        XCTAssertEqual(query.depth, 3)
        XCTAssertTrue(query.depthSpecified, "a record that carried a depth keeps sending it")
        let fresh = try JSONDecoder().decode(MemoryGraphQuery.self, from: Data(#"{"focus":""}"#.utf8))
        XCTAssertFalse(fresh.depthSpecified)
        let roundTrip = try JSONDecoder().decode(MemoryGraphQuery.self, from: JSONEncoder().encode(MemoryGraphQuery()))
        XCTAssertFalse(roundTrip.depthSpecified)
    }

    func testGraphImageDataOnlyFetchesAdminOriginGraphImagesThroughTheTransientSender() async throws {
        StubURLProtocol.reset(); URLProtocol.registerClass(StubURLProtocol.self)
        defer { URLProtocol.unregisterClass(StubURLProtocol.self); StubURLProtocol.reset() }
        let api = makeAPI(token: "synthetic-image-token")
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data([137, 80, 78, 71, 13, 10, 26, 10, 0, 0])
        let data = try await api.graphImageData(at: URL(string: "http://127.0.0.1:7861/api/graph/memory/image.png?focus=fact%3Ax&w=800&h=600")!)
        XCTAssertEqual(data.count, 10)
        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-image-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "image/png")
        XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
        XCTAssertEqual(request.url?.query, "focus=fact%3Ax&w=800&h=600", "sizing query items pass through untouched")
        StubURLProtocol.requestCount = 0
        // A result-supplied foreign host must never be fetched, even with a graph path.
        do {
            _ = try await api.graphImageData(at: URL(string: "http://evil.example:7861/api/graph/memory/image.png")!)
            XCTFail("foreign origin accepted")
        } catch let error as AdminAPI.GraphImageOriginError { XCTAssertEqual(error, .foreignOrigin) }
        do {
            _ = try await api.graphImageData(at: URL(string: "http://127.0.0.1:7861/api/memory")!)
            XCTFail("non-image path accepted")
        } catch let error as AdminAPI.GraphImageOriginError { XCTAssertEqual(error, .notAGraphImage) }
        XCTAssertEqual(StubURLProtocol.requestCount, 0, "rejected URLs make no request")
    }
}
