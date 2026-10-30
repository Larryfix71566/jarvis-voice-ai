import Foundation
import CoreFoundation

public enum PhoneRemoteOperationReason: String, Codable, CaseIterable, Sendable {
    case none
    case featureOff = "feature_off"
    case malformedRequest = "malformed_request"
    case unsupportedProtocol = "unsupported_protocol"
    case notAuthorized = "not_authorized"
    case authorityUnavailable = "authority_unavailable"
    case voiceNotReady = "voice_not_ready"
    case ownerBusy = "owner_busy"
    case operationUnavailable = "operation_unavailable"
    case requestConflict = "request_conflict"
    case requestCapacity = "request_capacity"
}

public struct PhoneRemoteOperationRequest: Codable, Equatable, Sendable {
    public enum Payload: Equatable, Sendable {
        case sessionStatus
        case voiceOffer(sdp: String)
        case voiceUpdate(peerID: String, sdp: String)
        case voiceEnd(peerID: String)
    }

    public let requestID: String
    public let operation: PhoneRemoteOperation
    public let payload: Payload

    public init(requestID: String, payload: Payload) throws {
        try Self.validateRequestID(requestID)
        self.requestID = requestID
        self.payload = payload
        switch payload {
        case .sessionStatus: operation = .sessionStatus
        case .voiceOffer: operation = .voiceOffer
        case .voiceUpdate: operation = .voiceUpdate
        case .voiceEnd: operation = .voiceEnd
        }
        try Self.validatePayload(payload)
    }

    private enum CodingKeys: String, CodingKey {
        case kind, protocolVersion = "protocol_version", requestID = "request_id", operation, payload
    }

    public func encode(to encoder: Encoder) throws {
        var root = encoder.container(keyedBy: CodingKeys.self)
        try root.encode("mortimer.phone-remote.v1", forKey: .kind)
        try root.encode(1, forKey: .protocolVersion)
        try root.encode(requestID, forKey: .requestID)
        try root.encode(operation, forKey: .operation)
        var body = root.nestedContainer(keyedBy: OperationPayloadKey.self, forKey: .payload)
        switch payload {
        case .sessionStatus:
            break
        case .voiceOffer(let sdp):
            try body.encode(sdp, forKey: .sdp)
        case .voiceUpdate(let peerID, let sdp):
            try body.encode(peerID, forKey: .peerID)
            try body.encode(sdp, forKey: .sdp)
        case .voiceEnd(let peerID):
            try body.encode(peerID, forKey: .peerID)
        }
    }

    public init(from decoder: Decoder) throws {
        guard decoder.userInfo[.checkedPhoneRemoteOperations] as? UUID == checkedDecoderPermit else {
            throw PhoneRemoteOperationsError.uncheckedDecoder
        }
        let root = try decoder.container(keyedBy: AnyOperationCodingKey.self)
        try rejectKeys(root, allowed: ["kind", "protocol_version", "request_id", "operation", "payload"])
        let kind = try root.decode(String.self, forKey: codingKey("kind"))
        let version = try root.decode(Int.self, forKey: codingKey("protocol_version"))
        guard kind == "mortimer.phone-remote.v1", version == 1 else {
            throw PhoneRemoteOperationsError.invalidEnvelope
        }
        let requestID = try root.decode(String.self, forKey: codingKey("request_id"))
        try Self.validateRequestID(requestID)
        let operation = try root.decode(PhoneRemoteOperation.self, forKey: codingKey("operation"))
        let body = try root.nestedContainer(keyedBy: AnyOperationCodingKey.self, forKey: codingKey("payload"))
        let payload: Payload
        switch operation {
        case .sessionStatus:
            try rejectKeys(body, allowed: [])
            payload = .sessionStatus
        case .voiceOffer:
            try rejectKeys(body, allowed: ["sdp"])
            payload = .voiceOffer(sdp: try body.decode(String.self, forKey: codingKey("sdp")))
        case .voiceUpdate:
            try rejectKeys(body, allowed: ["peer_id", "sdp"])
            payload = .voiceUpdate(
                peerID: try body.decode(String.self, forKey: codingKey("peer_id")),
                sdp: try body.decode(String.self, forKey: codingKey("sdp"))
            )
        case .voiceEnd:
            try rejectKeys(body, allowed: ["peer_id"])
            payload = .voiceEnd(peerID: try body.decode(String.self, forKey: codingKey("peer_id")))
        default:
            throw PhoneRemoteOperationsError.unsupportedOperation
        }
        try Self.validatePayload(payload)
        self.requestID = requestID
        self.operation = operation
        self.payload = payload
    }

