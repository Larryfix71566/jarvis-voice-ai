import XCTest
@testable import JarvisKit

/// Native-audio plan §7, `NativeAudioTransport`: lifecycle against a stub
/// socket and a stub engine, the text-frame round trip against the same
/// fixtures `AppMessageTests` decodes off the WebRTC data channel, and
/// `botIsSpeaking` driven only by the player node's playing state.
final class NativeAudioTransportTests: XCTestCase {

    // MARK: Stubs

    final class StubSocket: NativeSocket {
        var onOpen: (@Sendable () -> Void)?
        var onClose: (@Sendable (Error?) -> Void)?
        var onMessage: (@Sendable (Data) -> Void)?
        let request: URLRequest
        private let lock = NSLock()
        private var _sent: [Data] = []
        private var _opened = 0, _closed = 0, _pings = 0
        var sent: [Data] { lock.withLock { _sent } }
        var opened: Int { lock.withLock { _opened } }
        var closedCount: Int { lock.withLock { _closed } }
        var pings: Int { lock.withLock { _pings } }
        init(request: URLRequest) { self.request = request }
        /// A real socket opens on its own, and `connect` no longer returns
        /// before that happens, so the stub does too. Tests that need the
        /// window before open turn it off through `socketAutoOpens`.
        var autoOpen = true
        /// A real server sends something unprompted when the session starts
        /// (measured: `voice/catalog`, 5.7 s after the socket opened), and
        /// `connect` now waits for that rather than for a pong. An AUDIO
        /// frame is used because it establishes without reaching the
        /// delegate, so it does not disturb the frame-counting tests.
        var autoFirstFrame = true
        func open() {
            lock.withLock { _opened += 1 }
            guard autoOpen else { return }
            onOpen?()
            if autoFirstFrame {
                onMessage?(PipecatFrameCodec.encodeAudio(pcm: Data([0, 0]), sampleRate: 24_000, channels: 1))
            }
        }
        func send(_ data: Data, completion: @escaping (Error?) -> Void) { lock.withLock { _sent.append(data) }; completion(nil) }
        /// Answered by default; `answersPings = false` models a server whose
        /// event loop is blocked (building the session, §8 finding).
        private var _answersPings = true
        var answersPings: Bool {
            get { lock.withLock { _answersPings } }
            set { lock.withLock { _answersPings = newValue } }
        }
        func ping(completion: @escaping (Error?) -> Void) {
            let answers = lock.withLock { () -> Bool in _pings += 1; return _answersPings }
            if answers { completion(nil) }
        }
        func close() { lock.withLock { _closed += 1 } }
    }

    final class StubAudio: NativeAudioIO {
        var onCapturedPCM: (@Sendable (Data, AudioLevelSample) -> Void)?
        var onMonitorPCM: (@Sendable (Data) -> Void)?
        var onPlayoutChanged: (@Sendable (Bool) -> Void)?
        var onFailure: (@Sendable (Error) -> Void)?
        private let lock = NSLock()
        private var _started = 0, _stopped = 0, _flushes = 0
        private var _capture: [Bool] = []
        private var _played: [(Data, Double, Int)] = []
        var startError: Error?
        var started: Int { lock.withLock { _started } }
        var stopped: Int { lock.withLock { _stopped } }
        var flushes: Int { lock.withLock { _flushes } }
        var captureCalls: [Bool] { lock.withLock { _capture } }
        var played: [(Data, Double, Int)] { lock.withLock { _played } }
        func start() throws { if let startError { throw startError }; lock.withLock { _started += 1 } }
        func stop() { lock.withLock { _stopped += 1 } }
        func setCaptureEnabled(_ enabled: Bool) { lock.withLock { _capture.append(enabled) } }
        func play(pcm: Data, sampleRate: Double, channels: Int) { lock.withLock { _played.append((pcm, sampleRate, channels)) } }
        func flushPlayout() { lock.withLock { _flushes += 1 } }
    }

