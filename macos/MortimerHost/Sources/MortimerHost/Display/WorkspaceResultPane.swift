import SwiftUI
import JarvisKit

/// Reparented between main and supporting windows; data, graph and scroll state
/// remain app-owned. The main pane yields while its supporting renderer is live.
struct WorkspaceResultPane: View {
    let result: WorkspaceResult
    var onSupportingDisplay = false
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(result.payload.title ?? "Result").font(.headline)
            if !onSupportingDisplay && display.isWindowOpen && workspace.supportingContent == .result(result.id) {
                ContentUnavailableView {
                    Label("On the supporting display", systemImage: "display")
                } actions: {
                    Button("Return here") { drawer.placementRef?.closeDisplay() }
                }
            } else if let url = MemoryGraphSource.imageURL(result.payload) {
                let graphStore = workspace.graphStore(for: result, url: url)
                Button(graphStore.showsOriginalResult ? "Interactive graph" : "Original result and sources") {
                    graphStore.showsOriginalResult.toggle()
                }
                if graphStore.showsOriginalResult { original }
                else {
                    if let body = result.payload.body { Text(body).font(.caption).textSelection(.enabled) }
                    MemoryGraphView(store: graphStore, api: client.admin)
                }
            } else { original }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .id(result.id)
    }

    private var original: some View {
        DisplayContentView(payload: result.payload, restoredScrollOffset: workspace.scrollOffsets[result.id],
                           onScrollOffset: { workspace.rememberScroll($0, for: result.id) })
    }
}
