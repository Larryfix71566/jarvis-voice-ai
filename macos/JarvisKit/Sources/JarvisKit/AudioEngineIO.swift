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
final class AudioEngineIO {
    /// 16 kHz Int16 mono bytes plus the level of the buffer they came from.
    /// Called on the engine's queue, hence @Sendable.
    var onCapturedPCM: (@Sendable (Data, AudioLevelSample) -> Void)?
    /// True while at least one scheduled playout buffer is unfinished.
    var onPlayoutChanged: (@Sendable (Bool) -> Void)?

    private let queue = DispatchQueue(label: "com.mortimer.jarviskit.audio-engine")
    private let slotLock = NSLock()
    private var inputSlot: AudioLevelSample?
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
    /// Production always asks for Voice Processing I/O; the §3.3 bench
    /// builds a second engine with it off to measure what VPIO removes.
    let wantsVoiceProcessing: Bool

    init(voiceProcessing: Bool = true) {
        self.wantsVoiceProcessing = voiceProcessing
    }

    /// Latest input level (post-VPIO, what the bot hears), or nil before capture starts.
    var latestInputLevel: AudioLevelSample? { slotLock.withLock { inputSlot } }
    /// Latest level at the main mixer output (what the speaker plays), or nil.
    var latestPlayoutLevel: AudioLevelSample? { slotLock.withLock { playoutSlot } }
    var isPlaying: Bool { queue.sync { playout.isPlaying } }

    // MARK: Lifecycle

    /// Builds and starts the engine. Throws the engine's own error when the
    /// input device cannot be opened. `voiceProcessing` reports whether
    /// VPIO was accepted (it is required; a refusal is thrown, not hidden).
    func start() throws {
        try queue.sync { try startLocked() }
    }

    func stop() {
        queue.sync { stopLocked() }
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

    private func startLocked() throws {
        if engine != nil { stopLocked() }
        let engine = AVAudioEngine()
        // VPIO must be set before the input node is used or the engine started.
        if wantsVoiceProcessing {
            try engine.inputNode.setVoiceProcessingEnabled(true)
            voiceProcessing = engine.inputNode.isVoiceProcessingEnabled
            guard voiceProcessing else { throw JarvisError.transport("Voice Processing I/O was not enabled on the input node") }
        } else {
            voiceProcessing = false
        }
        engine.attach(player)
        // Pull the output side up so the engine has a render path even
        // before the first playout frame declares its format.
        engine.connect(engine.mainMixerNode, to: engine.outputNode, format: nil)
        try installTaps(on: engine)
        engine.prepare()
        try engine.start()
        self.engine = engine
        configObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: nil) { [weak self] _ in
            self?.queue.async { self?.rebuildLocked() }
        }
        engineLog.notice("audio engine started: input \(engine.inputNode.outputFormat(forBus: 0).sampleRate, privacy: .public) Hz, VPIO \(self.voiceProcessing ? "on" : "off", privacy: .public)")
    }

    private func installTaps(on engine: AVAudioEngine) throws {
        let inputFormat = engine.inputNode.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, let converter = CaptureConverter(inputFormat: inputFormat) else {
            throw JarvisError.transport("no capture converter for input format \(inputFormat)")
        }
        self.converter = converter
        engine.inputNode.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, time in
            guard let self else { return }
            let level = AudioLevelSample(rms: LevelMeter.rms(of: buffer), hostTime: time.hostTime)
            self.slotLock.withLock { self.inputSlot = level }
            self.queue.async {
                guard self.captureEnabled, let data = self.converter?.convert(buffer), !data.isEmpty else { return }
                self.onCapturedPCM?(data, level)
            }
        }
        engine.mainMixerNode.installTap(onBus: 0, bufferSize: 1024, format: nil) { [weak self] buffer, time in
            guard let self else { return }
            let level = AudioLevelSample(rms: LevelMeter.rms(of: buffer), hostTime: time.hostTime)
            self.slotLock.withLock { self.playoutSlot = level }
        }
    }

    private func removeTaps(from engine: AVAudioEngine) {
        engine.inputNode.removeTap(onBus: 0)
        engine.mainMixerNode.removeTap(onBus: 0)
    }

    private func stopLocked() {
        if let configObserver { NotificationCenter.default.removeObserver(configObserver) }
        configObserver = nil
        if let engine {
            removeTaps(from: engine)
            player.stop()
            engine.stop()
            engine.detach(player)
        }
        engine = nil
        converter = nil
        playerFormat = nil
        if playout.flush() { onPlayoutChanged?(false) }
        slotLock.withLock { inputSlot = nil; playoutSlot = nil }
    }

    /// D3: a device change stops the engine; rebuild the graph in place
    /// with the new input format and keep the player node and its format.
    private func rebuildLocked() {
        guard let engine else { return }
        rebuildCount += 1
        removeTaps(from: engine)
        do {
            try installTaps(on: engine)
            if let playerFormat, engine.attachedNodes.contains(player) {
                engine.connect(player, to: engine.mainMixerNode, format: playerFormat)
            }
            engine.connect(engine.mainMixerNode, to: engine.outputNode, format: nil)
            engine.prepare()
            try engine.start()
            if playerFormat != nil, playout.isPlaying { player.play() }
            engineLog.notice("audio engine rebuilt after configuration change (#\(self.rebuildCount, privacy: .public)): input \(engine.inputNode.outputFormat(forBus: 0).sampleRate, privacy: .public) Hz")
        } catch {
            engineLog.error("audio engine rebuild failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func playLocked(pcm: Data, sampleRate: Double, channels: Int) {
        guard let engine, let buffer = PlayoutDecoder.buffer(fromInt16: pcm, sampleRate: sampleRate, channels: channels) else { return }
        if playerFormat == nil || playerFormat!.sampleRate != buffer.format.sampleRate
            || playerFormat!.channelCount != buffer.format.channelCount {
            player.stop()
            engine.connect(player, to: engine.mainMixerNode, format: buffer.format)
            playerFormat = buffer.format
        }
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

    private func flushLocked() {
        let changed = playout.flush()
        player.stop()
        if playerFormat != nil, engine?.isRunning == true { player.play() }
        if changed { onPlayoutChanged?(false) }
    }
}