    fileprivate static func validateRequestID(_ value: String) throws {
        guard !value.isEmpty, let bytes = value.data(using: .utf8), bytes.count <= 128 else {
            throw PhoneRemoteOperationsError.invalidRequestID
        }
    }

    fileprivate static func validatePayload(_ payload: Payload) throws {
        func valid(_ value: String) -> Bool { !value.isEmpty && value.data(using: .utf8) != nil }
        switch payload {
        case .sessionStatus:
            break
        case .voiceOffer(let sdp):
            guard valid(sdp) else { throw PhoneRemoteOperationsError.invalidPayload }
        case .voiceUpdate(let peerID, let sdp):
            guard valid(peerID), valid(sdp) else { throw PhoneRemoteOperationsError.invalidPayload }
        case .voiceEnd(let peerID):
            guard valid(peerID) else { throw PhoneRemoteOperationsError.invalidPayload }
        }
    }
}

public struct PhoneRemoteOperationResponse: Codable, Equatable, Sendable {
    public enum Payload: Equatable, Sendable {
        case sessionStatus(readiness: String)
        case voiceOffer(peerID: String, sdp: String)
        case voiceUpdate(peerID: String, sdp: String)
        case voiceEnd(peerID: String, ended: Bool)
        case empty
    }

    public let requestID: String
    /// Local schema discriminator; R3.9 does not put operation in response JSON.
    public let operation: PhoneRemoteOperation
    public let status: PhoneRemoteStatus
    public let reason: PhoneRemoteOperationReason
    public let payload: Payload

    public init(requestID: String, operation: PhoneRemoteOperation, status: PhoneRemoteStatus,
                reason: PhoneRemoteOperationReason, payload: Payload) throws {
        try PhoneRemoteOperationRequest.validateRequestID(requestID)
        try Self.validate(operation: operation, status: status, reason: reason, payload: payload)
        self.requestID = requestID
        self.operation = operation
        self.status = status
        self.reason = reason
        self.payload = payload
    }

    private enum CodingKeys: String, CodingKey { case requestID = "request_id", status, reason, payload }

    public func encode(to encoder: Encoder) throws {
        try PhoneRemoteOperationRequest.validateRequestID(requestID)
        try Self.validate(operation: operation, status: status, reason: reason, payload: payload)
        var root = encoder.container(keyedBy: CodingKeys.self)
        try root.encode(requestID, forKey: .requestID)
        try root.encode(status, forKey: .status)
        try root.encode(reason, forKey: .reason)
        var body = root.nestedContainer(keyedBy: AnyOperationCodingKey.self, forKey: .payload)
        switch payload {
        case .sessionStatus(let readiness): try body.encode(readiness, forKey: codingKey("readiness"))
        case .voiceOffer(let peerID, let sdp), .voiceUpdate(let peerID, let sdp):
            try body.encode(peerID, forKey: codingKey("peer_id")); try body.encode(sdp, forKey: codingKey("sdp"))
        case .voiceEnd(let peerID, let ended):
            try body.encode(peerID, forKey: codingKey("peer_id")); try body.encode(ended, forKey: codingKey("ended"))
        case .empty: break
        }
    }

