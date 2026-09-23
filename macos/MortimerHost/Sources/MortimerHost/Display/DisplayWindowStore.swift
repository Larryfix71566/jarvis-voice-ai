import Foundation
import Observation
import JarvisKit

/// A display-window panel: a `surface == "window"` payload plus its
/// client-side placement state (displayWindow.ts's registry, P14).
struct DisplayWindowPanel: Identifiable, Equatable, Sendable {
    let id: Int
    var payload: DisplayPayload
    /// Stable within the session and independent of the transport timestamp.
    /// This is the identity used to decide whether a new window request is
    /// the same visual result as an existing panel.
    let identityKey: String
    let receivedAt: Date
    var workspaceID: UUID? = nil
    /// Additional results appended to this panel when one Developer/self-edit
    /// run produces several file reads. The workspace keeps each result in
    /// its own history row; the supporting display keeps one outer renderer.
    var appendedPayloads: [DisplayPayload] = []
    var appendedWorkspaceIDs: [UUID?] = []
    /// Non-nil only for a run-scoped Developer presentation batch.
    var aggregationKey: String? = nil
    /// Cascade offset within the display window (points); the panel view
    /// adds the user's drag translation on top.
    var offset: CGSize
    var size: CGSize
    var focused: Bool = true
    var pinned: Bool = false

    var allPayloads: [DisplayPayload] { [payload] + appendedPayloads }
    var allWorkspaceIDs: [UUID?] { [workspaceID] + appendedWorkspaceIDs }

    var displayTitle: String {
        guard !appendedPayloads.isEmpty else {
            return payload.title ?? payload.tool ?? "Display"
        }
        return "\(payload.agent ?? "Developer") request · \(allPayloads.count) results"
    }
}

/// APP plan §3 P14 — the native displayWindow.ts: `surface == "window"`
/// payloads only (weather, radar, research), rendered by the supporting
/// display stage as a bounded result grid. Explicitly pinned overflow remains
/// available as draggable/resizable panels. Bounded at maxDisplayWindowPanels
/// (F4 — a DISTINCT cap from the Output tab's).
@MainActor
@Observable
final class DisplayWindowStore {
    private(set) var panels: [DisplayWindowPanel] = []
    private var seq = 0
    private(set) var focusedID: Int?
    /// Whether the display Window scene is currently on screen — set by
    /// DisplayWindowView's onAppear/onDisappear (the native form of the
    /// web's hasLivePopup poll). The topbar's ⧉ Display active state and
    /// ↩︎ pop-in button read this.
    private(set) var isWindowOpen = false
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

    /// Number of unpinned panels in the supporting presentation stage. The
    /// stage shares up to `maxSupportingStagePanels` result tiles; pinned
    /// copies are explicit additions and do not consume this default budget.
    var defaultPresentationPanelCount: Int {
        panels.reduce(into: 0) { count, panel in count += panel.pinned ? 0 : 1 }
    }

    /// The one item rendered as the supporting display's full-stage content.
    /// Pinned panels are explicit overflow and therefore never become part of
    /// the default curated stage. A focused unpinned item wins; the latest
    /// unpinned item is a deterministic fallback before the first focus
    /// callback arrives.
    var activePresentationPanelID: Int? {
        if let focusedID,
           panels.contains(where: { $0.id == focusedID && !$0.pinned }) {
            return focusedID
        }
        return panels.last(where: { !$0.pinned })?.id
    }

    /// Panels rendered together in the single supporting-display stage. The
    /// focused item is first so a screen reader and keyboard focus land on the
    /// same result the console identifies as active.
    var presentationPanels: [DisplayWindowPanel] {
        let activeID = activePresentationPanelID
        let ordered = panels.filter { !$0.pinned }.sorted { lhs, rhs in
            if lhs.id == activeID { return true }
            if rhs.id == activeID { return false }
            return lhs.id < rhs.id
        }
        return Array(ordered.prefix(AppTuning.maxSupportingStagePanels))
    }

