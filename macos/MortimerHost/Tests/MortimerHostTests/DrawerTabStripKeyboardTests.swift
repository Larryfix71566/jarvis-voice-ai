import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

/// Closure plan C1.1 (gap G01): real key events into a real window drive
/// the header's selection, and each keyboard selection reveals the whole
/// selected label inside the scroll viewport at the 300 pt minimum.
@MainActor
final class DrawerTabStripKeyboardTests: XCTestCase {
    func testArrowAndHomeEndKeysMoveSelectionAndRevealTheSelectedLabel() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let selection = KeyboardHeaderSelection()
        let view = NSHostingView(rootView: KeyboardMountedHeader(selection: selection)
            .padding(8).background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: 300, height: 64)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view
        window.orderFrontRegardless(); window.makeKey()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.25))

        // Put keyboard focus on the strip: the hosting view becomes first
        // responder, then one Tab moves focus to the first focusable control,
        // which is the strip container (the plain tab buttons are not key-view
        // stops without Full Keyboard Access).
        XCTAssertTrue(window.makeFirstResponder(view))
        press(.tab, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))

        press(.right, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        XCTAssertEqual(selection.tab, "edit", "→ must select the next tab")
        try assertSelectedLabelVisible(selection.tab, view: view, window: window)

        press(.left, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        XCTAssertEqual(selection.tab, "repo", "← must select the previous tab")

        press(.left, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        XCTAssertEqual(selection.tab, "repo", "← at the first tab must not wrap")

        press(.end, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        XCTAssertEqual(selection.tab, "costs", "End must select the last tab")
        try assertSelectedLabelVisible(selection.tab, view: view, window: window)

        press(.right, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        XCTAssertEqual(selection.tab, "costs", "→ at the last tab must not wrap")

        press(.home, in: window)
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        XCTAssertEqual(selection.tab, "repo", "Home must select the first tab")
        try assertSelectedLabelVisible(selection.tab, view: view, window: window)

        // Walk every tab with → so each keyboard selection is proven revealed.
        for expected in DrawerState.tabKeys.dropFirst() {
            press(.right, in: window)
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            XCTAssertEqual(selection.tab, expected)
            try assertSelectedLabelVisible(expected, view: view, window: window)
        }
    }

    // MARK: - Helpers

    private enum Key { case tab, left, right, home, end }

    private func press(_ key: Key, in window: NSWindow) {
        let (code, chars): (UInt16, String) = switch key {
        case .tab: (48, "\t")
        case .left: (123, "\u{F702}")
        case .right: (124, "\u{F703}")
        case .home: (115, "\u{F729}")
        case .end: (119, "\u{F72B}")
        }
        for type in [NSEvent.EventType.keyDown, .keyUp] {
            guard let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: key == .tab ? [] : [.function],
                                               timestamp: ProcessInfo.processInfo.systemUptime,
                                               windowNumber: window.windowNumber, context: nil,
                                               characters: chars, charactersIgnoringModifiers: chars,
                                               isARepeat: false, keyCode: code) else {
                XCTFail("could not synthesize key event"); return
            }
            window.sendEvent(event)
        }
    }

    private func assertSelectedLabelVisible(_ key: String, view: NSView, window: NSWindow,
                                            file: StaticString = #filePath, line: UInt = #line) throws {
        let expected = try XCTUnwrap(DrawerState.tabLabels[key]).uppercased()
        var frames: [CGRect] = []
        func visit(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            if element.responds(to: labelSelector),
               let label = element.perform(labelSelector)?.takeUnretainedValue() as? String,
               label == expected,
               let frame = element.value(forKey: "accessibilityFrame") as? NSValue {
                frames.append(frame.rectValue)
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                children.forEach(visit)
            }
        }
        visit(view)
        XCTAssertFalse(frames.isEmpty, "Selected tab \(key) must be exposed to accessibility", file: file, line: line)
        // Exclude outer padding, the fixed overflow arrows and control gaps.
        let visible = window.convertToScreen(view.convert(view.bounds, to: nil)).insetBy(dx: 8 + 24 + 2, dy: 0)
        for frame in frames {
            XCTAssertGreaterThan(frame.width, 0, file: file, line: line)
            XCTAssertGreaterThanOrEqual(frame.minX, visible.minX - 1, "\(key) clipped left", file: file, line: line)
            XCTAssertLessThanOrEqual(frame.maxX, visible.maxX + 1, "\(key) clipped right", file: file, line: line)
        }
    }
}

@MainActor
@Observable
private final class KeyboardHeaderSelection { var tab = "repo" }

private struct KeyboardMountedHeader: View {
    @Bindable var selection: KeyboardHeaderSelection
    var body: some View {
        DrawerTabStrip(selectedTab: selection.tab, attention: [:], select: { selection.tab = $0 })
    }
}
