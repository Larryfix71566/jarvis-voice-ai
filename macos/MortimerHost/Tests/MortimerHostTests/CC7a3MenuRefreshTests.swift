import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Actual AppKit menu rows, not a second rendering of WorkspaceRecents.listing.
/// Reproduced on the Mac: button Results · 2, two store entries, one menu row.
@MainActor
final class CC7a3MenuRefreshTests: XCTestCase {
    private final class Capture {
        var menu: NSMenu?
        var rows: [String] = []
    }

    private func result(_ title: String) throws -> WorkspaceResult {
        WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
            from: JSONSerialization.data(withJSONObject: ["kind": "weather", "title": title,
                                                          "body": "Synthetic weather", "surface": "window"])))
    }

    private func resultsControl(in node: NSView) -> NSSegmentedControl? {
        if let control = node as? NSSegmentedControl,
           control.label(forSegment: 0)?.hasPrefix("Results") == true { return control }
        return node.subviews.lazy.compactMap { self.resultsControl(in: $0) }.first
    }

    private func renderedRows(in control: NSSegmentedControl) throws -> [String] {
        let capture = Capture()
        let observer = NotificationCenter.default.addObserver(forName: NSMenu.didBeginTrackingNotification,
                                                              object: nil, queue: .main) { note in
            MainActor.assumeIsolated { capture.menu = note.object as? NSMenu }
        }
        defer { NotificationCenter.default.removeObserver(observer) }
        // didBeginTracking fires BEFORE SwiftUI populates the menu. Inspect
        // while it is tracking; a pre-opening snapshot reads the prior menu.
        let timer = Timer(timeInterval: 0.15, repeats: true) { _ in
            MainActor.assumeIsolated {
                guard let menu = capture.menu else { return }
                capture.rows = menu.items.map(\.title)
                menu.cancelTracking()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        defer { timer.invalidate() }
        control.selectedSegment = 1
        control.performClick(nil)
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        XCTAssertNotNil(capture.menu, "The actual menu must open; no listing-only fallback")
        return capture.rows
    }

    func testActualMenuUpdatesAfterSecondArrivalAndPinAndClose() throws {
        _ = NSApplication.shared
        let workspace = WorkspaceStore()
        let beach = try result("Weather · Folly Beach"), atlanta = try result("Weather · Atlanta")
        workspace.receive(beach)
        let view = NSHostingView(rootView: ConsoleActionBar(coordinator: nil)
            .environment(workspace).environment(DisplayWindowStore())
            .environment(ShareCoordinator()).environment(ConsoleNoticeState())
            .environment(DrawerState()))
        view.frame = NSRect(x: 0, y: 0, width: 1200, height: 100)
        let window = NSWindow(contentRect: view.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        func settle() {
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.15))
        }
        settle()
        var control = try XCTUnwrap(resultsControl(in: view))
        var rows = try renderedRows(in: control)
        XCTAssertTrue(rows.contains { $0.hasPrefix("1  ") && $0.contains("Folly Beach") }, "\(rows)")

        workspace.receive(atlanta)
        settle()
        XCTAssertEqual(workspace.results.count, 2)
        XCTAssertEqual(workspace.recents.entries.map(\.id), [atlanta.id, beach.id])
        control = try XCTUnwrap(resultsControl(in: view))
        XCTAssertEqual(control.label(forSegment: 0), "Results · 2")
        rows = try renderedRows(in: control)
        XCTAssertTrue(rows.contains { $0.hasPrefix("1  ") && $0.contains("Atlanta") }, "\(rows)")
        XCTAssertTrue(rows.contains { $0.hasPrefix("2  ") && $0.contains("Folly Beach") }, "\(rows)")

        XCTAssertTrue(workspace.pin(beach.id))
        settle()
        rows = try renderedRows(in: XCTUnwrap(resultsControl(in: view)))
        XCTAssertTrue(rows.contains("Pinned"), "\(rows)")
        XCTAssertTrue(rows.contains { $0.hasPrefix("1  ") && $0.contains("Folly Beach") }, "\(rows)")
        XCTAssertTrue(rows.contains { $0.hasPrefix("2  ") && $0.contains("Atlanta") }, "\(rows)")

        workspace.close(atlanta.id)
        settle()
        rows = try renderedRows(in: XCTUnwrap(resultsControl(in: view)))
        XCTAssertFalse(rows.contains { $0.contains("Atlanta") }, "\(rows)")
        XCTAssertEqual(workspace.results.map(\.id), [beach.id])
    }
}
