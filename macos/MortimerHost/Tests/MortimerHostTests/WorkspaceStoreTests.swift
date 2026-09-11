import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class WorkspaceStoreTests: XCTestCase {
    private func result() throws -> WorkspaceResult {
        let payload = try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"body":"Research result","surface":"drawer"}"#.utf8))
        return WorkspaceResult(payload: payload)
    }

    func testArrivalPreservesReadingComparisonAndScroll() throws {
        let store = WorkspaceStore(historyLimit: 2)
        let a = try result(), b = try result()
        store.receive(a)
        store.receive(b)
        store.compare(with: b.id)
        store.rememberScroll(420, for: a.id)
        for _ in 0..<10 { store.receive(try result()) }
        XCTAssertEqual(store.activeID, a.id)
        XCTAssertEqual(store.comparisonID, b.id)
        XCTAssertEqual(store.scrollOffsets[a.id], 420)
        XCTAssertEqual(store.results.count, 4)
    }

    func testExplicitConversationChoiceSurvivesNewResults() throws {
        let store = WorkspaceStore()
        store.receive(try result())
        store.returnToConversation()
        store.receive(try result())
        XCTAssertTrue(store.showsConversation)
        XCTAssertEqual(store.unreadIDs.count, 1)
    }

    func testPinLimitRefusesWithoutEviction() throws {
        let store = WorkspaceStore(historyLimit: 1, pinLimit: 2)
        let a = try result(), b = try result(), c = try result()
        store.receive(a); XCTAssertTrue(store.pin(a.id))
        store.receive(b); XCTAssertTrue(store.pin(b.id))
        store.receive(c); XCTAssertFalse(store.pin(c.id))
        for _ in 0..<10 { store.receive(try result()) }
        XCTAssertEqual(store.pinnedIDs, [a.id, b.id])
        XCTAssertTrue(store.results.contains { $0.id == b.id })
    }

    func testClosingWorkspaceTabPreservesOutputHistoryAndSharedIdentity() throws {
        let workspace = WorkspaceStore(), output = DisplayResultStore()
        let received = try result()
        workspace.receive(received)
        output.apply(received.payload, workspaceID: received.id)
        XCTAssertEqual(output.results.first?.workspaceID, workspace.activeID)
        workspace.close(received.id)
        XCTAssertEqual(output.results.count, 1)
        XCTAssertNil(workspace.activeID)
        XCTAssertTrue(workspace.showsConversation)
    }

    func testIdenticalPayloadsAreDistinctButSameReceiptIsNotDuplicated() throws {
        let store = WorkspaceStore()
        let a = try result(), b = try result()
        store.receive(a); store.receive(a); store.receive(b)
        XCTAssertEqual(store.results.count, 2)
        XCTAssertNotEqual(a.id, b.id)
    }

    func testOutputExpansionBelongsToHistoryAndDoesNotReopenCollapsedItems() throws {
        let store = DisplayResultStore()
        store.apply(try result().payload)
        let first = try XCTUnwrap(store.results.first?.id)
        XCTAssertEqual(store.expandedID, first)
        store.expandedID = nil
        // A new presentation reads the same store without an on-appear reset.
        let detached = store
        XCTAssertNil(detached.expandedID)
        detached.apply(try result().payload)
        XCTAssertEqual(detached.expandedID, detached.results.first?.id)
        detached.remove(id: detached.results.first!.id)
        XCTAssertNil(detached.expandedID)
        XCTAssertEqual(detached.results.first?.id, first)
    }

    func testSupportingResultSurvivesHistoryTrimmingWithoutChangingMainSelection() throws {
        let store = WorkspaceStore(historyLimit: 1)
        let main = try result(), supporting = try result()
        store.receive(main); store.receive(supporting)
        store.rememberScroll(310, for: supporting.id)
        XCTAssertTrue(store.sendToDisplay(.result(supporting.id)))
        for _ in 0..<10 { store.receive(try result()) }
        XCTAssertEqual(store.activeID, main.id)
        XCTAssertEqual(store.supportingResult?.id, supporting.id)
        XCTAssertEqual(store.scrollOffsets[supporting.id], 310)
        XCTAssertFalse(store.sendToDisplay(.result(UUID())))
    }

    func testGraphDisplayAssignmentReusesGraphOwnerAndKeepsCompactComparisonChoice() {
        let store = WorkspaceStore()
        let graph = store.memoryGraph
        store.showComparisonOnCompact = true
        XCTAssertTrue(store.sendToDisplay(.memoryGraph))
        store.returnToConversation()
        store.returnToWorkspace()
        XCTAssertTrue(store.memoryGraph === graph)
        XCTAssertEqual(store.supportingContent, .memoryGraph)
        XCTAssertTrue(store.showComparisonOnCompact)
    }

    func testCloseActivePromotesComparisonAndRemovesOnlyItsMetadata() throws {
        let store = WorkspaceStore()
        let a = try result(), b = try result()
        store.receive(a); store.receive(b); store.compare(with: b.id)
        store.rememberScroll(70, for: b.id)
        store.close(a.id)
        XCTAssertEqual(store.activeID, b.id)
        XCTAssertNil(store.comparisonID)
        XCTAssertEqual(store.scrollOffsets[b.id], 70)
    }
}
