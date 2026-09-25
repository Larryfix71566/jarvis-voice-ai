import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

/// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md §7. Expected numbers come
/// from the approved preview (docs/interface-research/orb-crystal/), measured
/// 2026-09-23 at 400 × 180 pt on black: the key-window reflection covers
/// 70–79 pt² of the reflection band at ≥ 0.6 brightness in every voice
/// state, the legacy shell covers 0 pt², and pixels farther than
/// 1.25 × radius from the center are identical between the two shells.
@MainActor
final class CrystalOrbShellTests: XCTestCase {
    private static let width = 400.0, height = 180.0
    /// CometOrbRenderer: extent = min(height, 2 * min(cx, width - cx)) = 180, radius = 0.255 * extent.
    private static var radius: Double { min(height, 2 * min(width / 2, width / 2)) * 0.255 }

    private func render(_ activity: VoicePresentationState.Activity, userEnergy: Double = 0,
                        outputEnergy: Double = 0, phase: Double = 1.3,
                        shell: OrbShell) throws -> NSBitmapImageRep {
        let view = NSHostingView(rootView: Canvas { context, size in
            CometOrbRenderer.draw(context: &context, size: size, stageCenterX: nil, phase: phase,
                                  userEnergy: userEnergy, outputEnergy: outputEnergy,
                                  activity: activity, shell: shell)
        }.background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: Self.width, height: Self.height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        return bitmap
    }

    /// Visits every pixel with its distance from the sphere center in units
    /// of the radius. Orientation-independent, so bitmap row order cannot
    /// change the answer.
    private func forEachPixel(_ bitmap: NSBitmapImageRep,
                              _ body: (_ x: Int, _ y: Int, _ rho: Double, _ rgb: (Double, Double, Double)) -> Void) {
        let scale = Double(bitmap.pixelsWide) / Self.width
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                guard let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                let dx = (Double(x) + 0.5) / scale - Self.width / 2
                let dy = (Double(y) + 0.5) / scale - Self.height / 2
                body(x, y, (dx * dx + dy * dy).squareRoot() / Self.radius,
                     (Double(c.redComponent), Double(c.greenComponent), Double(c.blueComponent)))
            }
        }
    }

    /// Area (pt²) of the 0.55–0.95 radius band where every channel is ≥ 0.6.
    /// The window reflection lives in this band; plasma and comets do not
    /// reach this brightness there.
    private func reflectionArea(_ bitmap: NSBitmapImageRep) -> Double {
        let scale = Double(bitmap.pixelsWide) / Self.width
        var count = 0
        forEachPixel(bitmap) { _, _, rho, rgb in
            if rho >= 0.55, rho <= 0.95, min(rgb.0, rgb.1, rgb.2) >= 0.6 { count += 1 }
        }
        return Double(count) / (scale * scale)
    }

    // MARK: - Geometry (pure)

    func testMirrorPointIsTheHalfVector() {
        let straight = CrystalGlassRig.mirrorPoint(SIMD3<Double>(0, 0, 1))
        XCTAssertEqual(Double(straight.x), 0, accuracy: 1e-12)
        XCTAssertEqual(Double(straight.y), 0, accuracy: 1e-12)
        let side = CrystalGlassRig.mirrorPoint(SIMD3<Double>(1, 0, 0))
        XCTAssertEqual(Double(side.x), 1 / 2.0.squareRoot(), accuracy: 1e-12)
        XCTAssertEqual(Double(side.y), 0, accuracy: 1e-12)
    }

    func testTheKeyWindowSitsUpperLeftNearTheRim() {
        let panes = CrystalGlassRig.keyPanes
        XCTAssertEqual(panes.count, 2)
        XCTAssertEqual(Double(panes[0].mid.x), -0.5635384769511677, accuracy: 1e-9)
        XCTAssertEqual(Double(panes[0].mid.y), -0.5472685979705555, accuracy: 1e-9)
        XCTAssertEqual(Double(panes[1].mid.x), -0.509180915952978, accuracy: 1e-9)
        XCTAssertEqual(Double(panes[1].mid.y), -0.46948308141197354, accuracy: 1e-9)
        for pane in panes {
            XCTAssertEqual(pane.points.count, CrystalGlassRig.outlineSamples)
            for point in pane.points {
                XCTAssertLessThan(point.x, 0, "the key window must stay left of center")
                XCTAssertLessThan(point.y, 0, "the key window must stay above center")
                let rho = Double(hypot(point.x, point.y))
                XCTAssertGreaterThan(rho, 0.64); XCTAssertLessThan(rho, 0.83)
            }
        }
        XCTAssertEqual(Double(CrystalGlassRig.strip.mid.x), 0.684478514101287, accuracy: 1e-9)
        XCTAssertEqual(Double(CrystalGlassRig.strip.mid.y), 0.4277990713133043, accuracy: 1e-9)
    }

    func testFresnelStopsFollowSchlickForGlass() {
        let stops = CrystalGlassRig.fresnelStops
        XCTAssertEqual(stops.count, 16)
        XCTAssertEqual(stops.first!.location, 0); XCTAssertEqual(stops.first!.reflectance, 0.04, accuracy: 1e-12)
        XCTAssertEqual(stops.last!.location, 1); XCTAssertEqual(stops.last!.reflectance, 1.0, accuracy: 1e-12)
        XCTAssertEqual(CrystalGlassRig.schlick(0.992), 0.5289194569651289, accuracy: 1e-9)
        for (a, b) in zip(stops, stops.dropFirst()) {
            XCTAssertLessThan(a.location, b.location)
            XCTAssertLessThanOrEqual(a.reflectance, b.reflectance)
        }
    }

    func testTheShellDefaultsToCrystal() {
        // The test process has neither JARVIS_ORB_CRYSTAL in its environment
        // nor the key in its own defaults domain (not com.mortimer.host).
        XCTAssertEqual(OrbShell.resolved, .crystal)
    }

    // MARK: - Rendering

    /// The defect this plan fixes, stated as a test: the legacy glass all but
    /// vanishes in standby; the crystal glass keeps its window reflection.
    func testCrystalKeepsItsReflectionsInStandby() throws {
        let legacy = reflectionArea(try render(.offline, shell: .legacy))
        let crystal = reflectionArea(try render(.offline, shell: .crystal))
        XCTAssertEqual(legacy, 0, "legacy standby had no bright reflection in the preview")
        XCTAssertGreaterThanOrEqual(crystal, 35, "half of the preview's 70 pt² window reflection")
    }

    /// Reflections belong to the room, not to the voice state.
    func testCrystalReflectionsDoNotFollowVoiceState() throws {
        let standby = reflectionArea(try render(.offline, shell: .crystal))
        let cases: [(VoicePresentationState.Activity, Double, Double)] = [
            (.listening, 0, 0), (.user, 0.385, 0), (.assistant, 0, 0.294), (.user, 0.385, 0.294),
        ]
        for (activity, user, output) in cases {
            let area = reflectionArea(try render(activity, userEnergy: user, outputEnergy: output, shell: .crystal))
            XCTAssertEqual(area, standby, accuracy: standby * 0.15,
                           "\(activity) changed the reflection area (\(area) vs standby \(standby) pt²)")
        }
    }

    /// Plasma, comets and colors are outside the plan's scope. Beyond
    /// 1.25 × radius only the comets draw, so both shells must match there
    /// pixel for pixel, and the nucleus must keep its color.
    func testCometsAndNucleusAreUnchanged() throws {
        let cases: [(VoicePresentationState.Activity, Double, Double)] = [
            (.listening, 0, 0), (.user, 0.385, 0), (.assistant, 0, 0.294), (.user, 0.385, 0.294),
        ]
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for (activity, user, output) in cases {
            let legacy = try render(activity, userEnergy: user, outputEnergy: output, shell: .legacy)
            let crystal = try render(activity, userEnergy: user, outputEnergy: output, shell: .crystal)
            XCTAssertEqual(legacy.pixelsWide, crystal.pixelsWide)
            var outside = 0, differing = 0
            forEachPixel(legacy) { x, y, rho, a in
                guard rho > 1.25, let c = crystal.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { return }
                outside += 1
                let d = max(abs(a.0 - Double(c.redComponent)), abs(a.1 - Double(c.greenComponent)),
                            abs(a.2 - Double(c.blueComponent)))
                if d > 2.0 / 255 { differing += 1 }
            }
            XCTAssertGreaterThan(outside, 10_000)
            XCTAssertEqual(differing, 0, "\(activity): comets changed outside the glass")
            let cx = legacy.pixelsWide / 2, cy = legacy.pixelsHigh / 2
            let a = try XCTUnwrap(legacy.colorAt(x: cx, y: cy)?.usingColorSpace(.deviceRGB))
            let b = try XCTUnwrap(crystal.colorAt(x: cx, y: cy)?.usingColorSpace(.deviceRGB))
            XCTAssertEqual(Double(a.redComponent), Double(b.redComponent), accuracy: 0.06)
            XCTAssertEqual(Double(a.greenComponent), Double(b.greenComponent), accuracy: 0.06)
            XCTAssertEqual(Double(a.blueComponent), Double(b.blueComponent), accuracy: 0.06)
        }
        // Side-by-side fixtures for Larry's visual acceptance (§7 step V).
        let names: [(String, VoicePresentationState.Activity, Double, Double)] = [
            ("standby", .offline, 0, 0), ("idle", .listening, 0, 0), ("user", .user, 0.385, 0),
            ("mortimer", .assistant, 0, 0.294), ("overlap", .user, 0.385, 0.294),
        ]
        for (name, activity, user, output) in names {
            for shell in [OrbShell.legacy, .crystal] {
                let bitmap = try render(activity, userEnergy: user, outputEnergy: output, shell: shell)
                try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
                    .write(to: directory.appendingPathComponent("orb-\(shell == .crystal ? "crystal" : "legacy")-\(name).png"))
            }
        }
    }
}
