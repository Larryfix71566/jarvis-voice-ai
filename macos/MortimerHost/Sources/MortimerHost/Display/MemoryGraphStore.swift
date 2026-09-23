import Foundation
import Observation
import JarvisKit

struct MemoryGraphMetadata: Codable {
    var query: MemoryGraphQuery
    var camera = GraphCamera()
    var selectedID: String?
    var hiddenNodeTypes: Set<String> = []
    var hiddenEdgeTypes: Set<String> = []
    var collapsedTypes: Set<String> = []
    var positions: [String: CGPoint] = [:]
    var version = 1

    mutating func validate() {
        query.depth = min(4, max(1, query.depth))
        if !camera.scale.isFinite || !camera.offset.x.isFinite || !camera.offset.y.isFinite {
            camera = GraphCamera()
        }
        camera.scale = min(5, max(0.15, camera.scale))
        camera.offset.x = min(1_000_000, max(-1_000_000, camera.offset.x))
        camera.offset.y = min(1_000_000, max(-1_000_000, camera.offset.y))
        positions = Dictionary(uniqueKeysWithValues: positions.sorted { $0.key < $1.key }
            .filter { $0.value.x.isFinite && $0.value.y.isFinite && abs($0.value.x) <= 1_000_000 && abs($0.value.y) <= 1_000_000 }
            .prefix(MemoryGraphResponse.nodeLimit).map { ($0.key, $0.value) })
    }
}

@MainActor
@Observable
final class MemoryGraphStore {
    let imageFallback = MemoryGraphImageStore()
    private(set) var graph: MemoryGraphResponse?
    private(set) var loading = false
    private(set) var error: String?
    private(set) var metadata: MemoryGraphMetadata
    private(set) var selectedEdge: MemoryGraphEdge?
    private(set) var pathStart: String?
    private(set) var pathEnd: String?
    private(set) var fullDetail: String?
    private(set) var detailError: String?
    private(set) var detailLoading = false
    var search = ""
    var showsInspector = true
    var usesImageFallback = false
    private(set) var needsFit = true

    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var hasRequested = false
    @ObservationIgnored private var layoutRevision = 0
    @ObservationIgnored private var request: Task<Void, Never>?
    @ObservationIgnored private var detailRequest: Task<Void, Never>?
    @ObservationIgnored private var resetRequest: Task<Void, Never>?
    @ObservationIgnored private var lastFetch: (@Sendable (MemoryGraphQuery) async throws -> MemoryGraphResponse)?
    private struct HistoryEntry {
        let graph: MemoryGraphResponse?
        let metadata: MemoryGraphMetadata
        let selectedEdge: MemoryGraphEdge?
        let pathStart: String?
        let pathEnd: String?
        let search: String
        let showsInspector: Bool
    }
    @ObservationIgnored private var history: [HistoryEntry] = []
    @ObservationIgnored private let persistenceKey: String?
    @ObservationIgnored private let defaults: UserDefaults

    init(query: MemoryGraphQuery = MemoryGraphQuery(), persistenceKey: String? = nil,
         defaults: UserDefaults = .standard) {
        self.persistenceKey = persistenceKey
        self.defaults = defaults
        if let key = persistenceKey, let data = defaults.data(forKey: key), data.count < 200_000,
           var saved = try? JSONDecoder().decode(MemoryGraphMetadata.self, from: data), saved.version == 1 {
            saved.validate(); metadata = saved
            // Closing an unavailable or empty graph also saves metadata. There
            // is no established view to restore until it has node positions.
            needsFit = saved.positions.isEmpty
        } else { metadata = MemoryGraphMetadata(query: query) }
    }

    var canGoBack: Bool { !history.isEmpty }
    var selectedNode: MemoryGraphNode? { graph?.nodes.first { $0.id == metadata.selectedID } }
    var nodeTypes: [String] { Set((graph?.nodes.map(\.type) ?? []) + Array((graph?.legend.nodeTypes ?? [:]).keys)).sorted() }
    var edgeTypes: [String] { Set((graph?.edges.map(\.type) ?? []) + (graph?.edgeTypes ?? [])).sorted() }
    var filteredNodes: [MemoryGraphNode] {
        (graph?.nodes ?? []).filter { !metadata.hiddenNodeTypes.contains($0.type) }
    }
    var visibleNodes: [MemoryGraphNode] { filteredNodes.filter { !metadata.collapsedTypes.contains($0.type) } }
    var matchingNodes: [MemoryGraphNode] {
        filteredNodes.filter { search.isEmpty || $0.label.localizedCaseInsensitiveContains(search) || $0.id.localizedCaseInsensitiveContains(search) }
    }
    var visibleEdges: [MemoryGraphEdge] {
        let ids = Set(visibleNodes.map(\.id))
        return (graph?.edges ?? []).filter {
            !metadata.hiddenEdgeTypes.contains($0.type) && ids.contains($0.from) && ids.contains($0.to)
        }
    }
    var tracedPath: [String]? {
        guard let start = pathStart, let end = pathEnd else { return nil }
        return MemoryGraphLayout.path(from: start, to: end, nodes: Set(visibleNodes.map(\.id)), edges: visibleEdges)
    }

