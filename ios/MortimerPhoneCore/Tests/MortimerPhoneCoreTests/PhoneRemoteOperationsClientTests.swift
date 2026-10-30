import Foundation
import XCTest
@testable import MortimerPhoneCore

private actor ControlledByteTransport: PhoneRemoteByteTransport {
    private struct StartWaiter {
        let index: Int
        let continuation: CheckedContinuation<Data, Never>
    }
    private var requests: [Data] = []
    private var responseWaiter: CheckedContinuation<Data, Error>?
    private var startWaiters: [StartWaiter] = []

    func exchange(_ request: Data) async throws -> Data {
        requests.append(request)
        let ready = startWaiters.filter { $0.index < requests.count }
        startWaiters.removeAll { $0.index < requests.count }
        for waiter in ready { waiter.continuation.resume(returning: requests[waiter.index]) }
        return try await withCheckedThrowingContinuation { continuation in
            responseWaiter = continuation
        }
    }

    func waitForRequest(after index: Int = 0) async -> Data {
        if requests.count > index { return requests[index] }
        return await withCheckedContinuation { startWaiters.append(StartWaiter(index: index, continuation: $0)) }
    }

    func requestCount() -> Int { requests.count }

    func respond(_ data: Data) {
        guard let waiter = responseWaiter else { return }
        responseWaiter = nil
        waiter.resume(returning: data)
    }
}

final class PhoneRemoteOperationsClientTests: XCTestCase {
    func testFourOperationsCrossCheckedByteBoundary() async throws {
        for payload in [
            PhoneRemoteOperationRequest.Payload.sessionStatus,
            .voiceOffer(sdp: "offer-canary"),
            .voiceUpdate(peerID: "peer-canary", sdp: "update-canary"),
            .voiceEnd(peerID: "peer-canary"),
        ] {
            let transport = ControlledByteTransport()
            let client = PhoneRemoteOperationsClient(transport: transport)
            let operationTask = Task { try await client.send(payload) }
            let bytes = await transport.waitForRequest()
            let request = try PhoneRemoteOperationsJSON.decodeRequest(from: bytes)
            let response = try successResponse(for: request)
            await transport.respond(response)
            let result = try await operationTask.value
            XCTAssertEqual(result.requestID.utf8.elementsEqual(request.requestID.utf8), true)
            XCTAssertEqual(result.operation, request.operation)
            let finalState = await client.state
            XCTAssertEqual(finalState, .ready(requestID: request.requestID))
        }
    }

