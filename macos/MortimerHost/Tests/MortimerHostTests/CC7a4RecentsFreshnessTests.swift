import XCTest
import JarvisKit
@testable import MortimerHost

/// Recents presents source age independently of the card's arrival position.
/// These fixtures exercise the retained store and actual menu/voice projections.
@MainActor
final class CC7a4RecentsFreshnessTests: XCTestCase {
    private func weather(_ title: String, ts: Double?, receivedAt: TimeInterval) throws -> WorkspaceResult {
        var fields: [String: Any] = [
            "kind": "weather", "tool": "weather_report", "title": title,
            "body": "Public synthetic weather body", "data_policy": "approved_external",
            "subject_key": "weather:named:\(title.lowercased())",
        ]
        if let ts {
            if ts.isFinite {
                fields["ts"] = ts
                fields["fresh_until"] = ts + 900
            } else {
                fields["ts"] = ts.isNaN ? "NaN" : (ts > 0 ? "Infinity" : "-Infinity")
            }
        }
        let decoder = JSONDecoder()
        decoder.nonConformingFloatDecodingStrategy = .convertFromString(
            positiveInfinity: "Infinity", negativeInfinity: "-Infinity", nan: "NaN")
        let payload = try decoder.decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: fields))
        return WorkspaceResult(payload: payload, receivedAt: Date(timeIntervalSince1970: receivedAt))
    }

    private func assertAge(_ entry: WorkspaceRecents.Entry, _ expected: String, now: Date,
                           file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(ConsoleActionBar.recentsRowTitle(entry, now: now), "\(entry.label) · \(expected)",
                       "The menu must present source age", file: file, line: line)
        XCTAssertTrue(ConsoleActionBar.recentsAccessibilityLabel(entry, now: now)
            .components(separatedBy: ", ").contains(expected),
                      "VoiceOver must present the same source age", file: file, line: line)
        let choice = WorkspaceRecents.choices([entry], now: now).first
        XCTAssertEqual(choice?.id, entry.id.uuidString, file: file, line: line)
        XCTAssertEqual(choice?.label, "\(entry.label) · \(expected)",
                       "Clarification choices must match the menu's source age", file: file, line: line)
    }

    func testStoreRefreshUpdatesAllAgeLabelsWithoutMovingCardOrRecentsNumber() throws {
        let store = WorkspaceStore()
        let a = try weather("Folly Beach", ts: 1_000, receivedAt: 1_000)
        let b = try weather("Atlanta", ts: 1_500, receivedAt: 1_500)
        let pinned = try weather("Paris", ts: 900, receivedAt: 900)
        store.receive(a, quietly: true); store.receive(b, quietly: true); store.receive(pinned, quietly: true)
        XCTAssertTrue(store.pin(pinned.id))
        store.select(b.id); XCTAssertTrue(store.compare(with: a.id))
        store.rememberScroll(240, for: a.id)
        let before = store.recents
        XCTAssertEqual(before.entries.map(\.id), [pinned.id, b.id, a.id])
        XCTAssertEqual(before.entries.map(\.number), [1, 2, 3])

        let refreshed = try weather("Folly Beach", ts: 2_000, receivedAt: 2_000)
        XCTAssertEqual(store.receive(refreshed, quietly: true, answersCurrentRequest: true), a.id)
        let after = store.recents
        XCTAssertEqual(store.results.map(\.id), [a.id, b.id, pinned.id])
        XCTAssertEqual(after.entries.map(\.id), before.entries.map(\.id))
        XCTAssertEqual(after.entries.map(\.number), before.entries.map(\.number))
        XCTAssertEqual(after.pinned.map(\.id), [pinned.id])
        XCTAssertEqual(store.activeID, b.id); XCTAssertEqual(store.comparisonID, a.id)
        XCTAssertEqual(store.scrollOffsets[a.id], 240)
        let retained = try XCTUnwrap(store.results.first { $0.id == a.id })
        let entry = try XCTUnwrap(after.entries.first { $0.id == a.id })
        XCTAssertEqual(retained.payload.ts, 2_000)
        XCTAssertEqual(retained.receivedAt, a.receivedAt)
        XCTAssertEqual(entry.receivedAt, a.receivedAt)
        XCTAssertEqual(entry.card.time, a.receivedAt)
        XCTAssertEqual(entry.freshnessDate, Date(timeIntervalSince1970: 2_000))
        assertAge(entry, "now", now: Date(timeIntervalSince1970: 2_000))
    }

    func testZeroSourceReplayAndMissingOrNonfiniteTimestampFallback() throws {
        let now = Date(timeIntervalSince1970: 1_200)
        let cases: [(String, Double?, TimeInterval, String)] = [
            ("Zero", 0, 1_200, "20m"),
            ("Missing", nil, 900, "5m"),
            ("Positive infinity", .infinity, 600, "10m"),
            ("Negative infinity", -.infinity, 600, "10m"),
            ("NaN", .nan, 600, "10m"),
        ]
        for (title, ts, arrival, expected) in cases {
            let store = WorkspaceStore()
            let result = try weather(title, ts: ts, receivedAt: arrival)
            store.receive(result, quietly: true)
            let entry = try XCTUnwrap(store.recents.entries.first)
            XCTAssertEqual(entry.receivedAt, result.receivedAt)
            XCTAssertEqual(entry.card.time, result.receivedAt)
            if let ts, ts.isFinite {
                XCTAssertEqual(result.payload.ts, ts)
                XCTAssertEqual(entry.freshnessDate, Date(timeIntervalSince1970: ts))
            } else if let ts {
                XCTAssertFalse(ts.isFinite); XCTAssertFalse(try XCTUnwrap(result.payload.ts).isFinite)
                XCTAssertEqual(entry.freshnessDate, result.receivedAt)
            } else {
                XCTAssertNil(result.payload.ts)
                XCTAssertEqual(entry.freshnessDate, result.receivedAt)
            }
            assertAge(entry, expected, now: now)
        }
    }

    func testOlderRefreshProjectsSourceAgeWithoutChangingBoundOrNumbers() throws {
        let store = WorkspaceStore()
        let original = try weather("R0", ts: 0, receivedAt: 500)
        store.receive(original, quietly: true)
        for index in 1...11 {
            let arrival = 600 + Double(index) * 10
            store.receive(try weather("R\(index)", ts: arrival, receivedAt: arrival), quietly: true)
        }
        let before = store.recents
        XCTAssertEqual(store.results.count, 12)
        XCTAssertEqual(before.entries.count, 10); XCTAssertEqual(before.olderEntries.count, 2)
        let beforeOlder = try XCTUnwrap(before.olderEntries.first { $0.id == original.id })
        XCTAssertNil(beforeOlder.number)
        XCTAssertEqual(beforeOlder.freshnessDate, Date(timeIntervalSince1970: 0))
        XCTAssertEqual(ConsoleActionBar.recentsRowTitle(beforeOlder, now: Date(timeIntervalSince1970: 1_200)),
                       "Result · R0 · 20m")

        XCTAssertEqual(store.receive(try weather("R0", ts: 1_100, receivedAt: 1_100), quietly: true), original.id)
        let after = store.recents
        let afterOlder = try XCTUnwrap(after.olderEntries.first { $0.id == original.id })
        XCTAssertEqual(store.results.count, 12)
        XCTAssertEqual(after.entries.map(\.id), before.entries.map(\.id))
        XCTAssertEqual(after.entries.map(\.number), before.entries.map(\.number))
        XCTAssertEqual(after.olderEntries.map(\.id), before.olderEntries.map(\.id))
        XCTAssertNil(afterOlder.number)
        XCTAssertEqual(afterOlder.card.time, original.receivedAt)
        XCTAssertEqual(afterOlder.receivedAt, original.receivedAt)
        XCTAssertEqual(afterOlder.freshnessDate, Date(timeIntervalSince1970: 1_100))
        XCTAssertEqual(ConsoleActionBar.recentsRowTitle(afterOlder, now: Date(timeIntervalSince1970: 1_200)),
                       "Result · R0 · 1m")
        XCTAssertTrue(ConsoleActionBar.recentsAccessibilityLabel(afterOlder, now: Date(timeIntervalSince1970: 1_200))
            .components(separatedBy: ", ").contains("1m"))
        XCTAssertEqual(store.resolveResultReference("R0"), .none, "Older must not expand the numbered voice inventory")
    }

    func testExtremelyOldFiniteSourceAgeIsUnknownAcrossAllLabels() throws {
        let store = WorkspaceStore()
        let result = try weather("Ancient source", ts: -1e24, receivedAt: 1_200)
        store.receive(result, quietly: true)
        let entry = try XCTUnwrap(store.recents.entries.first)
        XCTAssertTrue(try XCTUnwrap(result.payload.ts).isFinite)
        XCTAssertEqual(entry.freshnessDate, Date(timeIntervalSince1970: -1e24))
        assertAge(entry, "unknown", now: Date(timeIntervalSince1970: 1_200))

        let intBoundarySeconds = Double(Int.max) * 86_400
        XCTAssertEqual(WorkspaceRecents.age(of: Date(timeIntervalSince1970: -intBoundarySeconds),
                                            now: Date(timeIntervalSince1970: 0)), "unknown")
    }

    func testInvalidElapsedAgeIsUnknownAndFiniteFutureDateStillClampsToNow() {
        let now = Date(timeIntervalSince1970: 1_200)
        for timestamp in [Double.infinity, -.infinity, .nan] {
            XCTAssertEqual(WorkspaceRecents.age(of: Date(timeIntervalSince1970: timestamp), now: now), "unknown")
        }
        XCTAssertEqual(WorkspaceRecents.age(of: Date(timeIntervalSince1970: -Double.greatestFiniteMagnitude),
                                            now: Date(timeIntervalSince1970: Double.greatestFiniteMagnitude)), "unknown")
        XCTAssertEqual(WorkspaceRecents.age(of: Date(timeIntervalSince1970: 1_260), now: now), "now")
        XCTAssertEqual(WorkspaceRecents.age(of: Date(timeIntervalSince1970: 1_140), now: now), "1m")
    }
}
