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
            "results.snapshot", "results.resume", "results.view", "results.select", "results.pin",
            "results.unpin", "results.close", "results.reopen", "call.state", "call.answer", "call.decline",
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

    func testAdoptedRequestShapeUsesLiteralProtocolKindAndVersion() throws {
        let fixture = #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"label":"x","count":1}}"#
        let request = try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<Fixture>.self, from: Data(fixture.utf8))
        XCTAssertEqual(request.kind, "mortimer.phone-remote.v1")
        XCTAssertEqual(request.protocolVersion, 1)
        XCTAssertEqual(request.requestID, "r")
        XCTAssertEqual(request.operation, .sessionStatus)
        XCTAssertEqual(request.payload, Fixture(label: "x", count: 1))
    }

    func testUnknownKindVersionOperationAndExtraEnvelopeKeysAreRejected() {
        let cases = [
            #"{"kind":"other","protocol_version":1,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":2,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.unknown","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{},"extra":true}"#,
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<[String: String]>.self, from: Data(json.utf8)))
        }
    }

    func testAdoptedResponseShapeHasOnlyItsFourContractFields() throws {
        let fixture = #"{"request_id":"r","status":"unavailable","reason":"opaque-fixture","payload":{"label":"x","count":1}}"#
        let response = try PhoneRemoteJSON.decodeResponse(PhoneRemoteResponse<Fixture, String>.self, from: Data(fixture.utf8))
        XCTAssertEqual(response.requestID, "r")
        XCTAssertEqual(response.status, .unavailable)
        XCTAssertEqual(response.reason, "opaque-fixture")
        XCTAssertEqual(response.payload, Fixture(label: "x", count: 1))
        let encoded = try JSONEncoder().encode(response)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        XCTAssertEqual(Set(object.keys), ["request_id", "status", "reason", "payload"])
        XCTAssertThrowsError(try PhoneRemoteJSON.decodeResponse(PhoneRemoteResponse<Fixture, String>.self, from: Data(#"{"request_id":"r","status":"ok","reason":"x","payload":{"label":"x","count":1},"kind":"mortimer.phone-remote.v1"}"#.utf8)))
    }

    func testDuplicateEnvelopeKeysIncludingEscapedEquivalentAreRejected() {
        let cases = [
            #"{"kind":"mortimer.phone-remote.v1","kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","request_id":"stale","operation":"session.status","payload":{}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"x":1,"x":2}}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{},"ki\u006ed":"mortimer.phone-remote.v1"}"#,
            #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":{"snowman ☃":1,"snowman \u2603":2}}"#,
        ]
        for json in cases {
            XCTAssertThrowsError(try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<[String: String]>.self, from: Data(json.utf8)))
        }
        let duplicateResponse = #"{"request_id":"r","request_id":"stale","status":"denied","reason":"fixture","payload":{"label":"x","count":1}}"#
        XCTAssertThrowsError(try PhoneRemoteJSON.decodeResponse(PhoneRemoteResponse<Fixture, String>.self, from: Data(duplicateResponse.utf8)))
    }

    func testEscapeCharactersInPayloadStringsDoNotConfuseDuplicateScan() throws {
        let fixture = #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":"brace } bracket ] quote \" key {\"kind\":1} snowman \u2603"}"#
        let decoded = try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<String>.self, from: Data(fixture.utf8))
        XCTAssertTrue(decoded.payload.contains("snowman ☃"))
    }

    func testDeeplyNestedPayloadIsRejectedInChildProcessWithoutTerminatingIt() throws {
        if ProcessInfo.processInfo.environment["MORTIMER_DEEP_JSON_CHILD"] == "1" {
            let deepPayload = String(repeating: "[", count: 100_000) + "0" + String(repeating: "]", count: 100_000)
            let prefix = #"{"kind":"mortimer.phone-remote.v1","protocol_version":1,"request_id":"r","operation":"session.status","payload":"#
            let json = prefix + deepPayload + "}"
            XCTAssertThrowsError(try PhoneRemoteJSON.decodeRequest(PhoneRemoteRequest<String>.self, from: Data(json.utf8)))
            return
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/xcrun")
        process.arguments = [
            "xctest",
            "-XCTest",
            "MortimerPhoneCoreTests.PhoneRemoteProtocolTests/testDeeplyNestedPayloadIsRejectedInChildProcessWithoutTerminatingIt",
            Bundle(for: type(of: self)).bundleURL.path,
        ]
        var environment = ProcessInfo.processInfo.environment
        environment["MORTIMER_DEEP_JSON_CHILD"] = "1"
        process.environment = environment
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        try process.run()
        process.waitUntilExit()
        XCTAssertEqual(process.terminationReason, .exit)
        XCTAssertEqual(process.terminationStatus, 0, "deep input must throw in the child instead of crashing")
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
