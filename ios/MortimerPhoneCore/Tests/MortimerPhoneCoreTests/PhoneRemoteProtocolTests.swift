import Foundation
import XCTest
@testable import MortimerPhoneCore

final class PhoneRemoteProtocolTests: XCTestCase {
    private struct Fixture: Codable, Equatable, Sendable {
        let label: String
        let count: Int
    }

    func testExactOperationsAndStatuses() {
        XCTAssertEqual(PhoneRemoteOperation.allCases.map(\.rawValue), [
            "session.status", "voice.offer", "voice.update", "voice.end",
            "results.snapshot", "results.resume", "call.state", "call.answer", "call.decline",
        ])
        XCTAssertEqual(PhoneRemoteStatus.allCases.map(\.rawValue), ["ok", "denied", "unavailable", "incompatible"])
    }

    func testGenericRequestAndResponsePayloadRoundTrip() throws {
        let request = PhoneRemoteRequest(requestID: "fixture-1", operation: .sessionStatus, payload: Fixture(label: "typed", count: 7))
        let requestData = try JSONEncoder().encode(request)
        let decodedRequest = try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<Fixture>.self, from: requestData)
        XCTAssertEqual(decodedRequest.requestID, request.requestID)
        XCTAssertEqual(decodedRequest.operation, request.operation)
        XCTAssertEqual(decodedRequest.payload, request.payload)

        let response = PhoneRemoteResponse(requestID: "fixture-1", status: .ok, reason: "fixture-reason", payload: Fixture(label: "admitted", count: 9))
        let responseData = try JSONEncoder().encode(response)
        let decodedResponse = try PhoneRemoteJSON.decodeResponse(PhoneRemoteResponse<Fixture, String>.self, from: responseData)
        XCTAssertEqual(decodedResponse.requestID, response.requestID)
        XCTAssertEqual(decodedResponse.status, response.status)
        XCTAssertEqual(decodedResponse.reason, response.reason)
        XCTAssertEqual(decodedResponse.payload, response.payload)
    }

    func testUnknownKindVersionOperationAndExtraEnvelopeKeysAreRejected() {
        let cases = [
            #"{"kind":"other","protocol_version":1,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"request","protocol_version":2,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"request","protocol_version":1,"request_id":"r","operation":"session.unknown","payload":{}}"#,
            #"{"kind":"request","protocol_version":1,"request_id":"r","operation":"session.status","payload":{},"extra":true}"#,
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<[String: String]>.self, from: Data(json.utf8)))
        }
    }

    func testDuplicateEnvelopeKeysIncludingEscapedEquivalentAreRejected() {
        let cases = [
            #"{"kind":"request","kind":"request","protocol_version":1,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"request","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"x":1,"x":2}}"#,
            #"{"kind":"request","protocol_version":1,"request_id":"r","operation":"session.status","payload":{},"ki\u006ed":"request"}"#,
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<[String: String]>.self, from: Data(json.utf8)))
        }
    }

    func testFakeHostIsInjectedDeterministicAndFailsClosedByDefaultFixture() {
        let host = FakePhoneRemoteHost<Fixture, String> { operation in
            switch operation {
            case .sessionStatus: .init(status: .ok, reason: "fixture")
            default: .init(status: .unavailable, reason: "fixture")
            }
        }
        let payload = Fixture(label: "opaque-fixture", count: 1)
        let request = PhoneRemoteRequest(requestID: "same-id", operation: .sessionStatus, payload: payload)
        XCTAssertEqual(host.send(request).requestID, host.send(request).requestID)
        XCTAssertEqual(host.send(request).status, host.send(request).status)
        XCTAssertEqual(host.send(request).reason, host.send(request).reason)
        XCTAssertEqual(host.send(request).payload, payload)
        for operation in [PhoneRemoteOperation.voiceOffer, .voiceUpdate, .voiceEnd, .resultsSnapshot, .resultsResume, .callState, .callAnswer, .callDecline] {
            let response = host.send(PhoneRemoteRequest(requestID: "r", operation: operation, payload: payload))
            XCTAssertEqual(response.status, .unavailable, "\(operation.rawValue) remains an unavailable fixture")
        }
    }
}
