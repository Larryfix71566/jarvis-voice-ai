import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

/// Real SwiftUI/AppKit layout, using a presentation-only header and no services.
@MainActor
final class DrawerTabStripRenderingTests: XCTestCase {
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
