import Foundation
import MortimerPhoneCore

/// Deterministic, in-process fixture for the unsigned preview. It has no endpoint or network API.
actor PhonePreviewFakeTransport: PhoneRemoteByteTransport {
    private let generation = "00000000-0000-0000-0000-000000000201"
    private let epoch = "00000000-0000-0000-0000-000000000301"
    private let viewID = "00000000-0000-0000-0000-000000000401"
    private let resultID = "00000000-0000-0000-0000-000000000101"
    private var viewRevision = 0
    private var open = true
    private var pinned = false
    private var selected = false
    private var receipts: [String: (Data, Data)] = [:]
    private var view: PhoneResultCardView {
        PhoneResultCardView(generation: generation, collectionEpoch: epoch, viewID: viewID,
            viewRevision: viewRevision, selectedResultID: selected ? resultID : nil,
            allowedOperations: PhoneResultCardAction.allCases.sorted { $0.rawValue < $1.rawValue },
            cards: [PhoneResultCardState(resultID: resultID, resultRevision: 1, open: open, pinned: pinned)])
    }

    func exchange(_ requestBytes: Data) async throws -> Data {
        let request = try PhoneRemoteOperationsJSON.decodeRequest(from: requestBytes)
        let canonical = try PhoneRemoteOperationsJSON.encodeRequest(request)
        if let prior = receipts[request.requestID] {
            if prior.0 == canonical { return prior.1 }
            return try error(request, .requestConflict)
        }
        guard receipts.count < 256 else { return try error(request, .requestCapacity) }
        let response: PhoneRemoteOperationResponse
        switch request.payload {
        case .sessionStatus:
            response = try PhoneRemoteOperationResponse(requestID: request.requestID,
                operation: .sessionStatus, status: .ok, reason: .none,
                payload: .sessionStatus(readiness: "ready"))
        case .resultsSnapshot:
            let id = "00000000-0000-0000-0000-000000000101"
            let item = PhoneRemoteResultItem(resultID: id, revision: 1, sourceID: id,
                sourceRevision: 1, title: "Synthetic result", body: "Preview data only",
                receivedAtMilliseconds: 1_800_000_000_000)
            let snapshot = PhoneRemoteResultsSnapshot(
                generation: "00000000-0000-0000-0000-000000000201",
                collectionEpoch: "00000000-0000-0000-0000-000000000301",
                contentWatermark: 1, cursor: String(repeating: "A", count: 43), items: [item])
            response = try PhoneRemoteOperationResponse(requestID: request.requestID,
                operation: .resultsSnapshot, status: .ok, reason: .none,
                payload: .resultsSnapshot(snapshot))
        case .resultsResume:
            let page = PhoneRemoteResultsPage(
                generation: "00000000-0000-0000-0000-000000000201",
                collectionEpoch: "00000000-0000-0000-0000-000000000301",
                contentWatermark: 1, resetRequired: false, hasMore: false,
                cursor: String(repeating: "B", count: 42) + "A", events: [])
            response = try PhoneRemoteOperationResponse(requestID: request.requestID,
                operation: .resultsResume, status: .ok, reason: .none,
                payload: .resultsResume(page))
        case .resultsView(let requestedGeneration, let requestedEpoch):
            guard requestedGeneration == generation, requestedEpoch == epoch else { return try error(request, .authorityUnavailable) }
            response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: request.operation,
                status: .ok, reason: .none, payload: .resultCardView(view))
        case .resultCard(let action, let target):
            guard target.generation == generation, target.collectionEpoch == epoch,
                  target.viewID == viewID, target.viewRevision == viewRevision,
                  target.resultID == resultID, target.resultRevision == 1 else { return try error(request, .requestConflict) }
            let before = view
            guard open || action == .close || action == .reopen else { return try error(request, .requestConflict) }
            switch action {
            case .select: selected = true
            case .pin: pinned = true
            case .unpin: pinned = false
            case .close: open = false; pinned = false; selected = false
            case .reopen: open = true; selected = true
            }
            if view != before { viewRevision += 1 }
            response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: request.operation,
                status: .ok, reason: .none, payload: .resultCardView(view))
        default:
            throw PhoneRemoteOperationsClientError.malformedResponse
        }
        let encoded = try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
        receipts[request.requestID] = (canonical, encoded)
        return encoded
    }

    private func error(_ request: PhoneRemoteOperationRequest, _ reason: PhoneRemoteOperationReason) throws -> Data {
        try PhoneRemoteOperationsJSON.encodeResponse(PhoneRemoteOperationResponse(requestID: request.requestID,
            operation: request.operation, status: reason == .authorityUnavailable ? .unavailable : .denied,
            reason: reason, payload: .empty), for: request.operation)
    }
}
