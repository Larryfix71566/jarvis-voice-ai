import XCTest
@testable import JarvisKit

final class ClientMessageTests: XCTestCase {
    private func jsonObject(_ data: Data) throws -> [String: Any] {
        try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testVoiceSetEncodesRawShape() throws {
        let msg = ClientMessage.voiceSet(voice: "bella")
        let data = try jsonData(msg)
        let obj = try jsonObject(data)
        XCTAssertEqual(obj.count, 2)
        XCTAssertEqual(obj["type"] as? String, "voice/set")
        XCTAssertEqual(obj["voice"] as? String, "bella")
    }

    func testUiNoopEncodesRawShape() throws {
        let msg = ClientMessage.uiNoop(reason: "The drawer is already open.")
        let data = try jsonData(msg)
        let obj = try jsonObject(data)
        XCTAssertEqual(obj.count, 2)
        XCTAssertEqual(obj["type"] as? String, "ui/noop")
        XCTAssertEqual(obj["reason"] as? String, "The drawer is already open.")
    }

    func testNoopRejectsEmpty() {
        XCTAssertNil(ClientMessage.noop("   "))
    }

    func testNoopRejectsOver200Chars() {
        let s = String(repeating: "a", count: 201)
        XCTAssertNil(ClientMessage.noop(s))
    }

    func testNoopAcceptsExactly200Chars() {
        let s = String(repeating: "a", count: 200)
        XCTAssertNotNil(ClientMessage.noop(s))
    }

    // jsonData() is package-internal (no `public`) — call it via the same
    // module the test target links against.
    private func jsonData(_ msg: ClientMessage) throws -> Data {
        try msg.jsonData()
    }
}
