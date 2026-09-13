import XCTest
@testable import JarvisKit

#if os(macOS)
/// The native path's wake source (§3.5). A stub socket stands in for
/// the sidecar so the framing and the mic-ownership rules are asserted
/// without a sidecar, a microphone, or a second AVAudioEngine.
@MainActor
final class WakeExternalFeedTests: XCTestCase {
    final class StubWakeSocket: WakeSocket {
        var onText: (@Sendable (String) -> Void)?
        var onFailure: (@Sendable (Error) -> Void)?
        private(set) var opens = 0
        private(set) var closes = 0
        private(set) var sent: [Data] = []
        func open() { opens += 1 }
        func send(_ data: Data) { sent.append(data) }
        func close() { closes += 1 }
    }

    private let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
                                      adminURL: URL(string: "http://127.0.0.1:7861")!,
                                      wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil)

    private func listener() -> (WakeWordListener, StubWakeSocket) {
        let socket = StubWakeSocket()
        let l = WakeWordListener(config: config, makeSocket: { _ in socket })
        return (l, socket)
    }

    func testExternalStartOpensTheSidecarSocketWithoutAnEngineOfItsOwn() async {
        let (l, socket) = listener()
        await l.start(source: .external)
        XCTAssertEqual(socket.opens, 1)
        XCTAssertEqual(l.source, .external)
        XCTAssertFalse(l.isUsingOwnEngine, "the native path must not open a second AVAudioEngine")
        XCTAssertEqual(l.availability, .available)
        await l.stop()
        XCTAssertEqual(socket.closes, 1)
    }

    func testFedAudioReachesTheSidecarAsWholeFramesOnly() async {
        let (l, socket) = listener()
        await l.start(source: .external)
        l.feed(Data(repeating: 7, count: JarvisTuning.wakeFrameBytes - 1))
        XCTAssertEqual(socket.sent.count, 0, "never a partial frame")
        l.feed(Data(repeating: 7, count: 1))
        XCTAssertEqual(socket.sent.count, 1)
        XCTAssertEqual(socket.sent[0].count, JarvisTuning.wakeFrameBytes)
        l.feed(Data(repeating: 7, count: JarvisTuning.wakeFrameBytes * 2 + 5))
        XCTAssertEqual(socket.sent.map(\.count), Array(repeating: JarvisTuning.wakeFrameBytes, count: 3))
        await l.stop()
    }

    func testFeedIsIgnoredWhenPausedStoppedOrOwningItsOwnEngine() async {
        let (l, socket) = listener()
        let frame = Data(repeating: 3, count: JarvisTuning.wakeFrameBytes)
        l.feed(frame)
        XCTAssertEqual(socket.sent.count, 0, "not started")
        await l.start(source: .external)
        l.setPaused(true)                       // N10 rule 4: bot speaking
        l.feed(frame)
        XCTAssertEqual(socket.sent.count, 0, "paused")
        l.setPaused(false)
        l.feed(frame)
        XCTAssertEqual(socket.sent.count, 1)
        await l.stop()
        l.feed(frame)
        XCTAssertEqual(socket.sent.count, 1, "stopped")
        // A listener that owns its own engine (the WebRTC path) must
        // ignore fed audio, so audio can never arrive twice.
        let (own, ownSocket) = listener()
        XCTAssertEqual(own.source, .ownEngine, "the WebRTC path's default")
        own.feed(frame)
        XCTAssertEqual(ownSocket.sent.count, 0)
    }
}
#endif

final class WakeWordFramingTests: XCTestCase {
    func testWakePCMFramesAreExactly2560Bytes() {
        var framer = WakeFramer()
        let input = Data(repeating: 0x11, count: 7000)
        let frames = framer.append(input)
        XCTAssertEqual(frames.count, 2)
        XCTAssertTrue(frames.allSatisfy { $0.count == JarvisTuning.wakeFrameBytes })   // server.py:86-89
        // 7000 - 2*2560 = 1880 bytes retained internally (verified by
        // feeding one more byte and confirming no third frame yet).
        var framer2 = WakeFramer()
        let more = framer2.append(Data(repeating: 0x22, count: 7000))
        XCTAssertEqual(more.count, 2)
        let extra = framer2.append(Data(repeating: 0x33, count: 680))   // 1880 + 680 = 2560
        XCTAssertEqual(extra.count, 1)
    }

    func testWakeFramerNeverEmitsPartial() {
        var framer = WakeFramer()
        let frames = framer.append(Data(repeating: 0x00, count: 100))
        XCTAssertEqual(frames.count, 0)
    }

    func testWakeMessageDecodes() {
        let json = """
        {"type":"wake","model":"mortimer","score":0.83}
        """
        let event = WakeFrameDecoder.decodeWakeEvent(from: Data(json.utf8))
        XCTAssertEqual(event, WakeEvent(model: "mortimer", score: 0.83))
    }

    func testNonWakeTextFrameIgnored() {
        let json = """
        {"type":"hello"}
        """
        let event = WakeFrameDecoder.decodeWakeEvent(from: Data(json.utf8))
        XCTAssertNil(event)   // wakeWord.ts:118 ignores everything else
    }
}
