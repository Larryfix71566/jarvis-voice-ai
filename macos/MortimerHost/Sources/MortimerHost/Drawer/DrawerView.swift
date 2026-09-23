import SwiftUI
import JarvisKit

/// APP plan §3 P15, §5 step 6 — the tab strip + active tab body; the
/// DrawerScene body and the console's docked drawer share it. The eight
/// keys/labels are load-bearing (SideDrawer.tsx / ui_control.py aliases)
/// and are owned by DrawerState. View-models are owned by app-scoped DrawerModels,
/// not by the tab views — a tab view unmounting on switch must not
/// restart its poll or lose a half-finished draft (P6). "costs" added
/// 2026-09-01 (MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9).
struct DrawerView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(DrawerState.self) private var drawer
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(ConversationStore.self) private var conversation

    @Environment(DrawerModels.self) private var models
    @State private var visibilityLease = UUID()
    @AppStorage("mortimer.interface.sidecarTabTextSize") private var tabTextSize = 11.0

    var body: some View {
        VStack(spacing: 0) {
            tabStrip
            Divider().overlay(AppTheme.hairline)
            activeBody
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .mortimerGlass(.drawer)
        // Docked: no leading inset — ConsoleView's resize grip
        // (AppTuning.drawerHandleWidth) IS the gap, so the grip sits on
        // the glass edge instead of 8pt into the background (2026-09-05).
        // Popped out into its own window: the full 8pt all round, as before.
        .padding(.top, 8)
        .padding(.bottom, 8)
        .padding(.trailing, 8)
        .padding(.leading, drawer.isPoppedOut ? 8 : 0)
        .foregroundStyle(AppTheme.text)
        .onAppear {
            models.configure(client.config)
            models.acquire(visibilityLease, tab: drawer.activeTab)
        }
        .onChange(of: drawer.activeTab) { _, tab in models.acquire(visibilityLease, tab: tab) }
        .onChange(of: client.state) { _, _ in models.configure(client.config) }
        .onDisappear { models.release(visibilityLease) }
    }

    /// The tab strip (SideDrawer.tsx:255-292, parity sweep 2026-08-30):
    /// mono uppercase tabs, per-tab attention dots (Agents — live
    /// self-edit; Output — new result, amber when the newest is a
    /// pending draft), then ⧉ pop-out and × close chrome controls.
    private var tabStrip: some View {
        HStack(spacing: 2) {
            DrawerTabStrip(selectedTab: drawer.activeTab,
                           attention: Dictionary(uniqueKeysWithValues: DrawerState.tabKeys.compactMap { key in
                               tabDot(key).map { (key, $0) }
                           }), select: drawer.setTab, textSize: tabTextSize,
                           scrollRequest: drawer.tabScrollRequest,
                           scrollDirection: drawer.tabScrollDirection)
            Menu {
                // Use direct menu actions rather than a nested Picker. On
                // macOS a Picker inside Menu becomes a hover submenu; moving
                // from the Aa button into that submenu can dismiss it before
                // a size is selectable. Direct actions keep the menu open
                // until the user clicks or presses a size.
                tabTextSizeItem("Standard", value: 11)
                tabTextSizeItem("Large", value: 16)
                tabTextSizeItem("Extra large", value: 22)
            } label: {
                Text("Aa").font(.system(size: 13))
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .accessibilityLabel("Sidecar tab text size")
            .accessibilityValue(tabTextSizeDescription)
            .help("Change the size of sidecar tab names")
            // Keep a concrete AX text node present even when Menu has not yet
            // materialized its popup; rendering fixtures use this to verify
            // the control remains reachable at minimum widths.
            Text(tabTextSizeDescription)
                .font(.system(size: 1))
                .opacity(0.01)
                .accessibilityLabel("Sidecar tab text size")
                .accessibilityValue(tabTextSizeDescription)
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

    private var tabTextSizeDescription: String {
        switch tabTextSize {
        case 16: return "Large"
        case 22: return "Extra large"
        default: return "Standard"
        }
    }

    @ViewBuilder
    private func tabTextSizeItem(_ title: String, value: Double) -> some View {
        Button {
            tabTextSize = value
        } label: {
            HStack {
                Text(title)
                if tabTextSize == value {
                    Spacer()
                    Image(systemName: "checkmark")
                }
            }
        }
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
            if let repoModel = models.repo { RepoTab(model: repoModel) }
        case "edit":
            if let editModel = models.edit { EditTab(model: editModel) }
        case "memory":
            if let memoryModel = models.memory { MemoryTab(model: memoryModel) }
        case "runs":
            if let runsModel = models.runs { RunsTab(model: runsModel) }
        case "agents":
            AgentsTab(council: models.council)
        case "output":
            OutputTab()
        case "transcript":
            LogTab()
        case "costs":
            if let costsModel = models.costs { CostsTab(model: costsModel) }
        default:
            EmptyView()
        }
    }
}
