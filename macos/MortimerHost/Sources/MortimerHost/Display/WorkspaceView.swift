import SwiftUI
import JarvisKit

/// Central results share the existing renderer and never invoke tools.
struct WorkspaceView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @State private var pinLimitNotice = false
    @State private var showComparisonOnCompact = false

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Button("Conversation") { workspace.returnToConversation() }
                Button("Memory graph") { workspace.openMemoryGraph() }
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
                MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
            } else if let active = workspace.activeResult {
                GeometryReader { geometry in
                    if let comparison = workspace.comparisonResult {
                        if geometry.size.width >= 960 {
                            HStack(spacing: 16) {
                                resultPane(active)
                                Divider()
                                resultPane(comparison)
                            }
                        } else {
                            VStack {
                                Picker("Comparison pane", selection: $showComparisonOnCompact) {
                                    Text("A: \(active.payload.title ?? "Result")").tag(false)
                                    Text("B: \(comparison.payload.title ?? "Result")").tag(true)
                                }.pickerStyle(.segmented)
                                resultPane(showComparisonOnCompact ? comparison : active)
                            }
                        }
                    } else { resultPane(active) }
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

    private func resultPane(_ result: WorkspaceResult) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(result.payload.title ?? "Result").font(.headline)
            if let url = MemoryGraphSource.imageURL(result.payload) {
                let graphStore = workspace.graphStore(for: result, url: url)
                Button(graphStore.showsOriginalResult ? "Interactive graph" : "Original result and sources") {
                    graphStore.showsOriginalResult.toggle()
                }
                if graphStore.showsOriginalResult {
                    DisplayContentView(payload: result.payload,
                        restoredScrollOffset: workspace.scrollOffsets[result.id],
                        onScrollOffset: { workspace.rememberScroll($0, for: result.id) })
                } else {
                    if let body = result.payload.body { Text(body).font(.caption).textSelection(.enabled) }
                    MemoryGraphView(store: graphStore, api: client.admin, fallbackURL: url)
                }
            } else {
                DisplayContentView(payload: result.payload,
                    restoredScrollOffset: workspace.scrollOffsets[result.id],
                    onScrollOffset: { workspace.rememberScroll($0, for: result.id) })
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .id(result.id)
    }
}
