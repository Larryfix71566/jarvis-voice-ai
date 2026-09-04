import Foundation

/// N8: outbound messages use the RAW payload shape, not the client-js
/// envelope. A closed enum so no caller can invent a type the bot does
/// not handle.
public enum ClientMessage: Sendable, Equatable {
    case voiceSet(voice: String)
    case uiNoop(reason: String)

    /// `if not reason or len(reason) > 200` in pipeline.py drops empty/over-200 reasons.
    public static func noop(_ reason: String) -> ClientMessage? {
        let r = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (1...200).contains(r.count) else { return nil }
        return .uiNoop(reason: r)
    }

    /// The RAW shape (N8): pipeline.py:728 returns a non-"client-message"
    /// dict verbatim, so no envelope is needed or wanted.
    func jsonData() throws -> Data {
        switch self {
        case .voiceSet(let v):  return try JSONEncoder().encode(["type": "voice/set", "voice": v])
        case .uiNoop(let r):    return try JSONEncoder().encode(["type": "ui/noop", "reason": r])
        }
    }
}
