import SwiftUI
import AppKit
import JarvisKit

/// Reparented between main and supporting windows; data, graph and scroll state
/// remain app-owned. The main pane yields while its supporting renderer is live.
struct WorkspaceResultPane: View {
    let result: WorkspaceResult
    var onSupportingDisplay = false
    let coordinator: ConsoleActionCoordinator?
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer
    @Environment(ShareCoordinator.self) private var sharing
    @State private var showingSharePreview = false
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 2

    init(result: WorkspaceResult, onSupportingDisplay: Bool = false,
         coordinator: ConsoleActionCoordinator? = nil) {
        self.result = result
        self.onSupportingDisplay = onSupportingDisplay
        self.coordinator = coordinator
    }

    var body: some View {
        let presentation = workspace.presentation(for: result)
        VStack(alignment: .leading, spacing: 8) {
            Text(result.payload.title ?? "Result").font(.headline)
            if !onSupportingDisplay && display.isPresented(.result(result.id),
                selection: workspace.supportingContent,
                layoutVersion: InterfaceLayoutVersion.resolve(layoutVersion)) {
                ContentUnavailableView {
                    Label("On the supporting display", systemImage: "display")
                } actions: {
                    Button("Return here") { drawer.placementRef?.closeDisplay() }
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack { modePicker(presentation); copyButton; shareButton; exportButton }
                    VStack(alignment: .leading) { modePicker(presentation); HStack { copyButton; shareButton; exportButton } }
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
                        // Result-specific connection graphs have their own
                        // store; the shared coordinator intentionally owns
                        // only the primary memory graph. Keep these local
                        // controls on their existing store path.
                        MemoryGraphView(store: graphStore, api: client.admin)
                    } else { original }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .id(result.id)
        .sheet(isPresented: $showingSharePreview) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Share preview").font(.headline)
                    Spacer()
                    Button("Cancel") {
                        if let coordinator { _ = coordinator.executePointer(.shareCancel) }
                        else { sharing.cancel() }
                        showingSharePreview = false
                    }
                    Button("Copy") {
                        if let coordinator { _ = coordinator.executePointer(.shareCopy) }
                        else { _ = sharing.copy() }
                    }
                    Button("Save…") {
                        if let coordinator { _ = coordinator.executePointer(.shareSave) }
                        else { sharing.chooseSave() }
                    }
                    Button("Share…") {
                        if let coordinator { _ = coordinator.executePointer(.sharePicker) }
                        else { _ = sharing.presentPicker() }
                    }
                }
                if let preview = sharing.preview {
                    SharePreviewView(text: preview.text, format: preview.format, data: preview.data)
                } else {
                    Text("The preview is no longer available.").foregroundStyle(AppTheme.textDim)
                }
            }
            .padding(16)
            .frame(minWidth: 520, minHeight: 360)
        }
    }

    private func modePicker(_ presentation: WorkspaceResultPresentation) -> some View {
        Picker("Result view", selection: Binding(get: { presentation.mode }, set: { mode in
            if let coordinator {
                _ = coordinator.executePointer(.resultMode, target: result.id.uuidString,
                                                args: ["mode": .string(mode.rawValue)])
            } else {
                presentation.mode = mode
            }
        })) {
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

    private var copyButton: some View {
        Button("Copy") {
            if let coordinator {
                _ = coordinator.executePointer(.sharePreview, target: result.id.uuidString)
                _ = coordinator.executePointer(.shareCopy)
            } else {
                workspace.exporter.copy(text: WorkspaceResultExport.text(result))
            }
        }
        .help("Copy the selected result text; clipboard payloads are excluded")
        .accessibilityLabel("Copy selected result")
    }

    private var shareButton: some View {
        Button("Share…") {
            if let coordinator {
                let outcome = coordinator.executePointer(.sharePreview, target: result.id.uuidString)
                if outcome == .applied { showingSharePreview = true }
            } else {
                sharing.beginPreview(result)
                showingSharePreview = true
            }
        }
        .help("Review the selected result before copying, saving, or sharing it")
        .accessibilityLabel("Share selected result")
    }

    private var original: some View {
        DisplayContentView(payload: result.payload, restoredScrollOffset: workspace.scrollOffsets[result.id],
                           onScrollOffset: { workspace.rememberScroll($0, for: result.id) })
    }
}
