import XCTest
import AppKit
import JarvisKit
@testable import MortimerHost

/// WS-21: Codex's six diagnostic tests from the 10-03 audit of `63aaeef`,
/// turned into regression tests. The originals asserted the defects and
/// passed on `63aaeef`; they are kept unchanged as evidence in
/// `docs/acceptance/supporting-display/codex-audit-2026-10-03/`. Each test
/// here has the same name with `Audit` replaced by `Regression`, the same
/// setup where the current seams allow it, and the repaired expectation.
@MainActor
final class VoiceDisplayAuditRegressionTests: XCTestCase {
    private static let screens = [
        PlacementScreen(id: "MAIN-0000", visibleFrame: CGRect(x: 0, y: 0, width: 1512, height: 945),
                        isMain: true, name: "Built-in Retina Display"),
        PlacementScreen(id: "DELL-0001", visibleFrame: CGRect(x: 1512, y: 0, width: 2560, height: 1415),
                        name: "DELL U2720Q"),
    ]

    private func result() throws -> WorkspaceResult {
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data("""
        {"title":"Weather Spartanburg","body":"Radar","kind":"weather","surface":"window"}
        """.utf8))
        return WorkspaceResult(payload: payload)
    }

    /// Audit 1: the voice popout opened the window without the weather.
    /// Now an empty popout opens nothing and says so; the transfer is
    /// `display_show` (covered in SupportingDisplayTransferTests).
    func testRegressionPopoutWithNothingOnTheDisplayOpensNothingAndSaysSo() throws {
        let workspace = WorkspaceStore()
        let weather = try result()
        workspace.receive(weather)
        workspace.select(weather.id)
        let display = DisplayWindowStore()
        let drawer = DrawerState()
        let windows = WindowActions()
        var opened: [String] = []
        windows.open = { opened.append($0) }
        let placement = WindowPlacement(drawer: drawer, windows: windows)
        let router = UICommandRouter(drawer: drawer, overlay: ConsoleOverlayState(),
            windows: windows, placement: placement, displayWindow: display, workspace: workspace)
        var spoken: [String] = []
        router.sendNoop = { spoken.append($0) }
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data("""
        {"type":"ui","action":"display_popout"}
        """.utf8)))
        guard case .ui(let command) = message else { return XCTFail("Bad fixture") }
        router.handle(command)
        XCTAssertEqual(opened, [], "no empty supporting display")
        XCTAssertEqual(spoken.count, 1, "the reason is spoken instead")
        XCTAssertNil(workspace.supportingContent)
        XCTAssertTrue(workspace.sendToDisplay(.result(weather.id)), "Control: explicit pointer path accepts this weather")
        XCTAssertEqual(workspace.supportingResult?.id, weather.id)
    }

    /// Audit 2: detach acknowledged a result that does not exist and opened
    /// an empty content window.
    func testRegressionDetachRefusesAnUnknownResultAndOpensNothing() {
        let workspace = WorkspaceStore()
        let panels = PanelStore()
        let windows = WindowActions()
        var opened: [ContentPanelID] = []
        windows.openContentPanel = { opened.append($0) }
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: windows), panels: panels,
            screens: { Self.screens })
        let unknown = UUID()
        let outcome = coordinator.executePointer(.panelDetach, target: "result:\(unknown.uuidString)")
        XCTAssertEqual(outcome, .invalid)
        XCTAssertEqual(opened.count, 0)
        XCTAssertEqual(panels.contentRecords.count, 0)
    }

    /// Audit 3: the coordinator read `screen_id` on detach, but the native
    /// contract rejected it.
    func testRegressionDetachAcceptsScreenIDThroughItsArgumentContract() {
        let request = ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
            revision: 0, action: .panelDetach, target: "result:\(UUID().uuidString)",
            args: ["screen_id": .string("external-screen")])
        XCTAssertTrue(ConsoleActionRegistry().validate(request))
    }

    /// Audit 4: a move to a screen that does not exist was acknowledged and
    /// stored.
    func testRegressionMoveRefusesANonexistentScreen() {
        let workspace = WorkspaceStore()
        let panels = PanelStore()
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()), panels: panels,
            screens: { Self.screens })
        let impossibleScreen = "codex-audit-this-screen-does-not-exist"
        XCTAssertEqual(coordinator.executePointer(.panelMove, target: "results",
            args: ["screen_id": .string(impossibleScreen)]), .invalid)
        XCTAssertNil(panels.screenByPanel[.results])
    }

    /// Audit 5: the inventory advertised display names while placement
    /// accepts hardware UUIDs. Uses this Mac's real screens, as the audit did.
    func testRegressionAdvertisedScreenIDsAreThePlacementScreenIDs() throws {
        let placementIDs = ScreenPlacement.liveScreens().prefix(8).map(\.id)
        try XCTSkipIf(placementIDs.isEmpty, "no screens in this test host")
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let placement = WindowPlacement(drawer: DrawerState(), windows: WindowActions())
        let supporting = SupportingDisplayCoordinator(workspace: workspace, display: display,
                                                      environment: .live(placement: placement))
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: display,
            placement: placement, supportingDisplay: supporting)
        let screens = try XCTUnwrap(coordinator.inventory()["screens"] as? [[String: Any]])
        let advertised = Set(screens.compactMap { $0["id"] as? String })
        XCTAssertEqual(advertised, Set(placementIDs))
    }

    /// Audit 6: the requested inventory reported neither the supporting
    /// result nor fixed-panel placement.
    func testRegressionInventoryReportsSupportingResultAndFixedPanelPlacement() throws {
        let workspace = WorkspaceStore()
        let weather = try result()
        workspace.receive(weather)
        XCTAssertTrue(workspace.sendToDisplay(.result(weather.id)))
        let panels = PanelStore()
        panels.detach(.results)
        XCTAssertTrue(panels.move(.results, to: Self.screens[1].id))
        let display = DisplayWindowStore()
        let supporting = SupportingDisplayCoordinator(workspace: workspace, display: display,
            environment: .live(placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions())))
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: display,
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()), panels: panels,
            supportingDisplay: supporting, screens: { Self.screens })
        let inventory = coordinator.inventory()
        let supportingDisplay = try XCTUnwrap(inventory["supporting_display"] as? [String: Any])
        XCTAssertEqual(supportingDisplay["content"] as? String, "result")
        XCTAssertEqual(supportingDisplay["result_id"] as? String, weather.id.uuidString)
        XCTAssertEqual(supportingDisplay["presented"] as? Bool, false, "the window is not open")
        let entries = try XCTUnwrap(inventory["panels"] as? [[String: Any]])
        let results = try XCTUnwrap(entries.first { $0["id"] as? String == "results" })
        XCTAssertEqual(results["screen_id"] as? String, Self.screens[1].id)
    }
}
