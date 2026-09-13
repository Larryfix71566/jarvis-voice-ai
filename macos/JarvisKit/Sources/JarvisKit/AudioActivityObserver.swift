import Foundation
import os

private let meterLog = Logger(subsystem: "com.mortimer.jarviskit", category: "audio-meter")

/// The latest-value level slots the observer samples (C6.2). Only the
/// native path measures real audio: `AudioEngineIO` fills these from its
/// own capture and main-mixer taps, so metering costs no second tap and
/// no second engine. `DirectWebRTCTransport` does not conform — on that
/// path the observer publishes nothing and the wave says the level is
/// unavailable rather than inventing one (closure C7 item 2).
public protocol AudioLevelSource: AnyObject {
    var latestInputLevel: AudioLevelSample? { get }
    var latestPlayoutLevel: AudioLevelSample? { get }
}

/// Round-trip of one observation: the audio buffer's own host time to the
/// moment the presentation was given the snapshot derived from it.
public struct AudioMeterLatency: Equatable, Sendable {
    public let samples: Int
    public let p50: Double
    public let p95: Double
    public let worst: Double
}

/// Closure C7.1: the connection generation and the sampling live here,
/// app-scoped, instead of in a view's `@State` (gap G24). Sampling is
/// capped at `AudioActivityObserver.sampleHz` (G25) and runs on its own
/// serial queue — never on the audio thread, which only writes the slots.
///
/// The accumulator (`AudioActivityAccumulator`) already owns the rules
/// that matter — duplicate timestamps, stale data, mute eligibility, the
/// 300 ms decay — and they are not re-implemented here.
public final class AudioActivityObserver: @unchecked Sendable {
    /// ≤30 Hz (G25). The wave's smoothing is elapsed-time based, so a
    /// faster sampler would buy nothing but wakeups.
    public static let sampleHz: Double = 30

    private let queue = DispatchQueue(label: "com.mortimer.jarviskit.audio-meter")
    private let lock = NSLock()
    private var accumulator: AudioActivityAccumulator
    private var timer: DispatchSourceTimer?
    private weak var source: AudioLevelSource?
    private var eligible = false
    private var latencies: [(measuredAt: TimeInterval, delay: Double)] = []
    private var _snapshot: AudioActivitySnapshot?
    private var _generation: UUID

    /// Called on the main actor with every new snapshot (≤30 Hz).
    private let publish: @Sendable (AudioActivitySnapshot) -> Void
    private let now: @Sendable () -> TimeInterval

    public init(publish: @escaping @Sendable (AudioActivitySnapshot) -> Void,
                now: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        let generation = UUID()
        self._generation = generation
        self.accumulator = AudioActivityAccumulator(generation: generation)
        self.publish = publish
        self.now = now
    }

    public var generation: UUID { lock.withLock { _generation } }
    public var snapshot: AudioActivitySnapshot? { lock.withLock { _snapshot } }

    /// A new session: a fresh generation invalidates everything the
    /// presentation still holds from the last one.
    public func beginSession(source: AudioLevelSource?, microphoneEnabled: Bool) {
        guard JarvisFlags.audioMeterEnabled else {
            meterLog.notice("audio meter disabled by JARVIS_AUDIO_METER — publishing nothing")
            endSession()
            return
        }
        lock.withLock {
            _generation = UUID()
            accumulator.reset(generation: _generation)
            accumulator.setMicrophoneEligible(microphoneEnabled && source != nil, at: now())
            eligible = microphoneEnabled && source != nil
            self.source = source
            latencies.removeAll()
        }
        meterLog.notice("""
            audio meter session \\(self.generation.uuidString, privacy: .public): \
            source \\(source == nil ? "none (levels unavailable)" : "measured", privacy: .public), \
            \\(Self.sampleHz, format: .fixed(precision: 0), privacy: .public) Hz
            """)
        startTimer()
    }

    public func endSession() {
        timer?.cancel(); timer = nil
        lock.withLock {
            source = nil
            eligible = false
            _generation = UUID()
            accumulator.reset(generation: _generation)
            _snapshot = nil
        }
    }

    /// Muting is an eligibility change, not a level of zero: the
    /// accumulator drops the pending input sample immediately.
    public func setMicrophoneEnabled(_ enabled: Bool) {
        lock.withLock {
            let hasSource = source != nil
            eligible = enabled && hasSource
            accumulator.setMicrophoneEligible(eligible, at: now())
        }
    }

    private func startTimer() {
        timer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        let interval = 1.0 / Self.sampleHz
        timer.schedule(deadline: .now() + interval, repeating: interval, leeway: .milliseconds(4))
        timer.setEventHandler { [weak self] in self?.sample() }
        self.timer = timer
        timer.resume()
    }

    /// One observation cycle. Internal rather than private so the tests
    /// can step it deterministically instead of waiting on a timer.
    func sample() {
        let moment = now()
        let snapshot: AudioActivitySnapshot? = lock.withLock {
            guard let source else { return nil }
            let generation = _generation
            if let input = source.latestInputLevel {
                accumulator.observe(.processedInput, level: input.rms,
                                    measuredAt: input.seconds, now: moment, generation: generation)
            }
            if let playout = source.latestPlayoutLevel {
                accumulator.observe(.actualPlayout, level: playout.rms,
                                    measuredAt: playout.seconds, now: moment, generation: generation)
            }
            let snapshot = accumulator.snapshot(at: moment)
            // C7.5: the delay a viewer actually sees is from the buffer's
            // own host time to the snapshot the presentation is handed.
            for measuredAt in [snapshot.userMeasuredAt, snapshot.outputMeasuredAt].compactMap({ $0 }) {
                latencies.append((measuredAt, moment - measuredAt))
            }
            let cutoff = moment - 60
            latencies.removeAll { $0.measuredAt < cutoff }
            _snapshot = snapshot
            return snapshot
        }
        guard let snapshot else { return }
        publish(snapshot)
    }

    /// p50/p95 over the last 60 s (C7.5 gate: p95 ≤ 150 ms).
    public func latency() -> AudioMeterLatency {
        let delays = lock.withLock { latencies.map(\.delay) }.sorted()
        guard !delays.isEmpty else { return AudioMeterLatency(samples: 0, p50: 0, p95: 0, worst: 0) }
        func percentile(_ p: Double) -> Double {
            let index = min(delays.count - 1, max(0, Int((p * Double(delays.count - 1)).rounded())))
            return delays[index]
        }
        return AudioMeterLatency(samples: delays.count, p50: percentile(0.5),
                                 p95: percentile(0.95), worst: delays[delays.count - 1])
    }
}
