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
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        for compact in [true, false] {
            defaults.set(compact, forKey: "mortimer.interface.compactConversation")
            let view = NSHostingView(rootView: AdaptiveStageView(voiceState: .offline, wideWindow: true)
                .defaultAppStorage(defaults).environment(workspace).environmentObject(client)
                .environment(AgentRunStore()).environment(DrawerState()).environment(DisplayResultStore())
                .environment(ConversationStore()).environment(ConsoleNoticeState())
                .foregroundStyle(AppTheme.text).background(AppTheme.bg).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: 1000, height: 600)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            var labels: [String] = []
            func visit(_ value: Any) {
                guard let object = value as? NSObject else { return }
                let label = NSSelectorFromString("accessibilityLabel")
                if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { labels.append(text) }
                let children = NSSelectorFromString("accessibilityChildren")
                if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                    values.forEach(visit)
                }
            }
            visit(view)
            XCTAssertTrue(labels.contains(compact ? "Expand voice" : "Keep voice compact"), "Missing mode control: \(labels)")
            XCTAssertTrue(workspace.showsConversation)
            XCTAssertEqual(defaults.bool(forKey: "mortimer.interface.compactConversation"), compact)
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
                .write(to: directory.appendingPathComponent("conversation-\(compact ? "compact" : "expanded").png"))
        }
    }
}
