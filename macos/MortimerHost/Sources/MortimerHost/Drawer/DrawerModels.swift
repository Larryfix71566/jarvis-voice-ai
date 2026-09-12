import Foundation
import Observation
import JarvisKit

/// One owner for both docked and floating presentations. Visibility leases
/// prevent an outgoing view from stopping its replacement's polling loop.
@MainActor
@Observable
final class DrawerModels {
    private(set) var repo: RepoViewModel?
    private(set) var edit: EditViewModel?
    private(set) var memory: MemoryViewModel?
    private(set) var runs: RunsViewModel?
    private(set) var costs: CostsViewModel?
    private(set) var council: CouncilViewModel?
    /// Remembered reading position per tab, restored when a presentation
    /// of that tab mounts (dock → pop-out → dock keeps the place).
    var scrollOffsets: [String: Double] = [:]
    @ObservationIgnored private var config: JarvisConfig?
    @ObservationIgnored private var leases: [UUID: String] = [:]
    /// Closure plan C1.4 (gap G04): at most ONE mounted presentation of a
    /// tab records scroll offsets — the most recently mounted one. Without
    /// this, a docked and a detached presentation of the same tab (both
    /// alive during a pop-out transition) would overwrite each other's
    /// offset on every scroll event. The writer is a lease, not the
    /// offset: releasing it never discards the remembered position.
    @ObservationIgnored private var scrollWriters: [String: UUID] = [:]

    func configure(_ next: JarvisConfig) {
        guard config != next else { return }
        let api = AdminAPI(config: next), costsAPI = CostsAPI(config: next)
        if let repo { repo.updateAPI(api) } else { repo = RepoViewModel(api: api) }
        if let edit { edit.updateAPI(api) } else { edit = EditViewModel(api: api) }
        if let memory { memory.updateAPI(api) } else { memory = MemoryViewModel(api: api) }
        if let runs { runs.updateAPI(api) } else { runs = RunsViewModel(api: api) }
        if let costs { costs.updateAPI(costsAPI) } else { costs = CostsViewModel(api: costsAPI) }
        if let council { council.updateAPI(api) } else { council = CouncilViewModel(api: api) }
        config = next
        for tab in Set(leases.values) { start(tab) }
    }

    func acquire(_ id: UUID, tab: String) {
        if leases[id] == tab { return }
        release(id)
        let alreadyVisible = leases.values.contains(tab)
        leases[id] = tab
        if !alreadyVisible { start(tab) }
    }

    func release(_ id: UUID) {
        guard let tab = leases.removeValue(forKey: id), !leases.values.contains(tab) else { return }
        stop(tab)
    }

    func visibleCount(for tab: String) -> Int { leases.values.filter { $0 == tab }.count }

    // MARK: - Scroll-offset writer arbitration (C1.4)

    /// The presentation `id` becomes the tab's scroll writer, displacing any
    /// earlier writer. Called when a presentation of `tab` appears.
    func claimScrollWriter(_ id: UUID, tab: String) {
        scrollWriters[tab] = id
    }

    /// Only the current writer relinquishes; a stale presentation
    /// disappearing after its replacement claimed the tab changes nothing.
    func releaseScrollWriter(_ id: UUID, tab: String) {
        if scrollWriters[tab] == id { scrollWriters[tab] = nil }
    }

    /// Records `offset` for `tab` only when `id` holds the writer lease.
    /// Returns whether the offset was recorded (for tests and callers that
    /// want to know they were ignored).
    @discardableResult
    func recordScroll(_ offset: Double, tab: String, from id: UUID) -> Bool {
        guard offset.isFinite, scrollWriters[tab] == id else { return false }
        scrollOffsets[tab] = max(0, offset)
        return true
    }

    func isScrollWriter(_ id: UUID, tab: String) -> Bool { scrollWriters[tab] == id }

    private func start(_ tab: String) {
        switch tab {
        case "repo": repo?.startPolling()
        case "edit": edit?.startPolling()
        case "memory": memory?.startPolling()
        case "runs": runs?.startPolling()
        case "costs": costs?.startPolling()
        case "agents": council?.startPolling()
        default: break
        }
    }

    private func stop(_ tab: String) {
        switch tab {
        case "repo": repo?.stopPolling()
        case "edit": edit?.stopPolling()
        case "memory": memory?.stopPolling()
        case "runs": runs?.stopPolling()
        case "costs": costs?.stopPolling()
        case "agents": council?.stopPolling()
        default: break
        }
    }
}
