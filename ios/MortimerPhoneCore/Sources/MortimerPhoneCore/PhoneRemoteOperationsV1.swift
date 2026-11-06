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

public enum PhoneResultCardAction: String, CaseIterable, Codable, Sendable {
    case select = "results.select", pin = "results.pin", unpin = "results.unpin"
    case close = "results.close", reopen = "results.reopen"
    public var operation: PhoneRemoteOperation { PhoneRemoteOperation(rawValue: rawValue)! }
}

public extension PhoneRemoteOperation {
    var isResultCardOperation: Bool { self == .resultsView || PhoneResultCardAction(rawValue: rawValue) != nil }
}

public struct PhoneResultCardTarget: Equatable, Sendable {
    public let generation: String
    public let collectionEpoch: String
    public let viewID: String
    public let viewRevision: Int
    public let resultID: String
    public let resultRevision: Int
    public init(generation: String, collectionEpoch: String, viewID: String, viewRevision: Int,
                resultID: String, resultRevision: Int) {
        self.generation = generation; self.collectionEpoch = collectionEpoch
        self.viewID = viewID; self.viewRevision = viewRevision
        self.resultID = resultID; self.resultRevision = resultRevision
    }
    fileprivate var json: [String: Any] {
        ["generation": generation, "collection_epoch": collectionEpoch, "view_id": viewID,
         "view_revision": viewRevision, "result_id": resultID, "result_revision": resultRevision]
    }
}

public struct PhoneResultCardState: Equatable, Sendable {
    public let resultID: String
    public let resultRevision: Int
    public let open: Bool
    public let pinned: Bool
    public init(resultID: String, resultRevision: Int, open: Bool, pinned: Bool) {
        self.resultID = resultID; self.resultRevision = resultRevision
        self.open = open; self.pinned = pinned
    }
}

public struct PhoneResultCardView: Equatable, Sendable {
    public let generation: String
    public let collectionEpoch: String
    public let viewID: String
    public let viewRevision: Int
    public let selectedResultID: String?
    public let allowedOperations: [PhoneResultCardAction]
    public let cards: [PhoneResultCardState]
    public init(generation: String, collectionEpoch: String, viewID: String, viewRevision: Int,
                selectedResultID: String?, allowedOperations: [PhoneResultCardAction], cards: [PhoneResultCardState]) {
        self.generation = generation; self.collectionEpoch = collectionEpoch
        self.viewID = viewID; self.viewRevision = viewRevision; self.selectedResultID = selectedResultID
        self.allowedOperations = allowedOperations; self.cards = cards
    }
    public func target(for resultID: String) -> PhoneResultCardTarget? {
        guard let card = cards.first(where: { $0.resultID == resultID }) else { return nil }
        return PhoneResultCardTarget(generation: generation, collectionEpoch: collectionEpoch,
            viewID: viewID, viewRevision: viewRevision, resultID: resultID, resultRevision: card.resultRevision)
    }
    fileprivate var json: [String: Any] {
        ["generation": generation, "collection_epoch": collectionEpoch, "view_id": viewID,
         "view_revision": viewRevision, "selected_result_id": selectedResultID as Any? ?? NSNull(),
         "allowed_operations": allowedOperations.map(\.rawValue),
         "cards": cards.map { ["result_id": $0.resultID, "result_revision": $0.resultRevision,
                                "open": $0.open, "pinned": $0.pinned] as [String: Any] }]
    }
}

