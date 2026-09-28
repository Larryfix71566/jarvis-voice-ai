import SwiftUI
import JarvisKit

/// A session-only working surface that combines live research results with
/// read-only project context. Result cards remain owned by WorkspaceStore;
/// the context projection is refreshed from the authenticated AdminAPI and
/// never becomes a second mutable source of truth.
struct KnowledgeAtlasView: View {
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(AtlasStore.self) private var atlas
    @Environment(AgentRunStore.self) private var agentRuns
    @EnvironmentObject private var client: JarvisClient
    private let columns = [GridItem(.adaptive(minimum: 260, maximum: 360), spacing: 20)]

    init(coordinator: ConsoleActionCoordinator? = nil) {
        self.coordinator = coordinator
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Knowledge Atlas").font(.title2.weight(.semibold))
                    Spacer()
                    Button { refreshContext(force: true) } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .accessibilityLabel("Refresh Knowledge Atlas sources")
                }
                sourceHealthStrip

                if atlas.cards.isEmpty {
                    if AtlasContextSource.allCases.contains(where: {
                        atlas.sourceHealth[$0]?.phase == .failed
                    }) {
                        ContentUnavailableView("Atlas sources unavailable",
                            systemImage: "exclamationmark.icloud",
                            description: Text("Some sources could not be loaded. Retry to try again."))
                    } else if AtlasContextSource.allCases.contains(where: {
                        atlas.sourceHealth[$0]?.phase == .loading
                    }) {
                        ProgressView("Loading Atlas sources…")
                            .frame(maxWidth: .infinity, minHeight: 180)
                    } else {
                        ContentUnavailableView("Atlas is empty", systemImage: "square.grid.2x2",
                            description: Text("Research, memory, architecture and plan context will appear here."))
                    }
                } else {
                    LazyVGrid(columns: columns, alignment: .leading, spacing: 20) {
                        ForEach(atlas.visibleCards) { card in
                            AtlasCardButton(card: card, selected: workspace.activeID == card.id) {
                                if let coordinator {
                                    _ = coordinator.executePointer(.resultSelect, target: card.id.uuidString)
                                } else {
                                    workspace.select(card.id)
                                }
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .scaleEffect(atlas.zoomScale, anchor: .center)
        .offset(atlas.panOffset)
        .background(AppTheme.bg)
        .onAppear {
            syncResults()
            refreshContext()
        }
        .onDisappear {
            cancelContextRefreshes()
        }
        .onChange(of: workspace.results) { _, _ in syncResults() }
        .onChange(of: workspace.memoryGraph.graph) { _, graph in syncGraphSource(graph) }
        .onChange(of: agentRuns.lastCompleted) { _, _ in refreshRuns() }
        .onChange(of: client.state) { _, state in
            if case .connected = state { refreshContext() }
        }
    }

    private var sourceHealthStrip: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                sourceStatusChip(.memory)
                sourceStatusChip(.architecture)
                sourceStatusChip(.plan)
                sourceStatusChip(.runs)
                sourceStatusChip(.memoryGraph)
            }
        }
        .scrollIndicators(.hidden)
    }

    private func sourceStatusChip(_ source: AtlasContextSource) -> some View {
        let health = atlas.sourceHealth[source] ?? AtlasSourceHealth()
        return Label(sourceStatusText(health), systemImage: sourceStatusIcon(health))
            .font(.caption)
            .foregroundStyle(health.phase == .failed ? AppTheme.attn : AppTheme.textDim)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(AppTheme.panel, in: Capsule())
            .accessibilityLabel("\(source.label): \(sourceStatusText(health))")
    }

    private func sourceStatusText(_ health: AtlasSourceHealth) -> String {
        switch health.phase {
        case .idle: return "Not loaded"
        case .loading: return "Loading"
        case .loaded:
            if health.stale { return "Stale · \(lastSuccessTime(health))" }
            return health.lastSuccessAt.map {
                "Updated \($0.formatted(date: .omitted, time: .shortened))"
            } ?? "Ready"
        case .empty:
            return health.lastSuccessAt.map {
                "No data · \($0.formatted(date: .omitted, time: .shortened))"
            } ?? "No data"
        case .failed:
            let category = health.failure?.rawValue ?? "unavailable"
            return health.stale
                ? "Stale · \(category) · \(lastSuccessTime(health))"
                : "Unavailable · \(category)"
        }
    }

