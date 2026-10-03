import XCTest
import JarvisKit
@testable import MortimerHost

/// WS-21 (`docs/plans/MORTIMER_SUPPORTING_DISPLAY_TRANSFER_PLAN.md` §4).
/// Larry, 10-03, on `63aaeef`: asked for the radar on the external monitor,
/// Mortimer said it was there while the supporting display opened empty.
/// Each case Codex named for review: weather/radar transfer, repeated
/// requests, stale result IDs, missing monitors, disconnect during transfer
/// and the conversation remaining on the main screen.
@MainActor
private final class FakeDisplay {
    static let main = PlacementScreen(id: "MAIN-0000", visibleFrame: CGRect(x: 0, y: 0, width: 1512, height: 945),
                                      isMain: true, name: "Built-in Retina Display")
    static let dell = PlacementScreen(id: "DELL-0001", visibleFrame: CGRect(x: 1512, y: 0, width: 2560, height: 1415),
                                      name: "DELL U2720Q")
    var screens: [PlacementScreen]
    var displayScreen: String?
    var assigned: [String] = []
    var opened = 0
    var closed = 0
    var clock: TimeInterval = 0
    /// What opening the display does; by default it presents on the
    /// assigned screen, as the real scene and placement do.
    var onOpen: (@MainActor () -> Void)?
    let store: DisplayWindowStore

    init(store: DisplayWindowStore) {
        self.store = store
        self.screens = [Self.main, Self.dell]
    }

    func presentOnAssignedScreen() {
        store.setWindowOpen(true)
        displayScreen = assigned.last
    }

    func environment() -> SupportingDisplayCoordinator.Environment {
        SupportingDisplayCoordinator.Environment(
            screens: { [unowned self] in self.screens },
            windowScreenID: { [unowned self] kind in
                switch kind {
                case .display: return self.store.isWindowOpen ? self.displayScreen : nil
                case .console: return FakeDisplay.main.id
                case .drawer: return nil
                }
            },
            consoleScreenID: { FakeDisplay.main.id },
            preferredSupportingScreenID: { nil },
            assignDisplay: { [unowned self] in self.assigned.append($0) },
            openDisplay: { [unowned self] in
                self.opened += 1
                if let onOpen = self.onOpen { onOpen() } else { self.presentOnAssignedScreen() }
            },
            closeDisplay: { [unowned self] in
                self.closed += 1
                self.store.setWindowOpen(false)
            },
            layoutVersion: { 2 },
            pause: { [unowned self] in
                self.clock += 0.25
                await Task.yield()
            },
            now: { [unowned self] in self.clock },
            confirmTimeout: 3.5)
    }
}

@MainActor
final class SupportingDisplayTransferTests: XCTestCase {
    private struct Fixture {
        let coordinator: SupportingDisplayCoordinator
        let workspace: WorkspaceStore
        let display: DisplayWindowStore
        let fake: FakeDisplay
    }

    private func fixture() -> Fixture {
        let workspace = WorkspaceStore()
        workspace.quietArrivals = true           // the layout-2 conversation thread
        let display = DisplayWindowStore()
        let fake = FakeDisplay(store: display)
        let coordinator = SupportingDisplayCoordinator(workspace: workspace, display: display,
                                                       environment: fake.environment())
        return Fixture(coordinator: coordinator, workspace: workspace, display: display, fake: fake)
    }

