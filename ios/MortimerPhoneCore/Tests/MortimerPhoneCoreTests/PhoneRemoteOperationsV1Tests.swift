import Foundation
import XCTest
@testable import MortimerPhoneCore

final class PhoneRemoteOperationsV1Tests: XCTestCase {
    func testSixClosedRequestSchemasRoundTripThroughCheckedBoundary() throws {
        let cases: [(PhoneRemoteOperationRequest.Payload, PhoneRemoteOperation, Set<String>)] = [
            (.sessionStatus, .sessionStatus, []),
            (.voiceOffer(sdp: "offer-canary"), .voiceOffer, ["sdp"]),
            (.voiceUpdate(peerID: "peer-canary", sdp: "update-canary"), .voiceUpdate, ["peer_id", "sdp"]),
            (.voiceEnd(peerID: "peer-canary"), .voiceEnd, ["peer_id"]),
            (.resultsSnapshot, .resultsSnapshot, []),
            (.resultsResume(cursor: String(repeating: "A", count: 43)), .resultsResume, ["cursor"]),
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
            envelope(op: "results.snapshot", payload: #"{"cursor":"unexpected"}"#),
            envelope(op: "results.resume", payload: #"{"cursor":"bad"}"#),
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
            (.resultsSnapshot, resultsSnapshotJSON()),
            (.resultsResume, resultsPageJSON()),
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

    func testFakeHostExchangesCheckedBytesForAllSixOperations() throws {
        let sampleSnapshot = snapshot()
        let samplePage = page()
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
            case .resultsSnapshot:
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsSnapshot, status: .ok, reason: .none, payload: .resultsSnapshot(sampleSnapshot))
            case .resultsResume:
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: .resultsResume, status: .ok, reason: .none, payload: .resultsResume(samplePage))
            case .resultsView, .resultCard:
                response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: request.operation, status: .ok, reason: .none, payload: .resultCardView(cardViewFixture()))
            }
            return try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
        }
        let cases: [(PhoneRemoteOperationRequest.Payload, PhoneRemoteOperation, PhoneRemoteOperationResponse.Payload)] = [
            (.sessionStatus, .sessionStatus, .sessionStatus(readiness: "ready")),
            (.voiceOffer(sdp: "synthetic-offer"), .voiceOffer, .voiceOffer(peerID: "offer-peer", sdp: "offer-answer")),
            (.voiceUpdate(peerID: "update-peer", sdp: "synthetic-update"), .voiceUpdate, .voiceUpdate(peerID: "update-peer", sdp: "update-answer")),
            (.voiceEnd(peerID: "end-peer"), .voiceEnd, .voiceEnd(peerID: "end-peer", ended: true)),
            (.resultsSnapshot, .resultsSnapshot, .resultsSnapshot(sampleSnapshot)),
            (.resultsResume(cursor: String(repeating: "A", count: 43)), .resultsResume, .resultsResume(samplePage)),
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

    func testResultsDTOsRejectGapsDuplicatesAndHiddenMetadata() throws {
        let item = resultItem()
        let invalidItems = [
            #"[{"result_id":"00000000-0000-0000-0000-000000000001","revision":1,"source":{"kind":"synthetic.workspace_result.v1","id":"00000000-0000-0000-0000-000000000001","revision":1},"classification":"protected","title":"x","body":"y","received_at_ms":1}]"#,
            #"[{"result_id":"00000000-0000-0000-0000-000000000001","revision":1,"source":{"kind":"synthetic.workspace_result.v1","id":"00000000-0000-0000-0000-000000000002","revision":1},"classification":"ordinary","title":"x","body":"y","received_at_ms":1}]"#,
        ]
        for items in invalidItems {
            let json = #"{"generation":"00000000-0000-0000-0000-000000000201","collection_epoch":"00000000-0000-0000-0000-000000000301","content_watermark":1,"cursor":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","items":"# + items + "}"
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(
                from: Data(response(status: "ok", reason: "none", payload: json).utf8), for: .resultsSnapshot))
        }
        let gap = #"{"generation":"00000000-0000-0000-0000-000000000201","collection_epoch":"00000000-0000-0000-0000-000000000301","content_watermark":3,"reset_required":false,"has_more":false,"cursor":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","events":[{"sequence":1,"kind":"upsert","item":"# + resultItemJSON(item) + #"},{"sequence":3,"kind":"upsert","item":"# + resultItemJSON(item) + #"}]}"#
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(
            from: Data(response(status: "ok", reason: "none", payload: gap).utf8), for: .resultsResume))
        let good = try PhoneRemoteOperationsJSON.decodeResponse(
            from: Data(response(status: "ok", reason: "none", payload: resultsPageJSON()).utf8), for: .resultsResume)
        XCTAssertEqual(good.operation, .resultsResume)
    }

    func testResultsNumbersAndCursorTokensRequireCanonicalWireForms() throws {
        let floatWatermark = #"{"request_id":"rid","status":"ok","reason":"none","payload":{"generation":"00000000-0000-0000-0000-000000000201","collection_epoch":"00000000-0000-0000-0000-000000000301","content_watermark":10.0,"cursor":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","items":[]}}"#
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(
            from: Data(floatWatermark.utf8), for: .resultsSnapshot))
        let noncanonical = String(repeating: "A", count: 42) + "B"
        XCTAssertThrowsError(try PhoneRemoteOperationRequest(requestID: "r",
            payload: .resultsResume(cursor: noncanonical)))
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(
            from: Data(resultsSnapshotJSON().replacingOccurrences(
                of: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", with: noncanonical).utf8),
            for: .resultsSnapshot))
    }

    func testMaximumSequenceCannotOverflowContiguityValidation() throws {
        let maximum = PhoneRemoteResultEvent(sequence: Int.max, item: resultItem())
        let afterMaximum = PhoneRemoteResultEvent(sequence: 1, item: resultItem())
        let invalid = PhoneRemoteResultsPage(generation: "00000000-0000-0000-0000-000000000201",
            collectionEpoch: "00000000-0000-0000-0000-000000000301", contentWatermark: Int.max,
            resetRequired: false, hasMore: false, cursor: String(repeating: "B", count: 42) + "A",
            events: [maximum, afterMaximum])
        XCTAssertThrowsError(try PhoneRemoteOperationResponse(requestID: "r", operation: .resultsResume,
            status: .ok, reason: .none, payload: .resultsResume(invalid)))
    }

    func testLargeVoiceResponseDoesNotUseResultsSpecificByteCap() throws {
        let response = try PhoneRemoteOperationResponse(requestID: "voice-large", operation: .voiceOffer,
            status: .ok, reason: .none,
            payload: .voiceOffer(peerID: "peer", sdp: String(repeating: "x", count: 600_000)))
        let bytes = try PhoneRemoteOperationsJSON.encodeResponse(response, for: .voiceOffer)
        XCTAssertGreaterThan(bytes.count, 512 * 1024)
        XCTAssertLessThan(bytes.count, PhoneRemoteOperationsJSON.maximumInputBytes)
    }

    private func resultItem() -> PhoneRemoteResultItem {
        PhoneRemoteResultItem(resultID: "00000000-0000-0000-0000-000000000001", revision: 1,
            sourceID: "00000000-0000-0000-0000-000000000001", sourceRevision: 1,
            title: "Synthetic", body: "Preview", receivedAtMilliseconds: 1_800_000_000_000)
    }

    private func snapshot() -> PhoneRemoteResultsSnapshot {
        PhoneRemoteResultsSnapshot(generation: "00000000-0000-0000-0000-000000000201",
            collectionEpoch: "00000000-0000-0000-0000-000000000301", contentWatermark: 1,
            cursor: String(repeating: "A", count: 43), items: [resultItem()])
    }

    private func page() -> PhoneRemoteResultsPage {
        PhoneRemoteResultsPage(generation: "00000000-0000-0000-0000-000000000201",
            collectionEpoch: "00000000-0000-0000-0000-000000000301", contentWatermark: 1,
            resetRequired: false, hasMore: false, cursor: String(repeating: "B", count: 42) + "A",
            events: [PhoneRemoteResultEvent(sequence: 1, item: resultItem())])
    }

    private func resultItemJSON(_ item: PhoneRemoteResultItem) -> String {
        #"{"result_id":"\#(item.resultID)","revision":\#(item.revision),"source":{"kind":"synthetic.workspace_result.v1","id":"\#(item.sourceID)","revision":\#(item.sourceRevision)},"classification":"ordinary","title":"\#(item.title)","body":"\#(item.body)","received_at_ms":\#(item.receivedAtMilliseconds)}"#
    }

    private func resultsSnapshotJSON() -> String {
        #"{"generation":"00000000-0000-0000-0000-000000000201","collection_epoch":"00000000-0000-0000-0000-000000000301","content_watermark":1,"cursor":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","items":["# + resultItemJSON(resultItem()) + "]}"
    }

    private func resultsPageJSON() -> String {
        #"{"generation":"00000000-0000-0000-0000-000000000201","collection_epoch":"00000000-0000-0000-0000-000000000301","content_watermark":1,"reset_required":false,"has_more":false,"cursor":"BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBA","events":[{"sequence":1,"kind":"upsert","item":"# + resultItemJSON(resultItem()) + "}]}"
    }

    private func envelope(op: String, rid: String = "rid", payload: String) -> String {
        #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"\#(rid)","operation":"\#(op)","payload":\#(payload)}"#
    }

    private func response(status: String, reason: String, payload: String, rid: String = "rid") -> String {
        #"{"request_id":"\#(rid)","status":"\#(status)","reason":"\#(reason)","payload":\#(payload)}"#
    }
}


