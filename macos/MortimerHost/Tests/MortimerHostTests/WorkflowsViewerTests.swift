import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

/// Sample data, outside the @MainActor test class: a default argument that
/// calls a main-actor static does not compile (first Mac run, 2026-09-25).
enum WorkflowFixtures {
    static let longStep = String(repeating: "A long step that must wrap in full. ", count: 9)  // 324 characters

    static func sample() -> [WorkflowDetail] {
        [
            WorkflowDetail(name: "voice-where-am-i", when: "Larry asks where he is",
                           steps: ["Call system_status", "Say the source", "Never from memory"],
                           doneWhen: ["system_status was called"], agents: ["supervisor"],
                           source: "voice-where-am-i.yaml", triggers: ["user"], priority: 15, kind: "voice"),
            WorkflowDetail(name: "voice-human-only-proposal", when: "A proposal result", steps: [longStep],
                           doneWhen: ["Larry answered"], agents: ["supervisor"],
                           source: "voice-human-only-proposal.yaml", triggers: ["result"], priority: 8, kind: "voice"),
            WorkflowDetail(name: "plan-before-implementing", when: "implementing a plan",
                           steps: ["Write the plan", "Get approval"], doneWhen: ["approved"],
                           source: "plan-before-implementing.yaml"),
            WorkflowDetail(name: "authorization-is-binding", when: "authorized work",
                           steps: ["Do what was authorized"], doneWhen: ["matches the approval"],
                           source: "authorization-is-binding.yaml"),
            WorkflowDetail(name: "user-task-website-comparison", when: "comparing three websites",
                           steps: ["comparing three websites"], source: "user-task-website-comparison.yaml",
                           draft: true),
        ]
    }

    static func response(_ workflows: [WorkflowDetail] = sample(), enabled: Bool = true) throws -> WorkflowsResponse {
        let object: [String: Any] = [
            "ok": true, "enabled": enabled, "match_threshold": 0.35,
            "workflows": try JSONSerialization.jsonObject(with: JSONEncoder().encode(workflows)),
        ]
        return try JSONDecoder().decode(WorkflowsResponse.self,
                                        from: JSONSerialization.data(withJSONObject: object))
    }
}

/// MORTIMER_WORKFLOW_VIEWER_PLAN.md piece 5 (layout C, Larry 2026-09-25):
/// the read-only workflow viewer's store, view mode, supporting-display case
/// and rendering.
@MainActor
final class WorkflowsViewerTests: XCTestCase {
    private func loadedStore() throws -> WorkflowsStore {
        let store = WorkflowsStore()
        store.apply(try WorkflowFixtures.response())
        return store
    }

    // MARK: store

    func testGroupsAndOrder() throws {
        let store = try loadedStore()
        XCTAssertEqual(store.section(.voice).map(\.name), ["voice-human-only-proposal", "voice-where-am-i"],
                       "voice sorts by priority, lowest first")
        XCTAssertEqual(store.section(.rules).map(\.name), ["authorization-is-binding", "plan-before-implementing"])
        XCTAssertEqual(store.section(.drafts).map(\.name), ["user-task-website-comparison"])
        XCTAssertEqual(store.ordered.count, 5)
        XCTAssertEqual(WorkflowGroup.allCases.map(\.title),
                       ["Voice · supervisor", "Standing rules", "Drafts · review me"])
    }

    func testFilterSearchesNameWhenAndSteps() throws {
        let store = try loadedStore()
        store.query = "approval"
        XCTAssertEqual(store.section(.rules).map(\.name), ["plan-before-implementing"])
        XCTAssertTrue(store.section(.voice).isEmpty)
        store.query = "where he is"
        XCTAssertEqual(store.section(.voice).map(\.name), ["voice-where-am-i"])
        store.query = "nothing like this"
        XCTAssertFalse(store.hasVisibleMatches)
        XCTAssertEqual(store.ordered.count, 5, "the filter never changes Next or n of N")
    }

    func testSelectNextWrapAndBack() throws {
        let store = try loadedStore()
        XCTAssertNil(store.selected)
        store.select("no-such-workflow.yaml")
        XCTAssertNil(store.selected)
        store.select("voice-human-only-proposal.yaml")
        XCTAssertEqual(store.position?.index, 1)
        XCTAssertEqual(store.position?.count, 5)
        XCTAssertEqual(store.next?.name, "voice-where-am-i")
        store.select("user-task-website-comparison.yaml")
        XCTAssertEqual(store.next?.name, "voice-human-only-proposal", "Next wraps to the first")
        store.showNext()
        XCTAssertEqual(store.selected?.name, "voice-human-only-proposal")
        store.showGallery()
        XCTAssertNil(store.selected)
    }

