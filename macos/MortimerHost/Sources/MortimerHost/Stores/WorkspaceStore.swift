import Foundation
import Observation
import JarvisKit
#if os(macOS)
import AppKit
#endif

/// Assigned once by the message router. Content stays in memory, including
/// clipboard payloads; this type deliberately has no persistence conformance.
struct WorkspaceResult: Identifiable, Equatable, Sendable {
    let id: UUID
    let payload: DisplayPayload
    let receivedAt: Date

    init(payload: DisplayPayload, id: UUID = UUID(), receivedAt: Date = Date()) {
        self.id = id
        self.payload = payload
        self.receivedAt = receivedAt
    }
}

enum SupportingDisplayContent: Equatable {
    case result(UUID)
    case memoryGraph
    case skills
    /// A pointer to the selected Skills detail. The detail remains owned by
    /// SkillsStore; this selection only transfers its single visible renderer.
    case skillDetail(String)
    /// MORTIMER_WORKFLOW_VIEWER_PLAN.md — the read-only workflow gallery.
    case workflows
}

enum WorkspaceComparisonSide: String, Sendable {
    case a = "A"
    case b = "B"
}

/// App-owned presentation state. Incoming results never change an existing
/// selection. Closing a tab has no authority over Output or display history.
@MainActor
@Observable
final class WorkspaceStore {
    private(set) var results: [WorkspaceResult] = []
    private(set) var activeID: UUID?
    private(set) var comparisonID: UUID?
    private(set) var pinnedIDs: Set<UUID> = []
    private(set) var unreadIDs: Set<UUID> = []
    private(set) var showsConversation = true
    private(set) var showsMemoryGraph = false
    private(set) var showsAtlas = false
    private(set) var showsSkills = false
    /// MORTIMER_WORKFLOW_VIEWER_PLAN.md: a standalone main view alongside
    /// Skills, Atlas, Memory Graph, and Conversation.
    private(set) var showsWorkflows = false
    private(set) var supportingContent: SupportingDisplayContent?
    /// CC7a.2 (WS-17, plan §7.2 "New result while reading"): a result that
    /// arrived quietly while something other than the conversation was on
    /// the stage. The stage shows "New: … Show / Dismiss" for it; the
    /// arrival itself never changes the selection or the view.
    private(set) var arrivalNoticeID: UUID?
    /// CC7a.2: on while layout 2 shows the conversation thread. Every
    /// arrival then follows `receive(_:quietly:)` (opens on the
    /// conversation, a "New" notice elsewhere), whichever route delivered
    /// it. Off by default, so other layouts and existing callers
    /// keep the pre-CC7a behaviour. Stages report through
    /// `setQuietArrivals(_:owner:)`; tests may set it directly.
    var quietArrivals = false
    /// Each stage's own answer, keyed by its identity (Codex review of PR
    /// #164): on a layout switch the new stage appears before the old one
    /// disappears, so a departing stage must remove only its own entry and
    /// never overwrite its replacement's.
    @ObservationIgnored private var quietArrivalOwners: [UUID: Bool] = [:]
    var showComparisonOnCompact = false
    private(set) var comparisonSide: WorkspaceComparisonSide = .a
    let exporter = WorkspaceExportCoordinator()
    let memoryGraph = MemoryGraphStore(persistenceKey: "mortimer.interface.memoryGraph.view")
    let workflows = WorkflowsStore()
    @ObservationIgnored private var presentations: [UUID: WorkspaceResultPresentation] = [:]
    @ObservationIgnored private var resultGraphs: [UUID: MemoryGraphStore] = [:]
    private(set) var scrollOffsets: [UUID: Double] = [:]
    private var hasReceivedResult = false
    private var inventoryRevision = 0
    private var hasChosenPresentation = false
    private let historyLimit: Int
    private let pinLimit: Int

    init(historyLimit: Int = AppTuning.maxDisplayResults, pinLimit: Int = 20) {
        self.historyLimit = max(1, historyLimit)
        self.pinLimit = max(1, pinLimit)
    }

    var activeResult: WorkspaceResult? { results.first { $0.id == activeID } }
    var comparisonResult: WorkspaceResult? { results.first { $0.id == comparisonID } }

