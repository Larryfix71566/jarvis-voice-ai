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
    var scrollOffsets: [String: Double] = [:]
    @ObservationIgnored private var config: JarvisConfig?
    @ObservationIgnored private var leases: [UUID: String] = [:]

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
