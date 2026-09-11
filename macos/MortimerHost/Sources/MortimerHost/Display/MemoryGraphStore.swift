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
            .filter { $0.value.x.isFinite && $0.value.y.isFinite && abs($0.value.x) < 1_000_000 && abs($0.value.y) < 1_000_000 }
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
    @ObservationIgnored private var history: [(MemoryGraphResponse?, MemoryGraphMetadata)] = []
    @ObservationIgnored private let persistenceKey: String?
    @ObservationIgnored private let defaults: UserDefaults

    init(query: MemoryGraphQuery = MemoryGraphQuery(), persistenceKey: String? = nil,
         defaults: UserDefaults = .standard) {
        self.persistenceKey = persistenceKey
        self.defaults = defaults
        if let key = persistenceKey, let data = defaults.data(forKey: key), data.count < 200_000,
           var saved = try? JSONDecoder().decode(MemoryGraphMetadata.self, from: data), saved.version == 1 {
            saved.validate(); metadata = saved; needsFit = false
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
        hasRequested = true
        if remember { history.append((graph, metadata)); history = Array(history.suffix(20)) }
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
        graph = previous.0; metadata = previous.1
        error = nil; selectedEdge = nil; fullDetail = nil
        pathStart = nil; pathEnd = nil
        persist()
    }

    func select(_ id: String) {
        guard let node = graph?.nodes.first(where: { $0.id == id }) else { return }
        metadata.selectedID = id
        metadata.hiddenNodeTypes.remove(node.type)
        metadata.collapsedTypes.remove(node.type)
        selectedEdge = nil; fullDetail = nil; showsInspector = true
        detailRequest?.cancel(); detailLoading = false
        persist()
    }

    func select(edge: MemoryGraphEdge) { selectedEdge = edge; showsInspector = true }

    func centerSelection() {
        guard let id = metadata.selectedID, let point = metadata.positions[id] else { return }
        var camera = metadata.camera
        camera.offset = CGPoint(x: -point.x * camera.scale, y: -point.y * camera.scale)
        setCamera(camera)
    }

    func traceFromSelection() { pathStart = metadata.selectedID; pathEnd = nil }
    func traceToSelection() { pathEnd = metadata.selectedID }
    func clearPath() { pathStart = nil; pathEnd = nil }

    func setNodeType(_ type: String, visible: Bool) {
        if visible { metadata.hiddenNodeTypes.remove(type) } else { metadata.hiddenNodeTypes.insert(type) }
        persist()
    }

    func setEdgeType(_ type: String, visible: Bool) {
        if visible { metadata.hiddenEdgeTypes.remove(type) } else { metadata.hiddenEdgeTypes.insert(type) }
        persist()
    }

    func toggleGroup(_ type: String) {
        if metadata.collapsedTypes.contains(type) { metadata.collapsedTypes.remove(type) }
        else { metadata.collapsedTypes.insert(type) }
        persist()
    }

    func setCamera(_ camera: GraphCamera, save: Bool = true) {
        layoutRevision += 1
        resetRequest?.cancel(); resetRequest = nil
        metadata.camera = camera; metadata.validate(); needsFit = false
        if save { persist() }
    }
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
    func moveNode(_ id: String, to point: CGPoint, save: Bool = true) {
        guard graph?.nodes.contains(where: { $0.id == id }) == true,
              point.x.isFinite, point.y.isFinite else { return }
        metadata.positions[id] = point
        layoutRevision += 1
        resetRequest?.cancel(); resetRequest = nil
        if save { persist() }
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
        guard let node = selectedNode, node.type == "fact", node.id.hasPrefix("fact:") else {
            fullDetail = "Full detail is unavailable through the current read API."
            return
        }
        let key = String(node.id.dropFirst(5)), current = generation
        detailRequest?.cancel(); detailLoading = true
        detailRequest = Task { [weak self] in
            do {
                let overview = try await api.memoryOverview()
                guard let self, !Task.isCancelled, self.generation == current, self.metadata.selectedID == node.id else { return }
                self.fullDetail = overview.ok ? (overview.facts.first { $0.key == key }?.content ?? "Full detail is unavailable for this memory.") : "Memory details unavailable."
                self.detailLoading = false
            } catch {
                guard let self, !Task.isCancelled, self.generation == current, self.metadata.selectedID == node.id else { return }
                self.fullDetail = TabStateMapper.fromError(error).0; self.detailLoading = false
            }
        }
    }

    private func reconcileSelection() {
        let ids = Set(graph?.nodes.map(\.id) ?? [])
        if let selected = metadata.selectedID, !ids.contains(selected) { metadata.selectedID = nil; fullDetail = nil }
        if let edge = selectedEdge, graph?.edges.contains(edge) != true { selectedEdge = nil }
        if let start = pathStart, !ids.contains(start) { pathStart = nil }
        if let end = pathEnd, !ids.contains(end) { pathEnd = nil }
    }

    private func persist() {
        guard let key = persistenceKey, let data = try? JSONEncoder().encode(metadata) else { return }
        defaults.set(data, forKey: key)
    }
}
