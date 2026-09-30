import Foundation
import MapKit
import Observation

/// WS-15 (Larry, 2026-09-29: "the map should be zoomable by voice"). The
/// ui_control map actions reach the weather card through this one app-wide
/// channel: UICommandRouter posts, the card on screen observes `serial` and
/// applies the newest command. With no card showing, nothing observes it
/// and the command changes nothing.
@MainActor
@Observable
final class WeatherMapCommands {
    static let shared = WeatherMapCommands()
    static let actions: Set<String> = [
        "map_zoom_in", "map_zoom_out", "map_reset",
        "radar_pause", "radar_play", "map_satellite", "map_standard",
        "map_zoom_to", "map_center",
    ]

    private(set) var serial = 0
    private(set) var latest: String?
    /// The newest command with its arguments (map_zoom_to / map_center).
    private(set) var latestCommand: WeatherMapCommand?

    func send(_ action: String, miles: Double? = nil, place: String? = nil) {
        guard Self.actions.contains(action) else { return }
        serial += 1
        latest = action
        latestCommand = WeatherMapCommand(serial: serial, action: action, miles: miles, place: place)
    }
}

/// One map command as the weather card applies it (applied once per serial).
struct WeatherMapCommand: Equatable {
    let serial: Int
    let action: String
    var miles: Double? = nil
    var place: String? = nil
}

/// Pure map-region maths for the zoom commands. Unit-tested.
enum WeatherMapZoom {
    /// Zoom in halves the span, zoom out doubles it (capped so the map never
    /// asks for more than the whole globe), reset returns the opening view.
    static func region(_ current: MKCoordinateRegion, action: String,
                       opening: MKCoordinateRegion) -> MKCoordinateRegion? {
        var r = current
        switch action {
        case "map_zoom_in":
            r.span = MKCoordinateSpan(latitudeDelta: r.span.latitudeDelta / 2,
                                      longitudeDelta: r.span.longitudeDelta / 2)
        case "map_zoom_out":
            r.span = MKCoordinateSpan(latitudeDelta: min(r.span.latitudeDelta * 2, 170),
                                      longitudeDelta: min(r.span.longitudeDelta * 2, 350))
        case "map_reset":
            return opening
        default:
            return nil
        }
        return r
    }

    static let metersPerMile = 1_609.344

    /// Larry, 2026-09-30: "zoom to 10 miles" means the map is 10 miles wide,
    /// edge to edge. `aspect` is the map's height / width, so the region's
    /// height keeps the view's shape and MapKit fits the width exactly.
    static func region(center: CLLocationCoordinate2D, acrossMiles miles: Double,
                       aspect: Double) -> MKCoordinateRegion {
        let width = max(miles, 0.1) * metersPerMile
        let shape = aspect.isFinite && aspect > 0 ? aspect : 1
        return MKCoordinateRegion(center: center, latitudinalMeters: width * shape,
                                  longitudinalMeters: width)
    }
}
