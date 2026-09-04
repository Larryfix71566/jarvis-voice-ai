import Foundation
import WebRTC
#if os(iOS)
import AVFoundation
#endif

/// N9 / §5 step 8: capture format, echo cancellation, and the one
/// mechanism (review F12) both platforms share for botIsSpeaking.
public enum AudioSession {
    /// The first THREE keys are the A1 protections web/src/micConstraints.ts
    /// forces on every getUserMedia call (echoCancellation, noiseSuppression,
    /// autoGainControl). googHighpassFilter is a NATIVE-ONLY extra (review
    /// F18) restoring a default the browser applies for free — not web
    /// parity, a correction of a native gap.
    public static let captureConstraints = RTCMediaConstraints(
        mandatoryConstraints: [
            "googEchoCancellation": "true",
            "googAutoGainControl": "true",
            "googNoiseSuppression": "true",
            "googHighpassFilter": "true",
        ],
        optionalConstraints: nil
    )

    #if os(iOS)
    /// .voiceChat routes input through VPIO, which is why the iOS wake
    /// listener is out of scope in T1.2 (N10 rule 3).
    public static func activate() {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
        } catch {
            // Logged, not thrown — a failed audio-session activation
            // should not prevent the signalling/data-channel path from
            // reporting its own, more specific error.
        }
    }

    public static func deactivate() {
        try? AVAudioSession.sharedInstance().setActive(false)
    }
    #else
    // macOS: no AVAudioSession. Echo cancellation comes from the
    // constraints above plus the system's default input processing.
    public static func activate() {}
    public static func deactivate() {}
    #endif
}

/// Pure threshold + hold-off state machine, deliberately independent of
/// any WebRTC type so it is unit-testable with a synthetic RMS sequence
/// (§7.5 testSpeakingHoldOffSuppressesInterWordGaps) without a real
/// audio buffer. `observe` returns whether THIS call flipped the gate.
///
/// Currently UNDRIVEN — see the note below on why no audio source in
/// this WebRTC build can feed it. Kept because it is the half that does
/// not depend on the mechanism.
final class SpeakingGate {
    private(set) var isSpeaking = false
    private var lastAboveThresholdAt: Date = .distantPast

    @discardableResult
    func observe(rms: Double, at time: Date = Date()) -> Bool {
        if rms > JarvisTuning.speakingLevelThreshold {
            lastAboveThresholdAt = time
            if !isSpeaking {
                isSpeaking = true
                return true
            }
        } else if isSpeaking {
            let elapsedMS = time.timeIntervalSince(lastAboveThresholdAt) * 1000
            if elapsedMS >= Double(JarvisTuning.speakingReleaseMS) {
                isSpeaking = false
                return true
            }
        }
        return false
    }
}

// MARK: - botIsSpeaking: DEGRADED on this WebRTC build (plan §5 step 8)
//
// The plan's chosen mechanism (review F12) was: register an audio
// renderer on the remote RTCAudioTrack and compute RMS over each
// delivered buffer. **That API does not exist in this dependency.**
// Verified against the resolved framework headers at
// .build/…/WebRTC.framework/Headers on 2026-08-28:
//
//   - RTCAudioTrack.h declares exactly one member, `source`; it inherits
//     only kind/trackId/isEnabled/readyState from RTCMediaStreamTrack.
//     There is no addRenderer:/removeRenderer:.
//   - `grep -rn -i renderer` across every header matches ONLY
//     RTCVideoRenderer / RTCVideoTrack / RTCMTLNSVideoView. There is no
//     RTCAudioRenderer and no RTCAudioBuffer anywhere in M120.
//
// (Those symbols exist in newer libwebrtc branches, which is where the
// plan's spec came from — they are not reachable from stasel/WebRTC
// 120.0.0, the Branch B dependency this package actually resolves.)
//
// The plan anticipated exactly this and wrote the degradation itself,
// so this is the documented path, NOT an improvised substitute (§0.7
// forbids inventing one):
//
//   "if the renderer API proves unavailable on macOS 26, it degrades to
//    always-false with a logged botIsSpeaking_unavailable, and the
//    wake-pause falls back to 'listener runs only while muted'
//    (N10 rule 1), which is already true."
//
// So: no detector is attached, `botIsSpeaking` stays false for the whole
// session, and the transport logs `botIsSpeaking_unavailable` once per
// connect. What this costs, stated plainly rather than buried:
//   - MortimerHost's speaking label never lights. Cosmetic.
//   - N10 rule 4 (pause the wake listener while the bot speaks) cannot
//     fire. Rule 1 still holds — the listener only runs while connected
//     AND muted — but the wake tap is not echo-cancelled, so while muted
//     with the wake word on, the sidecar can score Mortimer's own TTS
//     and self-trigger. §8 V8 is where that shows up if it is real.
//   - G1(b) does not depend on botIsSpeaking, so this does not gate it.
//
// SpeakingGate below is kept, intact and unit-tested (§7.5), because it
// is the mechanism-independent half: whatever future source supplies an
// audio level (a newer WebRTC with the renderer API, or an
// RTCStatisticsReport `audioLevel` poll — a design decision for T1.3 or
// its own plan, deliberately not made here), it plugs straight in.
