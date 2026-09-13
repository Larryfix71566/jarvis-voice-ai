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

/// The sidecar socket, as a seam (the shape `NativeAudioTransport` uses
/// for `NativeSocket`): production is a URLSession WebSocket to the wake
/// sidecar, and the tests substitute a collector so the framing and the
/// mic-contention rules are provable without a sidecar or a live mic.
protocol WakeSocket: AnyObject {
    var onText: (@Sendable (String) -> Void)? { get set }
    var onFailure: (@Sendable (Error) -> Void)? { get set }
    func open()
    func send(_ data: Data)
    func close()
}

final class URLSessionWakeSocket: WakeSocket {
    var onText: (@Sendable (String) -> Void)?
    var onFailure: (@Sendable (Error) -> Void)?
    private let url: URL
    private var session: URLSession?
    private var task: URLSessionWebSocketTask?

    init(url: URL) { self.url = url }

    func open() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        let session = URLSession(configuration: configuration)
        let task = session.webSocketTask(with: url)
        self.session = session
        self.task = task
        task.resume()
        receiveLoop(task)
    }

    func send(_ data: Data) {
        task?.send(.data(data)) { error in
            if let error { wakeLog.error("wake socket send failed: \(error.localizedDescription, privacy: .public)") }
        }
    }

    func close() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        session = nil
    }

    /// Failure ends the loop (the owner reports it as unavailable); the
    /// sidecar only ever sends text (server.py:84-85).
    private func receiveLoop(_ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(.string(let text)):
                self.onText?(text)
                self.receiveLoop(task)
            case .success:
                self.receiveLoop(task)
            case .failure(let error):
                self.onFailure?(error)
            }
        }
    }
}

/// Where the wake listener's audio comes from. `.ownEngine` is the
/// WebRTC path's shape (the listener opens its own AVAudioEngine, which
/// WebRTC's ADM tolerates). `.external` is the native path, measured
/// 2026-09-13: a second AVAudioEngine on the same input device receives
/// silence on the built-in mic AND costs the transport's engine its echo
/// cancellation (38.4 dB of reduction becomes 0.7 dB, and Silero raises
/// nine user turns on the bot's own playback), so the listener is fed
/// from the transport's already-processed tap through `feed(_:)` instead.
enum WakeAudioSource: Sendable, Equatable {
    case ownEngine
    case external
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
    private(set) var source: WakeAudioSource = .ownEngine
    private let makeSocket: (URL) -> WakeSocket

    #if os(macOS)
    private var engine: AVAudioEngine?
    private var converter: AVAudioConverter?
    private var socket: WakeSocket?
    private var chimePlayer: ChimePlayer?
    /// True while this listener owns an AVAudioEngine of its own — false
    /// on the native path, where audio arrives through `feed(_:)`.
    var isUsingOwnEngine: Bool { engine != nil }
    #endif

    init(config: JarvisConfig,
         makeSocket: @escaping (URL) -> WakeSocket = { URLSessionWakeSocket(url: $0) }) {
        self.config = config
        self.makeSocket = makeSocket
    }

    private func setAvailability(_ a: WakeAvailability) {
        availability = a
        onAvailabilityChange?(a)
    }

    /// N10's runtime availability check, run by JarvisClient on connect.
    /// Without this the host's wake toggle deadlocks: availability was
    /// only ever determined by start(), which only ran from the toggle,
    /// which was disabled until availability was true. A ping over a
    /// short-lived socket answers the question the plan's curl probe
    /// answers (§3 N10) without user action. Bounded at 3 s, mirroring
    /// the probe's --max-time.
    func probeAvailability() async {
        guard JarvisFlags.wakeWordEnabled else {
            setAvailability(.unavailable(reason: "disabled by JARVIS_WAKEWORD_ENABLED"))
            return
        }
        #if os(iOS)
        setAvailability(.unavailable(reason: "wake word is macOS-only in this release"))
        #else
        let task = URLSession.shared.webSocketTask(with: config.wakeWordURL)
        task.resume()
        let reachable: Bool = await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                await withCheckedContinuation { continuation in
                    task.sendPing { error in continuation.resume(returning: error == nil) }
                }
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                return false
            }
            let first = await group.next() ?? false
            group.cancelAll()
            return first
        }
        task.cancel(with: .goingAway, reason: nil)
        setAvailability(reachable ? .available : .unavailable(reason: "wake sidecar not reachable at \(config.wakeWordURL)"))
        #endif
    }

    /// `source` decides who owns the microphone; the owner
    /// (JarvisClient) picks it from the live transport.
    func start(source: WakeAudioSource = .ownEngine) async {
        self.source = source
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
        if source == .ownEngine { startCapture() }
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

    /// The native path's audio entry point: 16 kHz Int16 mono frames
    /// from the transport's processed capture tap
    /// (`CaptureConverter.wireSampleRate` == `JarvisTuning.wakeSampleRate`,
    /// so no conversion happens here). Ignored unless this listener was
    /// started with `.external`, so audio can never arrive twice.
    func feed(_ pcm: Data) {
        guard source == .external else { return }
        handleCapturedPCM(pcm)
    }

    private func handleCapturedPCM(_ data: Data) {
        guard isRunning, !isPaused else { return }
        let frames = framer.append(data)
        for frame in frames { socket?.send(frame) }
    }

    private func startSocket() {
        let socket = makeSocket(config.wakeWordURL)
        socket.onText = { [weak self] text in
            guard let data = text.data(using: .utf8),
                  let event = WakeFrameDecoder.decodeWakeEvent(from: data) else { return }
            Task { @MainActor in self?.handleWake(event) }
        }
        socket.onFailure = { [weak self] error in
            // Describe it here: only Sendable values cross into the actor.
            let reason = "wake socket error: \(error.localizedDescription)"
            Task { @MainActor in
                self?.setAvailability(.unavailable(reason: reason))
                self?.isRunning = false
            }
        }
        self.socket = socket
        socket.open()
        setAvailability(.available)
    }

    private func stopSocket() {
        socket?.onText = nil
        socket?.onFailure = nil
        socket?.close()
        socket = nil
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
