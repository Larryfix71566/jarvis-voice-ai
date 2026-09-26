import SwiftUI
import JarvisKit

/// APP plan §3 P14, §5 step 12 — the DisplayScene body: a cascade stack
/// of independent, draggable/resizable panels for `surface == "window"`
/// payloads (weather, radar, research). Parked on a second monitor by
/// ScreenPlacement (P11).
struct DisplayWindowView: View {
    // C9.5 / G30 — see MortimerHostApp for the default and one-time migration.
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 2
    private var activeLayoutVersion: Int {
        InterfaceLayoutVersion.resolve(layoutVersion)
    }
    @Environment(DisplayWindowStore.self) private var store
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DrawerState.self) private var drawer
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        ZStack(alignment: .topLeading) {
            AppTheme.bg.ignoresSafeArea()
            if activeLayoutVersion == 1 && workspace.supportingContent != nil {
                VStack(spacing: 12) {
                    HStack {
                        Button("Original display panels") { workspace.showOriginalDisplayPanels() }
                        Spacer()
                        Button("Return to main window") { drawer.placementRef?.closeDisplay() }
                    }
                    if workspace.supportingContent == .memoryGraph {
                        MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
                    } else if workspace.supportingContent == .workflows {
                        WorkflowsView(store: workspace.workflows, api: client.admin)
                    } else if let result = workspace.supportingResult {
                        WorkspaceResultPane(result: result, onSupportingDisplay: true)
                    }
                }.padding(16)
            } else {
            let stagePanels = store.stagePanels(selection: workspace.supportingContent)
            let supplemental = store.supplementalContent(workspace.supportingContent)
            if !stagePanels.isEmpty {
                SupportingDisplayStage(panels: stagePanels, supplemental: supplemental)
            } else if let supportingContent = supplemental {
                // Pointer-selected content uses the app-owned WorkspaceStore
                // path rather than a transport DisplayPayload. Keep that
                // path in the same single supporting-stage window so layout 2
                // cannot open an empty window while leaving a duplicate graph
                // or result visible in the main surface.
                LegacySupportingDisplayStage(content: supportingContent)
            } else {
                Text("Nothing on display. Ask for something visual — \"show the radar\".")
                    .foregroundStyle(AppTheme.textDim)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            // Only explicit pinned overflow leaves the bounded stage. Those
            // copies remain reachable as movable cards without changing the
            // default one-window presentation.
            ForEach(store.panels.filter(\.pinned)) { panel in
                SingleDisplayPanel(panel: panel)
            }
            }
        }
        .frame(minWidth: 700, minHeight: 500)
        .foregroundStyle(AppTheme.text)
        // The panels' viewport while this window is open — what a panel's
        // "fit to window" (double-click its title) fills.
        .onGeometryChange(for: CGSize.self) { proxy in
            proxy.size
        } action: { size in
            store.viewportSize = size
        }
    }
}

/// Renderer for pointer-selected WorkspaceStore content. This is deliberately
/// one outer stage, matching SupportingDisplayStage; it does not create a
/// nested result window inside the display window.
private struct LegacySupportingDisplayStage: View {
    let content: SupportingDisplayContent
    @Environment(WorkspaceStore.self) private var workspace
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: "display").foregroundStyle(AppTheme.accent)
                Text(title).font(.title3.weight(.semibold))
                Spacer()
                Text("SUPPORTING DISPLAY")
                    .font(.caption2.monospaced().weight(.semibold))
                    .foregroundStyle(AppTheme.textDim)
            }
            .padding(.horizontal, 4)
            Group {
                switch content {
                case .memoryGraph:
                    MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
                case .workflows:
                    WorkflowsView(store: workspace.workflows, api: client.admin)
                case .result(let id):
                    if let result = workspace.results.first(where: { $0.id == id }) {
                        WorkspaceResultPane(result: result, onSupportingDisplay: true)
                    } else {
                        ContentUnavailableView("Result unavailable", systemImage: "exclamationmark.triangle")
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(AppTheme.bg)
        .mortimerGlass(.display)
    }

    private var title: String {
        switch content {
        case .memoryGraph: return "Memory graph"
        case .workflows: return "Workflows"
        case .result(let id): return workspace.results.first(where: { $0.id == id })?.payload.title ?? "Result"
        }
    }
}

/// The default supporting-display renderer. The display scene is already a
/// window, so results share one responsive stage instead of opening a second
/// floating information window inside it. One result fills the stage; two to
/// four results use readable tiles. Explicitly pinned overflow continues to
/// use `SingleDisplayPanel` below.
struct SupportingDisplayStage: View {
    let panels: [DisplayWindowPanel]
    var supplemental: SupportingDisplayContent? = nil
    @Environment(DisplayWindowStore.self) private var store
    @Environment(WorkspaceStore.self) private var workspace
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: "display").foregroundStyle(AppTheme.accent)
                Text(tileCount == 1 ? "Supporting display" : "Supporting display · \(tileCount) results")
                    .font(.title3.weight(.semibold))
                Spacer()
                Text("SUPPORTING DISPLAY")
                    .font(.caption2.monospaced().weight(.semibold))
                    .foregroundStyle(AppTheme.textDim)
            }
            .padding(.horizontal, 4)

            if tileCount == 1, let panel = panels.first {
                SupportingDisplayTile(panel: panel, tiled: false)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else {
                // A multi-result stage is a bounded viewport. The previous
                // grid gave every tile an infinite height proposal; on a
                // real external display that could collapse the whole stage
                // to an empty surface while AppKit reported negative view
                // geometry. Keep the grid finite and let the stage scroll.
                ScrollView(.vertical) {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 420), spacing: 14)],
                              spacing: 14) {
                        if let supplemental {
                            LegacySupportingDisplayStage(content: supplemental)
                                .frame(height: 480)
                        }
                        ForEach(panels) { panel in
                            SupportingDisplayTile(panel: panel, tiled: true)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .padding(.bottom, 4)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(AppTheme.bg)
    }

    private var tileCount: Int { panels.count + (supplemental == nil ? 0 : 1) }
}