public struct PhoneRemoteOperationRequest: Codable, Equatable, Sendable {
    public enum Payload: Equatable, Sendable {
        case sessionStatus
        case voiceOffer(sdp: String)
        case voiceUpdate(peerID: String, sdp: String)
        case voiceEnd(peerID: String)
        case resultsSnapshot
        case resultsResume(cursor: String)
        case resultsView(generation: String, collectionEpoch: String)
        case resultCard(PhoneResultCardAction, PhoneResultCardTarget)
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
        case .resultsSnapshot: operation = .resultsSnapshot
        case .resultsResume: operation = .resultsResume
        case .resultsView: operation = .resultsView
        case .resultCard(let action, _): operation = action.operation
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
        case .resultsSnapshot:
            break
        case .resultsResume(let cursor):
            try body.encode(cursor, forKey: .cursor)
        case .resultsView(let generation, let epoch):
            try body.encode(generation, forKey: .generation); try body.encode(epoch, forKey: .collectionEpoch)
        case .resultCard(_, let target):
            try body.encode(target.generation, forKey: .generation)
            try body.encode(target.collectionEpoch, forKey: .collectionEpoch)
            try body.encode(target.viewID, forKey: .viewID); try body.encode(target.viewRevision, forKey: .viewRevision)
            try body.encode(target.resultID, forKey: .resultID); try body.encode(target.resultRevision, forKey: .resultRevision)
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
        case .resultsSnapshot:
            try rejectKeys(body, allowed: [])
            payload = .resultsSnapshot
        case .resultsResume:
            try rejectKeys(body, allowed: ["cursor"])
            payload = .resultsResume(cursor: try body.decode(String.self, forKey: codingKey("cursor")))
        case .resultsView:
            try rejectKeys(body, allowed: ["generation", "collection_epoch"])
            payload = .resultsView(generation: try body.decode(String.self, forKey: codingKey("generation")),
                collectionEpoch: try body.decode(String.self, forKey: codingKey("collection_epoch")))
        case .resultsSelect, .resultsPin, .resultsUnpin, .resultsClose, .resultsReopen:
            try rejectKeys(body, allowed: ["generation", "collection_epoch", "view_id", "view_revision", "result_id", "result_revision"])
            payload = .resultCard(PhoneResultCardAction(rawValue: operation.rawValue)!, PhoneResultCardTarget(
                generation: try body.decode(String.self, forKey: codingKey("generation")),
                collectionEpoch: try body.decode(String.self, forKey: codingKey("collection_epoch")),
                viewID: try body.decode(String.self, forKey: codingKey("view_id")),
                viewRevision: try body.decode(Int.self, forKey: codingKey("view_revision")),
                resultID: try body.decode(String.self, forKey: codingKey("result_id")),
                resultRevision: try body.decode(Int.self, forKey: codingKey("result_revision"))))
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
        case .resultsSnapshot:
            break
        case .resultsResume(let cursor):
            guard PhoneRemoteResultsCursor.isValid(cursor) else { throw PhoneRemoteOperationsError.invalidPayload }
        case .resultsView(let generation, let epoch):
            guard canonicalUUID(generation), canonicalUUID(epoch) else { throw PhoneRemoteOperationsError.invalidPayload }
        case .resultCard(_, let target):
            guard [target.generation, target.collectionEpoch, target.viewID, target.resultID].allSatisfy(canonicalUUID),
                  target.viewRevision >= 0, target.resultRevision > 0 else { throw PhoneRemoteOperationsError.invalidPayload }
        }
    }
}

public struct PhoneRemoteResultItem: Equatable, Sendable {
    public let resultID: String
    public let revision: Int
    public let sourceID: String
    public let sourceRevision: Int
    public let title: String
    public let body: String
    public let receivedAtMilliseconds: Int

    public init(resultID: String, revision: Int, sourceID: String, sourceRevision: Int,
                title: String, body: String, receivedAtMilliseconds: Int) {
        self.resultID = resultID
        self.revision = revision
        self.sourceID = sourceID
        self.sourceRevision = sourceRevision
        self.title = title
        self.body = body
        self.receivedAtMilliseconds = receivedAtMilliseconds
    }
}

public struct PhoneRemoteResultsSnapshot: Equatable, Sendable {
    public let generation: String
    public let collectionEpoch: String
    public let contentWatermark: Int
    public let cursor: String
    public let items: [PhoneRemoteResultItem]

    public init(generation: String, collectionEpoch: String, contentWatermark: Int,
                cursor: String, items: [PhoneRemoteResultItem]) {
        self.generation = generation
        self.collectionEpoch = collectionEpoch
        self.contentWatermark = contentWatermark
        self.cursor = cursor
        self.items = items
    }
}

