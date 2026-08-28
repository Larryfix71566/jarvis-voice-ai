import Foundation
#if os(macOS)
import AVFoundation
#endif
import os

private let wakeLog = Logger(subsystem: "com.mortimer.jarviskit", category: "wakeword")

/// Decoded from the sidecar's inbound text frame {"type":"wake","model":…,"score":…}.
public struct WakeEvent: Sendable, Equatable {
    public let model: String
    public let score: Double
}

/// Accumulates raw PCM bytes and emits exactly `JarvisTuning.wakeFrameBytes`
/// (2560, server.py:37-38 = 1280 samples x 2 bytes) sized chunks, and
/// NEVER a partial frame — the remainder stays buffered for the next
/// append. Pure, side-effect-free, and independently unit-testable
/// (§7.6) without a real audio engine or socket.
struct WakeFramer {
    private var buffer = Data()

    mutating func append(_ data: Data) -> [Data] {
        buffer.append(data)
        var frames: [Data] = []
        while buffer.count >= JarvisTuning.wakeFrameBytes {
            frames.append(buffer.prefix(JarvisTuning.wakeFrameBytes))
            buffer.removeFirst(JarvisTuning.wakeFrameBytes)
        }
        return frames
    }
}

/// Decodes the sidecar's inbound TEXT frames (server.py:84-85 ignores
/// binary/other text). Non-"wake" frames decode to nil without throwing
/// (wakeWord.ts:118 ignores everything else).
enum WakeFrameDecoder {
    static func decodeWakeEvent(from data: Data) -> WakeEvent? {
        guard let root = try? JSONDecoder().decode([String: JSONValue].self, from: data),
              root["type"]?.stringValue == "wake" else { return nil }
        guard let model = root["model"]?.stringValue, let score = root["score"]?.doubleValue else { return nil }
        return WakeEvent(model: model, score: score)
    }
}

/// The state WakeWordListener reports to JarvisClient.
public enum WakeAvailability: Sendable, Equatable {
    case unknown
    case available
    case unavailable(reason: String)
}

/// §5 step 10 (N10). Both W1 and W2 code paths are written unconditionally
/// — the choice between them is a RUNTIME probe Larry runs (§3 N10, §8
/// V8), not a decision this implementer makes blind.
///
/// Mic-contention rule (review F13), enforced by the OWNER (JarvisClient),
/// not here: this listener runs only while `state == .connected` AND
/// `micEnabled == false`, and is paused (not torn down) for the duration
/// of `botIsSpeaking`. This type exposes `start()`/`stop()`/`setPaused(_:)`
/// so the owner can drive that policy; it does not decide it.
@MainActor
final class WakeWordListener {
    private let config: JarvisConfig
    private(set) var availability: WakeAvailability = .unknown
    private var isRunning = false
    private var isPaused = false
    private var framer = WakeFramer()

    var onWake: (() -> Void)?
    var onAvailabilityChange: ((WakeAvailability) -> Void)?

    #if os(macOS)
    private var engine: AVAudioEngine?
    private var converter: AVAudioConverter?
    private var webSocketTask: URLSessionWebSocketTask?
    private var chimePlayer: ChimePlayer?
    #endif

    init(config: JarvisConfig) {
        self.config = config
    }

    private func setAvailability(_ a: WakeAvailability) {
        availability = a
        onAvailabilityChange?(a)
    }

    func start() async {
        guard JarvisFlags.wakeWordEnabled else {
            setAvailability(.unavailable(reason: "disabled by JARVIS_WAKEWORD_ENABLED"))
            return
        }
        #if os(iOS)
        // N10 rule 3: .voiceChat's VPIO routing does not permit a second
        // AVAudioEngine input tap. T1.5 owns the iOS wake path.
        setAvailability(.unavailable(reason: "wake word is macOS-only in this release"))
        #else
        guard !isRunning else { return }
        isRunning = true
        isPaused = false
        startSocket()
        startCapture()
        #endif
    }

    func stop() async {
        guard isRunning || availability == .unknown else { return }
        isRunning = false
        isPaused = false
        #if os(macOS)
        stopCapture()
        stopSocket()
        #endif
    }

    /// N10 rule 4: paused (not stopped) for the duration of botIsSpeaking
    /// — the wake tap is NOT echo-cancelled, so an un-paused listener
    /// would score the bot's own TTS.
    func setPaused(_ paused: Bool) {
        isPaused = paused
    }

