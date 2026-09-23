import XCTest
@testable import MortimerHost

@MainActor
final class PanelStoreTests: XCTestCase {
    func testDetachReturnAndReturnAllAreIdempotent() {
        let store = PanelStore(); store.detach(.atlas); store.detach(.atlas)
        XCTAssertEqual(store.detached, [.atlas]); store.returnPanel(.atlas); XCTAssertTrue(store.detached.isEmpty)
        store.detach(.memory); store.detach(.output); store.returnAll(); XCTAssertTrue(store.detached.isEmpty)
    }

    func testContentPanelsFocusExistingAndRefuseTheSeventhWithoutEviction() {
        let store = PanelStore()
        var ids: [ContentPanelID] = []
        for index in 0..<PanelStore.maxContentPanels {
            let result = store.openContent(.memoryGraph("graph-\(index)"), origin: "Graph \(index)")
            guard case .opened(let id) = result else {
                return XCTFail("panel \(index) should open")
            }
            ids.append(id)
        }
        XCTAssertEqual(store.contentRecords.count, PanelStore.maxContentPanels)
        let rejected = store.openContent(.transcript, origin: "Transcript")
        XCTAssertEqual(rejected, .rejectedLimit(maximum: PanelStore.maxContentPanels))
        XCTAssertEqual(store.contentRecords.count, PanelStore.maxContentPanels)
        XCTAssertTrue(ids.allSatisfy { store.contentRecord($0) != nil })

        let focused = store.openContent(.memoryGraph("graph-2"), origin: "duplicate")
        guard case .focused(let focusedID) = focused else {
            return XCTFail("repeating exact content should focus the existing panel")
        }
        XCTAssertEqual(focusedID, ids[2])
        XCTAssertEqual(store.focusedContentID, ids[2])
    }

    func testReturningContentReleasesCapacityAndInventoryUsesStableIdentity() {
        let store = PanelStore()
        guard case .opened(let id) = store.openContent(
            .comparison(UUID(), UUID()), origin: "Compare") else {
            return XCTFail("comparison panel should open")
        }
        XCTAssertEqual(store.contentInventoryEntries.count, 1)
        XCTAssertTrue(store.moveContent(id, to: "display-2"))
        guard case .object(let entry) = store.contentInventoryEntries[0] else {
            return XCTFail("inventory entry should be an object")
        }
        XCTAssertEqual(entry["id"], .string(id.rawValue.uuidString))
        XCTAssertEqual(entry["screen_id"], .string("display-2"))
        store.returnContent(id)
        XCTAssertNil(store.contentRecord(id))
        XCTAssertTrue(store.contentInventoryEntries.isEmpty)
    }
}
