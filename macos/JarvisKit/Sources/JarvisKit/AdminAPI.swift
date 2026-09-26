import Foundation

/// N14: leniently decoded — any 2xx with a JSON object means ok. Used by
/// the connection preflight; the one strongly-typed AdminAPI response.
public struct AdminHealth: Codable, Sendable {
    public let ok: Bool
    public init(from decoder: Decoder) throws {
        // Lenient: any successfully-parsed JSON object from a 2xx counts
        // as healthy, regardless of its actual shape.
        _ = decoder
        ok = true
    }
}

/// The two typed POST request bodies (review F10) — derivable from
/// jarvis/admin/server.py's own Pydantic models, so they are typed here
/// rather than passed through as JSONValue (a wrong key there would be a
/// silent 422, not a compile error).

/// class GoalIn(BaseModel) — goal: str = "", profile: str | None,
/// plan: str | None, plan_path: str | None, staging_id: str | None.
/// The wrapper exposes the four the Edit tab sends and lets the
/// sidecar's staging path own plan_path.
struct GoalIn: Encodable {
    var goal: String
    var profile: String?
    var plan: String?
    var stagingId: String?
    enum CodingKeys: String, CodingKey {
        case goal, profile, plan, stagingId = "staging_id"
    }
}

/// class MemoryReviewResolveIn(BaseModel) — action: str,
/// rewrite_content: str | None.
struct MemoryReviewResolveIn: Encodable {
    var action: String
    var rewriteContent: String?
    enum CodingKeys: String, CodingKey {
        case action, rewriteContent = "rewrite_content"
    }
}

/// Typed request bodies for the draft-confirmed model route preference flow.
public struct ModelRoutePreferenceStage: Encodable, Sendable {
    public let workload: String
    public let profile: String
    public let route: String
    public let privacy: String?
    public init(workload: String, profile: String, route: String, privacy: String? = nil) {
        self.workload = workload
        self.profile = profile
        self.route = route
        self.privacy = privacy
    }
}

public struct ModelRoutePreferenceConfirm: Encodable, Sendable {
    public let draftId: String
    public init(draftId: String) { self.draftId = draftId }
    enum CodingKeys: String, CodingKey { case draftId = "draft_id" }
}

/// N14: a typed wrapper over exactly the routes the drawer tabs call
/// today. Seventeen methods for seventeen routes (fourteen tab
/// groupings, review F10). Response bodies are JSONValue (a deliberate,
/// stated narrowing — the sidecar's response bodies are FastAPI dicts
/// this plan cannot verify from a sandbox); request bodies for the two
/// POSTs ARE typed, above. Per-tab response structs are T1.3's to add
/// inside this struct (R-N10) — this plan neither defines nor guesses
/// them.
public struct AdminAPI: Sendable {
    let config: JarvisConfig
    let graphImageRequests = GraphImageRequests()
    // Internal read-test seam. Production creates its own transient session.
    let graphSession: URLSession?
    public init(config: JarvisConfig) { self.config = config; self.graphSession = nil }
    init(config: JarvisConfig, graphSession: URLSession) {
        self.config = config; self.graphSession = graphSession
    }

    private func percentEncoded(_ segment: String) -> String {
        segment.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? segment
    }

    private func get(_ path: String) async throws -> JSONValue {
        var req = URLRequest(url: config.adminURL.appending(path: path))
        req.httpMethod = "GET"
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }

    private func delete(_ path: String) async throws -> JSONValue {
        var req = URLRequest(url: config.adminURL.appending(path: path))
        req.httpMethod = "DELETE"
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }

