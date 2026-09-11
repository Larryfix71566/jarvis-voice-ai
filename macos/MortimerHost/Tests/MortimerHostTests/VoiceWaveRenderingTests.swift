import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

@MainActor
final class VoiceWaveRenderingTests: XCTestCase {
    private func render(_ state: VoicePresentationState, now: Double, engine: WaveEngine) throws -> NSBitmapImageRep {
        let view = NSHostingView(rootView: Canvas { context, size in
            engine.draw(context: &context, size: size, now: now, state: .speaking,
                stageCenterX: nil, presentation: state)
        }.background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: 400, height: 180)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        return bitmap
    }

    func testUnavailableSpeechRendersIdenticallyAcrossTime() throws {
        let state = VoicePresentationState(activity: .assistant, userLevel: nil, outputLevel: nil,
            microphoneMuted: false, assistantSpeaking: true)
        let engine = WaveEngine()
        let first = try render(state, now: 10, engine: engine)
        let later = try render(state, now: 20, engine: engine)
        XCTAssertEqual(first.representation(using: .png, properties: [:]), later.representation(using: .png, properties: [:]),
            "A speaking flag without measured audio must not synthesize a speech envelope")
    }

    func testMeasuredSpeakersUseDistinctRenderedColors() throws {
        for user in [true, false] {
            let state = VoicePresentationState(activity: user ? .user : .assistant,
                userLevel: user ? 0.7 : nil, outputLevel: user ? nil : 0.7,
                microphoneMuted: false, assistantSpeaking: !user)
            let engine = WaveEngine()
            _ = try render(state, now: 10, engine: engine)
            let bitmap = try render(state, now: 10.1, engine: engine)
            var matchingPixels = 0
            for y in 0..<bitmap.pixelsHigh {
                for x in 0..<bitmap.pixelsWide {
                    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                    let r = color.redComponent, g = color.greenComponent, b = color.blueComponent
                    if user ? (g > 0.1 && g > r * 2 && b > r * 2) : (b > 0.1 && b > g * 1.2 && r > g * 1.1) {
                        matchingPixels += 1
                    }
                }
            }
            XCTAssertGreaterThan(matchingPixels, 20, "Missing rendered speaker color")
        }
    }
}