    /// Identity lookup used by the app-scoped display router when a repeated
    /// window payload is already represented by the shared workspace store.
    func containsResult(_ id: UUID) -> Bool {
        results.contains { $0.id == id }
    }

    /// Snapshot consumed by the command-console router. IDs are stable for the
    /// session; the count is a conservative revision for inventory checks.
    var consoleInventory: [String: Any] {
        let visibleResults = results.filter { !$0.payload.isProtectedLocal }
        let visibleIDs = Set(visibleResults.map(\.id))
        return ["revision": inventoryRevision,
         "mode": showsConversation ? "conversation" : (showsSkills ? "skills" : (showsMemoryGraph ? "memory" : (showsAtlas ? "atlas" : (showsWorkflows ? "workflows" : "results")))),
         "active_result_id": activeID.flatMap { visibleIDs.contains($0) ? $0.uuidString : nil } as Any,
         "focused_panel_id": NSNull(),
         "results": visibleResults.enumerated().map { index, result in
             ["id": result.id.uuidString,
              "title": String((result.payload.title ?? "Result").prefix(120)),
              "index": index,
              "pinned": pinnedIDs.contains(result.id),
              "can_connections": MemoryGraphSource.imageURL(result.payload) != nil]
         },
         "comparison": comparisonID.flatMap { visibleIDs.contains($0) ? $0.uuidString : nil } as Any,
         "atlas": ["available": true]]
    }

    /// Codable form sent to the Supervisor for voice target resolution. This
    /// intentionally mirrors only the bounded inventory contract; it never
    /// serializes display bodies, transcript text, paths or image bytes.
    var consoleInventoryJSON: JSONValue {
        // Protected/local results are visible only in the local result surface.
        // Do not forward even their titles or identifiers to the voice supervisor.
        let visibleResults = results.filter { !$0.payload.isProtectedLocal }
        let visibleIDs = Set(visibleResults.map(\.id))
        let resultValues: [JSONValue] = visibleResults.enumerated().map { index, result in
            .object([
                "id": .string(result.id.uuidString),
                "title": .string(String((result.payload.title ?? "Result").prefix(120))),
                "index": .number(Double(index)),
                "pinned": .bool(pinnedIDs.contains(result.id)),
                "can_connections": .bool(MemoryGraphSource.imageURL(result.payload) != nil),
            ])
        }
        let panelValues: [JSONValue] = ConsolePanel.allCases.map { panel in
            .object([
                "id": .string(panel.rawValue),
                "kind": .string(panel.rawValue),
                "title": .string(panel.rawValue.capitalized),
                "screen_id": .null,
            ])
        }
        // WS-21 D2: screens are listed by ConsoleActionCoordinator from
        // placement's own identities (the hardware display UUID), never by
        // NSScreen name, so a voice move names a screen placement knows.
        let screenValues: [JSONValue] = []
        let mode: String
        if showsConversation { mode = "conversation" }
        else if showsSkills { mode = "skills" }
        else if showsMemoryGraph { mode = "memory" }
        else if showsAtlas { mode = "atlas" }
        else if showsWorkflows { mode = "workflows" }
        else { mode = "results" }
        let activeValue: JSONValue = activeID.flatMap {
            visibleIDs.contains($0) ? .string($0.uuidString) : nil
        } ?? .null
        let comparisonValue: JSONValue = comparisonID.flatMap {
            visibleIDs.contains($0) ? .string($0.uuidString) : nil
        } ?? .null
        let graphValue: JSONValue = showsMemoryGraph ? .string("memory") : .null
        let nodeValue: JSONValue = memoryGraph.selectedNode.map { .string($0.id) } ?? .null
        let selection: JSONValue = .object([
            "graph_id": graphValue,
            "node_id": nodeValue,
            "edge_id": .null,
            "group_id": .null,
        ])
        let actions: [JSONValue] = ConsoleAction.allCases.map { action in .string(action.rawValue) }
        let payload: [String: JSONValue] = [
            "revision": .number(Double(inventoryRevision)),
            "mode": .string(mode),
            "active_result_id": activeValue,
            "focused_panel_id": .null,
            "results": .array(Array(resultValues.prefix(100))),
            "panels": .array(Array(panelValues.prefix(6))),
            "screens": .array(Array(screenValues.prefix(8))),
            "selection": selection,
            "attachments": .array([]),
            "available_actions": .array(actions),
            "atlas": .object(["available": .bool(true)]),
            "comparison": comparisonValue,
        ]
        return .object(payload)
    }

