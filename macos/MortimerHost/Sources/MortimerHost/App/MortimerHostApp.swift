import SwiftUI
import JarvisKit

/// APP plan §3 P1, §5 step 1 — MortimerHost is now the real three-window
/// SwiftUI app (the T1.3 view port). One JarvisClient and the app-scope
/// stores/routers live here and survive every window and tab lifecycle;
/// the G1(b) debug list moved to the Debug menu's "Show message log".
@main
struct MortimerHostApp: App {
    @StateObject private var client = JarvisClient()

    init() {
        // Run as a REGULAR foreground application even when launched as a
        // bare executable (`swift run`, Xcode running the SPM target).
        // Measured 2026-08-31: unbundled, the process showed no menu bar,
        // no edge-resize cursors, and native Full Screen was refused even
        // with .fullScreenPrimary held — the window server treats an
        // unactivated, unbundled process as not-quite-an-app. The proper
        // fix is the .app bundle (macos/MortimerHost/scripts/bundle.sh);
        // this is the belt to that suspenders.
        NSApplication.shared.setActivationPolicy(.regular)
        DispatchQueue.main.async {
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
    }

    // C9.5 / G30 — default 1 since 2026-09-17: a fresh install gets the
    // adaptive layout. `Debug ▸ Use previous layout` is retained (L4) so the
    // rollback is a menu press, not a rebuild. C8 is unrun; its unexercised
    // rows are accepted in docs/acceptance/adaptive-interface/C8-open-items.md
    // under Gate G-C8's written-acceptance route.
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 1
    @State private var agentRuns = AgentRunStore()
    @State private var displayResults = DisplayResultStore()
    @State private var workspace = WorkspaceStore()
    @State private var conversation = ConversationStore()
    @State private var displayWindow = DisplayWindowStore()
    @State private var drawer = DrawerState()
    @State private var drawerModels = DrawerModels()
    @State private var overlay = ConsoleOverlayState()
    @State private var notices = ConsoleNoticeState()

    // Non-Observable plumbing, created once for the app's lifetime
    // (@State so a re-initialized App struct cannot orphan the closures
    // the routers hold).
    @State private var windowActions = WindowActions()
    @State private var messageRouter = AppMessageRouter()
    @State private var placement: WindowPlacement?
    @State private var uiRouter: UICommandRouter?
    @State private var started = false

    var body: some Scene {
        Window("Mortimer", id: "console") {
            ConsoleView()
                .environmentObject(client)
                .environment(agentRuns)
                .environment(displayResults)
                .environment(workspace)
                .environment(conversation)
                .environment(displayWindow)
                .environment(drawer)
                .environment(drawerModels)
                .environment(overlay)
                .environment(notices)
                .background(WindowIdentifierSetter(identifier: "console"))
                // C7.5: every session that ends writes its own evidence.
                // The Debug menu item stays for an on-demand reading
                // mid-session, but the gate no longer depends on anyone
                // clicking it — or on the app having a menu bar at all,
                // which a bare-executable launch does not.
                .onChange(of: client.lastSessionAudioLatency) { _, latency in
                    guard let latency else { return }
                    AudioMeterLatencyReport.write(latency, connected: false,
                                                  native: client.isNativeAudio)
                }
                .onAppear(perform: startRoutersOnce)
                .installWindowActions(windowActions)
        }
        // Titled + contentMinSize: the standard traffic lights (incl. the
        // green fullscreen button) and free edge-resizing — the web
        // console lived in a browser window with both, so the native
        // console keeps them (Larry 2026-08-30: windows must fullscreen
        // and resize).
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1280, height: 800)

        Window("Mortimer Display", id: "display") {
            DisplayWindowView()
                .environment(displayWindow)
                .environment(workspace)
                .environment(drawer)
                .environmentObject(client)
                .background(WindowIdentifierSetter(identifier: "display"))
                // The native form of the web's hasLivePopup poll: scene
                // content on screen = window open. Drives the topbar's
                // ⧉ Display active state + ↩︎ pop-in.
                .onAppear { displayWindow.isWindowOpen = true }
                .onDisappear { displayWindow.isWindowOpen = false }
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 900, height: 700)

        Window("Mortimer Drawer", id: "drawer") {
            DrawerView()
                .environmentObject(client)
                .environment(agentRuns)
                .environment(displayResults)
                .environment(workspace)
                .environment(conversation)
                .environment(drawer)
                .environment(drawerModels)
                .background(WindowIdentifierSetter(identifier: "drawer"))
                // A traffic-light close of the popped drawer must flip
                // the console back to docked semantics (the web's
                // heartbeat falling edge, S3) — restore the in-page
                // drawer rather than losing the panels.
                .onDisappear {
                    if drawer.isPoppedOut {
                        drawer.isPoppedOut = false
                        drawer.isOpen = true
                    }
                }
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 440, height: 800)

        Window("Message Log", id: "debug-log") {
            DebugLogView()
                .environmentObject(client)
        }

        // Item 10: the wave's dB windows, dragged while talking.
        Window("Wave Levels", id: "wave-tuning") {
            WaveTuningView()
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 420, height: 380)
        .commands {
            // A guaranteed Full Screen path independent of the green
            // button's mode: sets the behavior and toggles in one step.
            CommandGroup(after: .windowSize) {
                Button("Toggle Full Screen") {
                    if let window = NSApp.keyWindow ?? NSApp.mainWindow {
                        window.collectionBehavior.insert(.fullScreenPrimary)
                        window.toggleFullScreen(nil)
                    }
                }
                .keyboardShortcut("f", modifiers: [.command, .control])
            }
            CommandMenu("Layout") {
                Button("Reset Layout") {
                    ScreenPlacement.shared.resetLayout()
                    drawer.width = AppTuning.drawerDefaultWidth
                }
            }
            CommandMenu("Debug") {
                Button(layoutVersion == 1 ? "Use previous layout" : "Preview adaptive layout") {
                    layoutVersion = layoutVersion == 1 ? 0 : 1
                }
                Divider()
                Button("Clear stored token") {
                    KeychainStore.setToken(nil, for: client.config.botURL)
                }
                Button("Show message log") {
                    windowActions.open("debug-log")
                }
                Button("Wave level windows") {
                    windowActions.open("wave-tuning")
                }
                Divider()
                // Closure C7.5: the meter's own latency, buffer host time to
                // the snapshot the presentation was handed, over the last
                // 60 s. Written where the acceptance record expects it so
                // the gate (p95 under 150 ms) is evidence rather than a
                // remembered number. Nothing is written when the meter has
                // not observed anything — an empty file would read as a
                // measurement of zero.
                Button("Write audio meter latency (P2-latency.json)") {
                    AudioMeterLatencyReport.write(client.audioMeterLatency(),
                                                  connected: client.state == .connected,
                                                  native: client.isNativeAudio)
                }
            }
        }
    }

