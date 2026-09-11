import SwiftUI
import JarvisKit

/// APP plan §3 P13 + parity sweep 2026-08-30 — the command-deck stage,
/// matched to web/src/components/OrbField.tsx: agent satellites (cards,
/// pentagon layout) + beams + the M.O.R.T.I.M.E.R. readout with
/// STATE_LABEL / thinking shimmer / armed + attention glow + live
/// captions + ambient strip + system vitals + wake ripple, all over the
/// full-window VoiceWave (the wave owns voice display).
struct AgentLayoutEntry {
    let key: String
    let label: String
    let x: Double   // percent of stage width
    let y: Double   // percent of stage height
}

/// agentLayout.ts:48-54, verbatim.
// 2026-09-06 — six satellites, not five: `app_builder` split out of
// `developer`. Rebalanced from a pentagon to an even hexagon (Larry's
// call) rather than bolting a sixth point onto the old shape. The
// angular ORDER of the original five is preserved, so nothing crosses
// the field; each moves a few percent and the new one takes the vacant
// bottom vertex. Centre (50,50), radius 29. Keep in sync with
// web/src/agentLayout.ts.
let AGENT_LAYOUT: [AgentLayoutEntry] = [
    AgentLayoutEntry(key: "developer", label: "Developer", x: 50, y: 21),
    AgentLayoutEntry(key: "analyst", label: "Analyst", x: 79, y: 36),
    AgentLayoutEntry(key: "systems", label: "Systems", x: 79, y: 64),
    AgentLayoutEntry(key: "app_builder", label: "App Builder", x: 50, y: 79),
    AgentLayoutEntry(key: "librarian", label: "Librarian", x: 21, y: 64),
    AgentLayoutEntry(key: "scheduler", label: "Scheduler", x: 21, y: 36),
]

