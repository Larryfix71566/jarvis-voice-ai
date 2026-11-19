import XCTest
@testable import MortimerHost

/// Interface cleanup Phase 2, slice B: one push-to-talk owner, visible mute.
@MainActor
final class OrbMicTests: XCTestCase {
    override func setUp() { PushToTalkOwnership.reset() }
    override func tearDown() { PushToTalkOwnership.reset() }

    func testOrbHoldBlocksSpaceAndRestoresPriorMic() {
        for initial in [false, true] {
            PushToTalkOwnership.reset()
            var orb = OrbPushToTalkGuard()
            XCTAssertTrue(orb.begin(micEnabled: initial))
            XCTAssertTrue(orb.promote())
            XCTAssertFalse(PushToTalkOwnership.begin(.space), "Space refused while the orb owns PTT")
            XCTAssertFalse(PushToTalkOwnership.spaceOwned)
            XCTAssertEqual(orb.finish(), initial, "release restores the pre-hold mic state")
            XCTAssertTrue(PushToTalkOwnership.begin(.space), "Space may begin after the orb releases")
        }
    }

    func testSpaceBlocksOrb() {
        XCTAssertTrue(PushToTalkOwnership.begin(.space))
        XCTAssertTrue(PushToTalkOwnership.spaceOwned)
        var orb = OrbPushToTalkGuard()
        XCTAssertFalse(orb.begin(micEnabled: true), "orb refused while Space owns PTT")
        XCTAssertNil(orb.finish(), "a refused orb press owns nothing")
        XCTAssertTrue(PushToTalkOwnership.spaceOwned, "refused orb release must not free Space's ownership")
        XCTAssertTrue(PushToTalkOwnership.release(.space))
        XCTAssertTrue(orb.begin(micEnabled: false))
    }

    func testOnlyOwnerCanRelease() {
        XCTAssertTrue(PushToTalkOwnership.begin(.orb))
        XCTAssertFalse(PushToTalkOwnership.release(.space))
        XCTAssertEqual(PushToTalkOwnership.owner, .orb)
        XCTAssertTrue(PushToTalkOwnership.release(.orb))
        XCTAssertNil(PushToTalkOwnership.owner)
    }

    func testSpaceRouteUsesSharedOwner() {
        XCTAssertTrue(PushToTalkOwnership.begin(.orb))
        // Space down while the orb owns: not owned by Space, so it routes to
        // startTalking, which the monitor then refuses at begin(.space).
        XCTAssertEqual(SpaceKeyRoute.route(isKeyDown: true, isRepeat: false, typingTarget: false,
                                           focusedControl: false, connected: true,
                                           owned: PushToTalkOwnership.spaceOwned), .startTalking)
        XCTAssertFalse(PushToTalkOwnership.begin(.space))
        // Space key up never stops the orb's hold.
        XCTAssertEqual(SpaceKeyRoute.route(isKeyDown: false, isRepeat: false, typingTarget: false,
                                           focusedControl: false, connected: true,
                                           owned: PushToTalkOwnership.spaceOwned), .passThrough)
    }

    func testMuteButtonPresentation() {
        let live = OrbMuteButton.presentation(connected: true, micEnabled: true)
        XCTAssertEqual(live?.title, "Mute")
        XCTAssertEqual(live?.symbol, "mic.fill")
        XCTAssertEqual(live?.accessibilityLabel, "Mute microphone")
        let muted = OrbMuteButton.presentation(connected: true, micEnabled: false)
        XCTAssertEqual(muted?.title, "Unmute")
        XCTAssertEqual(muted?.symbol, "mic.slash.fill")
        XCTAssertEqual(muted?.accessibilityLabel, "Unmute microphone")
        XCTAssertNil(OrbMuteButton.presentation(connected: false, micEnabled: true))
        XCTAssertNil(OrbMuteButton.presentation(connected: false, micEnabled: false))
    }
}
