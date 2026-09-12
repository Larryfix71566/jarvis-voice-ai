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
        let presentation = workspace.presentation(for: result)
        VStack(alignment: .leading, spacing: 8) {
            Text(result.payload.title ?? "Result").font(.headline)
            if !onSupportingDisplay && display.isWindowOpen && workspace.supportingContent == .result(result.id) {
                ContentUnavailableView {
                    Label("On the supporting display", systemImage: "display")
                } actions: {
                    Button("Return here") { drawer.placementRef?.closeDisplay() }
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack { modePicker(presentation); exportButton }
                    VStack(alignment: .leading) { modePicker(presentation); exportButton }
                }
                if workspace.exporter.resultID == result.id, let message = workspace.exporter.message {
                    Text(message).font(.caption).textSelection(.enabled)
                }
                switch presentation.mode {
                case .summary: original
                case .sources: WorkspaceSourcesView(result: result, presentation: presentation)
                case .connections:
                    if let url = MemoryGraphSource.imageURL(result.payload) {
                        let graphStore = workspace.graphStore(for: result, url: url)
                        if let body = result.payload.body { Text(body).font(.caption).textSelection(.enabled) }
                        MemoryGraphView(store: graphStore, api: client.admin)
                    } else { original }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .id(result.id)
    }

    private func modePicker(_ presentation: WorkspaceResultPresentation) -> some View {
        Picker("Result view", selection: Binding(get: { presentation.mode }, set: { presentation.mode = $0 })) {
            Text("Summary").tag(WorkspaceResultMode.summary)
            Text("Sources").tag(WorkspaceResultMode.sources)
            if MemoryGraphSource.imageURL(result.payload) != nil {
                Text("Connections").tag(WorkspaceResultMode.connections)
            }
        }.pickerStyle(.segmented)
    }

    private var exportButton: some View {
        Button("Export…") { workspace.exporter.chooseDestination(for: result) }
            .disabled(workspace.exporter.busy)
            .help("Save supplied text and reference URLs; clipboard content is excluded")
    }

    private var original: some View {
        DisplayContentView(payload: result.payload, restoredScrollOffset: workspace.scrollOffsets[result.id],
                           onScrollOffset: { workspace.rememberScroll($0, for: result.id) })
    }
}
