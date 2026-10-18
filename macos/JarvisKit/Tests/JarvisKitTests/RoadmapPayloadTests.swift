import XCTest
@testable import JarvisKit

final class RoadmapPayloadTests: XCTestCase {
    private func snapshot() -> [String: Any] {
        ["schema": "mortimer.roadmap.v1", "provenance": [
            "path": "ROADMAP.md", "repository_id": String(repeating: "d", count: 64), "revision": String(repeating: "a", count: 40),
            "sha256": String(repeating: "b", count: 64), "read_at": "2026-10-17T20:10:20.123+00:00",
            "dirty": false, "source_kind": "local_checkout"],
         "cards": [["id": "WS-17", "title": "Console", "status": "landed; acceptance open",
                    "lifecycle": "landed", "owner": "codex", "fields": ["Unknown": "retained"],
                    "details": String(repeating: "source ", count: 5000),
                    "checklist": [["text": "Larry checks", "checked": false, "section": "Acceptance"]]]],
         "logs": [["path": "docs/roadmap-log/entry.md", "date": "2026-10-17", "rows": ["WS-17"],
                   "sha256": String(repeating: "c", count: 64), "title": "Evidence"]], "issues": []]
    }
    private func decode(_ value: [String: Any]?) throws -> DisplayPayload {
        var body: [String: Any] = ["kind": "text", "title": "Roadmap", "body": "Fallback source"]
        if let value { body["roadmap"] = value }
        return try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: body))
    }
    func testCompleteCardAndUnknownFieldsRetainedWithoutOldTextCap() throws {
        let value = try XCTUnwrap(decode(snapshot()).roadmap)
        XCTAssertGreaterThan(value.cards[0].details.count, 30000)
        XCTAssertEqual(value.cards[0].fields["Unknown"], "retained")
        XCTAssertEqual(value.cards[0].lifecycle, "landed")
        XCTAssertFalse(value.cards[0].checklist[0].checked)
        XCTAssertEqual(value.logs[0].rows, ["WS-17"])
    }
    func testInvalidSnapshotDoesNotReplaceLegacyFallback() throws {
        var wrong = snapshot(); wrong["schema"] = "future"
        var duplicate = snapshot(); duplicate["cards"] = (duplicate["cards"] as! [[String: Any]]) + (duplicate["cards"] as! [[String: Any]])
        var tooLarge = snapshot(); tooLarge["issues"] = [String(repeating: "x", count: 600000)]
        for value in [wrong, duplicate, tooLarge] {
            let decoded = try decode(value)
            XCTAssertNil(decoded.roadmap)
            XCTAssertEqual(decoded.body, "Fallback source")
        }
        XCTAssertNil(try decode(nil).roadmap)
    }
    func testMalformedLogDatePathAndRowsRefuseWholeSnapshot() throws {
        for change: [String: Any] in [
            ["date": "2026-02-30"], ["path": "docs/roadmap-log/../private.md"],
            ["rows": []], ["sha256": "invented"]
        ] {
            var value = snapshot()
            var logs = value["logs"] as! [[String: Any]]
            logs[0].merge(change) { _, new in new }
            value["logs"] = logs
            XCTAssertNil(try decode(value).roadmap)
        }
    }

}
