import Foundation
import XCTest
@testable import MortimerPhoneCore

private actor PreviewTestTransport: PhoneRemoteByteTransport {
    enum Reply: Sendable, Equatable { case success, snapshot, resume, resultsFlow, resultsResetFlow, foreignGeneration, foreignEpoch, watermarkRollback, revisionRollback, sequenceOverflow, highWaterIncrease, collectionOverflow, reset, malformed, mismatchedID, wrongOperation, denied, hold }
    private let reply: Reply
    private var requestCountValue = 0
    private var lastRequestBytes: Data?
    private var heldReply: Data?
    private var responseContinuation: CheckedContinuation<Data, Never>?
    private var releaseRequested = false

    init(_ reply: Reply) { self.reply = reply }

    func exchange(_ requestBytes: Data) async throws -> Data {
        requestCountValue += 1
        lastRequestBytes = requestBytes
        let request = try PhoneRemoteOperationsJSON.decodeRequest(from: requestBytes)
        switch reply {
        case .hold:
            heldReply = try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: request.requestID, operation: .sessionStatus,
                                             status: .ok, reason: .none,
                                             payload: .sessionStatus(readiness: "ready")),
                for: .sessionStatus
            )
            return await withCheckedContinuation { continuation in
                if releaseRequested, let heldReply {
                    continuation.resume(returning: heldReply)
                } else {
                    responseContinuation = continuation
                }
            }
        case .malformed:
            return Data("{not-json".utf8)
        case .wrongOperation:
            return Data("{\"payload\":{\"peer_id\":\"peer\",\"sdp\":\"answer\"},\"reason\":\"none\",\"request_id\":\"\(request.requestID)\",\"status\":\"ok\"}".utf8)
        case .mismatchedID:
            return try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: "different-id", operation: .sessionStatus,
                                             status: .ok, reason: .none,
                                             payload: .sessionStatus(readiness: "ready")),
                for: .sessionStatus
            )
        case .denied:
            return try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: request.requestID, operation: .sessionStatus,
                                             status: .denied, reason: .notAuthorized, payload: .empty),
                for: .sessionStatus
            )
        case .success:
            return try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: request.requestID, operation: .sessionStatus,
                                             status: .ok, reason: .none,
                                             payload: .sessionStatus(readiness: "ready")),
                for: .sessionStatus
            )
        case .snapshot:
            guard request.operation == .resultsSnapshot else { throw PhoneRemoteOperationsClientError.malformedResponse }
            let id = "00000000-0000-0000-0000-000000000111"
            let item = PhoneRemoteResultItem(resultID: id, revision: 1, sourceID: id,
                sourceRevision: 1, title: "Synthetic card", body: "Fixture body",
                receivedAtMilliseconds: 1_800_000_000_000)
            let snapshot = PhoneRemoteResultsSnapshot(generation: "00000000-0000-0000-0000-000000000201",
                collectionEpoch: "00000000-0000-0000-0000-000000000301",
                contentWatermark: reply == .sequenceOverflow ? Int.max : 1,
                cursor: String(repeating: "A", count: 43), items: [item])
            return try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsSnapshot,
                    status: .ok, reason: .none, payload: .resultsSnapshot(snapshot)), for: .resultsSnapshot)
        case .resume, .reset:
            guard request.operation == .resultsResume else { throw PhoneRemoteOperationsClientError.malformedResponse }
            let reset = reply == .reset
            let page = PhoneRemoteResultsPage(generation: "00000000-0000-0000-0000-000000000201",
                collectionEpoch: "00000000-0000-0000-0000-000000000301",
                contentWatermark: reset ? nil : 2, resetRequired: reset,
                hasMore: reset ? nil : false, cursor: reset ? nil : String(repeating: "B", count: 42) + "A",
                events: [])
            return try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsResume,
                    status: .ok, reason: .none, payload: .resultsResume(page)), for: .resultsResume)
        case .resultsFlow, .resultsResetFlow, .foreignGeneration, .foreignEpoch,
             .watermarkRollback, .revisionRollback, .sequenceOverflow,
             .highWaterIncrease, .collectionOverflow:
            if request.operation == .resultsSnapshot {
                let count = reply == .collectionOverflow ? 25 : 1
                let items = (0..<count).map { index -> PhoneRemoteResultItem in
                    let id = String(format: "00000000-0000-0000-0000-%012x", 0x111 + index)
                    return PhoneRemoteResultItem(resultID: id, revision: 1, sourceID: id,
                        sourceRevision: 1, title: "Synthetic card", body: "Fixture body",
                        receivedAtMilliseconds: 1_800_000_000_000)
                }
                let snapshot = PhoneRemoteResultsSnapshot(generation: "00000000-0000-0000-0000-000000000201",
                    collectionEpoch: "00000000-0000-0000-0000-000000000301", contentWatermark: 1,
                    cursor: String(repeating: "A", count: 43), items: items)
                return try PhoneRemoteOperationsJSON.encodeResponse(
                    PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsSnapshot,
                        status: .ok, reason: .none, payload: .resultsSnapshot(snapshot)), for: .resultsSnapshot)
            }
            guard request.operation == .resultsResume else { throw PhoneRemoteOperationsClientError.malformedResponse }
            if reply == .highWaterIncrease {
                let firstPage = requestCountValue == 2
                let sequences = firstPage ? Array(2...26) : Array(27...50)
                let events = sequences.map { sequence -> PhoneRemoteResultEvent in
                    let id = "00000000-0000-0000-0000-000000000111"
                    let item = PhoneRemoteResultItem(resultID: id, revision: sequence,
                        sourceID: id, sourceRevision: sequence, title: "Synthetic card",
                        body: "revision-\(sequence)", receivedAtMilliseconds: 1_800_000_000_000)
                    return PhoneRemoteResultEvent(sequence: sequence, item: item)
                }
                let page = PhoneRemoteResultsPage(generation: "00000000-0000-0000-0000-000000000201",
                    collectionEpoch: "00000000-0000-0000-0000-000000000301",
                    contentWatermark: firstPage ? 40 : 50, resetRequired: false,
                    hasMore: firstPage, cursor: String(repeating: "B", count: 42) + "A", events: events)
                return try PhoneRemoteOperationsJSON.encodeResponse(
                    PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsResume,
                        status: .ok, reason: .none, payload: .resultsResume(page)), for: .resultsResume)
            }
            if reply == .collectionOverflow {
                let id = "00000000-0000-0000-0000-00000000012a"
                let item = PhoneRemoteResultItem(resultID: id, revision: 2, sourceID: id,
                    sourceRevision: 2, title: "Extra", body: "Overflow", receivedAtMilliseconds: 1_800_000_000_001)
                let event = PhoneRemoteResultEvent(sequence: 2, item: item)
                let page = PhoneRemoteResultsPage(generation: "00000000-0000-0000-0000-000000000201",
                    collectionEpoch: "00000000-0000-0000-0000-000000000301", contentWatermark: 2,
                    resetRequired: false, hasMore: false,
                    cursor: String(repeating: "B", count: 42) + "A", events: [event])
                return try PhoneRemoteOperationsJSON.encodeResponse(
                    PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsResume,
                        status: .ok, reason: .none, payload: .resultsResume(page)), for: .resultsResume)
            }
            let reset = reply == .resultsResetFlow
            let generation = reply == .foreignGeneration
                ? "00000000-0000-0000-0000-000000000202"
                : "00000000-0000-0000-0000-000000000201"
            let epoch = reply == .foreignEpoch
                ? "00000000-0000-0000-0000-000000000302"
                : "00000000-0000-0000-0000-000000000301"
            let watermark = reply == .watermarkRollback ? 0
                : (reply == .sequenceOverflow ? Int.max : 2)
            let id = "00000000-0000-0000-0000-000000000111"
            let revision = reply == .revisionRollback ? 1 : 2
            let item = PhoneRemoteResultItem(resultID: id, revision: revision, sourceID: id,
                sourceRevision: revision, title: "Synthetic card", body: revision == 1 ? "Changed at same revision" : "Updated body",
                receivedAtMilliseconds: 1_800_000_000_000)
            let events = reset || reply == .watermarkRollback ? [] : [PhoneRemoteResultEvent(
                sequence: reply == .sequenceOverflow ? 1 : 2, item: item)]
            let page = PhoneRemoteResultsPage(generation: generation,
                collectionEpoch: epoch,
                contentWatermark: reset ? nil : watermark, resetRequired: reset,
                hasMore: reset ? nil : false, cursor: reset ? nil : String(repeating: "B", count: 42) + "A", events: events)
            return try PhoneRemoteOperationsJSON.encodeResponse(
                PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsResume,
                    status: .ok, reason: .none, payload: .resultsResume(page)), for: .resultsResume)
        }
    }

    func requestCount() -> Int { requestCountValue }

    func waitForRequest() async throws -> Data {
        let deadline = ContinuousClock.now + .seconds(2)
        while lastRequestBytes == nil {
            guard ContinuousClock.now < deadline else { throw DispatchWaitError.timeout }
            try await Task.sleep(for: .milliseconds(5))
        }
        return lastRequestBytes!
    }

    func finishHeldExchange() {
        releaseRequested = true
        guard let responseContinuation, let heldReply else { return }
        self.responseContinuation = nil
        responseContinuation.resume(returning: heldReply)
    }
}

