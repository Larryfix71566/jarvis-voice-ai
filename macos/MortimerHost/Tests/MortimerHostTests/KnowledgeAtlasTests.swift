import XCTest
@testable import MortimerHost

@MainActor
final class KnowledgeAtlasTests: XCTestCase {
    func testAtlasSearchAndSelectionPreserveStableCardIdentity() {
        let store = AtlasStore()
        let first = AtlasCard(id: UUID(), title: "Weather", summary: "Forecast", source: "tool", group: nil)
        let second = AtlasCard(id: UUID(), title: "Repository", summary: "Changes", source: nil, group: nil)
        store.replace([first, second]); store.setQuery("weather")
        XCTAssertEqual(store.visibleCards.map(\.id), [first.id])
        store.select(first.id); XCTAssertEqual(store.selectedID, first.id)
        store.assign(first.id, to: "Research"); XCTAssertTrue(store.groups["Research"]?.contains(first.id) == true)
    }

    func testVoicePlacementSupportsExactGridAndCollisionSafeRelativeMoves() {
        let store = AtlasStore()
        let cards = (0..<4).map { index in
            AtlasCard(id: UUID(), title: "Card (index)", summary: "Summary", source: nil, group: nil)
        }
        store.replace(cards)
        XCTAssertEqual(store.position(of: cards[0].id), AtlasGridPosition(row: 1, column: 1))
        XCTAssertEqual(store.position(of: cards[3].id), AtlasGridPosition(row: 2, column: 1))

        XCTAssertTrue(store.move(cards[2].id, row: 2, column: 2))
        XCTAssertFalse(store.move(cards[3].id, row: 2, column: 2), "occupied exact slots are never overwritten")
        XCTAssertTrue(store.move(cards[3].id, relativeTo: cards[0].id, relation: "right"))
        XCTAssertEqual(store.position(of: cards[3].id), AtlasGridPosition(row: 3, column: 2),
                       "right moves descend until a free adjacent slot exists")
        XCTAssertTrue(store.move(cards[1].id, relativeTo: cards[0].id, relation: "left"))
        XCTAssertEqual(store.position(of: cards[1].id), AtlasGridPosition(row: 2, column: 1))
        XCTAssertTrue(store.move(cards[2].id, relativeTo: cards[0].id, relation: "left"))
        XCTAssertEqual(store.position(of: cards[2].id), AtlasGridPosition(row: 3, column: 1),
                       "left moves descend until a free adjacent slot exists")

        store.arrange()
        XCTAssertEqual(store.position(of: cards[0].id), AtlasGridPosition(row: 1, column: 1))
    }

    func testContextRefreshRetainsResultIdentityAndManualPlacement() {
        let store = AtlasStore()
        let result = AtlasCard(id: UUID(), title: "Weather", summary: "Forecast", source: "tool")
        let firstContext = AtlasCard(id: AtlasStore.stableID(namespace: "memory", key: "overview"),
                                     title: "Memory", summary: "One fact", source: "memory",
                                     kind: .memory)
        store.replace(results: [result], context: [firstContext])
        XCTAssertTrue(store.move(result.id, row: 3, column: 2))
        store.assign(result.id, to: "Research")

        let refreshed = AtlasCard(id: firstContext.id, title: "Memory", summary: "Two facts", source: "memory",
                                  kind: .memory)
        let architecture = AtlasCard(id: AtlasStore.stableID(namespace: "architecture", key: "docs/ARCHITECTURE.md"),
                                     title: "Architecture", summary: "Contract", source: "docs/ARCHITECTURE.md",
                                     kind: .architecture)
        store.replaceContext([refreshed, architecture])

        XCTAssertEqual(store.cards.first(where: { $0.id == result.id })?.title, "Weather")
        XCTAssertEqual(store.position(of: result.id), AtlasGridPosition(row: 3, column: 2))
        XCTAssertTrue(store.groups["Research"]?.contains(result.id) == true)
        XCTAssertEqual(store.cardsByKind[.architecture]?.count, 1)
        XCTAssertEqual(store.cards.first(where: { $0.id == firstContext.id })?.summary, "Two facts")
    }

    func testStableContextIdentityIsRepeatableAndNamespaced() {
        let a = AtlasStore.stableID(namespace: "memory", key: "overview")
        XCTAssertEqual(a, AtlasStore.stableID(namespace: "memory", key: "overview"))
        XCTAssertNotEqual(a, AtlasStore.stableID(namespace: "plan", key: "overview"))
    }
}