public struct PhoneRemoteResultsPage: Equatable, Sendable {
    public let generation: String
    public let collectionEpoch: String
    public let contentWatermark: Int?
    public let resetRequired: Bool
    public let hasMore: Bool?
    public let cursor: String?
    public let events: [PhoneRemoteResultEvent]

    public init(generation: String, collectionEpoch: String, contentWatermark: Int?,
                resetRequired: Bool, hasMore: Bool?, cursor: String?, events: [PhoneRemoteResultEvent]) {
        self.generation = generation
        self.collectionEpoch = collectionEpoch
        self.contentWatermark = contentWatermark
        self.resetRequired = resetRequired
        self.hasMore = hasMore
        self.cursor = cursor
        self.events = events
    }
}

public struct PhoneRemoteResultEvent: Equatable, Sendable {
    public let sequence: Int
    public let item: PhoneRemoteResultItem

    public init(sequence: Int, item: PhoneRemoteResultItem) {
        self.sequence = sequence
        self.item = item
    }
}

enum PhoneRemoteResultsCursor {
    static func isValid(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        guard bytes.count == 43 else { return false }
        guard bytes.dropLast().allSatisfy({ (65...90).contains($0) || (97...122).contains($0)
            || (48...57).contains($0) || $0 == 45 || $0 == 95 }) else { return false }
        let alphabet = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        guard let last = alphabet.firstIndex(of: Character(UnicodeScalar(bytes[42]))) else { return false }
        return last % 4 == 0
    }
}

public struct PhoneRemoteOperationResponse: Codable, Equatable, Sendable {
    public enum Payload: Equatable, Sendable {
        case sessionStatus(readiness: String)
        case voiceOffer(peerID: String, sdp: String)
        case voiceUpdate(peerID: String, sdp: String)
        case voiceEnd(peerID: String, ended: Bool)
        case resultsSnapshot(PhoneRemoteResultsSnapshot)
        case resultsResume(PhoneRemoteResultsPage)
        case resultCardView(PhoneResultCardView)
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
        case .resultsSnapshot(let snapshot):
            try encodeResultsSnapshot(snapshot, into: &body)
        case .resultsResume(let page):
            try encodeResultsPage(page, into: &body)
        case .resultCardView(let view): try encodeCardView(view, into: &body)
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
            case .resultsSnapshot:
                payload = .resultsSnapshot(try decodeResultsSnapshot(body))
            case .resultsResume:
                payload = .resultsResume(try decodeResultsPage(body))
            case .resultsView, .resultsSelect, .resultsPin, .resultsUnpin, .resultsClose, .resultsReopen:
                payload = .resultCardView(try decodeCardView(body))
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
        guard [.sessionStatus, .voiceOffer, .voiceUpdate, .voiceEnd,
               .resultsSnapshot, .resultsResume].contains(operation) || operation.isResultCardOperation else {
            throw PhoneRemoteOperationsError.unsupportedOperation
        }
        let reasonAllowed: Bool
        switch status {
        case .ok: reasonAllowed = reason == .none
        case .denied: reasonAllowed = [.malformedRequest, .notAuthorized, .requestConflict, .requestCapacity].contains(reason)
        case .unavailable: reasonAllowed = [.featureOff, .authorityUnavailable, .voiceNotReady, .ownerBusy, .operationUnavailable].contains(reason)
        case .incompatible: reasonAllowed = reason == .unsupportedProtocol
        }
        guard reasonAllowed, !(operation.isResultCardOperation && reason == .voiceNotReady) else { throw PhoneRemoteOperationsError.invalidStatusReasonPair }

