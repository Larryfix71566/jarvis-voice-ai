import SwiftUI
import JarvisKit

/// APP plan §3 P14, §5 step 12 — the DisplayScene body: a cascade stack
/// of independent, draggable/resizable panels for `surface == "window"`
/// payloads (weather, radar, research). Parked on a second monitor by
/// ScreenPlacement (P11).
struct DisplayWindowView: View {
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 0
    @Environment(DisplayWindowStore.self) private var store
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DrawerState.self) private var drawer
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        ZStack(alignment: .topLeading) {
            AppTheme.bg.ignoresSafeArea()
            if layoutVersion == 1 && workspace.supportingContent != nil {
                VStack(spacing: 12) {
                    HStack {
                        Button("Original display panels") { workspace.showOriginalDisplayPanels() }
                        Spacer()
                        Button("Return to main window") { drawer.placementRef?.closeDisplay() }
                    }
                    if workspace.supportingContent == .memoryGraph {
                        MemoryGraphView(store: workspace.memoryGraph, api: client.admin)
                    } else if let result = workspace.supportingResult {
                        WorkspaceResultPane(result: result, onSupportingDisplay: true)
                    }
                }.padding(16)
            } else {
            if store.panels.isEmpty {
                Text("Nothing on display. Ask for something visual — \"show the radar\".")
                    .foregroundStyle(AppTheme.textDim)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            ForEach(store.panels) { panel in
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
                Text(panel.payload.title ?? panel.payload.tool ?? "Display")
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Button {
                    store.close(id: panel.id)
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
            DisplayContentView(payload: panel.payload, isResizing: resizeTranslation != .zero)

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
        .padding(AppTuning.displayPanelInset)
    }
}
