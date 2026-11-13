import Foundation
import Observation
import JarvisKit

/// One received display payload plus a client-side identity — the payload
/// has no id and two results can be identical (displayResults.ts).
struct DisplayResult: Identifiable, Equatable, Sendable {
    let id: Int
    let payload: DisplayPayload
    let receivedAt: Date
    var workspaceID: UUID? = nil
}

/// APP plan §3 P8/P14 — the native displayResults.ts: DRAWER-routed
/// display payloads only (`surface != "window"`); the router owns the
/// surface split and this store never sees window payloads. Newest FIRST
/// (a results log reads newest-down), bounded at maxDisplayResults.
@MainActor
@Observable
final class DisplayResultStore {
    private(set) var results: [DisplayResult] = []
    var expandedID: Int?
    private var seq = 0

    /// The deterministic "needs your confirmation" rule, one home
    /// (displayResults.ts E1): attention is active iff the NEWEST item
    /// came from a draft-gated tool. Self-clearing — anything newer
    /// replaces it at the head.
    private static let draftTools: Set<String> = ["prepare_commit", "prepare_push", "repo_write_file"]
    var hasPendingDraft: Bool {
        guard let newest = results.first else { return false }
        return Self.draftTools.contains(newest.payload.tool ?? "")
    }

    func apply(_ payload: DisplayPayload, workspaceID: UUID? = nil) {
        if updateExistingAnswer(payload) { return }
        seq += 1
        results = Array(([DisplayResult(id: seq, payload: payload, receivedAt: Date(), workspaceID: workspaceID)] + results)
            .prefix(AppTuning.maxDisplayResults))
        // New results expand once at ingestion, not when a view is recreated.
        expandedID = seq
    }

    /// Returns true even for replay/stale packets: they are consumed, not inserted.
    @discardableResult
    func updateExistingAnswer(_ payload: DisplayPayload) -> Bool {
        guard let answer = payload.answerID, let revision = payload.answerRevision,
              let index = results.firstIndex(where: { $0.payload.answerID == answer }) else { return false }
        let old = results[index]
        if revision > (old.payload.answerRevision ?? 0) {
            results[index] = DisplayResult(id: old.id, payload: payload,
                                          receivedAt: old.receivedAt, workspaceID: old.workspaceID)
        }
        return true
    }

    func remove(id: Int) {
        results.removeAll { $0.id == id }
        if expandedID == id { expandedID = nil }
    }

    func clear() {
        results = []
        expandedID = nil
    }
}
