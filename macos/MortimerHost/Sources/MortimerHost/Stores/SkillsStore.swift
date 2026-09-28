import Foundation
import Observation
import JarvisKit

/// Shared, ephemeral navigation state for the Skills workspace and the
/// Command Console dispatcher. Skill packages and run evidence remain owned by
/// the backend; this store only publishes bounded identities and selection.
@MainActor
@Observable
final class SkillsStore {
    struct VoiceDraftPreview: Equatable {
        let id: String
        let skillID: String
        let taskBrief: String
        let expiresAt: Date
    }
    struct VoiceDraftRequest: Equatable {
        let skillID: String
        let taskBrief: String
    }

    private(set) var selectedSkillID: String?
    private(set) var selectedTab = "overview"
    private(set) var selectedStepID: String?
    private(set) var selectedRunID: String?
    private(set) var selectedExampleID: String?
    private(set) var searchQuery = ""
    private(set) var stateFilter = "all"
    private(set) var categoryFilter = "all"
    /// Counts accepted navigation requests, including repeated selections.
    /// A repeated voice request can be meaningful after compact Back even when
    /// the selected ID/tab is unchanged and the durable navigation state is not.
    private(set) var navigationRequestRevision = 0
    private(set) var catalogInventory: [JSONValue] = []
    private(set) var processInventoryBySkill: [String: [JSONValue]] = [:]
    private(set) var runInventoryBySkill: [String: [JSONValue]] = [:]
    private(set) var revision = 0
    private(set) var pendingVoiceDraft: VoiceDraftRequest?

    func displayName(for skillID: String) -> String? {
        catalogInventory.first { $0["skill_id"]?.stringValue == skillID }?["display_name"]?.stringValue
    }

    @ObservationIgnored var onInventoryMutation: (() -> Void)?
    /// Full loaded catalog membership validates pointer-driven selection and
    /// related IDs. `catalogInventory` below remains a small shared/voice
    /// inventory so loading many pages never expands model-visible context.
    @ObservationIgnored private var skillIDs: Set<String> = []
    @ObservationIgnored private var categories: Set<String> = ["home", "surveillance", "finance"]
    @ObservationIgnored private var stepIDsBySkill: [String: Set<String>] = [:]
    @ObservationIgnored private var runIDsBySkill: [String: Set<String>] = [:]
    @ObservationIgnored private var exampleIDsBySkill: [String: Set<String>] = [:]
    @ObservationIgnored private var voiceDraftPreviews: [String: VoiceDraftPreview] = [:]
    /// Small process-local cache for immutable package detail. The SHA-256
    /// revision is part of the key, so a changed package can never reuse the
    /// previous detail while navigating away and back.
    @ObservationIgnored private var detailCache: [String: JSONValue] = [:]
    @ObservationIgnored private var detailCacheOrder: [String] = []
    @ObservationIgnored private var packageRevisionBySkill: [String: String] = [:]

    func cachedDetail(skillID: String, revision: String?) -> JSONValue? {
        guard let revision, Self.validDigest(revision) else { return nil }
        let key = Self.detailCacheKey(skillID: skillID, revision: revision)
        guard let value = detailCache[key] else { return nil }
        detailCacheOrder.removeAll { $0 == key }
        detailCacheOrder.append(key)
        return value
    }

    func cacheDetail(_ detail: JSONValue, skillID: String, revision: String?) {
        guard let revision, Self.validDigest(revision),
              packageRevisionBySkill[skillID] == revision.lowercased(),
              detail["skill_id"]?.stringValue == skillID,
              detail["revision"]?.stringValue?.lowercased() == revision.lowercased() else { return }
        let key = Self.detailCacheKey(skillID: skillID, revision: revision)
        // A skill ID has one active package revision in a catalog. Remove its
        // older revisions so the cache stays bounded during repeated updates.
        let prefix = "\(skillID):"
        let staleKeys = detailCache.keys.filter { $0.hasPrefix(prefix) && $0 != key }
        for stale in staleKeys {
            detailCache.removeValue(forKey: stale)
            detailCacheOrder.removeAll { $0 == stale }
        }
        detailCache[key] = detail
        detailCacheOrder.removeAll { $0 == key }
        detailCacheOrder.append(key)
        while detailCacheOrder.count > 32 {
            detailCache.removeValue(forKey: detailCacheOrder.removeFirst())
        }
    }

