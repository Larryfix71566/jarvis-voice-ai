import AVFoundation
import XCTest
import JarvisKitObjC
@testable import JarvisKit

/// Native-audio plan §7, `AudioEngineIO`: the socket-free, device-free
/// halves — capture conversion from the rates real inputs present (the
/// AirPods 24 kHz mic case is a unit test, not a live gamble), playout
/// accounting behind `botIsSpeaking`, the Int16 → Float32 playout decode
/// and the level meter behind the C6.2 slots.
final class AudioEngineIOTests: XCTestCase {

    // MARK: Capture conversion (D2)

    private func sine(rate: Double, channels: AVAudioChannelCount, seconds: Double, hz: Double = 440, amplitude: Float = 0.5) -> AVAudioPCMBuffer {
        let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: channels)!
        let frames = AVAudioFrameCount(rate * seconds)
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames)!
        buffer.frameLength = frames
        for ch in 0..<Int(channels) {
            for i in 0..<Int(frames) {
                buffer.floatChannelData![ch][i] = amplitude * Float(sin(2 * .pi * hz * Double(i) / rate))
            }
        }
        return buffer
    }

    private func zeroCrossings(_ data: Data) -> Int {
        let samples = data.withUnsafeBytes { Array($0.bindMemory(to: Int16.self)) }
        var crossings = 0
        for i in 1..<samples.count where (samples[i - 1] < 0) != (samples[i] < 0) { crossings += 1 }
        return crossings
    }

    func testCaptureConverterProducesSixteenKilohertzMonoInt16FromEveryRealInputRate() throws {
        for (rate, channels) in [(24_000.0, 1), (44_100.0, 1), (48_000.0, 1), (48_000.0, 2), (24_000.0, 2)] as [(Double, Int)] {
            let input = sine(rate: rate, channels: AVAudioChannelCount(channels), seconds: 0.5)
            let converter = try XCTUnwrap(CaptureConverter(inputFormat: input.format), "\(rate)/\(channels)")
            XCTAssertEqual(converter.outputFormat.sampleRate, 16_000)
            XCTAssertEqual(converter.outputFormat.channelCount, 1)
            XCTAssertEqual(converter.outputFormat.commonFormat, .pcmFormatInt16)
            let data = try XCTUnwrap(converter.convert(input), "\(rate)/\(channels)")
            // 0.5 s at 16 kHz mono Int16 = 16,000 bytes; the resampler's
            // history may hold back a few frames on the first call.
            XCTAssertEqual(data.count % 2, 0)
            XCTAssertGreaterThan(data.count, 16_000 - 512, "\(rate)/\(channels): \(data.count) bytes")
            XCTAssertLessThanOrEqual(data.count, 16_000 + 64, "\(rate)/\(channels): \(data.count) bytes")
            // A 440 Hz tone crosses zero 880 times a second: pitch preserved,
            // no duplicated or dropped stretches.
            let expected = Double(data.count / 2) / 16_000 * 880
            XCTAssertEqual(Double(zeroCrossings(data)), expected, accuracy: expected * 0.05, "\(rate)/\(channels)")
        }
    }

    func testCaptureConverterIsContinuousAcrossConsecutiveBuffers() {
        let converter = CaptureConverter(inputFormat: sine(rate: 48_000, channels: 1, seconds: 0.02).format)!
        var total = Data()
        for _ in 0..<50 { total.append(converter.convert(sine(rate: 48_000, channels: 1, seconds: 0.02))!) }
        // 50 × 20 ms = 1 s → 32,000 bytes; continuity means no per-call
        // priming loss compounding across calls.
        XCTAssertGreaterThan(total.count, 32_000 - 512)
        XCTAssertLessThanOrEqual(total.count, 32_000 + 64)
    }

    // MARK: Playout accounting (D4)

    func testPlayoutQueueIsPlayingExactlyWhileScheduledBuffersAreUnfinished() {
        var queue = PlayoutQueue()
        XCTAssertFalse(queue.isPlaying)
        let g1 = queue.scheduled()
        let g2 = queue.scheduled()
        XCTAssertEqual(g1, g2)
        XCTAssertTrue(queue.isPlaying)
        XCTAssertFalse(queue.completed(generation: g1), "one of two still outstanding")
        XCTAssertTrue(queue.isPlaying)
        XCTAssertTrue(queue.completed(generation: g2), "last completion empties the queue")
        XCTAssertFalse(queue.isPlaying)
        XCTAssertFalse(queue.completed(generation: g2), "a spurious completion does not underflow")
        XCTAssertEqual(queue.outstanding, 0)
    }

    func testPlayoutFlushDropsTheQueueAndIgnoresCompletionsFromBeforeIt() {
        var queue = PlayoutQueue()
        let old = queue.scheduled()
        _ = queue.scheduled()
        XCTAssertTrue(queue.flush(), "flush while playing reports the change")
        XCTAssertFalse(queue.isPlaying)
        XCTAssertFalse(queue.flush(), "flush while idle reports no change")
        let new = queue.scheduled()
        XCTAssertNotEqual(old, new)
        XCTAssertFalse(queue.completed(generation: old), "a stale completion is ignored")
        XCTAssertTrue(queue.isPlaying, "…and does not release the new buffer")
        XCTAssertTrue(queue.completed(generation: new))
        XCTAssertFalse(queue.isPlaying)
    }

    // MARK: Playout decode (D3)

    func testPlayoutDecoderTurnsLittleEndianInt16IntoFloatFramesAtTheDeclaredRate() throws {
        var bytes = Data()
        for v in [Int16(0), 16_384, -32_768, 32_767] { withUnsafeBytes(of: v.littleEndian) { bytes.append(contentsOf: $0) } }
        let mono = try XCTUnwrap(PlayoutDecoder.buffer(fromInt16: bytes, sampleRate: 24_000, channels: 1))
        XCTAssertEqual(mono.format.sampleRate, 24_000)
        XCTAssertEqual(mono.format.channelCount, 1)
        XCTAssertEqual(mono.frameLength, 4)
        XCTAssertEqual(Array(UnsafeBufferPointer(start: mono.floatChannelData![0], count: 4)), [0, 0.5, -1, Float(32_767) / 32_768])
        let stereo = try XCTUnwrap(PlayoutDecoder.buffer(fromInt16: bytes, sampleRate: 48_000, channels: 2))
        XCTAssertEqual(stereo.frameLength, 2)
        XCTAssertEqual(stereo.floatChannelData![0][1], -1)
        XCTAssertEqual(stereo.floatChannelData![1][0], 0.5)
        XCTAssertNil(PlayoutDecoder.buffer(fromInt16: Data(), sampleRate: 24_000, channels: 1))
        XCTAssertNil(PlayoutDecoder.buffer(fromInt16: bytes, sampleRate: 24_000, channels: 3))
        XCTAssertNil(PlayoutDecoder.buffer(fromInt16: bytes, sampleRate: 0, channels: 1))
    }

    // MARK: Level meter (C6.2)

    func testLevelMeterReportsRMSOnFloatAndInt16BuffersClampedToUnity() {
        let silence = sine(rate: 48_000, channels: 1, seconds: 0.1, amplitude: 0)
        XCTAssertEqual(LevelMeter.rms(of: silence), 0)
        let half = sine(rate: 48_000, channels: 2, seconds: 0.1, amplitude: 0.5)
        XCTAssertEqual(LevelMeter.rms(of: half), 0.5 / 2.0.squareRoot(), accuracy: 0.005)
        let int16Format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)!
        let full = AVAudioPCMBuffer(pcmFormat: int16Format, frameCapacity: 160)!
        full.frameLength = 160
        for i in 0..<160 { full.int16ChannelData![0][i] = i % 2 == 0 ? .max : .min }
        XCTAssertEqual(LevelMeter.rms(of: full), 1, accuracy: 0.001)
        let empty = AVAudioPCMBuffer(pcmFormat: int16Format, frameCapacity: 16)!
        XCTAssertEqual(LevelMeter.rms(of: empty), 0)
        let sample = AudioLevelSample(rms: 0.25, hostTime: mach_absolute_time())
        XCTAssertEqual(sample.seconds, ProcessInfo.processInfo.systemUptime, accuracy: 0.5, "host time and systemUptime share a clock")
    }

    /// The input tap under Voice Processing delivers the mic array layout
    /// (9 ch / 48 kHz on the MacBook Air); the converter is fed channel 0.
    func testFirstChannelTakesChannelZeroOfAMultiChannelTapBufferAndPassesMonoThrough() throws {
        // No standard layout exists for 9 channels; the mic array reports a
        // discrete layout, which is what this builds.
        let layout = try XCTUnwrap(AVAudioChannelLayout(layoutTag: kAudioChannelLayoutTag_DiscreteInOrder | 9))
        let nine = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48_000, interleaved: false, channelLayout: layout)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: nine, frameCapacity: 480))
        buffer.frameLength = 480
        for ch in 0..<9 {
            for i in 0..<480 { buffer.floatChannelData![ch][i] = Float(ch) + Float(i) / 1000 }
        }
        let mono = try XCTUnwrap(CaptureConverter.firstChannel(of: buffer))
        XCTAssertEqual(mono.format.channelCount, 1)
        XCTAssertEqual(mono.format.sampleRate, 48_000)
        XCTAssertEqual(mono.frameLength, 480)
        XCTAssertEqual(mono.floatChannelData![0][0], 0)
        XCTAssertEqual(mono.floatChannelData![0][479], 0.479, accuracy: 1e-6)

        let layout3 = try XCTUnwrap(AVAudioChannelLayout(layoutTag: kAudioChannelLayoutTag_DiscreteInOrder | 3))
        let interleaved = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48_000, interleaved: true, channelLayout: layout3)
        let ibuf = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: interleaved, frameCapacity: 4))
        ibuf.frameLength = 4
        for i in 0..<12 { ibuf.floatChannelData![0][i] = Float(i) }
        let imono = try XCTUnwrap(CaptureConverter.firstChannel(of: ibuf))
        XCTAssertEqual((0..<4).map { imono.floatChannelData![0][$0] }, [0, 3, 6, 9])

        let monoFormat = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 24_000, channels: 1))
        let already = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: monoFormat, frameCapacity: 10))
        already.frameLength = 10
        XCTAssertTrue(CaptureConverter.firstChannel(of: already) === already, "mono input is passed through, not copied")

        // Channel 0 of a tap-shaped buffer converts to the wire format. A
        // single 10 ms buffer is shorter than the resampler's priming, so
        // the length is checked over 20 consecutive buffers (20 × 480
        // frames at 48 kHz = 0.2 s = 3,200 samples = 6,400 bytes) with the
        // same tolerances as the continuity test above.
        let converter = try XCTUnwrap(CaptureConverter(inputFormat: mono.format))
        var total = Data()
        for _ in 0..<20 {
            let channelZero = try XCTUnwrap(CaptureConverter.firstChannel(of: buffer))
            total.append(try XCTUnwrap(converter.convert(channelZero)))
        }
        XCTAssertEqual(total.count % 2, 0)
        XCTAssertGreaterThan(total.count, 6_400 - 512, "\(total.count) bytes")
        XCTAssertLessThanOrEqual(total.count, 6_400 + 64, "\(total.count) bytes")
    }
}

