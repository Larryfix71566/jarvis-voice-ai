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
    public init(config: JarvisConfig) { self.config = config }

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
}
