import Foundation
import Observation
import JarvisKit

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
    private(set) var supportingContent: SupportingDisplayContent?
    var showComparisonOnCompact = false
    let memoryGraph = MemoryGraphStore(persistenceKey: "mortimer.interface.memoryGraph.view")
    @ObservationIgnored private var resultGraphs: [UUID: MemoryGraphStore] = [:]
    private(set) var scrollOffsets: [UUID: Double] = [:]
    private var hasReceivedResult = false
    private let historyLimit: Int
    private let pinLimit: Int

    init(historyLimit: Int = AppTuning.maxDisplayResults, pinLimit: Int = 20) {
        self.historyLimit = max(1, historyLimit)
        self.pinLimit = max(1, pinLimit)
    }

    var activeResult: WorkspaceResult? { results.first { $0.id == activeID } }
    var comparisonResult: WorkspaceResult? { results.first { $0.id == comparisonID } }

    func receive(_ result: WorkspaceResult) {
        guard !results.contains(where: { $0.id == result.id }) else { return }
        results.append(result)
        if !hasReceivedResult {
            activeID = result.id
            showsConversation = false
        } else {
            unreadIDs.insert(result.id)
        }
        hasReceivedResult = true
        trimHistory()
    }

    func select(_ id: UUID) {
        guard results.contains(where: { $0.id == id }) else { return }
        if comparisonID == id { comparisonID = activeID }
        activeID = id
        showsConversation = false
        showsMemoryGraph = false
        unreadIDs.remove(id)
    }

    func returnToConversation() { showsConversation = true }
    func openMemoryGraph() { showsMemoryGraph = true; showsConversation = false }
    func returnToWorkspace() { showsConversation = false }

    @discardableResult
    func sendToDisplay(_ content: SupportingDisplayContent) -> Bool {
        if case .result(let id) = content, !results.contains(where: { $0.id == id }) { return false }
        supportingContent = content
        trimHistory()
        return true
    }

    func showOriginalDisplayPanels() { supportingContent = nil; trimHistory() }
    var supportingResult: WorkspaceResult? {
        guard case .result(let id) = supportingContent else { return nil }
        return results.first { $0.id == id }
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

    func compare(with id: UUID?) {
        guard let id else { comparisonID = nil; trimHistory(); return }
        guard activeID != nil, id != activeID,
              results.contains(where: { $0.id == id }) else { return }
        comparisonID = id
        unreadIDs.remove(id)
        showsConversation = false
        showsMemoryGraph = false
    }

    func rememberScroll(_ offset: Double, for id: UUID) {
        guard offset.isFinite, results.contains(where: { $0.id == id }) else { return }
        scrollOffsets[id] = max(0, offset)
    }

    func close(_ id: UUID) {
        guard let index = results.firstIndex(where: { $0.id == id }) else { return }
        remove(id)
        if activeID == id {
            activeID = comparisonID ?? (results.isEmpty ? nil : results[min(index, results.count - 1)].id)
            comparisonID = nil
        }
        if comparisonID == id { comparisonID = nil }
        if activeID == nil && !showsMemoryGraph { showsConversation = true }
    }

    private func remove(_ id: UUID) {
        if supportingContent == .result(id) { supportingContent = nil }
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
