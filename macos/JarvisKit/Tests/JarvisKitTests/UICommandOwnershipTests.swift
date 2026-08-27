import XCTest
@testable import JarvisKit

/// §7.5 — driven by injecting AppMessage.ui(...) into a JarvisClient with
/// a stub transport that records outbound frames.
@MainActor
final class UICommandOwnershipTests: XCTestCase {
    private func makeClient(stub: StubTransport = StubTransport()) -> (JarvisClient, StubTransport) {
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        let client = JarvisClient(config: config, stubTransport: stub)
        return (client, stub)
    }

    /// JarvisClient's transport-delegate conformance hops to @MainActor
    /// via an unstructured Task (review F5). Driving StubTransport
    /// synchronously needs to flush that Task before asserting on the
    /// state it mutates — see flushMainActor() in TestSupport.swift.
    private func deliverUI(_ client: JarvisClient, stub: StubTransport, action: String, tab: String? = nil) async {
        let tabJSON = tab.map { "\"tab\":\"\($0)\"," } ?? ""
        let json = """
        {"type":"ui",\(tabJSON)"action":"\(action)"}
        """
        stub.simulateReceivedFrame(Data(json.utf8))
        await flushMainActor()
    }

    func testMicMuteWhenLiveMutes() async {
        let (client, stub) = makeClient()
        await client.connect()
        client.micEnabled = true
        await deliverUI(client, stub: stub, action: "mic_mute")
        XCTAssertEqual(client.micEnabled, false)
        XCTAssertTrue(stub.sentFrames.isEmpty)   // no outbound frame
    }

    func testMicMuteWhenAlreadyMutedSendsNothing() async {
        let (client, stub) = makeClient()
        await client.connect()
        client.micEnabled = false
        await deliverUI(client, stub: stub, action: "mic_mute")
        XCTAssertEqual(client.micEnabled, false)   // no state change
        XCTAssertTrue(stub.sentFrames.isEmpty)     // MicControls.tsx:100-104
    }

    func testWakeOnWhenUnavailableSendsExactNoop() async {
        let (client, stub) = makeClient()
        await client.connect()
        client.wakeWordAvailable = false
        await deliverUI(client, stub: stub, action: "wake_on")
        let frame = try? XCTUnwrap(stub.sentFrames.last)
        let obj = try? JSONSerialization.jsonObject(with: frame ?? Data()) as? [String: Any]
        XCTAssertEqual(obj??["type"] as? String, "ui/noop")
        XCTAssertEqual(obj??["reason"] as? String, "The wake word listener isn't available on this machine.")
    }

    func testWakeOnWhenAlreadyOnSendsExactNoop() async {
        let (client, stub) = makeClient()
        await client.connect()
        client.wakeWordAvailable = true
        client.wakeWordOn = true
        await deliverUI(client, stub: stub, action: "wake_on")
        let frame = try? XCTUnwrap(stub.sentFrames.last)
        let obj = try? JSONSerialization.jsonObject(with: frame ?? Data()) as? [String: Any]
        XCTAssertEqual(obj??["reason"] as? String, "The wake word is already on.")
    }

    func testWakeOffWhenAlreadyOffSendsExactNoop() async {
        let (client, stub) = makeClient()
        await client.connect()
        client.wakeWordOn = false
        await deliverUI(client, stub: stub, action: "wake_off")
        let frame = try? XCTUnwrap(stub.sentFrames.last)
        let obj = try? JSONSerialization.jsonObject(with: frame ?? Data()) as? [String: Any]
        XCTAssertEqual(obj??["reason"] as? String, "The wake word is already off.")
    }

    func testUnownedUIActionIsForwardedNotApplied() async {
        let (client, stub) = makeClient()
        await client.connect()
        let before = client.micEnabled
        var received: AppMessage?
        client.subscribe { message in received = message }
        await deliverUI(client, stub: stub, action: "drawer_popout")
        guard case .ui(let cmd) = received else { return XCTFail("expected forwarded .ui") }
        XCTAssertEqual(cmd.action, "drawer_popout")
        XCTAssertEqual(client.micEnabled, before)   // client state unchanged (C5)
        XCTAssertTrue(stub.sentFrames.isEmpty)      // no outbound frame
    }

    func testSubscribeReturnsWorkingUnsubscribe() async {
        let (client, stub) = makeClient()
        await client.connect()
        var callCount = 0
        let subscription = client.subscribe { _ in callCount += 1 }
        await deliverUI(client, stub: stub, action: "drawer_popout")
        subscription.cancel()
        await deliverUI(client, stub: stub, action: "drawer_popin")
        XCTAssertEqual(callCount, 1)
    }

    func testSubscriptionDeinitUnsubscribes() async {
        let (client, stub) = makeClient()
        await client.connect()
        var callCount = 0
        do {
            let subscription = client.subscribe { _ in callCount += 1 }
            _ = subscription
        }
        await deliverUI(client, stub: stub, action: "drawer_popout")
        XCTAssertEqual(callCount, 0)
    }

    func testDisconnectPreservesVoicesAndTranscript() async {
        let (client, stub) = makeClient()
        await client.connect()
        stub.simulateReceivedFrame(Data("""
        {"type":"voice/catalog","voices":[{"id":"jarvis","label":"Jarvis"}],"current":"jarvis"}
        """.utf8))
        await flushMainActor()
        XCTAssertEqual(client.voices.count, 1)

        await client.disconnect()

        XCTAssertEqual(client.voices.count, 1)     // preserved
        XCTAssertEqual(client.currentVoice, "jarvis")
        XCTAssertEqual(client.state, .offline)
        XCTAssertEqual(client.botIsSpeaking, false)
    }

