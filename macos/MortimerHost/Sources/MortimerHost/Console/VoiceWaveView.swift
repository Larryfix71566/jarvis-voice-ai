import SwiftUI
import JarvisKit

/// Agent identities retained for the Runs tab after OrbFieldView's removal.
struct AgentLayoutEntry {
    let key: String
    let label: String
}

let AGENT_LAYOUT: [AgentLayoutEntry] = [
    AgentLayoutEntry(key: "developer", label: "Developer"),
    AgentLayoutEntry(key: "analyst", label: "Analyst"),
    AgentLayoutEntry(key: "systems", label: "Systems"),
    AgentLayoutEntry(key: "app_builder", label: "App Builder"),
    AgentLayoutEntry(key: "librarian", label: "Librarian"),
    AgentLayoutEntry(key: "scheduler", label: "Scheduler"),
]

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
    var needsYou: Bool = false
    /// Production orb slots opt in; rendering-only hosts need no client.
    var interactive: Bool = false

    /// Adaptive presentation supplies current truth on each display tick so
    /// stale measurements expire even when callbacks stop. Nil retains rollback.
    var presentation: (() -> VoicePresentationState)? = nil
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        Group {
            if interactive {
                VoiceWaveClientBridge(voiceState: voiceState, stageCenterX: stageCenterX,
                    wakePulse: wakePulse, needsYou: needsYou, presentation: presentation,
                    reduceMotion: reduceMotion, reduceTransparency: reduceTransparency)
            } else {
                VoiceWaveAnimation(voiceState: voiceState, stageCenterX: stageCenterX,
                    wakePulse: wakePulse, needsYou: needsYou, presentation: presentation,
                    reduceMotion: reduceMotion, reduceTransparency: reduceTransparency)
            }
        }
        // Canvas is not consistently exposed as an accessibility node in
        // compact macOS layouts. Keep one stable host element so the visual
        // channel mapping and current voice state remain discoverable.
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

/// Injects JarvisClient only in production's interactive orb slots. Rendering
/// and visibility fixtures can continue to host the wave without a client.
private struct VoiceWaveClientBridge: View {
    let voiceState: VoiceState
    var stageCenterX: CGFloat?
    var wakePulse: Int
    var needsYou: Bool
    var presentation: (() -> VoicePresentationState)?
    let reduceMotion: Bool
    let reduceTransparency: Bool
    @EnvironmentObject private var client: JarvisClient

    var body: some View {
        VoiceWaveAnimation(voiceState: voiceState, stageCenterX: stageCenterX,
            wakePulse: wakePulse, needsYou: needsYou, presentation: presentation,
            reduceMotion: reduceMotion, reduceTransparency: reduceTransparency,
            micEnabled: { client.micEnabled }, setMicEnabled: { client.setMicEnabled($0) })
    }
}

/// Separates the system accessibility setting from animation scheduling. The
/// same content can be exercised with either setting without changing macOS.
struct VoiceWaveAnimation: View {
    let voiceState: VoiceState
    var stageCenterX: CGFloat? = nil
    var wakePulse: Int = 0
    var needsYou: Bool = false
    var presentation: (() -> VoicePresentationState)? = nil
    let reduceMotion: Bool
    var reduceTransparency = false
    @State private var visible = false
    @State private var windowVisible = false
    @State private var engine = WaveEngine()
    @State private var pointer: CGPoint?
    @State private var pushToTalk = OrbPushToTalkGuard()
    @State private var holdTask: Task<Void, Never>?
    var micEnabled: (() -> Bool)?
    var setMicEnabled: ((Bool) -> Void)?

    var body: some View {
        Group {
            if presentation != nil, reduceMotion {
                // Keep the existing paused Reduced Motion schedule (C6 choice).
                wave(presentation?())
            } else {
                animatedWave
            }
        }
        // C6: the crystal energy orb is a real button, not a decorative Canvas.
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("Tap to toggle the microphone. Hold for 350 milliseconds to push to talk.")
        .accessibilityAction { toggleMic() }
        .onContinuousHover(coordinateSpace: .local) { phase in
            switch phase {
            case .active(let location): pointer = location
            case .ended: pointer = nil
            }
        }
        .gesture(DragGesture(minimumDistance: 0)
            .onChanged { value in
                pointer = value.location
                beginHold()
            }
            .onEnded { _ in endPress() })
        .onDisappear { cancelPress(); engine.suspend() }
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
        .onDisappear { visible = false; cancelPress(); engine.suspend() }
    }