    private func post<Body: Encodable>(_ path: String, body: Body) async throws -> JSONValue {
        var req = URLRequest(url: config.adminURL.appending(path: path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }

    // MARK: Repo
    public func gitStatus() async throws -> JSONValue { try await get("api/git/status") }

    // MARK: Edit
    public func selfeditModels() async throws -> JSONValue { try await get("api/selfedit/models") }
    public func selfeditStatus() async throws -> JSONValue { try await get("api/selfedit/status") }
    public func selfeditRun(goal: String?, profile: String?, plan: String?, stagingId: String?) async throws -> JSONValue {
        let body = GoalIn(goal: goal ?? "", profile: profile, plan: plan, stagingId: stagingId)
        return try await post("api/selfedit/run", body: body)
    }

    // MARK: Model access
    /// Route metadata contains availability flags only; it never returns secrets.
    public func modelRoutes() async throws -> JSONValue { try await get("api/model-routes") }
    public func stageModelRoute(_ preference: ModelRoutePreferenceStage) async throws -> JSONValue {
        try await post("api/model-routes/stage", body: preference)
    }
    public func confirmModelRoute(draftId: String) async throws -> JSONValue {
        try await post("api/model-routes/confirm", body: ModelRoutePreferenceConfirm(draftId: draftId))
    }

    // MARK: Memory
    public func memory() async throws -> JSONValue { try await get("api/memory") }
    public func deleteFact(key: String) async throws -> JSONValue {
        try await delete("api/memory/fact/\(percentEncoded(key))")
    }
    public func memoryReviews() async throws -> JSONValue { try await get("api/memory/reviews") }
    public func resolveReview(id: Int, action: String, rewriteContent: String?) async throws -> JSONValue {
        let body = MemoryReviewResolveIn(action: action, rewriteContent: rewriteContent)
        return try await post("api/memory/reviews/\(id)/resolve", body: body)
    }
    public func knowledge() async throws -> JSONValue { try await get("api/knowledge") }

    // MARK: Runs
    public func runs() async throws -> JSONValue { try await get("api/runs") }
    public func run(id: String) async throws -> JSONValue {
        try await get("api/runs/\(percentEncoded(id))")
    }

    // MARK: Ambient
    public func ambient() async throws -> JSONValue { try await get("api/ambient") }

    /// Phase 2 D4: the device fix also feeds the weather chip, through the
    /// sidecar's existing POST /api/location (lat, lon, label).
    public func reportDeviceLocation(lat: Double, lon: Double, label: String) async throws -> JSONValue {
        try await post("api/location", body: DeviceLocationBody(lat: lat, lon: lon, label: label))
    }

    // MARK: Council
    public func councilJob() async throws -> JSONValue { try await get("api/council/job") }
    public func councilRounds() async throws -> JSONValue { try await get("api/council/rounds") }
    public func councilRound(id: String) async throws -> JSONValue {
        try await get("api/council/round/\(percentEncoded(id))")
    }

    // MARK: Plan
    public func planJob() async throws -> JSONValue { try await get("api/plan/job") }

    // MARK: Health
    public func health() async throws -> AdminHealth {
        var req = URLRequest(url: config.adminURL.appending(path: "api/health"))
        req.httpMethod = "GET"
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        return try JSONDecoder().decode(AdminHealth.self, from: data)
    }

    // MARK: - Typed helpers (T1.3 / F12)

    func getDecoded<T: Decodable>(_ path: String) async throws -> T {
        var req = URLRequest(url: config.adminURL.appending(path: path))
        req.httpMethod = "GET"
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw JarvisError.decoding("\(path): \(error)") }
    }

    func postDecoded<Body: Encodable, T: Decodable>(_ path: String, body: Body) async throws -> T {
        var req = URLRequest(url: config.adminURL.appending(path: path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw JarvisError.decoding("\(path): \(error)") }
    }

    func postBodyless<T: Decodable>(_ path: String) async throws -> T {
        var req = URLRequest(url: config.adminURL.appending(path: path))
        req.httpMethod = "POST"
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw JarvisError.decoding("\(path): \(error)") }
    }
}

// MARK: - T1.3 per-tab response structs + additive write methods (F12)
//
// The concrete response structs MORTIMER_NATIVE_CLIENT_CORE_PLAN.md §3
// N14 deliberately deferred, added here per MORTIMER_NATIVE_CLIENT_APP_
// PLAN.md §3 P2-P5, VERBATIM (§0.7 — the CodingKeys, optionality, and
// Int-vs-Bool choices were each read from the sidecar's real responses
// and are load-bearing). The one uniform addition: every NON-optional
// scalar decodes with decodeIfPresent + a stated default (CORE's F8
// rule, restated by APP §3 P5) so an older sidecar's missing field
// degrades to a default, never a decode failure. Optionals stay nil.
//
// Request bodies for the write methods are typed from server.py's own
// Pydantic models (MessageIn, ActionIn) — additive to K8, declared in
// the APP plan header; CORE's seventeen read routes are unchanged.

// MARK: Repo (P2)

public struct GitStatus: Codable, Sendable {
    public let branch: String
    public let clean: Bool
    public let changedFiles: [String]
    public let ahead: Int
    public let behind: Int
    enum CodingKeys: String, CodingKey {
        case branch, clean, ahead, behind
        case changedFiles = "changed_files"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        branch = try c.decodeIfPresent(String.self, forKey: .branch) ?? ""
        clean = try c.decodeIfPresent(Bool.self, forKey: .clean) ?? false
        changedFiles = try c.decodeIfPresent([String].self, forKey: .changedFiles) ?? []
        ahead = try c.decodeIfPresent(Int.self, forKey: .ahead) ?? 0
        behind = try c.decodeIfPresent(Int.self, forKey: .behind) ?? 0
    }
}

/// The read-only checked-in architecture contract shown in the Repo sidecar.
/// `sha256` identifies the exact document without exposing repository internals
/// or creating a second source of truth in the native client.
public struct ArchitectureReference: Codable, Sendable {
    public let ok: Bool
    public let path: String
    public let content: String
    public let sha256: String?
    public let truncated: Bool
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, path, content, sha256, truncated, error }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        path = try c.decodeIfPresent(String.self, forKey: .path) ?? "docs/ARCHITECTURE.md"
        content = try c.decodeIfPresent(String.self, forKey: .content) ?? ""
        sha256 = try c.decodeIfPresent(String.self, forKey: .sha256)
        truncated = try c.decodeIfPresent(Bool.self, forKey: .truncated) ?? false
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

public struct GitDraft: Codable, Sendable {   // prepare-commit / prepare-push
    public let ok: Bool
    public let actionId: Int?
    public let summary: String?
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, summary, error; case actionId = "action_id" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        actionId = try c.decodeIfPresent(Int.self, forKey: .actionId)
        summary = try c.decodeIfPresent(String.self, forKey: .summary)
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

public struct GitActionResult: Codable, Sendable {  // commit / push
    public let ok: Bool
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, error }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

struct MessageIn: Encodable { let message: String }          // server.py MessageIn
struct ActionIn: Encodable {                                  // server.py ActionIn
    let actionId: Int
    enum CodingKeys: String, CodingKey { case actionId = "action_id" }
}

// MARK: Edit (P3)

public struct SelfEditModel: Codable, Sendable {
    public let name: String
    public let label: String
    public let provider: String
    public let model: String
    public let keyEnv: String
    public let keyPresent: Bool
    public let isDefault: Bool
    public let tier: String?          // economy|mid|frontier|null
    enum CodingKeys: String, CodingKey {
        case name, label, provider, model, tier
        case keyEnv = "key_env", keyPresent = "key_present", isDefault = "default"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        label = try c.decodeIfPresent(String.self, forKey: .label) ?? ""
        provider = try c.decodeIfPresent(String.self, forKey: .provider) ?? ""
        model = try c.decodeIfPresent(String.self, forKey: .model) ?? ""
        keyEnv = try c.decodeIfPresent(String.self, forKey: .keyEnv) ?? ""
        keyPresent = try c.decodeIfPresent(Bool.self, forKey: .keyPresent) ?? false
        isDefault = try c.decodeIfPresent(Bool.self, forKey: .isDefault) ?? false
        tier = try c.decodeIfPresent(String.self, forKey: .tier)
    }
}

public struct SelfEditModels: Codable, Sendable {
    public let ok: Bool
    public let models: [SelfEditModel]
    enum CodingKeys: String, CodingKey { case ok, models }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        models = try c.decodeIfPresent([SelfEditModel].self, forKey: .models) ?? []
    }
}

public struct SelfEditProposal: Codable, Sendable {
    public let path: String
    public let rationale: String
    public let diff: String
    enum CodingKeys: String, CodingKey { case path, rationale, diff }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        path = try c.decodeIfPresent(String.self, forKey: .path) ?? ""
        rationale = try c.decodeIfPresent(String.self, forKey: .rationale) ?? ""
        diff = try c.decodeIfPresent(String.self, forKey: .diff) ?? ""
    }
}

