import Foundation
import Observation
import JarvisKit

/// App-scope drawer state — the "same setter voice and click both call"
/// (C5). The tab strip's buttons and UICommandRouter both mutate THIS,
/// so voice and click can never diverge.
@MainActor
@Observable
final class DrawerState {
    /// The eight load-bearing tab keys (SideDrawer.tsx TAB_KEYS) —
    /// ui_control.py's TAB_ALIASES resolves server-side, so the client
    /// only ever receives one of these. "costs" added 2026-09-01
    /// (MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9) — kept in lockstep
    /// with jarvis/bot/ui_control.py's UI_TABS in the same commit.
    static let tabKeys = ["repo", "edit", "memory", "runs", "agents", "output", "transcript", "costs"]
    static let tabLabels: [String: String] = [
        "repo": "Repo", "edit": "Edit", "memory": "Memory", "runs": "Runs",
        "agents": "Agents", "output": "Output", "transcript": "Log", "costs": "Costs",
    ]

    var activeTab: String = "repo" {
        didSet { persist(activeTab, forKey: "mortimer.drawer.tab") }
    }
    /// Whether the drawer is popped out as its own window (vs docked in
    /// the console). DP6's popped-state, owned here.
    var isPoppedOut = false
    /// Whether the docked drawer is visible in the console.
    var isOpen = false {
        didSet {
            persist(String(isOpen), forKey: "mortimer.drawer.open")
            if isOpen && activeTab == "output" { outputDot = false }
        }
    }
    /// D12/D13 — the docked drawer's width, drag-resizable and persisted
    /// (SideDrawer.tsx mortimer.drawer.width; same key name carried over).
    var width: Double = AppTuning.drawerDefaultWidth {
        didSet { persist(String(width), forKey: "mortimer.drawer.width") }
    }
    /// D31 — a drawer-routed result arrived while the drawer was open on
    /// a tab other than Output. Set by AppMessageRouter (the auto-open
    /// decision maker), cleared the moment the Output tab is actually
    /// viewed. The topbar toggle and the Output tab's strip dot both
    /// render from this one flag.
    var outputDot = false
    /// Monotonic request token for voice/keyboard tab-strip scrolling. The
    /// strip consumes this event without changing the selected tab.
    private(set) var tabScrollRequest = 0
    private(set) var tabScrollDirection: Int = 0

    /// Set once at app start; lets the docked drawer's own pop-out
    /// button call the same WindowPlacement.popOutDrawer() the voice
    /// command uses (C5 — one setter for click and voice).
    @ObservationIgnored var placementRef: WindowPlacement?

    init() {
        // Persisted prefs (App.tsx D13): validated reads, defaults on
        // anything missing or out of range.
        let d = UserDefaults.standard
        if let tab = d.string(forKey: "mortimer.drawer.tab"), Self.tabKeys.contains(tab) {
            activeTab = tab
        }
        isOpen = d.string(forKey: "mortimer.drawer.open") == "true"
        let storedWidth = d.double(forKey: "mortimer.drawer.width")
        if storedWidth >= AppTuning.drawerMinWidth {
            width = min(storedWidth, AppTuning.drawerMaxWidthCap)
        }
    }

    private func persist(_ value: String, forKey key: String) {
        UserDefaults.standard.set(value, forKey: key)
    }

    func setTab(_ key: String) {
        guard Self.tabKeys.contains(key) else { return }
        activeTab = key
        if key == "output" { outputDot = false }
    }

    @discardableResult
    func scrollTabs(_ direction: String) -> Bool {
        let delta: Int
        switch direction.lowercased() {
        case "left", "back": delta = -1
        case "right", "forward": delta = 1
        default: return false
        }
        tabScrollDirection = delta
        tabScrollRequest &+= 1
        return true
    }

    /// SideDrawer.tsx clampDrawerWidth — [300, min(720, 60% of the
    /// window)], evaluated at drag time.
    static func clampWidth(_ px: Double, windowWidth: Double) -> Double {
        let maxWidth = min(AppTuning.drawerMaxWidthCap, windowWidth * AppTuning.drawerMaxWidthFraction)
        return min(maxWidth, max(AppTuning.drawerMinWidth, px))
    }
}

/// Transient console notices (App.tsx's auto-fading chip pattern):
/// speaker-gate "voice not recognized" (F4) — brief, ambient, no
/// interaction required. Auto-clears after noticeFadeSeconds.
@MainActor
@Observable
final class ConsoleNoticeState {
    private(set) var speakerGateNotice: String?
    private var clearTask: Task<Void, Never>?
    /// 2026-09-05 — "audio output moved to AirPods, Mortimer's voice did
    /// not follow" (JarvisClient.audioOutputChange). NOT auto-fading: it
    /// carries an action (Reconnect) and stays until the user acts,
    /// dismisses it, or the session reconnects on its own.
    private(set) var audioOutputNotice: String?

