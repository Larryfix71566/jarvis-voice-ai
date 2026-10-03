import XCTest
import AppKit
import JarvisKit
@testable import MortimerHost

// Temporary Codex audit probes: characterize the deployed revision, no app edits.
@MainActor
final class VoiceDisplayAuditTests: XCTestCase {
    private func result() throws -> WorkspaceResult {
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data("""
        {"title":"Weather Spartanburg","body":"Radar","kind":"weather","surface":"window"}
        """.utf8))
        return WorkspaceResult(payload: payload)
    }
    func testAuditLegacyPopoutOpensChromeWithoutAssigningWeather() throws {
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
            windows: windows, placement: placement, displayWindow: display)
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data("""
        {"type":"ui","action":"display_popout"}
        """.utf8)))
        guard case .ui(let command) = message else { return XCTFail("Bad fixture") }
        router.handle(command)
        XCTAssertEqual(opened, ["display"])
        XCTAssertNil(workspace.supportingContent, "Audit: voice popout did not transfer weather")
        XCTAssertTrue(display.panels.isEmpty, "Audit: no legacy display content to render")
        XCTAssertTrue(workspace.sendToDisplay(.result(weather.id)), "Control: explicit pointer path accepts this weather")
        XCTAssertEqual(workspace.supportingResult?.id, weather.id)
    }
    func testAuditDetachAcceptsAnUnknownResultAndOpensAnEmptyContentWindow() {
        let workspace = WorkspaceStore()
        let panels = PanelStore()
        let windows = WindowActions()
        var opened: [ContentPanelID] = []
        windows.openContentPanel = { opened.append($0) }
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: windows), panels: panels)
        let unknown = UUID()
        let outcome = coordinator.executePointer(.panelDetach, target: "result:\(unknown.uuidString)")
        XCTAssertEqual(outcome, .applied, "Audit: currently acknowledges a nonexistent result")
        XCTAssertEqual(opened.count, 1)
        XCTAssertEqual(panels.contentRecords.count, 1)
        XCTAssertFalse(workspace.results.contains(where: { $0.id == unknown }))
    }
    func testAuditDetachCannotPassScreenIDThroughItsArgumentContract() {
        let request = ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
            revision: 0, action: .panelDetach, target: "result:\(UUID().uuidString)",
            args: ["screen_id": .string("external-screen")])
        XCTAssertFalse(ConsoleActionRegistry().validate(request),
            "Audit: coordinator reads screen_id, but native contract rejects it")
    }
    func testAuditMoveAcknowledgesANonexistentScreen() {
        let workspace = WorkspaceStore()
        let panels = PanelStore()
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()), panels: panels)
        let impossibleScreen = "codex-audit-this-screen-does-not-exist"
        XCTAssertEqual(coordinator.executePointer(.panelMove, target: "results",
            args: ["screen_id": .string(impossibleScreen)]), .applied)
        XCTAssertEqual(panels.screenByPanel[.results], impossibleScreen,
            "Audit: stores the screen name without validating an attached screen")
    }

    func testAuditAdvertisedScreenIDsDoNotMatchPlacementScreenIDs() throws {
        let inventory = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(WorkspaceStore().consoleInventoryJSON)) as? [String: Any])
        let screens = try XCTUnwrap(inventory["screens"] as? [[String: Any]])
        let advertised = Set(screens.compactMap { $0["id"] as? String })
        let placement = Set(ScreenPlacement.liveScreens().map(\.id))
        XCTAssertFalse(advertised.isEmpty)
        XCTAssertFalse(placement.isEmpty)
        XCTAssertTrue(advertised.isDisjoint(with: placement),
            "Audit: inventory advertises display labels; placement accepts hardware UUIDs")
    }

    func testAuditInventoryCannotReportSupportingResultOrFixedPanelPlacement() throws {
        let workspace = WorkspaceStore()
        let weather = try result()
        workspace.receive(weather)
        XCTAssertTrue(workspace.sendToDisplay(.result(weather.id)))
        let panels = PanelStore()
        panels.detach(.results)
        XCTAssertTrue(panels.move(.results, to: "audit-screen"))
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
            placement: WindowPlacement(drawer: DrawerState(), windows: WindowActions()), panels: panels)
        let inventory = coordinator.inventory()
        XCTAssertNil(inventory["supporting_content"])
        XCTAssertNil(inventory["supporting_result_id"])
        XCTAssertNil(inventory["panels"], "Audit: requested inventory omits even fixed panel state")
        let wire = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(workspace.consoleInventoryJSON)) as? [String: Any])
        let entries = try XCTUnwrap(wire["panels"] as? [[String: Any]])
        let results = try XCTUnwrap(entries.first { $0["id"] as? String == "results" })
        XCTAssertTrue(results["screen_id"] is NSNull,
            "Audit: inventory remains null despite a stored panel screen")
    }
}