private enum DispatchWaitError: Error { case timeout }

@MainActor
final class PhoneAppPreviewModelTests: XCTestCase {
    func testStartsDisconnectedAndDoesNotDispatchUntilExplicitAction() async throws {
        let transport = PreviewTestTransport(.success)
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        XCTAssertEqual(model.state, .disconnected)
        XCTAssertEqual(PhoneAppPreviewModel.disconnectedNotice, "Disconnected from Mortimer. Synthetic preview only.")
        let initialCount = await transport.requestCount()
        XCTAssertEqual(initialCount, 0)

        await model.runSyntheticDemo()

        XCTAssertEqual(model.state, .syntheticResult(readiness: "ready"))
        let finalCount = await transport.requestCount()
        XCTAssertEqual(finalCount, 1)
    }

    func testMalformedMismatchedAndWrongOperationRepliesBecomeSafePreviewErrors() async {
        for reply in [PreviewTestTransport.Reply.malformed, .mismatchedID, .wrongOperation] {
            let transport = PreviewTestTransport(reply)
            let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
            await model.runSyntheticDemo()
            guard case .syntheticError = model.state else {
                XCTFail("invalid checked response should be presented as a bounded synthetic error")
                continue
            }
        }
    }

    func testNonOKResponseDoesNotBecomeSyntheticReadiness() async {
        let transport = PreviewTestTransport(.denied)
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        await model.runSyntheticDemo()
        XCTAssertEqual(model.state, .syntheticError(message: "Synthetic status returned denied."))
    }

