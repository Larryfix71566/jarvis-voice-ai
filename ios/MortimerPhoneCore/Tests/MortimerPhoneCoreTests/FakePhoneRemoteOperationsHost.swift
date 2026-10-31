import Foundation
import MortimerPhoneCore

/// Offline-only operation host. It has no socket, authentication, or device behavior.
struct FakePhoneRemoteOperationsHost: Sendable {
    private let exchangeBytes: @Sendable (Data) throws -> Data

    init(exchangeBytes: @escaping @Sendable (Data) throws -> Data) {
        self.exchangeBytes = exchangeBytes
    }

    func send(_ request: PhoneRemoteOperationRequest) throws -> PhoneRemoteOperationResponse {
        let requestBytes = try PhoneRemoteOperationsJSON.encodeRequest(request)
        let responseBytes = try exchangeBytes(requestBytes)
        let response = try PhoneRemoteOperationsJSON.decodeResponse(from: responseBytes, for: request.operation)
        // Swift String equality uses Unicode canonical equivalence. The wire
        // protocol correlates the original UTF-8 request-id bytes exactly.
        guard response.requestID.utf8.elementsEqual(request.requestID.utf8) else {
            throw PhoneRemoteOperationsError.requestIDMismatch
        }
        return response
    }
}