    public init(from decoder: Decoder) throws {
        guard decoder.userInfo[.checkedPhoneRemoteOperations] as? UUID == checkedDecoderPermit else {
            throw PhoneRemoteOperationsError.uncheckedDecoder
        }
        guard let operation = decoder.userInfo[.phoneRemoteOperation] as? PhoneRemoteOperation else {
            throw PhoneRemoteOperationsError.unsupportedOperation
        }
        let root = try decoder.container(keyedBy: AnyOperationCodingKey.self)
        try rejectKeys(root, allowed: ["request_id", "status", "reason", "payload"])
        let requestID = try root.decode(String.self, forKey: codingKey("request_id"))
        let status = try root.decode(PhoneRemoteStatus.self, forKey: codingKey("status"))
        let reason = try root.decode(PhoneRemoteOperationReason.self, forKey: codingKey("reason"))
        let body = try root.nestedContainer(keyedBy: AnyOperationCodingKey.self, forKey: codingKey("payload"))
        let payload: Payload
        if status != .ok {
            try rejectKeys(body, allowed: [])
            payload = .empty
        } else {
            switch operation {
            case .sessionStatus:
                try rejectKeys(body, allowed: ["readiness"])
                payload = .sessionStatus(readiness: try body.decode(String.self, forKey: codingKey("readiness")))
            case .voiceOffer:
                try rejectKeys(body, allowed: ["peer_id", "sdp"])
                payload = .voiceOffer(peerID: try body.decode(String.self, forKey: codingKey("peer_id")), sdp: try body.decode(String.self, forKey: codingKey("sdp")))
            case .voiceUpdate:
                try rejectKeys(body, allowed: ["peer_id", "sdp"])
                payload = .voiceUpdate(peerID: try body.decode(String.self, forKey: codingKey("peer_id")), sdp: try body.decode(String.self, forKey: codingKey("sdp")))
            case .voiceEnd:
                try rejectKeys(body, allowed: ["peer_id", "ended"])
                payload = .voiceEnd(peerID: try body.decode(String.self, forKey: codingKey("peer_id")), ended: try body.decode(Bool.self, forKey: codingKey("ended")))
            default: throw PhoneRemoteOperationsError.unsupportedOperation
            }
        }
        try PhoneRemoteOperationRequest.validateRequestID(requestID)
        try Self.validate(operation: operation, status: status, reason: reason, payload: payload)
        self.requestID = requestID
        self.operation = operation
        self.status = status
        self.reason = reason
        self.payload = payload
    }

    fileprivate static func validate(operation: PhoneRemoteOperation, status: PhoneRemoteStatus,
                                      reason: PhoneRemoteOperationReason, payload: Payload) throws {
        guard [.sessionStatus, .voiceOffer, .voiceUpdate, .voiceEnd].contains(operation) else {
            throw PhoneRemoteOperationsError.unsupportedOperation
        }
        let reasonAllowed: Bool
        switch status {
        case .ok: reasonAllowed = reason == .none
        case .denied: reasonAllowed = [.malformedRequest, .notAuthorized, .requestConflict, .requestCapacity].contains(reason)
        case .unavailable: reasonAllowed = [.featureOff, .authorityUnavailable, .voiceNotReady, .ownerBusy, .operationUnavailable].contains(reason)
        case .incompatible: reasonAllowed = reason == .unsupportedProtocol
        }
        guard reasonAllowed else { throw PhoneRemoteOperationsError.invalidStatusReasonPair }

        if status != .ok {
            guard case .empty = payload else { throw PhoneRemoteOperationsError.invalidResponsePayload }
            return
        }
        switch (operation, payload) {
        case (.sessionStatus, .sessionStatus(let readiness)) where readiness == "ready": break
        case (.voiceOffer, .voiceOffer(let peerID, let sdp)), (.voiceUpdate, .voiceUpdate(let peerID, let sdp)):
            guard !peerID.isEmpty, !sdp.isEmpty else { throw PhoneRemoteOperationsError.invalidResponsePayload }
        case (.voiceEnd, .voiceEnd(let peerID, let ended)):
            guard !peerID.isEmpty, ended else { throw PhoneRemoteOperationsError.invalidResponsePayload }
        default:
            throw PhoneRemoteOperationsError.invalidResponsePayload
        }
    }
}

public enum PhoneRemoteOperationsError: Error, Equatable {
    case invalidEnvelope
    case invalidRequestID
    case unsupportedOperation
    case requestIDMismatch
    case invalidPayload
    case invalidResponsePayload
    case invalidStatusReasonPair
    case duplicateKey(String)
    case inputTooLarge
    case nestingTooDeep
    case malformedJSON
    case uncheckedDecoder
}

public extension CodingUserInfoKey {
    static let phoneRemoteOperation = CodingUserInfoKey(rawValue: "mortimer.phoneRemoteOperation")!
}

private extension CodingUserInfoKey {
    static let checkedPhoneRemoteOperations = CodingUserInfoKey(rawValue: "mortimer.checkedPhoneRemoteOperations")!
}

private let checkedDecoderPermit = UUID()