/// /api/selfedit/status has TWO shapes: the busy shape {"ok": false,
/// "error": ...} and SelfEditService.status() (no "ok" key at all). One
/// struct decodes both — everything optional; the view branches on
/// `error != nil` (APP §3 P3).
public struct SelfEditStatus: Codable, Sendable {
    public let ok: Bool?              // present (false) only on the busy shape; nil on a real status
    public let error: String?
    public let active: Bool?
    public let branch: String?
    public let rollbackTag: String?
    public let goal: String?
    public let proposals: [SelfEditProposal]?
    public let validatedOk: Bool?
    enum CodingKeys: String, CodingKey {
        case ok, error, active, branch, goal, proposals
        case rollbackTag = "rollback_tag", validatedOk = "validated_ok"
    }
}

// MARK: Memory (P4)

public struct MemoryFact: Codable, Sendable {
    public let id: Int
    public let key: String
    public let content: String
    public let sourceSessionId: String?      // nullable in SQL
    public let updatedAt: String
    public let tier: String
    public let audience: String
    public let subject: String
    public let scope: String
    public let memoryType: String
    public let provenance: String
    public let evidenceStatus: String
    public let confidence: Double
    public let validFrom: String?
    public let validUntil: String?
    public let sourceTurnId: String?
    public let contentRevision: Int
    public let classifierVersion: String
    public let classifiedAt: String?
    public let supersedesId: Int?
    public let usedForCount: Int
    enum CodingKeys: String, CodingKey {
        case id, key, content, tier, audience, subject, scope, provenance, confidence
        case memoryType = "memory_type", evidenceStatus = "evidence_status"
        case validFrom = "valid_from", validUntil = "valid_until"
        case sourceTurnId = "source_turn_id", contentRevision = "content_revision"
        case classifierVersion = "classifier_version", classifiedAt = "classified_at"
        case supersedesId = "supersedes_id", usedForCount = "used_for_count"
        case sourceSessionId = "source_session_id", updatedAt = "updated_at"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(Int.self, forKey: .id) ?? 0
        key = try c.decodeIfPresent(String.self, forKey: .key) ?? ""
        content = try c.decodeIfPresent(String.self, forKey: .content) ?? ""
        sourceSessionId = try c.decodeIfPresent(String.self, forKey: .sourceSessionId)
        updatedAt = try c.decodeIfPresent(String.self, forKey: .updatedAt) ?? ""
        tier = try c.decodeIfPresent(String.self, forKey: .tier) ?? ""
        audience = try c.decodeIfPresent(String.self, forKey: .audience) ?? ""
        subject = try c.decodeIfPresent(String.self, forKey: .subject) ?? ""
        scope = try c.decodeIfPresent(String.self, forKey: .scope) ?? "global"
        memoryType = try c.decodeIfPresent(String.self, forKey: .memoryType) ?? "fact"
        provenance = try c.decodeIfPresent(String.self, forKey: .provenance) ?? "user"
        evidenceStatus = try c.decodeIfPresent(String.self, forKey: .evidenceStatus) ?? "unknown"
        confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 0
        validFrom = try c.decodeIfPresent(String.self, forKey: .validFrom)
        validUntil = try c.decodeIfPresent(String.self, forKey: .validUntil)
        sourceTurnId = try c.decodeIfPresent(String.self, forKey: .sourceTurnId)
        contentRevision = try c.decodeIfPresent(Int.self, forKey: .contentRevision) ?? 1
        classifierVersion = try c.decodeIfPresent(String.self, forKey: .classifierVersion) ?? "legacy-v1"
        classifiedAt = try c.decodeIfPresent(String.self, forKey: .classifiedAt)
        supersedesId = try c.decodeIfPresent(Int.self, forKey: .supersedesId)
        usedForCount = try c.decodeIfPresent(Int.self, forKey: .usedForCount) ?? 0
    }
}

