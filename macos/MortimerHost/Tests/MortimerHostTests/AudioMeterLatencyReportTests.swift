import XCTest
@testable import MortimerHost
@testable import JarvisKit

/// Closure C7.5: the report is the gate's evidence, so its verdict and its
/// no-data case are worth pinning down.
final class AudioMeterLatencyReportTests: XCTestCase {
    private func latency(p95: Double, samples: Int = 100) -> AudioMeterLatency {
        let channel = AudioMeterChannelLatency(samples: samples, displayedP50: p95 / 2,
                                               displayedP95: p95, worst: p95 * 1.2,
                                               arrivals: samples / 2, arrivalP50: p95 / 4,
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
        XCTAssertEqual(payload["gate_p95_seconds"] as? Double, 0.150)
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

    func testAP95OverTheGateFails() {
        let payload = AudioMeterLatencyReport.payload(latency(p95: 0.151), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "FAIL", "150 ms is the gate; 151 does not pass it")
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
