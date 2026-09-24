import Foundation
import os

private let nativeLog = Logger(subsystem: "com.mortimer.jarviskit", category: "native-transport")

/// Status spec P7 (reconnect instrumentation, logging only): the close code
/// and reason wherever the WebSocket task ends.
private let transportLog = Logger(subsystem: "com.mortimer.host", category: "transport")

private func logWebSocketEnd(_ event: String, code: URLSessionWebSocketTask.CloseCode, reason: Data?) {
    let text = reason.map { String(String(decoding: $0, as: UTF8.self).prefix(120)) } ?? ""
    transportLog.notice("websocket \(event, privacy: .public): closeCode=\(code.rawValue, privacy: .public) reason=\(text, privacy: .public)")
}

// MARK: - Seams (plan §7: lifecycle tests run against a stub socket and a stub engine)

/// One WebSocket to the bot. The real one wraps `URLSessionWebSocketTask`;
/// tests script open/close/messages directly.
protocol NativeSocket: AnyObject {
    var onOpen: (@Sendable () -> Void)? { get set }
    var onClose: (@Sendable (Error?) -> Void)? { get set }
    var onMessage: (@Sendable (Data) -> Void)? { get set }
    func open()
    func send(_ data: Data, completion: @escaping (Error?) -> Void)
    func ping(completion: @escaping (Error?) -> Void)
    func close()
}

/// The capture/playout half (`AudioEngineIO` in production).
protocol NativeAudioIO: AnyObject {
    var onCapturedPCM: (@Sendable (Data, AudioLevelSample) -> Void)? { get set }
    var onMonitorPCM: (@Sendable (Data) -> Void)? { get set }
    var onPlayoutChanged: (@Sendable (Bool) -> Void)? { get set }
    var onFailure: (@Sendable (Error) -> Void)? { get set }
    func start() throws
    func stop()
    func setCaptureEnabled(_ enabled: Bool)
    func play(pcm: Data, sampleRate: Double, channels: Int)
    func flushPlayout()
}

/// The audio seam is queue-confined by its implementations. This small box
/// makes that ownership explicit when the synchronous start is handed to a
/// background DispatchQueue under Swift 6's Sendable checking.
private final class AudioStartRequest: @unchecked Sendable {
    let audio: NativeAudioIO?
    let micEnabled: Bool
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Void, Error>?

    init(audio: NativeAudioIO?, micEnabled: Bool, continuation: CheckedContinuation<Void, Error>) {
        self.audio = audio
        self.micEnabled = micEnabled
        self.continuation = continuation
    }

    @discardableResult
    func finish(_ result: Result<Void, Error>) -> Bool {
        let pending = lock.withLock {
            let pending = continuation
            continuation = nil
            return pending
        }
        guard let pending else { return false }
        pending.resume(with: result)
        return true
    }
}

extension AudioEngineIO: NativeAudioIO {}

/// C7: the native transport is the only measured level source.
extension NativeAudioTransport: AudioLevelSource {}

// MARK: - Transport (plan D1, D5, D6; §6 step 3)

/// The second `RTVITransport` conformer: for a loopback bot, PCM audio
/// both ways plus the app/RTVI text frames on one WebSocket, framed with
/// pipecat's protobuf serializer (`PipecatFrameCodec`), with capture and
/// playout owned by `AudioEngineIO`. Lifecycle mirrors
/// `DirectWebRTCTransport`: connect tears down a live session first,
/// outbound app messages queue (bounded) until the socket is open, the
/// open deadline / keep-alive / stall thresholds are the same constants,
/// and every mutable member is confined to `queue`.
///
/// What is different, and why: `botIsSpeaking` is real here (D4 — the
/// player node's own completions), an `interruption` frame flushes the
/// playout queue (§3.2 findings), and the keep-alive is a WebSocket ping
/// rather than a data-channel "ping" text (the server answers pongs at
/// the protocol level; there is no data channel).
///
/// `@unchecked Sendable`: every mutable member is touched only on `queue`
/// (the public entry points hop there with `sync`, the callbacks with
/// `async`), which is the invariant Sendable would otherwise ask the
/// compiler to prove — it cannot, because the socket and engine seams are
/// non-Sendable existentials, so the promise is made here and kept by the
/// queue discipline. Review F5's reason for leaving DirectWebRTCTransport
/// unmarked (RTC objects crossing actor boundaries) does not apply.
final class NativeAudioTransport: RTVITransport, @unchecked Sendable {
    weak var delegate: RTVITransportDelegate?

