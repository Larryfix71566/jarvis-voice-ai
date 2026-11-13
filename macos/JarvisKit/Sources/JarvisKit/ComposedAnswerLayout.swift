import Foundation

/// Validated, in-memory v1 display structure. Unknown keys are discarded from
/// rendering decisions; unknown block types are skipped, not interpreted.
public struct ComposedAnswerLayout: Sendable, Equatable, Decodable {
    public let version: Int
    public let revision: Int
    public let template: String
    public let title: String
    public let summary: String
    public let complete: Bool
    public let blocks: [ComposedAnswerBlock]

    public init(from decoder: Decoder) throws {
        let raw = try JSONValue(from: decoder)
        let v = LayoutFields(raw)
        version = try v.integer("version", minimum: 1)
        guard version == 1 else { throw LayoutError.invalid }
        revision = try v.integer("revision", minimum: 1)
        template = try v.string("template", 40)
        title = try v.string("title", 120)
        summary = try v.string("summary", 600)
        complete = try v.boolean("complete")
        let values = try v.array("blocks", minimum: 1, maximum: 24)
        var decoded: [ComposedAnswerBlock] = []
        var ids = Set<String>()
        var budgetBlocks: [JSONValue] = []
        for value in values {
            let fields = LayoutFields(value)
            let id = try fields.string("id", 40)
            guard ids.insert(id).inserted else { throw LayoutError.invalid }
            let type = try fields.string("type", 80)
            if type == "actions" { throw LayoutError.invalid } // C7 owns safe action routing.
            if let kind = ComposedAnswerBlock.Kind(rawValue: type) {
                let block = try ComposedAnswerBlock(value, kind: kind)
                if kind == .header, !budgetBlocks.isEmpty { throw LayoutError.invalid }
                decoded.append(block)
            }
            // Match the composer budget: wrapper payload fields are excluded.
            var budget = value.objectValue ?? [:]
            if type == "roadmap", let roadmap = budget["roadmap"] {
                guard try JSONEncoder().encode(roadmap).count <= 1024 * 1024 else { throw LayoutError.invalid }
            }
            let wrapperKeys: [String: [String]] = [
                "weather": ["weather"], "brief": ["brief"], "roadmap": ["roadmap", "roadmap_timezone"],
                "commands": ["commands", "note", "expect_output"], "graph": ["image_url", "summary"]
            ]
            for key in wrapperKeys[type] ?? [] { budget.removeValue(forKey: key) }
            budgetBlocks.append(.object(budget))
        }
        guard !decoded.isEmpty else { throw LayoutError.invalid }
        var budget = raw.objectValue ?? [:]
        budget["blocks"] = .array(budgetBlocks)
        guard try JSONEncoder().encode(JSONValue.object(budget)).count <= 256 * 1024 else { throw LayoutError.invalid }
        blocks = decoded
    }

    /// Completion-only revisions do not represent updated answer content.
    public func hasSameContent(as other: Self) -> Bool {
        version == other.version && template == other.template && title == other.title
            && summary == other.summary && blocks == other.blocks
    }
}

public struct ComposedAnswerBlock: Sendable, Equatable, Identifiable {
    public enum Kind: String, Sendable { case header, stats, list, chart, text, media, sources, weather, brief, roadmap, commands, graph }
    public let id: String
    public let type: Kind
    /// Validated fields, available to native views without re-decoding JSON.
    public let data: JSONValue
    public let weather: WeatherCard?
    public let brief: BriefCard?
    public let roadmap: RoadmapSnapshot?
    public var a11y: String? { data["a11y"]?.stringValue }

