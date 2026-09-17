import XCTest

/// Item 10 (2026-09-16). The numbers in this file are the ones measured on
/// the deployment Mac over a minute of conversation — P2-latency.json,
/// 2026-09-17T00:06Z — not chosen to make the mapping look good.
final class PresentationLevelMappingTests: XCTestCase {
    private let inputMedian = 0.0012, inputP95 = 0.1604, inputPeak = 0.2949
    private let outputMedian = 0.1174, outputP95 = 0.3795, outputPeak = 0.5439

    private func level(_ rms: Double, isInput: Bool) -> Double {
        AudioPresentationTuning.presentationLevel(rms: rms, isInput: isInput) ?? -1
    }

    /// The windows are UserDefaults-backed so the Debug sliders can move
    /// them, which means these tests would otherwise assert against whatever
    /// Larry last dragged. Save his values, assert against the measured
    /// defaults, put his back.
    private static let keys = [
        AudioPresentationTuning.inputFloorKey, AudioPresentationTuning.inputCeilingKey,
        AudioPresentationTuning.outputFloorKey, AudioPresentationTuning.outputCeilingKey,
        AudioPresentationTuning.waveWidthKey,
    ]
    private var saved: [String: Any?] = [:]

    override func setUp() {
        super.setUp()
        for key in Self.keys {
            saved[key] = UserDefaults.standard.object(forKey: key)
            UserDefaults.standard.removeObject(forKey: key)
        }
    }

    override func tearDown() {
        for key in Self.keys {
            if let value = saved[key] ?? nil {
                UserDefaults.standard.set(value, forKey: key)
            } else {
                UserDefaults.standard.removeObject(forKey: key)
            }
        }
        saved = [:]
        super.tearDown()
    }

    /// Crossed or equal slider settings must retain measured variation,
    /// not report the quietest nonzero buffer as full-scale speech.
    func testInvalidWindowsPreserveTheDefaultChannelResponse() {
        for isInput in [true, false] {
            let floorKey = isInput ? AudioPresentationTuning.inputFloorKey : AudioPresentationTuning.outputFloorKey
            let ceilingKey = isInput ? AudioPresentationTuning.inputCeilingKey : AudioPresentationTuning.outputCeilingKey
            let quiet = isInput ? inputMedian : outputMedian
            let loud = isInput ? inputP95 : outputP95
            let expectedQuiet = level(quiet, isInput: isInput)
            let expectedLoud = level(loud, isInput: isInput)
            for ceiling in [-60.0, -10.0] {
                UserDefaults.standard.set(-10.0, forKey: floorKey)
                UserDefaults.standard.set(ceiling, forKey: ceilingKey)
                XCTAssertEqual(level(quiet, isInput: isInput), expectedQuiet, accuracy: 0.0001)
                XCTAssertEqual(level(loud, isInput: isInput), expectedLoud, accuracy: 0.0001)
                XCTAssertGreaterThan(level(loud, isInput: isInput), level(quiet, isInput: isInput))
                XCTAssertEqual(level(0, isInput: isInput), 0)
            }
        }
    }

    /// Item 10b. The width slider reads back exactly, clamps a stray
    /// `defaults write`, and never lets a non-finite value reach the
    /// window's division.
    func testTheWidthFractionIsStoredClampedAndDefaulted() {
        XCTAssertEqual(AudioPresentationTuning.waveWidthFraction, 0.11, "the constant the draw used before")
        UserDefaults.standard.set(0.25, forKey: AudioPresentationTuning.waveWidthKey)
        XCTAssertEqual(AudioPresentationTuning.waveWidthFraction, 0.25)
        UserDefaults.standard.set(0.0, forKey: AudioPresentationTuning.waveWidthKey)
        XCTAssertEqual(AudioPresentationTuning.waveWidthFraction, 0.04, "a zero-width lobe would divide by zero")
        UserDefaults.standard.set(3.0, forKey: AudioPresentationTuning.waveWidthKey)
        XCTAssertEqual(AudioPresentationTuning.waveWidthFraction, 0.45)
        UserDefaults.standard.set(Double.nan, forKey: AudioPresentationTuning.waveWidthKey)
        XCTAssertEqual(AudioPresentationTuning.waveWidthFraction, 0.11)
    }

