import Foundation
import JarvisKit

/// APP plan §3 P13 — derived exactly as the web derives it
/// (App.tsx:194-206 / voiceState.ts): connection state + botIsSpeaking,
/// nothing else. Not JarvisClient's ConnectionState — listening/speaking
/// are view-layer derivations (CORE §3 N5's reasoning).
enum VoiceState: String {
    case offline, connecting, listening, speaking

    static func derive(state: JarvisClient.ConnectionState, botIsSpeaking: Bool) -> VoiceState {
        switch state {
        case .connected: return botIsSpeaking ? .speaking : .listening
        case .connecting: return .connecting
        case .offline, .failed: return .offline
        }
    }

    /// OrbField.tsx STATE_LABEL, verbatim — never the raw enum name on
    /// screen (parity sweep 2026-08-30).
    var label: String {
        switch self {
        case .offline: return "Standby"
        case .connecting: return "Spinning up"
        case .listening: return "Listening"
        case .speaking: return "Speaking"
        }
    }
}