        if status != .ok {
            guard case .empty = payload else { throw PhoneRemoteOperationsError.invalidResponsePayload }
            return
        }
        if operation.isResultCardOperation {
            guard case .resultCardView(let view) = payload else { throw PhoneRemoteOperationsError.invalidResponsePayload }
            try validateCardView(view); return
        }
        switch (operation, payload) {
        case (.sessionStatus, .sessionStatus(let readiness)) where readiness == "ready": break
        case (.voiceOffer, .voiceOffer(let peerID, let sdp)), (.voiceUpdate, .voiceUpdate(let peerID, let sdp)):
            guard !peerID.isEmpty, !sdp.isEmpty else { throw PhoneRemoteOperationsError.invalidResponsePayload }
        case (.voiceEnd, .voiceEnd(let peerID, let ended)):
            guard !peerID.isEmpty, ended else { throw PhoneRemoteOperationsError.invalidResponsePayload }
        case (.resultsSnapshot, .resultsSnapshot(let snapshot)):
            try validateResultsSnapshot(snapshot)
        case (.resultsResume, .resultsResume(let page)):
            try validateResultsPage(page)
        default:
            throw PhoneRemoteOperationsError.invalidResponsePayload
        }
    }
}

private func canonicalUUID(_ value: String) -> Bool {
    guard let parsed = UUID(uuidString: value) else { return false }
    return parsed.uuidString.lowercased() == value
}

private func validateCardView(_ view: PhoneResultCardView) throws {
    let ids = view.cards.map(\.resultID)
    let actions = view.allowedOperations.map(\.rawValue)
    guard [view.generation, view.collectionEpoch, view.viewID].allSatisfy(canonicalUUID),
          view.viewRevision >= 0, view.cards.count <= 25, ids == ids.sorted(), Set(ids).count == ids.count,
          actions == actions.sorted(), Set(actions).count == actions.count,
          view.cards.filter(\.pinned).count <= 20,
          view.cards.allSatisfy({ canonicalUUID($0.resultID) && $0.resultRevision > 0 && (!$0.pinned || $0.open) }),
          view.selectedResultID == nil || view.cards.contains(where: { $0.resultID == view.selectedResultID && $0.open })
    else { throw PhoneRemoteOperationsError.invalidResponsePayload }
}

private func decodeCardView(_ body: KeyedDecodingContainer<AnyOperationCodingKey>) throws -> PhoneResultCardView {
    guard Set(body.allKeys.map(\.stringValue)) == Set(["generation", "collection_epoch", "view_id", "view_revision", "selected_result_id", "allowed_operations", "cards"]) else {
        throw PhoneRemoteOperationsError.invalidResponsePayload
    }
    var list = try body.nestedUnkeyedContainer(forKey: codingKey("cards"))
    var cards: [PhoneResultCardState] = []
    while !list.isAtEnd {
        guard cards.count < 25 else { throw PhoneRemoteOperationsError.invalidResponsePayload }
        let row = try list.nestedContainer(keyedBy: AnyOperationCodingKey.self)
        try rejectKeys(row, allowed: ["result_id", "result_revision", "open", "pinned"])
        cards.append(PhoneResultCardState(resultID: try row.decode(String.self, forKey: codingKey("result_id")),
            resultRevision: try row.decode(Int.self, forKey: codingKey("result_revision")),
            open: try row.decode(Bool.self, forKey: codingKey("open")), pinned: try row.decode(Bool.self, forKey: codingKey("pinned"))))
    }
    let view = PhoneResultCardView(generation: try body.decode(String.self, forKey: codingKey("generation")),
        collectionEpoch: try body.decode(String.self, forKey: codingKey("collection_epoch")),
        viewID: try body.decode(String.self, forKey: codingKey("view_id")),
        viewRevision: try body.decode(Int.self, forKey: codingKey("view_revision")),
        selectedResultID: try body.decodeIfPresent(String.self, forKey: codingKey("selected_result_id")),
        allowedOperations: try body.decode([PhoneResultCardAction].self, forKey: codingKey("allowed_operations")), cards: cards)
    try validateCardView(view); return view
}

