import AppKit
import MapKit
import SwiftUI
import JarvisKit
import os

/// Radar timing evidence (Larry, 09-29: radar "stutters or pauses"). Read with
/// `log show --last 10m --style compact --predicate 'subsystem == "com.mortimer.host" AND category == "radar"'`.
private let radarLog = Logger(subsystem: "com.mortimer.host", category: "radar")

/// WS-15 PR 2 (MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md S6): Apple's map
/// (streets, labels, standard or hybrid) with the radar drawn over it, a pin
/// at the place, and a loop through the radar frames.
///
/// Round 5 (Larry, 09-29, round-4 radar log): once loaded, the loop runs
/// with no downloads at all, but the first lap still paused ~1.8 s on every
/// frame: over 1,000 tiles were queued (about 150 per frame) although a
/// 200 km view shows only a handful. MapKit asks the renderer about far more
/// map than is on screen. Now only tiles on screen (plus a small margin) are
/// queued for the other frames and count towards "ready"; the rest load
/// for the shown frame only, behind them.
///
/// Round 4 (Larry, 09-29, round-3 radar log): first frame fell to 2.4 s,
/// but the loop waited 1.8-12.5 s between frames and, with nothing queued,
/// kept re-downloading ~300 tiles a second. Decoded tiles (256 KB each)
/// overflowed the 200 MB memory limit and were evicted and fetched again,
/// and readiness also waited on tiles from zoom levels no longer shown.
/// Now the compressed PNG (a few KB) is kept for every tile and decoded
/// copies are only a small cache, and readiness counts only the zoom level
/// the map last drew.
///
/// Round 3 (Larry, 09-29, from the radar log): with one MapKit tile overlay
/// per frame, MapKit loaded all 11 frames at once (704 fetches, average
/// 5.4 s, first frame after 10.8 s) and, while looping, re-requested tiles
/// constantly (3,512 requests in 10 s). Now there is ONE overlay whose
/// renderer draws the current frame from decoded tiles in memory. The shown
/// frame's tiles download first; other frames follow, six at a time.
/// Changing frame redraws that one layer and requests nothing. Past the
/// provider's last native zoom the tile is drawn enlarged and smoothed.
struct RadarMapView: NSViewRepresentable {
    let radar: WeatherCard.Radar
    let latitude: Double
    let longitude: Double
    let placeLabel: String
    var hybrid: Bool = false
    var playing: Bool = true
    /// WS-15 voice map control: the newest zoom/reset command and its serial
    /// (WeatherMapCommands); applied once per serial.
    var zoomCommand: WeatherMapCommand? = nil
    /// Called on the main actor with the index of the frame now shown.
    var onFrame: (Int) -> Void = { _ in }
    /// Called on the main actor when the shown frame's tiles are (or stop
    /// being) all loaded, so the card can say "Loading radar…".
    var onReady: (Bool) -> Void = { _ in }

