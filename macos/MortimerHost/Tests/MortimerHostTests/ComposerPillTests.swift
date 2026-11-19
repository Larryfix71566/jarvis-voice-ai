import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Interface cleanup Phase 2, slice A: one composer pill and window drop.
@MainActor
final class ComposerPillTests: XCTestCase {
    private static let png1x1 = Data(base64Encoded:
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")!

    private func client() -> JarvisClient {
        JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
    }

    private func host<V: View>(_ root: V, width: CGFloat, height: CGFloat) -> (NSHostingView<V>, NSWindow) {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: width, height: height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        return (view, window)
    }

    private func accessibleText(_ root: Any) -> [String] {
        var seen = Set<ObjectIdentifier>()
        var text: [String] = []
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            for name in ["accessibilityLabel", "accessibilityValue", "accessibilityTitle"] {
                let selector = NSSelectorFromString(name)
                guard object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue() else { continue }
                let string = (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
                if !string.isEmpty { text.append(string) }
            }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(root)
        return text
    }

    private func textItem(_ text: String) -> SharedContentTransfer {
        SharedContentTransfer(kind: .text, mimeType: "text/plain",
                              digest: String(repeating: "b", count: 64), payload: Data(text.utf8))
    }

    private func pill(store: AttachmentStore, composer: TypedComposerModel) -> some View {
        ComposerPillView(onAsk: {}, onApproveOffer: {}, onDeclineOffer: {})
            .environment(store).environment(composer).environmentObject(client())
            .frame(width: 600).preferredColorScheme(.dark)
    }

    // MARK: Pure

    func testNormalizeTextAndPng() throws {
        let text = try XCTUnwrap(AttachmentIntake.normalize(data: Data("hello".utf8), typeIdentifier: "public.plain-text"))
        XCTAssertEqual(text.kind, .text)
        let image = try XCTUnwrap(AttachmentIntake.normalize(data: Self.png1x1, typeIdentifier: "public.png"))
        XCTAssertEqual(image.kind, .image)
        XCTAssertNil(AttachmentIntake.normalize(data: Data([1, 2]), typeIdentifier: "public.data"))
    }

    func testDropZoneShowsOnlyWhileTargeted() {
        XCTAssertFalse(WindowDropOverlay.showsZone(isTargeted: false))
        XCTAssertTrue(WindowDropOverlay.showsZone(isTargeted: true))
    }

    func testAskStaysDisabledUntilApprovedWithAQuestion() {
        XCTAssertTrue(StagedContentPanel.askDisabled(hasAction: true, approvedCount: 0, question: "why"))
        XCTAssertTrue(StagedContentPanel.askDisabled(hasAction: true, approvedCount: 1, question: "  "))
        XCTAssertTrue(StagedContentPanel.askDisabled(hasAction: false, approvedCount: 1, question: "why"))
        XCTAssertFalse(StagedContentPanel.askDisabled(hasAction: true, approvedCount: 1, question: "why"))
    }

    // MARK: Rendered

    func testRestingPillExposesOnlyTheThreeControls() {
        let (view, window) = host(pill(store: AttachmentStore(), composer: TypedComposerModel()), width: 600, height: 200)
        defer { closeRenderingFixtureWindow(window) }
        let text = accessibleText(view)
        for kept in ["Attach content", "Type a request", "Send request"] {
            XCTAssertTrue(text.contains(kept), "pill lost \(kept): \(text)")
        }
        for gone in ["Drop text or image files here", "Add content", "Staged content"] {
            XCTAssertFalse(text.contains(gone), "resting pill shows \(gone): \(text)")
        }
    }

    func testStagedItemOpensReviewPanelWithAskDisabledUntilApproved() {
        let store = AttachmentStore()
        store.stage(textItem("synthetic"))
        let (view, window) = host(pill(store: store, composer: TypedComposerModel()), width: 600, height: 400)
        defer { closeRenderingFixtureWindow(window) }
        let text = accessibleText(view)
        XCTAssertTrue(text.contains("Staged content"), "\(text)")
        XCTAssertTrue(text.contains("Ask Mortimer"), "\(text)")
        XCTAssertTrue(text.contains("Approve"), "\(text)")
        XCTAssertTrue(StagedContentPanel.askDisabled(hasAction: true, approvedCount: store.approvedIDs.count,
                                                     question: store.question))
    }
}
