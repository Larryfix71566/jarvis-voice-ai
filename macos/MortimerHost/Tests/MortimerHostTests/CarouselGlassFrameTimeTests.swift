import XCTest
import AppKit
import SwiftUI
import QuartzCore
@testable import MortimerHost

/// Frame cost of the carousel's orb glass against today's `.mortimerGlass(.card)`,
/// measured the way OrbShellFrameTimeTests does: from the change until the
/// render server runs the completion block of the transaction that carried it.
/// Card 620 x 400 pt. The pointer is moved through `RimGlowPointer`, the
/// glow's test hook, not through events. Gate: probe 3 (lit + follow glow)
/// p50 and p95 each <= probe 1 x 1.10. Needs a logged-in graphical session.
@MainActor
final class CarouselGlassFrameTimeTests: XCTestCase {
    enum Probe { case today, crystal, crystalFollow }

    struct ProbeView: View {
        let probe: Probe
        let pointer: RimGlowPointer
        var body: some View {
            let card = VStack(alignment: .leading, spacing: 8) {
                Text("Front answer").font(.headline)
                Text("Supplied synthetic evidence for the timing probe.").font(.callout)
                Spacer()
            }
            .padding(12)
            .frame(width: 620, height: 400)
            Group {
                switch probe {
                case .today:
                    card.mortimerGlass(.card)
                case .crystal:
                    card.orbGlassCard(lit: true, glowColor: AppTheme.mortimer, glowSuppressed: true,
                                      glowDriver: pointer)
                case .crystalFollow:
                    card.orbGlassCard(lit: true, glowColor: AppTheme.mortimer, glowSuppressed: false,
                                      glowDriver: pointer)
                }
            }
            .frame(width: 700, height: 460)
            .background(Color.black)
        }
    }

    @MainActor
    private final class Harness {
        final class Presented { var at: Double? }
        let pointer = RimGlowPointer()
        let window: NSWindow
        var completions = 0

        init(probe: Probe) {
            let hosted = NSHostingView(rootView: ProbeView(probe: probe, pointer: pointer))
            hosted.frame = NSRect(x: 0, y: 0, width: 700, height: 460)
            let window = NSWindow(contentRect: hosted.frame, styleMask: [.borderless],
                                  backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = hosted
            window.orderFrontRegardless()
            RunLoop.main.run(until: Date().addingTimeInterval(0.4))
            self.window = window
        }

        func close() { closeRenderingFixtureWindow(window) }

        /// One frame: pointer moves around the card, then render completion, in ms.
        func step(_ index: Int) -> Double {
            let t = Double(index) * 0.05
            let point = CGPoint(x: 310 + cos(t) * 300, y: 200 + sin(t) * 190)
            let mark = Presented()
            let start = CACurrentMediaTime()
            CATransaction.begin()
            CATransaction.setCompletionBlock { mark.at = CACurrentMediaTime() }
            pointer.update(point)
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

        func run(frames: Int) -> [Double] {
            for index in 0..<10 { _ = step(index) }
            return (0..<frames).map { step(10 + $0) }
        }
    }

    private func percentile(_ values: [Double], _ p: Double) -> Double {
        let s = values.sorted()
        return s[min(s.count - 1, max(0, Int((Double(s.count) * p).rounded(.up)) - 1))]
    }

    private func ms(_ value: Double) -> Double { (value * 1000).rounded() / 1000 }

    func testFollowGlowStaysWithinTenPercentOfTodaysCard() throws {
        if ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true" {
            throw XCTSkip("Hosted-runner skip: Larry runs this on his Mac.")
        }
        _ = NSApplication.shared
        func measure(_ probe: Probe) -> (frames: [Double], completions: Int) {
            let harness = Harness(probe: probe)
            defer { harness.close() }
            let frames = harness.run(frames: 300)
            return (frames, harness.completions)
        }
        let today = measure(.today)
        let crystal = measure(.crystal)
        let follow = measure(.crystalFollow)
        for (name, result) in [("today", today), ("crystal", crystal), ("follow", follow)] {
            XCTAssertEqual(result.completions, 310, "\(name): every frame must reach the render server")
        }
        func summary(_ frames: [Double]) -> [String: Double] {
            ["p50_ms": ms(percentile(frames, 0.5)), "p95_ms": ms(percentile(frames, 0.95)),
             "max_ms": ms(frames.max() ?? 0)]
        }
        let record: [String: Any] = [
            "gate": "follow p50 and p95 <= today x 1.10",
            "today": summary(today.frames), "crystal": summary(crystal.frames),
            "crystal_follow": summary(follow.frames),
            "frames_per_probe": 300, "card_pt": ["width": 620, "height": 400],
            "os": ProcessInfo.processInfo.operatingSystemVersionString,
            "recorded_at": ISO8601DateFormatter().string(from: Date()),
            "test": "CarouselGlassFrameTimeTests.testFollowGlowStaysWithinTenPercentOfTodaysCard",
        ]
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
            .write(to: directory.appendingPathComponent("carousel-glass-frame-time.json"))
        let t50 = percentile(today.frames, 0.5), t95 = percentile(today.frames, 0.95)
        let f50 = percentile(follow.frames, 0.5), f95 = percentile(follow.frames, 0.95)
        print("Carousel glass p50/p95: today \(ms(t50))/\(ms(t95)), crystal \(ms(percentile(crystal.frames, 0.5)))/\(ms(percentile(crystal.frames, 0.95))), follow \(ms(f50))/\(ms(f95)) ms")
        if ProcessInfo.processInfo.environment["MORTIMER_SANDBOX_GUEST"] != "1" {
            XCTAssertLessThanOrEqual(f50, t50 * 1.10, "follow p50 \(f50) vs today \(t50) ms")
            XCTAssertLessThanOrEqual(f95, t95 * 1.10, "follow p95 \(f95) vs today \(t95) ms")
        }
    }
}
