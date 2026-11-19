import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md, Phase 1.
@MainActor
final class InterfaceCleanupPhase1Tests: XCTestCase {
    private func client() -> JarvisClient {
        JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
    }

    private func host<V: View>(_ root: V, width: CGFloat, height: CGFloat) -> (NSHostingView<V>, NSWindow) {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: width, height: height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        return (view, window)
    }

    /// Labels, values, titles and "id:" identifiers, each element once.
    private func accessible(_ root: Any) -> (text: [String], controls: [String: NSObject]) {
        var seen = Set<ObjectIdentifier>()
        var text: [String] = []
        var controls: [String: NSObject] = [:]
        func visit(_ value: Any) {
            guard let object = value as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            for name in ["accessibilityLabel", "accessibilityValue", "accessibilityTitle"] {
                let selector = NSSelectorFromString(name)
                guard object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue() else { continue }
                let string = (raw as? String) ?? (raw as? NSAttributedString)?.string ?? ""
                if !string.isEmpty { text.append(string); if controls[string] == nil { controls[string] = object } }
            }
            let ident = NSSelectorFromString("accessibilityIdentifier")
            if object.responds(to: ident), let string = object.perform(ident)?.takeUnretainedValue() as? String,
               !string.isEmpty { text.append("id:" + string) }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                values.forEach(visit)
            }
        }
        visit(root)
        return (text, controls)
    }

    private func press(_ control: NSObject) -> Bool {
        let selector = NSSelectorFromString("accessibilityPerformPress")
        guard control.responds(to: selector) else { return false }
        typealias Press = @convention(c) (AnyObject, Selector) -> Bool
        return unsafeBitCast(control.method(for: selector), to: Press.self)(control, selector)
    }

    private func withSavedDrawerDefaults(_ body: () throws -> Void) rethrows {
        let keys = ["mortimer.drawer.tab", "mortimer.drawer.open", "mortimer.drawer.width"]
        let saved = keys.map { ($0, UserDefaults.standard.object(forKey: $0)) }
        defer {
            for (key, value) in saved {
                if let value { UserDefaults.standard.set(value, forKey: key) }
                else { UserDefaults.standard.removeObject(forKey: key) }
            }
        }
        try body()
    }

    private func listening() -> VoicePresentationState {
        VoicePresentationState(activity: .listening, userLevel: 0, outputLevel: nil,
                               microphoneMuted: false, assistantSpeaking: false)
    }

    // MARK: Sizes

    func testRailIs260AndOrbSlotIs220() {
        XCTAssertEqual(AdaptiveLayoutMetrics.voiceRailWidth, 260)
        XCTAssertEqual(AdaptiveLayoutMetrics.railOrbSlotHeight, 220)
        XCTAssertEqual(AdaptiveLayoutMetrics.minimumRailStageWidth, 773)
    }

    func testRailModeAtCommonWindowWidths() {
        func mode(window: Double, drawer: Double?) -> AdaptiveLayoutMode {
            let stage = window - (drawer.map { $0 + AppTuning.drawerHandleWidth } ?? 0)
            return AdaptiveStageView.mode(showsConversation: true, compactConversation: true,
                                          wideWindow: window >= AppTuning.wideLayoutMinWidth, stageWidth: stage)
        }
        XCTAssertEqual(mode(window: 900, drawer: nil), .bottom)
        XCTAssertEqual(mode(window: 1180, drawer: nil), .rail)
        XCTAssertEqual(mode(window: 1280, drawer: nil), .rail)
        XCTAssertEqual(mode(window: 1280, drawer: 400), .rail, "default window with the drawer at its default width")
        XCTAssertEqual(mode(window: 1440, drawer: 400), .rail)
        XCTAssertEqual(mode(window: 1180, drawer: 400), .bottom, "770 pt of stage is 3 pt short of the 773 pt rail minimum")
        XCTAssertEqual(mode(window: 1440, drawer: 720), .bottom)
    }

    // MARK: Status line

    func testNotConnectedOffersConnectAndNothingElse() {
        for connection in [JarvisClient.ConnectionState.offline, .failed("synthetic")] {
            let status = OrbStatus.derive(connection: connection, presentation: listening(), needsYou: true,
                audioOutputNotice: "output moved", speakerGateNotice: "gate", audioInputNotice: "input")
            XCTAssertEqual(status.action, .connect)
            XCTAssertFalse(status.text.lowercased().contains("mic"))
        }
        XCTAssertEqual(OrbStatus.derive(connection: .offline, presentation: listening(), needsYou: false,
            audioOutputNotice: nil, speakerGateNotice: nil, audioInputNotice: nil).text, "Not connected")
    }

    func testConnectedStatusPriority() {
        func derive(needsYou: Bool = false, output: String? = nil, gate: String? = nil, input: String? = nil,
                    connection: JarvisClient.ConnectionState = .connected,
                    presentation: VoicePresentationState? = nil) -> OrbStatus {
            OrbStatus.derive(connection: connection, presentation: presentation ?? listening(), needsYou: needsYou,
                             audioOutputNotice: output, speakerGateNotice: gate, audioInputNotice: input)
        }
        XCTAssertEqual(derive(), OrbStatus(text: "Listening", tone: .quiet, action: nil))
        XCTAssertEqual(derive(needsYou: true, output: "Output moved", gate: "gate", input: "input"),
                       OrbStatus(text: "Output moved", tone: .attention, action: .reconnectAudio))
        XCTAssertEqual(derive(needsYou: true, gate: "gate", input: "input"),
                       OrbStatus(text: "Needs your approval", tone: .attention, action: nil))
        XCTAssertEqual(derive(gate: "Voice not recognized", input: "input"),
                       OrbStatus(text: "Voice not recognized", tone: .attention, action: nil))
        XCTAssertEqual(derive(input: "Mic set to MacBook Air"),
                       OrbStatus(text: "Mic set to MacBook Air", tone: .quiet, action: nil))
        XCTAssertEqual(derive(connection: .connecting).text, "Connecting")
        XCTAssertEqual(derive(input: "Mic set to MacBook Air", connection: .connecting).text, "Mic set to MacBook Air")
        let muted = VoicePresentationState(activity: .muted, userLevel: nil, outputLevel: nil,
                                           microphoneMuted: true, assistantSpeaking: false)
        XCTAssertEqual(derive(presentation: muted).text, "Muted")
        let overlap = VoicePresentationState(activity: .user, userLevel: 0.4, outputLevel: 0.3,
                                             microphoneMuted: false, assistantSpeaking: true)
        XCTAssertEqual(derive(presentation: overlap).text, "Hearing you · Mortimer still speaking")
    }

    func testRenderedStatusLineShowsAnEnabledConnectButton() throws {
        var connects = 0
        let status = OrbStatus.derive(connection: .offline, presentation: listening(), needsYou: false,
                                      audioOutputNotice: nil, speakerGateNotice: nil, audioInputNotice: nil)
        let (view, window) = host(OrbStatusLine(status: status, onConnect: { connects += 1 })
            .frame(width: 260).preferredColorScheme(.dark), width: 260, height: 140)
        defer { closeRenderingFixtureWindow(window) }
        let found = accessible(view)
        XCTAssertTrue(found.text.contains("Not connected"), "\(found.text)")
        XCTAssertTrue(found.text.contains("id:orb.connect"), "\(found.text)")
        let button = try XCTUnwrap(found.controls["Connect to Mortimer"], "\(found.text)")
        XCTAssertTrue(press(button))
        XCTAssertEqual(connects, 1)
    }

    func testAudioOutputNoticeKeepsReconnectAndDismiss() throws {
        var reconnects = 0, dismissals = 0
        let status = OrbStatus(text: "Audio output moved", tone: .attention, action: .reconnectAudio)
        let (view, window) = host(OrbStatusLine(status: status, onReconnectAudio: { reconnects += 1 },
                                                onDismissNotice: { dismissals += 1 })
            .frame(width: 260).preferredColorScheme(.dark), width: 260, height: 160)
        defer { closeRenderingFixtureWindow(window) }
        let found = accessible(view)
        XCTAssertTrue(press(try XCTUnwrap(found.controls["Reconnect"], "\(found.text)")))
        XCTAssertTrue(press(try XCTUnwrap(found.controls["Dismiss"], "\(found.text)")))
        XCTAssertEqual([reconnects, dismissals], [1, 1])
    }

    // MARK: Empty state

    func testEmptyThreadGivesNoMicrophonePromptWhileNotConnected() {
        XCTAssertNil(ConversationThreadView.emptyStatePrompt(offline: true))
        let prompt = ConversationThreadView.emptyStatePrompt(offline: false)
        XCTAssertEqual(prompt, "Hold Space to talk, or type a request below.")
        XCTAssertFalse(prompt?.contains("microphone controls") ?? true)
    }

    func testOfflineStageShowsConnectAndNoPromptToSpeak() {
        let (view, window) = host(AdaptiveStageView(voiceState: .offline, wideWindow: true)
            .environment(WorkspaceStore()).environment(ConversationStore()).environment(AgentRunStore())
            .environment(ConsoleNoticeState()).environment(DisplayResultStore())
            .environment(ShareCoordinator()).environment(DisplayWindowStore()).environment(DrawerState())
            .environmentObject(client()).environment(\.mortimerReduceMotion, true)
            .foregroundStyle(AppTheme.text).background(AppTheme.bg).preferredColorScheme(.dark),
            width: 1280, height: 700)
        defer { closeRenderingFixtureWindow(window) }
        let text = accessible(view).text
        XCTAssertTrue(text.contains("Not connected"), "\(text)")
        XCTAssertTrue(text.contains("Connect to Mortimer"), "\(text)")
        for retired in ["Use the microphone controls to start a conversation.", "Ready",
                        "Hold Space to talk, or type a request below.", "Microphone muted", "Wake word armed",
                        "Current time", "Mortimer"] {
            XCTAssertFalse(text.contains(retired), "offline stage still shows \(retired): \(text)")
        }
        for agent in ["DEVELOPER", "ANALYST", "SYSTEMS", "APP BUILDER", "LIBRARIAN", "SCHEDULER"] {
            XCTAssertFalse(text.contains(agent), "agent chip \(agent) is still in the rail: \(text)")
        }
    }

    // MARK: Drawer and Inspect

    func testDrawerIsClosedByDefaultAndRespectsTheSavedChoice() {
        withSavedDrawerDefaults {
            UserDefaults.standard.removeObject(forKey: "mortimer.drawer.open")
            XCTAssertFalse(DrawerState().isOpen, "a fresh install starts with the drawer closed")
            let opened = DrawerState()
            opened.isOpen = true
            XCTAssertEqual(UserDefaults.standard.string(forKey: "mortimer.drawer.open"), "true")
            XCTAssertTrue(DrawerState().isOpen, "a drawer the user left open comes back open")
            opened.isOpen = false
            XCTAssertFalse(DrawerState().isOpen)
        }
    }

    func testInspectButtonIsLabelledAndTogglesTheDrawer() throws {
        try withSavedDrawerDefaults {
            let drawer = DrawerState()
            drawer.isOpen = false
            let (view, window) = host(TopBarView()
                .environmentObject(client()).environment(AgentRunStore()).environment(DisplayResultStore())
                .environment(drawer).environment(DisplayWindowStore())
                .environment(\.mortimerReduceMotion, true).preferredColorScheme(.dark), width: 1280, height: 80)
            defer { closeRenderingFixtureWindow(window) }
            var found = accessible(view)
            XCTAssertTrue(found.text.contains("id:console.inspect"), "\(found.text)")
            for retired in ["◧ Panels", "◨ Close", "disconnected", "DISCONNECTED", "error", "ERROR"] {
                XCTAssertFalse(found.text.contains(retired), "top bar still shows \(retired): \(found.text)")
            }
            XCTAssertTrue(press(try XCTUnwrap(found.controls["Inspect"], "\(found.text)")))
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            XCTAssertTrue(drawer.isOpen)
            found = accessible(view)
            XCTAssertNotNil(found.controls["Close Inspect"], "\(found.text)")
        }
    }

    // MARK: Removed duplicates

    func testConsoleHasNoRetiredStringsAndOneKnowledgeEntry() throws {
        try withSavedDrawerDefaults {
            let suite = "cleanup-phase1-" + UUID().uuidString
            let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
            defer { defaults.removePersistentDomain(forName: suite) }
            let drawer = DrawerState()
            drawer.isOpen = false
            let (view, window) = host(ConsoleView().defaultAppStorage(defaults)
                .environmentObject(client()).environment(AgentRunStore()).environment(DisplayResultStore())
                .environment(WorkspaceStore()).environment(ConversationStore()).environment(DisplayWindowStore())
                .environment(drawer).environment(DrawerModels()).environment(AttachmentStore())
                .environment(ShareCoordinator()).environment(ConsoleOverlayState()).environment(ConsoleNoticeState())
                .environment(\.mortimerReduceMotion, true).preferredColorScheme(.dark), width: 1280, height: 800)
            defer { closeRenderingFixtureWindow(window) }
            let text = accessible(view).text
            for retired in ["Command Console", "Add content",
                            "Paste text or an image, choose a file, or drop it here for review.",
                            "Hold SPACE to talk", "SPACE TALK · T TRANSCRIPT",
                            "Use the microphone controls to start a conversation.",
                            "Knowledge Atlas", "Memory graph"] {
                XCTAssertFalse(text.contains(retired), "console still shows \(retired): \(text)")
            }
            XCTAssertEqual(text.filter { $0 == "id:console.knowledge" }.count, 1, "\(text)")
            XCTAssertEqual(text.filter { $0 == "id:console.inspect" }.count, 1, "\(text)")
            for kept in ["Paste content", "Choose content", "Drop text or image files here", "Wake word off"] {
                XCTAssertTrue(text.contains(kept), "console lost \(kept): \(text)")
            }
        }
    }

    func testCarouselHasNoResultsHeadline() throws {
        let store = WorkspaceStore()
        for title in ["First", "Second"] {
            store.receive(WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self, from:
                JSONSerialization.data(withJSONObject: ["title": title, "body": "Synthetic body for \(title)."]))))
        }
        store.select(store.results[0].id)   // as ResultCarouselRenderingTests.workspace() does
        let (view, window) = host(ResultCarouselView(coordinator: nil)
            .environment(store).environment(ShareCoordinator()).environment(DisplayWindowStore())
            .environment(DrawerState()).environmentObject(client()).preferredColorScheme(.dark), width: 700, height: 700)
        defer { closeRenderingFixtureWindow(window) }
        let text = accessible(view).text
        XCTAssertFalse(text.contains("Results"), "the bare Results headline is gone: \(text)")
        XCTAssertTrue(text.contains(where: { $0.hasPrefix("Results, ") }), "the front card keeps its spoken label: \(text)")
        XCTAssertTrue(text.contains("Show all results"), "\(text)")
    }
}
