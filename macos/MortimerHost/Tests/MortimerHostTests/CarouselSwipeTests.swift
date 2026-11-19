import XCTest
@testable import MortimerHost

final class CarouselSwipeTests: XCTestCase {
    private let w: CGFloat = 600

    func testOffsetFollowsFingerInsideRange() {
        XCTAssertEqual(CarouselSwipeModel.offset(translation: -120, index: 1, count: 3, width: w), -120)
        XCTAssertEqual(CarouselSwipeModel.offset(translation: 90, index: 1, count: 3, width: w), 90)
        XCTAssertEqual(CarouselSwipeModel.offset(translation: 0, index: 1, count: 3, width: w), 0)
    }

    func testRubberBandIsBoundedAtBothEnds() {
        let limit = CarouselSwipeModel.bandFraction * w
        for t in [10, 100, 600, 5000, 1_000_000] as [CGFloat] {
            let first = CarouselSwipeModel.offset(translation: t, index: 0, count: 3, width: w)
            XCTAssertGreaterThan(first, 0)
            XCTAssertLessThan(first, limit)
            let last = CarouselSwipeModel.offset(translation: -t, index: 2, count: 3, width: w)
            XCTAssertLessThan(last, 0)
            XCTAssertGreaterThan(last, -limit)
            XCTAssertLessThan(first, t)
        }
        XCTAssertEqual(CarouselSwipeModel.offset(translation: 50, index: 0, count: 1, width: w) > 0, true)
        XCTAssertEqual(CarouselSwipeModel.offset(translation: -50, index: 0, count: 1, width: w) < 0, true)
    }

    func testDecisionThresholds() {
        func d(_ t: CGFloat, v: CGFloat = 0, index: Int = 1) -> Int {
            CarouselSwipeModel.decision(translation: t, predictedEnd: t, velocity: v, index: index, count: 3, width: 100)
        }
        XCTAssertEqual(d(-27), 0)
        XCTAssertEqual(d(-28), 1)
        XCTAssertEqual(d(27), 0)
        XCTAssertEqual(d(28), -1)
    }

    func testFlickCommitsWithSmallTranslation() {
        func d(_ t: CGFloat, v: CGFloat) -> Int {
            CarouselSwipeModel.decision(translation: t, predictedEnd: t, velocity: v, index: 1, count: 3, width: 100)
        }
        XCTAssertEqual(d(-5, v: -600), 1)
        XCTAssertEqual(d(5, v: 600), -1)
        XCTAssertEqual(d(-5, v: 600), 0)
        XCTAssertEqual(d(-5, v: -499), 0)
    }

    func testDecisionNeverPassesTheEnds() {
        XCTAssertEqual(CarouselSwipeModel.decision(translation: 300, predictedEnd: 300, velocity: 900, index: 0, count: 3, width: 600), 0)
        XCTAssertEqual(CarouselSwipeModel.decision(translation: -300, predictedEnd: -300, velocity: -900, index: 2, count: 3, width: 600), 0)
        XCTAssertEqual(CarouselSwipeModel.decision(translation: -300, predictedEnd: -900, velocity: -2000, index: 0, count: 3, width: 600), 1)
        XCTAssertEqual(CarouselSwipeModel.decision(translation: -300, predictedEnd: -300, velocity: 0, index: 0, count: 1, width: 600), 0)
    }

    private func trackpad(_ acc: inout ScrollSwipeAccumulator, _ dx: CGFloat, _ dy: CGFloat,
                          _ phase: ScrollSwipePhase, momentum: Bool = false,
                          index: Int = 1, count: Int = 3) -> ScrollSwipeAccumulator.Output {
        acc.feed(deltaX: dx, deltaY: dy, phase: phase, momentum: momentum, precise: true,
                 timestamp: 0, index: index, count: count, width: 600)
    }

    func testAccumulatorIgnoresVerticalGestures() {
        var acc = ScrollSwipeAccumulator()
        _ = trackpad(&acc, 0, 0, .began)
        XCTAssertFalse(trackpad(&acc, 2, 14, .changed).claimed)
        XCTAssertFalse(trackpad(&acc, 40, 1, .changed).claimed)
        let end = trackpad(&acc, 0, 0, .ended)
        XCTAssertFalse(end.claimed)
        XCTAssertEqual(end.commit, 0)
    }

    func testAccumulatorClaimsHorizontalAndCommitsAtThreshold() {
        var acc = ScrollSwipeAccumulator()
        _ = trackpad(&acc, 0, 0, .began)
        XCTAssertFalse(trackpad(&acc, -6, 1, .changed).claimed)
        let claim = trackpad(&acc, -8, 1, .changed)
        XCTAssertTrue(claim.claimed)
        XCTAssertEqual(claim.translation, -14)
        _ = trackpad(&acc, -200, 0, .changed)
        let end = trackpad(&acc, 0, 0, .ended)
        XCTAssertTrue(end.finished)
        XCTAssertEqual(end.commit, 1)
    }

    func testAccumulatorShortSwipeSpringsBack() {
        var acc = ScrollSwipeAccumulator()
        _ = trackpad(&acc, 0, 0, .began)
        _ = trackpad(&acc, 60, 0, .changed)
        let end = trackpad(&acc, 0, 0, .ended)
        XCTAssertTrue(end.finished)
        XCTAssertEqual(end.commit, 0)
    }

    func testMomentumAfterCommitIsSwallowedWithoutEffect() {
        var acc = ScrollSwipeAccumulator()
        _ = trackpad(&acc, 0, 0, .began)
        _ = trackpad(&acc, -300, 0, .changed)
        XCTAssertEqual(trackpad(&acc, 0, 0, .ended).commit, 1)
        let momentum = trackpad(&acc, -80, 0, .changed, momentum: true)
        XCTAssertTrue(momentum.claimed)
        XCTAssertEqual(momentum.commit, 0)
        XCTAssertEqual(momentum.translation, 0)
        XCTAssertFalse(momentum.finished)
        // A new gesture starts clean.
        _ = trackpad(&acc, 0, 0, .began)
        XCTAssertFalse(trackpad(&acc, -3, 0, .changed, momentum: true).claimed)
    }

    func testCancelledPhaseResets() {
        var acc = ScrollSwipeAccumulator()
        _ = trackpad(&acc, 0, 0, .began)
        _ = trackpad(&acc, -300, 0, .changed)
        let cancel = trackpad(&acc, 0, 0, .cancelled)
        XCTAssertTrue(cancel.finished)
        XCTAssertEqual(cancel.commit, 0)
        XCTAssertEqual(acc.translation, 0)
    }

    func testMouseWheelStepsOneCardPerTickWithCooldown() {
        var acc = ScrollSwipeAccumulator()
        func tick(_ dx: CGFloat, at t: TimeInterval, index: Int = 1) -> ScrollSwipeAccumulator.Output {
            acc.feed(deltaX: dx, deltaY: 0, phase: .changed, momentum: false, precise: false,
                     timestamp: t, index: index, count: 3, width: 600)
        }
        XCTAssertEqual(tick(-3, at: 10).commit, 1)
        let held = tick(-3, at: 10.2)
        XCTAssertTrue(held.claimed)
        XCTAssertEqual(held.commit, 0)
        XCTAssertEqual(tick(3, at: 10.4).commit, -1)
        XCTAssertEqual(tick(-3, at: 11, index: 2).commit, 0)
        // Vertical wheel passes through.
        let v = acc.feed(deltaX: 0, deltaY: 5, phase: .changed, momentum: false, precise: false,
                         timestamp: 20, index: 1, count: 3, width: 600)
        XCTAssertFalse(v.claimed)
    }
}