    func testRepeatedSelectionWhileBusyDoesNotDispatchAnotherRequest() async throws {
        let transport = PreviewTestTransport(.hold)
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        let first = Task { await model.runSyntheticDemo() }
        _ = try await transport.waitForRequest()
        await model.runSyntheticDemo()
        let count = await transport.requestCount()
        XCTAssertEqual(count, 1)
        first.cancel()
        model.cancelDemo()
        await transport.finishHeldExchange()
        await first.value
        XCTAssertEqual(model.state, .disconnected)
    }

    func testCancellationBeforeDispatchSendsNoSyntheticBytes() async {
        let transport = PreviewTestTransport(.success)
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        let demo = Task { await model.runSyntheticDemo() }
        demo.cancel()
        model.cancelDemo()
        await demo.value

        let count = await transport.requestCount()
        XCTAssertEqual(count, 0)
        XCTAssertEqual(model.state, .disconnected)
    }

    func testCancellationInvalidatesResultImmediatelyAndDrainsBeforeRetry() async throws {
        let transport = PreviewTestTransport(.hold)
        let client = PhoneRemoteOperationsClient(transport: transport)
        let model = PhoneAppPreviewModel(client: client)
        let first = Task { await model.runSyntheticDemo() }
        _ = try await transport.waitForRequest()
        first.cancel()
        model.cancelDemo()
        XCTAssertEqual(model.state, .disconnected)
        let countDuringDrain = await transport.requestCount()
        let draining = await client.isDraining
        XCTAssertEqual(countDuringDrain, 1)
        XCTAssertTrue(draining)

        await transport.finishHeldExchange()
        await first.value
        XCTAssertEqual(model.state, .disconnected)
        let stillDraining = await client.isDraining
        let finalCount = await transport.requestCount()
        XCTAssertFalse(stillDraining)
        XCTAssertEqual(finalCount, 1)
    }

