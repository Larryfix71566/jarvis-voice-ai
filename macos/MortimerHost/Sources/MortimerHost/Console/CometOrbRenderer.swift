import SwiftUI

/// C6's glass energy orb. The crystal room rig is unchanged; the old plasma
/// and orbiting comets are replaced by deterministic, depth-projected arcs.
/// Temporal easing is owned by `OrbEnergyState`, so a 15 Hz idle redraw and a
/// 60 Hz active redraw cover the same fade in the same elapsed time.
enum CometOrbRenderer {
    private static let ice = Color(red: 0.74, green: 0.91, blue: 1)
    private static let demoRadius = 148.0

    private static func color(_ rgb: (Double, Double, Double)) -> Color {
        Color(red: rgb.0 / 255, green: rgb.1 / 255, blue: rgb.2 / 255)
    }

    private static func disc(_ center: CGPoint, _ radius: Double) -> Path {
        Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius,
                              width: radius * 2, height: radius * 2))
    }

    /// Fixed hash, independent of wall-clock randomness: no unseeded flicker.
    private static func noise(_ index: Int) -> Double {
        let n = sin(Double(index) * 127.1 + 311.7) * 43758.5453
        return n - floor(n)
    }

    static func draw(context: inout GraphicsContext, size: CGSize,
                     stageCenterX: CGFloat?, phase: Double, userEnergy: Double,
                     outputEnergy: Double, activity: VoicePresentationState.Activity,
                     pointer: CGPoint? = nil, ripple: Double = 0,
                     needsYou: Bool = false, reduceMotion: Bool = false,
                     refraction: Bool = false, energyState: OrbEnergyState? = nil) {
        let center = CGPoint(x: stageCenterX ?? size.width / 2, y: size.height / 2)
        let extent = min(size.height, 2 * min(center.x, size.width - center.x))
        guard extent > 0 else { return }
        let radius = extent * 0.255
        let measured = min(1, max(0, max(userEnergy, outputEnergy)))
        let energy = energyState?.level ?? measured
        let tint = energyState?.color ?? stateColor(activity)
        let ambient = activity == .listening || activity == .muted
        let ready = ambient || activity == .user || activity == .assistant || activity == .thinking
        let strength = ready ? 0.52 + energy * 0.48 : (activity == .offline ? 0.16 : 0.30)
        let breath = ambient && !reduceMotion ? 0.94 + 0.06 * sin(phase * 1.2) : 1
        let gain = energyState?.flash.gain ?? 1

        drawGround(context: &context, center: center, radius: radius,
                   tint: tint, brightness: energyState?.flash.cappedRatio ?? energy)
        if refraction { drawStaticRefraction(context: &context, center: center, radius: radius) }
        drawCrystalShell(context: &context, center: center, radius: radius, phase: phase,
                         userEnergy: userEnergy, outputEnergy: outputEnergy, tint: tint,
                         strength: strength, breath: breath, energy: energy, ready: ready,
                         activity: activity, pointer: pointer, ripple: ripple,
                         reduceMotion: reduceMotion, gain: gain,
                         depths: energyState?.depths)
        if needsYou {
            context.stroke(disc(center, radius * 1.12), with: .color(AppTheme.approval),
                           style: StrokeStyle(lineWidth: max(1.5, radius * 0.025)))
        }
    }

    static func stateRGB(_ activity: VoicePresentationState.Activity) -> (Double, Double, Double) {
        switch activity {
        case .listening: return (102, 115, 255)
        case .user: return (45, 212, 191)
        case .assistant, .thinking: return (224, 112, 32)
        case .muted: return (90, 100, 120)
        case .connecting: return (122, 135, 148)
        case .offline: return (46, 55, 64)
        }
    }

    static func stateColor(_ activity: VoicePresentationState.Activity) -> Color {
        color(stateRGB(activity))
    }

    /// Shader-free fallback from the approved spec: redraw the static rail,
    /// inverted and magnified, then absorb 30% toward #060A0E. It deliberately
    /// does not claim to sample live views behind the Canvas.
    private static func drawStaticRefraction(context: inout GraphicsContext,
                                             center: CGPoint, radius: Double) {
        var glass = context
        glass.clip(to: disc(center, radius))
        glass.fill(disc(center, radius), with: .color(AppTheme.panel))
        glass.translateBy(x: center.x, y: center.y)
        glass.rotate(by: .radians(.pi))
        glass.scaleBy(x: 1.67, y: 1.67)
        glass.translateBy(x: -center.x, y: -center.y)
        for index in -8...8 {
            let x = center.x + Double(index) * radius * 0.24
            var line = Path(); line.move(to: CGPoint(x: x, y: center.y - radius * 2))
            line.addLine(to: CGPoint(x: x, y: center.y + radius * 2))
            glass.stroke(line, with: .color(AppTheme.text.opacity(0.05)), lineWidth: 0.5)
        }
        glass.fill(disc(center, radius * 2), with: .color(color(CrystalGlassRig.inkRGB)
            .opacity(CrystalGlassRig.refractionAbsorption)))
    }

    private static func drawGround(context: inout GraphicsContext, center: CGPoint,
                                   radius: Double, tint: Color, brightness: Double) {
        let floor = CGPoint(x: center.x, y: center.y + radius * 1.14)
        let shadow = CGRect(x: floor.x - radius * 0.525, y: floor.y - radius * 0.105,
                            width: radius * 1.05, height: radius * 0.21)
        context.fill(Path(ellipseIn: shadow), with: .radialGradient(
            Gradient(stops: [.init(color: .black.opacity(0.62), location: 0),
                             .init(color: .black.opacity(0.34), location: 0.45),
                             .init(color: .clear, location: 1)]),
            center: floor, startRadius: 0, endRadius: radius * 0.525))
        var light = context
        light.blendMode = .plusLighter
        let l = min(1, max(0, brightness))
        light.fill(Path(ellipseIn: CGRect(x: floor.x - radius * 0.31, y: floor.y - radius * 0.075,
                                         width: radius * 0.62, height: radius * 0.15)),
                   with: .radialGradient(Gradient(stops: [
                    .init(color: .white.opacity(0.42 * l), location: 0),
                    .init(color: tint.opacity(0.5 * l), location: 0.22),
                    .init(color: .clear, location: 1)]),
                   center: floor, startRadius: 0, endRadius: radius * 0.31))
    }

    private static func arcCount(_ activity: VoicePresentationState.Activity, level: Double) -> Int {
        let base: Int
        let voice: Bool
        switch activity {
        case .listening: base = 4; voice = false
        case .user, .assistant: base = 9; voice = true
        case .thinking: base = 5; voice = false
        case .muted: base = 1; voice = false
        case .connecting: base = 2; voice = false
        case .offline: return 0
        }
        return Int((Double(base) * (voice ? 0.6 + 0.6 * level : 1)).rounded())
    }

    private static func drawEnergy(context: inout GraphicsContext, center: CGPoint,
                                   radius: Double, phase: Double, tint: Color,
                                   strength: Double, energy: Double,
                                   activity: VoicePresentationState.Activity,
                                   pointer: CGPoint?, ripple: Double,
                                   reduceMotion: Bool, gain: Double, echo: Bool,
                                   overlap: Bool, depths: [Double]?) {
        let inner = radius * CrystalGlassRig.plasmaClipFraction
        let scale = inner / demoRadius
        let count = arcCount(activity, level: energy)
        if echo {
            var reflected = context
            reflected.blendMode = .plusLighter
            reflected.opacity = 0.16 * gain
            reflected.translateBy(x: center.x, y: center.y)
            reflected.rotate(by: .radians(.pi))
            reflected.scaleBy(x: 0.8, y: 0.8)
            reflected.translateBy(x: -center.x, y: -center.y)
            drawArcSet(context: &reflected, center: center, scale: scale, phase: phase,
                       tint: tint, level: energy, activity: activity, pointer: pointer,
                       front: nil, contacts: false, depths: depths)
        }
        var frame = context
        frame.opacity = min(1, max(0, gain))
        frame.fill(disc(center, demoRadius * 1.35 * scale), with: .radialGradient(
            Gradient(colors: [tint.opacity(0.22 * energy * strength), .clear]),
            center: center, startRadius: demoRadius * 0.8 * scale,
            endRadius: demoRadius * 1.35 * scale))
        drawArcSet(context: &frame, center: center, scale: scale, phase: phase,
                   tint: tint, level: energy, activity: activity, pointer: pointer,
                   front: false, contacts: true, depths: depths)
        if activity != .offline {
            let minimum = (demoRadius / CrystalGlassRig.plasmaClipFraction / 3) / 0.75
            let core = (minimum + 3 + energy * 22 + (reduceMotion ? 0 : 3 * sin(phase * 5))) * scale
            frame.fill(disc(center, core * 0.8), with: .radialGradient(
                Gradient(colors: [Color(red: 8 / 255, green: 11 / 255, blue: 15 / 255).opacity(0.7), .clear]),
                center: center, startRadius: 0, endRadius: core * 0.8))
            var hot = frame
            hot.blendMode = .plusLighter
            hot.fill(disc(center, core), with: .radialGradient(
                Gradient(stops: [.init(color: .white.opacity(0.95), location: 0),
                                 .init(color: .white.opacity(0.35 + 0.3 * energy), location: 0.25),
                                 .init(color: tint.opacity(0.85), location: 0.5),
                                 .init(color: .clear, location: 1)]),
                center: center, startRadius: 0, endRadius: core))
        }
        drawArcSet(context: &frame, center: center, scale: scale, phase: phase,
                   tint: tint, level: energy, activity: activity, pointer: pointer,
                   front: true, contacts: true, depths: depths)
        if overlap {
            var boltPath = Path()
            let angle = Double.pi / 2 + (noise(Int(phase * 60)) - 0.5)
            let end = CGPoint(x: center.x + cos(angle) * demoRadius * scale,
                              y: center.y + sin(angle) * demoRadius * scale)
            boltPath.move(to: center)
            bolt(&boltPath, from: center, to: end, jitter: 70 * scale,
                 depth: 5, seed: 4_241)
            frame.stroke(boltPath, with: .color(AppTheme.user.opacity(0.9)),
                         lineWidth: smallWidth(3, scale: scale))
        }
        if ripple > 0 {
            frame.stroke(disc(center, inner * (0.35 + 0.65 * ripple)),
                         with: .color(tint.opacity((1 - ripple) * 0.65)),
                         lineWidth: max(1, 2 * (1 - ripple)))
        }
        if activity == .thinking {
            var path = Path(); path.addArc(center: center, radius: inner * 0.58,
                startAngle: .radians(phase * 1.8), endAngle: .radians(phase * 1.8 + .pi * 1.25), clockwise: false)
            frame.stroke(path, with: .color(tint.opacity(0.65)),
                         style: StrokeStyle(lineWidth: max(1, scale * 2), lineCap: .round))
        }
        if activity == .muted {
            var slash = Path(); slash.move(to: CGPoint(x: center.x - inner * 0.16, y: center.y + inner * 0.20))
            slash.addLine(to: CGPoint(x: center.x + inner * 0.16, y: center.y - inner * 0.20))
            frame.stroke(slash, with: .color(AppTheme.textDim), lineWidth: max(1.5, scale * 3))
        }
        if activity == .connecting {
            var sweep = Path(); sweep.addArc(center: center, radius: inner * 0.96,
                startAngle: .radians(phase * 2), endAngle: .radians(phase * 2 + 0.75), clockwise: false)
            frame.stroke(sweep, with: .color(tint), style: StrokeStyle(lineWidth: 2, lineCap: .round))
        }
    }

    private struct ArcEnd { let point: CGPoint; let z: Double }

    private static func arcEnds(center: CGPoint, scale: Double, phase: Double,
                                level: Double, activity: VoicePresentationState.Activity,
                                pointer: CGPoint?, depths: [Double]?) -> [ArcEnd] {
        let count = arcCount(activity, level: level)
        return (0..<count).map { index in
            let thinkingSpin = activity == .thinking ? phase * 0.8 : 0
            let angle = Double(index) * 0.63 + phase * (noise(index + 90) - 0.5) * 0.4 + thinkingSpin
            let z = depths.flatMap { $0.indices.contains(index) ? $0[index] : nil }
                ?? sin(phase * 0.35 + Double(index) * 1.71) * 0.82
            let projected = sqrt(max(0, 1 - z * z))
            var point = CGPoint(x: center.x + cos(angle) * demoRadius * projected * scale,
                                y: center.y + sin(angle) * demoRadius * projected * scale)
            var depth = z
            if let pointer, index < max(2, Int(ceil(Double(count) * 0.6))) {
                let dx = pointer.x - center.x, dy = pointer.y - center.y
                let distance = hypot(dx, dy) / scale
                if distance < demoRadius {
                    point = pointer
                    depth = sqrt(max(0, 1 - distance * distance / (demoRadius * demoRadius)))
                } else {
                    let angle = atan2(dy, dx)
                    point = CGPoint(x: center.x + cos(angle) * demoRadius * scale,
                                    y: center.y + sin(angle) * demoRadius * scale)
                    depth = 0
                }
            }
            return ArcEnd(point: point, z: depth)
        }
    }

    private static func drawArcSet(context: inout GraphicsContext, center: CGPoint,
                                   scale: Double, phase: Double, tint: Color,
                                   level: Double, activity: VoicePresentationState.Activity,
                                   pointer: CGPoint?, front: Bool?, contacts: Bool,
                                   depths: [Double]?) {
        for (index, end) in arcEnds(center: center, scale: scale, phase: phase, level: level,
                                    activity: activity, pointer: pointer, depths: depths).enumerated() {
            if let front, (end.z >= 0) != front { continue }
            let widening = end.z > 0 ? 1 + 0.9 * end.z : 1
            let dim = end.z < 0 ? 0.4 + 0.6 * (1 + end.z) : 1
            let width = smallWidth((1.2 + level * 1.6) * widening, scale: scale)
            var path = Path(); path.move(to: center)
            bolt(&path, from: center, to: end.point, jitter: (50 + level * 36) * scale,
                 depth: 5, seed: index * 101 + Int(phase * 60) * 17)
            context.drawLayer { glow in
                glow.addFilter(.blur(radius: max(0.5, width * 1.5)))
                glow.stroke(path, with: .color(tint.opacity(0.06 * dim)),
                            style: StrokeStyle(lineWidth: width * 6, lineCap: .round))
            }
            context.stroke(path, with: .color(tint.opacity(0.18 * dim)),
                           style: StrokeStyle(lineWidth: width * 2.5, lineCap: .round))
            context.stroke(path, with: .color(.white.opacity(0.72 * dim)),
                           style: StrokeStyle(lineWidth: width, lineCap: .round))
            if noise(index * 37 + Int(phase * 60)) < 0.3 {
                let fraction = 0.4 + noise(index + 700) * 0.4
                let branchStart = CGPoint(x: center.x + (end.point.x - center.x) * fraction,
                                          y: center.y + (end.point.y - center.y) * fraction)
                let branchEnd = CGPoint(x: branchStart.x + (noise(index + 800) - 0.5) * 70 * scale,
                                        y: branchStart.y + (noise(index + 900) - 0.5) * 70 * scale)
                var branch = Path(); branch.move(to: branchStart)
                bolt(&branch, from: branchStart, to: branchEnd, jitter: 24 * scale,
                     depth: 3, seed: index * 53 + 900)
                context.stroke(branch, with: .color(tint.opacity(0.5 * dim)), lineWidth: width * 0.8)
            }
            guard contacts else { continue }
            let dot = smallRadius((5 + level * 5) * widening, scale: scale)
            context.fill(disc(end.point, dot), with: .color(tint.opacity(0.35 * dim)))
            if end.z > 0.15 {
                let spot = smallRadius((6 + level * 8) * (1 + 1.6 * end.z), scale: scale)
                context.fill(disc(end.point, spot), with: .radialGradient(
                    Gradient(stops: [.init(color: .white.opacity(0.75 * end.z), location: 0),
                                     .init(color: tint.opacity(0.5 * end.z), location: 0.35),
                                     .init(color: .clear, location: 1)]),
                    center: end.point, startRadius: 0, endRadius: spot))
            }
        }
    }

    private static func smallWidth(_ width: Double, scale: Double) -> Double {
        let ratio = scale / 0.85
        guard ratio < 1 else { return width * scale }
        let root = sqrt(ratio)
        let floor = 1.5 * min(1, (1 - ratio) / 0.25)
        return width * 0.85 * root + max(0, floor - 1.02 * root)
    }

    private static func smallRadius(_ radius: Double, scale: Double) -> Double {
        let ratio = scale / 0.85
        return radius * scale * (ratio >= 1 ? 1 : 1 / sqrt(ratio))
    }

    private static func bolt(_ path: inout Path, from: CGPoint, to: CGPoint,
                             jitter: Double, depth: Int, seed: Int) {
        guard depth > 0 else { path.addLine(to: to); return }
        let middle = CGPoint(x: (from.x + to.x) / 2 + (noise(seed + depth * 11) - 0.5) * jitter,
                             y: (from.y + to.y) / 2 + (noise(seed + depth * 23) - 0.5) * jitter)
        bolt(&path, from: from, to: middle, jitter: jitter / 2, depth: depth - 1, seed: seed * 2 + 1)
        bolt(&path, from: middle, to: to, jitter: jitter / 2, depth: depth - 1, seed: seed * 2 + 2)
    }
}

