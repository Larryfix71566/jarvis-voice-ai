import Foundation

// C7a (contract §3): the approval message pair. The bot owns the pending
// list (`approval/pending`, `approval/settled`); the app answers with
// `approval/decide` and gets `approval/result`. None of these is a console
// action (contract 3.1), so ConsoleProtocol and the action registry are not
// touched.

/// Contract 3.4. Decoded leniently here; `isValid(sessionID:generation:)`
/// applies the client checks the contract lists, and the store drops an
/// invalid message.
public struct ApprovalPending: Codable, Sendable, Equatable {
    public static let maxSummary = 600
    public static let maxName = 80

    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let approvalID: UUID
    public let originRequestID: UUID?
    public let runID: String?
    public let agent: String
    public let tool: String
    public let summary: String
    public let ts: Double
    public let expiresAt: Double

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case approvalID = "approval_id", originRequestID = "origin_request_id"
        case runID = "run_id", agent, tool, summary, ts, expiresAt = "expires_at"
    }

    public init(sessionID: UUID, generation: UUID, approvalID: UUID, originRequestID: UUID?,
                runID: String? = nil, agent: String, tool: String, summary: String,
                ts: Double, expiresAt: Double) {
        self.type = "approval/pending"; self.version = 1
        self.sessionID = sessionID; self.generation = generation
        self.approvalID = approvalID; self.originRequestID = originRequestID
        self.runID = runID; self.agent = agent; self.tool = tool
        self.summary = summary; self.ts = ts; self.expiresAt = expiresAt
    }

    /// Contract 3.4 client validation: version 1; session and generation
    /// match; summary 1 to 600 characters; agent and tool at most 80;
    /// `expires_at > ts`. The UUID fields were already checked by decoding.
    public func isValid(sessionID: UUID, generation: UUID) -> Bool {
        version == 1 && self.sessionID == sessionID && self.generation == generation
            && (1...Self.maxSummary).contains(summary.count)
            && agent.count <= Self.maxName && tool.count <= Self.maxName
            && ts.isFinite && expiresAt.isFinite && expiresAt > ts
    }
}

/// Contract 3.5. `state` is approved, declined, resolved, superseded or expired.
public struct ApprovalSettled: Codable, Sendable, Equatable {
    public static let states: Set<String> = ["approved", "declined", "resolved", "superseded", "expired"]

    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let approvalID: UUID
    public let state: String

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case approvalID = "approval_id", state
    }

    public init(sessionID: UUID, generation: UUID, approvalID: UUID, state: String) {
        self.type = "approval/settled"; self.version = 1
        self.sessionID = sessionID; self.generation = generation
        self.approvalID = approvalID; self.state = state
    }
}

/// Contract 3.6. Exactly seven keys and no free text: the client sends an
/// id and an enum, never a string that could reach the model.
public struct ApprovalDecide: Codable, Sendable, Equatable {
    public enum Decision: String, Codable, Sendable { case approve, decline }

    public let type = "approval/decide"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let approvalID: UUID
    public let decision: Decision

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", approvalID = "approval_id", decision
    }

    public init(sessionID: UUID, generation: UUID, requestID: UUID,
                approvalID: UUID, decision: Decision) {
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.approvalID = approvalID; self.decision = decision
    }
}

/// Contract 3.7. `status` is accepted only with `code: "accepted"`.
public struct ApprovalResult: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let approvalID: UUID
    public let status: String
    public let code: String

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", approvalID = "approval_id", status, code
    }

    public init(sessionID: UUID, generation: UUID, requestID: UUID, approvalID: UUID,
                status: String, code: String) {
        self.type = "approval/result"; self.version = 1
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.approvalID = approvalID
        self.status = status; self.code = code
    }

    public var isAccepted: Bool { version == 1 && status == "accepted" && code == "accepted" }
}