    /// Opening view: about 200 km across, centred on the pin. Larry, 09-29:
    /// the radar looked blocky. The NEXRAD composite's finest level is zoom
    /// 8 (about 0.5 km per pixel); the old 60 km view was near zoom 10-11, so
    /// every radar pixel was blown up 4-8x. At 200 km the map opens near the
    /// data's own resolution; zooming in still works (enlarged, smoothed).
    static let openingSpanMeters: CLLocationDistance = 200_000
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
        if let command = zoomCommand, command.serial != context.coordinator.lastZoomSerial {
            context.coordinator.lastZoomSerial = command.serial
            let opening = MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
                                             latitudinalMeters: Self.openingSpanMeters,
                                             longitudinalMeters: Self.openingSpanMeters)
            let aspect = map.bounds.width > 0 ? Double(map.bounds.height / map.bounds.width) : 1
            switch command.action {
            case "map_zoom_to":
                if let miles = command.miles {
                    map.setRegion(WeatherMapZoom.region(center: map.region.center, acrossMiles: miles,
                                                        aspect: aspect), animated: true)
                }
            case "map_center":
                if let place = command.place {
                    context.coordinator.center(on: place, miles: command.miles, aspect: aspect, map: map)
                }
            default:
                if let region = WeatherMapZoom.region(map.region, action: command.action, opening: opening) {
                    map.setRegion(region, animated: true)
                }
            }
        }
    }

    static func dismantleNSView(_ map: MKMapView, coordinator: Coordinator) {
        coordinator.stop()
    }

    @MainActor
    final class Coordinator: NSObject, MKMapViewDelegate {
        private var overlay: RadarFramesOverlay?
        private var renderer: RadarFramesRenderer?
        private var store: RadarTileStore?
        private var frameCount = 0
        private(set) var shown: Int = -1
        private var timer: Timer?
        private var playing = false
        private var lastReady: Bool?
        private var installedAt = Date()
        private var waitingSince: Date?
        private var lastStats = Date()
        var onFrame: (Int) -> Void
        var onReady: (Bool) -> Void
        /// The last voice zoom command applied (so each is applied once).
        var lastZoomSerial = 0

        init(onFrame: @escaping (Int) -> Void, onReady: @escaping (Bool) -> Void) {
            self.onFrame = onFrame
            self.onReady = onReady
        }

        func install(radar: WeatherCard.Radar, on map: MKMapView) {
            let templates = radar.frames.map(\.template)
            guard !templates.isEmpty else { return }
            let store = RadarTileStore(templates: templates)
            self.store = store
            frameCount = templates.count
            shown = templates.count - 1                                    // newest first
            installedAt = Date()
            lastStats = installedAt
            radarLog.notice("radar installed frames=\(templates.count, privacy: .public) maxNativeZoom=\(radar.maxNativeZoom, privacy: .public) mode=single-layer")
            let overlay = RadarFramesOverlay(maxNativeZoom: radar.maxNativeZoom)
            self.overlay = overlay
            map.addOverlay(overlay, level: .aboveRoads)
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
            guard let store, shown >= 0 else { return }
            let ready = store.isReady(frame: shown)
            if ready != lastReady {
                if ready, lastReady != true {
                    let ms = Int(Date().timeIntervalSince(installedAt) * 1000)
                    radarLog.notice("radar frame \(self.shown, privacy: .public) ready; \(ms, privacy: .public) ms since install")
                }
                lastReady = ready
                let report = onReady
                DispatchQueue.main.async { report(ready) }
            }
            defer { logStatsIfDue() }
            guard playing, ready, frameCount > 1 else { return }
            let next = RadarTileMath.nextFrame(after: shown, count: frameCount)
            if store.isReady(frame: next) {
                if let since = waitingSince {
                    let ms = Int(Date().timeIntervalSince(since) * 1000)
                    radarLog.notice("radar waited \(ms, privacy: .public) ms for frame \(next, privacy: .public)")
                    waitingSince = nil
                }
                show(next)
            } else if waitingSince == nil {
                waitingSince = Date()
            }
        }

        func show(_ index: Int) {
            guard index >= 0, index < frameCount, index != shown else { return }
            shown = index
            renderer?.frame = index
            renderer?.setNeedsDisplay()
            report(frame: index)
        }

        private func report(frame index: Int) {
            // After this update pass: changing SwiftUI state while the map is
            // being made/updated is not allowed.
            let report = onFrame
            DispatchQueue.main.async { report(index) }
        }

        /// Every 10 s: tiles drawn, how many were in memory, how many went to
        /// the network and how long those took.
        private func logStatsIfDue() {
            guard let store, Date().timeIntervalSince(lastStats) >= 10 else { return }
            lastStats = Date()
            let s = store.takeStats()
            radarLog.notice("radar 10s: tileLookups=\(s.requests, privacy: .public) memoryHits=\(s.hits, privacy: .public) fetches=\(s.fetches, privacy: .public) failed=\(s.failures, privacy: .public) fetchAvgMs=\(s.averageFetchMs, privacy: .public) fetchMaxMs=\(s.maxFetchMs, privacy: .public) zooms=\(s.zoomList, privacy: .public) readyTiles=\(store.recentCount, privacy: .public) queued=\(store.queuedCount, privacy: .public) shown=\(self.shown, privacy: .public)")
        }

        func stop() {
            timer?.invalidate()
            timer = nil
        }

        /// map_center (Larry, 2026-09-30: "center the map on Atlanta"): find
        /// the place with Apple Maps search, nearest the current view first,
        /// and move there, keeping the current width unless miles were given.
        func center(on place: String, miles: Double?, aspect: Double, map: MKMapView) {
            let request = MKLocalSearch.Request()
            request.naturalLanguageQuery = place
            request.region = map.region
            let span = map.region.span
            MKLocalSearch(request: request).start { [weak map] response, error in
                MainActor.assumeIsolated {
                    guard let map else { return }
                    guard let item = response?.mapItems.first else {
                        radarLog.notice("map center: no match for \(place, privacy: .public) error=\(String(describing: error), privacy: .public)")
                        return
                    }
                    let coordinate = item.placemark.coordinate
                    radarLog.notice("map center: \(place, privacy: .public) -> \(coordinate.latitude, privacy: .public),\(coordinate.longitude, privacy: .public)")
                    let region = miles.map { WeatherMapZoom.region(center: coordinate, acrossMiles: $0, aspect: aspect) }
                        ?? MKCoordinateRegion(center: coordinate, span: span)
                    map.setRegion(region, animated: true)
                }
            }
        }

        /// Keep the renderer's idea of "on screen" current, and start
        /// readiness afresh for the new view.
        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            renderer?.visibleRect = RadarTileMath.expanded(RadarTileMath.cgRect(mapView.visibleMapRect), by: 0.15)
            store?.clearRecent()
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let frames = overlay as? RadarFramesOverlay, let store {
                let renderer = RadarFramesRenderer(overlay: frames, store: store)
                renderer.visibleRect = RadarTileMath.expanded(RadarTileMath.cgRect(mapView.visibleMapRect), by: 0.15)
                renderer.frame = shown
                renderer.alpha = RadarMapView.visibleAlpha
                self.renderer = renderer
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
        context.interpolationQuality = .high
        context.draw(piece, in: CGRect(x: 0, y: 0, width: side, height: side))
        guard let scaled = context.makeImage() else { return nil }
        return NSBitmapImageRep(cgImage: scaled).representation(using: .png, properties: [:])
    }

    /// World width in MapKit map points (256 × 2^20).
    static let worldMapPoints: Double = 268_435_456

    /// The provider zoom to draw at for a MapKit zoom scale: the map's own
    /// zoom, capped at the provider's last native level (tiles past it are
    /// drawn enlarged and smoothed).
    static func tileZoom(zoomScale: Double, maxNativeZoom: Int) -> Int {
        let z = Int((20 + log2(max(zoomScale, 1e-9))).rounded())
        return min(max(z, 0), max(maxNativeZoom, 0))
    }

    /// The map rectangle one tile covers, as (x, y, width, height) in map points.
    static func mapRect(z: Int, x: Int, y: Int) -> CGRect {
        let size = worldMapPoints / Double(1 << z)
        return CGRect(x: Double(x) * size, y: Double(y) * size, width: size, height: size)
    }

    static func cgRect(_ m: MKMapRect) -> CGRect {
        CGRect(x: m.origin.x, y: m.origin.y, width: m.size.width, height: m.size.height)
    }

    /// `rect` grown by `fraction` of its size on every side.
    static func expanded(_ rect: CGRect, by fraction: Double) -> CGRect {
        rect.insetBy(dx: -rect.width * fraction, dy: -rect.height * fraction)
    }

    /// Whether a tile touches the visible map. With no visible rect yet,
    /// every tile counts (the first draw before MapKit reports a region).
    static func isOnScreen(z: Int, x: Int, y: Int, visible: CGRect?) -> Bool {
        guard let visible else { return true }
        return mapRect(z: z, x: x, y: y).intersects(visible)
    }

    /// Every tile at zoom `z` that touches `rect` (map points).
    static func tiles(covering rect: CGRect, z: Int) -> [(x: Int, y: Int)] {
        let n = 1 << z
        let size = worldMapPoints / Double(n)
        func clamp(_ v: Int) -> Int { min(max(v, 0), n - 1) }
        let x0 = clamp(Int(floor(rect.minX / size))), x1 = clamp(Int(floor((rect.maxX - 1) / size)))
        let y0 = clamp(Int(floor(rect.minY / size))), y1 = clamp(Int(floor((rect.maxY - 1) / size)))
        guard x0 <= x1, y0 <= y1 else { return [] }
        var out: [(x: Int, y: Int)] = []
        for y in y0...y1 { for x in x0...x1 { out.append((x, y)) } }
        return out
    }
}