    func load(api: AdminAPI, query: MemoryGraphQuery? = nil, remember: Bool = false) {
        load(query: query, remember: remember) { try await api.memoryGraph($0) }
    }

    func loadIfNeeded(api: AdminAPI) {
        guard !hasRequested else { return }
        load(api: api)
    }

    /// Injectable read seam for cancellation and stale-response tests.
    func load(query: MemoryGraphQuery? = nil, remember: Bool = false,
              fetch: @escaping @Sendable (MemoryGraphQuery) async throws -> MemoryGraphResponse) {
        lastFetch = fetch
        hasRequested = true
        if remember {
            history.append(HistoryEntry(graph: graph, metadata: metadata, selectedEdge: selectedEdge,
                pathStart: pathStart, pathEnd: pathEnd, search: search, showsInspector: showsInspector))
            history = Array(history.suffix(20))
        }
        let next = query ?? metadata.query
        let preserving = metadata.positions
        cancel()
        metadata.query = next
        loading = true; error = nil
        let current = generation
        request = Task { [weak self] in
            do {
                try Task.checkCancellation()
                let response = try await fetch(next)
                try Task.checkCancellation()
                let layoutTask = Task.detached(priority: .userInitiated) {
                    try MemoryGraphLayout.positions(nodes: response.nodes, edges: response.edges, preserving: preserving)
                }
                let positions = try await withTaskCancellationHandler {
                    try await layoutTask.value
                } onCancel: { layoutTask.cancel() }
                guard let self, self.generation == current, !Task.isCancelled else { return }
                self.graph = response
                // Full facts come from a separate read and may no longer match
                // the refreshed graph, even when the selected ID survives.
                self.detailRequest?.cancel(); self.detailRequest = nil
                self.detailLoading = false; self.fullDetail = nil; self.detailError = nil
                // A user may drag while a fetch/layout is in flight. Keep
                // their latest points for IDs which survived the refresh.
                let latestPoints = self.metadata.positions
                self.metadata.positions = positions
                for id in positions.keys {
                    if let latest = latestPoints[id], let prior = preserving[id], latest != prior {
                        self.metadata.positions[id] = latest
                    }
                }
                self.metadata.query = next
                self.reconcileSelection()
                self.loading = false
                self.persist()
            } catch {
                guard let self, self.generation == current, !Task.isCancelled else { return }
                self.loading = false
                self.error = error is JarvisError ? TabStateMapper.fromError(error).0 : error.localizedDescription
            }
        }
    }

    /// Re-run the most recent graph request through the same injected API
    /// closure. Retry is explicit and never fabricates a graph on failure.
    @discardableResult
    func retry() -> Bool {
        guard let lastFetch else { return false }
        load(query: metadata.query, remember: false, fetch: lastFetch)
        return true
    }

    func cancel() {
        imageFallback.cancel()
        generation += 1
        request?.cancel(); request = nil
        resetRequest?.cancel(); resetRequest = nil
        detailRequest?.cancel(); detailRequest = nil
        loading = false; detailLoading = false
    }

    func back() {
        guard let previous = history.popLast() else { return }
        cancel()
        graph = previous.graph; metadata = previous.metadata
        error = nil; selectedEdge = previous.selectedEdge; fullDetail = nil; detailError = nil
        pathStart = previous.pathStart; pathEnd = previous.pathEnd
        search = previous.search; showsInspector = previous.showsInspector
        reconcileSelection()
        persist()
    }

    /// Closure C3.5 (gap G15): selecting never mutates the user's filters.
    /// A hidden selection is disclosed by `selectedNodeHidden`; revealing it
    /// is the explicit `revealSelection()` action.
    func select(_ id: String) {
        guard graph?.nodes.contains(where: { $0.id == id }) == true else { return }
        metadata.selectedID = id
        selectedEdge = nil; fullDetail = nil; detailError = nil; showsInspector = true
        detailRequest?.cancel(); detailLoading = false
        persist()
    }

