import SwiftUI
import JarvisKit

/// The console topbar, matched to the web's (App.tsx:534-623, parity
/// sweep 2026-08-30): brand with breathing dot · ConnectButton + raw
/// state pill · Voice picker (always visible; "(connect first)" when
/// empty) · CapabilityChip (ONLY when an agent is degraded) · drawer
/// toggle ◧/◨/◪ with the aggregate live/attention dot · ↩︎ pop-in
/// buttons while popped · ⧉ Display.
struct TopBarView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(DrawerState.self) private var drawer
    @Environment(DisplayWindowStore.self) private var displayWindow

    var body: some View {
        HStack(spacing: 16) {
            brand
            connectGroup
            voicePicker
            capabilityChip
            Spacer()
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
            displayButton
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .mortimerGlass(.panel)
        .padding([.horizontal, .top], 12)
    }

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
    }

    // ConnectButton.tsx — button + the raw-state pill.
    private var connectGroup: some View {
        HStack(spacing: 10) {
            Button {
                Task {
                    if case .connected = client.state {
                        await client.disconnect()
                    } else {
                        await client.connect()
                    }
                }
            } label: {
                Text(connectLabel)
                    .foregroundStyle(connectColor)
            }
            .disabled(isConnecting)

            Text(rawState)
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.2)
                .textCase(.uppercase)
                .foregroundStyle(pillColor)
                .padding(.horizontal, 10)
                .padding(.vertical, 3)
                .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(pillColor.opacity(0.4), lineWidth: 1))
        }
    }

    private var isConnecting: Bool {
        if case .connecting = client.state { return true }
        return false
    }

    private var connectLabel: String {
        switch client.state {
        case .offline: return "Connect"
        case .connecting: return "Connecting…"
        case .connected: return "Disconnect"
        case .failed: return "Connect"
        }
    }

    private var connectColor: Color {
        switch client.state {
        case .connected: return AppTheme.red       // .btn-danger
        default: return AppTheme.accent            // .btn-primary
        }
    }

    /// The pill shows the RAW connection state (ConnectButton.tsx:44) —
    /// a diagnostic readout, not a friendly label.
    private var rawState: String {
        switch client.state {
        case .offline: return "disconnected"
        case .connecting: return "connecting"
        case .connected: return "ready"
        case .failed: return "error"
        }
    }

    private var pillColor: Color {
        switch client.state {
        case .connected: return AppTheme.green     // pill-ready
        case .connecting: return AppTheme.amber    // pill-busy
        case .failed: return AppTheme.red          // pill-error
        case .offline: return AppTheme.textDim     // pill-idle
        }
    }

    // VoicePicker.tsx — label + select, ALWAYS visible; disabled with
    // "(connect first)" while the catalog is empty (never hidden).
    private var voicePicker: some View {
        HStack(spacing: 8) {
            Text("VOICE")
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.4)
                .foregroundStyle(AppTheme.textDim)
            if client.voices.isEmpty {
                Picker("", selection: .constant("")) {
                    Text("(connect first)").tag("")
                }
                .pickerStyle(.menu)
                .disabled(true)
                .frame(maxWidth: 160)
            } else {
                Picker("", selection: Binding(
                    get: { client.currentVoice },
                    set: { client.send(.voiceSet(voice: $0)) }
                )) {
                    ForEach(client.voices, id: \.id) { voice in
                        Text(voice.label).tag(voice.id)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 180)
            }
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

    // The single drawer toggle (App.tsx:546-569): label changes with
    // state, aggregate dot while closed (attention amber outranks the
    // cyan live/new signal).
    private var drawerToggle: some View {
        Button {
            if drawer.isPoppedOut {
                // DP5: while popped, the button refocuses/re-places the
                // popped window rather than toggling the hidden in-page
                // drawer.
                drawer.placementRef?.popOutDrawer()
            } else {
                drawer.isOpen.toggle()
            }
        } label: {
            HStack(spacing: 6) {
                Text(drawer.isPoppedOut ? "◪ Panels ⧉" : drawer.isOpen ? "◨ Close" : "◧ Panels")
                if !drawer.isOpen && !drawer.isPoppedOut && dotVisible {
                    Circle()
                        .fill(attention ? AppTheme.attn : AppTheme.accent)
                        .frame(width: 6, height: 6)
                        .shadow(color: attention ? AppTheme.attn : AppTheme.accent, radius: 4)
                }
            }
        }
        .help(drawer.isPoppedOut
              ? "Panels are on the display screen — click to focus/move"
              : "Console panels (Esc closes · T opens the Log)")
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

    private var displayButton: some View {
        Button {
            // Same WindowPlacement path display_popout uses (C5); a click
            // while open re-runs extended-screen placement (App.tsx:604-610).
            drawer.placementRef?.openDisplay()
        } label: {
            Text("⧉ Display")
                .foregroundStyle(displayWindow.isWindowOpen ? AppTheme.accent : AppTheme.textDim)
        }
        .help(displayWindow.isWindowOpen
              ? "Display window is open — click to refocus / move it to the extra screen"
              : "Open the display window (park it on a second monitor)")
    }
}

/// App.css brand-breathe — the 3.2s opacity cycle on the brand dot.
private struct BreathingDot: View {
    @State private var dim = false
    var body: some View {
        Circle()
            .fill(AppTheme.accent)
            .frame(width: 8, height: 8)
            .shadow(color: AppTheme.accent, radius: 5)
            .opacity(dim ? 0.5 : 1)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
                    dim = true
                }
            }
    }
}
