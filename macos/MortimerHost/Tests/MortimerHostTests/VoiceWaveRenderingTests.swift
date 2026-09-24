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

    func testMeasuredVoiceGainMakesQuietInputVisiblyResponsive() {
        let quietInputLevel = level(inputMedian, isInput: true)
        let compactRailHeight = 150.0
        let oldContribution = compactRailHeight * quietInputLevel * 0.115 * 2.0
        let newContribution = compactRailHeight * quietInputLevel * AudioPresentationTuning.measuredInputGain * 2.0
        XCTAssertGreaterThan(newContribution, oldContribution * 3.0)
        XCTAssertGreaterThan(newContribution, 3.0,
                             "quiet but measured speech must have visible travel")
        XCTAssertGreaterThan(AudioPresentationTuning.measuredInputGain,
                             AudioPresentationTuning.measuredOutputGain,
                             "the quieter input channel needs its own modest presentation lift")
    }
}
import AppKit
import SwiftUI
@testable import MortimerHost

@MainActor
final class VoiceWaveRenderingTests: XCTestCase {
    func testOrbitalTravelIsBoundedWhenAudioChangesAtLongUptime() {
        var motion = AtomMotion()
        let start = motion.advance(now: 1_000_000, energy: 0, moving: true)
        let next = motion.advance(now: 1_000_000 + 1.0 / 60, energy: 1, moving: true)
        XCTAssertEqual(next - start, 1.50 / 60, accuracy: 0.000001)
        XCTAssertEqual(motion.advance(now: 1_000_001, energy: 0.7, moving: false), next)
        motion.suspend()
        XCTAssertEqual(motion.advance(now: 2_000_000, energy: 1, moving: true), next)
    }