    /// `botURL` → `ws(s)://host:port/ws-client`, the runner's plain
    /// WebSocket route (pipecat `runner/run.py` `_setup_websocket_routes`).
    static func socketURL(for botURL: URL) -> URL? {
        guard var components = URLComponents(url: botURL, resolvingAgainstBaseURL: false) else { return nil }
        switch components.scheme?.lowercased() {
        case "https", "wss": components.scheme = "wss"
        default: components.scheme = "ws"
        }
        components.path = "/ws-client"
        components.query = nil
        return components.url
    }

    private let queue = DispatchQueue(label: "com.mortimer.jarviskit.native-transport")
    private let makeSocket: (URLRequest) -> NativeSocket
    private let makeAudio: () -> NativeAudioIO
    /// Injected so the tests can drive the establishment phase in
    /// milliseconds instead of waiting out the real deadlines.
    private let readyDeadline: TimeInterval
    private let audioStartDeadline: TimeInterval
    /// Must stay well above `pingInterval`: the stall test is "no pong for
    /// this long", and pongs only arrive as often as pings are sent.
    private let stallSeconds: TimeInterval
    private let pingInterval: TimeInterval

    private var socket: NativeSocket?
    private var audio: NativeAudioIO?
    private var config: JarvisConfig?
    private var isOpen = false
    private var audioStarting = false
    private var micEnabled = true
    private var outboundQueue: [Data] = []
    private var openDeadlineTimer: DispatchSourceTimer?
    private var keepAliveTimer: DispatchSourceTimer?
    private var watchdogTimer: DispatchSourceTimer?
    private var lastPongAt: Date = .distantPast
    /// False from socket-open until the server's first frame: the
    /// stall watchdog does not run before that (§8 finding — the server
    /// spends seconds building the session after the handshake).
    private var isEstablished = false
    private var readyDeadlineTimer: DispatchSourceTimer?
    /// `connect` parks here until the server shows a sign of life, so that
    /// `.connected` means "the bot can answer" on this transport too
    /// (C6 step 6 parity finding 1). Queue-confined like everything else.
    private var readyContinuation: CheckedContinuation<Void, Error>?
    /// When the socket opened, so the first frame's delay can be reported.
    /// The 2026-09-15 run showed `establish` firing on a pong 5.77 s before
    /// the server's pipeline started, so the pong is not readiness; what
    /// the server sends FIRST, and when, decides where the gate belongs.
    private var openedAt: Date?
    private var firstFrameLogged = false
    private var captureMonitor: (@Sendable (Data) -> Void)?
    private var audioFramesSent = 0
    private var audioBytesSent = 0
    private(set) var sessionCount = 0