public struct MemoryObservation: Codable, Sendable {
    public let key: String
    public let sessions: Int
    public let promoteAfter: Int
    public let latestContent: String
    public let promoted: Bool
    enum CodingKeys: String, CodingKey {
        case key, sessions, promoted
        case promoteAfter = "promote_after", latestContent = "latest_content"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        key = try c.decodeIfPresent(String.self, forKey: .key) ?? ""
        sessions = try c.decodeIfPresent(Int.self, forKey: .sessions) ?? 0
        promoteAfter = try c.decodeIfPresent(Int.self, forKey: .promoteAfter) ?? 0
        latestContent = try c.decodeIfPresent(String.self, forKey: .latestContent) ?? ""
        promoted = try c.decodeIfPresent(Bool.self, forKey: .promoted) ?? false
    }
}

public struct MemoryUsage: Codable, Sendable {
    public let factCount: Int
    public let tiers: [String: Int]
    public let caps: [String: Int]
    public let maxContextChars: Int
    public let overCapacity: Bool
    enum CodingKeys: String, CodingKey {
        case tiers, caps
        case factCount = "fact_count", maxContextChars = "max_context_chars", overCapacity = "over_capacity"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        factCount = try c.decodeIfPresent(Int.self, forKey: .factCount) ?? 0
        tiers = try c.decodeIfPresent([String: Int].self, forKey: .tiers) ?? [:]
        caps = try c.decodeIfPresent([String: Int].self, forKey: .caps) ?? [:]
        maxContextChars = try c.decodeIfPresent(Int.self, forKey: .maxContextChars) ?? 0
        overCapacity = try c.decodeIfPresent(Bool.self, forKey: .overCapacity) ?? false
    }
}

public struct MemoryOverview: Codable, Sendable {
    public let ok: Bool
    public let facts: [MemoryFact]
    public let summary: String
    public let observations: [MemoryObservation]
    public let usage: MemoryUsage
    enum CodingKeys: String, CodingKey { case ok, facts, summary, observations, usage }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        facts = try c.decodeIfPresent([MemoryFact].self, forKey: .facts) ?? []
        summary = try c.decodeIfPresent(String.self, forKey: .summary) ?? ""
        observations = try c.decodeIfPresent([MemoryObservation].self, forKey: .observations) ?? []
        usage = try c.decodeIfPresent(MemoryUsage.self, forKey: .usage)
            ?? MemoryUsage(factCount: 0, tiers: [:], caps: [:], maxContextChars: 0, overCapacity: false)
    }
}

extension MemoryUsage {
    /// Memberwise fallback for a response missing `usage` entirely.
    init(factCount: Int, tiers: [String: Int], caps: [String: Int], maxContextChars: Int, overCapacity: Bool) {
        self.factCount = factCount
        self.tiers = tiers
        self.caps = caps
        self.maxContextChars = maxContextChars
        self.overCapacity = overCapacity
    }
}

public struct MemoryReview: Codable, Sendable {
    public let id: Int
    public let kind: String
    public let keysJson: String
    public let detail: String
    public let status: String
    public let createdAt: String
    public let keys: [String]
    enum CodingKeys: String, CodingKey {
        case id, kind, detail, status, keys
        case keysJson = "keys_json", createdAt = "created_at"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(Int.self, forKey: .id) ?? 0
        kind = try c.decodeIfPresent(String.self, forKey: .kind) ?? ""
        keysJson = try c.decodeIfPresent(String.self, forKey: .keysJson) ?? ""
        detail = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? ""
        createdAt = try c.decodeIfPresent(String.self, forKey: .createdAt) ?? ""
        keys = try c.decodeIfPresent([String].self, forKey: .keys) ?? []
    }
}

public struct MemoryReviews: Codable, Sendable {
    public let ok: Bool
    public let reviews: [MemoryReview]?
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, reviews, error }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        reviews = try c.decodeIfPresent([MemoryReview].self, forKey: .reviews)
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

