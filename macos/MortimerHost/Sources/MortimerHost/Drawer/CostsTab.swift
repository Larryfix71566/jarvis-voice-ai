import SwiftUI
import Observation
import Charts
import JarvisKit

/// MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9 — the costs dashboard
/// card. Adapted from the plan's own CostDashboardView.swift draft
/// (docs/plans/optimization_rev3_files/CostDashboardView.swift) onto
/// this app's actual conventions rather than dropped in verbatim: the
/// draft was a standalone ObservableObject hitting URLSession directly
/// with its own hardcoded baseURL — here it follows RunsTab.swift's
/// established ViewModel/TabState/AppTheme/mortimerGlass pattern instead,
/// and reads its base URL from JarvisConfig.costsURL (JARVIS_COSTS_URL
/// override, default http://127.0.0.1:8487) like every other service
/// this app talks to.
///
/// Wired into DrawerView's tab strip as the eighth tab (Larry's go-ahead,
/// 2026-09-01) — DrawerState.tabKeys/tabLabels, DrawerView's
/// buildModelsOnce/activeBody switch, and jarvis/bot/ui_control.py's
/// UI_TABS were all updated together in the same commit so voice
/// ("open the costs tab") and click can never diverge (C5).
@MainActor
@Observable
final class CostsViewModel {
    private(set) var api: CostsAPI
    var state: TabState<CostSummary> = .loading
    var daily: [DailyCost] = []
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: CostsAPI) { self.api = api }

    func updateAPI(_ api: CostsAPI) {
        stopPolling()
        self.api = api
        stopped = false
    }

    func startPolling() {
        guard pollTask == nil, !stopped else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                if self?.stopped == true { return }
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.costsPollSeconds * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        do {
            async let s = api.summary()
            async let d = api.daily()
            let summary = try await s
            guard !Task.isCancelled else { return }
            let dailyResp = try await d
            guard !Task.isCancelled else { return }
            daily = dailyResp.daily
            state = TabStateMapper.map(ok: true, error: nil, isEmpty: summary.calls == 0, value: summary)
        } catch {
            guard !Task.isCancelled else { return }
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }
        }
    }
}

struct CostsTab: View {
    @Bindable var model: CostsViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("COSTS")
                    .font(.system(size: 10, design: .monospaced))
                    .kerning(2.0)
                    .foregroundStyle(AppTheme.textDim)
                switch model.state {
                case .loading:
                    Text("loading…").foregroundStyle(AppTheme.textDim).font(.caption)
                case .empty:
                    Text("No model spend recorded this month yet.")
                        .foregroundStyle(AppTheme.textDim)
                case .error(let message):
                    Text(message).foregroundStyle(AppTheme.red)
                case .loaded(let summary):
                    header(summary)
                    if !model.daily.isEmpty { sparkline }
                    if summary.budgetUsd > 0 { budgetBar(summary) }
                    rungBreakdown(summary)
                    if summary.unpricedCalls > 0 {
                        Label("\(summary.unpricedCalls) calls unpriced — update config/model_prices.yaml",
                              systemImage: "exclamationmark.triangle")
                            .font(.caption2)
                            .foregroundStyle(AppTheme.amber)
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .preserveDrawerScroll("costs")
    }

    private func header(_ s: CostSummary) -> some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Model spend").font(.callout.weight(.medium)).foregroundStyle(AppTheme.text)
                Text(s.month).font(.caption2).foregroundStyle(AppTheme.textDim)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(s.totalUsd, format: .currency(code: "USD"))
                    .font(.title3.weight(.semibold)).monospacedDigit()
                    .foregroundStyle(AppTheme.text)
                Text("→ \(s.projectedUsd, format: .currency(code: "USD")) proj.")
                    .font(.caption2).foregroundStyle(AppTheme.textDim)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .mortimerGlass(.card)
    }

    private var sparkline: some View {
        Chart(model.daily) { d in
            BarMark(
                x: .value("Day", String(d.day.suffix(2))),
                y: .value("USD", d.usd)
            )
            .foregroundStyle(AppTheme.accent)
        }
        .chartYAxis(.hidden)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 6)) {
                AxisValueLabel().font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(AppTheme.textDim)
            }
        }
        .frame(height: 64)
        .padding(10)
        .mortimerGlass(.card)
    }

    private func budgetBar(_ s: CostSummary) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ProgressView(value: min(s.budgetUsedPct / 100.0, 1.0))
                .tint(s.budgetUsedPct >= 100 ? AppTheme.red :
                      s.budgetUsedPct >= 80 ? AppTheme.amber : AppTheme.accent)
            Text("\(Int(s.budgetUsedPct))% of \(s.budgetUsd, format: .currency(code: "USD")) budget")
                .font(.caption2).foregroundStyle(AppTheme.textDim)
        }
        .padding(10)
        .mortimerGlass(.card)
    }

    private func rungBreakdown(_ s: CostSummary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(s.byRung.prefix(6)) { r in
                HStack {
                    Text(r.rung).font(.caption).foregroundStyle(AppTheme.text)
                    Spacer()
                    Text(r.usd, format: .currency(code: "USD"))
                        .font(.caption).monospacedDigit()
                        .foregroundStyle(AppTheme.textDim)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .mortimerGlass(.card)
    }
}
