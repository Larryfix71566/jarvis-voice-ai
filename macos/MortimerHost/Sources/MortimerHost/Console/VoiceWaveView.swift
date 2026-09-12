import SwiftUI

/// Silo's original layered sine geometry, with separate adaptive and rollback
/// presentation paths. Adaptive amplitude uses only supplied measured levels;
/// missing levels produce a static trace and accessible unavailable detail.
/// The legacy layout retains its original simulated envelope for rollback.
/// Wake flashes remain explicit wake-event feedback, never speech evidence.
struct VoiceWaveView: View {
    let voiceState: VoiceState
    /// Stage horizontal center in window coordinates; nil = window center.
    var stageCenterX: CGFloat? = nil
    /// JarvisClient.wakePulse — a change triggers the wake flash.
    var wakePulse: Int = 0

    /// Adaptive presentation supplies current truth on each display tick so
    /// stale measurements expire even when callbacks stop. Nil retains rollback.
    var presentation: (() -> VoicePresentationState)? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VoiceWaveAnimation(voiceState: voiceState, stageCenterX: stageCenterX,
            wakePulse: wakePulse, presentation: presentation, reduceMotion: reduceMotion)
    }
}

/// Separates the system accessibility setting from animation scheduling. The
/// same content can be exercised with either setting without changing macOS.
struct VoiceWaveAnimation: View {
    let voiceState: VoiceState
    var stageCenterX: CGFloat? = nil
    var wakePulse: Int = 0
    var presentation: (() -> VoicePresentationState)? = nil
    let reduceMotion: Bool
    @State private var visible = false
    @State private var windowVisible = false
    @State private var engine = WaveEngine()

    var body: some View {
        Group {
            if let presentation, reduceMotion {
                // A paused animation timeline can still reevaluate its content.
                // Reduced motion has no animation schedule or visibility-driven
                // sampling; ordinary parent state changes still update its label.
                wave(presentation())
            } else {
                animatedWave
            }
        }
        .allowsHitTesting(false)
        .onDisappear { engine.suspend() }
        .onChange(of: wakePulse) { _, _ in engine.flashWake() }
    }

    private var animatedWave: some View {
        let initial = presentation?()
        let active = (initial?.userLevel ?? 0) > 0 || (initial?.outputLevel ?? 0) > 0 ||
            initial?.activity == .thinking || initial?.activity == .connecting
        return TimelineView(.animation(minimumInterval: presentation == nil ? nil : (active ? 1.0 / 60 : 1.0 / 15),
                                paused: !visible || !windowVisible)) { _ in
            wave(presentation?())
        }
        .background(WindowVisibilityReader { windowVisible = $0 })
        .onChange(of: windowVisible) { _, value in
            if !value { engine.suspend() }
        }
        .onAppear { visible = true }
        .onDisappear { visible = false; engine.suspend() }
    }

    private func wave(_ current: VoicePresentationState?) -> some View {
        Canvas { context, size in
            engine.draw(context: &context, size: size,
                        now: ProcessInfo.processInfo.systemUptime,
                        state: voiceState, stageCenterX: stageCenterX,
                        presentation: current, reduceMotion: reduceMotion)
        }
        .accessibilityLabel(current?.label ?? voiceState.label)
        .accessibilityValue(current?.audioLevelUnavailable == true ? "Audio level unavailable" : "")
    }
}

/// Frame-to-frame mutable wave state (phases, eased dynamics, VU level) —
/// a reference type so the Canvas closure can advance it.
final class WaveEngine {
    private struct Dyn {
        var base: Double; var speed: Double; var alpha: Double; var glow: Double
        var cr: Double; var cg: Double; var cb: Double
    }

    private struct Target { let base: Double; let speed: Double; let alpha: Double; let glow: Double }

    // VoiceWave.tsx TARGETS, verbatim.
    private static let targets: [VoiceState: Target] = [
        .offline: Target(base: 0.004, speed: 0.12, alpha: 0.16, glow: 0),
        .connecting: Target(base: 0.014, speed: 1.4, alpha: 0.3, glow: 0.25),
        .listening: Target(base: 0.01, speed: 0.45, alpha: 0.34, glow: 0.15),
        .speaking: Target(base: 0.016, speed: 1.0, alpha: 0.92, glow: 1),
    ]

