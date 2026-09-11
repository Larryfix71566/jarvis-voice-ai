import Foundation
import JarvisKit

/// Read-only presentation. It never changes capture, wake, speaker gating or
/// interruption. A valid input level means eligible audio, not understood text.
struct VoicePresentationState: Equatable {
    enum Activity: Equatable { case offline, connecting, listening, user, assistant, thinking, muted }
    let activity: Activity
    let userLevel: Double?
    let outputLevel: Double?
    let microphoneMuted: Bool
    let assistantSpeaking: Bool

    var label: String {
        switch activity {
        case .offline: return "Standby"
        case .connecting: return "Connecting"
        case .listening: return "Listening"
        case .user: return "Hearing you"
        case .assistant: return "Mortimer speaking"
        case .thinking: return "Thinking"
        case .muted: return "Muted"
        }
    }

    var audioLevelUnavailable: Bool {
        switch activity {
        case .offline, .connecting: return false
        default: return (!microphoneMuted && userLevel == nil) || (assistantSpeaking && outputLevel == nil)
        }
    }

    static func derive(connection: JarvisClient.ConnectionState, microphoneEnabled: Bool,
                       botSpeaking: Bool, thinking: Bool, snapshot: AudioActivitySnapshot?,
                       generation: UUID, now: TimeInterval) -> Self {
        let unavailable: (Activity) -> Self = { activity in
            Self(activity: activity, userLevel: nil, outputLevel: nil,
                 microphoneMuted: !microphoneEnabled, assistantSpeaking: false)
        }
        switch connection {
        case .offline, .failed: return unavailable(.offline)
        case .connecting: return unavailable(.connecting)
        case .connected: break
        }
        let current = snapshot.flatMap { sample -> AudioActivitySnapshot? in
            guard sample.generation == generation, now.isFinite, sample.timestamp.isFinite,
                  now >= sample.timestamp, now - sample.timestamp < AudioActivityAccumulator.staleAfter else { return nil }
            return sample
        }
        func fresh(_ level: Double?, measuredAt: TimeInterval?) -> Double? {
            guard let measuredAt, measuredAt.isFinite, now >= measuredAt,
                  now - measuredAt < AudioActivityAccumulator.staleAfter else { return nil }
            return level
        }
        let input = microphoneEnabled && current?.microphoneEligible == true ? fresh(current?.userLevel, measuredAt: current?.userMeasuredAt) : nil
        let output = fresh(current?.outputLevel, measuredAt: current?.outputMeasuredAt)
        let assistantSpeaking = botSpeaking || (output ?? 0) > 0
        let activity: Activity
        if (input ?? 0) > 0 { activity = .user }
        else if assistantSpeaking { activity = .assistant }
        else if thinking { activity = .thinking }
        else { activity = microphoneEnabled ? .listening : .muted }
        return Self(activity: activity, userLevel: input, outputLevel: output,
                    microphoneMuted: !microphoneEnabled, assistantSpeaking: assistantSpeaking)
    }
}

/// Elapsed-time smoothing, independent of frame rate. Unavailable/muted input
/// clears immediately so smoothing cannot outlive the observation's deadline.
struct VoiceEnvelope {
    private(set) var level = 0.0
    private var last: TimeInterval?
    mutating func advance(target: Double?, now: TimeInterval) -> Double {
        guard now.isFinite else { level = 0; last = nil; return level }
        guard let target, target.isFinite, (0...1).contains(target) else {
            level = 0; last = now; return level
        }
        guard let previous = last, now >= previous else {
            level = 0; last = now; return level
        }
        last = now
        let duration = target > level ? 0.040 : 0.180
        level += (target - level) * (1 - exp(-(now - previous) / duration))
        return level
    }
}
