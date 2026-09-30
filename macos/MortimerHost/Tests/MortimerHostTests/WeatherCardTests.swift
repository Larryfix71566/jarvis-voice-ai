import XCTest
import AppKit
import MapKit
import JarvisKit
@testable import MortimerHost

/// WS-15 PR 2: the weather card's pure pieces — radar tile maths past the
/// provider's last native zoom, frame looping, card text, and the rule that
/// a weather card stays in the main window.
final class WeatherCardTests: XCTestCase {
    private func payload(kind: String = "weather", schema: Int = 1, policy: String? = nil) throws -> DisplayPayload {
        var display: [String: Any] = [
            "kind": kind, "surface": "window", "body": "Summary",
            "weather": [
                "schema": schema,
                "place": ["label": "Folly Beach, SC", "lat": 32.6611, "lon": -79.928,
                          "source": "device", "approximate": false],
                "units": "imperial",
                "now": ["temp": "82°", "condition": "Clear", "humidity": "72%",
                        "wind": "E 10 mph", "symbol": "sun.max.fill"],
                "days": [], "hourly": [], "alerts": [],
                "radar": ["provider": "iem", "max_native_zoom": 8,
                          "frames": [["label": "now", "template": "https://t/{z}/{x}/{y}.png"]],
                          "attribution": "Radar: NOAA"],
                "summary": "Summary", "attribution": "Forecast: NWS",
            ] as [String: Any],
        ]
        if let policy { display["data_policy"] = policy }
        let data = try JSONSerialization.data(withJSONObject: display)
        return try JSONDecoder().decode(DisplayPayload.self, from: data)
    }

    // MARK: tile maths

    func testNativeZoomFetchesItselfUncropped() {
        let s = RadarTileMath.source(z: 8, x: 71, y: 103, maxNativeZoom: 8)
        XCTAssertEqual(s, .init(z: 8, x: 71, y: 103, crop: CGRect(x: 0, y: 0, width: 1, height: 1)))
    }

    func testPastNativeZoomUsesTheParentQuarter() {
        // z9 (143, 206) sits in z8 (71, 103): right column, top row.
        let s = RadarTileMath.source(z: 9, x: 143, y: 206, maxNativeZoom: 8)
        XCTAssertEqual(s.z, 8); XCTAssertEqual(s.x, 71); XCTAssertEqual(s.y, 103)
        XCTAssertEqual(s.crop, CGRect(x: 0.5, y: 0, width: 0.5, height: 0.5))
    }

    func testThreeLevelsPastNativeZoom() {
        // z11 (575, 827): ancestor at z8 is (71, 103); offset (7, 3) of 8.
        let s = RadarTileMath.source(z: 11, x: 575, y: 827, maxNativeZoom: 8)
        XCTAssertEqual(s.z, 8); XCTAssertEqual(s.x, 71); XCTAssertEqual(s.y, 103)
        XCTAssertEqual(s.crop, CGRect(x: 7.0 / 8, y: 3.0 / 8, width: 1.0 / 8, height: 1.0 / 8))
    }

    func testTemplateSubstitution() {
        XCTAssertEqual(RadarTileMath.url(template: "https://h/l/{z}/{x}/{y}.png", z: 8, x: 71, y: 103)?
            .absoluteString, "https://h/l/8/71/103.png")
    }

    func testFramesLoop() {
        XCTAssertEqual(RadarTileMath.nextFrame(after: 9, count: 11), 10)
        XCTAssertEqual(RadarTileMath.nextFrame(after: 10, count: 11), 0)
        XCTAssertEqual(RadarTileMath.nextFrame(after: 0, count: 0), 0)
    }

