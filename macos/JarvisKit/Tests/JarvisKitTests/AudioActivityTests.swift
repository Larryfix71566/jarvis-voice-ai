import XCTest
@testable import JarvisKit

final class AudioActivityTests: XCTestCase {
    func testSilenceIsDistinctFromMissingAndExpiresWithoutCallbacks() {
        let id = UUID(); var activity = AudioActivityAccumulator(generation: id)
        activity.setMicrophoneEligible(true, at: 10)
        XCTAssertNil(activity.snapshot(at: 10).userLevel)
        XCTAssertTrue(activity.observe(.processedInput, level: 0, measuredAt: 10, now: 10, generation: id))
        XCTAssertEqual(activity.snapshot(at: 10.1).userLevel, 0)
        XCTAssertNil(activity.snapshot(at: 10.31).userLevel)
    }

    func testMuteClearsInputImmediatelyAndDoesNotSuppressPlayout() {
        let id = UUID(); var activity = AudioActivityAccumulator(generation: id)
        activity.setMicrophoneEligible(true, at: 10)
        activity.observe(.processedInput, level: 0.7, measuredAt: 10, now: 10, generation: id)
        activity.observe(.actualPlayout, level: 0.4, measuredAt: 10, now: 10, generation: id)
        activity.setMicrophoneEligible(false, at: 10.01)
        XCTAssertNil(activity.snapshot(at: 10.01).userLevel)
        XCTAssertEqual(activity.snapshot(at: 10.01).outputLevel, 0.4)
        XCTAssertFalse(activity.observe(.processedInput, level: 0.8, measuredAt: 10.02, now: 10.02, generation: id))
        activity.setMicrophoneEligible(true, at: 10.03)
        XCTAssertFalse(activity.observe(.processedInput, level: 0.9, measuredAt: 10.025, now: 10.04, generation: id))
        XCTAssertNil(activity.snapshot(at: 10.03).userLevel)
        XCTAssertFalse(activity.observe(.processedInput, level: 0.8, measuredAt: 10.02, now: 10.03, generation: id))
    }

    func testDuplicatesCannotExtendFreshnessAndResetRejectsOldSession() {
        let id = UUID(); var activity = AudioActivityAccumulator(generation: id)
        activity.observe(.actualPlayout, level: 0.4, measuredAt: 10, now: 10, generation: id)
        XCTAssertFalse(activity.observe(.actualPlayout, level: 0.8, measuredAt: 10, now: 10.2, generation: id))
        XCTAssertFalse(activity.observe(.actualPlayout, level: 0.8, measuredAt: 9.9, now: 10.1, generation: id))
        XCTAssertNil(activity.snapshot(at: 10.31).outputLevel)
        activity.reset(generation: UUID())
        XCTAssertFalse(activity.observe(.actualPlayout, level: 0.8, measuredAt: 10.32, now: 10.32, generation: id))
        XCTAssertNil(activity.snapshot(at: 10.32).outputLevel)
        XCTAssertFalse(activity.snapshot(at: 10.32).microphoneEligible)
    }

    func testMalformedFutureAndAlreadyStaleSamplesNeverBecomeValid() {
        let id = UUID(); var activity = AudioActivityAccumulator(generation: id)
        for level in [Double.nan, .infinity, -0.1, 1.1] {
            XCTAssertFalse(activity.observe(.actualPlayout, level: level, measuredAt: 10, now: 10, generation: id))
        }
        for time in [Double.nan, .infinity, 11, 9] {
            XCTAssertFalse(activity.observe(.actualPlayout, level: 0.5, measuredAt: time, now: 10, generation: id))
        }
        XCTAssertNil(activity.snapshot(at: 10).outputLevel)
    }
}
