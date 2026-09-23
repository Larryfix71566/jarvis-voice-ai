import XCTest
import AppKit
import JarvisKit
@testable import MortimerHost

@MainActor
final class ConsoleActionCoordinatorTests: XCTestCase {
    private func request(_ action: ConsoleAction, target: String? = nil,
                         secondary: String? = nil,
                         args: [String: JSONValue] = [:], revision: Int = 0) -> ConsoleRequest {
        ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                       revision: revision, action: action, target: target,
                       secondaryTarget: secondary, args: args)
    }

    private func coordinator() -> (ConsoleActionCoordinator, WorkspaceStore, AtlasStore, PanelStore, DrawerState) {
        let workspace = WorkspaceStore()
        let atlas = AtlasStore()
        let panels = PanelStore()
        let drawer = DrawerState()
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement,
                                                    atlas: atlas, panels: panels,
                                                    drawer: drawer)
        return (coordinator, workspace, atlas, panels, drawer)
    }

    private func result(title: String = "Research") -> WorkspaceResult {
        let data = "{\"title\":\"(title)\",\"body\":\"Evidence\"}".data(using: .utf8)!
        let payload = try! JSONDecoder().decode(DisplayPayload.self, from: data)
        return WorkspaceResult(payload: payload)
    }

    func testViewSetAndResultModeUseTheSharedWorkspaceOwner() {
        let (coordinator, workspace, _, _, _) = coordinator()
        let item = result(); workspace.receive(item)

        XCTAssertEqual(coordinator.execute(request(.viewSet, target: "atlas", revision: workspace.consoleRevision)), .applied)
        XCTAssertTrue(workspace.showsAtlas)
        XCTAssertEqual(coordinator.execute(request(.resultMode, target: item.id.uuidString,
            args: ["mode": .string("sources")], revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(workspace.presentation(for: item).mode, .sources)
    }

    func testViewSetUsesTheCatalogModeArgumentWithoutRequiringATarget() {
        let (coordinator, workspace, _, _, _) = coordinator()
        XCTAssertEqual(coordinator.execute(request(.viewSet,
            args: ["mode": .string("atlas")])), .applied)
        XCTAssertTrue(workspace.showsAtlas)
    }

    func testPointerHelperUsesTheSameDispatcherAsVoiceRequests() {
        let (coordinator, workspace, _, _, _) = coordinator()
        XCTAssertEqual(coordinator.executePointer(.viewSet, target: "atlas"), .applied)
        XCTAssertTrue(workspace.showsAtlas)
    }

    func testAtlasGroupingAndOrderingAreDeterministic() {
        let (coordinator, _, atlas, _, _) = coordinator()
        let a = result(title: "A"), b = result(title: "B")
        atlas.replace([AtlasCard(id: a.id, title: "A", summary: "", source: nil),
                      AtlasCard(id: b.id, title: "B", summary: "", source: nil)])
        XCTAssertEqual(coordinator.execute(request(.groupCreate, target: "work")), .applied)
        XCTAssertEqual(coordinator.execute(request(.groupAssign, target: a.id.uuidString,
            args: ["group": .string("work")])), .applied)
        XCTAssertEqual(atlas.groups["work"], Set([a.id]))
        XCTAssertEqual(coordinator.execute(request(.atlasMove, target: b.id.uuidString,
            secondary: a.id.uuidString, args: ["relation": .string("before")])), .applied)
        XCTAssertEqual(atlas.cards.map(\.id), [b.id, a.id])
    }

    func testPanelAndSidecarActionsUseExistingStateOwners() {
        let (coordinator, workspace, _, panels, drawer) = coordinator()
        XCTAssertEqual(coordinator.execute(request(.panelDetach, target: "atlas",
                                                   revision: workspace.consoleRevision)), .applied)
        XCTAssertTrue(panels.detached.contains(.atlas))
        XCTAssertEqual(coordinator.execute(request(.panelFocus, target: "memory",
                                                   revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.focused, .memory)
        XCTAssertEqual(coordinator.execute(request(.sidecarWidth,
            args: ["points": .number(680)], revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(drawer.width, 680)
    }

    func testPanelDetachAndMoveOpenValueAddressedWindow() {
        let workspace = WorkspaceStore()
        let panels = PanelStore()
        let drawer = DrawerState()
        let actions = WindowActions()
        var opened: [ConsolePanel] = []
        actions.openPanel = { opened.append($0) }
        let placement = WindowPlacement(drawer: drawer, windows: actions)
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement, panels: panels)

        XCTAssertEqual(coordinator.execute(request(.panelDetach, target: "atlas",
                                                   revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(coordinator.execute(request(.panelMove, target: "memory",
            secondary: "display-2", revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(opened, [.atlas, .memory])
        XCTAssertEqual(panels.screenByPanel[.memory], "display-2")
    }

    func testDynamicContentPanelUsesStableIdentityAndDoesNotDuplicate() {
        let (coordinator, workspace, _, panels, _) = coordinator()
        let item = result(); workspace.receive(item)
        let target = "result:\(item.id.uuidString)"
        XCTAssertEqual(coordinator.execute(request(.panelDetach, target: target,
                                                    revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.contentRecords.count, 1)
        guard let id = panels.contentRecords.keys.first else {
            return XCTFail("dynamic panel should have a stable UUID")
        }
        XCTAssertEqual(coordinator.execute(request(.panelDetach, target: target,
                                                    revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.contentRecords.count, 1, "repeated detach focuses existing content")
        XCTAssertEqual(coordinator.execute(request(.panelMove, target: id.rawValue.uuidString,
                                                    secondary: "display-2",
                                                    revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.contentRecord(id)?.screenID, "display-2")
        XCTAssertEqual(coordinator.execute(request(.panelReturn, target: id.rawValue.uuidString,
                                                    revision: workspace.consoleRevision)), .applied)
        XCTAssertTrue(panels.contentRecords.isEmpty)

        for index in 0..<PanelStore.maxContentPanels {
            XCTAssertEqual(coordinator.execute(request(.panelDetach,
                target: "memory:graph-\(index)", revision: workspace.consoleRevision)), .applied)
        }
        XCTAssertEqual(panels.contentRecords.count, PanelStore.maxContentPanels)
        XCTAssertEqual(coordinator.execute(request(.panelDetach, target: "content:transcript",
                                                    revision: workspace.consoleRevision)), .capacity)
        XCTAssertEqual(panels.contentRecords.count, PanelStore.maxContentPanels)
    }

    func testReturnAllDismissesEveryValueAddressedPanelWindow() {
        let workspace = WorkspaceStore()
        let panels = PanelStore()
        let drawer = DrawerState()
        let actions = WindowActions()
        var dismissCount = 0
        actions.dismissAllPanels = { dismissCount += 1 }
        let placement = WindowPlacement(drawer: drawer, windows: actions)
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement, panels: panels)
        panels.detach(.atlas); panels.detach(.memory)

        XCTAssertEqual(coordinator.execute(request(.panelsReturnAll)), .applied)
        XCTAssertEqual(dismissCount, 1)
        XCTAssertTrue(panels.detached.isEmpty)
    }

    func testInvalidTargetsNeverMutateState() {
        let (coordinator, workspace, _, panels, _) = coordinator()
        XCTAssertEqual(coordinator.execute(request(.resultClose, target: UUID().uuidString)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.graphSelect, target: "missing")), .invalid)
        XCTAssertEqual(coordinator.execute(request(.panelDetach, target: "unknown")), .invalid)
        XCTAssertTrue(workspace.results.isEmpty)
        XCTAssertTrue(panels.detached.isEmpty)
    }

    func testStaleRevisionAndUnknownArgumentsNeverMutateState() {
        let (coordinator, workspace, _, _, _) = coordinator()
        let item = result(); workspace.receive(item)
        let stale = ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                    revision: workspace.consoleRevision - 1,
                                    action: .resultClose, target: item.id.uuidString)
        XCTAssertEqual(coordinator.execute(stale), .stale)
        XCTAssertEqual(workspace.results.count, 1)
        let malformed = request(.viewSet, target: "atlas", args: ["unexpected": .string("x")],
                                revision: workspace.consoleRevision)
        XCTAssertEqual(coordinator.execute(malformed), .invalid)
        XCTAssertFalse(workspace.showsAtlas)
        let nonFinite = request(.sidecarWidth, args: ["points": .number(.infinity)],
                                revision: workspace.consoleRevision)
        XCTAssertEqual(coordinator.execute(nonFinite), .invalid)
    }

    func testSharePreviewAndCopyUseTheFrozenResult() {
        let workspace = WorkspaceStore()
        let sharing = ShareCoordinator()
        let drawer = DrawerState()
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement, sharing: sharing)
        let item = result(); workspace.receive(item)
        XCTAssertEqual(coordinator.execute(request(.sharePreview, target: item.id.uuidString,
                                                   revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(sharing.preview?.resultID, item.id)
        XCTAssertEqual(coordinator.execute(request(.sharePreview, target: item.id.uuidString,
            args: ["scope": .string("section"), "ordinal": .number(2)],
            revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(sharing.preview?.text, "Evidence\n")
        XCTAssertEqual(coordinator.execute(request(.shareCopy, revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(sharing.status, "copied")
        XCTAssertEqual(coordinator.execute(request(.shareCancel, revision: workspace.consoleRevision)), .applied)
        XCTAssertNil(sharing.preview)
    }

    func testExtendedResultAtlasPanelAndSidecarActionsUseSharedState() {
        let (coordinator, workspace, atlas, panels, drawer) = coordinator()
        let item = result(); workspace.receive(item)
        XCTAssertEqual(coordinator.execute(request(.contentScroll, target: item.id.uuidString,
            args: ["direction": .string("down"), "viewport": .number(500)],
            revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(workspace.scrollOffsets[item.id], 400)
        XCTAssertEqual(coordinator.execute(request(.compareSide, target: "B", revision: workspace.consoleRevision)), .noop)
        XCTAssertEqual(coordinator.execute(request(.atlasZoom, target: "in", revision: workspace.consoleRevision)), .applied)
        XCTAssertGreaterThan(atlas.zoomScale, 1)
        XCTAssertEqual(coordinator.execute(request(.atlasPan, target: "right", revision: workspace.consoleRevision)), .applied)
        XCTAssertNotEqual(atlas.panOffset, .zero)
        XCTAssertEqual(coordinator.execute(request(.panelMove, target: "atlas", secondary: "display-2", revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.screenByPanel[.atlas], "display-2")
        XCTAssertEqual(coordinator.execute(request(.sidecarText, target: "22", revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(UserDefaults.standard.double(forKey: "mortimer.interface.sidecarTabTextSize"), 22)
        XCTAssertEqual(coordinator.execute(request(.sidecarScrollTabs, target: "right", revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(drawer.tabScrollDirection, 1)
    }

    func testGraphActionsRejectUnknownIdentitiesAndOutOfBoundsCoordinates() async throws {
        let (coordinator, workspace, _, _, _) = coordinator()
        let graph = try GraphFixture.make()
        workspace.memoryGraph.load { _ in graph }
        for _ in 0..<200 where workspace.memoryGraph.loading {
            try await Task.sleep(nanoseconds: 5_000_000)
        }
        XCTAssertFalse(workspace.memoryGraph.loading)
        let revision = workspace.consoleRevision

        XCTAssertEqual(coordinator.execute(request(.graphPath, target: "missing",
            secondary: "fact:1", revision: revision)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.graphFilter, target: "missing",
            args: ["kind": .string("node"), "visible": .bool(false)], revision: revision)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.graphGroup, target: "missing",
            args: ["collapsed": .bool(true)], revision: revision)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.graphFocus, target: "fact:2",
            args: ["depth": .number(3)], revision: revision)), .applied)
        for _ in 0..<200 where workspace.memoryGraph.loading {
            try await Task.sleep(nanoseconds: 5_000_000)
        }
        XCTAssertFalse(workspace.memoryGraph.loading)
        XCTAssertEqual(workspace.memoryGraph.metadata.query.focus, "fact:2")
        XCTAssertEqual(workspace.memoryGraph.metadata.query.depth, 3)
        XCTAssertEqual(coordinator.execute(request(.graphZoom, target: "sideways",
            revision: revision)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.graphPan, target: "sideways",
            revision: revision)), .invalid)

        let before = workspace.memoryGraph.metadata.positions["fact:1"]
        XCTAssertEqual(coordinator.execute(request(.graphMoveNode, target: "fact:1",
            args: ["x": .number(1_000_001), "y": .number(0)], revision: revision)), .invalid)
        XCTAssertEqual(workspace.memoryGraph.metadata.positions["fact:1"], before)
        XCTAssertEqual(coordinator.execute(request(.graphMoveNode, target: "fact:1",
            args: ["x": .number(500), "y": .number(-300)], revision: revision)), .applied)
        XCTAssertEqual(workspace.memoryGraph.metadata.positions["fact:1"], CGPoint(x: 500, y: -300))
    }

    func testInputAndPresentationActionsRemainBoundedAndTruthful() {
        let (_, workspace, _, _, _) = coordinator()
        let attachments = AttachmentStore()
        let notices = ConsoleNoticeState()
        let drawer = DrawerState()
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let routed = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
                                              placement: placement, attachments: attachments,
                                              notices: notices)
        XCTAssertEqual(routed.execute(request(.inputQuestion,
            args: ["question": .string(String(repeating: "q", count: 2000))])), .applied)
        XCTAssertEqual(attachments.question.count, 2000)
        XCTAssertEqual(routed.execute(request(.inputPreview)), .applied)
        XCTAssertTrue(attachments.previewVisible)
        XCTAssertEqual(routed.execute(request(.inputCancel)), .applied)
        XCTAssertEqual(routed.execute(request(.consoleCaption, args: ["expanded": .bool(false)])), .applied)
        XCTAssertFalse(notices.captionExpanded)
        XCTAssertEqual(routed.execute(request(.consoleStatus, args: ["open": .bool(false)])), .applied)
        XCTAssertFalse(notices.statusOpen)
        XCTAssertEqual(routed.execute(request(.appearanceSet, target: "2")), .applied)
        XCTAssertEqual(UserDefaults.standard.integer(forKey: "mortimer.interface.layoutVersion"), 2)
        XCTAssertEqual(routed.execute(request(.waveTuningSet, args: ["key": .string("width"), "value": .number(0.2)])), .applied)
        XCTAssertEqual(routed.execute(request(.waveTuningSet, args: ["key": .string("width"), "value": .number(4)])), .invalid)
        attachments.clear()
    }
}