func cardViewFixture(revision: Int = 0, resultRevision: Int = 1, open: Bool = true,
                     pinned: Bool = false, selected: Bool = false) -> PhoneResultCardView {
    let id = "00000000-0000-0000-0000-000000000101"
    return PhoneResultCardView(generation: "00000000-0000-0000-0000-000000000201",
        collectionEpoch: "00000000-0000-0000-0000-000000000301",
        viewID: "00000000-0000-0000-0000-000000000401", viewRevision: revision,
        selectedResultID: selected ? id : nil,
        allowedOperations: PhoneResultCardAction.allCases.sorted { $0.rawValue < $1.rawValue },
        cards: [PhoneResultCardState(resultID: id, resultRevision: resultRevision, open: open, pinned: pinned)])
}

extension PhoneRemoteOperationsV1Tests {
    func testCardOperationsRoundTripAndExactTypes() throws {
        let view = cardViewFixture()
        let payloads: [PhoneRemoteOperationRequest.Payload] = [.resultsView(generation: view.generation, collectionEpoch: view.collectionEpoch)]
            + PhoneResultCardAction.allCases.map { .resultCard($0, view.target(for: view.cards[0].resultID)!) }
        for payload in payloads {
            let request = try PhoneRemoteOperationRequest(requestID: "card-request", payload: payload)
            let bytes = try PhoneRemoteOperationsJSON.encodeRequest(request)
            XCTAssertEqual(try PhoneRemoteOperationsJSON.decodeRequest(from: bytes), request)
            XCTAssertEqual(try PhoneRemoteOperationsJSON.decodeRequest(from: JSONEncoder().encode(request)), request)
            let response = try PhoneRemoteOperationResponse(requestID: request.requestID, operation: request.operation,
                status: .ok, reason: .none, payload: .resultCardView(view))
            let encoded = try PhoneRemoteOperationsJSON.encodeResponse(response, for: request.operation)
            XCTAssertEqual(try PhoneRemoteOperationsJSON.decodeResponse(from: encoded, for: request.operation), response)
            XCTAssertEqual(try PhoneRemoteOperationsJSON.decodeResponse(from: JSONEncoder().encode(response), for: request.operation), response)
            if request.operation != .resultsView {
                let text = String(decoding: bytes, as: UTF8.self)
                for replacement in ["0.0", "true", "\"0\"", "-1"] {
                    let bad = text.replacingOccurrences(of: "\"view_revision\":0", with: "\"view_revision\":\(replacement)")
                    XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeRequest(from: Data(bad.utf8)))
                }
            }
        }
    }

    func testCardViewRejectsAmbiguousMetadataAndOversizeBytes() throws {
        let view = cardViewFixture()
        let response = try PhoneRemoteOperationResponse(requestID: "view", operation: .resultsView,
            status: .ok, reason: .none, payload: .resultCardView(view))
        let data = try PhoneRemoteOperationsJSON.encodeResponse(response, for: .resultsView)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let original = try XCTUnwrap(root["payload"] as? [String: Any])
        let card = try XCTUnwrap((original["cards"] as? [[String: Any]])?.first)
        var variants: [[String: Any]] = []
        for change in [["extra": true], ["view_revision": true], ["view_revision": -1],
                       ["selected_result_id": "00000000-0000-0000-0000-000000000999"],
                       ["allowed_operations": ["shell"]], ["allowed_operations": ["results.pin", "results.pin"]],
                       ["cards": [card, card]], ["cards": Array(repeating: card, count: 26)]] as [[String: Any]] {
            variants.append(original.merging(change) { _, new in new })
        }
        for change in [["open": false, "pinned": true], ["result_revision": true], ["open": 1], ["extra": "bad"]] as [[String: Any]] {
            variants.append(original.merging(["cards": [card.merging(change) { _, new in new }]]) { _, new in new })
        }
        var missing = original; missing.removeValue(forKey: "selected_result_id"); variants.append(missing)
        for payload in variants {
            let bad = try JSONSerialization.data(withJSONObject: root.merging(["payload": payload]) { _, new in new })
            XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: bad, for: .resultsView))
        }
        let padded = Data(repeating: 0x20, count: 16 * 1024) + data
        XCTAssertThrowsError(try PhoneRemoteOperationsJSON.decodeResponse(from: padded, for: .resultsView))
    }
}

