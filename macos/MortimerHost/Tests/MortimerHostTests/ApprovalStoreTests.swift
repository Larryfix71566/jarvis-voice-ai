import XCTest
@testable import JarvisKit
@testable import MortimerHost

/// Records what the store transmits and the ids it is told about. No client,
/// no timers: the tests call `expire(requestID:)` themselves.
@MainActor
private final class ApprovalHarness {
    let store = ApprovalStore()
    var sent: [ApprovalDecide] = []
    var armed: [UUID] = []
    var approveSent: [UUID] = []
    let session = UUID()
    let generation = UUID()

    init(connected: Bool = true) {
        store.transmit = { [unowned self] message in
            if case .approvalDecide(let decide) = message { self.sent.append(decide) }
        }
        store.armTimeout = { [unowned self] id in self.armed.append(id) }
        store.didSendApprove = { [unowned self] id in self.approveSent.append(id) }
        if connected { store.sessionChanged(sessionID: session, generation: generation) }
    }

    func pending(_ id: UUID = UUID(), origin: UUID? = UUID(), summary: String = "Start the plan",
                 session: UUID? = nil, generation: UUID? = nil) -> ApprovalPending {
        ApprovalPending(sessionID: session ?? self.session, generation: generation ?? self.generation,
                        approvalID: id, originRequestID: origin, agent: "Developer", tool: "plan_start",
                        summary: summary, ts: 100, expiresAt: 400)
    }

    func settled(_ id: UUID, _ state: String) -> ApprovalSettled {
        ApprovalSettled(sessionID: session, generation: generation, approvalID: id, state: state)
    }

    func result(for decide: ApprovalDecide, code: String, status: String? = nil,
                session: UUID? = nil, generation: UUID? = nil) -> ApprovalResult {
        ApprovalResult(sessionID: session ?? self.session, generation: generation ?? self.generation,
                       requestID: decide.requestID, approvalID: decide.approvalID,
                       status: status ?? (code == "accepted" ? "accepted" : "rejected"), code: code)
    }
}

@MainActor
final class ApprovalStoreTests: XCTestCase {
    func testValidPendingIsShownAndInvalidIsDropped() {
        let h = ApprovalHarness()
        h.store.receive(h.pending(summary: ""))
        h.store.receive(h.pending(session: UUID()))
        h.store.receive(h.pending(generation: UUID()))
        XCTAssertTrue(h.store.items.isEmpty)
        let id = UUID()
        h.store.receive(h.pending(id, summary: "Start the plan for WS-36"))
        XCTAssertEqual(h.store.items.map(\.id), [id])
        XCTAssertEqual(h.store.items.first?.summary, "Start the plan for WS-36")
        XCTAssertEqual(h.store.items.first?.title, "Developer · plan_start")
        XCTAssertTrue(h.store.hasOpenItems)
    }

    func testPendingBeforeHelloIsDropped() {
        let h = ApprovalHarness(connected: false)
        h.store.receive(h.pending())
        XCTAssertTrue(h.store.items.isEmpty)
    }

    func testRepeatedPendingReplacesInPlace() {
        let h = ApprovalHarness()
        let first = UUID(), second = UUID()
        h.store.receive(h.pending(first))
        h.store.receive(h.pending(second))
        h.store.receive(h.pending(first, summary: "Updated"))
        XCTAssertEqual(h.store.items.map(\.id), [first, second])
        XCTAssertEqual(h.store.items.first?.summary, "Updated")
    }

    func testSettledRemovesTheItemAndLeavesAppTextNotes() {
        let expected: [String: String] = [
            "approved": "Approved.", "declined": "Declined.", "resolved": "Done by voice.",
            "superseded": "Replaced by a newer request.", "expired": "Expired before an answer.",
        ]
        for (state, text) in expected {
            let h = ApprovalHarness()
            let id = UUID()
            h.store.receive(h.pending(id, summary: "bot words that must not be the note"))
            h.store.receive(h.settled(id, state))
            XCTAssertTrue(h.store.items.isEmpty, state)
            XCTAssertEqual(h.store.notes.map(\.text), [text], state)
            XCTAssertEqual(h.store.notes.first?.id, id)
        }
    }