    func testAStoredWindowOverridesTheMeasuredDefault() {
        XCTAssertEqual(AudioPresentationTuning.inputLevelFloorDb,
                       AudioPresentationTuning.inputFloorDefault)
        UserDefaults.standard.set(-45.0, forKey: AudioPresentationTuning.inputFloorKey)
        XCTAssertEqual(AudioPresentationTuning.inputLevelFloorDb, -45)
        XCTAssertEqual(level(inputMedian, isInput: true), 0,
                       "a -45 dB floor puts the -58 dB median below it, which is the point of the slider")
    }

    /// The defect, stated as a test: linear RMS put the input median at
    /// 1.0% of the wave's 0…1 range, which drew a flat line. The mapping
    /// has to lift it into visible travel without flattening the top.
    func testTheInputWindowSpreadsMeasuredSpeechAcrossItsRange() {
        XCTAssertEqual(level(inputMedian, isInput: true), 0.032, accuracy: 0.005,
                       "just off the floor — quiet between syllables, not dead")
        XCTAssertEqual(level(inputP95, isInput: true), 0.882, accuracy: 0.005)
        XCTAssertEqual(level(inputPeak, isInput: true), 0.988, accuracy: 0.005)
        XCTAssertGreaterThan(level(inputP95, isInput: true) - level(inputMedian, isInput: true), 0.7,
                             "the whole point: measured speech has to MOVE")
    }

    /// Playout measures about 40 dB hotter, which is why the windows differ.
    /// Run through the input window it would sit at 0.85…1.0 and barely move.
    func testThePlayoutWindowKeepsMortimersVoiceMoving() {
        XCTAssertEqual(level(outputMedian, isInput: false), 0.320, accuracy: 0.005)
        XCTAssertEqual(level(outputP95, isInput: false), 0.830, accuracy: 0.005)
        XCTAssertEqual(level(outputPeak, isInput: false), 0.985, accuracy: 0.005)
        XCTAssertGreaterThan(level(outputP95, isInput: false) - level(outputMedian, isInput: false), 0.4)
        // The 0.15 that stood here was picked, not computed: the real figure
        // is 0.1721327612353618, because the playout p95 (-8.4 dB) sits above
        // the input window's -10 dB ceiling and clamps to 1.0 while the
        // median lands at 0.828. Asserting the RELATION instead of a
        // threshold states the actual claim and cannot be satisfied by
        // loosening a number: the shared window has to give less than half
        // the travel the dedicated one does.
        let sharedWindowTravel = level(outputP95, isInput: true) - level(outputMedian, isInput: true)
        let dedicatedTravel = level(outputP95, isInput: false) - level(outputMedian, isInput: false)
        XCTAssertEqual(sharedWindowTravel, 0.172, accuracy: 0.005)
        XCTAssertEqual(dedicatedTravel, 0.510, accuracy: 0.005)
        XCTAssertLessThan(sharedWindowTravel, dedicatedTravel / 2,
                          "one shared window would pin the playout trace — this is why there are two")
    }

    /// `VoiceEnvelope.advance` rejects a target outside 0…1 and zeroes the
    /// level, so a mapping that can overshoot would make the loudest
    /// syllables VANISH rather than clip. It must never overshoot.
    func testTheMappingIsClampedSoTheEnvelopeNeverRejectsIt() {
        for rms in [0.6, 0.9, 1.0, 2.5] {
            XCTAssertLessThanOrEqual(level(rms, isInput: true), 1.0)
            XCTAssertLessThanOrEqual(level(rms, isInput: false), 1.0)
        }
        XCTAssertGreaterThanOrEqual(level(1e-9, isInput: true), 0.0)
    }

    /// An absent level is not a silent one — the wave draws nothing for the
    /// first and a flat trace for the second, and only `nil` carries that.
    func testAbsentAndSilentAreDistinct() {
        XCTAssertNil(AudioPresentationTuning.presentationLevel(rms: nil, isInput: true))
        XCTAssertEqual(AudioPresentationTuning.presentationLevel(rms: 0, isInput: true), 0,
                       "a digitally silent buffer is a measurement, not a missing one")
        XCTAssertNil(AudioPresentationTuning.presentationLevel(rms: .nan, isInput: true))
    }

    func testTheMappingIsMonotonic() {
        var previous = -1.0
        for rms in [0.0005, 0.001, 0.005, 0.02, 0.08, 0.16, 0.3, 0.55, 0.9] {
            let value = level(rms, isInput: true)
            XCTAssertGreaterThanOrEqual(value, previous)
            previous = value
        }
    }
}
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