    func testEnlargeProducesATilePNG() throws {
        let rep = try XCTUnwrap(NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: 256, pixelsHigh: 256, bitsPerSample: 8,
            samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0))
        let png = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
        let out = try XCTUnwrap(RadarTileMath.enlarge(png, crop: CGRect(x: 0.5, y: 0, width: 0.5, height: 0.5)))
        let scaled = try XCTUnwrap(NSBitmapImageRep(data: out))
        XCTAssertEqual(scaled.pixelsWide, 256)
        XCTAssertEqual(scaled.pixelsHigh, 256)
        XCTAssertNil(RadarTileMath.enlarge(Data("not an image".utf8), crop: CGRect(x: 0, y: 0, width: 1, height: 1)))
    }

    // MARK: card text

    func testPlaceNotes() throws {
        let card = try XCTUnwrap(try payload().weather)
        XCTAssertEqual(WeatherCardText.placeNote(card.place), "This Mac's location")
        XCTAssertEqual(WeatherCardText.details(card.now), "Humidity 72% · Wind E 10 mph")
        XCTAssertEqual(WeatherCardText.frameLabel(try XCTUnwrap(card.radar), index: 0), "Radar · now")
        XCTAssertEqual(WeatherCardText.frameLabel(try XCTUnwrap(card.radar), index: 5), "Radar")
        XCTAssertEqual(WeatherCardText.radarStatus(try XCTUnwrap(card.radar), index: 0, ready: false),
                       "Loading radar…")
        XCTAssertEqual(WeatherCardText.radarStatus(try XCTUnwrap(card.radar), index: 0, ready: true),
                       "Radar · now")
    }

    // MARK: routing rule

    func testWeatherCardStaysInTheMainWindow() throws {
        XCTAssertTrue(AppMessageRouter.showsInMainWindowOnly(try payload()))
    }

    func testOtherPayloadsKeepTheirSurface() throws {
        XCTAssertFalse(AppMessageRouter.showsInMainWindowOnly(try payload(kind: "image")))
        XCTAssertFalse(AppMessageRouter.showsInMainWindowOnly(try payload(schema: 2)))  // undecodable card
        XCTAssertFalse(AppMessageRouter.showsInMainWindowOnly(try payload(policy: "local_only")))
        XCTAssertFalse(AppMessageRouter.showsInMainWindowOnly(DisplayPayload(responseText: "x", timestamp: 1)))
    }
}

/// The radar's tile memory (Larry, 2026-09-29: radar slow to start and
/// choppy; the radar log showed every frame loading at once and constant
/// re-requests). One overlay draws decoded tiles; downloads are queued with
/// the shown frame first and at most six at a time.
final class RadarTileStoreTests: XCTestCase {
    /// A fetcher that records requests and answers only when told to.
    final class FakeFetch: @unchecked Sendable {
        var requests: [URL] = []
        var pending: [(URL, RadarTileStore.Completion)] = []
        lazy var fetch: RadarTileStore.Fetch = { [unowned self] url, done in
            self.requests.append(url)
            self.pending.append((url, done))
        }
        func answerAll(with data: Data?) {
            let now = pending; pending = []
            now.forEach { $0.1(data, data == nil ? URLError(.badServerResponse) : nil) }
        }
        func answerFirst(with data: Data?) {
            let first = pending.removeFirst()
            first.1(data, data == nil ? URLError(.badServerResponse) : nil)
        }
    }

    private let templates = ["https://t/a/{z}/{x}/{y}.png", "https://t/b/{z}/{x}/{y}.png",
                             "https://t/c/{z}/{x}/{y}.png"]

