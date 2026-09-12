import XCTest
@testable import JarvisKit

/// Vectors produced by pipecat-ai 1.4.0's own compiled schema
/// (`pipecat/frames/protobufs/frames_pb2.py`, protobuf 6.33.6, from the
/// deployment checkout's `.venv`) on 2026-09-12 — the server-side shapes
/// exactly as `ProtobufFrameSerializer.serialize` emits them (with `id`
/// and `name` set, which the client must skip), plus the two minimal
/// client shapes the server was shown to deserialize back into
/// `InputAudioRawFrame(16000, 1, b'\x01\x02\x03\x04')` and
/// `InputTransportMessageFrame`.
final class PipecatFrameCodecTests: XCTestCase {
    private func hex(_ s: String) -> Data {
        var data = Data(); var i = s.startIndex
        while i < s.endIndex { let j = s.index(i, offsetBy: 2); data.append(UInt8(s[i..<j], radix: 16)!); i = j }
        return data
    }

    func testClientAudioEncodesExactlyWhatPipecatDeserializesIntoInputAudioRawFrame() {
        let encoded = PipecatFrameCodec.encodeAudio(pcm: Data([1, 2, 3, 4]), sampleRate: 16_000, channels: 1)
        XCTAssertEqual(encoded, hex("120b1a040102030420807d2801"))
        XCTAssertEqual(PipecatFrameCodec.decode(encoded), .audio(pcm: Data([1, 2, 3, 4]), sampleRate: 16_000, channels: 1))
    }

    func testClientMessageEncodesExactlyWhatPipecatDeserializesIntoInputTransportMessageFrame() {
        let json = Data(#"{"type": "voice/set", "voice": "x"}"#.utf8)
        let encoded = PipecatFrameCodec.encodeMessage(json: json)
        XCTAssertEqual(encoded, hex("22250a237b2274797065223a2022766f6963652f736574222c2022766f696365223a202278227d"))
        XCTAssertEqual(PipecatFrameCodec.decode(encoded), .message(json: json))
    }

    func testServerAudioFrameDecodesWithIdAndNameSkipped() {
        let frame = PipecatFrameCodec.decode(hex("1229080712154f7574707574417564696f5261774672616d6523371a08000000400080ff7f20c0bb012801"))
        XCTAssertEqual(frame, .audio(pcm: Data([0, 0, 0, 0x40, 0, 0x80, 0xff, 0x7f]), sampleRate: 24_000, channels: 1))
    }

    func testServerMessageFrameCarriesTheRtviEnvelopeJSONUnchanged() throws {
        let frame = PipecatFrameCodec.decode(hex("226f0a6d7b226964223a2022616263222c20226c6162656c223a2022727476692d6169222c202274797065223a20227365727665722d6d657373616765222c202264617461223a207b2274797065223a2022646973706c6179222c2022646973706c6179223a207b226b223a20317d7d7d"))
        guard case .message(let json)? = frame else { return XCTFail("\(String(describing: frame))") }
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: json) as? [String: Any])
        XCTAssertEqual(object["label"] as? String, "rtvi-ai")
        XCTAssertEqual(object["type"] as? String, "server-message")
        XCTAssertEqual((object["data"] as? [String: Any])?["type"] as? String, "display")
    }

    func testInterruptionTextAndTranscriptionFramesDecode() {
        XCTAssertEqual(PipecatFrameCodec.decode(hex("2a1708091213496e74657272757074696f6e4672616d652339")), .interruption)
        XCTAssertEqual(PipecatFrameCodec.decode(hex("0a170803120b546578744672616d6523331a0668c3a96c6c6f")), .text("héllo"))
        XCTAssertEqual(PipecatFrameCodec.decode(hex("1a36080412145472616e736372697074696f6e4672616d6523341a026869220275312a14323032362d30392d31325430303a30303a30305a")),
                       .transcription(text: "hi", userID: "u1", timestamp: "2026-09-12T00:00:00Z"))
    }

    func testMalformedInputIsRefusedNotMisread() {
        let audio = hex("120b1a040102030420807d2801")
        XCTAssertNil(PipecatFrameCodec.decode(Data()), "empty Frame")
        XCTAssertNil(PipecatFrameCodec.decode(audio.prefix(audio.count - 1)), "truncated inner varint/bytes")
        XCTAssertNil(PipecatFrameCodec.decode(hex("1205")), "length past the end")
        XCTAssertNil(PipecatFrameCodec.decode(hex("3200")), "field 6 is not a Frame member")
        XCTAssertNil(PipecatFrameCodec.decode(hex("1001")), "a varint where a message is required")
        XCTAssertNil(PipecatFrameCodec.decode(hex("12ffffffffffffffffffff01")), "overlong varint")
        XCTAssertNil(PipecatFrameCodec.decode(hex("0a020a")), "unterminated nested field")
    }

    func testVarintsAboveOneByteAndLargePayloadsRoundTrip() {
        let pcm = Data((0..<20_000).map { UInt8($0 & 0xff) })
        let encoded = PipecatFrameCodec.encodeAudio(pcm: pcm, sampleRate: 48_000, channels: 2)
        XCTAssertEqual(PipecatFrameCodec.decode(encoded), .audio(pcm: pcm, sampleRate: 48_000, channels: 2))
        // inner = 1 + 3 (len 20,000 = a0 9c 01) + 20,000 + 1 + 3 (48,000) + 1 + 1 = 20,010;
        // outer = 1 + 3 (len 20,010 = aa 9c 01) + 20,010 = 20,014.
        XCTAssertEqual(encoded.prefix(4), Data([0x12, 0xaa, 0x9c, 0x01]))
        XCTAssertEqual(encoded.count, 20_014)
    }
}
