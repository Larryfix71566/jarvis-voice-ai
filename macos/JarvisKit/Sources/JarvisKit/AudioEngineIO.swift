import AVFoundation
import Foundation
import os

private let engineLog = Logger(subsystem: "com.mortimer.jarviskit", category: "audio-engine")

// MARK: - Level slot (closure plan C6.2)

/// One RMS over one buffer, stamped with that buffer's host time. Both
/// channels of `AudioEngineIO` publish their latest sample here so C7 can
/// read a level without a second tap. `seconds` is the host clock in
/// seconds (`AVAudioTime.seconds(forHostTime:)`), the same monotonic
/// uptime clock `ProcessInfo.systemUptime` reads.
public struct AudioLevelSample: Equatable, Sendable {
    public let rms: Double          // linear, 0…1 full scale
    public let hostTime: UInt64     // mach host time of the buffer
    public let seconds: TimeInterval

    public init(rms: Double, hostTime: UInt64) {
        self.rms = rms
        self.hostTime = hostTime
        self.seconds = AVAudioTime.seconds(forHostTime: hostTime)
    }
}

/// RMS of a PCM buffer, clamped to 0…1. Pure: unit-tested with synthetic
/// buffers, no engine involved.
enum LevelMeter {
    static func rms(of buffer: AVAudioPCMBuffer) -> Double {
        let frames = Int(buffer.frameLength)
        guard frames > 0 else { return 0 }
        let channels = Int(buffer.format.channelCount)
        var sum = 0.0
        var count = 0
        if let floats = buffer.floatChannelData {
            for ch in 0..<channels {
                let p = floats[ch]
                if buffer.format.isInterleaved {
                    for i in stride(from: ch, to: frames * channels, by: channels) { let v = Double(p[i]); sum += v * v }
                } else {
                    for i in 0..<frames { let v = Double(p[i]); sum += v * v }
                }
                count += frames
            }
        } else if let ints = buffer.int16ChannelData {
            for ch in 0..<channels {
                let p = ints[ch]
                if buffer.format.isInterleaved {
                    for i in stride(from: ch, to: frames * channels, by: channels) { let v = Double(p[i]) / 32768; sum += v * v }
                } else {
                    for i in 0..<frames { let v = Double(p[i]) / 32768; sum += v * v }
                }
                count += frames
            }
        } else {
            return 0
        }
        guard count > 0 else { return 0 }
        return min(1, max(0, (sum / Double(count)).squareRoot()))
    }
}

/// C7.5 diagnosis, 2026-09-13: the meter measured its levels arriving
/// ~137 ms old (input) and ~104 ms (playout), with a spread of under
/// 2 ms — a fixed offset rather than jitter — while new levels appeared
/// only 2.3 and 8.8 times a second against a 1024-frame tap that should
/// deliver ~47. Neither number is explicable from the sampler, so the
/// tap itself is measured here: how big its buffers really are, how far
/// apart the callbacks land, and how old the audio already is when the
/// callback runs (`AVAudioTime.seconds(forHostTime:)` against
/// `systemUptime`, the same clock the meter compares).
final class TapCadence: @unchecked Sendable {
    private let lock = NSLock()
    private let label: String
    private var buffers = 0
    private var frames = 0
    private var lastCallback: TimeInterval?
    private var intervals: [Double] = []
    private var ages: [Double] = []
    private var lastReport: TimeInterval

    init(label: String, now: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        self.label = label
        self.lastReport = now
    }

    func record(frameLength: Int, sampleRate: Double, channels: Int, bufferSeconds: TimeInterval) {
        let now = ProcessInfo.processInfo.systemUptime
        let report: String? = lock.withLock {
            buffers += 1
            frames += frameLength
            ages.append(now - bufferSeconds)
            if let last = lastCallback { intervals.append(now - last) }
            lastCallback = now
            guard now - lastReport >= 2.0, buffers > 1 else { return nil }
            let sortedAges = ages.sorted(), sortedIntervals = intervals.sorted()
            func median(_ v: [Double]) -> Double { v.isEmpty ? 0 : v[v.count / 2] }
            let text = """
                \(label) tap: \(buffers) buffers in \(String(format: "%.1f", now - lastReport))s                 (\(String(format: "%.1f", Double(buffers) / (now - lastReport)))/s),                 \(frames / max(buffers, 1)) frames each at \(Int(sampleRate)) Hz \(channels) ch                 = \(String(format: "%.1f", Double(frames / max(buffers, 1)) / sampleRate * 1000)) ms of audio,                 callback interval median \(String(format: "%.1f", median(sortedIntervals) * 1000)) ms,                 age at callback median \(String(format: "%.1f", median(sortedAges) * 1000)) ms                 (worst \(String(format: "%.1f", (sortedAges.last ?? 0) * 1000)) ms)
                """
            buffers = 0; frames = 0; intervals.removeAll(); ages.removeAll(); lastReport = now
            return text
        }
        if let report { engineLog.notice("\(report, privacy: .public)") }
    }
}

