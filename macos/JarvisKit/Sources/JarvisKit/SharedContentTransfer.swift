import Foundation

/// Cross-process representation of user-approved text/image content. The
/// payload is ephemeral and carries a digest so reconnects cannot duplicate it.
public enum SharedContentKind: String, Codable, Sendable { case text, image }

public struct SharedContentTransfer: Codable, Sendable, Equatable {
    public let contentID: UUID
    public let kind: SharedContentKind
    public let mimeType: String
    public let digest: String
    public let payload: Data
    public let provider: String?
    public let approved: Bool
    public let ephemeral: Bool

    public init(contentID: UUID = UUID(), kind: SharedContentKind,
                mimeType: String, digest: String, payload: Data,
                provider: String? = nil, approved: Bool = false,
                ephemeral: Bool = true) {
        self.contentID = contentID; self.kind = kind; self.mimeType = mimeType
        self.digest = digest; self.payload = payload; self.provider = provider
        self.approved = approved; self.ephemeral = ephemeral
    }
}

/// Metadata and messages for the bounded, user-approved inbound transfer.
/// Payload bytes are sent only in ``InputChunk``; the manifest never carries
/// a path or an implicit provider instruction.
public struct InputManifestAttachment: Codable, Sendable, Equatable {
    public let contentID: UUID
    public let kind: SharedContentKind
    public let mimeType: String
    public let digest: String
    public let totalBytes: Int

    public init(_ content: SharedContentTransfer) {
        contentID = content.contentID; kind = content.kind
        mimeType = content.mimeType; digest = content.digest
        totalBytes = content.payload.count
    }

    enum CodingKeys: String, CodingKey {
        case contentID = "content_id", kind, mimeType = "mime_type", digest
        case totalBytes = "total_bytes"
    }
}

public struct InputManifest: Codable, Sendable, Equatable {
    public let type = "input/manifest"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let batchID: UUID
    public let approvalID: UUID
    public let question: String
    public let attachments: [InputManifestAttachment]

    public init(sessionID: UUID, generation: UUID, requestID: UUID = UUID(),
                batchID: UUID, approvalID: UUID, question: String,
                attachments: [InputManifestAttachment]) {
        self.sessionID = sessionID; self.generation = generation; self.requestID = requestID
        self.batchID = batchID; self.approvalID = approvalID
        self.question = String(question.prefix(2000)); self.attachments = Array(attachments.prefix(4))
    }
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, requestID = "request_id"
        case batchID = "batch_id", approvalID = "approval_id", question, attachments
    }
}

/// Server-to-client approval offer emitted by the voice tool. It contains
/// only staged IDs, the user-authored question and the disclosed provider;
/// the native client must still create an approval and send a manifest before
/// any bytes leave the Mac.
public struct InputOffer: Codable, Sendable, Equatable {
    public let type = "input/offer"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let batchID: UUID
    public let attachmentIDs: [UUID]
    public let question: String
    public let profile: ConsoleInputProfile

    public init(sessionID: UUID, generation: UUID, requestID: UUID,
                batchID: UUID, attachmentIDs: [UUID], question: String,
                profile: ConsoleInputProfile) {
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.batchID = batchID
        self.attachmentIDs = Array(attachmentIDs.prefix(4))
        self.question = String(question.prefix(2000)); self.profile = profile
    }

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", batchID = "batch_id"
        case attachmentIDs = "attachment_ids", question, profile
    }
}

/// Server-to-client result of an exact spoken consent phrase. The native
/// client consumes this once for the matching pending offer and then reuses
/// the button path to create the normal approval/manifest.
public struct InputConsent: Codable, Sendable, Equatable {
    public let type = "input/consent"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let batchID: UUID
    public let approved: Bool
    public let userTurnID: UUID

    public init(sessionID: UUID, generation: UUID, requestID: UUID = UUID(),
                batchID: UUID, approved: Bool, userTurnID: UUID = UUID()) {
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.batchID = batchID
        self.approved = approved; self.userTurnID = userTurnID
    }

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", batchID = "batch_id"
        case approved, userTurnID = "user_turn_id"
    }
}

public struct InputChunk: Codable, Sendable, Equatable {
    public let type = "input/chunk"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let transferID: UUID
    public let attachmentID: UUID
    public let sequence: Int
    public let base64: String

    public init(sessionID: UUID, generation: UUID, requestID: UUID = UUID(),
                transferID: UUID, attachmentID: UUID, sequence: Int, base64: String) {
        self.sessionID = sessionID; self.generation = generation; self.requestID = requestID
        self.transferID = transferID; self.attachmentID = attachmentID
        self.sequence = sequence; self.base64 = base64
    }
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, requestID = "request_id"
        case transferID = "transfer_id", attachmentID = "attachment_id", sequence, base64
    }
}

public struct InputCommit: Codable, Sendable, Equatable {
    public let type = "input/commit"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let transferID: UUID
    public let attachmentID: UUID
    public let totalChunks: Int
    public let totalBytes: Int
    public let sha256: String

    public init(sessionID: UUID, generation: UUID, requestID: UUID = UUID(),
                transferID: UUID, attachmentID: UUID, totalChunks: Int,
                totalBytes: Int, sha256: String) {
        self.sessionID = sessionID; self.generation = generation; self.requestID = requestID
        self.transferID = transferID; self.attachmentID = attachmentID
        self.totalChunks = totalChunks; self.totalBytes = totalBytes; self.sha256 = sha256
    }
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, requestID = "request_id"
        case transferID = "transfer_id", attachmentID = "attachment_id"
        case totalChunks = "total_chunks", totalBytes = "total_bytes", sha256
    }
}