private func encodeCardView(_ view: PhoneResultCardView, into body: inout KeyedEncodingContainer<AnyOperationCodingKey>) throws {
    try body.encode(view.generation, forKey: codingKey("generation"))
    try body.encode(view.collectionEpoch, forKey: codingKey("collection_epoch"))
    try body.encode(view.viewID, forKey: codingKey("view_id")); try body.encode(view.viewRevision, forKey: codingKey("view_revision"))
    try body.encode(view.selectedResultID, forKey: codingKey("selected_result_id"))
    try body.encode(view.allowedOperations, forKey: codingKey("allowed_operations"))
    var list = body.nestedUnkeyedContainer(forKey: codingKey("cards"))
    for card in view.cards {
        var row = list.nestedContainer(keyedBy: AnyOperationCodingKey.self)
        try row.encode(card.resultID, forKey: codingKey("result_id")); try row.encode(card.resultRevision, forKey: codingKey("result_revision"))
        try row.encode(card.open, forKey: codingKey("open")); try row.encode(card.pinned, forKey: codingKey("pinned"))
    }
}

private func boundedText(_ value: String, maximum: Int) -> Bool {
    !value.isEmpty && !value.contains("\0") && value.utf8.count <= maximum
}

private func decodeResultItem(_ body: KeyedDecodingContainer<AnyOperationCodingKey>) throws -> PhoneRemoteResultItem {
    try rejectKeys(body, allowed: ["result_id", "revision", "source", "classification", "title", "body", "received_at_ms"])
    let resultID = try body.decode(String.self, forKey: codingKey("result_id"))
    let revision = try body.decode(Int.self, forKey: codingKey("revision"))
    let source = try body.nestedContainer(keyedBy: AnyOperationCodingKey.self, forKey: codingKey("source"))
    try rejectKeys(source, allowed: ["kind", "id", "revision"])
    let kind = try source.decode(String.self, forKey: codingKey("kind"))
    let sourceID = try source.decode(String.self, forKey: codingKey("id"))
    let sourceRevision = try source.decode(Int.self, forKey: codingKey("revision"))
    let classification = try body.decode(String.self, forKey: codingKey("classification"))
    let title = try body.decode(String.self, forKey: codingKey("title"))
    let text = try body.decode(String.self, forKey: codingKey("body"))
    let receivedAt = try body.decode(Int.self, forKey: codingKey("received_at_ms"))
    guard canonicalUUID(resultID), sourceID == resultID, revision > 0, revision <= Int64.max,
          revision == sourceRevision, kind == "synthetic.workspace_result.v1",
          classification == "ordinary", boundedText(title, maximum: 512),
          boundedText(text, maximum: 8192), receivedAt >= 0,
          receivedAt <= 9_007_199_254_740_991 else {
        throw PhoneRemoteOperationsError.invalidResponsePayload
    }
    return PhoneRemoteResultItem(resultID: resultID, revision: revision, sourceID: sourceID,
        sourceRevision: sourceRevision, title: title, body: text,
        receivedAtMilliseconds: receivedAt)
}

private func decodeResultsSnapshot(_ body: KeyedDecodingContainer<AnyOperationCodingKey>) throws -> PhoneRemoteResultsSnapshot {
    try rejectKeys(body, allowed: ["generation", "collection_epoch", "content_watermark", "cursor", "items"])
    let generation = try body.decode(String.self, forKey: codingKey("generation"))
    let epoch = try body.decode(String.self, forKey: codingKey("collection_epoch"))
    let watermark = try body.decode(Int.self, forKey: codingKey("content_watermark"))
    let cursor = try body.decode(String.self, forKey: codingKey("cursor"))
    var items = try body.nestedUnkeyedContainer(forKey: codingKey("items"))
    var values: [PhoneRemoteResultItem] = []
    while !items.isAtEnd {
        let item = try items.nestedContainer(keyedBy: AnyOperationCodingKey.self)
        values.append(try decodeResultItem(item))
    }
    let result = PhoneRemoteResultsSnapshot(generation: generation, collectionEpoch: epoch,
        contentWatermark: watermark, cursor: cursor, items: values)
    try validateResultsSnapshot(result)
    return result
}

