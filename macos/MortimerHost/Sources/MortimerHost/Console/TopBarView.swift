import SwiftUI
import JarvisKit

/// Interface cleanup Phase 2: the console's one floating capsule. Brand, the
/// workspace switcher (the embedded ConsoleActionBar), the degraded-capability
/// chip, the latest console result, Glance, Command-K, Inspect, pop-in buttons
/// while popped, and an overflow menu for what is rarely needed (Disconnect,
/// Voice, Wake word, Sounds, Open display). Connecting lives beside the orb on
/// the disconnected screen, so the overflow never offers Connect.
struct TopBarView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(DrawerState.self) private var drawer
    @Environment(DisplayWindowStore.self) private var displayWindow
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(ConsoleNoticeState.self) private var notices: ConsoleNoticeState?
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = true
    @State private var soundsOn = Sounds.enabled
    @State private var showingPalette = false

    let coordinator: ConsoleActionCoordinator?

    init(coordinator: ConsoleActionCoordinator? = nil) {
        self.coordinator = coordinator
    }

    var body: some View {
        HStack(spacing: 12) {
            brand
            ConsoleActionBar(coordinator: coordinator, embedded: true)
                .layoutPriority(1)
            capabilityChip
            resultNotice
            Spacer(minLength: 8)
            GlanceButton()
            paletteButton
            drawerToggle
            if displayWindow.isWindowOpen {
                popInButton(help: "Bring the display back into this window") {
                    drawer.placementRef?.closeDisplay()
                }
            }
            if drawer.isPoppedOut {
                popInButton(help: "Bring the panels back into this window") {
                    drawer.placementRef?.popInDrawer()
                }
            }
            overflowMenu
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .mortimerGlass(.panel)
        .padding([.horizontal, .top], 12)
        .sheet(isPresented: $showingPalette) { paletteSheet }
    }

    // MARK: Rules (pure, tested)

    /// What the overflow offers. Connect is deliberately absent.
    enum OverflowItem: Hashable {
        case disconnect
        case connecting
        case voice
        case wakeWord(on: Bool)
        case sounds(on: Bool)
        case openDisplay
        case commandMenu
    }

    static func overflowItems(connection: JarvisClient.ConnectionState, hasVoices: Bool,
                              wakeWordAvailable: Bool, wakeWordOn: Bool,
                              soundsOn: Bool) -> [OverflowItem] {
        var items: [OverflowItem] = []
        switch connection {
        case .connected: items.append(.disconnect)
        case .connecting: items.append(.connecting)
        default: break
        }
        if hasVoices { items.append(.voice) }
        if wakeWordAvailable { items.append(.wakeWord(on: wakeWordOn)) }
        items.append(.sounds(on: soundsOn))
        items.append(.openDisplay)
        items.append(.commandMenu)
        return items
    }

    // MARK: Brand

    // .brand — mono, letterspaced, cyan, with the breathing dot
    // (App.css .brand::before, brand-breathe 3.2s).
    private var brand: some View {
        HStack(spacing: 10) {
            BreathingDot()
            Text("MORTIMER")
                .font(.system(size: 13, weight: .semibold, design: .monospaced))
                .kerning(5.2)   // letter-spacing: 0.4em at 13px
                .foregroundStyle(AppTheme.accent)
                .shadow(color: AppTheme.accentDim, radius: 6)
        }
        .fixedSize()
    }

    // MARK: Console result summary (moved here from the old action row)

    @ViewBuilder
    private var resultNotice: some View {
        if let result = notices?.consoleResult {
            Text(result.summary)
                .font(.caption)
                .lineLimit(1)
                .foregroundStyle(result.status == "error" ? AppTheme.red : AppTheme.text.opacity(0.7))
                .layoutPriority(-1)   // the switcher keeps its room
        }
    }

    // CapabilityChip.tsx — renders ONLY when at least one agent reports
    // fallback:true; a clean boot shows no chip at all.
    @ViewBuilder
    private var capabilityChip: some View {
        let degraded = agentRuns.capabilityAgents.filter { $0.fallback }
        if !degraded.isEmpty {
            Text("⚠ \(degraded.count == 1 ? degraded[0].displayName : "\(degraded.count) agents") degraded")
                .font(.caption)
                .foregroundStyle(AppTheme.attn)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .mortimerGlass(.chip)
                .help(degraded.map {
                    "\($0.displayName): assigned \($0.profile ?? "a profile"), " +
                    "running on \($0.resolvedModel ?? "the fallback model") instead"
                }.joined(separator: "\n"))
        }
    }

    // MARK: Command-K

    private var paletteButton: some View {
        Button { showingPalette = true } label: {
            Text("⌘K")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(AppTheme.textDim)
        }
        .keyboardShortcut("k", modifiers: .command)
        .help("Command menu (⌘K)")
        .accessibilityLabel("Command menu")
        .accessibilityIdentifier("console.commandMenu")
    }

    private var paletteSheet: some View {
        CommandPaletteView(commands: paletteCommands,
                           onRun: { command in
                               showingPalette = false
                               run(command.action)
                           },
                           onClose: { showingPalette = false })
    }

    private var paletteCommands: [CommandPalette.Command] {
        var connected = false
        var connecting = false
        switch client.state {
        case .connected: connected = true
        case .connecting: connecting = true
        default: break
        }
        return CommandPalette.commands(connected: connected, connecting: connecting,
                                       wakeWordAvailable: client.wakeWordAvailable,
                                       wakeWordOn: client.wakeWordOn, soundsOn: soundsOn,
                                       inspectOpen: drawer.isOpen,
                                       compactConversation: compactConversation)
    }

    private func run(_ action: CommandPalette.Action) {
        switch action {
        case .view(let target): go(target)
        case .toggleInspect: toggleInspect()
        case .openLog:
            drawer.isOpen = true
            drawer.setTab("transcript")
        case .openDisplay: drawer.placementRef?.openDisplay()
        case .connect: Task { await client.connect() }
        case .disconnect: Task { await client.disconnect() }
        case .toggleWakeWord: Task { await client.setWakeWord(!client.wakeWordOn) }
        case .toggleSounds: toggleSounds()
        case .toggleExpandVoice: compactConversation.toggle()
        }
    }

    // Same path ConsoleActionBar uses, with the same store fallbacks.
    private func go(_ target: String) {
        if let coordinator { _ = coordinator.executePointer(.viewSet, target: target); return }
        switch target {
        case "conversation": workspace.returnToConversation()
        case "results": workspace.returnToWorkspace()
        case "atlas": workspace.openAtlas()
        case "memory": workspace.openMemoryGraph()
        case "skills": workspace.openSkills()
        case "workflows": workspace.openWorkflows()
        default: break
        }
    }

    // MARK: Overflow

    private var overflowMenu: some View {
        let items = Self.overflowItems(connection: client.state, hasVoices: !client.voices.isEmpty,
                                       wakeWordAvailable: client.wakeWordAvailable,
                                       wakeWordOn: client.wakeWordOn, soundsOn: soundsOn)
        return Menu {
            ForEach(items, id: \.self) { item in
                overflowRow(item)
            }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More")
        .accessibilityLabel("More")
        .accessibilityIdentifier("console.more")
    }

    @ViewBuilder
    private func overflowRow(_ item: OverflowItem) -> some View {
        switch item {
        case .disconnect:
            Button("Disconnect") { Task { await client.disconnect() } }
        case .connecting:
            Button("Connecting…") {}.disabled(true)
        case .voice:
            Menu("Voice") {
                Picker("Voice", selection: Binding(
                    get: { client.currentVoice },
                    set: { client.send(.voiceSet(voice: $0)) }
                )) {
                    ForEach(client.voices, id: \.id) { voice in
                        Text(voice.label).tag(voice.id)
                    }
                }
                .pickerStyle(.inline)
            }
        case .wakeWord(let on):
            Button(on ? "Wake word on" : "Wake word off") {
                Task { await client.setWakeWord(!client.wakeWordOn) }
            }
        case .sounds(let on):
            Button(on ? "Sounds on" : "Sounds off") { toggleSounds() }
        case .openDisplay:
            Button("Open display") { drawer.placementRef?.openDisplay() }
        case .commandMenu:
            Button("Command menu…  ⌘K") { showingPalette = true }
        }
    }

    private func toggleSounds() {
        soundsOn.toggle()
        Sounds.enabled = soundsOn
        if soundsOn { Sounds.play(.boot) }
    }

    // MARK: Inspect

    // The single drawer toggle (App.tsx:546-569): label changes with
    // state, aggregate dot while closed (attention amber outranks the
    // cyan live/new signal).
    private var drawerToggle: some View {
        Button { toggleInspect() } label: {
            HStack(spacing: 6) {
                Text(inspectTitle)
                if inspectDotShown {
                    Circle()
                        .fill(attention ? AppTheme.attn : AppTheme.accent)
                        .frame(width: 6, height: 6)
                        .shadow(color: attention ? AppTheme.attn : AppTheme.accent, radius: 4)
                }
            }
        }
        .help(drawer.isPoppedOut
              ? "Panels are on the display screen — click to focus/move"
              : "Inspect agents, runs, output and the log (Esc closes · T opens the Log)")
        .accessibilityLabel(inspectTitle)
        .accessibilityValue(inspectDotDescription)
        .accessibilityIdentifier("console.inspect")
    }

    /// The dot only shows on the closed, docked drawer's button.
    private var inspectDotShown: Bool {
        !drawer.isOpen && !drawer.isPoppedOut && dotVisible
    }

    /// WS-37: the dot is the only sign a drawer result arrived, so it is
    /// spoken too. Empty when no dot shows.
    private var inspectDotDescription: String {
        guard inspectDotShown else { return "" }
        if attention { return "Needs attention" }
        if drawer.outputDot { return "New output" }
        return "Agent working"
    }

    private func toggleInspect() {
        if drawer.isPoppedOut {
            // DP5: while popped, refocus/re-place the popped window rather
            // than toggling the hidden in-page drawer.
            drawer.placementRef?.popOutDrawer()
        } else {
            drawer.isOpen.toggle()
        }
    }

    /// Interface cleanup Phase 1: the drawer is the back room, behind a
    /// labelled Inspect button. "Close Inspect" names what it closes.
    private var inspectTitle: String {
        if drawer.isPoppedOut { return "Inspect ⧉" }
        return drawer.isOpen ? "Close Inspect" : "Inspect"
    }

    private var attention: Bool { displayResults.hasPendingDraft }
    private var dotVisible: Bool {
        agentRuns.selfEditRunning || drawer.outputDot || attention
    }

    private func popInButton(help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text("↩︎")
        }
        .help(help)
    }
}

/// App.css brand-breathe — the 3.2s opacity cycle on the brand dot.
private struct BreathingDot: View {
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @State private var dim = false
    var body: some View {
        Circle()
            .fill(AppTheme.accent)
            .frame(width: 8, height: 8)
            .shadow(color: AppTheme.accent, radius: 5)
            .opacity(reduceMotion ? 1 : (dim ? 0.5 : 1))
            .onAppear {
                startBreathingIfAllowed()
            }
            .onChange(of: reduceMotion) { _, isReduced in
                if isReduced {
                    withAnimation(nil) { dim = false }
                } else {
                    startBreathingIfAllowed()
                }
            }
    }

    private func startBreathingIfAllowed() {
        guard !reduceMotion else { return }
        withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
            dim = true
        }
    }
}