    fileprivate init(_ raw: JSONValue, kind: Kind) throws {
        let v = LayoutFields(raw)
        id = try v.string("id", 40); type = kind
        _ = try v.optionalString("a11y", 300)
        if let source = raw["source"], source != .null {
            let s = LayoutFields(source)
            guard source.objectValue != nil else { throw LayoutError.invalid }
            _ = try s.optionalString("tool", 80); _ = try s.optionalString("run_id", 120); _ = try s.optionalString("agent", 80)
        }
        var w: WeatherCard?; var b: BriefCard?; var r: RoadmapSnapshot?
        switch kind {
        case .header:
            _ = try v.string("title", 120); _ = try v.string("summary", 600)
            for item in try (raw["agents"] == nil ? [] : v.array("agents", maximum: 6)) {
                let a = LayoutFields(item); _ = try a.string("name", 80)
                if item["latency_ms"] != nil { _ = try a.integer("latency_ms", minimum: 0) }
            }
        case .stats:
            for item in try v.array("items", minimum: 1, maximum: 4) {
                let a = LayoutFields(item); _ = try a.string("value", 16); _ = try a.string("label", 60); try a.tone()
            }
        case .list:
            _ = try v.optionalString("title", 120)
            for item in try v.array("items", maximum: 12) {
                let a = LayoutFields(item); _ = try a.string("title", 120)
                _ = try a.optionalString("detail", 240); _ = try a.optionalString("meta", 40); try a.tone()
            }
            if raw["more_count"] != nil { _ = try v.integer("more_count", minimum: 0) }
        case .chart:
            _ = try v.optionalString("title", 120); _ = try v.optionalString("unit", 16)
            guard try v.string("chart", 40) == "bar" else { throw LayoutError.invalid }
            _ = try v.string("a11y", 300)
            for item in try v.array("points", minimum: 2, maximum: 48) {
                let a = LayoutFields(item); _ = try a.string("label", 16)
                guard let number = item["value"]?.doubleValue, number.isFinite else { throw LayoutError.invalid }
                if item["highlight"] != nil { _ = try a.boolean("highlight") }
            }
        case .text:
            guard ["markdown", "plain"].contains(try v.string("format", 16)) else { throw LayoutError.invalid }
            _ = try v.string("text", 30_000)
        case .media:
            _ = try v.string("a11y", 300); _ = try v.optionalString("caption", 240)
            try v.urls("images", maximum: 9)
            if raw["basemap_images"] != nil { try v.urls("basemap_images", maximum: 9) }
        case .sources:
            for item in try v.array("items", maximum: 12) {
                let a = LayoutFields(item); _ = try a.string("label", 120)
                if let url = try a.optionalString("url", 2048) { try LayoutFields.url(url) }
            }
        case .weather: w = try v.model("weather")
        case .brief: b = try v.model("brief")
        case .roadmap:
            r = try v.model("roadmap")
            guard r?.isValid == true else { throw LayoutError.invalid }
            _ = try v.optionalString("roadmap_timezone", 80)
        case .commands:
            for command in try v.array("commands", maximum: 1000) {
                guard let text = command.stringValue, text.unicodeScalars.count <= 30_000 else { throw LayoutError.invalid }
            }
            _ = try v.optionalString("note", 600)
            if raw["expect_output"] != nil { _ = try v.boolean("expect_output") }
        case .graph:
            try LayoutFields.url(v.string("image_url", 2048))
            _ = try v.optionalString("summary", 600)
        }
        data = raw; weather = w; brief = b; roadmap = r
    }
}

private enum LayoutError: Error { case invalid }
private struct LayoutFields {
    let raw: JSONValue
    init(_ raw: JSONValue) { self.raw = raw }
    func string(_ key: String, _ limit: Int) throws -> String {
        guard let value = raw[key]?.stringValue, value.unicodeScalars.count <= limit else { throw LayoutError.invalid }
        return value
    }
    func optionalString(_ key: String, _ limit: Int) throws -> String? {
        guard let value = raw[key], value != .null else { return nil }
        return try string(key, limit)
    }
    func integer(_ key: String, minimum: Int) throws -> Int {
        guard let n = raw[key]?.doubleValue, n.isFinite, n >= Double(minimum),
              n < Double(Int.max), n.rounded(.towardZero) == n else { throw LayoutError.invalid }
        return Int(n)
    }
    func boolean(_ key: String) throws -> Bool {
        guard let value = raw[key]?.boolValue else { throw LayoutError.invalid }; return value
    }
    func array(_ key: String, minimum: Int = 0, maximum: Int) throws -> [JSONValue] {
        guard let value = raw[key]?.arrayValue, (minimum...maximum).contains(value.count) else { throw LayoutError.invalid }; return value
    }
    func tone() throws {
        if let tone = try optionalString("tone", 16), !["neutral", "ok", "approval", "error"].contains(tone) { throw LayoutError.invalid }
    }
    func model<T: Decodable>(_ key: String) throws -> T {
        guard let value = raw[key] else { throw LayoutError.invalid }
        return try JSONDecoder().decode(T.self, from: JSONEncoder().encode(value))
    }
    func urls(_ key: String, maximum: Int) throws {
        for value in try array(key, maximum: maximum) {
            guard let text = value.stringValue else { throw LayoutError.invalid }; try Self.url(text)
        }
    }
    static func url(_ text: String) throws {
        guard text.unicodeScalars.count <= 2048,
              !text.unicodeScalars.contains(where: { $0.value < 0x21 || $0.value == 0x7f }),
              let url = URLComponents(string: text), let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme), let host = url.host, !host.isEmpty,
              url.user == nil, url.password == nil else { throw LayoutError.invalid }
    }
}