    // VoiceWave.tsx COLORS, verbatim (offline dim slate; speaking bright cyan-white).
    private static let colors: [VoiceState: (Double, Double, Double)] = [
        .offline: (95, 130, 150),
        .connecting: (44, 201, 255),
        .listening: (44, 201, 255),
        .speaking: (190, 240, 255),
    ]

    /// Global vertical scale (user-tuned: 2x) — AMP_SCALE.
    private static let ampScale = 2.0
    /// Trace layers: main + two phase-offset echoes for the phosphor look.
    private static let layers: [(aMul: Double, fMul: Double, po: Double, width: Double)] = [
        (1, 1, 0, 2),
        (0.45, 1.35, 0.9, 1.4),
        (0.22, 0.72, -1.6, 1),
    ]
    private static let bootRampSeconds = 0.9   // E2 boot ramp

    private var dyn = Dyn(base: 0.004, speed: 0.12, alpha: 0.16, glow: 0,
                          cr: 95, cg: 130, cb: 150)
    private var p1 = 0.0, p2 = 0.0, p3 = 0.0
    private var level = 0.0
    private var measuredEnvelope = VoiceEnvelope()
    private var cxEased = -1.0
    private var last: Double?
    private var lastState: VoiceState = .offline
    private var bootStart: Double = 0   // 0 = never booted = full amplitude
    private var wakeFlashStart: Double = 0   // 0 = no flash pending/active

    /// Drop transient amplitude and pending wake flashes across invisibility.
    func suspend() {
        last = nil
        level = 0
        measuredEnvelope = VoiceEnvelope()
        wakeFlashStart = 0
    }

    /// Wake-detection flash: a ~0.9s glow + amplitude swell, decaying
    /// ease-out. Called from the view on each wakePulse.
    func flashWake() {
        wakeFlashStart = -1   // armed; stamped with `now` on the next draw
    }

    /// Simulated speech envelope — the web's own fallback (simLevel).
    private func simLevel(_ t: Double) -> Double {
        let s = abs(sin(t * 6.1) * 0.6 + sin(t * 9.7 + 1.3) * 0.4)
        return 0.25 + 0.75 * s
    }

