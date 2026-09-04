import SwiftUI
import JarvisKit

/// APP plan §3 P15, §5 step 6 — the tab strip + active tab body; the
/// DrawerScene body and the console's docked drawer share it. The eight
/// keys/labels are load-bearing (SideDrawer.tsx / ui_control.py aliases)
/// and are owned by DrawerState. View-models are owned HERE (the scene),
/// not by the tab views — a tab view unmounting on switch must not
/// restart its poll or lose a half-finished draft (P6). "costs" added
/// 2026-09-01 (MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9).
struct DrawerView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(DrawerState.self) private var drawer
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(ConversationStore.self) private var conversation

    @State private var repoModel: RepoViewModel?
    @State private var editModel: EditViewModel?
    @State private var memoryModel: MemoryViewModel?
    @State private var runsModel: RunsViewModel?
    @State private var costsModel: CostsViewModel?
    /// Interface Task — the council roster under the Agents tab's runs.
    @State private var councilModel: CouncilViewModel?

    var body: some View {
        VStack(spacing: 0) {
            tabStrip
            Divider().overlay(AppTheme.hairline)
            activeBody
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .mortimerGlass(.drawer)
        .padding(8)
        .foregroundStyle(AppTheme.text)
        .onAppear(perform: buildModelsOnce)
    }

    private func buildModelsOnce() {
        if repoModel == nil { repoModel = RepoViewModel(api: client.admin) }
        if editModel == nil { editModel = EditViewModel(api: client.admin) }
        if memoryModel == nil { memoryModel = MemoryViewModel(api: client.admin) }
        if runsModel == nil { runsModel = RunsViewModel(api: client.admin) }
        if costsModel == nil { costsModel = CostsViewModel(api: client.costs) }
        if councilModel == nil { councilModel = CouncilViewModel(api: client.admin) }
    }

    /// The tab strip (SideDrawer.tsx:255-292, parity sweep 2026-08-30):
    /// mono uppercase tabs, per-tab attention dots (Agents — live
    /// self-edit; Output — new result, amber when the newest is a
    /// pending draft), then ⧉ pop-out and × close chrome controls.
    private var tabStrip: some View {
        HStack(spacing: 2) {
            ForEach(DrawerState.tabKeys, id: \.self) { key in
                Button {
                    drawer.setTab(key)   // the SAME setter drawer_tab calls (C5)
                } label: {
                    HStack(spacing: 6) {
                        Text((DrawerState.tabLabels[key] ?? key).uppercased())
                            .font(.system(size: 10, design: .monospaced))
                            .kerning(1.2)
                        if let dotColor = tabDot(key) {
                            Circle()
                                .fill(dotColor)
                                .frame(width: 6, height: 6)
                                .shadow(color: dotColor, radius: 4)
                        }
                    }
                    .padding(.horizontal, 9)
                    .padding(.vertical, 5)
                    .overlay(
                        RoundedRectangle(cornerRadius: 2)
                            .strokeBorder(drawer.activeTab == key ? AppTheme.accentDim : .clear,
                                          lineWidth: 1)
                    )
                    .foregroundStyle(drawer.activeTab == key ? AppTheme.accent : AppTheme.textDim)
                }
                .buttonStyle(.plain)
            }
            Spacer()
            if !drawer.isPoppedOut {
                Button {
                    drawer.placementRef?.popOutDrawer()   // same call drawer_popout makes
                } label: {
                    Text("⧉")
                        .font(.system(size: 13, design: .monospaced))
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textDim)
                .help("Pop the panels out to their own window")
                Button {
                    drawer.isOpen = false
                } label: {
                    Text("×")
                        .font(.system(size: 15, design: .monospaced))
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textDim)
                .padding(.leading, 4)
                .help("Close the panels")
            }
        }
        .padding(8)
    }

    /// D7/E1 — the per-tab dots: Agents pulses cyan while a self-edit is
    /// in flight; Output shows cyan for a new result, amber (attention)
    /// while the newest result is a pending draft confirmation.
    private func tabDot(_ key: String) -> Color? {
        switch key {
        case "agents" where agentRuns.selfEditRunning:
            return AppTheme.accent
        case "output" where drawer.outputDot || displayResults.hasPendingDraft:
            return displayResults.hasPendingDraft ? AppTheme.attn : AppTheme.accent
        default:
            return nil
        }
    }

    @ViewBuilder
    private var activeBody: some View {
        switch drawer.activeTab {
        case "repo":
            if let repoModel { RepoTab(model: repoModel) }
        case "edit":
            if let editModel { EditTab(model: editModel) }
        case "memory":
            if let memoryModel { MemoryTab(model: memoryModel) }
        case "runs":
            if let runsModel { RunsTab(model: runsModel) }
        case "agents":
            AgentsTab(council: councilModel)
        case "output":
            OutputTab()
        case "transcript":
            LogTab()
        case "costs":
            if let costsModel { CostsTab(model: costsModel) }
        default:
            EmptyView()
        }
    }
}
