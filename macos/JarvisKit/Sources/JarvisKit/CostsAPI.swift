import Foundation

/// MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9. Typed client for the
/// costs service (jarvis/costs_api.py, its own process on
/// JarvisConfig.costsURL — NOT under the admin sidecar's /api/* prefix,
/// so this is its own struct rather than three more AdminAPI methods).
///
/// Response shapes are decoded directly as typed Codable structs (unlike
/// AdminAPI's JSONValue — see that file's own note on why: the admin
/// sidecar's response bodies are FastAPI dicts this plan couldn't verify
/// from a sandbox, whereas costs_api.py's three routes are fully known
/// and owned by this same optimization work, so a wrong field name here
/// is a compile error instead of a silent runtime mismatch).
public struct CostSummary: Codable, Sendable {
    public let month: String
    public let calls: Int
    public let totalUsd: Double
    public let projectedUsd: Double
    public let byRung: [RungCost]
    public let byProvider: [ProviderCost]
    public let budgetUsd: Double
    public let budgetUsedPct: Double
    public let unpricedCalls: Int
    public let spoken: String

    enum CodingKeys: String, CodingKey {
        case month, calls, spoken
        case totalUsd = "total_usd"
        case projectedUsd = "projected_usd"
        case byRung = "by_rung"
        case byProvider = "by_provider"
        case budgetUsd = "budget_usd"
        case budgetUsedPct = "budget_used_pct"
        case unpricedCalls = "unpriced_calls"
    }
}

public struct RungCost: Codable, Sendable, Identifiable {
    public let rung: String
    public let usd: Double
    public var id: String { rung }
}

public struct ProviderCost: Codable, Sendable, Identifiable {
    public let provider: String
    public let usd: Double
    public var id: String { provider }
}

public struct DailyCost: Codable, Sendable, Identifiable {
    public let day: String
    public let usd: Double
    public var id: String { day }
}

public struct DailyCostResponse: Codable, Sendable {
    public let month: String
    public let daily: [DailyCost]
}

public struct MonthCost: Codable, Sendable, Identifiable {
    public let month: String
    public let usd: Double
    public var id: String { month }
}

public struct MonthsCostResponse: Codable, Sendable {
    public let months: [MonthCost]
}

public struct CostsAPI: Sendable {
    let config: JarvisConfig
    public init(config: JarvisConfig) { self.config = config }

    private func get<T: Decodable>(_ path: String, month: String? = nil) async throws -> T {
        var url = config.costsURL.appending(path: path)
        if let month {
            url = url.appending(queryItems: [URLQueryItem(name: "month", value: month)])
        }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw JarvisError.decoding("\(error)")
        }
    }

    public func summary(month: String? = nil) async throws -> CostSummary {
        try await get("costs/summary", month: month)
    }

    public func daily(month: String? = nil) async throws -> DailyCostResponse {
        try await get("costs/daily", month: month)
    }

    public func months() async throws -> MonthsCostResponse {
        try await get("costs/months")
    }
}
