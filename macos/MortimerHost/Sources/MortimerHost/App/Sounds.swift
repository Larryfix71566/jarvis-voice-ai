import AVFoundation
import Foundation

/// Mortimer's four-tone audio identity, ported from web/src/sounds.ts
/// (MORTIMER_ENGAGEMENT_DESIGN_PLAN.md E3): synthesized, zero assets,
/// master gain 0.08 — texture, not notification noise. The tone specs
/// (frequency/duration/waveform/peak) are sounds.ts's values verbatim.
///
/// Toggle persisted at UserDefaults "mortimer.sounds" (default ON) — the
/// same key name the web used in localStorage, so the semantics carry
/// over one-to-one. No per-tone settings (sounds.ts:14).
///
/// Rendering: each tone is synthesized into one AVAudioPCMBuffer (with
/// the click-free 10ms-attack / exponential-decay envelope sounds.ts's
/// `note()` builds in Web Audio) and played through a shared
/// AVAudioEngine + AVAudioPlayerNode. The engine starts lazily on first
/// play and failures are silently swallowed — a sound that can't play
/// must never break the console (sounds.ts:69 "silently a no-op").
@MainActor
enum Sounds {
    enum Tone: String {
        case boot, tick, done, fail
    }

    private static let masterGain: Float = 0.08
    private static let sampleRate = 44_100.0

    // nonisolated: only touches UserDefaults, and @State initializers
    // (not MainActor-isolated) read it.
    nonisolated static var enabled: Bool {
        get { UserDefaults.standard.string(forKey: "mortimer.sounds") != "off" }
        set { UserDefaults.standard.set(newValue ? "on" : "off", forKey: "mortimer.sounds") }
    }

    private static var engine: AVAudioEngine?
    private static var player: AVAudioPlayerNode?
    private static var format: AVAudioFormat?

    static func play(_ tone: Tone) {
        guard enabled else { return }
        guard let (player, format) = startEngineIfNeeded() else { return }
        guard let buffer = buffer(for: tone, format: format) else { return }
        player.scheduleBuffer(buffer, completionHandler: nil)
        if !player.isPlaying { player.play() }
    }

    private static func startEngineIfNeeded() -> (AVAudioPlayerNode, AVAudioFormat)? {
        if let player, let format, engine?.isRunning == true { return (player, format) }
        let engine = self.engine ?? AVAudioEngine()
        let player = self.player ?? AVAudioPlayerNode()
        guard let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1) else { return nil }
        if player.engine == nil {
            engine.attach(player)
            engine.connect(player, to: engine.mainMixerNode, format: format)
        }
        if !engine.isRunning {
            do { try engine.start() } catch { return nil }
        }
        self.engine = engine
        self.player = player
        self.format = format
        return (player, format)
    }

    private enum Waveform { case sine, triangle }

    /// sounds.ts note(): 10ms linear attack to `peak`, exponential decay
    /// to 0.001 over the note's duration.
    private static func writeNote(
        into samples: UnsafeMutablePointer<Float>, frameCount: Int,
        waveform: Waveform, frequency: Double,
        startSeconds: Double, durationSeconds: Double, peak: Float
    ) {
        let attack = 0.01
        let start = Int(startSeconds * sampleRate)
        let notes = Int(durationSeconds * sampleRate)
        for i in 0..<notes {
            let frame = start + i
            guard frame < frameCount else { break }
            let t = Double(i) / sampleRate
            let envelope: Float
            if t < attack {
                envelope = peak * Float(t / attack)
            } else {
                // exponentialRampToValueAtTime(0.001, start + duration)
                let progress = (t - attack) / max(durationSeconds - attack, 0.001)
                envelope = peak * Float(pow(0.001 / Double(peak), progress))
            }
            let phase = frequency * t
            let wave: Double
            switch waveform {
            case .sine:
                wave = sin(2 * .pi * phase)
            case .triangle:
                let frac = phase - floor(phase)
                wave = 4 * abs(frac - 0.5) - 1
            }
            samples[frame] += envelope * Float(wave)
        }
    }

    private static func buffer(for tone: Tone, format: AVAudioFormat) -> AVAudioPCMBuffer? {
        // Total length: last note's end + the 20ms stop margin.
        let totalSeconds: Double
        switch tone {
        case .boot: totalSeconds = 0.20
        case .tick: totalSeconds = 0.05
        case .done: totalSeconds = 0.14
        case .fail: totalSeconds = 0.18
        }
        let frameCount = AVAudioFrameCount(totalSeconds * sampleRate)
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount),
              let samples = buffer.floatChannelData?[0] else { return nil }
        buffer.frameLength = frameCount
        samples.update(repeating: 0, count: Int(frameCount))

        switch tone {
        case .boot:
            // Two ascending sines, 180ms total — the arrival chirp.
            writeNote(into: samples, frameCount: Int(frameCount), waveform: .sine,
                      frequency: 520, startSeconds: 0, durationSeconds: 0.09, peak: masterGain)
            writeNote(into: samples, frameCount: Int(frameCount), waveform: .sine,
                      frequency: 780, startSeconds: 0.09, durationSeconds: 0.09, peak: masterGain)
        case .tick:
            // 1.2 kHz blip, 30ms — a delegation left the station.
            writeNote(into: samples, frameCount: Int(frameCount), waveform: .sine,
                      frequency: 1200, startSeconds: 0, durationSeconds: 0.03, peak: masterGain * 0.6)
        case .done:
            // 660+990 Hz dyad, 120ms — work came back clean.
            writeNote(into: samples, frameCount: Int(frameCount), waveform: .sine,
                      frequency: 660, startSeconds: 0, durationSeconds: 0.12, peak: masterGain)
            writeNote(into: samples, frameCount: Int(frameCount), waveform: .sine,
                      frequency: 990, startSeconds: 0, durationSeconds: 0.12, peak: masterGain * 0.7)
        case .fail:
            // 220 Hz triangle, 160ms — something went wrong.
            writeNote(into: samples, frameCount: Int(frameCount), waveform: .triangle,
                      frequency: 220, startSeconds: 0, durationSeconds: 0.16, peak: masterGain)
        }
        return buffer
    }
}