    /// §5 step 9 / §8 V6 readout on the native path: audio frames this
    /// client has put on the socket this session (cumulative, like the
    /// WebRTC outbound-rtp counters) — a climbing count through the bot's
    /// reply is not what this measures; capture is the client's own audio.
    var outboundAudioStats: OutboundAudioStats {
        queue.sync { OutboundAudioStats(packetsSent: audioFramesSent, bytesSent: audioBytesSent) }
    }
    /// The wake path's audio sink (§3.5). Set while the owner wants the
    /// wake listener fed from this engine's processed tap — the only
    /// supported way to run wake on the native path, since a second
    /// AVAudioEngine on the same input device receives silence and costs
    /// this one its echo cancellation. Cleared on teardown with the rest
    /// of the session state; frames are 16 kHz Int16 mono, i.e. already
    /// `JarvisTuning.wakeSampleRate`.
    func setCaptureMonitor(_ monitor: (@Sendable (Data) -> Void)?) {
        queue.sync {
            captureMonitor = monitor
            guard monitor != nil else { audio?.onMonitorPCM = nil; return }
            let session = sessionCount
            // Installed only while a monitor exists, so with wake off the
            // engine does no capture conversion at all on a muted mic.
            audio?.onMonitorPCM = { [weak self] pcm in
                guard let self else { return }
                self.queue.async { [weak self] in self?.monitored(pcm, session: session) }
            }
        }
    }

    /// True once the server has sent an inbound frame —
    /// which is the moment the stall watchdog starts running (§8: the
    /// server accepts the socket several seconds before it can answer).
    var isSessionEstablished: Bool { queue.sync { isEstablished } }

    /// The last answered keep-alive ping; nil before the socket opens.
    var lastKeepAliveDate: Date? {
        queue.sync { lastPongAt == .distantPast ? nil : lastPongAt }
    }

    /// Latest levels for C7 (closure C6.2): forwarded from the engine.
    /// `public` and protocol-visible because the meter is the one consumer
    /// outside this file (`AudioLevelSource`).
    public var latestInputLevel: AudioLevelSample? { (audio as? AudioEngineIO)?.latestInputLevel }
    public var latestPlayoutLevel: AudioLevelSample? { (audio as? AudioEngineIO)?.latestPlayoutLevel }

    init(makeSocket: @escaping (URLRequest) -> NativeSocket = { URLSessionSocket(request: $0) },
         makeAudio: @escaping () -> NativeAudioIO = { AudioEngineIO() },
         readyDeadline: TimeInterval = JarvisTuning.nativeReadyDeadline,
         audioStartDeadline: TimeInterval = JarvisTuning.nativeReadyDeadline,
         stallSeconds: TimeInterval = JarvisTuning.nativeKeepAliveStallSeconds,
         pingInterval: TimeInterval = JarvisTuning.keepAliveInterval) {
        self.makeSocket = makeSocket
        self.makeAudio = makeAudio
        self.readyDeadline = readyDeadline
        self.audioStartDeadline = audioStartDeadline
        self.stallSeconds = stallSeconds
        self.pingInterval = pingInterval
    }

    // MARK: RTVITransport

