import XCTest
import SwiftUI
import AppKit
import JarvisKit
@testable import MortimerHost

/// Closure plan C2 (P3 gaps G05–G10). Pure assertions where the rule is
/// pure; real `NSHostingView` rendering where the gap is "not rendered".
@MainActor
final class AdaptiveInterfaceClosureC2Tests: XCTestCase {
    private func payload(_ title: String) throws -> DisplayPayload {
        try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"title":"\#(title)","body":"Synthetic result body.","surface":"drawer"}"#.utf8))
    }

    // MARK: G07 / G08 — tuning lives in one place

    func testTuningConstantsMatchInterfacePlanSection7() {
        XCTAssertEqual(AppTuning.layoutTransitionSeconds, 0.2)
        XCTAssertEqual(AppTuning.wideLayoutMinWidth, 1180)
        XCTAssertEqual(AppTuning.inspectorSubpaneMinWidth, 820)
        XCTAssertEqual(AppTuning.inspectorWidth, 300)
        XCTAssertEqual(AdaptiveLayoutMetrics.voiceRailWidth, 200)
        XCTAssertEqual(AdaptiveLayoutMetrics.resultContentWidth, 480)
        XCTAssertEqual(AudioPresentationTuning.attackSeconds, 0.040)
        XCTAssertEqual(AudioPresentationTuning.releaseSeconds, 0.180)
        // #2DD4BF and #E07020, the plan's teal and warm orange.
        XCTAssertEqual([AudioPresentationTuning.userRGB.0, AudioPresentationTuning.userRGB.1, AudioPresentationTuning.userRGB.2], [45, 212, 191])
        XCTAssertEqual([AudioPresentationTuning.assistantRGB.0, AudioPresentationTuning.assistantRGB.1, AudioPresentationTuning.assistantRGB.2], [224, 112, 32])
    }

    func testEnvelopeUsesTheTunedAttackAndRelease() {
        // After exactly one attack constant the level reaches 1 - 1/e of the target.
        var envelope = VoiceEnvelope()
        _ = envelope.advance(target: 0, now: 10)
        let attacked = envelope.advance(target: 1, now: 10 + AudioPresentationTuning.attackSeconds)
        XCTAssertEqual(attacked, 1 - exp(-1), accuracy: 0.001)
        var release = VoiceEnvelope()
        _ = release.advance(target: 0, now: 20)
        _ = release.advance(target: 1, now: 30)          // long attack settles near 1
        let released = release.advance(target: 0, now: 30 + AudioPresentationTuning.releaseSeconds)
        XCTAssertEqual(released, (1 - exp(-10 / AudioPresentationTuning.attackSeconds)) * exp(-1), accuracy: 0.001)
    }

    func testTransitionIsSuppressedUnderReduceMotion() {
        XCTAssertNil(AdaptiveTransition.animation(reduceMotion: true))
        // With no pointer button held and no text view focused in this test
        // process, the 200 ms transition is available.
        if NSEvent.pressedMouseButtons == 0, !(NSApplication.shared.keyWindow?.firstResponder is NSTextView) {
            XCTAssertNotNil(AdaptiveTransition.animation(reduceMotion: false))
        }
    }

    // MARK: G09 — the large-wave rule, as amended in §4.1

    func testLargeWaveOnlyWhenReturnedToConversationAndReturnKeepsTheActiveResult() throws {
        let store = WorkspaceStore()
        XCTAssertEqual(AdaptiveStageView.mode(showsConversation: store.showsConversation, compactConversation: false,
                                              wideWindow: true, stageWidth: 1400), .conversation)
        let first = WorkspaceResult(payload: try payload("First"))
        store.receive(first)
        XCTAssertFalse(store.showsConversation, "the first eligible result enters the workspace")
        XCTAssertEqual(AdaptiveStageView.mode(showsConversation: false, compactConversation: false,
                                              wideWindow: true, stageWidth: 1400), .rail)
        XCTAssertEqual(AdaptiveStageView.mode(showsConversation: false, compactConversation: false,
                                              wideWindow: false, stageWidth: 900), .bottom)
        XCTAssertEqual(AdaptiveStageView.mode(showsConversation: false, compactConversation: false,
                                              wideWindow: true, stageWidth: AdaptiveLayoutMetrics.minimumRailStageWidth - 1), .bottom)
        store.returnToConversation()
        XCTAssertTrue(store.showsConversation)
        XCTAssertEqual(store.activeID, first.id, "returning to conversation keeps the selection for Return to workspace")
        XCTAssertEqual(AdaptiveStageView.mode(showsConversation: true, compactConversation: false,
                                              wideWindow: true, stageWidth: 1400), .conversation)
        XCTAssertEqual(AdaptiveStageView.mode(showsConversation: true, compactConversation: true,
                                              wideWindow: true, stageWidth: 1400), .rail,
                       "the user's compact preference keeps the voice region compact even in conversation")
        // A result arriving while the user is in conversation is history + unread, never a mode change.
        let second = WorkspaceResult(payload: try payload("Second"))
        store.receive(second)
        XCTAssertTrue(store.showsConversation)
        XCTAssertEqual(store.activeID, first.id)
        XCTAssertTrue(store.unreadIDs.contains(second.id))
        store.returnToWorkspace()
        XCTAssertFalse(store.showsConversation)
        XCTAssertEqual(store.activeID, first.id)
    }

    // MARK: G10 — production limits and window-store correlation

    func testProductionPinLimitOfTwentyRefusesTheTwentyFirstWithoutEviction() throws {
        let store = WorkspaceStore()   // production defaults: history 20, pins 20
        var pinned: [UUID] = []
        for index in 0..<20 {
            let result = WorkspaceResult(payload: try payload("Pinned \(index)"))
            store.receive(result)
            XCTAssertTrue(store.pin(result.id), "pin \(index) must be accepted")
            pinned.append(result.id)
        }
        let extra = WorkspaceResult(payload: try payload("Twenty-first"))
        store.receive(extra)
        XCTAssertFalse(store.pin(extra.id), "the 21st pin is refused")
        XCTAssertEqual(store.pinnedIDs.count, 20)
        XCTAssertEqual(Set(store.pinnedIDs), Set(pinned), "no existing pin was evicted")
        // Pinned results survive history eviction of unpinned arrivals.
        for index in 0..<30 { store.receive(WorkspaceResult(payload: try payload("Unpinned \(index)"))) }
        for id in pinned { XCTAssertTrue(store.results.contains { $0.id == id }, "pinned result evicted") }
    }

    func testWindowSurfaceResultsShareTheWorkspaceIdentity() throws {
        let workspace = WorkspaceStore(), window = DisplayWindowStore()
        let received = WorkspaceResult(payload: try payload("Radar"))
        workspace.receive(received)
        window.apply(received.payload, workspaceID: received.id)
        XCTAssertEqual(window.panels.first?.workspaceID, received.id)
        XCTAssertEqual(window.panels.first?.workspaceID, workspace.activeID)
        // Closing the central tab leaves the window panel (UI-3) and its identity intact.
        workspace.close(received.id)
        XCTAssertEqual(window.panels.count, 1)
        XCTAssertEqual(window.panels.first?.workspaceID, received.id)
    }

    // MARK: G06 — the barge-in "small label" is rendered

    func testOverlapLabelIsDerivedAndRendered() throws {
        let overlap = VoicePresentationState(activity: .user, userLevel: 0.4, outputLevel: 0.3,
                                             microphoneMuted: false, assistantSpeaking: true)
        XCTAssertEqual(overlap.overlapLabel, "Mortimer still speaking")
        XCTAssertNil(VoicePresentationState(activity: .user, userLevel: 0.4, outputLevel: nil,
                                            microphoneMuted: false, assistantSpeaking: false).overlapLabel)
        XCTAssertNil(VoicePresentationState(activity: .assistant, userLevel: nil, outputLevel: 0.5,
                                            microphoneMuted: false, assistantSpeaking: true).overlapLabel,
                     "the label is only for overlap, not ordinary assistant speech")
        // Rendered truth: the label is drawn in the plan's warm orange, so the
        // bitmap must contain orange pixels during overlap and none without.
        func orangePixels(_ state: VoicePresentationState) throws -> Int {
            let view = NSHostingView(rootView: VoiceOverlapLabel(presentation: state).padding(8).background(Color.black))
            view.frame = NSRect(x: 0, y: 0, width: 300, height: 40)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { window.close() }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            var count = 0
            for y in 0..<bitmap.pixelsHigh {
                for x in 0..<bitmap.pixelsWide {
                    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                    let r = color.redComponent, g = color.greenComponent, b = color.blueComponent
                    if r > 0.5 && g > 0.25 && r > g * 1.2 && g > b * 1.4 { count += 1 }
                }
            }
            return count
        }
        XCTAssertGreaterThan(try orangePixels(overlap), 20, "overlap label must be rendered in warm orange")
        XCTAssertEqual(try orangePixels(VoicePresentationState(activity: .assistant, userLevel: nil, outputLevel: 0.5,
                                                               microphoneMuted: false, assistantSpeaking: true)), 0,
                       "no label outside overlap")
    }

    // MARK: G05 — the compact rail has homes for agent activity and the wake ripple

    func testCompactRailRendersAgentActivityAffordance() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let runs = AgentRunStore()
        runs.apply(try XCTUnwrap(try AppMessage.decode(frame: Data("""
        {"type":"agent","name":"developer","display_name":"Developer","state":"working",
         "run_id":"r-c2","task":"synthetic","model":"fixture","model_fallback":false}
        """.utf8))))
        let view = NSHostingView(rootView: OrbFieldView(voiceState: .listening, compactPresentation: true, hidesLettering: true)
            .environmentObject(client).environment(runs).environment(DrawerState())
            .environment(DisplayResultStore()).environment(ConversationStore()).environment(ConsoleNoticeState())
            .frame(width: 200, height: 600))
        view.frame = NSRect(x: 0, y: 0, width: 200, height: 600)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let labels = accessibilityLabels(in: view)
        XCTAssertTrue(labels.contains("Developer working"), "compact rail must show the working affordance; tree: \(labels)")
        XCTAssertTrue(labels.contains(where: { $0.hasPrefix("DEVELOPER") || $0 == "Developer" }), "satellite still present; tree: \(labels)")
    }

    func testCompactRailPinsClockAboveAgentActivity() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let runs = AgentRunStore()
        runs.apply(try XCTUnwrap(try AppMessage.decode(frame: Data("""
        {"type":"agent","name":"developer","display_name":"Developer","state":"working",
         "run_id":"r-clock","task":"synthetic","model":"fixture","model_fallback":false}
        """.utf8))))
        let view = NSHostingView(rootView: OrbFieldView(voiceState: .listening, compactPresentation: true, hidesLettering: true)
            .environmentObject(client).environment(runs).environment(DrawerState())
            .environment(DisplayResultStore()).environment(ConversationStore()).environment(ConsoleNoticeState())
            .frame(width: 220, height: 640))
        view.frame = NSRect(x: 0, y: 0, width: 220, height: 640)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let labels = accessibilityLabels(in: view)
        let clockIndex = try XCTUnwrap(labels.firstIndex(of: "Current time"),
                                       "clock accessibility element missing; tree: \(labels)")
        let developerIndex = try XCTUnwrap(labels.firstIndex(of: "Developer working"),
                                           "agent accessibility element missing; tree: \(labels)")
        XCTAssertLessThan(clockIndex, developerIndex,
                          "persistent clock must remain before the changing agent/status stack")
    }

    private func accessibilityLabels(in view: NSView) -> [String] {
        var labels: [String] = []
        func visit(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            if element.responds(to: labelSelector),
               let label = element.perform(labelSelector)?.takeUnretainedValue() as? String, !label.isEmpty {
                labels.append(label)
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                children.forEach(visit)
            }
        }
        visit(view)
        return labels
    }

}