public struct KnowledgeMemory: Codable, Sendable {
    public let live: Int
    public let archived: Int
    public let tiers: [String: Int]
    public let reachingPrompt: Int
    public let notReachingPrompt: Int
    public let contextChars: Int
    enum CodingKeys: String, CodingKey {
        case live, archived, tiers
        case reachingPrompt = "reaching_prompt", notReachingPrompt = "not_reaching_prompt", contextChars = "context_chars"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        live = try c.decodeIfPresent(Int.self, forKey: .live) ?? 0
        archived = try c.decodeIfPresent(Int.self, forKey: .archived) ?? 0
        tiers = try c.decodeIfPresent([String: Int].self, forKey: .tiers) ?? [:]
        reachingPrompt = try c.decodeIfPresent(Int.self, forKey: .reachingPrompt) ?? 0
        notReachingPrompt = try c.decodeIfPresent(Int.self, forKey: .notReachingPrompt) ?? 0
        contextChars = try c.decodeIfPresent(Int.self, forKey: .contextChars) ?? 0
    }
}

public struct KnowledgeSkillEntry: Codable, Sendable {
    public let name: String
    public let hasScripts: Bool
    enum CodingKeys: String, CodingKey { case name; case hasScripts = "has_scripts" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        hasScripts = try c.decodeIfPresent(Bool.self, forKey: .hasScripts) ?? false
    }
}

public struct KnowledgeSkills: Codable, Sendable {
    public let onDisk: Int
    public let invalid: Int
    public let registered: Int
    public let enabled: [KnowledgeSkillEntry]
    enum CodingKeys: String, CodingKey { case invalid, registered, enabled; case onDisk = "on_disk" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        onDisk = try c.decodeIfPresent(Int.self, forKey: .onDisk) ?? 0
        invalid = try c.decodeIfPresent(Int.self, forKey: .invalid) ?? 0
        registered = try c.decodeIfPresent(Int.self, forKey: .registered) ?? 0
        enabled = try c.decodeIfPresent([KnowledgeSkillEntry].self, forKey: .enabled) ?? []
    }
}

public struct KnowledgeWorkflow: Codable, Sendable {
    public let name: String
    public let source: String
    public let hasDoneWhen: Bool
    enum CodingKeys: String, CodingKey { case name, source; case hasDoneWhen = "has_done_when" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        source = try c.decodeIfPresent(String.self, forKey: .source) ?? ""
        hasDoneWhen = try c.decodeIfPresent(Bool.self, forKey: .hasDoneWhen) ?? false
    }
}

public struct KnowledgeOverview: Codable, Sendable {
    public let ok: Bool
    public let memory: KnowledgeMemory?
    public let procedures: [String: Int]?
    public let skills: KnowledgeSkills?
    public let workflows: [KnowledgeWorkflow]?
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, memory, procedures, skills, workflows, error }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        memory = try c.decodeIfPresent(KnowledgeMemory.self, forKey: .memory)
        procedures = try c.decodeIfPresent([String: Int].self, forKey: .procedures)
        skills = try c.decodeIfPresent(KnowledgeSkills.self, forKey: .skills)
        workflows = try c.decodeIfPresent([KnowledgeWorkflow].self, forKey: .workflows)
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

// MARK: Runs (P5)

public struct RunSummary: Codable, Sendable {
    public let runId: String
    public let sessionId: String?
    public let agent: String
    public let displayName: String
    public let task: String
    public let status: String          // running|ok|failed|timeout|orphaned
    public let startedAt: String
    public let endedAt: String?
    public let latencyMs: Int?
    public let toolCount: Int
    public let error: String?
    public let replyPreview: String?
    public let payloadPath: String?
    public let model: String?          // review F3 — db.py:325, ALTER TABLE ... ADD COLUMN model TEXT
    public let toolsOk: Int?           // review F3 — db.py:236, nullable, pre-migration rows are nil
    public let toolsFailed: Int?       // review F3 — db.py:237, nullable, pre-migration rows are nil
    enum CodingKeys: String, CodingKey {
        case agent, task, status, error, model
        case runId = "run_id", sessionId = "session_id", displayName = "display_name"
        case startedAt = "started_at", endedAt = "ended_at", latencyMs = "latency_ms"
        case toolCount = "tool_count", replyPreview = "reply_preview", payloadPath = "payload_path"
        case toolsOk = "tools_ok", toolsFailed = "tools_failed"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        runId = try c.decodeIfPresent(String.self, forKey: .runId) ?? ""
        sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId)
        agent = try c.decodeIfPresent(String.self, forKey: .agent) ?? ""
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName) ?? ""
        task = try c.decodeIfPresent(String.self, forKey: .task) ?? ""
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? ""
        startedAt = try c.decodeIfPresent(String.self, forKey: .startedAt) ?? ""
        endedAt = try c.decodeIfPresent(String.self, forKey: .endedAt)
        latencyMs = try c.decodeIfPresent(Int.self, forKey: .latencyMs)
        toolCount = try c.decodeIfPresent(Int.self, forKey: .toolCount) ?? 0
        error = try c.decodeIfPresent(String.self, forKey: .error)
        replyPreview = try c.decodeIfPresent(String.self, forKey: .replyPreview)
        payloadPath = try c.decodeIfPresent(String.self, forKey: .payloadPath)
        model = try c.decodeIfPresent(String.self, forKey: .model)
        toolsOk = try c.decodeIfPresent(Int.self, forKey: .toolsOk)
        toolsFailed = try c.decodeIfPresent(Int.self, forKey: .toolsFailed)
    }
}

