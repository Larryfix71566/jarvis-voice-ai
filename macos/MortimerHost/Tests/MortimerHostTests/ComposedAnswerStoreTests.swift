import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class ComposedAnswerStoreTests: XCTestCase {
    private func sequences() throws -> [[DisplayPayload]] {
        var macos = URL(fileURLWithPath: #filePath)
        for _ in 0..<4 { macos.deleteLastPathComponent() }
        let path = macos.appendingPathComponent("JarvisKit/Tests/JarvisKitTests/Fixtures/composed-answer-transitions.json")
        return try JSONDecoder().decode([[DisplayPayload]].self, from: Data(contentsOf: path))
    }

    func testFiveContractSequencesPreserveDrawerIdentityAndExpansion() throws {
        for sequence in try sequences() {
            let store = DisplayResultStore()
            let workspaceID = UUID()
            store.apply(sequence[0], workspaceID: workspaceID)
            let first = try XCTUnwrap(store.results.first)
            store.expandedID = nil
            for payload in sequence.dropFirst() { store.apply(payload) }
            if sequence[0].answerID == nil {
                XCTAssertEqual(store.results.count, sequence.count)
            } else {
                XCTAssertEqual(store.results.count, 1)
                XCTAssertEqual(store.results[0].id, first.id)
                XCTAssertEqual(store.results[0].receivedAt, first.receivedAt)
                XCTAssertEqual(store.results[0].workspaceID, workspaceID)
                XCTAssertNil(store.expandedID)
                let newest = sequence.max { ($0.answerRevision ?? 0) < ($1.answerRevision ?? 0) }!
                XCTAssertEqual(store.results[0].payload, newest)
            }
        }
    }

    func testFiveContractSequencesPreserveWindowPinPlacementAndFocus() throws {
        for sequence in try sequences() where sequence[0].answerID != nil {
            let store = DisplayWindowStore()
            let id = try XCTUnwrap(store.apply(sequence[0], workspaceID: UUID()))
            XCTAssertTrue(store.pin(id: id))
            let original = try XCTUnwrap(store.panels.first)
            for payload in sequence.dropFirst() { XCTAssertEqual(store.apply(payload), id) }
            let final = try XCTUnwrap(store.panels.first)
            XCTAssertEqual(store.panels.count, 1)
            XCTAssertEqual(final.id, original.id)
            XCTAssertEqual(final.receivedAt, original.receivedAt)
            XCTAssertEqual(final.workspaceID, original.workspaceID)
            XCTAssertEqual(final.offset, original.offset)
            XCTAssertEqual(final.size, original.size)
            XCTAssertEqual(final.focused, original.focused)
            XCTAssertEqual(final.pinned, original.pinned)
            XCTAssertEqual(final.payload.answerRevision, sequence.compactMap(\.answerRevision).max())
        }
    }
}
