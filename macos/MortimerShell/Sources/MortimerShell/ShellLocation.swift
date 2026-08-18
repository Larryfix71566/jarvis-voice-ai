// ShellLocation.swift
// Larry 2026-08-18: "I want to know where I am so that current weather
// is correct for my current location." IP geolocation (the sidecar's
// fallback) is ISP-accurate at best — tens of miles off, and wrong
// entirely on a VPN. This is the accurate path: CoreLocation, which on a
// Mac resolves position from surrounding WiFi networks (Macs have no GPS
// receiver) to roughly a city block.
//
// Deliberately NOT routed through the web layer: the shell POSTs
// coordinates straight to the admin sidecar's /api/location, so the
// console page never touches the Geolocation API and the ambient layer's
// "the client never initiates its own API calls" rule stays intact. The
// sidecar keeps ownership of the weather fetch (jarvis/ambient_weather.py).
//
// Privacy posture, matching the sidecar side: coordinates live in the
// sidecar's memory only — never written to disk, never logged with the
// values, never sent anywhere except Open-Meteo as lat/lon. Location
// stops being reported the moment the shell quits, and the sidecar
// expires it after an hour.
//
// Requires (see templates/ and README): NSLocationWhenInUseUsageDescription
// in Info.plist and com.apple.security.personal-information.location in
// the entitlements. Without them CoreLocation reports .denied and this
// class stays silent — the sidecar simply keeps using IP geolocation, so
// a build missing the entitlement degrades instead of breaking.

import CoreLocation
import Foundation
import os

private let logger = Logger(subsystem: "com.mortimer.shell", category: "location")

/// Where the sidecar listens. Matches JARVIS_ADMIN_URL's default; the
/// shell has no .env reader, and this is the same localhost-only posture
/// every other admin endpoint already assumes.
private let sidecarLocationURL = URL(string: "http://127.0.0.1:7861/api/location")!

/// Report only after moving this far (meters) — a parked laptop should
/// not generate traffic, and weather does not change block to block.
private let significantDistanceMeters: CLLocationDistance = 1000

@MainActor
final class ShellLocation: NSObject, CLLocationManagerDelegate {
    static let shared = ShellLocation()

    private let manager = CLLocationManager()
    private let geocoder = CLGeocoder()
    private var started = false
    private var lastReported: CLLocation?

    private override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
        manager.distanceFilter = significantDistanceMeters
    }

    /// Called once from ShellRootView.onAppear, beside
    /// ScreenPlacement.startObserving(). Safe to call repeatedly.
    func start() {
        guard !started else { return }
        started = true
        logger.debug("start: requesting authorization")
        manager.requestWhenInUseAuthorization()
    }

    // MARK: - CLLocationManagerDelegate

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorized:
            logger.debug("authorization granted — starting updates")
            manager.startUpdatingLocation()
        case .notDetermined:
            logger.debug("authorization not determined yet")
        case .denied, .restricted:
            // Not an error worth surfacing: the sidecar falls back to IP
            // geolocation on its own. Logged so the reason is findable.
            logger.error("authorization denied/restricted — weather will fall back to IP geolocation")
        @unknown default:
            logger.error("unknown authorization status")
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        if let prev = lastReported, loc.distance(from: prev) < significantDistanceMeters {
            return
        }
        lastReported = loc
        // Resolve a human city name for the chip; the POST goes out
        // either way, since an unlabeled coordinate still gives correct
        // weather (the label is cosmetic).
        geocoder.reverseGeocodeLocation(loc) { [weak self] placemarks, _ in
            let label = placemarks?.first?.locality ?? ""
            Task { @MainActor in
                self?.post(coordinate: loc.coordinate, label: label)
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Never fatal — IP geolocation remains the fallback.
        logger.error("location update failed: \(error.localizedDescription, privacy: .public)")
    }

    // MARK: - Reporting

    private func post(coordinate: CLLocationCoordinate2D, label: String) {
        var request = URLRequest(url: sidecarLocationURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 5
        let body: [String: Any] = [
            "lat": coordinate.latitude,
            "lon": coordinate.longitude,
            "label": label,
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else {
            logger.error("post: could not encode body")
            return
        }
        request.httpBody = data
        // Deliberately does not log the coordinates themselves — only
        // that a report happened, and to where.
        logger.debug("post: reporting location to sidecar (label='\(label, privacy: .public)')")
        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error {
                logger.error("post: failed — \(error.localizedDescription, privacy: .public)")
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if status >= 400 {
                logger.error("post: sidecar returned \(status)")
            }
        }.resume()
    }
}