/// D10 (2026-09-13): capture through `AVAudioSinkNode` instead of a tap.
///
/// `installTap(bufferSize:)` is a hint the engine is free to ignore, and on
/// this Mac it does: both taps deliver **4800 frames — 100 ms — ten times a
/// second**, while the devices themselves run at 512 frames (10.7 ms) and
/// will not accept more than 4096. That 100 ms sits in front of everything
/// the client sends: the bot hears a word a tenth of a second late, a
/// barge-in registers a tenth of a second late, and the wave lags by the
/// same amount (measured: levels arriving 137 ms old, C7.5 p95 204 ms
/// against a 150 ms gate). WebRTC's device module delivered 10 ms frames,
/// so the tap silently broke D6's "no behaviour change vs today".
///
/// A sink node receives the render quantum itself. Its block runs on the
/// audio thread, so it does no allocation: channel 0 is copied into one of
/// a small ring of preallocated mono buffers and everything else — the
/// level, the resample, the send — happens on the engine queue. The ring
/// holds ~85 ms at 512 frames, far more slack than the queue needs, and a
/// buffer reused before the queue reads it would show up as a glitch in
/// the capture, not as a crash.
final class SinkCapture {
    let node: AVAudioSinkNode
    private let pool: [AVAudioPCMBuffer]
    private let cursor = OSAllocatedUnfairLock(initialState: 0)

    /// `deliver` is called on the audio thread with a mono buffer valid
    /// until the ring wraps; it must copy or hand off, never block.
    init?(inputFormat: AVAudioFormat, maxFrames: AVAudioFrameCount = 4096, depth: Int = 8,
          deliver: @escaping @Sendable (AVAudioPCMBuffer, UInt64) -> Void) {
        guard let mono = AVAudioFormat(standardFormatWithSampleRate: inputFormat.sampleRate, channels: 1) else { return nil }
        var buffers: [AVAudioPCMBuffer] = []
        for _ in 0..<depth {
            guard let buffer = AVAudioPCMBuffer(pcmFormat: mono, frameCapacity: maxFrames) else { return nil }
            buffers.append(buffer)
        }
        self.pool = buffers
        let pool = buffers
        let cursor = self.cursor
        let channels = Int(inputFormat.channelCount)
        let interleaved = inputFormat.isInterleaved
        node = AVAudioSinkNode { timestamp, frameCount, audioBufferList -> OSStatus in
            let frames = Int(frameCount)
            guard frames > 0, frames <= Int(maxFrames) else { return noErr }
            let list = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: audioBufferList))
            guard let raw = list.first?.mData?.assumingMemoryBound(to: Float.self) else { return noErr }
            let index = cursor.withLock { value -> Int in
                let current = value
                value = (value + 1) % pool.count
                return current
            }
            let buffer = pool[index]
            guard let destination = buffer.floatChannelData?[0] else { return noErr }
            if interleaved || list.count == 1 {
                // One buffer holding every channel: stride past the rest.
                let stride = interleaved ? channels : 1
                for i in 0..<frames { destination[i] = raw[i * stride] }
            } else {
                destination.update(from: raw, count: frames)   // channel 0 is its own buffer
            }
            buffer.frameLength = AVAudioFrameCount(frames)
            deliver(buffer, timestamp.pointee.mHostTime)
            return noErr
        }
    }
}

// MARK: - Capture conversion (D2)

/// Converts whatever the input node delivers (any rate, 1–2 channels,
/// Float32) to the wire format the pipecat WebSocket input expects: mono
/// Int16 at `wireSampleRate` (16 kHz — the WebSocket input does not
/// resample, §3.1 findings). Stateful across calls so the resampler's
/// filter history is continuous; the input block serves each pull from a
/// moving offset (see `convert`) — returning the same whole buffer on
/// every pull would duplicate audio during rate conversion.
final class CaptureConverter {
    static let wireSampleRate: Double = 16_000
    let inputFormat: AVAudioFormat
    let outputFormat: AVAudioFormat
    private let converter: AVAudioConverter