    private func lastSuccessTime(_ health: AtlasSourceHealth) -> String {
        health.lastSuccessAt?.formatted(date: .omitted, time: .shortened) ?? "last good"
    }

    private func sourceStatusIcon(_ health: AtlasSourceHealth) -> String {
        switch health.phase {
        case .idle: return "circle"
        case .loading: return "arrow.triangle.2.circlepath"
        case .loaded: return health.stale ? "clock" : "checkmark.circle.fill"
        case .empty: return "minus.circle"
        case .failed: return "exclamationmark.circle.fill"
        }
    }

    private func syncResults() {
        atlas.replaceResults(workspace.results.map { result in
            AtlasCard(id: result.id, title: result.payload.title ?? "Result",
                      summary: result.payload.body ?? "No preview supplied",
                      source: result.payload.links?.first?.url, group: nil,
                      kind: .result)
        })
    }

    private func refreshContext(force: Bool = false) {
        let api = client.admin
        let classify = Self.failureCategory
        atlas.refresh(source: .memory, force: force, classifyFailure: classify) {
            let value = try await api.memoryOverview()
            return Self.cards(for: .memory, memory: value)
        }
        atlas.refresh(source: .architecture, force: force, classifyFailure: classify) {
            let value = try await api.architectureReference()
            guard value.ok else { throw AtlasInvalidResponse() }
            return Self.cards(for: .architecture, architecture: value)
        }
        atlas.refresh(source: .plan, force: force, classifyFailure: classify) {
            let value = try await api.planJob()
            return Self.cards(for: .plan, plan: value)
        }
        atlas.refresh(source: .runs, force: force, classifyFailure: classify) {
            let value = try await api.runsTyped()
            return Self.cards(for: .runs, runs: value)
        }
        syncGraphSource(workspace.memoryGraph.graph)
    }

    /// Agent completion is the existing source-change event for run history.
    /// Refresh only that projection; changing or moving an Atlas presentation
    /// must not refetch unrelated sources or create another result request.
    private func refreshRuns() {
        let api = client.admin
        atlas.refresh(source: .runs, classifyFailure: Self.failureCategory) {
            let value = try await api.runsTyped()
            return Self.cards(for: .runs, runs: value)
        }
    }

    private func cancelContextRefreshes() {
        atlas.cancelRefreshes()
    }

    private func syncGraphSource(_ graph: MemoryGraphResponse?) {
        let generation = atlas.beginRefresh(.memoryGraph)
        _ = atlas.completeRefresh(.memoryGraph, generation: generation,
            cards: Self.cards(for: .memoryGraph, graph: graph), empty: graph == nil)
    }

    private static func failureCategory(_ error: Error) -> AtlasFailureCategory {
        if error is AtlasInvalidResponse { return .invalidResponse }
        if let error = error as? URLError, error.code == .timedOut { return .timedOut }
        if error is DecodingError { return .invalidResponse }
        return .unavailable
    }

    private struct AtlasInvalidResponse: Error {}

    private static func cards(for source: AtlasContextSource,
                              memory: MemoryOverview? = nil,
                              architecture: ArchitectureReference? = nil,
                              plan: JSONValue? = nil,
                              runs: RunsList? = nil,
                              graph: MemoryGraphResponse? = nil) -> [AtlasCard] {
        let all = contextCards(memory: memory, architecture: architecture,
                               plan: plan, runs: runs, graph: graph)
        switch source {
        case .memory: return all.filter { $0.kind == .memory }
        case .architecture: return all.filter { $0.kind == .architecture }
        case .plan: return all.filter { $0.kind == .plan }
        case .runs: return all.filter { $0.kind == .run }
        case .memoryGraph: return all.filter { $0.kind == .memoryGraph }
        }
    }