/// Checked JSON boundary for the four operation DTOs. Callers handling wire bytes
/// must use this type so duplicate keys and resource limits are checked before decoding.
public enum PhoneRemoteOperationsJSON {
    public static let maximumInputBytes = 1_048_576
    public static let maximumDepth = 64

    public static func decodeRequest(from data: Data) throws -> PhoneRemoteOperationRequest {
        try check(data)
        let root = try object(data)
        guard Set(root.keys) == ["kind", "protocol_version", "request_id", "operation", "payload"],
              root["kind"] as? String == "mortimer.phone-remote.v1",
              let version = exactInteger(root["protocol_version"]), version == 1 else {
            throw PhoneRemoteOperationsError.invalidEnvelope
        }
        let decoder = JSONDecoder()
        decoder.userInfo[.checkedPhoneRemoteOperations] = checkedDecoderPermit
        return try decoder.decode(PhoneRemoteOperationRequest.self, from: data)
    }

    public static func encodeRequest(_ request: PhoneRemoteOperationRequest) throws -> Data {
        try PhoneRemoteOperationRequest.validateRequestID(request.requestID)
        try PhoneRemoteOperationRequest.validatePayload(request.payload)
        var payload: [String: Any] = [:]
        switch request.payload {
        case .sessionStatus: break
        case .voiceOffer(let sdp): payload["sdp"] = sdp
        case .voiceUpdate(let peerID, let sdp): payload["peer_id"] = peerID; payload["sdp"] = sdp
        case .voiceEnd(let peerID): payload["peer_id"] = peerID
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "kind": "mortimer.phone-remote.v1", "protocol_version": 1,
            "request_id": request.requestID, "operation": request.operation.rawValue, "payload": payload,
        ], options: [.sortedKeys])
        guard data.count <= maximumInputBytes else { throw PhoneRemoteOperationsError.inputTooLarge }
        return data
    }

    public static func decodeResponse(from data: Data, for operation: PhoneRemoteOperation) throws -> PhoneRemoteOperationResponse {
        try check(data)
        guard [.sessionStatus, .voiceOffer, .voiceUpdate, .voiceEnd].contains(operation) else {
            throw PhoneRemoteOperationsError.unsupportedOperation
        }
        let decoder = JSONDecoder()
        decoder.userInfo[.checkedPhoneRemoteOperations] = checkedDecoderPermit
        decoder.userInfo[.phoneRemoteOperation] = operation
        return try decoder.decode(PhoneRemoteOperationResponse.self, from: data)
    }

    public static func encodeResponse(_ response: PhoneRemoteOperationResponse, for operation: PhoneRemoteOperation) throws -> Data {
        try PhoneRemoteOperationRequest.validateRequestID(response.requestID)
        try PhoneRemoteOperationResponse.validate(operation: operation, status: response.status, reason: response.reason, payload: response.payload)
        var payload: [String: Any] = [:]
        switch response.payload {
        case .sessionStatus(let readiness): payload["readiness"] = readiness
        case .voiceOffer(let peerID, let sdp), .voiceUpdate(let peerID, let sdp): payload["peer_id"] = peerID; payload["sdp"] = sdp
        case .voiceEnd(let peerID, let ended): payload["peer_id"] = peerID; payload["ended"] = ended
        case .empty: break
        }
        return try JSONSerialization.data(withJSONObject: [
            "request_id": response.requestID, "status": response.status.rawValue,
            "reason": response.reason.rawValue, "payload": payload,
        ], options: [.sortedKeys])
    }

    private static func check(_ data: Data) throws {
        guard data.count <= maximumInputBytes else { throw PhoneRemoteOperationsError.inputTooLarge }
        let bytes = Array(data)
        var scanner = DuplicateKeyScanner(bytes: bytes)
        try scanner.scan(maximumDepth: maximumDepth)
    }

    private static func object(_ data: Data) throws -> [String: Any] {
        do {
            guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                throw PhoneRemoteOperationsError.malformedJSON
            }
            return object
        } catch let error as PhoneRemoteOperationsError { throw error }
        catch { throw PhoneRemoteOperationsError.malformedJSON }
    }

    private static func exactInteger(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        guard !["f", "d"].contains(String(cString: number.objCType)) else { return nil }
        let double = number.doubleValue
        guard double.isFinite, double.rounded(.towardZero) == double,
              double >= Double(Int.min), double <= Double(Int.max) else { return nil }
        return number.intValue
    }
}