    init?(inputFormat: AVAudioFormat) {
        guard let out = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Self.wireSampleRate,
                                      channels: 1, interleaved: true),
              let conv = AVAudioConverter(from: inputFormat, to: out) else { return nil }
        self.inputFormat = inputFormat
        self.outputFormat = out
        self.converter = conv
    }

    /// Returns the converted bytes (little-endian Int16, mono, 16 kHz), or
    /// nil on a converter error. The output may be a few frames shorter or
    /// longer than `frames × ratio` because the resampler is stateful.
    ///
    /// The input block serves the converter's pulls from a moving offset
    /// into `buffer`: a multi-channel input is pulled in chunks smaller
    /// than the buffer (observed: 20,480 of 24,000 frames on the first
    /// pull of a 48 kHz stereo buffer), so handing the whole buffer over
    /// once loses the remainder. Output is drained until the converter
    /// reports its input ran dry.
    func convert(_ buffer: AVAudioPCMBuffer) -> Data? {
        let ratio = outputFormat.sampleRate / inputFormat.sampleRate
        let total = Int(buffer.frameLength)
        guard total > 0 else { return Data() }
        var offset = 0
        var result = Data()
        while true {
            let capacity = AVAudioFrameCount(Double(total - offset) * ratio) + 64
            guard let out = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else { return nil }
            var error: NSError?
            let status = converter.convert(to: out, error: &error) { requested, outStatus in
                let remaining = total - offset
                guard remaining > 0 else { outStatus.pointee = .noDataNow; return nil }
                let count = min(Int(requested), remaining)
                guard let slice = Self.slice(buffer, from: offset, count: count) else { outStatus.pointee = .noDataNow; return nil }
                offset += count
                outStatus.pointee = .haveData
                return slice
            }
            guard status != .error, error == nil, let int16 = out.int16ChannelData else {
                engineLog.error("capture converter: \(error?.localizedDescription ?? "status \(status.rawValue)", privacy: .public)")
                return nil
            }
            result.append(Data(bytes: int16[0], count: Int(out.frameLength) * MemoryLayout<Int16>.size))
            // .haveData with input left: the output buffer filled before
            // the input was consumed — go round again. Input fully served
            // (or .inputRanDry / .endOfStream): done; the resampler keeps
            // its own history for the next call.
            if status != .haveData || offset >= total { break }
        }
        return result
    }

    /// Channel 0 of `buffer` as a mono Float32 buffer at the buffer's rate
    /// (the buffer itself when it is already mono, non-interleaved
    /// Float32). Used on the input tap: with Voice Processing on, the
    /// MacBook Air's input bus delivers the 9-channel array layout with
    /// every channel carrying the same processed signal.
    static func firstChannel(of buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        let frames = Int(buffer.frameLength)
        let channels = Int(buffer.format.channelCount)
        guard frames > 0, channels > 0, let src = buffer.floatChannelData else { return nil }
        if channels == 1, !buffer.format.isInterleaved { return buffer }
        guard let mono = AVAudioFormat(standardFormatWithSampleRate: buffer.format.sampleRate, channels: 1),
              let out = AVAudioPCMBuffer(pcmFormat: mono, frameCapacity: AVAudioFrameCount(frames)),
              let dst = out.floatChannelData else { return nil }
        if buffer.format.isInterleaved {
            for i in 0..<frames { dst[0][i] = src[0][i * channels] }
        } else {
            dst[0].update(from: src[0], count: frames)
        }
        out.frameLength = AVAudioFrameCount(frames)
        return out
    }

    /// A copy of `count` frames of `buffer` starting at `from`, in the
    /// buffer's own format.
    static func slice(_ buffer: AVAudioPCMBuffer, from: Int, count: Int) -> AVAudioPCMBuffer? {
        guard count > 0, from + count <= Int(buffer.frameLength),
              let out = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: AVAudioFrameCount(count)) else { return nil }
        let channels = Int(buffer.format.channelCount)
        let interleaved = buffer.format.isInterleaved
        if let src = buffer.floatChannelData, let dst = out.floatChannelData {
            if interleaved {
                dst[0].update(from: src[0] + from * channels, count: count * channels)
            } else {
                for ch in 0..<channels { dst[ch].update(from: src[ch] + from, count: count) }
            }
        } else if let src = buffer.int16ChannelData, let dst = out.int16ChannelData {
            if interleaved {
                dst[0].update(from: src[0] + from * channels, count: count * channels)
            } else {
                for ch in 0..<channels { dst[ch].update(from: src[ch] + from, count: count) }
            }
        } else if let src = buffer.int32ChannelData, let dst = out.int32ChannelData {
            if interleaved {
                dst[0].update(from: src[0] + from * channels, count: count * channels)
            } else {
                for ch in 0..<channels { dst[ch].update(from: src[ch] + from, count: count) }
            }
        } else {
            return nil
        }
        out.frameLength = AVAudioFrameCount(count)
        return out
    }
}

// MARK: - Playout accounting (D4: botIsSpeaking from the player node)

/// Counts buffers handed to the player node against their playback
/// completions. `isPlaying` is true exactly while at least one scheduled
/// buffer has not finished playing. `flush()` starts a new generation:
/// completions from buffers scheduled before the flush are ignored, so an
/// `interruption` frame (§3.2 findings) drops the queue without a race
/// against callbacks that are already in flight. Pure value type.
struct PlayoutQueue: Equatable {
    private(set) var generation: UInt64 = 0
    private(set) var outstanding: Int = 0

    var isPlaying: Bool { outstanding > 0 }

    /// Returns the generation the caller must echo back on completion.
    mutating func scheduled() -> UInt64 {
        outstanding += 1
        return generation
    }

    /// Returns true when this completion emptied the queue.
    @discardableResult
    mutating func completed(generation: UInt64) -> Bool {
        guard generation == self.generation, outstanding > 0 else { return false }
        outstanding -= 1
        return outstanding == 0
    }

    /// Returns true when the flush changed `isPlaying`.
    @discardableResult
    mutating func flush() -> Bool {
        let wasPlaying = isPlaying
        generation &+= 1
        outstanding = 0
        return wasPlaying
    }
}

/// Int16 little-endian mono/stereo PCM → a Float32 buffer the player node
/// can schedule, at the rate the frame declared. Pure.
enum PlayoutDecoder {
    static func buffer(fromInt16 data: Data, sampleRate: Double, channels: Int) -> AVAudioPCMBuffer? {
        guard channels >= 1, channels <= 2, sampleRate > 0,
              let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: AVAudioChannelCount(channels)) else { return nil }
        let frames = data.count / (MemoryLayout<Int16>.size * channels)
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)),
              let floats = buffer.floatChannelData else { return nil }
        data.withUnsafeBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            for frame in 0..<frames {
                for ch in 0..<channels {
                    floats[ch][frame] = Float(Int16(littleEndian: samples[frame * channels + ch])) / 32768
                }
            }
        }
        buffer.frameLength = AVAudioFrameCount(frames)
        return buffer
    }
}

// MARK: - Engine wrapper (D2, D3, D4; closure C6.2 level slots)

