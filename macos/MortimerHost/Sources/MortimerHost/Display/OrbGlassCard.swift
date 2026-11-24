import SwiftUI
import JarvisKit
import Observation

/// Constants for the result card's orb glass (Option B, plasma-lit crystal).
/// Colours come from CrystalGlassRig; the rest are the approved mockup's
/// values (carousel-glass-2026-11-19). Change them only with Larry's approval.
enum OrbGlassCardStyle {
    static let cornerRadius: CGFloat = 12
    static let tintOpacity = 0.44
    static let unlitContentOpacity = 0.7
    static let hairlineOpacity = 0.14
    static let rimWidth: CGFloat = 1.2
    static let wallInset: CGFloat = 5
    static let wallCornerRadius: CGFloat = 8
    static let wallLineOpacity = 0.38
    static let wallHighlightOpacity = 0.11
    static let plasmaOpacity = 0.50
    static let plasmaEdgeOpacity = 0.55
    static let rimEndOpacity = 0.7
    static let sweepDelay = 0.22
    static let sweepDuration = 0.7

    static func rgb(_ value: (Double, Double, Double)) -> Color {
        Color(red: value.0 / 255, green: value.1 / 255, blue: value.2 / 255)
    }
    static var ink: Color { rgb(CrystalGlassRig.inkRGB) }
    static var sky: Color { rgb(CrystalGlassRig.skyRGB) }
    static var cool: Color { rgb(CrystalGlassRig.dispersionCoolRGB) }
    static var warm: Color { rgb(CrystalGlassRig.dispersionWarmRGB) }
    static var tint: Color { ink.opacity(tintOpacity) }
}

/// The follow glow's on/off setting. Off unless turned on: on Larry's Mac
/// (2026-11-24, next `e655fbe`) the tracking glow measured p50/p95 3.92/12.90 ms
/// against today's card at 0.90/0.99 ms, failing the 10% frame-time gate in
/// `CarouselGlassFrameTimeTests`. Turn it on with the environment variable
/// `JARVIS_CAROUSEL_FOLLOW_GLOW=1`, or `defaults write com.mortimer.host
/// JARVIS_CAROUSEL_FOLLOW_GLOW -bool true`. The static crystal glass is
/// unaffected either way, and so is the Reduce Motion even rim.
enum OrbGlassCardSettings {
    static let followGlowKey = "JARVIS_CAROUSEL_FOLLOW_GLOW"

    static var followGlowEnabled: Bool {
        if let raw = ProcessInfo.processInfo.environment[followGlowKey]?.lowercased() {
            return ["1", "true", "on", "yes"].contains(raw)
        }
        return UserDefaults.standard.bool(forKey: followGlowKey)
    }
}

/// Which surface a card gets, and whether its rim glow tracks the pointer.
struct OrbGlassCardPolicy {
    enum Treatment: Equatable { case litCrystal, unlitCrystal, opaque }
    enum GlowMode: Equatable { case tracking, staticEven, off }

    static func treatment(lit: Bool, glassEnabled: Bool, reduceTransparency: Bool,
                          increasedContrast: Bool) -> Treatment {
        if MortimerGlassAccessibilityPolicy.usesOpaqueSurface(
            glassEnabled: glassEnabled, reduceTransparency: reduceTransparency,
            increasedContrast: increasedContrast) { return .opaque }
        return lit ? .litCrystal : .unlitCrystal
    }

    /// `followGlow` false turns tracking off; the Reduce Motion even rim
    /// (static, no per-frame work) is kept.
    static func glow(lit: Bool, glassEnabled: Bool, reduceTransparency: Bool,
                     increasedContrast: Bool, reduceMotion: Bool, suppressed: Bool,
                     followGlow: Bool) -> GlowMode {
        guard treatment(lit: lit, glassEnabled: glassEnabled, reduceTransparency: reduceTransparency,
                        increasedContrast: increasedContrast) == .litCrystal, !suppressed else { return .off }
        if reduceMotion { return .staticEven }
        return followGlow ? .tracking : .off
    }
}

