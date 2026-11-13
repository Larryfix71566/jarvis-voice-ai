import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class ComposedWorkspaceIdentityTests: XCTestCase {
    private func sequences() throws -> [[DisplayPayload]] {
        var macos = URL(fileURLWithPath: #filePath)
        for _ in 0..<4 { macos.deleteLastPathComponent() }
        return try JSONDecoder().decode([[DisplayPayload]].self, from: Data(contentsOf:
            macos.appendingPathComponent("JarvisKit/Tests/JarvisKitTests/Fixtures/composed-answer-transitions.json")))
    }

    func testFiveSequencesPreserveWorkspaceIdentityAndReaderState() throws {
        for sequence in try sequences() {
            let store = WorkspaceStore()
            let first = WorkspaceResult(payload: sequence[0])
            store.receive(first, answersCurrentRequest: true)
            store.select(first.id)
            _ = store.pin(first.id)
            store.rememberScroll(42, for: first.id)
            for payload in sequence.dropFirst() { store.receive(WorkspaceResult(payload: payload)) }
            if sequence[0].answerID == nil {
                XCTAssertEqual(store.results.count, sequence.count)
            } else {
                XCTAssertEqual(store.results.count, 1)
                XCTAssertEqual(store.activeID, first.id)
                XCTAssertEqual(store.results[0].receivedAt, first.receivedAt)
                XCTAssertEqual(store.results[0].payload.answerRevision, sequence.compactMap(\.answerRevision).max())
                XCTAssertTrue(store.pinnedIDs.contains(first.id))
                XCTAssertEqual(store.scrollOffsets[first.id], 42)
                XCTAssertFalse(store.updatedIDs.contains(first.id))
            }
        }
    }

    func testRevisionMarkersReplayAndSupportingOwnership() throws {
        let sequence = try sequences()[0]
        let store = WorkspaceStore()
        let first = WorkspaceResult(payload: sequence[0])
        store.receive(first, answersCurrentRequest: true)
        _ = store.sendToDisplay(.result(first.id))
        let other = WorkspaceResult(payload: DisplayPayload(responseText: "Other", timestamp: 1))
        store.receive(other, answersCurrentRequest: true)
        store.select(other.id)
        let update = try XCTUnwrap(store.applyAnswerRevision(sequence[1]))
        XCTAssertTrue(update.applied)
        XCTAssertTrue(store.updatedIDs.contains(first.id))
        XCTAssertEqual(store.activeID, other.id)
        XCTAssertEqual(store.supportingContent, .result(first.id))
        let revision = store.consoleRevision
        XCTAssertFalse(try XCTUnwrap(store.applyAnswerRevision(sequence[0])).applied)
        XCTAssertEqual(store.consoleRevision, revision)
        store.select(first.id)
        XCTAssertFalse(store.updatedIDs.contains(first.id))
    }

    func testCompletionOnlyDoesNotMarkUpdated() throws {
        let sequence = try sequences()[0]
        let first = sequence[0]
        let encoderData = try Data(contentsOf: fixtureURL())
        var raw = try XCTUnwrap(JSONSerialization.jsonObject(with: encoderData) as? [[[String: Any]]])[0][0]
        raw["answer_revision"] = 2
        var layout = try XCTUnwrap(raw["layout"] as? [String: Any])
        layout["revision"] = 2; layout["complete"] = true; raw["layout"] = layout
        let completed = try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: raw))
        let store = WorkspaceStore()
        let result = WorkspaceResult(payload: first)
        store.receive(result)
        let other = WorkspaceResult(payload: DisplayPayload(responseText: "Other", timestamp: 1))
        store.receive(other); store.select(other.id)
        XCTAssertFalse(try XCTUnwrap(store.applyAnswerRevision(completed)).contentChanged)
        XCTAssertTrue(store.updatedIDs.isEmpty)
    }

    private func fixtureURL() -> URL {
        var macos = URL(fileURLWithPath: #filePath)
        for _ in 0..<4 { macos.deleteLastPathComponent() }
        return macos.appendingPathComponent("JarvisKit/Tests/JarvisKitTests/Fixtures/composed-answer-transitions.json")
    }
}