    /// One-shot wiring the first time the console appears: the routers
    /// need the client + stores, and WindowPlacement needs the
    /// openWindow action ConsoleView installs into `windowActions`.
    private func startRoutersOnce() {
        guard !started else { return }
        started = true
        let placement = WindowPlacement(drawer: drawer, windows: windowActions)
        self.placement = placement
        let router = UICommandRouter(drawer: drawer, overlay: overlay, windows: windowActions,
                                     placement: placement, displayWindow: displayWindow)
        self.uiRouter = router
        messageRouter.start(
            client: client,
            agentRuns: agentRuns,
            displayResults: displayResults,
            displayWindow: displayWindow,
            workspace: workspace,
            conversation: conversation,
            drawer: drawer,
            notices: notices
        )
        router.start(client: client)
        drawer.placementRef = placement
    }
}

/// Stamps the hosting NSWindow's identifier so the ported
/// findHostWindow(kind:)/ScreenPlacement match the scene (P1). SwiftUI
/// does not reliably hand the scene id to NSWindow.identifier verbatim —
/// the exact failure WindowLookup.swift documents — so we set it directly.
struct WindowIdentifierSetter: NSViewRepresentable {
    let identifier: String
    func makeNSView(context: Context) -> NSView {
        WindowProbeView(identifier: identifier)
    }
    func updateNSView(_ nsView: NSView, context: Context) {}
}

