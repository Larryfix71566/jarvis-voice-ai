import XCTest
import JarvisKit
@testable import MortimerHost

enum GraphFixture {
    static func clustered() throws -> MemoryGraphResponse {
        var nodes: [[String: Any]] = [], edges: [[String: Any]] = []
        for group in 0..<5 {
            let prefix = "prefix:project.\(group)", turn = "turn:\(group)"
            nodes.append(["id": prefix, "type": "prefix", "label": "Project \(group)", "attrs": [:]])
            nodes.append(["id": turn, "type": "turn", "label": "Conversation \(group)", "attrs": ["role": "user"]])
            for index in 0..<8 {
                let id = "fact:project.\(group).item.\(index)"
                nodes.append(["id": id, "type": "fact", "label": index == 3 ? "A longer synthetic memory label for project \(group)" : "Memory \(group).\(index)",
                              "attrs": ["provenance": "synthetic acceptance fixture", "content_preview": "No private memory data"]])
                edges.append(["from": id, "to": prefix, "type": "child_of", "attrs": [:]])
                edges.append(["from": id, "to": turn, "type": "stated_in", "attrs": [:]])
            }
        }
        let object: [String: Any] = ["ok": true, "graph": "memory", "focus": NSNull(), "depth": 2,
            "edge_types": ["child_of", "stated_in"], "node_count": nodes.count, "edge_count": edges.count,
            "truncated": false, "truncated_reason": "", "nodes": nodes, "edges": edges,
            "legend": ["node_types": ["fact": "#5ec8ff", "prefix": "#a78bfa", "turn": "#9aa5b1"],
                       "edge_types": ["child_of": "solid", "stated_in": "dashed"]]]
        return try JSONDecoder().decode(MemoryGraphResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    static func make(count: Int = 4, edges edgeCount: Int? = nil, edgeNote: String? = nil) throws -> MemoryGraphResponse {
        let nodes: [[String: Any]] = (0..<count).map {
            ["id": "fact:\($0)", "type": "fact", "label": "Synthetic node \($0)", "attrs": ["content_preview": "fixture content only"]]
        }
        let edgeTotal = edgeCount ?? max(0, count - 1)
        let edges: [[String: Any]] = (0..<edgeTotal).map {
            ["from": "fact:\($0 % count)", "to": "fact:\(($0 + 1) % count)", "type": "child_of", "attrs": edgeNote.map { ["note": $0] } ?? [:]]
        }
        let object: [String: Any] = ["ok": true, "graph": "memory", "focus": NSNull(), "depth": 2, "edge_types": ["child_of"],
            "node_count": count, "edge_count": edgeTotal, "truncated": false, "truncated_reason": "", "nodes": nodes, "edges": edges,
            "legend": ["node_types": ["fact": "#5ec8ff"], "edge_types": ["child_of": "solid"]]]
        return try JSONDecoder().decode(MemoryGraphResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }
}

final class MemoryGraphLayoutTests: XCTestCase {
    func testDeterministicLayoutAndExpansionPreserveExistingPositions() throws {
        let graph = try GraphFixture.make(), expanded = try GraphFixture.make(count: 5)
        let a = try MemoryGraphLayout.positions(nodes: graph.nodes, edges: graph.edges)
        let b = try MemoryGraphLayout.positions(nodes: graph.nodes.reversed(), edges: graph.edges)
        XCTAssertEqual(a, b)
        let next = try MemoryGraphLayout.positions(nodes: expanded.nodes, edges: expanded.edges, preserving: a)
        for (id, point) in a { XCTAssertEqual(next[id], point) }
        XCTAssertNotNil(next["fact:4"])
    }

    func testPathUsesUndirectedLoadedEdgesAndFiltersMatter() throws {
        let graph = try GraphFixture.make()
        let ids = Set(graph.nodes.map(\.id))
        XCTAssertEqual(MemoryGraphLayout.path(from: "fact:3", to: "fact:0", nodes: ids, edges: graph.edges), ["fact:3", "fact:2", "fact:1", "fact:0"])
        XCTAssertNil(MemoryGraphLayout.path(from: "fact:3", to: "fact:0", nodes: ids, edges: Array(graph.edges.dropFirst())))
        XCTAssertNil(MemoryGraphLayout.path(from: "missing", to: "fact:0", nodes: ids, edges: graph.edges))
    }

    func testStressFixturesProduceFiniteBoundedLayout() throws {
        for count in [50, 200, 500] {
            let graph = try GraphFixture.make(count: count, edges: count == 500 ? 2000 : count * 2)
            let start = Date()
            let positions = try MemoryGraphLayout.positions(nodes: graph.nodes, edges: graph.edges)
            XCTAssertEqual(positions.count, count)
            XCTAssertTrue(positions.values.allSatisfy { $0.x.isFinite && $0.y.isFinite })
            print("Graph layout fixture \(count) nodes / \(graph.edges.count) edges: \(Date().timeIntervalSince(start)) seconds; not a frame-time measurement")
        }
    }

    func testFitAndCameraRoundTripSupportNegativeCoordinates() {
        var camera = GraphCamera()
        let size = CGSize(width: 600, height: 400)
        camera.fit([CGPoint(x: -300, y: -200), CGPoint(x: 100, y: 50)], size: size)
        let world = CGPoint(x: -51, y: 23)
        let restored = camera.worldPoint(camera.screenPoint(world, size: size), size: size)
        XCTAssertEqual(restored.x, world.x, accuracy: 0.001)
        XCTAssertEqual(restored.y, world.y, accuracy: 0.001)
    }
}

@MainActor
final class MemoryGraphStoreTests: XCTestCase {
    private func loaded(_ store: MemoryGraphStore, response: MemoryGraphResponse) async {
        store.load { _ in response }
        await settle(store)
    }
    private func settle(_ store: MemoryGraphStore) async {
        for _ in 0..<200 where store.loading { try? await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertFalse(store.loading, "Graph load did not settle")
        XCTAssertNil(store.error)
    }

    func testRefreshKeepsRelationshipSelectionAndUpdatesSuppliedAttributes() async throws {
        let store = MemoryGraphStore()
        let original = try GraphFixture.make(edgeNote: "Original supplied detail")
        await loaded(store, response: original)
        store.select("fact:0")
        store.select(edge: original.edges[0])
        await loaded(store, response: try GraphFixture.make(edgeNote: "Updated supplied detail"))
        XCTAssertEqual(store.selectedEdge?.from, "fact:0")
        XCTAssertEqual(store.selectedEdge?.to, "fact:1")
        XCTAssertEqual(store.selectedEdge?.type, "child_of")
        XCTAssertEqual(store.selectedEdge?.attrs["note"], .string("Updated supplied detail"))
        XCTAssertTrue(store.showsInspector)
        await loaded(store, response: try GraphFixture.make(edges: 0))
        XCTAssertNil(store.selectedEdge)
        XCTAssertEqual(store.selectedNode?.id, "fact:0")
    }

    func testAmbiguousRefreshedRelationshipsDoNotInventSelectionIdentity() async throws {
        let store = MemoryGraphStore(), original = try GraphFixture.make(edgeNote: "Original")
        await loaded(store, response: original)
        store.select(edge: original.edges[0])
        await loaded(store, response: try GraphFixture.make(edges: 8, edgeNote: "Changed"))
        XCTAssertNil(store.selectedEdge)
    }

    func testFailedFullDetailCanRetryWithoutReselectingNode() async throws {
        let store = MemoryGraphStore()
        await loaded(store, response: try GraphFixture.make())
        store.select("fact:0")
        store.loadFullDetail { throw URLError(.notConnectedToInternet) }
        for _ in 0..<200 where store.detailLoading { try await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertFalse(store.detailLoading)
        XCTAssertNotNil(store.detailError)
        XCTAssertNil(store.fullDetail)
        XCTAssertEqual(store.selectedNode?.id, "fact:0")
        let response = try JSONDecoder().decode(MemoryOverview.self, from: Data(#"{"ok":true}"#.utf8))
        store.loadFullDetail { response }
        for _ in 0..<200 where store.detailLoading { try await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertFalse(store.detailLoading)
        XCTAssertNil(store.detailError)
        XCTAssertEqual(store.fullDetail, "Full detail is unavailable for this memory.")
        XCTAssertEqual(store.selectedNode?.id, "fact:0")
    }

    func testGraphRefreshInvalidatesPreviouslyLoadedFullFact() async throws {
        let store = MemoryGraphStore(), graph = try GraphFixture.make()
        await loaded(store, response: graph); store.select("fact:0")
        let detail = try JSONDecoder().decode(MemoryOverview.self,
            from: Data(#"{"ok":true,"facts":[{"key":"0","content":"Original full memory"}]}"#.utf8))
        store.loadFullDetail { detail }
        for _ in 0..<200 where store.detailLoading { try await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertEqual(store.fullDetail, "Original full memory")
        await loaded(store, response: graph)
        XCTAssertEqual(store.selectedNode?.id, "fact:0")
        XCTAssertNil(store.fullDetail)
        XCTAssertNil(store.detailError)
        XCTAssertFalse(store.detailLoading)
    }

    func testLateDetailCannotReplaceNewSelection() async throws {
        let store = MemoryGraphStore()
        await loaded(store, response: try GraphFixture.make()); store.select("fact:0")
        let detail = try JSONDecoder().decode(MemoryOverview.self,
            from: Data(#"{"ok":true,"facts":[{"key":"0","content":"Old selection"}]}"#.utf8))
        let started = expectation(description: "Old detail request started")
        store.loadFullDetail {
            started.fulfill()
            try? await Task.sleep(nanoseconds: 100_000_000)
            return detail // intentionally returns despite cancellation
        }
        await fulfillment(of: [started], timeout: 1)
        store.select("fact:1")
        try await Task.sleep(nanoseconds: 120_000_000)
        XCTAssertEqual(store.selectedNode?.id, "fact:1")
        XCTAssertNil(store.fullDetail)
        XCTAssertNil(store.detailError)
        XCTAssertFalse(store.detailLoading)
    }

    func testStaleRequestCannotReplaceNewerFocus() async throws {
        let store = MemoryGraphStore(), old = try GraphFixture.make(count: 3), new = try GraphFixture.make(count: 5)
        store.load(query: MemoryGraphQuery(focus: "old")) { _ in
            try? await Task.sleep(nanoseconds: 100_000_000) // deliberately ignores cancellation
            return old
        }
        store.load(query: MemoryGraphQuery(focus: "new")) { _ in new }
        await settle(store)
        try await Task.sleep(nanoseconds: 120_000_000)
        XCTAssertEqual(store.graph?.nodes.count, 5)
        XCTAssertEqual(store.metadata.query.focus, "new")
    }

    func testInitialFitWaitsForUsableViewportAndVisibleNodes() async throws {
        let store = MemoryGraphStore()
        await loaded(store, response: try GraphFixture.make())
        let original = store.metadata.camera
        for size in [CGSize.zero, CGSize(width: 80, height: 600),
                     CGSize(width: 900, height: CGFloat.infinity)] {
            store.fit(size: size)
            XCTAssertTrue(store.needsFit)
            XCTAssertEqual(store.metadata.camera, original)
        }
        store.toggleGroup("fact")
        store.fit(size: CGSize(width: 900, height: 600))
        XCTAssertTrue(store.needsFit)
        XCTAssertEqual(store.metadata.camera, original)
        store.toggleGroup("fact")
        let size = CGSize(width: 900, height: 600)
        store.fit(size: size)
        XCTAssertFalse(store.needsFit)
        for point in store.metadata.positions.values {
            let screen = store.metadata.camera.screenPoint(point, size: size)
            XCTAssertGreaterThanOrEqual(screen.x, 0)
            XCTAssertLessThanOrEqual(screen.x, size.width)
            XCTAssertGreaterThanOrEqual(screen.y, 0)
            XCTAssertLessThanOrEqual(screen.y, size.height)
        }
    }

    func testBackRestoresCameraSelectionAndFilters() async throws {
        let store = MemoryGraphStore(), graph = try GraphFixture.make()
        await loaded(store, response: graph)
        store.select("fact:1")
        store.setCamera(GraphCamera(scale: 1.7, offset: CGPoint(x: 20, y: -30)))
        store.setEdgeType("child_of", visible: false)
        let saved = store.metadata
        store.load(query: MemoryGraphQuery(focus: "fact:2"), remember: true) { _ in graph }
        await settle(store); store.select("fact:2"); store.back()
        XCTAssertEqual(store.metadata.selectedID, "fact:1")
        XCTAssertEqual(store.metadata.camera, saved.camera)
        XCTAssertEqual(store.metadata.hiddenEdgeTypes, ["child_of"])
    }

    func testRefreshPreservesNodeDraggedWhileRequestIsInFlight() async throws {
        let store = MemoryGraphStore(), graph = try GraphFixture.make()
        await loaded(store, response: graph)
        store.load { _ in
            try await Task.sleep(nanoseconds: 50_000_000)
            return graph
        }
        let manual = CGPoint(x: 777, y: -444)
        store.moveNode("fact:1", to: manual)
        await settle(store)
        XCTAssertEqual(store.metadata.positions["fact:1"], manual)
    }

    func testManualCameraChangeSupersedesPendingLayoutReset() async throws {
        let store = MemoryGraphStore()
        await loaded(store, response: try GraphFixture.make())
        store.resetLayout()
        let manual = GraphCamera(scale: 2, offset: CGPoint(x: 50, y: 70))
        store.setCamera(manual)
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(store.metadata.camera, manual)
    }

    func testSearchGroupingAndRefreshDoNotInventOrLoseNodes() async throws {
        let store = MemoryGraphStore()
        await loaded(store, response: try GraphFixture.make())
        store.search = "node 2"
        XCTAssertEqual(store.matchingNodes.map(\.id), ["fact:2"])
        store.select("fact:2"); store.toggleGroup("fact")
        XCTAssertTrue(store.visibleNodes.isEmpty)
        XCTAssertEqual(store.graph?.nodes.count, 4)
        XCTAssertEqual(store.selectedNode?.id, "fact:2")
        store.select("fact:2")
        XCTAssertEqual(store.visibleNodes.count, 4)
        await loaded(store, response: try GraphFixture.make(count: 2))
        XCTAssertNil(store.selectedNode)
        XCTAssertNil(store.metadata.positions["fact:2"])
    }

    func testSavedMetadataContainsNoNodeContentAndRejectsInvalidVersion() async throws {
        let suite = "graph-fixture-\(UUID().uuidString)", key = "view"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = MemoryGraphStore(persistenceKey: key, defaults: defaults)
        await loaded(store, response: try GraphFixture.make())
        store.select("fact:1")
        let data = try XCTUnwrap(defaults.data(forKey: key))
        let json = String(decoding: data, as: UTF8.self)
        XCTAssertFalse(json.contains("fixture content")); XCTAssertFalse(json.contains("Synthetic node"))
        let restored = MemoryGraphStore(persistenceKey: key, defaults: defaults)
        XCTAssertEqual(restored.metadata.selectedID, "fact:1")
        defaults.set(Data(#"{"version":999}"#.utf8), forKey: key)
        let invalid = MemoryGraphStore(persistenceKey: key, defaults: defaults)
        XCTAssertNil(invalid.metadata.selectedID)
    }
}
