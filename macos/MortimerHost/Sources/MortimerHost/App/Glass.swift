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

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: role.cornerRadius)
        if JarvisFlags.glassEnabled {
            // T1.0: the signed material — .glassEffect(.regular) over the
            // transparent window, with the heavy roles carrying an extra
            // tint layer for dense-text contrast (the CSS -heavy trade:
            // more diffusion buys less opacity).
            content
                .background(role.isHeavy ? AppTheme.glassBgHeavy : Color.clear)
                .glassEffect(.regular, in: .rect(cornerRadius: role.cornerRadius))
                .overlay(shape.strokeBorder(AppTheme.glassBorder, lineWidth: 1))
        } else {
            content
                .background(AppTheme.panelOpaque, in: shape)
                .overlay(shape.strokeBorder(AppTheme.hairline, lineWidth: 1))
        }
    }
}

extension View {
    func mortimerGlass(_ role: GlassRole) -> some View {
        modifier(MortimerGlass(role: role))
    }
}
