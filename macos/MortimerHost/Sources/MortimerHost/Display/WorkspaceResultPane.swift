import SwiftUI
import AppKit
import JarvisKit

/// Reparented between main and supporting windows; data, graph and scroll state
/// remain app-owned. The main pane yields while its supporting renderer is live.
struct WorkspaceResultPane: View {
    let result: WorkspaceResult
    var onSupportingDisplay = false
    let coordinator: ConsoleActionCoordinator?
    /// WS-17: false in the Command Console, whose single control row
    /// (`ConsoleActionBar`) carries these actions.
    var showsActions = true
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer
    @Environment(ShareCoordinator.self) private var sharing
    @State private var showingSharePreview = false
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 2

    init(result: WorkspaceResult, onSupportingDisplay: Bool = false,
         coordinator: ConsoleActionCoordinator? = nil, showsActions: Bool = true) {
        self.result = result
        self.onSupportingDisplay = onSupportingDisplay
        self.coordinator = coordinator
        self.showsActions = showsActions
    }

    var body: some View {
        let presentation = workspace.presentation(for: result)
        VStack(alignment: .leading, spacing: 8) {
            Text(result.payload.title ?? "Result").font(.headline)
            if result.payload.isProtectedLocal {
                Label("Protected local result · sharing and export disabled",
                      systemImage: "lock.shield")
                    .font(.caption)
                    .foregroundStyle(AppTheme.amber)
                if let reference = result.payload.opaqueRef {
                    Text("Reference: \(reference)")
                        .font(.caption2.monospaced())
                        .foregroundStyle(AppTheme.textDim)
                }
            }
            if !onSupportingDisplay && display.isPresented(.result(result.id),
                selection: workspace.supportingContent,
                layoutVersion: InterfaceLayoutVersion.resolve(layoutVersion)) {
                ContentUnavailableView {
                    Label("On the supporting display", systemImage: "display")
                } actions: {
                    Button("Return here") { drawer.placementRef?.closeDisplay() }
                }
            } else {
                if showsActions {
                    ViewThatFits(in: .horizontal) {
                        HStack {
                            if !result.payload.isProtectedLocal { modePicker(presentation) }
                            copyButton; shareButton; exportButton
                        }
                        VStack(alignment: .leading) {
                            if !result.payload.isProtectedLocal { modePicker(presentation) }
                            HStack { copyButton; shareButton; exportButton }
                        }
                    }
                }
                if workspace.exporter.resultID == result.id, let message = workspace.exporter.message {
                    Text(message).font(.caption).textSelection(.enabled)
                }
                if result.payload.isProtectedLocal {
                    original
                } else {
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
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .id(result.id)
        .sheet(isPresented: $showingSharePreview) {
            SharePreviewSheet(coordinator: coordinator, isPresented: $showingSharePreview)
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
            .disabled(workspace.exporter.busy || result.payload.isProtectedLocal)
            .help("Save supplied text and reference URLs; clipboard content is excluded")
    }

    private var copyButton: some View {
        Button("Copy") {
            guard !result.payload.isProtectedLocal else { return }
            if let coordinator {
                _ = coordinator.executePointer(.sharePreview, target: result.id.uuidString)
                _ = coordinator.executePointer(.shareCopy)
            } else {
                workspace.exporter.copy(result: result)
            }
        }
        .disabled(result.payload.isProtectedLocal)
        .help("Copy the selected result text; clipboard payloads are excluded")
        .accessibilityLabel("Copy selected result")
    }

    private var shareButton: some View {
        Button("Share…") {
            guard !result.payload.isProtectedLocal else { return }
            if let coordinator {
                let outcome = coordinator.executePointer(.sharePreview, target: result.id.uuidString)
                if outcome == .applied { showingSharePreview = true }
            } else {
                if sharing.beginPreview(result) != nil { showingSharePreview = true }
            }
        }
        .disabled(result.payload.isProtectedLocal)
        .help("Review the selected result before copying, saving, or sharing it")
        .accessibilityLabel("Share selected result")
    }

    private var original: some View {
        DisplayContentView(payload: result.payload, restoredScrollOffset: workspace.scrollOffsets[result.id],
                           onScrollOffset: { workspace.rememberScroll($0, for: result.id) })
    }
}

/// The share preview, shared by the result pane and the console's single
/// control row (WS-17). Unchanged from the pane's former inline sheet.
struct SharePreviewSheet: View {
    let coordinator: ConsoleActionCoordinator?
    @Binding var isPresented: Bool
    @Environment(ShareCoordinator.self) private var sharing

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Share preview").font(.headline)
                Spacer()
                Button("Cancel") {
                    if let coordinator { _ = coordinator.executePointer(.shareCancel) }
                    else { sharing.cancel() }
                    isPresented = false
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
