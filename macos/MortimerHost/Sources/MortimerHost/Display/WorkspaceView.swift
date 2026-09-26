import SwiftUI
import JarvisKit

/// Central results share the existing renderer and never invoke tools.
struct WorkspaceView: View {
    /// Optional for the legacy/adaptive layouts; layout 2 injects the
    /// app-scoped coordinator so result and view navigation share voice.
    let coordinator: ConsoleActionCoordinator?
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @State private var pinLimitNotice = false
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 2
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer

    init(coordinator: ConsoleActionCoordinator? = nil) {
        self.coordinator = coordinator
    }

    var body: some View {
        VStack(spacing: 12) {
            ViewThatFits(in: .horizontal) {
                HStack { navigationControls; Spacer(); resultControls }
                    .fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 8) {
                    HStack { navigationControls; Spacer(minLength: 0) }
                    HStack { resultControls; Spacer(minLength: 0) }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            ScrollView(.horizontal) {
                HStack {
                    ForEach(workspace.results) { result in
                        HStack(spacing: 6) {
                            Button {
                                if let coordinator {
                                    _ = coordinator.executePointer(.resultSelect, target: result.id.uuidString)
                                } else {
                                    workspace.select(result.id)
                                }
                            } label: {
                                HStack {
                                    if workspace.pinnedIDs.contains(result.id) { Image(systemName: "pin.fill") }
                                    Text(result.payload.title ?? "Result")
                                        .lineLimit(1)
                                    if workspace.unreadIDs.contains(result.id) { Image(systemName: "circle.fill").font(.system(size: 6)) }
                                }
                            }
                            .accessibilityAddTraits(workspace.activeID == result.id ? [.isSelected] : [])
                            Button {
                                if let coordinator {
                                    _ = coordinator.executePointer(.resultClose, target: result.id.uuidString)
                                } else {
                                    workspace.close(result.id)
                                }
                            } label: { Image(systemName: "xmark") }
                                .accessibilityLabel("Close \(result.payload.title ?? "result")")
                        }
                        .padding(8)
                        .background(workspace.activeID == result.id ? AppTheme.accent.opacity(0.15) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }
            }
            if workspace.showsMemoryGraph {
                if isOnSupportingDisplay(.memoryGraph) {
                    ContentUnavailableView {
                        Label("Memory graph is on the supporting display", systemImage: "display")
                    } actions: {
                        Button("Return here") { drawer.placementRef?.closeDisplay() }
                    }
                } else { MemoryGraphView(store: workspace.memoryGraph, api: client.admin, coordinator: coordinator) }
            } else if workspace.showsAtlas {
                KnowledgeAtlasView(coordinator: coordinator)
            } else if workspace.showsWorkflows {
                if isOnSupportingDisplay(.workflows) {
                    ContentUnavailableView {
                        Label("Workflows are on the supporting display", systemImage: "display")
                    } actions: {
                        Button("Return here") { drawer.placementRef?.closeDisplay() }
                    }
                } else { WorkflowsView(store: workspace.workflows, api: client.admin) }
            } else if let active = workspace.activeResult {
                GeometryReader { geometry in
                    if let comparison = workspace.comparisonResult {
                        if geometry.size.width >= AdaptiveLayoutMetrics.minimumComparisonWidth {
                            HStack(spacing: AdaptiveLayoutMetrics.comparisonSpacing) {
                                resultPane(active)
                                Divider()
                                resultPane(comparison)
                            }
                        } else {
                            VStack {
                                Picker("Comparison pane", selection: Binding(get: { workspace.showComparisonOnCompact }, set: { workspace.showComparisonOnCompact = $0 })) {
                                    Text("A: \(active.payload.title ?? "Result")").tag(false)
                                    Text("B: \(comparison.payload.title ?? "Result")").tag(true)
                                }.pickerStyle(.segmented)
                                resultPane(workspace.showComparisonOnCompact ? comparison : active)
                            }
                        }
                    } else { resultPane(active) }
                }
            } else {
                ContentUnavailableView("Results appear here", systemImage: "doc.text.magnifyingglass",
                    description: Text("Ask Mortimer to research something, or return to conversation."))
            }
        }
        .padding(AdaptiveLayoutMetrics.workspacePadding)
        .background(AppTheme.bg)
        // §7 / closure C2.3: entering or leaving comparison and the graph animate for 200 ms.
        .animation(AdaptiveTransition.animation(reduceMotion: reduceMotion), value: workspace.comparisonID)
        .animation(AdaptiveTransition.animation(reduceMotion: reduceMotion), value: workspace.showsMemoryGraph)
        .alert("Pin limit reached", isPresented: $pinLimitNotice) {
            Button("OK", role: .cancel) {}
        } message: { Text("Unpin a result before pinning another. Your existing pins are preserved.") }
    }

    @ViewBuilder
    private func resultPane(_ result: WorkspaceResult) -> some View {
        if isOnSupportingDisplay(.result(result.id)) {
            ContentUnavailableView {
                Label("Result is on the supporting display", systemImage: "display")
            } actions: {
                Button("Return here") { drawer.placementRef?.closeDisplay() }
            }
        } else {
            WorkspaceResultPane(result: result, coordinator: coordinator)
        }
    }

    private func isOnSupportingDisplay(_ content: SupportingDisplayContent) -> Bool {
        display.isPresented(content, selection: workspace.supportingContent,
                            layoutVersion: InterfaceLayoutVersion.resolve(layoutVersion))
    }

    @ViewBuilder
    private var navigationControls: some View {
        Button("Conversation") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "conversation") }
            else { workspace.returnToConversation() }
        }
        Button("Knowledge Atlas") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "atlas") }
            else { workspace.openAtlas() }
        }
        Button("Memory graph") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "memory") }
            else { workspace.openMemoryGraph() }
        }
        Button("Workflows") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "workflows") }
            else { workspace.openWorkflows() }
        }
        Menu("Display") {
            Button("Show memory graph") { sendToDisplay(.memoryGraph) }
            Button("Show workflows") { sendToDisplay(.workflows) }
            if let active = workspace.activeResult {
                Button("Show active result") { sendToDisplay(.result(active.id)) }
            }
            if let comparison = workspace.comparisonResult {
                Button("Show comparison result") { sendToDisplay(.result(comparison.id)) }
            }
            ForEach(workspace.results.filter { workspace.pinnedIDs.contains($0.id) }) { result in
                Button(result.payload.title ?? "Pinned result") { sendToDisplay(.result(result.id)) }
            }
            if display.isWindowOpen {
                Button("Return display content here") { drawer.placementRef?.closeDisplay() }
            }
        }
    }

    @ViewBuilder
    private var resultControls: some View {
        if let active = workspace.activeResult {
            Button(workspace.pinnedIDs.contains(active.id) ? "Unpin" : "Pin") {
                if let coordinator {
                    let action: ConsoleAction = workspace.pinnedIDs.contains(active.id) ? .resultUnpin : .resultPin
                    if coordinator.executePointer(action, target: active.id.uuidString) == .noop {
                        pinLimitNotice = true
                    }
                } else if workspace.pinnedIDs.contains(active.id) { workspace.unpin(active.id) }
                else { pinLimitNotice = !workspace.pin(active.id) }
            }
            Menu("Compare") {
                ForEach(workspace.results.filter { $0.id != active.id }) { result in
                    Button(result.payload.title ?? "Result") {
                        if let coordinator {
                            _ = coordinator.executePointer(.compareSet,
                                target: active.id.uuidString,
                                secondaryTarget: result.id.uuidString)
                        } else {
                            workspace.compare(with: result.id)
                        }
                    }
                }
                Button("End comparison") {
                    if let coordinator { _ = coordinator.executePointer(.compareEnd) }
                    else { workspace.compare(with: nil) }
                }
            }
        }
    }

    private func sendToDisplay(_ content: SupportingDisplayContent) {
        guard workspace.sendToDisplay(content) else { return }
        drawer.placementRef?.openDisplay()
    }
}