/// The probe view that configures its host NSWindow the moment it is
/// attached (viewDidMoveToWindow — reliable, unlike a main-queue hop
/// that can run before the window exists and then silently do nothing).
///
/// Larry 2026-08-30/31: "no resizing or maximum window available" after
/// two SwiftUI-level attempts. This is the AppKit-level guarantee AND the
/// instrumentation to see what AppKit actually has: it logs the window's
/// style mask, min/max size and collection behavior at attach time and
/// again 0.5s later (to catch SwiftUI re-asserting its own values), so
/// the next fix is aimed at a measured cause, not a third theory.
final class WindowProbeView: NSView {
    /// The scene id to stamp (named windowID: NSView already owns
    /// `identifier`, typed NSUserInterfaceItemIdentifier?).
    let windowID: String
    private var configured = false

    init(identifier: String) {
        self.windowID = identifier
        super.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError("unused") }

    private var updateObserver: NSObjectProtocol?
    private var stripCount = 0

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard let window, !configured else { return }
        configured = true
        window.identifier = NSUserInterfaceItemIdentifier(windowID)
        Self.log("attach", windowID, window)
        Self.configure(window)
        Self.log("configured", windowID, window)
        let id = windowID
        // MEASURED 2026-08-31 (logs/mortimerhost-window.log): the window is
        // resizable from the start (the "can't resize" was a screen-filling
        // frame), but SwiftUI STRIPS .fullScreenPrimary again within 0.5s of
        // our setting it — and keeps doing so on its own schedule — so a
        // one-shot insert never survives to the green button. Hold the flag
        // continuously: re-insert whenever the window updates and it is
        // missing. Cheap (a bitmask test per update) and idempotent.
        updateObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didUpdateNotification, object: window, queue: .main
        ) { [weak self, weak window] _ in
            guard let self, let window else { return }
            if !window.collectionBehavior.contains(.fullScreenPrimary) {
                window.collectionBehavior.insert(.fullScreenPrimary)
                self.stripCount += 1
                if self.stripCount <= 3 || self.stripCount % 100 == 0 {
                    Self.log("re-added-fullScreenPrimary#\(self.stripCount)", id, window)
                }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak window] in
            guard let window else { return }
            Self.log("after-0.5s", id, window)
            Self.configure(window)
            Self.log("reasserted", id, window)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) { [weak window] in
            guard let window else { return }
            Self.log("after-5s", id, window)
        }
    }

    deinit {
        if let updateObserver { NotificationCenter.default.removeObserver(updateObserver) }
    }

    static func configure(_ window: NSWindow) {
        window.styleMask.insert([.resizable, .titled, .closable, .miniaturizable])
        window.collectionBehavior.insert(.fullScreenPrimary)
        window.minSize = NSSize(width: 400, height: 300)
        // A maxSize equal to the current size is the one setting that
        // produces exactly "no resizing, no zoom" with a resizable mask.
        window.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude,
                                height: CGFloat.greatestFiniteMagnitude)
        window.contentMinSize = NSSize(width: 400, height: 300)
        window.contentMaxSize = NSSize(width: CGFloat.greatestFiniteMagnitude,
                                       height: CGFloat.greatestFiniteMagnitude)
        window.standardWindowButton(.zoomButton)?.isEnabled = true
    }

    static func log(_ stage: String, _ id: String, _ window: NSWindow) {
        let mask = window.styleMask
        let flags = [
            mask.contains(.resizable) ? "resizable" : "NOT-resizable",
            mask.contains(.titled) ? "titled" : "untitled",
            mask.contains(.fullSizeContentView) ? "fullSizeContent" : "",
            window.collectionBehavior.contains(.fullScreenPrimary) ? "fullScreenPrimary" : "no-fullScreenPrimary",
        ].filter { !$0.isEmpty }.joined(separator: ",")
        let screen = window.screen?.visibleFrame ?? NSScreen.main?.visibleFrame ?? .zero
        // stderr (unbuffered) AND <repo>/logs/mortimerhost-window.log, so the
        // lines can be read off disk without a terminal relay.
        let line = ("[window \(id)] \(stage): class=\(type(of: window)) mask=\(mask.rawValue) [\(flags)] "
              + "screenVisible=\(Int(screen.width))x\(Int(screen.height)) "
              + "resizable=\(window.isResizable) "
              + "frame=\(Int(window.frame.width))x\(Int(window.frame.height)) "
              + "min=\(Int(window.minSize.width))x\(Int(window.minSize.height)) "
              + "max=\(window.maxSize.width > 1e6 ? "inf" : "\(Int(window.maxSize.width))x\(Int(window.maxSize.height))") "
              + "contentMin=\(Int(window.contentMinSize.width))x\(Int(window.contentMinSize.height)) "
              + "contentMax=\(window.contentMaxSize.width > 1e6 ? "inf" : "\(Int(window.contentMaxSize.width))x\(Int(window.contentMaxSize.height))") "
              + "zoomEnabled=\(window.standardWindowButton(.zoomButton)?.isEnabled ?? false) "
              + "zoomHidden=\(window.standardWindowButton(.zoomButton)?.isHidden ?? true)\n")
        FileHandle.standardError.write(Data(line.utf8))
        appendToRepoLog(line)
    }

    /// Append to <repo>/logs/mortimerhost-window.log, locating the repo by
    /// walking up from the executable (…/macos/MortimerHost/.build/…) to
    /// the first directory containing `.git`. Best-effort, never throws.
    static func appendToRepoLog(_ line: String) {
        var dir = URL(fileURLWithPath: Bundle.main.executablePath ?? CommandLine.arguments[0])
            .deletingLastPathComponent()
        for _ in 0..<12 {
            if FileManager.default.fileExists(atPath: dir.appendingPathComponent(".git").path) {
                let logs = dir.appendingPathComponent("logs")
                try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
                let file = logs.appendingPathComponent("mortimerhost-window.log")
                let stamp = ISO8601DateFormatter().string(from: Date())
                if let handle = try? FileHandle(forWritingTo: file) {
                    handle.seekToEndOfFile()
                    handle.write(Data((stamp + " " + line).utf8))
                    try? handle.close()
                } else {
                    try? (stamp + " " + line).write(to: file, atomically: true, encoding: .utf8)
                }
                return
            }
            dir = dir.deletingLastPathComponent()
        }
    }
}

