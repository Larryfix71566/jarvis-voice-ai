import SwiftUI
import AppKit
import JarvisKit

/// The bottombar (App.tsx:655-659, parity sweep 2026-08-30): MicControls
/// (exact web labels + SPACE push-to-talk) · SoundToggle 🔊/🔇 · hints
/// "SPACE talk · T transcript".
///
/// Mic semantics are the web's (MicControls.tsx): the mic button toggles;
/// SPACE keydown unmutes and keyup ALWAYS mutes (pttOwned guard so a
/// keyup from ordinary typing never mutes); there is deliberately no
/// mic_unmute voice action (U7 — while muted the user cannot be heard;
/// the wake word is the way back). The three ui commands
/// (mic_mute/wake_on/wake_off) are applied by JarvisClient itself (CORE
/// N11); this view binds to that state through the same setters.
struct MicControlsView: View {
    @EnvironmentObject private var client: JarvisClient
    @State private var pttHeld = false
    @State private var pttOwned = false
    @State private var keyMonitor: Any?
    @State private var soundsOn = Sounds.enabled

    private var connected: Bool {
        if case .connected = client.state { return true }
        return false
    }

    private var live: Bool { connected && client.micEnabled }

    var body: some View {
        HStack(spacing: 14) {
            // 🎙 Mic on / 🔇 Mic off (MicControls.tsx:147).
            Button {
                client.setMicEnabled(!client.micEnabled)
            } label: {
                Text(live ? "🎙 Mic on" : "🔇 Mic off")
                    .foregroundStyle(live ? AppTheme.green : AppTheme.textDim)
            }
            .disabled(!connected)

            // .ptt — the dashed hint chip; cyan while held.
            Text(pttHeld ? "Talking…" : "Hold SPACE to talk")
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.4)
                .textCase(.uppercase)
                .foregroundStyle(pttHeld ? AppTheme.accent : AppTheme.textDim)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .overlay(
                    RoundedRectangle(cornerRadius: 2)
                        .strokeBorder(pttHeld ? AppTheme.accentDim : AppTheme.hairline,
                                      style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                )

            // 👂 Wake word on / Wake word off (MicControls.tsx:152-160).
            Button {
                Task { await client.setWakeWord(!client.wakeWordOn) }
            } label: {
                Text(client.wakeWordOn ? "👂 Wake word on" : "Wake word off")
                    .foregroundStyle(client.wakeWordOn ? AppTheme.accent : AppTheme.textDim)
            }
            .disabled(!client.wakeWordAvailable)
            .help("Say \"Mortimer\" to unmute (local openWakeWord sidecar)")

            Spacer()

            // SoundToggle (App.tsx:127 — turning sounds ON plays boot).
            Button {
                soundsOn.toggle()
                Sounds.enabled = soundsOn
                if soundsOn { Sounds.play(.boot) }
            } label: {
                Text(soundsOn ? "🔊" : "🔇")
            }
            .help(soundsOn ? "Sounds on" : "Sounds off")

            // .hints (App.tsx:658).
            Text("SPACE TALK · T TRANSCRIPT")
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.8)
                .foregroundStyle(AppTheme.textDim)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .mortimerGlass(.panel)
        .padding([.horizontal, .bottom], 12)
        .onAppear(perform: installKeyMonitor)
        .onDisappear(perform: removeKeyMonitor)
    }

    // SPACE push-to-talk (MicControls.tsx:37-60): keydown → unmute;
    // keyup → mute (always — muted is PTT's resting state). NSEvent
    // local monitor; a first responder that accepts text (a TextField)
    // keeps its space bar (isTypingTarget guard).
    private func installKeyMonitor() {
        guard keyMonitor == nil else { return }
        // Capture the client OBJECT (not the view struct's env wrapper) —
        // the monitor closure outlives any one render.
        let client = self.client
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .keyUp]) { event in
            guard event.keyCode == 49 else { return event }   // space
            if isTypingTarget() { return event }
            if event.type == .keyDown {
                guard case .connected = client.state, !event.isARepeat else { return nil }
                pttOwned = true
                pttHeld = true
                client.setMicEnabled(true)
                return nil
            } else {
                guard pttOwned else { return event }
                pttOwned = false
                pttHeld = false
                client.setMicEnabled(false)
                return nil
            }
        }
    }

    private func removeKeyMonitor() {
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor) }
        keyMonitor = nil
    }
}

/// The web's isTypingTarget (MicControls.tsx:13-17), native form: the
/// key window's first responder is editing text.
@MainActor
func isTypingTarget() -> Bool {
    guard let responder = NSApp.keyWindow?.firstResponder else { return false }
    return responder is NSTextView || responder is NSTextField
}
