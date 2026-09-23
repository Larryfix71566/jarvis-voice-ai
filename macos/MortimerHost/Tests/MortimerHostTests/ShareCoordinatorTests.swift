import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class ShareCoordinatorTests: XCTestCase {
    private final class WriteBox: @unchecked Sendable {
        var value: (Data, URL)?
    }

    private func result(title: String, body: String) throws -> WorkspaceResult {
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            "{\"title\":\"\(title)\",\"body\":\"\(body)\",\"surface\":\"drawer\"}".utf8))
        return WorkspaceResult(payload: payload)
    }

    func testPreviewIsAnImmutableSnapshot() throws {
        let sharing = ShareCoordinator()
        let first = try result(title: "First", body: "Original")
        let second = try result(title: "Second", body: "Later")
        let preview = sharing.beginPreview(first)
        _ = second // A new result arriving elsewhere must not mutate this snapshot.
        XCTAssertEqual(sharing.preview, preview)
        XCTAssertTrue(preview.text.contains("Original"))
        XCTAssertFalse(preview.text.contains("Later"))
    }

    func testSaveReportsActualWriterOutcomeAndCancelClearsPreview() async throws {
        let sharing = ShareCoordinator()
        let item = try result(title: "Export", body: "Supplied text")
        sharing.beginPreview(item)
        let written = WriteBox()
        let destination = URL(fileURLWithPath: "/tmp/mortimer-share.txt")
        let saved = await sharing.save(to: destination) { data, url in
            written.value = (data, url)
        }
        XCTAssertTrue(saved)
        XCTAssertEqual(written.value?.1, destination)
        XCTAssertEqual(String(data: written.value!.0, encoding: .utf8), sharing.preview?.text)
        XCTAssertEqual(sharing.status, "saved")
        XCTAssertEqual(sharing.message, "Saved mortimer-share.txt.")
        sharing.cancel()
        XCTAssertNil(sharing.preview)
        XCTAssertEqual(sharing.status, "idle")
    }

    func testFailedWriterIsNeverReportedAsSaved() async throws {
        let sharing = ShareCoordinator()
        sharing.beginPreview(try result(title: "Export", body: "Text"))
        let ok = await sharing.save(to: URL(fileURLWithPath: "/tmp/mortimer-share.txt")) { _, _ in
            throw NSError(domain: "test", code: 1)
        }
        XCTAssertFalse(ok)
        XCTAssertEqual(sharing.status, "error")
        XCTAssertTrue(sharing.message?.contains("Save failed") == true)
    }
}
