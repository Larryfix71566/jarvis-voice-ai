import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class ResultCarouselStateTests: XCTestCase {
    private func item(_ n: Int) -> WorkspaceResult {
        WorkspaceResult(payload: decodedResponsePayload(text: "Result \(n)", timestamp: Double(n)),
                        receivedAt: Date(timeIntervalSince1970: Double(n)))
    }

    func testPinnedAndRecentInventorySharedByBothModesAndStopsAtEnds() {
        let store = WorkspaceStore(historyLimit: 40)
        let cards = (0..<15).map(item)
        for card in cards { store.receive(card) }
        _ = store.pin(cards[0].id)
        store.select(cards[14].id)
        let expected = [cards[0].id] + cards[5...14].reversed().map(\.id)
        XCTAssertEqual(store.carouselResults.map(\.id), expected)
        let source = store.results
        store.setShowsAllResults(true)
        XCTAssertEqual(store.carouselResults.map(\.id), expected)
        XCTAssertEqual(store.results, source)
        store.select(expected[0])
        XCTAssertFalse(store.selectAdjacentResult(step: -1))
        XCTAssertTrue(store.selectAdjacentResult(step: 1))
        XCTAssertEqual(store.activeID, expected[1])
        store.select(expected.last!)
        XCTAssertFalse(store.selectAdjacentResult(step: 1))
        XCTAssertFalse(store.selectAdjacentResult(step: Int.max))
    }

    func testOlderOpenReaderIsRetainedWithoutChangingRecentsOrAge() {
        let store = WorkspaceStore(historyLimit: 40)
        let cards = (0..<15).map(item)
        for card in cards { store.receive(card) }
        let recents = store.recents.entries.map(\.id)
        store.select(cards[1].id)
        XCTAssertEqual(store.carouselFrontResult?.id, cards[1].id)
        XCTAssertTrue(store.carouselResults.contains { $0.id == cards[1].id })
        XCTAssertEqual(store.recents.entries.map(\.id), recents)
        XCTAssertEqual(store.results[1].receivedAt, cards[1].receivedAt)
        store.setShowsAllResults(true)
        XCTAssertEqual(store.carouselFrontResult?.id, cards[1].id)
        store.setShowsAllResults(false)
        XCTAssertEqual(store.carouselFrontResult?.id, cards[1].id)
        store.select(cards[14].id)
        XCTAssertFalse(store.carouselResults.contains { $0.id == cards[1].id })
        XCTAssertTrue(store.containsResult(cards[1].id), "Leaving an Older reader must not discard its retained history")
    }

    func testModeAndPagingUseSharedCoordinatorWithoutChangingContentMode() {
        let workspace = WorkspaceStore()
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()), atlas: AtlasStore(),
            panels: PanelStore(), drawer: drawer)
        let a = item(1), b = item(2)
        workspace.receive(a); workspace.receive(b); workspace.select(b.id)
        XCTAssertEqual(coordinator.executePointer(.resultMode, target: b.id.uuidString,
            args: ["mode": .string("all")]), .applied)
        XCTAssertTrue(workspace.showsAllResults)
        XCTAssertEqual(workspace.presentation(for: b).mode, .summary)
        XCTAssertEqual(coordinator.executePointer(.resultNext), .applied)
        XCTAssertEqual(workspace.activeID, a.id)
        XCTAssertEqual(coordinator.executePointer(.resultNext), .noop)
        XCTAssertEqual(coordinator.executePointer(.resultPrevious), .applied)
        XCTAssertEqual(coordinator.executePointer(.resultMode, target: b.id.uuidString,
            args: ["mode": .string("carousel")]), .applied)
        XCTAssertFalse(workspace.showsAllResults)
        XCTAssertEqual(coordinator.executePointer(.resultMode, target: UUID().uuidString,
            args: ["mode": .string("all")]), .invalid)
        XCTAssertFalse(workspace.showsAllResults)
    }

    func testClosingCardDoesNotDeleteOutputHistoryOrPinnedCards() {
        let workspace = WorkspaceStore()
        let output = DisplayResultStore()
        let a = item(1), b = item(2)
        workspace.receive(a); workspace.receive(b)
        output.apply(a.payload, workspaceID: a.id); output.apply(b.payload, workspaceID: b.id)
        _ = workspace.pin(a.id)
        workspace.close(b.id)
        XCTAssertTrue(workspace.containsResult(a.id))
        XCTAssertEqual(output.results.count, 2)
    }
}