    /// Collects what a capture monitor hears (called on the transport's
    /// queue, asserted from the test thread).
    final class Collector: @unchecked Sendable {
        private let lock = NSLock()
        private var _all: [Data] = []
        var all: [Data] { lock.withLock { _all } }
        func add(_ data: Data) { lock.withLock { _all.append(data) } }
    }

    final class Recorder: RTVITransportDelegate {
        private let lock = NSLock()
        private var _connects = 0
        private var _disconnects: [Error?] = []
        private var _frames: [Data] = []
        private var _speaking: [Bool] = []
        var connects: Int { lock.withLock { _connects } }
        var disconnects: [Error?] { lock.withLock { _disconnects } }
        var frames: [Data] { lock.withLock { _frames } }
        var speaking: [Bool] { lock.withLock { _speaking } }
        func transportDidConnect() { lock.withLock { _connects += 1 } }
        func transportDidDisconnect(error: Error?) { lock.withLock { _disconnects.append(error) } }
        func transport(didReceiveFrame data: Data) { lock.withLock { _frames.append(data) } }
        func transport(botIsSpeaking: Bool) { lock.withLock { _speaking.append(botIsSpeaking) } }
    }

    private var sockets: [StubSocket] = []
    private var audios: [StubAudio] = []
    private var recorder = Recorder()
    private let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
                                      adminURL: URL(string: "http://127.0.0.1:7861")!,
                                      wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "tok")

    private func makeTransport(readyDeadline: TimeInterval = JarvisTuning.nativeReadyDeadline,
                               stallSeconds: TimeInterval = JarvisTuning.nativeKeepAliveStallSeconds,
                               pingInterval: TimeInterval = JarvisTuning.keepAliveInterval) -> NativeAudioTransport {
        let transport = NativeAudioTransport(
            makeSocket: { [unowned self] request in
                let s = StubSocket(request: request)
                s.autoOpen = self.socketAutoOpens
                s.autoFirstFrame = self.socketAutoFirstFrame
                s.answersPings = self.socketAnswersPings
                self.sockets.append(s)
                return s
            },
            makeAudio: { [unowned self] in let a = StubAudio(); self.audios.append(a); return a },
            readyDeadline: readyDeadline, stallSeconds: stallSeconds, pingInterval: pingInterval)
        transport.delegate = recorder
        return transport
    }

    /// How the next stub socket behaves. `connect` returns only once the
    /// server has answered, so the defaults let it complete; a test needing
    /// the pre-open or pre-answer window turns one off BEFORE calling
    /// connect, since the socket is created inside it.
    private var socketAutoOpens = true
    private var socketAutoFirstFrame = true
    private var socketAnswersPings = true

    /// Opens the stub AND delivers the frame `connect` waits for. A real
    /// server sends something unprompted when the session starts (measured:
    /// `voice/catalog`), so a test driving `open()` by hand has to do the
    /// same or the call sits until the ready deadline and throws.
    private func openAndAnswer(_ index: Int) {
        sockets[index].onOpen?()
        sockets[index].onMessage?(PipecatFrameCodec.encodeAudio(pcm: Data([0, 0]), sampleRate: 24_000, channels: 1))
    }

    /// Waits for the socket `connect` created while the call is still in
    /// flight. Cooperative, unlike `settle`, which blocks its thread.
    private func awaitSocket(_ index: Int) async {
        for _ in 0..<400 where sockets.count <= index {
            try? await Task.sleep(for: .milliseconds(5))
        }
    }

    /// Delegate calls and stub callbacks hop through the transport's own
    /// serial queue; poll until the condition holds (bounded, 2 s).
    private func settle(_ condition: @escaping () -> Bool, _ message: String, file: StaticString = #filePath, line: UInt = #line) {
        let deadline = Date().addingTimeInterval(2)
        while !condition() && Date() < deadline { Thread.sleep(forTimeInterval: 0.005) }
        XCTAssertTrue(condition(), message, file: file, line: line)
    }

    // MARK: URL

    func testSocketURLIsTheRunnersPlainWebSocketRouteWithTheSchemeMapped() {
        XCTAssertEqual(NativeAudioTransport.socketURL(for: URL(string: "http://127.0.0.1:7860")!)?.absoluteString, "ws://127.0.0.1:7860/ws-client")
        XCTAssertEqual(NativeAudioTransport.socketURL(for: URL(string: "https://mac.tail:7860/some/path?x=1")!)?.absoluteString, "wss://mac.tail:7860/ws-client")
        XCTAssertEqual(NativeAudioTransport.socketURL(for: URL(string: "http://[::1]:7860")!)?.absoluteString, "ws://[::1]:7860/ws-client")
    }

    // MARK: Lifecycle

    func testConnectStartsCaptureOpensTheSocketAndReportsConnectedOnlyWhenTheBotAnswers() async throws {
        socketAutoOpens = false
        let transport = makeTransport()
        let connecting = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        XCTAssertEqual(audios.count, 1); XCTAssertEqual(sockets.count, 1)
        XCTAssertEqual(audios[0].started, 1)
        XCTAssertEqual(audios[0].captureCalls, [true], "capture enabled with the default mic state")
        XCTAssertEqual(sockets[0].opened, 1)
        XCTAssertEqual(sockets[0].request.url?.absoluteString, "ws://127.0.0.1:7860/ws-client")
        XCTAssertEqual(sockets[0].request.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
        XCTAssertEqual(recorder.connects, 0, "not connected until the bot answers")
        // A message before open is queued, not sent.
        try transport.send(Data(#"{"type":"voice/set","voice":"a"}"#.utf8))
        XCTAssertEqual(sockets[0].sent.count, 0)
        openAndAnswer(0)
        try await connecting.value
        XCTAssertEqual(recorder.connects, 1, "connected once the bot answered the first ping")
        settle({ self.sockets[0].sent.count == 1 }, "queued message flushed on open")
        XCTAssertEqual(PipecatFrameCodec.decode(sockets[0].sent[0]), .message(json: Data(#"{"type":"voice/set","voice":"a"}"#.utf8)))
        try transport.send(Data(#"{"type":"ui/noop","reason":"r"}"#.utf8))
        XCTAssertEqual(sockets[0].sent.count, 2, "after open a message goes straight out")
        await transport.disconnect()
        XCTAssertEqual(audios[0].stopped, 1)
        XCTAssertEqual(sockets[0].closedCount, 1)
        XCTAssertEqual(recorder.disconnects.count, 0, "a client-initiated disconnect is not reported as a drop")
    }

    func testOutboundQueueBeforeOpenIsBoundedOldestDropped() async throws {
        socketAutoOpens = false
        let transport = makeTransport()
        let connecting = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        for i in 0..<(JarvisTuning.outboundQueueMax + 5) { try transport.send(Data("{\"n\":\(i)}".utf8)) }
        openAndAnswer(0)
        try await connecting.value
        settle({ self.sockets[0].sent.count == JarvisTuning.outboundQueueMax }, "queue capped at outboundQueueMax")
        XCTAssertEqual(PipecatFrameCodec.decode(sockets[0].sent[0]), .message(json: Data("{\"n\":5}".utf8)), "oldest five dropped")
        await transport.disconnect()
    }

    func testReconnectTearsDownTheLiveSessionFirstAndOrphansItsCallbacks() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "first session open")
        let oldClose = sockets[0].onClose
        try await transport.connect(config: config)
        XCTAssertEqual(sockets.count, 2); XCTAssertEqual(audios.count, 2)
        XCTAssertEqual(audios[0].stopped, 1, "old engine stopped")
        XCTAssertEqual(sockets[0].closedCount, 1, "old socket closed")
        XCTAssertNil(sockets[0].onClose, "old socket's callbacks detached")
        oldClose?(JarvisError.transport("late close from the old socket"))
        sockets[1].onOpen?()
        settle({ self.recorder.connects == 2 }, "second session open")
        XCTAssertEqual(recorder.disconnects.count, 0, "the old socket's late close is not reported")
        await transport.disconnect()
        XCTAssertEqual(audios[1].stopped, 1)
    }

    func testAnEngineThatCannotStartFailsConnectWithoutOpeningTheSocket() async {
        let transport = makeTransport()
        // The engine is built inside connect; make it fail through the factory.
        let failing = NativeAudioTransport(
            makeSocket: { [unowned self] request in let s = StubSocket(request: request); self.sockets.append(s); return s },
            makeAudio: { let a = StubAudio(); a.startError = JarvisError.transport("no input device"); return a })
        failing.delegate = recorder
        do {
            try await failing.connect(config: config)
            XCTFail("connect should throw")
        } catch {
            XCTAssertEqual(error as? JarvisError, .transport("no input device"))
        }
        XCTAssertEqual(sockets.count, 1)
        XCTAssertEqual(sockets[0].opened, 0, "socket never opened")
        _ = transport
    }

    func testServerCloseIsReportedOnceAndStopsTheEngine() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        sockets[0].onClose?(JarvisError.transport("WebSocket closed with code 1011"))
        settle({ self.recorder.disconnects.count == 1 }, "drop reported")
        XCTAssertEqual(recorder.disconnects[0] as? JarvisError, .transport("WebSocket closed with code 1011"))
        XCTAssertEqual(audios[0].stopped, 1)
        XCTAssertEqual(sockets[0].closedCount, 1)
        await transport.disconnect()
        XCTAssertEqual(recorder.disconnects.count, 1, "a second teardown does not report again")
        XCTAssertEqual(audios[0].stopped, 1)
    }

    // MARK: Frames

    private func fixture(_ name: String) throws -> Data {
        let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")
            ?? Bundle.module.url(forResource: name, withExtension: "json")
        return try Data(contentsOf: XCTUnwrap(url))
    }

    func testEveryAppMessageFixtureDecodesTheSameThroughTheWebSocketAsOffTheDataChannel() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        let names = ["agent_activity", "agent_done", "agent_tool", "agent_working", "capability", "display_window",
                     "speaker_gate", "ui_command", "unknown_type", "voice_catalog", "voice_current"]
        var expected: [AppMessage?] = []
        for name in names {
            let json = try fixture(name)
            expected.append(try AppMessage.decode(frame: json))
            sockets[0].onMessage?(PipecatFrameCodec.encodeMessage(json: json))
        }
        settle({ self.recorder.frames.count == names.count }, "all frames delivered")
        for (i, frame) in recorder.frames.enumerated() {
            XCTAssertEqual(try AppMessage.decode(frame: frame), expected[i], names[i])
        }
        await transport.disconnect()
    }

    func testAudioFramesGoToPlayoutInterruptionFlushesAndTextFramesAreIgnored() async throws {
        // No auto first frame: this test counts what reaches playout, so the
        // audio vector below has to be the frame that establishes.
        socketAutoOpens = false
        socketAutoFirstFrame = false
        let transport = makeTransport()
        let connecting = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        sockets[0].onOpen?()
        let pcm = Data([0, 0, 0, 0x40, 0, 0x80, 0xff, 0x7f])
        // The server-side audio vector (id/name present) and the two frames
        // the client ignores.
        sockets[0].onMessage?(Data(hexString: "1229080712154f7574707574417564696f5261774672616d6523371a08000000400080ff7f20c0bb012801"))
        try await connecting.value
        XCTAssertEqual(recorder.connects, 1, "the audio frame established the session")
        sockets[0].onMessage?(Data(hexString: "0a170803120b546578744672616d6523331a0668c3a96c6c6f"))
        sockets[0].onMessage?(Data(hexString: "2a1708091213496e74657272757074696f6e4672616d652339"))
        sockets[0].onMessage?(Data([0x10, 0x01]))   // malformed: dropped
        settle({ self.audios[0].flushes == 1 }, "interruption flushed playout")
        XCTAssertEqual(audios[0].played.count, 1)
        XCTAssertEqual(audios[0].played[0].0, pcm)
        XCTAssertEqual(audios[0].played[0].1, 24_000)
        XCTAssertEqual(audios[0].played[0].2, 1)
        XCTAssertEqual(recorder.frames.count, 0, "audio, text and interruption never reach the app-message path")
        await transport.disconnect()
    }

    /// §3.5: the wake listener runs exactly while the mic is muted, so
    /// its audio source cannot be the mute-gated capture path — and it
    /// must not be a second AVAudioEngine either (that costs VPIO its
    /// echo cancellation, measured 2026-09-13).
    func testCaptureMonitorHearsProcessedAudioWhileMutedAndDoesNotSurviveTheSession() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        let heard = Collector()
        transport.setCaptureMonitor { heard.add($0) }
        audios[0].onMonitorPCM?(Data([1, 2]))
        settle({ heard.all.count == 1 }, "wake audio does not wait for the bot socket to open")
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        transport.setMicEnabled(false)
        let level = AudioLevelSample(rms: 0.1, hostTime: 1)
        audios[0].onMonitorPCM?(Data([3, 4]))
        audios[0].onCapturedPCM?(Data([3, 4]), level)
        settle({ heard.all.count == 2 }, "the monitor fires while muted")
        XCTAssertEqual(heard.all, [Data([1, 2]), Data([3, 4])])
        XCTAssertEqual(sockets[0].sent.count, 0, "the same buffer is not sent to the bot while muted")
        await transport.disconnect()
        XCTAssertNil(audios[0].onMonitorPCM, "the engine callback is cleared with the session")
        try await transport.connect(config: config)
        audios[1].onMonitorPCM?(Data([5, 6]))
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(heard.all.count, 2, "a monitor does not survive a reconnect — the owner re-arms it")
        await transport.disconnect()
    }

    func testCapturedPCMIsSentOnlyWhileOpenAndUnmuted() async throws {
        socketAutoOpens = false
        let transport = makeTransport()
        let connecting = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        let level = AudioLevelSample(rms: 0.1, hostTime: 1)
        audios[0].onCapturedPCM?(Data([1, 2, 3, 4]), level)
        openAndAnswer(0)
        try await connecting.value
        XCTAssertEqual(recorder.connects, 1, "open")
        XCTAssertEqual(sockets[0].sent.count, 0, "frames captured before open are dropped, not queued")
        audios[0].onCapturedPCM?(Data([1, 2, 3, 4]), level)
        settle({ self.sockets[0].sent.count == 1 }, "captured frame sent")
        XCTAssertEqual(sockets[0].sent[0], Data(hexString: "120b1a040102030420807d2801"), "the exact bytes pipecat deserializes into InputAudioRawFrame(16000, 1)")
        transport.setMicEnabled(false)
        XCTAssertEqual(audios[0].captureCalls, [true, false])
        audios[0].onCapturedPCM?(Data([5, 6]), level)
        transport.setMicEnabled(true)
        audios[0].onCapturedPCM?(Data([7, 8]), level)
        settle({ self.sockets[0].sent.count == 2 }, "unmuted frame sent")
        XCTAssertEqual(PipecatFrameCodec.decode(sockets[0].sent[1]), .audio(pcm: Data([7, 8]), sampleRate: 16_000, channels: 1), "the muted frame was not sent")
        XCTAssertEqual(transport.outboundAudioStats, OutboundAudioStats(packetsSent: 2, bytesSent: sockets[0].sent[0].count + sockets[0].sent[1].count))
        await transport.disconnect()
        XCTAssertEqual(transport.outboundAudioStats, OutboundAudioStats(packetsSent: 0, bytesSent: 0), "counters reset with the session")
        XCTAssertNil(transport.lastKeepAliveDate)
    }

    func testBotIsSpeakingFollowsThePlayerNodeAndStopsAtDisconnect() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        audios[0].onPlayoutChanged?(true)
        audios[0].onPlayoutChanged?(false)
        settle({ self.recorder.speaking == [true, false] }, "speaking follows playout")
        let orphan = audios[0].onPlayoutChanged
        await transport.disconnect()
        orphan?(true)
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(recorder.speaking, [true, false], "no speaking report after disconnect")
    }

    /// §8, 2026-09-13: the server accepts the WebSocket and only then builds
    /// the session — 5.4 s of blocked event loop on this Mac (Smart Turn and
    /// Silero loading, memory sweep, STT/TTS connects). The old watchdog was
    /// armed at socket-open with a 2.5 s threshold and killed every session
    /// before the bot ever spoke.
    func testASilentServerIsGivenTheReadyDeadlineBeforeTheStallWatchdogExists() async throws {
        // stall > ping, as in production (6 s vs 1 s), scaled down.
        socketAnswersPings = false               // loop blocked: no pongs
        socketAutoFirstFrame = false             // and nothing sent yet
        let transport = makeTransport(readyDeadline: 3.0, stallSeconds: 0.3, pingInterval: 0.05)
        let connecting = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        // Well past the stall threshold, nowhere near the ready deadline.
        try await Task.sleep(for: .milliseconds(700))
        XCTAssertEqual(recorder.disconnects.count, 0, "a server still starting up must not be torn down")
        XCTAssertEqual(recorder.connects, 0, "and it is not called connected while it starts")
        XCTAssertGreaterThan(sockets[0].pings, 5, "pings are sent throughout the wait")
        // A pong is NOT readiness any more, so answering pings changes
        // nothing; the session becomes ready when the server sends a frame.
        sockets[0].answersPings = true
        try await Task.sleep(for: .milliseconds(200))
        XCTAssertEqual(recorder.connects, 0, "an answered ping is not the bot starting the session")
        sockets[0].onMessage?(PipecatFrameCodec.encodeAudio(pcm: Data([0, 0]), sampleRate: 24_000, channels: 1))
        try await connecting.value
        XCTAssertEqual(recorder.connects, 1, "connected when the server answered")
        XCTAssertEqual(recorder.disconnects.count, 0, "an answering server keeps the session")
        // And the watchdog is now armed — proof that establishment happened.
        XCTAssertTrue(transport.isSessionEstablished, "the answered ping established the session")
        sockets[0].answersPings = false
        settle({ self.recorder.disconnects.count == 1 }, "the watchdog exists once the server has answered")
    }

    func testTheReadyDeadlineFailsTheSessionWhenTheBotNeverAnswers() async throws {
        socketAutoFirstFrame = false
        socketAnswersPings = false
        let transport = makeTransport(readyDeadline: 0.4, stallSeconds: 0.3, pingInterval: 0.05)
        do {
            try await transport.connect(config: config)
            XCTFail("connect must not succeed when the bot never answers")
        } catch {
            XCTAssertEqual(Self.message(error), "the bot did not start the session")
        }
        XCTAssertEqual(audios[0].stopped, 1, "the engine is stopped with the session")
        XCTAssertEqual(recorder.connects, 0, "it was never reported connected")
        XCTAssertEqual(recorder.disconnects.count, 0,
                       "a session that never started is a failed connect, not a drop")
    }

    func testOnceEstablishedSilenceBeyondTheStallThresholdTearsTheSessionDown() async throws {
        let transport = makeTransport(readyDeadline: 5.0, stallSeconds: 0.3, pingInterval: 0.05)
        try await transport.connect(config: config)
        // lastKeepAliveDate is non-nil from the moment pings start, so it is
        // not the establishment signal — this is, and connect waited for it.
        XCTAssertTrue(transport.isSessionEstablished, "established by the first pong")
        sockets[0].answersPings = false          // the server goes quiet mid-session
        settle({ self.recorder.disconnects.count == 1 }, "the stall watchdog fires once established")
        XCTAssertEqual(Self.message(recorder.disconnects.first ?? nil), "keep-alive stalled")
    }

    func testAnInboundFrameEstablishesTheSessionWithoutAPong() async throws {
        socketAutoFirstFrame = false
        socketAnswersPings = false
        let transport = makeTransport(readyDeadline: 3.0, stallSeconds: 5.0, pingInterval: 0.05)
        let connecting = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        // The bot's first message is as good a sign of life as a pong. The
        // stub opens itself inside connect and every callback hops through
        // the same serial queue, so `opened` has already run by now.
        sockets[0].onMessage?(PipecatFrameCodec.encodeMessage(json: Data(#"{"type":"bot-ready"}"#.utf8)))
        try await connecting.value
        XCTAssertEqual(recorder.connects, 1, "the frame established the session")
        settle({ self.recorder.frames.count == 1 }, "frame delivered")
        XCTAssertTrue(transport.isSessionEstablished, "a frame establishes the session")
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertEqual(recorder.disconnects.count, 0, "the ready deadline was cancelled by the frame")
        await transport.disconnect()
    }

    private static func message(_ error: Error?) -> String? {
        guard case .transport(let text)? = error as? JarvisError else { return nil }
        return text
    }

    /// D3: a device change the engine cannot recover from leaves the
    /// socket perfectly healthy -- pongs and all -- so nothing else in the
    /// stack notices. The session has to be failed from the audio side.
    func testAnEngineThatGivesUpOnItsDeviceFailsTheSession() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")

        audios[0].onFailure?(JarvisError.transport("audio device lost: nope"))

        settle({ self.recorder.disconnects.count == 1 }, "the session is torn down")
        XCTAssertEqual(Self.message(recorder.disconnects.first ?? nil), "audio device lost: nope")
        XCTAssertEqual(audios[0].stopped, 1, "the engine is stopped with the session")
        XCTAssertEqual(sockets[0].closedCount, 1, "and the socket does not stay up without audio")
    }

    /// The callback is cleared with the session: a late failure from an
    /// engine belonging to a torn-down session must not disturb the next one.
    func testAFailureFromAPreviousSessionIsIgnored() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        let orphaned = audios[0].onFailure
        await transport.disconnect()

        try await transport.connect(config: config)
        sockets[1].onOpen?()
        settle({ self.recorder.connects == 2 }, "second session open")
        let disconnectsBefore = recorder.disconnects.count

        orphaned?(JarvisError.transport("audio device lost: stale"))
        try await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(recorder.disconnects.count, disconnectsBefore,
                       "a dead session's engine cannot tear down the live one")
        await transport.disconnect()
    }

    /// The 2026-09-15 measurement, as a test: the first pong arrived in the
    /// same millisecond as the socket opening, 5.72 s before the server's
    /// first frame, because uvicorn answers pings from its protocol layer
    /// while the session is still being built. A pong must therefore not
    /// make the session ready, and must not arm the stall watchdog either --
    /// the old behaviour left under 300 ms between a healthy start and a
    /// spurious teardown.
    func testAnsweredPingsAloneNeverMakeTheSessionReady() async throws {
        socketAutoFirstFrame = false
        let transport = makeTransport(readyDeadline: 5.0, stallSeconds: 0.3, pingInterval: 0.02)
        // Stated, not inferred: a Task whose body the compiler reads as
        // non-throwing becomes Task<Void, Never> and every `try` in it is an
        // error, which is how the duplicate above surfaced.
        let connecting: Task<Void, Error> = Task { try await transport.connect(config: self.config) }
        await awaitSocket(0)
        // Pings answered throughout, well past the stall threshold.
        try await Task.sleep(for: .milliseconds(600))
        XCTAssertGreaterThan(sockets[0].pings, 5, "the server is answering")
        XCTAssertEqual(recorder.connects, 0, "answered pings are not the bot being ready")
        XCTAssertEqual(recorder.disconnects.count, 0, "and the stall watchdog is not armed yet")
        // The frame is what does it.
        sockets[0].onMessage?(PipecatFrameCodec.encodeAudio(pcm: Data([0, 0]), sampleRate: 24_000, channels: 1))
        try await connecting.value
        XCTAssertEqual(recorder.connects, 1)
        XCTAssertTrue(transport.isSessionEstablished)
        await transport.disconnect()
    }

    func testKeepAlivePingsRunWhileOpen() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        let deadline = Date().addingTimeInterval(JarvisTuning.keepAliveInterval * 2.5)
        while sockets[0].pings < 2 && Date() < deadline { try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertGreaterThanOrEqual(sockets[0].pings, 2, "a ping every keepAliveInterval")
        XCTAssertNotNil(transport.lastKeepAliveDate, "answered pings are recorded")
        await transport.disconnect()
        XCTAssertEqual(recorder.disconnects.count, 0, "answered pings never trip the watchdog")
    }
}

// MARK: - Plan D1: transport selection in JarvisClient

@MainActor
final class TransportSelectionTests: XCTestCase {
    private func config(_ bot: String) -> JarvisConfig {
        JarvisConfig(botURL: URL(string: bot)!, adminURL: URL(string: "http://127.0.0.1:7861")!,
                     wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil)
    }

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: "JARVIS_FORCE_WEBRTC")
        super.tearDown()
    }

    func testLoopbackBotsUseTheNativePathAndRemoteBotsKeepWebRTC() {
        UserDefaults.standard.removeObject(forKey: "JARVIS_FORCE_WEBRTC")
        XCTAssertFalse(JarvisFlags.forceWebRTC, "absent key == off")
        for bot in ["http://127.0.0.1:7860", "http://localhost:7860", "http://[::1]:7860"] {
            XCTAssertTrue(JarvisClient.usesNativeAudio(for: config(bot)), bot)
            XCTAssertTrue(JarvisClient.makeTransport(for: config(bot)) is NativeAudioTransport, bot)
        }
        for bot in ["http://100.64.0.2:7860", "https://mac.tail-net.ts.net:7860"] {
            XCTAssertFalse(JarvisClient.usesNativeAudio(for: config(bot)), bot)
            XCTAssertTrue(JarvisClient.makeTransport(for: config(bot)) is DirectWebRTCTransport, bot)
        }
    }

    func testForceWebRTCIsTheRollbackLeverForLoopback() {
        UserDefaults.standard.set(true, forKey: "JARVIS_FORCE_WEBRTC")
        XCTAssertTrue(JarvisFlags.forceWebRTC)
        XCTAssertFalse(JarvisClient.usesNativeAudio(for: config("http://127.0.0.1:7860")))
        XCTAssertTrue(JarvisClient.makeTransport(for: config("http://127.0.0.1:7860")) is DirectWebRTCTransport)
        UserDefaults.standard.set(false, forKey: "JARVIS_FORCE_WEBRTC")
        XCTAssertTrue(JarvisClient.usesNativeAudio(for: config("http://127.0.0.1:7860")))
    }
}

private extension Data {
    init(hexString: String) {
        self.init(); var i = hexString.startIndex
        while i < hexString.endIndex { let j = hexString.index(i, offsetBy: 2); append(UInt8(hexString[i..<j], radix: 16)!); i = j }
    }
}