/// Mutable per-orb easing and brightness-rate state. Depth uses the approved
/// ±0.025 reference step scaled by r; colour uses k=0.08 and level k=0.20.
final class OrbEnergyState {
    struct RGB {
        var r = 102.0, g = 115.0, b = 255.0
    }
    private(set) var level = 0.0
    private(set) var color = AppTheme.listening
    private var rgb = RGB()
    private(set) var depths = (0..<10).map { sin(Double($0) * 1.71) * 0.82 }
    private(set) var flash = OrbFlashCap()

    func advance(activity: VoicePresentationState.Activity, measuredLevel: Double,
                 phase: Double, now: Double, dt: Double) {
        let targetRGB = CometOrbRenderer.stateRGB(activity)
        let colorEase = FrameRateIndependentEasing.factor(0.08, dt: dt)
        rgb.r += (targetRGB.0 - rgb.r) * colorEase
        rgb.g += (targetRGB.1 - rgb.g) * colorEase
        rgb.b += (targetRGB.2 - rgb.b) * colorEase
        color = Color(red: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255)
        let voice = activity == .user || activity == .assistant
        let base: Double
        switch activity {
        case .listening: base = 0.35
        case .thinking: base = 0.55
        case .muted: base = 0.12
        case .connecting: base = 0.30
        case .offline: base = 0
        case .user, .assistant: base = 1
        }
        let target = voice ? min(1, max(0, measuredLevel)) : base * 0.4
        level += (target - level) * FrameRateIndependentEasing.factor(0.20, dt: dt)
        let depthStep = FrameRateIndependentEasing.step(0.025, dt: dt)
        for index in depths.indices {
            depths[index] += sin(phase * 0.7 + Double(index) * 2.13) * depthStep
            if depths[index] > 0.95 { depths[index] = 1.9 - depths[index] }
            if depths[index] < -0.9 { depths[index] = -1.8 - depths[index] }
        }
        let luminance = min(1, max(0, (0.04 + level * 0.42) * (activity == .offline ? 0 : 1)))
        flash.advance(luminance: luminance, now: now, dt: dt)
    }
}

