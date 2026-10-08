import XCTest
import JarvisKit
@testable import MortimerHost

/// The Recents display limit must not remove controls for a retained pane.
/// The same UUIDs used by the console menus are exercised through the shared
/// pointer coordinator; Output history is a separate owner and stays intact.
@MainActor
final class CC7a3OlderControlsTests: XCTestCase {
    private struct Fixture {
        let workspace: WorkspaceStore
        let output: DisplayResultStore
        let results: [WorkspaceResult]
        let coordinator: ConsoleActionCoordinator
    }

    private func result(_ index: Int, isPrivate: Bool = false) throws -> WorkspaceResult {
        var fields: [String: Any] = ["title": "Retained fixture \(index)", "body": "Local fixture body"]
        if isPrivate { fields["data_policy"] = "local_only" }
        let payload = try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: fields))
        return WorkspaceResult(payload: payload,
                               receivedAt: Date(timeIntervalSince1970: 1_000 + Double(index)))
    }

    private func coordinator(_ workspace: WorkspaceStore) -> ConsoleActionCoordinator {
        let drawer = DrawerState()
        return ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
            drawer: drawer, screens: { [] })
    }

    private func fixture(count: Int = 11, privateOldest: Bool = false) throws -> Fixture {
        let workspace = WorkspaceStore(), output = DisplayResultStore()
        let results = try (0..<count).map { try result($0, isPrivate: privateOldest && $0 == 0) }
        for item in results {
            workspace.receive(item, quietly: true)
            // Protected payloads never enter Output through the real router.
            if !item.payload.isProtectedLocal { output.apply(item.payload, workspaceID: item.id) }
        }
        return Fixture(workspace: workspace, output: output, results: results,
                       coordinator: coordinator(workspace))
    }

    func testOpenedEleventhResultHasUnnumberedControlsAndClosesOnlyItsUUID() throws {
        let f = try fixture()
        let oldest = try XCTUnwrap(f.results.first)
        XCTAssertEqual(f.coordinator.executePointer(.resultSelect, target: oldest.id.uuidString), .applied)
        let listing = f.workspace.recents
        let older = try XCTUnwrap(listing.actionableEntries.first { $0.id == oldest.id })
        XCTAssertFalse(listing.entries.contains { $0.id == oldest.id })
        XCTAssertEqual(listing.entries.count, 10)
        XCTAssertEqual(listing.entries.map(\.number), Array(1...10).map(Optional.some))
        XCTAssertEqual(older.section, .older)
        XCTAssertNil(older.number)
        XCTAssertTrue(older.isActive)
        XCTAssertTrue(ConsoleActionBar.recentsAccessibilityLabel(older).contains("shown"))
        XCTAssertFalse(ConsoleActionBar.recentsAccessibilityLabel(older).contains("Number"))
        XCTAssertEqual(WorkspaceRecents.resolve("number 11", in: listing.entries), .none)

        let numberedIDs = listing.entries.map(\.id)
        XCTAssertEqual(f.coordinator.executePointer(.resultClose, target: older.id.uuidString), .applied)
        XCTAssertFalse(f.workspace.containsResult(oldest.id))
        XCTAssertEqual(f.workspace.results.count, 10)
        XCTAssertEqual(f.workspace.recents.entries.map(\.id), numberedIDs)
        XCTAssertEqual(f.output.results.count, 11)
        XCTAssertTrue(f.output.results.contains { $0.workspaceID == oldest.id },
                      "Closing a retained pane must not remove its Output record")
    }

    func testOlderPinAndUnpinKeepTheSameIdentityWithoutExpandingRecentNumbers() throws {
        let f = try fixture(count: 12)
        let oldest = try XCTUnwrap(f.results.first)
        let older = try XCTUnwrap(f.workspace.recents.actionableEntries.first { $0.id == oldest.id })
        let before = f.workspace.consoleRevision
        XCTAssertEqual(f.coordinator.executePointer(.resultPin, target: older.id.uuidString), .applied)
        XCTAssertEqual(f.workspace.pinnedIDs, [oldest.id])
        XCTAssertEqual(f.workspace.recents.pinned.first?.id, oldest.id)
        XCTAssertEqual(f.workspace.recents.pinned.first?.number, 1)
        XCTAssertEqual(f.workspace.recents.recent.count, 10)
        XCTAssertEqual(f.workspace.results.count, 12)

        XCTAssertEqual(f.coordinator.executePointer(.resultUnpin, target: older.id.uuidString), .applied)
        let unpinned = try XCTUnwrap(f.workspace.recents.olderEntries.first { $0.id == oldest.id })
        XCTAssertNil(unpinned.number)
        XCTAssertTrue(f.workspace.pinnedIDs.isEmpty)
        XCTAssertEqual(f.workspace.recents.entries.count, 10)
        XCTAssertEqual(f.workspace.consoleRevision, before + 2)
        XCTAssertEqual(f.output.results.count, 12)
    }

    func testComparedOlderResultCanCloseWithoutClosingTheShownResult() throws {
        let f = try fixture(count: 12)
        let oldest = try XCTUnwrap(f.results.first), shown = try XCTUnwrap(f.results.last)
        let candidate = try XCTUnwrap(f.workspace.recents.actionableEntries.first { $0.id == oldest.id })
        XCTAssertNil(candidate.number)
        XCTAssertEqual(f.coordinator.executePointer(.compareSet, target: shown.id.uuidString,
            secondaryTarget: candidate.id.uuidString), .applied)
        XCTAssertEqual(f.workspace.activeID, shown.id)
        XCTAssertEqual(f.workspace.comparisonID, oldest.id)
        XCTAssertEqual(ConsoleActionBar.actionTarget(active: f.workspace.activeResult,
            comparison: f.workspace.comparisonResult, side: .b)?.id, oldest.id)

        XCTAssertEqual(f.coordinator.executePointer(.resultClose, target: candidate.id.uuidString), .applied)
        XCTAssertEqual(f.workspace.activeID, shown.id)
        XCTAssertNil(f.workspace.comparisonID)
        XCTAssertTrue(f.workspace.containsResult(shown.id))
        XCTAssertTrue(f.workspace.containsResult(f.results[1].id), "The other Older result must be untouched")
        XCTAssertEqual(f.output.results.count, 12)
        XCTAssertTrue(f.output.results.contains { $0.workspaceID == oldest.id })
    }

    func testOlderCanBeTheShownComparisonPaneUsingItsCanonicalUUID() throws {
        let f = try fixture()
        let oldest = try XCTUnwrap(f.results.first), newest = try XCTUnwrap(f.results.last)
        let candidate = try XCTUnwrap(f.workspace.recents.actionableEntries.first { $0.id == oldest.id })
        XCTAssertEqual(f.coordinator.executePointer(.compareSet, target: candidate.id.uuidString,
            secondaryTarget: newest.id.uuidString), .applied)
        XCTAssertEqual(f.workspace.activeID, oldest.id)
        XCTAssertEqual(f.workspace.comparisonID, newest.id)
        XCTAssertTrue(f.workspace.recents.olderEntries.contains { $0.id == oldest.id && $0.isActive })
        XCTAssertEqual(f.workspace.recents.entries.count, 10)
        XCTAssertEqual(f.workspace.results.count, 11)
        XCTAssertEqual(f.output.results.count, 11)
    }

    func testPrivateOlderControlsRemainLocalAndNeverAcquireAVoiceNumber() throws {
        let f = try fixture(privateOldest: true)
        let secret = try XCTUnwrap(f.results.first)
        let older = try XCTUnwrap(f.workspace.recents.actionableEntries.first { $0.id == secret.id })
        XCTAssertNil(older.number)
        XCTAssertTrue(older.isPrivate)
        XCTAssertEqual(older.card.summary, ConversationThread.privateSummary)
        XCTAssertEqual(WorkspaceRecents.resolve(secret.payload.title!, in: f.workspace.recents.entries), .none)
        XCTAssertEqual(WorkspaceRecents.resolve("number 11", in: f.workspace.recents.entries), .none)

        XCTAssertEqual(f.coordinator.executePointer(.resultPin, target: older.id.uuidString), .applied)
        let pinned = try XCTUnwrap(f.workspace.recents.pinned.first)
        XCTAssertNil(pinned.number)
        XCTAssertEqual(f.workspace.recents.recent.map(\.number), Array(1...10).map(Optional.some))
        XCTAssertFalse(String(describing: f.coordinator.inventoryJSON()).contains(secret.id.uuidString))
        XCTAssertFalse(String(describing: f.coordinator.inventoryJSON()).contains(secret.payload.title!))
        XCTAssertEqual(f.coordinator.executePointer(.resultUnpin, target: older.id.uuidString), .applied)
        XCTAssertEqual(f.coordinator.executePointer(.resultClose, target: older.id.uuidString), .applied)
        XCTAssertFalse(f.workspace.containsResult(secret.id))
        XCTAssertEqual(f.output.results.count, 10, "Protected results never entered the Output fixture")
    }

    func testOlderListingAndActionsPreserveTwentyOtherResultsAndBothComparisonPanes() throws {
        let workspace = WorkspaceStore()
        let first = try result(0), second = try result(1)
        workspace.receive(first, quietly: true); workspace.receive(second, quietly: true)
        let console = coordinator(workspace)
        XCTAssertEqual(console.executePointer(.compareSet, target: first.id.uuidString,
            secondaryTarget: second.id.uuidString), .applied)
        for index in 2..<24 { workspace.receive(try result(index), quietly: true) }
        let before = workspace.results.map(\.id)
        let listing = workspace.recents
        XCTAssertEqual(before.count, 22, "Twenty ordinary results plus both protected comparison panes")
        XCTAssertEqual(listing.entries.count, 10)
        XCTAssertEqual(Set(listing.actionableEntries.map(\.id)), Set(before))
        XCTAssertEqual(workspace.results.map(\.id), before, "Building controls must not mutate retention")
        let compared = try XCTUnwrap(listing.olderEntries.first { $0.id == second.id })
        XCTAssertNil(compared.number)
        XCTAssertEqual(console.executePointer(.resultClose, target: compared.id.uuidString), .applied)
        XCTAssertEqual(workspace.activeID, first.id)
        XCTAssertEqual(workspace.results.count, 21)
        XCTAssertEqual(Set(workspace.results.map(\.id)), Set(before).subtracting([second.id]))
    }
}