    /// Pointer-selected content shares the same finite stage as transport
    /// results. It needs an extra tile only when no existing panel owns it.
    func supplementalContent(_ selection: SupportingDisplayContent?) -> SupportingDisplayContent? {
        guard let selection else { return nil }
        switch selection {
        case .memoryGraph:
            return containsMemoryGraph() ? nil : selection
        case .result(let id):
            return containsWorkspaceResult(id) ? nil : selection
        }
    }

    func stagePanels(selection: SupportingDisplayContent?) -> [DisplayWindowPanel] {
        let reserved = supplementalContent(selection) == nil ? 0 : 1
        return Array(presentationPanels.prefix(AppTuning.maxSupportingStagePanels - reserved))
    }

    /// Used by the main surface's return locator. A queued selection alone
    /// cannot hide a result which the supporting window is not rendering.
    func isPresented(_ content: SupportingDisplayContent,
                     selection: SupportingDisplayContent?, layoutVersion: Int = 2) -> Bool {
        guard isWindowOpen else { return false }
        if layoutVersion == 1, let selection { return content == selection }
        if supplementalContent(selection) == content { return true }
        let visible = stagePanels(selection: selection) + panels.filter(\.pinned)
        switch content {
        case .memoryGraph:
            return visible.contains { $0.allPayloads.contains(where: Self.isMemoryGraphPayload) }
        case .result(let id):
            return visible.contains { $0.allWorkspaceIDs.contains(id) }
        }
    }

    /// Mark the native supporting-display scene as present or absent. Opening
    /// the scene also reconciles panels that accumulated while it was closed,
    /// retaining the bounded unpinned stage set and every explicit pin.
    func setWindowOpen(_ open: Bool) {
        isWindowOpen = open
        if open { enforcePresentationBudget() }
    }

    /// Accept a transport payload. Exact visual identities are reused and
    /// focused by default; this is the native equivalent of the web
    /// display-window registry's replace/focus behavior. A caller may opt in
    /// to an additional copy only through `openAdditional`, which makes
    /// deliberate pinning explicit instead of turning repeated voice
    /// requests into a panel fan-out.
    @discardableResult
    func apply(_ payload: DisplayPayload, workspaceID: UUID? = nil) -> Int {
        let aggregationKey = Self.aggregationKey(for: payload)
        if let aggregationKey,
           let index = panels.firstIndex(where: {
               $0.aggregationKey == aggregationKey && !$0.pinned
           }) {
            let matchedIndex = panels[index].allPayloads.firstIndex {
                Self.identityKey(for: $0) == Self.identityKey(for: payload)
            }
            if let matchedIndex {
                if let workspaceID {
                    if matchedIndex == 0 {
                        panels[index].workspaceID = workspaceID
                    } else {
                        let offset = matchedIndex - 1
                        if panels[index].appendedWorkspaceIDs.indices.contains(offset) {
                            panels[index].appendedWorkspaceIDs[offset] = workspaceID
                        }
                    }
                }
            } else {
                panels[index].appendedPayloads.append(payload)
                panels[index].appendedWorkspaceIDs.append(workspaceID)
            }
            focus(id: panels[index].id)
            return panels[index].id
        }
        let identity = Self.identityKey(for: payload)
        // A new Developer run is a new presentation batch even when it reads
        // the same file as an earlier run. Ordinary payloads retain the
        // value-addressed focus/reuse rule below.
        if aggregationKey == nil,
           let existing = panels.first(where: { $0.identityKey == identity }) {
            focus(id: existing.id)
            if let index = panels.firstIndex(where: { $0.id == existing.id }) {
                // Keep the first workspace result as the authoritative owner;
                // repeated transport delivery must not retarget the main
                // surface to a newly-created duplicate history row.
                if let workspaceID { panels[index].workspaceID = workspaceID }
            }
            return existing.id
        }
        // A full panel inventory may contain only explicitly pinned panels.
        // Preserve those pins instead of evicting one to make room for an
        // ordinary repeated-result arrival; the caller can still use the
        // existing pinned panel or explicitly close one.
        guard let id = insert(payload, identityKey: identity, workspaceID: workspaceID) else {
            return focusedID ?? panels.last?.id ?? 0
        }
        // Enforce the curated-stage budget at insertion time, not only when
        // the external scene happens to be open. A one-screen or closed-
        // display session must not accumulate an unbounded fallback stack
        // that later fans out when a monitor is attached.
        enforcePresentationBudget()
        return id
    }

