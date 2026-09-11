import Foundation

public struct MemoryGraphQuery: Codable, Equatable, Sendable {
    public var focus: String
    public var depth: Int
    public var edgeTypes: [String]
    public var since: String?

    public init(focus: String = "", depth: Int = 2, edgeTypes: [String] = [], since: String? = nil) {
        self.focus = focus
        self.depth = min(4, max(1, depth))
        self.edgeTypes = edgeTypes
        self.since = since
    }
}

public struct MemoryGraphNode: Decodable, Equatable, Identifiable, Sendable {
    public let id: String
    public let type: String
    public let label: String
    public let attrs: [String: JSONValue]
}

public struct MemoryGraphEdge: Decodable, Equatable, Sendable {
    public let from: String
    public let to: String
    public let type: String
    public let attrs: [String: JSONValue]
}

public struct MemoryGraphLegend: Decodable, Equatable, Sendable {
    public let nodeTypes: [String: String]
    public let edgeTypes: [String: String]
    enum CodingKeys: String, CodingKey { case nodeTypes = "node_types", edgeTypes = "edge_types" }
}

public enum MemoryGraphError: Error, LocalizedError, Equatable {
    case unavailable(String)
    case invalidShape
    public var errorDescription: String? {
        switch self {
        case .unavailable(let reason): return reason
        case .invalidShape: return "Unsupported memory graph response. The original result remains available."
        }
    }
}

/// Strict graph identity/structure with an explicit bounded client projection.
/// Server truncation and extra client limits are both exposed to the user.
public struct MemoryGraphResponse: Decodable, Equatable, Sendable {
    public let graph: String
    public let focus: String?
    public let depth: Int
    public let edgeTypes: [String]
    public let nodeCount: Int
    public let edgeCount: Int
    public let truncated: Bool
    public let truncatedReason: String
    public let nodes: [MemoryGraphNode]
    public let edges: [MemoryGraphEdge]
    public let legend: MemoryGraphLegend
    public static let nodeLimit = 500
    public static let edgeLimit = 2000

    enum CodingKeys: String, CodingKey {
        case ok, error, graph, focus, depth, nodes, edges, legend, truncated
        case edgeTypes = "edge_types", nodeCount = "node_count", edgeCount = "edge_count"
        case truncatedReason = "truncated_reason"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        guard try c.decode(Bool.self, forKey: .ok) else {
            throw MemoryGraphError.unavailable(try c.decodeIfPresent(String.self, forKey: .error) ?? "Memory graph unavailable")
        }
        graph = try c.decode(String.self, forKey: .graph)
        guard graph == "memory" else { throw MemoryGraphError.invalidShape }
        focus = try c.decodeIfPresent(String.self, forKey: .focus)
        depth = try c.decode(Int.self, forKey: .depth)
        edgeTypes = try c.decode([String].self, forKey: .edgeTypes)
        nodeCount = try c.decode(Int.self, forKey: .nodeCount)
        edgeCount = try c.decode(Int.self, forKey: .edgeCount)
        legend = try c.decode(MemoryGraphLegend.self, forKey: .legend)
        let allNodes = try c.decode([MemoryGraphNode].self, forKey: .nodes)
        let allEdges = try c.decode([MemoryGraphEdge].self, forKey: .edges)
        let allIDs = Set(allNodes.map(\.id))
        guard allIDs.count == allNodes.count, !allIDs.contains(""),
              nodeCount == allNodes.count, edgeCount == allEdges.count,
              allEdges.allSatisfy({ allIDs.contains($0.from) && allIDs.contains($0.to) })
        else { throw MemoryGraphError.invalidShape }
        // Preserve the requested focus if a configured server cap exceeds ours.
        let requestedFocus = focus
        let ordered = allNodes.sorted {
            if $0.id == $1.id { return false }
            if $0.id == requestedFocus { return true }
            if $1.id == requestedFocus { return false }
            return $0.id < $1.id
        }
        nodes = Array(ordered.prefix(Self.nodeLimit))
        let visibleIDs = Set(nodes.map(\.id))
        edges = Array(allEdges.filter { visibleIDs.contains($0.from) && visibleIDs.contains($0.to) }.prefix(Self.edgeLimit))
        let clientLimited = nodes.count < allNodes.count || edges.count < allEdges.count
        truncated = (try c.decode(Bool.self, forKey: .truncated)) || clientLimited
        let reason = try c.decodeIfPresent(String.self, forKey: .truncatedReason) ?? ""
        truncatedReason = [reason, clientLimited ? "Display limit: 500 nodes / 2,000 edges; focus a node to explore further." : ""]
            .filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

extension AdminAPI {
    func memoryGraphRequest(_ query: MemoryGraphQuery) -> URLRequest {
        var components = URLComponents(url: config.adminURL.appending(path: "api/graph/memory"), resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "depth", value: String(min(4, max(1, query.depth))))]
        if !query.focus.isEmpty { items.append(URLQueryItem(name: "focus", value: query.focus)) }
        if !query.edgeTypes.isEmpty { items.append(URLQueryItem(name: "edge_types", value: query.edgeTypes.joined(separator: ","))) }
        if let since = query.since, !since.isEmpty { items.append(URLQueryItem(name: "since", value: since)) }
        components.queryItems = items
        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        return request
    }

    public func memoryGraph(_ query: MemoryGraphQuery = MemoryGraphQuery()) async throws -> MemoryGraphResponse {
        let (data, _) = try await JarvisHTTP.send(memoryGraphRequest(query), config: config)
        guard data.count <= 10_000_000 else { throw MemoryGraphError.invalidShape }
        return try JSONDecoder().decode(MemoryGraphResponse.self, from: data)
    }
}