private func decodeResultsPage(_ body: KeyedDecodingContainer<AnyOperationCodingKey>) throws -> PhoneRemoteResultsPage {
    let reset = try body.decode(Bool.self, forKey: codingKey("reset_required"))
    let generation = try body.decode(String.self, forKey: codingKey("generation"))
    let epoch = try body.decode(String.self, forKey: codingKey("collection_epoch"))
    if reset {
        try rejectKeys(body, allowed: ["generation", "collection_epoch", "reset_required"])
        let page = PhoneRemoteResultsPage(generation: generation, collectionEpoch: epoch,
            contentWatermark: nil, resetRequired: true, hasMore: nil, cursor: nil, events: [])
        try validateResultsPage(page)
        return page
    }
    try rejectKeys(body, allowed: ["generation", "collection_epoch", "content_watermark",
        "reset_required", "has_more", "cursor", "events"])
    let watermark = try body.decode(Int.self, forKey: codingKey("content_watermark"))
    let hasMore = try body.decode(Bool.self, forKey: codingKey("has_more"))
    let cursor = try body.decode(String.self, forKey: codingKey("cursor"))
    var eventContainer = try body.nestedUnkeyedContainer(forKey: codingKey("events"))
    var events: [PhoneRemoteResultEvent] = []
    while !eventContainer.isAtEnd {
        let event = try eventContainer.nestedContainer(keyedBy: AnyOperationCodingKey.self)
        try rejectKeys(event, allowed: ["sequence", "kind", "item"])
        let sequence = try event.decode(Int.self, forKey: codingKey("sequence"))
        guard try event.decode(String.self, forKey: codingKey("kind")) == "upsert" else {
            throw PhoneRemoteOperationsError.invalidResponsePayload
        }
        events.append(PhoneRemoteResultEvent(sequence: sequence,
            item: try decodeResultItem(event.nestedContainer(keyedBy: AnyOperationCodingKey.self,
                                                               forKey: codingKey("item")))))
    }
    let page = PhoneRemoteResultsPage(generation: generation, collectionEpoch: epoch,
        contentWatermark: watermark, resetRequired: false, hasMore: hasMore,
        cursor: cursor, events: events)
    try validateResultsPage(page)
    return page
}

private func validateResultsSnapshot(_ snapshot: PhoneRemoteResultsSnapshot) throws {
    guard canonicalUUID(snapshot.generation), canonicalUUID(snapshot.collectionEpoch),
          snapshot.contentWatermark >= 0, snapshot.contentWatermark <= Int64.max,
          PhoneRemoteResultsCursor.isValid(snapshot.cursor),
          snapshot.items.count <= 25 else { throw PhoneRemoteOperationsError.invalidResponsePayload }
    let ids = snapshot.items.map(\.resultID)
    guard ids == ids.sorted() && Set(ids).count == ids.count else {
        throw PhoneRemoteOperationsError.invalidResponsePayload
    }
}

private func validateResultsPage(_ page: PhoneRemoteResultsPage) throws {
    guard canonicalUUID(page.generation), canonicalUUID(page.collectionEpoch) else {
        throw PhoneRemoteOperationsError.invalidResponsePayload
    }
    if page.resetRequired {
        guard page.contentWatermark == nil, page.hasMore == nil, page.cursor == nil, page.events.isEmpty else {
            throw PhoneRemoteOperationsError.invalidResponsePayload
        }
        return
    }
    guard let watermark = page.contentWatermark, watermark >= 0, watermark <= Int64.max,
          page.hasMore != nil, let cursor = page.cursor,
          PhoneRemoteResultsCursor.isValid(cursor), page.events.count <= 25 else {
        throw PhoneRemoteOperationsError.invalidResponsePayload
    }
    var previous: Int?
    for event in page.events {
        guard event.sequence > 0, event.sequence <= watermark,
              previous.map({ $0 < Int.max && event.sequence == $0 + 1 }) ?? true else {
            throw PhoneRemoteOperationsError.invalidResponsePayload
        }
        previous = event.sequence
    }
}

private func resultItemJSON(_ item: PhoneRemoteResultItem) -> [String: Any] {
    ["result_id": item.resultID, "revision": item.revision,
     "source": ["kind": "synthetic.workspace_result.v1", "id": item.sourceID,
                "revision": item.sourceRevision],
     "classification": "ordinary", "title": item.title, "body": item.body,
     "received_at_ms": item.receivedAtMilliseconds]
}