/// The AVAudioEngine half of the native transport, with no socket in it:
/// capture (Voice Processing I/O on) → `CaptureConverter` → `onCapturedPCM`
/// with 16 kHz Int16 mono; `play(...)` → `AVAudioPlayerNode` → main mixer
/// → output; `onPlayoutChanged` from the player node's own completions
/// (D4); latest-value level slots for both channels (C6.2). The engine
/// follows the system default devices and is rebuilt in place on
/// `AVAudioEngineConfigurationChange` (D3) — the player node survives it.
///
/// Every mutable member is confined to `queue`; the public read-only
/// slots are guarded by `slotLock` so C7 can read them from any thread.
/// Not exercised by XCTest (it needs a live input device and would raise
/// the microphone permission prompt inside the test runner); the §3.3
/// bench and §8 are its verification.
/// `@unchecked Sendable` on the same terms as `NativeAudioTransport`: every
/// mutable member is confined to `queue`, except the level slots and the
/// engine handles, which are guarded by `slotLock`. The audio thread (the
/// sink node's block) touches only preallocated buffers and those locks.
final class AudioEngineIO: @unchecked Sendable {
    /// 16 kHz Int16 mono bytes plus the level of the buffer they came from.
    /// Called on the engine's queue, hence @Sendable.
    var onCapturedPCM: (@Sendable (Data, AudioLevelSample) -> Void)?
    /// Every converted capture buffer, whether or not capture is enabled.
    /// The wake path needs audio precisely while the mic is muted (§3.5:
    /// a second AVAudioEngine on the same device gets silence and breaks
    /// this engine's echo cancellation), and it must be the processed
    /// signal, so it is taken from the same tap rather than a new engine.
    /// Every converted capture buffer, whether or not capture is enabled.
    /// The wake path needs audio precisely while the mic is muted (§3.5:
    /// a second AVAudioEngine on the same device gets silence and breaks
    /// this engine's echo cancellation), and it must be the processed
    /// signal, so it is taken from the same tap rather than a new engine.
    var onMonitorPCM: (@Sendable (Data) -> Void)?
    /// True while at least one scheduled playout buffer is unfinished.
    var onPlayoutChanged: (@Sendable (Bool) -> Void)?

    /// The engine is down and will not come back by itself: every retry of
    /// a device-change rebuild has failed. Nothing else reports this -- by
    /// the time it fires the configuration-change observer is gone, so no
    /// further device notification will arrive, and the socket above is
    /// still perfectly healthy. The transport turns it into a visible
    /// session failure rather than a silent one (D3).
    var onFailure: (@Sendable (Error) -> Void)?

    private let queue = DispatchQueue(label: "com.mortimer.jarviskit.audio-engine")
    private let slotLock = NSLock()
    private var inputSlot: AudioLevelSample?
    private var _captureTapFormat: AVAudioFormat?
    /// Held for the life of the engine: the sink node's block stops being
    /// called when the graph is torn down (D10).
    private var sinkCapture: SinkCapture?
    /// D10: RMS per ~20 ms of scheduled playout, positioned in the
    /// player's sample clock. Trimmed as the player passes each slice.
    private var playoutSlices: [(start: AVAudioFramePosition, end: AVAudioFramePosition, rms: Double)] = []
    /// Where the queue ends in the player's sample clock. That clock runs
    /// on while the player is started, silence included, so a slice's
    /// position must be anchored to where the player actually is when the
    /// buffer is scheduled — a running total of scheduled frames falls
    /// behind at the first gap and every slice is then read as already
    /// played (measured: the channel went permanently dark).
    private var lastScheduledEnd: AVAudioFramePosition = 0
    /// True only while `player` is attached to a live engine. Guarded by
    /// `slotLock`, and the detach in `stopLocked` happens inside that same
    /// critical section: `AVAudioNode.lastRenderTime` on a DETACHED node
    /// raises an Objective-C exception that Swift cannot catch, so a
    /// non-atomic check would still lose the race and kill the process
    /// (measured 2026-09-14 — an AirPod coming out terminated the app).
    private var playerAttached = false
    private var playoutHits = 0
    private var playoutMisses = 0
    private var lastTimelineReport: TimeInterval = 0
    private var playoutSlot: AudioLevelSample?

    private var engine: AVAudioEngine?
    private let player = AVAudioPlayerNode()
    private var playerFormat: AVAudioFormat?
    private var converter: CaptureConverter?
    private var captureEnabled = true
    private var playout = PlayoutQueue()
    private var configObserver: NSObjectProtocol?
    private(set) var voiceProcessing = false
    private(set) var rebuildCount = 0
    /// Set by the public `stop()`, cleared by the public `start()`. A
    /// rebuild retry scheduled before a stop must not resurrect the engine
    /// after it; `stopLocked` alone cannot say, because `startLocked` calls
    /// it on every rebuild.
    private var stoppedByOwner = false
    /// How long a device is given to come back before the session is failed:
    /// `rebuildAttempts` tries, `rebuildRetryGap` apart, on top of the
    /// settle wait inside each attempt.
    /// The device topology the running graph was built against; see the
    /// configuration-change observer.
    private var builtDeviceSignature = "-"
    private static let rebuildAttempts = 6
    private static let rebuildRetryGap: TimeInterval = 0.5
    /// Production always asks for Voice Processing I/O; the §3.3 bench
    /// builds a second engine with it off to measure what VPIO removes.
    let wantsVoiceProcessing: Bool

    init(voiceProcessing: Bool = true) {
        self.wantsVoiceProcessing = voiceProcessing
    }

