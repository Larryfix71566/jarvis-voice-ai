import Foundation

/// The five frames pipecat's `ProtobufFrameSerializer` puts on the
/// WebSocket (`pipecat/frames/frames.proto`, pipecat-ai 1.4.0):
///
///     message Frame { oneof frame {
///         TextFrame text = 1; AudioRawFrame audio = 2;
///         TranscriptionFrame transcription = 3; MessageFrame message = 4;
///         InterruptionFrame interruption = 5; } }
///     AudioRawFrame { uint64 id = 1; string name = 2; bytes audio = 3;
///                     uint32 sample_rate = 4; uint32 num_channels = 5;
///                     optional uint64 pts = 6; }
///     MessageFrame  { string data = 1; }        // JSON of the app message
///     TextFrame     { id = 1; name = 2; string text = 3; }
///     TranscriptionFrame { id; name; string text = 3; string user_id = 4;
///                          string timestamp = 5; }
///     InterruptionFrame { id = 1; name = 2; }
///
/// Hand-written protobuf for exactly this schema (§3.1 findings): varints
/// and length-delimited fields are all it needs, so no SwiftProtobuf
/// dependency. Unknown fields (`id`, `name`, `pts`, anything newer) are
/// skipped on decode; nothing outside the schema is ever encoded.
enum PipecatFrame: Equatable {
    case text(String)
    case audio(pcm: Data, sampleRate: Int, channels: Int)
    case transcription(text: String, userID: String, timestamp: String)
    case message(json: Data)
    case interruption
}

enum PipecatFrameCodec {
    // MARK: Encode (client → server)

    /// `Frame{ audio{ audio, sample_rate, num_channels } }` — the shape the
    /// server deserializes into `InputAudioRawFrame`.
    static func encodeAudio(pcm: Data, sampleRate: Int, channels: Int) -> Data {
        var inner = Data()
        appendLengthDelimited(&inner, field: 3, bytes: pcm)
        appendVarint(&inner, field: 4, value: UInt64(max(0, sampleRate)))
        appendVarint(&inner, field: 5, value: UInt64(max(0, channels)))
        var out = Data()
        appendLengthDelimited(&out, field: 2, bytes: inner)
        return out
    }

    /// `Frame{ message{ data: <json> } }` — deserialized by the server into
    /// `InputTransportMessageFrame(message: json.loads(data))`.
    static func encodeMessage(json: Data) -> Data {
        var inner = Data()
        appendLengthDelimited(&inner, field: 1, bytes: json)
        var out = Data()
        appendLengthDelimited(&out, field: 4, bytes: inner)
        return out
    }

    // MARK: Decode (server → client)

    /// nil for anything malformed, for an empty `Frame`, and for a oneof
    /// member outside 1…5. Fields inside the member that the client does
    /// not use are skipped.
    static func decode(_ data: Data) -> PipecatFrame? {
        var reader = Reader(data)
        var result: PipecatFrame?
        while !reader.atEnd {
            guard let (field, wire) = reader.key() else { return nil }
            guard wire == 2, let body = reader.lengthDelimited() else {
                // A Frame has only message-typed members; anything else is
                // not this schema.
                return nil
            }
            switch field {
            case 1:
                guard let text = decodeStrings(body, wanted: [3]) else { return nil }
                result = .text(text[3] ?? "")
            case 2:
                guard let audio = decodeAudio(body) else { return nil }
                result = audio
            case 3:
                guard let s = decodeStrings(body, wanted: [3, 4, 5]) else { return nil }
                result = .transcription(text: s[3] ?? "", userID: s[4] ?? "", timestamp: s[5] ?? "")
            case 4:
                guard let json = decodeBytes(body, wanted: 1) else { return nil }
                result = .message(json: json ?? Data())
            case 5:
                guard skipAll(body) else { return nil }
                result = .interruption
            default:
                return nil
            }
        }
        return result
    }

