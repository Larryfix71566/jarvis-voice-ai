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

    func testSkillsViewSetUsesTheSharedWorkspaceOwner() {
        let (coordinator, workspace, _, _, _) = coordinator()
        XCTAssertEqual(coordinator.execute(request(.viewSet,
            args: ["mode": .string("skills")])), .applied)
        XCTAssertTrue(workspace.showsSkills)
        XCTAssertFalse(workspace.showsConversation)
        XCTAssertFalse(workspace.showsAtlas)
        XCTAssertEqual(workspace.consoleInventory["mode"] as? String, "skills")
    }

    func testPointerSkillSelectionUsesCoordinatorDispatcherAndPublishesMutation() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        skills.updateCatalog([.object([
            "skill_id": .string("pointer-skill"), "display_name": .string("Pointer skill"),
            "category": .string("development"), "installation": .string("installed"),
            "enabled": .bool(true), "readiness": .string("ready"),
        ])])
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()),
            skills: skills)
        let startRevision = workspace.consoleRevision

        XCTAssertEqual(coordinator.executePointer(.skillSelect, target: "pointer-skill"), .applied)
        XCTAssertEqual(skills.selectedSkillID, "pointer-skill")
        XCTAssertGreaterThan(workspace.consoleRevision, startRevision)
    }

    func testSkillDisplayTransferRequiresTheCurrentlySelectedSkill() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        skills.updateCatalog([.object([
            "skill_id": .string("display-skill"), "display_name": .string("Display skill"),
            "category": .string("development"), "installation": .string("installed"),
            "enabled": .bool(true), "readiness": .string("ready"),
        ])])
        XCTAssertTrue(skills.selectSkill("display-skill"))
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()),
            skills: skills)
        XCTAssertEqual(coordinator.executePointer(.skillDisplayTransfer, target: "other-skill"), .invalid)
        XCTAssertNil(workspace.supportingContent)

        let result = coordinator.executePointer(.skillDisplayTransfer, target: "display-skill")
        if NSScreen.screens.count > 1 {
            XCTAssertEqual(result, .applied)
            XCTAssertEqual(workspace.supportingContent, .skillDetail("display-skill"))
        } else {
            XCTAssertEqual(result, .unsupported)
            XCTAssertNil(workspace.supportingContent)
        }
    }

    func testViewOwnedSkillControlsShareTheValidatedCoordinatorPath() {
        let (coordinator, workspace, _, _, _) = coordinator()
        let owner = UUID()
        var received: [ConsoleAction] = []
        coordinator.registerSkillWorkspaceActionHandler(owner: owner) { action, _ in
            received.append(action)
            return .applied
        }
        for action: ConsoleAction in [.skillsRefresh, .skillBack, .skillActivityRetry, .skillActivityMore,
                                      .skillCreatorOpen] {
            XCTAssertEqual(coordinator.executePointer(action), .applied)
        }
        XCTAssertEqual(received, [.skillsRefresh, .skillBack, .skillActivityRetry, .skillActivityMore,
                                  .skillCreatorOpen])

        coordinator.unregisterSkillWorkspaceActionHandler(owner: UUID())
        XCTAssertEqual(coordinator.execute(request(.skillsRefresh,
            revision: workspace.consoleRevision)), .applied,
            "a stale view cannot unregister the currently mounted handler")
        coordinator.unregisterSkillWorkspaceActionHandler(owner: owner)
        XCTAssertEqual(coordinator.execute(request(.skillsRefresh,
            revision: workspace.consoleRevision)), .unsupported)
    }

    func testCreatorOpenWithoutMountedAuthorizedComposerCannotStartDrafting() {
        let skills = SkillsStore()
        let coordinator = ConsoleActionCoordinator(
            workspace: WorkspaceStore(), display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()),
            skills: skills)
        XCTAssertEqual(coordinator.executePointer(.skillCreatorOpen), .unsupported)
        XCTAssertNil(skills.pendingVoiceDraft)
    }

    func testSkillsVoiceNavigationUsesLoadedCatalogAndProcessInventory() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        let entry = JSONValue.object([
            "skill_id": .string("skill-creator"), "display_name": .string("Skill Creator"),
            "category": .string("development"), "installation": .string("installed"),
            "enabled": .bool(true), "readiness": .string("ready"),
        ])
        skills.updateCatalog([entry])
        skills.updateProcess(skillID: "skill-creator", stepIDs: ["inspect", "draft"])
        skills.updateRuns(skillID: "skill-creator", runIDs: ["run-1"])
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
            skills: skills)

        func current(_ action: ConsoleAction, target: String? = nil,
                     args: [String: JSONValue] = [:]) -> ConsoleRequest {
            request(action, target: target, args: args, revision: workspace.consoleRevision)
        }
        XCTAssertEqual(coordinator.execute(current(.skillSelect, target: "skill-creator")), .applied)
        XCTAssertEqual(skills.selectedSkillID, "skill-creator")
        XCTAssertEqual(coordinator.execute(current(.skillTab, args: ["tab": .string("process")])), .applied)
        XCTAssertEqual(skills.selectedTab, "process")
        XCTAssertEqual(coordinator.execute(current(.skillStepSelect, target: "draft")), .applied)
        XCTAssertEqual(skills.selectedStepID, "draft")
        XCTAssertEqual(coordinator.execute(current(.skillStepExplain, target: "inspect")), .stepDetailsOpened)
        XCTAssertTrue(workspace.showsSkills)
        XCTAssertEqual(skills.selectedTab, "process")
        XCTAssertEqual(skills.selectedStepID, "inspect")
        XCTAssertEqual(coordinator.execute(current(.skillRunSelect, target: "run-1")), .applied)
        XCTAssertEqual(skills.selectedTab, "activity")
        XCTAssertEqual(skills.selectedRunID, "run-1")
        XCTAssertEqual(coordinator.execute(current(.skillStepSelect, target: "foreign-step")), .invalid)
        XCTAssertEqual(coordinator.execute(current(.skillsFilter, args: [
            "state": .string("installed"), "category": .string("unknown"),
        ])), .invalid)
        XCTAssertEqual(skills.catalogInventory.count, 1)
        let inventorySkills = coordinator.inventory()["skills"] as? [[String: Any]]
        XCTAssertEqual(inventorySkills?.count, 1)
        XCTAssertEqual(coordinator.execute(current(.skillSelect, target: "skill-creator")), .applied)
        XCTAssertEqual(skills.selectedTab, "overview", "reopening a selected skill returns to its overview")
        XCTAssertNil(skills.selectedRunID)
    }

    func testSkillsVoiceActionRejectsStaleInventoryAndUnknownTargetsActionably() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        skills.updateCatalog([.object([
            "skill_id": .string("listed-skill"), "display_name": .string("Listed skill"),
            "category": .string("development"), "installation": .string("installed"),
            "enabled": .bool(true), "readiness": .string("ready"),
        ])])
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
            skills: skills)
        let inventoryRevision = workspace.consoleRevision
        let staleTarget = request(.skillSelect, target: "listed-skill", revision: inventoryRevision)

        // Removing a target mutates the shared inventory revision. A voice
        // request resolved against the previous snapshot must ask for a fresh
        // selection instead of silently acting on a changed library.
        skills.updateCatalog([])
        XCTAssertGreaterThan(workspace.consoleRevision, inventoryRevision)
        XCTAssertEqual(coordinator.execute(staleTarget), .stale)

        // A target that was never in the current inventory is reported as an
        // unavailable target, which the native router turns into a useful
        // spoken/action-notice message.
        XCTAssertEqual(coordinator.execute(request(.skillSelect, target: "missing-skill",
            revision: workspace.consoleRevision)), .invalid)
    }

    func testSameStepIDInDifferentSkillsCannotUseAStaleSelectionContext() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        skills.updateCatalog([
            .object([
                "skill_id": .string("alpha-skill"), "display_name": .string("Alpha"),
                "category": .string("development"), "installation": .string("installed"),
                "enabled": .bool(true), "readiness": .string("ready"),
            ]),
            .object([
                "skill_id": .string("beta-skill"), "display_name": .string("Beta"),
                "category": .string("development"), "installation": .string("installed"),
                "enabled": .bool(true), "readiness": .string("ready"),
            ]),
        ])
        skills.updateProcess(skillID: "alpha-skill", stepIDs: ["draft"])
        skills.updateProcess(skillID: "beta-skill", stepIDs: ["draft"])
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
            skills: skills)

        XCTAssertEqual(coordinator.execute(request(.skillSelect, target: "alpha-skill",
            revision: workspace.consoleRevision)), .applied)
        let alphaInventoryRevision = workspace.consoleRevision
        let alphaStepRequest = request(.skillStepSelect, target: "draft",
            revision: alphaInventoryRevision)

        XCTAssertEqual(coordinator.execute(request(.skillSelect, target: "beta-skill",
            revision: workspace.consoleRevision)), .applied)
        XCTAssertGreaterThan(workspace.consoleRevision, alphaInventoryRevision)
        XCTAssertEqual(coordinator.execute(alphaStepRequest), .stale,
                       "a duplicate step ID must not resolve against a different selected skill")
        XCTAssertNil(skills.selectedStepID)
        XCTAssertEqual(coordinator.execute(request(.skillStepSelect, target: "draft",
            revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(skills.selectedStepID, "draft")
    }

    func testVoiceDraftPreviewIsOpaqueSingleUseAndNeverEntersInventory() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        skills.updateCatalog([.object([
            "skill_id": .string("existing-skill"), "display_name": .string("Existing"),
            "category": .string("development"), "installation": .string("installed"),
            "enabled": .bool(true), "readiness": .string("ready"),
        ])])
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()), skills: skills)
        let brief = "PRIVATE brief for a new skill"
        let preview = coordinator.execute(request(.skillRequestPreview, args: [
            "operation": .string("draft"), "skill_id": .string("new-skill"),
            "task_brief": .string(brief),
        ]))
        guard case .previewReady(let id) = preview else { return XCTFail("expected a native preview ID") }
        XCTAssertFalse(String(describing: coordinator.inventory()).contains(brief))
        XCTAssertEqual(coordinator.execute(request(.skillRequest, args: [
            "operation": .string("draft"), "preview_id": .string(id),
        ])), .draftStarted)
        XCTAssertTrue(workspace.showsSkills)
        XCTAssertEqual(skills.pendingVoiceDraft?.taskBrief, brief)
        XCTAssertNotEqual(coordinator.execute(request(.skillRequest, args: [
            "operation": .string("draft"), "preview_id": .string(id),
        ])), .draftStarted, "a preview must be consumed once")
    }

    func testVoiceDraftPreviewExpiresAfterFiveMinutes() {
        let skills = SkillsStore()
        let start = Date(timeIntervalSince1970: 100)
        let preview = skills.makeVoiceDraftPreview(skillID: "new-skill",
            taskBrief: "Create a new skill", now: start)
        XCTAssertNotNil(preview)
        XCTAssertFalse(skills.consumeVoiceDraftPreview(preview!.id,
            now: start.addingTimeInterval(301)))
        XCTAssertNil(skills.pendingVoiceDraft)
    }

    func testVoiceExamplePreviewRequiresDeclaredSkillAndExample() {
        let workspace = WorkspaceStore()
        let skills = SkillsStore()
        skills.updateCatalog([.object([
            "skill_id": .string("technical-plan-document"),
            "display_name": .string("Technical plan"),
            "category": .string("development"), "installation": .string("installed"),
            "enabled": .bool(true), "readiness": .string("ready"),
            "example_ids": .array([.string("implementation-plan")]),
        ])])
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()), skills: skills)
        XCTAssertEqual(coordinator.execute(request(.skillExamplePreview, target: "implementation-plan",
            args: ["skill_id": .string("technical-plan-document")])), .examplePreviewOpened)
        XCTAssertTrue(workspace.showsSkills)
        XCTAssertEqual(skills.selectedSkillID, "technical-plan-document")
        XCTAssertEqual(skills.selectedExampleID, "implementation-plan")
        XCTAssertEqual(coordinator.execute(request(.skillExamplePreview, target: "missing-example",
            args: ["skill_id": .string("technical-plan-document")], revision: workspace.consoleRevision)), .invalid)
    }

    func testSkillsInventoryIsBoundedAndOmitsUnreviewedTaskFields() {
        let skills = SkillsStore()
        let entries = (0..<40).map { index in
            JSONValue.object([
                "skill_id": .string("skill-\(index)"),
                "display_name": .string("Skill \(index)"),
                "category": .string("general"),
                "installation": .string("installed"),
                "enabled": .bool(false), "readiness": .string("unknown"),
                "description": .string("Must never be sent in this inventory"),
                "task_prompt": .string("PRIVATE TASK CONTENT"),
            ])
        }
        skills.updateCatalog(entries)
        let drawer = DrawerState()
        let coordinator = ConsoleActionCoordinator(
            workspace: WorkspaceStore(), display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
            skills: skills)
        let inventorySkills = coordinator.inventory()["skills"] as? [[String: Any]]
        XCTAssertEqual(inventorySkills?.count, 32)
        XCTAssertFalse(String(describing: coordinator.inventory()).contains("PRIVATE TASK CONTENT"))
        XCTAssertFalse(String(describing: coordinator.inventory()).contains("Must never be sent"))
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
        let sharing = ShareCoordinator(clipboardWriter: { _ in true })
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

    func testUnclassifiedMemoryGraphBitmapCannotBeSharedAsPublicResultPNG() {
        let workspace = WorkspaceStore()
        let sharing = ShareCoordinator(clipboardWriter: { _ in true })
        let drawer = DrawerState()
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement, sharing: sharing)
        let item = result(title: "Public result")
        workspace.receive(item)

        XCTAssertEqual(coordinator.execute(request(.sharePreview, target: "graph",
            args: ["format": .string("png")], revision: workspace.consoleRevision)), .unsupported)
        XCTAssertEqual(coordinator.execute(request(.sharePreview, target: item.id.uuidString,
            args: ["format": .string("png")], revision: workspace.consoleRevision)), .unsupported)
        XCTAssertNil(sharing.preview,
                     "a public result cannot authorize sharing the separately sourced memory-graph bitmap")
    }

    func testProtectedLocalResultCannotBeSharedThroughConsoleActions() throws {
        let workspace = WorkspaceStore()
        let sharing = ShareCoordinator()
        let drawer = DrawerState()
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement, sharing: sharing)
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected","body":"private evidence","surface":"window","data_policy":"local_only"}"#.utf8))
        let item = WorkspaceResult(payload: payload)
        workspace.receive(item)
        XCTAssertEqual(coordinator.execute(request(.sharePreview, target: item.id.uuidString,
            revision: workspace.consoleRevision)), .unsupported)
        XCTAssertNil(sharing.preview)
    }

    func testComparisonShareRejectsProtectedContentOnEitherSide() throws {
        for protectedIsActive in [true, false] {
            let workspace = WorkspaceStore()
            let sharing = ShareCoordinator()
            let drawer = DrawerState()
            let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
            let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                        display: DisplayWindowStore(),
                                                        placement: placement, sharing: sharing)
            let protectedData = try JSONDecoder().decode(DisplayPayload.self, from: Data(
                #"{"title":"Protected comparison canary","body":"private comparison body","data_policy":"confidential"}"#.utf8))
            let protected = WorkspaceResult(payload: protectedData)
            let publicItem = result(title: "Public comparison")
            let active = protectedIsActive ? protected : publicItem
            let compared = protectedIsActive ? publicItem : protected
            workspace.receive(active)
            workspace.receive(compared)
            XCTAssertTrue(workspace.compare(with: compared.id))

            XCTAssertEqual(coordinator.execute(request(.sharePreview, target: "comparison",
                revision: workspace.consoleRevision)), .unsupported)
            XCTAssertNil(sharing.preview, "comparison preview leaked protected content")
        }
    }

    func testProtectedImagePreviewCannotReachCopySaveOrShareActions() throws {
        let workspace = WorkspaceStore()
        var copied: [String] = []
        let sharing = ShareCoordinator(clipboardWriter: { copied.append($0); return true })
        let drawer = DrawerState()
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let coordinator = ConsoleActionCoordinator(workspace: workspace,
                                                    display: DisplayWindowStore(),
                                                    placement: placement,
                                                    sharing: sharing)
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected","body":"private evidence","surface":"window","data_policy":"confidential"}"#.utf8))
        let item = WorkspaceResult(payload: payload)
        workspace.receive(item)
        XCTAssertFalse(sharing.beginImagePreview(result: item,
            sourceURL: URL(string: "https://example.org/protected.png")!, pngData: Data([1, 2, 3])))
        XCTAssertNil(sharing.preview, "protected image payload must not enter the share preview")
        XCTAssertEqual(sharing.status, "error")

        XCTAssertEqual(coordinator.execute(request(.shareCopy, revision: workspace.consoleRevision)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.shareSave, revision: workspace.consoleRevision)), .invalid)
        XCTAssertEqual(coordinator.execute(request(.sharePicker, revision: workspace.consoleRevision)), .invalid)
        XCTAssertTrue(copied.isEmpty)
        XCTAssertEqual(sharing.status, "error")
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
        // The width slider went with the wave it shaped (2026-09-24), so the
        // dB windows are what this action sets. Whatever was stored before is
        // put back rather than left at the test's value.
        let floorKey = AudioPresentationTuning.inputFloorKey
        let storedFloor = UserDefaults.standard.object(forKey: floorKey)
        defer {
            if let storedFloor { UserDefaults.standard.set(storedFloor, forKey: floorKey) }
            else { UserDefaults.standard.removeObject(forKey: floorKey) }
        }
        XCTAssertEqual(routed.execute(request(.waveTuningSet, args: ["key": .string("input_floor"), "value": .number(-45)])), .applied)
        XCTAssertEqual(UserDefaults.standard.double(forKey: floorKey), -45)
        XCTAssertEqual(routed.execute(request(.waveTuningSet, args: ["key": .string("input_floor"), "value": .number(-5)])), .invalid)
        XCTAssertEqual(UserDefaults.standard.double(forKey: floorKey), -45, "a rejected value must not be written")
        XCTAssertEqual(routed.execute(request(.waveTuningSet, args: ["key": .string("width"), "value": .number(0.2)])), .invalid,
                       "width is no longer a tuning key")
        attachments.clear()
    }
}
