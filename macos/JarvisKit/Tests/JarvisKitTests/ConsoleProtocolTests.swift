import XCTest
@testable import JarvisKit

final class ConsoleProtocolTests: XCTestCase {
    func testProtocolFixtureRoundTripsIncludingSecondaryTarget() throws {
        let data = #"{"type":"console/request","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","request_id":"00000000-0000-4000-8000-000000000003","revision":0,"action":"inventory","target":null,"secondary_target":null,"args":{}}"#.data(using: .utf8)!
        let request = try JSONDecoder().decode(ConsoleRequest.self, from: data)
        XCTAssertEqual(request.action, .inventory)
        XCTAssertNil(request.secondaryTarget)
        XCTAssertEqual(try JSONDecoder().decode(ConsoleRequest.self,
            from: JSONEncoder().encode(request)), request)
    }

    func testUnknownActionIsRejectedByClosedEnum() {
        let data = #"{"type":"console/request","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","request_id":"00000000-0000-4000-8000-000000000003","revision":0,"action":"made_up","args":{}}"#.data(using: .utf8)!
        XCTAssertThrowsError(try JSONDecoder().decode(ConsoleRequest.self, from: data))
    }

    func testConsoleResultDecodesBoundedSummaryAndChoices() throws {
        let data = #"{"type":"console/result","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","request_id":"00000000-0000-4000-8000-000000000003","status":"needs_choice","code":"duplicate_title","summary":"choose","choices":[{"id":"a","label":"First"}]}"#.data(using: .utf8)!
        let result = try JSONDecoder().decode(ConsoleResult.self, from: data)
        XCTAssertEqual(result.status, "needs_choice")
        XCTAssertEqual(result.choices?.first?.label, "First")
    }

    func testClientConsoleRequestUsesRawLockedShape() throws {
        let request = ConsoleRequest(
            sessionID: UUID(uuidString: "00000000-0000-4000-8000-000000000001")!,
            generation: UUID(uuidString: "00000000-0000-4000-8000-000000000002")!,
            requestID: UUID(uuidString: "00000000-0000-4000-8000-000000000003")!,
            revision: 0, action: .inventory)
        let message = ClientMessage.consoleRequest(request)
        let encoded = try JSONSerialization.jsonObject(with: message.jsonData()) as! [String: Any]
        XCTAssertEqual(encoded["type"] as? String, "console/request")
        XCTAssertNil(encoded["label"])
    }

    func testHelloDecodesAndReadyUsesMatchingSessionGeneration() throws {
        let data = #"{"type":"console/hello","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","actions":["view_set"],"input_types":["text/plain"],"input_profile":{"id":"vision","label":"Configured vision"}}"#.data(using: .utf8)!
        let hello = try JSONDecoder().decode(ConsoleHello.self, from: data)
        XCTAssertEqual(hello.actions, ["view_set"])
        XCTAssertEqual(hello.inputProfile?.label, "Configured vision")
        let message = ClientMessage.consoleReady(sessionID: hello.sessionID,
                                                  generation: hello.generation,
                                                  actions: hello.actions,
                                                  inputTypes: hello.inputTypes)
        let encoded = try JSONSerialization.jsonObject(with: message.jsonData()) as! [String: Any]
        XCTAssertEqual(encoded["type"] as? String, "console/ready")
        XCTAssertEqual(encoded["session_id"] as? String, hello.sessionID.uuidString)
        XCTAssertEqual(encoded["generation"] as? String, hello.generation.uuidString)
    }

    func testNativeInventoryUsesRevisionAndSafeJSONPayload() throws {
        let session = UUID(uuidString: "00000000-0000-4000-8000-000000000001")!
        let generation = UUID(uuidString: "00000000-0000-4000-8000-000000000002")!
        let inventory = ConsoleInventory(
            sessionID: session, generation: generation, revision: 9,
            data: .object(["mode": .string("atlas"), "results": .array([])]))
        let encoded = try JSONSerialization.jsonObject(
            with: ClientMessage.consoleInventory(inventory).jsonData()) as! [String: Any]
        XCTAssertEqual(encoded["type"] as? String, "console/inventory")
        XCTAssertEqual(encoded["revision"] as? Int, 9)
        XCTAssertNil(encoded["body"])
        let roundTrip = try JSONDecoder().decode(ConsoleInventory.self,
                                                  from: try JSONSerialization.data(withJSONObject: encoded))
        XCTAssertEqual(roundTrip, inventory)
    }
}
