import SwiftUI
import JarvisKit

enum AgentsTabSections {
    struct Split: Equatable {
        let current: [AgentRun]
        let history: [AgentRun]
    }
    static let historyExpandedKey = "mortimer.drawer.agentsHistoryExpanded"
    static let emptyCurrent = "No agent is working right now."

    /// Current: unfinished runs newest first, plus the focused run even if it
    /// has since finished, focused run first. History: every other run, newest first.
    static func split(runs: [AgentRun], focusedRunID: Int?) -> Split {
        let newestFirst = Array(runs.reversed())
        var current = newestFirst.filter { $0.doneAt == nil || $0.id == focusedRunID }
        if let focusedRunID, let index = current.firstIndex(where: { $0.id == focusedRunID }), index > 0 {
            current.insert(current.remove(at: index), at: 0)
        }
        let shown = Set(current.map(\.id))
        return Split(current: current, history: newestFirst.filter { !shown.contains($0.id) })
    }

    static func historyTitle(runCount: Int) -> String {
        switch runCount {
        case 0: return "HISTORY"
        case 1: return "HISTORY · 1 RUN"
        default: return "HISTORY · \(runCount) RUNS"
        }
    }
}

/// APP plan §3 P8, §5 step 10 — the Agents tab: LIVE sub-agent progress
/// from AgentRunStore (the message stream), newest last per the store's
/// oldest-first order, rendered newest-first here. Registers NO stream
/// consumer — it only reads its store (the single-listener rule).
///
/// Below the live runs, MORTIMER_OPTIMIZATION_PLAN.md's Interface Task
/// adds the council roster (CouncilRosterView.swift). That section is
/// HTTP-polled rather than stream-fed, which does not breach the
/// single-listener rule — it registers no stream consumer either — and
/// its view-model is owned by DrawerView like every other polling tab's
/// (P6: a tab view unmounting on switch must not restart its poll).
struct AgentsTab: View {
    @Environment(AgentRunStore.self) private var agentRuns
    /// Optional so the live runs still render during the one frame
    /// before DrawerView's buildModelsOnce has run.
    let council: CouncilViewModel?

    @Environment(DrawerState.self) private var drawer: DrawerState?
    @AppStorage(AgentsTabSections.historyExpandedKey) private var historyExpanded = false
    private static let topID = "agents-current-top"

    var body: some View {
        let split = AgentsTabSections.split(runs: agentRuns.runs, focusedRunID: drawer?.focusedRunID)
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    sectionTitle("CURRENT RUN").id(Self.topID)
                    if split.current.isEmpty {
                        Text(AgentsTabSections.emptyCurrent).foregroundStyle(AppTheme.textDim)
                    } else {
                        ForEach(split.current) { run in card(run) }
                    }
                    Divider().overlay(AppTheme.hairline).padding(.vertical, 2)
                    historyToggle(runCount: split.history.count)
                    if historyExpanded {
                        ForEach(split.history) { run in card(run) }
                        if let drawer {
                            Button("All runs") { drawer.setTab("runs") }
                                .buttonStyle(.plain).font(.caption).foregroundStyle(AppTheme.textDim)
                                .accessibilityHint("Opens the Runs tab")
                        }
                        if let council { CouncilRosterSection(model: council) }
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .preserveDrawerScroll("agents")
            .onChange(of: drawer?.runFocusRequest) { _, _ in scrollToCurrent(proxy) }
            .task { scrollToCurrent(proxy) }
        }
    }

    private func scrollToCurrent(_ proxy: ScrollViewProxy) {
        guard drawer?.consumeRunFocusScroll() == true else { return }
        proxy.scrollTo(Self.topID, anchor: .top)   // a cut, so Reduce Motion needs no branch
    }

    private func sectionTitle(_ text: String) -> some View {
        Text(text).font(.system(size: 10, design: .monospaced)).kerning(2.0)
            .foregroundStyle(AppTheme.textDim)
    }

    private func historyToggle(runCount: Int) -> some View {
        Button { historyExpanded.toggle() } label: {
            HStack(spacing: 6) {
                Image(systemName: historyExpanded ? "chevron.down" : "chevron.right")
                    .font(.caption2).accessibilityHidden(true)
                Text(AgentsTabSections.historyTitle(runCount: runCount))
                    .font(.system(size: 10, design: .monospaced)).kerning(2.0)
                Spacer()
            }
            .foregroundStyle(AppTheme.textDim)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("History")
        .accessibilityValue(historyExpanded ? "Expanded" : "Collapsed")
        .accessibilityHint("Shows earlier runs and council rounds")
        .accessibilityIdentifier("agents.history")
    }

    private func card(_ run: AgentRun) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(run.displayName).font(.callout.weight(.semibold))
                if !run.model.isEmpty {
                    // Model chip with fallback/unusable colour (K4).
                    Text(shortModel(run.model))
                        .font(.caption2)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .foregroundStyle(run.modelUnusable ? AppTheme.red
                                         : (run.modelFallback ? AppTheme.amber : AppTheme.textDim))
                        .mortimerGlass(.chip)
                        .help(run.modelUnusable ? run.modelUnusableDetail : run.model)
                }
                if !run.plannerModel.isEmpty {
                    Text("planner: \(shortModel(run.plannerModel))")
                        .font(.caption2).foregroundStyle(AppTheme.accent)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .mortimerGlass(.chip)
                        .help(run.plannerModel)
                }
                Spacer()
                if run.doneAt == nil {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: run.ok ? "checkmark.circle" : "xmark.circle")
                        .foregroundStyle(run.ok ? AppTheme.green : AppTheme.red)
                }
            }

            if !run.task.isEmpty {
                Text(run.task).font(.caption).foregroundStyle(AppTheme.textDim)
            }

            // Self-edit stage dots.
            if isSelfEditRun(name: run.name, tools: run.tools) {
                HStack(spacing: 6) {
                    ForEach(Array(RUN_STAGES.enumerated()), id: \.offset) { index, stage in
                        Text(stage)
                            .font(.caption2)
                            .foregroundStyle(index <= run.stage ? AppTheme.accent : AppTheme.textDim.opacity(0.5))
                    }
                }
            }

            // The activity ticker — one line per finished tool call,
            // every line a recorded fact (never a model narrating itself).
            if !run.activity.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(run.activity.enumerated()), id: \.offset) { _, line in
                            HStack(spacing: 6) {
                                Image(systemName: line.ok ? "circle.fill" : "xmark")
                                    .font(.system(size: 5))
                                    .foregroundStyle(line.ok ? AppTheme.green : AppTheme.red)
                                Text(line.tool).font(.system(.caption2, design: .monospaced))
                                Spacer()
                                Text("\(line.latencyMs) ms")
                                    .font(.caption2).foregroundStyle(AppTheme.textDim)
                            }
                        }
                    }
                }
                .frame(maxHeight: 120)
            }

            if run.doneAt != nil && !run.ok && !run.detail.isEmpty {
                Text(run.detail).font(.caption).foregroundStyle(AppTheme.red)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .mortimerGlass(.card)
    }
}
