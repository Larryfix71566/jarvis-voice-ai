import SwiftUI
import Observation
import JarvisKit

/// APP plan §3 P5, §5 step 9 — the Runs tab: the PERSISTED run history
/// from /api/runs (the Agents tab is the live stream — two surfaces, two
/// sources, §11 item 4). Polls every runsPollSeconds (5 s — new
/// behavior, not web parity; F5). Row: agent, task, status colour,
/// latency, model chip (model ?? "—"), and toolsOk/toolsFailed as
/// "ok/failed" when both non-nil, falling back to toolCount (F3 — the
/// web's exact fallback). Satellite-click pre-filter via
/// AgentRunStore.consumeRequestedAgentFilter (E5).
/// RunsPanel.tsx STATUSES — the run-status taxonomy (D9).
let RUN_STATUSES = ["ok", "failed", "timeout", "running", "orphaned"]

@MainActor
@Observable
final class RunsViewModel {
    private(set) var api: AdminAPI
    var state: TabState<[RunSummary]> = .loading
    /// Filters passed server-side as ?agent=&status= (RunsPanel.tsx:111-116).
    var agentFilter: String? { didSet { if agentFilter != oldValue { refreshSoon() } } }
    var statusFilter: String? { didSet { if statusFilter != oldValue { refreshSoon() } } }
    var detail: RunDetail?
    var detailRunId: String?
    private(set) var detailError: String?
    @ObservationIgnored private var listGeneration = 0
    @ObservationIgnored private var detailGeneration = 0
    @ObservationIgnored private var filterTask: Task<Void, Never>?
    @ObservationIgnored private var detailTask: Task<Void, Never>?
    @ObservationIgnored private let fetchList: @Sendable (AdminAPI, String?, String?) async throws -> RunsList
    @ObservationIgnored private let fetchDetail: @Sendable (AdminAPI, String) async throws -> RunDetail
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    private func refreshSoon() {
        listGeneration += 1
        filterTask?.cancel()
        state = .loading
        filterTask = Task { [weak self] in await self?.refresh() }
    }

    init(api: AdminAPI,
         fetchList: @escaping @Sendable (AdminAPI, String?, String?) async throws -> RunsList = { api, agent, status in
             try await api.runsTyped(agent: agent, status: status)
         },
         fetchDetail: @escaping @Sendable (AdminAPI, String) async throws -> RunDetail = { api, id in
             try await api.runTyped(id: id)
         }) {
        self.api = api; self.fetchList = fetchList; self.fetchDetail = fetchDetail
    }

    func updateAPI(_ api: AdminAPI) {
        stopPolling()
        self.api = api
        stopped = false
        detailGeneration += 1; detailTask?.cancel(); detailTask = nil
        if let id = detailRunId { loadDetail(runId: id, force: true) }
    }

    func startPolling() {
        guard pollTask == nil, !stopped else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                if self?.stopped == true { return }
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.runsPollSeconds * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        listGeneration += 1
        filterTask?.cancel(); filterTask = nil
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        guard !Task.isCancelled else { return }
        listGeneration += 1
        let generation = listGeneration
        let agent = agentFilter, status = statusFilter, api = api
        do {
            let list = try await fetchList(api, agent, status)
            guard !Task.isCancelled, generation == listGeneration,
                  agent == agentFilter, status == statusFilter else { return }
            state = TabStateMapper.map(ok: list.ok, error: nil, isEmpty: list.runs.isEmpty, value: list.runs)
        } catch {
            guard !Task.isCancelled, generation == listGeneration,
                  agent == agentFilter, status == statusFilter else { return }
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }
        }
    }

    func loadDetail(runId: String, force: Bool = false) {
        detailGeneration += 1
        detailTask?.cancel(); detailTask = nil
        detailError = nil
        if detailRunId == runId && !force { detailRunId = nil; detail = nil; return }
        detailRunId = runId; detail = nil
        let generation = detailGeneration, api = api, fetch = fetchDetail
        detailTask = Task { [weak self] in
            do {
                let response = try await fetch(api, runId)
                guard !Task.isCancelled, let self, self.detailGeneration == generation,
                      self.detailRunId == runId else { return }
                self.detail = response; self.detailTask = nil
            } catch {
                guard !Task.isCancelled, let self, self.detailGeneration == generation,
                      self.detailRunId == runId else { return }
                self.detailError = TabStateMapper.fromError(error).0
                self.detailTask = nil
            }
        }
    }

}

