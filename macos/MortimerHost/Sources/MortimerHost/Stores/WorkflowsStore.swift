import Foundation
import Observation
import JarvisKit

/// MORTIMER_WORKFLOW_VIEWER_PLAN.md (layout C, Larry 2026-09-25): the three
/// gallery groups, in display order.
enum WorkflowGroup: String, CaseIterable, Identifiable, Sendable {
    case voice, rules, drafts

    var id: String { rawValue }

    var title: String {
        switch self {
        case .voice: return "Voice · supervisor"
        case .rules: return "Standing rules"
        case .drafts: return "Drafts · review me"
        }
    }

    static func of(_ workflow: WorkflowDetail) -> WorkflowGroup {
        if workflow.draft { return .drafts }
        return workflow.isVoice ? .voice : .rules
    }
}

/// State of the read-only workflow viewer: what `GET /api/workflows` returned,
/// the filter text, and which workflow's flow is open (nil = the gallery).
/// Loaded once per app session unless forced; the viewer never writes.
@MainActor
@Observable
final class WorkflowsStore {
    private(set) var workflows: [WorkflowDetail] = []
    private(set) var enabled = true
    private(set) var matchThreshold = 0.35
    private(set) var loading = false
    private(set) var loaded = false
    private(set) var error: String?
    /// `WorkflowDetail.id` (its file) of the open workflow; nil = the gallery.
    private(set) var selectedID: String?
    var query = ""
    @ObservationIgnored private var request: Task<Void, Never>?
    @ObservationIgnored private var generation = 0

    /// One group's members, filtered by `query` unless `filtered` is false.
    /// Voice workflows sort by priority (lowest wins when two match), then
    /// name; the other groups by name.
    func section(_ group: WorkflowGroup, filtered: Bool = true) -> [WorkflowDetail] {
        let members = workflows.filter { WorkflowGroup.of($0) == group && (!filtered || matches($0)) }
        switch group {
        case .voice:
            return members.sorted { ($0.priority, $0.name, $0.id) < ($1.priority, $1.name, $1.id) }
        case .rules, .drafts:
            return members.sorted { ($0.name, $0.id) < ($1.name, $1.id) }
        }
    }

    /// Every workflow in gallery order, ignoring the filter: the order
    /// "Next" walks and "workflow n of N" counts.
    var ordered: [WorkflowDetail] {
        WorkflowGroup.allCases.flatMap { section($0, filtered: false) }
    }

    var hasVisibleMatches: Bool {
        WorkflowGroup.allCases.contains { !section($0).isEmpty }
    }

    func matches(_ workflow: WorkflowDetail) -> Bool {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return true }
        let haystack = ([workflow.name, workflow.when] + workflow.steps)
            .joined(separator: "\n").lowercased()
        return haystack.contains(needle)
    }

    var selected: WorkflowDetail? {
        guard let selectedID else { return nil }
        return workflows.first { $0.id == selectedID }
    }

    /// 1-based position of the open workflow in `ordered`, and the total.
    var position: (index: Int, count: Int)? {
        let all = ordered
        guard let selectedID, let index = all.firstIndex(where: { $0.id == selectedID }) else { return nil }
        return (index + 1, all.count)
    }

    /// The workflow after the open one, wrapping at the end; nil when fewer
    /// than two exist.
    var next: WorkflowDetail? {
        let all = ordered
        guard all.count > 1, let selectedID,
              let index = all.firstIndex(where: { $0.id == selectedID }) else { return nil }
        return all[(index + 1) % all.count]
    }

    func select(_ id: String) {
        guard workflows.contains(where: { $0.id == id }) else { return }
        selectedID = id
    }

    func showNext() {
        if let next { selectedID = next.id }
    }

    func showGallery() { selectedID = nil }

    func apply(_ response: WorkflowsResponse) {
        workflows = response.workflows
        enabled = response.enabled
        matchThreshold = response.matchThreshold
        error = response.ok ? nil : (response.error ?? "The workflows could not be read.")
        // A failed read is not "loaded": the next open (or Reload) tries again.
        loaded = response.ok
        loading = false
        if let selectedID, !workflows.contains(where: { $0.id == selectedID }) {
            self.selectedID = nil
        }
    }

    func load(api: AdminAPI, force: Bool = false) {
        load(force: force) { try await api.workflows() }
    }

    func load(force: Bool = false,
              fetch: @escaping @Sendable () async throws -> WorkflowsResponse) {
        guard force || (!loaded && !loading) else { return }
        request?.cancel()
        generation += 1
        let current = generation
        loading = true
        error = nil
        request = Task { [weak self] in
            do {
                let response = try await fetch()
                guard !Task.isCancelled, let self, self.generation == current else { return }
                self.apply(response)
                self.request = nil
            } catch {
                guard !Task.isCancelled, let self, self.generation == current else { return }
                self.error = error is JarvisError ? TabStateMapper.fromError(error).0 : error.localizedDescription
                self.loading = false
                self.request = nil
            }
        }
    }
}
