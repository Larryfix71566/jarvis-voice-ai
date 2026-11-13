import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

@MainActor
final class ResultCarouselRenderingTests: XCTestCase {
    private func client() -> JarvisClient {
        JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil))
    }

    private func workspace() throws -> WorkspaceStore {
        let store = WorkspaceStore()
        for (index, title) in ["First neighbour", "Front answer", "Last neighbour"].enumerated() {
            let payload = try JSONDecoder().decode(DisplayPayload.self, from:
                JSONSerialization.data(withJSONObject: ["title": title,
                    "body": "Supplied synthetic evidence for \(title). This card has no network images or external actions."]))
            store.receive(WorkspaceResult(payload: payload, receivedAt: Date(timeIntervalSince1970: Double(index))))
        }
        store.select(store.results[1].id)
        return store
    }

    private func host<V: View>(_ root: V, width: CGFloat = 700, height: CGFloat = 700) -> (NSHostingView<V>, NSWindow) {
        _ = NSApplication.shared
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: width, height: height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        return (view, window)
    }

    private func accessibleText(_ root: Any) -> String {
        var seen = Set<ObjectIdentifier>()
        var text: [String] = []
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            for name in ["accessibilityLabel", "accessibilityValue", "accessibilityTitle"] {
                let selector = NSSelectorFromString(name)
                if object.responds(to: selector), let string = object.perform(selector)?.takeUnretainedValue() as? String {
                    text.append(string)
                }
            }
            let selector = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: selector), let children = object.perform(selector)?.takeUnretainedValue() as? [Any] {
                children.forEach(visit)
            }
        }
        visit(root)
        return text.joined(separator: "\n")
    }

    func testFlatFallbackForEachAccessibilityPreference() {
        XCTAssertFalse(ResultCarouselView.usesFlatPresentation(reduceMotion: false, reduceTransparency: false))
        XCTAssertTrue(ResultCarouselView.usesFlatPresentation(reduceMotion: true, reduceTransparency: false))
        XCTAssertTrue(ResultCarouselView.usesFlatPresentation(reduceMotion: false, reduceTransparency: true))
        XCTAssertTrue(ResultCarouselView.usesFlatPresentation(reduceMotion: true, reduceTransparency: true))
        XCTAssertTrue(ResultCarouselView.usesFlatPresentation(reduceMotion: false, reduceTransparency: false, increasedContrast: true))
    }

    func testAccessibilityExposesOnlyFrontCardAndPagingControls() throws {
        let store = try workspace()
        let (view, window) = host(ResultCarouselView(coordinator: nil)
            .environment(store).environment(ShareCoordinator()).environment(DisplayWindowStore())
            .environment(DrawerState()).environmentObject(client()).preferredColorScheme(.dark))
        defer { closeRenderingFixtureWindow(window) }
        let text = accessibleText(view)
        XCTAssertTrue(text.contains("Results, 2 of 3, Front answer"), text)
        XCTAssertTrue(text.contains("Previous result"), text)
        XCTAssertTrue(text.contains("Next result"), text)
        XCTAssertFalse(text.contains("First neighbour"), "Non-front cards must be hidden from VoiceOver: \(text)")
        XCTAssertFalse(text.contains("Last neighbour"), "Non-front cards must be hidden from VoiceOver: \(text)")
    }

    func testShowAllExposesIdenticalCanonicalInventory() throws {
        let store = try workspace()
        _ = store.pin(store.results[0].id)
        let ids = store.carouselResults.map(\.id)
        let (view, window) = host(ResultAllResultsView(coordinator: nil)
            .environment(store).environment(ShareCoordinator()).environment(DisplayWindowStore())
            .environment(DrawerState()).environmentObject(client()).preferredColorScheme(.dark))
        defer { closeRenderingFixtureWindow(window) }
        let text = accessibleText(view)
        for result in store.carouselResults { XCTAssertTrue(text.contains(ResultCarouselView.title(result)), text) }
        XCTAssertTrue(text.contains("Pinned"), text)
        XCTAssertEqual(store.carouselResults.map(\.id), ids, "Showing B must not reorder or create results")
    }

    private func nativeScroll(_ view: NSView) -> NSScrollView? {
        if let scroll = view as? NSScrollView { return scroll }
        return view.subviews.lazy.compactMap { self.nativeScroll($0) }.first
    }

    func testFrontRevisionPreservesNativeReaderAndKeyboardFocus() throws {
        let store = WorkspaceStore()
        let text = (0..<100).map { "Evidence line \($0), stable supplied content." }.joined(separator: "\n\n")
        func payload(_ revision: Int) throws -> DisplayPayload {
            var raw: [String: Any] = ["kind": "markdown", "title": "Stable", "body": text,
                "answer_id": "11111111-2222-3333-4444-555555555555", "answer_revision": revision]
            if revision == 1 { raw["layout"] = ["version": 1, "revision": 1, "template": "text",
                "title": "Stable", "summary": "Summary", "complete": false,
                "blocks": [["id": "text", "type": "text", "format": "plain", "text": text]]] }
            return try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: raw))
        }
        let first = WorkspaceResult(payload: try payload(1)); store.receive(first); store.select(first.id)
        let (view, window) = host(ResultCarouselView(coordinator: nil)
            .environment(store).environment(ShareCoordinator()).environment(DisplayWindowStore())
            .environment(DrawerState()).environmentObject(client()).environment(\.mortimerReduceMotion, true))
        defer { closeRenderingFixtureWindow(window) }
        let before = try XCTUnwrap(nativeScroll(view))
        before.contentView.scroll(to: NSPoint(x: 0, y: 180)); before.reflectScrolledClipView(before.contentView)
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        let offset = before.contentView.bounds.origin.y
        XCTAssertGreaterThan(offset, 100)
        window.makeFirstResponder(view)
        let responder = window.firstResponder
        XCTAssertTrue(try XCTUnwrap(store.applyAnswerRevision(payload(2))).applied)
        view.layoutSubtreeIfNeeded(); RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        let after = try XCTUnwrap(nativeScroll(view))
        XCTAssertEqual(store.carouselFrontResult?.id, first.id)
        XCTAssertEqual(after.contentView.bounds.origin.y, offset, accuracy: 2, "Layout fallback must retain the actual reader position")
        XCTAssertTrue(window.firstResponder === responder, "Revision must not steal keyboard focus")
    }

    func testIntegratedCompactStageRendersThreadAndCarouselAboveUnchangedVoiceSlot() throws {
        let store = try workspace()
        let (view, window) = host(AdaptiveStageView(voiceState: .offline, wideWindow: false)
            .environment(store).environment(ConversationStore()).environment(AgentRunStore())
            .environment(ConsoleNoticeState()).environment(DisplayResultStore())
            .environment(ShareCoordinator()).environment(DisplayWindowStore()).environment(DrawerState())
            .environmentObject(client()).environment(\.mortimerReduceMotion, true)
            .foregroundStyle(AppTheme.text).background(AppTheme.bg).preferredColorScheme(.dark), width: 720, height: 720)
        defer { closeRenderingFixtureWindow(window) }
        XCTAssertTrue(accessibleText(view).contains("Front answer"))
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try png.write(to: directory.appendingPathComponent("carousel-integrated-compact-720.png"))
    }

    func testOfflineCarouselRendersAtNarrowAndWideWidthsWithFlatFallbacks() throws {
        for (width, motion, transparency) in [(480, false, false), (1100, false, false),
                                               (480, true, false), (480, false, true)] {
            let store = try workspace()
            let (view, window) = host(ResultCarouselView(coordinator: nil, reduceTransparencyOverride: transparency)
                .environment(store).environment(ShareCoordinator()).environment(DisplayWindowStore())
                .environment(DrawerState()).environmentObject(client())
                .environment(\.mortimerReduceMotion, motion)
                .foregroundStyle(AppTheme.text).background(AppTheme.panelSolid).preferredColorScheme(.dark), width: CGFloat(width))
            defer { closeRenderingFixtureWindow(window) }
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try png.write(to: directory.appendingPathComponent("carousel-\(width)-motion-\(motion)-transparency-\(transparency).png"))
        }
    }
}
