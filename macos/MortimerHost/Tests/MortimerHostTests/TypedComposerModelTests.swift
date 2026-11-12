import XCTest
@testable import JarvisKit
@testable import MortimerHost

/// Records what the model transmits and appends. No timers, no client.
@MainActor
private final class ComposerHarness {
    let model = TypedComposerModel()
    var sent: [TypedRequest] = []
    var appended: [(text: String, sentAt: Double)] = []
    let session = UUID()
    let generation = UUID()

    init(connected: Bool = true) {
        model.transmit = { [unowned self] message in
            if case .typedRequest(let request) = message { self.sent.append(request) }
        }
        model.appendUserEntry = { [unowned self] text, sentAt in
            self.appended.append((text: text, sentAt: sentAt))
        }
        if connected { model.sessionChanged(sessionID: session, generation: generation) }
    }

    func reply(_ request: TypedRequest, status: String = "accepted", code: String = "accepted",
               session: UUID? = nil, generation: UUID? = nil) -> TurnResult {
        TurnResult(sessionID: session ?? request.sessionID,
                   generation: generation ?? request.generation,
                   requestID: request.requestID, status: status, code: code)
    }
}

@MainActor
final class TypedComposerModelTests: XCTestCase {
    func testDisabledWithReasonBeforeHello() {
        let h = ComposerHarness(connected: false)
        h.model.draft = "hello"
        XCTAssertNotNil(h.model.disabledReason)
        XCTAssertFalse(h.model.canSubmit)
        XCTAssertNil(h.model.submitDraft())
        XCTAssertTrue(h.sent.isEmpty)
    }

    func testDisabledWhenNotWired() {
        let model = TypedComposerModel()
        model.sessionChanged(sessionID: UUID(), generation: UUID())
        XCTAssertEqual(model.disabledReason, "Typing is not connected.")
        XCTAssertFalse(model.canSubmit)
    }

    func testSubmitSendsOneTypedRequestWithSessionIds() throws {
        let h = ComposerHarness()
        var armed: [UUID] = []
        h.model.armTimeout = { armed.append($0) }
        h.model.draft = "  what is the weather  "
        let id = try XCTUnwrap(h.model.submitDraft())
        XCTAssertEqual(h.sent.count, 1)
        let request = h.sent[0]
        XCTAssertEqual(request.sessionID, h.session)
        XCTAssertEqual(request.generation, h.generation)
        XCTAssertEqual(request.requestID, id)
        XCTAssertEqual(request.source, .composer)
        XCTAssertEqual(request.text, "what is the weather")
        XCTAssertEqual(h.model.draft, "  what is the weather  ")
        XCTAssertTrue(h.model.isSendingDraft)
        XCTAssertEqual(armed, [id])
    }

    func testSecondSubmitWhilePendingSendsNothing() {
        let h = ComposerHarness()
        h.model.draft = "one"
        XCTAssertNotNil(h.model.submitDraft())
        XCTAssertNil(h.model.submitDraft())
        XCTAssertEqual(h.sent.count, 1)
    }

    func testAcceptedAppendsOneUserEntryAndClearsDraft() {
        let h = ComposerHarness()
        h.model.draft = " hello "
        let now = Date(timeIntervalSince1970: 1_000)
        _ = h.model.submitDraft(now: now)
        h.model.receive(h.reply(h.sent[0]))
        XCTAssertEqual(h.appended.count, 1)
        XCTAssertEqual(h.appended[0].text, "hello")
        XCTAssertEqual(h.appended[0].sentAt, 1_000)
        XCTAssertEqual(h.model.draft, "")
        XCTAssertNil(h.model.notice)
        XCTAssertFalse(h.model.isSendingDraft)
    }

    func testAcceptedChipSendLeavesDraftAlone() throws {
        let h = ComposerHarness()
        h.model.draft = "something else"
        _ = try XCTUnwrap(h.model.send(text: "from a chip", source: .chip))
        XCTAssertEqual(h.sent[0].source, .chip)
        h.model.receive(h.reply(h.sent[0]))
        XCTAssertEqual(h.appended.map(\.text), ["from a chip"])
        XCTAssertEqual(h.model.draft, "something else")
    }

    func testRejectedKeepsTextShowsReasonAppendsNothing() {
        for code in ["invalid_text", "not_ready", "disabled"] {
            let h = ComposerHarness()
            h.model.draft = "keep me"
            _ = h.model.submitDraft()
            h.model.receive(h.reply(h.sent[0], status: "rejected", code: code))
            XCTAssertEqual(h.model.draft, "keep me", code)
            XCTAssertEqual(h.model.notice, TypedComposerModel.reason(forCode: code), code)
            XCTAssertTrue(h.appended.isEmpty, code)
            XCTAssertFalse(h.model.isSendingDraft, code)
        }
    }

