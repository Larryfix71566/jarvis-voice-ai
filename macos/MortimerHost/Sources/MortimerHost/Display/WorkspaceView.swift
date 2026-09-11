import SwiftUI
import JarvisKit

/// Central results share the existing renderer and never invoke tools.
struct WorkspaceView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @State private var pinLimitNotice = false
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Button("Conversation") { workspace.returnToConversation() }
                Button("Memory graph") { workspace.openMemoryGraph() }
                Menu("Display") {
                    Button("Show memory graph") { sendToDisplay(.memoryGraph) }
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
                Spacer()
                if let active = workspace.activeResult {
                    Button(workspace.pinnedIDs.contains(active.id) ? "Unpin" : "Pin") {
                        if workspace.pinnedIDs.contains(active.id) { workspace.unpin(active.id) }
                        else { pinLimitNotice = !workspace.pin(active.id) }
                    }
                    Menu("Compare") {
                        ForEach(workspace.results.filter { $0.id != active.id }) { result in
                            Button(result.payload.title ?? "Result") { workspace.compare(with: result.id) }
                        }
                        Button("End comparison") { workspace.compare(with: nil) }
                    }
                }
            }
            ScrollView(.horizontal) {
                HStack {
                    ForEach(workspace.results) { result in
                        HStack(spacing: 6) {
                            Button {
                                workspace.select(result.id)
                            } label: {
                                HStack {
                                    if workspace.pinnedIDs.contains(result.id) { Image(systemName: "pin.fill") }
                                    Text(result.payload.title ?? "Result")
                                        .lineLimit(1)
                                    if workspace.unreadIDs.contains(result.id) { Image(systemName: "circle.fill").font(.system(size: 6)) }
                                }
                            }
                            .accessibilityAddTraits(workspace.activeID == result.id ? [.isSelected] : [])
                            Button { workspace.close(result.id) } label: { Image(systemName: "xmark") }
                                .accessibilityLabel("Close \(result.payload.title ?? "result")")
                        }
                        .padding(8)
                        .background(workspace.activeID == result.id ? AppTheme.accent.opacity(0.15) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }
            }
            if workspace.showsMemoryGraph {
                if display.isWindowOpen && workspace.supportingContent == .memoryGraph {
                    ContentUnavailableView {
                        Label("Memory graph is on the supporting display", systemImage: "display")
                    } actions: {
                        Button("Return here") { drawer.placementRef?.closeDisplay() }
                    }
                } else { MemoryGraphView(store: workspace.memoryGraph, api: client.admin) }
            } else if let active = workspace.activeResult {
                GeometryReader { geometry in
                    if let comparison = workspace.comparisonResult {
                        if geometry.size.width >= 960 {
                            HStack(spacing: 16) {
                                WorkspaceResultPane(result: active)
                                Divider()
                                WorkspaceResultPane(result: comparison)
                            }
                        } else {
                            VStack {
                                Picker("Comparison pane", selection: Binding(get: { workspace.showComparisonOnCompact }, set: { workspace.showComparisonOnCompact = $0 })) {
                                    Text("A: \(active.payload.title ?? "Result")").tag(false)
                                    Text("B: \(comparison.payload.title ?? "Result")").tag(true)
                                }.pickerStyle(.segmented)
                                WorkspaceResultPane(result: workspace.showComparisonOnCompact ? comparison : active)
                            }
                        }
                    } else { WorkspaceResultPane(result: active) }
                }
            } else {
                ContentUnavailableView("Results appear here", systemImage: "doc.text.magnifyingglass",
                    description: Text("Ask Mortimer to research something, or return to conversation."))
            }
        }
        .padding(16)
        .background(AppTheme.bg)
        .alert("Pin limit reached", isPresented: $pinLimitNotice) {
            Button("OK", role: .cancel) {}
        } message: { Text("Unpin a result before pinning another. Your existing pins are preserved.") }
    }

    private func sendToDisplay(_ content: SupportingDisplayContent) {
        guard workspace.sendToDisplay(content) else { return }
        drawer.placementRef?.openDisplay()
    }
}
