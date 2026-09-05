import XCTest
import JarvisKit
@testable import MortimerHost

/// 2026-09-05 — the pure halves of the "graph window sizable without
/// limitation" fixes: graph-image URL sizing, panel fit-to-viewport, and
/// ScreenPlacement's user-adjusted rule. Everything here runs without a
/// window; the gesture/coordinate-space halves are the manual §8 check.
final class GraphImageURLTests: XCTestCase {
    private let graphURL = URL(string: "http://127.0.0.1:7861/api/graph/memory/image.png?focus=prefix%3Auser.style&depth=1&edge_types=child_of%2Cbecame")!

    func testIsGraphImageMatchesOnlyTheSidecarImageEndpoints() {
        XCTAssertTrue(GraphImageURL.isGraphImage(graphURL))
        XCTAssertTrue(GraphImageURL.isGraphImage(URL(string: "http://127.0.0.1:7861/api/graph/deliberation/image.svg?focus=round%3Aabc")!))
        // The JSON twin, a radar tile, and a basemap all keep the plain fetch.
        XCTAssertFalse(GraphImageURL.isGraphImage(URL(string: "http://127.0.0.1:7861/api/graph/memory?focus=x")!))
        XCTAssertFalse(GraphImageURL.isGraphImage(URL(string: "https://tilecache.rainviewer.com/v2/radar/1/256/6/17/25/2/1_1.png")!))
        XCTAssertFalse(GraphImageURL.isGraphImage(URL(string: "https://tiles.openfreemap.org/6/17/25.png")!))
    }

    func testRequestSizeIsViewportTimesScaleMinusReserve() {
        let size = GraphImageURL.requestSize(viewport: CGSize(width: 800, height: 600), scale: 2)
        XCTAssertEqual(size?.w, 1600)
        XCTAssertEqual(size?.h, 1120)   // (600 - 40 reserve) × 2
    }

    func testRequestSizeClampsToTheSidecarRange() {
        // Below GRAPH_IMAGE_MIN_PX rounds UP to it; above MAX rounds down.
        let small = GraphImageURL.requestSize(viewport: CGSize(width: 100, height: 100), scale: 1)
        XCTAssertEqual(small?.w, AppTuning.graphImageMinPx)
        XCTAssertEqual(small?.h, AppTuning.graphImageMinPx)
        let huge = GraphImageURL.requestSize(viewport: CGSize(width: 4000, height: 3000), scale: 2)
        XCTAssertEqual(huge?.w, AppTuning.graphImageMaxPx)
        XCTAssertEqual(huge?.h, AppTuning.graphImageMaxPx)
    }

    func testRequestSizeIsNilUntilMeasured() {
        XCTAssertNil(GraphImageURL.requestSize(viewport: .zero, scale: 2))
        XCTAssertNil(GraphImageURL.requestSize(viewport: CGSize(width: 500, height: 0), scale: 2))
        XCTAssertNil(GraphImageURL.requestSize(viewport: CGSize(width: 500, height: 400), scale: 0))
    }

    func testSizedAppendsWAndHAndKeepsEveryOtherQueryItem() throws {
        let sized = GraphImageURL.sized(graphURL, w: 1600, h: 1120)
        let items = try XCTUnwrap(URLComponents(url: sized, resolvingAgainstBaseURL: false)?.queryItems)
        XCTAssertEqual(items.first { $0.name == "w" }?.value, "1600")
        XCTAssertEqual(items.first { $0.name == "h" }?.value, "1120")
        XCTAssertEqual(items.first { $0.name == "focus" }?.value, "prefix:user.style")
        XCTAssertEqual(items.first { $0.name == "depth" }?.value, "1")
        XCTAssertEqual(items.first { $0.name == "edge_types" }?.value, "child_of,became")
        XCTAssertEqual(sized.path, "/api/graph/memory/image.png")
    }

    func testSizedReplacesRatherThanDuplicates() throws {
        let once = GraphImageURL.sized(graphURL, w: 800, h: 600)
        let twice = GraphImageURL.sized(once, w: 1600, h: 1120)
        let items = try XCTUnwrap(URLComponents(url: twice, resolvingAgainstBaseURL: false)?.queryItems)
        XCTAssertEqual(items.filter { $0.name == "w" }.count, 1)
        XCTAssertEqual(items.filter { $0.name == "h" }.count, 1)
        XCTAssertEqual(items.first { $0.name == "w" }?.value, "1600")
    }
}

