import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Interface cleanup Phase 2, slice C: one top capsule, a Command-K menu.
@MainActor
final class ConsoleCapsuleTests: XCTestCase {
    private func client() -> JarvisClient {
        JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
    }

    private func commands(connected: Bool = true, connecting: Bool = false, wake: Bool = true) -> [CommandPalette.Command] {
        CommandPalette.commands(connected: connected, connecting: connecting, wakeWordAvailable: wake,
                                wakeWordOn: false, soundsOn: true, inspectOpen: false,
                                compactConversation: true)
    }

    // MARK: Palette rules

    func testEmptyQueryKeepsTheFullOrderedList() {
        let list = commands()
        XCTAssertEqual(CommandPalette.filter(list, query: "  "), list)
        XCTAssertEqual(list.prefix(6).map { $0.id },
                       ["conversation", "results", "atlas", "memory", "skills", "workflows"])
    }

    func testPrefixOutranksSubstringAndKeywords() {
        let ids = CommandPalette.filter(commands(), query: "in").map { $0.id }
        XCTAssertEqual(ids.first, "inspect", "title prefix wins: \(ids)")
        XCTAssertTrue(CommandPalette.filter(commands(), query: "zzz").isEmpty)
        XCTAssertEqual(CommandPalette.filter(commands(), query: "transcript").first?.id, "log")
    }

    func testReturnRunsTheFirstMatch() {
        XCTAssertEqual(CommandPalette.filter(commands(), query: "log").first?.action, .openLog)
        XCTAssertEqual(CommandPalette.filter(commands(), query: "skill").first?.action, .view("skills"))
    }

    func testConnectOnlyWhenNotConnectedAndWakeWordOnlyWhenAvailable() {
        XCTAssertNil(commands(connected: true).first(where: { $0.id == "connect" }))
        XCTAssertNotNil(commands(connected: true).first(where: { $0.id == "disconnect" }))
        XCTAssertNotNil(commands(connected: false).first(where: { $0.id == "connect" }))
        XCTAssertNil(commands(connected: false, connecting: true).first(where: { $0.id == "connect" }))
        XCTAssertNil(commands(wake: false).first(where: { $0.id == "wake" }))
        XCTAssertNotNil(commands(wake: true).first(where: { $0.id == "wake" }))
    }

    // MARK: Overflow rules

    private func items(_ state: JarvisClient.ConnectionState, voices: Bool = true, wake: Bool = true)
        -> [TopBarView.OverflowItem] {
        TopBarView.overflowItems(connection: state, hasVoices: voices, wakeWordAvailable: wake,
                                 wakeWordOn: false, soundsOn: true)
    }

    func testOverflowNeverOffersConnect() {
        XCTAssertTrue(items(.connected).contains(.disconnect))
        for state in [JarvisClient.ConnectionState.offline, .failed("synthetic")] {
            let list = items(state)
            XCTAssertFalse(list.contains(.disconnect), "\(state)")
            XCTAssertFalse(list.contains(.connecting), "\(state)")
        }
        XCTAssertTrue(items(.connecting).contains(.connecting))
    }

    func testDisabledPreferencesAreHidden() {
        let list = items(.offline, voices: false, wake: false)
        XCTAssertFalse(list.contains(.voice))
        XCTAssertFalse(list.contains(.wakeWord(on: false)))
        XCTAssertTrue(list.contains(.sounds(on: true)))
        XCTAssertTrue(list.contains(.openDisplay))
        XCTAssertTrue(list.contains(.commandMenu))
        XCTAssertTrue(items(.connected).contains(.voice))
    }

    // MARK: Rendered

    func testOfflineCapsuleShowsBrandInspectAndMoreOnly() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let drawer = DrawerState()
        drawer.isOpen = false
        let root = TopBarView()
            .environmentObject(client()).environment(AgentRunStore()).environment(DisplayResultStore())
            .environment(drawer).environment(DisplayWindowStore())
            .environment(WorkspaceStore()).environment(ShareCoordinator()).environment(ConsoleNoticeState())
            .environment(\.mortimerReduceMotion, true).preferredColorScheme(.dark)
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: 1280, height: 80)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        var seen = Set<ObjectIdentifier>()
        var text: [String] = []
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            for name in ["accessibilityLabel", "accessibilityValue", "accessibilityTitle"] {
                let selector = NSSelectorFromString(name)
                guard object.responds(to: selector),
                      let raw = object.perform(selector)?.takeUnretainedValue() else { continue }
                let string = (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
                if !string.isEmpty { text.append(string) }
            }
            let ident = NSSelectorFromString("accessibilityIdentifier")
            if object.responds(to: ident), let id = object.perform(ident)?.takeUnretainedValue() as? String,
               !id.isEmpty { text.append("id:" + id) }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children),
               let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(view)
        XCTAssertTrue(text.contains("Inspect"), "\(text)")
        XCTAssertTrue(text.contains("More"), "\(text)")
        XCTAssertTrue(text.contains("MORTIMER"), "\(text)")
        XCTAssertTrue(text.contains("id:console.conversation"), "\(text)")
        XCTAssertFalse(text.contains("Connect"), "capsule must not carry Connect: \(text)")
        XCTAssertFalse(text.contains(where: { $0.contains("VOICE") }), "no VOICE label: \(text)")
    }
}
