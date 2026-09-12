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
        func open() { lock.withLock { _opened += 1 } }
        func send(_ data: Data, completion: @escaping (Error?) -> Void) { lock.withLock { _sent.append(data) }; completion(nil) }
        func ping(completion: @escaping (Error?) -> Void) { lock.withLock { _pings += 1 }; completion(nil) }
        func close() { lock.withLock { _closed += 1 } }
    }

    final class StubAudio: NativeAudioIO {
        var onCapturedPCM: (@Sendable (Data, AudioLevelSample) -> Void)?
        var onPlayoutChanged: (@Sendable (Bool) -> Void)?
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

    private func makeTransport() -> NativeAudioTransport {
        let transport = NativeAudioTransport(
            makeSocket: { [unowned self] request in let s = StubSocket(request: request); self.sockets.append(s); return s },
            makeAudio: { [unowned self] in let a = StubAudio(); self.audios.append(a); return a })
        transport.delegate = recorder
        return transport
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

    func testConnectStartsCaptureOpensTheSocketAndReportsConnectedOnlyWhenItOpens() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        XCTAssertEqual(audios.count, 1); XCTAssertEqual(sockets.count, 1)
        XCTAssertEqual(audios[0].started, 1)
        XCTAssertEqual(audios[0].captureCalls, [true], "capture enabled with the default mic state")
        XCTAssertEqual(sockets[0].opened, 1)
        XCTAssertEqual(sockets[0].request.url?.absoluteString, "ws://127.0.0.1:7860/ws-client")
        XCTAssertEqual(sockets[0].request.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
        XCTAssertEqual(recorder.connects, 0, "not connected until the socket opens")
        // A message before open is queued, not sent.
        try transport.send(Data(#"{"type":"voice/set","voice":"a"}"#.utf8))
        XCTAssertEqual(sockets[0].sent.count, 0)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "connected on open")
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
        let transport = makeTransport()
        try await transport.connect(config: config)
        for i in 0..<(JarvisTuning.outboundQueueMax + 5) { try transport.send(Data("{\"n\":\(i)}".utf8)) }
        sockets[0].onOpen?()
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
        let transport = makeTransport()
        try await transport.connect(config: config)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
        let pcm = Data([0, 0, 0, 0x40, 0, 0x80, 0xff, 0x7f])
        // The server-side audio vector (id/name present) and the two frames
        // the client ignores.
        sockets[0].onMessage?(Data(hexString: "1229080712154f7574707574417564696f5261774672616d6523371a08000000400080ff7f20c0bb012801"))
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

    func testCapturedPCMIsSentOnlyWhileOpenAndUnmuted() async throws {
        let transport = makeTransport()
        try await transport.connect(config: config)
        let level = AudioLevelSample(rms: 0.1, hostTime: 1)
        audios[0].onCapturedPCM?(Data([1, 2, 3, 4]), level)
        sockets[0].onOpen?()
        settle({ self.recorder.connects == 1 }, "open")
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