    func testUnauthorizedConnectDoesNotRetry() async {
        let stub = StubTransport()
        stub.connectError = JarvisError.unauthorized
        let (client, _) = makeClient(stub: stub)
        await client.connect()
        XCTAssertEqual(client.state, .failed("Token required"))
        XCTAssertEqual(stub.connectCallCount, 1)   // no retry
    }

    func testReconnectAfterDisconnectBuildsNewPeerConnection() async {
        let (client, stub) = makeClient()
        await client.connect()
        await client.disconnect()
        await client.connect()
        XCTAssertEqual(stub.connectCallCount, 2)   // fresh session, not a no-op second click (F3)
    }

    func testKeepAliveStallFailsTheSession() async {
        let (client, stub) = makeClient()
        await client.connect()
        stub.simulateDisconnected(error: JarvisError.transport("keep-alive stalled"))
        await flushMainActor()
        if case .failed(let message) = client.state {
            XCTAssertTrue(message.contains("keep-alive stalled"))
        } else {
            XCTFail("expected .failed after a keep-alive stall")
        }
    }

    func testPeerLeftDisconnects() async {
        let (client, stub) = makeClient()
        await client.connect()
        // The stub's stand-in for peerLeft: real DirectWebRTCTransport
        // intercepts the peerLeft signalling frame internally (§5 step
        // 12) and calls transportDidDisconnect(error: nil) itself; the
        // stub here plays the transport's role directly.
        stub.simulateDisconnected(error: nil)
        await flushMainActor()
        XCTAssertEqual(client.state, .offline)
    }

    func testTwoStreamsBothReceiveEveryMessage() async {
        let (client, stub) = makeClient()
        await client.connect()
        let stream1 = client.messageStream()
        let stream2 = client.messageStream()
        var iterator1 = stream1.makeAsyncIterator()
        var iterator2 = stream2.makeAsyncIterator()

        await deliverUI(client, stub: stub, action: "drawer_popout")
        await deliverUI(client, stub: stub, action: "drawer_popin")
        await deliverUI(client, stub: stub, action: "overlay_dismiss")

        var received1: [AppMessage] = []
        var received2: [AppMessage] = []
        for _ in 0..<3 {
            if let m = await iterator1.next() { received1.append(m) }
        }
        for _ in 0..<3 {
            if let m = await iterator2.next() { received2.append(m) }
        }
        XCTAssertEqual(received1.count, 3)
        XCTAssertEqual(received2.count, 3)   // F9 fan-out; not single-consumer
    }

    func testStreamBufferDropsOldest() async {
        let (client, stub) = makeClient()
        await client.connect()
        let stream = client.messageStream()   // undrained
        let extra = 5
        for i in 0..<(JarvisTuning.messageStreamBuffer + extra) {
            await deliverUI(client, stub: stub, action: "drawer_tab", tab: "t\(i)")
        }
        var iterator = stream.makeAsyncIterator()
        var count = 0
        var firstTab: String?
        while let message = await iterator.next() {
            if case .ui(let cmd) = message, firstTab == nil { firstTab = cmd.tab }
            count += 1
            if count >= JarvisTuning.messageStreamBuffer { break }
        }
        XCTAssertEqual(count, JarvisTuning.messageStreamBuffer)
        // The oldest `extra` were dropped, so the first surviving tab is "t5".
        XCTAssertEqual(firstTab, "t\(extra)")
    }

    /// The hold-off itself lives in SpeakingGate (AudioSession.swift), a
    /// pure state machine BotSpeakingDetector drives with real RMS values
    /// computed over RTCAudioBuffer — deliberately factored out so it is
    /// testable here with a synthetic RMS sequence and no WebRTC type.
    func testSpeakingHoldOffSuppressesInterWordGaps() {
        let gate = SpeakingGate()
        let t0 = Date()
        XCTAssertTrue(gate.observe(rms: 0.5, at: t0))              // crosses threshold -> speaking
        XCTAssertTrue(gate.isSpeaking)
        // A 0.3 s sub-threshold gap — shorter than speakingReleaseMS (400 ms).
        let changedDuringGap = gate.observe(rms: 0.001, at: t0.addingTimeInterval(0.3))
        XCTAssertFalse(changedDuringGap)
        XCTAssertTrue(gate.isSpeaking)   // must NOT drop during the gap
        // Speech resumes before the release window elapses.
        XCTAssertFalse(gate.observe(rms: 0.5, at: t0.addingTimeInterval(0.35)))
        XCTAssertTrue(gate.isSpeaking)
        // Now a real turn boundary: silence past the release window.
        let changedAtBoundary = gate.observe(rms: 0.001, at: t0.addingTimeInterval(0.35 + 0.45))
        XCTAssertTrue(changedAtBoundary)
        XCTAssertFalse(gate.isSpeaking)
    }

    /// JarvisClient itself must not invent a second gate on top of the
    /// transport's already-gated signal — it reflects botIsSpeaking
    /// verbatim.
    func testJarvisClientReflectsTransportSpeakingSignalVerbatim() async {
        let (client, stub) = makeClient()
        await client.connect()
        stub.simulateBotSpeaking(true)
        await flushMainActor()
        XCTAssertTrue(client.botIsSpeaking)
        stub.simulateBotSpeaking(false)
        await flushMainActor()
        XCTAssertFalse(client.botIsSpeaking)
    }
}
