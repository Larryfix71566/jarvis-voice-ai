import XCTest
import AppKit
import SwiftUI
import QuartzCore
import Observation
@testable import MortimerHost

/// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D6. Measures the crystal
/// shell against the legacy shell and an empty canvas with the per-frame span
/// MemoryGraphFrameTimeTests uses: from the state change until the render
/// server runs the completion block of the Core Animation transaction that
/// carried it. Canvas 1440 × 220 pt, the widest the conversation layout gives
/// the voice region (AdaptiveStageView conversation mode: maxHeight 220 at
/// full workspace width). Blurred layers can be as large as the canvas, so
/// the widest canvas is the one to measure.
/// Writes orb-frame-time.json into .build/interface-fixtures/ under the test
/// process's working directory, next to VoiceWaveRenderingTests' fixtures.
/// Gates: legacy p50 > 1.10 × empty p50 (the span sees drawing cost);
/// crystal p95 ≤ 16.7 ms (one 60 Hz frame); crystal p50 ≤ 1.5 × legacy p50.
/// Needs a logged-in graphical session, like MemoryGraphFrameTimeTests.
@MainActor
final class OrbShellFrameTimeTests: XCTestCase {
    @MainActor @Observable
    final class PhaseModel {
        var phase = 0.0
    }

    enum Probe {
        case empty
        case shell(OrbShell)
    }

    struct ProbeView: View {
        let model: PhaseModel
        let probe: Probe
        var body: some View {
            // Read in body so each phase change re-renders the Canvas.
            let phase = model.phase
            Canvas { context, size in
                guard case .shell(let shell) = probe else { return }
                CometOrbRenderer.draw(context: &context, size: size, stageCenterX: nil, phase: phase,
                                      userEnergy: 0.2, outputEnergy: 0.35, activity: .assistant,
                                      shell: shell)
            }
            .background(Color.black)
        }
    }

    @MainActor
    private final class Harness {
        static let size = CGSize(width: 1440, height: 220)
        final class Presented { var at: Double? }
        let model: PhaseModel
        let window: NSWindow
        var completions = 0

        init(probe: Probe) {
            let model = PhaseModel()
            let hosted = NSHostingView(rootView: ProbeView(model: model, probe: probe)
                .frame(width: Harness.size.width, height: Harness.size.height))
            hosted.frame = NSRect(origin: .zero, size: Harness.size)
            let window = NSWindow(contentRect: hosted.frame, styleMask: [.borderless],
                                  backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = hosted
            window.orderFrontRegardless()
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            self.model = model
            self.window = window
        }

        func close() { window.close() }

        /// One frame: phase change → render server completion, in ms.
        func step(_ phase: Double) -> Double {
            let mark = Presented()
            let start = CACurrentMediaTime()
            CATransaction.begin()
            CATransaction.setCompletionBlock { mark.at = CACurrentMediaTime() }
            model.phase = phase
            RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.0005))
            CATransaction.commit()
            CATransaction.flush()
            let deadline = Date(timeIntervalSinceNow: 0.5)
            while mark.at == nil, Date() < deadline {
                RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.0005))
            }
            if mark.at != nil { completions += 1 }
            return ((mark.at ?? CACurrentMediaTime()) - start) * 1000
        }

        /// 10 warm-up frames (not recorded), then `frames` recorded frames,
        /// advancing 0.025 rad per frame (1.5 rad/s at 60 Hz, the fastest
        /// AtomMotion travels).
        func run(frames: Int) -> [Double] {
            for index in 0..<10 { _ = step(Double(index) * 0.025) }
            return (0..<frames).map { step(0.25 + Double($0) * 0.025) }
        }
    }

    private func percentile(_ values: [Double], _ p: Double) -> Double {
        let s = values.sorted()
        return s[min(s.count - 1, max(0, Int((Double(s.count) * p).rounded(.up)) - 1))]
    }

    private func ms(_ value: Double) -> Double { (value * 1000).rounded() / 1000 }

    // Synchronous on purpose, as in MemoryGraphFrameTimeTests: Core
    // Animation completion blocks must drain on the main run loop.
    func testCrystalShellStaysWithinTheFrameBudget() throws {
        _ = NSApplication.shared
        func measure(_ probe: Probe) -> (frames: [Double], completions: Int) {
            let harness = Harness(probe: probe)
            defer { harness.close() }
            let frames = harness.run(frames: 300)
            return (frames, harness.completions)
        }
        let empty = measure(.empty)
        let legacy = measure(.shell(.legacy))
        let crystal = measure(.shell(.crystal))
        for (name, result) in [("empty", empty), ("legacy", legacy), ("crystal", crystal)] {
            XCTAssertEqual(result.completions, 310, "\(name): every frame must reach the render server")
        }
        func summary(_ frames: [Double]) -> [String: Double] {
            ["p50_ms": ms(percentile(frames, 0.5)), "p95_ms": ms(percentile(frames, 0.95)),
             "max_ms": ms(frames.max() ?? 0)]
        }
        let emptyP50 = percentile(empty.frames, 0.5)
        let legacyP50 = percentile(legacy.frames, 0.5)
        let crystalP50 = percentile(crystal.frames, 0.5)
        let crystalP95 = percentile(crystal.frames, 0.95)
        let record: [String: Any] = [
            "gates": [
                "sensitivity": ["rule": "legacy p50 > 1.10 × empty p50", "passed": legacyP50 > emptyP50 * 1.10],
                "budget": ["rule": "crystal p95 ≤ 16.7 ms", "passed": crystalP95 <= 16.7],
                "relative": ["rule": "crystal p50 ≤ 1.5 × legacy p50", "passed": crystalP50 <= legacyP50 * 1.5],
            ],
            "empty": summary(empty.frames), "legacy": summary(legacy.frames), "crystal": summary(crystal.frames),
            "frames_per_probe": 300,
            "canvas_pt": ["width": Double(Harness.size.width), "height": Double(Harness.size.height)],
            "state": ["activity": "assistant", "user_energy": 0.2, "output_energy": 0.35, "phase_step_rad": 0.025],
            "hardware": ["model": sysctl("hw.model"), "cpu": sysctl("machdep.cpu.brand_string"),
                         "os": ProcessInfo.processInfo.operatingSystemVersionString,
                         "main_screen_scale": Double(NSScreen.main?.backingScaleFactor ?? 0)],
            "recorded_at": ISO8601DateFormatter().string(from: Date()),
            "test": "OrbShellFrameTimeTests.testCrystalShellStaysWithinTheFrameBudget",
        ]
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
            .write(to: directory.appendingPathComponent("orb-frame-time.json"))
        print("Orb frame time p50/p95: empty \(ms(emptyP50))/\(ms(percentile(empty.frames, 0.95))), legacy \(ms(legacyP50))/\(ms(percentile(legacy.frames, 0.95))), crystal \(ms(crystalP50))/\(ms(crystalP95)) ms")

        XCTAssertGreaterThan(legacyP50, emptyP50 * 1.10,
            "the span does not respond to drawing cost (legacy p50 \(legacyP50) vs empty \(emptyP50) ms)")
        XCTAssertLessThanOrEqual(crystalP95, 16.7, "crystal p95 \(crystalP95) ms exceeds one 60 Hz frame")
        XCTAssertLessThanOrEqual(crystalP50, legacyP50 * 1.5,
            "crystal p50 \(crystalP50) ms is more than 1.5 × legacy p50 \(legacyP50) ms")
    }

    private func sysctl(_ name: String) -> String {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return "unknown" }
        var buffer = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &buffer, &size, nil, 0) == 0 else { return "unknown" }
        return String(cString: buffer)
    }
}