    func resolveDetail(
        skillID: String,
        revision: String?,
        load: () async throws -> JSONValue
    ) async throws -> JSONValue {
        if let cached = cachedDetail(skillID: skillID, revision: revision) { return cached }
        let loaded = try await load()
        guard loaded["skill_id"]?.stringValue == skillID,
              revision.map({ loaded["revision"]?.stringValue?.lowercased() == $0.lowercased() }) ?? true else {
            throw JarvisError.decoding("skill detail identity or revision mismatch")
        }
        cacheDetail(loaded, skillID: skillID, revision: revision)
        return loaded
    }

    /// Preview payloads stay in process memory and expire quickly. They are
    /// intentionally excluded from every console inventory representation.
    func makeVoiceDraftPreview(skillID: String, taskBrief: String, now: Date = .now) -> VoiceDraftPreview? {
        guard Self.validID(skillID), skillID.unicodeScalars.count <= 64,
              !taskBrief.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              taskBrief.unicodeScalars.count <= 8_000, !skillIDs.contains(skillID) else { return nil }
        voiceDraftPreviews = voiceDraftPreviews.filter { $0.value.expiresAt > now }
        guard voiceDraftPreviews.count < 8 else { return nil }
        let preview = VoiceDraftPreview(id: UUID().uuidString.lowercased(), skillID: skillID,
                                        taskBrief: taskBrief, expiresAt: now.addingTimeInterval(300))
        voiceDraftPreviews[preview.id] = preview
        return preview
    }

    func consumeVoiceDraftPreview(_ id: String, now: Date = .now) -> Bool {
        voiceDraftPreviews = voiceDraftPreviews.filter { $0.value.expiresAt > now }
        guard let preview = voiceDraftPreviews.removeValue(forKey: id), preview.expiresAt > now,
              !skillIDs.contains(preview.skillID) else { return false }
        pendingVoiceDraft = VoiceDraftRequest(skillID: preview.skillID, taskBrief: preview.taskBrief)
        return true
    }

    func takePendingVoiceDraft() -> VoiceDraftRequest? {
        defer { pendingVoiceDraft = nil }
        return pendingVoiceDraft
    }

    var selectedProcessInventory: [JSONValue] {
        selectedSkillID.flatMap { processInventoryBySkill[$0] } ?? []
    }

    var selectedRunInventory: [JSONValue] {
        selectedSkillID.flatMap { runInventoryBySkill[$0] } ?? []
    }

