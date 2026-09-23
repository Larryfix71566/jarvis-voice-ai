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
        /// Signed parallax position: negative is behind the main trace,
        /// positive is in front of it.
        let depth: Double
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
    /// Rollback geometry: main + two phase-offset echoes for the phosphor
    /// look. Keeping this separate makes the old layout a real rollback path.
    private static let legacyLayers: [Layer] = [
        Layer(aMul: 1, fMul: 1, po: 0, width: 2, depth: 0),
        Layer(aMul: 0.45, fMul: 1.35, po: 0.9, width: 1.4, depth: 0),
        Layer(aMul: 0.22, fMul: 0.72, po: -1.6, width: 1, depth: 0),
    ]

    /// Adaptive presentation geometry: the same sine silhouette becomes a
    /// shallow ribbon with rear echoes and a foreground filament. The signed
    /// depth is a visual parallax offset, not a second audio signal.
    private static let depthLayers: [Layer] = [
        Layer(aMul: 0.18, fMul: 0.68, po: 1.8, width: 0.9, depth: -1.00),
        Layer(aMul: 0.34, fMul: 1.28, po: 0.9, width: 1.2, depth: -0.52),
        Layer(aMul: 1.00, fMul: 1.00, po: 0, width: 2.1, depth: 0),
        Layer(aMul: 0.38, fMul: 1.52, po: -0.9, width: 1.35, depth: 0.52),
        Layer(aMul: 0.16, fMul: 0.74, po: -1.8, width: 0.85, depth: 1.00),
    ]
    private static let bootRampSeconds = 0.9   // E2 boot ramp

    private var dyn = Dyn(base: 0.004, speed: 0.12, alpha: 0.16, glow: 0,
                          cr: 95, cg: 130, cb: 150)
    private var p1 = 0.0, p2 = 0.0, p3 = 0.0
    private var level = 0.0
    private var measuredEnvelope = VoiceEnvelope()
    private var userEnvelope = VoiceEnvelope()
    private var outputEnvelope = VoiceEnvelope()
    private var atomMotion = AtomMotion()
    private var previousMeasuredLevel = 0.0
    private var depthPulse = 0.0
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
        userEnvelope = VoiceEnvelope()
        outputEnvelope = VoiceEnvelope()
        atomMotion.suspend()
        previousMeasuredLevel = 0
        depthPulse = 0
        wakeFlashStart = 0
    }

    /// Wake-detection flash: a ~0.9s glow + amplitude swell, decaying
    /// ease-out. Called from the view on each wakePulse.
    func flashWake() {
        wakeFlashStart = -1   // armed; stamped with `now` on the next draw
    }

    /// Converts measured envelope and its positive attack into a bounded
    /// visual depth value. A zero level produces zero depth, preserving the
    /// rule that a missing/silent channel cannot look like speech.
    static func ribbonDepthEnergy(level: Double, transient: Double,
                                  activity: VoicePresentationState.Activity) -> Double {
        guard activity == .user || activity == .assistant else { return 0 }
        let level = min(1, max(0, level.isFinite ? level : 0))
        let transient = min(1, max(0, transient.isFinite ? transient : 0))
        let speakerScale = activity == .assistant
            ? AudioPresentationTuning.assistantDepthScale : 1.0
        return min(1, (level * AudioPresentationTuning.depthLevelContribution
                       + transient * AudioPresentationTuning.depthTransientContribution)
                      * speakerScale)
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
            // Listening and connected/muted are ready states, not speech evidence:
            // keep its low-energy idle motion so the compact interface does
            // not look frozen between utterances. A missing level while
            // Mortimer is speaking remains static and is labelled unavailable
            // rather than synthesising speech.
            reduceMotion || (value.userLevel == nil && value.outputLevel == nil &&
                value.activity != .thinking && value.activity != .connecting &&
                value.activity != .listening && value.activity != .muted)
        } ?? false
        let dt = staticTrace ? 0 : max(0, min(now - (last ?? now), 0.1))
        last = now
        let t = staticTrace ? 0 : now

        // The adaptive Command Center uses the compact atom treatment. Each
        // speaker has its own measured envelope and orbital plane, so overlap
        // remains visible without inventing a second audio channel. The
        // legacy path below stays intact for layouts 0/1 rollback.
        if let presentation {
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

        // E2 boot ramp: rises from flatline over 900ms when a connection
        // arrives (offline/connecting -> listening/speaking).
        if (lastState == .offline || lastState == .connecting),
           state == .listening || state == .speaking {
            bootStart = now
        }
        lastState = state

        // Adaptive levels are measured; only the legacy rollback uses simulation.
        // Item 10: mapped through the channel's dB window BEFORE smoothing,
        // so the envelope's 40 ms/180 ms easing runs in perceptual space —
        // a linear release from a loud syllable would otherwise collapse
        // most of its visible travel in the first few milliseconds.
        if let presentation {
            let isInput = presentation.activity == .user
            let raw = isInput ? presentation.userLevel : presentation.outputLevel
            let target = AudioPresentationTuning.presentationLevel(rms: raw, isInput: isInput)
            level = measuredEnvelope.advance(target: target, now: now)
        } else {
            let target = state == .speaking ? simLevel(t) : 0
            level = target > level ? level + (target - level) * 0.45
                                   : level + (target - level) * 0.06
        }

        // A positive envelope attack gives the ribbon a short forward push.
        // It is deliberately derived after measured smoothing and is frozen
        // when a speech level is unavailable, so it cannot synthesize output.
        if let presentation, !staticTrace {
            let attack = max(0, level - previousMeasuredLevel)
            previousMeasuredLevel = level
            let targetDepth = Self.ribbonDepthEnergy(
                level: level,
                transient: min(1, attack / 0.035),
                activity: presentation.activity
            )
            let easing = targetDepth > depthPulse ? 0.28 : 0.08
            depthPulse += (targetDepth - depthPulse) * easing
        } else if presentation != nil {
            previousMeasuredLevel = level
            depthPulse = 0
        } else {
            depthPulse = 0
        }

        // --- ease dynamics + color toward the current state (0.06) ---
        let tg = Self.targets[state]!
        let (tr, tgc, tb) = Self.colors[state]!
        // Item 10 follow-up: `staticTrace` freezes the easing too. Removing
        // the `dyn.base` pin (item 10) left `base` easing 0.004 -> 0.016
        // once per draw call even when nothing was arriving, so a trace
        // with no measured audio thickened four-fold across successive
        // draws -- caught by testUnavailableSpeechRendersIdenticallyAcrossTime
        // as an 11329 vs 11409 byte render. Zeroing `speed` stopped lateral
        // motion but not this, so the comment below claiming motion stops
        // dead was only two-thirds true. Freezing instead of snapping to
        // `tg.base`: snapping would pop the trace the moment audio stopped,
        // and holding the last value is what "nothing is arriving" looks
        // like. Measured audio is unaffected -- staticTrace is false then.
        if !staticTrace {
            dyn.base += (tg.base - dyn.base) * 0.06
            dyn.speed += (tg.speed - dyn.speed) * 0.06
            dyn.alpha += (tg.alpha - dyn.alpha) * 0.06
            dyn.glow += (tg.glow - dyn.glow) * 0.06
            dyn.cr += (tr - dyn.cr) * 0.06
            dyn.cg += (tgc - dyn.cg) * 0.06
            dyn.cb += (tb - dyn.cb) * 0.06
        }

        if let presentation {
            // §7 colours, one source (AudioPresentationTuning, closure C2.4).
            let color = presentation.activity == .user ? AudioPresentationTuning.userRGB :
                (presentation.activity == .assistant || presentation.activity == .thinking ?
                    AudioPresentationTuning.assistantRGB : AudioPresentationTuning.neutralRGB)
            dyn.cr = color.0; dyn.cg = color.1; dyn.cb = color.2
            dyn.alpha = presentation.activity == .offline ? 0.16 : 0.65
            dyn.glow = staticTrace ? 0 : 0.4
            // Item 10: `base` and `speed` were pinned to 0.004 and 0.45 —
            // the first is the `.offline` target, so the resting thickness
            // was the one meant for a dead connection, and the second runs
            // the wobble at under half the legacy speaking rate. Both now
            // ease to the per-state targets above like the legacy path.
            // `staticTrace` still stops motion dead, which is what keeps a
            // trace with nothing arriving honest.
            if staticTrace {
                dyn.speed = 0
                p1 = 0; p2 = 0; p3 = 0
            }
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
            ((presentation?.activity == .thinking || presentation?.activity == .listening) && !reduceMotion
                ? 0.004 * (1 + sin(t * 0.9)) : 0)
        let voice: Double
        if let presentation {
            let gain = presentation.activity == .user
                ? AudioPresentationTuning.measuredInputGain
                : AudioPresentationTuning.measuredOutputGain
            voice = level * gain
        } else {
            voice = state == .speaking ? level * AudioPresentationTuning.measuredOutputGain : 0
        }
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
        let depthSpan = presentation == nil
            ? 0
            : h * AudioPresentationTuning.depthSpanFraction * depthPulse

        let r = dyn.cr, g = dyn.cg, b = dyn.cb

        // Item 10b: the lobe width is tunable on the adaptive path (Debug ▸
        // Wave level windows). The legacy rollback keeps the constant so it
        // stays the known quantity a rollback exists to be.
        let widthFraction = presentation == nil ? 0.11 : AudioPresentationTuning.waveWidthFraction
        let layers = presentation == nil ? Self.legacyLayers : Self.depthLayers
        for layer in layers {
            var path = Path()
            var x = 0.0
            var first = true
            while x <= w {
                // Super-Gaussian window: tight central plateau (middle
                // ~10% of the width holds >=94% of peak at the default
                // 0.11), fast falloff.
                let perspective = presentation == nil
                    ? 1.0
                    : 1.0 + layer.depth * 0.08 * depthPulse
                let envWidth = max(1, widthFraction * w * perspective)
                let env = exp(-pow((x - cx) / envWidth, 4))
                // slow speech-like wobble along the trace
                let mod = 0.65 + 0.35 * sin(0.012 * x * layer.fMul + t * 6.3 * dyn.speed + layer.po)
                let y = cy + layer.depth * depthSpan + env * amp * layer.aMul * mod *
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
            // accent cyan; approximated with blurred echo strokes. Front
            // layers receive a small additional lift when measured audio
            // has depth, while the no-level path remains unchanged.
            let layerGlow = min(1, glow + depthPulse * (layer.depth > 0 ? 0.16 : 0.08))
            if layerGlow > 0.05 {
                var glowContext = context
                glowContext.addFilter(.blur(radius: 13 * layerGlow))
                glowContext.stroke(
                    path,
                    with: .color(Color(red: presentation == nil ? 44 / 255 : r / 255,
                                       green: presentation == nil ? 201 / 255 : g / 255,
                                       blue: presentation == nil ? 1 : b / 255)
                        .opacity(0.75 * layerGlow * layer.aMul)),
                    style: StrokeStyle(lineWidth: layer.width * (2 + depthPulse * 0.35), lineJoin: .round)
                )
            }
            // One broad, low-opacity halo creates the shallow volumetric
            // read. It is driven by measured depthPulse, so idle/listening
            // and unavailable speech do not gain a fake speaking glow.
            if presentation != nil && !staticTrace && depthPulse > 0.03 {
                var volumeContext = context
                volumeContext.addFilter(.blur(radius: 18 + 8 * depthPulse))
                volumeContext.stroke(
                    path,
                    with: .color(Color(red: r / 255, green: g / 255, blue: b / 255)
                        .opacity(0.12 * depthPulse * layer.aMul)),
                    style: StrokeStyle(lineWidth: layer.width * 3.0, lineJoin: .round)
                )
            }
            context.stroke(path, with: .color(color),
                           style: StrokeStyle(
                            lineWidth: layer.width * (presentation == nil ? 1 : 1 + max(0, layer.depth) * depthPulse * 0.35),
                            lineJoin: .round
                           ))
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
