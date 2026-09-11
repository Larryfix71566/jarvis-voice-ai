import Foundation

/// Widths are logical points. Account for workspace padding before deciding
/// whether the left voice rail or a docked drawer leaves a readable result.
@MainActor
enum AdaptiveLayoutMetrics {
    static let resultContentWidth = 480.0
    static let workspacePadding = 16.0
    static let voiceRailWidth = 200.0
    static let dividerWidth = 1.0
    static let comparisonSpacing = 16.0
    static var minimumComparisonWidth: Double { 2 * resultContentWidth + 2 * comparisonSpacing + dividerWidth }
    static var minimumWorkspaceWidth: Double { resultContentWidth + 2 * workspacePadding }
    static var minimumRailStageWidth: Double { minimumWorkspaceWidth + voiceRailWidth + dividerWidth }

    static func drawerWidth(_ requested: Double, windowWidth: Double) -> Double {
        let available = windowWidth - minimumWorkspaceWidth - AppTuning.drawerHandleWidth
        return min(DrawerState.clampWidth(requested, windowWidth: windowWidth),
                   max(AppTuning.drawerMinWidth, available))
    }
}