struct OrbFieldView: View {
    let voiceState: VoiceState
    var compactPresentation = false
    var hidesLettering = false
    @EnvironmentObject private var client: JarvisClient
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DrawerState.self) private var drawer
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(ConversationStore.self) private var conversation
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
        GeometryReader { geo in
            if compactPresentation {
                compactReadout
            } else {
            ZStack {
                // Faint center radial (command-deck.css .orb-field).
                RadialGradient(colors: [AppTheme.accent.opacity(0.05), .clear],
                               center: .center, startRadius: 0,
                               endRadius: min(geo.size.width, geo.size.height) * 0.6)

                // E4 — ambient signs of life, top-left.
                AmbientStripView(connected: connected)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .padding(16)

                // Machine vitals, bottom-right — nothing when healthy.
                SystemVitalsView(connected: connected)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(16)

                // Wake burst: expanding ring from the field center.
                if ripplePulse > 0 {
                    WakeRipple().id(ripplePulse)
                }

                // Beams: satellite -> centre, lit while that agent works;
                // brief fade-out afterglow when it settles (beam-done).
                Canvas { context, size in
                    let center = CGPoint(x: size.width / 2, y: size.height / 2)
                    for agent in AGENT_LAYOUT {
                        let from = CGPoint(x: size.width * agent.x / 100,
                                           y: size.height * agent.y / 100)
                        var path = Path()
                        path.move(to: from)
                        path.addLine(to: center)
                        if isWorking(agent.key) {
                            context.stroke(path, with: .color(AppTheme.accent.opacity(0.55)), lineWidth: 1.5)
                        } else if let done = agentRuns.lastCompleted[agent.key] {
                            // beam-fade 2.4s ease-out.
                            let age = now.timeIntervalSince(done.doneAt)
                            if age < 2.4 {
                                let opacity = 0.5 * (1 - age / 2.4)
                                context.stroke(path, with: .color(AppTheme.accent.opacity(opacity)), lineWidth: 1)
                            }
                        }
                    }
                }
                .allowsHitTesting(false)

                // The five satellites at their pentagon positions, with
                // the E2 staggered entrance per connect.
                ForEach(Array(AGENT_LAYOUT.enumerated()), id: \.element.key) { index, agent in
                    satellite(agent)
                        .position(x: geo.size.width * agent.x / 100,
                                  y: geo.size.height * agent.y / 100)
                        .modifier(BootFadeIn(
                            pulse: bootPulse,
                            delay: 0.2 + Double(index) * 0.08,
                            restingOpacity: isWorking(agent.key) ? 1.0 : 0.9
                        ))
                }

                // The centre readout (OrbField.tsx .orb-center).
                centerReadout

                // Live captions / first-run hint, lower third.
                captions
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, geo.size.height * 0.08)

                // F4 — the speaker-gate "voice not recognized" chip, same
                // bottom-of-stage position, amber, auto-fading.
                if let notice = notices.speakerGateNotice {
                    Text(notice)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(AppTheme.attn)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .mortimerGlass(.chip)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
                        .padding(.bottom, geo.size.height * 0.08 + 60)
                        .transition(.opacity)
                        .allowsHitTesting(false)
                }

                // 2026-09-05 — the default output device moved (AirPods)
                // and the bot's voice did not follow (AudioOutputMonitor).
                // Same chip idiom, but interactive and persistent: it
                // carries the one fix this WebRTC build allows.
                if let notice = notices.audioOutputNotice {
                    HStack(spacing: 10) {
                        Text(notice)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(AppTheme.attn)
                            .lineLimit(1)
                        Button("Reconnect") {
                            notices.clearAudioOutputNotice()
                            Task { await client.reconnect() }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .foregroundStyle(AppTheme.accent)
                        .help("Open a new session so Mortimer's voice plays on the new output device")
                        Button {
                            notices.clearAudioOutputNotice()
                        } label: {
                            Text("×").font(.system(size: 13, design: .monospaced))
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(AppTheme.textDim)
                        .help("Keep the current session")
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .mortimerGlass(.chip)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, geo.size.height * 0.08 + 96)
                    .transition(.opacity)
                }

                // 2026-09-05 — the input got repointed to a rate-matching
                // mic at connect (AirPods 24 kHz-mic fix). Informational,
                // auto-fading; the correction already happened.
                if let notice = notices.audioInputNotice {
                    Text(notice)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(AppTheme.textDim)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .mortimerGlass(.chip)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
                        .padding(.bottom, geo.size.height * 0.08 + 60)
                        .transition(.opacity)
                        .allowsHitTesting(false)
                }
            }
        }
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

    /// Compact layout reuses the same status, caption and satellite owners.
    /// Scrolling keeps every notice and agent reachable in a narrow voice rail.
    private var compactReadout: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                centerReadout
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
                captions
                ForEach(AGENT_LAYOUT, id: \.key) { agent in satellite(agent) }
                AmbientStripView(connected: connected)
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
                Text(thinkingVisible ? "Thinking" : voiceState.label)
                    .textCase(.uppercase)
                    .kerning(3.3)   // letter-spacing: 0.3em at 11px
            }
            .font(.system(size: 11, design: .monospaced))
            .foregroundStyle(labelColor)
            .shadow(color: voiceState == .speaking ? AppTheme.accentDim : .clear, radius: 5)
        }
        .allowsHitTesting(false)
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

    // MARK: - Live captions (OrbField.tsx:338-367 + E8 first-run hint)

    private var lastUser: ConversationEntry? {
        conversation.entries.last {
            $0.role == "user" && !$0.text.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }

    private var lastAssistant: ConversationEntry? {
        conversation.entries.last {
            $0.role == "assistant" && !$0.text.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }

    @ViewBuilder
    private var captions: some View {
        if lastUser == nil && lastAssistant == nil && connected {
            // E8 — connected, nothing said yet; replaced forever by the
            // first caption.
            captionPanel {
                Text("Try: \"What's the weather?\" · \"Show me the runs\" · \"Remind me in twenty minutes\"")
                    .font(.system(size: 11, design: .monospaced))
                    .kerning(0.7)
                    .foregroundStyle(AppTheme.textDim)
            }
        } else if lastUser != nil || lastAssistant != nil {
            captionPanel {
                VStack(spacing: 4) {
                    if let user = lastUser {
                        Text("You — \(truncateCaption(user.text, AppTuning.captionMaxUser))")
                            .font(.system(size: 11, design: .monospaced))
                            .kerning(0.7)
                            .foregroundStyle(AppTheme.textDim)
                    }
                    if let bot = lastAssistant {
                        Text(truncateCaption(bot.text, AppTuning.captionMaxBot))
                            .font(.system(size: 13))
                            .foregroundStyle(AppTheme.text)
                            .shadow(color: AppTheme.accentFaint, radius: 7)
                    }
                }
            }
        }
    }

    private func captionPanel<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .multilineTextAlignment(.center)
            .frame(maxWidth: 900)
            .padding(.horizontal, 18)
            .padding(.vertical, 10)
            .mortimerGlass(.chip)
            .padding(.horizontal, 24)
            .allowsHitTesting(false)
    }

    private func truncateCaption(_ s: String, _ max: Int) -> String {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        return t.count > max ? String(t.prefix(max - 1)) + "…" : t
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
    @State private var expanded = false
    var body: some View {
        Circle()
            .strokeBorder(AppTheme.accent, lineWidth: 2)
            .frame(width: 300, height: 300)
            .scaleEffect(expanded ? 1.6 : 0.85)
            .opacity(expanded ? 0 : 0.9)
            .onAppear {
                withAnimation(.easeOut(duration: 0.9)) { expanded = true }
            }
            .allowsHitTesting(false)
    }
}

/// E2 one-shot entrance: opacity 0 → resting, after `delay`, replayed
/// whenever `pulse` changes (the React key trick, native form).
private struct BootFadeIn: ViewModifier {
    let pulse: Int
    let delay: Double
    let restingOpacity: Double
    @State private var visible = false

    func body(content: Content) -> some View {
        content
            .opacity(visible ? restingOpacity : (pulse == 0 ? restingOpacity : 0))
            .onAppear { visible = true }
            .onChange(of: pulse) { _, _ in
                visible = false
                withAnimation(.easeIn(duration: 0.35).delay(delay)) { visible = true }
            }
    }
}

/// App.css dot-pulse — opacity 0.35 ↔ 1 cycle while active.
private struct DotPulse: ViewModifier {
    let active: Bool
    let period: Double
    @State private var dim = false

    func body(content: Content) -> some View {
        content
            .opacity(active && dim ? 0.35 : 1)
            .onChange(of: active, initial: true) { _, isActive in
                if isActive && period > 0 {
                    withAnimation(.easeInOut(duration: period / 2).repeatForever(autoreverses: true)) {
                        dim = true
                    }
                } else {
                    withAnimation(.linear(duration: 0.1)) { dim = false }
                }
            }
    }
}