private func snapshotJSON(_ snapshot: PhoneRemoteResultsSnapshot) -> [String: Any] {
    ["generation": snapshot.generation, "collection_epoch": snapshot.collectionEpoch,
     "content_watermark": snapshot.contentWatermark, "cursor": snapshot.cursor,
     "items": snapshot.items.map(resultItemJSON)]
}

private func pageJSON(_ page: PhoneRemoteResultsPage) -> [String: Any] {
    if page.resetRequired {
        return ["generation": page.generation, "collection_epoch": page.collectionEpoch,
                "reset_required": true]
    }
    return ["generation": page.generation, "collection_epoch": page.collectionEpoch,
            "content_watermark": page.contentWatermark ?? 0, "reset_required": false,
            "has_more": page.hasMore ?? false, "cursor": page.cursor ?? "",
            "events": page.events.map { ["sequence": $0.sequence, "kind": "upsert",
                                         "item": resultItemJSON($0.item)] as [String: Any] }]
}

private func encodeResultItem(_ item: PhoneRemoteResultItem,
    into container: inout KeyedEncodingContainer<AnyOperationCodingKey>) throws {
    try container.encode(item.resultID, forKey: codingKey("result_id"))
    try container.encode(item.revision, forKey: codingKey("revision"))
    var source = container.nestedContainer(keyedBy: AnyOperationCodingKey.self, forKey: codingKey("source"))
    try source.encode("synthetic.workspace_result.v1", forKey: codingKey("kind"))
    try source.encode(item.sourceID, forKey: codingKey("id"))
    try source.encode(item.sourceRevision, forKey: codingKey("revision"))
    try container.encode("ordinary", forKey: codingKey("classification"))
    try container.encode(item.title, forKey: codingKey("title"))
    try container.encode(item.body, forKey: codingKey("body"))
    try container.encode(item.receivedAtMilliseconds, forKey: codingKey("received_at_ms"))
}

private func encodeResultsSnapshot(_ snapshot: PhoneRemoteResultsSnapshot,
    into body: inout KeyedEncodingContainer<AnyOperationCodingKey>) throws {
    try body.encode(snapshot.generation, forKey: codingKey("generation"))
    try body.encode(snapshot.collectionEpoch, forKey: codingKey("collection_epoch"))
    try body.encode(snapshot.contentWatermark, forKey: codingKey("content_watermark"))
    try body.encode(snapshot.cursor, forKey: codingKey("cursor"))
    var items = body.nestedUnkeyedContainer(forKey: codingKey("items"))
    for item in snapshot.items {
        var child = items.nestedContainer(keyedBy: AnyOperationCodingKey.self)
        try encodeResultItem(item, into: &child)
    }
}