    func draw(context: inout GraphicsContext, size: CGSize, now: Double,
              state: VoiceState, stageCenterX: CGFloat?,
              presentation: VoicePresentationState? = nil, reduceMotion: Bool = false) {
        let staticTrace = presentation.map { value in
            reduceMotion || (value.userLevel == nil && value.outputLevel == nil &&
                value.activity != .thinking && value.activity != .connecting)
        } ?? false
        let dt = staticTrace ? 0 : max(0, min(now - (last ?? now), 0.1))
        last = now
        let t = staticTrace ? 0 : now

        // E2 boot ramp: rises from flatline over 900ms when a connection
        // arrives (offline/connecting -> listening/speaking).
        if (lastState == .offline || lastState == .connecting),
           state == .listening || state == .speaking {
            bootStart = now
        }
        lastState = state

        // Adaptive levels are measured; only the legacy rollback uses simulation.
        if let presentation {
            let target = presentation.activity == .user ? presentation.userLevel : presentation.outputLevel
            level = measuredEnvelope.advance(target: target, now: now)
        } else {
            let target = state == .speaking ? simLevel(t) : 0
            level = target > level ? level + (target - level) * 0.45
                                   : level + (target - level) * 0.06
        }

        // --- ease dynamics + color toward the current state (0.06) ---
        let tg = Self.targets[state]!
        let (tr, tgc, tb) = Self.colors[state]!
        dyn.base += (tg.base - dyn.base) * 0.06
        dyn.speed += (tg.speed - dyn.speed) * 0.06
        dyn.alpha += (tg.alpha - dyn.alpha) * 0.06
        dyn.glow += (tg.glow - dyn.glow) * 0.06
        dyn.cr += (tr - dyn.cr) * 0.06
        dyn.cg += (tgc - dyn.cg) * 0.06
        dyn.cb += (tb - dyn.cb) * 0.06

        if let presentation {
            // §7 colours, one source (AudioPresentationTuning, closure C2.4).
            let color = presentation.activity == .user ? AudioPresentationTuning.userRGB :
                (presentation.activity == .assistant || presentation.activity == .thinking ?
                    AudioPresentationTuning.assistantRGB : AudioPresentationTuning.neutralRGB)
            dyn.cr = color.0; dyn.cg = color.1; dyn.cb = color.2
            dyn.base = 0.004
            dyn.alpha = presentation.activity == .offline ? 0.16 : 0.65
            dyn.glow = staticTrace ? 0 : 0.4
            dyn.speed = staticTrace ? 0 : 0.45
            if staticTrace { p1 = 0; p2 = 0; p3 = 0 }
        }

        p1 += dt * 2.2 * dyn.speed
        p2 -= dt * 3.1 * dyn.speed
        p3 += dt * 5.3 * dyn.speed

        let w = size.width
        let h = size.height

        // Peak centered on the STAGE, eased 0.12 so a drawer snap slides
        // the wave over rather than teleporting it.
        let cxTarget = Double(stageCenterX ?? w / 2)
        cxEased = cxEased < 0 ? cxTarget : cxEased + (cxTarget - cxEased) * 0.12
        let cx = cxEased
        let cy = h * 0.5

        let breath = presentation == nil ? (state == .listening ? 0.004 + 0.004 * sin(t * 0.9) : 0) :
            (presentation?.activity == .thinking && !reduceMotion ? 0.004 * (1 + sin(t * 0.9)) : 0)
        let voice = presentation == nil ? (state == .speaking ? level * 0.115 : 0) : level * 0.115
        var bootRamp = 1.0
        if bootStart > 0 {
            let p = min(1, (now - bootStart) / Self.bootRampSeconds)
            bootRamp = p * (2 - p)   // ease-out
        }

        // Wake flash envelope: 1 -> 0 over 0.9s, ease-out.
        if wakeFlashStart < 0 { wakeFlashStart = now }
        var flash = 0.0
        if wakeFlashStart > 0 {
            let p = (now - wakeFlashStart) / 0.9
            if p < 1 { flash = 1 - p * (2 - p) } else { wakeFlashStart = 0 }
        }

        if presentation != nil { bootRamp = 1 }
        if presentation != nil && reduceMotion { flash = 0 }
        let amp = h * (dyn.base + breath + voice + 0.01 * flash) * Self.ampScale * bootRamp
        let alpha = min(1, dyn.alpha + 0.4 * flash)
        let glow = min(1, dyn.glow + flash)

        let r = dyn.cr, g = dyn.cg, b = dyn.cb

        for layer in Self.layers {
            var path = Path()
            var x = 0.0
            var first = true
            while x <= w {
                // Super-Gaussian window: tight central plateau (middle
                // ~10% of the width holds >=94% of peak), fast falloff.
                let env = exp(-pow((x - cx) / (0.11 * w), 4))
                // slow speech-like wobble along the trace
                let mod = 0.65 + 0.35 * sin(0.012 * x * layer.fMul + t * 6.3 * dyn.speed + layer.po)
                let y = cy + env * amp * layer.aMul * mod *
                    (0.55 * sin(0.04 * x * layer.fMul + p1 * layer.fMul + layer.po)
                     + 0.3 * sin(0.084 * x * layer.fMul + p2 * layer.fMul - layer.po)
                     + 0.15 * sin(0.172 * x * layer.fMul + p3 * layer.fMul + layer.po * 2))
                if first { path.move(to: CGPoint(x: x, y: y)); first = false }
                else { path.addLine(to: CGPoint(x: x, y: y)) }
                x += 3
            }

            let color = Color(red: r / 255, green: g / 255, blue: b / 255)
                .opacity(alpha * layer.aMul)

            // Phosphor glow: the canvas used shadowBlur 26*glow in
            // accent cyan; approximated with blurred echo strokes.
            if glow > 0.05 {
                var glowContext = context
                glowContext.addFilter(.blur(radius: 13 * glow))
                glowContext.stroke(
                    path,
                    with: .color(Color(red: presentation == nil ? 44 / 255 : r / 255,
                                       green: presentation == nil ? 201 / 255 : g / 255,
                                       blue: presentation == nil ? 1 : b / 255)
                        .opacity(0.75 * glow * layer.aMul)),
                    style: StrokeStyle(lineWidth: layer.width * 2, lineJoin: .round)
                )
            }
            context.stroke(path, with: .color(color),
                           style: StrokeStyle(lineWidth: layer.width, lineJoin: .round))
        }
    }
}
