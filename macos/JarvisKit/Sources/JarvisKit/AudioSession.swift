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
/// RTCAudioBuffer. `observe` returns whether THIS call flipped the gate.
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

/// botIsSpeaking — ONE mechanism for both platforms (review F12).
/// RTCAudioSession is iOS-only and unavailable on macOS (this plan's
/// primary platform), so instead: register on the remote RTCAudioTrack
/// and compute RMS over each delivered RTCAudioBuffer. Reports `true`
/// when RMS exceeds JarvisTuning.speakingLevelThreshold and `false` only
/// after it has stayed below for JarvisTuning.speakingReleaseMS — a
/// hold-off longer than inter-word gaps so a bound view does not strobe.
///
/// If the renderer API proves unavailable on macOS 26 at build time, the
/// call site (DirectWebRTCTransport.attachSpeakingDetector) simply never
/// attaches one and botIsSpeaking degrades to always-false with a logged
/// "botIsSpeaking_unavailable" — the wake-pause rule already falls back
/// to "listener runs only while muted" (N10 rule 1), which holds
/// regardless.
final class BotSpeakingDetector: NSObject, RTCAudioRenderer {
    private let onChange: (Bool) -> Void
    private let gate = SpeakingGate()
    private let lock = NSLock()

    init(onChange: @escaping (Bool) -> Void) {
        self.onChange = onChange
    }

    /// Called on a non-main audio thread for every delivered buffer.
    func renderSample(_ audioBuffer: RTCAudioBuffer) {
        let rms = Self.rms(of: audioBuffer)
        lock.lock()
        let changed = gate.observe(rms: rms)
        let speaking = gate.isSpeaking
        lock.unlock()
        if changed { onChange(speaking) }
    }

    private static func rms(of buffer: RTCAudioBuffer) -> Double {
        guard buffer.channels > 0, buffer.frames > 0 else { return 0 }
        // First channel is sufficient for a speaking/not-speaking gate —
        // this bot's remote track is mono.
        let raw = buffer.rawBuffer(forChannel: 0)
        var sumSquares: Double = 0
        let frameCount = Int(buffer.frames)
        for i in 0..<frameCount {
            let sample = Double(raw[i])
            sumSquares += sample * sample
        }
        return (sumSquares / Double(frameCount)).squareRoot()
    }
}
