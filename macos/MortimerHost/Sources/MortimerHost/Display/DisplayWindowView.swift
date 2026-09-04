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
    }
}

/// One display panel: title bar (close), body via the shared renderer,
/// drag anywhere on the title, resize by the corner handle. Internal
/// (not private): ConsoleView renders the SAME stack in-page while the
/// display window is closed — the web's DisplayPanel/DisplayWindowApp
/// one-renderer rule (D43), carried over.
struct SingleDisplayPanel: View {
    let panel: DisplayWindowPanel
    @Environment(DisplayWindowStore.self) private var store
    @State private var dragTranslation: CGSize = .zero
    @State private var resizeTranslation: CGSize = .zero

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
                DragGesture()
                    .onChanged { dragTranslation = $0.translation }
                    .onEnded { value in
                        store.move(id: panel.id, by: value.translation)
                        dragTranslation = .zero
                    }
            )

            DisplayContentView(payload: panel.payload)

            HStack {
                Spacer()
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.caption2)
                    .foregroundStyle(AppTheme.textDim)
                    .gesture(
                        DragGesture()
                            .onChanged { resizeTranslation = $0.translation }
                            .onEnded { value in
                                store.resize(id: panel.id, to: CGSize(
                                    width: panel.size.width + value.translation.width,
                                    height: panel.size.height + value.translation.height
                                ))
                                resizeTranslation = .zero
                            }
                    )
            }
        }
        .padding(14)
        .frame(
            width: max(280, panel.size.width + resizeTranslation.width),
            height: max(200, panel.size.height + resizeTranslation.height)
        )
        .mortimerGlass(.display)
        .offset(
            x: panel.offset.width + dragTranslation.width,
            y: panel.offset.height + dragTranslation.height
        )
        .padding(20)
    }
}
