import Foundation

public struct MemoryGraphQuery: Codable, Equatable, Sendable {
    public var focus: String
    /// Effective depth shown in the UI (server default 2 when unspecified).
    public var depth: Int
    /// Closure C3.4 (gap G14): `depth` is only SENT when the user chose one,
    /// so an operator's `JARVIS_GRAPH_DEPTH` server default still applies.
    public var depthSpecified: Bool
    public var edgeTypes: [String]
    public var since: String?

    public init(focus: String = "", depth: Int? = nil, edgeTypes: [String] = [], since: String? = nil) {
        self.focus = focus
        self.depth = min(4, max(1, depth ?? 2))
        self.depthSpecified = depth != nil
        self.edgeTypes = edgeTypes
        self.since = since
    }

    enum CodingKeys: String, CodingKey { case focus, depth, depthSpecified, edgeTypes, since }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        focus = try c.decodeIfPresent(String.self, forKey: .focus) ?? ""
        depth = min(4, max(1, try c.decodeIfPresent(Int.self, forKey: .depth) ?? 2))
        // Records saved before this field existed carried an explicit depth.
        depthSpecified = try c.decodeIfPresent(Bool.self, forKey: .depthSpecified) ?? (c.contains(.depth))
        edgeTypes = try c.decodeIfPresent([String].self, forKey: .edgeTypes) ?? []
        since = try c.decodeIfPresent(String.self, forKey: .since)
    }

    /// Choose a depth explicitly (the Depth picker); marks it for sending.
    public mutating func setDepth(_ value: Int) {
        depth = min(4, max(1, value))
        depthSpecified = true
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

/// Shape of `render.legend_for` in jarvis/graphs/render.py: node type → hex
/// colour, edge type → style name ("solid"/"dashed"/"dotted"/"won"). Every
/// key is optional so an absent or partial legend still decodes (G14).
public struct MemoryGraphLegend: Decodable, Equatable, Sendable {
    public let nodeTypes: [String: String]
    public let edgeTypes: [String: String]
    enum CodingKeys: String, CodingKey { case nodeTypes = "node_types", edgeTypes = "edge_types" }
    public init(nodeTypes: [String: String] = [:], edgeTypes: [String: String] = [:]) {
        self.nodeTypes = nodeTypes; self.edgeTypes = edgeTypes
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        nodeTypes = try c.decodeIfPresent([String: String].self, forKey: .nodeTypes) ?? [:]
        edgeTypes = try c.decodeIfPresent([String: String].self, forKey: .edgeTypes) ?? [:]
    }
    /// The memory graph's builder (jarvis/graphs/memory_graph.py) emits every
    /// edge as src → dst: child_of (fact/prefix → parent prefix), became
    /// (fact → successor/archive), stated_in and restated (fact → turn). The
    /// legend carries the server's current edge-type vocabulary, so arrows are
    /// drawn for exactly the types the server declares; when the legend is
    /// absent, this documented set is the fallback.
    public static let memoryDirectionalEdgeTypes: Set<String> = ["child_of", "became", "stated_in", "restated"]
    public var directionalEdgeTypes: Set<String> {
        edgeTypes.isEmpty ? Self.memoryDirectionalEdgeTypes : Set(edgeTypes.keys)
    }
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
        legend = try c.decodeIfPresent(MemoryGraphLegend.self, forKey: .legend) ?? MemoryGraphLegend()
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
        var items: [URLQueryItem] = []
        if query.depthSpecified { items.append(URLQueryItem(name: "depth", value: String(min(4, max(1, query.depth))))) }
        if !query.focus.isEmpty { items.append(URLQueryItem(name: "focus", value: query.focus)) }
        if !query.edgeTypes.isEmpty { items.append(URLQueryItem(name: "edge_types", value: query.edgeTypes.joined(separator: ","))) }
        if let since = query.since, !since.isEmpty { items.append(URLQueryItem(name: "since", value: since)) }
        components.queryItems = items
        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        return request
    }

    public func memoryGraph(_ query: MemoryGraphQuery = MemoryGraphQuery()) async throws -> MemoryGraphResponse {
        let (data, _) = try await JarvisHTTP.sendTransient(memoryGraphRequest(query), config: config, session: graphSession)
        guard data.count <= 10_000_000 else { throw MemoryGraphError.invalidShape }
        return try JSONDecoder().decode(MemoryGraphResponse.self, from: data)
    }
}

/// Image fallback uses the configured admin origin, never a result-supplied host.
extension AdminAPI {
    public func memoryGraphImage(_ query: MemoryGraphQuery = MemoryGraphQuery()) async throws -> Data {
        let graphRequest = memoryGraphRequest(query)
        var components = URLComponents(url: config.adminURL.appending(path: "api/graph/memory/image.png"), resolvingAgainstBaseURL: false)!
        components.queryItems = URLComponents(url: graphRequest.url!, resolvingAgainstBaseURL: false)!.queryItems
        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        request.setValue("image/png", forHTTPHeaderField: "Accept")
        let (data, response) = try await JarvisHTTP.sendTransient(request, config: config, session: graphSession)
        guard response.mimeType == "image/png", data.count <= 20_000_000,
              data.starts(with: [137, 80, 78, 71, 13, 10, 26, 10]) else {
            throw MemoryGraphError.unavailable("The server did not return a supported graph image.")
        }
        return data
    }
}

/// Closure C3.3 (gap G13): the legacy `GraphImageView` path used a bare
/// `URLSession.shared` with no Authorization and the shared URL cache. Every
/// graph image now goes through JarvisHTTP's transient sender, and only for
/// URLs on the configured admin origin under /api/graph/.
extension AdminAPI {
    public enum GraphImageOriginError: Error, Equatable { case foreignOrigin, notAGraphImage }

    public func graphImageData(at url: URL) async throws -> Data {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let admin = URLComponents(url: config.adminURL, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == admin.scheme?.lowercased(),
              components.host?.lowercased() == admin.host?.lowercased(),
              (components.port ?? defaultPort(components.scheme)) == (admin.port ?? defaultPort(admin.scheme))
        else { throw GraphImageOriginError.foreignOrigin }
        guard components.path.contains("/api/graph/"),
              components.path.hasSuffix("/image.png") || components.path.hasSuffix("/image.svg")
        else { throw GraphImageOriginError.notAGraphImage }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue(components.path.hasSuffix(".svg") ? "image/svg+xml" : "image/png", forHTTPHeaderField: "Accept")
        let imageRequest = request
        return try await graphImageRequests.data(at: url) {
            let (data, _) = try await JarvisHTTP.sendTransient(imageRequest, config: config, session: graphSession)
            guard data.count <= 20_000_000 else { throw MemoryGraphError.invalidShape }
            return data
        }
    }

    private func defaultPort(_ scheme: String?) -> Int? {
        switch scheme?.lowercased() { case "https": return 443; case "http": return 80; default: return nil }
    }
}
