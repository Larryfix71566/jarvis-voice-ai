import Foundation

/// Closed API request for starting a skill draft or opening its reviewed PR.
/// Free-form task text remains transient in the native process and is never
/// copied into SkillsStore/console inventory.
public struct SkillAuthoringRequest: Encodable, Sendable {
    public let schemaVersion = 1
    public let operation: String
    public let requestID: String
    public let botSessionID: String?
    public let expectedCatalogRevision: String
    public let skillID: String
    public let skillRevision: String?
    public let privacyContext = "standard"
    public let taskBrief: String?
    public let reviewArtifactRef: String?
    public let candidateDigest: String?
    public let jobID: String?

    public init(operation: String, requestID: String = UUID().uuidString.lowercased(),
                expectedCatalogRevision: String, skillID: String, botSessionID: String? = nil,
                skillRevision: String? = nil, taskBrief: String? = nil,
                reviewArtifactRef: String? = nil, candidateDigest: String? = nil,
                jobID: String? = nil) {
        self.operation = operation
        self.requestID = requestID
        self.botSessionID = botSessionID
        self.expectedCatalogRevision = expectedCatalogRevision
        self.skillID = skillID
        self.skillRevision = skillRevision
        self.taskBrief = taskBrief
        self.reviewArtifactRef = reviewArtifactRef
        self.candidateDigest = candidateDigest
        self.jobID = jobID
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version", operation
        case requestID = "request_id", botSessionID = "bot_session_id"
        case expectedCatalogRevision = "expected_catalog_revision"
        case skillID = "skill_id", skillRevision = "skill_revision"
        case privacyContext = "privacy_context", taskBrief = "task_brief"
        case reviewArtifactRef = "review_artifact_ref", candidateDigest = "candidate_digest"
        case jobID = "job_id"
    }
}

/// A bounded run card returned by the Skills activity API. It intentionally
/// contains no task prompt, model reply, or tool arguments.
public struct SkillRunSummary: Codable, Sendable, Identifiable, Equatable {
    public let runID: String
    public let agent: String
    public let displayName: String
    public let status: String
    public let startedAt: String
    public let endedAt: String?
    public let latencyMs: Int?
    public let lastEventType: String?
    public let lastEventStatus: String?

    public var id: String { runID }

    enum CodingKeys: String, CodingKey {
        case runID = "run_id", agent
        case displayName = "display_name", status
        case startedAt = "started_at", endedAt = "ended_at"
        case latencyMs = "latency_ms", lastEventType = "last_event_type"
        case lastEventStatus = "last_event_status"
    }
}

public struct SkillRunPage: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let runs: [SkillRunSummary]
    public let nextCursor: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version", runs
        case nextCursor = "next_cursor"
    }
}

public struct SkillActivityEvidence: Codable, Sendable, Equatable {
    public let kind: String
    public let id: String
}

public struct SkillActivityEvent: Codable, Sendable, Identifiable, Equatable {
    public let eventID: String
    public let runID: String
    public let requestID: String
    public let sequence: Int
    public let schemaVersion: Int
    public let occurredAt: String
    public let skillID: String?
    public let skillRevision: String?
    public let stepID: String?
    public let attemptID: String?
    public let type: String
    public let status: String
    public let evidenceRefs: [SkillActivityEvidence]

    public var id: String { eventID }

    enum CodingKeys: String, CodingKey {
        case eventID = "event_id", runID = "run_id", requestID = "request_id"
        case sequence = "seq", schemaVersion = "schema_version"
        case occurredAt = "occurred_at", skillID = "skill_id"
        case skillRevision = "skill_revision", stepID = "step_id"
        case attemptID = "attempt_id", type, status
        case evidenceRefs = "evidence_refs"
    }
}

public struct SkillActivityPage: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let traceStatus: String
    public let events: [SkillActivityEvent]
    public let afterSeq: Int
    public let nextAfterSeq: Int
    public let hasMore: Bool
    public let truncated: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version", traceStatus = "trace_status"
        case events, afterSeq = "after_seq", nextAfterSeq = "next_after_seq"
        case hasMore = "has_more", truncated
    }

    /// Reject a page that cannot safely be merged into the requested run's
    /// trace. The UI may receive overlapping pages while polling and loading
    /// history; page-level cursor and ordering checks keep malformed responses
    /// from moving the visible cursor backwards or mixing runs.
    public func validate(runID: String, afterSeq requestedAfterSeq: Int) throws {
        guard schemaVersion == 1,
              afterSeq == requestedAfterSeq,
              requestedAfterSeq >= 0,
              traceStatus == "recorded" || traceStatus == "unavailable" else {
            throw JarvisError.decoding("invalid Skills activity page envelope")
        }

        var seenIDs = Set<String>()
        var previousSequence = requestedAfterSeq
        for event in events {
            guard event.runID == runID,
                  !event.eventID.isEmpty,
                  seenIDs.insert(event.eventID).inserted,
                  event.sequence > previousSequence else {
                throw JarvisError.decoding("invalid Skills activity event order")
            }
            try event.validate()
            previousSequence = event.sequence
        }

        guard nextAfterSeq == previousSequence,
              !hasMore || !events.isEmpty,
              traceStatus != "unavailable" || events.isEmpty else {
            throw JarvisError.decoding("invalid Skills activity page cursor")
        }
    }
}

private extension SkillActivityEvent {
    /// The API response is an inspection boundary: reject impossible lifecycle
    /// claims instead of letting malformed or stale data look like completion.
    func validate() throws {
        let allowedStatuses: Set<String>
        switch type {
        case "skill_selected": allowedStatuses = ["unknown"]
        case "skill_resource_read": allowedStatuses = ["passed", "failed", "unknown"]
        case "skill_step_started": allowedStatuses = ["running"]
        case "skill_step_finished": allowedStatuses = ["passed", "failed", "unknown"]
        case "skill_step_skipped": allowedStatuses = ["skipped"]
        case "skill_selection_refused": allowedStatuses = ["failed", "unknown"]
        case "protected_activity", "truncated": allowedStatuses = ["unknown"]
        default: allowedStatuses = []
        }

        guard schemaVersion == 1,
              allowedStatuses.contains(status),
              evidenceRefs.count <= 8,
              evidenceRefs.allSatisfy({
                  ["tool_call_id", "check_receipt_id", "artifact_id"].contains($0.kind)
                      && !$0.id.isEmpty && $0.id.count <= 128
                      && $0.id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || "._:-".contains($0)) })
              }) else {
            throw JarvisError.decoding("invalid Skills activity event schema")
        }

        if type == "skill_step_finished", status == "passed",
           !evidenceRefs.contains(where: { $0.kind == "check_receipt_id" }) {
            throw JarvisError.decoding("passed Skills activity event has no check receipt")
        }

        if type == "protected_activity" || type == "truncated" {
            guard skillID == nil, skillRevision == nil, stepID == nil,
                  evidenceRefs.isEmpty else {
                throw JarvisError.decoding("protected or truncation event exposes trace details")
            }
        }
    }
}
