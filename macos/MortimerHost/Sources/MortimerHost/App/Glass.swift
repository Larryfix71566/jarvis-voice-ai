import SwiftUI
import JarvisKit

/// APP plan §3 P10 — the visual treatment is ONE layer on a fixed view
/// structure. Every glass surface calls `.mortimerGlass(_:)`; no view
/// applies a material or colour directly. Two arms selected by
/// JarvisFlags.glassEnabled (CORE §3 N16, default true):
///   glass-on  — the T1.0-signed treatment: `.glassEffect()` over the
///               transparent window (spike S1 PASS, signed LEF 08/30/26).
///   glass-off — opaque AppTheme.panelOpaque fill (§9 rollback,
///               `defaults write <bundle-id> JARVIS_GLASS_ENABLED -bool false`).
enum GlassRole {
    case panel, drawer, display, chip, card

    var cornerRadius: CGFloat {
        switch self {
        case .panel, .drawer, .display: return 16
        case .card: return 12
        case .chip: return 8
        }
    }

    /// The `-heavy` CSS variant exists for dense scrolling text (drawer,
    /// cards) — the HIG post-blur contrast rule. Mirrored here as the
    /// tint used behind text-dense roles.
    var isHeavy: Bool {
        switch self {
        case .drawer, .card: return true
        case .panel, .display, .chip: return false
        }
    }
}

private struct MortimerGlass: ViewModifier {
    let role: GlassRole
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: role.cornerRadius)
        let increasedContrast = colorSchemeContrast == .increased
        let accessibleOpaque = MortimerGlassAccessibilityPolicy.usesOpaqueSurface(
            glassEnabled: JarvisFlags.glassEnabled,
            reduceTransparency: reduceTransparency,
            increasedContrast: increasedContrast
        )
        if JarvisFlags.glassEnabled && !accessibleOpaque {
            // T1.0: the signed material — .glassEffect(.regular) over the
            // transparent window, with the heavy roles carrying an extra
            // tint layer for dense-text contrast (the CSS -heavy trade:
            // more diffusion buys less opacity).
            content
                .background(role.isHeavy ? AppTheme.glassBgHeavy : Color.clear)
                .glassEffect(.regular, in: .rect(cornerRadius: role.cornerRadius))
                .overlay(shape.strokeBorder(AppTheme.glassBorder, lineWidth: 1))
        } else {
            // Respect system accessibility overrides while leaving the
            // explicit glass-off rollback appearance unchanged.
            let fill = reduceTransparency && JarvisFlags.glassEnabled
                ? AppTheme.panelSolid : AppTheme.panelOpaque
            content
                .background(fill, in: shape)
                .overlay(shape.strokeBorder(
                    increasedContrast ? AppTheme.highContrastBorder : AppTheme.hairline,
                    lineWidth: increasedContrast ? 1.5 : 1
                ))
        }
    }
}

enum MortimerGlassAccessibilityPolicy {
    static func usesOpaqueSurface(glassEnabled: Bool, reduceTransparency: Bool,
                                  increasedContrast: Bool) -> Bool {
        !glassEnabled || reduceTransparency || increasedContrast
    }
}

extension View {
    func mortimerGlass(_ role: GlassRole) -> some View {
        modifier(MortimerGlass(role: role))
    }
}
