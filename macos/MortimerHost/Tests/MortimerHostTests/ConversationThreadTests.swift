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
}
