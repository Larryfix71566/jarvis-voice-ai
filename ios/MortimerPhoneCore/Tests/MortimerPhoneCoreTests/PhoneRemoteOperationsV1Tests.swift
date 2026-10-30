import Foundation
import XCTest
@testable import MortimerPhoneCore

final class PhoneRemoteOperationsV1Tests: XCTestCase {
    func testFourClosedRequestSchemasRoundTripThroughCheckedBoundary() throws {
        let cases: [(PhoneRemoteOperationRequest.Payload, PhoneRemoteOperation, Set<String>)] = [
            (.sessionStatus, .sessionStatus, []),
            (.voiceOffer(sdp: "offer-canary"), .voiceOffer, ["sdp"]),
            (.voiceUpdate(peerID: "peer-canary", sdp: "update-canary"), .voiceUpdate, ["peer_id", "sdp"]),
            (.voiceEnd(peerID: "peer-canary"), .voiceEnd, ["peer_id"]),
        ]
        for (payload, operation, payloadKeys) in cases {
            let request = try PhoneRemoteOperationRequest(requestID: "rid-1", payload: payload)
            let data = try PhoneRemoteOperationsJSON.encodeRequest(request)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(Set(object.keys), ["kind", "protocol_version", "request_id", "operation", "payload"])
            XCTAssertEqual(object["operation"] as? String, operation.rawValue)
            XCTAssertEqual(Set(try XCTUnwrap(object["payload"] as? [String: Any]).keys), payloadKeys)
            let decoded = try PhoneRemoteOperationsJSON.decodeRequest(from: data)
            XCTAssertEqual(decoded, request)
            let codableData = try JSONEncoder().encode(request)
            XCTAssertThrowsError(try JSONDecoder().decode(PhoneRemoteOperationRequest.self, from: codableData))
        }
    }