private struct SupportingDisplayTile: View {
    let panel: DisplayWindowPanel
    let tiled: Bool
    @Environment(DisplayWindowStore.self) private var store
    @Environment(WorkspaceStore.self) private var workspace
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text(panel.displayTitle)
                    .font(tiled ? .headline : .title2)
                    .lineLimit(2)
                Spacer()
                Button {
                    if panel.pinned { _ = store.openAdditional(id: panel.id) }
                    else { _ = store.pin(id: panel.id) }
                } label: {
                    Image(systemName: panel.pinned ? "plus.square" : "pin")
                }
                .buttonStyle(.plain)
                .foregroundStyle(panel.pinned ? AppTheme.accent : AppTheme.textDim)
                .accessibilityLabel(panel.pinned ? "Open another copy" : "Pin panel")
                Button {
                    let closesLastPanel = store.panels.count == 1
                    store.close(id: panel.id)
                    if closesLastPanel { workspace.showOriginalDisplayPanels() }
                } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain)
                    .foregroundStyle(AppTheme.textDim)
                    .accessibilityLabel("Close " + (panel.payload.title ?? "display panel"))
            }
            Group {
                DisplayWindowPanelContent(panel: panel)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .padding(tiled ? 14 : 4)
        // Every stage tile uses the shared Liquid Glass switch. The role
        // changes with density, but the setting cannot silently diverge
        // between a single full-stage result and a multi-result grid.
        .mortimerGlass(tiled ? .card : .display)
        // Tiled cards have a finite height because their parent is a
        // scrolling grid. A single full-stage card may still expand to the
        // entire display viewport.
        .frame(maxWidth: .infinity, minHeight: tiled ? 280 : 0,
               maxHeight: tiled ? 480 : .infinity, alignment: .topLeading)
    }

}

