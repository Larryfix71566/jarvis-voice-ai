import XCTest
@testable import MortimerHost

final class TabStripViewportTests: XCTestCase {
    private let keys = ["repo", "edit", "memory", "runs"]
    private let frames: [String: CGRect] = [
        "repo": CGRect(x: 0, y: 0, width: 70, height: 32),
        "edit": CGRect(x: 72, y: 0, width: 80, height: 32),
        "memory": CGRect(x: 154, y: 0, width: 110, height: 32),
        "runs": CGRect(x: 266, y: 0, width: 80, height: 32),
    ]

    func testFittingHeaderHasNoScrollControls() {
        let view = TabStripViewport(width: 400, contentWidth: 346)
        XCTAssertFalse(view.overflows)
        XCTAssertNil(view.target(forward: true, keys: keys, frames: frames))
        XCTAssertNil(view.target(forward: false, keys: keys, frames: frames))
    }

    func testForwardRevealsFirstPartiallyHiddenTab() {
        let view = TabStripViewport(width: 200, contentWidth: 346)
        XCTAssertFalse(view.canScrollBack)
        XCTAssertTrue(view.canScrollForward)
        XCTAssertEqual(view.target(forward: true, keys: keys, frames: frames), "memory")
    }

    func testBackRevealsNearestHiddenTabRatherThanJumpingToStart() {
        let view = TabStripViewport(offset: 146, width: 200, contentWidth: 346)
        XCTAssertTrue(view.canScrollBack)
        XCTAssertFalse(view.canScrollForward)
        XCTAssertEqual(view.target(forward: false, keys: keys, frames: frames), "edit")
    }

    func testUnmeasuredTabsDoNotProduceInventedScrollTargets() {
        let view = TabStripViewport(width: 200, contentWidth: 346)
        XCTAssertNil(view.target(forward: true, keys: keys, frames: [:]))
    }

    func testSubpixelRoundingAndRubberBandingDoNotEnableEndArrow() {
        let view = TabStripViewport(offset: 146.5, width: 200, contentWidth: 346)
        XCTAssertFalse(view.canScrollForward)
        XCTAssertFalse(TabStripViewport(offset: -4, width: 200, contentWidth: 346).canScrollBack)
    }
}