    /// The revision is part of every console request. Exposing it read-only
    /// lets the message router reject a stale target before the coordinator
    /// touches any store.
    var consoleRevision: Int { inventoryRevision }

    /// App-scoped stores such as PanelStore can change the inventory without
    /// owning result selection. They use this hook to make delayed voice
    /// requests stale before a panel mutation can be retargeted.
    func noteConsoleMutation() { inventoryRevision += 1 }

    /// `answersCurrentRequest`: the caller has established that this result
    /// answers what Larry just asked and belongs on the main stage (see
    /// `ArrivalIntent`). Defaults to false, so an arrival nobody vouched
    /// for never opens by itself.
    func receive(_ result: WorkspaceResult, answersCurrentRequest: Bool = false) {
        receive(result, quietly: quietArrivals, answersCurrentRequest: answersCurrentRequest)
    }

    /// `quietly` (CC7a.2, conversation thread on): the result never
    /// interrupts something being read. On the conversation, a result that
    /// answers what Larry just asked opens, like Open on its card (Larry,
    /// 10-03, after the UI2-23 run: "when I requested the weather ... it
    /// didn't focus on the weather card, that should happen
    /// automatically"); anything else, such as a background job finishing
    /// later (Codex review of #169), stays a card in the thread. While
    /// another result or view is shown, it joins unread and raises the
    /// "New" notice. If no result is active yet it becomes the active one
    /// without being shown. Off: the pre-CC7a behaviour.
    func receive(_ result: WorkspaceResult, quietly: Bool, answersCurrentRequest: Bool = false) {
        guard !results.contains(where: { $0.id == result.id }) else { return }
        results.append(result)
        inventoryRevision += 1
        if quietly {
            hasReceivedResult = true
            if showsConversation && answersCurrentRequest {
                select(result.id)
            } else {
                if activeID == nil { activeID = result.id }
                unreadIDs.insert(result.id)
                if !showsConversation { arrivalNoticeID = result.id }
            }
            trimHistory()
            return
        }
        if !hasReceivedResult {
            activeID = result.id
            // Opening the graph or returning to conversation can happen
            // before any result arrives. Preserve that explicit choice.
            if hasChosenPresentation {
                unreadIDs.insert(result.id)
            } else {
                showsConversation = false
            }
        } else {
            unreadIDs.insert(result.id)
        }
        hasReceivedResult = true
        trimHistory()
    }

    /// Streaming replaces the body under the same identity, preserving the
    /// tab, pin, comparison, inspector and scroll state. It does not change
    /// the inventory contract or steal selection on each token.
    func updateResponse(_ result: WorkspaceResult) {
        guard let index = results.firstIndex(where: { $0.id == result.id }) else { return }
        results[index] = result
    }

    func select(_ id: UUID) {
        guard results.contains(where: { $0.id == id }) else { return }
        if comparisonID == id { comparisonID = activeID }
        activeID = id
        showsAtlas = false
        showsSkills = false
        showsWorkflows = false
        showsConversation = false
        showsMemoryGraph = false
        unreadIDs.remove(id)
        if arrivalNoticeID == id { arrivalNoticeID = nil }
        inventoryRevision += 1
    }

    /// A stage reports whether it shows the conversation thread.
    func setQuietArrivals(_ on: Bool, owner: UUID) {
        quietArrivalOwners[owner] = on
        quietArrivals = quietArrivalOwners.values.contains(true)
    }

    /// A stage that leaves the screen withdraws only its own report.
    func releaseQuietArrivals(owner: UUID) {
        quietArrivalOwners.removeValue(forKey: owner)
        quietArrivals = quietArrivalOwners.values.contains(true)
    }

    /// "Dismiss" on the arrival notice. The result stays unread in the
    /// thread and the Results menu.
    func dismissArrivalNotice() { arrivalNoticeID = nil }