extension PhoneRemoteOperationsV1Tests {
    func testCardErrorMatrixMatchesPythonAndExcludesVoiceReadiness() throws {
        for operation in [PhoneRemoteOperation.resultsView, .resultsSelect, .resultsPin, .resultsUnpin, .resultsClose, .resultsReopen] {
            let cases: [(PhoneRemoteStatus, [PhoneRemoteOperationReason])] = [
                (.denied, [.malformedRequest, .notAuthorized, .requestConflict, .requestCapacity]),
                (.unavailable, [.featureOff, .authorityUnavailable, .ownerBusy, .operationUnavailable]),
                (.incompatible, [.unsupportedProtocol])]
            for (status, reasons) in cases {
                for reason in reasons {
                    let response = try PhoneRemoteOperationResponse(requestID: "matrix", operation: operation,
                        status: status, reason: reason, payload: .empty)
                    let bytes = try PhoneRemoteOperationsJSON.encodeResponse(response, for: operation)
                    XCTAssertEqual(try PhoneRemoteOperationsJSON.decodeResponse(from: bytes, for: operation), response)
                }
            }
            XCTAssertThrowsError(try PhoneRemoteOperationResponse(requestID: "voice", operation: operation,
                status: .unavailable, reason: .voiceNotReady, payload: .empty))
        }
    }
}