    func testSnapshotAndResumeAreExplicitCheckedAndAppliedAsOnePage() async {
        let transport = PreviewTestTransport(.resultsFlow)
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        XCTAssertEqual(model.state, .disconnected)
        await model.runSyntheticResults()
        guard case .syntheticResults(let items, let cursor, _) = model.state else {
            return XCTFail("checked synthetic result snapshot should be published")
        }
        XCTAssertEqual(items.map(\.title), ["Synthetic card"])
        XCTAssertEqual(cursor, String(repeating: "A", count: 43))
        await model.resumeSyntheticResults()
        guard case .syntheticResults(let resumed, let nextCursor, _) = model.state else {
            return XCTFail("checked resume page should preserve the existing collection")
        }
        XCTAssertEqual(resumed.map(\.body), ["Updated body"])
        XCTAssertEqual(nextCursor, String(repeating: "B", count: 42) + "A")
        let count = await transport.requestCount()
        XCTAssertEqual(count, 2)
    }

    func testResetMasksPreviouslyPublishedResults() async {
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: PreviewTestTransport(.resultsResetFlow)))
        await model.runSyntheticResults()
        guard case .syntheticResults = model.state else { return XCTFail("snapshot missing") }
        await model.resumeSyntheticResults()
        XCTAssertEqual(model.state, .disconnected)
    }

    func testResumeRejectsForeignEpochGenerationWatermarkAndRevisionBeforeAtomicApply() async {
        for reply in [PreviewTestTransport.Reply.foreignGeneration, .foreignEpoch,
                      .watermarkRollback, .revisionRollback, .sequenceOverflow] {
            let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(
                transport: PreviewTestTransport(reply)))
            await model.runSyntheticResults()
            let before = model.state
            await model.resumeSyntheticResults()
            XCTAssertEqual(model.state, before, "invalid page must not partially publish: \(reply)")
        }
    }

    func testResumeKeepsTraversalHighWaterAndBoundsMergedCollectionAtomically() async {
        let highWaterModel = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(
            transport: PreviewTestTransport(.highWaterIncrease)))
        await highWaterModel.runSyntheticResults()
        await highWaterModel.resumeSyntheticResults()
        let firstPageState = highWaterModel.state
        guard case .syntheticResults(let firstItems, _, let hasMore) = firstPageState else {
            return XCTFail("first page should be retained")
        }
        XCTAssertTrue(hasMore)
        XCTAssertEqual(firstItems.map(\.revision), [26])
        await highWaterModel.resumeSyntheticResults()
        XCTAssertEqual(highWaterModel.state, firstPageState,
                       "a successor page cannot change the frozen traversal high-water")

        let overflowModel = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(
            transport: PreviewTestTransport(.collectionOverflow)))
        await overflowModel.runSyntheticResults()
        let snapshotState = overflowModel.state
        guard case .syntheticResults(let snapshotItems, _, _) = snapshotState else {
            return XCTFail("bounded snapshot should be retained")
        }
        XCTAssertEqual(snapshotItems.count, 25)
        await overflowModel.resumeSyntheticResults()
        XCTAssertEqual(overflowModel.state, snapshotState,
                       "a 26th result must not partially publish")
    }

    func testForegroundLossMasksResultsAndInvalidatesPendingPublication() async {
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(
            transport: PreviewTestTransport(.resultsFlow)))
        await model.runSyntheticResults()
        guard case .syntheticResults = model.state else { return XCTFail("snapshot missing") }
        model.applicationDidLoseForeground()
        XCTAssertEqual(model.state, .disconnected)
    }

    func testRepeatedResultsSelectionDuringDrainDoesNotDispatchAgain() async throws {
        let transport = PreviewTestTransport(.hold)
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        let first = Task { await model.runSyntheticResults() }
        _ = try await transport.waitForRequest()
        await model.runSyntheticResults()
        let countDuringDrain = await transport.requestCount()
        XCTAssertEqual(countDuringDrain, 1)
        model.cancelDemo()
        first.cancel()
        await transport.finishHeldExchange()
        await first.value
        XCTAssertEqual(model.state, .disconnected)
        let finalCount = await transport.requestCount()
        XCTAssertEqual(finalCount, 1)
    }
}