/// Bridges SwiftUI's environment-only openWindow/dismissWindow actions
/// into the app-scope WindowActions the routers use.
private struct WindowActionsInstaller: ViewModifier {
    let actions: WindowActions
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissWindow) private var dismissWindow

    func body(content: Content) -> some View {
        content.onAppear {
            actions.open = { id in openWindow(id: id) }
            actions.dismiss = { id in dismissWindow(id: id) }
        }
    }
}

extension View {
    func installWindowActions(_ actions: WindowActions) -> some View {
        modifier(WindowActionsInstaller(actions: actions))
    }
}

/// The G1(b) debug affordance, preserved (P1): the old harness List,
/// now behind Debug ▸ Show message log.
struct DebugLogView: View {
    @EnvironmentObject private var client: JarvisClient
    @State private var messages: [String] = []
    @State private var subscription: JarvisSubscription?

    var body: some View {
        List(messages.indices, id: \.self) { i in
            Text(messages[i]).font(.system(.caption, design: .monospaced))
        }
        .frame(minWidth: 480, minHeight: 320)
        .onAppear {
            guard subscription == nil else { return }
            subscription = client.subscribe { message in
                messages.append(message.debugDescription)
                if messages.count > JarvisTuning.maxHostMessages {
                    messages.removeFirst(messages.count - JarvisTuning.maxHostMessages)
                }
            }
        }
    }
}
