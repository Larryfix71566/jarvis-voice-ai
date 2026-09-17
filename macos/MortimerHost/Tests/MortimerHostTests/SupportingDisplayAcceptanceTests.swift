import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// C8 supporting-content branch: exercise the rendered escape control,
/// not just its store method. Physical monitor recovery remains separate.
@MainActor
final class SupportingDisplayAcceptanceTests: XCTestCase {
    func testReturningToOriginalPanelsPreservesResearchPinsAndReadingState() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let suite = "supporting-display-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let payload = try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: [
                "title": "Preserved research", "surface": "window",
                "body": (1...100).map { "Finding \($0): synthetic research remains available after changing presentation." }.joined(separator: "\n\n")
            ]))
        let workspace = WorkspaceStore(), display = DisplayWindowStore()
        let result = WorkspaceResult(payload: payload)
        workspace.receive(result)
        XCTAssertTrue(workspace.pin(result.id))
        workspace.rememberScroll(240, for: result.id)
        display.apply(payload)
        let panelIDs = display.panels.map(\.id)
        let drawerKeys = ["mortimer.drawer.tab", "mortimer.drawer.open", "mortimer.drawer.width"]
        let saved = drawerKeys.map { ($0, UserDefaults.standard.object(forKey: $0)) }
        defer {
            for (key, value) in saved {
                if let value { UserDefaults.standard.set(value, forKey: key) }
                else { UserDefaults.standard.removeObject(forKey: key) }
            }
        }
        for layout in [0, 1] {
            defaults.set(layout, forKey: "mortimer.interface.layoutVersion")
            XCTAssertTrue(workspace.sendToDisplay(.result(result.id)))
            let view = NSHostingView(rootView: DisplayWindowView().defaultAppStorage(defaults)
                .environment(display).environment(workspace).environment(DrawerState())
                .environmentObject(client).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: 900, height: 600)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            let controls = labels(in: view)
            if layout == 1 {
                let button = try XCTUnwrap(controls["Original display panels"])
                let frame = try XCTUnwrap(button.value(forKey: "accessibilityFrame") as? NSValue).rectValue
                let viewport = window.convertToScreen(view.convert(view.bounds, to: nil))
                XCTAssertTrue(viewport.insetBy(dx: -1, dy: -1).contains(frame))
                try snapshot(view, name: "supporting-adaptive")
                let press = NSSelectorFromString("accessibilityPerformPress")
                XCTAssertTrue(button.responds(to: press))
                guard button.responds(to: press) else { return }
                typealias Press = @convention(c) (AnyObject, Selector) -> Bool
                let action = unsafeBitCast(button.method(for: press), to: Press.self)
                XCTAssertTrue(action(button, press))
                RunLoop.main.run(until: Date().addingTimeInterval(0.3))
                XCTAssertNil(workspace.supportingContent)
                XCTAssertNil(labels(in: view)["Original display panels"])
                try snapshot(view, name: "supporting-original-panels")
            } else {
                XCTAssertNil(controls["Original display panels"], "legacy layout retains its panel stack")
                try snapshot(view, name: "supporting-legacy")
            }
            XCTAssertEqual(display.panels.map(\.id), panelIDs, "switching presentation must not create or remove results")
            XCTAssertEqual(workspace.activeID, result.id)
            XCTAssertTrue(workspace.pinnedIDs.contains(result.id))
            XCTAssertEqual(workspace.scrollOffsets[result.id], 240)
            XCTAssertEqual(workspace.results.count, 1)
        }
    }

    private func labels(in root: Any) -> [String: NSObject] {
        var result: [String: NSObject] = [:]
        func visit(_ value: Any) {
            guard let object = value as? NSObject else { return }
            let label = NSSelectorFromString("accessibilityLabel")
            if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { result[text] = object }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] { values.forEach(visit) }
        }
        visit(root)
        return result
    }

    private func snapshot(_ view: NSView, name: String) throws {
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: directory.appendingPathComponent(name + ".png"))
    }
}