/// A device that is still coming up must be waited for, not refused: the
/// bench measured CoreAudio reporting "2 ch, 44100 Hz" input and "0 ch,
/// 0 Hz" output for a moment after another engine stopped, and the same
/// window exists on the app's device-change rebuild (D3).
final class DeviceSettlingTests: XCTestCase {
    private let good = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2)!

    func testUsableFormatsAreReturnedImmediately() throws {
        var slept = 0.0
        let (input, output) = try AudioEngineIO.settledFormats(
            input: { self.good }, output: { self.good }, sleep: { slept += $0 })
        XCTAssertEqual(input.sampleRate, 48_000)
        XCTAssertEqual(output.channelCount, 2)
        XCTAssertEqual(slept, 0, "no wait when the devices are already up")
    }

    func testAHalfBuiltOutputIsWaitedForRatherThanRefused() throws {
        var reads = 0
        var slept = 0.0
        let (_, output) = try AudioEngineIO.settledFormats(
            input: { self.good },
            output: {
                reads += 1
                // Three reads of a not-yet-ready output, then the real one.
                return reads < 4 ? AVAudioFormat() : self.good
            },
            sleep: { slept += $0 })
        XCTAssertEqual(output.channelCount, 2, "the settled format, not the transient one")
        XCTAssertGreaterThan(slept, 0, "it waited")
        XCTAssertLessThan(slept, 1.0, "and not for the whole deadline")
    }

    func testADeviceThatNeverComesUpStillFails() {
        var slept = 0.0
        XCTAssertThrowsError(try AudioEngineIO.settledFormats(
            input: { self.good }, output: { AVAudioFormat() },
            deadline: 0.2, step: 0.05, sleep: { slept += $0 })) { error in
            guard case JarvisError.transport(let message)? = error as? JarvisError else {
                return XCTFail("expected a transport error, got \(error)")
            }
            XCTAssertTrue(message.contains("no audio devices after"), message)
        }
        XCTAssertGreaterThanOrEqual(slept, 0.2, "it used its deadline before giving up")
    }
}

