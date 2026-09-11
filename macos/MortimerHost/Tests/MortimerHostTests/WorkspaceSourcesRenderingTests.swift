import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

@MainActor
final class WorkspaceSourcesRenderingTests: XCTestCase {
    func testSourceListAndWideInspectorRender() throws {
        _ = NSApplication.shared
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(#"{"title":"Synthetic research comparison","links":[{"label":"Primary documentation with a deliberately long source title","url":"https://example.org/documentation/long-source-path?section=voice-and-display"},{"label":"Supporting evidence","url":"https://example.org/research"},{"label":"Unopenable source stays readable","url":"relative/reference"}]}"#.utf8))
        let result = WorkspaceResult(payload: payload)
        for width in [480, 1100] {
            let presentation = WorkspaceResultPresentation(hasConnections: false)
            presentation.mode = .sources; presentation.selectedSource = 0
            presentation.showsInspector = width > 800
            let view = NSHostingView(rootView: WorkspaceSourcesView(result: result, presentation: presentation)
                .padding(16).background(AppTheme.bg).foregroundStyle(AppTheme.text).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: width, height: 500)
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
            try data.write(to: directory.appendingPathComponent("workspace-sources-\(width).png"))
        }
    }
}