/// Post-pass brightness model. The 24×24 renderer sample supplies L in a
/// raster implementation; Canvas uses OrbEnergyState's bounded estimate.
/// Gain applies to the whole energy layer, never by clipping separate passes.
struct OrbFlashCap {
    private(set) var reference = 0.0
    private(set) var anchor = 0.0
    private(set) var shown = 0.0
    private(set) var gain = 1.0
    private(set) var previous = 0.0
    private(set) var carry = 0.0
    private var direction = 0
    private var lastReversal = -Double.infinity

    var cappedRatio: Double { reference > 0 ? shown / reference : 0 }

    mutating func advance(luminance: Double, now: Double, dt: Double) {
        let l = min(1, max(0, luminance.isFinite ? luminance : 0))
        let r = FrameRateIndependentEasing.ratio(dt: dt)
        reference = max(reference * pow(0.995, r), l, 0.000001)
        let step = 0.04 * reference * r
        let difference = l - anchor
        if abs(difference) > step * 0.5 {
            let next = difference > 0 ? 1 : -1
            if direction == next || now - lastReversal >= 0.220 {
                if direction != next { lastReversal = now }
                direction = next
                anchor += Double(next) * min(abs(difference), step)
            }
        }
        let half = 0.03 * reference
        shown = min(anchor + half, max(anchor - half, l))
        gain = l > 0.000001 ? min(1, shown / l) : 0
        carry = shown > l && previous > 0.000001 ? min(1, (shown - l) / previous) : 0
        previous = l
    }
}

