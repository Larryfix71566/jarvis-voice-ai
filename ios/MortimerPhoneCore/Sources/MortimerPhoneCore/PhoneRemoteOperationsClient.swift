import Foundation

/// Lock-backed linearization point shared with Task's synchronous cancellation handler.
/// It contains no callbacks and protects only the local preparation/dispatch/publish phase.
final class PhoneRemoteClientExchangeGate: @unchecked Sendable {
    private enum Phase { case preparing, readyToDispatch, dispatched, cancelled, published }
    private let lock = NSLock()
    private var phase = Phase.preparing

    func cancel() {
        lock.lock()
        if phase != .published { phase = .cancelled }
        lock.unlock()
    }

    func finishEncoding() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard phase == .preparing else { return false }
        phase = .readyToDispatch
        return true
    }

    func beginDispatch() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard phase == .readyToDispatch else { return false }
        phase = .dispatched
        return true
    }

    func commitPublication() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard phase == .dispatched else { return false }
        phase = .published
        return true
    }

    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return phase == .cancelled
    }
}

/// Injectable byte transport. Production transports are intentionally outside this claim.
public protocol PhoneRemoteByteTransport: Sendable {
    func exchange(_ request: Data) async throws -> Data
}

public enum PhoneRemoteOperationsClientError: Error, Equatable, Sendable {
    case busy
    case reconnectRequired
    case reconnectUnavailable
    case ended
    case invalidRequest
    case cancelled
    case transportFailure
    case malformedResponse
}