struct RunsTab: View {
    @Bindable var model: RunsViewModel
    @Environment(AgentRunStore.self) private var agentRuns

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("RUNS")
                    .font(.system(size: 10, design: .monospaced))
                    .kerning(2.0)
                    .foregroundStyle(AppTheme.textDim)
                // The web's filter row (RunsPanel.tsx:162-186): agent +
                // status selects (server-side params) and a ↻ refresh.
                HStack(spacing: 8) {
                    Picker("", selection: Binding(
                        get: { model.agentFilter ?? "" },
                        set: { model.agentFilter = $0.isEmpty ? nil : $0 }
                    )) {
                        Text("all agents").tag("")
                        ForEach(AGENT_LAYOUT, id: \.key) { agent in
                            Text(agent.label).tag(agent.key)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: 130)
                    Picker("", selection: Binding(
                        get: { model.statusFilter ?? "" },
                        set: { model.statusFilter = $0.isEmpty ? nil : $0 }
                    )) {
                        Text("all statuses").tag("")
                        ForEach(RUN_STATUSES, id: \.self) { status in
                            Text(status).tag(status)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: 130)
                    Button("↻") { Task { await model.refresh() } }
                        .buttonStyle(.plain)
                        .foregroundStyle(AppTheme.textDim)
                        .help("Refresh")
                    Spacer()
                }
                switch model.state {
                case .loading:
                    Text("loading…").foregroundStyle(AppTheme.textDim).font(.caption)
                case .empty:
                    Text("No runs yet — try \"check how my computer is doing\".")
                        .foregroundStyle(AppTheme.textDim)
                case .error(let message):
                    Text(message).foregroundStyle(AppTheme.red)
                case .loaded(let runs):
                    ForEach(runs, id: \.runId) { run in
                        row(run)
                        if model.detailRunId == run.runId {
                            detailView
                        }
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .preserveDrawerScroll("runs")
        .task {
            // E5: a satellite click while this tab was unmounted must be
            // readable at the next mount.
            if let requested = agentRuns.consumeRequestedAgentFilter() {
                model.agentFilter = requested
            }
        }
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "ok": return AppTheme.green
        case "running": return AppTheme.accent
        case "failed", "timeout", "orphaned": return AppTheme.red
        default: return AppTheme.textDim
        }
    }

    private func row(_ run: RunSummary) -> some View {
        Button {
            model.loadDetail(runId: run.runId)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Circle().fill(statusColor(run.status)).frame(width: 8, height: 8)
                    Text(run.displayName.isEmpty ? run.agent : run.displayName)
                        .font(.callout.weight(.medium))
                    // F3 — the model chip; full string in help.
                    Text(run.model.map { shortModel($0) } ?? "—")
                        .font(.caption2)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .mortimerGlass(.chip)
                        .help(run.model ?? "model unknown")
                    Spacer()
                    if let latency = run.latencyMs {
                        Text("\(latency) ms").font(.caption2).foregroundStyle(AppTheme.textDim)
                    }
                    // F3 — ok/failed readout, toolCount fallback (the
                    // web's exact rule).
                    if let ok = run.toolsOk, let failed = run.toolsFailed {
                        Text("\(ok)/\(failed)").font(.caption2)
                            .foregroundStyle(failed > 0 ? AppTheme.amber : AppTheme.textDim)
                    } else {
                        Text("\(run.toolCount) tools").font(.caption2).foregroundStyle(AppTheme.textDim)
                    }
                }
                Text(run.task).font(.caption).foregroundStyle(AppTheme.textDim).lineLimit(2)
                if let error = run.error, !error.isEmpty {
                    Text(error).font(.caption2).foregroundStyle(AppTheme.red).lineLimit(2)
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .mortimerGlass(.card)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var detailView: some View {
        if let error = model.detailError {
            Text(error).foregroundStyle(AppTheme.red).font(.caption)
            if let id = model.detailRunId {
                Button("Retry details") { model.loadDetail(runId: id, force: true) }
            }
        } else if let detail = model.detail {
            if let error = detail.error {
                Text(error).foregroundStyle(AppTheme.red).font(.caption)
            }
            if let events = detail.events, !events.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(events, id: \.id) { event in
                        HStack(spacing: 6) {
                            Text(event.type).font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(AppTheme.textDim)
                            if let tool = event.tool {
                                Text(tool).font(.system(.caption2, design: .monospaced))
                            }
                            // ok is Int? (1|0|NULL) — NOT a Bool (P5).
                            if let ok = event.ok {
                                Image(systemName: ok == 1 ? "checkmark" : "xmark")
                                    .font(.caption2)
                                    .foregroundStyle(ok == 1 ? AppTheme.green : AppTheme.red)
                            }
                            Spacer()
                            if let latency = event.latencyMs {
                                Text("\(latency) ms").font(.caption2).foregroundStyle(AppTheme.textDim)
                            }
                        }
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.panel.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
            }
            if let payload = detail.payload {
                Text("\(payload.count) payload entries")
                    .font(.caption2).foregroundStyle(AppTheme.textDim)
            }
        } else {
            ProgressView().controlSize(.small)
        }
    }
}
