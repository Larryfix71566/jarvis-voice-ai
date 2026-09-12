import XCTest
@testable import MortimerHost

/// Closure plan C1.4 (gap G04): two mounted presentations of one tab
/// cannot fight over the remembered scroll offset — only the most recently
/// mounted one records, and an outgoing one can neither overwrite nor
/// erase the position.
@MainActor
final class DrawerScrollWriterTests: XCTestCase {
    func testOnlyTheMostRecentlyMountedPresentationRecordsScroll() {
        let models = DrawerModels(), docked = UUID(), detached = UUID()
        models.claimScrollWriter(docked, tab: "edit")
        XCTAssertTrue(models.recordScroll(120, tab: "edit", from: docked))
        XCTAssertEqual(models.scrollOffsets["edit"], 120)

        // A detached presentation mounts while the docked one is still alive.
        models.claimScrollWriter(detached, tab: "edit")
        XCTAssertFalse(models.recordScroll(0, tab: "edit", from: docked), "outgoing presentation must be ignored")
        XCTAssertEqual(models.scrollOffsets["edit"], 120, "outgoing presentation must not overwrite the offset")
        XCTAssertTrue(models.recordScroll(340, tab: "edit", from: detached))
        XCTAssertEqual(models.scrollOffsets["edit"], 340)

        // The outgoing presentation disappearing later does not disturb the
        // new writer, and releasing never discards the remembered position.
        models.releaseScrollWriter(docked, tab: "edit")
        XCTAssertTrue(models.isScrollWriter(detached, tab: "edit"))
        XCTAssertTrue(models.recordScroll(360, tab: "edit", from: detached))
        models.releaseScrollWriter(detached, tab: "edit")
        XCTAssertEqual(models.scrollOffsets["edit"], 360)
        XCTAssertFalse(models.recordScroll(0, tab: "edit", from: detached), "a released writer no longer records")
        XCTAssertEqual(models.scrollOffsets["edit"], 360)
    }

    func testWriterLeasesAreIndependentPerTabAndRejectNonFiniteOffsets() {
        let models = DrawerModels(), a = UUID(), b = UUID()
        models.claimScrollWriter(a, tab: "repo")
        models.claimScrollWriter(b, tab: "memory")
        XCTAssertTrue(models.recordScroll(50, tab: "repo", from: a))
        XCTAssertTrue(models.recordScroll(75, tab: "memory", from: b))
        XCTAssertFalse(models.recordScroll(1, tab: "memory", from: a), "a writer for one tab is not a writer for another")
        XCTAssertFalse(models.recordScroll(.nan, tab: "repo", from: a))
        XCTAssertFalse(models.recordScroll(.infinity, tab: "repo", from: a))
        XCTAssertTrue(models.recordScroll(-20, tab: "repo", from: a), "negative overscroll clamps to zero")
        XCTAssertEqual(models.scrollOffsets["repo"], 0)
        XCTAssertEqual(models.scrollOffsets["memory"], 75)
    }
}