    private func beginHold() {
        guard let setMicEnabled, holdTask == nil,
              pushToTalk.begin(micEnabled: micEnabled?() ?? false) else { return }
        holdTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(350))
            guard !Task.isCancelled, pushToTalk.promote() else { return }
            setMicEnabled(true)
        }
    }

    private func endPress() {
        holdTask?.cancel()
        holdTask = nil
        if let restore = pushToTalk.finish() {
            setMicEnabled?(restore)
        } else {
            toggleMic()
        }
    }

    private func cancelPress() {
        holdTask?.cancel()
        holdTask = nil
        if let restore = pushToTalk.finish() { setMicEnabled?(restore) }
        pointer = nil
    }

    private func toggleMic() {
        setMicEnabled?(!(micEnabled?() ?? false))
        engine.tapRipple()
    }

    private func wave(_ current: VoicePresentationState?) -> some View {
        Canvas { context, size in
            engine.draw(context: &context, size: size,
                        now: ProcessInfo.processInfo.systemUptime,
                        state: voiceState, stageCenterX: stageCenterX,
                        presentation: current, reduceMotion: reduceMotion,
                        pointer: pointer, refraction: !reduceTransparency,
                        needsYou: needsYou)
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
    private let orbEnergy = OrbEnergyState()
    private var rippleStart: Double?

    func tapRipple() { rippleStart = -1 }

    /// Drop transient amplitude and pending wake flashes across invisibility.
    func suspend() {
        last = nil
        level = 0
        userEnvelope = VoiceEnvelope()
        outputEnvelope = VoiceEnvelope()
        atomMotion.suspend()
        wakeFlashStart = 0
        rippleStart = nil
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
              presentation: VoicePresentationState? = nil, reduceMotion: Bool = false,
              pointer: CGPoint? = nil, refraction: Bool = false,
              needsYou: Bool = false) {
        let previous = last
        last = now
        let measuredDt = max(0, min(now - (previous ?? now), 0.1))

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
                     reduceMotion: reduceMotion, staticTrace: staticTrace,
                     pointer: pointer, dt: measuredDt, refraction: refraction,
                     needsYou: needsYou)
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
        let rise = FrameRateIndependentEasing.factor(0.45, dt: measuredDt)
        let fall = FrameRateIndependentEasing.factor(0.06, dt: measuredDt)
        level = target > level ? level + (target - level) * rise
                               : level + (target - level) * fall

        // --- ease dynamics + color toward the current state (0.06 at 60 Hz) ---
        let ease = FrameRateIndependentEasing.factor(0.06, dt: measuredDt)
        let tg = Self.targets[state]!
        let (tr, tgc, tb) = Self.colors[state]!
        dyn.base += (tg.base - dyn.base) * ease
        dyn.speed += (tg.speed - dyn.speed) * ease
        dyn.alpha += (tg.alpha - dyn.alpha) * ease
        dyn.glow += (tg.glow - dyn.glow) * ease
        dyn.cr += (tr - dyn.cr) * ease
        dyn.cg += (tgc - dyn.cg) * ease
        dyn.cb += (tb - dyn.cb) * ease

        p1 += dt * 2.2 * dyn.speed
        p2 -= dt * 3.1 * dyn.speed
        p3 += dt * 5.3 * dyn.speed

        let w = size.width
        let h = size.height

        // Peak centered on the STAGE, eased 0.12 so a drawer snap slides
        // the wave over rather than teleporting it.
        let cxTarget = Double(stageCenterX ?? w / 2)
        cxEased = cxEased < 0 ? cxTarget : cxEased + (cxTarget - cxEased) *
            FrameRateIndependentEasing.factor(0.12, dt: measuredDt)
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

        let r = dyn.cr, g = dyn.g, b = dyn.cb

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
    /// always draws the crystal glass/plasma/comet treatment.
    private func drawAtom(context: inout GraphicsContext, size: CGSize, now: Double,
                          stageCenterX: CGFloat?, userLevel: Double,
                          outputLevel: Double, presentation: VoicePresentationState,
                          reduceMotion: Bool, staticTrace: Bool,
                          pointer: CGPoint?, dt: Double, refraction: Bool,
                          needsYou: Bool) {
        let userEnergy = min(1, max(0, userLevel * AudioPresentationTuning.measuredInputGain))
        let outputEnergy = min(1, max(0, outputLevel * AudioPresentationTuning.measuredOutputGain))
        let phase = atomMotion.advance(now: now, energy: max(userEnergy, outputEnergy),
                                       moving: !staticTrace)
        orbEnergy.advance(activity: presentation.activity,
                          measuredLevel: max(userEnergy, outputEnergy),
                          phase: phase, now: now, dt: dt)
        if rippleStart == -1 { rippleStart = now }
        let rippleAge = rippleStart.map { now - $0 } ?? .infinity
        let ripple = rippleAge < 0.45 ? min(1, max(0, rippleAge / 0.45)) : 0
        if rippleAge >= 0.45 { rippleStart = nil }
        CometOrbRenderer.draw(context: &context, size: size, stageCenterX: stageCenterX,
                              phase: phase, userEnergy: userEnergy,
                              outputEnergy: outputEnergy, activity: presentation.activity,
                              pointer: pointer, ripple: ripple, needsYou: needsYou,
                              reduceMotion: reduceMotion, refraction: refraction,
                              energyState: orbEnergy)
    }
}

// Legacy compact readout retained source-compatible for existing non-orb tests.
// C5/C6 production slots no longer mount it; the energy orb replaces its satellites.
struct OrbFieldView: View {
    let voiceState: VoiceState
    var hidesLettering = false
    var presentation: VoicePresentationState? = nil
    @EnvironmentObject private var client: JarvisClient
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DrawerState.self) private var drawer
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(ConsoleNoticeState.self) private var notices

    /// E2 — boot counter: increments when a connection arrives; keys the
    /// readout/satellite entrance animations so they replay per connect.
    @State private var bootPulse = 0
    @State private var prevState: VoiceState = .offline
    /// Wake ripple replay key (client.wakePulse mirrored so the ripple
    /// view can animate one-shot per pulse).
    @State private var ripplePulse = 0
    /// 0.5s heartbeat driving MIN_WORKING_MS hold expiry re-evaluation.
    @State private var now = Date()

    private var connected: Bool {
        voiceState == .listening || voiceState == .speaking
    }

    var body: some View {
        GeometryReader { _ in
            compactReadout
        }
        .onChange(of: voiceState) { _, next in
            // E2: every connect is an arrival (connecting -> live).
            if prevState == .connecting && (next == .listening || next == .speaking) {
                bootPulse += 1
            }
            prevState = next
        }
        .onChange(of: client.wakePulse) { _, _ in
            ripplePulse += 1
        }
        .task {
            while !Task.isCancelled {
                now = Date()
                try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
    }

    /// The compact rail keeps the transcript in the main conversation surface
    /// instead of repeating captions here.
    /// Scrolling keeps every notice and agent reachable in a narrow voice rail.
    private var compactReadout: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                // The clock is persistent context, not conversation content:
                // keep it pinned to the top of the compact rail so it cannot
                // drift below the agent/status stack as the session grows.
                AmbientStripView(connected: connected)
                ZStack {
                    // C2.1 (gap G05): the wake burst has a home in the rail too.
                    if ripplePulse > 0 {
                        WakeRipple(diameter: 72).id(ripplePulse)
                            .accessibilityLabel("Wake word detected")
                    }
                    centerReadout
                }
                if client.wakeWordOn { Text("Wake word armed").font(.caption) }
                if !client.micEnabled { Text("Microphone muted").foregroundStyle(AppTheme.attn) }
                if attention { Text("Confirmation needed in Output").foregroundStyle(AppTheme.attn) }
                if let notice = notices.speakerGateNotice { Text(notice).foregroundStyle(AppTheme.attn) }
                if let notice = notices.audioOutputNotice {
                    Text(notice).foregroundStyle(AppTheme.attn)
                    HStack {
                        Button("Reconnect") {
                            notices.clearAudioOutputNotice()
                            Task { await client.reconnect() }
                        }
                        Button("Dismiss") { notices.clearAudioOutputNotice() }
                    }
                }
                if let notice = notices.audioInputNotice { Text(notice).font(.caption) }
                ForEach(AGENT_LAYOUT, id: \.key) { agent in
                    HStack(spacing: 8) { compactBeam(agent); satellite(agent) }
                }
                SystemVitalsView(connected: connected)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Working / completion state (OrbField.tsx:104-141, E5)

    private func liveRun(for key: String) -> AgentRun? {
        agentRuns.runs.last { $0.name == key && $0.doneAt == nil }
    }

    /// MIN_WORKING_MS: the working VISUAL holds at least 2.5s from its
    /// start even when the run settles sooner — most delegations finish
    /// in 3-7s and the lit satellite was gone before the eye arrived.
    private func isWorking(_ key: String) -> Bool {
        if liveRun(for: key) != nil { return true }
        if let done = agentRuns.lastCompleted[key],
           now < done.startedAt.addingTimeInterval(AppTuning.minWorkingSeconds) {
            return true
        }
        return false
    }

    // MARK: - Centre readout

    private var thinkingVisible: Bool {
        client.botIsThinking && voiceState != .speaking
    }

    private var attention: Bool { displayResults.hasPendingDraft }
    private var wakeArmed: Bool { client.wakeWordOn }

    private var readoutColor: Color {
        // E1: attention (amber) outranks the armed glow (command-deck.css
        // declaration order).
        if attention { return AppTheme.attn }
        if wakeArmed { return AppTheme.accent }
        return AppTheme.textDim
    }

    private var centerReadout: some View {
        VStack(spacing: 14) {
            if !hidesLettering {
            // "M.O.R.T.I.M.E.R." — per-letter boot cascade (40ms steps),
            // replayed per connect via the bootPulse key.
            HStack(spacing: 0) {
                ForEach(Array("M.O.R.T.I.M.E.R.".enumerated()), id: \.offset) { index, ch in
                    Text(String(ch))
                        .modifier(BootFadeIn(pulse: bootPulse, delay: Double(index) * 0.04, restingOpacity: 1))
                }
            }
            .font(.system(size: 10, design: .monospaced))
            .kerning(5)   // letter-spacing: 0.5em at 10px
            .foregroundStyle(readoutColor)
            .shadow(color: attention ? AppTheme.attnDim : (wakeArmed ? AppTheme.accentDim : .clear),
                    radius: attention ? 7 : 6)

            } else {
                Text("Mortimer").font(.headline).foregroundStyle(readoutColor)
            }

            // .orb-label — dot + STATE_LABEL / Thinking (speech outranks
            // the shimmer).
            HStack(spacing: 8) {
                Circle()
                    .fill(labelColor)
                    .frame(width: 6, height: 6)
                    .modifier(DotPulse(active: dotPulses, period: dotPeriod))
                Text(presentation?.label ?? (thinkingVisible ? "Thinking" : voiceState.label))
                    .textCase(.uppercase)
                    .kerning(3.3)   // letter-spacing: 0.3em at 11px
            }
            .font(.system(size: 11, design: .monospaced))
            .foregroundStyle(labelColor)
            .shadow(color: voiceState == .speaking ? AppTheme.accentDim : .clear, radius: 5)
            VoiceOverlapLabel(presentation: presentation)
            if presentation?.audioLevelUnavailable == true {
                Text("Audio level unavailable").font(.caption2).foregroundStyle(AppTheme.textDim)
            }
        }
        .allowsHitTesting(false)
    }

    /// C2.1 (gap G05): the beam's meaning — "this agent is working now /
    /// just finished" — in a form that fits the compact rail. Same
    /// isWorking / lastCompleted truth as the agent cards.
    private func compactBeam(_ agent: AgentLayoutEntry) -> some View {
        let working = isWorking(agent.key)
        var opacity = 0.0
        var label: String? = nil
        if working {
            opacity = 0.55; label = "\(agent.label) working"
        } else if let done = agentRuns.lastCompleted[agent.key] {
            let age = now.timeIntervalSince(done.doneAt)
            if age < 2.4 { opacity = 0.5 * (1 - age / 2.4); label = "\(agent.label) finished" }
        }
        return Rectangle()
            .fill(AppTheme.accent.opacity(opacity))
            .frame(width: 18, height: 2)
            .accessibilityHidden(label == nil)
            .accessibilityLabel(label ?? "")
    }

    private var labelColor: Color {
        if thinkingVisible { return AppTheme.textDim }
        switch voiceState {
        case .speaking: return AppTheme.accent
        case .listening: return AppTheme.green
        case .connecting: return AppTheme.amber
        case .offline: return AppTheme.textDim
        }
    }

    private var dotPulses: Bool {
        thinkingVisible || voiceState != .offline
    }

    private var dotPeriod: Double {
        if thinkingVisible { return 1.6 }   // think-shimmer
        switch voiceState {
        case .speaking: return 0.9
        case .listening: return 2.4
        case .connecting: return 0.6
        case .offline: return 0
        }
    }

    // MARK: - Satellite card (.satellite, command-deck.css — exact port)

    private func satellite(_ agent: AgentLayoutEntry) -> some View {
        let working = isWorking(agent.key)
        let last = agentRuns.lastCompleted[agent.key]
        let showDone = !working && last != nil

        let dotColor: Color = working ? AppTheme.accent
            : (showDone ? (last!.ok ? AppTheme.green : AppTheme.red) : AppTheme.textDim)
        let nameColor: Color = working ? AppTheme.accent : AppTheme.text
        let borderColor: Color = working ? AppTheme.accentDim : AppTheme.glassBorder

        return Button {
            // E5: satellite click → Runs tab pre-filtered to this agent —
            // the same dispatch "show me the runs" uses.
            agentRuns.requestedAgentFilter = agent.key
            drawer.setTab("runs")
            drawer.isOpen = true
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(dotColor)
                    .frame(width: 10, height: 10)
                    .shadow(color: working || showDone ? dotColor : .clear,
                            radius: working ? 6 : (showDone ? 5 : 0))
                    .modifier(DotPulse(active: working, period: 1.0))
                Text(agent.label.uppercased())
                    .font(.system(size: 10, design: .monospaced))
                    .kerning(2.2)   // .satellite-name letter-spacing: 0.22em
                    .foregroundStyle(nameColor)
                    .shadow(color: working ? AppTheme.accentDim : .clear, radius: 5)
                if let last {
                    Text(last.ok ? "✓" : "✗")
                        .font(.system(size: 10))
                        .foregroundStyle(last.ok ? AppTheme.accent : AppTheme.red)
                        .opacity(0.7)
                }
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 12)
            .background(AppTheme.glassBg)
            .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(borderColor, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 2))
        }
        .buttonStyle(.plain)
        .help(last.map { "Last: \(clampText($0.task, 80))" }
              ?? "No runs yet — click for \(agent.label)'s history")
    }
}

