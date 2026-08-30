import SwiftUI
import JarvisKit

/// APP plan §3 P1, §5 step 1 — MortimerHost is now the real three-window
/// SwiftUI app (the T1.3 view port). One JarvisClient and the app-scope
/// stores/routers live here and survive every window and tab lifecycle;
/// the G1(b) debug list moved to the Debug menu's "Show message log".
@main
struct MortimerHostApp: App {
    @StateObject private var client = JarvisClient()

    @State private var agentRuns = AgentRunStore()
    @State private var displayResults = DisplayResultStore()
    @State private var conversation = ConversationStore()
    @State private var displayWindow = DisplayWindowStore()
    @State private var drawer = DrawerState()
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
                .environment(conversation)
                .environment(displayWindow)
                .environment(drawer)
                .environment(overlay)
                .environment(notices)
                .background(WindowIdentifierSetter(identifier: "console"))
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
                .environment(conversation)
                .environment(drawer)
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
        .commands {
            CommandMenu("Debug") {
                Button("Clear stored token") {
                    KeychainStore.setToken(nil, for: client.config.botURL)
                }
                Button("Show message log") {
                    windowActions.open("debug-log")
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
        let probe = NSView()
        DispatchQueue.main.async {
            probe.window?.identifier = NSUserInterfaceItemIdentifier(identifier)
        }
        return probe
    }
    func updateNSView(_ nsView: NSView, context: Context) {}
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
