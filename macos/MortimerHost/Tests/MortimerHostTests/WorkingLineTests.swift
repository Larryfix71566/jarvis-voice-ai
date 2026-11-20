import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Interface cleanup Phase 2, slice D: the current-tense working line.
@MainActor
final class WorkingLineTests: XCTestCase {
    private func phrase(_ tool: String?, _ agent: String? = nil) -> String {
        WorkingLine.phrase(tool: tool, agent: agent)
    }

    func testToolFamiliesUseRealToolIds() {
        let cases: [(String, String)] = [
            ("kb_search", "Searching your notes"), ("memory_search", "Searching your notes"),
            ("search_notes", "Searching your notes"), ("memory_graph_view", "Searching your notes"),
            ("repo_read_file", "Reading the repository"), ("repo_search", "Reading the repository"),
            ("git_status", "Reading the repository"), ("git_log", "Reading the repository"),
            ("selfedit_read", "Reading the repository"),
            ("selfedit_write", "Editing code"), ("repo_write_file", "Editing code"),
            ("plan_start", "Editing code"), ("commit", "Editing code"),
            ("web_search", "Searching the web"), ("research_compare_start", "Searching the web"),
            ("get_current_time", "Checking your calendar"), ("date_add", "Checking your calendar"),
            ("mail_headlines", "Reading your email"),
            ("list_reminders", "Checking your reminders"), ("set_reminder", "Checking your reminders"),
            ("get_weather", "Checking the weather"), ("get_weather_radar", "Checking the weather"),
            ("get_system_status", "Checking the Mac"), ("get_top_processes", "Checking the Mac"),
            ("status_overview", "Checking the Mac"),
            ("python_run", "Running code"), ("sandbox_exec", "Running code"),
            ("runlog_stats", "Analysing the data"),
            ("app_create", "Building the app"), ("app_build_start", "Building the app"),
        ]
        for (tool, expected) in cases {
            XCTAssertEqual(phrase(tool), expected, "tool \(tool)")
        }
    }

    func testToolIdIsCaseAndPrefixTolerant() {
        XCTAssertEqual(phrase("  MCP-KB__kb_search "), "Searching your notes")
    }

    func testUnknownToolFallsBackToTheAgent() {
        let cases: [(String, String)] = [
            ("librarian", "Looking that up"), ("developer", "Working on the code"),
            ("analyst", "Analysing"), ("systems", "Checking the Mac"),
            ("scheduler", "Checking your schedule"), ("app_builder", "Building the app"),
        ]
        for (agent, expected) in cases {
            XCTAssertEqual(phrase("zz_mystery", agent), expected, "agent \(agent)")
        }
    }

    func testNothingKnownAndNoToolYet() {
        XCTAssertEqual(phrase("zz_mystery"), "Working on it")
        XCTAssertEqual(phrase("zz_mystery", "unknown_agent"), "Working on it")
        XCTAssertEqual(phrase(nil, "developer"), "Starting")
        XCTAssertEqual(phrase("  ", nil), "Starting")
    }

    private func run(_ id: Int, name: String, display: String, tools: [String]) -> AgentRun {
        AgentRun(id: id, name: name, displayName: display, runId: "run-\(id)", task: "private task words",
                 tools: tools, activity: [], stage: 0, startedAt: Date(timeIntervalSince1970: Double(id)),
                 doneAt: nil, ok: false, detail: "", model: "", modelFallback: false, modelUnusable: false,
                 modelUnusableDetail: "", plannerModel: "")
    }

    func testActivityReturnsThePhraseAndTheActor() throws {
        let runs = [run(1, name: "librarian", display: "Librarian", tools: ["kb_search"])]
        let activity = try XCTUnwrap(ConversationThread.activity(runs: runs, thinking: false))
        XCTAssertEqual(activity.step, "Searching your notes")
        XCTAssertEqual(activity.text, "Searching your notes")
        XCTAssertEqual(activity.actor, "Librarian")
        XCTAssertEqual(activity.runID, 1)
        XCTAssertEqual(activity.accessibilityLabel, "Librarian is working: Searching your notes")
        XCTAssertFalse(activity.text.contains("private task words"))
    }

    func testActivityUsesTheAgentIdForUnknownTools() throws {
        let runs = [run(1, name: "analyst", display: "Analyst", tools: ["zz_mystery"])]
        XCTAssertEqual(ConversationThread.activity(runs: runs, thinking: false)?.step, "Analysing")
    }

    // MARK: Rendered

    private func host<V: View>(_ root: V) -> (NSHostingView<V>, NSWindow) {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: 400, height: 60)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        return (view, window)
    }

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
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(root)
        return (text, controls)
    }

    private var sample: ConversationThread.Activity {
        ConversationThread.Activity(actor: "Librarian", step: "Searching your notes")
    }

    func testRowShowsThePhraseAndWorksWithoutADrawer() {
        let (view, window) = host(ConversationActivityRowView(activity: sample, reduceMotion: true))
        defer { closeRenderingFixtureWindow(window) }
        let found = accessible(view)
        XCTAssertTrue(found.text.contains("Librarian is working: Searching your notes"), "\(found.text)")
        XCTAssertFalse(found.text.contains { $0.contains("Librarian ·") })
    }

    func testPerformingTheRowActionOpensInspectOnAgents() {
        let drawer = DrawerState()
        let saved = ["mortimer.drawer.tab", "mortimer.drawer.open"].map { ($0, UserDefaults.standard.object(forKey: $0)) }
        defer {
            for (key, value) in saved {
                if let value { UserDefaults.standard.set(value, forKey: key) }
                else { UserDefaults.standard.removeObject(forKey: key) }
            }
        }
        drawer.setTab("repo"); drawer.isOpen = false
        ConversationActivityRowView.openInspect(drawer)
        XCTAssertEqual(drawer.activeTab, "agents")
        XCTAssertTrue(drawer.isOpen)
        XCTAssertNil(drawer.focusedRunID)
    }

    func testPerformingTheRowActionFocusesItsRun() {
        let drawer = DrawerState()
        let saved = ["mortimer.drawer.tab", "mortimer.drawer.open"].map { ($0, UserDefaults.standard.object(forKey: $0)) }
        defer {
            for (key, value) in saved {
                if let value { UserDefaults.standard.set(value, forKey: key) }
                else { UserDefaults.standard.removeObject(forKey: key) }
            }
        }
        drawer.setTab("repo"); drawer.isOpen = false
        ConversationActivityRowView.openInspect(drawer, runID: 7)
        XCTAssertEqual(drawer.activeTab, "agents")
        XCTAssertTrue(drawer.isOpen)
        XCTAssertEqual(drawer.focusedRunID, 7)
    }

    func testRowWithADrawerIsRenderedAsAControl() {
        let drawer = DrawerState()
        let (view, window) = host(ConversationActivityRowView(activity: sample, reduceMotion: true)
            .environment(drawer))
        defer { closeRenderingFixtureWindow(window) }
        let found = accessible(view)
        XCTAssertTrue(found.text.contains("Librarian is working: Searching your notes"), "\(found.text)")
        XCTAssertTrue(found.text.contains("Opens Inspect on this run") || found.controls["Librarian is working: Searching your notes"] != nil,
                      "\(found.text)")
    }
}
