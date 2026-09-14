import Foundation
import os

private let nativeLog = Logger(subsystem: "com.mortimer.jarviskit", category: "native-transport")

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
    /// Must stay well above `pingInterval`: the stall test is "no pong for
    /// this long", and pongs only arrive as often as pings are sent.
    private let stallSeconds: TimeInterval
    private let pingInterval: TimeInterval

    private var socket: NativeSocket?
    private var audio: NativeAudioIO?
    private var config: JarvisConfig?
    private var isOpen = false
    private var micEnabled = true
    private var outboundQueue: [Data] = []
    private var openDeadlineTimer: DispatchSourceTimer?
    private var keepAliveTimer: DispatchSourceTimer?
    private var watchdogTimer: DispatchSourceTimer?
    private var lastPongAt: Date = .distantPast
    /// False from socket-open until the server's first pong or frame: the
    /// stall watchdog does not run before that (§8 finding — the server
    /// spends seconds building the session after the handshake).
    private var isEstablished = false
    private var readyDeadlineTimer: DispatchSourceTimer?
    /// `connect` parks here until the server shows a sign of life, so that
    /// `.connected` means "the bot can answer" on this transport too
    /// (C6 step 6 parity finding 1). Queue-confined like everything else.
    private var readyContinuation: CheckedContinuation<Void, Error>?
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

    /// True once the server has answered — a pong or any inbound frame —
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
         stallSeconds: TimeInterval = JarvisTuning.nativeKeepAliveStallSeconds,
         pingInterval: TimeInterval = JarvisTuning.keepAliveInterval) {
        self.makeSocket = makeSocket
        self.makeAudio = makeAudio
        self.readyDeadline = readyDeadline
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
        try queue.sync {
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
            // Capture starts with the socket so the first words are not
            // lost to engine warm-up; frames before open are dropped in
            // `captured`.
            do { try audio.start() } catch {
                self.audio = nil
                self.socket = nil
                throw error
            }
            audio.setCaptureEnabled(micEnabled)
            armOpenDeadline(session: session)
            socket.open()
            startedSession = session
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
            queue.async {
                guard session == self.sessionCount, self.socket != nil else {
                    continuation.resume(throwing: JarvisError.transport("the session ended before the bot started"))
                    return
                }
                if self.isEstablished { continuation.resume(); return }
                self.readyContinuation = continuation
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

    private func pongReceived(session: Int) {
        guard session == sessionCount else { return }
        let gap = Date().timeIntervalSince(lastPongAt)
        lastPongAt = Date()
        // Evidence for §8: a server loop blocked long enough to matter shows
        // up here before it shows up as a teardown.
        if isEstablished, gap > JarvisTuning.keepAliveStallSeconds {
            nativeLog.notice("pong gap \(gap, format: .fixed(precision: 2), privacy: .public)s")
        }
        establish(session: session)
    }

    /// The server is alive: stop waiting for it and start watching for a
    /// stall. Called on the first pong and on the first inbound frame,
    /// whichever the server produces first.
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
        audio?.stop()
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
        finish(error: closeCode == .normalClosure || closeCode == .goingAway ? nil
               : JarvisError.transport("WebSocket closed with code \(closeCode.rawValue)"))
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        finish(error: error)
    }
}