    func workspaceID(for panelID: Int) -> UUID? {
        panels.first(where: { $0.id == panelID })?.workspaceID
    }

    /// Responses use request identity, not body identity: two identical
    /// answers to different requests remain distinct, while streamed chunks
    /// update one tile. A closed/evicted tile is not reopened by later chunks.
    func presentResponse(_ result: WorkspaceResult, isNew: Bool) {
        let identity = "response:\(result.id.uuidString)"
        let matches = panels.indices.filter { panels[$0].identityKey == identity }
        if !matches.isEmpty {
            for index in matches { panels[index].payload = result.payload }
        } else if isNew {
            _ = insert(result.payload, identityKey: identity, workspaceID: result.id)
            enforcePresentationBudget()
        }
    }

    /// Return the workspace identity already owned by this display renderer
    /// for an exact payload identity. A same-run Developer payload is only a
    /// match when its exact section is already present; a new file/result in
    /// that run must still receive its own workspace history row and append to
    /// the existing outer panel.
    func presentedWorkspaceID(for payload: DisplayPayload) -> UUID? {
        let identity = Self.identityKey(for: payload)
        let aggregation = Self.aggregationKey(for: payload)
        for panel in panels {
            if let aggregation {
                guard panel.aggregationKey == aggregation else { continue }
            } else {
                guard panel.aggregationKey == nil, panel.identityKey == identity else { continue }
            }
            for (index, existing) in panel.allPayloads.enumerated()
            where Self.identityKey(for: existing) == identity {
                return panel.allWorkspaceIDs.indices.contains(index)
                    ? panel.allWorkspaceIDs[index] : nil
            }
        }
        return nil
    }

    /// A workspace locator is truthful only while the corresponding live
    /// display panel exists. WorkspaceStore's supporting-content choice can
    /// outlive a window close or a restored session, so views must not use it
    /// alone to claim that content is currently on another screen.
    func containsWorkspaceResult(_ id: UUID) -> Bool {
        panels.contains { panel in panel.allWorkspaceIDs.contains(id) }
    }

    func containsMemoryGraph() -> Bool {
        panels.contains { panel in
            panel.allPayloads.contains(where: Self.isMemoryGraphPayload)
        }
    }

    /// Explicit escape hatch for a user-requested second copy. The panel is
    /// marked pinned so later identical requests still focus the original
    /// identity rather than creating more copies.
    @discardableResult
    func openAdditional(id: Int, workspaceID: UUID? = nil) -> Int? {
        guard let source = panels.first(where: { $0.id == id }) else { return nil }
        // The explicit duplicate path pins the source first so opening the
        // additional copy cannot cause the active presentation to be replaced.
        if let index = panels.firstIndex(where: { $0.id == id }) {
            panels[index].pinned = true
        }
        guard let created = insert(source.payload, identityKey: source.identityKey,
                                   workspaceID: workspaceID ?? source.workspaceID) else {
            return nil
        }
        guard let index = panels.firstIndex(where: { $0.id == created }) else { return created }
        panels[index].appendedPayloads = source.appendedPayloads
        panels[index].appendedWorkspaceIDs = source.appendedWorkspaceIDs
        panels[index].pinned = true
        panels[index].focused = true
        return created
    }

    func pin(id: Int) -> Bool {
        guard let index = panels.firstIndex(where: { $0.id == id }) else { return false }
        panels[index].pinned = true
        focus(id: id)
        return true
    }

    func focus(id: Int) {
        guard panels.contains(where: { $0.id == id }) else { return }
        focusedID = id
        for index in panels.indices { panels[index].focused = panels[index].id == id }
    }