    #if os(macOS)
    private func startCapture() {
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16, sampleRate: JarvisTuning.wakeSampleRate,
            channels: 1, interleaved: true
        ) else {
            setAvailability(.unavailable(reason: "could not construct 16kHz mono format"))
            return
        }
        guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            setAvailability(.unavailable(reason: "AVAudioConverter unavailable for this input format"))
            return
        }
        self.converter = converter

        input.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
            guard let self else { return }
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * (targetFormat.sampleRate / inputFormat.sampleRate) + 16)
            guard let outBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else { return }
            var error: NSError?
            let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
                outStatus.pointee = .haveData
                return buffer
            }
            converter.convert(to: outBuffer, error: &error, withInputFrom: inputBlock)
            if let error { wakeLog.error("wake converter error: \(error.localizedDescription, privacy: .public)"); return }
            guard let int16Data = outBuffer.int16ChannelData else { return }
            let frameCount = Int(outBuffer.frameLength)
            let byteCount = frameCount * MemoryLayout<Int16>.size
            let data = Data(bytes: int16Data[0], count: byteCount)
            Task { @MainActor [weak self] in self?.handleCapturedPCM(data) }
        }

        do {
            try engine.start()
            self.engine = engine
        } catch {
            setAvailability(.unavailable(reason: "AVAudioEngine failed to start: \(error.localizedDescription)"))
        }
    }

    private func stopCapture() {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        converter = nil
        framer = WakeFramer()
    }

    private func handleCapturedPCM(_ data: Data) {
        guard isRunning, !isPaused else { return }
        let frames = framer.append(data)
        for frame in frames {
            webSocketTask?.send(.data(frame)) { error in
                if let error { wakeLog.error("wake socket send failed: \(error.localizedDescription, privacy: .public)") }
            }
        }
    }

    private func startSocket() {
        let task = URLSession.shared.webSocketTask(with: config.wakeWordURL)
        webSocketTask = task
        task.resume()
        setAvailability(.available)
        receiveNext()
    }

    private func stopSocket() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
    }

    private func receiveNext() {
        webSocketTask?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let error):
                Task { @MainActor in
                    self.setAvailability(.unavailable(reason: "wake socket error: \(error.localizedDescription)"))
                    self.isRunning = false
                }
                return
            case .success(let message):
                if case .string(let text) = message, let data = text.data(using: .utf8),
                   let event = WakeFrameDecoder.decodeWakeEvent(from: data) {
                    Task { @MainActor in self.handleWake(event) }
                }
            }
            Task { @MainActor in self.receiveNext() }
        }
    }

    private func handleWake(_ event: WakeEvent) {
        wakeLog.debug("wake event: model=\(event.model, privacy: .public) score=\(event.score)")
        playChime()
        onWake?()
    }

    private func playChime() {
        let player = ChimePlayer()
        chimePlayer = player
        player.play()
    }
    #endif
}

#if os(macOS)
/// Exact parity with wakeWord.ts:57-82 — 880 Hz at t+0, 1320 Hz at t+0.12s,
/// each gain 0.18 decaying exponentially to 0.001 over 0.25s, whole thing
/// torn down at 0.8s. Synthesised with AVAudioEngine + two
/// AVAudioPlayerNodes, no asset file.
final class ChimePlayer {
    private let engine = AVAudioEngine()
    private var nodes: [AVAudioPlayerNode] = []

    func play() {
        let format = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 1)!
        // One player node per tone; the tones themselves are scheduled
        // in the second loop below, which needs the node/tone pairing.
        for _ in JarvisTuning.chimeTones {
            let node = AVAudioPlayerNode()
            engine.attach(node)
            engine.connect(node, to: engine.mainMixerNode, format: format)
            nodes.append(node)
        }
        do { try engine.start() } catch {
            return
        }
        for (index, tone) in JarvisTuning.chimeTones.enumerated() {
            let node = nodes[index]
            let buffer = Self.tone(frequency: tone.frequency, format: format)
            DispatchQueue.main.asyncAfter(deadline: .now() + tone.startOffset) {
                node.scheduleBuffer(buffer, at: nil, options: [])
                node.play()
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + JarvisTuning.chimeTeardown) { [weak self] in
            self?.engine.stop()
        }
    }

    private static func tone(frequency: Double, format: AVAudioFormat) -> AVAudioPCMBuffer {
        let duration = JarvisTuning.chimeDecayDuration
        let sampleRate = format.sampleRate
        let frameCount = AVAudioFrameCount(duration * sampleRate)
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount)!
        buffer.frameLength = frameCount
        guard let channel = buffer.floatChannelData?[0] else { return buffer }
        let gain = JarvisTuning.chimeGain
        let floor = JarvisTuning.chimeDecayFloor
        // Exponential decay from `gain` to `floor` over `duration`.
        let decayRate = log(floor / gain) / duration
        for frame in 0..<Int(frameCount) {
            let t = Double(frame) / sampleRate
            let envelope = gain * exp(decayRate * t)
            let sample = sin(2.0 * .pi * frequency * t) * envelope
            channel[frame] = Float(sample)
        }
        return buffer
    }
}
#endif
