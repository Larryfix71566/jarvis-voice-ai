import XCTest
import SwiftUI
import AppKit
@testable import JarvisKit
@testable import MortimerHost

private final class RetiredResponseTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws {}
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ type: String, text: String? = nil) throws {
        var message: [String: Any] = ["type": type]
        if let text { message["data"] = ["text": text, "final": true] }
        let frame = try JSONSerialization.data(withJSONObject:
            ["id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": message])
        delegate?.transport(didReceiveFrame: frame)
    }
}

/// Contract §4.2: retired false preference never recreates spoken-answer cards.
@MainActor
final class ResponseResultRouterTests: XCTestCase {
    func testFalseStoredPreferenceKeepsExchangeInThreadAndLogNotResults() async throws {
        let key = "mortimer.interface.conversationThread"
        let previous = UserDefaults.standard.object(forKey: key)
        UserDefaults.standard.set(false, forKey: key)
        defer {
            if let previous { UserDefaults.standard.set(previous, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }
        let transport = RetiredResponseTransport()
        let client = JarvisClient(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil), stubTransport: transport)
        let workspace = WorkspaceStore(), display = DisplayWindowStore(), output = DisplayResultStore()
        display.setWindowOpen(true)
        let conversation = ConversationStore(), runs = AgentRunStore(), router = AppMessageRouter()
        router.start(client: client, agentRuns: runs, displayResults: output,
            displayWindow: display, workspace: workspace, conversation: conversation)
        defer { router.stop() }
        let user = "Synthetic spoken request retained in history"
        let answer = "Synthetic spoken answer stays only in the conversation"
        try transport.emit("user-transcription", text: user)
        for _ in 0..<100 { await Task.yield() }
        try transport.emit("bot-llm-started")
        for _ in 0..<100 { await Task.yield() }
        try transport.emit("bot-llm-text", text: answer)
        for _ in 0..<100 { await Task.yield() }
        try transport.emit("bot-llm-stopped")
        for _ in 0..<200 { await Task.yield() }
        XCTAssertEqual(conversation.entries.map(\.text), [user, answer])
        XCTAssertEqual(ConversationThread.rows(conversation.entries).map(\.text), [user, answer])
        XCTAssertTrue(workspace.results.isEmpty)
        XCTAssertTrue(output.results.isEmpty)
        XCTAssertTrue(display.panels.isEmpty)
        XCTAssertNil(workspace.supportingContent)

        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: LogTab().environment(DrawerModels())
            .environment(conversation).environment(runs).environment(\.mortimerReduceMotion, true))
        view.frame = NSRect(x: 0, y: 0, width: 800, height: 500)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(250))
        let texts = labels(in: view)
        XCTAssertTrue(texts.contains(user), "Log history must retain the user's line")
        XCTAssertTrue(texts.contains(answer), "Log history must retain Mortimer's line")
    }

    private func labels(in root: Any) -> Set<String> {
        var result = Set<String>()
        func visit(_ value: Any) {
            guard let object = value as? NSObject else { return }
            for selector in ["accessibilityLabel", "accessibilityValue"] {
                let key = NSSelectorFromString(selector)
                if object.responds(to: key), let text = object.perform(key)?.takeUnretainedValue() as? String { result.insert(text) }
            }
            let children = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] { values.forEach(visit) }
        }
        visit(root); return result
    }
}
