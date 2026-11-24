import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

@MainActor
final class OrbGlassCardTests: XCTestCase {
    typealias Policy = OrbGlassCardPolicy

    func testTreatmentForEveryAccessibilityCombination() {
        for lit in [true, false] {
            for glass in [true, false] {
                for rt in [true, false] {
                    for hc in [true, false] {
                        let got = Policy.treatment(lit: lit, glassEnabled: glass,
                                                   reduceTransparency: rt, increasedContrast: hc)
                        let want: Policy.Treatment = (!glass || rt || hc) ? .opaque : (lit ? .litCrystal : .unlitCrystal)
                        XCTAssertEqual(got, want, "lit \(lit) glass \(glass) rt \(rt) hc \(hc)")
                    }
                }
            }
        }
    }

    func testGlowModeForEveryCombination() {
        for lit in [true, false] {
            for glass in [true, false] {
                for rt in [true, false] {
                    for hc in [true, false] {
                        for rm in [true, false] {
                            for suppressed in [true, false] {
                                for follow in [true, false] {
                                    let got = Policy.glow(lit: lit, glassEnabled: glass, reduceTransparency: rt,
                                                          increasedContrast: hc, reduceMotion: rm, suppressed: suppressed,
                                                          followGlow: follow)
                                    let crystal = glass && !rt && !hc
                                    let want: Policy.GlowMode = (!lit || !crystal || suppressed) ? .off
                                        : (rm ? .staticEven : (follow ? .tracking : .off))
                                    XCTAssertEqual(got, want,
                                        "lit \(lit) glass \(glass) rt \(rt) hc \(hc) rm \(rm) suppressed \(suppressed) follow \(follow)")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    func testFocusSnapsToTheNearestEdge() throws {
        let size = CGSize(width: 400, height: 200)
        func focus(_ x: CGFloat, _ y: CGFloat) throws -> UnitPoint {
            try XCTUnwrap(RimGlow.focus(pointer: CGPoint(x: x, y: y), in: size))
        }
        var p = try focus(200, 10)
        XCTAssertEqual(p.x, 0.5, accuracy: 1e-9); XCTAssertEqual(p.y, 0, accuracy: 1e-9)
        p = try focus(200, 190)
        XCTAssertEqual(p.x, 0.5, accuracy: 1e-9); XCTAssertEqual(p.y, 1, accuracy: 1e-9)
        p = try focus(10, 100)
        XCTAssertEqual(p.x, 0, accuracy: 1e-9); XCTAssertEqual(p.y, 0.5, accuracy: 1e-9)
        p = try focus(390, 100)
        XCTAssertEqual(p.x, 1, accuracy: 1e-9); XCTAssertEqual(p.y, 0.5, accuracy: 1e-9)
        // Centre: top and bottom tie at 100 pt; the top edge wins.
        p = try focus(200, 100)
        XCTAssertEqual(p.x, 0.5, accuracy: 1e-9); XCTAssertEqual(p.y, 0, accuracy: 1e-9)
        // Corners stay off the arc: 12 pt in along the edge.
        p = try focus(1, 1)
        XCTAssertEqual(p.x, 12.0 / 400, accuracy: 1e-9); XCTAssertEqual(p.y, 0, accuracy: 1e-9)
        p = try focus(399, 199)
        XCTAssertEqual(p.x, 388.0 / 400, accuracy: 1e-9); XCTAssertEqual(p.y, 1, accuracy: 1e-9)
    }

    func testFocusIsNilOutsideOrEmpty() {
        let size = CGSize(width: 400, height: 200)
        XCTAssertNil(RimGlow.focus(pointer: CGPoint(x: -1, y: 50), in: size))
        XCTAssertNil(RimGlow.focus(pointer: CGPoint(x: 401, y: 50), in: size))
        XCTAssertNil(RimGlow.focus(pointer: CGPoint(x: 50, y: -0.5), in: size))
        XCTAssertNil(RimGlow.focus(pointer: CGPoint(x: 50, y: 201), in: size))
        XCTAssertNil(RimGlow.focus(pointer: CGPoint(x: 0, y: 0), in: .zero))
    }

    func testMockupConstants() {
        XCTAssertEqual(OrbGlassCardStyle.tintOpacity, 0.44)
        XCTAssertEqual(OrbGlassCardStyle.cornerRadius, 12)
        XCTAssertEqual(RimGlow.rimRadius, 210)
        XCTAssertEqual(RimGlow.fade, 0.18)
        XCTAssertEqual(RimGlow.rimStops.map(\.opacity), [1, 0.34, 0.12])
    }

    func testFollowGlowIsOffUnlessTurnedOn() throws {
        let key = OrbGlassCardSettings.followGlowKey
        guard ProcessInfo.processInfo.environment[key] == nil else {
            throw XCTSkip("\(key) is set in this test environment")
        }
        let saved = UserDefaults.standard.object(forKey: key)
        defer { UserDefaults.standard.set(saved, forKey: key) }
        UserDefaults.standard.removeObject(forKey: key)
        XCTAssertFalse(OrbGlassCardSettings.followGlowEnabled)
        UserDefaults.standard.set(true, forKey: key)
        XCTAssertTrue(OrbGlassCardSettings.followGlowEnabled)
    }

    func testPointerModelKeepsLastLocationOnExit() {
        let model = RimGlowPointer()
        model.update(CGPoint(x: 5, y: 6))
        XCTAssertTrue(model.hovering)
        model.update(nil)
        XCTAssertFalse(model.hovering)
        XCTAssertEqual(model.location, CGPoint(x: 5, y: 6))
    }

    // MARK: render smoke

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

    private func renderCarousel(width: CGFloat, reduceTransparency: Bool?) throws {
        _ = NSApplication.shared
        let store = try workspace()
        let root = ResultCarouselView(coordinator: nil, reduceTransparencyOverride: reduceTransparency)
            .environment(store).environment(ShareCoordinator()).environment(DisplayWindowStore())
            .environment(DrawerState()).environmentObject(client()).preferredColorScheme(.dark)
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: width, height: 700)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        defer { closeRenderingFixtureWindow(window) }
        XCTAssertGreaterThan(view.fittingSize.width, 0)
        let text = accessibleText(view)
        XCTAssertTrue(text.contains("Results, 2 of 3, Front answer"), text)
        XCTAssertFalse(text.contains("First neighbour"), text)
        XCTAssertFalse(text.contains("Last neighbour"), text)
    }

    func testLitCarouselLaysOutAtBothWidths() throws {
        try renderCarousel(width: 700, reduceTransparency: false)
        try renderCarousel(width: 1000, reduceTransparency: false)
    }

    func testFlatCarouselLaysOutAtBothWidths() throws {
        try renderCarousel(width: 700, reduceTransparency: true)
        try renderCarousel(width: 1000, reduceTransparency: true)
    }
}
