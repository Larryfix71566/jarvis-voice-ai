// DeviceLocator.swift
// MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 2 D4 (Larry's decision D-L6,
// 2026-09-25): "where am I" is answered by the device Larry is talking
// through, asked on demand, before any IP lookup (jarvis/bot/device_location.py).
//
// Adapted from the legacy MortimerShell's ShellLocation.swift, with three
// changes: ~100 m accuracy instead of 1 km (that class was sized for the
// weather chip), a one-shot requestLocation() per bot request instead of
// continuous updates, and the answer goes back on the session's own data
// channel, so the fix always comes from the client in this conversation.
// Macs have no GPS receiver; CoreLocation resolves position from nearby
// Wi-Fi networks. The fix also goes to the sidecar's POST /api/location so
// the weather chip uses it (no coordinates are logged).

import CoreLocation
import Foundation
import JarvisKit
import os

private let locationLogger = Logger(subsystem: "com.mortimer.host", category: "location")

/// Pure mappings, unit-tested in DeviceLocatorTests.
enum DeviceLocationReply {
    static func authorization(_ status: CLAuthorizationStatus) -> LocationAuthorization {
        switch status {
        case .authorizedAlways, .authorized: return .authorized
        case .notDetermined: return .notDetermined
        case .denied: return .denied
        case .restricted: return .restricted
        @unknown default: return .unknown
        }
    }

    static func failure(for error: Error) -> LocationFailure {
        if let clError = error as? CLError, clError.code == .denied { return .denied }
        return .unavailable
    }

    static func result(requestID: String, location: CLLocation, label: String?,
                       now: Date = Date()) -> LocationResult {
        .fix(requestID: requestID,
             lat: location.coordinate.latitude,
             lon: location.coordinate.longitude,
             accuracyM: location.horizontalAccuracy,
             ageS: now.timeIntervalSince(location.timestamp),
             label: label)
    }

    /// "Alpharetta, GA" — locality and state, whichever are known.
    static func label(locality: String?, administrativeArea: String?) -> String? {
        let parts = [locality, administrativeArea]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }
}

@MainActor
final class DeviceLocator: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private let geocoder = CLGeocoder()
    private var waiting: [(id: String, reply: (LocationResult) -> Void)] = []
    private var started = false

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    var authorization: LocationAuthorization {
        DeviceLocationReply.authorization(manager.authorizationStatus)
    }

    /// Ask for permission once. macOS shows its own prompt the first time;
    /// Larry can turn it off in System Settings, and the bot is then told
    /// "denied" and says so.
    func start() {
        guard !started else { return }
        started = true
        if manager.authorizationStatus == .notDetermined {
            manager.requestWhenInUseAuthorization()
        }
    }

    /// Answer one location/request. `reply` is called exactly once.
    func answer(_ request: LocationRequest, reply: @escaping (LocationResult) -> Void) {
        switch manager.authorizationStatus {
        case .denied, .restricted:
            reply(.failure(requestID: request.requestID, .denied))
            return
        default:
            break
        }
        waiting.append((id: request.requestID, reply: reply))
        if waiting.count == 1 {
            manager.requestLocation()
        }
    }

    private func finish(_ build: (String) -> LocationResult) {
        let pending = waiting
        waiting.removeAll()
        for entry in pending { entry.reply(build(entry.id)) }
    }

    // MARK: - CLLocationManagerDelegate

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last, !waiting.isEmpty else { return }
        geocoder.reverseGeocodeLocation(location) { [weak self] placemarks, _ in
            let place = placemarks?.first
            let label = DeviceLocationReply.label(locality: place?.locality,
                                                  administrativeArea: place?.administrativeArea)
            Task { @MainActor in
                guard let self else { return }
                locationLogger.debug("fix answered (accuracy \(Int(location.horizontalAccuracy), privacy: .public) m)")
                self.finish { id in DeviceLocationReply.result(requestID: id, location: location, label: label) }
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let failure = DeviceLocationReply.failure(for: error)
        locationLogger.error("fix failed: \(error.localizedDescription, privacy: .public)")
        finish { id in .failure(requestID: id, failure) }
    }
}
