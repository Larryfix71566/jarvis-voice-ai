import Foundation
import SwiftUI
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

    /// Interface plan §4.3, barge-in: while eligible user audio has visual
    /// priority, Mortimer's continuing speech stays indicated by this small
    /// label until the actual interrupted/stopped event clears
    /// `assistantSpeaking`. Nil outside overlap (closure C2.2, gap G06).
    var overlapLabel: String? {
        activity == .user && assistantSpeaking ? "Mortimer still speaking" : nil
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

/// Larry's C6 easing rule: every per-frame constant is referenced to 60 Hz.
/// Invalid, negative and resume-sized deltas do not create a jump.
enum FrameRateIndependentEasing {
    static func ratio(dt: TimeInterval) -> Double {
        guard dt.isFinite, dt > 0 else { return 0 }
        return min(dt, 0.1) * 60
    }

    static func factor(_ reference: Double, dt: TimeInterval) -> Double {
        guard reference.isFinite else { return 0 }
        let k = min(1, max(0, reference))
        return 1 - pow(1 - k, ratio(dt: dt))
    }

    static func step(_ reference: Double, dt: TimeInterval) -> Double {
        reference * ratio(dt: dt)
    }
}

/// Ownership state for the orb's 350 ms hold. It uses MicControlsView's
/// pttOwned rule: only the gesture that acquired PTT may finish it, and a
/// cancelled/disappearing gesture restores the microphone's prior state.
struct OrbPushToTalkGuard {
    static let holdSeconds: TimeInterval = 0.350
    private(set) var pttOwned = false
    private(set) var held = false
    private(set) var restoreMicEnabled = false

    mutating func begin(micEnabled: Bool) -> Bool {
        guard !pttOwned else { return false }
        pttOwned = true
        held = false
        restoreMicEnabled = micEnabled
        return true
    }

    mutating func promote() -> Bool {
        guard pttOwned, !held else { return false }
        held = true
        return true
    }

    mutating func finish() -> Bool? {
        guard pttOwned else { return nil }
        let restore = held ? restoreMicEnabled : nil
        pttOwned = false
        held = false
        return restore
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
        let duration = target > level ? AudioPresentationTuning.attackSeconds : AudioPresentationTuning.releaseSeconds
        level += (target - level) * (1 - exp(-(now - previous) / duration))
        return level
    }
}

/// §4.3 barge-in indicator, retained after OrbFieldView's removal.
struct VoiceOverlapLabel: View {
    let presentation: VoicePresentationState?
    var body: some View {
        if let text = presentation?.overlapLabel {
            Text(text)
                .font(.caption2)
                .foregroundStyle(AudioPresentationTuning.assistantColor)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(text)
                .accessibilityAddTraits(.isStaticText)
        }
    }
}
