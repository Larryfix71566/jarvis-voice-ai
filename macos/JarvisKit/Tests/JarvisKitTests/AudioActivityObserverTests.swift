import AVFoundation
import XCTest
@testable import JarvisKit

/// Closure C7.1/C7.2/C7.4/C7.5. The accumulator's rules (watermarks,
/// staleness, the 300 ms decay) are AudioActivityTests' job; these cover
/// what the observer adds: the source, eligibility, the generation, and
/// the latency readout. `sample()` is stepped directly rather than waiting
/// on the 30 Hz timer, and levels are built through the engine's own
/// host-time conversion so the times are the ones production produces.
final class AudioActivityObserverTests: XCTestCase {
    final class StubSource: AudioLevelSource, @unchecked Sendable {
        private let lock = NSLock()
        private var _input: AudioLevelSample?
        private var _playout: AudioLevelSample?
        var latestInputLevel: AudioLevelSample? { lock.withLock { _input } }
        var latestPlayoutLevel: AudioLevelSample? { lock.withLock { _playout } }
        func set(input: AudioLevelSample?, playout: AudioLevelSample?) {
            lock.withLock { _input = input; _playout = playout }
        }
    }

    final class SnapshotBox: @unchecked Sendable {
        private let lock = NSLock()
        private var _all: [AudioActivitySnapshot] = []
        var all: [AudioActivitySnapshot] { lock.withLock { _all } }
        var last: AudioActivitySnapshot? { lock.withLock { _all.last } }
        func append(_ snapshot: AudioActivitySnapshot) { lock.withLock { _all.append(snapshot) } }
    }

    /// A level whose measurement time is `ago` seconds in the past, on the
    /// same monotonic clock the observer reads.
    private func level(_ rms: Double, ago: TimeInterval) -> AudioLevelSample {
        AudioLevelSample(rms: rms, hostTime: AVAudioTime.hostTime(forSeconds: ProcessInfo.processInfo.systemUptime - ago))
    }

    private func observer(_ box: SnapshotBox) -> AudioActivityObserver {
        AudioActivityObserver(publish: { box.append($0) })
    }

    /// Begins a session and lets eligibility age. The accumulator only
    /// accepts input measured at or after the moment the microphone became
    /// eligible (that is what keeps a buffer captured while muted from
    /// appearing the instant you unmute), so a test that backdates its
    /// samples must start the session further in the past than it
    /// backdates them.
    private func begin(_ observer: AudioActivityObserver, source: AudioLevelSource?,
                       microphoneEnabled: Bool = true, settle: TimeInterval = 0.15) {
        observer.beginSession(source: source, microphoneEnabled: microphoneEnabled)
        Thread.sleep(forTimeInterval: settle)
    }

    func testSamplingIsCappedAtThirtyHertz() {
        XCTAssertEqual(AudioActivityObserver.sampleHz, 30, "gap G25")
    }

    func testMeasuredLevelsReachThePresentationWhileTheMicrophoneIsEligible() throws {
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        begin(observer, source: source)
        source.set(input: level(0.4, ago: 0.01), playout: level(0.6, ago: 0.01))
        observer.sample()
        let snapshot = try XCTUnwrap(box.last)
        XCTAssertEqual(snapshot.userLevel, 0.4)
        XCTAssertEqual(snapshot.outputLevel, 0.6)
        XCTAssertEqual(snapshot.generation, observer.generation)
        XCTAssertTrue(snapshot.microphoneEligible)
    }

    func testMutingDropsTheInputChannelButNotPlayout() throws {
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        begin(observer, source: source)
        source.set(input: level(0.4, ago: 0.02), playout: level(0.6, ago: 0.02))
        observer.sample()
        XCTAssertEqual(box.last?.userLevel, 0.4)
        observer.setMicrophoneEnabled(false)
        source.set(input: level(0.4, ago: 0.01), playout: level(0.6, ago: 0.01))
        observer.sample()
        let muted = try XCTUnwrap(box.last)
        XCTAssertNil(muted.userLevel, "muted input is no level at all, not a level of zero")
        XCTAssertEqual(muted.outputLevel, 0.6, "the bot's own audio is still measured while muted")
        XCTAssertFalse(muted.microphoneEligible)
    }

