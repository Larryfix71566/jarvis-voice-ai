import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

@MainActor
final class CompactConversationTests: XCTestCase {
    func testSavedCompactPreferenceChangesNativeConversationPresentation() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let suite = "compact-conversation-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let workspace = WorkspaceStore()
        let result = WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"body":"Preserved research","surface":"drawer"}"#.utf8)))
        workspace.receive(result)
        workspace.rememberScroll(240, for: result.id)
        workspace.returnToConversation()
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        for width in [512, 1000] {
        for compact in [true, false] {
            defaults.set(compact, forKey: "mortimer.interface.compactConversation")
            let view = NSHostingView(rootView: AdaptiveStageView(voiceState: .offline, wideWindow: width == 1000)
                .defaultAppStorage(defaults).environment(workspace).environmentObject(client)
                .environment(AgentRunStore()).environment(DrawerState()).environment(DisplayResultStore())
                .environment(ConversationStore()).environment(ConsoleNoticeState())
                .foregroundStyle(AppTheme.text).background(AppTheme.bg).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: CGFloat(width), height: 600)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            var labels: [String] = []
            var controls: [String: NSObject] = [:]
            func visit(_ value: Any) {
                guard let object = value as? NSObject else { return }
                let label = NSSelectorFromString("accessibilityLabel")
                if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { labels.append(text); controls[text] = object }
                let children = NSSelectorFromString("accessibilityChildren")
                if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                    values.forEach(visit)
                }
            }
            visit(view)
            XCTAssertTrue(labels.contains(compact ? "Expand voice" : "Keep voice compact"), "Missing mode control: \(labels)")
            XCTAssertTrue(labels.contains("Voice activity — user teal, Mortimer orange"),
                          "compact voice display must remain discoverable to VoiceOver: \(labels)")
            XCTAssertTrue(workspace.showsConversation)
            XCTAssertEqual(defaults.bool(forKey: "mortimer.interface.compactConversation"), compact)
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
                .write(to: directory.appendingPathComponent("conversation-\(width)-\(compact ? "compact" : "expanded").png"))
            let modeLabel = compact ? "Expand voice" : "Keep voice compact"
            for label in [modeLabel, "Memory graph", "Return to workspace"] {
                let control = try XCTUnwrap(controls[label])
                let rect = try XCTUnwrap(control.value(forKey: "accessibilityFrame") as? NSValue).rectValue
                let viewport = window.convertToScreen(view.convert(view.bounds, to: nil))
                XCTAssertTrue(viewport.insetBy(dx: -1, dy: -1).contains(rect), "Clipped \(label) at \(width): \(rect)")
                XCTAssertGreaterThan(rect.width, 20)
            }
            let toggle = try XCTUnwrap(controls[modeLabel])
            let press = NSSelectorFromString("accessibilityPerformPress")
            XCTAssertTrue(toggle.responds(to: press))
            if toggle.responds(to: press) {
                typealias Press = @convention(c) (AnyObject, Selector) -> Bool
                let action = unsafeBitCast(toggle.method(for: press), to: Press.self)
                XCTAssertTrue(action(toggle, press))
                RunLoop.main.run(until: Date().addingTimeInterval(0.2))
                XCTAssertEqual(defaults.bool(forKey: "mortimer.interface.compactConversation"), !compact)
                labels.removeAll(); controls.removeAll(); visit(view)
                XCTAssertTrue(labels.contains(compact ? "Keep voice compact" : "Expand voice"))
                XCTAssertEqual(workspace.activeID, result.id)
                XCTAssertEqual(workspace.scrollOffsets[result.id], 240)
                XCTAssertTrue(workspace.showsConversation)
            }
        }
        }
    }
}