/// A single-session, single-exchange client over the checked R3.12 wire boundary.
/// The actor owns an in-flight transport task until that task actually completes.
public actor PhoneRemoteOperationsClient {
    private struct Exchange {
        let requestID: String
        let generation: UInt64
        let task: Task<Data, Error>
    }

    private let transport: any PhoneRemoteByteTransport
    private var machine = PhoneSessionStateMachine()
    private var generation: UInt64 = 0
    private var exchange: Exchange?

    public init(transport: any PhoneRemoteByteTransport) {
        self.transport = transport
    }

    public var state: PhoneSessionState { machine.state }
    public var isDraining: Bool {
        exchange != nil && (machine.state == .reconnecting || machine.state == .ended)
    }

    /// Starts one ordinary request. A request is never queued behind another exchange.
    public func send(_ payload: PhoneRemoteOperationRequest.Payload) async throws -> PhoneRemoteOperationResponse {
        guard machine.state != .ended else { throw PhoneRemoteOperationsClientError.ended }
        guard exchange == nil else { throw PhoneRemoteOperationsClientError.busy }
        guard machine.state != .reconnecting else { throw PhoneRemoteOperationsClientError.reconnectRequired }
        return try await start(payload, reconnect: false)
    }

    /// Explicitly starts a new request after interruption and completed drain.
    public func reconnect(_ payload: PhoneRemoteOperationRequest.Payload) async throws -> PhoneRemoteOperationResponse {
        guard exchange == nil else { throw PhoneRemoteOperationsClientError.busy }
        guard machine.state == .reconnecting else { throw PhoneRemoteOperationsClientError.reconnectUnavailable }
        return try await start(payload, reconnect: true)
    }

    /// Invalidates response publication immediately, then waits for actual transport completion.
    public func interrupt() async {
        invalidateForInterruption()
        await drainCurrentExchange()
    }

    /// Closes the local session immediately and retains exchange ownership through drain.
    public func close() async {
        generation &+= 1
        machine.apply(.end)
        await drainCurrentExchange()
    }

    private func start(_ payload: PhoneRemoteOperationRequest.Payload, reconnect: Bool) async throws -> PhoneRemoteOperationResponse {
        let gate = PhoneRemoteClientExchangeGate()
        let requestID = UUID().uuidString
        let capturedGeneration = generation
        return try await withTaskCancellationHandler {
            guard !Task.isCancelled else { throw PhoneRemoteOperationsClientError.cancelled }
            let request: PhoneRemoteOperationRequest
            do {
                request = try PhoneRemoteOperationRequest(requestID: requestID, payload: payload)
            } catch {
                throw gate.isCancelled ? PhoneRemoteOperationsClientError.cancelled : .invalidRequest
            }
            let bytes: Data
            do {
                bytes = try PhoneRemoteOperationsJSON.encodeRequest(request)
            } catch {
                throw gate.isCancelled ? PhoneRemoteOperationsClientError.cancelled : .invalidRequest
            }
            guard gate.finishEncoding() else { throw PhoneRemoteOperationsClientError.cancelled }

            if reconnect {
                machine.apply(.reconnectRequested(requestID: requestID))
            } else {
                machine.apply(.beginRequest(requestID: requestID))
            }
            guard machine.state == .requesting(requestID: requestID) else {
                throw reconnect ? PhoneRemoteOperationsClientError.reconnectUnavailable : .busy
            }

            // This owned task is deliberately not cancelled with its caller. Its completion
            // is the only event that releases the single-exchange gate.
            let transportTask = Task {
                guard gate.beginDispatch() else { throw CancellationError() }
                return try await transport.exchange(bytes)
            }
            exchange = Exchange(requestID: requestID, generation: capturedGeneration, task: transportTask)

            let responseBytes: Data
            do {
                responseBytes = try await transportTask.value
            } catch {
                let wasCancelled = Task.isCancelled || gate.isCancelled
                gate.cancel()
                if isCurrent(requestID: requestID, generation: capturedGeneration) {
                    invalidateForInterruption()
                }
                clearExchange(requestID: requestID, generation: capturedGeneration)
                if wasCancelled { throw PhoneRemoteOperationsClientError.cancelled }
                throw PhoneRemoteOperationsClientError.transportFailure
            }

            if Task.isCancelled { gate.cancel() }
            guard !gate.isCancelled else {
                if isCurrent(requestID: requestID, generation: capturedGeneration) {
                    invalidateForInterruption()
                }
                clearExchange(requestID: requestID, generation: capturedGeneration)
                throw PhoneRemoteOperationsClientError.cancelled
            }
            guard isCurrent(requestID: requestID, generation: capturedGeneration) else {
                clearExchange(requestID: requestID, generation: capturedGeneration)
                throw PhoneRemoteOperationsClientError.cancelled
            }

            let response: PhoneRemoteOperationResponse
            do {
                response = try PhoneRemoteOperationsJSON.decodeResponse(from: responseBytes, for: request.operation)
            } catch {
                let wasCancelled = Task.isCancelled || gate.isCancelled
                gate.cancel()
                invalidateForInterruption()
                clearExchange(requestID: requestID, generation: capturedGeneration)
                if wasCancelled { throw PhoneRemoteOperationsClientError.cancelled }
                throw PhoneRemoteOperationsClientError.malformedResponse
            }
            if Task.isCancelled { gate.cancel() }
            guard !gate.isCancelled else {
                if isCurrent(requestID: requestID, generation: capturedGeneration) {
                    invalidateForInterruption()
                }
                clearExchange(requestID: requestID, generation: capturedGeneration)
                throw PhoneRemoteOperationsClientError.cancelled
            }
            guard response.requestID.utf8.elementsEqual(requestID.utf8) else {
                gate.cancel()
                invalidateForInterruption()
                clearExchange(requestID: requestID, generation: capturedGeneration)
                throw PhoneRemoteOperationsClientError.malformedResponse
            }
            guard gate.commitPublication() else {
                if isCurrent(requestID: requestID, generation: capturedGeneration) {
                    invalidateForInterruption()
                }
                clearExchange(requestID: requestID, generation: capturedGeneration)
                throw PhoneRemoteOperationsClientError.cancelled
            }
            machine.apply(.response(requestID: requestID, status: response.status))
            clearExchange(requestID: requestID, generation: capturedGeneration)
            return response
        } onCancel: {
            gate.cancel()
            Task { await self.cancelExchange(requestID: requestID, generation: capturedGeneration) }
        }
    }

    private func cancelExchange(requestID: String, generation capturedGeneration: UInt64) {
        guard isCurrent(requestID: requestID, generation: capturedGeneration) else { return }
        invalidateForInterruption()
    }

    private func isCurrent(requestID: String, generation capturedGeneration: UInt64) -> Bool {
        generation == capturedGeneration && exchange?.requestID == requestID && exchange?.generation == capturedGeneration
    }

    private func invalidateForInterruption() {
        generation &+= 1
        machine.apply(.transportInterrupted)
    }

    private func clearExchange(requestID: String, generation capturedGeneration: UInt64) {
        guard exchange?.requestID == requestID, exchange?.generation == capturedGeneration else { return }
        exchange = nil
    }

    private func drainCurrentExchange() async {
        guard let current = exchange else { return }
        _ = await current.task.result
        clearExchange(requestID: current.requestID, generation: current.generation)
    }
}
