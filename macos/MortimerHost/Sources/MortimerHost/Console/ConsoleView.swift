import SwiftUI
import AppKit
import JarvisKit

/// APP plan §3 P1 + parity sweep 2026-08-30 — the console window,
/// matched to the web's App.tsx layout: full-bleed VoiceWave · topbar ·
/// error banner · stage (with in-page display panels while the display
/// window is closed) · docked, drag-resizable drawer · bottombar.
/// Keyboard: T toggles the Log tab (three-case), Escape closes the
/// drawer (App.tsx:512-528), SPACE PTT lives in MicControlsView.
struct ConsoleView: View {
    @EnvironmentObject private var client: JarvisClient
    @Environment(AgentRunStore.self) private var agentRuns
    @Environment(DisplayResultStore.self) private var displayResults
    @Environment(DisplayWindowStore.self) private var displayWindow
    @Environment(DrawerState.self) private var drawer

    private var voiceState: VoiceState {
        VoiceState.derive(state: client.state, botIsSpeaking: client.botIsSpeaking)
    }

    /// The stage's horizontal center in window coordinates — the wave's
    /// peak follows THIS, not the window center, so an open drawer
    /// slides the wave over (VoiceWave.tsx stageCxRef).
    @State private var stageCenterX: CGFloat?
    /// Live width during a resize drag (committed to drawer.width on end).
    @State private var dragWidth: Double?
    /// Pointer over the resize grip — drives the cursor + the highlight.
    @State private var handleHovering = false
    @State private var windowWidth: Double = 1280
    @State private var keyMonitor: Any?

