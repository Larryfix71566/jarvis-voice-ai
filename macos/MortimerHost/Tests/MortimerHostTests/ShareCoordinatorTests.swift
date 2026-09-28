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

    private func tinyPNG() -> Data {
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1, pixelsHigh: 1,
                                      bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                      isPlanar: false, colorSpaceName: .deviceRGB,
                                      bytesPerRow: 0, bitsPerPixel: 0)!
        return bitmap.representation(using: .png, properties: [:])!
    }

    func testPreviewIsAnImmutableSnapshot() throws {
        let sharing = ShareCoordinator()
        let first = try result(title: "First", body: "Original")
        let second = try result(title: "Second", body: "Later")
        let preview = try XCTUnwrap(sharing.beginPreview(first))
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

    func testProtectedLocalResultCannotCreateSharePreview() throws {
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected","body":"private text","surface":"window","data_policy":"confidential","opaque_ref":"opaque-123"}"#.utf8))
        XCTAssertTrue(payload.isProtectedLocal)
        XCTAssertEqual(payload.opaqueRef, "opaque-123")
        let sharing = ShareCoordinator()
        XCTAssertNil(sharing.beginPreview(WorkspaceResult(payload: payload)))
        XCTAssertNil(sharing.preview)
        XCTAssertEqual(sharing.status, "error")

        let workspace = WorkspaceStore()
        let result = WorkspaceResult(payload: payload)
        workspace.exporter.chooseDestination(for: result)
        XCTAssertFalse(workspace.exporter.busy)
        XCTAssertEqual(workspace.exporter.message, "This protected result cannot be exported.")

        var copied: [String] = []
        workspace.exporter.copy(result: result) { text in
            copied.append(text)
            return true
        }
        XCTAssertTrue(copied.isEmpty, "protected result text must never reach a clipboard writer")
        XCTAssertEqual(workspace.exporter.message,
                       "This protected result cannot be copied or exported.")
    }

    func testEveryNonExternalPolicyFailsClosedAcrossTextSinks() async throws {
        // The contract is deliberately fail-closed: only the exact
        // approved_external label may leave the local result surface. This
        // also protects against policy labels added by a newer producer.
        for policy in ["local_only", "confidential", "future_restricted_policy"] {
            let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
                """
                {"title":"Protected title canary","body":"Protected body canary",\
                "surface":"window","data_policy":"\(policy)",\
                "links":[{"label":"Protected link","url":"https://private.invalid/?token=secret"}],\
                "commands":["protected command"],"content":"protected clipboard"}
                """.utf8))
            let item = WorkspaceResult(payload: payload)
            XCTAssertTrue(payload.isProtectedLocal, "policy must be protected: \(policy)")

            let sharing = ShareCoordinator()
            XCTAssertNil(sharing.beginPreview(item, text: "caller supplied private text"), policy)
            XCTAssertNil(sharing.preview, policy)
            XCTAssertFalse(sharing.beginImagePreview(result: item,
                sourceURL: URL(string: "https://example.org/image.png")!, pngData: tinyPNG()), policy)
            XCTAssertNil(sharing.preview, policy)

            let exporter = WorkspaceExportCoordinator()
            var copied: [String] = []
            exporter.copy(result: item) { copied.append($0); return true }
            XCTAssertTrue(copied.isEmpty, "protected text reached clipboard for \(policy)")
            XCTAssertEqual(exporter.message, "This protected result cannot be copied or exported.")
            exporter.chooseDestination(for: item)
            XCTAssertFalse(exporter.busy, "protected result opened a save dialog for \(policy)")

            let writer = WriteBox()
            await exporter.write(result: item, to: URL(fileURLWithPath: "/tmp/protected-canary.txt")) { _, _ in
                writer.value = (Data(), URL(fileURLWithPath: "/tmp/protected-canary.txt"))
            }
            XCTAssertNil(writer.value, "protected result reached file writer for \(policy)")
            XCTAssertEqual(exporter.message, "This protected result cannot be exported.")
        }
    }

    func testImageShareRequiresExactApprovedResultReferenceAndReencodesBitmap() throws {
        let source = URL(string: "https://example.org/result.png")!
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Approved image","surface":"drawer","data_policy":"approved_external","images":["https://example.org/result.png"]}"#.utf8))
        let item = WorkspaceResult(payload: payload)
        let sharing = ShareCoordinator()

        XCTAssertTrue(sharing.beginImagePreview(result: item, sourceURL: source, pngData: tinyPNG()))
        XCTAssertEqual(sharing.preview?.resultID, item.id)
        XCTAssertEqual(sharing.preview?.format, "png")
        XCTAssertNotEqual(sharing.preview?.data, tinyPNG(), "source PNG must be decoded and re-encoded")

        let unclassified = try result(title: "Unclassified", body: "text only")
        XCTAssertFalse(sharing.beginImagePreview(result: unclassified, sourceURL: source, pngData: tinyPNG()))
        XCTAssertNil(sharing.preview)
        XCTAssertFalse(sharing.beginImagePreview(result: item,
            sourceURL: URL(string: "https://example.org/other.png")!, pngData: tinyPNG()))
        XCTAssertNil(sharing.preview)

        let graphPayload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Graph","surface":"drawer","data_policy":"approved_external","images":["https://example.org/api/graph/memory/image.png"]}"#.utf8))
        XCTAssertFalse(sharing.beginImagePreview(result: WorkspaceResult(payload: graphPayload),
            sourceURL: URL(string: "https://example.org/api/graph/memory/image.png")!, pngData: tinyPNG()))
        XCTAssertNil(sharing.preview)
    }

    func testLocalExportCoordinatorCopiesOnlyAnUnprotectedResult() throws {
        let result = try result(title: "Allowed", body: "Public response")
        let exporter = WorkspaceExportCoordinator()
        var copied: [String] = []

        exporter.copy(result: result) { text in
            copied.append(text)
            return true
        }

        XCTAssertEqual(copied, [WorkspaceResultExport.text(result)])
        XCTAssertEqual(exporter.message, "Copied result.")
    }
}