    /// Latest input level (post-VPIO, what the bot hears), or nil before capture starts.
    var latestInputLevel: AudioLevelSample? { slotLock.withLock { inputSlot } }
    /// Latest level at the main mixer output (what the speaker plays), or nil.
    /// The level of the audio the player is rendering *now*. On the
    /// scheduled path this is looked up rather than measured after the
    /// fact, so it carries the render time itself (D10); on the tap
    /// fallback it is whatever the mixer tap last reported.
    var latestPlayoutLevel: AudioLevelSample? {
        guard JarvisFlags.captureUsesSinkNode else { return slotLock.withLock { playoutSlot } }
        // The whole read sits inside the lock, node time included: this
        // runs on the meter's 30 Hz timer while the engine can be torn
        // down on its own queue, and touching a detached node is fatal.
        return slotLock.withLock { () -> AudioLevelSample? in
            guard playerAttached,
                  let nodeTime = player.lastRenderTime, nodeTime.isSampleTimeValid,
                  let playerTime = player.playerTime(forNodeTime: nodeTime) else { return nil }
            let position = playerTime.sampleTime
            // Drop everything the player has already passed.
            if let index = playoutSlices.lastIndex(where: { $0.end <= position }), index >= 0 {
                playoutSlices.removeFirst(index + 1)
            }
            let slice = playoutSlices.first
            let hit = slice.map { $0.start <= position && position < $0.end } ?? false
            if hit { playoutHits += 1 } else { playoutMisses += 1 }
            let now = ProcessInfo.processInfo.systemUptime
            // The engine renders ahead of the speaker, so lastRenderTime can
            // sit in the future — and the accumulator refuses a measurement
            // time later than now, which is why a working timeline still
            // produced zero observations. The level is known before the
            // audio plays, so "now" is the honest stamp; the raw lead is
            // logged rather than hidden.
            let renderSeconds = AVAudioTime.seconds(forHostTime: nodeTime.hostTime)
            let lead = renderSeconds - now
            if now - lastTimelineReport >= 2.0, playoutHits + playoutMisses > 0 {
                lastTimelineReport = now
                engineLog.notice("playout timeline: \(self.playoutSlices.count, privacy: .public) slices queued, player at \(position, privacy: .public), \(self.playoutHits, privacy: .public) hits / \(self.playoutMisses, privacy: .public) misses, render time leads now by \(lead * 1000, format: .fixed(precision: 1), privacy: .public) ms")
                playoutHits = 0; playoutMisses = 0
            }
            guard hit, let slice else { return nil }
            // Stamp the level with when this slice STARTED playing, not
            // with the render time: the engine renders 12–20 ms ahead of
            // the wall clock, and the meter reads its own `now` before
            // asking for the level, so any stamp at or after the render
            // time is in that reader's future and the accumulator drops it
            // (measured: a timeline with 60 hits per 2 s recording zero
            // observations). The final clamp keeps it strictly in the past
            // for a reader whose `now` is microseconds older than ours.
            let sliceAge = Double(position - slice.start) / max(playerTime.sampleRate, 1)
            let measured = min(renderSeconds - sliceAge, now - 0.001)
            return AudioLevelSample(rms: slice.rms, hostTime: AVAudioTime.hostTime(forSeconds: measured))
        }
    }
    /// The input bus format the running tap was installed with (bench/diagnostics).
    var captureTapFormat: AVAudioFormat? { slotLock.withLock { _captureTapFormat } }
    var isPlaying: Bool { queue.sync { playout.isPlaying } }

    // MARK: Lifecycle

    /// Builds and starts the engine. Throws the engine's own error when the
    /// input device cannot be opened. `voiceProcessing` reports whether
    /// VPIO was accepted (it is required; a refusal is thrown, not hidden).
    func start() throws {
        try queue.sync {
            stoppedByOwner = false
            try startLocked()
        }
    }

    func stop() {
        queue.sync {
            stoppedByOwner = true
            stopLocked()
        }
    }

    /// Mute keeps the tap running (the VPIO reference path stays stable)
    /// and simply stops delivering frames — D6.
    func setCaptureEnabled(_ enabled: Bool) {
        queue.async { self.captureEnabled = enabled }
    }

    /// Schedules one frame of Int16 PCM at the rate the frame declares.
    /// The player node is (re)connected when the declared format changes.
    func play(pcm: Data, sampleRate: Double, channels: Int) {
        queue.async { self.playLocked(pcm: pcm, sampleRate: sampleRate, channels: channels) }
    }

    /// Drops every queued buffer — the client-side half of an
    /// `interruption` frame (§3.2 findings).
    func flushPlayout() {
        queue.async { self.flushLocked() }
    }

    // MARK: Queue-confined implementation

