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
public struct AudioMeterChannelLatency: Equatable, Sendable {
    public let samples: Int
    public let displayedP50: Double
    public let displayedP95: Double
    public let worst: Double
    public let arrivals: Int
    public let arrivalP50: Double
    public let arrivalP95: Double
    /// Item 10 (2026-09-16): the MAGNITUDE behind the timings above, linear
    /// RMS 0…1 full scale, one entry per distinct level. VoiceWaveView maps
    /// this through `level * 0.115`, a multiplier inherited from a simulated
    /// envelope that floored at 0.25 and peaked at 1.0; real speech RMS is
    /// far below that, which is why the adaptive trace lost its amplitude.
    /// Nothing else on disk records it.
    public let levelP50: Double
    public let levelP95: Double
    public let levelMax: Double

    public static let empty = AudioMeterChannelLatency(samples: 0, displayedP50: 0, displayedP95: 0,
                                                       worst: 0, arrivals: 0, arrivalP50: 0, arrivalP95: 0)

    public init(samples: Int, displayedP50: Double, displayedP95: Double, worst: Double,
                arrivals: Int, arrivalP50: Double, arrivalP95: Double,
                levelP50: Double = 0, levelP95: Double = 0, levelMax: Double = 0) {
        self.samples = samples
        self.displayedP50 = displayedP50
        self.displayedP95 = displayedP95
        self.worst = worst
        self.arrivals = arrivals
        self.arrivalP50 = arrivalP50
        self.arrivalP95 = arrivalP95
        self.levelP50 = levelP50
        self.levelP95 = levelP95
        self.levelMax = levelMax
    }
}

public struct AudioMeterLatency: Equatable, Sendable {
    public let input: AudioMeterChannelLatency
    public let playout: AudioMeterChannelLatency

    public init(input: AudioMeterChannelLatency, playout: AudioMeterChannelLatency) {
        self.input = input
        self.playout = playout
    }

    /// Whole-meter figures take the worse channel: the gate is about what
    /// a viewer sees, and they see both.
    public var samples: Int { input.samples + playout.samples }
    public var p50: Double { max(input.displayedP50, playout.displayedP50) }
    public var p95: Double { max(input.displayedP95, playout.displayedP95) }
    public var worst: Double { max(input.worst, playout.worst) }
    /// What C7.5 is actually about: the cost from the audio arriving to the
    /// accumulator holding it. `displayed` above counts a HELD level's
    /// staleness on every tick, so on the intermittent playout channel it
    /// measures how recently the bot spoke -- three sessions of identical
    /// code gave 34.3, 65.5 and 167.6 ms while these figures stayed at
    /// 1.0-1.7 ms. The gate reads these.
    public var arrivalP50: Double { max(input.arrivalP50, playout.arrivalP50) }
    public var arrivalP95: Double { max(input.arrivalP95, playout.arrivalP95) }
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
    /// Two readings (C7.5). `displayed` counts the level the snapshot
    /// carries on every tick — what the viewer sees, ageing while it waits
    /// for the next buffer. `arrivals` counts each level once, the first
    /// time the sampler sees it — the audio path's own delay, which a
    /// faster sampler cannot reduce. The first reading was 132 ms p50 and
    /// could not distinguish the two.
    private var displayed: [(channel: Int, measuredAt: TimeInterval, delay: Double)] = []
    private var arrivals: [(channel: Int, measuredAt: TimeInterval, delay: Double, level: Double)] = []
    private var lastSeen: [TimeInterval?] = [nil, nil]      // 0 input, 1 playout
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
            displayed.removeAll(); arrivals.removeAll(); lastSeen = [nil, nil]
        }
        meterLog.notice("""
            audio meter session \(self.generation.uuidString, privacy: .public): \
            source \(source == nil ? "none (levels unavailable)" : "measured", privacy: .public), \
            \(Self.sampleHz, format: .fixed(precision: 0), privacy: .public) Hz
            """)
        startTimer()
    }

    public func endSession() {
        let summary = latency()
        if summary.samples > 0 {
            meterLog.notice("""
                audio meter session ended — input: \(summary.input.samples, privacy: .public) shown, displayed p95 \(summary.input.displayedP95 * 1000, format: .fixed(precision: 1), privacy: .public) ms, arrival p95 \(summary.input.arrivalP95 * 1000, format: .fixed(precision: 1), privacy: .public) ms over \(summary.input.arrivals, privacy: .public) arrivals; playout: \(summary.playout.samples, privacy: .public) shown, displayed p95 \(summary.playout.displayedP95 * 1000, format: .fixed(precision: 1), privacy: .public) ms, arrival p95 \(summary.playout.arrivalP95 * 1000, format: .fixed(precision: 1), privacy: .public) ms over \(summary.playout.arrivals, privacy: .public) arrivals (C7.5 gate: ARRIVAL p95 under 50 ms; displayed counts a held level's staleness and is informational)
                """)
        }
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
            let levels = [snapshot.userLevel, snapshot.outputLevel]
            for (channel, measuredAt) in [snapshot.userMeasuredAt, snapshot.outputMeasuredAt].enumerated() {
                guard let measuredAt else { continue }
                let delay = moment - measuredAt
                displayed.append((channel, measuredAt, delay))
                if lastSeen[channel] != measuredAt {
                    lastSeen[channel] = measuredAt
                    // A nil level with a non-nil measuredAt means the snapshot
                    // withheld it (muted, or ineligible), so 0 is the honest
                    // magnitude for that arrival rather than a skipped entry.
                    arrivals.append((channel, measuredAt, delay, levels[channel] ?? 0))
                }
            }
            let cutoff = moment - 60
            displayed.removeAll { $0.measuredAt < cutoff }
            arrivals.removeAll { $0.measuredAt < cutoff }
            _snapshot = snapshot
            return snapshot
        }
        guard let snapshot else { return }
        publish(snapshot)
    }

    /// Per channel, over the last 60 s (C7.5 gate: arrival p95 ≤ 50 ms).
    public func latency() -> AudioMeterLatency {
        let (shown, arrived) = lock.withLock { (displayed, arrivals) }
        func percentile(_ sorted: [Double], _ p: Double) -> Double {
            guard !sorted.isEmpty else { return 0 }
            return sorted[min(sorted.count - 1, max(0, Int((p * Double(sorted.count - 1)).rounded())))]
        }
        func channel(_ index: Int) -> AudioMeterChannelLatency {
            let d = shown.filter { $0.channel == index }.map(\.delay).sorted()
            let a = arrived.filter { $0.channel == index }.map(\.delay).sorted()
            let levels = arrived.filter { $0.channel == index }.map(\.level).sorted()
            guard !d.isEmpty else { return .empty }
            return AudioMeterChannelLatency(
                samples: d.count, displayedP50: percentile(d, 0.5), displayedP95: percentile(d, 0.95),
                worst: d[d.count - 1], arrivals: a.count,
                arrivalP50: percentile(a, 0.5), arrivalP95: percentile(a, 0.95),
                levelP50: percentile(levels, 0.5), levelP95: percentile(levels, 0.95),
                levelMax: levels.last ?? 0)
        }
        return AudioMeterLatency(input: channel(0), playout: channel(1))
    }
}