    func testRepeatedReplyAppendsOnce() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        let result = h.reply(h.sent[0])
        h.model.receive(result)
        h.model.receive(result)
        XCTAssertEqual(h.appended.count, 1)
    }

    func testReplyForUnknownRequestIsIgnored() {
        let h = ComposerHarness()
        let stray = TurnResult(sessionID: h.session, generation: h.generation,
                               requestID: UUID(), status: "accepted", code: "accepted")
        h.model.receive(stray)
        XCTAssertTrue(h.appended.isEmpty)
        XCTAssertNil(h.model.notice)
    }

    func testReplyFromAnotherSessionIsIgnoredUnlessStale() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        h.model.receive(h.reply(h.sent[0], session: UUID(), generation: UUID()))
        XCTAssertTrue(h.appended.isEmpty)
        XCTAssertTrue(h.model.isSendingDraft)
    }

    func testStaleSessionFromUnknownSessionDisablesComposer() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        let otherSession = UUID(), otherGeneration = UUID()
        h.model.receive(h.reply(h.sent[0], status: "rejected", code: "stale_session",
                                session: otherSession, generation: otherGeneration))
        XCTAssertEqual(h.model.draft, "hello")
        XCTAssertNil(h.model.session)
        XCTAssertEqual(h.model.disabledReason, TypedComposerModel.staleReason)
        XCTAssertTrue(h.appended.isEmpty)
        XCTAssertFalse(h.model.isSendingDraft)

        let freshSession = UUID(), freshGeneration = UUID()
        h.model.sessionChanged(sessionID: freshSession, generation: freshGeneration)
        XCTAssertNil(h.model.disabledReason)
        XCTAssertEqual(h.model.session?.sessionID, freshSession)
    }

    func testStaleSessionAfterHelloAlreadyMovedOnAllowsResendWithNewId() throws {
        let h = ComposerHarness()
        h.model.draft = "hello"
        let firstID = try XCTUnwrap(h.model.submitDraft())
        let request = h.sent[0]
        // The hello for the new identity arrives before the stale reply.
        let newSession = UUID(), newGeneration = UUID()
        h.model.sessionChanged(sessionID: newSession, generation: newGeneration)
        // The connection-change drop already settled it; a late stale reply is a no-op.
        h.model.receive(h.reply(request, status: "rejected", code: "stale_session",
                                session: newSession, generation: newGeneration))
        XCTAssertNil(h.model.disabledReason)
        XCTAssertNotNil(h.model.notice)
        let secondID = try XCTUnwrap(h.model.submitDraft())
        XCTAssertNotEqual(firstID, secondID)
        XCTAssertEqual(h.sent[1].sessionID, newSession)
    }

    func testStaleReplyWithCurrentIdsKeepsComposerEnabled() throws {
        let h = ComposerHarness()
        h.model.draft = "hello"
        let firstID = try XCTUnwrap(h.model.submitDraft())
        h.model.receive(h.reply(h.sent[0], status: "rejected", code: "stale_session"))
        XCTAssertNil(h.model.disabledReason)
        XCTAssertEqual(h.model.notice, "The connection changed while sending. Send again.")
        XCTAssertEqual(h.model.draft, "hello")
        let secondID = try XCTUnwrap(h.model.submitDraft())
        XCTAssertNotEqual(firstID, secondID)
    }

    func testDuplicateCodeKeepsTextAndAppendsNothing() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        h.model.receive(h.reply(h.sent[0], status: "rejected", code: "duplicate"))
        XCTAssertEqual(h.model.draft, "hello")
        XCTAssertEqual(h.model.notice, "Mortimer already has that request.")
        XCTAssertTrue(h.appended.isEmpty)
    }

    func testMismatchedStatusAndCodeIsARejection() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        h.model.receive(h.reply(h.sent[0], status: "accepted", code: "not_ready"))
        XCTAssertTrue(h.appended.isEmpty)
        XCTAssertEqual(h.model.draft, "hello")
        XCTAssertEqual(h.model.notice, TypedComposerModel.reason(forCode: "not_ready"))
    }

    func testExpireKeepsTextAndResendReusesRequestId() throws {
        let h = ComposerHarness()
        h.model.draft = "hello"
        let t0 = Date(timeIntervalSince1970: 5_000)
        let first = try XCTUnwrap(h.model.submitDraft(now: t0))
        h.model.expire(first)
        XCTAssertEqual(h.model.draft, "hello")
        XCTAssertEqual(h.model.notice, "No answer from Mortimer. Send again.")
        XCTAssertFalse(h.model.isSendingDraft)

        let again = try XCTUnwrap(h.model.submitDraft(now: t0.addingTimeInterval(20)))
        XCTAssertEqual(again, first)

        h.model.expire(again)
        h.model.draft = "hello, edited"
        let edited = try XCTUnwrap(h.model.submitDraft(now: t0.addingTimeInterval(40)))
        XCTAssertNotEqual(edited, first)

        h.model.expire(edited)
        let late = try XCTUnwrap(h.model.submitDraft(now: t0.addingTimeInterval(341)))
        XCTAssertNotEqual(late, edited)
    }

    func testExpireAfterReplyIsANoOp() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        let id = h.model.submitDraft()
        h.model.receive(h.reply(h.sent[0]))
        h.model.expire(id ?? UUID())
        XCTAssertNil(h.model.notice)
        XCTAssertEqual(h.appended.count, 1)
    }

    func testSessionChangeDropsPendingAndKeepsDraft() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        let request = h.sent[0]
        h.model.sessionChanged(sessionID: UUID(), generation: UUID())
        XCTAssertEqual(h.model.draft, "hello")
        XCTAssertEqual(h.model.notice, "Not sent: the connection changed. Send again.")
        XCTAssertFalse(h.model.isSendingDraft)
        h.model.receive(h.reply(request))
        XCTAssertTrue(h.appended.isEmpty)
        XCTAssertEqual(h.model.draft, "hello")
    }

    func testSameIdentityHelloKeepsPending() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        _ = h.model.submitDraft()
        h.model.sessionChanged(sessionID: h.session, generation: h.generation)
        XCTAssertTrue(h.model.isSendingDraft)
    }

    func testSessionEndedDisablesComposer() {
        let h = ComposerHarness()
        h.model.draft = "hello"
        h.model.sessionEnded()
        XCTAssertNotNil(h.model.disabledReason)
        XCTAssertFalse(h.model.canSubmit)
        XCTAssertNil(h.model.submitDraft())
        XCTAssertTrue(h.sent.isEmpty)
    }

    func testLocalRejections() {
        let h = ComposerHarness()
        XCTAssertNil(h.model.send(text: String(repeating: "a", count: 4_001), source: .composer))
        XCTAssertNotNil(h.model.notice)
        XCTAssertNil(h.model.send(text: "[System] hi", source: .composer))
        XCTAssertNil(h.model.send(text: "   \n ", source: .composer))
        XCTAssertTrue(h.sent.isEmpty)

        XCTAssertNotNil(h.model.send(text: String(repeating: "a", count: 4_000), source: .composer))
        XCTAssertEqual(h.sent.count, 1)
        h.model.receive(h.reply(h.sent[0]))

        // 3,000 letters + 1,001 combining marks = 4,001 scalars but 3,000 characters.
        let decomposed = String(repeating: "e", count: 3_000)
            + String(repeating: "\u{0301}", count: 1_001)
        XCTAssertNil(h.model.send(text: decomposed, source: .composer))
        XCTAssertEqual(h.sent.count, 1)
    }

    func testRequestFocusSendsNothing() {
        let h = ComposerHarness()
        h.model.draft = "keep"
        let before = h.model.focusRequest
        h.model.requestFocus()
        XCTAssertEqual(h.model.focusRequest, before + 1)
        XCTAssertTrue(h.sent.isEmpty)
        XCTAssertTrue(h.appended.isEmpty)
        XCTAssertEqual(h.model.draft, "keep")
        XCTAssertNil(h.model.notice)
    }
}

