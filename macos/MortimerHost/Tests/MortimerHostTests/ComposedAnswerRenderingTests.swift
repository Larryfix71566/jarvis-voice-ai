import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

@MainActor
final class ComposedAnswerRenderingTests: XCTestCase {
    func testOfflineBlocksRenderAtNarrowAndWideWidths() throws {
        _ = NSApplication.shared
        let data = Data(#"""
        {"kind":"markdown","body":"Legacy fallback","answer_id":"11111111-2222-3333-4444-555555555555","answer_revision":1,
         "layout":{"version":1,"revision":1,"template":"comparison","title":"Research","summary":"Summary","complete":false,"blocks":[
         {"id":"heading","type":"header","title":"Research","summary":"Two options compared"},
         {"id":"stats","type":"stats","items":[{"value":"2","label":"Options","tone":"ok"}]},
         {"id":"list","type":"list","title":"Evidence","items":[{"title":"First option","detail":"Long supporting detail remains readable","tone":"approval"}],"more_count":2},
         {"id":"chart","type":"chart","chart":"bar","title":"Comparison","points":[{"label":"A","value":3},{"label":"B","value":-2}],"a11y":"A is 3 and B is negative 2"},
         {"id":"text","type":"text","format":"markdown","text":"**Summary** with supporting prose."},
         {"id":"sources","type":"sources","items":[{"label":"Offline reference"}]},
         {"id":"commands","type":"commands","commands":["printf hello"],"note":"Run only when ready","expect_output":true}
         ]}}
        """#.utf8)
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: data)
        XCTAssertEqual(try XCTUnwrap(payload.layout).blocks.count, 7)
        for width in [480, 1100] {
            let view = NSHostingView(rootView: DisplayContentView(payload: payload)
                .padding(16).background(AppTheme.bg).foregroundStyle(AppTheme.text).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: width, height: 850)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = view
            window.orderFrontRegardless()
            defer { closeRenderingFixtureWindow(window) }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try png.write(to: directory.appendingPathComponent("composed-answer-\(width).png"))
        }
    }
}