    private func png() throws -> Data {
        let rep = try XCTUnwrap(NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: 256, pixelsHigh: 256, bitsPerSample: 8,
            samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0))
        return try XCTUnwrap(rep.representation(using: .png, properties: [:]))
    }

    func testATileIsFetchedOnceAndThenDrawnFromMemory() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        var loaded = 0
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: false) { loaded += 1 }
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true) { loaded += 1 }
        XCTAssertEqual(fake.requests.count, 1)
        XCTAssertNil(store.image(frame: 0, z: 8, x: 71, y: 103))
        fake.answerAll(with: try png())
        XCTAssertEqual(loaded, 2)
        let image = try XCTUnwrap(store.image(frame: 0, z: 8, x: 71, y: 103))
        XCTAssertEqual(image.width, 256)
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true) { loaded += 1 }
        XCTAssertEqual(fake.requests.count, 1, "a tile in memory is not fetched again")
        XCTAssertEqual(loaded, 2)
    }

    func testTheShownFrameDownloadsAheadOfOtherFrames() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        // Fill every download slot with other frames' tiles, then ask for the shown one.
        for x in 0..<(RadarTileStore.maxInFlight + 3) {
            store.request(frame: 1, z: 8, x: x, y: 0, urgent: false)
        }
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        XCTAssertEqual(fake.requests.count, RadarTileStore.maxInFlight, "never more than the limit at once")
        XCTAssertEqual(store.queuedCount, 4)
        fake.answerFirst(with: try png())
        XCTAssertEqual(fake.requests.last?.absoluteString, "https://t/a/8/71/103.png",
                       "the freed slot goes to the shown frame")
    }

    func testOtherFramesLoadWholeFramesInLoopOrder() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        for x in 0..<RadarTileStore.maxInFlight { store.request(frame: 0, z: 8, x: x, y: 9, urgent: true) }
        // Queued tile by tile (as the map asks), frames 2 then 1 for each tile.
        for x in 0..<2 {
            store.request(frame: 2, z: 8, x: x, y: 0, urgent: false)
            store.request(frame: 1, z: 8, x: x, y: 0, urgent: false)
        }
        fake.answerFirst(with: try png())
        fake.answerFirst(with: try png())
        XCTAssertEqual(fake.requests.suffix(2).map(\.absoluteString),
                       ["https://t/b/8/0/0.png", "https://t/b/8/1/0.png"], "all of frame 1 before frame 2")
    }

    func testAFrameIsReadyOnlyWhenItsRequestedTilesAreIn() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        XCTAssertFalse(store.isReady(frame: 0), "nothing asked for yet")
        store.noteRequested(z: 8, x: 71, y: 103)
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        store.queueOtherFrames(than: 0, z: 8, x: 71, y: 103)
        XCTAssertFalse(store.isReady(frame: 0))
        fake.answerAll(with: try png())
        XCTAssertTrue(store.isReady(frame: 0))
        XCTAssertTrue(store.isReady(frame: 1), "other frames were queued behind it")
        XCTAssertTrue(store.isReady(frame: 2))
        XCTAssertEqual(fake.requests.count, 3)
    }

    func testDroppedDecodedTilesComeBackWithoutADownload() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        store.noteRequested(z: 8, x: 71, y: 103)
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        fake.answerAll(with: try png())
        store.purgeDecoded()
        XCTAssertTrue(store.isReady(frame: 0), "the kept PNG still counts")
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        XCTAssertEqual(fake.requests.count, 1, "no second download")
        XCTAssertEqual(try XCTUnwrap(store.image(frame: 0, z: 8, x: 71, y: 103)).width, 256)
    }

    func testReadinessCountsOnlyTheZoomLevelLastDrawn() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        store.noteRequested(z: 7, x: 35, y: 51)           // an earlier zoom, never loaded
        store.noteRequested(z: 8, x: 71, y: 103)
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        fake.answerFirst(with: try png())
        XCTAssertTrue(store.isReady(frame: 0))
        store.noteRequested(z: 7, x: 35, y: 51)           // zoomed back out: z7 now matters
        XCTAssertFalse(store.isReady(frame: 0))
        XCTAssertEqual(store.takeStats().zooms, [7, 8])
    }

    func testAFailedTileDoesNotStallTheLoop() {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        store.noteRequested(z: 8, x: 71, y: 103)
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: false)
        fake.answerAll(with: nil)
        XCTAssertTrue(store.isReady(frame: 0))
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: false)
        XCTAssertEqual(fake.requests.count, 1, "background does not retry a failed tile")
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        XCTAssertEqual(fake.requests.count, 2, "the shown frame does")
    }

    func testStatsCountLookupsHitsAndFetchesThenReset() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        store.request(frame: 0, z: 8, x: 1, y: 1, urgent: true)
        store.request(frame: 1, z: 8, x: 1, y: 1, urgent: true)
        fake.answerFirst(with: try png())
        fake.answerFirst(with: nil)
        _ = store.image(frame: 0, z: 8, x: 1, y: 1)
        _ = store.image(frame: 1, z: 8, x: 1, y: 1)
        let s = store.takeStats()
        XCTAssertEqual(s.requests, 2)
        XCTAssertEqual(s.hits, 1)
        XCTAssertEqual(s.fetches, 2)
        XCTAssertEqual(s.failures, 1)
        XCTAssertEqual(store.takeStats(), RadarTileStore.Stats())
    }

    func testRecentRequestsAreBounded() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        for x in 0..<(RadarTileStore.recentLimit + 5) { store.noteRequested(z: 8, x: x, y: 0) }
        // Only the newest `recentLimit` tiles decide readiness: load just those.
        for x in 5..<(RadarTileStore.recentLimit + 5) { store.request(frame: 0, z: 8, x: x, y: 0, urgent: true) }
        while !fake.pending.isEmpty { fake.answerAll(with: try png()) }
        XCTAssertTrue(store.isReady(frame: 0))
    }

    // MARK: drawing maths

    func testDrawZoomFollowsTheMapAndStopsAtTheLastNativeLevel() {
        XCTAssertEqual(RadarTileMath.tileZoom(zoomScale: pow(2, -13), maxNativeZoom: 8), 7)
        XCTAssertEqual(RadarTileMath.tileZoom(zoomScale: pow(2, -12), maxNativeZoom: 8), 8)
        XCTAssertEqual(RadarTileMath.tileZoom(zoomScale: pow(2, -9), maxNativeZoom: 8), 8)
        XCTAssertEqual(RadarTileMath.tileZoom(zoomScale: pow(2, -9), maxNativeZoom: 7), 7)
    }

    func testTileRectanglesAndCoverage() {
        let size = RadarTileMath.worldMapPoints / 256
        XCTAssertEqual(RadarTileMath.mapRect(z: 8, x: 71, y: 103),
                       CGRect(x: 71 * size, y: 103 * size, width: size, height: size))
        let inside = CGRect(x: 71.5 * size, y: 103.5 * size, width: size, height: size / 4)
        let tiles = RadarTileMath.tiles(covering: inside, z: 8)
        XCTAssertEqual(tiles.map { "\($0.x)/\($0.y)" }, ["71/103", "72/103"])
        XCTAssertEqual(RadarTileMath.tiles(covering: CGRect(x: -10, y: -10, width: 5, height: 5), z: 1).count, 1)
    }

    func testVoiceZoomHalvesDoublesAndResets() throws {
        let center = CLLocationCoordinate2D(latitude: 32.66, longitude: -79.93)
        let start = MKCoordinateRegion(center: center, span: MKCoordinateSpan(latitudeDelta: 2, longitudeDelta: 2.4))
        let opening = MKCoordinateRegion(center: center, span: MKCoordinateSpan(latitudeDelta: 1.8, longitudeDelta: 2.1))
        let closer = try XCTUnwrap(WeatherMapZoom.region(start, action: "map_zoom_in", opening: opening))
        XCTAssertEqual(closer.span.latitudeDelta, 1, accuracy: 1e-9)
        XCTAssertEqual(closer.span.longitudeDelta, 1.2, accuracy: 1e-9)
        let wider = try XCTUnwrap(WeatherMapZoom.region(start, action: "map_zoom_out", opening: opening))
        XCTAssertEqual(wider.span.latitudeDelta, 4, accuracy: 1e-9)
        let huge = MKCoordinateRegion(center: center, span: MKCoordinateSpan(latitudeDelta: 120, longitudeDelta: 300))
        XCTAssertEqual(try XCTUnwrap(WeatherMapZoom.region(huge, action: "map_zoom_out", opening: opening)).span.latitudeDelta, 170)
        let reset = try XCTUnwrap(WeatherMapZoom.region(closer, action: "map_reset", opening: opening))
        XCTAssertEqual(reset.span.latitudeDelta, 1.8, accuracy: 1e-9)
        XCTAssertNil(WeatherMapZoom.region(start, action: "radar_pause", opening: opening))
    }

    @MainActor
    func testUnknownMapActionsAreIgnored() {
        let channel = WeatherMapCommands()
        channel.send("map_spin")
        XCTAssertEqual(channel.serial, 0)
        XCTAssertNil(channel.latest)
    }

    func testOnlyTilesOnScreenCount() {
        let size = RadarTileMath.worldMapPoints / 256
        let visible = RadarTileMath.expanded(CGRect(x: 71.2 * size, y: 103.2 * size, width: 0.5 * size, height: 0.5 * size), by: 0.15)
        XCTAssertTrue(RadarTileMath.isOnScreen(z: 8, x: 71, y: 103, visible: visible))
        XCTAssertFalse(RadarTileMath.isOnScreen(z: 8, x: 75, y: 103, visible: visible))
        XCTAssertFalse(RadarTileMath.isOnScreen(z: 8, x: 71, y: 110, visible: visible))
        XCTAssertTrue(RadarTileMath.isOnScreen(z: 8, x: 75, y: 103, visible: nil), "before the map reports a view, everything counts")
        XCTAssertEqual(RadarTileMath.expanded(CGRect(x: 10, y: 10, width: 100, height: 50), by: 0.1),
                       CGRect(x: 0, y: 5, width: 120, height: 60))
    }

    func testANewViewStartsReadinessAgain() throws {
        let fake = FakeFetch(); let store = RadarTileStore(templates: templates, fetch: fake.fetch)
        store.noteRequested(z: 8, x: 71, y: 103)
        store.request(frame: 0, z: 8, x: 71, y: 103, urgent: true)
        fake.answerAll(with: try png())
        XCTAssertTrue(store.isReady(frame: 0))
        XCTAssertEqual(store.recentCount, 1)
        store.clearRecent()
        XCTAssertEqual(store.recentCount, 0)
        XCTAssertFalse(store.isReady(frame: 0), "not ready until the new view's tiles are asked for")
    }

    func testOpeningViewIsNearTheRadarsOwnResolution() {
        XCTAssertEqual(RadarMapView.openingSpanMeters, 200_000)
    }
}
