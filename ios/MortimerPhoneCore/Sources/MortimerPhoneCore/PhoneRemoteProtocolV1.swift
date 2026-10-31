import Foundation

public enum PhoneRemoteOperation: String, Codable, CaseIterable, Sendable {
    case sessionStatus = "session.status"
    case voiceOffer = "voice.offer"
    case voiceUpdate = "voice.update"
    case voiceEnd = "voice.end"
    case resultsSnapshot = "results.snapshot"
    case resultsResume = "results.resume"
    case resultsView = "results.view"
    case resultsSelect = "results.select"
    case resultsPin = "results.pin"
    case resultsUnpin = "results.unpin"
    case resultsClose = "results.close"
    case resultsReopen = "results.reopen"
    case callState = "call.state"
    case callAnswer = "call.answer"
    case callDecline = "call.decline"
}

public enum PhoneRemoteStatus: String, Codable, CaseIterable, Sendable {
    case ok
    case denied
    case unavailable
    case incompatible
}

public enum PhoneRemoteProtocolError: Error, Equatable {
    case unsupportedKind(String)
    case unsupportedVersion(Int)
    case duplicateKey(String)
    case inputTooLarge
    case nestingTooDeep
}

private struct AnyCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?
    init?(stringValue: String) { self.stringValue = stringValue; self.intValue = nil }
    init?(intValue: Int) { self.stringValue = String(intValue); self.intValue = intValue }
}

public struct PhoneRemoteRequest<Payload: Codable & Sendable>: Encodable, Sendable {
    public static var kind: String { "mortimer.phone-remote.v1" }
    public static var protocolVersion: Int { 1 }

    public let kind: String
    public let protocolVersion: Int
    public let requestID: String
    public let operation: PhoneRemoteOperation
    public let payload: Payload

    public init(requestID: String, operation: PhoneRemoteOperation, payload: Payload) {
        kind = Self.kind
        protocolVersion = Self.protocolVersion
        self.requestID = requestID
        self.operation = operation
        self.payload = payload
    }

    private enum CodingKeys: String, CodingKey {
        case kind, protocolVersion = "protocol_version", requestID = "request_id", operation, payload
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(kind, forKey: .kind)
        try container.encode(protocolVersion, forKey: .protocolVersion)
        try container.encode(requestID, forKey: .requestID)
        try container.encode(operation, forKey: .operation)
        try container.encode(payload, forKey: .payload)
    }
}

public struct PhoneRemoteResponse<Payload: Codable & Sendable, Reason: Codable & Sendable>: Encodable, Sendable {
    public let requestID: String
    public let status: PhoneRemoteStatus
    public let reason: Reason
    public let payload: Payload

    public init(requestID: String, status: PhoneRemoteStatus, reason: Reason, payload: Payload) {
        self.requestID = requestID
        self.status = status
        self.reason = reason
        self.payload = payload
    }

    private enum CodingKeys: String, CodingKey {
        case requestID = "request_id", status, reason, payload
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(requestID, forKey: .requestID)
        try container.encode(status, forKey: .status)
        try container.encode(reason, forKey: .reason)
        try container.encode(payload, forKey: .payload)
    }
}

public enum PhoneRemoteJSON {
    private static let maximumInputBytes = 1_048_576

    public static func decodeRequest<Payload: Codable & Sendable>(_ type: PhoneRemoteRequest<Payload>.Type, from data: Data) throws -> PhoneRemoteRequest<Payload> {
        try validateAndScan(data)
        let wire = try JSONDecoder().decode(RequestWire<Payload>.self, from: data)
        guard wire.kind == PhoneRemoteRequest<Payload>.kind else {
            throw PhoneRemoteProtocolError.unsupportedKind(wire.kind)
        }
        guard wire.protocolVersion == PhoneRemoteRequest<Payload>.protocolVersion else {
            throw PhoneRemoteProtocolError.unsupportedVersion(wire.protocolVersion)
        }
        return PhoneRemoteRequest(requestID: wire.requestID, operation: wire.operation, payload: wire.payload)
    }

    public static func decodeResponse<Payload: Codable & Sendable, Reason: Codable & Sendable>(_ type: PhoneRemoteResponse<Payload, Reason>.Type, from data: Data) throws -> PhoneRemoteResponse<Payload, Reason> {
        try validateAndScan(data)
        let wire = try JSONDecoder().decode(ResponseWire<Payload, Reason>.self, from: data)
        return PhoneRemoteResponse(requestID: wire.requestID, status: wire.status, reason: wire.reason, payload: wire.payload)
    }

    private static func validateAndScan(_ data: Data) throws {
        guard data.count <= maximumInputBytes else { throw PhoneRemoteProtocolError.inputTooLarge }
        let bytes = Array(data)
        try DuplicateKeyScanner.validateNesting(bytes)
        var scanner = DuplicateKeyScanner(bytes: bytes)
        try scanner.scan()
    }
}