    var body: some View {
        ZStack {
            AppTheme.bg.ignoresSafeArea()
            VoiceWaveView(voiceState: voiceState,
                          stageCenterX: stageCenterX,
                          wakePulse: client.wakePulse)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                TopBarView()
                if case .failed(let why) = client.state {
                    errorBanner(why)
                }
                HStack(spacing: 0) {
                    ZStack {
                        OrbFieldView(voiceState: voiceState)
                        // The web's in-page DisplayPanel stack: window-
                        // surface results float here while the display
                        // window is closed (DisplayPanel.tsx:365 — popup
                        // open means external only).
                        if !displayWindow.isWindowOpen {
                            ForEach(displayWindow.panels) { panel in
                                SingleDisplayPanel(panel: panel)
                                    .frame(maxWidth: .infinity, maxHeight: .infinity,
                                           alignment: .topTrailing)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .onGeometryChange(for: CGRect.self) { proxy in
                        proxy.frame(in: .global)
                    } action: { frame in
                        stageCenterX = frame.midX
                        // While the display window is closed the stage IS
                        // the panels' viewport — what "fit to window" on a
                        // panel's title bar fills (DisplayWindowStore.fit).
                        if !displayWindow.isWindowOpen {
                            displayWindow.viewportSize = frame.size
                        }
                    }
                    if drawer.isOpen && !drawer.isPoppedOut {
                        resizeHandle
                        DrawerView()
                            .frame(width: dragWidth ?? drawer.width)
                            .transition(.move(edge: .trailing))
                    }
                }
                MicControlsView()
            }
        }
        .frame(minWidth: 900, minHeight: 600)
        .foregroundStyle(AppTheme.text)
        .onGeometryChange(for: CGSize.self) { proxy in
            proxy.size
        } action: { size in
            windowWidth = size.width
        }
        .onAppear(perform: installKeyMonitor)
        .onDisappear(perform: removeKeyMonitor)
    }

    private func errorBanner(_ why: String) -> some View {
        Text(why)
            .font(.system(size: 12, design: .monospaced))
            .kerning(0.7)
            .foregroundStyle(AppTheme.red)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(AppTheme.red.opacity(0.08))
            .overlay(Rectangle().fill(AppTheme.red.opacity(0.35)).frame(height: 1),
                     alignment: .bottom)
    }

    /// D11/D12 — the drawer's left-edge resize handle: drag to resize
    /// (clamped 300…min(720, 60%)), double-click resets to the 400pt
    /// default.
    ///
    /// Rewritten 2026-09-05 after "it doesn't let me drag on anything"
    /// (Larry, live). Three things were wrong with the first cut:
    ///
    ///  1. `DragGesture` in the default `.local` space. The handle is laid
    ///     out by the HStack BEFORE the drawer, so every width change
    ///     moves the handle under the pointer — and a `.local` translation
    ///     is re-derived from the handle's CURRENT frame, so after each
    ///     layout pass it reads ≈0, `dragWidth` snaps back to `base`, and
    ///     the drawer twitches instead of following. `.global` measures the
    ///     raw pointer delta, which is what a resize wants.
    ///  2. `.onTapGesture(count: 2)` stacked on the same view as the drag —
    ///     the double-click recogniser sits in front of the drag. It is now
    ///     a `simultaneousGesture`, so a stationary double-click still
    ///     resets and a moving press is only ever a drag.
    ///  3. Nothing said "grab here": a 1pt hairline 8pt away from the
    ///     drawer's glass edge (DrawerView's own padding), no cursor
    ///     change, no hover state. The grip is now the gap itself
    ///     (AppTuning.drawerHandleWidth; DrawerView drops its leading
    ///     padding when docked), the hairline hugs the panel edge, it
    ///     brightens on hover/drag, and the pointer becomes ↔.
    private var resizeHandle: some View {
        let active = handleHovering || dragWidth != nil
        return Rectangle()
            .fill(Color.clear)
            .frame(width: AppTuning.drawerHandleWidth)
            .overlay(alignment: .trailing) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(active ? AppTheme.accent : AppTheme.hairline)
                    .frame(width: active ? 2 : 1)
                    .padding(.vertical, 24)
            }
            .contentShape(Rectangle())
            .onHover { hovering in
                handleHovering = hovering
                // set(), not push/pop: onHover enter/exit is not guaranteed
                // to pair (the grip moves under the pointer mid-drag), and
                // an unbalanced push leaves a stale ↔ on the cursor stack.
                if hovering {
                    NSCursor.resizeLeftRight.set()
                } else if dragWidth == nil {
                    NSCursor.arrow.set()
                }
            }
            .gesture(
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { value in
                        // drawer.width is NOT mutated until onEnded, so it is
                        // the stable base for the whole drag.
                        dragWidth = DrawerState.clampWidth(
                            drawer.width - value.translation.width, windowWidth: windowWidth)
                        NSCursor.resizeLeftRight.set()
                    }
                    .onEnded { _ in
                        if let dragWidth { drawer.width = dragWidth }
                        dragWidth = nil
                        if !handleHovering { NSCursor.arrow.set() }
                    }
            )
            .simultaneousGesture(
                TapGesture(count: 2).onEnded {
                    drawer.width = DrawerState.clampWidth(
                        AppTuning.drawerDefaultWidth, windowWidth: windowWidth)
                }
            )
            .help("Drag to resize the panels · double-click to reset")
    }

    // T / Escape (App.tsx:512-528): T = three-case Log toggle; Escape
    // closes the drawer. isTypingTarget guard so a text field keeps its
    // keys; e.repeat ignored.
    private func installKeyMonitor() {
        guard keyMonitor == nil else { return }
        // Capture the drawer OBJECT — the monitor closure outlives any
        // one render of this view struct.
        let drawer = self.drawer
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.isARepeat || isTypingTarget() { return event }
            switch event.keyCode {
            case 17:   // T
                if drawer.isOpen && drawer.activeTab == "transcript" {
                    drawer.isOpen = false
                } else {
                    drawer.setTab("transcript")
                    drawer.isOpen = true
                }
                return nil
            case 53:   // Escape
                if drawer.isOpen {
                    drawer.isOpen = false
                    return nil
                }
                return event
            default:
                return event
            }
        }
    }

    private func removeKeyMonitor() {
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor) }
        keyMonitor = nil
    }
}
