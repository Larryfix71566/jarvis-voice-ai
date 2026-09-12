import XCTest
@testable import MortimerHost

@MainActor
final class AdaptiveLayoutMetricsTests: XCTestCase {
    func testDrawerLeavesReadableResultsAtAllSupportedWindowSizes() {
        for window in [900.0, 1180, 1280, 1440, 2560] {
            for requested in [300.0, 400, 540, 720] {
                let width = AdaptiveLayoutMetrics.drawerWidth(requested, windowWidth: window)
                let resultWidth = window - width - AppTuning.drawerHandleWidth - 2 * AdaptiveLayoutMetrics.workspacePadding
                XCTAssertGreaterThanOrEqual(resultWidth, 480)
                XCTAssertGreaterThanOrEqual(width, AppTuning.drawerMinWidth)
                XCTAssertLessThanOrEqual(width, AppTuning.drawerMaxWidthCap)
            }
        }
    }

    func testTemporaryConstraintDoesNotChangeSavedWidth() {
        let drawer = DrawerState()
        let original = drawer.width
        defer { drawer.width = original }
        drawer.width = 720
        let compact = AdaptiveLayoutMetrics.drawerWidth(drawer.width, windowWidth: 900)
        XCTAssertEqual(compact, 378)
        XCTAssertEqual(drawer.width, 720)
        XCTAssertEqual(AdaptiveLayoutMetrics.drawerWidth(drawer.width, windowWidth: 1440), 720)
    }

    func testComparisonThresholdPreservesBothReadablePanes() {
        let usable = AdaptiveLayoutMetrics.minimumComparisonWidth
            - 2 * AdaptiveLayoutMetrics.comparisonSpacing - AdaptiveLayoutMetrics.dividerWidth
        XCTAssertEqual(usable / 2, 480)
    }

    func testRailThresholdIncludesResultPaddingAndDivider() {
        let content = AdaptiveLayoutMetrics.minimumRailStageWidth - AdaptiveLayoutMetrics.voiceRailWidth
            - AdaptiveLayoutMetrics.dividerWidth - 2 * AdaptiveLayoutMetrics.workspacePadding
        XCTAssertEqual(content, 480)
    }
}