/// Pure geometry and strengths of the follow glow.
enum RimGlow {
    /// Rim peak at the focus, mid at 55% of the radius, floor beyond it.
    static let rimStops: [(opacity: Double, location: Double)] = [(1, 0), (0.34, 0.55), (0.12, 1)]
    static let rimRadius: CGFloat = 210
    static let rimWidth: CGFloat = 1.6
    static let bandOpacity = 0.36
    static let bandRadius: CGFloat = 150
    static let bandWidth: CGFloat = 10
    static let bandBlur: CGFloat = 3
    static let fade = 0.18
    /// Reduce Motion: even rim at half strength, no tracking, no fade.
    static let reducedStrength = 0.5
    static let reducedRimOpacity = 0.95
    static let reducedBandOpacity = 0.42

    /// Nearest point on the card's edge to `pointer`, as a unit point. The
    /// point is kept off the corner arcs. Nil when the pointer is outside.
    static func focus(pointer: CGPoint, in size: CGSize,
                      cornerRadius: CGFloat = OrbGlassCardStyle.cornerRadius) -> UnitPoint? {
        guard size.width > 0, size.height > 0,
              pointer.x >= 0, pointer.x <= size.width,
              pointer.y >= 0, pointer.y <= size.height else { return nil }
        let r = min(cornerRadius, size.width / 2, size.height / 2)
        let top = pointer.y, bottom = size.height - pointer.y
        let left = pointer.x, right = size.width - pointer.x
        let nearest = min(top, bottom, left, right)
        let x = min(max(pointer.x, r), size.width - r)
        let y = min(max(pointer.y, r), size.height - r)
        let point: CGPoint
        if top == nearest { point = CGPoint(x: x, y: 0) }
        else if bottom == nearest { point = CGPoint(x: x, y: size.height) }
        else if left == nearest { point = CGPoint(x: 0, y: y) }
        else { point = CGPoint(x: size.width, y: y) }
        return UnitPoint(x: point.x / size.width, y: point.y / size.height)
    }
}

/// Pointer state for the glow. Only the glow overlay reads it, so a pointer
/// move re-renders that overlay and not the card's content.
@MainActor @Observable
final class RimGlowPointer {
    var hovering = false
    /// Last known position; kept after exit so the fade-out stays put.
    var location = CGPoint.zero

    func update(_ point: CGPoint?) {
        if let point { location = point; hovering = true } else { hovering = false }
    }
}

extension View {
    /// The orb's glass on a result card. `lit` is the live front card.
    /// `glowDriver` lets tests move the simulated pointer without events.
    /// `followGlow` nil reads `OrbGlassCardSettings.followGlowEnabled`.
    func orbGlassCard(lit: Bool, glowColor: Color, glowSuppressed: Bool = false,
                      glowDriver: RimGlowPointer? = nil, followGlow: Bool? = nil) -> some View {
        modifier(OrbGlassCardModifier(lit: lit, glowColor: glowColor,
                                      glowSuppressed: glowSuppressed, glowDriver: glowDriver,
                                      followGlow: followGlow ?? OrbGlassCardSettings.followGlowEnabled))
    }
}

private struct OrbGlassCardModifier: ViewModifier {
    let lit: Bool
    let glowColor: Color
    let glowSuppressed: Bool
    let glowDriver: RimGlowPointer?
    let followGlow: Bool
    @State private var ownPointer = RimGlowPointer()
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.mortimerReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: OrbGlassCardStyle.cornerRadius)
        let increased = contrast == .increased
        let treatment = OrbGlassCardPolicy.treatment(
            lit: lit, glassEnabled: JarvisFlags.glassEnabled,
            reduceTransparency: reduceTransparency, increasedContrast: increased)
        let mode = OrbGlassCardPolicy.glow(
            lit: lit, glassEnabled: JarvisFlags.glassEnabled, reduceTransparency: reduceTransparency,
            increasedContrast: increased, reduceMotion: reduceMotion, suppressed: glowSuppressed,
            followGlow: followGlow)
        let pointer = glowDriver ?? ownPointer
        switch treatment {
        case .opaque:
            content
                .background(AppTheme.panelSolid, in: shape)
                .overlay(shape.strokeBorder(increased ? AppTheme.highContrastBorder : AppTheme.hairline,
                                            lineWidth: increased ? 1.5 : 1))
        case .unlitCrystal:
            content
                .opacity(OrbGlassCardStyle.unlitContentOpacity)
                .background(OrbGlassCardStyle.tint, in: shape)
                .glassEffect(.regular, in: .rect(cornerRadius: OrbGlassCardStyle.cornerRadius))
                .overlay(OrbGlassLayers(lit: false, glowColor: glowColor).allowsHitTesting(false))
        case .litCrystal:
            content
                .background(OrbGlassCardStyle.tint, in: shape)
                .glassEffect(.regular, in: .rect(cornerRadius: OrbGlassCardStyle.cornerRadius))
                .overlay(OrbGlassLayers(lit: true, glowColor: glowColor).allowsHitTesting(false))
                .overlay(SpecularSweep(reduceMotion: reduceMotion).allowsHitTesting(false))
                .overlay(RimGlowOverlay(pointer: pointer, color: glowColor, mode: mode)
                    .allowsHitTesting(false))
                .onContinuousHover(coordinateSpace: .local) { phase in
                    // With the glow off nothing reads the pointer; skip the writes.
                    guard mode != .off else { return }
                    switch phase {
                    case .active(let point): pointer.update(point)
                    case .ended: pointer.update(nil)
                    }
                }
        }
    }
}