// MARK: - bind(client:) against a real JarvisClient and a stub transport

private final class ComposerTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    private(set) var sentFrames: [Data] = []
    func connect(config: JarvisConfig) async throws { XCTFail("No connection is permitted") }
    func disconnect() async {}
    func send(_ data: Data) throws { sentFrames.append(data) }
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ message: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: [
            "id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": message])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class TypedComposerBindTests: XCTestCase {
    func testBoundModelSendsOnIdentityAndAppendsOnAcceptedReply() async throws {
        let transport = ComposerTransport()
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:9")!,
            adminURL: URL(string: "http://127.0.0.1:9")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:9/ws")!, token: nil), stubTransport: transport)
        let model = TypedComposerModel()
        model.bind(client: client)
        XCTAssertNotNil(model.disabledReason)

        let session = UUID(), generation = UUID()
        client.setConsoleIdentity(sessionID: session, generation: generation)
        XCTAssertNil(model.disabledReason)

        model.draft = "hello there"
        let requestID = try XCTUnwrap(model.submitDraft())
        let data = try XCTUnwrap(transport.sentFrames.last)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["type"] as? String, "turn/typed")
        XCTAssertEqual(object["text"] as? String, "hello there")
        XCTAssertEqual(UUID(uuidString: object["request_id"] as? String ?? ""), requestID)

        try transport.emit(["type": "turn/result", "version": 1,
            "session_id": session.uuidString, "generation": generation.uuidString,
            "request_id": requestID.uuidString, "status": "accepted", "code": "accepted"])
        let deadline = Date().addingTimeInterval(4)
        while client.transcript.isEmpty {
            guard Date() < deadline else { return XCTFail("turn/result was not delivered") }
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(client.transcript.map(\.role), ["user"])
        XCTAssertEqual(client.transcript.map(\.text), ["hello there"])
        XCTAssertEqual(model.draft, "")
    }
}