/// The crash of 2026-09-14 19:50:00.245. Pulling an AirPod tore the engine
/// down while the audio meter's own 30 Hz timer was mid-read, and
/// `-[AVAudioNode lastRenderTime]` on a node whose engine is gone raises
/// `required condition is false: _engine != nil` -- an Objective-C
/// exception Swift cannot catch, so the app was terminated rather than
/// failing a session.
///
/// There is no way to assert against that: on the unfixed code these two
/// tests kill the test process. The proof is the suite dying before the
/// guard and passing after it.
final class DetachedPlayerTests: XCTestCase {
    func testPlayoutLevelIsNilWhenThePlayerHasNoEngine() {
        XCTAssertTrue(JarvisFlags.captureUsesSinkNode,
                      "only the sink-node path reads lastRenderTime; the guard is untested otherwise")
        let io = AudioEngineIO(voiceProcessing: false)
        // Never started, so the player was never attached to anything.
        XCTAssertNil(io.latestPlayoutLevel)
    }

    func testPlayoutLevelIsNilAfterTheEngineStopsWhileTheMeterKeepsAsking() {
        let io = AudioEngineIO(voiceProcessing: false)
        io.stop()
        // The meter does not know the session ended; it just keeps sampling.
        for _ in 0..<5 {
            XCTAssertNil(io.latestPlayoutLevel)
            XCTAssertNil(io.latestInputLevel)
        }
    }
}

