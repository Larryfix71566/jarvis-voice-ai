import XCTest
import SwiftUI
import AppKit
import Vision
import JarvisKit
@testable import MortimerHost

@MainActor
private func compactConversationAccessibilityLabels(in root: Any) -> [String] {
    var labels: [String] = []
    func visit(_ value: Any) {
        if let element = value as? NSAccessibilityProtocol {
            if let label = element.accessibilityLabel(), !label.isEmpty { labels.append(label) }
            for child in element.accessibilityChildren() ?? [] { visit(child) }
            return
        }
        guard let object = value as? NSObject else { return }
        let label = NSSelectorFromString("accessibilityLabel")
        if object.responds(to: label),
           let text = object.perform(label)?.takeUnretainedValue() as? String {
            labels.append(text)
        }
        let children = NSSelectorFromString("accessibilityChildren")
        if object.responds(to: children),
           let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
            values.forEach(visit)
        }
    }
    visit(root)
    return labels
}

@MainActor
private func renderedText(in view: NSView) throws -> String {
    let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
    view.cacheDisplay(in: view.bounds, to: bitmap)
    let image = try XCTUnwrap(bitmap.cgImage)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .fast
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: image).perform([request])
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: " ").split(whereSeparator: \.isWhitespace).joined()
}

@MainActor
final class CompactConversationTests: XCTestCase {
    func testV2CompactOrbOmitsTranscriptButKeepsConversationAndNotices() throws {
        _ = NSApplication.shared
        let suite = "compact-transcript-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(2, forKey: "mortimer.interface.layoutVersion")

        let conversation = ConversationStore()
        let userText = "Transcript sentinel user 6f3a"
        let assistantText = "Transcript sentinel Mortimer 4a82"
        func entry(_ id: String, _ role: String, _ text: String) throws -> ConversationEntry {
            try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
                ["id": id, "role": role, "text": text, "createdAt": 1234.0]))
        }
        conversation.set([try entry("user", "user", userText),
                          try entry("assistant", "assistant", assistantText)])
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let notices = ConsoleNoticeState()
        notices.showAudioInputNotice("Audio input notice remains visible")
        let compact = NSHostingView(rootView: OrbFieldView(voiceState: .offline, compactPresentation: true)
            .defaultAppStorage(defaults)
            .environment(conversation)
            .environment(AgentRunStore())
            .environment(DrawerState())
            .environment(DisplayResultStore())
            .environment(notices)
            .environmentObject(client)
            .preferredColorScheme(.dark))
        compact.frame = NSRect(x: 0, y: 0, width: 260, height: 900)
        let compactWindow = NSWindow(contentRect: compact.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        compactWindow.isReleasedWhenClosed = false
        compactWindow.contentView = compact
        compactWindow.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(compactWindow) }
        compact.layoutSubtreeIfNeeded(); compactWindow.contentView?.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))

        let compactOCR = try renderedText(in: compact)
        XCTAssertFalse(compactOCR.contains(userText.filter { !$0.isWhitespace }) || compactOCR.contains(assistantText.filter { !$0.isWhitespace }), "v2 compact orb must not duplicate transcript: \(compactOCR)")
        let compactText = try renderedText(in: compact)
        XCTAssertTrue(compactText.contains("Audioinputnoticeremainsvisible"),
                      "non-transcript audio notices remain visible: \(compactText)")
        XCTAssertEqual(conversation.entries.map(\.text), [userText, assistantText], "removing compact captions must not alter transcript storage")

        // An arriving live transcription after the compact view is mounted
        // also stays out of that view while remaining in the shared store.
        let arrivingText = "Transcript sentinel arriving update 9c17"
        conversation.set([try entry("user", "user", userText),
                          try entry("assistant", "assistant", assistantText),
                          try entry("user-update", "user", arrivingText)])
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        XCTAssertFalse(try renderedText(in: compact).contains(arrivingText.filter { !$0.isWhitespace }), "live updates must not reappear in v2 compact")
        XCTAssertEqual(conversation.entries.last?.text, arrivingText)

        // The existing main-window Log remains the readable transcript home.
        let log = NSHostingView(rootView: LogTab()
            .environment(conversation)
            .environment(AgentRunStore())
            .environment(DrawerModels())
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        log.frame = NSRect(x: 0, y: 0, width: 720, height: 520)
        let logWindow = NSWindow(contentRect: log.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        logWindow.isReleasedWhenClosed = false
        logWindow.contentView = log
        logWindow.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(logWindow) }
        log.layoutSubtreeIfNeeded(); logWindow.contentView?.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        let logOCR = try renderedText(in: log)
        XCTAssertTrue(logOCR.contains(userText.filter { !$0.isWhitespace }), "main transcript keeps the user entry: \(logOCR)")
        XCTAssertTrue(logOCR.contains(assistantText.filter { !$0.isWhitespace }), "main transcript keeps the Mortimer entry: \(logOCR)")
        XCTAssertTrue(logOCR.contains(arrivingText.filter { !$0.isWhitespace }), "main transcript receives later entries: \(logOCR)")
    }

    func testLegacyCompactOrbRetainsTranscriptCaptions() throws {
        _ = NSApplication.shared
        let suite = "legacy-compact-transcript-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(1, forKey: "mortimer.interface.layoutVersion")
        let conversation = ConversationStore()
        let userText = "Legacy user caption b931"
        let assistantText = "Legacy Mortimer caption e527"
        let entries = try [
            JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
                ["id": "legacy-user", "role": "user", "text": userText, "createdAt": 1234.0])),
            JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
                ["id": "legacy-assistant", "role": "assistant", "text": assistantText, "createdAt": 1235.0])),
        ]
        conversation.set(entries)
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let view = NSHostingView(rootView: OrbFieldView(voiceState: .offline, compactPresentation: true)
            .defaultAppStorage(defaults)
            .environment(conversation)
            .environment(AgentRunStore())
            .environment(DrawerState())
            .environment(DisplayResultStore())
            .environment(ConsoleNoticeState())
            .environmentObject(client)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 260, height: 520)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        view.layoutSubtreeIfNeeded(); window.contentView?.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        let legacyOCR = try renderedText(in: view)
        XCTAssertTrue(legacyOCR.contains("Legacyusercaptionb931"), "legacy compact layout retains the user caption: \(legacyOCR)")
        XCTAssertTrue(legacyOCR.contains("LegacyMortimercaptione527"), "legacy compact layout retains Mortimer’s caption: \(legacyOCR)")
    }

    func testSavedCompactPreferenceChangesNativeConversationPresentation() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let suite = "compact-conversation-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let workspace = WorkspaceStore()
        let result = WorkspaceResult(payload: try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"body":"Preserved research","surface":"drawer"}"#.utf8)))
        workspace.receive(result)
        workspace.rememberScroll(240, for: result.id)
        workspace.returnToConversation()
        let conversation = ConversationStore()
        let userTranscript = "Main conversation user 7d21"
        let assistantTranscript = "Main conversation Mortimer 39b4"
        func transcriptEntry(_ id: String, _ role: String, _ text: String) throws -> ConversationEntry {
            try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(withJSONObject:
                ["id": id, "role": role, "text": text, "createdAt": 1234.0]))
        }
        conversation.set([try transcriptEntry("stage-user", "user", userTranscript),
                          try transcriptEntry("stage-assistant", "assistant", assistantTranscript)])
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        for width in [512, 1000] {
        for compact in [true, false] {
            defaults.set(compact, forKey: "mortimer.interface.compactConversation")
            defaults.set(2, forKey: "mortimer.interface.layoutVersion")
            let view = NSHostingView(rootView: AdaptiveStageView(voiceState: .offline, wideWindow: width == 1000)
                .defaultAppStorage(defaults).environment(workspace).environmentObject(client)
                .environment(AgentRunStore()).environment(DrawerState()).environment(DisplayResultStore())
                .environment(conversation).environment(ConsoleNoticeState())
                .environment(\.mortimerReduceMotion, true)
                .foregroundStyle(AppTheme.text).background(AppTheme.bg).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: CGFloat(width), height: 600)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
            defer { closeRenderingFixtureWindow(window) }
            window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            var labels: [String] = []
            var controls: [String: NSObject] = [:]
            func visit(_ value: Any) {
                guard let object = value as? NSObject else { return }
                let label = NSSelectorFromString("accessibilityLabel")
                if object.responds(to: label), let text = object.perform(label)?.takeUnretainedValue() as? String { labels.append(text); controls[text] = object }
                let children = NSSelectorFromString("accessibilityChildren")
                if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] {
                    values.forEach(visit)
                }
            }
            visit(view)
            if compact {
                let stageOCR = try renderedText(in: view)
                XCTAssertFalse(stageOCR.contains(userTranscript.filter { !$0.isWhitespace }) || stageOCR.contains(assistantTranscript.filter { !$0.isWhitespace }),
                               "layout v2 compact stage at width \(width) must not repeat transcript: \(stageOCR)")
            } else {
                let stageOCR = try renderedText(in: view)
                XCTAssertTrue(stageOCR.contains(userTranscript.filter { !$0.isWhitespace }), "expanded main conversation retains the user transcript: \(stageOCR)")
                XCTAssertTrue(stageOCR.contains(assistantTranscript.filter { !$0.isWhitespace }), "expanded main conversation retains Mortimer’s transcript: \(stageOCR)")
            }
            XCTAssertTrue(labels.contains(compact ? "Expand voice" : "Keep voice compact"), "Missing mode control: \(labels)")
            XCTAssertTrue(labels.contains("Voice activity — user teal, Mortimer orange"),
                          "compact voice display must remain discoverable to VoiceOver: \(labels)")
            XCTAssertTrue(workspace.showsConversation)
            XCTAssertEqual(defaults.bool(forKey: "mortimer.interface.compactConversation"), compact)
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".build/interface-fixtures")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
                .write(to: directory.appendingPathComponent("conversation-\(width)-\(compact ? "compact" : "expanded").png"))
            let modeLabel = compact ? "Expand voice" : "Keep voice compact"
            for label in [modeLabel, "Memory graph", "Return to workspace"] {
                let control = try XCTUnwrap(controls[label])
                let rect = try XCTUnwrap(control.value(forKey: "accessibilityFrame") as? NSValue).rectValue
                let viewport = window.convertToScreen(view.convert(view.bounds, to: nil))
                XCTAssertTrue(viewport.insetBy(dx: -1, dy: -1).contains(rect), "Clipped \(label) at \(width): \(rect)")
                XCTAssertGreaterThan(rect.width, 20)
            }
            let toggle = try XCTUnwrap(controls[modeLabel])
            let press = NSSelectorFromString("accessibilityPerformPress")
            XCTAssertTrue(toggle.responds(to: press))
            if toggle.responds(to: press) {
                typealias Press = @convention(c) (AnyObject, Selector) -> Bool
                let action = unsafeBitCast(toggle.method(for: press), to: Press.self)
                XCTAssertTrue(action(toggle, press))
                RunLoop.main.run(until: Date().addingTimeInterval(0.2))
                XCTAssertEqual(defaults.bool(forKey: "mortimer.interface.compactConversation"), !compact)
                labels.removeAll(); controls.removeAll(); visit(view)
                XCTAssertTrue(labels.contains(compact ? "Keep voice compact" : "Expand voice"))
                let toggledOCR = try renderedText(in: view)
                if compact {
                    XCTAssertTrue(toggledOCR.contains(userTranscript.filter { !$0.isWhitespace }), "expanding voice exposes the main user transcript: \(toggledOCR)")
                    XCTAssertTrue(toggledOCR.contains(assistantTranscript.filter { !$0.isWhitespace }), "expanding voice exposes Mortimer’s main transcript: \(toggledOCR)")
                } else {
                    XCTAssertFalse(toggledOCR.contains(userTranscript.filter { !$0.isWhitespace }) || toggledOCR.contains(assistantTranscript.filter { !$0.isWhitespace }),
                                   "returning to compact removes duplicate transcript: \(toggledOCR)")
                }
                XCTAssertEqual(workspace.activeID, result.id)
                XCTAssertEqual(workspace.scrollOffsets[result.id], 240)
                XCTAssertTrue(workspace.showsConversation)
            }
        }
        }
    }
}
