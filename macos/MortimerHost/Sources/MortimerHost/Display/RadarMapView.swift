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
    /// Called on the main actor when the shown frame's tiles are (or stop
    /// being) all loaded, so the card can say "Loading radar…".
    var onReady: (Bool) -> Void = { _ in }

    /// Opening view: about 60 km across, centred on the pin.
    static let openingSpanMeters: CLLocationDistance = 60_000
    static let frameInterval: TimeInterval = 0.6
    static let visibleAlpha: CGFloat = 0.8

    func makeCoordinator() -> Coordinator { Coordinator(onFrame: onFrame, onReady: onReady) }

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
        context.coordinator.onReady = onReady
        context.coordinator.setPlaying(playing)
    }

    static func dismantleNSView(_ map: MKMapView, coordinator: Coordinator) {
        coordinator.stop()
    }

    /// Larry, 2026-09-29: the radar "comes up slowly and flashes". It
    /// flashed because each step removed the shown frame and added the next,
    /// whose tiles were not loaded yet. Now every frame is added once and
    /// stays; only the shown frame's renderer is visible (alpha). Tiles are
    /// kept in `RadarTileStore`, a request for one frame warms the same tile
    /// in every other frame, and the loop only moves to a frame whose tiles
    /// are all in.
    @MainActor
    final class Coordinator: NSObject, MKMapViewDelegate {
        private var overlays: [RadarTileOverlay] = []
        private var renderers: [ObjectIdentifier: MKTileOverlayRenderer] = [:]
        private(set) var shown: Int = -1
        private var timer: Timer?
        private var playing = false
        private var lastReady: Bool?
        private let store: RadarTileStore
        var onFrame: (Int) -> Void
        var onReady: (Bool) -> Void

        init(onFrame: @escaping (Int) -> Void, onReady: @escaping (Bool) -> Void,
             store: RadarTileStore = RadarTileStore()) {
            self.onFrame = onFrame
            self.onReady = onReady
            self.store = store
        }

        func install(radar: WeatherCard.Radar, on map: MKMapView) {
            let templates = radar.frames.map(\.template)
            overlays = templates.map {
                RadarTileOverlay(template: $0, maxNativeZoom: radar.maxNativeZoom,
                                 siblings: templates, store: store)
            }
            guard !overlays.isEmpty else { return }
            shown = overlays.count - 1                                     // newest first
            map.addOverlays(overlays, level: .aboveRoads)
            report(frame: shown)
            timer = Timer.scheduledTimer(withTimeInterval: RadarMapView.frameInterval,
                                         repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.tick() }
            }
        }

        func setPlaying(_ playing: Bool) {
            self.playing = playing && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        }

        /// Every tick: report whether the shown frame is loaded; when
        /// playing, step to the next frame only if both are loaded.
        func tick() {
            guard overlays.indices.contains(shown) else { return }
            let ready = store.isReady(template: overlays[shown].template)
            if ready != lastReady {
                lastReady = ready
                let report = onReady
                DispatchQueue.main.async { report(ready) }
            }
            guard playing, ready, overlays.count > 1 else { return }
            let next = RadarTileMath.nextFrame(after: shown, count: overlays.count)
            if store.isReady(template: overlays[next].template) { show(next) }
        }

        func show(_ index: Int) {
            guard overlays.indices.contains(index), index != shown else { return }
            shown = index
            for (i, overlay) in overlays.enumerated() {
                guard let renderer = renderers[ObjectIdentifier(overlay)] else { continue }
                let alpha = i == index ? RadarMapView.visibleAlpha : 0
                if renderer.alpha != alpha {
                    renderer.alpha = alpha
                    renderer.setNeedsDisplay()
                }
            }
            report(frame: index)
        }

        private func report(frame index: Int) {
            // After this update pass: changing SwiftUI state while the map is
            // being made/updated is not allowed.
            let report = onFrame
            DispatchQueue.main.async { report(index) }
        }

        func stop() {
            timer?.invalidate()
            timer = nil
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let tiles = overlay as? RadarTileOverlay {
                let renderer = MKTileOverlayRenderer(tileOverlay: tiles)
                let index = overlays.firstIndex { $0 === tiles }
                renderer.alpha = index == shown ? RadarMapView.visibleAlpha : 0
                renderers[ObjectIdentifier(tiles)] = renderer
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
/// provider's last native zoom. Tiles come through the shared
/// `RadarTileStore`; asking for one tile also warms it in the other frames.
final class RadarTileOverlay: MKTileOverlay {
    let template: String
    let maxNativeZoom: Int
    let siblings: [String]
    let store: RadarTileStore

    init(template: String, maxNativeZoom: Int, siblings: [String] = [],
         store: RadarTileStore = RadarTileStore()) {
        self.template = template
        self.maxNativeZoom = maxNativeZoom
        self.siblings = siblings
        self.store = store
        super.init(urlTemplate: template)
        canReplaceMapContent = false
        minimumZ = 1
        maximumZ = 20
    }

    override func loadTile(at path: MKTileOverlayPath, result: @escaping (Data?, Error?) -> Void) {
        let source = RadarTileMath.source(z: path.z, x: path.x, y: path.y,
                                          maxNativeZoom: maxNativeZoom)
        store.noteRequested(z: source.z, x: source.x, y: source.y)
        // This frame's own tile first; the other frames' copies of it after,
        // so warming the loop never slows the first picture.
        store.tile(template: template, source: source) { [store, siblings, template] data, error in
            result(data, error)
            for sibling in siblings where sibling != template {
                store.prefetch(template: sibling, z: source.z, x: source.x, y: source.y)
            }
        }
    }
}

/// The radar's tile memory, one per map: raw tiles by URL (fetched once,
/// however many overlays or prefetches ask), enlarged tiles by URL and
/// crop, and the tiles the map most recently asked for, which decide
/// whether a frame is ready to show. Unit-tested (RadarTileStoreTests).
final class RadarTileStore: @unchecked Sendable {
    typealias Completion = (Data?, Error?) -> Void
    typealias Fetch = (URL, @escaping Completion) -> Void

    /// Radar tiles come from third-party servers, so they get their own
    /// ephemeral session: nothing shared with Mortimer's own HTTP, and the
    /// app's shared session stays reserved for JarvisHTTP (G13,
    /// MemoryGraphClosureC3Tests).
    private static let tileSession = URLSession(configuration: .ephemeral)
    /// Tiles the map asked for most recently (one view's worth, with room).
    static let recentLimit = 48

    static let networkFetch: Fetch = { url, done in
        RadarTileStore.tileSession.dataTask(with: url) { data, response, error in
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard let data, error == nil, status == 200 else {
                done(nil, error ?? URLError(.badServerResponse))
                return
            }
            done(data, nil)
        }.resume()
    }

    private let fetch: Fetch
    private let lock = NSLock()
    private let raw = NSCache<NSString, NSData>()
    private let enlarged = NSCache<NSString, NSData>()
    private var failed: Set<String> = []
    private var waiting: [String: [Completion]] = [:]
    private var recent: [String] = []          // "z/x/y", newest last

    init(fetch: @escaping Fetch = RadarTileStore.networkFetch) {
        self.fetch = fetch
        raw.countLimit = 1_500
        enlarged.countLimit = 1_500
    }

    func noteRequested(z: Int, x: Int, y: Int) {
        let key = "\(z)/\(x)/\(y)"
        lock.lock(); defer { lock.unlock() }
        recent.removeAll { $0 == key }
        recent.append(key)
        if recent.count > Self.recentLimit { recent.removeFirst(recent.count - Self.recentLimit) }
    }

    /// True when every recently requested tile of this frame is loaded (or
    /// has failed — a missing tile must not stall the loop). False before
    /// the map has asked for anything.
    func isReady(template: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard !recent.isEmpty else { return false }
        return recent.allSatisfy { key in
            let p = key.split(separator: "/").compactMap { Int($0) }
            guard p.count == 3, let url = RadarTileMath.url(template: template, z: p[0], x: p[1], y: p[2])
            else { return true }
            let k = url.absoluteString
            return raw.object(forKey: k as NSString) != nil || failed.contains(k)
        }
    }

    func prefetch(template: String, z: Int, x: Int, y: Int) {
        guard let url = RadarTileMath.url(template: template, z: z, x: x, y: y) else { return }
        rawTile(url) { _, _ in }
    }

    /// The tile MapKit asked for: the provider's own tile, or the enlarged
    /// part of its ancestor past the last native zoom.
    func tile(template: String, source: RadarTileMath.Source, completion: @escaping Completion) {
        guard let url = RadarTileMath.url(template: template, z: source.z, x: source.x, y: source.y) else {
            completion(nil, nil)
            return
        }
        let whole = source.crop == CGRect(x: 0, y: 0, width: 1, height: 1)
        let key = "\(url.absoluteString)#\(source.crop.minX),\(source.crop.minY),\(source.crop.width)" as NSString
        if !whole, let done = enlarged.object(forKey: key) {
            completion(done as Data, nil)
            return
        }
        rawTile(url) { [enlarged] data, error in
            guard let data else { completion(nil, error); return }
            if whole { completion(data, nil); return }
            let out = RadarTileMath.enlarge(data, crop: source.crop)
            if let out { enlarged.setObject(out as NSData, forKey: key) }
            completion(out, nil)
        }
    }

    private func rawTile(_ url: URL, completion: @escaping Completion) {
        let key = url.absoluteString
        lock.lock()
        if let hit = raw.object(forKey: key as NSString) {
            lock.unlock()
            completion(hit as Data, nil)
            return
        }
        if waiting[key] != nil {
            waiting[key]?.append(completion)
            lock.unlock()
            return
        }
        waiting[key] = [completion]
        lock.unlock()
        fetch(url) { [weak self] data, error in
            guard let self else { completion(data, error); return }
            self.lock.lock()
            let waiters = self.waiting.removeValue(forKey: key) ?? []
            if let data {
                self.raw.setObject(data as NSData, forKey: key as NSString)
                self.failed.remove(key)
            } else {
                self.failed.insert(key)
            }
            self.lock.unlock()
            waiters.forEach { $0(data, error) }
        }
    }
}
