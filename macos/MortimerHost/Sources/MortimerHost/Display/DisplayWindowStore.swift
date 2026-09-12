import Foundation
import Observation
import JarvisKit

/// A display-window panel: a `surface == "window"` payload plus its
/// client-side placement state (displayWindow.ts's registry, P14).
struct DisplayWindowPanel: Identifiable, Equatable, Sendable {
    let id: Int
    let payload: DisplayPayload
    let receivedAt: Date
    var workspaceID: UUID? = nil
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
    /// The area the panels are stacked in, in points: the display window's
    /// content when it is open, the console stage otherwise (each sets it
    /// from its own geometry). `fit(id:)` fills it. Zero until measured.
    var viewportSize: CGSize = .zero

    private static let cascadeStep: CGFloat = 28
    private static let defaultSize = CGSize(width: 520, height: 400)
    /// Minimum panel size — the ONLY limit on a panel; there is no maximum
    /// (2026-09-05, "sizable without limitation"). A panel larger than the
    /// viewport is simply clipped by it; grow the window.
    static let minPanelSize = CGSize(width: 280, height: 200)

    func apply(_ payload: DisplayPayload, workspaceID: UUID? = nil) {
        seq += 1
        let step = Self.cascadeStep * CGFloat(panels.count % 8)
        let panel = DisplayWindowPanel(
            id: seq, payload: payload, receivedAt: Date(), workspaceID: workspaceID,
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
        panels[i].size = Self.clamped(size)
    }

    /// Double-click on a panel's title bar: fill the viewport (minus the
    /// panel inset on every side) and drop the cascade offset. A no-op
    /// until the viewport has been measured.
    func fit(id: Int) {
        guard let i = panels.firstIndex(where: { $0.id == id }),
              let size = Self.fittedSize(viewport: viewportSize) else { return }
        panels[i].offset = .zero
        panels[i].size = size
    }

    /// Pure: the panel size that fills `viewport` with the standard inset,
    /// or nil when the viewport is unmeasured/too small to be meaningful.
    static func fittedSize(viewport: CGSize, inset: CGFloat = CGFloat(AppTuning.displayPanelInset)) -> CGSize? {
        let inner = CGSize(width: viewport.width - inset * 2, height: viewport.height - inset * 2)
        guard inner.width >= minPanelSize.width, inner.height >= minPanelSize.height else { return nil }
        return inner
    }

    static func clamped(_ size: CGSize) -> CGSize {
        CGSize(width: max(minPanelSize.width, size.width),
               height: max(minPanelSize.height, size.height))
    }

    func close(id: Int) {
        panels.removeAll { $0.id == id }
    }
}
