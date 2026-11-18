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

    /// The legacy wave's E2 boot ramp eases in over 0.9 s and then holds full
    /// amplitude. bootStart is never reset, so without the clamp p·(2 − p)
    /// fell back to 0 at 1.8 s and reached about −19.8 at bootStart + 5 s.
    func testLegacyBootRampHoldsSteadyAmplitudeAfterItCompletes() {
        let start = 10.0
        XCTAssertEqual(WaveEngine.bootRamp(now: start, bootStart: start), 0, accuracy: 1e-12)
        XCTAssertEqual(WaveEngine.bootRamp(now: start + WaveEngine.bootRampSeconds, bootStart: start),
                       1, accuracy: 1e-12)
        XCTAssertEqual(WaveEngine.bootRamp(now: start + 5, bootStart: start), 1,
                       "five seconds after boot the wave must be at steady-state amplitude")
        XCTAssertEqual(WaveEngine.bootRamp(now: start + 5, bootStart: 0), 1,
                       "a wave that never booted is at full amplitude")
        var previous = 0.0
        for step in 0...500 {
            let ramp = WaveEngine.bootRamp(now: start + Double(step) * 0.01, bootStart: start)
            XCTAssertGreaterThanOrEqual(ramp, previous, "the boot ramp never falls back")
            XCTAssertLessThanOrEqual(ramp, 1)
            previous = ramp
        }
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
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        return bitmap
    }

    /// Let the approved measured-time colour and audio envelopes settle before
    /// asserting the speaker palette; a single 100 ms frame is mid-transition.
    /// The 60 warm-up frames only advance the engine, so they draw offscreen
    /// through ImageRenderer instead of opening a window each: 61 fixture
    /// windows per call (about 370 per run) slowed the window server for
    /// WindowVisibilityTests, which runs next. Only the sampled frame uses
    /// the on-screen fixture.
    private func renderSettled(_ state: VoicePresentationState, engine: WaveEngine) throws -> NSBitmapImageRep {
        var drawn = 0
        for frame in 0..<60 {
            let now = 10 + Double(frame) / 60
            let renderer = ImageRenderer(content: Canvas { context, size in
                drawn += 1
                engine.draw(context: &context, size: size, now: now, state: .speaking,
                    stageCenterX: nil, presentation: state, reduceMotion: false)
            }.frame(width: 400, height: 180).background(Color.black))
            _ = renderer.cgImage
        }
        XCTAssertGreaterThanOrEqual(drawn, 60, "every warm-up frame must advance the engine")
        return try render(state, now: 11, engine: engine)
    }

    private func assertWhiteCore(_ bitmap: NSBitmapImageRep, file: StaticString = #filePath,
                                 line: UInt = #line) throws {
        let center = try XCTUnwrap(bitmap.colorAt(x: bitmap.pixelsWide / 2,
            y: bitmap.pixelsHigh / 2)?.usingColorSpace(.deviceRGB), file: file, line: line)
        let channels = [center.redComponent, center.greenComponent, center.blueComponent]
        XCTAssertLessThan((channels.max() ?? 0) - (channels.min() ?? 0), 0.08,
                          "C6's approved nucleus is white, not the current talker colour", file: file, line: line)
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

    func testReducedMotionRedrawsIdleEnergyOnlyAtScheduledTicks() throws {
        let idle = VoicePresentationState(activity: .listening, userLevel: nil,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let engine = WaveEngine()
        let first = try render(idle, now: 10, engine: engine, reduceMotion: true)
        let hover = try render(idle, now: 10.02, engine: engine, reduceMotion: true)
        let tick = try render(idle, now: 10.1000000001, engine: engine, reduceMotion: true)
        XCTAssertEqual(first.representation(using: .png, properties: [:]),
                       hover.representation(using: .png, properties: [:]),
                       "Pointer repaints between 0.1-second ticks must reuse the scheduled energy state")
        XCTAssertNotEqual(first.representation(using: .png, properties: [:]),
                          tick.representation(using: .png, properties: [:]),
                          "Reduced Motion uses the approved 0.1-second cadence, not a frozen orb")
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try XCTUnwrap(first.representation(using: .png, properties: [:]))
            .write(to: directory.appendingPathComponent("orb-idle.png"))
    }

    func testConnectedMutedOrbUsesMutedStateAndKeepsMoving() throws {
        let idle = VoicePresentationState(activity: .listening, userLevel: nil,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let muted = VoicePresentationState(activity: .muted, userLevel: nil,
            outputLevel: nil, microphoneMuted: true, assistantSpeaking: false)
        let engine = WaveEngine()
        let idleFrame = try render(idle, now: 10, engine: WaveEngine())
        let first = try render(muted, now: 10, engine: engine)
        let later = try render(muted, now: 10.1, engine: engine)
        XCTAssertNotEqual(first.representation(using: .png, properties: [:]),
                          idleFrame.representation(using: .png, properties: [:]),
                          "C6 muted uses one slate arc and a mic slash, not the listening orb")
        XCTAssertNotEqual(first.representation(using: .png, properties: [:]),
                          later.representation(using: .png, properties: [:]),
                          "Connected/muted arcs keep moving without input audio")
        XCTAssertEqual(muted.label, "Muted")
    }

    func testMutedReducedMotionUsesScheduleAndDisconnectedOrbRemainsStill() throws {
        let offline = VoicePresentationState(activity: .offline, userLevel: nil,
            outputLevel: nil, microphoneMuted: true, assistantSpeaking: false)
        let offlineEngine = WaveEngine()
        let offlineFirst = try render(offline, now: 10, engine: offlineEngine)
        let offlineLater = try render(offline, now: 20, engine: offlineEngine)
        XCTAssertEqual(offlineFirst.representation(using: .png, properties: [:]),
                       offlineLater.representation(using: .png, properties: [:]))

        let muted = VoicePresentationState(activity: .muted, userLevel: nil,
            outputLevel: nil, microphoneMuted: true, assistantSpeaking: false)
        let mutedEngine = WaveEngine()
        let first = try render(muted, now: 10, engine: mutedEngine, reduceMotion: true)
        let hover = try render(muted, now: 10.02, engine: mutedEngine, reduceMotion: true)
        let tick = try render(muted, now: 10.1000000001, engine: mutedEngine, reduceMotion: true)
        XCTAssertEqual(first.representation(using: .png, properties: [:]),
                       hover.representation(using: .png, properties: [:]))
        XCTAssertNotEqual(first.representation(using: .png, properties: [:]),
                          tick.representation(using: .png, properties: [:]))
    }

    func testMeasuredSpeakersUseDistinctRenderedColors() throws {
        for user in [true, false] {
            let state = VoicePresentationState(activity: user ? .user : .assistant,
                userLevel: user ? 0.7 : nil, outputLevel: user ? nil : 0.7,
                microphoneMuted: false, assistantSpeaking: !user)
            let engine = WaveEngine()
            let bitmap = try renderSettled(state, engine: engine)
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
        let bitmap = try renderSettled(state, engine: engine)
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

    func testAtomNucleusKeepsApprovedWhiteCoreAcrossTalkers() throws {
        let user = VoicePresentationState(activity: .user, userLevel: 0.8,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        let assistant = VoicePresentationState(activity: .assistant, userLevel: nil,
            outputLevel: 0.8, microphoneMuted: false, assistantSpeaking: true)
        try assertWhiteCore(renderSettled(user, engine: WaveEngine()))
        try assertWhiteCore(renderSettled(assistant, engine: WaveEngine()))
    }

    func testIdleNucleusUsesApprovedWhiteCore() throws {
        let idle = VoicePresentationState(activity: .listening, userLevel: nil,
            outputLevel: nil, microphoneMuted: false, assistantSpeaking: false)
        try assertWhiteCore(render(idle, now: 10, engine: WaveEngine()))
    }
}
