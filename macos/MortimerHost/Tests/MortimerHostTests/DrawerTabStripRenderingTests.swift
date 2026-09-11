import XCTest
import AppKit
import SwiftUI
import ApplicationServices
@testable import MortimerHost

/// Real SwiftUI/AppKit layout, using a presentation-only header and no services.
@MainActor
final class DrawerTabStripRenderingTests: XCTestCase {
    func testWideHeaderExposesEveryLabel() throws {
        _ = NSApplication.shared
        let accessibilityApp = AXUIElementCreateApplication(getpid())
        let activation = AXUIElementSetAttributeValue(accessibilityApp,
            "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
        print("Header fixture accessibility activation: \(activation.rawValue)")
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
            guard let element = value as? NSAccessibilityProtocol else { return }
            if let label = element.accessibilityLabel(), !label.isEmpty { labels.append(label) }
            for child in element.accessibilityChildren() ?? [] { visit(child) }
        }
        visit(view)
        for label in DrawerState.tabLabels.values {
            XCTAssertTrue(labels.contains(label), "Missing accessible tab: \(label); tree: \(labels)")
        }
    }
}
