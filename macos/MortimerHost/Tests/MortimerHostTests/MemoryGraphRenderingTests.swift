import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

/// Synthetic native windows only; no live client, databases or graph requests.
@MainActor
final class MemoryGraphRenderingTests: XCTestCase {
    func testGraphLayoutsRenderAtCompactAndWideSizes() async throws {
        _ = NSApplication.shared
        let api = AdminAPI(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        for (count, size) in [(50, CGSize(width: 1280, height: 800)),
                              (200, CGSize(width: 900, height: 600)),
                              (500, CGSize(width: 1440, height: 900))] {
            let store = MemoryGraphStore()
            let graph = try count == 50 ? GraphFixture.clustered() : GraphFixture.make(count: count, edges: count == 500 ? 2000 : count * 2)
            store.load { _ in graph }
            for _ in 0..<600 where store.loading { try await Task.sleep(nanoseconds: 5_000_000) }
            XCTAssertFalse(store.loading)
            XCTAssertNil(store.error)
            let view = NSHostingView(rootView: MemoryGraphView(store: store, api: api)
                .padding(16).background(AppTheme.bg).foregroundStyle(AppTheme.text).preferredColorScheme(.dark))
            view.frame = NSRect(origin: .zero, size: size)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            XCTAssertGreaterThan(bitmap.pixelsWide, 0)
            XCTAssertGreaterThan(bitmap.pixelsHigh, 0)
            let data = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            // Ignored build output, retained for visual review by the verifier.
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(".build/interface-fixtures", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let file = directory.appendingPathComponent("memory-graph-\(count).png")
            try data.write(to: file)
            print("Synthetic graph snapshot: \(file.path)")
        }
    }
}
