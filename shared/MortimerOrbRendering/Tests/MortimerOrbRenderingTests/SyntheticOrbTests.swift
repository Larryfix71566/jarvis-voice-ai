import XCTest
@testable import MortimerOrbRendering

final class SyntheticOrbTests: XCTestCase {
    func testSyntheticLevelsAreDeterministicAndBounded() {
        for step in 0...120 {
            let t = Double(step) / 15
            let frame = SyntheticOrbFrame(elapsed: t, reduceMotion: false)
            XCTAssertEqual(frame, SyntheticOrbFrame(elapsed: t, reduceMotion: false))
            XCTAssertTrue((0.19...0.35).contains(frame.level))
        }
        XCTAssertGreaterThan(SyntheticOrbFrame(elapsed: 1, reduceMotion: false).level,
                             SyntheticOrbFrame(elapsed: 3, reduceMotion: false).level)
    }

    func testReduceMotionAndInvalidTimeUseTheSameStill() {
        let still = SyntheticOrbFrame(elapsed: 0, reduceMotion: true)
        for t in [-1, 0, 62, .infinity, .nan] {
            XCTAssertEqual(SyntheticOrbFrame(elapsed: t, reduceMotion: true), still)
        }
        for t in [-1, .infinity, .nan] {
            XCTAssertEqual(SyntheticOrbFrame(elapsed: t, reduceMotion: false), still)
        }
    }

    func testEnergyIsStableForAnUnscheduledReducedMotionRedraw() {
        let energy = OrbEnergyState()
        energy.advance(activity: .assistant, measuredLevel: 0.34,
                       phase: 0, now: 1, dt: 0, reducedMotion: true)
        let initial = energy.depths
        energy.advance(activity: .assistant, measuredLevel: 0.34,
                       phase: 1, now: 1.05, dt: 0.05, reducedMotion: true)
        XCTAssertEqual(energy.depths, initial)
        energy.advance(activity: .assistant, measuredLevel: 0.34,
                       phase: 1, now: 1.11, dt: 0.06, reducedMotion: true)
        XCTAssertNotEqual(energy.depths, initial)
    }
}
