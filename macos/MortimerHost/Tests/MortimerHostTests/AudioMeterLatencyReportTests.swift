import XCTest
@testable import MortimerHost
@testable import JarvisKit

/// Closure C7.5: the report is the gate's evidence, so its verdict and its
/// no-data case are worth pinning down.
final class AudioMeterLatencyReportTests: XCTestCase {
    private func latency(p95: Double, samples: Int = 100) -> AudioMeterLatency {
        AudioMeterLatency(samples: samples, p50: p95 / 2, p95: p95, worst: p95 * 1.2)
    }

    func testAPassingSessionRecordsTheNumbersAndTheVerdict() throws {
        let payload = AudioMeterLatencyReport.payload(latency(p95: 0.080), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "pass")
        XCTAssertEqual(payload["p95_ms"] as? Double, 80.0)
        XCTAssertEqual(payload["p50_ms"] as? Double, 40.0)
        XCTAssertEqual(payload["worst_ms"] as? Double, 96.0)
        XCTAssertEqual(payload["observations"] as? Int, 100)
        XCTAssertEqual(payload["connected"] as? Bool, true)
        XCTAssertEqual(payload["native_audio"] as? Bool, true)
        XCTAssertEqual(payload["gate_p95_seconds"] as? Double, 0.150)
    }

    func testAP95OverTheGateFails() {
        let payload = AudioMeterLatencyReport.payload(latency(p95: 0.151), connected: true, native: true)
        XCTAssertEqual(payload["gate"] as? String, "FAIL", "150 ms is the gate; 151 does not pass it")
    }

    /// A meter that never observed anything must not read as a perfect score.
    func testNoObservationsIsRecordedAsNoDataRatherThanZero() {
        let payload = AudioMeterLatencyReport.payload(
            AudioMeterLatency(samples: 0, p50: 0, p95: 0, worst: 0), connected: false, native: false)
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
