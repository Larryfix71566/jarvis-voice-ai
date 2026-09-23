import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class WorkspaceResultDetailsTests: XCTestCase {
    private func result() throws -> WorkspaceResult {
        let json = #"{"title":"Synthetic research","body":"Supplied findings","links":[{"label":"Evidence","url":"https://example.org/source"}],"images":["https://example.org/image.png"],"basemap_images":["https://example.org/map.png"],"commands":["echo manual"],"note":"Supplied note","expect_output":true,"content":"PRIVATE_CLIPBOARD_FIXTURE","truncated":true}"#
        return WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self, from: Data(json.utf8)))
    }

    func testSourceInspectionSurvivesPresentationChangesWithoutChangingSelectionOrScroll() throws {
        let workspace = WorkspaceStore(), a = try result(), b = try result()
        workspace.receive(a); workspace.receive(b)
        workspace.rememberScroll(321, for: a.id)
        let presentation = workspace.presentation(for: a)
        presentation.mode = .sources; presentation.selectedSource = 0
        presentation.showsInspector = true; presentation.sourceScrollOffset = 250
        workspace.compare(with: b.id)
        workspace.sendToDisplay(.result(a.id))
        XCTAssertTrue(workspace.presentation(for: a) === presentation)
        XCTAssertEqual(presentation.mode, .sources)
        XCTAssertEqual(presentation.selectedSource, 0)
        XCTAssertTrue(presentation.showsInspector)
        XCTAssertEqual(presentation.sourceScrollOffset, 250)
        XCTAssertEqual(workspace.scrollOffsets[a.id], 321)
        XCTAssertEqual(workspace.activeID, a.id)
        XCTAssertEqual(workspace.comparisonID, b.id)
    }

    func testExportPreservesSuppliedFieldsButNeverIncludesClipboard() throws {
        let text = WorkspaceResultExport.text(try result())
        for expected in ["Synthetic research", "Supplied findings", "https://example.org/source",
                         "https://example.org/image.png", "https://example.org/map.png", "echo manual",
                         "Supplied note", "truncated", "output to be returned", "Clipboard content omitted"] {
            XCTAssertTrue(text.contains(expected), expected)
        }
        XCTAssertFalse(text.contains("PRIVATE_CLIPBOARD_FIXTURE"))
    }

    func testScopedExportUsesOneBasedDeterministicSections() throws {
        let item = try result()
        let whole = try XCTUnwrap(WorkspaceResultExport.scopedText(item, scope: "whole", ordinal: nil))
        XCTAssertTrue(whole.hasPrefix("Synthetic research"))
        let second = try XCTUnwrap(WorkspaceResultExport.scopedText(item, scope: "section", ordinal: 2))
        XCTAssertEqual(second, "Supplied findings\n")
        XCTAssertNil(WorkspaceResultExport.scopedText(item, scope: "section", ordinal: 0))
        XCTAssertNil(WorkspaceResultExport.scopedText(item, scope: "whole", ordinal: 1))
        XCTAssertNil(WorkspaceResultExport.scopedText(item, scope: "section", ordinal: 999))
    }

    func testOnlyWebSourceAddressesAreOpenable() {
        XCTAssertNotNil(WorkspaceResultExport.sourceURL("https://example.org/source?a=1"))
        for address in ["javascript:alert(1)", "file:///private/data", "relative/path", "https:"] {
            XCTAssertNil(WorkspaceResultExport.sourceURL(address))
        }
    }

    func testExportSuccessFollowsActualWriteAndFailureIsNotReportedAsSaved() async throws {
        let exporter = WorkspaceExportCoordinator()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let destination = directory.appendingPathComponent("result.txt")
        let text = WorkspaceResultExport.text(try result())
        await exporter.write(text: text, to: destination)
        XCTAssertEqual(try String(contentsOf: destination, encoding: .utf8), text)
        XCTAssertEqual(exporter.message, "Saved result.txt.")
        XCTAssertFalse(exporter.busy)
        await exporter.write(text: text, to: destination) { _, _ in throw CocoaError(.fileWriteNoPermission) }
        XCTAssertTrue(exporter.message?.hasPrefix("Export failed:") == true)
        XCTAssertFalse(exporter.busy)
        XCTAssertEqual(try String(contentsOf: destination, encoding: .utf8), text)
    }
}