    private func payload(_ json: String) throws -> WorkspaceResult {
        WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self, from: Data(json.utf8)))
    }

    private func weather() throws -> WorkspaceResult {
        try payload("""
        {"kind":"weather","title":"Weather","surface":"window","tool":"weather_report",
         "weather":{"schema":1,"place":{"label":"Folly Beach","source":"device","approximate":false},
                    "units":"imperial","now":{"temp":"82°","condition":"Sunny","symbol":"sun.max"},
                    "alerts":[],"summary":"Sunny","attribution":"NWS"}}
        """)
    }

    // MARK: Weather / radar transfer

    func testWeatherTransferIsPresentedOnTheRequestedScreenAndTheConversationStays() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        XCTAssertTrue(f.workspace.showsConversation)

        let outcome = await f.coordinator.transfer(.result(item.id), screenID: FakeDisplay.dell.id)

        XCTAssertEqual(outcome, .presented(title: "Weather", screen: "DELL U2720Q"))
        XCTAssertEqual(outcome.status, "ok")
        XCTAssertEqual(f.fake.assigned, [FakeDisplay.dell.id], "placement is told the destination")
        XCTAssertEqual(f.workspace.supportingContent, .result(item.id), "the result is the display's content")
        XCTAssertTrue(f.coordinator.isPresented(.result(item.id)))
        XCTAssertTrue(f.workspace.showsConversation, "the conversation stays on the main screen")
    }

    func testWithNoScreenNamedTheOtherScreenIsUsed() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        let outcome = await f.coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(outcome, .presented(title: "Weather", screen: "DELL U2720Q"))
        XCTAssertEqual(f.fake.assigned, [FakeDisplay.dell.id])
    }

    // MARK: Repeated requests

    func testARepeatedRequestReusesThePresentation() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        _ = await f.coordinator.transfer(.result(item.id), screenID: nil)
        let again = await f.coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(again, .alreadyShowing(title: "Weather", screen: "DELL U2720Q"))
        XCTAssertEqual(again.status, "noop")
        XCTAssertEqual(f.fake.opened, 1, "nothing reopened")
    }

    // MARK: Stale result IDs and protected content

    func testAStaleResultIDIsRejectedBeforeAnythingOpens() async {
        let f = fixture()
        let outcome = await f.coordinator.transfer(.result(UUID()), screenID: nil)
        XCTAssertEqual(outcome.code, "result_unavailable")
        XCTAssertEqual(outcome.status, "error")
        XCTAssertEqual(f.fake.opened, 0)
        XCTAssertTrue(f.fake.assigned.isEmpty)
        XCTAssertNil(f.workspace.supportingContent)
    }

    func testProtectedContentIsRejectedBeforeAnythingOpens() async throws {
        let f = fixture()
        let item = try payload("""
        {"kind":"markdown","title":"Private","body":"Local only","surface":"window","data_policy":"local_only"}
        """)
        f.workspace.receive(item)
        let outcome = await f.coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(outcome.code, "protected_result")
        XCTAssertEqual(f.fake.opened, 0)
        XCTAssertNil(f.workspace.supportingContent)
    }

    // MARK: Missing monitors

    func testWithOneScreenTheTransferIsRejected() async throws {
        let f = fixture()
        f.fake.screens = [FakeDisplay.main]
        let item = try weather()
        f.workspace.receive(item)
        let outcome = await f.coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(outcome.code, "single_screen")
        XCTAssertEqual(f.fake.opened, 0)
        XCTAssertNil(f.workspace.supportingContent)
    }

    func testAScreenThatIsNotConnectedOrIsTheConsolesIsRejected() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        let missing = await f.coordinator.transfer(.result(item.id), screenID: "Built-in Retina Display")
        XCTAssertEqual(missing.code, "screen_unavailable", "a screen name is not a placement ID")
        let console = await f.coordinator.transfer(.result(item.id), screenID: FakeDisplay.main.id)
        XCTAssertEqual(console.code, "console_screen")
        XCTAssertEqual(f.fake.opened, 0)
        XCTAssertNil(f.workspace.supportingContent)
    }

    // MARK: Disconnect during transfer, and no confirmation

    func testADisconnectDuringTheTransferFailsAndReturnsTheResultToMain() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        f.fake.onOpen = { f.fake.screens.removeAll { $0.id == FakeDisplay.dell.id } }
        let outcome = await f.coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(outcome.code, "screen_disconnected")
        XCTAssertEqual(outcome.status, "error")
        XCTAssertNil(f.workspace.supportingContent, "main does not point at an absent window")
        XCTAssertEqual(f.fake.closed, 1, "the window it opened is closed")
    }

    func testAnUnconfirmedTransferTimesOutTruthfully() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        f.fake.onOpen = {}                       // the window never presents
        let outcome = await f.coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(outcome.code, "not_confirmed")
        XCTAssertLessThanOrEqual(f.fake.clock, 3.75, "inside the bot's 5 s wait")
        XCTAssertNil(f.workspace.supportingContent)
        XCTAssertEqual(f.fake.closed, 1)
    }

    func testAPresentationOnTheWrongScreenIsNotConfirmed() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        f.fake.onOpen = {
            f.display.setWindowOpen(true)
            f.fake.displayScreen = FakeDisplay.main.id   // placement left it on the console's screen
        }
        let outcome = await f.coordinator.transfer(.result(item.id), screenID: FakeDisplay.dell.id)
        XCTAssertEqual(outcome.code, "not_confirmed")
    }

    // MARK: Pointer route and inventory

    func testAPointerTransferFailureIsReported() async throws {
        let f = fixture()
        f.fake.screens = [FakeDisplay.main]
        let item = try weather()
        f.workspace.receive(item)
        var reported: SupportingDisplayCoordinator.Outcome?
        f.coordinator.onPointerFailure = { reported = $0 }
        f.coordinator.show(.result(item.id))
        for _ in 0..<50 where reported == nil { await Task.yield() }
        XCTAssertEqual(reported?.code, "single_screen")
    }

    func testInventoryNamesPlacementScreensAndWhatTheDisplayOwns() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        _ = await f.coordinator.transfer(.result(item.id), screenID: nil)
        let screens = f.coordinator.screensInventory()
        XCTAssertEqual(screens.count, 2)
        XCTAssertEqual(screens.first, .object([
            "id": .string(FakeDisplay.main.id), "label": .string("Built-in Retina Display"),
            "index": .number(0), "primary": .bool(true),
            "is_console": .bool(true), "is_supporting": .bool(false),
        ]))
        XCTAssertEqual(f.coordinator.supportingDisplayInventory(), .object([
            "open": .bool(true), "content": .string("result"),
            "result_id": .string(item.id.uuidString),
            "result_ids": .array([.string(item.id.uuidString)]), "tiles": .number(1),
            "screen_id": .string(FakeDisplay.dell.id), "presented": .bool(true),
        ]))
    }

    // MARK: Through the console coordinator (voice `display_show`)

    private func request(_ action: ConsoleAction, target: String? = nil,
                         args: [String: JSONValue] = [:], revision: Int) -> ConsoleRequest {
        ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                       revision: revision, action: action, target: target,
                       secondaryTarget: nil, args: args)
    }

    // A MainActor default argument would be evaluated outside the actor.
    private func consoleCoordinator(_ f: Fixture, panels: PanelStore? = nil) -> ConsoleActionCoordinator {
        let fake = f.fake
        let panels = panels ?? PanelStore()
        return ConsoleActionCoordinator(
            workspace: f.workspace, display: f.display,
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()),
            panels: panels, supportingDisplay: f.coordinator, screens: { fake.screens })
    }

    func testDisplayShowGoesThroughTheValidatedConfirmedRoute() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        let console = consoleCoordinator(f)
        XCTAssertTrue(ConsoleActionCoordinator.isDisplayTransfer(.displayShow))
        XCTAssertEqual(console.execute(request(.displayShow, target: item.id.uuidString,
                                               revision: f.workspace.consoleRevision)), .unsupported,
                       "never reported synchronously")
        let shown = await console.executeTransfer(request(
            .displayShow, target: item.id.uuidString,
            args: ["screen_id": .string(FakeDisplay.dell.id)], revision: f.workspace.consoleRevision))
        XCTAssertEqual(shown.status, "ok")
        XCTAssertEqual(shown.summary, "Weather is now on DELL U2720Q.")
        let unknown = await console.executeTransfer(request(
            .displayShow, target: "radar-please", revision: f.workspace.consoleRevision))
        XCTAssertEqual(unknown.code, "invalid_target")
    }

    func testRequestedAndPublishedInventoriesAreOneBuilder() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        let console = consoleCoordinator(f)
        _ = await console.executeTransfer(request(.displayShow, target: item.id.uuidString,
                                                  revision: f.workspace.consoleRevision))
        guard case .object(let published) = console.inventoryJSON() else { return XCTFail("object") }
        let requested = console.inventory()
        XCTAssertEqual(Set(requested.keys), Set(published.keys))
        XCTAssertEqual((requested["screens"] as? [Any])?.count, 2)
        XCTAssertEqual((requested["supporting_display"] as? [String: Any])?["screen_id"] as? String,
                       FakeDisplay.dell.id)
        XCTAssertEqual((requested["panels"] as? [Any])?.isEmpty, false, "fixed panels carry their destination")
    }

    // MARK: Detach and move validation (Codex audit F3/F4)

    func testDetachOfAResultThatDoesNotExistCreatesNothing() throws {
        let f = fixture()
        let panels = PanelStore()
        let console = consoleCoordinator(f, panels: panels)
        XCTAssertEqual(console.execute(request(.panelDetach, target: "result:\(UUID().uuidString)",
                                               revision: f.workspace.consoleRevision)), .invalid)
        XCTAssertTrue(panels.contentRecords.isEmpty)
        let item = try weather()
        f.workspace.receive(item)
        XCTAssertEqual(console.execute(request(.panelDetach, target: "result:\(item.id.uuidString)",
                                               args: ["screen_id": .string("Built-in Retina Display")],
                                               revision: f.workspace.consoleRevision)), .invalid,
                       "a screen name is not a placement ID")
        XCTAssertTrue(panels.contentRecords.isEmpty)
        XCTAssertEqual(console.execute(request(.panelDetach, target: "result:\(item.id.uuidString)",
                                               args: ["screen_id": .string(FakeDisplay.dell.id)],
                                               revision: f.workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.contentRecords.values.first?.screenID, FakeDisplay.dell.id)
    }

    func testMoveToAScreenThatIsNotConnectedChangesNothing() {
        let f = fixture()
        let panels = PanelStore()
        let console = consoleCoordinator(f, panels: panels)
        XCTAssertEqual(console.execute(request(.panelMove, target: "atlas",
                                               args: ["screen_id": .string("GONE")],
                                               revision: f.workspace.consoleRevision)), .invalid)
        XCTAssertNil(panels.screenByPanel[.atlas])
        XCTAssertEqual(console.execute(request(.panelMove, target: "atlas",
                                               args: ["screen_id": .string(FakeDisplay.dell.id)],
                                               revision: f.workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.screenByPanel[.atlas], FakeDisplay.dell.id)
    }

    // MARK: display_popout with nothing to show

    func testAnEmptyDisplayPopoutSaysSoInsteadOfOpeningAnEmptyWindow() throws {
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let windows = WindowActions()
        var opened: [String] = []
        windows.open = { opened.append($0) }
        let drawer = DrawerState()
        let router = UICommandRouter(drawer: drawer, overlay: ConsoleOverlayState(), windows: windows,
                                     placement: WindowPlacement(drawer: drawer, windows: windows),
                                     displayWindow: display, workspace: workspace)
        var spoken: [String] = []
        router.sendNoop = { spoken.append($0) }
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(#"{"type":"ui","action":"display_popout"}"#.utf8)))
        guard case .ui(let command) = message else { return XCTFail("not a ui message") }

        router.handle(command)
        XCTAssertTrue(opened.isEmpty, "no empty window")
        XCTAssertEqual(spoken, ["Nothing is on the other display yet. Ask me to show a specific result there."])

        XCTAssertTrue(workspace.sendToDisplay(.memoryGraph))
        router.handle(command)
        XCTAssertEqual(opened, ["display"], "with content it opens as before")
    }

    // Independent Codex review probes. Desired behavior; no implementation edits.
    func testReviewRejectedRequestDoesNotAbandonAnInFlightTransfer() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        f.fake.onOpen = { f.display.setWindowOpen(true) }
        var env = f.fake.environment()
        var pendingCoordinator: SupportingDisplayCoordinator!
        var rejection: SupportingDisplayCoordinator.Outcome?
        env.pause = {
            rejection = await pendingCoordinator.transfer(.result(UUID()), screenID: nil)
            f.fake.displayScreen = FakeDisplay.dell.id
        }
        pendingCoordinator = SupportingDisplayCoordinator(workspace: f.workspace, display: f.display,
                                                         environment: env)
        let original = await pendingCoordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(rejection?.code, "result_unavailable")
        XCTAssertEqual(original.status, "ok", "a rejected request changed nothing and must not cancel the valid transfer")
    }

    func testReviewFailedReplacementClosesTheWindowOpenedByTheSupersededTransfer() async throws {
        let f = fixture()
        let first = try weather()
        let replacement = try payload(#"{"title":"Research","body":"Evidence","surface":"window"}"#)
        f.workspace.receive(first); f.workspace.receive(replacement)
        f.fake.onOpen = { f.display.setWindowOpen(true) }
        var env = f.fake.environment()
        var pendingCoordinator: SupportingDisplayCoordinator!
        var replacing = false
        var replacementOutcome: SupportingDisplayCoordinator.Outcome?
        env.pause = {
            f.fake.clock += 0.25
            if !replacing {
                replacing = true
                replacementOutcome = await pendingCoordinator.transfer(.result(replacement.id), screenID: nil)
            } else { await Task.yield() }
        }
        pendingCoordinator = SupportingDisplayCoordinator(workspace: f.workspace, display: f.display,
                                                         environment: env)
        let original = await pendingCoordinator.transfer(.result(first.id), screenID: nil)
        XCTAssertEqual(original.code, "superseded")
        XCTAssertEqual(replacementOutcome?.code, "not_confirmed")
        XCTAssertNil(f.workspace.supportingContent)
        XCTAssertFalse(f.display.isWindowOpen, "neither request confirmed; the chain-created empty window must close")
        XCTAssertEqual(f.fake.closed, 1)
    }

    func testReviewFixedPanelDetachHonorsItsRequestedScreen() {
        let f = fixture()
        let panels = PanelStore()
        let console = consoleCoordinator(f, panels: panels)
        let bad = console.execute(request(.panelDetach, target: "results",
            args: ["screen_id": .string("DISCONNECTED")], revision: f.workspace.consoleRevision))
        XCTAssertEqual(bad, .invalid, "the fixed-panel route must validate the destination too")
        XCTAssertFalse(panels.detached.contains(.results))
        let good = console.execute(request(.panelDetach, target: "results",
            args: ["screen_id": .string(FakeDisplay.dell.id)], revision: f.workspace.consoleRevision))
        XCTAssertEqual(good, .applied)
        XCTAssertEqual(panels.screenByPanel[.results], FakeDisplay.dell.id)
    }

    func testReviewInventoryReportsATransportResultActuallyPresentedOnTheSharedStage() async throws {
        let f = fixture()
        let item = try payload(#"{"title":"Web search","body":"Evidence","surface":"window"}"#)
        f.workspace.receive(item)
        XCTAssertNotNil(f.display.apply(item.payload, workspaceID: item.id))
        f.fake.assigned = [FakeDisplay.dell.id]
        f.fake.presentOnAssignedScreen()
        XCTAssertNil(f.workspace.supportingContent, "the normal transport route does not set a supplemental selection")
        XCTAssertTrue(f.coordinator.isPresented(.result(item.id)), "the result is actually in the visible shared stage")
        guard case .object(let inventory) = f.coordinator.supportingDisplayInventory() else { return XCTFail("object") }
        XCTAssertEqual(inventory["presented"], .bool(true), "inventory must not say nothing is presented")
        XCTAssertEqual(inventory["content"], .string("result"))
        XCTAssertEqual(inventory["result_id"], .string(item.id.uuidString))
    }

    // MARK: Ownership and cleanup across superseding transfers (repair of the review probes)

    func testASupersededTransferLeavesItsSuccessfulSuccessorAlone() async throws {
        let f = fixture()
        let first = try weather()
        let second = try payload(#"{"title":"Research","body":"Evidence","surface":"window"}"#)
        f.workspace.receive(first); f.workspace.receive(second)
        var opens = 0
        f.fake.onOpen = {
            opens += 1
            f.display.setWindowOpen(true)
            if opens == 2 { f.fake.displayScreen = f.fake.assigned.last }   // only the second presents
        }
        var env = f.fake.environment()
        var coordinator: SupportingDisplayCoordinator!
        var secondOutcome: SupportingDisplayCoordinator.Outcome?
        env.pause = {
            f.fake.clock += 0.25
            if secondOutcome == nil {
                secondOutcome = await coordinator.transfer(.result(second.id), screenID: nil)
            }
        }
        coordinator = SupportingDisplayCoordinator(workspace: f.workspace, display: f.display, environment: env)
        let firstOutcome = await coordinator.transfer(.result(first.id), screenID: nil)
        XCTAssertEqual(secondOutcome?.status, "ok")
        XCTAssertEqual(firstOutcome.code, "superseded")
        XCTAssertEqual(f.workspace.supportingContent, .result(second.id), "the older request did not undo the newer one")
        XCTAssertTrue(f.display.isWindowOpen)
        XCTAssertEqual(f.fake.closed, 0)
    }

    func testAFailedTransferPutsBackTheDisplayItReplaced() async throws {
        let f = fixture()
        let earlier = try weather()
        let next = try payload(#"{"title":"Research","body":"Evidence","surface":"window"}"#)
        f.workspace.receive(earlier); f.workspace.receive(next)
        let shown = await f.coordinator.transfer(.result(earlier.id), screenID: nil)
        XCTAssertEqual(shown.status, "ok")
        f.fake.onOpen = { f.fake.screens.removeAll { $0.id == FakeDisplay.dell.id } }
        let failed = await f.coordinator.transfer(.result(next.id), screenID: nil)
        XCTAssertEqual(failed.code, "screen_disconnected")
        XCTAssertEqual(f.workspace.supportingContent, .result(earlier.id), "the display it replaced is back")
        XCTAssertTrue(f.display.isWindowOpen, "a window that was already open stays open")
        XCTAssertEqual(f.fake.closed, 0)
    }

    func testARejectedRequestLeavesNoTraceOnALaterFailure() async throws {
        let f = fixture()
        let item = try weather()
        f.workspace.receive(item)
        f.fake.onOpen = { f.display.setWindowOpen(true) }        // never on the right screen
        var env = f.fake.environment()
        var coordinator: SupportingDisplayCoordinator!
        var refused: SupportingDisplayCoordinator.Outcome?
        env.pause = {
            f.fake.clock += 0.25
            if refused == nil { refused = await coordinator.transfer(.result(item.id), screenID: "GONE") }
        }
        coordinator = SupportingDisplayCoordinator(workspace: f.workspace, display: f.display, environment: env)
        let outcome = await coordinator.transfer(.result(item.id), screenID: nil)
        XCTAssertEqual(refused?.code, "screen_unavailable")
        XCTAssertEqual(outcome.code, "not_confirmed", "the valid transfer kept ownership and settled itself")
        XCTAssertNil(f.workspace.supportingContent)
        XCTAssertFalse(f.display.isWindowOpen)
        XCTAssertEqual(f.fake.closed, 1)
    }

    // MARK: Detach destinations on every route

    func testDetachOfAnOpenContentPanelHonorsItsRequestedScreen() throws {
        let f = fixture()
        let panels = PanelStore()
        let console = consoleCoordinator(f, panels: panels)
        let item = try weather()
        f.workspace.receive(item)
        XCTAssertEqual(console.execute(request(.panelDetach, target: "result:\(item.id.uuidString)",
                                               revision: f.workspace.consoleRevision)), .applied)
        let record = try XCTUnwrap(panels.contentRecords.values.first)
        XCTAssertNil(record.screenID)
        let uuid = record.id.rawValue.uuidString
        XCTAssertEqual(console.execute(request(.panelDetach, target: uuid, args: ["screen_id": .string("GONE")],
                                               revision: f.workspace.consoleRevision)), .invalid)
        XCTAssertNil(panels.contentRecords[record.id]?.screenID, "a disconnected screen changes nothing")
        XCTAssertEqual(console.execute(request(.panelDetach, target: uuid,
                                               args: ["screen_id": .string(FakeDisplay.dell.id)],
                                               revision: f.workspace.consoleRevision)), .applied)
        XCTAssertEqual(panels.contentRecords[record.id]?.screenID, FakeDisplay.dell.id)
        XCTAssertEqual(console.execute(request(.panelDetach, target: "result:\(item.id.uuidString)",
                                               args: ["screen_id": .string(FakeDisplay.main.id)],
                                               revision: f.workspace.consoleRevision)), .applied,
                       "the content target names the open panel and moves it")
        XCTAssertEqual(panels.contentRecords.count, 1)
        XCTAssertEqual(panels.contentRecords[record.id]?.screenID, FakeDisplay.main.id)
    }

    // MARK: Inventory from the visible stage

    func testInventoryListsEveryTileOnTheSharedStage() throws {
        let f = fixture()
        let item = try payload(#"{"title":"Web search","body":"Evidence","surface":"window"}"#)
        f.workspace.receive(item)
        XCTAssertNotNil(f.display.apply(item.payload, workspaceID: item.id))
        XCTAssertTrue(f.workspace.sendToDisplay(.memoryGraph))
        f.fake.assigned = [FakeDisplay.dell.id]
        f.fake.presentOnAssignedScreen()
        guard case .object(let shown) = f.coordinator.supportingDisplayInventory() else { return XCTFail("object") }
        XCTAssertEqual(shown["content"], .string("memory_graph"), "the first tile, as the stage renders it")
        XCTAssertEqual(shown["result_id"], .null)
        XCTAssertEqual(shown["result_ids"], .array([.string(item.id.uuidString)]))
        XCTAssertEqual(shown["tiles"], .number(2))
        XCTAssertEqual(shown["presented"], .bool(true))
        XCTAssertEqual(shown["screen_id"], .string(FakeDisplay.dell.id))
        f.display.setWindowOpen(false)
        guard case .object(let closed) = f.coordinator.supportingDisplayInventory() else { return XCTFail("object") }
        XCTAssertEqual(closed["presented"], .bool(false), "nothing is presented while the window is closed")
        XCTAssertEqual(closed["screen_id"], .null)
    }
}
