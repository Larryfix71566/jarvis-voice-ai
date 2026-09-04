import XCTest
@testable import JarvisKit

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