    private func insert(_ payload: DisplayPayload, identityKey: String,
                        workspaceID: UUID?) -> Int? {
        seq += 1
        let step = Self.cascadeStep * CGFloat(panels.count % 8)
        let panel = DisplayWindowPanel(
            id: seq, payload: payload, identityKey: identityKey,
            receivedAt: Date(), workspaceID: workspaceID,
            aggregationKey: Self.aggregationKey(for: payload),
            offset: CGSize(width: step, height: step),
            size: Self.defaultSize
        )
        // Keep the fixed display-window inventory bounded while protecting
        // every explicit pin. If no unpinned panel can be retired, reject the
        // new arrival rather than silently evicting user-pinned content.
        if panels.count >= AppTuning.maxDisplayWindowPanels,
           !panels.contains(where: { !$0.pinned }) {
            return nil
        }
        panels.append(panel)
        if panels.count > AppTuning.maxDisplayWindowPanels {
            let overflow = panels.count - AppTuning.maxDisplayWindowPanels
            let removable = panels.indices.filter { !panels[$0].pinned && panels[$0].id != panel.id }
            for index in removable.prefix(overflow).reversed() {
                panels.remove(at: index)
            }
        }
        focus(id: panel.id)
        return panel.id
    }

    /// Keep the supporting display useful without hiding explicitly pinned
    /// work. Up to four unpinned results share the stage; the oldest unpinned
    /// results are replaced when the bounded stage is full.
    private func enforcePresentationBudget() {
        let unpinned = panels.filter { !$0.pinned }
        let overflow = unpinned.count - AppTuning.maxSupportingStagePanels
        guard overflow > 0 else { return }
        let protectedID = focusedID
        let removable = unpinned.filter { $0.id != protectedID }
        let ids = removable.prefix(overflow).map(\.id)
        panels.removeAll { ids.contains($0.id) }
        if let focusedID, !panels.contains(where: { $0.id == focusedID }) {
            self.focusedID = panels.last?.id
            if let next = self.focusedID { focus(id: next) }
        }
    }

    /// Payload timestamps and workspace UUIDs identify delivery events, not
    /// visual content, so they are intentionally excluded. The remaining
    /// fields are length-prefixed to avoid delimiter collisions and preserve
    /// exact distinctions between research, weather, radar and graph data.
    static func identityKey(for payload: DisplayPayload) -> String {
        func field(_ value: String?) -> String {
            guard let value else { return "-1:" }
            return "\(value.utf8.count):\(value)"
        }
        func fields(_ values: [String]?) -> String {
            guard let values else { return "-1:" }
            return values.map(field).joined(separator: "|")
        }
        let links = payload.links?.map { field($0.label) + field($0.url) }
        let boolField = payload.expectOutput.map { $0 ? "1" : "0" } ?? "-1"
        let intField = payload.chars.map(String.init) ?? "-1"
        let truncatedField = payload.truncated.map { $0 ? "1" : "0" } ?? "-1"
        return [
            field(payload.kind), field(payload.title), field(payload.body),
            fields(payload.images), fields(payload.basemapImages), fields(links),
            field(payload.agent), field(payload.tool), fields(payload.commands),
            field(payload.note), boolField, field(payload.content), intField,
            truncatedField,
        ].joined(separator: "\u{1e}")
    }

    /// A Developer/self-edit run is a single user request even when the
    /// agent reads several files. Group only window-routed Developer payloads
    /// carrying the same backend run ID; ordinary research and weather
    /// requests remain independent panels.
    private static func aggregationKey(for payload: DisplayPayload) -> String? {
        guard payload.surface == .window,
              let runID = payload.runID?.trimmingCharacters(in: .whitespacesAndNewlines),
              !runID.isEmpty,
              let agent = payload.agent?.lowercased(),
              agent.contains("developer") else { return nil }
        return "developer-run:\(runID)"
    }

    private static func isMemoryGraphPayload(_ payload: DisplayPayload) -> Bool {
        let values = [payload.kind, payload.title, payload.tool]
            .compactMap { $0?.lowercased() }
        if values.contains(where: { $0.contains("memory_graph") || $0.contains("memory graph") }) {
            return true
        }
        return payload.images?.contains { $0.lowercased().contains("/graph/memory") } == true
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
        if focusedID == id { focusedID = panels.last?.id; if let focusedID { focus(id: focusedID) } }
    }
}
