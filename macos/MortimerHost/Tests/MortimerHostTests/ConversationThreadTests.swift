import XCTest
import SwiftUI
import AppKit
import Vision
import JarvisKit
@testable import MortimerHost

@MainActor
private func threadRenderedText(in view: NSView) throws -> String {
    let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
    view.cacheDisplay(in: view.bounds, to: bitmap)
    let image = try XCTUnwrap(bitmap.cgImage)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: image).perform([request])
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: " ").split(whereSeparator: \.isWhitespace).joined().lowercased()
}

/// CC7a.1 (WS-17, Command Console plan §7.2): conversation thread rules.
@MainActor
final class ConversationThreadTests: XCTestCase {
    private func entry(_ id: String, _ role: String, _ text: String, at time: Double = 1234) throws -> ConversationEntry {
        try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
            ["id": id, "role": role, "text": text, "createdAt": time]))
    }

    func testSwitchDefaultsOnAndCanBeTurnedOff() throws {
        let suite = "ConversationThreadTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertTrue(ConversationThread.isEnabled(defaults))
        defaults.set(false, forKey: ConversationThread.flagKey)
        XCTAssertFalse(ConversationThread.isEnabled(defaults))
        defaults.set(true, forKey: ConversationThread.flagKey)
        XCTAssertTrue(ConversationThread.isEnabled(defaults))
    }

    func testSpokenAnswersBecomeResultsOnlyInLayoutTwoWithTheThreadOff() {
        XCTAssertFalse(ConversationThread.routesSpokenAnswersToResults(layoutVersion: 2, threadEnabled: true))
        XCTAssertTrue(ConversationThread.routesSpokenAnswersToResults(layoutVersion: 2, threadEnabled: false))
        for layout in [0, 1, 7] {
            XCTAssertFalse(ConversationThread.routesSpokenAnswersToResults(layoutVersion: layout, threadEnabled: false))
            XCTAssertFalse(ConversationThread.routesSpokenAnswersToResults(layoutVersion: layout, threadEnabled: true))
        }
    }

    func testThreadShowsOnlyInLayoutTwoWithTheSwitchOn() {
        XCTAssertTrue(ConversationThread.showsThread(layoutVersion: 2, threadEnabled: true))
        XCTAssertFalse(ConversationThread.showsThread(layoutVersion: 2, threadEnabled: false))
        XCTAssertFalse(ConversationThread.showsThread(layoutVersion: 1, threadEnabled: true))
        XCTAssertFalse(ConversationThread.showsThread(layoutVersion: 0, threadEnabled: true))
        XCTAssertFalse(ConversationThread.showsThread(layoutVersion: 9, threadEnabled: true),
                       "An unknown layout resolves to layout 1, which keeps its own stage.")
    }

    func testRowsKeepBothSpeakersFullTextInOrder() throws {
        let long = String(repeating: "GitHub moves ubuntu-latest to Ubuntu 26 on October 19. ", count: 5)
        XCTAssertGreaterThan(long.count, 160)
        let rows = ConversationThread.rows([
            try entry("u1", "user", "  Remind me about WS-12.  ", at: 100),
            try entry("a1", "assistant", long, at: 101),
            try entry("a2", "assistant", "   ", at: 102),
            try entry("u2", "user", "Thanks", at: 103),
        ])
        XCTAssertEqual(rows.map(\.id), ["u1", "a1", "u2"], "Empty entries are skipped; order is kept.")
        XCTAssertEqual(rows.map(\.speaker), ["YOU", "MORTIMER", "YOU"])
        XCTAssertEqual(rows[0].text, "Remind me about WS-12.")
        XCTAssertEqual(rows[1].text, long.trimmingCharacters(in: .whitespacesAndNewlines))
        XCTAssertFalse(rows[1].text.hasPrefix("…"), "Unlike the old caption, the thread never truncates.")
        XCTAssertEqual(rows[1].time, Date(timeIntervalSince1970: 101))
    }

    func testThreadReadsEveryRetainedEntryNotJustTheLastTwo() throws {
        let store = ConversationStore()
        store.set(try (0..<6).map { try entry("e\($0)", $0 % 2 == 0 ? "user" : "assistant", "turn \($0)") })
        XCTAssertEqual(store.latestCaptions.count, 2)
        XCTAssertEqual(ConversationThread.rows(store.entries).count, 6)
    }

    /// Regression for the Codex review of PR #140: at the 200-entry
    /// retention bound a new turn replaces the oldest, so the row count does
    /// not change. New turns must still be counted while Larry is scrolled up.
    func testNewTurnIsCountedAtTheRetentionBoundWhenScrolledUp() throws {
        let store = ConversationStore()
        let limit = AppTuning.maxConversationEntries
        let full = try (0..<limit).map { try entry("e\($0)", $0 % 2 == 0 ? "user" : "assistant", "turn \($0)") }
        store.set(full)
        let before = ConversationThread.rows(store.entries).map(\.id)
        store.set(full + [try entry("e\(limit)", "assistant", "the newest turn")])
        let after = ConversationThread.rows(store.entries).map(\.id)
        XCTAssertEqual(before.count, limit)
        XCTAssertEqual(after.count, limit, "At the bound the count does not change.")
        XCTAssertEqual(after.first, "e1", "The oldest entry was dropped.")

        let added = ConversationThread.newTurns(from: before, to: after)
        XCTAssertEqual(added, 1)
        var follow = ConversationThread.Follow()
        follow.scrolled(atBottom: false)
        XCTAssertFalse(follow.rowsChanged(added: added), "Scrolled up: the text must not move.")
        XCTAssertEqual(follow.unseen, 1, "The New button must appear.")
    }

    func testNewTurnCountingByIdentity() {
        XCTAssertEqual(ConversationThread.newTurns(from: [], to: ["a", "b"]), 2)
        XCTAssertEqual(ConversationThread.newTurns(from: ["a", "b"], to: ["a", "b"]), 0,
                       "A streaming answer that grows in place is not a new turn.")
        XCTAssertEqual(ConversationThread.newTurns(from: ["a", "b"], to: ["a", "b", "c", "d"]), 2)
        XCTAssertEqual(ConversationThread.newTurns(from: ["a", "b"], to: ["b", "c"]), 1,
                       "Oldest dropped, one added: one new turn.")
        XCTAssertEqual(ConversationThread.newTurns(from: ["a", "b"], to: ["b"]), 0,
                       "Trimming only is not a new turn.")
        XCTAssertEqual(ConversationThread.newTurns(from: ["a", "b"], to: ["x", "y"]), 2,
                       "A replaced transcript counts as new.")
        XCTAssertEqual(ConversationThread.newTurns(from: ["a"], to: []), 0)
    }

    func testBottomDetectionAllowsASmallToleranceAndShortContent() {
        XCTAssertTrue(ConversationThread.isAtBottom(contentHeight: 1000, visibleMaxY: 1000))
        XCTAssertTrue(ConversationThread.isAtBottom(contentHeight: 1000, visibleMaxY: 980))
        XCTAssertFalse(ConversationThread.isAtBottom(contentHeight: 1000, visibleMaxY: 900))
        XCTAssertTrue(ConversationThread.isAtBottom(contentHeight: 300, visibleMaxY: 600),
                      "Content shorter than the view is always at the bottom.")
    }

    func testFollowsNewTurnsOnlyWhileAtTheBottom() {
        var follow = ConversationThread.Follow()
        XCTAssertTrue(follow.following)
        XCTAssertTrue(follow.rowsChanged(added: 1), "At the bottom, a new turn scrolls into view.")
        XCTAssertEqual(follow.unseen, 0)

        follow.scrolled(atBottom: false)
        XCTAssertFalse(follow.rowsChanged(added: 2), "Reading history: the text must not move.")
        XCTAssertFalse(follow.rowsChanged(added: 1))
        XCTAssertEqual(follow.unseen, 3)
        XCTAssertFalse(follow.rowsChanged(added: -4), "Retention trimming does not count as new turns.")
        XCTAssertEqual(follow.unseen, 3)

        follow.jumpedToEnd()
        XCTAssertTrue(follow.following)
        XCTAssertEqual(follow.unseen, 0)

        follow.scrolled(atBottom: false)
        _ = follow.rowsChanged(added: 1)
        follow.scrolled(atBottom: true)
        XCTAssertEqual(follow.unseen, 0, "Scrolling back down clears the count.")
    }

    /// UI2-22 evidence in the suite: the rendered thread shows both turns and
    /// the end of a reply longer than the old 160-character caption.
    func testRenderedThreadShowsBothSpeakersAndTheEndOfALongReply() throws {
        _ = NSApplication.shared
        let conversation = ConversationStore()
        let longReply = "Thread start marker. " + String(repeating: "The storms stay west of Charleston for now. ", count: 5) + "Thread end marker."
        XCTAssertGreaterThan(longReply.count, 160)
        conversation.set([try entry("u1", "user", "Weather question marker"),
                          try entry("a1", "assistant", longReply)])
        let view = NSHostingView(rootView: ConversationThreadView()
            .environment(conversation)
            .environment(WorkspaceStore())
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 760, height: 520)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let text = try threadRenderedText(in: view)
        // Body text only: the 10-point speaker labels are checked through the
        // rows and accessibility labels, not OCR, to keep this deterministic.
        for expected in ["weatherquestionmarker", "threadstartmarker", "threadendmarker"] {
            XCTAssertTrue(text.contains(expected), "missing \(expected) in rendered thread: \(text)")
        }
    }

    // MARK: CC7a.2 inline result cards (UI2-23)

    private func payload(_ object: [String: Any]) throws -> DisplayPayload {
        try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func weatherPayload() throws -> DisplayPayload {
        try payload(["kind": "weather", "title": "Weather", "surface": "window",
                     "body": "82 and mostly sunny",
                     "weather": ["schema": 1,
                                 "place": ["label": "Folly Beach, SC", "source": "device", "approximate": false],
                                 "units": "imperial",
                                 "now": ["temp": "82°", "condition": "Mostly sunny", "symbol": "sun.max"],
                                 "alerts": [["event": "Heat", "headline": "Heat advisory"]],
                                 "summary": "Sunny", "attribution": "NWS"]])
    }

    func testCardsNameKindSubjectAndOneSummaryLine() throws {
        let weather = ConversationThread.card(WorkspaceResult(payload: try weatherPayload()))
        XCTAssertEqual(weather.title, "Weather · Folly Beach, SC")
        XCTAssertEqual(weather.summary, "82° · Mostly sunny · 1 alert")
        XCTAssertEqual(weather.icon, "cloud.sun")

        let research = ConversationThread.card(WorkspaceResult(payload: try payload([
            "kind": "research", "title": "GitHub Ubuntu 26 runners",
            "links": [["url": "https://a.example"], ["url": "https://b.example"], ["url": "https://c.example"]]])))
        XCTAssertEqual(research.title, "Research · GitHub Ubuntu 26 runners")
        XCTAssertEqual(research.summary, "3 sources")

        let image = ConversationThread.card(WorkspaceResult(payload: try payload([
            "title": "Truist Park map", "images": ["https://img.example/map.png"]])))
        XCTAssertEqual(image.title, "Image · Truist Park map")
        XCTAssertEqual(image.summary, "1 image")

        let text = ConversationThread.card(WorkspaceResult(payload: try payload([
            "title": "Notes", "body": "\n\n## First heading line\nSecond line"])))
        XCTAssertEqual(text.summary, "First heading line", "One line, Markdown marks removed.")

        let long = ConversationThread.oneLine(String(repeating: "word ", count: 60))
        XCTAssertEqual(long.count, 140)
        XCTAssertTrue(long.hasSuffix("…"))
    }

    /// Protected (local-only) results show no body excerpt in the thread.
    func testPrivateCardsShowNoBodyText() throws {
        let card = ConversationThread.card(WorkspaceResult(payload: try payload([
            "title": "Account summary", "body": "Protected body canary", "data_policy": "local_only"])))
        XCTAssertTrue(card.isPrivate)
        XCTAssertEqual(card.summary, ConversationThread.privateSummary)
        XCTAssertFalse(card.title.contains("canary") || card.summary.contains("canary"))
    }

    /// Cards sit at the end of the turn they arrived in: after Mortimer's
    /// reply (even when the tool result came first) and before the next
    /// question; in arrival order within a turn.
    func testCardsSitAtTheEndOfTheTurnTheyArrivedIn() throws {
        let rows = ConversationThread.rows([
            try entry("u1", "user", "What's the weather?", at: 100),
            try entry("a1", "assistant", "It's 82 and sunny.", at: 105),
            try entry("u2", "user", "Look up the runner change.", at: 200),
            try entry("a2", "assistant", "Here it is.", at: 205),
        ])
        func card(_ name: String, at time: Double) -> ConversationThread.Card {
            ConversationThread.Card(id: UUID(), time: Date(timeIntervalSince1970: time), kind: "Result",
                                    icon: "doc.text", subject: name, summary: "", isPrivate: false)
        }
        let early = card("early", at: 50)
        let weather = card("weather", at: 102)      // the tool answered before the reply
        let radar = card("radar", at: 103)
        let research = card("research", at: 210)
        let items = ConversationThread.items(rows: rows, cards: [research, radar, early, weather])
        XCTAssertEqual(items.map(\.id), [
            "card-\(early.id.uuidString)", "u1", "a1",
            "card-\(weather.id.uuidString)", "card-\(radar.id.uuidString)",
            "u2", "a2", "card-\(research.id.uuidString)",
        ])
        XCTAssertEqual(ConversationThread.items(rows: [], cards: [radar, weather]).map(\.id),
                       ["card-\(weather.id.uuidString)", "card-\(radar.id.uuidString)"])
    }

    /// A card joining the end counts as new for the "New" button.
    func testACardAtTheEndCountsAsNew() {
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "a1"], to: ["u1", "a1", "card-x"]), 1)
    }

    /// Codex review of PR #164: new items are counted by identity, wherever
    /// they sit. A reply inserted before its turn's tool-first card is new;
    /// closing the last card adds nothing; a scrolled-up reader is told.
    func testNewItemsAreCountedByIdentityNotPosition() {
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "card-x"], to: ["u1", "a1", "card-x"]), 1)
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "a1", "card-x"], to: ["u1", "a1"]), 0)
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "a1", "card-x"],
                                                   to: ["u1", "a1", "card-x", "u2", "card-y"]), 2)
        XCTAssertEqual(ConversationThread.newTurns(from: ["u1", "a1", "card-x"], to: ["a1", "card-x", "u2"]), 1,
                       "At the retention bound: oldest dropped, one added.")
        var follow = ConversationThread.Follow()
        follow.scrolled(atBottom: false)
        XCTAssertFalse(follow.rowsChanged(added: ConversationThread.newTurns(
            from: ["u1", "card-x"], to: ["u1", "a1", "card-x"])))
        XCTAssertEqual(follow.unseen, 1, "The reply that slid in above the card shows the New button.")
    }

    /// UI2-23 evidence in the suite: the rendered thread shows the card's
    /// title and summary under the reply.
    func testRenderedThreadShowsAResultCard() throws {
        _ = NSApplication.shared
        let conversation = ConversationStore()
        conversation.set([try entry("u1", "user", "Card question marker", at: 1000),
                          try entry("a1", "assistant", "Card reply marker", at: 1001)])
        let workspace = WorkspaceStore()
        workspace.quietArrivals = true
        workspace.receive(WorkspaceResult(payload: try payload([
            "kind": "research", "title": "Runner card marker",
            "links": [["url": "https://a.example"], ["url": "https://b.example"], ["url": "https://c.example"]]]),
            receivedAt: Date(timeIntervalSince1970: 1002)))
        let view = NSHostingView(rootView: ConversationThreadView()
            .environment(conversation)
            .environment(workspace)
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 760, height: 520)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let text = try threadRenderedText(in: view)
        for expected in ["cardreplymarker", "runnercardmarker"] {
            XCTAssertTrue(text.contains(expected), "missing \(expected) in rendered thread: \(text)")
        }
        XCTAssertTrue(workspace.showsConversation, "Rendering the card did not open the result.")
    }

    // MARK: CC7a.2b: what counts as the answer to the current request

    /// Larry, 10-03, with Codex's review of #169: a result opens on the
    /// conversation only when it answers what he just asked.
    func testArrivalIntentOpensOnlyTheAnswerToTheCurrentRequest() {
        let spoke = Date(timeIntervalSince1970: 10_000)
        func answers(_ tool: String?, run: Double?, runID: String? = "r1", spoke: Date? = spoke,
                     now: Double) -> Bool {
            ArrivalIntent.answersCurrentRequest(
                tool: tool, runID: run == nil ? nil : runID,
                runStartedAt: run.map { Date(timeIntervalSince1970: $0) },
                lastUserTurnAt: spoke, now: Date(timeIntervalSince1970: now))
        }
        XCTAssertTrue(answers("weather_report", run: 10_002, now: 10_009),
                      "A delegation started after Larry spoke answers him.")
        XCTAssertFalse(answers("web_search", run: 9_000, now: 10_009),
                       "A detached run started before his latest turn finishes later: not this answer.")
        XCTAssertFalse(answers("research_report", run: nil, now: 10_005),
                       "A background research job's completion never opens by itself.")
        XCTAssertFalse(answers("plan_ready", run: 10_002, now: 10_005))
        XCTAssertTrue(answers("memory_graph_view", run: nil, now: 10_030),
                      "A direct tool right after he spoke answers him.")
        XCTAssertFalse(answers("memory_graph_view", run: nil, now: 10_000 + ArrivalIntent.directWindow + 1),
                       "Long after he spoke, an unattributed result does not open.")
        XCTAssertFalse(answers("get_weather", run: 10_002, spoke: nil, now: 10_005),
                       "With no turn of his on record, nothing counts as asked for.")
        XCTAssertFalse(ArrivalIntent.answersCurrentRequest(
            tool: "web_search", runID: "r-unseen", runStartedAt: nil,
            lastUserTurnAt: spoke, now: Date(timeIntervalSince1970: 10_005)),
            "Codex re-review of #169: a run ID the app never saw start is a card, not a direct result.")
        XCTAssertTrue(ArrivalIntent.answersCurrentRequest(
            tool: "web_search", runID: "", runStartedAt: nil,
            lastUserTurnAt: spoke, now: Date(timeIntervalSince1970: 10_005)),
            "An empty run ID is no run: the direct-result window applies.")
    }

    func testArrivalRunClockKeepsStartsByRunAndForgetsTheOldestPastCapacity() {
        let clock = ArrivalRunClock()
        let t0 = Date(timeIntervalSince1970: 1_000)
        clock.recordStart("r-old", at: t0)
        clock.recordStart("r-new", at: t0.addingTimeInterval(5))
        XCTAssertEqual(clock.startedAt("r-old"), t0, "A replaced run keeps its start.")
        XCTAssertNil(clock.startedAt(nil)); XCTAssertNil(clock.startedAt(""))
        clock.recordStart(nil, at: t0); clock.recordStart("", at: t0)
        for i in 0..<ArrivalRunClock.capacity { clock.recordStart("r\(i)", at: t0) }
        XCTAssertNil(clock.startedAt("r-old"), "Bounded: the oldest start is dropped first.")
        XCTAssertNotNil(clock.startedAt("r\(ArrivalRunClock.capacity - 1)"))
    }
}
