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

    func testStreamedResponseSinkRejectsProtectedCreationAndReplacement() throws {
        let store = DisplayWindowStore()
        let protectedPayload = try payload(
            #"{"title":"PRIVATE RESPONSE CANARY","body":"PRIVATE STREAM CANARY","surface":"window","data_policy":"confidential"}"#
        )
        let protectedResult = WorkspaceResult(payload: protectedPayload)

        store.presentResponse(protectedResult, isNew: true)
        XCTAssertTrue(store.panels.isEmpty, "protected response must not create a supporting tile")

        let publicPayload = try payload(
            #"{"title":"Public response","body":"public streamed response","surface":"window"}"#
        )
        let publicResult = WorkspaceResult(payload: publicPayload)
        store.presentResponse(publicResult, isNew: true)
        store.presentResponse(protectedResult, isNew: false)

        XCTAssertEqual(store.panels.count, 1)
        XCTAssertEqual(store.panels.first?.payload, publicPayload,
                       "a protected streamed update must not replace an existing public response")
        XCTAssertFalse(String(describing: store.panels).contains("PRIVATE STREAM CANARY"))
    }
}
