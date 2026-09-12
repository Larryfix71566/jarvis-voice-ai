import XCTest
import JarvisKit
@testable import MortimerHost

/// Closure plan C3.2, C3.3 and C3.5 (gaps G12, G13, G15) on the host side.
/// C3.1 lives in MemoryGraphFrameTimeTests; C3.4 in JarvisKitTests.
@MainActor
final class MemoryGraphClosureC3Tests: XCTestCase {
    private func loaded(_ store: MemoryGraphStore, response: MemoryGraphResponse) async {
        store.load { _ in response }
        for _ in 0..<4000 where store.loading { try? await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertFalse(store.loading, "Graph load did not settle")
        XCTAssertNil(store.error)
    }

    // MARK: G12 — dense hub

    func testDenseHubFixtureHasTheRequiredShapeAndABoundedFiniteLayout() throws {
        let graph = try GraphFixture.denseHub()
        XCTAssertEqual(graph.nodes.count, 500)
        XCTAssertEqual(graph.edges.count, 2000)
        let hubDegree = graph.edges.filter { $0.from == GraphFixture.hubID || $0.to == GraphFixture.hubID }.count
        XCTAssertGreaterThanOrEqual(hubDegree, 200, "the hub must have degree ≥ 200")
        XCTAssertTrue(graph.nodes.allSatisfy { $0.label.count == GraphFixture.longLabelLength }, "every label is 48 characters")
        XCTAssertFalse(graph.edges.contains { $0.from == $0.to }, "no self-loops")
        let positions = try MemoryGraphLayout.positions(nodes: graph.nodes, edges: graph.edges)
        XCTAssertEqual(positions.count, 500)
        XCTAssertTrue(positions.values.allSatisfy { $0.x.isFinite && $0.y.isFinite }, "layout produced NaN/inf")
        // Bound derivation: initial spiral radius 24·√500 ≈ 537 pt, then at
        // most 60 steps of ≤ 12 pt each (≤ 720 pt) — well inside 5,000 pt,
        // and far inside the 1,000,000 pt metadata cap.
        XCTAssertTrue(positions.values.allSatisfy { abs($0.x) < 5_000 && abs($0.y) < 5_000 }, "layout is not bounded")
        let distinct = Set(positions.values.map { "\(Int($0.x.rounded())),\(Int($0.y.rounded()))" })
        XCTAssertGreaterThan(distinct.count, 450, "hub neighbours collapsed onto the same points")
        // The hub is reachable from the far end of the chain through loaded edges.
        let path = MemoryGraphLayout.path(from: "fact:499", to: GraphFixture.hubID,
                                          nodes: Set(graph.nodes.map(\.id)), edges: graph.edges)
        XCTAssertNotNil(path)
    }

    // MARK: G13 — no bare URLSession.shared outside JarvisHTTP

    func testURLSessionSharedIsOnlyUsedByJarvisHTTPAndTheWakeWordSocket() throws {
        let root = GraphFixture.repositoryRoot()
        var offenders: [String] = []
        var uses: [String: [String]] = [:]
        var scanned: Set<String> = []
        for package in ["macos/MortimerHost/Sources", "macos/JarvisKit/Sources"] {
            let base = root.appendingPathComponent(package)
            let enumerator = try XCTUnwrap(FileManager.default.enumerator(at: base, includingPropertiesForKeys: nil))
            for case let file as URL in enumerator where file.pathExtension == "swift" {
                let relative = String(file.path.dropFirst(root.path.count + 1))
                scanned.insert(relative)
                for line in try String(contentsOf: file, encoding: .utf8).components(separatedBy: "\n") {
                    let code = line.components(separatedBy: "//").first ?? line
                    guard code.contains("URLSession.shared") else { continue }
                    uses[relative, default: []].append(line.trimmingCharacters(in: .whitespaces))
                    // Pre-existing at baseline (P0 checklist): the wake-word
                    // listener's WebSocket task is not an HTTP fetch and is
                    // out of this closure's scope. Everything else is an offender.
                    let allowed = relative.hasSuffix("JarvisKit/Sources/JarvisKit/JarvisHTTP.swift")
                        || (relative.hasSuffix("JarvisKit/Sources/JarvisKit/WakeWordListener.swift") && code.contains("webSocketTask"))
                    if !allowed { offenders.append("\(relative): \(line.trimmingCharacters(in: .whitespaces))") }
                }
            }
        }
        // JarvisHTTP spells the shared session `session: .shared`; the scan
        // must have reached it and the graph/image views for the result to mean anything.
        XCTAssertTrue(scanned.contains("macos/JarvisKit/Sources/JarvisKit/JarvisHTTP.swift"), "scan did not reach JarvisHTTP.swift: \(scanned.count) files")
        XCTAssertTrue(scanned.contains("macos/MortimerHost/Sources/MortimerHost/Display/GraphImageView.swift"))
        XCTAssertGreaterThan(scanned.count, 40, "the scan covered too few files: \(scanned.count)")
        XCTAssertEqual(offenders, [], "bare URLSession.shared outside JarvisHTTP")
        XCTAssertEqual(uses.keys.sorted(), ["macos/JarvisKit/Sources/JarvisKit/WakeWordListener.swift"],
                       "the only remaining literal use is the pre-existing wake-word WebSocket; uses: \(uses)")
        XCTAssertNil(uses.keys.first { $0.hasSuffix("GraphImageView.swift") }, "GraphImageView must not fetch on its own")
        let imageView = try String(contentsOf: root.appendingPathComponent("macos/MortimerHost/Sources/MortimerHost/Display/GraphImageView.swift"), encoding: .utf8)
        XCTAssertTrue(imageView.contains("client.admin.graphImageData(at: url)"), "GraphImageView fetches through AdminAPI")
    }

    // MARK: G15 — selection never mutates filters; hidden selection is disclosed and revealable

    func testSelectingAHiddenOrCollapsedNodeKeepsTheFilterAndRevealIsExplicit() async throws {
        let suite = "graph-c3-\(UUID().uuidString)", key = "view"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = MemoryGraphStore(persistenceKey: key, defaults: defaults)
        await loaded(store, response: try GraphFixture.clustered())
        XCTAssertFalse(store.selectedNodeHidden)
        store.setNodeType("fact", visible: false)
        store.select("fact:project.1.item.2")
        XCTAssertEqual(store.selectedNode?.id, "fact:project.1.item.2")
        XCTAssertEqual(store.metadata.hiddenNodeTypes, ["fact"], "select() must not un-hide the type")
        XCTAssertTrue(store.selectedNodeHidden)
        XCTAssertFalse(store.visibleNodes.contains { $0.type == "fact" })
        store.revealSelection()
        XCTAssertEqual(store.metadata.hiddenNodeTypes, [])
        XCTAssertFalse(store.selectedNodeHidden)
        XCTAssertTrue(store.visibleNodes.contains { $0.id == "fact:project.1.item.2" })
        // Collapsed groups behave the same way.
        store.toggleGroup("turn")
        store.select("turn:3")
        XCTAssertEqual(store.metadata.collapsedTypes, ["turn"])
        XCTAssertTrue(store.selectedNodeHidden)
        XCTAssertFalse(store.visibleNodes.contains { $0.id == "turn:3" })
        store.revealSelection()
        XCTAssertEqual(store.metadata.collapsedTypes, [])
        XCTAssertTrue(store.visibleNodes.contains { $0.id == "turn:3" })
        // The reveal is persisted like any other filter change.
        let restored = MemoryGraphStore(persistenceKey: key, defaults: defaults)
        XCTAssertEqual(restored.metadata.hiddenNodeTypes, []); XCTAssertEqual(restored.metadata.collapsedTypes, [])
        XCTAssertEqual(restored.metadata.selectedID, "turn:3")
        // Selecting an unknown id changes nothing.
        store.setNodeType("prefix", visible: false)
        store.select("fact:missing")
        XCTAssertEqual(store.selectedNode?.id, "turn:3")
        XCTAssertEqual(store.metadata.hiddenNodeTypes, ["prefix"])
    }

    // MARK: G15 — §4.5 item 6 wording, exactly

    func testNoPathWordingMatchesTheInterfacePlanExactly() throws {
        let root = GraphFixture.repositoryRoot()
        let view = try String(contentsOf: root.appendingPathComponent("macos/MortimerHost/Sources/MortimerHost/Display/MemoryGraphView.swift"), encoding: .utf8)
        XCTAssertTrue(view.contains("Text(\"No path in this loaded view\")"), "the truncation message is the plan's literal")
        let literals = view.components(separatedBy: "Text(\"").dropFirst().compactMap { $0.components(separatedBy: "\")").first }
        XCTAssertEqual(literals.filter { $0.hasPrefix("No path") }, ["No path in this loaded view"], "no extended variant of the literal remains")
        XCTAssertFalse(view.contains("These memories are unrelated"))
        XCTAssertTrue(view.contains("Text(\"Selected node is hidden by a filter\")") && view.contains("Button(\"Reveal\")"),
                      "hidden selection is disclosed with an explicit Reveal action")
        let plan = try String(contentsOf: root.appendingPathComponent("docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md"), encoding: .utf8)
        XCTAssertTrue(plan.contains("**No path in this loaded view**"), "plan §4.5 item 6 still carries the literal this test pins")
    }
}
