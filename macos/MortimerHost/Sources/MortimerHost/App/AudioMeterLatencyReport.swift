import Foundation
import JarvisKit
import os

private let reportLog = Logger(subsystem: "com.mortimer.host", category: "audio-meter")

/// Closure C7.5. Writes the observer's p50/p95 to the file the acceptance
/// record names, next to the other measured artefacts
/// (`P4-frame-time.json`, `P2-desktop-verification.json`).
///
/// The gate is ARRIVAL p95 ≤ 50 ms for both channels on the deployment
/// Mac, so the verdict is computed here rather than left to whoever reads
/// the file, and the context that makes the number meaningful — whether a
/// session was live and whether it was the native path — travels with it.
/// A report with no observations is written as `"gate": "no data"`: a
/// meter that never ran is not a meter that measured zero.
///
/// It gated on DISPLAYED p95 ≤ 150 ms until 2026-09-15, which was the wrong
/// number: `displayed` counts a held level's staleness on every 30 Hz tick,
/// so on the intermittent playout channel it measured how recently the bot
/// had spoken. Three sessions of identical code returned 34.3, 65.5 and
/// 167.6 ms — one of them a FAIL — while arrival never left 1.0-1.7 ms.
/// The 50 ms threshold comes from the measurements: healthy input arrival
/// p95 of 23.5, 24.5, 25.2 and 41.9 ms (the last on the 24 kHz Bluetooth
/// path), against ~110 ms for the D10 regression this gate exists to catch.
enum AudioMeterLatencyReport {
    static let gateSeconds: Double = 0.050

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
            // Named so a reader knows which figure the verdict used, and
            // does not reach for `p95_ms` (displayed) beside it.
            "gate_metric": "arrival_p95",
        ]
        guard latency.samples > 0 else {
            payload["gate"] = "no data"
            return payload
        }
        func channel(_ c: AudioMeterChannelLatency) -> [String: Any] {
            [
                "observations": c.samples,
                "displayed_p50_ms": (c.displayedP50 * 1000).rounded(toPlaces: 1),
                "displayed_p95_ms": (c.displayedP95 * 1000).rounded(toPlaces: 1),
                "worst_ms": (c.worst * 1000).rounded(toPlaces: 1),
                // How old each level was the first time the sampler saw it:
                // the audio path's own cost, which no sampler change fixes.
                "arrivals": c.arrivals,
                "arrival_p50_ms": (c.arrivalP50 * 1000).rounded(toPlaces: 1),
                "arrival_p95_ms": (c.arrivalP95 * 1000).rounded(toPlaces: 1),
                // Item 10: the magnitudes behind those timings. Linear RMS,
                // 0…1 full scale — the number VoiceWaveView multiplies by
                // 0.115. Four decimal places because speech RMS lives in
                // the third and fourth.
                "level_p50": c.levelP50.rounded(toPlaces: 4),
                "level_p95": c.levelP95.rounded(toPlaces: 4),
                "level_max": c.levelMax.rounded(toPlaces: 4),
            ]
        }
        payload["input"] = channel(latency.input)
        payload["playout"] = channel(latency.playout)
        payload["p50_ms"] = (latency.p50 * 1000).rounded(toPlaces: 1)
        payload["p95_ms"] = (latency.p95 * 1000).rounded(toPlaces: 1)
        payload["arrival_p95_ms"] = (latency.arrivalP95 * 1000).rounded(toPlaces: 1)
        payload["worst_ms"] = (latency.worst * 1000).rounded(toPlaces: 1)
        // A silent channel is not a fast one. C7.5 is a statement about
        // both, so a session where one produced nothing cannot pass on the
        // strength of the other.
        if latency.input.samples == 0 || latency.playout.samples == 0 {
            payload["gate"] = "incomplete — one channel produced no observations"
        } else {
            payload["gate"] = latency.arrivalP95 <= gateSeconds ? "pass" : "FAIL"
        }
        return payload
    }

    @discardableResult
    static func write(_ latency: AudioMeterLatency, connected: Bool, native: Bool) -> URL? {
        let url = destination()
        // A session with no meter at all must not erase one that measured.
        // Observed 2026-09-15: the section 9 rollback session runs on
        // DirectWebRTCTransport, which is not an AudioLevelSource, so the
        // observer had no source and wrote {"gate": "no data"} over the
        // arrival-gate figures from the session before it. "No data" is the
        // right PAYLOAD for such a session (a meter that never ran is not a
        // meter that measured zero) and the wrong thing to overwrite
        // evidence with.
        guard latency.samples > 0 else {
            reportLog.notice("not writing \(url.lastPathComponent, privacy: .public): no observations this session, keeping the existing report")
            return nil
        }
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