public struct InputAnalyze: Codable, Sendable, Equatable {
    public let type = "input/analyze"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let batchID: UUID
    public let attachmentIDs: [UUID]
    public let question: String

    public init(sessionID: UUID, generation: UUID, requestID: UUID = UUID(),
                batchID: UUID, attachmentIDs: [UUID], question: String) {
        self.sessionID = sessionID; self.generation = generation; self.requestID = requestID
        self.batchID = batchID; self.attachmentIDs = Array(attachmentIDs.prefix(4))
        self.question = String(question.prefix(2000))
    }
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, requestID = "request_id"
        case batchID = "batch_id", attachmentIDs = "attachment_ids", question
    }
}

public struct InputCancel: Codable, Sendable, Equatable {
    public let type = "input/cancel"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let batchID: UUID
    public let transferID: UUID?

    public init(sessionID: UUID, generation: UUID, requestID: UUID = UUID(),
                batchID: UUID, transferID: UUID? = nil) {
        self.sessionID = sessionID; self.generation = generation; self.requestID = requestID
        self.batchID = batchID; self.transferID = transferID
    }
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, requestID = "request_id"
        case batchID = "batch_id", transferID = "transfer_id"
    }
}

/// Server acknowledgement emitted before any bytes are sent.  Keeping the
/// transfer UUID separate from the batch UUID prevents a reconnect or a
/// replayed manifest from being mistaken for an in-flight byte stream.
public struct InputAccept: Codable, Sendable, Equatable {
    public let type = "input/accept"
    public let version = 1
    public let sessionID: UUID?
    public let generation: UUID?
    public let requestID: UUID?
    public let batchID: UUID?
    public let transferID: UUID
    public let temporaryContentMode: Bool
    public let maxChunkBytes: Int

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", batchID = "batch_id", transferID = "transfer_id"
        case temporaryContentMode = "temporary_content_mode", maxChunkBytes = "max_chunk_bytes"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sessionID = try c.decodeIfPresent(UUID.self, forKey: .sessionID)
        generation = try c.decodeIfPresent(UUID.self, forKey: .generation)
        requestID = try c.decodeIfPresent(UUID.self, forKey: .requestID)
        batchID = try c.decodeIfPresent(UUID.self, forKey: .batchID)
        transferID = try c.decode(UUID.self, forKey: .transferID)
        temporaryContentMode = try c.decodeIfPresent(Bool.self, forKey: .temporaryContentMode) ?? false
        maxChunkBytes = try c.decodeIfPresent(Int.self, forKey: .maxChunkBytes) ?? 16 * 1024
    }
}

public struct InputAck: Codable, Sendable, Equatable {
    public let type = "input/ack"
    public let version = 1
    public let sessionID: UUID?
    public let generation: UUID?
    public let requestID: UUID?
    public let transferID: UUID
    public let attachmentID: UUID
    public let sequence: Int

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", transferID = "transfer_id"
        case attachmentID = "attachment_id", sequence
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sessionID = try c.decodeIfPresent(UUID.self, forKey: .sessionID)
        generation = try c.decodeIfPresent(UUID.self, forKey: .generation)
        requestID = try c.decodeIfPresent(UUID.self, forKey: .requestID)
        transferID = try c.decode(UUID.self, forKey: .transferID)
        attachmentID = try c.decode(UUID.self, forKey: .attachmentID)
        sequence = try c.decode(Int.self, forKey: .sequence)
    }
}

public struct InputReady: Codable, Sendable, Equatable {
    public let type = "input/ready"
    public let version = 1
    public let sessionID: UUID?
    public let generation: UUID?
    public let requestID: UUID?
    public let batchID: UUID
    public let transferID: UUID

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", batchID = "batch_id", transferID = "transfer_id"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sessionID = try c.decodeIfPresent(UUID.self, forKey: .sessionID)
        generation = try c.decodeIfPresent(UUID.self, forKey: .generation)
        requestID = try c.decodeIfPresent(UUID.self, forKey: .requestID)
        batchID = try c.decode(UUID.self, forKey: .batchID)
        transferID = try c.decode(UUID.self, forKey: .transferID)
    }
}

public struct InputStatus: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let status: String
    public let code: String
    public let summary: String
    public let requestID: UUID?
    public let batchID: UUID?
    public let transferID: UUID?
    public let attachmentID: UUID?
    public let data: JSONValue?

    enum CodingKeys: String, CodingKey {
        case type, version, status, code, summary
        case requestID = "request_id", batchID = "batch_id"
        case transferID = "transfer_id", attachmentID = "attachment_id", data
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? "input/status"
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? 1
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? "error"
        code = try c.decodeIfPresent(String.self, forKey: .code) ?? "invalid"
        summary = String((try c.decodeIfPresent(String.self, forKey: .summary) ?? "").prefix(240))
        requestID = try c.decodeIfPresent(UUID.self, forKey: .requestID)
        batchID = try c.decodeIfPresent(UUID.self, forKey: .batchID)
        transferID = try c.decodeIfPresent(UUID.self, forKey: .transferID)
        attachmentID = try c.decodeIfPresent(UUID.self, forKey: .attachmentID)
        data = try c.decodeIfPresent(JSONValue.self, forKey: .data)
    }
}
