import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Closure plan C1.2 (gap G02): the WHOLE DrawerView — strip plus the Aa,
/// ⧉ and × chrome — hosted at AppTuning.drawerMinWidth, docked and
/// detached, with every tab selected in turn. The earlier P1 fixtures only
/// hosted the bare strip.
@MainActor
final class DrawerViewMinimumWidthTests: XCTestCase {
    func testDockedDrawerAtMinimumWidthKeepsChromeAndEverySelectedLabelReachable() throws {
        try checkDrawer(poppedOut: false)
    }

    func testDetachedDrawerAtMinimumWidthKeepsChromeAndEverySelectedLabelReachable() throws {
        try checkDrawer(poppedOut: true)
    }

    private func checkDrawer(poppedOut: Bool) throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let suite = "drawer-min-width-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(11.0, forKey: "mortimer.interface.sidecarTabTextSize")
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
        let drawer = DrawerState()
        drawer.isPoppedOut = poppedOut
        drawer.isOpen = !poppedOut
        let width = AppTuning.drawerMinWidth
        let view = NSHostingView(rootView: DrawerView().defaultAppStorage(defaults)
            .environmentObject(client).environment(AgentRunStore()).environment(DisplayResultStore())
            .environment(ConversationStore()).environment(drawer).environment(DrawerModels())
            .environment(WorkspaceStore()).preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: width, height: 600)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))

        func controls() -> [String: CGRect] {
            var found: [String: CGRect] = [:]
            func visit(_ value: Any) {
                guard let object = value as? NSObject else { return }
                let label = NSSelectorFromString("accessibilityLabel")
                if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String,
                   let frame = object.value(forKey: "accessibilityFrame") as? NSValue {
                    found[text] = frame.rectValue
                }
                let children = NSSelectorFromString("accessibilityChildren")
                if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] { values.forEach(visit) }
            }
            visit(view); return found
        }
        let viewport = window.convertToScreen(view.convert(view.bounds, to: nil))
        // Chrome: the text-size menu always; pop-out and close only when docked.
        let chrome = poppedOut ? ["Sidecar tab text size"] : ["Sidecar tab text size", "⧉", "×"]
        for key in DrawerState.tabKeys {
            drawer.setTab(key)
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            let found = controls()
            for label in chrome {
                let frame = try XCTUnwrap(found[label], "Missing \(label) with \(key) selected (poppedOut=\(poppedOut)); labels: \(found.keys.sorted())")
                XCTAssertTrue(viewport.insetBy(dx: -1, dy: -1).contains(frame), "Clipped \(label): \(frame) in \(viewport)")
            }
            let expected = try XCTUnwrap(DrawerState.tabLabels[key]).uppercased()
            let frame = try XCTUnwrap(found[expected], "Selected label \(expected) not exposed (poppedOut=\(poppedOut))")
            XCTAssertGreaterThan(frame.width, 0)
            XCTAssertTrue(viewport.insetBy(dx: -1, dy: -1).contains(frame),
                          "Selected label \(expected) clipped at \(Int(width)) pt (poppedOut=\(poppedOut)): \(frame) in \(viewport)")
            XCTAssertEqual(drawer.activeTab, key)
        }
        XCTAssertEqual(view.bounds.width, width)
    }
}
