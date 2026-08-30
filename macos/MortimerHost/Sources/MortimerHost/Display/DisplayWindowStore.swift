import Foundation
import Observation
import JarvisKit

/// A display-window panel: a `surface == "window"` payload plus its
/// client-side placement state (displayWindow.ts's registry, P14).
struct DisplayWindowPanel: Identifiable, Equatable, Sendable {
    let id: Int
    let payload: DisplayPayload
    let receivedAt: Date
    /// Cascade offset within the display window (points); the panel view
    /// adds the user's drag translation on top.
    var offset: CGSize
    var size: CGSize
}

/// APP plan §3 P14 — the native displayWindow.ts: `surface == "window"`
/// payloads only (weather, radar, research), rendered by DisplayScene as
/// a cascade-offset stack of draggable/resizable panels. Bounded at
/// maxDisplayWindowPanels (F4 — a DISTINCT cap from the Output tab's).
@MainActor
@Observable
final class DisplayWindowStore {
    private(set) var panels: [DisplayWindowPanel] = []
    private var seq = 0
    /// Whether the display Window scene is currently on screen — set by
    /// DisplayWindowView's onAppear/onDisappear (the native form of the
    /// web's hasLivePopup poll). The topbar's ⧉ Display active state and
    /// ↩︎ pop-in button read this.
    var isWindowOpen = false

    private static let cascadeStep: CGFloat = 28
    private static let defaultSize = CGSize(width: 520, height: 400)

    func apply(_ payload: DisplayPayload) {
        seq += 1
        let step = Self.cascadeStep * CGFloat(panels.count % 8)
        let panel = DisplayWindowPanel(
            id: seq, payload: payload, receivedAt: Date(),
            offset: CGSize(width: step, height: step),
            size: Self.defaultSize
        )
        panels.append(panel)
        if panels.count > AppTuning.maxDisplayWindowPanels {
            panels.removeFirst(panels.count - AppTuning.maxDisplayWindowPanels)
        }
    }

    func move(id: Int, by translation: CGSize) {
        guard let i = panels.firstIndex(where: { $0.id == id }) else { return }
        panels[i].offset.width += translation.width
        panels[i].offset.height += translation.height
    }

    func resize(id: Int, to size: CGSize) {
        guard let i = panels.firstIndex(where: { $0.id == id }) else { return }
        panels[i].size = CGSize(width: max(280, size.width), height: max(200, size.height))
    }

    func close(id: Int) {
        panels.removeAll { $0.id == id }
    }
}
