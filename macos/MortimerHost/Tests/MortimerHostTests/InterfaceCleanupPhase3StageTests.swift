import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Interface cleanup Phase 3, slice 1: the stage's at-rest layout and the
/// move aside when the first turn or the first result arrives.
@MainActor
final class InterfaceCleanupPhase3StageTests: XCTestCase {
    private func client() -> JarvisClient {
        JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
    }

    private func host<V: View>(_ root: V, width: CGFloat, height: CGFloat) -> (NSHostingView<V>, NSWindow) {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: width, height: height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        return (view, window)
    }

    /// Labels, values, titles and "id:" identifiers, each element once.
    private func accessible(_ root: Any) -> (text: [String], controls: [String: NSObject]) {
        var seen = Set<ObjectIdentifier>()
        var text: [String] = []
        var controls: [String: NSObject] = [:]
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            for name in ["accessibilityLabel", "accessibilityValue", "accessibilityTitle"] {
                let selector = NSSelectorFromString(name)
                guard object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue() else { continue }
                let string = (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
                if !string.isEmpty { text.append(string); if controls[string] == nil { controls[string] = object } }
            }
            let ident = NSSelectorFromString("accessibilityIdentifier")
            if object.responds(to: ident), let string = object.perform(ident)?.takeUnretainedValue() as? String,
               !string.isEmpty { text.append("id:" + string) }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(root)
        return (text, controls)
    }

    private func entry(_ id: String, _ role: String, _ text: String) throws -> ConversationEntry {
        try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
            ["id": id, "role": role, "text": text, "createdAt": 1234.0]))
    }

    private typealias Stage = AdaptiveStageView

    // MARK: Placement

    func testEmptyThreadCentresTheOrbAndFirstTurnOrFirstResultMovesItToTheMargin() {
        XCTAssertEqual(Stage.orbPlacement(threadIsEmpty: true, hasResults: false,
                                          showsOtherSurface: false, working: false), .centred)
        XCTAssertEqual(Stage.orbPlacement(threadIsEmpty: false, hasResults: false,
                                          showsOtherSurface: false, working: false), .margin)
        XCTAssertEqual(Stage.orbPlacement(threadIsEmpty: true, hasResults: true,
                                          showsOtherSurface: false, working: false), .margin)
        XCTAssertEqual(Stage.orbPlacement(threadIsEmpty: true, hasResults: false,
                                          showsOtherSurface: true, working: false), .margin)
        XCTAssertEqual(Stage.orbPlacement(threadIsEmpty: true, hasResults: false,
                                          showsOtherSurface: false, working: true), .margin)
    }

    func testThreadIsEmptyCountsRowsReferencesApprovalsAndNotes() throws {
        XCTAssertTrue(Stage.threadIsEmpty(entries: [], references: [], approvals: [], approvalNotes: []))
        XCTAssertFalse(Stage.threadIsEmpty(entries: [try entry("e1", "user", "Hello")],
                                           references: [], approvals: [], approvalNotes: []))
        XCTAssertTrue(Stage.threadIsEmpty(entries: [try entry("e2", "assistant", "  \n ")],
                                          references: [], approvals: [], approvalNotes: []))
        let item = ApprovalStore.Item(id: UUID(), originRequestID: UUID(), agent: "Developer", tool: "plan_start",
                                      summary: "Start the plan", receivedAt: Date(timeIntervalSince1970: 10),
                                      inFlight: nil, notice: nil)
        XCTAssertFalse(Stage.threadIsEmpty(entries: [], references: [], approvals: [item], approvalNotes: []))
        let note = ApprovalStore.Note(id: UUID(), time: Date(timeIntervalSince1970: 11), text: "Approved")
        XCTAssertFalse(Stage.threadIsEmpty(entries: [], references: [], approvals: [], approvalNotes: [note]))
    }

    func testPlacementRuleIsTheSameAtNarrowAndWideWidths() {
        for width in [600.0, 772, 773, 1180, 1440, 2560] {
            for wide in [false, true] {
                let rest = Stage.layout(threadIsEmpty: true, hasResults: false, showsOtherSurface: false,
                    working: false, showsConversation: false, compactConversation: true,
                    wideWindow: wide, stageWidth: width)
                XCTAssertEqual(rest.placement, .centred, "width \(width) wide \(wide)")
                let busy = Stage.layout(threadIsEmpty: false, hasResults: false, showsOtherSurface: false,
                    working: false, showsConversation: false, compactConversation: true,
                    wideWindow: wide, stageWidth: width)
                XCTAssertEqual(busy.placement, .margin, "width \(width) wide \(wide)")
                XCTAssertEqual(busy.mode, Stage.mode(showsConversation: false, compactConversation: true,
                                                     wideWindow: wide, stageWidth: width))
            }
        }
    }

    func testTransitionIsNilUnderReduceMotionAndWhileNeedsYou() {
        XCTAssertNil(StageTransition.animation(reduceMotion: true, needsYou: false))
        XCTAssertNil(StageTransition.animation(reduceMotion: false, needsYou: true))
        if NSEvent.pressedMouseButtons == 0, !(NSApplication.shared.keyWindow?.firstResponder is NSTextView) {
            XCTAssertNotNil(StageTransition.animation(reduceMotion: false, needsYou: false))
        }
    }

    func testOtherWorkFinishingDoesNotMoveTheOrbOnceThereIsAThread() {
        func layout(working: Bool) -> StageLayout {
            Stage.layout(threadIsEmpty: false, hasResults: false, showsOtherSurface: false, working: working,
                showsConversation: false, compactConversation: true, wideWindow: true, stageWidth: 1280)
        }
        XCTAssertEqual(layout(working: true), layout(working: false))
    }

    func testRestOrbSlotSide() {
        XCTAssertEqual(AdaptiveLayoutMetrics.restOrbSlotSide(stageWidth: 1280, stageHeight: 670), 440, accuracy: 0.001)
        XCTAssertEqual(AdaptiveLayoutMetrics.restOrbSlotSide(stageWidth: 512, stageHeight: 470), 320, accuracy: 0.001)
        XCTAssertEqual(AdaptiveLayoutMetrics.restOrbSlotSide(stageWidth: 300, stageHeight: 200), 160, accuracy: 0.001)
    }

    // MARK: Rendering

    func testRenderedStageCentresTheOrbThenMovesItAsideAndKeepsFocus() throws {
        let conversation = ConversationStore()
        let (view, window) = host(AdaptiveStageView(voiceState: .offline, wideWindow: true)
            .environment(WorkspaceStore()).environment(conversation).environment(AgentRunStore())
            .environment(ConsoleNoticeState()).environment(DisplayResultStore())
            .environment(ShareCoordinator()).environment(DisplayWindowStore()).environment(DrawerState())
            .environmentObject(client()).environment(\.mortimerReduceMotion, true)
            .foregroundStyle(AppTheme.text).background(AppTheme.bg).preferredColorScheme(.dark),
            width: 1280, height: 700)
        defer { closeRenderingFixtureWindow(window) }
        let micLabel = "Microphone — tap to toggle, hold to talk"
        func orbFrame() throws -> NSRect {
            let controls = accessible(view).controls
            let orb = try XCTUnwrap(controls[micLabel], "Missing orb; labels: \(controls.keys.sorted())")
            return try XCTUnwrap(orb.value(forKey: "accessibilityFrame") as? NSValue).rectValue
        }
        let viewport = window.convertToScreen(view.convert(view.bounds, to: nil))
        let rest = try orbFrame()
        XCTAssertLessThanOrEqual(abs(rest.midX - viewport.midX), 2, "rest orb must be centred: \(rest) in \(viewport)")
        XCTAssertEqual(rest.width, CGFloat(AdaptiveLayoutMetrics.restOrbSlotSide(stageWidth: 1280, stageHeight: 700)),
                       accuracy: 2)

        window.makeFirstResponder(view)
        let responder = window.firstResponder
        conversation.set([try entry("phase3", "user", "Phase three marker")])
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))

        let moved = try orbFrame()
        XCTAssertLessThanOrEqual(moved.maxX, viewport.minX + 261, "orb must be in the margin: \(moved)")
        XCTAssertTrue(accessible(view).text.contains("You: Phase three marker"), "\(accessible(view).text)")
        XCTAssertTrue(window.firstResponder === responder, "the move must not steal keyboard focus")
    }
}