private actor CardModelTransport: PhoneRemoteByteTransport {
    private var replies: [PhoneRemoteOperationResponse.Payload]
    private var countValue = 0
    private var holdAction: Bool
    private var held: CheckedContinuation<Void, Never>?
    init(_ replies: [PhoneRemoteOperationResponse.Payload], holdAction: Bool = false) {
        self.replies = replies; self.holdAction = holdAction
    }
    func exchange(_ data: Data) async throws -> Data {
        let request = try PhoneRemoteOperationsJSON.decodeRequest(from: data)
        countValue += 1
        guard !replies.isEmpty else { throw PhoneRemoteOperationsClientError.transportFailure }
        let payload = replies.removeFirst()
        if case .resultCard = request.payload, holdAction {
            await withCheckedContinuation { held = $0 }
        }
        return try PhoneRemoteOperationsJSON.encodeResponse(PhoneRemoteOperationResponse(
            requestID: request.requestID, operation: request.operation,
            status: .ok, reason: .none, payload: payload), for: request.operation)
    }
    func count() -> Int { countValue }
    func release() { holdAction = false; held?.resume(); held = nil }
}

private func cardSnapshotFixture(revision: Int = 1) -> PhoneRemoteOperationResponse.Payload {
    let view = cardViewFixture(), id = view.cards[0].resultID
    return .resultsSnapshot(PhoneRemoteResultsSnapshot(generation: view.generation,
        collectionEpoch: view.collectionEpoch, contentWatermark: revision,
        cursor: String(repeating: "A", count: 43), items: [PhoneRemoteResultItem(
            resultID: id, revision: revision, sourceID: id, sourceRevision: revision,
            title: "Synthetic card", body: "Fixture content", receivedAtMilliseconds: 1)]))
}

extension PhoneAppPreviewModelTests {
    @MainActor func testWholeContentJoinDisablesAllActionsAndRefreshIsOneAttempt() async {
        let baseline = cardViewFixture()
        let extra = PhoneResultCardView(generation: baseline.generation, collectionEpoch: baseline.collectionEpoch,
            viewID: baseline.viewID, viewRevision: 1, selectedResultID: nil, allowedOperations: baseline.allowedOperations,
            cards: baseline.cards + [PhoneResultCardState(resultID: "00000000-0000-0000-0000-000000000102", resultRevision: 1, open: true, pinned: false)])
        for mismatch in [cardViewFixture(revision: 1, resultRevision: 2), extra] {
            let transport = CardModelTransport([cardSnapshotFixture(), .resultCardView(mismatch),
                cardSnapshotFixture(), .resultCardView(baseline)])
            let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
            await model.refreshSyntheticCards()
            guard case .syntheticCardResults(let items, _, false, let notice) = model.state else {
                XCTFail("Incomplete join enabled controls"); continue
            }
            XCTAssertEqual(items.count, 1); XCTAssertEqual(notice, "Results changed. Refresh to sync.")
            await model.performCardAction(.pin, resultID: baseline.cards[0].resultID)
            let before = await transport.count(); XCTAssertEqual(before, 2)
            await model.refreshSyntheticCards()
            guard case .syntheticCardResults(_, _, true, _) = model.state else { XCTFail("Explicit stable refresh failed"); continue }
            let after = await transport.count(); XCTAssertEqual(after, 4)
        }
    }