public struct RunsList: Codable, Sendable {
    public let ok: Bool
    public let runs: [RunSummary]
    enum CodingKeys: String, CodingKey { case ok, runs }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        runs = try c.decodeIfPresent([RunSummary].self, forKey: .runs) ?? []
    }
}

public struct RunEvent: Codable, Sendable {
    public let id: Int
    public let runId: String
    public let seq: Int
    public let type: String            // tool_call|tool_result|mcp_call
    public let tool: String?
    public let server: String?
    public let ok: Int?                 // 1|0|NULL — NOT a Bool (db.py:151 `ok INTEGER`)
    public let latencyMs: Int?
    public let argsPreview: String?
    public let resultPreview: String?
    public let createdAt: String
    enum CodingKeys: String, CodingKey {
        case id, seq, type, tool, server, ok
        case runId = "run_id", latencyMs = "latency_ms"
        case argsPreview = "args_preview", resultPreview = "result_preview", createdAt = "created_at"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(Int.self, forKey: .id) ?? 0
        runId = try c.decodeIfPresent(String.self, forKey: .runId) ?? ""
        seq = try c.decodeIfPresent(Int.self, forKey: .seq) ?? 0
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? ""
        tool = try c.decodeIfPresent(String.self, forKey: .tool)
        server = try c.decodeIfPresent(String.self, forKey: .server)
        ok = try c.decodeIfPresent(Int.self, forKey: .ok)
        latencyMs = try c.decodeIfPresent(Int.self, forKey: .latencyMs)
        argsPreview = try c.decodeIfPresent(String.self, forKey: .argsPreview)
        resultPreview = try c.decodeIfPresent(String.self, forKey: .resultPreview)
        createdAt = try c.decodeIfPresent(String.self, forKey: .createdAt) ?? ""
    }
}

public struct RunDetail: Codable, Sendable {
    public let ok: Bool
    public let run: RunSummary?
    public let events: [RunEvent]?
    public let payload: [JSONValue]?
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, run, events, payload, error }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        run = try c.decodeIfPresent(RunSummary.self, forKey: .run)
        events = try c.decodeIfPresent([RunEvent].self, forKey: .events)
        payload = try c.decodeIfPresent([JSONValue].self, forKey: .payload)
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

// MARK: - Council roster (GET /api/council/roster)
// MORTIMER_OPTIMIZATION_PLAN.md "Interface Task — Council Roster on the
// Agent Card". The sidecar ASSEMBLES the roster
// (jarvis/council/council.py `build_roster`, pinned by
// tests/unit/test_council_roster.py) so these types decode a finished
// shape rather than recomputing a mean the round already decided by — a
// rule implemented twice is a rule that eventually disagrees with
// itself, and only one of the two copies would be in the Python suite.
// Every field decodes leniently for the same reason RunSummary's do:
// rounds recorded months ago predate later migrations.

public struct CouncilProposer: Codable, Sendable, Equatable {
    public let label: String            // "Proposal A"
    public let profile: String
    public let mean: Double?            // nil when no judge scored it
    public let scoredBy: Int
    public let abstainedBy: Int
    public let isWinner: Bool
    enum CodingKeys: String, CodingKey {
        case label, profile, mean
        case scoredBy = "scored_by", abstainedBy = "abstained_by", isWinner = "is_winner"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        label = try c.decodeIfPresent(String.self, forKey: .label) ?? ""
        profile = try c.decodeIfPresent(String.self, forKey: .profile) ?? ""
        mean = try c.decodeIfPresent(Double.self, forKey: .mean)
        scoredBy = try c.decodeIfPresent(Int.self, forKey: .scoredBy) ?? 0
        abstainedBy = try c.decodeIfPresent(Int.self, forKey: .abstainedBy) ?? 0
        isWinner = try c.decodeIfPresent(Bool.self, forKey: .isWinner) ?? false
    }
}

public struct CouncilJudge: Codable, Sendable, Equatable {
    public let profile: String
    public let tier: String?
    public let scored: Int
    public let abstained: Int
    public let abstainReasons: [String]
    public let allAbstained: Bool
    public let alsoProposed: Bool
    enum CodingKeys: String, CodingKey {
        case profile, tier, scored, abstained
        case abstainReasons = "abstain_reasons"
        case allAbstained = "all_abstained", alsoProposed = "also_proposed"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        profile = try c.decodeIfPresent(String.self, forKey: .profile) ?? ""
        tier = try c.decodeIfPresent(String.self, forKey: .tier)
        scored = try c.decodeIfPresent(Int.self, forKey: .scored) ?? 0
        abstained = try c.decodeIfPresent(Int.self, forKey: .abstained) ?? 0
        abstainReasons = try c.decodeIfPresent([String].self, forKey: .abstainReasons) ?? []
        allAbstained = try c.decodeIfPresent(Bool.self, forKey: .allAbstained) ?? false
        alsoProposed = try c.decodeIfPresent(Bool.self, forKey: .alsoProposed) ?? false
    }
}