private struct DuplicateKeyScanner {
    let bytes: [UInt8]
    var index = 0

    mutating func scan(maximumDepth: Int) throws {
        skipWhitespace()
        try value(depth: 0, maximumDepth: maximumDepth)
        skipWhitespace()
        guard index == bytes.count else { throw PhoneRemoteOperationsError.malformedJSON }
    }

    mutating func value(depth: Int, maximumDepth: Int) throws {
        skipWhitespace()
        guard index < bytes.count else { throw PhoneRemoteOperationsError.malformedJSON }
        switch bytes[index] {
        case 0x7B: try object(depth: depth + 1, maximumDepth: maximumDepth)
        case 0x5B: try array(depth: depth + 1, maximumDepth: maximumDepth)
        case 0x22: _ = try string()
        default: try primitive()
        }
    }

    mutating func object(depth: Int, maximumDepth: Int) throws {
        guard depth <= maximumDepth else { throw PhoneRemoteOperationsError.nestingTooDeep }
        index += 1; skipWhitespace()
        if consume(0x7D) { return }
        var keys = Set<String>()
        while true {
            skipWhitespace()
            guard index < bytes.count, bytes[index] == 0x22 else { throw PhoneRemoteOperationsError.malformedJSON }
            let key = try string()
            guard keys.insert(key).inserted else { throw PhoneRemoteOperationsError.duplicateKey(key) }
            skipWhitespace(); guard consume(0x3A) else { throw PhoneRemoteOperationsError.malformedJSON }
            try value(depth: depth, maximumDepth: maximumDepth)
            skipWhitespace()
            if consume(0x7D) { return }
            guard consume(0x2C) else { throw PhoneRemoteOperationsError.malformedJSON }
        }
    }

    mutating func array(depth: Int, maximumDepth: Int) throws {
        guard depth <= maximumDepth else { throw PhoneRemoteOperationsError.nestingTooDeep }
        index += 1; skipWhitespace()
        if consume(0x5D) { return }
        while true {
            try value(depth: depth, maximumDepth: maximumDepth)
            skipWhitespace()
            if consume(0x5D) { return }
            guard consume(0x2C) else { throw PhoneRemoteOperationsError.malformedJSON }
        }
    }

    mutating func string() throws -> String {
        let start = index
        index += 1
        var escaped = false
        while index < bytes.count {
            let byte = bytes[index]; index += 1
            if escaped { escaped = false; continue }
            if byte == 0x5C { escaped = true; continue }
            if byte == 0x22 {
                let token = Data(bytes[start..<index])
                guard let value = try? JSONDecoder().decode(String.self, from: token) else {
                    throw PhoneRemoteOperationsError.malformedJSON
                }
                return value
            }
        }
        throw PhoneRemoteOperationsError.malformedJSON
    }

    mutating func primitive() throws {
        while index < bytes.count, ![0x20, 0x09, 0x0A, 0x0D, 0x2C, 0x5D, 0x7D].contains(bytes[index]) { index += 1 }
        guard index > 0 else { throw PhoneRemoteOperationsError.malformedJSON }
    }

    mutating func skipWhitespace() { while index < bytes.count, [0x20, 0x09, 0x0A, 0x0D].contains(bytes[index]) { index += 1 } }
    mutating func consume(_ byte: UInt8) -> Bool { guard index < bytes.count, bytes[index] == byte else { return false }; index += 1; return true }
}

private struct AnyOperationCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?
    init?(stringValue: String) { self.stringValue = stringValue; self.intValue = nil }
    init?(intValue: Int) { self.stringValue = String(intValue); self.intValue = intValue }
}

private enum OperationPayloadKey: String, CodingKey { case sdp, peerID = "peer_id" }
private func codingKey(_ name: String) -> AnyOperationCodingKey { AnyOperationCodingKey(stringValue: name)! }

private func rejectKeys(_ container: KeyedDecodingContainer<AnyOperationCodingKey>, allowed: Set<String>) throws {
    guard container.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
        throw PhoneRemoteOperationsError.invalidPayload
    }
}

private func rejectKeys(_ container: KeyedDecodingContainer<AnyOperationCodingKey>, allowed: [String]) throws {
    try rejectKeys(container, allowed: Set(allowed))
}
