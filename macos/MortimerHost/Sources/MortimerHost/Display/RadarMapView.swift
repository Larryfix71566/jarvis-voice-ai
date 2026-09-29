import AppKit
import MapKit
import SwiftUI
import JarvisKit

/// WS-15 PR 2 (MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md S6): Apple's map
/// (streets, labels, standard or hybrid) with the radar as a tile overlay,
/// a pin at the place, and a loop through the radar frames.
///
/// G-3 (2026-09-29 spike): MapKit renders in this ad-hoc-signed app and the
/// IEM tiles load, but MapKit requests nothing past an overlay's
/// `maximumZ`, so radar vanished at the opening close-up view. Here the
/// overlay accepts every zoom and serves zooms past the provider's last
/// native level by enlarging the matching part of the parent tile
/// (`RadarTileMath`), so the radar stays at street level.
struct RadarMapView: NSViewRepresentable {
    let radar: WeatherCard.Radar
    let latitude: Double
    let longitude: Double
    let placeLabel: String
    var hybrid: Bool = false
    var playing: Bool = true
    /// Called on the main actor with the index of the frame now shown.
    var onFrame: (Int) -> Void = { _ in }

    /// Opening view: about 60 km across, centred on the pin.
    static let openingSpanMeters: CLLocationDistance = 60_000
    static let frameInterval: TimeInterval = 0.6

    func makeCoordinator() -> Coordinator { Coordinator(onFrame: onFrame) }

    func makeNSView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        map.showsZoomControls = true
        map.showsCompass = true
        map.showsScale = true
        map.pointOfInterestFilter = .excludingAll
        let center = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        map.setRegion(MKCoordinateRegion(center: center,
                                         latitudinalMeters: Self.openingSpanMeters,
                                         longitudinalMeters: Self.openingSpanMeters),
                      animated: false)
        let pin = MKPointAnnotation()
        pin.coordinate = center
        pin.title = placeLabel
        map.addAnnotation(pin)
        context.coordinator.install(radar: radar, on: map)
        return map
    }

    func updateNSView(_ map: MKMapView, context: Context) {
        map.preferredConfiguration = hybrid
            ? MKHybridMapConfiguration(elevationStyle: .flat)
            : MKStandardMapConfiguration(elevationStyle: .flat)
        context.coordinator.onFrame = onFrame
        context.coordinator.setPlaying(playing, on: map)
    }

    static func dismantleNSView(_ map: MKMapView, coordinator: Coordinator) {
        coordinator.stop()
    }

    @MainActor
    final class Coordinator: NSObject, MKMapViewDelegate {
        private var overlays: [RadarTileOverlay] = []
        private var shown: Int = -1
        private var timer: Timer?
        var onFrame: (Int) -> Void

        init(onFrame: @escaping (Int) -> Void) { self.onFrame = onFrame }

        func install(radar: WeatherCard.Radar, on map: MKMapView) {
            overlays = radar.frames.map {
                RadarTileOverlay(template: $0.template, maxNativeZoom: radar.maxNativeZoom)
            }
            if !overlays.isEmpty { show(overlays.count - 1, on: map) }   // newest first
        }

        func show(_ index: Int, on map: MKMapView) {
            guard overlays.indices.contains(index), index != shown else { return }
            if overlays.indices.contains(shown) { map.removeOverlay(overlays[shown]) }
            shown = index
            map.addOverlay(overlays[index], level: .aboveRoads)
            // Report after this update pass: changing SwiftUI state while
            // the map is being made/updated is not allowed.
            let report = onFrame
            DispatchQueue.main.async { report(index) }
        }

        func setPlaying(_ playing: Bool, on map: MKMapView) {
            let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
            guard playing, !reduceMotion, overlays.count > 1 else {
                stop()
                return
            }
            guard timer == nil else { return }
            timer = Timer.scheduledTimer(withTimeInterval: RadarMapView.frameInterval,
                                         repeats: true) { [weak self, weak map] _ in
                MainActor.assumeIsolated {
                    guard let self, let map else { return }
                    self.show(RadarTileMath.nextFrame(after: self.shown, count: self.overlays.count),
                              on: map)
                }
            }
        }

        func stop() {
            timer?.invalidate()
            timer = nil
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let tiles = overlay as? MKTileOverlay {
                let renderer = MKTileOverlayRenderer(tileOverlay: tiles)
                renderer.alpha = 0.8
                return renderer
            }
            return MKOverlayRenderer(overlay: overlay)
        }
    }
}