    func connect(config: JarvisConfig) async throws {
        await disconnect()
        guard let url = Self.socketURL(for: config.botURL) else {
            throw JarvisError.transport("no WebSocket URL for \(config.botURL)")
        }
        nativeLog.notice("dialing \(url.absoluteString, privacy: .public)")
        var request = URLRequest(url: url)
        if let token = config.token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        var startedSession = 0
        var startedAudio: NativeAudioIO?
        var micEnabledAtStart = true
        queue.sync {
            self.config = config
            sessionCount += 1
            let session = sessionCount
            let audio = makeAudio()
            // Callbacks arrive on engine/socket threads (they are @Sendable
            // for that reason) and hop onto `queue` weakly — the
            // DirectWebRTCTransport shape; `session` orphans anything from
            // a torn-down session.
            audio.onCapturedPCM = { [weak self] pcm, _ in
                guard let self else { return }
                self.queue.async { [weak self] in self?.captured(pcm, session: session) }
            }
            audio.onPlayoutChanged = { [weak self] playing in
                guard let self else { return }
                self.queue.async { [weak self] in self?.playoutChanged(playing, session: session) }
            }
            // The engine has given up on the device (D3). The socket is
            // still fine, which is exactly the problem: without this the
            // session stays "connected" with no audio in either direction.
            audio.onFailure = { [weak self] error in
                guard let self else { return }
                self.queue.async { [weak self] in self?.audioFailed(error, session: session) }
            }
            let socket = makeSocket(request)
            socket.onOpen = { [weak self] in
                guard let self else { return }
                self.queue.async { [weak self] in self?.opened(session: session) }
            }
            socket.onClose = { [weak self] error in
                guard let self else { return }
                self.queue.async { [weak self] in self?.closed(error: error, session: session) }
            }
            socket.onMessage = { [weak self] data in
                guard let self else { return }
                self.queue.async { [weak self] in self?.received(data, session: session) }
            }
            self.socket = socket
            self.audio = audio
            self.audioStarting = true
            // Open the socket before CoreAudio initialization. On a real Mac,
            // AVAudioEngine can spend several seconds settling a device (or
            // wait on an input-permission/device transition). Opening first
            // lets the bot build its session in parallel instead of leaving
            // the native client stuck in CONNECTING with no server request.
            // Capture callbacks begin only when the engine actually starts.
            armOpenDeadline(session: session)
            socket.open()
            startedSession = session
            startedAudio = audio
            micEnabledAtStart = micEnabled
        }
        // CoreAudio can block while it negotiates a device or waits for the
        // input-permission transition. Do this outside the transport queue
        // AND outside the caller's actor: JarvisClient.connect() is
        // @MainActor, so a synchronous start here freezes the Command
        // Console while the socket is already able to open and answer.
        // URLSession delivers `onOpen` onto the transport queue, and holding
        // either queue or the main actor here leaves the candidate stuck in
        // CONNECTING with an unresponsive window.
        do {
            try await Self.startAudioOffMainActor(startedAudio, micEnabled: micEnabledAtStart,
                                                 deadline: audioStartDeadline)
        } catch {
            let audio = startedAudio
            queue.sync {
                guard startedSession == sessionCount else { return }
                socket?.onOpen = nil; socket?.onClose = nil; socket?.onMessage = nil
                audio?.onCapturedPCM = nil; audio?.onPlayoutChanged = nil
                audio?.onMonitorPCM = nil; audio?.onFailure = nil
                // A timed-out CoreAudio start can still hold the engine queue.
                // Its completion owns cleanup; waiting in stop() here would
                // block the transport queue and defeat the startup deadline.
                socket?.close()
                self.audio = nil
                self.audioStarting = false
                self.socket = nil
                self.cancelAllTimers()
                self.isOpen = false
                self.isEstablished = false
                self.sessionCount += 1
                self.resumeReady(error)
            }
            throw error
        }
        let current = queue.sync {
            guard startedSession == sessionCount, socket != nil else { return false }
            audioStarting = false
            return true
        }
        guard current else {
            startedAudio?.stop()
            throw JarvisError.transport("the session ended while the audio device was starting")
        }
        // C6 step 6, parity finding 1. On WebRTC this call returns after
        // /api/offer, which the server answers only once the session is
        // built, so JarvisClient's `state = .connected` means the bot can
        // answer. Here the socket opening says nothing about the bot --
        // measured 5.4 s between the handshake and the pipeline starting --
        // so returning at open() reported a session that could not yet hear
        // anything. Wait for the signal `establish` already keys on, bounded
        // by `readyDeadline`.
        let session = startedSession
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            // Install the continuation synchronously on the owner queue. The
            // first server frame can arrive while CoreAudio is starting or
            // immediately before this wait is reached; using queue.async here
            // left a valid established session waiting forever when the
            // establish callback won that race.
            queue.sync {
                guard session == self.sessionCount, self.socket != nil else {
                    continuation.resume(throwing: JarvisError.transport("the session ended before the bot started"))
                    return
                }
                if self.isEstablished { continuation.resume(); return }
                self.readyContinuation = continuation
            }
        }
    }

    /// AudioEngineIO.start() performs synchronous CoreAudio negotiation. The
    /// native client is normally driven by JarvisClient's @MainActor, so even
    /// a correct transport-queue handoff is insufficient: the call would
    /// still block the UI actor until the device settles. Keep the seam
    /// asynchronous so the socket callbacks and the Command Console remain
    /// responsive while the engine starts.
    private static func startAudioOffMainActor(_ audio: NativeAudioIO?,
                                               micEnabled: Bool, deadline: TimeInterval) async throws {
        try await withCheckedThrowingContinuation { continuation in
            let request = AudioStartRequest(audio: audio, micEnabled: micEnabled,
                                            continuation: continuation)
            DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + deadline) { [weak request] in
                request?.finish(.failure(JarvisError.transport(
                    "audio device startup timed out; check the selected input/output devices and reconnect")))
            }
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try request.audio?.start()
                    request.audio?.setCaptureEnabled(request.micEnabled)
                    if !request.finish(.success(())) { request.audio?.stop() }
                } catch {
                    request.audio?.stop()
                    request.finish(.failure(error))
                }
            }
        }
    }

    /// Resolves `connect`'s wait exactly once.
    private func resumeReady(_ error: Error?) {
        guard let continuation = readyContinuation else { return }
        readyContinuation = nil
        if let error { continuation.resume(throwing: error) } else { continuation.resume() }
    }

    func disconnect() async {
        queue.sync { teardown(notify: false, error: nil) }
    }

    /// One app message → `Frame{message{data}}`; queued (bounded, oldest
    /// dropped — the WebRTC discipline) until the socket is open.
    func send(_ data: Data) throws {
        queue.sync {
            guard isOpen, let socket else {
                outboundQueue.append(data)
                if outboundQueue.count > JarvisTuning.outboundQueueMax {
                    outboundQueue.removeFirst(outboundQueue.count - JarvisTuning.outboundQueueMax)
                }
                return
            }
            socket.send(PipecatFrameCodec.encodeMessage(json: data)) { error in
                if let error { nativeLog.error("message send failed: \(error.localizedDescription, privacy: .public)") }
            }
        }
    }

    /// D6: muting stops feeding capture frames; the engine keeps running.
    func setMicEnabled(_ enabled: Bool) {
        queue.sync {
            micEnabled = enabled
            audio?.setCaptureEnabled(enabled)
        }
    }

    // MARK: Queue-confined

    private func opened(session: Int) {
        guard session == sessionCount, socket != nil, !isOpen else { return }
        isOpen = true
        openedAt = Date()
        firstFrameLogged = false
        nativeLog.notice("socket open (session \(session, privacy: .public))")
        openDeadlineTimer?.cancel(); openDeadlineTimer = nil
        startKeepAlive(session: session)
        armReadyDeadline(session: session)
        // NOT transportDidConnect() -- the socket being up says nothing about
        // the bot. That moves to `establish` (C6 step 6, finding 1).
        let queued = outboundQueue
        outboundQueue.removeAll()
        for frame in queued {
            socket?.send(PipecatFrameCodec.encodeMessage(json: frame)) { _ in }
        }
    }

    /// D3: the audio engine could not be rebuilt after a device change.
    /// Fail the session so the UI and the bot both find out, rather than
    /// holding a healthy socket over a dead engine.
    private func audioFailed(_ error: Error, session: Int) {
        guard session == sessionCount else { return }
        nativeLog.error("audio engine failed: \(String(describing: error), privacy: .public)")
        teardown(notify: true, error: error)
    }

    /// For the first-frame diagnostic: the frame's kind, and for a message
    /// frame the payload's `type`, which is what would identify a readiness
    /// message if the server sends one.
    private static func describe(_ frame: PipecatFrame) -> String {
        switch frame {
        case .audio(let pcm, let rate, let channels):
            return "audio \(pcm.count)B @\(rate)Hz x\(channels)"
        case .message(let json):
            let type = (try? JSONSerialization.jsonObject(with: json)) as? [String: Any]
            let inner = (type?["data"] as? [String: Any])?["type"] as? String
            return "message type=\(type?["type"] as? String ?? "?")\(inner.map { " data.type=\($0)" } ?? "")"
        case .interruption:
            return "interruption"
        case .text:
            return "text"
        case .transcription:
            return "transcription"
        }
    }

    private func pongReceived(session: Int) {
        guard session == sessionCount else { return }
        let gap = Date().timeIntervalSince(lastPongAt)
        lastPongAt = Date()
        // Evidence for §8: a server loop blocked long enough to matter shows
        // up here before it shows up as a teardown.
        if isEstablished, gap > JarvisTuning.keepAliveStallSeconds {
            nativeLog.notice("pong gap \(gap, format: .fixed(precision: 2), privacy: .public)s")
        }
        // Deliberately NOT establish(). Measured 2026-09-15: the first pong
        // arrived in the same millisecond as the socket opening, 5.72 s
        // before the server's first frame, because uvicorn answers pings
        // from its protocol layer while the session is still being built. A
        // pong says the socket layer is alive and keeps `lastPongAt` fresh
        // for the watchdog; it says nothing about the bot.
    }

    /// The server's pipeline is running -- it has sent us something. Stop
    /// waiting, report connected, and start watching for a stall.
    ///
    /// Called ONLY from `received`, on the first frame. Arming the watchdog
    /// here rather than at socket open also closes a near-miss: it used to
    /// be armed on the first pong with a 6 s threshold while the first
    /// frame took 5.72 s (5.79 s the run before), leaving under 300 ms
    /// between a healthy start and a spurious teardown.
    private func establish(session: Int) {
        guard session == sessionCount, !isEstablished, isOpen else { return }
        isEstablished = true
        readyDeadlineTimer?.cancel(); readyDeadlineTimer = nil
        lastPongAt = Date()
        startStallWatchdog(session: session)
        nativeLog.notice("session established; stall watchdog armed at \(self.stallSeconds, privacy: .public)s")
        delegate?.transportDidConnect()
        resumeReady(nil)
    }

    private func playoutChanged(_ playing: Bool, session: Int) {
        guard session == sessionCount else { return }
        delegate?.transport(botIsSpeaking: playing)
    }

    private func closed(error: Error?, session: Int) {
        nativeLog.error("""
            socket closed (session \(session, privacy: .public), current \(self.sessionCount, privacy: .public),             established \(self.isEstablished, privacy: .public)):             \(error.map { String(describing: $0) } ?? "no error", privacy: .public)
            """)
        guard session == sessionCount, socket != nil else { return }
        teardown(notify: true, error: error)
    }

    private func received(_ data: Data, session: Int) {
        guard session == sessionCount else { return }
        establish(session: session)
        guard let frame = PipecatFrameCodec.decode(data) else {
            nativeLog.error("undecodable frame of \(data.count, privacy: .public) bytes dropped")
            return
        }
        if !firstFrameLogged {
            firstFrameLogged = true
            let delay = openedAt.map { Date().timeIntervalSince($0) } ?? -1
            nativeLog.notice("""
                first inbound frame: \(Self.describe(frame), privacy: .public), \
                \(delay * 1000, format: .fixed(precision: 0), privacy: .public) ms after the socket opened
                """)
        }
        switch frame {
        case .audio(let pcm, let sampleRate, let channels):
            audio?.play(pcm: pcm, sampleRate: Double(sampleRate), channels: channels)
        case .message(let json):
            delegate?.transport(didReceiveFrame: json)
        case .interruption:
            audio?.flushPlayout()
        case .text, .transcription:
            // Not on the WebRTC path either (the app reads transcripts
            // from the server-message envelope); ignored, not an error.
            break
        }
    }

    private func captured(_ pcm: Data, session: Int) {
        guard session == sessionCount, isOpen, micEnabled, let socket else { return }
        let frame = PipecatFrameCodec.encodeAudio(pcm: pcm, sampleRate: Int(CaptureConverter.wireSampleRate), channels: 1)
        audioFramesSent += 1
        audioBytesSent += frame.count
        socket.send(frame) { error in
            if let error { nativeLog.error("audio send failed: \(error.localizedDescription, privacy: .public)") }
        }
    }

    /// Unlike `captured`, this does NOT require `micEnabled` — the wake
    /// listener runs exactly while the mic is muted — nor an open socket:
    /// wake audio goes to the sidecar, not to the bot.
    private func monitored(_ pcm: Data, session: Int) {
        guard session == sessionCount else { return }
        captureMonitor?(pcm)
    }

    private func armOpenDeadline(session: Int) {
        openDeadlineTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + JarvisTuning.dataChannelOpenDeadline)
        timer.setEventHandler { [weak self] in
            guard let self, session == self.sessionCount, !self.isOpen else { return }
            nativeLog.error("WebSocket did not open within deadline")
            self.teardown(notify: true, error: JarvisError.transport("WebSocket never opened"))
        }
        openDeadlineTimer = timer
        timer.resume()
    }

    /// Bounds the establishment phase: the server accepted the socket but
    /// has not yet answered anything. Deliberately generous — the work it
    /// does in that window is model loading, not a network round trip.
    private func armReadyDeadline(session: Int) {
        readyDeadlineTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + readyDeadline)
        timer.setEventHandler { [weak self] in
            guard let self, session == self.sessionCount, !self.isEstablished else { return }
            nativeLog.error("no reply from the bot within \(self.readyDeadline, privacy: .public)s of the socket opening")
            self.teardown(notify: true, error: JarvisError.transport("the bot did not start the session"))
        }
        readyDeadlineTimer = timer
        timer.resume()
    }

    private func startKeepAlive(session: Int) {
        lastPongAt = Date()
        let keepAlive = DispatchSource.makeTimerSource(queue: queue)
        // Immediately, not one interval later: this ping is what tells us
        // the server's loop is free, and `connect` is waiting on the answer.
        keepAlive.schedule(deadline: .now(), repeating: pingInterval)
        keepAlive.setEventHandler { [weak self] in
            guard let self, session == self.sessionCount, let socket = self.socket else { return }
            socket.ping { [weak self] error in
                guard error == nil, let self else { return }
                self.queue.async { [weak self] in self?.pongReceived(session: session) }
            }
        }
        keepAliveTimer = keepAlive
        keepAlive.resume()
    }

    private func startStallWatchdog(session: Int) {
        watchdogTimer?.cancel()
        let watchdog = DispatchSource.makeTimerSource(queue: queue)
        let tick = min(pingInterval, stallSeconds / 2)
        watchdog.schedule(deadline: .now() + tick, repeating: tick)
        watchdog.setEventHandler { [weak self] in
            guard let self, session == self.sessionCount, self.isEstablished else { return }
            if Date().timeIntervalSince(self.lastPongAt) > self.stallSeconds {
                nativeLog.error("keep-alive stalled past \(self.stallSeconds, privacy: .public)s")
                self.teardown(notify: true, error: JarvisError.transport("keep-alive stalled"))
            }
        }
        watchdogTimer = watchdog
        watchdog.resume()
    }

    private func cancelAllTimers() {
        openDeadlineTimer?.cancel(); openDeadlineTimer = nil
        readyDeadlineTimer?.cancel(); readyDeadlineTimer = nil
        keepAliveTimer?.cancel(); keepAliveTimer = nil
        watchdogTimer?.cancel(); watchdogTimer = nil
    }

    private func teardown(notify: Bool, error: Error?) {
        cancelAllTimers()
        let hadSession = socket != nil || audio != nil
        // A session that never established has no connect for the delegate
        // to be disconnected from: `connect` throws instead, the way a
        // refused /api/offer throws on the WebRTC path.
        let neverStarted = readyContinuation != nil
        resumeReady(error ?? JarvisError.transport("the session ended before the bot started"))
        socket?.onOpen = nil; socket?.onClose = nil; socket?.onMessage = nil
        socket?.close()
        audio?.onCapturedPCM = nil; audio?.onPlayoutChanged = nil; audio?.onMonitorPCM = nil
        audio?.onFailure = nil
        // A CoreAudio call may be stuck on the engine queue. The pending
        // start completion will stop its orphaned engine when it returns.
        if !audioStarting { audio?.stop() }
        audioStarting = false
        socket = nil
        audio = nil
        config = nil
        isOpen = false
        isEstablished = false
        outboundQueue.removeAll()
        captureMonitor = nil
        audioFramesSent = 0
        audioBytesSent = 0
        lastPongAt = .distantPast
        sessionCount += 1   // orphan any callback still in flight
        if notify, hadSession, !neverStarted { delegate?.transportDidDisconnect(error: error) }
    }
}