    /// Focus a loaded node and, when a depth is supplied, repeat the existing
    /// authenticated graph request at that depth. The request closure is the
    /// same one used for the current graph; no alternate data source is
    /// invented for a voice command.
    @discardableResult
    func focus(_ id: String, depth: Int? = nil) -> Bool {
        guard graph?.nodes.contains(where: { $0.id == id }) == true else { return false }
        if let depth, !(1...4).contains(depth) { return false }
        select(id)
        centerSelection()
        guard let depth, depth != metadata.query.depth else { return true }
        guard let fetch = lastFetch else { return false }
        var query = metadata.query
        query.focus = id
        query.setDepth(depth)
        load(query: query, remember: true, fetch: fetch)
        return true
    }

    func select(edge: MemoryGraphEdge) { selectedEdge = edge; showsInspector = true }

    var selectedNodeHidden: Bool {
        guard let node = selectedNode else { return false }
        return metadata.hiddenNodeTypes.contains(node.type) || metadata.collapsedTypes.contains(node.type)
    }

    func revealSelection() {
        guard let node = selectedNode else { return }
        metadata.hiddenNodeTypes.remove(node.type)
        metadata.collapsedTypes.remove(node.type)
        persist()
    }

    /// Arrowhead vocabulary for the canvas (closure C3.4): the server's
    /// legend keys, or the documented memory-graph set when absent.
    var directionalEdgeTypes: Set<String> {
        graph?.legend.directionalEdgeTypes ?? MemoryGraphLegend.memoryDirectionalEdgeTypes
    }

    func centerSelection() {
        guard let id = metadata.selectedID, let point = metadata.positions[id] else { return }
        var camera = metadata.camera
        camera.offset = CGPoint(x: -point.x * camera.scale, y: -point.y * camera.scale)
        setCamera(camera)
    }

    func traceFromSelection() { pathStart = metadata.selectedID; pathEnd = nil }
    func traceToSelection() { pathEnd = metadata.selectedID }
    func clearPath() { pathStart = nil; pathEnd = nil }

    @discardableResult
    func setNodeType(_ type: String, visible: Bool) -> Bool {
        guard graph?.nodes.contains(where: { $0.type == type }) == true else { return false }
        if visible { metadata.hiddenNodeTypes.remove(type) } else { metadata.hiddenNodeTypes.insert(type) }
        persist()
        return true
    }

    @discardableResult
    func setEdgeType(_ type: String, visible: Bool) -> Bool {
        guard graph?.edges.contains(where: { $0.type == type }) == true else { return false }
        if visible { metadata.hiddenEdgeTypes.remove(type) } else { metadata.hiddenEdgeTypes.insert(type) }
        persist()
        return true
    }

    func toggleGroup(_ type: String) {
        if metadata.collapsedTypes.contains(type) { metadata.collapsedTypes.remove(type) }
        else { metadata.collapsedTypes.insert(type) }
        persist()
    }
    @discardableResult
    func setGroup(_ type: String, collapsed: Bool) -> Bool {
        guard graph?.nodes.contains(where: { $0.type == type }) == true else { return false }
        if collapsed { metadata.collapsedTypes.insert(type) }
        else { metadata.collapsedTypes.remove(type) }
        persist()
        return true
    }
    @discardableResult
    func setPath(start: String, end: String) -> Bool {
        guard start != end, let nodes = graph?.nodes.map(\.id),
              nodes.contains(start), nodes.contains(end) else { return false }
        pathStart = start; pathEnd = end; persist()
        return true
    }

    func setCamera(_ camera: GraphCamera, save: Bool = true) {
        layoutRevision += 1
        resetRequest?.cancel(); resetRequest = nil
        metadata.camera = camera; metadata.validate(); needsFit = false
        if save { persist() }
    }

