import XCTest
@testable import MortimerHost
@testable import JarvisKit

/// Closure C7.5: the report is the gate's evidence, so its verdict and its
/// no-data case are worth pinning down.
final class AudioMeterLatencyReportTests: XCTestCase {
    private func latency(p95: Double, samples: Int = 100) -> AudioMeterLatency {
        let channel = AudioMeterChannelLatency(samples: samples, displayedP50: p95 / 2,
                                               displayedP95: p95, worst: p95 * 1.2,
                                               arrivals: samples, arrivalP50: p95 / 4,
                                               arrivalP95: p95 / 3)
        return AudioMeterLatency(input: channel, playout: channel)
    }

    func testAPassingSessionRecordsTheNumbersAndTheVerdict() throws {
        let payload = AudioMeterLatencyReport.payload(latency(p95: 0.080), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "pass")
        XCTAssertEqual(payload["p95_ms"] as? Double, 80.0)
        XCTAssertEqual(payload["p50_ms"] as? Double, 40.0)
        XCTAssertEqual(payload["worst_ms"] as? Double, 96.0)
        XCTAssertEqual(payload["observations"] as? Int, 200, "both channels")
        let input = try XCTUnwrap(payload["input"] as? [String: Any])
        XCTAssertEqual(input["displayed_p95_ms"] as? Double, 80.0)
        XCTAssertEqual(input["arrival_p95_ms"] as? Double, 26.7, "the audio path's own share")
        XCTAssertEqual(payload["connected"] as? Bool, true)
        XCTAssertEqual(payload["native_audio"] as? Bool, true)
        XCTAssertEqual(payload["gate_p95_seconds"] as? Double, 0.050)
        XCTAssertEqual(payload["gate_metric"] as? String, "arrival_p95",
                       "the verdict must name the figure it used")
        XCTAssertEqual(payload["arrival_p95_ms"] as? Double, 26.7)
    }

    /// The bug this caught: input passed at 25 ms while playout recorded
    /// nothing at all, and the report called the session a pass.
    func testAChannelWithNoObservationsCannotPass() {
        let good = AudioMeterChannelLatency(samples: 100, displayedP50: 0.020, displayedP95: 0.025,
                                            worst: 0.030, arrivals: 100, arrivalP50: 0.020, arrivalP95: 0.025)
        let payload = AudioMeterLatencyReport.payload(
            AudioMeterLatency(input: good, playout: .empty), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "incomplete — one channel produced no observations")
    }

    func testHeldSnapshotsCannotTurnAShortSampleIntoAPass() {
        let sparse = AudioMeterChannelLatency(samples: 1800, displayedP50: 0.01,
            displayedP95: 0.02, worst: 0.03, arrivals: 99,
            arrivalP50: 0.01, arrivalP95: 0.02)
        let sufficient = AudioMeterChannelLatency(samples: 1800, displayedP50: 0.01,
            displayedP95: 0.02, worst: 0.03, arrivals: 100,
            arrivalP50: 0.01, arrivalP95: 0.02)
        for channels in [(sparse, sufficient), (sufficient, sparse)] {
            let payload = AudioMeterLatencyReport.payload(
                AudioMeterLatency(input: channels.0, playout: channels.1), connected: true, native: true)
            XCTAssertEqual(payload["gate"] as? String,
                "incomplete — fewer than 100 distinct arrivals on one or both channels")
        }
        let enough = AudioMeterLatencyReport.payload(
            AudioMeterLatency(input: sufficient, playout: sufficient), connected: true, native: true)
        XCTAssertEqual(enough["gate"] as? String, "pass")
    }

    func testCoverageDescribesActivityAcrossTheSixtySecondWindow() throws {
        let payload = AudioMeterLatencyReport.payload(latency(p95: 0.08, samples: 900), connected: false, native: true)
        let input = try XCTUnwrap(payload["input"] as? [String: Any])
        XCTAssertEqual(input["activity_coverage_fraction"] as? Double, 0.5)
        XCTAssertEqual(input["level_present_seconds"] as? Double, 30)
        XCTAssertEqual(payload["minimum_arrivals_per_channel"] as? Int, 100)
        XCTAssertEqual(payload["connected"] as? Bool, false,
            "ending a session does not erase its preceding observations")
    }

    func testAnArrivalP95OverTheGateFails() {
        let slow = AudioMeterChannelLatency(samples: 100, displayedP50: 0.030, displayedP95: 0.040,
                                            worst: 0.050, arrivals: 100,
                                            arrivalP50: 0.040, arrivalP95: 0.051)
        let payload = AudioMeterLatencyReport.payload(
            AudioMeterLatency(input: slow, playout: slow), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "FAIL", "50 ms is the gate; 51 does not pass it")
    }

    /// The measurement that changed the gate (2026-09-15). Displayed p95 of
    /// 167.6 ms with arrival at 1.0 ms was recorded as a FAIL, and it was
    /// not a latency failure at all: `displayed` counts a held level's
    /// staleness every tick, so on the playout channel it measured how
    /// recently the bot had spoken. The same session's arrival figures are
    /// what the gate reads now.
    func testAQuietBotDoesNotFailTheGate() throws {
        let quiet = AudioMeterChannelLatency(samples: 275, displayedP50: 0.0009, displayedP95: 0.1676,
                                             worst: 0.2711, arrivals: 243,
                                             arrivalP50: 0.0009, arrivalP95: 0.001)
        let busy = AudioMeterChannelLatency(samples: 840, displayedP50: 0.0352, displayedP95: 0.0419,
                                            worst: 0.042, arrivals: 840,
                                            arrivalP50: 0.0352, arrivalP95: 0.0419)
        let payload = AudioMeterLatencyReport.payload(
            AudioMeterLatency(input: busy, playout: quiet), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "pass",
                       "a quiet playout channel is not a slow one")
        XCTAssertEqual(payload["arrival_p95_ms"] as? Double, 41.9, "the worse channel's arrival")
        XCTAssertEqual(payload["p95_ms"] as? Double, 167.6,
                       "displayed is still reported, it just no longer decides")
    }

    /// A meter that never observed anything must not read as a perfect score.
    func testNoObservationsIsRecordedAsNoDataRatherThanZero() {
        let payload = AudioMeterLatencyReport.payload(
            AudioMeterLatency(input: .empty, playout: .empty), connected: false, native: false)
        XCTAssertEqual(payload["gate"] as? String, "no data")
        XCTAssertNil(payload["p95_ms"], "no measurement, no number")
        XCTAssertEqual(payload["observations"] as? Int, 0)
        XCTAssertEqual(payload["connected"] as? Bool, false)
    }

    func testTheReportLandsInTheAcceptanceDirectoryWhenRunFromTheWorkingCopy() {
        let url = AudioMeterLatencyReport.destination()
        XCTAssertEqual(url.lastPathComponent, "P2-latency.json")
        XCTAssertTrue(url.path.contains("docs/acceptance/adaptive-interface")
                      || url.path.contains("Documents"),
                      "either the acceptance directory or the documented fallback: \(url.path)")
    }
}