// MARK: - Crystal shell (docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md, option A)
//
// The crystal renderer calls the shared energy, `disc`, `color` and `ice`
// helpers. Every blurred group
// is drawn as ONE layer through a context copy that carries the filter, so
// the blur applies to the composited group (GraphicsContext.addFilter
// filters each drawing operation, and a drawLayer call is one operation).
extension CometOrbRenderer {
    /// Immutable unit-space vector geometry. Each frame still renders the
    /// original fills/strokes at its exact radius; no pixels or voice state
    /// are cached, and resizing never reuses a raster from a different scale.
    private struct CrystalLight {
        let path: Path
        let direction: CGPoint
        init(_ outline: CrystalGlassRig.LightOutline) {
            var path = Path()
            for (index, point) in outline.points.enumerated() {
                if index == 0 { path.move(to: point) } else { path.addLine(to: point) }
            }
            path.closeSubpath()
            self.path = path
            let length = hypot(outline.mid.x, outline.mid.y)
            let norm = length > 0 ? length : 1
            direction = CGPoint(x: outline.mid.x / norm, y: outline.mid.y / norm)
        }
    }

    private static let crystalKeyPanes = CrystalGlassRig.keyPanes.map(CrystalLight.init)
    private static let crystalStrip = CrystalLight(CrystalGlassRig.strip)
    private static let crystalRimSegments: [(path: Path, weight: Double)] = {
        typealias Rig = CrystalGlassRig
        return (0..<Rig.arcSegmentCount).map { index in
            let t0 = Double(index) / Double(Rig.arcSegmentCount)
            let t1 = Double(index + 1) / Double(Rig.arcSegmentCount)
            let start = Rig.dispersionStartRadians, end = Rig.dispersionEndRadians
            let a0 = start + (end - start) * t0, a1 = start + (end - start) * t1
            var path = Path()
            path.move(to: CGPoint(x: cos(a0), y: sin(a0)))
            path.addLine(to: CGPoint(x: cos(a1), y: sin(a1)))
            return (path, pow(sin(Double.pi * (t0 + t1) / 2), Rig.arcFalloffExponent))
        }
    }()