    private func render(_ state: VoicePresentationState, now: Double, engine: WaveEngine,
                        reduceMotion: Bool = false) throws -> NSBitmapImageRep {
        let view = NSHostingView(rootView: Canvas { context, size in
            engine.draw(context: &context, size: size, now: now, state: .speaking,
                stageCenterX: nil, presentation: state, reduceMotion: reduceMotion)
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

    func testListeningWithoutMeterKeepsReadyTraceAlive() throws {
        let state = VoicePresentationState(activity: .listening, userLevel: nil, outputLevel: nil,
            microphoneMuted: false, assistantSpeaking: false)
        let engine = WaveEngine()
        let first = try render(state, now: 10, engine: engine)
        let later = try render(state, now: 10.5, engine: engine)
        XCTAssertNotEqual(first.representation(using: .png, properties: [:]),
                          later.representation(using: .png, properties: [:]),
                          "The ready state should retain a subtle animated trace")
    }

    func testReducedMotionFreezesIdlePlasmaAndComets() throws {
        let idle = VoicePresentationState(activity: .listening, userLevel: nil,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let engine = WaveEngine()
        let first = try render(idle, now: 10, engine: engine, reduceMotion: true)
        let later = try render(idle, now: 20, engine: engine, reduceMotion: true)
        XCTAssertEqual(first.representation(using: .png, properties: [:]),
                       later.representation(using: .png, properties: [:]),
                       "Idle breathing, sparks and plasma must respect Reduced Motion too")
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try XCTUnwrap(first.representation(using: .png, properties: [:]))
            .write(to: directory.appendingPathComponent("orb-idle.png"))
    }

    func testConnectedMutedOrbMatchesIdleAndKeepsMoving() throws {
        let idle = VoicePresentationState(activity: .listening, userLevel: nil,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let muted = VoicePresentationState(activity: .muted, userLevel: nil,
            outputLevel: nil, microphoneMuted: true, assistantSpeaking: false)
        let engine = WaveEngine()
        let idleFrame = try render(idle, now: 10, engine: WaveEngine())
        let first = try render(muted, now: 10, engine: engine)
        let later = try render(muted, now: 10.1, engine: engine)
        XCTAssertEqual(first.representation(using: .png, properties: [:]),
                       idleFrame.representation(using: .png, properties: [:]),
                       "Muting input must preserve the connected periwinkle orb")
        XCTAssertNotEqual(first.representation(using: .png, properties: [:]),
                          later.representation(using: .png, properties: [:]),
                          "Connected/muted comets should keep moving without input audio")
        XCTAssertEqual(muted.label, "Muted")
    }

    func testMutedReducedMotionAndDisconnectedOrbRemainStill() throws {
        for activity: VoicePresentationState.Activity in [.muted, .offline] {
            let state = VoicePresentationState(activity: activity, userLevel: nil,
                outputLevel: nil, microphoneMuted: true, assistantSpeaking: false)
            let engine = WaveEngine()
            let first = try render(state, now: 10, engine: engine, reduceMotion: activity == .muted)
            let later = try render(state, now: 20, engine: engine, reduceMotion: activity == .muted)
            XCTAssertEqual(first.representation(using: .png, properties: [:]),
                           later.representation(using: .png, properties: [:]))
        }
    }

    func testMeasuredSpeakersUseDistinctRenderedColors() throws {
        for user in [true, false] {
            let state = VoicePresentationState(activity: user ? .user : .assistant,
                userLevel: user ? 0.7 : nil, outputLevel: user ? nil : 0.7,
                microphoneMuted: false, assistantSpeaking: !user)
            let engine = WaveEngine()
            _ = try render(state, now: 10, engine: engine)
            let bitmap = try render(state, now: 10.1, engine: engine)
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
                .write(to: directory.appendingPathComponent(user ? "orb-user.png" : "orb-mortimer.png"))
            var matchingPixels = 0
            for y in 0..<bitmap.pixelsHigh {
                for x in 0..<bitmap.pixelsWide {
                    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                    let r = color.redComponent, g = color.greenComponent, b = color.blueComponent
                    if user ? (g > 0.1 && g > r * 2 && b > r * 2) :
                        (r > 0.5 && g > 0.25 && r > g * 1.2 && g > b * 1.4) {
                        matchingPixels += 1
                    }
                }
            }
            XCTAssertGreaterThan(matchingPixels, 20, "Missing rendered speaker color")
        }
    }

    func testAtomRendersBothMeasuredChannelsDuringOverlap() throws {
        let state = VoicePresentationState(activity: .user, userLevel: 0.7,
            outputLevel: 0.7, microphoneMuted: false, assistantSpeaking: true)
        let engine = WaveEngine()
        _ = try render(state, now: 10, engine: engine)
        let bitmap = try render(state, now: 10.1, engine: engine)
        var teal = 0, orange = 0
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                let r = color.redComponent, g = color.greenComponent, b = color.blueComponent
                if g > 0.1 && g > r * 2 && b > r * 2 { teal += 1 }
                if r > 0.5 && g > 0.25 && r > g * 1.2 && g > b * 1.4 { orange += 1 }
            }
        }
        XCTAssertGreaterThan(teal, 20, "overlap must retain the user orbital channel")
        XCTAssertGreaterThan(orange, 20, "overlap must retain Mortimer's orbital channel")
    }

    func testAtomNucleusFollowsCurrentTalkerColor() throws {
        let user = VoicePresentationState(activity: .user, userLevel: 0.8,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let assistant = VoicePresentationState(activity: .assistant, userLevel: nil,
            outputLevel: 0.8, microphoneMuted: false, assistantSpeaking: true)
        let userBitmap = try render(user, now: 10, engine: WaveEngine())
        let assistantBitmap = try render(assistant, now: 10, engine: WaveEngine())
        let userCenter = try XCTUnwrap(userBitmap.colorAt(x: userBitmap.pixelsWide / 2,
                                                           y: userBitmap.pixelsHigh / 2)?.usingColorSpace(.deviceRGB))
        let assistantCenter = try XCTUnwrap(assistantBitmap.colorAt(x: assistantBitmap.pixelsWide / 2,
                                                                     y: assistantBitmap.pixelsHigh / 2)?.usingColorSpace(.deviceRGB))
        XCTAssertGreaterThan(userCenter.greenComponent, userCenter.redComponent,
                             "user nucleus should use teal")
        XCTAssertGreaterThan(assistantCenter.redComponent, assistantCenter.greenComponent,
                             "Mortimer nucleus should use orange")
    }

    func testIdleNucleusUsesPeriwinkle() throws {
        let idle = VoicePresentationState(activity: .listening, userLevel: nil,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let bitmap = try render(idle, now: 10, engine: WaveEngine())
        let center = try XCTUnwrap(bitmap.colorAt(x: bitmap.pixelsWide / 2,
                                                   y: bitmap.pixelsHigh / 2)?.usingColorSpace(.deviceRGB))
        XCTAssertGreaterThan(center.blueComponent, center.redComponent,
                             "idle nucleus should use periwinkle")
    }
}