    func testWithoutAMeasuredSourceNothingIsPublished() {
        let box = SnapshotBox(); let observer = observer(box)
        begin(observer, source: nil, settle: 0.02)   // the WebRTC path
        observer.sample()
        XCTAssertTrue(box.all.isEmpty, "the wave reports unavailable rather than inventing a level")
        XCTAssertNil(observer.snapshot)
    }

    func testANewSessionIsANewGeneration() throws {
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        begin(observer, source: source)
        let first = observer.generation
        source.set(input: level(0.4, ago: 0.02), playout: nil)
        observer.sample()
        begin(observer, source: source)
        XCTAssertNotEqual(observer.generation, first)
        source.set(input: level(0.2, ago: 0.01), playout: nil)
        observer.sample()
        let snapshot = try XCTUnwrap(box.last)
        XCTAssertEqual(snapshot.generation, observer.generation)
        XCTAssertEqual(snapshot.userLevel, 0.2)
    }

    func testEndSessionStopsPublishingAndClearsTheSnapshot() {
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        begin(observer, source: source)
        source.set(input: level(0.4, ago: 0.01), playout: nil)
        observer.sample()
        XCTAssertNotNil(observer.snapshot)
        let count = box.all.count
        observer.endSession()
        XCTAssertNil(observer.snapshot)
        observer.sample()
        XCTAssertEqual(box.all.count, count, "a stopped observer samples nothing")
    }

    /// C7.5: the numbers the ≤150 ms p95 gate is read from.
    func testLatencyReportsPercentilesOfBufferToPresentationDelay() {
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        begin(observer, source: source)
        XCTAssertEqual(observer.latency().samples, 0)
        // Oldest first: each sample must be measured LATER than the last
        // or the accumulator's watermark refuses it, so the delays are fed
        // in decreasing order of age.
        for delay in [0.100, 0.040, 0.030, 0.020, 0.010] {
            source.set(input: level(0.3, ago: delay), playout: nil)
            observer.sample()
        }
        let latency = observer.latency()
        XCTAssertEqual(latency.samples, 5)
        XCTAssertEqual(latency.p50, 0.030, accuracy: 0.010)
        XCTAssertEqual(latency.p95, 0.100, accuracy: 0.010)
        XCTAssertEqual(latency.worst, 0.100, accuracy: 0.010)
        XCTAssertLessThanOrEqual(latency.p95, 0.150, "the gate this readout exists to answer")
    }

    /// Audio captured before the microphone became eligible must never
    /// surface — otherwise unmuting would flash whatever was in the tap
    /// while the user was muted.
    func testInputMeasuredBeforeEligibilityBeganIsRefused() throws {
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        observer.beginSession(source: source, microphoneEnabled: true)
        source.set(input: level(0.4, ago: 0.05), playout: level(0.6, ago: 0.05))
        observer.sample()
        let snapshot = try XCTUnwrap(box.last)
        XCTAssertNil(snapshot.userLevel, "measured 50 ms before this session's microphone became eligible")
        XCTAssertEqual(snapshot.outputLevel, 0.6, "playout has no eligibility gate")
    }

    func testTheMeterCanBeDisabledAtRuntime() {
        UserDefaults.standard.set(false, forKey: "JARVIS_AUDIO_METER")
        defer { UserDefaults.standard.removeObject(forKey: "JARVIS_AUDIO_METER") }
        XCTAssertFalse(JarvisFlags.audioMeterEnabled)
        let box = SnapshotBox(); let observer = observer(box); let source = StubSource()
        begin(observer, source: source, settle: 0.02)
        source.set(input: level(0.4, ago: 0.01), playout: level(0.6, ago: 0.01))
        observer.sample()
        XCTAssertTrue(box.all.isEmpty, "JARVIS_AUDIO_METER off publishes nothing")
    }
}