// MARK: - URLSession-backed socket

/// `URLSessionWebSocketTask` behind `NativeSocket`: open/close come from
/// the session delegate, messages from a receive loop that re-arms itself
/// until the task ends. Binary messages are the protobuf frames; text
/// messages are not part of the serializer's output and are dropped.
final class URLSessionSocket: NSObject, NativeSocket, URLSessionWebSocketDelegate {
    var onOpen: (@Sendable () -> Void)?
    var onClose: (@Sendable (Error?) -> Void)?
    var onMessage: (@Sendable (Data) -> Void)?

    private let request: URLRequest
    private var session: URLSession?
    private var task: URLSessionWebSocketTask?
    private var closed = false

    init(request: URLRequest) {
        self.request = request
    }

    func open() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let task = session.webSocketTask(with: request)
        task.maximumMessageSize = 4 * 1024 * 1024
        self.session = session
        self.task = task
        nativeLog.notice("URLSession task resuming for \(self.request.url?.absoluteString ?? "nil", privacy: .public)")
        task.resume()
        receiveLoop(task)
    }

    private func receiveLoop(_ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(.data(let data)):
                self.onMessage?(data)
                self.receiveLoop(task)
            case .success(.string):
                self.receiveLoop(task)
            case .success:
                self.receiveLoop(task)
            case .failure(let error):
                self.finish(error: error)
            }
        }
    }

    func send(_ data: Data, completion: @escaping (Error?) -> Void) {
        guard let task else { completion(JarvisError.transport("socket not open")); return }
        task.send(.data(data), completionHandler: completion)
    }

    func ping(completion: @escaping (Error?) -> Void) {
        guard let task else { completion(JarvisError.transport("socket not open")); return }
        task.sendPing(pongReceiveHandler: completion)
    }

    func close() {
        closed = true
        task?.cancel(with: .goingAway, reason: nil)
        session?.invalidateAndCancel()
        task = nil
        session = nil
    }

    private func finish(error: Error?) {
        nativeLog.notice("""
            URLSession finish: \(error.map { String(describing: $0) } ?? "no error", privacy: .public)             (already closed: \(self.closed, privacy: .public), HTTP             \((self.task?.response as? HTTPURLResponse)?.statusCode ?? -1, privacy: .public))
            """)
        guard !closed else { return }
        closed = true
        onClose?(error)
    }

    // URLSessionWebSocketDelegate
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        nativeLog.notice("URLSession didOpen (HTTP \((webSocketTask.response as? HTTPURLResponse)?.statusCode ?? -1, privacy: .public))")
        onOpen?()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        logWebSocketEnd("closed", code: closeCode, reason: reason)
        finish(error: closeCode == .normalClosure || closeCode == .goingAway ? nil
               : JarvisError.transport("WebSocket closed with code \(closeCode.rawValue)"))
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let webSocketTask = task as? URLSessionWebSocketTask {
            logWebSocketEnd(error == nil ? "completed" : "failed",
                            code: webSocketTask.closeCode, reason: webSocketTask.closeReason)
        }
        finish(error: error)
    }
}