    func testRequestOperationAndPayloadCannotBeCrossed() {
        let malformed = [
            envelope(op: "session.status", payload: #"{"peer_id":"p"}"#),
            envelope(op: "voice.offer", payload: "{}"),
            envelope(op: "voice.update", payload: #"{"sdp":"s"}"#),
            envelope(op: "voice.end", payload: #"{"peer_id":"p","sdp":"s"}"#),
            envelope(op: "results.snapshot", payload: "{}"),
        ]
        for json in malformed {
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(json.utf8)))
        }
    }

    func testRequestIDsMustBeNonemptyAndAtMost128UTF8Bytes() throws {
        XCTAssertThrowsError(try PhoneRemoteOperationRequest(requestID: "", payload: .sessionStatus))
        let atLimit = String(repeating: "🙂", count: 32)
        XCTAssertEqual(try PhoneRemoteOperationRequest(requestID: atLimit, payload: .sessionStatus).requestID.utf8.count, 128)
        XCTAssertThrowsError(try PhoneRemoteOperationRequest(requestID: atLimit + "x", payload: .sessionStatus))
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(envelope(op: "session.status", rid: "", payload: "{}").utf8)))
    }

    func testDuplicateKeysIncludingEscapedEquivalentAreRejectedAtEveryDepth() {
        let cases = [
            #"{"kind":"mortimer.phone-remote.v1","kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"voice.offer","payload":{"sdp":"a","sd\u0070":"b"}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"nested":{"x":1,"x":2}}}"#,
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(json.utf8)))
        }
    }

    func testPublicDecodableInitializersCannotBypassCheckedJSONBoundary() {
        let duplicateRequest = #"{"kind":"mortimer.phone-remote.v1","kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{}}"#
        let oversizedRequest = #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"voice.offer","payload":{"sdp":"""# + String(repeating: "x", count: PhoneRemoteOperationsJSON.maximumInputBytes) + #"""}"#
        for input in [duplicateRequest, oversizedRequest] {
            XCTAssertThrowsError(try JSONDecoder().decode(PhoneRemoteOperationRequest.self, from: Data(input.utf8)))
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(input.utf8)))
        }

        let duplicateResponse = #"{"request_id":"r","request_id":"x","status":"denied","reason":"not_authorized","payload":{}}"#
        let responseDecoder = JSONDecoder()
        responseDecoder.userInfo[.phoneRemoteOperation] = PhoneRemoteOperation.voiceOffer
        XCTAssertThrowsError(try responseDecoder.decode(PhoneRemoteOperationResponse.self, from: Data(duplicateResponse.utf8)))
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(duplicateResponse.utf8), for: .voiceOffer))
    }

    func testUnknownKeysMissingFieldsAndEmptyStringsAreRejected() {
        let cases = [
            envelope(op: "session.status", payload: #"{"unexpected":1}"#),
            envelope(op: "voice.offer", payload: "{}"),
            envelope(op: "voice.offer", payload: #"{"sdp":"","extra":true}"#),
            envelope(op: "voice.update", payload: #"{"peer_id":"p","sdp":"s","extra":true}"#),
            envelope(op: "voice.update", payload: #"{"peer_id":"","sdp":"s"}"#),
            envelope(op: "voice.end", payload: #"{"peer_id":""}"#),
            envelope(op: "voice.end", payload: #"{"peer_id":"p","ended":true}"#),
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(json.utf8)))
        }
    }

    func testWrongEnvelopeFieldsAndNonFiniteNumbersAreRejected() {
        let cases = [
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1.5,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1.0,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1e0,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1.00000000000000000001,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":true,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{},"extra":0}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"x":NaN}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"x":Infinity}}"#,
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(json.utf8)))
        }
    }

    func testRequestSizeAndDepthLimits() throws {
        let small = try PhoneRemoteOperationRequest(requestID: "rid", payload: .voiceOffer(sdp: "x"))
        let overhead = try PhoneRemoteOperationsJSON.encodeRequest(small).count - 1
        let exactSize = try PhoneRemoteOperationRequest(
            requestID: "rid", payload: .voiceOffer(sdp: String(repeating: "x", count: PhoneRemoteOperationsJSON.maximumInputBytes - overhead))
        )
        let exactData = try PhoneRemoteOperationsJSON.encodeRequest(exactSize)
        XCTAssertEqual(exactData.count, PhoneRemoteOperationsJSON.maximumInputBytes)
        XCTAssertNoThrow(try PhoneRemoteOperationsJSON.decodeRequest(from: exactData))

        let large = envelope(op: "voice.offer", payload: #"{"sdp":"""# + String(repeating: "x", count: PhoneRemoteOperationsJSON.maximumInputBytes) + #"""}"#)
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(large.utf8))) { error in
            XCTAssertEqual(error as? PhoneRemoteOperationsError, .inputTooLarge)
        }
        let depth65 = #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"x":"# + String(repeating: "[", count: 63) + "0" + String(repeating: "]", count: 63) + "}}"
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(depth65.utf8))) { error in
            XCTAssertEqual(error as? PhoneRemoteOperationsError, .nestingTooDeep)
        }
        let depth64 = #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"x":"# + String(repeating: "[", count: 62) + "0" + String(repeating: "]", count: 62) + "}}"
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(depth64.utf8))) { error in
            XCTAssertNotEqual(error as? PhoneRemoteOperationsError, .nestingTooDeep)
        } // depth is accepted; the closed payload schema then rejects the unknown field.
    }

    func testSuccessPayloadMustMatchOperationAndExactSchema() throws {
        let valid: [(PhoneRemoteOperation, String)] = [
            (.sessionStatus, #"{"readiness":"ready"}"#),
            (.voiceOffer, #"{"peer_id":"p","sdp":"answer"}"#),
            (.voiceUpdate, #"{"peer_id":"p","sdp":"answer"}"#),
            (.voiceEnd, #"{"peer_id":"p","ended":true}"#),
        ]
        for (operation, payload) in valid {
            let data = Data(response(status: "ok", reason: "none", payload: payload).utf8)
            let decoded = try PhoneRemoteOperationsJSON.decodeResponse(from: data, for: operation)
            XCTAssertEqual(decoded.requestID, "rid")
            let encoded = try JSONEncoder().encode(decoded)
            XCTAssertEqual(try PhoneRemoteOperationsJSON.decodeResponse(from: encoded, for: operation), decoded)
        }
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(response(status: "ok", reason: "none", payload: #"{"readiness":"ready"}"#).utf8), for: .voiceOffer))
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(response(status: "ok", reason: "none", payload: #"{"peer_id":"p","ended":1}"#).utf8), for: .voiceEnd))
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(response(status: "ok", reason: "none", payload: #"{"peer_id":"p","ended":false}"#).utf8), for: .voiceEnd))
    }

    func testEveryStatusReasonPairingMatchesR39Allowlist() throws {
        let valid: [PhoneRemoteStatus: Set<PhoneRemoteOperationReason>] = [
            .ok: [.none],
            .denied: [.malformedRequest, .notAuthorized, .requestConflict, .requestCapacity],
            .unavailable: [.featureOff, .authorityUnavailable, .voiceNotReady, .ownerBusy, .operationUnavailable],
            .incompatible: [.unsupportedProtocol],
        ]
        for status in PhoneRemoteStatus.allCases {
            for reason in PhoneRemoteOperationReason.allCases {
                let payload: PhoneRemoteOperationResponse.Payload = status == .ok ? .sessionStatus(readiness: "ready") : .empty
                let accepted: Bool
                do {
                    _ = try PhoneRemoteOperationResponse(requestID: "r", operation: .sessionStatus, status: status, reason: reason, payload: payload)
                    accepted = true
                } catch {
                    accepted = false
                }
                XCTAssertEqual(accepted, valid[status, default: []].contains(reason), "\(status.rawValue)/\(reason.rawValue)")
            }
        }
    }

    func testErrorsHaveExactlyEmptyPayloadAndNoPrivateData() throws {
        let reasons: [(String, String)] = [
            ("denied", "not_authorized"), ("unavailable", "voice_not_ready"), ("incompatible", "unsupported_protocol"),
        ]
        for (status, reason) in reasons {
            let json = response(status: status, reason: reason, payload: "{}")
            let response = try PhoneRemoteOperationsJSON.decodeResponse(from: Data(json.utf8), for: .voiceOffer)
            XCTAssertEqual(response.payload, .empty)
            let encoded = try PhoneRemoteOperationsJSON.encodeResponse(response, for: .voiceOffer)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
            XCTAssertEqual((object["payload"] as? [String: Any])?.count, 0)
            XCTAssertEqual(Set(object.keys), ["request_id", "status", "reason", "payload"])
        }
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(response(status: "denied", reason: "not_authorized", payload: #"{"detail":"private"}"#).utf8), for: .voiceOffer))
    }

    func testResponseEnvelopeDuplicateUnknownAndRequestIDLimits() {
        let bad = [
            #"{"request_id":"r","request_id":"x","status":"denied","reason":"not_authorized","payload":{}}"#,
            #"{"request_id":"r","status":"denied","reason":"not_authorized","payload":{},"extra":true}"#,
            response(status: "denied", reason: "not_authorized", payload: "{}", rid: ""),
            response(status: "denied", reason: "not_authorized", payload: "{}", rid: String(repeating: "x", count: 129)),
        ]
        for json in bad {
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(json.utf8), for: .voiceEnd))
        }
        let reservedOperationError = response(status: "unavailable", reason: "operation_unavailable", payload: "{}")
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: Data(reservedOperationError.utf8), for: .callAnswer))
        XCTAssertThrowsError(try PhoneRemoteOperationResponse(requestID: "r", operation: .callAnswer, status: .unavailable, reason: .operationUnavailable, payload: .empty))
    }

    func testFakeHostExchangesCheckedBytesForAllFourOperations() throws {
        let host = FakePhoneRemoteOperationsHost { requestBytes in
            let request = try PhoneRemoteOperationsJSON.decodeRequest(from: requestBytes)
            let response: PhoneRemoteOperationResponse
            switch request.payload {
            case .sessionStatus:
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: .sessionStatus, status: .ok, reason: .none, payload: .sessionStatus(readiness: "ready"))
            case .voiceOffer:
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: .voiceOffer, status: .ok, reason: .none, payload: .voiceOffer(peerID: "offer-peer", sdp: "offer-answer"))
            case .voiceUpdate(let peerID, _):
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: .voiceUpdate, status: .ok, reason: .none, payload: .voiceUpdate(peerID: peerID, sdp: "update-answer"))
            case .voiceEnd(let peerID):
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: .voiceEnd, status: .ok, reason: .none, payload: .voiceEnd(peerID: peerID, ended: true))
            }
            return try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
        }
        let cases: [(PhoneRemoteOperationRequest.Payload, PhoneRemoteOperation, PhoneRemoteOperationResponse.Payload)] = [
            (.sessionStatus, .sessionStatus, .sessionStatus(readiness: "ready")),
            (.voiceOffer(sdp: "synthetic-offer"), .voiceOffer, .voiceOffer(peerID: "offer-peer", sdp: "offer-answer")),
            (.voiceUpdate(peerID: "update-peer", sdp: "synthetic-update"), .voiceUpdate, .voiceUpdate(peerID: "update-peer", sdp: "update-answer")),
            (.voiceEnd(peerID: "end-peer"), .voiceEnd, .voiceEnd(peerID: "end-peer", ended: true)),
        ]
        for (index, item) in cases.enumerated() {
            let request = try PhoneRemoteOperationRequest(requestID: "request-\(index)", payload: item.0)
            let response = try host.send(request)
            XCTAssertEqual(request.operation, item.1)
            XCTAssertEqual(response.requestID, request.requestID)
            XCTAssertEqual(response.status, .ok)
            XCTAssertEqual(response.reason, .none)
            XCTAssertEqual(response.payload, item.2)
        }
    }

    func testFakeHostRejectsMismatchedRequestIDCorrelation() throws {
        let host = FakePhoneRemoteOperationsHost { requestBytes in
            let request = try PhoneRemoteOperationsJSON.decodeRequest(from: requestBytes)
            let response = try PhoneRemoteOperationResponse(requestID: "other", operation: request.operation, status: .unavailable, reason: .voiceNotReady, payload: .empty)
            return try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
        }
        let request = try PhoneRemoteOperationRequest(requestID: "rid", payload: .voiceOffer(sdp: "synthetic"))
        XCTAssertThrowsError(try host.send(request)) { error in
            XCTAssertEqual(error as? PhoneRemoteOperationsError, .requestIDMismatch)
        }
    }

    func testFakeHostCorrelatesRequestIDByExactUTF8Bytes() throws {
        let composed = "\u{00E9}"
        let decomposed = "e\u{0301}"
        XCTAssertEqual(composed, decomposed) // Swift String equality is canonically equivalent.
        XCTAssertFalse(composed.utf8.elementsEqual(decomposed.utf8))

        let matchingHost = FakePhoneRemoteOperationsHost { requestBytes in
            let request = try PhoneRemoteOperationsJSON.decodeRequest(from: requestBytes)
            let response = try PhoneRemoteOperationResponse(
                requestID: request.requestID, operation: request.operation,
                status: .ok, reason: .none, payload: .voiceOffer(peerID: "peer", sdp: "answer")
            )
            return try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
        }
        let request = try PhoneRemoteOperationRequest(requestID: composed, payload: .voiceOffer(sdp: "offer"))
        XCTAssertEqual(try matchingHost.send(request).requestID.utf8.elementsEqual(composed.utf8), true)

        let byteDifferentHost = FakePhoneRemoteOperationsHost { requestBytes in
            let decoded = try PhoneRemoteOperationsJSON.decodeRequest(from: requestBytes)
            let response = try PhoneRemoteOperationResponse(
                requestID: decomposed, operation: decoded.operation,
                status: .ok, reason: .none, payload: .voiceOffer(peerID: "peer", sdp: "answer")
            )
            return try PhoneRemoteOperationsJSON.encodeResponse(response, for: decoded.operation)
        }
        XCTAssertThrowsError(try byteDifferentHost.send(request)) { error in
            XCTAssertEqual(error as? PhoneRemoteOperationsError, .requestIDMismatch)
        }
    }

    private func envelope(op: String, rid: String = "rid", payload: String) -> String {
        #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"\#(rid)","operation":"\#(op)","payload":\#(payload)}"#
    }

    private func response(status: String, reason: String, payload: String, rid: String = "rid") -> String {
        #"{"request_id":"\#(rid)","status":"\#(status)","reason":"\#(reason)","payload":\#(payload)}"#
    }
}
