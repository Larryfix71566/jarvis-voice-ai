import Foundation

/// Widths are logical points. Account for workspace padding before deciding
/// whether the left voice rail or a docked drawer leaves a readable result.
@MainActor
enum AdaptiveLayoutMetrics {
    static let resultContentWidth = 480.0
    static let workspacePadding = 16.0
    static let voiceRailWidth = 260.0
    /// Interface cleanup Phase 1: the rail's orb slot height. The orb's glass
    /// diameter is 0.51 of the smaller slot side (CometOrbRenderer), so
    /// 260 x 220 gives about 112 pt.
    static let railOrbSlotHeight = 220.0
    /// Interface cleanup Phase 3: the centred at-rest orb slot (square).
    static let restOrbSlotMax = 440.0
    static let restOrbSlotMin = 160.0
    /// Height kept for the status line (up to three lines), its button and mute.
    static let restControlsReserve = 150.0
    static func restOrbSlotSide(stageWidth: Double, stageHeight: Double) -> Double {
        let fit = min(stageWidth - 2 * workspacePadding, stageHeight - restControlsReserve)
        return min(restOrbSlotMax, max(restOrbSlotMin, fit))
    }
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
