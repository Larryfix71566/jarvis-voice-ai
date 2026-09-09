import SwiftUI
import JarvisKit

/// APP plan §3 P14, §5 step 12 — the DisplayScene body: a cascade stack
/// of independent, draggable/resizable panels for `surface == "window"`
/// payloads (weather, radar, research). Parked on a second monitor by
/// ScreenPlacement (P11).
struct DisplayWindowView: View {
    @Environment(DisplayWindowStore.self) private var store

    var body: some View {
        ZStack(alignment: .topLeading) {
            AppTheme.bg.ignoresSafeArea()
            if store.panels.isEmpty {
                Text("Nothing on display. Ask for something visual — \"show the radar\".")
                    .foregroundStyle(AppTheme.textDim)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            ForEach(store.panels) { panel in
                SingleDisplayPanel(panel: panel)
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
/// drag anywhere on the title, resize by any edge or corner, double-click
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
///
/// 2026-09-08 ("edge resize handles"): the bottom-right grip is joined by
/// right-edge, bottom-edge and top-left/top-right/bottom-left handles.
/// A handle anchored on the leading/top side both shrinks the size and
/// moves the panel, so the opposite edge stays put; `resizeGeometry`
/// derives the offset from the CLAMPED size, so at the minimum size the
/// panel stops moving instead of sliding away under the pointer.
struct SingleDisplayPanel: View {
    let panel: DisplayWindowPanel
    @Environment(DisplayWindowStore.self) private var store
    @State private var dragTranslation: CGSize = .zero
    @State private var resizeTranslation: CGSize = .zero
    @State private var activeHandle: ResizeHandle?
    @State private var hoveredHandle: ResizeHandle?

    /// Which side(s) of the panel a handle moves. `h`/`v` are +1 for the
    /// trailing/bottom side, -1 for the leading/top side, 0 for neither.
    enum ResizeHandle: Hashable {
        case right, bottom
        case topLeading, topTrailing, bottomLeading, bottomTrailing

        var h: CGFloat {
            switch self {
            case .right, .topTrailing, .bottomTrailing: return 1
            case .topLeading, .bottomLeading: return -1
            case .bottom: return 0
            }
        }

        var v: CGFloat {
            switch self {
            case .bottom, .bottomLeading, .bottomTrailing: return 1
            case .topLeading, .topTrailing: return -1
            case .right: return 0
            }
        }
    }

    private static let edgeThickness: CGFloat = 10
    private static let cornerSize: CGFloat = 16

    /// Pure: the live size and the offset delta for a drag of `translation`
    /// on `handle`, starting from `base`. The offset delta is derived from
    /// the clamped size so the minimum-size clamp pins the panel too.
    static func resizeGeometry(handle: ResizeHandle, base: CGSize, translation: CGSize) -> (size: CGSize, offset: CGSize) {
        let size = DisplayWindowStore.clamped(CGSize(
            width: base.width + handle.h * translation.width,
            height: base.height + handle.v * translation.height))
        let offset = CGSize(
            width: handle.h < 0 ? base.width - size.width : 0,
            height: handle.v < 0 ? base.height - size.height : 0)
        return (size, offset)
    }

    private var live: (size: CGSize, offset: CGSize) {
        guard let handle = activeHandle else {
            return (DisplayWindowStore.clamped(panel.size), .zero)
        }
        return Self.resizeGeometry(handle: handle, base: panel.size, translation: resizeTranslation)
    }

    private func isLit(_ handle: ResizeHandle) -> Bool {
        hoveredHandle == handle || activeHandle == handle
    }

    /// Every resize drag measures in `.global` — see the type comment.
    private func resizeGesture(_ handle: ResizeHandle) -> some Gesture {
        DragGesture(minimumDistance: 1, coordinateSpace: .global)
            .onChanged { value in
                activeHandle = handle
                resizeTranslation = value.translation
            }
            .onEnded { value in
                let result = Self.resizeGeometry(handle: handle, base: panel.size, translation: value.translation)
                store.resize(id: panel.id, to: result.size)
                if result.offset != .zero {
                    store.move(id: panel.id, by: result.offset)
                }
                resizeTranslation = .zero
                activeHandle = nil
            }
    }

    private func handleShape(_ handle: ResizeHandle) -> some View {
        Rectangle()
            .fill(isLit(handle) ? AppTheme.accent.opacity(0.45) : Color.clear)
            .contentShape(Rectangle())
            .onHover { inside in
                if inside {
                    hoveredHandle = handle
                } else if hoveredHandle == handle {
                    hoveredHandle = nil
                }
            }
            .gesture(resizeGesture(handle))
            .help("Drag to resize")
    }

    /// Edge strips are inset by a corner's width at each end so the corner
    /// handles — and the bottom-right grip in the body — stay reachable.
    private var resizeHandles: some View {
        ZStack {
            handleShape(.right)
                .frame(width: Self.edgeThickness)
                .padding(.vertical, Self.cornerSize)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
            handleShape(.bottom)
                .frame(height: Self.edgeThickness)
                .padding(.horizontal, Self.cornerSize)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
            handleShape(.topLeading)
                .frame(width: Self.cornerSize, height: Self.cornerSize)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            handleShape(.topTrailing)
                .frame(width: Self.cornerSize, height: Self.cornerSize)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
            handleShape(.bottomLeading)
                .frame(width: Self.cornerSize, height: Self.cornerSize)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
        }
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
            DisplayContentView(payload: panel.payload, isResizing: activeHandle != nil)

            HStack {
                Spacer()
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.caption2)
                    .foregroundStyle(isLit(.bottomTrailing) ? AppTheme.accent : AppTheme.textDim)
                    .frame(width: AppTuning.displayPanelGripSize, height: AppTuning.displayPanelGripSize)
                    .contentShape(Rectangle())
                    .onHover { inside in
                        if inside {
                            hoveredHandle = .bottomTrailing
                        } else if hoveredHandle == .bottomTrailing {
                            hoveredHandle = nil
                        }
                    }
                    .gesture(resizeGesture(.bottomTrailing))
                    .help("Drag to resize")
            }
        }
        .padding(14)
        .frame(width: live.size.width, height: live.size.height)
        .mortimerGlass(.display)
        .overlay(resizeHandles)
        .offset(
            x: panel.offset.width + dragTranslation.width + live.offset.width,
            y: panel.offset.height + dragTranslation.height + live.offset.height
        )
        .padding(AppTuning.displayPanelInset)
    }
}
