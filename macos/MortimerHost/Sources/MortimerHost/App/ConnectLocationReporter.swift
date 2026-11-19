// ConnectLocationReporter.swift
// 2026-11-19 (WS-15 follow-up): the weather chip read "Mulberry" because the
// sidecar only had an IP guess. The Mac posted a CoreLocation fix to
// POST /api/location only when the bot asked for one (a local_weather or
// "where am I" turn), so a session that never asked showed weather.gov's
// nearest place for the IP's coordinates.
//
// Now, on every connect, the app asks CoreLocation for one fix and posts it
// to the sidecar, then refreshes it on a timer that is shorter than the
// sidecar's one-hour keep (ambient_weather.DEVICE_LOCATION_MAX_AGE_S), so
// the chip names the device's own city for as long as the app is connected.
// The bot's per-request location/request path (D-L6) is unchanged; this
// only feeds the sidecar. When Location Services is denied or not yet
// answered, nothing is posted and the sidecar keeps its IP fallback.

import Foundation
import JarvisKit

@MainActor
final class ConnectLocationReporter {
    /// Half the sidecar's one-hour keep for a device fix, so a connected
    /// app's fix never ages out between refreshes.
    static let refreshInterval: TimeInterval = 30 * 60

    /// One fix, or nil when Location Services hasn't allowed one.
    typealias Fix = @MainActor () async -> LocationResult?
    typealias Report = @MainActor (_ lat: Double, _ lon: Double, _ label: String) async -> Void
    typealias Sleep = (TimeInterval) async throws -> Void

    private let fix: Fix
    private let report: Report
    private let sleep: Sleep
    private var loop: Task<Void, Never>?

    init(fix: @escaping Fix,
         report: @escaping Report,
         sleep: @escaping Sleep = { try await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000)) }) {
        self.fix = fix
        self.report = report
        self.sleep = sleep
    }

    var isRunning: Bool { loop != nil }

    /// The running refresh loop, for tests to await.
    var loopTask: Task<Void, Never>? { loop }

    /// Start (or restart, on a reconnect) the loop: one fix now, then one
    /// every `refreshInterval` until `stop()`.
    func start() {
        stop()
        let sleep = self.sleep
        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refreshOnce()
                do { try await sleep(Self.refreshInterval) } catch { return }
            }
        }
    }

    func stop() {
        loop?.cancel()
        loop = nil
    }

    /// An extra fix outside the timer (Location Services was just allowed).
    /// Ignored while stopped, so nothing is posted before a connect.
    @discardableResult
    func refreshNow() -> Task<Void, Never>? {
        guard isRunning else { return nil }
        return Task { [weak self] in await self?.refreshOnce() }
    }

    func refreshOnce() async {
        guard let result = await fix(), result.ok,
              let lat = result.lat, let lon = result.lon else { return }
        await report(lat, lon, result.label ?? "")
    }
}