private struct RequestWire<Payload: Decodable>: Decodable {
    let kind: String
    let protocolVersion: Int
    let requestID: String
    let operation: PhoneRemoteOperation
    let payload: Payload

    private enum Keys: String, CaseIterable { case kind, protocolVersion = "protocol_version", requestID = "request_id", operation, payload }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        try rejectUnknownKeys(container, allowed: Set(Keys.allCases.map(\.rawValue)))
        kind = try container.decode(String.self, forKey: key("kind"))
        protocolVersion = try container.decode(Int.self, forKey: key("protocol_version"))
        requestID = try container.decode(String.self, forKey: key("request_id"))
        operation = try container.decode(PhoneRemoteOperation.self, forKey: key("operation"))
        payload = try container.decode(Payload.self, forKey: key("payload"))
    }
}

private struct ResponseWire<Payload: Decodable, Reason: Decodable>: Decodable {
    let requestID: String
    let status: PhoneRemoteStatus
    let reason: Reason
    let payload: Payload

    private enum Keys: String, CaseIterable { case requestID = "request_id", status, reason, payload }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        try rejectUnknownKeys(container, allowed: Set(Keys.allCases.map(\.rawValue)))
        requestID = try container.decode(String.self, forKey: key("request_id"))
        status = try container.decode(PhoneRemoteStatus.self, forKey: key("status"))
        reason = try container.decode(Reason.self, forKey: key("reason"))
        payload = try container.decode(Payload.self, forKey: key("payload"))
    }
}

private func key(_ name: String) -> AnyCodingKey { AnyCodingKey(stringValue: name)! }

private func rejectUnknownKeys(_ container: KeyedDecodingContainer<AnyCodingKey>, allowed: Set<String>) throws {
    if let extra = container.allKeys.map(\.stringValue).first(where: { !allowed.contains($0) }) {
        throw DecodingError.dataCorrupted(.init(codingPath: container.codingPath, debugDescription: "Unknown envelope key: \(extra)"))
    }
}

private struct DuplicateKeyScanner {
    let bytes: [UInt8]
    var index = 0

    static func validateNesting(_ bytes: [UInt8]) throws {
        var depth = 0
        var inString = false
        var escaped = false
        for byte in bytes {
            if inString {
                if escaped { escaped = false }
                else if byte == 0x5C { escaped = true }
                else if byte == 0x22 { inString = false }
                continue
            }
            if byte == 0x22 { inString = true }
            else if byte == 0x7B || byte == 0x5B {
                depth += 1
                guard depth <= 64 else { throw PhoneRemoteProtocolError.nestingTooDeep }
            } else if byte == 0x7D || byte == 0x5D { depth -= 1 }
        }
    }

    mutating func scan() throws {
        skipWhitespace()
        try value()
        skipWhitespace()
        guard index == bytes.count else { throw malformed() }
    }

    mutating func value() throws {
        skipWhitespace()
        guard index < bytes.count else { throw malformed() }
        switch bytes[index] {
        case 0x7B: try object()
        case 0x5B: try array()
        case 0x22: _ = try string()
        default: try primitive()
        }
    }

    mutating func object() throws {
        index += 1
        skipWhitespace()
        if consume(0x7D) { return }
        var keys = Set<String>()
        while true {
            skipWhitespace()
            guard index < bytes.count, bytes[index] == 0x22 else { throw malformed() }
            let key = try string()
            guard keys.insert(key).inserted else { throw PhoneRemoteProtocolError.duplicateKey(key) }
            skipWhitespace()
            guard consume(0x3A) else { throw malformed() }
            try value()
            skipWhitespace()
            if consume(0x7D) { return }
            guard consume(0x2C) else { throw malformed() }
        }
    }

    mutating func array() throws {
        index += 1
        skipWhitespace()
        if consume(0x5D) { return }
        while true {
            try value()
            skipWhitespace()
            if consume(0x5D) { return }
            guard consume(0x2C) else { throw malformed() }
        }
    }

    mutating func string() throws -> String {
        let start = index
        index += 1
        while index < bytes.count {
            let byte = bytes[index]
            index += 1
            if byte == 0x22 {
                return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index]))
            }
            if byte == 0x5C {
                guard index < bytes.count else { throw malformed() }
                index += 1
            } else if byte < 0x20 { throw malformed() }
        }
        throw malformed()
    }

    mutating func primitive() throws {
        let start = index
        while index < bytes.count && ![0x20, 0x09, 0x0A, 0x0D, 0x2C, 0x5D, 0x7D].contains(bytes[index]) { index += 1 }
        guard index > start else { throw malformed() }
    }

    mutating func skipWhitespace() {
        while index < bytes.count && [0x20, 0x09, 0x0A, 0x0D].contains(bytes[index]) { index += 1 }
    }

    mutating func consume(_ byte: UInt8) -> Bool {
        guard index < bytes.count, bytes[index] == byte else { return false }
        index += 1
        return true
    }

    func malformed() -> DecodingError {
        .dataCorrupted(.init(codingPath: [], debugDescription: "Malformed JSON while checking duplicate keys"))
    }
}