/// The radar as one map overlay covering the world; what it shows is the
/// renderer's current frame.
final class RadarFramesOverlay: NSObject, MKOverlay {
    let maxNativeZoom: Int
    init(maxNativeZoom: Int) { self.maxNativeZoom = maxNativeZoom }
    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: 0, longitude: 0) }
    var boundingMapRect: MKMapRect { .world }
}

/// Draws the current radar frame from decoded tiles held by the store.
/// MapKit calls `canDraw`/`draw` on background threads, so the frame index is
/// lock-protected. A missing tile is requested (current frame first) and its
/// rectangle redrawn when it arrives; the other frames' copies of every tile
/// the map shows are queued behind it.
final class RadarFramesRenderer: MKOverlayRenderer {
    private let store: RadarTileStore
    private let maxNativeZoom: Int
    private let lock = NSLock()
    private var _frame = 0
    private var _visible: CGRect?

    var frame: Int {
        get { lock.lock(); defer { lock.unlock() }; return _frame }
        set { lock.lock(); _frame = newValue; lock.unlock() }
    }

    /// The map on screen (map points, with a margin); nil until known.
    var visibleRect: CGRect? {
        get { lock.lock(); defer { lock.unlock() }; return _visible }
        set { lock.lock(); _visible = newValue; lock.unlock() }
    }

