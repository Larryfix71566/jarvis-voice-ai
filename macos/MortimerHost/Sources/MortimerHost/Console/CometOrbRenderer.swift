import MortimerOrbRendering
import SwiftUI

/// Keep the Mac call sites on their existing voice activity and theme types.
enum CometOrbRenderer {
    private static let palette = OrbPalette(
        approval: AppTheme.approval, panel: AppTheme.panel, text: AppTheme.text,
        user: AppTheme.user, textDim: AppTheme.textDim, mortimer: AppTheme.mortimer
    )

    static func draw(context: inout GraphicsContext, size: CGSize,
                     stageCenterX: CGFloat?, phase: Double, userEnergy: Double,
                     outputEnergy: Double, activity: VoicePresentationState.Activity,
                     pointer: CGPoint? = nil, ripple: Double = 0,
                     needsYou: Bool = false, reduceMotion: Bool = false,
                     refraction: Bool = false, energyState: OrbEnergyState? = nil) {
        MortimerOrbRendering.CometOrbRenderer.draw(
            context: &context, size: size, stageCenterX: stageCenterX, phase: phase,
            userEnergy: userEnergy, outputEnergy: outputEnergy, activity: activity.orbActivity,
            pointer: pointer, ripple: ripple, needsYou: needsYou, reduceMotion: reduceMotion,
            refraction: refraction, energyState: energyState?.renderState, palette: palette
        )
    }

    static func stateColor(_ activity: VoicePresentationState.Activity) -> Color {
        MortimerOrbRendering.CometOrbRenderer.stateColor(activity.orbActivity)
    }

    static func drawCrystalReflections(into context: inout GraphicsContext,
                                       center: CGPoint, radius: Double) {
        MortimerOrbRendering.CometOrbRenderer.drawCrystalReflections(
            into: &context, center: center, radius: radius
        )
    }
}

final class OrbEnergyState {
    fileprivate let renderState = MortimerOrbRendering.OrbEnergyState(initialColor: AppTheme.listening)
    static let reducedMotionInterval = MortimerOrbRendering.OrbEnergyState.reducedMotionInterval

    var depths: [Double] { renderState.depths }

    func advance(activity: VoicePresentationState.Activity, measuredLevel: Double,
                 phase: Double, now: Double, dt: Double, reducedMotion: Bool = false) {
        renderState.advance(activity: activity.orbActivity, measuredLevel: measuredLevel,
                            phase: phase, now: now, dt: dt, reducedMotion: reducedMotion)
    }
}

typealias OrbFlashCap = MortimerOrbRendering.OrbFlashCap

private extension VoicePresentationState.Activity {
    var orbActivity: OrbActivity {
        switch self {
        case .offline: return .offline
        case .connecting: return .connecting
        case .listening: return .listening
        case .user: return .user
        case .assistant: return .assistant
        case .thinking: return .thinking
        case .muted: return .muted
        }
    }
}