    private static func drawCrystalShell(context: inout GraphicsContext, center: CGPoint,
                                         radius: Double, phase: Double, userEnergy: Double,
                                         outputEnergy: Double, tint: Color, strength: Double,
                                         breath: Double, energy: Double, ready: Bool,
                                         activity: VoicePresentationState.Activity,
                                         pointer: CGPoint?, ripple: Double, reduceMotion: Bool,
                                         gain: Double, depths: [Double]?) {
        typealias Rig = CrystalGlassRig
        let sphere = disc(center, radius)

        // 1. Plasma bloom just outside the glass; follows the voice state.
        let haloRadius = radius * Rig.haloExtent
        context.fill(disc(center, haloRadius), with: .radialGradient(
            Gradient(stops: Rig.haloStops.map {
                Gradient.Stop(color: tint.opacity($0.weight * Rig.haloOpacity * strength),
                              location: $0.location)
            }),
            center: center, startRadius: 0, endRadius: haloRadius))

        // 3. Glass body.
        context.fill(sphere, with: .radialGradient(
            Gradient(stops: Rig.bodyStops.map {
                Gradient.Stop(color: color(Rig.inkRGB).opacity($0.opacity), location: $0.location)
            }),
            center: center, startRadius: 0, endRadius: radius))

        // 4. The capped energy frame, seen through the unchanged inner wall.
        var inside = context
        inside.clip(to: disc(center, radius * Rig.plasmaClipFraction))
        drawEnergy(context: &inside, center: center, radius: radius, phase: phase,
                   tint: tint, strength: strength * breath, energy: energy,
                   activity: activity, pointer: pointer, ripple: ripple,
                   reduceMotion: reduceMotion, gain: gain, echo: true,
                   overlap: activity == .user && outputEnergy > 0, depths: depths)

        // 5. Plasma light carried in the wall, strongest opposite the key light.
        var wall = context
        wall.clip(to: sphere)
        wall.blendMode = .plusLighter
        wall.addFilter(.blur(radius: radius * Rig.wallGlowBlurFraction))
        wall.drawLayer { layer in
            var ring = Path()
            ring.addEllipse(in: CGRect(x: center.x - radius * Rig.wallOuterFraction,
                                       y: center.y - radius * Rig.wallOuterFraction,
                                       width: radius * Rig.wallOuterFraction * 2,
                                       height: radius * Rig.wallOuterFraction * 2))
            ring.addEllipse(in: CGRect(x: center.x - radius * Rig.wallInnerFraction,
                                       y: center.y - radius * Rig.wallInnerFraction,
                                       width: radius * Rig.wallInnerFraction * 2,
                                       height: radius * Rig.wallInnerFraction * 2))
            layer.fill(ring, with: .linearGradient(
                Gradient(colors: [tint.opacity(0), tint.opacity(Rig.wallGlowOpacity * strength)]),
                startPoint: CGPoint(x: center.x + radius * Rig.wallGlowStart.x,
                                    y: center.y + radius * Rig.wallGlowStart.y),
                endPoint: CGPoint(x: center.x + radius * Rig.wallGlowEnd.x,
                                  y: center.y + radius * Rig.wallGlowEnd.y)),
                style: FillStyle(eoFill: true))
        }

        // 6. Wall thickness: dark inner-surface line, faint light line outside it.
        context.stroke(disc(center, radius * Rig.wallLineFraction),
                       with: .color(.black.opacity(Rig.wallLineOpacity)),
                       lineWidth: max(Rig.wallLineMinWidth, radius * Rig.wallLineWidthFraction))
        context.stroke(disc(center, radius * (Rig.wallLineFraction + Rig.wallHighlightOffset)),
                       with: .color(ice.opacity(Rig.wallHighlightOpacity)),
                       lineWidth: Rig.wallHighlightWidth)

        // 7. Reflections of the room: one layer, screened onto the scene.
        // Nothing in it depends on voice state or phase.
        var room = context
        room.blendMode = .screen
        room.drawLayer { env in
            drawCrystalReflections(into: &env, center: center, radius: radius)
        }

    }