    private static func decodeAudio(_ body: Data) -> PipecatFrame? {
        var reader = Reader(body)
        var pcm = Data(), rate = 0, channels = 0
        while !reader.atEnd {
            guard let (field, wire) = reader.key() else { return nil }
            switch (field, wire) {
            case (3, 2):
                guard let bytes = reader.lengthDelimited() else { return nil }
                pcm = bytes
            case (4, 0):
                guard let v = reader.varint(), v <= UInt64(Int32.max) else { return nil }
                rate = Int(v)
            case (5, 0):
                guard let v = reader.varint(), v <= UInt64(Int32.max) else { return nil }
                channels = Int(v)
            default:
                guard reader.skip(wire: wire) else { return nil }
            }
        }
        return .audio(pcm: pcm, sampleRate: rate, channels: channels)
    }

    /// Collects the UTF-8 string fields in `wanted`; skips the rest.
    private static func decodeStrings(_ body: Data, wanted: Set<Int>) -> [Int: String]? {
        var reader = Reader(body)
        var out: [Int: String] = [:]
        while !reader.atEnd {
            guard let (field, wire) = reader.key() else { return nil }
            if wanted.contains(field), wire == 2 {
                guard let bytes = reader.lengthDelimited(), let s = String(data: bytes, encoding: .utf8) else { return nil }
                out[field] = s
            } else {
                guard reader.skip(wire: wire) else { return nil }
            }
        }
        return out
    }

    /// The bytes of one length-delimited field (last occurrence wins, as
    /// protobuf merges), or `.some(nil)` when it is absent.
    private static func decodeBytes(_ body: Data, wanted: Int) -> Data?? {
        var reader = Reader(body)
        var out: Data?
        while !reader.atEnd {
            guard let (field, wire) = reader.key() else { return nil }
            if field == wanted, wire == 2 {
                guard let bytes = reader.lengthDelimited() else { return nil }
                out = bytes
            } else {
                guard reader.skip(wire: wire) else { return nil }
            }
        }
        return .some(out)
    }

    private static func skipAll(_ body: Data) -> Bool {
        var reader = Reader(body)
        while !reader.atEnd {
            guard let (_, wire) = reader.key(), reader.skip(wire: wire) else { return false }
        }
        return true
    }

    // MARK: Wire primitives

    private static func appendVarint(_ out: inout Data, field: Int, value: UInt64) {
        appendRawVarint(&out, UInt64(field << 3))
        appendRawVarint(&out, value)
    }

    private static func appendLengthDelimited(_ out: inout Data, field: Int, bytes: Data) {
        appendRawVarint(&out, UInt64(field << 3 | 2))
        appendRawVarint(&out, UInt64(bytes.count))
        out.append(bytes)
    }

    private static func appendRawVarint(_ out: inout Data, _ value: UInt64) {
        var v = value
        while v >= 0x80 {
            out.append(UInt8(v & 0x7f) | 0x80)
            v >>= 7
        }
        out.append(UInt8(v))
    }

    private struct Reader {
        private let bytes: [UInt8]
        private var index = 0
        init(_ data: Data) { bytes = [UInt8](data) }
        var atEnd: Bool { index >= bytes.count }

        mutating func varint() -> UInt64? {
            var result: UInt64 = 0
            var shift: UInt64 = 0
            while index < bytes.count {
                let byte = bytes[index]; index += 1
                if shift >= 64 { return nil }
                result |= UInt64(byte & 0x7f) << shift
                if byte & 0x80 == 0 { return result }
                shift += 7
            }
            return nil
        }

        mutating func key() -> (field: Int, wire: Int)? {
            guard let k = varint(), k >> 3 <= UInt64(Int32.max), k >> 3 > 0 else { return nil }
            return (Int(k >> 3), Int(k & 7))
        }

        mutating func lengthDelimited() -> Data? {
            guard let length = varint(), length <= UInt64(bytes.count - index) else { return nil }
            let start = index
            index += Int(length)
            return Data(bytes[start..<index])
        }

        mutating func skip(wire: Int) -> Bool {
            switch wire {
            case 0: return varint() != nil
            case 1: guard bytes.count - index >= 8 else { return false }; index += 8; return true
            case 2: return lengthDelimited() != nil
            case 5: guard bytes.count - index >= 4 else { return false }; index += 4; return true
            default: return false   // groups (3, 4) are not proto3
            }
        }
    }
}
