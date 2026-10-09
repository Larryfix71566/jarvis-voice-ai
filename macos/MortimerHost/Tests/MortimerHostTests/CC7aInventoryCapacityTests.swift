import XCTest
import JarvisKit
@testable import MortimerHost

/// A bounded inventory must retain the voice numbers actually visible in
/// Recents even when a custom store retains more than 100 results.
@MainActor
final class CC7aInventoryCapacityTests: XCTestCase {
    private func result(_ index: Int, private isPrivate: Bool = false) throws -> WorkspaceResult {
        let prefix = String(format: "Result %03d ", index)
        let title = prefix + String(repeating: "x", count: 120 - prefix.count)
        var fields: [String: Any] = ["kind": "markdown", "title": title,
                                     "body": "Public synthetic inventory fixture"]
        if isPrivate {
            fields["title"] = "PRIVATE-TITLE-\(index)"
            fields["body"] = "PRIVATE-BODY-\(index)"
            fields["data_policy"] = "local_only"
        }
        let payload = try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: fields))
        return WorkspaceResult(payload: payload,
                               receivedAt: Date(timeIntervalSince1970: Double(index)))
    }

    private func rows(_ store: WorkspaceStore) throws -> [[String: JSONValue]] {
        let values = try XCTUnwrap(store.consoleInventoryJSON["results"]?.arrayValue)
        return values.map { value in
            guard case .object(let row) = value else {
                XCTFail("Inventory rows must remain JSON objects")
                return [:]
            }
            return row
        }
    }

    func testHundredLongRowsKeepAllNumberedRecentsAndNewestOlder() throws {
        let store = WorkspaceStore(historyLimit: 200, pinLimit: 20)
        let retained = try (0..<125).map { try result($0) }
        for item in retained { store.receive(item, quietly: true) }
        // Pin an early, middle and late result. Oldest-first prefix(100)
        // loses the late pin and all ten newest numbered unpinned results.
        for index in [0, 61, 124] { XCTAssertTrue(store.pin(retained[index].id)) }
        store.select(retained[0].id)
        store.compare(with: retained[1].id)
        store.rememberScroll(420, for: retained[0].id)
        let beforeResults = store.results
        let beforeRevision = store.consoleRevision
        let beforeUnread = store.unreadIDs
        let beforeNotice = store.arrivalNoticeID
        let listing = store.recents
        let expected = Array((listing.entries + listing.olderEntries).prefix(100))

        let inventoryRows = try rows(store)
        XCTAssertEqual(inventoryRows.count, 100)
        XCTAssertEqual(store.consoleInventoryJSON["results_omitted"], .number(25))
        XCTAssertEqual(inventoryRows.compactMap { $0["id"]?.stringValue },
                       expected.map { $0.id.uuidString })
        for entry in listing.entries {
            let row = try XCTUnwrap(inventoryRows.first { $0["id"] == .string(entry.id.uuidString) })
            XCTAssertEqual(row["number"], entry.number.map { .number(Double($0)) } ?? .null)
            XCTAssertEqual(row["pinned"], .bool(store.pinnedIDs.contains(entry.id)))
        }
        for row in inventoryRows {
            let id = try XCTUnwrap(row["id"]?.stringValue)
            let originalIndex = try XCTUnwrap(retained.firstIndex { $0.id.uuidString == id })
            XCTAssertEqual(row["index"], .number(Double(originalIndex)),
                           "Projection order must not redefine the original public-store index")
            XCTAssertEqual(row["title"]?.stringValue?.count, 120)
        }
        let foundationRows = try XCTUnwrap(store.consoleInventory["results"] as? [[String: Any]])
        XCTAssertEqual(foundationRows.compactMap { $0["id"] as? String },
                       expected.map { $0.id.uuidString })
        for row in foundationRows {
            let id = try XCTUnwrap(row["id"] as? String)
            XCTAssertEqual(row["index"] as? Int, retained.firstIndex { $0.id.uuidString == id })
        }
        // This is the same encoder ClientMessage.consoleInventory uses.
        // A row-count ceiling alone is not the protocol's byte ceiling;
        // the backend's bounded disclosure is still required for this frame.
        let published = ConsoleInventory(sessionID: UUID(), generation: UUID(),
                                         revision: store.consoleRevision,
                                         data: store.consoleInventoryJSON)
        let encoded = try JSONEncoder().encode(published)
        XCTAssertGreaterThan(encoded.count, 32 * 1024,
                             "The synthetic 100-row sender witness must exercise byte-budget projection")
        print("CC7aInventoryCapacityTests sender witness: rows=100 title_chars=120 wire_bytes=\(encoded.count) max_message=32768")
        XCTAssertEqual(store.results, beforeResults)
        XCTAssertEqual(store.consoleRevision, beforeRevision)
        XCTAssertEqual(store.activeID, retained[0].id)
        XCTAssertEqual(store.comparisonID, retained[1].id)
        XCTAssertEqual(store.scrollOffsets[retained[0].id], 420)
        XCTAssertEqual(store.unreadIDs, beforeUnread)
        XCTAssertEqual(store.arrivalNoticeID, beforeNotice)
    }

    func testPrivateResultsDoNotConsumeProjectionSlotsOrChangePublicIndexes() throws {
        let store = WorkspaceStore(historyLimit: 200, pinLimit: 20)
        let retained = try (0..<140).map { try result($0, private: $0.isMultiple(of: 7)) }
        for item in retained { store.receive(item, quietly: true) }
        for index in [0, 7, 9, 139] { XCTAssertTrue(store.pin(retained[index].id)) }
        let publicResults = store.results.filter { !$0.payload.isProtectedLocal }
        let expected = Array(store.recents.actionableEntries.filter { !$0.isPrivate }.prefix(100))
        let inventoryRows = try rows(store)

        XCTAssertEqual(inventoryRows.count, 100)
        XCTAssertEqual(publicResults.count, 120)
        XCTAssertEqual(store.consoleInventoryJSON["results_omitted"], .number(20),
                       "Omission counts must describe public rows only")
        XCTAssertEqual(inventoryRows.compactMap { $0["id"]?.stringValue },
                       expected.map { $0.id.uuidString })
        XCTAssertTrue(store.recents.entries.filter { !$0.isPrivate }.allSatisfy { entry in
            inventoryRows.contains { $0["id"] == .string(entry.id.uuidString) }
        })
        for row in inventoryRows {
            let id = try XCTUnwrap(row["id"]?.stringValue)
            XCTAssertEqual(row["index"], publicResults.firstIndex { $0.id.uuidString == id }
                .map { JSONValue.number(Double($0)) })
        }
        let data = try JSONEncoder().encode(store.consoleInventoryJSON)
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("PRIVATE-"))
        XCTAssertEqual(store.results.count, 140, "Inventory projection has no retention authority")
    }
}