    private static func contextCards(memory: MemoryOverview?, architecture: ArchitectureReference?,
                                     plan: JSONValue?, runs: RunsList?, graph: MemoryGraphResponse?)
        -> [AtlasCard] {
        var cards: [AtlasCard] = []
        if let memory {
            let usage = "\(memory.usage.factCount) facts; \(memory.usage.maxContextChars) context chars"
            cards.append(AtlasCard(
                id: AtlasStore.stableID(namespace: "memory", key: "overview"),
                title: "Memory overview", summary: [memory.summary, usage].filter { !$0.isEmpty }.joined(separator: "\n"),
                source: "AdminAPI /api/memory", group: "Memory", kind: .memory,
                metadata: ["fact_count": String(memory.usage.factCount), "over_capacity": String(memory.usage.overCapacity)]))
            for fact in memory.facts.prefix(12) {
                cards.append(AtlasCard(
                    id: AtlasStore.stableID(namespace: "memory", key: "fact:\(fact.id)"),
                    title: fact.key.isEmpty ? "Memory fact" : fact.key,
                    summary: fact.content, source: "\(fact.tier) · \(fact.evidenceStatus)", group: "Memory",
                    kind: .memory,
                    metadata: ["confidence": String(fact.confidence), "memory_type": fact.memoryType]))
            }
        }
        if let architecture, architecture.ok {
            cards.append(AtlasCard(
                id: AtlasStore.stableID(namespace: "architecture", key: architecture.path),
                title: "Architecture reference", summary: clipped(architecture.content, to: 1_200),
                source: architecture.path, group: "Project context", kind: .architecture,
                metadata: ["sha256": architecture.sha256 ?? "", "truncated": String(architecture.truncated)]))
        }
        if let plan {
            let job = plan["job"] ?? plan
            let state = job["state"]?.stringValue ?? "unknown"
            let goal = job["goal"]?.stringValue ?? ""
            let body = job["plan"]?.stringValue ?? job["summary"]?.stringValue ?? ""
            let summary = [goal.isEmpty ? nil : goal, body.isEmpty ? nil : clipped(body, to: 1_000)]
                .compactMap { $0 }.joined(separator: "\n\n")
            cards.append(AtlasCard(
                id: AtlasStore.stableID(namespace: "plan", key: "current"),
                title: "Current plan · \(state)", summary: summary.isEmpty ? "No active plan details." : summary,
                source: "AdminAPI /api/plan/job", group: "Project context", kind: .plan,
                metadata: ["state": state]))
        }
        if let runs {
            cards.append(AtlasCard(
                id: AtlasStore.stableID(namespace: "runs", key: "overview"),
                title: "Recent runs", summary: runs.runs.isEmpty ? "No recorded runs." : "\(runs.runs.count) runs available.",
                source: "AdminAPI /api/runs", group: "Project context", kind: .run,
                metadata: ["count": String(runs.runs.count)]))
            for run in runs.runs.prefix(8) {
                let detail = [run.task, run.replyPreview].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "\n")
                cards.append(AtlasCard(
                    id: AtlasStore.stableID(namespace: "run", key: run.runId),
                    title: "\(run.displayName.isEmpty ? run.agent : run.displayName) · \(run.status)",
                    summary: detail.isEmpty ? "No preview supplied." : clipped(detail, to: 700),
                    source: run.model ?? run.runId, group: "Runs", kind: .run,
                    metadata: ["run_id": run.runId]))
            }
        }
        let nodeCount = graph?.nodeCount ?? 0
        let edgeCount = graph?.edgeCount ?? 0
        cards.append(AtlasCard(
            id: AtlasStore.stableID(namespace: "memoryGraph", key: "summary"),
            title: "Memory graph", summary: graph == nil
                ? "Graph not loaded in this session. Open Memory graph to load it."
                : "\(nodeCount) nodes · \(edgeCount) edges · depth \(graph?.depth ?? 0)",
            source: "WorkspaceStore.memoryGraph", group: "Memory", kind: .memoryGraph,
            metadata: ["loaded": String(graph != nil), "nodes": String(nodeCount), "edges": String(edgeCount)]))
        return cards
    }

    private static func clipped(_ value: String, to limit: Int) -> String {
        let cleaned = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard cleaned.count > limit else { return cleaned }
        return String(cleaned.prefix(limit)) + "…"
    }
}
