import SwiftUI

/// Silo's measured voice feedback with separate adaptive and rollback paths.
/// The adaptive Command Center uses a compact two-channel atom; legacy layouts
/// retain the original layered sine geometry and simulated envelope for
/// rollback. Missing levels produce a static trace and accessible unavailable
/// detail. Wake flashes remain explicit wake-event feedback, never speech
/// evidence.
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
            // Canvas is not consistently exposed as an accessibility node in
            // compact macOS layouts. Keep one stable host element so the
            // visual channel mapping and current voice state remain discoverable.
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Voice activity — user teal, Mortimer orange")
            .accessibilityValue(accessibilityValue)
    }

    private var accessibilityValue: String {
        let current = presentation?()
        let state = current?.label ?? voiceState.label
        guard current?.audioLevelUnavailable == true else { return state }
        return "\(state); audio level unavailable"
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
struct AtomMotion {
    private(set) var phase = 0.0
    private var lastTime: Double?

    mutating func suspend() { lastTime = nil }

    mutating func advance(now: Double, energy: Double, moving: Bool) -> Double {
        guard now.isFinite else { lastTime = nil; return phase }
        defer { lastTime = now }
        guard moving, let previous = lastTime, now >= previous else { return phase }
        // Bound resume/long-frame travel; audio changes velocity, never position.
        let elapsed = min(now - previous, 0.1)
        let level = energy.isFinite ? min(1, max(0, energy)) : 0
        phase += elapsed * (0.60 + 0.90 * level)
        return phase
    }
}

final class WaveEngine {
    private struct Layer {
        let aMul: Double
        let fMul: Double
        let po: Double
        let width: Double
    }

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
    /// Layout-0 geometry: main + two phase-offset echoes for the phosphor
    /// look.
    private static let legacyLayers: [Layer] = [
        Layer(aMul: 1, fMul: 1, po: 0, width: 2),
        Layer(aMul: 0.45, fMul: 1.35, po: 0.9, width: 1.4),
        Layer(aMul: 0.22, fMul: 0.72, po: -1.6, width: 1),
    ]
    private static let bootRampSeconds = 0.9   // E2 boot ramp

    private var dyn = Dyn(base: 0.004, speed: 0.12, alpha: 0.16, glow: 0,
                          cr: 95, cg: 130, cb: 150)
    private var p1 = 0.0, p2 = 0.0, p3 = 0.0
    private var level = 0.0
    private var userEnvelope = VoiceEnvelope()
    private var outputEnvelope = VoiceEnvelope()
    private var atomMotion = AtomMotion()
    private var cxEased = -1.0
    private var last: Double?
    private var lastState: VoiceState = .offline
    private var bootStart: Double = 0   // 0 = never booted = full amplitude
    private var wakeFlashStart: Double = 0   // 0 = no flash pending/active

    /// Drop transient amplitude and pending wake flashes across invisibility.
    func suspend() {
        last = nil
        level = 0
        userEnvelope = VoiceEnvelope()
        outputEnvelope = VoiceEnvelope()
        atomMotion.suspend()
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
        let previous = last
        last = now

        // The adaptive Command Center uses the compact atom treatment. Each
        // speaker has its own measured envelope and orbital plane, so overlap
        // remains visible without inventing a second audio channel.
        if let presentation {
            // Listening and connected/muted are ready states, not speech evidence:
            // keep its low-energy idle motion so the compact interface does
            // not look frozen between utterances. A missing level while
            // Mortimer is speaking remains static and is labelled unavailable
            // rather than synthesising speech.
            let staticTrace = reduceMotion || (presentation.userLevel == nil && presentation.outputLevel == nil &&
                presentation.activity != .thinking && presentation.activity != .connecting &&
                presentation.activity != .listening && presentation.activity != .muted)
            let userTarget = AudioPresentationTuning.presentationLevel(
                rms: presentation.userLevel, isInput: true)
            let outputTarget = AudioPresentationTuning.presentationLevel(
                rms: presentation.outputLevel, isInput: false)
            let userLevel = userEnvelope.advance(target: userTarget, now: now)
            let outputLevel = outputEnvelope.advance(target: outputTarget, now: now)
            drawAtom(context: &context, size: size, now: now,
                     stageCenterX: stageCenterX, userLevel: userLevel,
                     outputLevel: outputLevel, presentation: presentation,
                     reduceMotion: reduceMotion, staticTrace: staticTrace)
            return
        }

        // Everything below is the layout-0 rollback wave. Only layout 0 draws
        // VoiceWaveView without a presentation (ConsoleView), so this path
        // never sees measured audio and runs on the web's simulated envelope.
        // The measured-wave branches, depth ribbon and width slider that used
        // to sit here were reachable only with a presentation, which returns
        // above; they were removed 2026-09-24 (C6 item 10).
        let dt = max(0, min(now - (previous ?? now), 0.1))
        let t = now

        // E2 boot ramp: rises from flatline over 900ms when a connection
        // arrives (offline/connecting -> listening/speaking).
        if (lastState == .offline || lastState == .connecting),
           state == .listening || state == .speaking {
            bootStart = now
        }
        lastState = state

        let target = state == .speaking ? simLevel(t) : 0
        level = target > level ? level + (target - level) * 0.45
                               : level + (target - level) * 0.06

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

        let breath = state == .listening ? 0.004 + 0.004 * sin(t * 0.9) : 0
        let voice = state == .speaking ? level * AudioPresentationTuning.measuredOutputGain : 0
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

        let amp = h * (dyn.base + breath + voice + 0.01 * flash) * Self.ampScale * bootRamp
        let alpha = min(1, dyn.alpha + 0.4 * flash)
        let glow = min(1, dyn.glow + flash)

        let r = dyn.cr, g = dyn.cg, b = dyn.cb

        // Super-Gaussian window: tight central plateau (middle ~10% of the
        // width holds >=94% of peak), fast falloff.
        let envWidth = max(1, 0.11 * Double(w))
        for layer in Self.legacyLayers {
            var path = Path()
            var x = 0.0
            var first = true
            while x <= w {
                let env = exp(-pow((x - cx) / envWidth, 4))
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
                    with: .color(Color(red: 44 / 255, green: 201 / 255, blue: 1)
                        .opacity(0.75 * glow * layer.aMul)),
                    style: StrokeStyle(lineWidth: layer.width * 2, lineJoin: .round)
                )
            }
            context.stroke(path, with: .color(color),
                           style: StrokeStyle(lineWidth: layer.width, lineJoin: .round))
        }
    }

    /// Audio state and easing stay in the shared engine. The adaptive renderer
    /// draws the selected glass/plasma/comet treatment; rollback stays above.
    private func drawAtom(context: inout GraphicsContext, size: CGSize, now: Double,
                          stageCenterX: CGFloat?, userLevel: Double,
                          outputLevel: Double, presentation: VoicePresentationState,
                          reduceMotion: Bool, staticTrace: Bool) {
        let userEnergy = min(1, max(0, userLevel * AudioPresentationTuning.measuredInputGain))
        let outputEnergy = min(1, max(0, outputLevel * AudioPresentationTuning.measuredOutputGain))
        let phase = atomMotion.advance(now: now, energy: max(userEnergy, outputEnergy),
                                       moving: !reduceMotion && !staticTrace)
        CometOrbRenderer.draw(context: &context, size: size, stageCenterX: stageCenterX,
                              phase: phase, userEnergy: userEnergy,
                              outputEnergy: outputEnergy, activity: presentation.activity)
    }
}
