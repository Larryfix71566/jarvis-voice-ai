import XCTest
@testable import JarvisKit

final class ComposedAnswerLayoutTests: XCTestCase {
    private let identity = "11111111-2222-3333-4444-555555555555"
    private func layout(_ blocks: [[String: Any]]? = nil) -> [String: Any] {
        ["version": 1, "revision": 1, "template": "text", "title": "Answer", "summary": "Summary", "complete": false,
         "blocks": blocks ?? [["id": "text", "type": "text", "format": "plain", "text": "Hello"]]]
    }
    private func payload(_ structure: [String: Any]?, extras: [String: Any] = [:]) throws -> DisplayPayload {
        var fields: [String: Any] = ["kind": "markdown", "body": "Legacy", "answer_id": identity, "answer_revision": 1]
        fields["layout"] = structure
        fields.merge(extras) { _, new in new }
        return try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: fields))
    }
    func testIdentitySurvivesLayoutFallbacks() throws {
        for mutation in [["version": 2], ["revision": 2], ["blocks": []], ["title": 42]] as [[String: Any]] {
            let p = try payload(layout().merging(mutation) { _, new in new })
            XCTAssertNil(p.layout); XCTAssertEqual(p.answerID?.uuidString, identity); XCTAssertEqual(p.answerRevision, 1)
        }
        XCTAssertEqual(try payload(nil).answerRevision, 1)
    }
    func testIdentityPairIsLenientAndAtomic() throws {
        for extras: [String: Any] in [["answer_revision": NSNull()], ["answer_revision": 0], ["answer_revision": -1], ["answer_revision": 1.5], ["answer_revision": "1"], ["answer_id": "invalid"], ["answer_id": NSNull()]] {
            let p = try payload(layout(), extras: extras)
            XCTAssertNil(p.answerID); XCTAssertNil(p.answerRevision); XCTAssertNil(p.layout); XCTAssertEqual(p.body, "Legacy")
        }
    }
    func testProtectedAndClipboardNeverRenderLayout() throws {
        for extras in [["data_policy": "local_only"], ["data_policy": "future_policy"], ["tool": "read_clipboard"], ["kind": "clipboard"], ["content": "secret"]] {
            XCTAssertNil(try payload(layout(), extras: extras).layout)
        }
        XCTAssertNotNil(try payload(layout(), extras: ["data_policy": "approved_external"]).layout)
    }
    func testUnknownBlocksSkippedButKnownMalformedInvalidates() throws {
        let text: [String: Any] = ["id": "text", "type": "text", "format": "plain", "text": "Hello"]
        let unknown: [String: Any] = ["id": "future", "type": "future"]
        XCTAssertEqual(try payload(layout([unknown, text])).layout?.blocks.map(\.id), ["text"])
        XCTAssertNil(try payload(layout([unknown])).layout)
        XCTAssertNil(try payload(layout([text, ["id": "broken", "type": "chart"]])).layout)
        XCTAssertNil(try payload(layout([text, text])).layout)
        XCTAssertNil(try payload(layout([["id": "action", "type": "actions", "items": []]])).layout)
    }
    func testURLsAndLimitsFailClosed() throws {
        for url in ["file:///tmp/image", "data:image/png;base64,abc", "javascript:alert(1)", "https://user:pass@example.org/image", "https:///", "//example.org/image"] {
            XCTAssertNil(try payload(layout([["id": "media", "type": "media", "images": [url], "a11y": "Image"]])).layout, url)
        }
        XCTAssertNotNil(try payload(layout([["id": "graph", "type": "graph", "image_url": "http://127.0.0.1:8484/graph.png", "summary": "Graph"]])).layout)
        XCTAssertNil(try payload(layout([["id": "text", "type": "text", "format": "plain", "text": String(repeating: "a", count: 30_001)]])).layout)
        XCTAssertNil(try payload(layout([["id": "media", "type": "media", "images": Array(repeating: "https://example.org/image", count: 10), "a11y": "Image"]])).layout)
        var oversized = layout(); oversized["extra"] = String(repeating: "x", count: 256 * 1024)
        XCTAssertNil(try payload(oversized).layout)
    }
    func testHeaderPositionAndCompletionComparison() throws {
        let header: [String: Any] = ["id": "header", "type": "header", "title": "Title", "summary": "Summary", "agents": []]
        let text: [String: Any] = ["id": "text", "type": "text", "format": "plain", "text": "Hello"]
        XCTAssertNotNil(try payload(layout([header, text])).layout)
        XCTAssertNil(try payload(layout([text, header])).layout)
        let first = try XCTUnwrap(payload(layout()).layout)
        var last = layout(); last["complete"] = true; last["revision"] = 2
        let completed = try XCTUnwrap(payload(last, extras: ["answer_revision": 2]).layout)
        XCTAssertTrue(first.hasSameContent(as: completed))
        let originalPayload = try payload(layout())
        XCTAssertTrue(try originalPayload.hasSameAnswerContent(as: payload(last, extras: ["answer_revision": 2, "ts": 999])))
        XCTAssertFalse(try originalPayload.hasSameAnswerContent(as: payload(last, extras: ["answer_revision": 2, "body": "Changed fallback"])))
        XCTAssertFalse(try originalPayload.hasSameAnswerContent(as: payload(nil)))
    }
    func testTotalDisplayBudgetFallsBackWithoutDiscardingIdentity() throws {
        // Each commands wrapper is individually valid and excluded from the
        // layout budget, but together they exceed the whole-display ceiling.
        let block: [String: Any] = ["id": "commands", "type": "commands", "commands": Array(repeating: String(repeating: "x", count: 30_000), count: 42)]
        let oversized = try payload(layout([block]))
        XCTAssertNil(oversized.layout)
        XCTAssertEqual(oversized.answerID?.uuidString, identity)
        XCTAssertEqual(oversized.answerRevision, 1)
        XCTAssertEqual(oversized.body, "Legacy")
        XCTAssertNotNil(try payload(layout(), extras: ["body": String(repeating: "x", count: 1_000_000)]).layout)
        XCTAssertNil(try payload(layout(), extras: ["body": String(repeating: "x", count: 1200 * 1024)]).layout)
    }
    func testContentBlocksAndOptionalComposerFields() throws {
        let blocks: [[String: Any]] = [
            ["id": "header", "type": "header", "title": "Title", "summary": "Summary", "source": ["tool": "display"]],
            ["id": "stats", "type": "stats", "items": [["value": "1", "label": "Result", "tone": "ok"]]],
            ["id": "list", "type": "list", "items": [["title": "Item", "detail": "Detail", "meta": "Meta"]], "more_count": 2],
            ["id": "chart", "type": "chart", "chart": "bar", "points": [["label": "A", "value": -2], ["label": "B", "value": 3, "highlight": true]], "a11y": "A minus two, B three"],
            ["id": "media", "type": "media", "images": ["https://example.org/image"], "a11y": "Image"],
            ["id": "sources", "type": "sources", "items": [["label": "Example", "url": "https://example.org"]]],
            ["id": "commands", "type": "commands", "commands": ["echo hello"]],
            ["id": "graph", "type": "graph", "image_url": "http://localhost:8484/graph.png"]
        ]
        XCTAssertEqual(try payload(layout(blocks)).layout?.blocks.count, blocks.count)
        for type in ["weather", "brief", "roadmap"] {
            XCTAssertNil(try payload(layout([["id": type, "type": type, type: [:]]])).layout)
        }
        XCTAssertNil(try payload(layout([["id": "bad", "type": "stats", "items": [["value": "1", "label": "Result", "tone": "future"]]]])).layout)
        XCTAssertNil(try payload(layout([["id": "bad", "type": "chart", "chart": "line", "points": [], "a11y": "Chart"]])).layout)
    }
    func testContractTransitionFixturesDecodeIndependentlyOfRenderMode() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "composed-answer-transitions", withExtension: "json", subdirectory: "Fixtures"))
        let sequences = try JSONDecoder().decode([[DisplayPayload]].self, from: Data(contentsOf: url))
        XCTAssertEqual(sequences.count, 5)
        XCTAssertEqual(sequences.map { $0.map(\.answerRevision) }, [[1, 2], [2, 1, 1], [1, 2], [1, 2], [nil]])
        XCTAssertEqual(sequences.map { $0.map { $0.layout != nil } }, [[true, false], [false, true, true], [false, true], [true, false], [false]])
    }
}
