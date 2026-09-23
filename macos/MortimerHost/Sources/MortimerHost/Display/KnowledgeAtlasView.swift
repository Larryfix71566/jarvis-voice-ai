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
    @EnvironmentObject private var client: JarvisClient
    @State private var contextTask: Task<Void, Never>?
    private let columns = [GridItem(.adaptive(minimum: 260, maximum: 360), spacing: 20)]

    init(coordinator: ConsoleActionCoordinator? = nil) {
        self.coordinator = coordinator
    }

    var body: some View {
        ScrollView {
            if atlas.cards.isEmpty {
                ContentUnavailableView("Atlas is empty", systemImage: "square.grid.2x2",
                    description: Text("Research, memory, architecture and plan context will appear here."))
            } else {
                LazyVGrid(columns: columns, alignment: .leading, spacing: 20) {
                    ForEach(atlas.visibleCards) { card in
                        Button {
                            guard card.kind == .result else { return }
                            if let coordinator {
                                _ = coordinator.executePointer(.resultSelect, target: card.id.uuidString)
                            } else {
                                workspace.select(card.id)
                            }
                        } label: {
                            AtlasCardView(card: card, selected: workspace.activeID == card.id)
                        }
                        .buttonStyle(.plain)
                        .disabled(card.kind != .result)
                        .accessibilityLabel(card.kind == .result
                            ? "Open atlas result \(card.title)"
                            : "Atlas \(card.kind.label): \(card.title)")
                    }
                }
            }
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
            contextTask?.cancel()
            contextTask = nil
        }
        .onChange(of: workspace.results) { _, _ in syncResults() }
    }

    private func syncResults() {
        atlas.replaceResults(workspace.results.map { result in
            AtlasCard(id: result.id, title: result.payload.title ?? "Result",
                      summary: result.payload.body ?? "No preview supplied",
                      source: result.payload.links?.first?.url, group: nil,
                      kind: .result)
        })
    }

    private func refreshContext() {
        contextTask?.cancel()
        let api = client.admin
        contextTask = Task { @MainActor in
            async let memory = api.memoryOverview()
            async let architecture = api.architectureReference()
            async let plan = api.planJob()
            async let runs = api.runsTyped()
            let context = Self.contextCards(
                memory: try? await memory,
                architecture: try? await architecture,
                plan: try? await plan,
                runs: try? await runs,
                graph: workspace.memoryGraph.graph)
            guard !Task.isCancelled else { return }
            atlas.replaceContext(context)
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
