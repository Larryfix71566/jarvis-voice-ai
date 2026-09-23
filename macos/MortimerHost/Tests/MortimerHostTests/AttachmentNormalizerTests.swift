import XCTest
import Foundation
@testable import MortimerHost

final class AttachmentNormalizerTests: XCTestCase {
    func testTextIsNormalizedAndBounded() {
        let item = AttachmentNormalizer.text(" hello\u{0}\nworld ")
        XCTAssertEqual(item?.kind, .text); XCTAssertEqual(String(data: item!.payload, encoding: .utf8), "hello\nworld")
        XCTAssertNil(AttachmentNormalizer.text(String(repeating: "x", count: AttachmentNormalizer.maxTextCharacters + 1)))
    }

    func testImageTypeAndQuotaAreEnforced() {
        let tinyPNG = Data(base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")!
        XCTAssertNotNil(AttachmentNormalizer.image(tinyPNG, mimeType: "image/png"))
        XCTAssertNil(AttachmentNormalizer.image(Data([1]), mimeType: "image/svg+xml"))
        XCTAssertNil(AttachmentNormalizer.image(Data([1, 2]), mimeType: "image/png"))
        XCTAssertNil(AttachmentNormalizer.image(Data(repeating: 0, count: AttachmentNormalizer.maxImageBytes + 1), mimeType: "image/png"))
    }
}