/// Pure tile maths for zooms past a provider's last native level, and the
/// loop's frame order. Unit-tested (RadarTileMathTests).
enum RadarTileMath {
    struct Source: Equatable {
        let z: Int, x: Int, y: Int
        /// The part of the source tile to enlarge, as fractions of its size.
        let crop: CGRect
    }

    /// The tile to fetch for (z, x, y): itself up to `maxNativeZoom`,
    /// otherwise its ancestor at `maxNativeZoom` plus the sub-square to crop.
    static func source(z: Int, x: Int, y: Int, maxNativeZoom: Int) -> Source {
        guard z > maxNativeZoom, maxNativeZoom >= 0 else {
            return Source(z: z, x: x, y: y, crop: CGRect(x: 0, y: 0, width: 1, height: 1))
        }
        let dz = z - maxNativeZoom
        let n = 1 << dz
        let px = x >> dz, py = y >> dz
        let size = 1.0 / Double(n)
        return Source(z: maxNativeZoom, x: px, y: py,
                      crop: CGRect(x: Double(x - (px << dz)) * size,
                                   y: Double(y - (py << dz)) * size,
                                   width: size, height: size))
    }

    static func url(template: String, z: Int, x: Int, y: Int) -> URL? {
        URL(string: template
            .replacingOccurrences(of: "{z}", with: String(z))
            .replacingOccurrences(of: "{x}", with: String(x))
            .replacingOccurrences(of: "{y}", with: String(y)))
    }

    static func nextFrame(after index: Int, count: Int) -> Int {
        guard count > 0 else { return 0 }
        return (index + 1) % count
    }

    /// Crop `crop` (fractions, top-left origin) out of a PNG and scale it to
    /// `side` × `side` pixels. Nil when the data isn't an image.
    static func enlarge(_ data: Data, crop: CGRect, side: Int = 256) -> Data? {
        guard let image = NSBitmapImageRep(data: data)?.cgImage else { return nil }
        let rect = CGRect(x: crop.minX * CGFloat(image.width), y: crop.minY * CGFloat(image.height),
                          width: max(1, crop.width * CGFloat(image.width)),
                          height: max(1, crop.height * CGFloat(image.height))).integral
        guard let piece = image.cropping(to: rect),
              let context = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8,
                                      bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return nil }
        context.interpolationQuality = .medium
        context.draw(piece, in: CGRect(x: 0, y: 0, width: side, height: side))
        guard let scaled = context.makeImage() else { return nil }
        return NSBitmapImageRep(cgImage: scaled).representation(using: .png, properties: [:])
    }
}

/// A radar frame as a MapKit tile overlay that never goes blank past the
/// provider's last native zoom.
final class RadarTileOverlay: MKTileOverlay {
    let template: String
    let maxNativeZoom: Int

    init(template: String, maxNativeZoom: Int) {
        self.template = template
        self.maxNativeZoom = maxNativeZoom
        super.init(urlTemplate: template)
        canReplaceMapContent = false
        minimumZ = 1
        maximumZ = 20
    }

    override func loadTile(at path: MKTileOverlayPath, result: @escaping (Data?, Error?) -> Void) {
        let source = RadarTileMath.source(z: path.z, x: path.x, y: path.y,
                                          maxNativeZoom: maxNativeZoom)
        guard let url = RadarTileMath.url(template: template, z: source.z, x: source.x, y: source.y)
        else {
            result(nil, nil)
            return
        }
        URLSession.shared.dataTask(with: url) { data, _, error in
            guard let data, error == nil else {
                result(nil, error)
                return
            }
            if source.z == path.z {
                result(data, nil)
            } else {
                result(RadarTileMath.enlarge(data, crop: source.crop), nil)
            }
        }.resume()
    }
}