    private static func drawCrystalReflections(into env: inout GraphicsContext,
                                               center: CGPoint, radius: Double) {
        typealias Rig = CrystalGlassRig
        let sphere = disc(center, radius)

        // a. Room reflection: sky gradient masked by Fresnel reflectance.
        // The 0.62 layer opacity is folded into the gradient's alpha, which
        // is mathematically identical under destinationIn.
        env.drawLayer { layer in
            layer.fill(sphere, with: .linearGradient(
                Gradient(stops: Rig.skyStops.map {
                    Gradient.Stop(color: color(Rig.skyRGB).opacity($0.opacity * Rig.fresnelOpacity),
                                  location: $0.location)
                }),
                startPoint: CGPoint(x: center.x, y: center.y - radius),
                endPoint: CGPoint(x: center.x, y: center.y + radius)))
            layer.blendMode = .destinationIn
            layer.fill(sphere, with: .radialGradient(
                Gradient(stops: Rig.fresnelStops.map {
                    Gradient.Stop(color: Color.white.opacity($0.reflectance), location: $0.location)
                }),
                center: center, startRadius: 0, endRadius: radius))
        }

        // b. Caustic on the far inner wall.
        let focus = CGPoint(x: center.x + radius * Rig.causticCenter.x,
                            y: center.y + radius * Rig.causticCenter.y)
        let focusRadius = radius * Rig.causticRadiusFraction
        var caustic = env
        caustic.clip(to: disc(center, radius * Rig.causticClipFraction))
        caustic.addFilter(.blur(radius: radius * Rig.causticBlurFraction))
        caustic.drawLayer { layer in
            layer.fill(disc(focus, focusRadius), with: .radialGradient(
                Gradient(stops: [
                    .init(color: Color.white.opacity(Rig.causticOpacity), location: 0),
                    .init(color: ice.opacity(Rig.causticOpacity * Rig.causticMidOpacityRatio), location: 0.5),
                    .init(color: ice.opacity(0), location: 1),
                ]),
                center: focus, startRadius: 0, endRadius: focusRadius))
        }

        // c. Studio lights: the two-pane window key and the rim strip.
        var lights = env
        lights.addFilter(.blur(radius: max(Rig.lightsMinBlur, radius * Rig.lightsBlurFraction)))
        lights.drawLayer { layer in
            for pane in crystalKeyPanes {
                fillLight(&layer, pane, center: center, radius: radius, opacity: Rig.keyOpacity)
            }
            fillLight(&layer, crystalStrip, center: center, radius: radius, opacity: Rig.stripOpacity)
        }

        // d. The window again, off the inside of the far wall: rotated a
        // half turn about the center and scaled down.
        var back = env
        back.addFilter(.blur(radius: radius * Rig.backKeyBlurFraction))
        back.drawLayer { layer in
            layer.translateBy(x: center.x, y: center.y)
            layer.rotate(by: .radians(Double.pi))
            layer.scaleBy(x: Rig.backKeyScale, y: Rig.backKeyScale)
            layer.translateBy(x: -center.x, y: -center.y)
            for pane in crystalKeyPanes {
                fillLight(&layer, pane, center: center, radius: radius, opacity: Rig.backKeyOpacity)
            }
        }

        // e. Dispersion along the lit rim.
        var dispersion = env
        dispersion.addFilter(.blur(radius: Rig.dispersionBlur))
        dispersion.drawLayer { layer in
            strokeRimArc(&layer, center: center, radius: radius * Rig.dispersionCoolRadius,
                         peak: Rig.dispersionCoolPeak, color: color(Rig.dispersionCoolRGB))
            strokeRimArc(&layer, center: center, radius: radius * Rig.dispersionWarmRadius,
                         peak: Rig.dispersionWarmPeak, color: color(Rig.dispersionWarmRGB))
        }

        // f. Silhouette hairline.
        env.stroke(disc(center, radius * Rig.hairlineFraction),
                   with: .color(Color.white.opacity(Rig.hairlineOpacity)),
                   lineWidth: Rig.hairlineWidth)
    }

