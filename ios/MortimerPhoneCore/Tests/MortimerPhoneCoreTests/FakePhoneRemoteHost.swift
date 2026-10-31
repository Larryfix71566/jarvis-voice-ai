import Foundation
import MortimerPhoneCore

/// Deterministic, in-memory protocol fixture. It is deliberately supplied by a
/// test and has no transport, credential, clock, or production-host behavior.
struct FakePhoneRemoteHost<Payload: Codable & Sendable, Reason: Codable & Sendable> {
    struct Outcome: Sendable {
        let status: PhoneRemoteStatus
        let reason: Reason

        init(status: PhoneRemoteStatus, reason: Reason) {
            self.status = status
            self.reason = reason
        }
    }

    private let outcomeFor: @Sendable (PhoneRemoteOperation) -> Outcome

    init(outcomeFor: @escaping @Sendable (PhoneRemoteOperation) -> Outcome) {
        self.outcomeFor = outcomeFor
    }

    func send(_ request: PhoneRemoteRequest<Payload>) -> PhoneRemoteResponse<Payload, Reason> {
        let outcome = outcomeFor(request.operation)
        return PhoneRemoteResponse(
            requestID: request.requestID,
            status: outcome.status,
            reason: outcome.reason,
            payload: request.payload
        )
    }
}