    /// Builds the graph the 2026-09-13 benches showed both starting and
    /// cancelling echo on this Mac (`macos/VPIOBench --probe`, `--channels`):
    ///
    /// - the hardware formats are read BEFORE `setVoiceProcessingEnabled`;
    ///   afterwards the input bus reports the mic array's raw layout (9 ch
    ///   on the MacBook Air) and the output bus 0 ch / 0 Hz, and a
    ///   `mainMixer → output` connection with `format: nil` inherits that
    ///   nothing and fails `kAUInitialize` (-10875);
    /// - the input node is NOT connected to anything: it is tapped with
    ///   `format: nil`, i.e. in whatever layout Voice Processing reports,
    ///   and channel 0 of each buffer is taken (the `--channels` bench
    ///   showed all nine channels identical, at the idle floor during
    ///   playback). Connecting the input node to the main mixer in a mono
    ///   format — the earlier shape — starts fine but the canceller then
    ///   leaves the playback in the tap at −2 dB, and Silero raises user
    ///   turns on it (built-in mic + speakers, quiet room);
    /// - `mainMixer → output` gets the hardware output format explicitly.
    private func startLocked(settleDeadline: TimeInterval = 1.0) throws {
        if engine != nil { stopLocked() }
        let engine = AVAudioEngine()
        #if os(macOS)
        // Before the graph is built: what the devices' I/O buffers are, and
        // a different size if JARVIS_AUDIO_IO_FRAMES asks for one. The
        // measured default here is 4800 frames — 100 ms — which is the
        // dominant term in every latency this client has (C7.5).
        AudioDeviceTuning.report()
        #endif
        // CoreAudio reports a half-built device for a moment after another
        // engine stops — measured 2026-09-13 in the bench, which starts and
        // stops engines back to back: input read "2 ch, 44100 Hz" (not this
        // mic at all) and output "0 ch, 0 Hz", and the start was refused.
        // The same window exists in the app on D3's device-change rebuild,
        // where refusing means the session drops and stays down. Wait for
        // the devices to settle instead of failing on the first read.
        let (hardwareInput, hardwareOutput) = try Self.settledFormats(
            input: { engine.inputNode.outputFormat(forBus: 0) },
            output: { engine.outputNode.outputFormat(forBus: 0) },
            deadline: settleDeadline)
        // VPIO must be set before the input node is used or the engine started.
        if wantsVoiceProcessing {
            try engine.inputNode.setVoiceProcessingEnabled(true)
            voiceProcessing = engine.inputNode.isVoiceProcessingEnabled
            guard voiceProcessing else { throw JarvisError.transport("Voice Processing I/O was not enabled on the input node") }
        } else {
            voiceProcessing = false
        }
        // The bus format after VPIO is what the tap delivers (9 ch / 48 kHz
        // on the MacBook Air mic array, 1 ch on AirPods); the converter
        // works on channel 0 of it.
        let tapFormat = engine.inputNode.outputFormat(forBus: 0)
        guard tapFormat.sampleRate > 0, tapFormat.channelCount > 0,
              let captureFormat = AVAudioFormat(standardFormatWithSampleRate: tapFormat.sampleRate, channels: 1),
              let outputFormat = AVAudioFormat(standardFormatWithSampleRate: hardwareOutput.sampleRate, channels: hardwareOutput.channelCount) else {
            throw JarvisError.transport("no graph formats for input \(tapFormat), output \(hardwareOutput)")
        }
        engine.attach(player)
        engine.connect(engine.mainMixerNode, to: engine.outputNode, format: outputFormat)
        try installTaps(on: engine, captureFormat: captureFormat)
        engine.prepare()
        do { try engine.start() } catch {
            // Say what the graph looked like: the bench and the app log both
            // need it to tell a permission refusal from a VPIO/device fault.
            removeTaps(from: engine)
            throw JarvisError.transport("audio engine start failed (\(error)); input \(engine.inputNode.outputFormat(forBus: 0)), output \(engine.outputNode.outputFormat(forBus: 0)), voice processing \(voiceProcessing)")
        }
        self.engine = engine
        #if os(macOS)
        builtDeviceSignature = AudioDeviceTuning.signature()
        #endif
        slotLock.withLock { playerAttached = true }
        configObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: nil) { [weak self] _ in
            // The signature is read HERE, on the notification, not inside
            // the rebuild: the question this answers is whether the device
            // topology actually differs from what the running graph was
            // built against, or whether this notification is our own
            // rebuild talking (2026-09-15: two hardware changes, six
            // rebuilds, no kAudioHardwareProperty change behind four).
            #if os(macOS)
            let now = AudioDeviceTuning.signature()
            let built = self?.builtDeviceSignature ?? "-"
            engineLog.notice("configuration change: devices now [\(now, privacy: .public)], graph built against [\(built, privacy: .public)]\(now == built ? " — NO DEVICE DIFFERENCE" : "", privacy: .public)")
            #endif
            self?.queue.async { self?.rebuildLocked() }
        }
        engineLog.notice("audio engine started: capture \(captureFormat.sampleRate, privacy: .public) Hz mono, channel 0 of \(tapFormat.channelCount, privacy: .public) (hardware \(hardwareInput.channelCount, privacy: .public) ch before VPIO), output \(outputFormat.sampleRate, privacy: .public) Hz \(outputFormat.channelCount, privacy: .public) ch, VPIO \(self.voiceProcessing ? "on" : "off", privacy: .public)")
    }

    /// Polls both device formats until they are usable, up to
    /// `deadline`. Pure enough to test: the reads are injected.
    static func settledFormats(input: () -> AVAudioFormat, output: () -> AVAudioFormat,
                               deadline: TimeInterval = 1.0, step: TimeInterval = 0.05,
                               sleep: (TimeInterval) -> Void = { Thread.sleep(forTimeInterval: $0) }
    ) throws -> (AVAudioFormat, AVAudioFormat) {
        var waited: TimeInterval = 0
        var lastInput = input(), lastOutput = output()
        while waited <= deadline {
            if lastInput.sampleRate > 0, lastOutput.sampleRate > 0, lastOutput.channelCount > 0 {
                if waited > 0 {
                    engineLog.notice("audio devices settled after \(waited * 1000, format: .fixed(precision: 0), privacy: .public) ms")
                }
                return (lastInput, lastOutput)
            }
            sleep(step)
            waited += step
            lastInput = input(); lastOutput = output()
        }
        throw JarvisError.transport("""
            no audio devices after \(String(format: "%.1f", deadline))s: \
            input \(lastInput), output \(lastOutput)
            """)
    }

    private func installTaps(on engine: AVAudioEngine, captureFormat: AVAudioFormat) throws {
        guard let converter = CaptureConverter(inputFormat: captureFormat) else {
            throw JarvisError.transport("no capture converter for \(captureFormat)")
        }
        self.converter = converter
        let inputFormat = engine.inputNode.outputFormat(forBus: 0)
        slotLock.withLock { _captureTapFormat = inputFormat }
        let inputCadence = TapCadence(label: "input")
        // One handler for both capture paths: everything after the copy is
        // identical, so the flag changes only how audio is delivered.
        let handle: @Sendable (AVAudioPCMBuffer, UInt64, Int, Int) -> Void = { [weak self] buffer, hostTime, rawFrames, rawChannels in
            guard let self else { return }
            let level = AudioLevelSample(rms: LevelMeter.rms(of: buffer), hostTime: hostTime)
            inputCadence.record(frameLength: rawFrames, sampleRate: inputFormat.sampleRate,
                                channels: rawChannels, bufferSeconds: level.seconds)
            self.slotLock.withLock { self.inputSlot = level }
            let frames = Int(buffer.frameLength)
            // Copy off the audio thread's buffer before the ring wraps.
            // `nonisolated(unsafe)`: AVAudioPCMBuffer is not Sendable, but
            // this copy has exactly one owner — made here, read once on
            // `queue`, referenced nowhere else.
            nonisolated(unsafe) let owned = CaptureConverter.slice(buffer, from: 0, count: frames)
            self.queue.async {
                let monitor = self.onMonitorPCM
                guard self.captureEnabled || monitor != nil, let owned else { return }
                guard let data = self.converter?.convert(owned), !data.isEmpty else { return }
                monitor?(data)
                // With a monitor attached (the wake path) conversion runs
                // while muted too, which also keeps the resampler's
                // history continuous across a mute toggle.
                if self.captureEnabled { self.onCapturedPCM?(data, level) }
            }
        }
        if JarvisFlags.captureUsesSinkNode,
           let sink = SinkCapture(inputFormat: inputFormat,
                                  deliver: { buffer, hostTime in
                                      handle(buffer, hostTime, Int(buffer.frameLength), Int(inputFormat.channelCount))
                                  }) {
            engine.attach(sink.node)
            engine.connect(engine.inputNode, to: sink.node, format: nil)
            sinkCapture = sink
            engineLog.notice("capture: sink node (render quantum), input \(inputFormat, privacy: .public)")
        } else {
            // Rollback path (JARVIS_AUDIO_CAPTURE=tap): 100 ms buffers.
            engine.inputNode.installTap(onBus: 0, bufferSize: 1024, format: nil) { raw, time in
                guard let buffer = CaptureConverter.firstChannel(of: raw) else { return }
                handle(buffer, time.hostTime, Int(raw.frameLength), Int(raw.format.channelCount))
            }
            engineLog.notice("capture: input tap (JARVIS_AUDIO_CAPTURE=tap)")
        }
        // Playout metering (D10). The mixer tap has the same 100 ms
        // problem, and a sink node cannot fix it here: a sink is driven by
        // the input hardware, so hung off the mixer nothing ever pulls it
        // and it delivered exactly zero buffers when tried. But playout
        // needs no tap at all — this client schedules every buffer, so the
        // level is known before the audio reaches the speaker. The levels
        // go into a timeline in the player's own sample clock, and the
        // meter asks the player where it is (`playerTime`) when it reads.
        // Zero added latency, and it cannot disagree with what is audible.
        if !JarvisFlags.captureUsesSinkNode {
            let playoutCadence = TapCadence(label: "playout")
            engine.mainMixerNode.installTap(onBus: 0, bufferSize: 1024, format: nil) { [weak self] buffer, time in
                guard let self else { return }
                let level = AudioLevelSample(rms: LevelMeter.rms(of: buffer), hostTime: time.hostTime)
                playoutCadence.record(frameLength: Int(buffer.frameLength), sampleRate: buffer.format.sampleRate,
                                      channels: Int(buffer.format.channelCount), bufferSeconds: level.seconds)
                self.slotLock.withLock { self.playoutSlot = level }
            }
            engineLog.notice("playout meter: main-mixer tap (JARVIS_AUDIO_CAPTURE=tap)")
        } else {
            engineLog.notice("playout meter: scheduled levels on the player clock")
        }
    }

    private func removeTaps(from engine: AVAudioEngine) {
        if let sinkCapture {
            engine.detach(sinkCapture.node)
            self.sinkCapture = nil
        } else {
            engine.inputNode.removeTap(onBus: 0)
        }
        if !JarvisFlags.captureUsesSinkNode { engine.mainMixerNode.removeTap(onBus: 0) }
    }

    private func stopLocked() {
        if let configObserver { NotificationCenter.default.removeObserver(configObserver) }
        configObserver = nil
        if let engine {
            removeTaps(from: engine)
            player.stop()
            engine.stop()
            // Atomic with the flag, not merely before it: a reader that had
            // already passed the check would otherwise still be inside
            // lastRenderTime when the node lost its engine.
            slotLock.withLock {
                playerAttached = false
                engine.detach(player)
            }
        }
        engine = nil
        converter = nil
        playerFormat = nil
        if playout.flush() { onPlayoutChanged?(false) }
        lastScheduledEnd = 0
        slotLock.withLock { inputSlot = nil; playoutSlot = nil; playoutSlices.removeAll(); _captureTapFormat = nil }
    }

    /// D3: a device change (AirPods arriving, the default output moving)
    /// stops the engine and may change both hardware formats, so the graph
    /// is built again from scratch through `startLocked` — the same player
    /// node object is re-attached, so the transport's reference and the
    /// declared playout format survive; whatever was queued in the old
    /// engine is gone (a short gap mid-sentence, then the stream resumes),
    /// which `playout.flush()` reports as not-playing.
    ///
    /// A failed attempt is not the end of it. `startLocked` has by then
    /// stopped the old engine, which also removed the configuration-change
    /// observer, so nothing will ever call this again on its own: without a
    /// retry the session stays up with a dead engine. Retries are scheduled
    /// on `queue` rather than slept so `stop()` is not stuck behind them,
    /// and only the first attempt pays the full settle wait.
    private func rebuildLocked(attempt: Int = 1, keeping carried: (AVAudioFormat?, Bool)? = nil) {
        guard !stoppedByOwner else { return }
        guard attempt > 1 || engine != nil else { return }
        if attempt == 1 { rebuildCount += 1 }
        let (keptFormat, wasEnabled) = carried ?? (playerFormat, captureEnabled)
        do {
            try startLocked(settleDeadline: attempt == 1 ? 1.0 : 0.2)  // stops the old engine first
            captureEnabled = wasEnabled
            if let keptFormat, let engine {
                engine.connect(player, to: engine.mainMixerNode, format: keptFormat)
                playerFormat = keptFormat
            }
            engineLog.notice("audio engine rebuilt after configuration change (#\(self.rebuildCount, privacy: .public), attempt \(attempt, privacy: .public))")
        } catch {
            guard attempt < Self.rebuildAttempts else {
                // String(describing:) not localizedDescription: a JarvisError
                // renders as "JarvisKit.JarvisError error 1" through the
                // latter, which is how the one retried rebuild on
                // 2026-09-15 came out unexplained in the log.
                engineLog.error("audio engine rebuild failed after \(attempt, privacy: .public) attempts: \(String(describing: error), privacy: .public)")
                onFailure?(JarvisError.transport("audio device lost: \(error.localizedDescription)"))
                return
            }
            engineLog.error("audio engine rebuild attempt \(attempt, privacy: .public) failed (\(String(describing: error), privacy: .public)); retrying")
            queue.asyncAfter(deadline: .now() + Self.rebuildRetryGap) { [weak self] in
                self?.rebuildLocked(attempt: attempt + 1, keeping: (keptFormat, wasEnabled))
            }
        }
    }

    private func playLocked(pcm: Data, sampleRate: Double, channels: Int) {
        guard let engine, let buffer = PlayoutDecoder.buffer(fromInt16: pcm, sampleRate: sampleRate, channels: channels) else { return }
        if playerFormat == nil || playerFormat!.sampleRate != buffer.format.sampleRate
            || playerFormat!.channelCount != buffer.format.channelCount {
            player.stop()
            resetPlayoutTimeline()
            engine.connect(player, to: engine.mainMixerNode, format: buffer.format)
            playerFormat = buffer.format
        }
        recordPlayoutLevels(of: buffer)
        let wasPlaying = playout.isPlaying
        let generation = playout.scheduled()
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            guard let self else { return }
            self.queue.async {
                if self.playout.completed(generation: generation) { self.onPlayoutChanged?(false) }
            }
        }
        if !player.isPlaying { player.play() }
        if !wasPlaying { onPlayoutChanged?(true) }
    }

    /// ~20 ms slices, so the wave has something to move to within a
    /// syllable rather than per scheduled chunk.
    private func recordPlayoutLevels(of buffer: AVAudioPCMBuffer) {
        let frames = Int(buffer.frameLength)
        guard frames > 0 else { return }
        // The queue plays back to back from wherever the player is now.
        let base = max(currentPlayerPosition() ?? 0, lastScheduledEnd)
        let sliceFrames = max(1, Int(buffer.format.sampleRate * 0.020))
        var offset = 0
        var slices: [(AVAudioFramePosition, AVAudioFramePosition, Double)] = []
        while offset < frames {
            let count = min(sliceFrames, frames - offset)
            if let slice = CaptureConverter.slice(buffer, from: offset, count: count) {
                let start = base + AVAudioFramePosition(offset)
                slices.append((start, start + AVAudioFramePosition(count), LevelMeter.rms(of: slice)))
            }
            offset += count
        }
        lastScheduledEnd = base + AVAudioFramePosition(frames)
        slotLock.withLock { playoutSlices.append(contentsOf: slices) }
    }

    private func currentPlayerPosition() -> AVAudioFramePosition? {
        // Same rule as `latestPlayoutLevel`: never ask a detached node for
        // its render time. This one runs on the engine queue, where the
        // engine is normally alive, but the guard is the invariant and not
        // a property of the caller.
        slotLock.withLock { () -> AVAudioFramePosition? in
            guard playerAttached,
                  let nodeTime = player.lastRenderTime, nodeTime.isSampleTimeValid,
                  let playerTime = player.playerTime(forNodeTime: nodeTime) else { return nil }
            return playerTime.sampleTime
        }
    }

    /// The player's sample clock restarts with the player, so the timeline
    /// must too — otherwise the meter reads the previous utterance.
    private func resetPlayoutTimeline() {
        lastScheduledEnd = 0
        slotLock.withLock { playoutSlices.removeAll() }
    }

    private func flushLocked() {
        let changed = playout.flush()
        player.stop()
        resetPlayoutTimeline()
        if playerFormat != nil, engine?.isRunning == true { player.play() }
        if changed { onPlayoutChanged?(false) }
    }
}