/// WS-18: an output-device switch must not terminate the app. 2026-09-30:
/// AirPods → Mac speaker rebuilt the engine, Voice Processing then faulted
/// its downlink, and `AVAudioPlayerNode.play()` raised "player did not see
/// an IO cycle" five seconds later.
final class OutputIOWatchTests: XCTestCase {
    func testAFirstReadIsOnlyABaselineAndMovementMeansFlowing() {
        var watch = OutputIOWatch(startedAt: 100)
        XCTAssertEqual(watch.observe(sampleTime: 4_800, now: 100.1), .waiting, "one read proves nothing")
        XCTAssertEqual(watch.observe(sampleTime: 9_600, now: 100.2), .flowing)
        XCTAssertEqual(watch.state(now: 100.2 + OutputIOWatch.freshness - 0.05), .flowing)
        XCTAssertEqual(watch.state(now: 100.2 + OutputIOWatch.freshness + 0.05), .waiting,
                       "flowing needs recent movement")
    }

    func testAFrozenRenderTimeIsAStallNotIO() {
        var watch = OutputIOWatch(startedAt: 100)
        for i in 1...14 { XCTAssertNotEqual(watch.observe(sampleTime: 4_800, now: 100 + Double(i) * 0.1), .flowing) }
        XCTAssertEqual(watch.observe(sampleTime: 4_800, now: 100 + OutputIOWatch.stallAfter + 0.01), .stalled,
                       "the 09-30 case: running engine, no output cycle")
    }