/// Renders one panel's content. A Developer/self-edit panel can contain
/// several file results, but it remains one outer display renderer with
/// readable dividers between the appended sections.
private struct DisplayWindowPanelContent: View {
    let panel: DisplayWindowPanel
    @Environment(WorkspaceStore.self) private var workspace
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        if panel.appendedPayloads.isEmpty {
            item(payload: panel.payload, workspaceID: panel.workspaceID)
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Developer request · \(panel.allPayloads.count) results")
                        .font(.headline)
                        .foregroundStyle(AppTheme.accent)
                    ForEach(Array(panel.allPayloads.indices), id: \.self) { index in
                        if index > 0 { Divider().overlay(AppTheme.hairline) }
                        VStack(alignment: .leading, spacing: 8) {
                            Text(panel.allPayloads[index].title ?? panel.allPayloads[index].tool ?? "Result")
                                .font(.subheadline.weight(.semibold))
                            item(payload: panel.allPayloads[index], workspaceID: panel.allWorkspaceIDs[index])
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func item(payload: DisplayPayload, workspaceID: UUID?) -> some View {
        if Self.isMemoryGraphPayload(payload) {
            MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
        } else if let workspaceID,
                  let result = workspace.results.first(where: { $0.id == workspaceID }) {
            WorkspaceResultPane(result: result, onSupportingDisplay: true)
        } else {
            DisplayContentView(payload: payload)
        }
    }

    private static func isMemoryGraphPayload(_ payload: DisplayPayload) -> Bool {
        let values = [payload.kind, payload.title, payload.tool]
            .compactMap { $0?.lowercased() }
        if values.contains(where: { $0.contains("memory_graph") || $0.contains("memory graph") }) {
            return true
        }
        return payload.images?.contains { $0.lowercased().contains("/graph/memory") } == true
    }
}

/// One display panel: title bar (close), body via the shared renderer,
/// drag anywhere on the title, resize by the corner handle, double-click
/// the title to fill the viewport. Internal (not private): ConsoleView
/// renders the SAME stack in-page while the display window is closed —
/// the web's DisplayPanel/DisplayWindowApp one-renderer rule (D43),
/// carried over.
///
/// 2026-09-05 ("graph window sizable without limitation"): both drags
/// measure in `.global` — the panel's frame changes DURING a resize, so
/// a `.local` translation is re-derived from the moving frame and fights
/// the pointer (the same defect as ConsoleView's drawer grip). No maximum
/// size anywhere; the corner grip grew to a real hit target with hover
/// feedback; the body reports its size so a graph image can be
/// re-rendered at the panel's true pixel size (DisplayContentView).
struct SingleDisplayPanel: View {
    let panel: DisplayWindowPanel
    @Environment(DisplayWindowStore.self) private var store
    @Environment(WorkspaceStore.self) private var workspace
    @State private var dragTranslation: CGSize = .zero
    @State private var resizeTranslation: CGSize = .zero
    @State private var gripHovering = false

    private var liveSize: CGSize {
        DisplayWindowStore.clamped(CGSize(
            width: panel.size.width + resizeTranslation.width,
            height: panel.size.height + resizeTranslation.height))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(panel.displayTitle)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Button {
                    if panel.pinned { _ = store.openAdditional(id: panel.id) }
                    else { _ = store.pin(id: panel.id) }
                } label: {
                    Image(systemName: panel.pinned ? "plus.square" : "pin")
                }
                .buttonStyle(.plain)
                .foregroundStyle(panel.pinned ? AppTheme.accent : AppTheme.textDim)
                .accessibilityLabel(panel.pinned ? "Open another copy" : "Pin panel")
                .help(panel.pinned ? "Open another copy" : "Pin this panel; repeated requests will reuse it")
                Button {
                    // Closing the last supporting card returns ownership to
                    // the main work surface. Without clearing the locator,
                    // WorkspaceResultPane would continue to claim that the
                    // result is on a display that is now empty.
                    let closesLastPanel = store.panels.count == 1
                    store.close(id: panel.id)
                    if closesLastPanel {
                        workspace.showOriginalDisplayPanels()
                    }
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textDim)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { dragTranslation = $0.translation }
                    .onEnded { value in
                        store.move(id: panel.id, by: value.translation)
                        dragTranslation = .zero
                    }
            )
            .simultaneousGesture(
                TapGesture(count: 2).onEnded { store.fit(id: panel.id) }
            )
            .help("Drag to move · double-click to fill the window")

            // isResizing lets a graph image hold its current bitmap through
            // the drag and re-request once the size settles.
            DisplayWindowPanelContent(panel: panel)

            HStack {
                Spacer()
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.caption2)
                    .foregroundStyle(gripHovering || resizeTranslation != .zero ? AppTheme.accent : AppTheme.textDim)
                    .frame(width: AppTuning.displayPanelGripSize, height: AppTuning.displayPanelGripSize)
                    .contentShape(Rectangle())
                    .onHover { gripHovering = $0 }
                    .gesture(
                        DragGesture(minimumDistance: 1, coordinateSpace: .global)
                            .onChanged { resizeTranslation = $0.translation }
                            .onEnded { value in
                                store.resize(id: panel.id, to: CGSize(
                                    width: panel.size.width + value.translation.width,
                                    height: panel.size.height + value.translation.height
                                ))
                                resizeTranslation = .zero
                            }
                    )
                    .help("Drag to resize")
            }
        }
        .padding(14)
        .frame(width: liveSize.width, height: liveSize.height)
        .mortimerGlass(.display)
        .offset(
            x: panel.offset.width + dragTranslation.width,
            y: panel.offset.height + dragTranslation.height
        )
        .zIndex(panel.focused ? 1 : 0)
        .padding(AppTuning.displayPanelInset)
    }
}