    init(overlay: RadarFramesOverlay, store: RadarTileStore) {
        self.store = store
        self.maxNativeZoom = overlay.maxNativeZoom
        super.init(overlay: overlay)
    }

    override func canDraw(_ mapRect: MKMapRect, zoomScale: MKZoomScale) -> Bool {
        let z = RadarTileMath.tileZoom(zoomScale: Double(zoomScale), maxNativeZoom: maxNativeZoom)
        let current = frame
        let visible = visibleRect
        for tile in RadarTileMath.tiles(covering: cgRect(mapRect), z: z) {
            let onScreen = RadarTileMath.isOnScreen(z: z, x: tile.x, y: tile.y, visible: visible)
            if onScreen { store.noteRequested(z: z, x: tile.x, y: tile.y) }
            store.request(frame: current, z: z, x: tile.x, y: tile.y, urgent: onScreen) { [weak self] in
                let r = RadarTileMath.mapRect(z: z, x: tile.x, y: tile.y)
                DispatchQueue.main.async {
                    self?.setNeedsDisplay(MKMapRect(x: r.minX, y: r.minY, width: r.width, height: r.height),
                                          zoomScale: zoomScale)
                }
            }
            if onScreen { store.queueOtherFrames(than: current, z: z, x: tile.x, y: tile.y) }
        }
        return true
    }

    override func draw(_ mapRect: MKMapRect, zoomScale: MKZoomScale, in context: CGContext) {
        let z = RadarTileMath.tileZoom(zoomScale: Double(zoomScale), maxNativeZoom: maxNativeZoom)
        let current = frame
        context.interpolationQuality = .high
        for tile in RadarTileMath.tiles(covering: cgRect(mapRect), z: z) {
            guard let image = store.image(frame: current, z: z, x: tile.x, y: tile.y) else { continue }
            let m = RadarTileMath.mapRect(z: z, x: tile.x, y: tile.y)
            let r = rect(for: MKMapRect(x: m.minX, y: m.minY, width: m.width, height: m.height))
            // The renderer's context is flipped (y down); draw the image upright.
            context.saveGState()
            context.translateBy(x: r.minX, y: r.maxY)
            context.scaleBy(x: 1, y: -1)
            context.draw(image, in: CGRect(x: 0, y: 0, width: r.width, height: r.height))
            context.restoreGState()
        }
    }