public struct CouncilTokens: Codable, Sendable, Equatable {
    public let prompt: Int
    public let completion: Int
    public let total: Int
    enum CodingKeys: String, CodingKey { case prompt, completion, total }
    public init(prompt: Int = 0, completion: Int = 0, total: Int = 0) {
        self.prompt = prompt
        self.completion = completion
        self.total = total
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        prompt = try c.decodeIfPresent(Int.self, forKey: .prompt) ?? 0
        completion = try c.decodeIfPresent(Int.self, forKey: .completion) ?? 0
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? 0
    }
}

public struct CouncilRoster: Codable, Sendable, Equatable, Identifiable {
    public var id: String { roundId }
    public let roundId: String
    public let workflow: String
    public let placement: String        // planner | scope | ...
    public let trigger: String
    public let tier: Int?
    public let status: String           // ok | too_small | ...
    public let goal: String
    public let startedAt: String
    public let latencyMs: Int?
    /// The primary chip's value — what actually proceeded.
    public let winnerProfile: String?
    public let winnerLabel: String?
    public let winnerMean: Double?
    public let selectReason: String?
    public let retryOutcome: String?    // migration 0018; nil on older rounds
    public let proposers: [CouncilProposer]
    public let judges: [CouncilJudge]
    public let shadowJudges: [CouncilJudge]
    public let abstentions: Int
    public let tokens: CouncilTokens
    public let degraded: Bool
    public let degradedReasons: [String]
    enum CodingKeys: String, CodingKey {
        case workflow, placement, trigger, tier, status, goal, proposers, judges
        case abstentions, tokens, degraded
        case roundId = "round_id", startedAt = "started_at", latencyMs = "latency_ms"
        case winnerProfile = "winner_profile", winnerLabel = "winner_label"
        case winnerMean = "winner_mean", selectReason = "select_reason"
        case retryOutcome = "retry_outcome", shadowJudges = "shadow_judges"
        case degradedReasons = "degraded_reasons"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        roundId = try c.decodeIfPresent(String.self, forKey: .roundId) ?? ""
        workflow = try c.decodeIfPresent(String.self, forKey: .workflow) ?? ""
        placement = try c.decodeIfPresent(String.self, forKey: .placement) ?? ""
        trigger = try c.decodeIfPresent(String.self, forKey: .trigger) ?? ""
        tier = try c.decodeIfPresent(Int.self, forKey: .tier)
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? ""
        goal = try c.decodeIfPresent(String.self, forKey: .goal) ?? ""
        startedAt = try c.decodeIfPresent(String.self, forKey: .startedAt) ?? ""
        latencyMs = try c.decodeIfPresent(Int.self, forKey: .latencyMs)
        winnerProfile = try c.decodeIfPresent(String.self, forKey: .winnerProfile)
        winnerLabel = try c.decodeIfPresent(String.self, forKey: .winnerLabel)
        winnerMean = try c.decodeIfPresent(Double.self, forKey: .winnerMean)
        selectReason = try c.decodeIfPresent(String.self, forKey: .selectReason)
        retryOutcome = try c.decodeIfPresent(String.self, forKey: .retryOutcome)
        proposers = try c.decodeIfPresent([CouncilProposer].self, forKey: .proposers) ?? []
        judges = try c.decodeIfPresent([CouncilJudge].self, forKey: .judges) ?? []
        shadowJudges = try c.decodeIfPresent([CouncilJudge].self, forKey: .shadowJudges) ?? []
        abstentions = try c.decodeIfPresent(Int.self, forKey: .abstentions) ?? 0
        tokens = try c.decodeIfPresent(CouncilTokens.self, forKey: .tokens) ?? CouncilTokens()
        degraded = try c.decodeIfPresent(Bool.self, forKey: .degraded) ?? false
        degradedReasons = try c.decodeIfPresent([String].self, forKey: .degradedReasons) ?? []
    }
}

public struct CouncilRosterList: Codable, Sendable, Equatable {
    public let ok: Bool
    public let rounds: [CouncilRoster]
    enum CodingKeys: String, CodingKey { case ok, rounds }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        rounds = try c.decodeIfPresent([CouncilRoster].self, forKey: .rounds) ?? []
    }
}

// MARK: The additive methods (typed reads + draft→confirm writes)

public extension AdminAPI {
    // Repo (P2). Draft→confirm is TWO methods, never one (C4): the view
    // holds the returned actionId between the two explicit user actions.
    func gitStatusTyped() async throws -> GitStatus { try await getDecoded("api/git/status") }
    func architectureReference() async throws -> ArchitectureReference {
        try await getDecoded("api/architecture")
    }
    func prepareCommit(message: String) async throws -> GitDraft {
        try await postDecoded("api/git/prepare-commit", body: MessageIn(message: message))
    }
    func commit(actionId: Int) async throws -> GitActionResult {
        try await postDecoded("api/git/commit", body: ActionIn(actionId: actionId))
    }
    func preparePush() async throws -> GitDraft { try await postBodyless("api/git/prepare-push") }
    func push(actionId: Int) async throws -> GitActionResult {
        try await postDecoded("api/git/push", body: ActionIn(actionId: actionId))
    }