    @discardableResult
    func selectAdjacentResult(step: Int) -> Bool {
        guard !results.isEmpty, let activeID,
              let index = results.firstIndex(where: { $0.id == activeID }) else { return false }
        let next = min(max(index + step, 0), results.count - 1)
        guard next != index else { return false }
        select(results[next].id)
        return true
    }

    func returnToConversation() {
        hasChosenPresentation = true
        showsAtlas = false
        showsSkills = false
        showsWorkflows = false
        showsMemoryGraph = false
        showsConversation = true
        // The new result's card is in the thread now; the notice is done.
        arrivalNoticeID = nil
        inventoryRevision += 1
    }
    func openMemoryGraph() {
        hasChosenPresentation = true
        showsMemoryGraph = true
        showsAtlas = false
        showsSkills = false
        showsWorkflows = false
        showsConversation = false
        inventoryRevision += 1
    }
    func openAtlas() {
        hasChosenPresentation = true
        showsAtlas = true
        showsSkills = false
        showsWorkflows = false
        showsMemoryGraph = false
        showsConversation = false
        inventoryRevision += 1
    }

    /// MORTIMER_WORKFLOW_VIEWER_PLAN.md — view_set mode "workflows".
    func openWorkflows() {
        hasChosenPresentation = true
        showsWorkflows = true
        showsAtlas = false
        showsSkills = false
        showsMemoryGraph = false
        showsConversation = false
        inventoryRevision += 1
    }

    func returnToWorkspace() {
        hasChosenPresentation = true
        showsAtlas = false
        showsSkills = false
        showsWorkflows = false
        showsMemoryGraph = false
        showsConversation = false
        inventoryRevision += 1
    }

    func openSkills() {
        hasChosenPresentation = true
        showsSkills = true
        showsWorkflows = false
        showsAtlas = false
        showsMemoryGraph = false
        showsConversation = false
        inventoryRevision += 1
    }

    /// Returns a transferred skill detail to the main Skills workspace and
    /// releases the supporting stage's pointer to it.
    func returnSkillDetailsToMain() {
        guard case .some(.skillDetail(_)) = supportingContent else { return }
        supportingContent = nil
        openSkills()
    }

    @discardableResult
    func sendToDisplay(_ content: SupportingDisplayContent) -> Bool {
        if case .result(let id) = content {
            guard let result = results.first(where: { $0.id == id }),
                  !result.payload.isProtectedLocal else { return false }
        }
        supportingContent = content
        trimHistory()
        return true
    }

    func showOriginalDisplayPanels() { supportingContent = nil; trimHistory() }
    var supportingResult: WorkspaceResult? {
        guard case .result(let id) = supportingContent else { return nil }
        return results.first { $0.id == id }
    }

    func presentation(for result: WorkspaceResult) -> WorkspaceResultPresentation {
        if let existing = presentations[result.id] { return existing }
        let state = WorkspaceResultPresentation(hasConnections: MemoryGraphSource.imageURL(result.payload) != nil)
        presentations[result.id] = state
        return state
    }

    func graphStore(for result: WorkspaceResult, url: URL) -> MemoryGraphStore {
        if let existing = resultGraphs[result.id] { return existing }
        let store = MemoryGraphStore(query: MemoryGraphSource.query(url))
        resultGraphs[result.id] = store
        return store
    }

    @discardableResult
    func pin(_ id: UUID) -> Bool {
        guard results.contains(where: { $0.id == id }) else { return false }
        guard pinnedIDs.contains(id) || pinnedIDs.count < pinLimit else { return false }
        pinnedIDs.insert(id)
        return true
    }

    func unpin(_ id: UUID) { pinnedIDs.remove(id); trimHistory() }

    @discardableResult
    func compare(with id: UUID?) -> Bool {
        guard let id else {
            comparisonID = nil
            comparisonSide = .a
            trimHistory()
            inventoryRevision += 1
            return true
        }
        guard activeID != nil, id != activeID,
              results.contains(where: { $0.id == id }) else { return false }
        comparisonID = id
        unreadIDs.remove(id)
        showsConversation = false
        showsMemoryGraph = false
        showsWorkflows = false   // the comparison must be visible
        inventoryRevision += 1
        return true
    }