    func testSimultaneousSendRejectsSecondWithoutDispatch() async throws {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        let first = Task { try await client.send(.sessionStatus) }
        let firstBytes = await transport.waitForRequest()
        do {
            _ = try await client.send(.voiceOffer(sdp: "must-not-dispatch"))
            XCTFail("second exchange should be rejected")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .busy)
        }
        let count = await transport.requestCount()
        XCTAssertEqual(count, 1)
        let request = try PhoneRemoteOperationsJSON.decodeRequest(from: firstBytes)
        await transport.respond(try successResponse(for: request))
        _ = try await first.value
    }

    func testPrecancelledTaskDispatchesNoBytes() async {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        let task = Task { () throws -> Void in
            withUnsafeCurrentTask { $0?.cancel() }
            _ = try await client.send(.voiceOffer(sdp: "no-bytes"))
        }
        do {
            try await task.value
            XCTFail("precancelled request should fail locally")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .cancelled)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
        let count = await transport.requestCount()
        let state = await client.state
        XCTAssertEqual(count, 0)
        XCTAssertEqual(state, .idle)
    }

    func testCancellationInvalidatesAndRetainsGateUntilActualCompletion() async throws {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        let first = Task { try await client.send(.voiceOffer(sdp: "one-shot-effect")) }
        let bytes = await transport.waitForRequest()
        first.cancel()
        try await waitUntil {
            let state = await client.state
            let draining = await client.isDraining
            return state == .reconnecting && draining
        }
        do {
            _ = try await client.reconnect(.sessionStatus)
            XCTFail("reconnect must wait for actual completion")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .busy)
        }
        let request = try PhoneRemoteOperationsJSON.decodeRequest(from: bytes)
        await transport.respond(try successResponse(for: request))
        do {
            _ = try await first.value
            XCTFail("invalidated late response must not report success")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .cancelled)
        }
        try await waitUntil { !(await client.isDraining) }
        let state = await client.state
        let count = await transport.requestCount()
        XCTAssertEqual(state, .reconnecting)
        XCTAssertEqual(count, 1)
    }

    func testInvalidRequestIsLocalAndDoesNotInventServerStatus() async {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        do {
            _ = try await client.send(.voiceOffer(sdp: ""))
            XCTFail("invalid local payload should fail before dispatch")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .invalidRequest)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
        let count = await transport.requestCount()
        let state = await client.state
        XCTAssertEqual(count, 0)
        XCTAssertEqual(state, .idle)
    }

    func testCancellationGateLinearizesEncodeDispatchAndPublication() {
        let cancelledDuringEncoding = PhoneRemoteClientExchangeGate()
        cancelledDuringEncoding.cancel()
        XCTAssertFalse(cancelledDuringEncoding.finishEncoding())
        XCTAssertFalse(cancelledDuringEncoding.beginDispatch())

        let cancelledBeforeDispatch = PhoneRemoteClientExchangeGate()
        XCTAssertTrue(cancelledBeforeDispatch.finishEncoding())
        cancelledBeforeDispatch.cancel()
        XCTAssertFalse(cancelledBeforeDispatch.beginDispatch())

        let cancelledDuringResponseDecode = PhoneRemoteClientExchangeGate()
        XCTAssertTrue(cancelledDuringResponseDecode.finishEncoding())
        XCTAssertTrue(cancelledDuringResponseDecode.beginDispatch())
        cancelledDuringResponseDecode.cancel()
        XCTAssertFalse(cancelledDuringResponseDecode.commitPublication())

        let publishedBeforeCancellation = PhoneRemoteClientExchangeGate()
        XCTAssertTrue(publishedBeforeCancellation.finishEncoding())
        XCTAssertTrue(publishedBeforeCancellation.beginDispatch())
        XCTAssertTrue(publishedBeforeCancellation.commitPublication())
        publishedBeforeCancellation.cancel()
        XCTAssertFalse(publishedBeforeCancellation.isCancelled)
    }

    func testExplicitInterruptDrainsThenReconnectsWithFreshIDAndNoReplay() async throws {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        let first = Task { try await client.send(.voiceUpdate(peerID: "p", sdp: "effect")) }
        let firstBytes = await transport.waitForRequest()
        let interrupt = Task { await client.interrupt() }
        try await waitUntil {
            let state = await client.state
            let draining = await client.isDraining
            return state == .reconnecting && draining
        }
        do {
            _ = try await client.reconnect(.voiceUpdate(peerID: "p", sdp: "effect"))
            XCTFail("must not reconnect during drain")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .busy)
        }
        let oldRequest = try PhoneRemoteOperationsJSON.decodeRequest(from: firstBytes)
        await transport.respond(try successResponse(for: oldRequest))
        await interrupt.value
        do {
            _ = try await first.value
            XCTFail("interrupted response must be stale")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .cancelled)
        }

        let reconnect = Task { try await client.reconnect(.sessionStatus) }
        let newBytes = await transport.waitForRequest(after: 1)
        let newRequest = try PhoneRemoteOperationsJSON.decodeRequest(from: newBytes)
        XCTAssertEqual(newRequest.operation, .sessionStatus)
        XCTAssertFalse(newRequest.requestID.utf8.elementsEqual(oldRequest.requestID.utf8))
        let count = await transport.requestCount()
        XCTAssertEqual(count, 2)
        await transport.respond(try successResponse(for: newRequest))
        _ = try await reconnect.value
        let state = await client.state
        XCTAssertEqual(state, .ready(requestID: newRequest.requestID))

        await client.interrupt()
        let secondReconnect = Task { try await client.reconnect(.sessionStatus) }
        let thirdBytes = await transport.waitForRequest(after: 2)
        let thirdRequest = try PhoneRemoteOperationsJSON.decodeRequest(from: thirdBytes)
        XCTAssertFalse(thirdRequest.requestID.utf8.elementsEqual(newRequest.requestID.utf8))
        XCTAssertEqual(thirdRequest.operation, .sessionStatus)
        let countAfterRepeatedReconnect = await transport.requestCount()
        XCTAssertEqual(countAfterRepeatedReconnect, 3)
        await transport.respond(try successResponse(for: thirdRequest))
        _ = try await secondReconnect.value
        let finalState = await client.state
        XCTAssertEqual(finalState, .ready(requestID: thirdRequest.requestID))
    }

    func testCloseInvalidatesResponseAndWaitsForDrain() async throws {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        let requestTask = Task { try await client.send(.voiceEnd(peerID: "peer")) }
        let bytes = await transport.waitForRequest()
        let close = Task { await client.close() }
        try await waitUntil {
            let state = await client.state
            let draining = await client.isDraining
            return state == .ended && draining
        }
        do {
            _ = try await client.send(.sessionStatus)
            XCTFail("closed client must reject calls")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .ended) // Closed clients reject new work even while draining.
        }
        let request = try PhoneRemoteOperationsJSON.decodeRequest(from: bytes)
        await transport.respond(try successResponse(for: request))
        await close.value
        do {
            _ = try await requestTask.value
            XCTFail("late response after close must not report success")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .cancelled)
        }
        let finalState = await client.state
        let draining = await client.isDraining
        let count = await transport.requestCount()
        XCTAssertEqual(finalState, .ended)
        XCTAssertFalse(draining)
        XCTAssertEqual(count, 1)
    }

    func testMalformedAndMismatchedResponseDoNotInventStatus() async throws {
        let transport = ControlledByteTransport()
        let client = PhoneRemoteOperationsClient(transport: transport)
        let requestTask = Task { try await client.send(.sessionStatus) }
        _ = await transport.waitForRequest()
        await transport.respond(Data(#"{"request_id":"wrong","status":"ok","reason":"none","payload":{"readiness":"ready"}}"#.utf8))
        do {
            _ = try await requestTask.value
            XCTFail("mismatched response must fail")
        } catch let error as PhoneRemoteOperationsClientError {
            XCTAssertEqual(error, .malformedResponse)
        }
        let finalState = await client.state
        XCTAssertEqual(finalState, .reconnecting)
    }

    func testClientInstancesDoNotShareExchangeOrState() async throws {
        let transportA = ControlledByteTransport()
        let transportB = ControlledByteTransport()
        let clientA = PhoneRemoteOperationsClient(transport: transportA)
        let clientB = PhoneRemoteOperationsClient(transport: transportB)
        let taskA = Task { try await clientA.send(.sessionStatus) }
        let bytesA = await transportA.waitForRequest()
        let taskB = Task { try await clientB.send(.voiceOffer(sdp: "independent")) }
        let bytesB = await transportB.waitForRequest()
        let requestA = try PhoneRemoteOperationsJSON.decodeRequest(from: bytesA)
        let requestB = try PhoneRemoteOperationsJSON.decodeRequest(from: bytesB)
        await transportB.respond(try successResponse(for: requestB))
        _ = try await taskB.value
        let stateA = await clientA.state
        let stateB = await clientB.state
        XCTAssertEqual(stateA, .requesting(requestID: requestA.requestID))
        XCTAssertEqual(stateB, .ready(requestID: requestB.requestID))
        await transportA.respond(try successResponse(for: requestA))
        _ = try await taskA.value
    }

    private func successResponse(for request: PhoneRemoteOperationRequest) throws -> Data {
        let payload: PhoneRemoteOperationResponse.Payload
        switch request.payload {
        case .sessionStatus: payload = .sessionStatus(readiness: "ready")
        case .voiceOffer: payload = .voiceOffer(peerID: "peer-canary", sdp: "answer-canary")
        case .voiceUpdate: payload = .voiceUpdate(peerID: "peer-canary", sdp: "answer-canary")
        case .voiceEnd: payload = .voiceEnd(peerID: "peer-canary", ended: true)
        }
        let response = try PhoneRemoteOperationResponse(
            requestID: request.requestID, operation: request.operation,
            status: .ok, reason: .none, payload: payload
        )
        return try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
    }

    private func waitUntil(
        file: StaticString = #filePath,
        line: UInt = #line,
        _ condition: () async -> Bool
    ) async throws {
        for _ in 0..<10_000 {
            if await condition() { return }
            await Task.yield()
        }
        XCTFail("condition did not become true", file: file, line: line)
        throw NSError(domain: "PhoneRemoteOperationsClientTests", code: 1)
    }
}
