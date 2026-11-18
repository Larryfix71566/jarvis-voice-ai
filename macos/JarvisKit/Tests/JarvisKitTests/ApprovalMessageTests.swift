import XCTest
@testable import JarvisKit

/// C7a (contract §3): the approval message pair decodes from the RTVI
/// envelope, `approval/decide` is exactly seven keys, and the debug line
/// never carries the summary.
final class ApprovalMessageTests: XCTestCase {
    private let session = UUID(uuidString: "00000000-0000-4000-8000-000000000001")!
    private let generation = UUID(uuidString: "00000000-0000-4000-8000-000000000002")!
    private let approval = UUID(uuidString: "00000000-0000-4000-8000-000000000004")!
    private let origin = UUID(uuidString: "00000000-0000-4000-8000-000000000005")!
    private let request = UUID(uuidString: "00000000-0000-4000-8000-000000000006")!

    private func envelope(_ data: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: [
            "id": "m", "label": "rtvi-ai", "type": "server-message", "data": data])
    }

    private func pendingObject(origin: Any? = nil, summary: String = "Start the plan for WS-36",
                               ts: Double = 100, expiresAt: Double = 400) -> [String: Any] {
        [
            "type": "approval/pending", "version": 1,
            "session_id": session.uuidString.lowercased(),
            "generation": generation.uuidString.lowercased(),
            "approval_id": approval.uuidString.lowercased(),
            "origin_request_id": origin ?? NSNull(),
            "run_id": "run-1", "agent": "Developer", "tool": "plan_start",
            "summary": summary, "ts": ts, "expires_at": expiresAt,
        ]
    }

    func testDecodePendingFromEnvelopeAndValidate() throws {
        let data = try envelope(pendingObject(origin: origin.uuidString.lowercased()))
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .approvalPending(let pending) = message else { return XCTFail("expected .approvalPending") }
        XCTAssertEqual(pending.approvalID, approval)
        XCTAssertEqual(pending.originRequestID, origin)
        XCTAssertEqual(pending.agent, "Developer")
        XCTAssertEqual(pending.tool, "plan_start")
        XCTAssertEqual(pending.summary, "Start the plan for WS-36")
        XCTAssertTrue(pending.isValid(sessionID: session, generation: generation))
        XCTAssertFalse(pending.isValid(sessionID: UUID(), generation: generation))
        XCTAssertFalse(pending.isValid(sessionID: session, generation: UUID()))
    }

    func testDecodePendingWithNullOrigin() throws {
        let message = try XCTUnwrap(try AppMessage.decode(frame: envelope(pendingObject())))
        guard case .approvalPending(let pending) = message else { return XCTFail("expected .approvalPending") }
        XCTAssertNil(pending.originRequestID)
        XCTAssertTrue(pending.isValid(sessionID: session, generation: generation))
    }

    func testPendingValidationBounds() {
        func pending(summary: String = "ok", agent: String = "Developer", tool: String = "plan_start",
                     ts: Double = 100, expiresAt: Double = 400) -> ApprovalPending {
            ApprovalPending(sessionID: session, generation: generation, approvalID: approval,
                            originRequestID: nil, agent: agent, tool: tool, summary: summary,
                            ts: ts, expiresAt: expiresAt)
        }
        XCTAssertTrue(pending(summary: String(repeating: "a", count: 600)).isValid(sessionID: session, generation: generation))
        XCTAssertFalse(pending(summary: String(repeating: "a", count: 601)).isValid(sessionID: session, generation: generation))
        XCTAssertFalse(pending(summary: "").isValid(sessionID: session, generation: generation))
        XCTAssertFalse(pending(agent: String(repeating: "a", count: 81)).isValid(sessionID: session, generation: generation))
        XCTAssertFalse(pending(tool: String(repeating: "a", count: 81)).isValid(sessionID: session, generation: generation))
        XCTAssertFalse(pending(ts: 400, expiresAt: 400).isValid(sessionID: session, generation: generation))
    }

    func testPendingWithBadApprovalIDDoesNotDecode() throws {
        var object = pendingObject()
        object["approval_id"] = "not-a-uuid"
        XCTAssertThrowsError(try AppMessage.decode(frame: envelope(object)))
    }

    func testDecodeSettled() throws {
        let data = try envelope([
            "type": "approval/settled", "version": 1,
            "session_id": session.uuidString, "generation": generation.uuidString,
            "approval_id": approval.uuidString, "state": "superseded"])
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .approvalSettled(let settled) = message else { return XCTFail("expected .approvalSettled") }
        XCTAssertEqual(settled.approvalID, approval)
        XCTAssertEqual(settled.state, "superseded")
        XCTAssertTrue(ApprovalSettled.states.contains(settled.state))
    }

    func testDecodeResult() throws {
        let data = try envelope([
            "type": "approval/result", "version": 1,
            "session_id": session.uuidString, "generation": generation.uuidString,
            "request_id": request.uuidString, "approval_id": approval.uuidString,
            "status": "accepted", "code": "accepted"])
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .approvalResult(let result) = message else { return XCTFail("expected .approvalResult") }
        XCTAssertTrue(result.isAccepted)
        XCTAssertEqual(result.requestID, request)
        XCTAssertEqual(result.approvalID, approval)
    }

    func testResultAcceptedNeedsMatchingCode() {
        let result = ApprovalResult(sessionID: session, generation: generation, requestID: request,
                                    approvalID: approval, status: "accepted", code: "not_ready")
        XCTAssertFalse(result.isAccepted)
    }

    func testDecideEncodesExactlySevenKeys() throws {
        let decide = ApprovalDecide(sessionID: session, generation: generation, requestID: request,
                                    approvalID: approval, decision: .decline)
        let data = try ClientMessage.approvalDecide(decide).jsonData()
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(Set(object.keys), ["type", "version", "session_id", "generation",
                                          "request_id", "approval_id", "decision"])
        XCTAssertEqual(object["type"] as? String, "approval/decide")
        XCTAssertEqual(object["version"] as? Int, 1)
        XCTAssertEqual(object["decision"] as? String, "decline")
        XCTAssertEqual(UUID(uuidString: object["session_id"] as? String ?? ""), session)
        XCTAssertEqual(UUID(uuidString: object["generation"] as? String ?? ""), generation)
        XCTAssertEqual(UUID(uuidString: object["request_id"] as? String ?? ""), request)
        XCTAssertEqual(UUID(uuidString: object["approval_id"] as? String ?? ""), approval)
    }

    func testDebugDescriptionNeverCarriesTheSummary() {
        let secret = "summary-marker-should-not-log"
        let pending = ApprovalPending(sessionID: session, generation: generation, approvalID: approval,
                                      originRequestID: nil, agent: "Developer", tool: "plan_start",
                                      summary: secret, ts: 1, expiresAt: 2)
        let line = AppMessage.approvalPending(pending).debugDescription
        XCTAssertTrue(line.contains("approvalPending("))
        XCTAssertTrue(line.contains(approval.uuidString))
        XCTAssertFalse(line.contains(secret))
        let settled = AppMessage.approvalSettled(ApprovalSettled(
            sessionID: session, generation: generation, approvalID: approval, state: "declined"))
        XCTAssertTrue(settled.debugDescription.contains("declined"))
    }
}
