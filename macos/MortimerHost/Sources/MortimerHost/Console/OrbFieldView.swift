import SwiftUI
import JarvisKit

/// Agent identities and display order shared by the compact voice rail and Runs tab.
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

/// §4.3 barge-in indicator (closure C2.2, gap G06): a small violet label
/// that stays while Mortimer is still speaking under the user's teal
/// priority. Internal so a rendering test can host it alone.
struct VoiceOverlapLabel: View {
    let presentation: VoicePresentationState?
    var body: some View {
        if let text = presentation?.overlapLabel {
            Text(text)
                .font(.caption2)
                .foregroundStyle(AudioPresentationTuning.assistantColor)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(text)
                .accessibilityAddTraits(.isStaticText)
        }
    }
}
