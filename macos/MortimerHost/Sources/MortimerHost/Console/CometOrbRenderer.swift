import SwiftUI

/// Procedural glass, plasma and comet rendering. No bitmap is substituted for
/// voice feedback. Geometry is deterministic so unavailable audio and reduced
/// motion remain still, including the particle field and internal filaments.
enum CometOrbRenderer {
    private static let blue = Color(red: 0.24, green: 0.60, blue: 1)
    private static let ice = Color(red: 0.74, green: 0.91, blue: 1)

    private static func color(_ rgb: (Double, Double, Double)) -> Color {
        Color(red: rgb.0 / 255, green: rgb.1 / 255, blue: rgb.2 / 255)
    }

    private static func disc(_ center: CGPoint, _ radius: Double) -> Path {
        Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius,
                              width: radius * 2, height: radius * 2))
    }

    // Fixed hash, independent of frame count: no random flicker on redraw.
    private static func noise(_ index: Int) -> Double {
        let n = sin(Double(index) * 127.1 + 311.7) * 43758.5453
        return n - floor(n)
    }

    static func draw(context: inout GraphicsContext, size: CGSize,
                     stageCenterX: CGFloat?, phase: Double, userEnergy: Double,
                     outputEnergy: Double, activity: VoicePresentationState.Activity) {
        let center = CGPoint(x: stageCenterX ?? size.width / 2, y: size.height / 2)
        // Give the sphere the prominence of the reference, with room for the
        // extended comet paths and bloom inside the existing compact bounds.
        let extent = min(size.height, 2 * min(center.x, size.width - center.x))
        guard extent > 0 else { return }
        let radius = extent * 0.255
        let energy = max(userEnergy, outputEnergy)
        let ambient = activity == .listening || activity == .muted
        let ready = ambient || activity == .user ||
            activity == .assistant || activity == .thinking
        let tint: Color
        switch activity {
        case .user: tint = color(AudioPresentationTuning.userRGB)
        case .assistant, .thinking: tint = color(AudioPresentationTuning.assistantRGB)
        case .listening, .muted: tint = color(AudioPresentationTuning.idleRGB)
        case .offline, .connecting: tint = color(AudioPresentationTuning.neutralRGB)
        }
        let strength = ready ? 0.52 + energy * 0.48 : 0.16
        // Idle breathing is a ready cue; voice intensity uses only the measured
        // envelopes. All temporal terms use the pausable phase, never uptime.
        let breath = ambient ? 0.94 + 0.06 * sin(phase * 1.2) : 1

        // Split the orbits into back/front passes. The shell can tint rear
        // trails, while near comets stay sharp instead of looking pasted on.
        if ready {
            comets(context: &context, center: center, radius: radius, phase: phase,
                   userEnergy: userEnergy, outputEnergy: outputEnergy, front: false)
        }
        let sphere = disc(center, radius)
        context.fill(disc(center, radius * 1.15), with: .radialGradient(
            Gradient(stops: [.init(color: blue.opacity(0), location: 0.74),
                             .init(color: blue.opacity(0.11 * strength), location: 0.85),
                             .init(color: .clear, location: 1)]),
            center: center, startRadius: 0, endRadius: radius * 1.15))
        context.fill(sphere, with: .radialGradient(
            Gradient(stops: [.init(color: blue.opacity(0.025), location: 0),
                             .init(color: blue.opacity(0.06), location: 0.65),
                             .init(color: blue.opacity(0.25 * strength), location: 0.91),
                             .init(color: ice.opacity(0.38 * strength), location: 0.975),
                             .init(color: blue.opacity(0.12), location: 1)]),
            center: center, startRadius: 0, endRadius: radius))

        var inside = context
        inside.clip(to: disc(center, radius * 0.94))
        plasma(context: &inside, center: center, radius: radius, phase: phase,
               tint: tint, strength: strength * breath, energy: energy)

        // Broken specular highlights replace the latitude/longitude cage.
        // Unequal arcs and an off-center soft reflection read as curved glass.
        for (start, length, opacity, width) in [
            (3.45, 1.25, 0.76, 1.5), (0.05, 0.90, 0.54, 1.1),
            (1.65, 0.48, 0.30, 0.8), (4.9, 0.34, 0.42, 0.7)
        ] {
            var arc = Path()
            for i in 0...40 {
                let t = Double(i) / 40
                let theta = start + t * length
                let r = radius * (0.966 + 0.007 * sin(t * .pi))
                let point = CGPoint(x: center.x + cos(theta) * r,
                                    y: center.y + sin(theta) * r)
                if i == 0 { arc.move(to: point) } else { arc.addLine(to: point) }
            }
            context.stroke(arc, with: .color(ice.opacity(opacity * strength)),
                           style: StrokeStyle(lineWidth: width, lineCap: .round))
        }
        var reflection = context
        reflection.clip(to: sphere)
        reflection.addFilter(.blur(radius: radius * 0.035))
        let highlight = CGPoint(x: center.x - radius * 0.49, y: center.y - radius * 0.64)
        reflection.fill(disc(highlight, radius * 0.25), with: .radialGradient(
            Gradient(colors: [ice.opacity(0.40 * strength), ice.opacity(0.05), .clear]),
            center: highlight, startRadius: 0, endRadius: radius * 0.25))
        if ready {
            comets(context: &context, center: center, radius: radius, phase: phase,
                   userEnergy: userEnergy, outputEnergy: outputEnergy, front: true)
        }
    }

    private static func plasma(context: inout GraphicsContext, center: CGPoint,
                               radius: Double, phase: Double, tint: Color,
                               strength: Double, energy: Double) {
        let reach = radius * 0.75
        context.fill(disc(center, reach), with: .radialGradient(
            Gradient(stops: [.init(color: tint.opacity(0.90 * strength), location: 0),
                             .init(color: tint.opacity(0.38 * strength), location: 0.27),
                             .init(color: tint.opacity(0.09 * strength), location: 0.70),
                             .init(color: .clear, location: 1)]),
            center: center, startRadius: 0, endRadius: reach))

        var volume = context
        volume.clip(to: disc(center, reach))
        for cloud in 0..<7 {
            let angle = Double(cloud) * 2.39996 + phase * 0.09
            let distance = reach * (0.18 + noise(cloud + 88) * 0.37)
            let point = CGPoint(x: center.x + cos(angle) * distance,
                                y: center.y + sin(angle) * distance)
            let cloudRadius = reach * (0.28 + noise(cloud + 92) * 0.28)
            volume.fill(disc(point, cloudRadius), with: .radialGradient(
                Gradient(colors: [tint.opacity(0.13 * strength), tint.opacity(0.045 * strength), .clear]),
                center: point, startRadius: 0, endRadius: cloudRadius))
        }

        // Irregular, projected loops distributed through the energy volume.
        // Different frequencies produce branching-looking folds without the
        // regular spirals that made the previous core resemble a target icon.
        var filaments: [(Path, Double)] = []
        for strand in 0..<16 {
            let seed = Double(strand)
            let turn = seed * 2.39996 + phase * (strand.isMultiple(of: 2) ? 0.14 : -0.11)
            var path = Path()
            for step in 0...72 {
                let t = Double(step) / 72 * (3.1 + noise(strand + 15) * 2.9) + seed
                let wave = 0.79 + 0.085 * sin(t * 3 + seed + phase * 0.25)
                    + 0.05 * sin(t * 7 - seed * 2) + 0.018 * sin(t * 17 + seed)
                let r = reach * (0.30 + noise(strand + 5) * 0.65) * wave
                let x = cos(t) * r + reach * 0.10 * sin(seed * 3)
                let y = sin(t) * r * (0.36 + noise(strand + 31) * 0.60) + reach * 0.10 * cos(seed * 2)
                let point = CGPoint(x: center.x + x * cos(turn) - y * sin(turn),
                                    y: center.y + x * sin(turn) + y * cos(turn))
                if step == 0 { path.move(to: point) } else { path.addLine(to: point) }
            }
            filaments.append((path, 0.10 + noise(strand + 72) * 0.25))
        }
        // A single blurred layer for all filaments avoids a blur pass per line.
        context.drawLayer { glow in
            glow.addFilter(.blur(radius: radius * 0.035))
            for (path, alpha) in filaments {
                glow.stroke(path, with: .color(tint.opacity(alpha * strength * 0.7)),
                            lineWidth: radius * 0.042)
            }
        }
        for (path, alpha) in filaments {
            context.stroke(path, with: .color(tint.opacity(alpha * strength)),
                           lineWidth: max(0.35, radius * 0.009))
        }
        // Fine, stable motes add the particulate texture visible in the study.
        for i in 0..<85 {
            let angle = noise(i + 100) * .pi * 2 + phase * 0.10
            let r = reach * sqrt(noise(i + 250))
            let point = CGPoint(x: center.x + cos(angle) * r,
                                y: center.y + sin(angle) * r * 0.91)
            context.fill(disc(point, 0.25 + noise(i + 400) * 0.40),
                         with: .color(tint.opacity((0.12 + noise(i + 550) * 0.40) * strength)))
        }
        // White-hot center with a colored halo; not an opaque colored disc.
        let core = radius * (0.17 + energy * 0.055)
        context.fill(disc(center, core * 1.8), with: .radialGradient(
            Gradient(stops: [.init(color: .white.opacity(0.98 * strength), location: 0),
                             .init(color: tint.opacity(0.95 * strength), location: 0.30),
                             .init(color: tint.opacity(0.30 * strength), location: 0.50),
                             .init(color: .clear, location: 1)]),
            center: center, startRadius: 0, endRadius: core * 1.8))
        for index in 0..<7 {
            let angle = Double(index) * 2.39996 + 0.3
            let length = core * (1.0 + noise(index + 900) * 1.6)
            var ray = Path()
            ray.move(to: center)
            ray.addLine(to: CGPoint(x: center.x + cos(angle) * length,
                                   y: center.y + sin(angle) * length))
            context.stroke(ray, with: .linearGradient(
                Gradient(colors: [tint.opacity(0.6 * strength), .clear]),
                startPoint: center, endPoint: CGPoint(x: center.x + cos(angle) * length,
                                                     y: center.y + sin(angle) * length)),
                lineWidth: 0.65)
        }
    }

    private struct OrbitPoint {
        let point: CGPoint
        let depth: Double
    }

    private static func comets(context: inout GraphicsContext, center: CGPoint,
                               radius: Double, phase: Double, userEnergy: Double,
                               outputEnergy: Double, front: Bool) {
        for channel in 0..<2 {
            let level = channel == 0 ? userEnergy : outputEnergy
            let tint = color(channel == 0 ? AudioPresentationTuning.userRGB : AudioPresentationTuning.assistantRGB)
            // Both reference colors remain visible as ready indicators. Only
            // the measured channel brightens; the nucleus identifies the talker.
            let brightness = 0.48 + 0.52 * level
            let tilt = channel == 0 ? -0.48 : 0.56
            let direction = channel == 0 ? 1.0 : -1.0
            func position(_ angle: Double) -> OrbitPoint {
                let x = cos(angle) * radius * 1.53
                let y = sin(angle) * radius * 1.17
                let depth = sin(angle) * 0.64
                return OrbitPoint(point: CGPoint(x: center.x + x * cos(tilt) - y * sin(tilt),
                                                y: center.y + x * sin(tilt) + y * cos(tilt)),
                                  depth: depth)
            }
            // Opposed comets leave a full-radian gap between tail and next head.
            for comet in 0..<2 {
                let headAngle = direction * phase + Double(comet) * .pi +
                    (channel == 0 ? 3.9 : 0.45)
                let span = 2.05 + 0.15 * level
                let steps = 64
                var strokes: [(Path, Double, Double)] = []
                for i in 0..<steps {
                    let age = Double(i) / Double(steps)
                    let p = position(headAngle - direction * span * age)
                    guard (p.depth >= 0) == front else { continue }
                    let next = position(headAngle - direction * span * Double(i + 1) / Double(steps))
                    let fade = pow(1 - age, 1.45)
                    var segment = Path()
                    segment.move(to: p.point); segment.addLine(to: next.point)
                    strokes.append((segment, fade * (0.70 + 0.30 * p.depth),
                                    max(0.22, radius * 0.052 * fade)))
                }
                context.drawLayer { glow in
                    glow.addFilter(.blur(radius: radius * 0.055))
                    // Fade the bloom too, so the end never becomes a solid ring.
                    for (path, fade, width) in strokes {
                        glow.stroke(path, with: .color(tint.opacity(fade * brightness * 0.36)),
                                    style: StrokeStyle(lineWidth: width * 3, lineCap: .round))
                    }
                }
                for (path, fade, width) in strokes {
                    context.stroke(path, with: .color(tint.opacity(fade * brightness * 0.92)),
                                   style: StrokeStyle(lineWidth: width, lineCap: .round))
                }
                // Spread small sparks across the tail, not regularly spaced
                // dots on the centerline. Stable seeds keep motion coherent.
                for i in 0..<100 {
                    let seed = i + channel * 317 + comet * 613
                    let age = noise(seed + 40)
                    let p = position(headAngle - direction * span * age)
                    guard (p.depth >= 0) == front else { continue }
                    let scatter = radius * (0.018 + age * 0.08)
                    let point = CGPoint(x: p.point.x + (noise(seed + 740) - 0.5) * scatter * 2,
                                        y: p.point.y + (noise(seed + 1040) - 0.5) * scatter * 2)
                    let alpha = pow(1 - age, 1.25) * brightness
                    context.fill(disc(point, 0.28 + noise(seed + 1340) * 0.65),
                                 with: .color((i.isMultiple(of: 5) ? ice : tint).opacity(alpha)))
                }
                let head = position(headAngle)
                guard (head.depth >= 0) == front else { continue }
                let headSize = radius * (0.075 + level * 0.012) * (0.91 + head.depth * 0.17)
                context.fill(disc(head.point, headSize * 3.4), with: .radialGradient(
                    Gradient(colors: [tint.opacity(brightness * 0.85), tint.opacity(0.15 * brightness), .clear]),
                    center: head.point, startRadius: 0, endRadius: headSize * 3.4))
                context.fill(disc(head.point, headSize), with: .radialGradient(
                    Gradient(colors: [.white.opacity(0.95), ice.opacity(0.88), tint.opacity(0.85)]),
                    center: head.point, startRadius: 0, endRadius: headSize))
                context.stroke(disc(head.point, headSize), with: .color(tint.opacity(brightness)), lineWidth: 0.8)
            }
        }
    }
}