    func updateCatalog(_ entries: [JSONValue]) {
        var exampleIDsBySkill: [String: Set<String>] = [:]
        let validEntries = entries.compactMap { entry -> (String, String, String, String, Bool, String, [String])? in
            guard let id = entry["skill_id"]?.stringValue, Self.validID(id),
                  let name = entry["display_name"]?.stringValue else { return nil }
            let category = entry["category"]?.stringValue ?? "general"
            let examples = Array((entry["example_ids"]?.arrayValue ?? []).compactMap { value -> String? in
                guard let id = value.stringValue, Self.validID(id), id.count <= 64 else { return nil }
                return id
            }.prefix(32))
            exampleIDsBySkill[id] = Set(examples)
            let installation = entry["installation"]?.stringValue ?? "unknown"
            let enabled = entry["enabled"]?.boolValue ?? false
            let readiness = entry["readiness"]?.stringValue ?? "unknown"
            return (id, name, category, installation, enabled, readiness, examples)
        }
        let bounded = Array(validEntries.prefix(32)).map {
            id, name, category, installation, enabled, readiness, examples in
            JSONValue.object([
                "id": .string(id),
                "name": .string(String(name.prefix(80))),
                "category": .string(String(category.prefix(24))),
                "installation": .string(String(installation.prefix(24))),
                "enabled": .bool(enabled),
                "readiness": .string(String(readiness.prefix(24))),
                "example_ids": .array(examples.map(JSONValue.string)),
            ])
        }
        let ids = Set(validEntries.map { $0.0 })
        let packageRevisions = Dictionary(entries.compactMap { entry -> (String, String)? in
            guard let id = entry["skill_id"]?.stringValue,
                  let revision = entry["revision"]?.stringValue,
                  Self.validID(id), Self.validDigest(revision) else { return nil }
            return (id, revision.lowercased())
        }, uniquingKeysWith: { _, latest in latest })
        packageRevisionBySkill = packageRevisions
        let staleDetails = detailCache.keys.filter { key in
            guard let separator = key.firstIndex(of: ":") else { return true }
            let id = String(key[..<separator])
            let revision = String(key[key.index(after: separator)...])
            return packageRevisions[id] != revision
        }
        for key in staleDetails {
            detailCache.removeValue(forKey: key)
            detailCacheOrder.removeAll { $0 == key }
        }
        self.exampleIDsBySkill = exampleIDsBySkill
        let newCategories = Set(validEntries.map { $0.2 }
            .filter { !$0.isEmpty && $0.count <= 40 })
            .union(["home", "surveillance", "finance"])
        guard ids != skillIDs || newCategories != categories || bounded != catalogInventory else { return }
        catalogInventory = bounded
        skillIDs = ids
        categories = newCategories
        if let selectedSkillID, !ids.contains(selectedSkillID) { clearSelection() }
        if let selectedSkillID, let selectedExampleID,
           exampleIDsBySkill[selectedSkillID]?.contains(selectedExampleID) != true {
            self.selectedExampleID = nil
        }
        if categoryFilter != "all", !newCategories.contains(categoryFilter) { categoryFilter = "all" }
        changed()
    }

    func updateProcess(skillID: String, stepIDs: [String]) {
        guard skillIDs.contains(skillID) else { return }
        let ids = Set(stepIDs.filter(Self.validID).prefix(32))
        guard stepIDsBySkill[skillID] != ids else { return }
        stepIDsBySkill[skillID] = ids
        if selectedSkillID == skillID, let selectedStepID, !ids.contains(selectedStepID) {
            self.selectedStepID = nil
        }
        changed()
    }

    func updateProcess(skillID: String, nodes: [JSONValue]) {
        guard skillIDs.contains(skillID) else { return }
        let entries = Array(nodes.prefix(32)).compactMap { node -> JSONValue? in
            guard let id = node["step_id"]?.stringValue, Self.validID(id) else { return nil }
            let title = node["title"]?.stringValue ?? "Process step"
            return .object(["id": .string(id), "title": .string(String(title.prefix(80)))])
        }
        let previous = processInventoryBySkill[skillID]
        let oldIDs = stepIDsBySkill[skillID] ?? []
        let ids = Set(entries.compactMap { $0["id"]?.stringValue })
        processInventoryBySkill[skillID] = entries
        if oldIDs == ids {
            if previous != entries { changed() }
        } else {
            updateProcess(skillID: skillID, stepIDs: Array(ids))
        }
    }

    func updateRuns(skillID: String, runIDs: [String]) {
        guard skillIDs.contains(skillID) else { return }
        let ids = Set(runIDs.filter(Self.validID).prefix(100))
        guard runIDsBySkill[skillID] != ids else { return }
        runIDsBySkill[skillID] = ids
        if selectedSkillID == skillID, let selectedRunID, !ids.contains(selectedRunID) {
            self.selectedRunID = nil
        }
        changed()
    }

