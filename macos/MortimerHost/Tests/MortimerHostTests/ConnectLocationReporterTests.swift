import XCTest
import CoreLocation
import JarvisKit
@testable import MortimerHost

/// 2026-11-19 (WS-15 follow-up): the app posts the device's own fix to the
/// sidecar on connect and on a timer, so the weather chip names the
/// device's city instead of weather.gov's nearest place for an IP guess.
/// CoreLocation and the permission prompt are a live Mac check.
@MainActor
final class ConnectLocationReporterTests: XCTestCase {
    private struct Stop: Error {}

    private final class Calls {
        var fixes = 0
        var reports: [(Double, Double, String)] = []
        var sleeps: [TimeInterval] = []
    }

    private func reporter(_ calls: Calls,
                          results: [LocationResult?],
                          sleepsBeforeStop: Int = 0) -> ConnectLocationReporter {
        var queue = results
        return ConnectLocationReporter(
            fix: {
                calls.fixes += 1
                return queue.isEmpty ? nil : queue.removeFirst()
            },
            report: { lat, lon, label in calls.reports.append((lat, lon, label)) },
            sleep: { interval in
                calls.sleeps.append(interval)
                if calls.sleeps.count > sleepsBeforeStop { throw Stop() }
            })
    }

    private func alpharetta(label: String? = "Alpharetta, GA") -> LocationResult {
        .fix(requestID: "connect-1", lat: 34.0754, lon: -84.2941,
             accuracyM: 65, ageS: 2, label: label)
    }

    func testConnectPostsOneFixWithTheDeviceLabel() async {
        let calls = Calls()
        let sut = reporter(calls, results: [alpharetta()])
        sut.start()
        await sut.loopTask?.value
        XCTAssertEqual(calls.fixes, 1)
        XCTAssertEqual(calls.reports.count, 1)
        XCTAssertEqual(calls.reports.first?.0 ?? 0, 34.0754, accuracy: 1e-9)
        XCTAssertEqual(calls.reports.first?.1 ?? 0, -84.2941, accuracy: 1e-9)
        XCTAssertEqual(calls.reports.first?.2, "Alpharetta, GA")
    }

    func testRefreshesOnTheIntervalUntilStopped() async {
        let calls = Calls()
        let sut = reporter(calls, results: [alpharetta(), alpharetta()], sleepsBeforeStop: 1)
        sut.start()
        await sut.loopTask?.value
        XCTAssertEqual(calls.fixes, 2)
        XCTAssertEqual(calls.reports.count, 2)
        XCTAssertEqual(calls.sleeps, [ConnectLocationReporter.refreshInterval,
                                      ConnectLocationReporter.refreshInterval])
    }

    func testIntervalIsShorterThanTheSidecarsOneHourKeep() {
        // jarvis/ambient_weather.py DEVICE_LOCATION_MAX_AGE_S = 3600.
        XCTAssertLessThan(ConnectLocationReporter.refreshInterval, 3600)
        XCTAssertGreaterThan(ConnectLocationReporter.refreshInterval, 60)
    }

    func testNothingIsPostedWhenLocationIsNotAllowed() async {
        let calls = Calls()
        let sut = reporter(calls, results: [nil])
        sut.start()
        await sut.loopTask?.value
        XCTAssertEqual(calls.fixes, 1)
        XCTAssertTrue(calls.reports.isEmpty)
    }

    func testAFailedFixPostsNothing() async {
        let calls = Calls()
        let sut = reporter(calls, results: [.failure(requestID: "connect-1", .denied)])
        sut.start()
        await sut.loopTask?.value
        XCTAssertTrue(calls.reports.isEmpty)
    }

    func testAMissingLabelPostsAnEmptyLabel() async {
        let calls = Calls()
        let sut = reporter(calls, results: [alpharetta(label: nil)])
        sut.start()
        await sut.loopTask?.value
        XCTAssertEqual(calls.reports.first?.2, "")
    }

    func testRefreshNowIsIgnoredUntilStartedAndAfterStop() async {
        let calls = Calls()
        let sut = reporter(calls, results: [alpharetta(), alpharetta()])
        XCTAssertNil(sut.refreshNow())
        XCTAssertFalse(sut.isRunning)
        sut.start()
        await sut.loopTask?.value
        // The fake sleep ended the loop, but the reporter is still started
        // until stop(): an allowed prompt then asks for one more fix.
        let extra = sut.refreshNow()
        XCTAssertNotNil(extra)
        await extra?.value
        XCTAssertEqual(calls.reports.count, 2)
        sut.stop()
        XCTAssertFalse(sut.isRunning)
        XCTAssertNil(sut.refreshNow())
    }

    func testAllowsFixOnlyOnceLocationServicesAllowsIt() {
        XCTAssertFalse(DeviceLocator.allowsFix(.notDetermined))
        XCTAssertFalse(DeviceLocator.allowsFix(.denied))
        XCTAssertFalse(DeviceLocator.allowsFix(.restricted))
        XCTAssertTrue(DeviceLocator.allowsFix(.authorizedAlways))
    }
}