    /// Fills a light's reflection, brighter toward the rim.
    private static func fillLight(_ layer: inout GraphicsContext, _ light: CrystalLight,
                                  center: CGPoint, radius: Double, opacity: Double) {
        typealias Rig = CrystalGlassRig
        let transform = CGAffineTransform(a: radius, b: 0, c: 0, d: radius,
                                          tx: center.x, ty: center.y)
        let path = light.path.applying(transform)
        let ux = light.direction.x, uy = light.direction.y
        layer.fill(path, with: .linearGradient(
            Gradient(colors: [Color.white.opacity(opacity),
                              Color.white.opacity(opacity * Rig.lightInnerOpacityRatio)]),
            startPoint: CGPoint(x: center.x + ux * radius, y: center.y + uy * radius),
            endPoint: CGPoint(x: center.x + ux * radius * Rig.lightGradientInnerFraction,
                              y: center.y + uy * radius * Rig.lightGradientInnerFraction)))
    }

    /// One dispersion arc: short segments whose opacity rises and falls
    /// as sin(pi * t)^1.6 along the arc.
    private static func strokeRimArc(_ layer: inout GraphicsContext, center: CGPoint,
                                     radius: Double, peak: Double, color: Color) {
        typealias Rig = CrystalGlassRig
        let transform = CGAffineTransform(a: radius, b: 0, c: 0, d: radius,
                                          tx: center.x, ty: center.y)
        for cached in crystalRimSegments {
            let alpha = peak * cached.weight
            let segment = cached.path.applying(transform)
            layer.stroke(segment, with: .color(color.opacity(alpha)),
                         style: StrokeStyle(lineWidth: Rig.dispersionWidth, lineCap: .round))
        }
    }
}
