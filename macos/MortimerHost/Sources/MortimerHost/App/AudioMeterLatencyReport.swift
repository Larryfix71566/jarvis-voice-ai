import Foundation
import JarvisKit
import os

private let reportLog = Logger(subsystem: "com.mortimer.host", category: "audio-meter")

/// Closure C7.5. Writes the observer's p50/p95 to the file the acceptance
/// record names, next to the other measured artefacts
/// (`P4-frame-time.json`, `P2-desktop-verification.json`).
///
/// The gate is p95 ≤ 150 ms for both channels on the deployment Mac, so
/// the verdict is computed here rather than left to whoever reads the
/// file, and the context that makes the number meaningful — whether a
/// session was live and whether it was the native path — travels with it.
/// A report with no observations is written as `"gate": "no data"`: a
/// meter that never ran is not a meter that measured zero.
enum AudioMeterLatencyReport {
    static let gateSeconds: Double = 0.150

    /// Repo-relative so a debug build run from the working copy lands the
    /// file in the acceptance directory; falls back to the user's
    /// Documents when the app is running from somewhere else entirely.
    static func destination() -> URL {
        let repo = URL(fileURLWithPath: #filePath)          // …/macos/MortimerHost/Sources/MortimerHost/App/…
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let acceptance = repo.appendingPathComponent("docs/acceptance/adaptive-interface", isDirectory: true)
        if FileManager.default.fileExists(atPath: acceptance.path) {
            return acceptance.appendingPathComponent("P2-latency.json")
        }
        return FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("P2-latency.json")
    }

    static func payload(_ latency: AudioMeterLatency, connected: Bool, native: Bool,
                        date: Date = Date()) -> [String: Any] {
        let formatter = ISO8601DateFormatter()
        var payload: [String: Any] = [
            "measured_at": formatter.string(from: date),
            "window_seconds": 60,
            "sample_hz": AudioActivityObserver.sampleHz,
            "observations": latency.samples,
            "connected": connected,
            "native_audio": native,
            "gate_p95_seconds": gateSeconds,
        ]
        guard latency.samples > 0 else {
            payload["gate"] = "no data"
            return payload
        }
        payload["p50_ms"] = (latency.p50 * 1000).rounded(toPlaces: 1)
        payload["p95_ms"] = (latency.p95 * 1000).rounded(toPlaces: 1)
        payload["worst_ms"] = (latency.worst * 1000).rounded(toPlaces: 1)
        payload["gate"] = latency.p95 <= gateSeconds ? "pass" : "FAIL"
        return payload
    }

    @discardableResult
    static func write(_ latency: AudioMeterLatency, connected: Bool, native: Bool) -> URL? {
        let url = destination()
        do {
            let data = try JSONSerialization.data(withJSONObject: payload(latency, connected: connected, native: native),
                                                  options: [.prettyPrinted, .sortedKeys])
            try data.write(to: url, options: .atomic)
            reportLog.notice("""
                wrote \(url.lastPathComponent, privacy: .public): \
                \(latency.samples, privacy: .public) observations, \
                p95 \(latency.p95 * 1000, format: .fixed(precision: 1), privacy: .public) ms
                """)
            return url
        } catch {
            reportLog.error("could not write the latency report: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }
}

private extension Double {
    func rounded(toPlaces places: Int) -> Double {
        let factor = pow(10.0, Double(places))
        return (self * factor).rounded() / factor
    }
}