    private func cgRect(_ m: MKMapRect) -> CGRect { RadarTileMath.cgRect(m) }
}

/// The radar's tile memory, one per map: decoded tiles per frame, a download
/// queue with the shown frame first and at most `maxInFlight` downloads at a
/// time, and the tiles the map most recently asked for, which decide whether
/// a frame is ready to show. Unit-tested (RadarTileStoreTests).
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
    static let maxInFlight = 6

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

    /// Counters for the radar log; `takeStats` reads and resets them.
    struct Stats: Equatable {
        var requests = 0, hits = 0, fetches = 0, failures = 0
        var totalFetchMs = 0, maxFetchMs = 0
        /// Zoom levels the map asked for in this window.
        var zooms: Set<Int> = []
        var averageFetchMs: Int { fetches == 0 ? 0 : totalFetchMs / fetches }
        var zoomList: String { zooms.sorted().map(String.init).joined(separator: ",") }
    }

    private final class ImageBox { let image: CGImage; init(_ i: CGImage) { image = i } }
    private struct Job { let key: String; let url: URL; let frame: Int }

    let templates: [String]
    private let fetch: Fetch
    private let lock = NSLock()
    /// Compressed tiles, kept for the life of the map (a few KB each).
    private let raw = NSCache<NSString, NSData>()
    /// Decoded tiles for drawing; a small cache, refilled from `raw`.
    private let images = NSCache<NSString, ImageBox>()
    private var latestZ: Int?
    private var failed: Set<String> = []
    private var waiting: [String: [() -> Void]] = [:]   // queued or in flight
    private var urgent: [Job] = []
    private var background: [Job] = []
    private var inFlight = 0
    private var recent: [String] = []                    // "z/x/y", newest last
    private var stats = Stats()

    init(templates: [String], fetch: @escaping Fetch = RadarTileStore.networkFetch) {
        self.templates = templates
        self.fetch = fetch
        raw.totalCostLimit = 256 * 1024 * 1024
        images.countLimit = 400
    }

    var queuedCount: Int { lock.lock(); defer { lock.unlock() }; return urgent.count + background.count }
    var recentCount: Int { lock.lock(); defer { lock.unlock() }; return recent.count }

    /// The view changed: readiness starts again from the tiles now drawn.
    func clearRecent() { lock.lock(); recent.removeAll(); lock.unlock() }

    func takeStats() -> Stats {
        lock.lock(); defer { lock.unlock() }
        let out = stats
        stats = Stats()
        return out
    }

    func noteRequested(z: Int, x: Int, y: Int) {
        let key = "\(z)/\(x)/\(y)"
        lock.lock(); defer { lock.unlock() }
        latestZ = z
        stats.zooms.insert(z)
        if recent.last == key { return }
        recent.removeAll { $0 == key }
        recent.append(key)
        if recent.count > Self.recentLimit { recent.removeFirst(recent.count - Self.recentLimit) }
    }

    /// The decoded tile, if it is in memory (decoding the kept PNG when the
    /// decoded copy was dropped). Counts as a draw lookup.
    func image(frame: Int, z: Int, x: Int, y: Int) -> CGImage? {
        guard let key = key(frame: frame, z: z, x: x, y: y) else { return nil }
        var image = images.object(forKey: key as NSString)?.image
        if image == nil, let data = raw.object(forKey: key as NSString), let decoded = Self.decode(data as Data) {
            images.setObject(ImageBox(decoded), forKey: key as NSString)
            image = decoded
        }
        lock.lock(); stats.requests += 1; if image != nil { stats.hits += 1 }; lock.unlock()
        return image
    }

    private func has(_ key: String) -> Bool {
        raw.object(forKey: key as NSString) != nil || images.object(forKey: key as NSString) != nil
    }

    /// Drop every decoded copy (tests use this to prove tiles come back from
    /// the kept PNGs without a download).
    func purgeDecoded() { images.removeAllObjects() }

    /// True when every recently requested tile of this frame, at the zoom
    /// level the map last drew, is in memory (or has failed — a missing tile
    /// must not stall the loop). False before the map has asked for anything.
    func isReady(frame: Int) -> Bool {
        lock.lock(); let keys = recent; let failedNow = failed; let z = latestZ; lock.unlock()
        guard let z else { return false }
        let prefix = "\(z)/"
        let current = keys.filter { $0.hasPrefix(prefix) }
        guard !current.isEmpty else { return false }
        return current.allSatisfy { k in
            let p = k.split(separator: "/").compactMap { Int($0) }
            guard p.count == 3, let key = key(frame: frame, z: p[0], x: p[1], y: p[2]) else { return true }
            return has(key) || failedNow.contains(key)
        }
    }

    /// Ask for a tile. Urgent requests go ahead of queued background ones
    /// (and promote a queued background copy). `loaded` runs once the tile is
    /// in memory; never if it is already there.
    func request(frame: Int, z: Int, x: Int, y: Int, urgent isUrgent: Bool, loaded: @escaping () -> Void = {}) {
        guard let key = key(frame: frame, z: z, x: x, y: y), let url = URL(string: key) else { return }
        if has(key) { return }
        lock.lock()
        if !isUrgent && failed.contains(key) { lock.unlock(); return }
        if waiting[key] != nil {
            waiting[key]?.append(loaded)
            if isUrgent, let i = background.firstIndex(where: { $0.key == key }) {
                urgent.append(background.remove(at: i))
            }
            lock.unlock()
            return
        }
        failed.remove(key)
        waiting[key] = [loaded]
        let job = Job(key: key, url: url, frame: frame)
        if isUrgent { urgent.append(job) } else { background.append(job) }
        lock.unlock()
        pump()
    }

    /// Queue the same tile in every other frame, in loop order.
    func queueOtherFrames(than current: Int, z: Int, x: Int, y: Int) {
        for f in templates.indices where f != current {
            request(frame: f, z: z, x: x, y: y, urgent: false)
        }
    }

    private func key(frame: Int, z: Int, x: Int, y: Int) -> String? {
        guard templates.indices.contains(frame) else { return nil }
        return RadarTileMath.url(template: templates[frame], z: z, x: x, y: y)?.absoluteString
    }

    private func pump() {
        var start: [Job] = []
        lock.lock()
        while inFlight < Self.maxInFlight, !(urgent.isEmpty && background.isEmpty) {
            let job: Job
            if !urgent.isEmpty {
                job = urgent.removeFirst()
            } else {
                // Other frames load whole frames at a time, in loop order
                // (oldest first), so the loop can move on as soon as possible.
                let i = background.indices.min { background[$0].frame < background[$1].frame } ?? 0
                job = background.remove(at: i)
            }
            inFlight += 1
            start.append(job)
        }
        lock.unlock()
        for job in start { run(job) }
    }

    private func run(_ job: Job) {
        let started = Date()
        fetch(job.url) { [weak self] data, _ in
            guard let self else { return }
            let ms = Int(Date().timeIntervalSince(started) * 1000)
            let image = data.flatMap(Self.decode)
            if let image, let data {
                self.raw.setObject(data as NSData, forKey: job.key as NSString, cost: data.count)
                self.images.setObject(ImageBox(image), forKey: job.key as NSString)
            }
            self.lock.lock()
            self.inFlight -= 1
            self.stats.fetches += 1
            self.stats.totalFetchMs += ms
            self.stats.maxFetchMs = max(self.stats.maxFetchMs, ms)
            if image == nil { self.failed.insert(job.key); self.stats.failures += 1 }
            let callbacks = self.waiting.removeValue(forKey: job.key) ?? []
            self.lock.unlock()
            if image != nil { callbacks.forEach { $0() } }
            self.pump()
        }
    }

    /// Decode once, up front, so drawing never decodes a PNG.
    static func decode(_ data: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary)
    }
}