    func updateRuns(skillID: String, runs: [SkillRunSummary]) {
        guard skillIDs.contains(skillID) else { return }
        let entries = Array(runs.prefix(20)).compactMap { run -> JSONValue? in
            guard Self.validID(run.runID) else { return nil }
            return .object([
                "id": .string(run.runID),
                "status": .string(String(run.status.prefix(24))),
                "started_at": .string(String(run.startedAt.prefix(32))),
            ])
        }
        let previous = runInventoryBySkill[skillID]
        let oldIDs = runIDsBySkill[skillID] ?? []
        let ids = Set(entries.compactMap { $0["id"]?.stringValue })
        runInventoryBySkill[skillID] = entries
        if oldIDs == ids {
            if previous != entries { changed() }
        } else {
            updateRuns(skillID: skillID, runIDs: Array(ids))
        }
    }

    @discardableResult
    func selectSkill(_ id: String) -> Bool {
        guard skillIDs.contains(id) else { return false }
        navigationRequestRevision &+= 1
        let needsReset = selectedSkillID != id || selectedTab != "overview"
            || selectedStepID != nil || selectedRunID != nil || selectedExampleID != nil
        guard needsReset else { return true }
        selectedSkillID = id
        selectedTab = "overview"
        selectedStepID = nil
        selectedRunID = nil
        selectedExampleID = nil
        changed()
        return true
    }

    @discardableResult
    func selectTab(_ tab: String) -> Bool {
        guard ["overview", "process", "activity", "versions"].contains(tab) else { return false }
        navigationRequestRevision &+= 1
        guard selectedTab != tab else { return true }
        selectedTab = tab
        changed()
        return true
    }

    @discardableResult
    func selectStep(_ id: String) -> Bool {
        guard let selectedSkillID, stepIDsBySkill[selectedSkillID]?.contains(id) == true else { return false }
        navigationRequestRevision &+= 1
        selectedTab = "process"
        selectedStepID = id
        changed()
        return true
    }

    @discardableResult
    func selectExample(_ id: String) -> Bool {
        guard let selectedSkillID, exampleIDsBySkill[selectedSkillID]?.contains(id) == true else { return false }
        navigationRequestRevision &+= 1
        let needsMutation = selectedTab != "overview" || selectedExampleID != id
        guard needsMutation else { return true }
        selectedTab = "overview"
        selectedExampleID = id
        changed()
        return true
    }

    @discardableResult
    func selectRun(_ id: String) -> Bool {
        guard let selectedSkillID, runIDsBySkill[selectedSkillID]?.contains(id) == true else { return false }
        navigationRequestRevision &+= 1
        selectedTab = "activity"
        selectedRunID = id
        changed()
        return true
    }

    @discardableResult
    func setSearch(_ query: String) -> Bool {
        // Match Python's console protocol, where len(str) counts Unicode code
        // points rather than user-perceived grapheme clusters.
        guard query.unicodeScalars.count <= 256 else { return false }
        guard searchQuery != query else { return true }
        searchQuery = query
        changed()
        return true
    }

    @discardableResult
    func setFilters(state: String, category: String) -> Bool {
        guard ["all", "installed", "proposed", "needs_attention"].contains(state),
              category == "all" || categories.contains(category) else { return false }
        guard stateFilter != state || categoryFilter != category else { return true }
        stateFilter = state
        categoryFilter = category
        changed()
        return true
    }

    func clearStep() {
        guard selectedStepID != nil else { return }
        selectedStepID = nil
        changed()
    }

    func clearRun() {
        guard selectedRunID != nil else { return }
        selectedRunID = nil
        changed()
    }

    private func clearSelection() {
        selectedSkillID = nil
        selectedStepID = nil
        selectedRunID = nil
        selectedExampleID = nil
    }

    private func changed() {
        revision &+= 1
        onInventoryMutation?()
    }

    private static func validID(_ value: String) -> Bool {
        !value.isEmpty && value.count <= 120 && value.rangeOfCharacter(from: .whitespacesAndNewlines) == nil
    }

    private static func validDigest(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy(\.isHexDigit)
    }

    private static func detailCacheKey(skillID: String, revision: String) -> String {
        "\(skillID):\(revision.lowercased())"
    }
}
