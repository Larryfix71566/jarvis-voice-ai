import Foundation

/// Presentation observations only. An adapter must establish processed input or
/// actual playout provenance before supplying a level; decoded RTP is not playout.
/// No PCM, transcript, transport control, or credentials belong in this boundary.
public struct AudioActivitySnapshot: Equatable, Sendable {
    public let generation: UUID
    public let timestamp: TimeInterval
    public let userLevel: Double?
    public let outputLevel: Double?
    public let microphoneEligible: Bool
}

/// Serial-owner value state. Caller supplies one monotonic clock for measurement
/// and snapshot times. Freshness expires on reads, even if callbacks stop entirely.
public struct AudioActivityAccumulator {
    public enum Channel { case processedInput, actualPlayout }
    public static let staleAfter: TimeInterval = 0.300
    private struct Sample {
        let timestamp: TimeInterval
        let level: Double
    }
    public private(set) var generation: UUID
    private var input: Sample?
    private var output: Sample?
    private var inputWatermark: TimeInterval = -.infinity
    private var outputWatermark: TimeInterval = -.infinity
    private var microphoneEligible = false
    private var eligibilitySince: TimeInterval = .infinity

    public init(generation: UUID) { self.generation = generation }

    public mutating func reset(generation: UUID) {
        self = Self(generation: generation)
    }

    public mutating func setMicrophoneEligible(_ eligible: Bool, at now: TimeInterval) {
        guard now.isFinite else { microphoneEligible = false; input = nil; return }
        if eligible != microphoneEligible {
            input = nil
            eligibilitySince = eligible ? now : .infinity
        }
        microphoneEligible = eligible
    }

    /// Returns false for unavailable, malformed, old, future or duplicate data.
    /// Timestamps must describe measurement time, never callback arrival time.
    @discardableResult
    public mutating func observe(_ channel: Channel, level: Double,
                                 measuredAt: TimeInterval, now: TimeInterval,
                                 generation: UUID) -> Bool {
        guard generation == self.generation, level.isFinite, (0...1).contains(level),
              measuredAt.isFinite, now.isFinite, measuredAt <= now,
              now - measuredAt < Self.staleAfter else { return false }
        switch channel {
        case .processedInput:
            guard measuredAt > inputWatermark else { return false }
            inputWatermark = measuredAt
            guard microphoneEligible, measuredAt >= eligibilitySince else { return false }
            input = Sample(timestamp: measuredAt, level: level)
        case .actualPlayout:
            guard measuredAt > outputWatermark else { return false }
            outputWatermark = measuredAt
            output = Sample(timestamp: measuredAt, level: level)
        }
        return true
    }

    public func snapshot(at now: TimeInterval) -> AudioActivitySnapshot {
        func fresh(_ sample: Sample?) -> Double? {
            guard let sample, now.isFinite, now >= sample.timestamp,
                  now - sample.timestamp < Self.staleAfter else { return nil }
            return sample.level
        }
        return AudioActivitySnapshot(generation: generation, timestamp: now,
            userLevel: microphoneEligible ? fresh(input) : nil,
            outputLevel: fresh(output), microphoneEligible: microphoneEligible)
    }
}