private func encodeResultsPage(_ page: PhoneRemoteResultsPage,
    into body: inout KeyedEncodingContainer<AnyOperationCodingKey>) throws {
    try body.encode(page.generation, forKey: codingKey("generation"))
    try body.encode(page.collectionEpoch, forKey: codingKey("collection_epoch"))
    try body.encode(page.resetRequired, forKey: codingKey("reset_required"))
    guard !page.resetRequired, let watermark = page.contentWatermark,
          let hasMore = page.hasMore, let cursor = page.cursor else { return }
    try body.encode(watermark, forKey: codingKey("content_watermark"))
    try body.encode(hasMore, forKey: codingKey("has_more"))
    try body.encode(cursor, forKey: codingKey("cursor"))
    var events = body.nestedUnkeyedContainer(forKey: codingKey("events"))
    for event in page.events {
        var child = events.nestedContainer(keyedBy: AnyOperationCodingKey.self)
        try child.encode(event.sequence, forKey: codingKey("sequence"))
        try child.encode("upsert", forKey: codingKey("kind"))
        var item = child.nestedContainer(keyedBy: AnyOperationCodingKey.self, forKey: codingKey("item"))
        try encodeResultItem(event.item, into: &item)
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

/// Checked JSON boundary for the status, voice, and bounded results DTOs. Callers handling wire bytes
/// must use this type so duplicate keys and resource limits are checked before decoding.
public enum PhoneRemoteOperationsJSON {
    public static let maximumInputBytes = 1_048_576
    public static let maximumDepth = 64

    public static func decodeRequest(from data: Data) throws -> PhoneRemoteOperationRequest {
        try check(data)
        guard hasOnlyIntegerNumberTokens(data) else { throw PhoneRemoteOperationsError.invalidPayload }
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
        case .resultsSnapshot: break
        case .resultsResume(let cursor): payload["cursor"] = cursor
        case .resultsView(let generation, let epoch): payload = ["generation": generation, "collection_epoch": epoch]
        case .resultCard(_, let target): payload = target.json
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
        guard hasOnlyIntegerNumberTokens(data) else {
            throw PhoneRemoteOperationsError.invalidResponsePayload
        }
        if operation == .resultsSnapshot || operation == .resultsResume,
           data.count > 512 * 1024 {
            throw PhoneRemoteOperationsError.inputTooLarge
        }
        guard [.sessionStatus, .voiceOffer, .voiceUpdate, .voiceEnd,
               .resultsSnapshot, .resultsResume].contains(operation) || operation.isResultCardOperation else {
            throw PhoneRemoteOperationsError.unsupportedOperation
        }
        if operation.isResultCardOperation && data.count > 16 * 1024 { throw PhoneRemoteOperationsError.inputTooLarge }
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
        case .resultsSnapshot(let snapshot):
            payload = snapshotJSON(snapshot)
        case .resultsResume(let page):
            payload = pageJSON(page)
        case .resultCardView(let view): payload = view.json
        case .empty: break
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "request_id": response.requestID, "status": response.status.rawValue,
            "reason": response.reason.rawValue, "payload": payload,
        ], options: [.sortedKeys])
        if operation == .resultsSnapshot || operation == .resultsResume,
           data.count > 512 * 1024 {
            throw PhoneRemoteOperationsError.inputTooLarge
        }
        if operation.isResultCardOperation && data.count > 16 * 1024 { throw PhoneRemoteOperationsError.inputTooLarge }
        return data
    }

    private static func hasOnlyIntegerNumberTokens(_ data: Data) -> Bool {
        let bytes = Array(data)
        var index = 0
        var inString = false
        var escaped = false
        while index < bytes.count {
            let byte = bytes[index]
            if inString {
                if escaped { escaped = false }
                else if byte == 0x5C { escaped = true }
                else if byte == 0x22 { inString = false }
                index += 1
                continue
            }
            if byte == 0x22 { inString = true; index += 1; continue }
            if byte == 0x2D || (0x30...0x39).contains(byte) {
                let start = index
                while index < bytes.count,
                      bytes[index] != 0x20, bytes[index] != 0x09, bytes[index] != 0x0A,
                      bytes[index] != 0x0D, bytes[index] != 0x2C,
                      bytes[index] != 0x5D, bytes[index] != 0x7D {
                    index += 1
                }
                if bytes[start..<index].contains(where: { $0 == 0x2E || $0 == 0x65 || $0 == 0x45 }) {
                    return false
                }
                continue
            }
            index += 1
        }
        return true
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

private enum OperationPayloadKey: String, CodingKey { case sdp, peerID = "peer_id", cursor, generation, collectionEpoch = "collection_epoch", viewID = "view_id", viewRevision = "view_revision", resultID = "result_id", resultRevision = "result_revision" }
private func codingKey(_ name: String) -> AnyOperationCodingKey { AnyOperationCodingKey(stringValue: name)! }

private func rejectKeys(_ container: KeyedDecodingContainer<AnyOperationCodingKey>, allowed: Set<String>) throws {
    guard container.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
        throw PhoneRemoteOperationsError.invalidPayload
    }
}

private func rejectKeys(_ container: KeyedDecodingContainer<AnyOperationCodingKey>, allowed: [String]) throws {
    try rejectKeys(container, allowed: Set(allowed))
}
