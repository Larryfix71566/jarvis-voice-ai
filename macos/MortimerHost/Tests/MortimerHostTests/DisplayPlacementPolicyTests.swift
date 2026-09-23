import XCTest
@testable import MortimerHost

final class DisplayPlacementPolicyTests: XCTestCase {
    private let primary = PlacementScreen(id: "primary", visibleFrame: CGRect(x: 0, y: 0, width: 1440, height: 900), isMain: true)
    private let external = PlacementScreen(id: "external", visibleFrame: CGRect(x: 1440, y: 0, width: 1920, height: 1080))
    private let console = CGRect(x: 80, y: 80, width: 1000, height: 700)
    private let manual = CGRect(x: 1700, y: 200, width: 600, height: 500)

    func testFreshConsoleDefaultsToMainDisplayWhenAppKitRestoredItOnAuxiliary() {
        var policy = DisplayPlacementPolicy()
        let auxiliaryConsole = CGRect(x: 1500, y: 100, width: 900, height: 600)
        let moves = policy.reconcile(windows: [.console: auxiliaryConsole],
                                     screens: [external, primary], primaryID: primary.id)
        XCTAssertEqual(moves[.console], DisplayPlacementPolicy.clamp(auxiliaryConsole, to: primary.visibleFrame))
        XCTAssertEqual(policy.records[.console]?.screenID, primary.id)
        XCTAssertEqual(policy.records[.console]?.manual, false)
    }

    func testManualWindowRecoversAfterUnplugEvenWhenAppKitAlreadyMovedIt() {
        var policy = DisplayPlacementPolicy()
        policy.noteManual(.display, frame: manual, screens: [primary, external])
        let osMoved = CGRect(x: 100, y: 100, width: 600, height: 500)
        let recovery = policy.reconcile(windows: [.console: console, .display: osMoved], screens: [primary], primaryID: primary.id)
        XCTAssertTrue(primary.visibleFrame.contains(recovery[.display]!))
        XCTAssertEqual(policy.records[.display]?.recovery?.frame, manual)
        let restored = policy.reconcile(windows: [.console: console, .display: recovery[.display]!], screens: [external, primary], primaryID: primary.id)
        XCTAssertEqual(restored[.display], manual)
        XCTAssertNil(policy.records[.display]?.recovery)
    }

    func testManualMoveAfterRecoveryWinsOverReconnect() {
        var policy = DisplayPlacementPolicy()
        policy.noteManual(.drawer, frame: manual, screens: [primary, external])
        _ = policy.reconcile(windows: [.console: console, .drawer: manual], screens: [primary], primaryID: primary.id)
        let newChoice = CGRect(x: 400, y: 100, width: 400, height: 600)
        policy.noteManual(.drawer, frame: newChoice, screens: [primary])
        let moves = policy.reconcile(windows: [.console: console, .drawer: newChoice], screens: [primary, external], primaryID: primary.id)
        XCTAssertNil(moves[.drawer])
        XCTAssertEqual(policy.records[.drawer]?.frame, newChoice)
        XCTAssertNil(policy.records[.drawer]?.recovery)
    }

    func testCloseOrDockCancelsReconnectRecovery() {
        var policy = DisplayPlacementPolicy()
        policy.noteManual(.drawer, frame: manual, screens: [primary, external])
        _ = policy.reconcile(windows: [.drawer: manual], screens: [primary], primaryID: primary.id)
        policy.noteClosed(.drawer)
        XCTAssertNil(policy.records[.drawer]?.recovery)
        let moves = policy.reconcile(windows: [.console: console], screens: [primary, external], primaryID: primary.id)
        XCTAssertNil(moves[.drawer])
    }

