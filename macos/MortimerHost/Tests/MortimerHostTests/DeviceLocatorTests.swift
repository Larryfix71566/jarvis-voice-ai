import XCTest
import CoreLocation
import JarvisKit
@testable import MortimerHost

/// MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 2 D4 (D-L6): the pure half of
/// DeviceLocator. CoreLocation itself is exercised in the end-of-project
/// live check ("where am I" on the Mac).
final class DeviceLocatorTests: XCTestCase {
    func testAuthorizationMapping() {
        XCTAssertEqual(DeviceLocationReply.authorization(.authorizedAlways), .authorized)
        XCTAssertEqual(DeviceLocationReply.authorization(.notDetermined), .notDetermined)
        XCTAssertEqual(DeviceLocationReply.authorization(.denied), .denied)
        XCTAssertEqual(DeviceLocationReply.authorization(.restricted), .restricted)
    }

    func testDeniedErrorIsDenied() {
        XCTAssertEqual(DeviceLocationReply.failure(for: CLError(.denied)), .denied)
    }

    func testOtherErrorsAreUnavailable() {
        XCTAssertEqual(DeviceLocationReply.failure(for: CLError(.locationUnknown)), .unavailable)
        XCTAssertEqual(DeviceLocationReply.failure(for: CLError(.network)), .unavailable)
        XCTAssertEqual(DeviceLocationReply.failure(for: URLError(.notConnectedToInternet)), .unavailable)
    }

    func testResultCarriesAccuracyAndAge() {
        let fixTime = Date(timeIntervalSince1970: 1_790_000_000)
        let location = CLLocation(coordinate: CLLocationCoordinate2D(latitude: 34.0754, longitude: -84.2941),
                                  altitude: 0, horizontalAccuracy: 65, verticalAccuracy: -1,
                                  timestamp: fixTime)
        let result = DeviceLocationReply.result(requestID: "5f2c", location: location,
                                                label: "Alpharetta, GA",
                                                now: fixTime.addingTimeInterval(4))
        XCTAssertTrue(result.ok)
        XCTAssertEqual(result.requestID, "5f2c")
        XCTAssertEqual(result.lat ?? 0, 34.0754, accuracy: 1e-9)
        XCTAssertEqual(result.lon ?? 0, -84.2941, accuracy: 1e-9)
        XCTAssertEqual(result.accuracyM, 65)
        XCTAssertEqual(result.ageS, 4)
        XCTAssertEqual(result.label, "Alpharetta, GA")
    }

    func testLabelJoinsWhatIsKnown() {
        XCTAssertEqual(DeviceLocationReply.label(locality: "Alpharetta", administrativeArea: "GA"), "Alpharetta, GA")
        XCTAssertEqual(DeviceLocationReply.label(locality: nil, administrativeArea: "GA"), "GA")
        XCTAssertEqual(DeviceLocationReply.label(locality: "  ", administrativeArea: nil), nil)
    }
}
