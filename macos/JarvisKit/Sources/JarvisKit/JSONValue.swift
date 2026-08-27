import Foundation

/// A recursive, order-preserving-enough JSON value used for every
/// AdminAPI response body (N14) and as the intermediate form
/// AppMessage.decode(frame:) parses before dispatching on "type".
public enum JSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let v = try? container.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? container.decode(Double.self) {
            self = .number(v)
        } else if let v = try? container.decode(String.self) {
            self = .string(v)
        } else if let v = try? container.decode([JSONValue].self) {
            self = .array(v)
        } else if let v = try? container.decode([String: JSONValue].self) {
            self = .object(v)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "JSONValue: unrecognised JSON shape"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let v): try container.encode(v)
        case .number(let v): try container.encode(v)
        case .string(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        }
    }

    public subscript(_ key: String) -> JSONValue? {
        if case .object(let obj) = self { return obj[key] }
        return nil
    }

    public var stringValue: String? {
        if case .string(let v) = self { return v }
        return nil
    }
    public var doubleValue: Double? {
        if case .number(let v) = self { return v }
        return nil
    }
    public var intValue: Int? {
        if case .number(let v) = self { return Int(v) }
        return nil
    }
    public var boolValue: Bool? {
        if case .bool(let v) = self { return v }
        return nil
    }
    public var arrayValue: [JSONValue]? {
        if case .array(let v) = self { return v }
        return nil
    }
    public var objectValue: [String: JSONValue]? {
        if case .object(let v) = self { return v }
        return nil
    }
}