/// Static layers of the orb rig on a flat slab. Nothing here redraws unless
/// the card's size or colour changes.
private struct OrbGlassLayers: View {
    let lit: Bool
    let glowColor: Color

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: OrbGlassCardStyle.cornerRadius)
        let sky = OrbGlassCardStyle.sky
        let ink = OrbGlassCardStyle.ink
        ZStack {
            // Absorption: the body darkens toward the edge.
            shape.strokeBorder(ink.opacity(0.46), lineWidth: 18)
                .blur(radius: 14).clipShape(shape)
            if lit {
                // Room reflection: Fresnel line and sky wash from above and the left.
                shape.strokeBorder(
                    LinearGradient(stops: [.init(color: sky.opacity(0.30), location: 0),
                                           .init(color: .clear, location: 0.12)],
                                   startPoint: .top, endPoint: .bottom), lineWidth: 1)
                LinearGradient(stops: [.init(color: sky.opacity(0.22), location: 0),
                                       .init(color: .clear, location: 0.10)],
                               startPoint: .top, endPoint: .bottom).clipShape(shape)
                LinearGradient(stops: [.init(color: sky.opacity(0.10), location: 0),
                                       .init(color: .clear, location: 0.07)],
                               startPoint: .leading, endPoint: .trailing).clipShape(shape)
                // Two-pane window sheen in the upper left.
                LinearGradient(stops: [
                    .init(color: Color.white.opacity(0.085), location: 0),
                    .init(color: Color.white.opacity(0.085), location: 0.11),
                    .init(color: .clear, location: 0.112),
                    .init(color: .clear, location: 0.126),
                    .init(color: Color.white.opacity(0.05), location: 0.128),
                    .init(color: Color.white.opacity(0.05), location: 0.22),
                    .init(color: .clear, location: 0.223),
                    .init(color: .clear, location: 1)],
                    startPoint: .topLeading, endPoint: .bottomTrailing).clipShape(shape)
                // Plasma carried in the wall, opposite the key light.
                shape.strokeBorder(
                    LinearGradient(stops: [.init(color: .clear, location: 0.45),
                                           .init(color: glowColor.opacity(OrbGlassCardStyle.plasmaOpacity), location: 1)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 22)
                    .blur(radius: 12).clipShape(shape)
                shape.strokeBorder(
                    LinearGradient(stops: [.init(color: .clear, location: 0.6),
                                           .init(color: glowColor.opacity(OrbGlassCardStyle.plasmaEdgeOpacity), location: 1)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 2)
                // Caustic: the key light focused onto the far wall.
                RadialGradient(stops: [
                    .init(color: Color.white.opacity(0.13), location: 0),
                    .init(color: sky.opacity(0.05), location: 0.55),
                    .init(color: .clear, location: 1)],
                    center: UnitPoint(x: 0.8, y: 0.84), startRadius: 0, endRadius: 70).clipShape(shape)
                // Wall line: dark inner line with a faint light line outside it.
                RoundedRectangle(cornerRadius: OrbGlassCardStyle.wallCornerRadius)
                    .strokeBorder(Color.black.opacity(OrbGlassCardStyle.wallLineOpacity), lineWidth: 1)
                    .padding(OrbGlassCardStyle.wallInset)
                RoundedRectangle(cornerRadius: OrbGlassCardStyle.wallCornerRadius + 1)
                    .strokeBorder(sky.opacity(OrbGlassCardStyle.wallHighlightOpacity), lineWidth: 0.7)
                    .padding(OrbGlassCardStyle.wallInset - 1)
                // Dispersion hairlines at the lit corner.
                shape.strokeBorder(
                    LinearGradient(stops: [.init(color: OrbGlassCardStyle.cool.opacity(0.75), location: 0),
                                           .init(color: .clear, location: 0.36)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1.4)
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(
                        LinearGradient(stops: [.init(color: OrbGlassCardStyle.warm.opacity(0.55), location: 0),
                                               .init(color: .clear, location: 0.34)],
                                       startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1.4)
                    .padding(2)
                // Key-light rim: bright upper left, plasma colour lower right.
                shape.strokeBorder(
                    LinearGradient(stops: [
                        .init(color: Color.white.opacity(0.55), location: 0),
                        .init(color: Color.white.opacity(0.22), location: 0.20),
                        .init(color: Color.white.opacity(0.06), location: 0.46),
                        .init(color: Color.white.opacity(0.05), location: 0.72),
                        .init(color: glowColor.opacity(OrbGlassCardStyle.rimEndOpacity), location: 1)],
                        startPoint: .topLeading, endPoint: .bottomTrailing),
                    lineWidth: OrbGlassCardStyle.rimWidth)
            } else {
                shape.strokeBorder(Color.white.opacity(OrbGlassCardStyle.hairlineOpacity), lineWidth: 1)
            }
        }
    }
}

/// One specular sweep when a card arrives (the card is recreated per result).
private struct SpecularSweep: View {
    let reduceMotion: Bool
    @State private var progress: CGFloat = -0.7

    var body: some View {
        GeometryReader { proxy in
            LinearGradient(stops: [
                .init(color: .clear, location: 0.38),
                .init(color: Color.white.opacity(0.20), location: 0.49),
                .init(color: OrbGlassCardStyle.sky.opacity(0.06), location: 0.56),
                .init(color: .clear, location: 0.62)],
                startPoint: .topLeading, endPoint: .bottomTrailing)
                .offset(x: progress * proxy.size.width)
        }
        .clipShape(RoundedRectangle(cornerRadius: OrbGlassCardStyle.cornerRadius))
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.timingCurve(0.3, 0.1, 0.3, 1, duration: OrbGlassCardStyle.sweepDuration)
                .delay(OrbGlassCardStyle.sweepDelay)) { progress = 0.7 }
        }
    }
}

/// The follow glow. Owns the only view that reads the pointer.
private struct RimGlowOverlay: View {
    let pointer: RimGlowPointer
    let color: Color
    let mode: OrbGlassCardPolicy.GlowMode

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: OrbGlassCardStyle.cornerRadius)
        let on = pointer.hovering && mode != .off
        GeometryReader { proxy in
            switch mode {
            case .tracking:
                let focus = RimGlow.focus(pointer: pointer.location, in: proxy.size)
                    ?? RimGlow.focus(pointer: CGPoint(x: min(max(pointer.location.x, 0), proxy.size.width),
                                                      y: min(max(pointer.location.y, 0), proxy.size.height)),
                                     in: proxy.size) ?? .top
                ZStack {
                    shape.strokeBorder(
                        RadialGradient(colors: [color.opacity(RimGlow.bandOpacity), .clear],
                                       center: focus, startRadius: 0, endRadius: RimGlow.bandRadius),
                        lineWidth: RimGlow.bandWidth)
                        .blur(radius: RimGlow.bandBlur).clipShape(shape)
                    shape.strokeBorder(
                        RadialGradient(gradient: Gradient(stops: RimGlow.rimStops.map {
                            Gradient.Stop(color: color.opacity($0.opacity), location: $0.location)
                        }), center: focus, startRadius: 0, endRadius: RimGlow.rimRadius),
                        lineWidth: RimGlow.rimWidth)
                }
            case .staticEven:
                ZStack {
                    shape.strokeBorder(color.opacity(RimGlow.reducedBandOpacity), lineWidth: RimGlow.bandWidth)
                        .blur(radius: RimGlow.bandBlur).clipShape(shape)
                    shape.strokeBorder(color.opacity(RimGlow.reducedRimOpacity), lineWidth: RimGlow.rimWidth)
                }
                .opacity(RimGlow.reducedStrength)
            case .off:
                Color.clear
            }
        }
        .opacity(on ? 1 : 0)
        .animation(mode == .tracking ? .easeInOut(duration: RimGlow.fade) : nil, value: on)
    }
}
