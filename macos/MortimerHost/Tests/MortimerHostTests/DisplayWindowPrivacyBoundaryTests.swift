import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class DisplayWindowPrivacyBoundaryTests: XCTestCase {
    private func payload(_ json: String) throws -> DisplayPayload {
        try JSONDecoder().decode(DisplayPayload.self, from: Data(json.utf8))
    }

    func testDirectDisplaySinkRejectsProtectedPayloadBeforeDeveloperBatchAppend() throws {
        let store = DisplayWindowStore()
        let publicItem = try payload(
            #"{"title":"Public file result","body":"public content","surface":"window","agent":"Developer","run_id":"run-1"}"#
        )
        let panelID = try XCTUnwrap(store.apply(publicItem))
        let protectedItem = try payload(
            #"{"title":"PRIVATE TITLE CANARY","body":"PRIVATE BODY CANARY","surface":"window","agent":"Developer","run_id":"run-1","data_policy":"local_only","links":[{"label":"PRIVATE LINK","url":"https://private.invalid/?token=secret"}]}"#
        )

        XCTAssertNil(store.apply(protectedItem), "the display sink must reject protected payloads")
        XCTAssertEqual(store.panels.count, 1)
        let panel = try XCTUnwrap(store.panels.first)
        XCTAssertEqual(panel.id, panelID)
        XCTAssertEqual(panel.payload, publicItem)
        XCTAssertTrue(panel.appendedPayloads.isEmpty,
                      "a rejected payload must not append to an existing Developer request tile")
        let serialized = String(describing: store.panels)
        XCTAssertFalse(serialized.contains("PRIVATE TITLE CANARY"))
        XCTAssertFalse(serialized.contains("PRIVATE BODY CANARY"))
        XCTAssertFalse(serialized.contains("PRIVATE LINK"))
    }

    func testComposedRevisionSinkRejectsProtectedCreationAndReplacement() throws {
        let store = DisplayWindowStore()
        let protectedPayload = try payload(
            #"{"title":"PRIVATE RESPONSE CANARY","body":"PRIVATE STREAM CANARY","surface":"window","data_policy":"confidential","answer_id":"11111111-2222-3333-4444-555555555555","answer_revision":2}"#
        )

        XCTAssertNil(store.apply(protectedPayload))
        XCTAssertTrue(store.panels.isEmpty, "protected response must not create a supporting tile")

        let publicPayload = try payload(
            #"{"title":"Public response","body":"public streamed response","surface":"window","answer_id":"11111111-2222-3333-4444-555555555555","answer_revision":1}"#
        )
        XCTAssertNotNil(store.apply(publicPayload))
        XCTAssertNil(store.updateExistingAnswer(protectedPayload))

        XCTAssertEqual(store.panels.count, 1)
        XCTAssertEqual(store.panels.first?.payload, publicPayload,
                       "a protected streamed update must not replace an existing public response")
        XCTAssertFalse(String(describing: store.panels).contains("PRIVATE STREAM CANARY"))
    }
}