    @MainActor func testHistoricalOlderEqualConflictingAndUnjoinedActionViewsCannotPublish() async {
        for invalid in [cardViewFixture(revision: 1), cardViewFixture(revision: 2, pinned: true),
                        cardViewFixture(revision: 3, resultRevision: 2)] {
            let transport = CardModelTransport([cardSnapshotFixture(), .resultCardView(cardViewFixture(revision: 2)), .resultCardView(invalid)])
            let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
            await model.refreshSyntheticCards()
            await model.performCardAction(.pin, resultID: invalid.cards[0].resultID)
            guard case .syntheticCardResults(_, let retained?, false, _) = model.state else { XCTFail("Stale view published"); continue }
            XCTAssertEqual(retained, cardViewFixture(revision: 2))
            await model.performCardAction(.close, resultID: invalid.cards[0].resultID)
            let count = await transport.count(); XCTAssertEqual(count, 3)
        }
    }

    @MainActor func testForegroundAndLocalResetMaskPendingActionWithoutLatePublication() async {
        for foreground in [true, false] {
            let transport = CardModelTransport([cardSnapshotFixture(), .resultCardView(cardViewFixture()),
                .resultCardView(cardViewFixture(revision: 1, pinned: true))], holdAction: true)
            let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
            await model.refreshSyntheticCards()
            let task = Task { await model.performCardAction(.pin, resultID: cardViewFixture().cards[0].resultID) }
            for _ in 0..<1000 { if await transport.count() == 3 { break }; await Task.yield() }
            let count = await transport.count(); XCTAssertEqual(count, 3)
            if foreground { model.applicationDidLoseForeground() } else { model.cancelDemo() }
            XCTAssertEqual(model.state, .disconnected)
            await transport.release(); await task.value
            XCTAssertEqual(model.state, .disconnected)
        }
    }
}

private actor CardReviewFaultTransport: PhoneRemoteByteTransport {
    let baseline: CardModelTransport
    let fault: String
    let at: Int
    var count = 0
    init(fault: String, at: Int) {
        self.fault = fault; self.at = at
        baseline = CardModelTransport([cardSnapshotFixture(), .resultCardView(cardViewFixture()),
            cardSnapshotFixture(), .resultCardView(cardViewFixture())])
    }
    func exchange(_ request: Data) async throws -> Data {
        count += 1
        if count == at {
            if fault == "transport" { throw CocoaError(.fileReadUnknown) }
            if fault == "malformed" { return Data("{bad".utf8) }
            let parsed = try PhoneRemoteOperationsJSON.decodeRequest(from: request)
            return try PhoneRemoteOperationsJSON.encodeResponse(PhoneRemoteOperationResponse(
                requestID: "different-request", operation: parsed.operation, status: .ok, reason: .none,
                payload: .resultCardView(cardViewFixture(revision: 1, pinned: true))), for: parsed.operation)
        }
        return try await baseline.exchange(request)
    }
}

extension PhoneAppPreviewModelTests {
    @MainActor func testReviewMalformedActionAndRefreshMaskWhileTransportFailureRetainsInertContent() async {
        for fault in ["malformed", "correlation", "transport"] {
            for action in [true, false] {
                let transport = CardReviewFaultTransport(fault: fault, at: action ? 3 : 4)
                let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
                await model.refreshSyntheticCards()
                guard case .syntheticCardResults(_, _, true, _) = model.state else { XCTFail("positive join failed"); continue }
                if action { await model.performCardAction(.pin, resultID: cardViewFixture().cards[0].resultID) }
                else { await model.refreshSyntheticCards() }
                if fault == "transport" {
                    guard case .syntheticCardResults(let items, let view?, false, _) = model.state else { XCTFail("transport state was not inert"); continue }
                    XCTAssertEqual(items.count, 1); XCTAssertEqual(view, cardViewFixture())
                } else {
                    if case .syntheticCardResults = model.state { XCTFail("malformed checked response retained card state") }
                    if case .syntheticResults = model.state { XCTFail("malformed checked response retained content") }
                }
            }
        }
    }
}
