import XCTest
import AppKit
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
