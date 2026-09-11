import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

@MainActor
final class WorkspaceRenderingTests: XCTestCase {
    func testWorkspaceRendersAtMinimumReadableWidthAndInComparison() throws {
        _ = NSApplication.shared
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        for width in [512, 1100] {
            let workspace = WorkspaceStore()
            for title in ["Research findings", "Comparison evidence"] {
                let json: [String: Any] = ["title": title, "body": "Supplied research text stays readable while Mortimer speaks.\n\nNew results must not replace the selected result or reset its scroll position.",
                                          "links": [["label": "Primary documentation", "url": "https://example.org/source"]]]
                workspace.receive(WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
                    from: JSONSerialization.data(withJSONObject: json))))
            }
            if width > 1000 { workspace.compare(with: workspace.results.last!.id) }
            let view = NSHostingView(rootView: WorkspaceView().environment(workspace)
                .environment(DisplayWindowStore()).environment(DrawerState()).environmentObject(client)
                .foregroundStyle(AppTheme.text).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: width, height: 450)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let data = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try data.write(to: directory.appendingPathComponent("workspace-readable-\(width).png"))
        }
    }
}
