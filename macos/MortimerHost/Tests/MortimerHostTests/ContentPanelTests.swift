import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class ContentPanelTests: XCTestCase {
    func testPointerGraphSharesFullStageWithoutHidingDisplacedResult() throws {
        let store = DisplayWindowStore()
        store.setWindowOpen(true)
        var ids: [UUID] = []
        for index in 1...4 {
            let id = UUID()
            ids.append(id)
            store.apply(try payload(title: "Result \(index)"), workspaceID: id)
        }
        let selection = SupportingDisplayContent.memoryGraph
        XCTAssertEqual(store.supplementalContent(selection), selection)
        let visible = store.stagePanels(selection: selection)
        XCTAssertEqual(visible.count, 3, "graph reserves one of the four tiles")
        XCTAssertTrue(store.isPresented(.memoryGraph, selection: selection))
        for id in ids {
            XCTAssertEqual(store.isPresented(.result(id), selection: selection),
                           visible.contains { $0.allWorkspaceIDs.contains(id) })
        }
        XCTAssertEqual(store.panels.count, 4, "selection does not delete stored results")
        store.setWindowOpen(false)
        XCTAssertFalse(store.isPresented(.memoryGraph, selection: selection))
        XCTAssertTrue(ids.allSatisfy { !store.isPresented(.result($0), selection: selection) })
        store.setWindowOpen(true)
        XCTAssertEqual(store.stagePanels(selection: selection).map(\.id), visible.map(\.id))
    }

    func testAllVisibleResultsHaveLocatorsAndRepeatSelectionDoesNotDuplicate() throws {
        let store = DisplayWindowStore()
        store.setWindowOpen(true)
        let first = UUID(), second = UUID()
        store.apply(try payload(title: "First"), workspaceID: first)
        store.apply(try payload(title: "Second"), workspaceID: second)
        let selection = SupportingDisplayContent.result(second)
        XCTAssertNil(store.supplementalContent(selection))
        XCTAssertEqual(store.stagePanels(selection: selection).count, 2)
        XCTAssertTrue(store.isPresented(.result(first), selection: selection))
        XCTAssertTrue(store.isPresented(.result(second), selection: selection))
        XCTAssertFalse(store.isPresented(.result(first), selection: selection, layoutVersion: 1),
                       "adaptive rollback shows only its selected supporting result")
        XCTAssertTrue(store.isPresented(.result(second), selection: selection, layoutVersion: 1))
        let pointerOnly = SupportingDisplayContent.result(UUID())
        XCTAssertEqual(store.supplementalContent(pointerOnly), pointerOnly)
        XCTAssertTrue(store.isPresented(pointerOnly, selection: pointerOnly))
    }

    private func payload(title: String = "Research", body: String = "body",
                         agent: String? = nil, runID: String? = nil) throws -> DisplayPayload {
        let object: [String: String] = [
            "kind": "text", "title": title, "body": body, "surface": "window",
        ].merging(agent.map { ["agent": $0] } ?? [:]) { _, new in new }
            .merging(runID.map { ["run_id": $0] } ?? [:]) { _, new in new }
        return try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: object))
    }

    func testDisplayPanelsKeepIdentityAndRespectBounds() throws {
        let store = DisplayWindowStore()
        store.apply(try payload(), workspaceID: UUID())
        let repeated = store.apply(try payload(), workspaceID: UUID())
        XCTAssertEqual(store.panels.count, 1, "an exact repeat reuses the existing renderer")
        XCTAssertEqual(store.focusedID, repeated)
        let id = try XCTUnwrap(store.panels.first?.id)
        store.resize(id: id, to: CGSize(width: 10, height: 10))
        XCTAssertEqual(store.panels.first?.size, DisplayWindowStore.minPanelSize)
        store.move(id: id, by: CGSize(width: 20, height: 15))
        XCTAssertEqual(store.panels.first?.offset, CGSize(width: 20, height: 15))
        store.close(id: id)
        XCTAssertEqual(store.panels.count, 0)
    }

    func testAdditionalPanelRequiresExplicitPinAction() throws {
        let store = DisplayWindowStore()
        let id = store.apply(try payload())
        XCTAssertTrue(store.pin(id: id))
        let duplicate = try XCTUnwrap(store.openAdditional(id: id))
        XCTAssertNotEqual(duplicate, id)
        XCTAssertEqual(store.panels.count, 2)
        XCTAssertTrue(store.panels.allSatisfy(\.pinned))
        XCTAssertEqual(store.focusedID, duplicate)

        _ = store.apply(try payload())
        XCTAssertEqual(store.panels.count, 2, "repeated delivery must not fan out pinned copies")
    }

    func testSupportingDisplaySharesBoundedUnpinnedPresentations() throws {
        let store = DisplayWindowStore()
        store.setWindowOpen(true)
        _ = store.apply(try payload(title: "First"))
        let second = store.apply(try payload(title: "Second"))
        XCTAssertEqual(store.panels.count, 2)
        XCTAssertEqual(store.panels.last?.id, second)
        XCTAssertEqual(store.defaultPresentationPanelCount, 2)
        XCTAssertEqual(store.activePresentationPanelID, second)
    }

    func testSupportingStageCapsUnpinnedResultsAndKeepsNewestFocused() throws {
        let store = DisplayWindowStore()
        store.setWindowOpen(true)
        for index in 1...(AppTuning.maxSupportingStagePanels + 1) {
            _ = store.apply(try payload(title: "Result " + String(index)))
        }

        XCTAssertEqual(store.defaultPresentationPanelCount, AppTuning.maxSupportingStagePanels)
        XCTAssertEqual(store.presentationPanels.count, AppTuning.maxSupportingStagePanels)
        XCTAssertEqual(store.presentationPanels.first?.payload.title,
                       "Result " + String(AppTuning.maxSupportingStagePanels + 1),
                       "the newly focused result must remain the first tile")
        XCTAssertFalse(store.presentationPanels.contains { $0.payload.title == "Result 1" },
                       "the oldest unpinned result is the only one evicted at the stage budget")
    }

    func testClosedDisplayAlsoKeepsFallbackStageBounded() throws {
        let store = DisplayWindowStore()
        // No supporting scene is open: this is the one-screen / fallback
        // path. It must obey the same curated-stage budget so attaching a
        // monitor later cannot fan out every historical result.
        for index in 1...(AppTuning.maxSupportingStagePanels + 2) {
            _ = store.apply(try payload(title: "Fallback \(index)"))
        }

        XCTAssertEqual(store.defaultPresentationPanelCount, AppTuning.maxSupportingStagePanels)
        XCTAssertEqual(store.presentationPanels.count, AppTuning.maxSupportingStagePanels)
        XCTAssertEqual(store.presentationPanels.first?.payload.title,
                       "Fallback \(AppTuning.maxSupportingStagePanels + 2)")
    }

    func testOpeningSupportingDisplayPreservesBoundedUnpinnedPanelsAndPins() throws {
        let store = DisplayWindowStore()
        _ = store.apply(try payload(title: "First"))
        let second = store.apply(try payload(title: "Second"))
        XCTAssertTrue(store.pin(id: second))
        _ = store.apply(try payload(title: "Third"))
        XCTAssertEqual(store.panels.count, 3)

        store.setWindowOpen(true)
        XCTAssertEqual(store.panels.filter { !$0.pinned }.count, 2)
        XCTAssertEqual(store.panels.filter(\.pinned).count, 1)
        XCTAssertEqual(store.defaultPresentationPanelCount, 2)
    }

    func testSupportingStageLeavesPinnedCopiesAsExplicitExtras() throws {
        let store = DisplayWindowStore()
        let first = store.apply(try payload(title: "First"))
        XCTAssertEqual(store.activePresentationPanelID, first)
        XCTAssertTrue(store.pin(id: first))
        let second = try XCTUnwrap(store.openAdditional(id: first))

        XCTAssertNil(store.activePresentationPanelID,
                     "when every panel is explicitly pinned, the default stage is empty")
        XCTAssertTrue(store.presentationPanels.isEmpty,
                      "pinned overflow must not consume the curated stage")
        XCTAssertEqual(store.panels.filter { $0.id != second }.count, 1)
        XCTAssertTrue(store.panels.first(where: { $0.id == first })?.pinned == true)
    }

    func testPinnedPanelStaysOutsideStageWhenUnpinnedResultsRemain() throws {
        let store = DisplayWindowStore()
        let pinned = store.apply(try payload(title: "Pinned"))
        XCTAssertTrue(store.pin(id: pinned))
        _ = store.apply(try payload(title: "Current"))

        XCTAssertEqual(store.presentationPanels.map { $0.payload.title }, ["Current"])
        XCTAssertEqual(store.panels.filter { !$0.pinned }.count, 1)
        XCTAssertEqual(store.panels.filter(\.pinned).count, 1)
    }

    func testPanelCapacityRetiresUnpinnedBeforePinnedContent() throws {
        let store = DisplayWindowStore()
        var pinnedIDs: [Int] = []
        for index in 0..<AppTuning.maxDisplayWindowPanels {
            let id = store.apply(try payload(title: "Pinned \(index)"))
            XCTAssertTrue(store.pin(id: id))
            pinnedIDs.append(id)
        }

        let rejected = store.openAdditional(id: pinnedIDs[0])
        XCTAssertNil(rejected, "a full pinned inventory must reject an extra copy")
        XCTAssertEqual(store.panels.count, AppTuning.maxDisplayWindowPanels)
        XCTAssertEqual(Set(store.panels.map(\.id)), Set(pinnedIDs))
        XCTAssertTrue(store.panels.allSatisfy(\.pinned))
    }

    func testDeveloperRunAppendsDistinctResultsIntoOneDisplayPanel() throws {
        let store = DisplayWindowStore()
        let firstWorkspaceID = UUID()
        let secondWorkspaceID = UUID()
        let first = try payload(title: "README", agent: "Developer", runID: "run-1")
        let second = try payload(title: "ROADMAP", agent: "Developer", runID: "run-1")

        let panelID = store.apply(first, workspaceID: firstWorkspaceID)
        let appendedID = store.apply(second, workspaceID: secondWorkspaceID)

        XCTAssertEqual(appendedID, panelID)
        XCTAssertEqual(store.panels.count, 1)
        XCTAssertEqual(store.panels.first?.allPayloads.map(\.title), ["README", "ROADMAP"])
        XCTAssertTrue(store.containsWorkspaceResult(firstWorkspaceID))
        XCTAssertTrue(store.containsWorkspaceResult(secondWorkspaceID))
    }

    func testExactRepeatReusesTheExistingWorkspaceOwnerButNewRunSectionDoesNot() throws {
        let store = DisplayWindowStore()
        let first = try payload(title: "README", agent: "Developer", runID: "run-1")
        let second = try payload(title: "ROADMAP", agent: "Developer", runID: "run-1")
        let firstID = UUID()
        let secondID = UUID()

        _ = store.apply(first, workspaceID: firstID)
        XCTAssertEqual(store.presentedWorkspaceID(for: first), firstID)
        XCTAssertNil(store.presentedWorkspaceID(for: second),
                     "a new file in the same run still needs its own history row")

        _ = store.apply(second, workspaceID: secondID)
        XCTAssertEqual(store.presentedWorkspaceID(for: second), secondID)
        XCTAssertEqual(store.presentedWorkspaceID(for: first), firstID)

        let replacementID = UUID()
        _ = store.apply(first, workspaceID: replacementID)
        XCTAssertEqual(store.presentedWorkspaceID(for: first), replacementID,
                        "a stale workspace owner can be repaired without another panel")
        XCTAssertEqual(store.panels.count, 1)
    }

    func testSeparateDeveloperRunsRemainSeparateDisplayPanels() throws {
        let store = DisplayWindowStore()
        _ = store.apply(try payload(title: "README", agent: "Developer", runID: "run-1"))
        _ = store.apply(try payload(title: "README", agent: "Developer", runID: "run-2"))
        XCTAssertEqual(store.panels.count, 2)
    }

    func testFitRequiresMeasuredViewportAndPreservesReachablePanel() throws {
        let store = DisplayWindowStore()
        store.apply(try payload())
        let id = try XCTUnwrap(store.panels.first?.id)
        let originalSize = store.panels.first?.size
        store.fit(id: id)
        XCTAssertEqual(store.panels.first?.size, originalSize)
        store.viewportSize = CGSize(width: 900, height: 700)
        store.fit(id: id)
        XCTAssertEqual(store.panels.first?.offset, .zero)
        XCTAssertNotNil(store.panels.first?.size)
    }

    func testLastSupportingPanelCanReturnOwnershipToMainWorkspace() throws {
        let workspace = WorkspaceStore()
        let resultPayload = try payload(title: "Research result")
        let result = WorkspaceResult(payload: resultPayload)
        workspace.receive(result)
        XCTAssertTrue(workspace.sendToDisplay(.result(result.id)))

        let display = DisplayWindowStore()
        let panelID = display.apply(resultPayload, workspaceID: result.id)
        XCTAssertEqual(display.panels.count, 1)

        // This mirrors the last-panel close action in SingleDisplayPanel.
        display.close(id: panelID)
        if display.panels.isEmpty {
            workspace.showOriginalDisplayPanels()
        }

        XCTAssertTrue(display.panels.isEmpty)
        XCTAssertNil(workspace.supportingContent)
        XCTAssertEqual(workspace.supportingResult, nil)
    }

    func testMainLocatorRequiresALiveSupportingPanel() throws {
        let display = DisplayWindowStore()
        let workspace = WorkspaceStore()
        let resultPayload = try payload(title: "Research result")
        let result = WorkspaceResult(payload: resultPayload)
        workspace.receive(result)
        XCTAssertTrue(workspace.sendToDisplay(.result(result.id)))
        display.setWindowOpen(true)

        XCTAssertFalse(display.containsWorkspaceResult(result.id),
                       "a stale workspace assignment must not claim an empty display")
        _ = display.apply(resultPayload, workspaceID: result.id)
        XCTAssertTrue(display.containsWorkspaceResult(result.id))
    }
}
