import Foundation

public enum PhoneRemoteOperation: String, Codable, CaseIterable, Sendable {
    case sessionStatus = "session.status"
    case voiceOffer = "voice.offer"
    case voiceUpdate = "voice.update"
    case voiceEnd = "voice.end"
    case resultsSnapshot = "results.snapshot"
    case resultsResume = "results.resume"
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

public enum PhoneRemoteEnvelopeKind: String, Codable, Sendable {
    case request
    case response
}

public enum PhoneRemoteProtocolError: Error, Equatable {
    case unsupportedKind(String)
    case unsupportedVersion(Int)
    case duplicateKey(String)
}

private struct AnyCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?
    init?(stringValue: String) { self.stringValue = stringValue; self.intValue = nil }
    init?(intValue: Int) { self.stringValue = String(intValue); self.intValue = intValue }
}

public struct PhoneRemoteRequest<Payload: Codable & Sendable>: Codable, Sendable {
    public static var kind: PhoneRemoteEnvelopeKind { .request }
    public static var protocolVersion: Int { 1 }

    public let protocolKind: PhoneRemoteEnvelopeKind
    public let protocolVersion: Int
    public let requestID: String
    public let operation: PhoneRemoteOperation
    public let payload: Payload

    public init(requestID: String, operation: PhoneRemoteOperation, payload: Payload) {
        self.protocolKind = .request
        self.protocolVersion = Self.protocolVersion
        self.requestID = requestID
        self.operation = operation
        self.payload = payload
    }

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case kind, protocolVersion = "protocol_version", requestID = "request_id", operation, payload
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        try Self.rejectUnknownKeys(container, allowed: Set(CodingKeys.allCases.map(\.rawValue)))
        let kind = try container.decode(PhoneRemoteEnvelopeKind.self, forKey: AnyCodingKey(stringValue: "kind")!)
        guard kind == .request else { throw PhoneRemoteProtocolError.unsupportedKind(kind.rawValue) }
        let version = try container.decode(Int.self, forKey: AnyCodingKey(stringValue: "protocol_version")!)
        guard version == Self.protocolVersion else { throw PhoneRemoteProtocolError.unsupportedVersion(version) }
        protocolKind = kind
        protocolVersion = version
        requestID = try container.decode(String.self, forKey: AnyCodingKey(stringValue: "request_id")!)
        operation = try container.decode(PhoneRemoteOperation.self, forKey: AnyCodingKey(stringValue: "operation")!)
        payload = try container.decode(Payload.self, forKey: AnyCodingKey(stringValue: "payload")!)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(protocolKind, forKey: .kind)
        try container.encode(protocolVersion, forKey: .protocolVersion)
        try container.encode(requestID, forKey: .requestID)
        try container.encode(operation, forKey: .operation)
        try container.encode(payload, forKey: .payload)
    }

    private static func rejectUnknownKeys(_ container: KeyedDecodingContainer<AnyCodingKey>, allowed: Set<String>) throws {
        if let extra = container.allKeys.map(\.stringValue).first(where: { !allowed.contains($0) }) {
            throw DecodingError.dataCorrupted(.init(codingPath: container.codingPath, debugDescription: "Unknown envelope key: \(extra)"))
        }
    }
}

public struct PhoneRemoteResponse<Payload: Codable & Sendable, Reason: Codable & Sendable>: Codable, Sendable {
    public static var protocolVersion: Int { 1 }

    public let protocolKind: PhoneRemoteEnvelopeKind
    public let protocolVersion: Int
    public let requestID: String
    public let status: PhoneRemoteStatus
    public let reason: Reason
    public let payload: Payload

    public init(requestID: String, status: PhoneRemoteStatus, reason: Reason, payload: Payload) {
        self.protocolKind = .response
        self.protocolVersion = Self.protocolVersion
        self.requestID = requestID
        self.status = status
        self.reason = reason
        self.payload = payload
    }

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case kind, protocolVersion = "protocol_version", requestID = "request_id", status, reason, payload
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        let allowed = Set(CodingKeys.allCases.map(\.rawValue))
        if let extra = container.allKeys.map(\.stringValue).first(where: { !allowed.contains($0) }) {
            throw DecodingError.dataCorrupted(.init(codingPath: container.codingPath, debugDescription: "Unknown envelope key: \(extra)"))
        }
        let kind = try container.decode(PhoneRemoteEnvelopeKind.self, forKey: AnyCodingKey(stringValue: "kind")!)
        guard kind == .response else { throw PhoneRemoteProtocolError.unsupportedKind(kind.rawValue) }
        let version = try container.decode(Int.self, forKey: AnyCodingKey(stringValue: "protocol_version")!)
        guard version == Self.protocolVersion else { throw PhoneRemoteProtocolError.unsupportedVersion(version) }
        protocolKind = kind
        protocolVersion = version
        requestID = try container.decode(String.self, forKey: AnyCodingKey(stringValue: "request_id")!)
        status = try container.decode(PhoneRemoteStatus.self, forKey: AnyCodingKey(stringValue: "status")!)
        reason = try container.decode(Reason.self, forKey: AnyCodingKey(stringValue: "reason")!)
        payload = try container.decode(Payload.self, forKey: AnyCodingKey(stringValue: "payload")!)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(protocolKind, forKey: .kind)
        try container.encode(protocolVersion, forKey: .protocolVersion)
        try container.encode(requestID, forKey: .requestID)
        try container.encode(status, forKey: .status)
        try container.encode(reason, forKey: .reason)
        try container.encode(payload, forKey: .payload)
    }
}

public enum PhoneRemoteJSON {
    public static func decodeRequest<Payload: Codable & Sendable>(_ type: PhoneRemoteRequest<Payload>.Type, from data: Data) throws -> PhoneRemoteRequest<Payload> {
        try rejectDuplicateKeys(in: data)
        return try JSONDecoder().decode(type, from: data)
    }

    public static func decodeResponse<Payload: Codable & Sendable, Reason: Codable & Sendable>(_ type: PhoneRemoteResponse<Payload, Reason>.Type, from data: Data) throws -> PhoneRemoteResponse<Payload, Reason> {
        try rejectDuplicateKeys(in: data)
        return try JSONDecoder().decode(type, from: data)
    }

    private static func rejectDuplicateKeys(in data: Data) throws {
        var scanner = DuplicateKeyScanner(bytes: Array(data))
        try scanner.scan()
    }
}

private struct DuplicateKeyScanner {
    let bytes: [UInt8]
    var index = 0

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
                let raw = Data(bytes[start..<index])
                return try JSONDecoder().decode(String.self, from: raw)
            }
            if byte == 0x5C {
                guard index < bytes.count else { throw malformed() }
                index += 1
            } else if byte < 0x20 {
                throw malformed()
            }
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
