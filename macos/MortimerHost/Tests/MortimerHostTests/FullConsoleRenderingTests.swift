import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

@MainActor
final class FullConsoleRenderingTests: XCTestCase {
    func testEveryPersistedLayoutMigratesToCommandConsole() throws {
        let suite = "layout-migration-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        for previous in [nil, 0, 1, 2, 99, -1] as [Int?] {
            if let previous { defaults.set(previous, forKey: InterfaceLayoutVersion.preferenceKey) }
            else { defaults.removeObject(forKey: InterfaceLayoutVersion.preferenceKey) }
            // The former one-time migration must not preserve a retired layout.
            defaults.set(true, forKey: "mortimer.interface.commandConsoleDefaultMigrated")
            InterfaceLayoutVersion.migrate(defaults)
            XCTAssertEqual(defaults.integer(forKey: InterfaceLayoutVersion.preferenceKey), 2)
            InterfaceLayoutVersion.migrate(defaults)
            XCTAssertEqual(defaults.integer(forKey: InterfaceLayoutVersion.preferenceKey), 2)
        }
    }

    func testMinimumConsoleKeepsOutputAndMicrophoneControlsReachable() throws {
        try checkConsole(tabTextSize: 11)
    }

    func testEnlargedTabTextKeepsFullConsoleControlsReachable() throws {
        try checkConsole(tabTextSize: 22)
    }

    func testCommandConsoleStartsInConversationWithVoiceControls() throws {
        try checkConsole(tabTextSize: 11, layoutVersion: 2, startup: true)
    }

    func testRetiredAndUnknownPreferencesStillRenderCommandConsole() throws {
        for previous in [0, 1, -1, 99] {
            try checkConsole(tabTextSize: 11, layoutVersion: previous, startup: true)
        }
    }

    private func checkConsole(tabTextSize: Double, layoutVersion: Int = 2, startup: Bool = false) throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let suite = "full-console-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(layoutVersion, forKey: "mortimer.interface.layoutVersion")
        // Result-view checks opt out explicitly. The startup fixture
        // exercises the production default, which is compact conversation.
        if !startup { defaults.set(false, forKey: "mortimer.interface.compactConversation") }
        defaults.set(tabTextSize, forKey: "mortimer.interface.sidecarTabTextSize")
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let drawerKeys = ["mortimer.drawer.tab", "mortimer.drawer.open", "mortimer.drawer.width"]
        let savedDrawer = drawerKeys.map { ($0, UserDefaults.standard.object(forKey: $0)) }
        defer {
            for (key, value) in savedDrawer {
                if let value { UserDefaults.standard.set(value, forKey: key) }
                else { UserDefaults.standard.removeObject(forKey: key) }
            }
        }
        let drawer = DrawerState(); drawer.activeTab = "output"; drawer.isOpen = true
        drawer.width = 400
        let workspace = WorkspaceStore(), output = DisplayResultStore(), attachments = AttachmentStore()
        let payload = try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"body":"Synthetic research result for minimum console acceptance.","surface":"drawer"}"#.utf8))
        let result = WorkspaceResult(payload: payload)
        if !startup { workspace.receive(result); output.apply(payload, workspaceID: result.id) }
        for (width, height) in [(900, 600), (1280, 800), (1440, 900), (2560, 1080), (900, 1440)] {
        let view = NSHostingView(rootView: ConsoleView().defaultAppStorage(defaults)
            .environmentObject(client).environment(AgentRunStore()).environment(output)
            .environment(workspace).environment(ConversationStore()).environment(DisplayWindowStore())
            .environment(drawer).environment(DrawerModels()).environment(attachments)
            .environment(ShareCoordinator())
            .environment(ConsoleOverlayState())
            .environment(ConsoleNoticeState())
            // Rendering fixtures should not create perpetual AppKit animation
            // roots; production views normally follow the system preference.
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height))
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        var controls: [String: NSObject] = [:]
        func visit(_ value: Any) {
            guard let object = value as? NSObject else { return }
            let label = NSSelectorFromString("accessibilityLabel")
            if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { controls[text] = object }
            // WS-17: a console Menu is an AXMenuButton named by its AXTitle, an
            // NSAttributedString (probe on the Mac, 09-30).
            let title = NSSelectorFromString("accessibilityTitle")
            if object.responds(to: title), let raw = object.perform(title)?.takeUnretainedValue(),
               let text = (raw as? String) ?? (raw as? NSAttributedString)?.string,
               !text.isEmpty, controls[text] == nil { controls[text] = object }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] { values.forEach(visit) }
        }
        visit(view)
        let viewport = window.convertToScreen(view.convert(view.bounds, to: nil))
        let required = ["OUTPUT", "Sidecar tab text size", "🔇 Mic off", "Wake word off"] + (startup ? ["Expand voice", "Knowledge", "Tools", "Paste content", "Choose content"] : [])
        for label in required {
            let control = try XCTUnwrap(controls[label], "Missing \(label); labels: \(controls.keys.sorted())")
            let frame = try XCTUnwrap(control.value(forKey: "accessibilityFrame") as? NSValue).rectValue
            XCTAssertTrue(viewport.insetBy(dx: -1, dy: -1).contains(frame), "Clipped \(label): \(frame)")
        }
        XCTAssertEqual(view.bounds.width, CGFloat(width))
        XCTAssertEqual(view.bounds.height, CGFloat(height))
        XCTAssertEqual(workspace.activeID, startup ? nil : result.id)
        XCTAssertEqual(workspace.showsConversation, startup)
        XCTAssertEqual(drawer.activeTab, "output")
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: directory.appendingPathComponent("console-\(width)-\(height)-text-\(Int(tabTextSize)).png"))
        }
    }
}