    /// Select which member of a comparison receives the active reader focus.
    /// This is presentation state only; both result identities remain stable.
    @discardableResult
    func setComparisonSide(_ side: WorkspaceComparisonSide) -> Bool {
        guard comparisonID != nil else { return false }
        guard comparisonSide != side else { return true }
        comparisonSide = side
        inventoryRevision += 1
        return true
    }

    /// Shared scroll mutation used by pointer and voice paths. The renderer
    /// reports its real offset back through `rememberScroll`; voice commands
    /// use a bounded viewport step and never mutate result content.
    @discardableResult
    func scrollResult(_ id: UUID, direction: String, viewport: Double = 800) -> Bool {
        guard results.contains(where: { $0.id == id }), viewport.isFinite, viewport > 0 else { return false }
        let step = viewport * 0.8
        let current = scrollOffsets[id] ?? 0
        switch direction {
        case "up": scrollOffsets[id] = max(0, current - step)
        case "down": scrollOffsets[id] = current + step
        case "top": scrollOffsets[id] = 0
        case "bottom": scrollOffsets[id] = max(current, 1_000_000)
        default: return false
        }
        inventoryRevision += 1
        return true
    }

    @discardableResult
    func selectSource(_ index: Int, for id: UUID) -> Bool {
        guard let result = results.first(where: { $0.id == id }),
              let links = result.payload.links, links.indices.contains(index) else { return false }
        presentation(for: result).selectedSource = index
        inventoryRevision += 1
        return true
    }

    @discardableResult
    func selectImage(_ index: Int, for id: UUID) -> Bool {
        guard let result = results.first(where: { $0.id == id }),
              let images = result.payload.images, images.indices.contains(index) else { return false }
        presentation(for: result).selectedImage = index
        inventoryRevision += 1
        return true
    }

    @discardableResult
    func setSourceInspector(_ open: Bool, for id: UUID) -> Bool {
        guard let result = results.first(where: { $0.id == id }) else { return false }
        presentation(for: result).showsInspector = open
        inventoryRevision += 1
        return true
    }

    @discardableResult
    func markSourceOpened(_ index: Int, for id: UUID) -> URL? {
        guard let result = results.first(where: { $0.id == id }),
              let links = result.payload.links, links.indices.contains(index),
              let url = WorkspaceResultExport.sourceURL(links[index].url) else { return nil }
        presentation(for: result).openedSource = index
        inventoryRevision += 1
        return url
    }

    func rememberScroll(_ offset: Double, for id: UUID) {
        guard offset.isFinite, results.contains(where: { $0.id == id }) else { return }
        scrollOffsets[id] = max(0, offset)
    }

    func close(_ id: UUID) {
        guard let index = results.firstIndex(where: { $0.id == id }) else { return }
        remove(id)
        inventoryRevision += 1
        if activeID == id {
            activeID = comparisonID ?? (results.isEmpty ? nil : results[min(index, results.count - 1)].id)
            comparisonID = nil
        }
        if comparisonID == id { comparisonID = nil }
        // Standalone views stay selected when the last result tab closes;
        // closing a result says nothing about the selected view.
        if activeID == nil && !showsMemoryGraph && !showsWorkflows &&
            !showsSkills && !showsAtlas {
            showsConversation = true
        }
    }

    private func remove(_ id: UUID) {
        if supportingContent == .result(id) { supportingContent = nil }
        if arrivalNoticeID == id { arrivalNoticeID = nil }
        presentations.removeValue(forKey: id)
        resultGraphs.removeValue(forKey: id)?.cancel()
        results.removeAll { $0.id == id }
        pinnedIDs.remove(id)
        unreadIDs.remove(id)
        scrollOffsets.removeValue(forKey: id)
    }

    private func trimHistory() {
        // Pins and the two panes are protected, with explicit finite bounds.
        // Retain historyLimit other results so reading never evicts a pane.
        let protected = pinnedIDs.union([activeID, comparisonID, supportingResult?.id].compactMap { $0 })
        let ordinary = results.filter { !protected.contains($0.id) }
        for result in ordinary.prefix(max(0, ordinary.count - historyLimit)) { remove(result.id) }
    }
}