@MainActor
final class DisplayWindowStoreFitTests: XCTestCase {
    private func payload() throws -> DisplayPayload {
        let json = #"{"kind":"image","title":"Memory graph — prefix:user.style","surface":"window","tool":"memory_graph_view","images":["http://127.0.0.1:7861/api/graph/memory/image.png?focus=prefix%3Auser.style&depth=1"]}"#
        return try JSONDecoder().decode(DisplayPayload.self, from: Data(json.utf8))
    }

    func testFittedSizeIsViewportMinusInsetOnEverySide() {
        let inset = CGFloat(AppTuning.displayPanelInset)
        let size = DisplayWindowStore.fittedSize(viewport: CGSize(width: 900, height: 700))
        XCTAssertEqual(size, CGSize(width: 900 - inset * 2, height: 700 - inset * 2))
    }

    func testFittedSizeIsNilWhenUnmeasuredOrTooSmall() {
        XCTAssertNil(DisplayWindowStore.fittedSize(viewport: .zero))
        XCTAssertNil(DisplayWindowStore.fittedSize(viewport: CGSize(width: 300, height: 200)))
    }

    func testFitFillsTheViewportAndDropsTheCascadeOffset() throws {
        let store = DisplayWindowStore()
        store.apply(try payload())
        store.apply(try payload())   // second panel carries a cascade offset
        let second = try XCTUnwrap(store.panels.last)
        XCTAssertNotEqual(second.offset, .zero)

        store.viewportSize = CGSize(width: 1200, height: 900)
        store.fit(id: second.id)

        let fitted = try XCTUnwrap(store.panels.last)
        let inset = CGFloat(AppTuning.displayPanelInset)
        XCTAssertEqual(fitted.offset, .zero)
        XCTAssertEqual(fitted.size, CGSize(width: 1200 - inset * 2, height: 900 - inset * 2))
    }

    func testFitIsANoOpUntilTheViewportIsMeasured() throws {
        let store = DisplayWindowStore()
        store.apply(try payload())
        let before = try XCTUnwrap(store.panels.first)
        store.fit(id: before.id)
        XCTAssertEqual(store.panels.first, before)
    }

    func testResizeHasAMinimumButNoMaximum() throws {
        let store = DisplayWindowStore()
        store.apply(try payload())
        let id = try XCTUnwrap(store.panels.first?.id)
        store.resize(id: id, to: CGSize(width: 10, height: 10))
        XCTAssertEqual(store.panels.first?.size, DisplayWindowStore.minPanelSize)
        store.resize(id: id, to: CGSize(width: 5000, height: 4000))
        XCTAssertEqual(store.panels.first?.size, CGSize(width: 5000, height: 4000))
    }
}

@MainActor
final class ScreenPlacementUserAdjustedTests: XCTestCase {
    private let placed = NSRect(x: 0, y: 0, width: 1152, height: 1080)

    func testNeverPlacedIsNotUserAdjusted() {
        XCTAssertFalse(ScreenPlacement.isUserAdjusted(live: placed, placed: nil))
    }

    func testExactMatchIsNotUserAdjusted() {
        XCTAssertFalse(ScreenPlacement.isUserAdjusted(live: placed, placed: placed))
    }

    func testAPointOfAppKitRoundingIsNotUserAdjusted() {
        let rounded = NSRect(x: 0, y: 1, width: 1151, height: 1080)
        XCTAssertFalse(ScreenPlacement.isUserAdjusted(live: rounded, placed: placed))
    }

    func testAResizeIsUserAdjusted() {
        let resized = NSRect(x: 0, y: 0, width: 1500, height: 1080)
        XCTAssertTrue(ScreenPlacement.isUserAdjusted(live: resized, placed: placed))
    }

    func testAMoveIsUserAdjusted() {
        let moved = NSRect(x: 300, y: 0, width: 1152, height: 1080)
        XCTAssertTrue(ScreenPlacement.isUserAdjusted(live: moved, placed: placed))
    }
}
