import SwiftUI
import JarvisKit

/// Shared-store renderer for one value-addressed detached panel. The panel
/// scene is presentation only: result ingestion, graph state, attachments,
/// audio and placement remain owned by the app scope.
struct DetachedPanelView: View {
    let panel: ConsolePanel
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(AtlasStore.self) private var atlas
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        Group {
            switch panel {
            case .atlas:
                KnowledgeAtlasView()
            case .results:
                WorkspaceView()
            case .memory:
                MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
            case .output:
                DrawerView()
            }
        }
        .frame(minWidth: 420, minHeight: 300)
        .foregroundStyle(AppTheme.text)
        .background(AppTheme.bg)
    }
}

/// Dynamic content-panel scene used by the v2 detachable-content contract.
/// It reads the record by UUID and renders from the existing app stores; a
/// missing record becomes a truthful, closable empty state.
struct ContentPanelSceneView: View {
    let panelID: ContentPanelID
    @Environment(PanelStore.self) private var panels
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(AtlasStore.self) private var atlas
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        Group {
            if let record = panels.contentRecord(panelID) {
                switch record.content {
                case .result, .sources, .comparison:
                    WorkspaceView()
                case .memoryGraph:
                    MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
                case .atlas:
                    KnowledgeAtlasView()
                case .transcript:
                    DrawerView()
                }
            } else {
                VStack(spacing: 12) {
                    Text("This session's content is no longer available")
                    Text("Close this panel and choose the content again.")
                        .font(.caption).foregroundStyle(AppTheme.textDim)
                }
                .padding(32)
            }
        }
        .frame(minWidth: 420, minHeight: 300)
        .foregroundStyle(AppTheme.text)
        .background(AppTheme.bg)
    }
}
