import XCTest
@testable import JarvisKit

final class SharedContentTransferTests: XCTestCase {
    func testRoundTripPreservesApprovalAndEphemeralFlags() throws {
        let item = SharedContentTransfer(kind: .text, mimeType: "text/plain",
                                          digest: "abc", payload: Data("hello".utf8),
                                          provider: "openai", approved: true)
        let decoded = try JSONDecoder().decode(SharedContentTransfer.self,
            from: JSONEncoder().encode(item))
        XCTAssertEqual(decoded, item)
    }

    func testApprovedInputSequenceUsesRawBoundedMessages() throws {
        let session = UUID(uuidString: "00000000-0000-4000-8000-000000000001")!
        let generation = UUID(uuidString: "00000000-0000-4000-8000-000000000002")!
        let attachment = SharedContentTransfer(kind: .text, mimeType: "text/plain",
                                                digest: String(repeating: "a", count: 64),
                                                payload: Data("hello".utf8))
        let manifest = InputManifest(sessionID: session, generation: generation,
                                     batchID: UUID(uuidString: "00000000-0000-4000-8000-000000000003")!,
                                     approvalID: UUID(uuidString: "00000000-0000-4000-8000-000000000004")!,
                                     question: "Summarize", attachments: [InputManifestAttachment(attachment)])
        let message = ClientMessage.inputManifest(manifest)
        let encoded = try JSONSerialization.jsonObject(with: message.jsonData()) as! [String: Any]
        XCTAssertEqual(encoded["type"] as? String, "input/manifest")
        XCTAssertEqual(encoded["version"] as? Int, 1)
        XCTAssertNil(encoded["path"])
        let metadata = (encoded["attachments"] as! [[String: Any]]).first!
        XCTAssertEqual(metadata["content_id"] as? String, attachment.contentID.uuidString)
        XCTAssertEqual(metadata["total_bytes"] as? Int, 5)
    }
}