    func testReloadDropsASelectionThatNoLongerExists() throws {
        let store = try loadedStore()
        store.select("plan-before-implementing.yaml")
        store.apply(try WorkflowFixtures.response(Array(WorkflowFixtures.sample().prefix(2))))
        XCTAssertNil(store.selected)
    }

    func testTwoFilesWithOneNameStayDistinct() throws {
        // load_workflows() does not reject a repeated `name:`; the file is the identity.
        let twin = WorkflowDetail(name: "plan-before-implementing", when: "another file, same name",
                                  steps: ["Different step"], source: "plan-before-implementing-2.yaml")
        let store = WorkflowsStore()
        store.apply(try WorkflowFixtures.response(WorkflowFixtures.sample() + [twin]))
        XCTAssertEqual(Set(store.ordered.map(\.id)).count, 6)
        store.select("plan-before-implementing-2.yaml")
        XCTAssertEqual(store.selected?.steps, ["Different step"])
        store.showNext()
        XCTAssertNotEqual(store.selected?.id, "plan-before-implementing-2.yaml")
    }

    func testAFailedReadIsNotLoadedSoTheNextOpenRetries() async throws {
        let store = WorkflowsStore()
        let failed = try JSONDecoder().decode(WorkflowsResponse.self,
            from: Data(#"{"ok":false,"error":"could not read the workflows"}"#.utf8))
        store.apply(failed)
        XCTAssertFalse(store.loaded)
        XCTAssertEqual(store.error, "could not read the workflows")
        let full = try WorkflowFixtures.response()
        store.load { full }     // not forced: allowed, because nothing loaded
        while store.loading { await Task.yield() }
        XCTAssertTrue(store.loaded)
        XCTAssertNil(store.error)
        XCTAssertEqual(store.workflows.count, 5)
    }

    func testLoadAppliesOnceUnlessForcedAndReportsFailures() async throws {
        let store = WorkflowsStore()
        let full = try WorkflowFixtures.response()
        let smaller = try WorkflowFixtures.response(Array(WorkflowFixtures.sample().prefix(2)))
        store.load { full }
        while store.loading { await Task.yield() }
        XCTAssertTrue(store.loaded)
        XCTAssertEqual(store.workflows.count, 5)
        store.load { smaller }
        XCTAssertFalse(store.loading, "already loaded: no second fetch")
        XCTAssertEqual(store.workflows.count, 5)
        store.load(force: true) { smaller }
        while store.loading { await Task.yield() }
        XCTAssertEqual(store.workflows.count, 2, "force refetches")
        store.load(force: true) { throw URLError(.cannotConnectToHost) }
        while store.loading { await Task.yield() }
        XCTAssertNotNil(store.error)
    }

    func testWorkflowsOffIsReported() throws {
        let store = WorkflowsStore()
        store.apply(try WorkflowFixtures.response([], enabled: false))
        XCTAssertFalse(store.enabled)
        XCTAssertTrue(store.workflows.isEmpty)
    }

    func testCardSummaries() {
        let sample = WorkflowFixtures.sample()
        XCTAssertEqual(WorkflowCard(workflow: sample[0]).summary, "3 steps · priority 15")
        XCTAssertEqual(WorkflowCard(workflow: sample[2]).summary, "2 steps · 1 done-when · all specialists")
        XCTAssertEqual(WorkflowCard(workflow: sample[4]).summary, "1 step · no finish test · all specialists")
    }

    // MARK: view mode, voice and the supporting display

    func testWorkflowsIsAFourthMutuallyExclusiveMode() {
        let workspace = WorkspaceStore()
        func modes() -> [Bool] {
            [workspace.showsConversation, workspace.showsMemoryGraph, workspace.showsAtlas, workspace.showsWorkflows]
        }
        workspace.openWorkflows()
        XCTAssertEqual(modes(), [false, false, false, true])
        XCTAssertEqual(workspace.consoleInventory["mode"] as? String, "workflows")
        guard case .object(let inventory) = workspace.consoleInventoryJSON,
              case .string(let mode) = inventory["mode"] else { return XCTFail("inventory shape") }
        XCTAssertEqual(mode, "workflows")
        workspace.openAtlas()
        XCTAssertEqual(modes(), [false, false, true, false])
        workspace.openWorkflows()
        workspace.openMemoryGraph()
        XCTAssertEqual(modes(), [false, true, false, false])
        workspace.openWorkflows()
        workspace.returnToConversation()
        XCTAssertFalse(workspace.showsWorkflows)
        workspace.openWorkflows()
        workspace.returnToWorkspace()
        XCTAssertFalse(workspace.showsWorkflows)
    }

    func testClosingTheLastResultKeepsTheViewerAndComparingLeavesIt() throws {
        let workspace = WorkspaceStore()
        func result() throws -> WorkspaceResult {
            WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
                from: Data(#"{"body":"Research result","surface":"drawer"}"#.utf8)))
        }
        let only = try result()
        workspace.receive(only)
        workspace.openWorkflows()
        workspace.close(only.id)
        XCTAssertTrue(workspace.showsWorkflows)
        XCTAssertFalse(workspace.showsConversation, "one view at a time")
        let a = try result(), b = try result()
        workspace.receive(a); workspace.receive(b)
        workspace.select(a.id)
        workspace.openWorkflows()
        XCTAssertTrue(workspace.compare(with: b.id))
        XCTAssertFalse(workspace.showsWorkflows, "the comparison must be visible")
    }

    func testEveryModeVoiceIsToldAboutIsAccepted() throws {
        // config/console_view_modes.json is also what jarvis/bot/console_actions.py
        // puts in console_action's description, so the two cannot drift.
        let url = GraphFixture.repositoryRoot().appendingPathComponent("config/console_view_modes.json")
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let modes = try XCTUnwrap(object["view_set"] as? [String])
        XCTAssertTrue(modes.contains("workflows"))
        for mode in modes {
            let workspace = WorkspaceStore()
            let drawer = DrawerState()
            let coordinator = ConsoleActionCoordinator(
                workspace: workspace, display: DisplayWindowStore(),
                placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
                atlas: AtlasStore(), panels: PanelStore(), drawer: drawer)
            let request = ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                         revision: workspace.consoleRevision, action: .viewSet,
                                         target: nil, secondaryTarget: nil, args: ["mode": .string(mode)])
            XCTAssertEqual(coordinator.execute(request), .applied, mode)
        }
        let workspace = WorkspaceStore()
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
            atlas: AtlasStore(), panels: PanelStore(), drawer: drawer)
        XCTAssertEqual(coordinator.executePointer(.viewSet, target: "workflows"), .applied)
        XCTAssertTrue(workspace.showsWorkflows)
        XCTAssertEqual(coordinator.executePointer(.viewSet, target: "not-a-mode"), .invalid)
    }

    func testWorkflowsGoToTheSupportingDisplayAsTheirOwnTile() {
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        XCTAssertTrue(workspace.sendToDisplay(.workflows))
        XCTAssertEqual(workspace.supportingContent, .workflows)
        XCTAssertEqual(display.supplementalContent(.workflows), .workflows)
        XCTAssertFalse(display.isPresented(.workflows, selection: .workflows), "closed window shows nothing")
        display.setWindowOpen(true)
        XCTAssertTrue(display.isPresented(.workflows, selection: .workflows))
        XCTAssertFalse(display.isPresented(.workflows, selection: .memoryGraph))
    }

    // MARK: rendering

    func testGalleryAndFlowRender() throws {
        _ = NSApplication.shared
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: "synthetic"))
        let store = try loadedStore()
        for (label, selection) in [("gallery", nil), ("flow", "voice-human-only-proposal.yaml"),
                                   ("draft", "user-task-website-comparison.yaml")] as [(String, String?)] {
            if let selection { store.select(selection) } else { store.showGallery() }
            let view = NSHostingView(rootView: WorkflowsView(store: store, api: nil)
                .environmentObject(client)
                .foregroundStyle(AppTheme.text).preferredColorScheme(.dark)
                .background(AppTheme.bg))
            view.frame = NSRect(x: 0, y: 0, width: 1000, height: 560)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let data = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            XCTAssertGreaterThan(data.count, 1000, label)
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try data.write(to: directory.appendingPathComponent("workflows-\(label).png"))
        }
        XCTAssertEqual(WorkflowFixtures.longStep.count, 324)
    }
}