    /// Console adapters use the same camera and filter setters as pointer
    /// gestures. Keeping these operations here prevents a second graph state
    /// owner for voice commands.
    func setSearch(_ value: String) { search = String(value.prefix(200)) }
    @discardableResult
    func zoom(_ direction: String) -> Bool {
        var camera = metadata.camera
        switch direction {
        case "in": camera.zoom(1.25)
        case "out": camera.zoom(0.8)
        case "reset": camera = GraphCamera()
        default: return false
        }
        setCamera(camera)
        return true
    }
    @discardableResult
    func pan(_ direction: String, amount: CGFloat = 80) -> Bool {
        guard amount.isFinite, amount > 0 else { return false }
        var camera = metadata.camera
        switch direction {
        case "up": camera.offset.y += amount
        case "down": camera.offset.y -= amount
        case "left": camera.offset.x += amount
        case "right": camera.offset.x -= amount
        default: return false
        }
        setCamera(camera)
        return true
    }
    func setInspector(_ open: Bool) { showsInspector = open; persist() }
    func fit(size: CGSize) {
        // SwiftUI may report zero before layout, or all nodes may temporarily
        // be grouped/filtered. Neither consumes the pending initial fit.
        let points = visibleNodes.compactMap { metadata.positions[$0.id] }
        guard size.width.isFinite, size.height.isFinite,
              size.width > 80, size.height > 80, !points.isEmpty else { return }
        var camera = metadata.camera
        camera.fit(points, size: size)
        setCamera(camera)
    }
    func saveView() { persist() }
    @discardableResult
    func moveNode(_ id: String, to point: CGPoint, save: Bool = true) -> Bool {
        guard graph?.nodes.contains(where: { $0.id == id }) == true,
              point.x.isFinite, point.y.isFinite,
              abs(point.x) <= 1_000_000, abs(point.y) <= 1_000_000 else { return false }
        metadata.positions[id] = point
        layoutRevision += 1
        resetRequest?.cancel(); resetRequest = nil
        if save { persist() }
        return true
    }

    func resetLayout() {
        guard let graph else { return }
        resetRequest?.cancel()
        layoutRevision += 1
        let current = generation, revision = layoutRevision
        resetRequest = Task { [weak self] in
            let layout = Task.detached(priority: .userInitiated) {
                try MemoryGraphLayout.positions(nodes: graph.nodes, edges: graph.edges)
            }
            let points = try? await withTaskCancellationHandler { try await layout.value } onCancel: { layout.cancel() }
            guard let self, !Task.isCancelled, self.generation == current, self.layoutRevision == revision, let points else { return }
            self.metadata.positions = points; self.metadata.camera = GraphCamera(); self.needsFit = true; self.persist()
        }
    }

    func loadFullDetail(api: AdminAPI) {
        loadFullDetail { try await api.memoryOverview() }
    }

    func loadFullDetail(fetch: @escaping @Sendable () async throws -> MemoryOverview) {
        guard let node = selectedNode, node.type == "fact", node.id.hasPrefix("fact:") else {
            fullDetail = "Full detail is unavailable through the current read API."
            return
        }
        let key = String(node.id.dropFirst(5)), current = generation
        detailRequest?.cancel(); detailLoading = true; detailError = nil; fullDetail = nil
        detailRequest = Task { [weak self] in
            do {
                let overview = try await fetch()
                guard let self, !Task.isCancelled, self.generation == current, self.metadata.selectedID == node.id else { return }
                if overview.ok {
                    self.fullDetail = overview.facts.first { $0.key == key }?.content ?? "Full detail is unavailable for this memory."
                } else { self.detailError = "Memory details unavailable." }
                self.detailLoading = false
            } catch {
                guard let self, !Task.isCancelled, self.generation == current, self.metadata.selectedID == node.id else { return }
                self.detailError = TabStateMapper.fromError(error).0; self.detailLoading = false
            }
        }
    }

    private func reconcileSelection() {
        let ids = Set(graph?.nodes.map(\.id) ?? [])
        if let selected = metadata.selectedID, !ids.contains(selected) { metadata.selectedID = nil; fullDetail = nil }
        if let edge = selectedEdge {
            let candidates = (graph?.edges ?? []).filter {
                $0.from == edge.from && $0.to == edge.to && $0.type == edge.type
            }
            // Attributes can change on refresh. Preserve an exact match first;
            // otherwise update only an unambiguous directed relationship.
            selectedEdge = candidates.first(where: { $0 == edge })
                ?? (candidates.count == 1 ? candidates.first : nil)
        }
        if let start = pathStart, !ids.contains(start) { pathStart = nil }
        if let end = pathEnd, !ids.contains(end) { pathEnd = nil }
    }

    private func persist() {
        guard let key = persistenceKey, let data = try? JSONEncoder().encode(metadata) else { return }
        defaults.set(data, forKey: key)
    }
}