    func testOpeningSecondAuxiliaryUsesLegacySplitWithoutMovingManualWindow() {
        var policy = DisplayPlacementPolicy()
        let initial = policy.reconcile(windows: [.console: console, .display: console], screens: [primary, external], primaryID: primary.id)
        XCTAssertEqual(initial[.display], external.visibleFrame)
        let split = policy.reconcile(windows: [.console: console, .display: initial[.display]!, .drawer: console], screens: [primary, external], primaryID: primary.id)
        XCTAssertEqual(split[.display]?.width, 1920 * 0.6)
        XCTAssertEqual(split[.drawer]?.width, 1920 * 0.4)
        policy.noteManual(.display, frame: manual, screens: [primary, external])
        let next = policy.reconcile(windows: [.console: console, .display: manual, .drawer: split[.drawer]!], screens: [primary, external], primaryID: primary.id)
        XCTAssertNil(next[.display])
    }

    func testStableDisplayRolesSurviveScreenArrayReordering() {
        var policy = DisplayPlacementPolicy()
        let portrait = PlacementScreen(id: "portrait", visibleFrame: CGRect(x: -1080, y: -200, width: 1080, height: 1920))
        let first = policy.reconcile(windows: [.console: console, .display: console, .drawer: console], screens: [primary, external, portrait], primaryID: primary.id)
        let second = policy.reconcile(windows: [.console: console, .display: first[.display]!, .drawer: first[.drawer]!], screens: [portrait, external, primary], primaryID: primary.id)
        XCTAssertEqual(second[.display], first[.display])
        XCTAssertEqual(second[.drawer], first[.drawer])
        XCTAssertNotEqual(second[.display], second[.drawer])
    }

    func testMirroredDisplaysDoNotCreateAnExtendedAreaOrEmptyWindows() {
        var policy = DisplayPlacementPolicy()
        let mirror = PlacementScreen(id: "mirror", visibleFrame: primary.visibleFrame)
        let moves = policy.reconcile(windows: [.console: console], screens: [primary, mirror], primaryID: primary.id)
        XCTAssertTrue(moves.isEmpty)
        XCTAssertNil(policy.records[.display])
        XCTAssertNil(policy.records[.drawer])
    }

    func testOffscreenTitleBarIsRecoveredAndNegativeCoordinatesAreValid() {
        let left = PlacementScreen(id: "left", visibleFrame: CGRect(x: -1280, y: 0, width: 1280, height: 800))
        XCTAssertTrue(DisplayPlacementPolicy.reachable(CGRect(x: -1000, y: 100, width: 600, height: 500), screens: [left]))
        let unreachable = CGRect(x: 20, y: -600, width: 1000, height: 700)
        XCTAssertTrue(DisplayPlacementPolicy.reachable(unreachable, screens: [primary])) // title bar is still accessible
        let above = CGRect(x: 20, y: 800, width: 1000, height: 700)
        XCTAssertFalse(DisplayPlacementPolicy.reachable(above, screens: [primary]))
        var policy = DisplayPlacementPolicy()
        let moves = policy.reconcile(windows: [.display: above], screens: [primary], primaryID: primary.id)
        XCTAssertTrue(primary.visibleFrame.contains(moves[.display]!))
    }

    func testResolutionShrinkClampsManualWindowAndRestoresWhenItFitsAgain() {
        var policy = DisplayPlacementPolicy()
        let large = CGRect(x: 1700, y: 100, width: 1400, height: 900)
        policy.noteManual(.display, frame: large, screens: [primary, external])
        _ = policy.reconcile(windows: [.console: console, .display: large], screens: [primary, external], primaryID: primary.id)
        let smaller = PlacementScreen(id: external.id, visibleFrame: CGRect(x: 1440, y: 0, width: 1280, height: 720))
        let shrunk = policy.reconcile(windows: [.console: console, .display: large], screens: [primary, smaller], primaryID: primary.id)
        XCTAssertTrue(smaller.visibleFrame.contains(shrunk[.display]!))
        let restored = policy.reconcile(windows: [.console: console, .display: shrunk[.display]!], screens: [primary, external], primaryID: primary.id)
        XCTAssertEqual(restored[.display], large)
    }

    func testReopenedManualWindowRestoresItsSavedFrame() {
        var policy = DisplayPlacementPolicy()
        policy.noteManual(.display, frame: manual, screens: [primary, external])
        let moves = policy.reconcile(windows: [.console: console, .display: console], screens: [primary, external], primaryID: primary.id, restoring: [.display])
        XCTAssertEqual(moves[.display], manual)
    }
}