/// command-deck.css .wake-ripple — expanding ring from the field centre,
/// 0.9s ease-out, one-shot (replayed by identity).
private struct WakeRipple: View {
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    var diameter: CGFloat = 300
    @State private var expanded = false
    var body: some View {
        Circle()
            .strokeBorder(AppTheme.accent, lineWidth: 2)
            .frame(width: diameter, height: diameter)
            .scaleEffect(reduceMotion ? 1 : (expanded ? 1.6 : 0.85))
            .opacity(reduceMotion ? 0.65 : (expanded ? 0 : 0.9))
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.easeOut(duration: 0.9)) { expanded = true }
            }
            .transaction { if reduceMotion { $0.animation = nil } }
            .allowsHitTesting(false)
    }
}

/// E2 one-shot entrance: opacity 0 → resting, after `delay`, replayed
/// whenever `pulse` changes (the React key trick, native form).
private struct BootFadeIn: ViewModifier {
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    let pulse: Int
    let delay: Double
    let restingOpacity: Double
    @State private var visible = false

    func body(content: Content) -> some View {
        content
            .opacity(visible ? restingOpacity : (pulse == 0 ? restingOpacity : 0))
            .onAppear { visible = true }
            .onChange(of: pulse) { _, _ in
                guard !reduceMotion else {
                    visible = true
                    return
                }
                visible = false
                withAnimation(.easeIn(duration: 0.35).delay(delay)) { visible = true }
            }
            .onChange(of: reduceMotion) { _, isReduced in
                if isReduced { visible = true }
            }
            .transaction { if reduceMotion { $0.animation = nil } }
    }
}

/// App.css dot-pulse — opacity 0.35 ↔ 1 cycle while active.
private struct DotPulse: ViewModifier {
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    let active: Bool
    let period: Double
    @State private var dim = false

    func body(content: Content) -> some View {
        content
            .opacity(active && dim ? 0.35 : 1)
            .onChange(of: active, initial: true) { _, isActive in
                if isActive && period > 0 && !reduceMotion {
                    startPulsing()
                } else {
                    withAnimation(nil) { dim = false }
                }
            }
            .onChange(of: reduceMotion) { _, isReduced in
                if isReduced || !active || period <= 0 {
                    withAnimation(nil) { dim = false }
                } else {
                    startPulsing()
                }
            }
    }

    private func startPulsing() {
        withAnimation(.easeInOut(duration: period / 2).repeatForever(autoreverses: true)) {
            dim = true
        }
    }
}
