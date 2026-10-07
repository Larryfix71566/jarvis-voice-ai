import XCTest
import JarvisKit
@testable import MortimerHost

/// WS-17 CC7a.3 (plan §7.2): the Recents list behind Results ▾ and voice
/// result actions by Recents number and subject.
@MainActor
final class CC7a3RecentsTests: XCTestCase {
    private func payload(_ fields: [String: Any]) -> DisplayPayload {
        let data = try! JSONSerialization.data(withJSONObject: fields)
        return try! JSONDecoder().decode(DisplayPayload.self, from: data)
    }

    private func result(_ title: String, minutesAgo: Double, now: Date,
                        private isPrivate: Bool = false,
                        sources: Bool = false) -> WorkspaceResult {
        var fields: [String: Any] = ["kind": "markdown", "title": title, "body": "Body of \(title)"]
        if isPrivate { fields["data_policy"] = "local_only" }
        if sources { fields["links"] = [["title": "Source", "url": "https://example.com"]] }
        return WorkspaceResult(payload: payload(fields), receivedAt: now.addingTimeInterval(-minutesAgo * 60))
    }

    private func request(_ action: ConsoleAction, target: String?, secondary: String? = nil,
                         revision: Int) -> ConsoleRequest {
        ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                       revision: revision, action: action, target: target,
                       secondaryTarget: secondary)
    }

    private func coordinator(_ workspace: WorkspaceStore) -> ConsoleActionCoordinator {
        let drawer = DrawerState()
        return ConsoleActionCoordinator(workspace: workspace, display: DisplayWindowStore(),
                                        placement: WindowPlacement(drawer: drawer, windows: WindowActions()),
                                        drawer: drawer, screens: { [] })
    }

    // MARK: Listing

    func testPinnedComeFirstThenNewestUnpinnedNumberedFromOne() {
        let now = Date()
        let a = result("Alpha", minutesAgo: 30, now: now)
        let b = result("Bravo", minutesAgo: 20, now: now)
        let c = result("Charlie", minutesAgo: 10, now: now)
        let listing = WorkspaceRecents.listing(results: [a, b, c], pinned: [a.id],
                                               unread: [c.id], active: b.id)
        XCTAssertEqual(listing.entries.map(\.id), [a.id, c.id, b.id])
        XCTAssertEqual(listing.entries.map(\.number), [1, 2, 3])
        XCTAssertEqual(listing.pinned.map(\.id), [a.id])
        XCTAssertEqual(listing.entries[1].isUnread, true)
        XCTAssertEqual(listing.entries[2].isActive, true)
    }

    func testTheBoundIsADisplayLimitAndOlderResultsStayListed() {
        let now = Date()
        let results = (0..<13).map { result("R\($0)", minutesAgo: Double(13 - $0), now: now) }
        let listing = WorkspaceRecents.listing(results: results, pinned: [], unread: [], active: nil)
        XCTAssertEqual(listing.recent.count, WorkspaceRecents.recentLimit)
        XCTAssertEqual(listing.older.map(\.id), results.prefix(3).reversed().map(\.id))
        XCTAssertEqual(listing.recent.first?.card.subject, "R12")

        let workspace = WorkspaceStore()
        for item in results { workspace.receive(item, quietly: true) }
        XCTAssertEqual(workspace.results.count, 13, "Recents never removes a result")
    }

    func testPrivateResultsTakeNoNumber() {
        let now = Date()
        let open = result("Open", minutesAgo: 20, now: now)
        let secret = result("Secret", minutesAgo: 10, now: now, private: true)
        let later = result("Later", minutesAgo: 5, now: now)
        let listing = WorkspaceRecents.listing(results: [open, secret, later], pinned: [],
                                               unread: [], active: nil)
        XCTAssertEqual(listing.entries.map(\.number), [1, nil, 2])
        XCTAssertEqual(WorkspaceRecents.resolve("Secret", in: listing.entries), .none)
    }

    func testAgeLabels() {
        let now = Date()
        XCTAssertEqual(WorkspaceRecents.age(of: now.addingTimeInterval(-20), now: now), "now")
        XCTAssertEqual(WorkspaceRecents.age(of: now.addingTimeInterval(-5 * 60), now: now), "5m")
        XCTAssertEqual(WorkspaceRecents.age(of: now.addingTimeInterval(-3 * 3_600), now: now), "3h")
        XCTAssertEqual(WorkspaceRecents.age(of: now.addingTimeInterval(-2 * 86_400), now: now), "2d")
    }

    func testMenuRowShowsNumberTitleAndAge() {
        let now = Date()
        let r = result("Folly Beach", minutesAgo: 5, now: now, sources: true)
        let entry = WorkspaceRecents.listing(results: [r], pinned: [], unread: [r.id], active: nil).entries[0]
        XCTAssertEqual(ConsoleActionBar.recentsRowTitle(entry, now: now), "1  Research · Folly Beach · 5m")
        XCTAssertEqual(ConsoleActionBar.recentsAccessibilityLabel(entry, now: now),
                       "Number 1, Research · Folly Beach, 5m, unread")
        XCTAssertEqual(ConsoleActionBar.recentsIcon(entry), "circle.fill")
    }

    // MARK: Resolution

    func testNumbersInEachSpokenForm() {
        let now = Date()
        let results = (0..<4).map { result("R\($0)", minutesAgo: Double(4 - $0), now: now) }
        let entries = WorkspaceRecents.listing(results: results, pinned: [], unread: [], active: nil).entries
        for spoken in ["2", "#2", "number 2", "No. 2", "number two", "two", "second"] {
            XCTAssertEqual(WorkspaceRecents.resolve(spoken, in: entries), .result(results[2].id), spoken)
        }
        XCTAssertEqual(WorkspaceRecents.resolve("9", in: entries), .none)
        XCTAssertEqual(WorkspaceRecents.resolve("0", in: entries), .none)
    }

    func testSubjectMatchesEveryWordAndExactSubjectWins() {
        let now = Date()
        let beach = result("Folly Beach", minutesAgo: 9, now: now, sources: true)
        let island = result("Folly Beach Island Ferry", minutesAgo: 8, now: now, sources: true)
        let paris = result("Paris", minutesAgo: 7, now: now)
        let entries = WorkspaceRecents.listing(results: [beach, island, paris], pinned: [],
                                               unread: [], active: nil).entries
        XCTAssertEqual(WorkspaceRecents.resolve("the Folly Beach research", in: entries), .result(beach.id),
                       "exact subject beats a longer one containing it")
        XCTAssertEqual(WorkspaceRecents.resolve("ferry", in: entries), .result(island.id))
        XCTAssertEqual(WorkspaceRecents.resolve("PARIS", in: entries), .result(paris.id))
        XCTAssertEqual(WorkspaceRecents.resolve("London", in: entries), .none)
    }

    func testDuplicateSubjectsAreAmbiguousAndOfferNumberedChoices() {
        let now = Date()
        let older = result("Folly Beach", minutesAgo: 60, now: now, sources: true)
        let newer = result("Folly Beach", minutesAgo: 5, now: now, sources: true)
        let entries = WorkspaceRecents.listing(results: [older, newer], pinned: [],
                                               unread: [], active: nil).entries
        guard case .ambiguous(let matches) = WorkspaceRecents.resolve("Folly Beach", in: entries) else {
            return XCTFail("duplicate subjects must not be acted on")
        }
        let choices = WorkspaceRecents.choices(matches, now: now)
        XCTAssertEqual(choices.map(\.id), [newer.id.uuidString, older.id.uuidString])
        XCTAssertEqual(choices.map(\.label), ["1  Research · Folly Beach · 5m", "2  Research · Folly Beach · 1h"])
    }

    // MARK: Store and coordinator

    func testPinAndUnpinAdvanceTheRevision() {
        let workspace = WorkspaceStore()
        let r = result("Alpha", minutesAgo: 1, now: Date())
        workspace.receive(r, quietly: true)
        let before = workspace.consoleRevision
        XCTAssertTrue(workspace.pin(r.id))
        XCTAssertEqual(workspace.consoleRevision, before + 1)
        XCTAssertTrue(workspace.pin(r.id))
        XCTAssertEqual(workspace.consoleRevision, before + 1, "pinning a pinned result changes nothing")
        workspace.unpin(r.id)
        XCTAssertEqual(workspace.consoleRevision, before + 2)
    }

    func testInventoryCarriesTheMenuNumberKindAndSubject() {
        let workspace = WorkspaceStore()
        let now = Date()
        let a = result("Alpha", minutesAgo: 2, now: now, sources: true)
        let b = result("Bravo", minutesAgo: 1, now: now)
        let hidden = result("Hidden", minutesAgo: 0.5, now: now, private: true)
        for item in [a, b, hidden] { workspace.receive(item, quietly: true) }
        guard case .object(let inventory) = workspace.consoleInventoryJSON,
              case .array(let results) = inventory["results"] else { return XCTFail("inventory shape") }
        XCTAssertEqual(results.count, 2, "private results never reach voice")
        let byTitle = Dictionary(uniqueKeysWithValues: results.compactMap { value -> (String, [String: JSONValue])? in
            guard case .object(let fields) = value, case .string(let title) = fields["title"] else { return nil }
            return (title, fields)
        })
        XCTAssertEqual(byTitle["Bravo"]?["number"], .number(1))
        XCTAssertEqual(byTitle["Alpha"]?["number"], .number(2))
        XCTAssertEqual(byTitle["Alpha"]?["kind"], .string("Research"))
        XCTAssertEqual(byTitle["Alpha"]?["subject"], .string("Alpha"))
        XCTAssertEqual(byTitle["Bravo"]?["unread"], .bool(true))
        let foundation = workspace.consoleInventory["results"] as? [[String: Any]]
        XCTAssertEqual(foundation?.first { $0["title"] as? String == "Bravo" }?["number"] as? Int, 1)
    }

    func testVoiceOpensPinsAndClosesByNumberAndSubject() {
        let workspace = WorkspaceStore()
        let now = Date()
        let a = result("Alpha", minutesAgo: 3, now: now)
        let b = result("Bravo", minutesAgo: 2, now: now)
        let c = result("Charlie", minutesAgo: 1, now: now)
        for item in [a, b, c] { workspace.receive(item, quietly: true) }
        let console = coordinator(workspace)

        XCTAssertEqual(console.execute(request(.resultSelect, target: "number 3",
                                               revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(workspace.activeID, a.id)
        XCTAssertEqual(console.execute(request(.resultPin, target: "Bravo",
                                               revision: workspace.consoleRevision)), .applied)
        XCTAssertTrue(workspace.pinnedIDs.contains(b.id))
        // Bravo is now pinned and therefore number 1.
        XCTAssertEqual(console.execute(request(.resultUnpin, target: "1",
                                               revision: workspace.consoleRevision)), .applied)
        XCTAssertFalse(workspace.pinnedIDs.contains(b.id))
        XCTAssertEqual(console.execute(request(.resultClose, target: "charlie",
                                               revision: workspace.consoleRevision)), .applied)
        XCTAssertFalse(workspace.containsResult(c.id))
        XCTAssertEqual(console.execute(request(.compareSet, target: "Alpha", secondary: "Bravo",
                                               revision: workspace.consoleRevision)), .applied)
        XCTAssertEqual(workspace.comparisonID, b.id)
    }

    func testAmbiguousOrUnknownReferencesChangeNothing() {
        let workspace = WorkspaceStore()
        let now = Date()
        let older = result("Folly Beach", minutesAgo: 60, now: now)
        let newer = result("Folly Beach", minutesAgo: 5, now: now)
        for item in [older, newer] { workspace.receive(item, quietly: true) }
        let console = coordinator(workspace)
        let revision = workspace.consoleRevision
        let active = workspace.activeID

        guard case .needsChoice(let choices) = console.execute(
            request(.resultClose, target: "Folly Beach", revision: revision)) else {
            return XCTFail("an ambiguous subject must ask, not act")
        }
        XCTAssertEqual(choices.map(\.id), [newer.id.uuidString, older.id.uuidString])
        XCTAssertEqual(workspace.results.count, 2)
        XCTAssertEqual(workspace.consoleRevision, revision)
        XCTAssertEqual(workspace.activeID, active)

        XCTAssertEqual(console.execute(request(.resultSelect, target: "London", revision: revision)), .noMatch)
        XCTAssertEqual(console.execute(request(.resultSelect, target: UUID().uuidString, revision: revision)),
                       .invalid, "a UUID that is gone stays invalid")
    }

    func testANumberSpokenAgainstOldNumbersIsStale() {
        let workspace = WorkspaceStore()
        let now = Date()
        let a = result("Alpha", minutesAgo: 2, now: now)
        let b = result("Bravo", minutesAgo: 1, now: now)
        for item in [a, b] { workspace.receive(item, quietly: true) }
        let console = coordinator(workspace)
        let seen = workspace.consoleRevision
        XCTAssertTrue(workspace.pin(a.id))    // renumbers: Alpha becomes 1
        XCTAssertEqual(console.execute(request(.resultClose, target: "1", revision: seen)), .stale)
        XCTAssertEqual(workspace.results.count, 2)
    }
}
