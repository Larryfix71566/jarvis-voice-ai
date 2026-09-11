import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

/// Real SwiftUI/AppKit layout, using a presentation-only header and no services.
@MainActor
final class DrawerTabStripRenderingTests: XCTestCase {
    func testNarrowStripRevealsEntireSelectedLastTab() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: DrawerTabStrip(selectedTab: "costs", attention: [:], select: { _ in })
            .padding(8).background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: 300, height: 64)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view
        window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.25))
        var selectedFrames: [CGRect] = []
        func visit(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            if element.responds(to: labelSelector),
               let label = element.perform(labelSelector)?.takeUnretainedValue() as? String,
               label == "COSTS", element.responds(to: NSSelectorFromString("accessibilityFrame")),
               let frame = element.value(forKey: "accessibilityFrame") as? NSValue {
                selectedFrames.append(frame.rectValue)
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                for child in children { visit(child) }
            }
        }
        visit(view)
        XCTAssertFalse(selectedFrames.isEmpty, "Selected tab must be exposed to accessibility")
        // Exclude outer padding, fixed overflow arrows and inter-control gaps:
        // being inside the window alone would not prove the label is unclipped.
        let visible = window.convertToScreen(view.convert(view.bounds, to: nil))
            .insetBy(dx: 8 + 24 + 2, dy: 0)
        for frame in selectedFrames {
            XCTAssertGreaterThan(frame.width, 0)
            XCTAssertGreaterThanOrEqual(frame.minX, visible.minX)
            XCTAssertLessThanOrEqual(frame.maxX, visible.maxX)
        }
    }

    func testNarrowMountedStripRevealsEverySelectionInBothDirections() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let selection = HeaderSelection()
        let view = NSHostingView(rootView: MountedHeader(selection: selection)
            .padding(8).background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: 300, height: 64)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view
        window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.25))
        for key in DrawerState.tabKeys + DrawerState.tabKeys.reversed() {
        selection.tab = key
        RunLoop.main.run(until: Date().addingTimeInterval(0.25))
        var selectedFrames: [CGRect] = []
        func visit(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            if element.responds(to: labelSelector),
               let label = element.perform(labelSelector)?.takeUnretainedValue() as? String,
               label == DrawerState.tabLabels[key]?.uppercased(), element.responds(to: NSSelectorFromString("accessibilityFrame")),
               let frame = element.value(forKey: "accessibilityFrame") as? NSValue {
                selectedFrames.append(frame.rectValue)
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                for child in children { visit(child) }
            }
        }
        visit(view)
        XCTAssertFalse(selectedFrames.isEmpty, "Selected tab must be exposed to accessibility")
        // Exclude outer padding, fixed overflow arrows and inter-control gaps:
        // being inside the window alone would not prove the label is unclipped.
        let visible = window.convertToScreen(view.convert(view.bounds, to: nil))
            .insetBy(dx: 8 + 24 + 2, dy: 0)
        for frame in selectedFrames {
            XCTAssertGreaterThan(frame.width, 0)
            XCTAssertGreaterThanOrEqual(frame.minX, visible.minX)
            XCTAssertLessThanOrEqual(frame.maxX, visible.maxX)
        }
        }
    }

    func testOverflowButtonsReachBothEndsWithoutChangingSelection() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let selection = HeaderSelection()
        let view = NSHostingView(rootView: MountedHeader(selection: selection)
            .padding(8))
        view.frame = NSRect(x: 0, y: 0, width: 300, height: 64)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        RunLoop.main.run(until: Date().addingTimeInterval(0.25))
        func controls() -> [String: NSObject] {
            var found: [String: NSObject] = [:]
            func visit(_ value: Any) {
                guard let object = value as? NSObject else { return }
                let label = NSSelectorFromString("accessibilityLabel")
                if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { found[text] = object }
                let children = NSSelectorFromString("accessibilityChildren")
                if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] { values.forEach(visit) }
            }
            visit(view); return found
        }
        for (arrow, endLabel) in [("Scroll tabs right", "COSTS"), ("Scroll tabs left", "REPO")] {
            var presses = 0
            for _ in 0..<16 {
                let button = try XCTUnwrap(controls()[arrow])
                let enabled = try XCTUnwrap(button.value(forKey: "accessibilityEnabled") as? NSNumber).boolValue
                if !enabled { break }
                let selector = NSSelectorFromString("accessibilityPerformPress")
                XCTAssertTrue(button.responds(to: selector))
                guard button.responds(to: selector) else { return }
                typealias Press = @convention(c) (AnyObject, Selector) -> Bool
                XCTAssertTrue(unsafeBitCast(button.method(for: selector), to: Press.self)(button, selector))
                presses += 1
                RunLoop.main.run(until: Date().addingTimeInterval(0.3))
                XCTAssertEqual(selection.tab, "repo", "Scrolling must not select a tab")
            }
            XCTAssertGreaterThan(presses, 0)
            let reached = controls()
            let button = try XCTUnwrap(reached[arrow])
            XCTAssertEqual((button.value(forKey: "accessibilityEnabled") as? NSNumber)?.boolValue, false)
            let end = try XCTUnwrap(reached[endLabel])
            let frame = try XCTUnwrap(end.value(forKey: "accessibilityFrame") as? NSValue).rectValue
            let visible = window.convertToScreen(view.convert(view.bounds, to: nil)).insetBy(dx: 34, dy: 0)
            XCTAssertGreaterThanOrEqual(frame.minX, visible.minX - 1)
            XCTAssertLessThanOrEqual(frame.maxX, visible.maxX + 1)
        }
    }

    func testWideHeaderExposesEveryLabel() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: DrawerTabStrip(selectedTab: "memory", attention: [:], select: { _ in })
            .padding(8).background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: 1000, height: 64)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded()
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.15))
        var labels: [String] = []
        func visit(_ value: Any) {
            if let element = value as? NSAccessibilityProtocol {
                if let label = element.accessibilityLabel(), !label.isEmpty { labels.append(label) }
                for child in element.accessibilityChildren() ?? [] { visit(child) }
            } else if let element = value as? NSObject {
                // SwiftUI implements the public selectors without declaring
                // formal protocol conformance; avoid losing those nodes.
                let labelSelector = NSSelectorFromString("accessibilityLabel")
                if element.responds(to: labelSelector),
                   let label = element.perform(labelSelector)?.takeUnretainedValue() as? String,
                   !label.isEmpty { labels.append(label) }
                let childrenSelector = NSSelectorFromString("accessibilityChildren")
                if element.responds(to: childrenSelector),
                   let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                    for child in children { visit(child) }
                }
            }
        }
        visit(view)
        for label in DrawerState.tabLabels.values {
            // The existing header renders these labels in uppercase. Assert
            // the complete rendered label, including every character.
            XCTAssertTrue(labels.contains(label.uppercased()), "Missing accessible tab: \(label); tree: \(labels)")
        }
    }
}

@MainActor
@Observable
private final class HeaderSelection { var tab = "repo" }

private struct MountedHeader: View {
    @Bindable var selection: HeaderSelection
    var body: some View {
        DrawerTabStrip(selectedTab: selection.tab, attention: [:]) { selection.tab = $0 }
    }
}
