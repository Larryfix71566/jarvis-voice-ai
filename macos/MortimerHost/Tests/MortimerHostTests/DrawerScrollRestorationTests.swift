import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

@MainActor
private final class ScrollProbe { var offset = -1.0 }

@MainActor
private struct ScrollFixture: View {
    let probe: ScrollProbe
    var body: some View {
        ScrollView {
            VStack {
                ForEach(0..<100) { row in Text("Synthetic row \(row)").frame(height: 30) }
            }.frame(maxWidth: .infinity)
        }
        .preserveDrawerScroll("edit")
        .onScrollGeometryChange(for: Double.self) {
            Double($0.contentOffset.y + $0.contentInsets.top)
        } action: { _, offset in probe.offset = offset }
    }
}

@MainActor
final class DrawerScrollRestorationTests: XCTestCase {
    func testScrollRestoresIntoReplacementNativeWindow() async throws {
        _ = NSApplication.shared
        let models = DrawerModels()
        models.scrollOffsets["edit"] = 500
        func window(_ probe: ScrollProbe) -> NSWindow {
            let view = NSHostingView(rootView: ScrollFixture(probe: probe).environment(models))
            view.frame = NSRect(x: 0, y: 0, width: 400, height: 350)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view
            window.orderFrontRegardless(); window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            return window
        }
        func waitForRestore(_ probe: ScrollProbe) async throws {
            for _ in 0..<200 {
                if abs(probe.offset - 500) <= 2 { break }
                try await Task.sleep(nanoseconds: 5_000_000)
            }
            XCTAssertEqual(probe.offset, 500, accuracy: 2)
        }
        let firstProbe = ScrollProbe(), first = window(firstProbe)
        try await waitForRestore(firstProbe)
        first.close()
        let secondProbe = ScrollProbe(), replacement = window(secondProbe)
        defer { replacement.close() }
        try await waitForRestore(secondProbe)
        XCTAssertEqual(models.scrollOffsets["edit"] ?? -1, 500, accuracy: 2)
    }
}
