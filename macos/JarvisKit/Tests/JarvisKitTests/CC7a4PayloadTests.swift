import XCTest
@testable import JarvisKit

final class CC7a4PayloadTests: XCTestCase {
    private func payload(_ changes: [String: Any] = [:]) throws -> DisplayPayload {
        var fields: [String: Any] = [
            "title": "Weather", "body": "Existing fallback body", "kind": "weather",
            "tool": "weather_report", "data_policy": "approved_external",
            "subject_key": "weather:named:atlanta", "ts": 100, "fresh_until": 1000,
            "weather_source": ["weather": ["city": "Atlanta", "units": "imperial"],
                               "radar": NSNull(), "subject_aliases": ["atlanta"]]
        ]
        fields.merge(changes) { _, new in new }
        return try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: fields))
    }

    func testOriginalFetchTimingAndZeroSurviveReplay() throws {
        let ordinary = try payload()
        XCTAssertEqual(ordinary.subjectKey, "weather:named:atlanta")
        XCTAssertEqual(ordinary.ts, 100)
        XCTAssertEqual(ordinary.freshUntil, 1000)
        XCTAssertNotNil(ordinary.weatherSource)
        let zero = try payload(["ts": 0, "fresh_until": 900])
        XCTAssertEqual(zero.ts, 0)
        XCTAssertEqual(zero.freshUntil, 900)
        XCTAssertNotNil(zero.weatherSource)
    }

    func testInvalidCacheMetadataKeepsLegacyBodyAndSafeKey() throws {
        for changes: [String: Any] in [
            ["fresh_until": "wrong"], ["fresh_until": 1001], ["fresh_until": 99],
            ["weather_source": ["weather": "wrong"]],
            ["weather_source": ["weather": [:], "subject_aliases": [true]]],
            ["weather_source": ["weather": [:], "subject_aliases": [" Atlanta "]]],
            ["weather_source": ["weather": [:], "subject_aliases": Array(repeating: "atlanta", count: 9)]],
            ["weather_source": ["weather": [:], "unexpected": "field"]],
            ["weather_source": ["weather": ["human": String(repeating: "界", count: 6000)]]]
        ] {
            let decoded = try payload(changes)
            XCTAssertEqual(decoded.body, "Existing fallback body")
            XCTAssertEqual(decoded.subjectKey, "weather:named:atlanta")
            XCTAssertNil(decoded.weatherSource)
            XCTAssertNil(decoded.freshUntil)
        }
    }

    func testInvalidOrMissingKeyDisablesReuseRatherThanTruncatingIdentity() throws {
        for key: Any in [NSNull(), true, "", String(repeating: "x", count: 201),
                         "a" + String(repeating: "\u{0301}", count: 201)] {
            let decoded = try payload(["subject_key": key])
            XCTAssertNil(decoded.subjectKey)
            XCTAssertNil(decoded.weatherSource)
            XCTAssertEqual(decoded.body, "Existing fallback body")
        }
    }

    func testCanonicalUnicodeAliasesAndUnescapedURLBudget() throws {
        let source: [String: Any] = ["weather": ["human": "forecast"],
                                    "subject_aliases": ["strasse", "i\u{0307}", "são paulo"],
                                    "radar": ["tiles": ["https://example.invalid/" + String(repeating: "/", count: 10000)]]]
        let decoded = try payload(["weather_source": source])
        XCTAssertNotNil(decoded.weatherSource, "URL escaping must not create a stricter source-field budget")
    }

    func testLegacyPayloadRemainsRenderableWithoutCacheFields() throws {
        let decoded = try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"title":"Legacy","body":"Still available","ts":0}"#.utf8))
        XCTAssertEqual(decoded.body, "Still available")
        XCTAssertEqual(decoded.ts, 0)
        XCTAssertNil(decoded.subjectKey)
        XCTAssertNil(decoded.freshUntil)
        XCTAssertNil(decoded.weatherSource)
    }
}