    // Edit (P3). Result shapes are SelfEditService-internal and vary →
    // JSONValue per N14's response rule; the view reads ok/error.
    func selfeditModelsTyped() async throws -> SelfEditModels { try await getDecoded("api/selfedit/models") }
    func selfeditStatusTyped() async throws -> SelfEditStatus { try await getDecoded("api/selfedit/status") }
    func selfeditValidate() async throws -> JSONValue { try await postBodyless("api/selfedit/validate") }
    func selfeditSubmit() async throws -> JSONValue { try await postBodyless("api/selfedit/submit") }
    func selfeditRevert() async throws -> JSONValue { try await postBodyless("api/selfedit/revert") }

    // Memory (P4).
    func memoryOverview() async throws -> MemoryOverview { try await getDecoded("api/memory") }
    func memoryReviewsTyped() async throws -> MemoryReviews { try await getDecoded("api/memory/reviews") }
    func knowledgeTyped() async throws -> KnowledgeOverview { try await getDecoded("api/knowledge") }

    // Runs (P5). Filters ride as query params, exactly the web's
    // `?agent=&status=` (RunsPanel.tsx:111-116) — server-side filtering,
    // never a client-side subset of an unfiltered fetch.
    func runsTyped(agent: String? = nil, status: String? = nil) async throws -> RunsList {
        var params: [String] = []
        if let agent, !agent.isEmpty {
            params.append("agent=\(agent.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? agent)")
        }
        if let status, !status.isEmpty {
            params.append("status=\(status.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? status)")
        }
        let query = params.isEmpty ? "" : "?" + params.joined(separator: "&")
        return try await getDecoded("api/runs\(query)")
    }
    func runTyped(id: String) async throws -> RunDetail {
        try await getDecoded("api/runs/\(id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id)")
    }

    // Ambient (E4/vitals). One endpoint feeds both the ambient strip and
    // the system-vitals readout (SystemVitals.tsx deliberately rides the
    // same poll rather than adding a second data source).
    func ambientTyped() async throws -> AmbientResponse { try await getDecoded("api/ambient") }

    // Council roster (Interface Task). No query params on purpose: the
    // sidecar's own default (20, clamped to 50) is the page this panel
    // wants, and the untyped councilRounds() above stays as it is for
    // callers that want raw rows.
    func councilRosterTyped() async throws -> CouncilRosterList {
        try await getDecoded("api/council/roster")
    }
}

// MARK: - Ambient (GET /api/ambient — AmbientStrip.tsx / SystemVitals.tsx)

public struct AmbientReminder: Codable, Sendable, Equatable {
    public let text: String
    public let dueAt: String
    enum CodingKeys: String, CodingKey { case text, dueAt = "due_at" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
        dueAt = try c.decodeIfPresent(String.self, forKey: .dueAt) ?? ""
    }
}

public struct AmbientWeather: Codable, Sendable, Equatable {
    public let summary: String
    public let tempF: Double
    public let location: String
    enum CodingKeys: String, CodingKey { case summary, tempF = "temp_f", location }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        summary = try c.decodeIfPresent(String.self, forKey: .summary) ?? ""
        tempF = try c.decodeIfPresent(Double.self, forKey: .tempF) ?? 0
        location = try c.decodeIfPresent(String.self, forKey: .location) ?? ""
    }
}

/// SystemVitals.tsx's SystemData — nullable metrics stay optional (a
/// machine without a battery reports null, rendered "—"/omitted).
public struct AmbientSystem: Codable, Sendable, Equatable {
    public let cpu: Double?
    public let memory: Double?
    public let disk: Double?
    public let battery: Double?
    public let uptimeHours: Double?
    public let flags: [String]
    enum CodingKeys: String, CodingKey {
        case cpu, memory, disk, battery, uptimeHours = "uptime_hours", flags
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        cpu = try c.decodeIfPresent(Double.self, forKey: .cpu)
        memory = try c.decodeIfPresent(Double.self, forKey: .memory)
        disk = try c.decodeIfPresent(Double.self, forKey: .disk)
        battery = try c.decodeIfPresent(Double.self, forKey: .battery)
        uptimeHours = try c.decodeIfPresent(Double.self, forKey: .uptimeHours)
        flags = try c.decodeIfPresent([String].self, forKey: .flags) ?? []
    }
}

public struct AmbientResponse: Codable, Sendable, Equatable {
    public let ok: Bool
    public let reminder: AmbientReminder?
    public let summary: String?
    public let weather: AmbientWeather?
    public let system: AmbientSystem?
    enum CodingKeys: String, CodingKey { case ok, reminder, summary, weather, system }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        reminder = try c.decodeIfPresent(AmbientReminder.self, forKey: .reminder)
        summary = try c.decodeIfPresent(String.self, forKey: .summary)
        weather = try c.decodeIfPresent(AmbientWeather.self, forKey: .weather)
        system = try c.decodeIfPresent(AmbientSystem.self, forKey: .system)
    }
}

struct DeviceLocationBody: Encodable {
    let lat: Double
    let lon: Double
    let label: String
}