    func testNoRenderTimeAtAllIsAStallAfterTheWindow() {
        var watch = OutputIOWatch(startedAt: 50)
        XCTAssertEqual(watch.observe(sampleTime: nil, now: 50.5), .waiting)
        XCTAssertEqual(watch.observe(sampleTime: nil, now: 50 + OutputIOWatch.stallAfter + 0.01), .stalled)
    }

    func testAStallIsMeasuredFromTheLastMovement() {
        var watch = OutputIOWatch(startedAt: 0)
        watch.observe(sampleTime: 1, now: 0.1)
        watch.observe(sampleTime: 2, now: 0.2)
        XCTAssertEqual(watch.observe(sampleTime: 2, now: 1.0), .waiting)
        XCTAssertEqual(watch.observe(sampleTime: 2, now: 0.2 + OutputIOWatch.stallAfter + 0.01), .stalled)
        XCTAssertEqual(watch.observe(sampleTime: 3, now: 2.0), .flowing, "IO coming back clears the stall")
    }

    func testTheObjectiveCCatcherReturnsTheRaisedExceptionInsteadOfTerminating() {
        let caught = JKCatchObjCException {
            NSException(name: NSExceptionName("com.apple.coreaudio.avfaudio"),
                        reason: "player did not see an IO cycle.", userInfo: nil).raise()
        }
        XCTAssertEqual(caught?.name.rawValue, "com.apple.coreaudio.avfaudio")
        XCTAssertEqual(caught?.reason, "player did not see an IO cycle.")
        var ran = false
        XCTAssertNil(JKCatchObjCException { ran = true })
        XCTAssertTrue(ran)
    }

    func testTheWatchCanBeSwitchedOff() {
        let key = "JARVIS_AUDIO_OUTPUT_WATCH"
        let previous = UserDefaults.standard.object(forKey: key)
        defer {
            if let previous { UserDefaults.standard.set(previous, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }
        UserDefaults.standard.removeObject(forKey: key)
        XCTAssertTrue(JarvisFlags.outputIOWatchEnabled, "on by default")
        UserDefaults.standard.set(false, forKey: key)
        XCTAssertFalse(JarvisFlags.outputIOWatchEnabled)
    }

    /// The signal the watch relies on, measured on this Mac: a running
    /// output-only engine (no microphone, no permission prompt) advances its
    /// output node's render sample time. Skipped when there is no output.
    func testOutputNodeRenderTimeAdvancesOnARunningEngine() throws {
        let engine = AVAudioEngine()
        let format = engine.outputNode.outputFormat(forBus: 0)
        try XCTSkipIf(format.sampleRate <= 0 || format.channelCount == 0, "no output device")
        engine.connect(engine.mainMixerNode, to: engine.outputNode, format: format)
        engine.mainMixerNode.outputVolume = 0
        engine.prepare()
        try engine.start()
        defer { engine.stop() }
        var watch = OutputIOWatch(startedAt: ProcessInfo.processInfo.systemUptime)
        var state = OutputIOWatch.State.waiting
        for _ in 0..<15 where state != .flowing {
            Thread.sleep(forTimeInterval: 0.1)
            let t = engine.outputNode.lastRenderTime
            state = watch.observe(sampleTime: t.flatMap { $0.isSampleTimeValid ? Double($0.sampleTime) : nil },
                                  now: ProcessInfo.processInfo.systemUptime)
        }
        XCTAssertEqual(state, .flowing, "the output node's render time did not advance within 1.5 s")
    }
}
