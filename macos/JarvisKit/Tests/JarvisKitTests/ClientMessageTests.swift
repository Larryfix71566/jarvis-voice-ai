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

    // MARK: - C7b typed request (contract 2.2)

    private let typedSession = UUID(uuidString: "00000000-0000-4000-8000-000000000001")!
    private let typedGeneration = UUID(uuidString: "00000000-0000-4000-8000-000000000002")!
    private let typedRequestID = UUID(uuidString: "00000000-0000-4000-8000-000000000003")!

    private func typedObject(source: TypedRequest.Source) throws -> [String: Any] {
        let request = TypedRequest(sessionID: typedSession, generation: typedGeneration,
                                   requestID: typedRequestID, text: "what is the weather",
                                   source: source)
        return try jsonObject(try jsonData(.typedRequest(request)))
    }

    func testTypedRequestEncodesExactlySevenKeys() throws {
        let obj = try typedObject(source: .composer)
        XCTAssertEqual(obj.count, 7)
        XCTAssertEqual(obj["type"] as? String, "turn/typed")
        XCTAssertEqual(obj["version"] as? Int, 1)
        XCTAssertEqual(obj["text"] as? String, "what is the weather")
        XCTAssertEqual(obj["source"] as? String, "composer")
        XCTAssertEqual(UUID(uuidString: obj["session_id"] as? String ?? ""), typedSession)
        XCTAssertEqual(UUID(uuidString: obj["generation"] as? String ?? ""), typedGeneration)
        XCTAssertEqual(UUID(uuidString: obj["request_id"] as? String ?? ""), typedRequestID)
    }

    func testTypedRequestChipSource() throws {
        let obj = try typedObject(source: .chip)
        XCTAssertEqual(obj["source"] as? String, "chip")
    }

    func testTypedRequestMatchesContractFixtureShape() throws {
        let obj = try typedObject(source: .composer)
        let expected: Set<String> = ["type", "version", "session_id", "generation",
                                     "request_id", "text", "source"]
        XCTAssertEqual(Set(obj.keys), expected)
    }
}
