import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// C8 supporting-content branch: exercise the rendered escape control,
/// not just its store method. Physical monitor recovery remains separate.
@MainActor
final class SupportingDisplayAcceptanceTests: XCTestCase {
    func testStreamedResponseRendersOnlyOnSupportingDisplayThenReturnsToMain() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let screens = NSScreen.screens
        guard screens.count >= 2 else { throw XCTSkip("requires two connected displays") }
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let workspace = WorkspaceStore(), display = DisplayWindowStore(), router = ResponseResultRouter()
        let defaults = try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
        defaults.set(2, forKey: "mortimer.interface.layoutVersion")
        defer { defaults.removeObject(forKey: "mortimer.interface.layoutVersion") }
        func entry(_ text: String) throws -> ConversationEntry {
            try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
                ["id": "answer", "role": "assistant", "text": text, "createdAt": 1234]))
        }
        router.receive([try entry("Initial response")], workspace: workspace, display: display)
        let main = NSHostingView(rootView: WorkspaceView().defaultAppStorage(defaults)
            .environment(ShareCoordinator()).environment(workspace).environment(display)
            .environment(DrawerState()).environmentObject(client).preferredColorScheme(.dark))
        let supporting = NSHostingView(rootView: DisplayWindowView().defaultAppStorage(defaults)
            .environment(ShareCoordinator()).environment(workspace).environment(display)
            .environment(DrawerState()).environmentObject(client).preferredColorScheme(.dark))
        var windows: [NSWindow] = []
        defer { windows.forEach { $0.close() } }
        for (index, view) in ([main, supporting] as [NSView]).enumerated() {
            let screen = screens[index]
            let frame = CGRect(x: screen.visibleFrame.minX, y: screen.visibleFrame.minY,
                               width: min(1100, screen.visibleFrame.width), height: 740)
            view.frame = CGRect(origin: .zero, size: frame.size)
            let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view
            windows.append(window); window.orderFrontRegardless()
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        }
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        display.setWindowOpen(true)
        let answer = "Completed response with all findings, shown in the results area."
        router.receive([try entry(answer)], workspace: workspace, display: display)
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        XCTAssertTrue(labels(in: supporting).keys.contains { $0.contains(answer) })
        XCTAssertFalse(labels(in: main).keys.contains { $0.contains(answer) })
        XCTAssertNotNil(labels(in: main)["Result is on the supporting display"])
        XCTAssertEqual(display.panels.count, 1)
        try snapshot(main, name: "response-main-locator")
        try snapshot(supporting, name: "response-supporting")
        windows[1].close()
        display.setWindowOpen(false)
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        XCTAssertTrue(labels(in: main).keys.contains { $0.contains(answer) })
        XCTAssertNil(labels(in: main)["Result is on the supporting display"])
        try snapshot(main, name: "response-main-returned")
    }

    func testPointerSelectedResultSharesStageOnConnectedDisplays() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let screens = NSScreen.screens
        guard screens.count >= 2 else { throw XCTSkip("requires two connected displays") }
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let workspace = WorkspaceStore(), display = DisplayWindowStore()
        display.setWindowOpen(true)
        func result(_ title: String) throws -> WorkspaceResult {
            let payload = try JSONDecoder().decode(DisplayPayload.self,
                from: JSONSerialization.data(withJSONObject: [
                    "title": title, "surface": "window", "body": "Synthetic display acceptance content."
                ]))
            return WorkspaceResult(payload: payload)
        }
        for index in 1...4 {
            let item = try result("Transport tile \(index)")
            workspace.receive(item)
            display.apply(item.payload, workspaceID: item.id)
        }
        let selected = try result("Pointer selected tile")
        workspace.receive(selected)
        XCTAssertTrue(workspace.sendToDisplay(.result(selected.id)))
        let defaults = try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
        defaults.set(2, forKey: "mortimer.interface.layoutVersion")
        defer { defaults.removeObject(forKey: "mortimer.interface.layoutVersion") }

        for (index, screen) in screens.prefix(2).enumerated() {
            let view = NSHostingView(rootView: DisplayWindowView().defaultAppStorage(defaults)
                .environment(ShareCoordinator()).environment(display).environment(workspace)
                .environment(DrawerState()).environmentObject(client).preferredColorScheme(.dark))
            let frame = CGRect(x: screen.visibleFrame.minX, y: screen.visibleFrame.minY,
                               width: min(1280, screen.visibleFrame.width),
                               height: min(1050, screen.visibleFrame.height))
            view.frame = CGRect(origin: .zero, size: frame.size)
            let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = view
            window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.4))
            XCTAssertEqual(window.screen, screen)
            let controls = labels(in: view)
            XCTAssertTrue(controls.keys.contains { $0.contains("Pointer selected tile") },
                          "explicit selection must actually render: \(controls.keys.sorted())")
            XCTAssertTrue(controls.keys.contains { $0.contains("Transport tile 4") },
                          "the latest transport result shares the stage")
            XCTAssertFalse(controls.keys.contains { $0.contains("Transport tile 3") },
                           "the reserved fourth tile cannot escape into a floating panel")
            try snapshot(view, name: "supporting-pointer-mixed-display-\(index)")
        }
        XCTAssertEqual(workspace.results.count, 5)
        XCTAssertEqual(display.panels.count, 4, "stage selection preserves result history")
    }

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
        for layout in [0, 1, 2] {
            defaults.set(layout, forKey: "mortimer.interface.layoutVersion")
            XCTAssertTrue(workspace.sendToDisplay(.result(result.id)))
            let view = NSHostingView(rootView: DisplayWindowView().defaultAppStorage(defaults)
                .environment(ShareCoordinator())
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
            } else if layout == 0 {
                XCTAssertNil(controls["Original display panels"], "legacy layout retains its panel stack")
                try snapshot(view, name: "supporting-legacy")
            } else {
                XCTAssertNil(controls["Original display panels"])
                try snapshot(view, name: "supporting-command-console")
            }
            XCTAssertEqual(display.panels.map(\.id), panelIDs, "switching presentation must not create or remove results")
            XCTAssertEqual(workspace.activeID, result.id)
            XCTAssertTrue(workspace.pinnedIDs.contains(result.id))
            XCTAssertEqual(workspace.scrollOffsets[result.id], 240)
            XCTAssertEqual(workspace.results.count, 1)
        }
    }

    func testFourResultStageRendersAVisibleBoundedGrid() throws {
        _ = NSApplication.shared
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        display.setWindowOpen(true)
        for index in 1...4 {
            let payload = try JSONDecoder().decode(DisplayPayload.self,
                from: JSONSerialization.data(withJSONObject: [
                    "title": "Grid result \(index)", "surface": "window",
                    "body": "Visible result \(index) — the supporting stage keeps this tile readable."
                ]))
            let result = WorkspaceResult(payload: payload)
            workspace.receive(result)
            display.apply(payload, workspaceID: result.id)
        }

        let root = DisplayWindowView()
            .environment(ShareCoordinator())
            .environment(display)
            .environment(workspace)
            .environment(DrawerState())
            .environmentObject(client)
            .preferredColorScheme(.dark)
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: 1280, height: 800)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded()
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))

        XCTAssertEqual(display.presentationPanels.count, 4)
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let samples = stride(from: 0, to: bitmap.pixelsHigh, by: 4).flatMap { y in
            stride(from: 0, to: bitmap.pixelsWide, by: 4).compactMap { x in
                bitmap.colorAt(x: x, y: y)
            }
        }
        let visiblyLit = samples.filter {
            let rgb = $0.usingColorSpace(.deviceRGB)
            return (rgb?.redComponent ?? 0) + (rgb?.greenComponent ?? 0) + (rgb?.blueComponent ?? 0) > 0.42
        }.count
        XCTAssertGreaterThan(visiblyLit, 100,
            "a four-result stage must render visible content instead of collapsing to the background")
        try snapshot(view, name: "supporting-four-result-grid")
    }

    private func labels(in root: Any) -> [String: NSObject] {
        var result: [String: NSObject] = [:]
        func visit(_ value: Any) {
            guard let object = value as? NSObject else { return }
            let label = NSSelectorFromString("accessibilityLabel")
            if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { result[text] = object }
            let value = NSSelectorFromString("accessibilityValue")
            if object.responds(to: value), let text = object.perform(value)?.takeUnretainedValue() as? String { result[text] = object }
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
