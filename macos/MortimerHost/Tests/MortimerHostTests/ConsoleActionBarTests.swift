import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// WS-17 (Larry, 2026-09-30): "all buttons on the console line, none below."
/// The Command Console has one control row (`ConsoleActionBar`); the stage,
/// the results view and the result pane draw no buttons of their own in
/// layout 2, and keep them in the other layouts.
@MainActor
final class ConsoleActionBarTests: XCTestCase {
    private func result(_ title: String) throws -> WorkspaceResult {
        WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"title":"\#(title)","body":"Body of \#(title)","surface":"drawer"}"#.utf8)))
    }

    // MARK: Rules

    func testModeFollowsTheInventoryPrecedence() {
        typealias B = ConsoleActionBar
        XCTAssertEqual(B.mode(conversation: true, skills: true, memory: false, atlas: false, workflows: false), .conversation)
        XCTAssertEqual(B.mode(conversation: false, skills: true, memory: true, atlas: false, workflows: false), .skills)
        XCTAssertEqual(B.mode(conversation: false, skills: false, memory: true, atlas: true, workflows: false), .memory)
        XCTAssertEqual(B.mode(conversation: false, skills: false, memory: false, atlas: true, workflows: false), .atlas)
        XCTAssertEqual(B.mode(conversation: false, skills: false, memory: false, atlas: false, workflows: true), .workflows)
        XCTAssertEqual(B.mode(conversation: false, skills: false, memory: false, atlas: false, workflows: false), .results)
    }

    func testActionsTargetTheChosenSideOfAComparison() throws {
        let a = try result("A"), b = try result("B")
        XCTAssertEqual(ConsoleActionBar.actionTarget(active: a, comparison: nil, side: .b)?.id, a.id,
                       "no comparison: the active result")
        XCTAssertEqual(ConsoleActionBar.actionTarget(active: a, comparison: b, side: .a)?.id, a.id)
        XCTAssertEqual(ConsoleActionBar.actionTarget(active: a, comparison: b, side: .b)?.id, b.id)
        XCTAssertNil(ConsoleActionBar.actionTarget(active: nil, comparison: nil, side: .a))
    }

    func testActionsAppearOnlyWhileAResultIsShown() {
        XCTAssertTrue(ConsoleActionBar.showsActions(mode: .results, hasActiveResult: true))
        XCTAssertFalse(ConsoleActionBar.showsActions(mode: .results, hasActiveResult: false))
        XCTAssertFalse(ConsoleActionBar.showsActions(mode: .conversation, hasActiveResult: true))
        XCTAssertFalse(ConsoleActionBar.showsActions(mode: .atlas, hasActiveResult: true))
    }

    // MARK: Rendered

    private func labels(layoutVersion: Int, width: CGFloat, withBar: Bool) throws -> [String] {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let suite = "console-bar-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(layoutVersion, forKey: "mortimer.interface.layoutVersion")
        let workspace = WorkspaceStore()
        let first = try result("Weather — Folly Beach"), second = try result("Research — Charleston")
        workspace.receive(first); workspace.receive(second)
        workspace.select(first.id)                       // the results view, a result shown
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let view = NSHostingView(rootView: VStack(spacing: 0) {
                if withBar { ConsoleActionBar(coordinator: nil) }
                AdaptiveStageView(voiceState: .offline, wideWindow: width >= 1000)
            }
            .defaultAppStorage(defaults)
            .environment(workspace).environmentObject(client)
            .environment(AgentRunStore()).environment(DrawerState()).environment(DisplayResultStore())
            .environment(ConversationStore()).environment(ConsoleNoticeState())
            .environment(DisplayWindowStore()).environment(ShareCoordinator())
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: width, height: 640)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        var found: [String] = []
        func visit(_ value: Any) {
            guard let object = value as? NSObject else { return }
            // A plain SwiftUI Menu is an AXMenuButton whose name is its
            // AXTitle, returned as an NSAttributedString (probe on the Mac,
            // 09-30: title "Knowledge" for every Menu form, label empty).
            // Collect label, title (string or attributed) and identifier.
            for selector in ["accessibilityLabel", "accessibilityTitle"] {
                let sel = NSSelectorFromString(selector)
                guard object.responds(to: sel), let raw = object.perform(sel)?.takeUnretainedValue() else { continue }
                let text = (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
                if !text.isEmpty { found.append(text) }
            }
            let ident = NSSelectorFromString("accessibilityIdentifier")
            if object.responds(to: ident), let text = object.perform(ident)?.takeUnretainedValue() as? String,
               !text.isEmpty { found.append("id:" + text) }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(view)
        return found
    }

    /// Controls that used to sit in rows below the console header.
    private let formerSecondRow = ["Return to workspace", "Knowledge Atlas", "Memory graph", "Skills", "Workflows",
                                   "Pin", "Compare", "Display", "Copy selected result", "Share selected result",
                                   "Export…", "Close Weather — Folly Beach"]

    func testLayoutTwoHasOneControlRowAtEveryWidth() throws {
        for width: CGFloat in [520, 1000, 1600] {
            let found = try labels(layoutVersion: 2, width: width, withBar: true)
            for label in formerSecondRow {
                XCTAssertFalse(found.contains(label), "layout 2 at \(width): \(label) is drawn below the console row: \(found)")
            }
            for id in ["conversation", "results", "knowledge", "tools", "actions"] {
                XCTAssertTrue(found.contains("id:console.\(id)"), "layout 2 at \(width): console.\(id) missing from the console row: \(found)")
            }
            for name in ["Conversation", "Knowledge", "Tools", "Actions", "Results · 2"] {
                XCTAssertTrue(found.contains(name), "layout 2 at \(width): no accessible name \(name) in the console row: \(found)")
            }
        }
    }

    func testTheStageAloneDrawsNoControlsInLayoutTwo() throws {
        let found = try labels(layoutVersion: 2, width: 1200, withBar: false)
        for label in formerSecondRow + ["Expand voice", "Keep voice compact"] {
            XCTAssertFalse(found.contains(label), "the layout-2 stage draws \(label): \(found)")
        }
    }

    func testOtherLayoutsKeepTheirOwnRows() throws {
        let found = try labels(layoutVersion: 1, width: 1600, withBar: false)
        for label in ["Pin", "Close Weather — Folly Beach", "Copy selected result"] {
            XCTAssertTrue(found.contains(label), "layout 1 lost \(label): \(found)")
        }
    }
}
