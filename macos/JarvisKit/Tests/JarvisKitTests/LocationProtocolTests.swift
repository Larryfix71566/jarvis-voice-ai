import XCTest
@testable import JarvisKit

/// MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 2 D4 (D-L6): the wire shapes the
/// bot's jarvis/bot/device_location.py sends and parses.
final class LocationProtocolTests: XCTestCase {
    private func object(_ message: ClientMessage) throws -> [String: Any] {
        try XCTUnwrap(try JSONSerialization.jsonObject(with: message.jsonData()) as? [String: Any])
    }

    func testDecodeLocationRequestFromRTVIEnvelope() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"location/request","version":1,"request_id":"5f2c","accuracy_m":100}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .locationRequest(let request) = message else { return XCTFail("expected .locationRequest") }
        XCTAssertEqual(request.requestID, "5f2c")
        XCTAssertEqual(request.accuracyM, 100)
    }

    func testHelloRawShape() throws {
        let obj = try object(.locationHello(LocationHello(authorization: .notDetermined)))
        XCTAssertEqual(obj["type"] as? String, "location/hello")
        XCTAssertEqual(obj["version"] as? Int, 1)
        XCTAssertEqual(obj["authorization"] as? String, "not_determined")
    }

    func testFixRawShape() throws {
        let result = LocationResult.fix(requestID: "5f2c", lat: 34.0754, lon: -84.2941,
                                        accuracyM: 65, ageS: 4, label: "Alpharetta, GA")
        let obj = try object(.locationResult(result))
        XCTAssertEqual(obj["type"] as? String, "location/result")
        XCTAssertEqual(obj["request_id"] as? String, "5f2c")
        XCTAssertEqual(obj["ok"] as? Bool, true)
        XCTAssertEqual(obj["lat"] as? Double, 34.0754)
        XCTAssertEqual(obj["lon"] as? Double, -84.2941)
        XCTAssertEqual(obj["accuracy_m"] as? Double, 65)
        XCTAssertEqual(obj["age_s"] as? Double, 4)
        XCTAssertEqual(obj["label"] as? String, "Alpharetta, GA")
        XCTAssertNil(obj["error"])
    }

    func testFailureRawShape() throws {
        let obj = try object(.locationResult(.failure(requestID: "5f2c", .denied)))
        XCTAssertEqual(obj["ok"] as? Bool, false)
        XCTAssertEqual(obj["error"] as? String, "denied")
        XCTAssertNil(obj["lat"])
    }

    func testNegativeAccuracyAndAgeAreClamped() {
        let result = LocationResult.fix(requestID: "x", lat: 0, lon: 0, accuracyM: -1, ageS: -3, label: nil)
        XCTAssertEqual(result.accuracyM, 0)
        XCTAssertEqual(result.ageS, 0)
    }
}
