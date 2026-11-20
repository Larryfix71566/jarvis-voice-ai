import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Interface cleanup Phase 3, Fable changes A and B: the transcript's
/// reading width, one speaker label per run, and the hover timestamp.
@MainActor
final class TranscriptReadabilityTests: XCTestCase {
    private func row(_ id: String, user: Bool, at time: Double) -> ConversationThread.Row {
        ConversationThread.Row(id: id, isUser: user, time: Date(timeIntervalSince1970: time), text: id)
    }

    private func entry(_ id: String, _ role: String, _ text: String, at time: Double) throws -> ConversationEntry {
        try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
            ["id": id, "role": role, "text": text, "createdAt": time]))
    }

    func testReadingWidthIs680() {
        XCTAssertEqual(ConversationThread.readingWidth, 680)
    }

    func testSpeakerLabelAppearsOncePerRunOfConsecutiveMessages() {
        let rows = [row("u1", user: true, at: 1), row("a1", user: false, at: 2),
                    row("a2", user: false, at: 3), row("u2", user: true, at: 4),
                    row("u3", user: true, at: 5), row("a3", user: false, at: 6)]
        let items = ConversationThread.items(rows: rows, cards: [])
        XCTAssertEqual(ConversationThread.speakerRunStarts(items), ["u1", "a1", "u2", "a3"])
    }

    func testAnApprovalBetweenTwoRepliesStartsANewRun() {
        let rows = [row("u1", user: true, at: 100), row("a1", user: false, at: 101),
                    row("a2", user: false, at: 103)]
        let note = ApprovalStore.Note(id: UUID(), time: Date(timeIntervalSince1970: 102), text: "Declined.")
        let items = ConversationThread.items(rows: rows, cards: [], approvalNotes: [note])
        XCTAssertEqual(items.map(\.id).count, 4)
        XCTAssertEqual(ConversationThread.speakerRunStarts(items), ["u1", "a1", "a2"])
    }

    func testTimestampShowsOnlyOnHover() {
        XCTAssertEqual(ConversationThreadRowView.timeOpacity(hovering: false), 0)
        XCTAssertEqual(ConversationThreadRowView.timeOpacity(hovering: true), 1)
    }

    // MARK: Rendered

    private func accessible(_ root: Any) -> [NSObject] {
        var seen = Set<ObjectIdentifier>()
        var found: [NSObject] = []
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            found.append(object)
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(root)
        return found
    }

    private func string(_ object: NSObject, _ name: String) -> String {
        let selector = NSSelectorFromString(name)
        guard object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue() else { return "" }
        return (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
    }

    func testRenderedThreadIsCappedAtTheReadingWidthAndCentred() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let createdAt = 1_700_000_000.0
        let long = "Reading width marker. " + String(repeating: "The storms stay west of Charleston for now. ", count: 30)
        let conversation = ConversationStore()
        conversation.set([try entry("a1", "assistant", long, at: createdAt)])
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "p3-readability-" + UUID().uuidString))
        let view = NSHostingView(rootView: ConversationThreadView()
            .defaultAppStorage(defaults)
            .environment(conversation)
            .environment(WorkspaceStore())
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 1400, height: 520)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))

        let elements = accessible(view)
        let rowElement = try XCTUnwrap(elements.first { string($0, "accessibilityLabel").hasPrefix("Mortimer: ") },
                                       "no Mortimer row in the accessibility tree")
        let frame = (rowElement.value(forKey: "accessibilityFrame") as? NSValue)?.rectValue ?? .zero
        XCTAssertGreaterThan(frame.width, 0)
        XCTAssertLessThanOrEqual(frame.width, 681, "row is wider than the reading width: \(frame)")
        let viewport = window.frame // accessibilityFrame is in screen coordinates
        XCTAssertLessThanOrEqual(abs(frame.midX - viewport.midX), 2,
                                 "row is not centred: row \(frame), viewport \(viewport)")

        let time = Date(timeIntervalSince1970: createdAt).formatted(date: .omitted, time: .shortened)
        XCTAssertTrue(elements.contains { string($0, "accessibilityValue") == time },
                      "the row's time is not its accessibility value")
    }
}
