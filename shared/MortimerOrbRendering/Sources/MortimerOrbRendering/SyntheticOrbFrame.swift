import Foundation

/// A deterministic phone preview waveform. This has no input from a session,
/// microphone, audio engine, transport, or device.
public struct SyntheticOrbFrame: Equatable, Sendable {
    public let phase: Double
    public let level: Double

    public init(elapsed: TimeInterval, reduceMotion: Bool) {
        let validElapsed = elapsed.isFinite ? max(0, elapsed) : 0
        let seconds = reduceMotion ? 0 : min(3_600, validElapsed)
        phase = seconds * Double.pi / 6
        level = 0.27 + 0.07 * sin(seconds * Double.pi / 2)
    }
}
