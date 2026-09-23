import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class ResponseResultRouterTests: XCTestCase {
    private func entry(_ id: String, _ role: String, _ text: String) throws -> ConversationEntry {
        try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
            ["id": id, "role": role, "text": text, "createdAt": 1234.0]))
    }

    func testStreamingAndToolSubturnsUpdateOneResultWithoutLosingReadingState() throws {
        let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
        let user = try entry("u1", "user", "Research this")
        router.receive([user, try entry("a1", "assistant", "Looking")], workspace: workspace, display: display)
        let result = try XCTUnwrap(workspace.activeResult)
        let panel = try XCTUnwrap(display.panels.first)
        let presentation = workspace.presentation(for: result)
        presentation.showsInspector = true
        workspace.rememberScroll(240, for: result.id)
        XCTAssertTrue(workspace.pin(result.id))
        let revision = workspace.consoleRevision
        let entries = [user, try entry("a1", "assistant", "Looking into it."),
                       try entry("a2", "assistant", "Here are the findings.")]
        router.receive(entries, workspace: workspace, display: display)
        router.receive(entries, workspace: workspace, display: display)
        XCTAssertEqual(workspace.results.count, 1)
        XCTAssertEqual(display.panels.count, 1)
        XCTAssertEqual(display.panels.first?.id, panel.id)
        XCTAssertEqual(workspace.activeResult?.payload.body, "Looking into it.\n\nHere are the findings.")
        XCTAssertEqual(display.panels.first?.payload, workspace.activeResult?.payload)
        XCTAssertEqual(workspace.activeResult?.receivedAt, result.receivedAt)
        XCTAssertEqual(workspace.scrollOffsets[result.id], 240)
        XCTAssertTrue(workspace.presentation(for: result) === presentation)
        XCTAssertEqual(workspace.consoleRevision, revision, "Streaming must not invalidate pending voice targets.")
    }

    func testIdenticalAnswersToSeparateRequestsRemainSeparateAndFollowResponses() throws {
        let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
        var entries = [try entry("u1", "user", "Hello"), try entry("a1", "assistant", "Hello.")]
        router.receive(entries, workspace: workspace, display: display)
        let firstID = workspace.activeID
        entries += [try entry("u2", "user", "Again"), try entry("a2", "assistant", "Hello.")]
        router.receive(entries, workspace: workspace, display: display)
        XCTAssertEqual(workspace.results.count, 2)
        XCTAssertEqual(display.panels.count, 2)
        XCTAssertNotEqual(workspace.activeID, firstID)
        XCTAssertFalse(workspace.showsConversation)
    }

    func testSupportingDisplayOwnsAnswerAndClosingReturnsItToMain() throws {
        let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
        display.setWindowOpen(true)
        router.receive([try entry("a1", "assistant", "Welcome.")], workspace: workspace, display: display)
        let id = try XCTUnwrap(workspace.activeID)
        XCTAssertTrue(display.isPresented(.result(id), selection: workspace.supportingContent))
        display.setWindowOpen(false)
        XCTAssertFalse(display.isPresented(.result(id), selection: workspace.supportingContent))
        XCTAssertEqual(workspace.activeResult?.payload.body, "Welcome.")
        display.setWindowOpen(true)
        XCTAssertEqual(display.panels.count, 1)
    }

    func testClosingResponseOrTileIsNotUndoneByStreaming() throws {
        let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
        let user = try entry("u1", "user", "Research")
        router.receive([user, try entry("a1", "assistant", "One")], workspace: workspace, display: display)
        display.close(id: try XCTUnwrap(display.panels.first?.id))
        router.receive([user, try entry("a1", "assistant", "One two")], workspace: workspace, display: display)
        XCTAssertTrue(display.panels.isEmpty)
        workspace.close(try XCTUnwrap(workspace.activeID))
        router.receive([user, try entry("a1", "assistant", "One two three")], workspace: workspace, display: display)
        XCTAssertTrue(workspace.results.isEmpty)
        XCTAssertTrue(display.panels.isEmpty)
    }

    func testAtlasGraphAndComparisonAreNotReplacedByReply() throws {
        for mode in ["atlas", "graph", "comparison"] {
            let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
            let research = WorkspaceResult(payload: DisplayPayload(responseText: "Research", timestamp: 1))
            let other = WorkspaceResult(payload: research.payload)
            workspace.receive(research); workspace.receive(other)
            if mode == "atlas" { workspace.openAtlas() }
            if mode == "graph" { workspace.openMemoryGraph() }
            if mode == "comparison" { workspace.compare(with: other.id) }
            router.receive([try entry("a1", "assistant", "New answer")], workspace: workspace, display: display)
            XCTAssertEqual(workspace.activeID, research.id)
            if mode == "atlas" { XCTAssertTrue(workspace.showsAtlas) }
            if mode == "graph" { XCTAssertTrue(workspace.showsMemoryGraph) }
            if mode == "comparison" { XCTAssertEqual(workspace.comparisonID, other.id) }
            XCTAssertEqual(workspace.results.count, 3)
        }
    }

    func testManyResponsesKeepStageBoundedAndHistoryAvailable() throws {
        let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
        for index in 0..<12 {
            router.receive([try entry("u\(index)", "user", "Question"),
                            try entry("a\(index)", "assistant", "Answer \(index)")],
                           workspace: workspace, display: display)
        }
        XCTAssertEqual(workspace.results.count, 12)
        XCTAssertEqual(display.panels.count, AppTuning.maxSupportingStagePanels)
        XCTAssertEqual(workspace.activeResult?.payload.body, "Answer 11")
    }

    func testEmptyAssistantDoesNotOpenResultsAndCaptionShowsLatestWords() throws {
        let router = ResponseResultRouter(), workspace = WorkspaceStore(), display = DisplayWindowStore()
        router.receive([try entry("a1", "assistant", "  ")], workspace: workspace, display: display)
        XCTAssertTrue(workspace.showsConversation)
        XCTAssertTrue(workspace.results.isEmpty)
        let text = String(repeating: "Earlier words ", count: 100) + "latest spoken words"
        let caption = ConversationStore.liveCaption(text)
        XCTAssertEqual(caption.count, 160)
        XCTAssertTrue(caption.hasSuffix("latest spoken words"))
        XCTAssertFalse(caption.contains("\n"))
    }
}
