import Foundation

/// Contract 2.2. Exactly seven keys; the bot drops a message with any other.
public struct TypedRequest: Codable, Sendable, Equatable {
    public enum Source: String, Codable, Sendable { case composer, chip }
    public static let maxScalars = 4000
    public let type = "turn/typed"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let text: String
    public let source: Source
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", text, source
    }
    public init(sessionID: UUID, generation: UUID, requestID: UUID, text: String, source: Source) {
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.text = text; self.source = source
    }
}

/// Contract 2.3. Never carries the text.
public struct TurnResult: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let status: String
    public let code: String
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", status, code
    }
    public init(sessionID: UUID, generation: UUID, requestID: UUID, status: String, code: String) {
        self.type = "turn/result"; self.version = 1
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.status = status; self.code = code
    }
    /// accepted pairs only with accepted (typed_request.py _pair_ok).
    public var isAccepted: Bool { version == 1 && status == "accepted" && code == "accepted" }
}