    func showSpeakerGateNotice(_ text: String) {
        speakerGateNotice = text
        clearTask?.cancel()
        clearTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(AppTuning.noticeFadeSeconds * 1_000_000_000))
            guard !Task.isCancelled else { return }
            self?.speakerGateNotice = nil
        }
    }

    func showAudioOutputNotice(_ text: String) {
        audioOutputNotice = text
    }

    func clearAudioOutputNotice() {
        audioOutputNotice = nil
    }

    /// 2026-09-05 — "Mic set to MacBook Air … " when connect() repointed the
    /// input to dodge the AirPods 24 kHz-mic slowdown (JarvisClient.
    /// audioInputChange). Informational — the fix already happened — so it
    /// AUTO-FADES like the speaker-gate chip, no action.
    private(set) var audioInputNotice: String?
    private var inputClearTask: Task<Void, Never>?
    /// Last bounded Command Console acknowledgement. Keeping the response in
    /// app state lets voice and pointer paths surface the same truthful result
    /// without treating transport receipt as completion.
    private(set) var consoleResult: ConsoleResult?
    /// Presentation toggles are app state so pointer and voice requests
    /// produce the same visible console configuration.
    var captionExpanded = true
    var statusOpen = true

    func showConsoleResult(_ result: ConsoleResult) {
        consoleResult = result
    }

    func showAudioInputNotice(_ text: String) {
        audioInputNotice = text
        inputClearTask?.cancel()
        inputClearTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(AppTuning.noticeFadeSeconds * 2 * 1_000_000_000))
            guard !Task.isCancelled else { return }
            self?.audioInputNotice = nil
        }
    }
}

/// Console overlay state — the floating on-stage panel showing the
/// newest drawer-routed result (the web's floating DisplayPanel).
/// `overlay_dismiss`'s owner (P15).
@MainActor
@Observable
final class ConsoleOverlayState {
    var isVisible = true
    func dismiss() { isVisible = false }
    func show() { isVisible = true }
}

/// The window-open/close actions the router needs. SwiftUI's
/// openWindow/dismissWindow are @Environment values only views can read,
/// so ConsoleView installs them here on appear; tests install spies.
@MainActor
final class WindowActions {
    var open: (String) -> Void = { _ in }
    var dismiss: (String) -> Void = { _ in }
    var openPanel: (ConsolePanel) -> Void = { _ in }
    var dismissPanel: (ConsolePanel) -> Void = { _ in }
    var dismissAllPanels: () -> Void = {}
    var openContentPanel: (ContentPanelID) -> Void = { _ in }
    var dismissContentPanel: (ContentPanelID) -> Void = { _ in }
    var dismissAllContentPanels: () -> Void = {}
}

/// APP plan §3 P15 / review F2, §5 step 5 — the second messageStream()
/// consumer. Applies the EIGHT non-MicControls UI_ACTIONS through the
/// exact same setters the target views' own buttons call. The three
/// MicControls actions (mic_mute/wake_on/wake_off) are owned by
/// JarvisClient itself (CORE N11) and are deliberately NOT handled here
/// (§7.3 testMicActionsNotDoubleHandled).
///
/// A command that changes nothing is a no-op — this router never replies
/// on the client's behalf; the bot's own ui/noop TTS is how "that changed
/// nothing" is communicated (ui_control.py:13).
@MainActor
final class UICommandRouter {
    private var task: Task<Void, Never>?

    let drawer: DrawerState
    let overlay: ConsoleOverlayState
    let windows: WindowActions
    let placement: WindowPlacement
    /// Optional (defaulted for the §7.3 tests' existing constructor
    /// calls): lets overlay_dismiss close the topmost in-console display
    /// panel, the web's exact semantics (DisplayPanel.tsx:351-358).
    let displayWindow: DisplayWindowStore?

    init(drawer: DrawerState, overlay: ConsoleOverlayState, windows: WindowActions,
         placement: WindowPlacement, displayWindow: DisplayWindowStore? = nil) {
        self.drawer = drawer
        self.overlay = overlay
        self.windows = windows
        self.placement = placement
        self.displayWindow = displayWindow
    }

    func start(client: JarvisClient) {
        guard task == nil else { return }
        task = Task {
            for await message in client.messageStream() {
                if case .ui(let command) = message {
                    handle(command)
                }
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    /// P15's dispatch table, verbatim. Internal (not private) so §7.3
    /// can drive it directly without a live stream.
    func handle(_ command: UICommand) {
        switch command.action {
        case "drawer_tab":
            if let tab = command.tab { drawer.setTab(tab) }
        case "drawer_open":
            if let tab = command.tab { drawer.setTab(tab) }
            if drawer.isPoppedOut {
                // already its own window — nothing to open
            } else if !drawer.isOpen {
                drawer.isOpen = true
            }
        case "drawer_close":
            if drawer.isPoppedOut {
                windows.dismiss("drawer")
                drawer.isPoppedOut = false
            } else {
                drawer.isOpen = false
            }
        case "drawer_popout":
            placement.popOutDrawer()
        case "drawer_popin":
            windows.dismiss("drawer")
            drawer.isPoppedOut = false
            drawer.isOpen = true
        case "display_popout":
            placement.openDisplay()
        case "display_close":
            windows.dismiss("display")
        case "overlay_dismiss":
            overlay.dismiss()
            // The web's semantics: dismiss closes the most recent
            // in-page panel when the display window isn't showing them
            // (DisplayPanel.tsx:351-358).
            if let displayWindow, !displayWindow.isWindowOpen,
               let top = displayWindow.panels.last {
                displayWindow.close(id: top.id)
            }
        default:
            // mic_mute/wake_on/wake_off are JarvisClient's (CORE N11) —
            // never double-handled here. Unknown actions are ignored.
            break
        }
    }
}