    func testSettledForUnknownIdOrBadStateIsIgnored() {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        h.store.receive(h.settled(UUID(), "approved"))
        h.store.receive(h.settled(id, "maybe"))
        XCTAssertEqual(h.store.items.map(\.id), [id])
        XCTAssertTrue(h.store.notes.isEmpty)
    }

    func testApproveSendsOneDecisionAndBlocksASecondWhileInFlight() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        let requestID = try XCTUnwrap(h.store.decide(id, .approve))
        XCTAssertNil(h.store.decide(id, .approve))
        XCTAssertNil(h.store.decide(id, .decline))
        XCTAssertEqual(h.sent.count, 1)
        let decide = h.sent[0]
        XCTAssertEqual(decide.requestID, requestID)
        XCTAssertEqual(decide.approvalID, id)
        XCTAssertEqual(decide.decision, .approve)
        XCTAssertEqual(decide.sessionID, h.session)
        XCTAssertEqual(decide.generation, h.generation)
        XCTAssertEqual(h.armed, [requestID])
        XCTAssertEqual(h.approveSent, [id], "The router is told so the approve turn's answer comes forward")
        XCTAssertTrue(h.store.items[0].isBusy)
    }

    func testDeclineDoesNotBindATurn() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        _ = try XCTUnwrap(h.store.decide(id, .decline))
        XCTAssertEqual(h.sent.first?.decision, .decline)
        XCTAssertTrue(h.approveSent.isEmpty)
    }

    func testDecideNeedsAnOpenItemAndASession() {
        let h = ApprovalHarness()
        XCTAssertNil(h.store.decide(UUID(), .approve))
        let unwired = ApprovalStore()
        unwired.sessionChanged(sessionID: UUID(), generation: UUID())
        XCTAssertNil(unwired.decide(UUID(), .approve))
        XCTAssertTrue(h.sent.isEmpty)
    }

    func testAcceptedKeepsButtonsDisabledUntilSettled() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        _ = try XCTUnwrap(h.store.decide(id, .approve))
        h.store.receive(h.result(for: h.sent[0], code: "accepted"))
        XCTAssertTrue(h.store.items[0].isBusy)
        h.store.receive(h.settled(id, "approved"))
        XCTAssertTrue(h.store.items.isEmpty)
        XCTAssertEqual(h.store.notes.map(\.text), ["Approved."])
    }

    func testNotReadyReEnablesWithANoticeAndANewTapIsANewRequest() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        let first = try XCTUnwrap(h.store.decide(id, .approve))
        h.store.receive(h.result(for: h.sent[0], code: "not_ready"))
        XCTAssertFalse(h.store.items[0].isBusy)
        XCTAssertEqual(h.store.items[0].notice, "Mortimer couldn't start it. Try again.")
        let second = try XCTUnwrap(h.store.decide(id, .approve))
        XCTAssertNotEqual(first, second)
        XCTAssertNil(h.store.items[0].notice)
    }

    func testDeclineNotReadyNotice() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        _ = try XCTUnwrap(h.store.decide(id, .decline))
        h.store.receive(h.result(for: h.sent[0], code: "not_ready"))
        XCTAssertEqual(h.store.items[0].notice, "Mortimer couldn't take that. Try again.")
    }

    func testUnknownAndAlreadySettledRemoveTheItem() throws {
        for code in ["unknown_approval", "already_settled"] {
            let h = ApprovalHarness()
            let id = UUID()
            h.store.receive(h.pending(id))
            _ = try XCTUnwrap(h.store.decide(id, .approve))
            h.store.receive(h.result(for: h.sent[0], code: code))
            XCTAssertTrue(h.store.items.isEmpty, code)
            XCTAssertEqual(h.store.notes.map(\.text), ["No longer waiting."], code)
        }
    }

    func testExpiredResultLeavesTheExpiredNote() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        _ = try XCTUnwrap(h.store.decide(id, .approve))
        h.store.receive(h.result(for: h.sent[0], code: "expired"))
        XCTAssertEqual(h.store.notes.map(\.text), ["Expired before an answer."])
    }

    func testOtherRejectionsReEnableWithAReason() throws {
        let expected = [
            "protected_turn": "This one needs your answer by voice.",
            "disabled": "Approvals in the app are turned off. Answer by voice.",
            "duplicate": "Mortimer already has that answer.",
        ]
        for (code, text) in expected {
            let h = ApprovalHarness()
            let id = UUID()
            h.store.receive(h.pending(id))
            _ = try XCTUnwrap(h.store.decide(id, .approve))
            h.store.receive(h.result(for: h.sent[0], code: code))
            XCTAssertFalse(h.store.items[0].isBusy, code)
            XCTAssertEqual(h.store.items[0].notice, text, code)
        }
    }

    func testResultForAnotherRequestOrSessionIsIgnored() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        _ = try XCTUnwrap(h.store.decide(id, .approve))
        let wrongRequest = ApprovalResult(sessionID: h.session, generation: h.generation, requestID: UUID(),
                                          approvalID: id, status: "rejected", code: "not_ready")
        h.store.receive(wrongRequest)
        h.store.receive(h.result(for: h.sent[0], code: "not_ready", generation: UUID()))
        XCTAssertTrue(h.store.items[0].isBusy)
    }

    func testStaleSessionClearsEverything() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        h.store.receive(h.pending(UUID()))
        _ = try XCTUnwrap(h.store.decide(id, .approve))
        h.store.receive(h.result(for: h.sent[0], code: "stale_session", session: UUID()))
        XCTAssertTrue(h.store.items.isEmpty)
        XCTAssertTrue(h.store.notes.isEmpty)
        XCTAssertNil(h.store.session)
    }

    func testTimeoutReEnablesTheButtons() throws {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        let requestID = try XCTUnwrap(h.store.decide(id, .approve))
        h.store.expire(requestID: UUID())
        XCTAssertTrue(h.store.items[0].isBusy)
        h.store.expire(requestID: requestID)
        XCTAssertFalse(h.store.items[0].isBusy)
        XCTAssertEqual(h.store.items[0].notice, "No answer from Mortimer. Try again.")
    }

    func testDisconnectAndNewSessionClear() {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(h.pending(id))
        h.store.receive(h.settled(id, "declined"))
        h.store.receive(h.pending(UUID()))
        h.store.sessionChanged(sessionID: h.session, generation: h.generation)
        XCTAssertEqual(h.store.items.count, 1, "The same session keeps its items")
        h.store.sessionChanged(sessionID: h.session, generation: UUID())
        XCTAssertTrue(h.store.items.isEmpty)
        XCTAssertTrue(h.store.notes.isEmpty)
        h.store.receive(h.pending(UUID(), generation: h.store.session?.generation))
        XCTAssertEqual(h.store.items.count, 1)
        h.store.sessionEnded()
        XCTAssertTrue(h.store.items.isEmpty)
        XCTAssertNil(h.store.session)
    }

    func testNotesAreBounded() {
        let h = ApprovalHarness()
        for _ in 0..<(ApprovalStore.maxNotes + 5) {
            let id = UUID()
            h.store.receive(h.pending(id))
            h.store.receive(h.settled(id, "declined"))
        }
        XCTAssertEqual(h.store.notes.count, ApprovalStore.maxNotes)
    }

    func testReceiveDispatchesAppMessages() {
        let h = ApprovalHarness()
        let id = UUID()
        h.store.receive(AppMessage.approvalPending(h.pending(id)))
        XCTAssertEqual(h.store.items.map(\.id), [id])
        h.store.receive(AppMessage.approvalSettled(h.settled(id, "resolved")))
        XCTAssertEqual(h.store.notes.map(\.text), ["Done by voice."])
    }

    // MARK: hasPendingDraft (contract 3.9)

    func testOpenApprovalLightsHasPendingDraftAndSettleClearsIt() {
        let h = ApprovalHarness()
        let display = DisplayResultStore()
        display.approvals = h.store
        XCTAssertFalse(display.hasPendingDraft)
        let id = UUID()
        h.store.receive(h.pending(id))
        XCTAssertTrue(display.hasPendingDraft)
        h.store.receive(h.settled(id, "approved"))
        XCTAssertFalse(display.hasPendingDraft)
    }
}
