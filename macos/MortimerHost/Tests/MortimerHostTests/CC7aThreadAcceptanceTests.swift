import XCTest
import AppKit
import SwiftUI
import ScreenCaptureKit
@testable import JarvisKit
@testable import MortimerHost

/// Candidate-path evidence only: synthetic frames, an actual app router and
/// actual SwiftUI thread. This does not manufacture Larry's live voice sign-off.
private final class ThreadAcceptanceTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    private(set) var sentFrames = 0
    func connect(config: JarvisConfig) async throws {}
    func disconnect() async {}
    func send(_ data: Data) throws { sentFrames += 1 }
    func setMicEnabled(_ enabled: Bool) {}

    func emit(_ type: String, text: String? = nil, final: Bool? = nil) throws {
        var message: [String: Any] = ["type": type]
        if let text {
            var data: [String: Any] = ["text": text]
            if let final { data["final"] = final }
            message["data"] = data
        }
        try emitPayload(message)
    }

    func emitPayload(_ message: [String: Any]) throws {
        let frame = try JSONSerialization.data(withJSONObject: [
            "id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": message,
        ])
        delegate?.transport(didReceiveFrame: frame)
    }
}

@MainActor
final class CC7aThreadAcceptanceTests: XCTestCase {
    private static let privateBody = "PUBLIC SYNTHETIC PRIVATE BODY CANARY — never a transcript excerpt"
    private static let privateTitle = "Protected local fixture"

    private final class Probe {
        var clipboardWrites: [String] = []
        var displayOpens = 0
        var displayAssignments: [String] = []
        var clock: TimeInterval = 0
    }

    private struct Fixture {
        let transport: ThreadAcceptanceTransport
        let client: JarvisClient
        let router: AppMessageRouter
        let conversation: ConversationStore
        let workspace: WorkspaceStore
        let display: DisplayWindowStore
        let output: DisplayResultStore
        let drawer: DrawerState
        let sharing: ShareCoordinator
        let coordinator: ConsoleActionCoordinator
        let probe: Probe
    }

    private struct Hosted {
        let view: NSHostingView<AnyView>
        let window: NSWindow
    }

    private func prerequisite(_ message: String) -> NSError {
        NSError(domain: "CC7aThreadAcceptanceTests.Prerequisite", code: 1,
                userInfo: [NSLocalizedDescriptionKey: message])
    }

    /// The router reads standard defaults. They belong to this isolated test
    /// runner, never the installed com.mortimer.host domain, and are restored.
    private func configureTestDefaults() throws -> () -> Void {
        guard Bundle.main.bundleIdentifier != "com.mortimer.host",
              ProcessInfo.processInfo.processName != "MortimerHost" else {
            throw prerequisite("Refusing to change defaults in the live MortimerHost process")
        }
        let defaults = UserDefaults.standard
        let keys = ["mortimer.interface.layoutVersion", ConversationThread.flagKey]
        let previous = keys.map { defaults.object(forKey: $0) }
        defaults.set(2, forKey: keys[0]); defaults.set(true, forKey: keys[1])
        return {
            for (key, value) in zip(keys, previous) {
                if let value { defaults.set(value, forKey: key) }
                else { defaults.removeObject(forKey: key) }
            }
        }
    }

    private func fixture() -> Fixture {
        // Placement's window adapter requires AppKit even before hosting.
        _ = NSApplication.shared
        let transport = ThreadAcceptanceTransport()
        let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:9")!,
            adminURL: URL(string: "http://127.0.0.1:9")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:9/ws")!, token: nil)
        // Never connect: frames arrive only from the inert test transport.
        let client = JarvisClient(config: config, stubTransport: transport)
        let conversation = ConversationStore(), workspace = WorkspaceStore()
        workspace.quietArrivals = true
        let display = DisplayWindowStore(), output = DisplayResultStore(), drawer = DrawerState()
        let probe = Probe()
        let sharing = ShareCoordinator(clipboardWriter: { text in
            probe.clipboardWrites.append(text); return true
        })
        let placement = WindowPlacement(drawer: drawer, windows: WindowActions())
        let main = PlacementScreen(id: "fixture-main", visibleFrame: CGRect(x: 0, y: 0, width: 900, height: 600), isMain: true)
        let external = PlacementScreen(id: "fixture-external", visibleFrame: CGRect(x: 900, y: 0, width: 900, height: 600))
        let supporting = SupportingDisplayCoordinator(workspace: workspace, display: display,
            environment: .init(screens: { [main, external] },
                windowScreenID: { kind in kind == .console ? main.id : (display.isWindowOpen ? external.id : nil) },
                consoleScreenID: { main.id }, preferredSupportingScreenID: { external.id },
                assignDisplay: { probe.displayAssignments.append($0) },
                openDisplay: { probe.displayOpens += 1; display.setWindowOpen(true) },
                closeDisplay: { display.setWindowOpen(false) }, layoutVersion: { 2 },
                pause: { probe.clock += 0.25; await Task.yield() }, now: { probe.clock }))
        let coordinator = ConsoleActionCoordinator(workspace: workspace, display: display,
            placement: placement, drawer: drawer, sharing: sharing, supportingDisplay: supporting,
            screens: { [main, external] })
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: output,
            displayWindow: display, workspace: workspace, conversation: conversation,
            drawer: drawer, consoleCoordinator: coordinator)
        return Fixture(transport: transport, client: client, router: router,
            conversation: conversation, workspace: workspace, display: display,
            output: output, drawer: drawer, sharing: sharing, coordinator: coordinator, probe: probe)
    }

    private func waitUntil(_ reason: String, timeout: TimeInterval = 4,
                           _ condition: @MainActor () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() {
            guard Date() < deadline else {
                print("CC7aThreadAcceptanceTests unmet prerequisite: \(reason)")
                throw prerequisite("Timed out waiting for \(reason)")
            }
            try await Task.sleep(for: .milliseconds(20))
        }
    }

    private func threadView(_ fixture: Fixture, workspace: WorkspaceStore? = nil,
                            identity: String = "thread-candidate-original") -> AnyView {
        AnyView(ConversationThreadView(coordinator: fixture.coordinator)
            .environment(fixture.conversation).environment(workspace ?? fixture.workspace)
            .environment(\.mortimerReduceMotion, true)
            .padding(4).background(AppTheme.bg).foregroundStyle(AppTheme.text)
            .preferredColorScheme(.dark).accessibilityIdentifier(identity))
    }

    private func host(_ root: AnyView, width: CGFloat = 900, height: CGFloat = 500) -> Hosted {
        let app = NSApplication.shared
        app.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: root)
        view.frame = NSRect(x: 0, y: 0, width: width, height: height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        // A supporting screen can have moved the desktop's origin. Place
        // only this synthetic fixture inside an actual visible screen.
        if let screen = NSScreen.main ?? NSScreen.screens.first {
            window.setFrameOrigin(NSPoint(x: screen.visibleFrame.midX - width / 2,
                                          y: screen.visibleFrame.midY - height / 2))
        }
        window.level = .floating
        window.makeKeyAndOrderFront(nil); window.orderFrontRegardless()
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        return Hosted(view: view, window: window)
    }

    private func nativeScrollView(in view: NSView) -> NSScrollView? {
        if let scroll = view as? NSScrollView { return scroll }
        for child in view.subviews {
            if let scroll = nativeScrollView(in: child) { return scroll }
        }
        return nil
    }

    private func distanceFromEnd(_ scroll: NSScrollView) -> CGFloat {
        guard let document = scroll.documentView else { return .infinity }
        let visible = scroll.documentVisibleRect
        return max(0, document.isFlipped ? document.bounds.maxY - visible.maxY
                                        : visible.minY - document.bounds.minY)
    }

    private func scrollToFraction(_ fraction: CGFloat, in scroll: NSScrollView) {
        guard let document = scroll.documentView else { return }
        let extent = max(0, document.bounds.height - scroll.documentVisibleRect.height)
        let y = document.bounds.minY + extent * (document.isFlipped ? fraction : 1 - fraction)
        scroll.contentView.scroll(to: NSPoint(x: scroll.contentView.bounds.minX, y: y))
        scroll.reflectScrolledClipView(scroll.contentView)
    }

    private func accessibilityObjects(_ view: NSView) -> [NSObject] {
        var objects: [NSObject] = [], visited = Set<ObjectIdentifier>()
        func visit(_ value: Any) {
            guard let object = value as? NSObject, visited.insert(ObjectIdentifier(object)).inserted else { return }
            objects.append(object)
            let selector = NSSelectorFromString("accessibilityChildren")
            if object.responds(to: selector), let children = object.perform(selector)?.takeUnretainedValue() as? [Any] {
                children.forEach(visit)
            }
        }
        visit(view)
        return objects
    }

    private func label(_ object: NSObject) -> String {
        for name in ["accessibilityLabel", "accessibilityTitle", "accessibilityValue"] {
            let selector = NSSelectorFromString(name)
            if object.responds(to: selector), let raw = object.perform(selector)?.takeUnretainedValue() {
                if let text = raw as? String, !text.isEmpty { return text }
                if let text = raw as? NSAttributedString, !text.string.isEmpty { return text.string }
            }
        }
        return ""
    }

    private func labels(_ view: NSView) -> [String] { accessibilityObjects(view).map(label) }

    private func hasIdentifier(_ identifier: String, in view: NSView) -> Bool {
        let selector = NSSelectorFromString("accessibilityIdentifier")
        return accessibilityObjects(view).contains {
            $0.responds(to: selector)
                && ($0.perform(selector)?.takeUnretainedValue() as? String) == identifier
        }
    }

    private func press(_ object: NSObject) throws {
        let selector = NSSelectorFromString("accessibilityPerformPress")
        guard object.responds(to: selector) else { throw prerequisite("Fixture control has no accessibility press action") }
        typealias Press = @convention(c) (AnyObject, Selector) -> Bool
        let action = unsafeBitCast(object.method(for: selector), to: Press.self)
        XCTAssertTrue(action(object, selector), "Actual fixture control refused its press action")
    }

    private func frame(_ object: NSObject) -> NSRect? {
        let selector = NSSelectorFromString("accessibilityFrame")
        guard object.responds(to: selector) else { return nil }
        return (object.value(forKey: "accessibilityFrame") as? NSValue)?.rectValue
    }

    private func newTurnsButton(in view: NSView) -> NSObject? {
        accessibilityObjects(view).first { label($0).hasPrefix("Show ") && label($0).contains("new conversation turns") }
    }

    private func emitPublicReply(_ fixture: Fixture, user: String, answer: String) async throws {
        let before = fixture.conversation.entries.count
        try fixture.transport.emit("user-transcription", text: user, final: true)
        try await waitUntil("public user row") { fixture.conversation.entries.count == before + 1 }
        try fixture.transport.emit("bot-llm-started")
        try fixture.transport.emit("bot-llm-text", text: answer)
        try fixture.transport.emit("bot-llm-stopped")
        try await waitUntil("public assistant row") { fixture.conversation.entries.last?.text == answer }
    }

    private func protectedFields(body: String) -> [String: Any] {
        ["kind": "markdown", "title": Self.privateTitle,
            "body": body, "surface": "window", "tool": "protected_result",
            "data_policy": "local_only", "opaque_ref": "synthetic-opaque-reference",
            "commands": ["synthetic-command-canary"], "content": "synthetic-clipboard-canary",
            "images": ["file:///nonexistent-synthetic-image-canary.png"],
            "links": [["label": "synthetic-link-canary", "url": "file:///nonexistent-synthetic-link-canary"]]]
    }

    private func emitProtected(_ fixture: Fixture) async throws -> WorkspaceResult {
        try fixture.transport.emitPayload(["type": "display", "display": protectedFields(body: Self.privateBody)])
        try await waitUntil("protected result in local workspace") { fixture.workspace.results.count == 1 }
        return try XCTUnwrap(fixture.workspace.results.first)
    }

    func testProtectedResultUsesRenderedPrivateCardAndLocalOnlyCoordinatorGuards() async throws {
        let restore = try configureTestDefaults(); defer { restore() }
        let f = fixture(); defer { f.router.stop() }
        try await emitPublicReply(f, user: "Inspect the synthetic protected fixture", answer: "A protected local result is ready.")
        let result = try await emitProtected(f)
        XCTAssertEqual(f.workspace.activeID, result.id)
        XCTAssertFalse(f.workspace.showsConversation, "A requested private result may correctly open locally")
        XCTAssertEqual(f.coordinator.executePointer(.viewSet, args: ["mode": .string("conversation")]), .applied)
        XCTAssertEqual(f.conversation.entries.count, 2)
        XCTAssertFalse(f.client.transcript.contains { $0.text.contains(Self.privateBody) })
        XCTAssertFalse(f.conversation.entries.contains { $0.text.contains(Self.privateBody) })
        XCTAssertTrue(f.output.results.isEmpty)
        XCTAssertTrue(f.display.panels.isEmpty)
        XCTAssertNil(f.workspace.supportingContent)
        XCTAssertFalse(String(describing: f.coordinator.inventoryJSON()).contains(result.id.uuidString))
        XCTAssertFalse(String(describing: f.coordinator.inventoryJSON()).contains(Self.privateTitle))
        let hosted = host(threadView(f)); defer { closeRenderingFixtureWindow(hosted.window) }
        try await waitUntil("rendered private card") { self.labels(hosted.view).contains { $0.contains(ConversationThread.privateSummary) } }
        let rendered = labels(hosted.view).joined(separator: "\n")
        for sentinel in [Self.privateBody, "synthetic-command-canary", "synthetic-clipboard-canary", "synthetic-link-canary"] {
            XCTAssertFalse(rendered.contains(sentinel), "Protected content entered the rendered thread")
        }
        let open = try XCTUnwrap(accessibilityObjects(hosted.view).first {
            self.label($0).hasPrefix("Open ") && self.label($0).contains(Self.privateTitle)
        })
        XCTAssertTrue(f.workspace.showsConversation, "Protected arrival must remain a private card until opened")
        try press(open)
        try await waitUntil("same private UUID opened by actual Open button") {
            f.workspace.activeID == result.id && !f.workspace.showsConversation
        }
        XCTAssertEqual(f.workspace.activeResult?.payload.body, Self.privateBody)
        XCTAssertEqual(f.coordinator.executePointer(.sharePreview, target: result.id.uuidString), .unsupported)
        XCTAssertEqual(f.coordinator.executePointer(.shareCopy), .invalid)
        XCTAssertNil(f.sharing.preview)
        XCTAssertTrue(f.probe.clipboardWrites.isEmpty)
        let transfer = await f.coordinator.executeTransfer(ConsoleRequest(sessionID: UUID(), generation: UUID(),
            requestID: UUID(), revision: f.workspace.consoleRevision, action: .displayShow, target: result.id.uuidString))
        XCTAssertEqual(transfer.code, "protected_result")
        XCTAssertEqual(f.probe.displayOpens, 0)
        XCTAssertTrue(f.probe.displayAssignments.isEmpty)

        hosted.view.rootView = AnyView(WorkspaceResultPane(result: result, coordinator: f.coordinator)
            .environmentObject(f.client).environment(f.workspace).environment(f.display)
            .environment(f.drawer).environment(f.sharing).preferredColorScheme(.dark))
        hosted.view.layoutSubtreeIfNeeded()
        do {
            try await waitUntil("protected body visible only in selected local pane") { self.labels(hosted.view).contains(Self.privateBody) }
        } catch {
            XCTFail("Synthetic local-pane readiness failed: \(error); visible AX labels: \(self.labels(hosted.view))")
            throw error
        }
        let pane = labels(hosted.view).joined(separator: "\n")
        XCTAssertFalse(pane.contains("synthetic-link-canary") || pane.contains("synthetic-command-canary") || pane.contains("synthetic-clipboard-canary"))

        let publicPayload = try JSONDecoder().decode(DisplayPayload.self, from: Data(#"{"title":"Public comparison fixture","body":"Public body"}"#.utf8))
        let publicResult = WorkspaceResult(payload: publicPayload)
        f.workspace.receive(publicResult, quietly: true)
        XCTAssertEqual(f.coordinator.executePointer(.compareSet, target: result.id.uuidString,
            secondaryTarget: publicResult.id.uuidString), .applied)
        XCTAssertEqual(f.coordinator.executePointer(.sharePreview, target: "comparison"), .unsupported)
        XCTAssertEqual(f.coordinator.executePointer(.compareSet, target: publicResult.id.uuidString,
            secondaryTarget: result.id.uuidString), .applied)
        XCTAssertEqual(f.coordinator.executePointer(.sharePreview, target: "comparison"), .unsupported)
        XCTAssertTrue(f.probe.clipboardWrites.isEmpty)
        XCTAssertEqual(f.transport.sentFrames, 0, "Disconnected fake session must never send a provider/transport request")
    }

    func testActualThreadWindowCaptureDoesNotExposePrivateBodyExcerpt() async throws {
        guard CGPreflightScreenCaptureAccess(), !NSScreen.screens.isEmpty else {
            throw XCTSkip("Thread window capture requires Screen Recording and an interactive WindowServer; no acceptance is inferred")
        }
        let restore = try configureTestDefaults(); defer { restore() }
        let app = NSApplication.shared, originalPolicy = NSApplication.shared.activationPolicy()
        guard app.setActivationPolicy(.regular) else { throw XCTSkip("Thread fixture cannot activate in this WindowServer") }
        defer { _ = app.setActivationPolicy(originalPolicy) }
        app.finishLaunching(); app.activate(ignoringOtherApps: true)
        let f = fixture(); defer { f.router.stop() }
        try await emitPublicReply(f, user: "Synthetic local task", answer: "A protected local result is ready.")
        let result = try await emitProtected(f)
        XCTAssertEqual(f.workspace.activeID, result.id)
        XCTAssertFalse(f.workspace.showsConversation)
        XCTAssertEqual(f.coordinator.executePointer(.viewSet, args: ["mode": .string("conversation")]), .applied)
        let hosted = host(threadView(f), width: 760, height: 420)
        defer { closeRenderingFixtureWindow(hosted.window) }
        try await waitUntil("private card AX ready for window capture") {
            self.labels(hosted.view).contains { $0.contains(ConversationThread.privateSummary) }
        }
        hosted.window.displayIfNeeded()
        // AppKit's activation and occlusion flags are not the capture inventory.
        // Require ScreenCaptureKit to identify this exact on-screen fixture.
        let windowID = CGWindowID(hosted.window.windowNumber)
        let deadline = Date().addingTimeInterval(4)
        var captureWindowReady = false
        while true {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            if content.windows.contains(where: { $0.windowID == windowID }) {
                captureWindowReady = true
                break
            }
            guard Date() < deadline else { break }
            try await Task.sleep(for: .milliseconds(20))
        }
        guard captureWindowReady else {
            let onScreen = NSScreen.screens.contains { $0.frame.intersects(hosted.window.frame) }
            let diagnostics = "windowID=\(windowID), visible=\(hosted.window.isVisible), "
                + "unoccluded=\(hosted.window.occlusionState.contains(.visible)), "
                + "active app=\(app.isActive), active Space=\(hosted.window.isOnActiveSpace), "
                + "on a screen=\(onScreen), SCK matched=\(captureWindowReady)"
            if onScreen && (!app.isActive || !hosted.window.isOnActiveSpace) {
                throw XCTSkip("Synthetic fixture window is absent from ScreenCaptureKit's on-screen inventory "
                    + "while the test app or its Space is inactive; actual window capture remains unaccepted; "
                    + diagnostics)
            }
            XCTFail("Synthetic thread capture readiness: " + diagnostics)
            throw prerequisite("Synthetic fixture window did not enter ScreenCaptureKit's on-screen inventory")
        }
        try await Task.sleep(for: .milliseconds(200)) // Allow the WindowServer to composite this fixture.
        let original = try await captureWindow(hosted.window)
        // Same window and identical public card metadata, but entirely
        // different private body. Capture equality must not depend on it.
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(
            withJSONObject: protectedFields(body: "DIFFERENT PUBLIC SYNTHETIC PRIVATE BODY")))
        let reference = WorkspaceStore()
        reference.receive(WorkspaceResult(payload: payload, id: result.id, receivedAt: result.receivedAt), quietly: true)
        reference.select(result.id)
        reference.returnToConversation()
        hosted.view.rootView = threadView(f, workspace: reference, identity: "thread-candidate-reference")
        hosted.window.layoutIfNeeded(); hosted.view.layoutSubtreeIfNeeded()
        try await waitUntil("reference private card rendered in the replaced view") {
            self.hasIdentifier("thread-candidate-reference", in: hosted.view)
                && self.labels(hosted.view).contains { $0.contains(ConversationThread.privateSummary) }
        }
        hosted.window.displayIfNeeded()
        try await Task.sleep(for: .milliseconds(200))
        let referenceImage = try await captureWindow(hosted.window)
        XCTAssertEqual(original.width, referenceImage.width)
        XCTAssertEqual(original.height, referenceImage.height)
        XCTAssertTrue(original.bytes == referenceImage.bytes, "Actual thread capture depends on a protected body excerpt")
        reference.close(result.id)
        try await waitUntil("private card removed from reference thread") { !self.labels(hosted.view).contains { $0.contains(ConversationThread.privateSummary) } }
        hosted.window.displayIfNeeded()
        try await Task.sleep(for: .milliseconds(200))
        let withoutCard = try await captureWindow(hosted.window)
        XCTAssertEqual(withoutCard.width, referenceImage.width)
        XCTAssertEqual(withoutCard.height, referenceImage.height)
        XCTAssertFalse(referenceImage.bytes == withoutCard.bytes, "Equal empty captures do not prove that the private card was visible")
    }

    private func captureWindow(_ window: NSWindow) async throws -> (width: Int, height: Int, bytes: Data) {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        let target = try XCTUnwrap(content.windows.first { $0.windowID == CGWindowID(window.windowNumber) },
                                   "Only the synthetic fixture window may be captured")
        let config = SCStreamConfiguration()
        config.width = max(1, Int(window.frame.width * window.backingScaleFactor))
        config.height = max(1, Int(window.frame.height * window.backingScaleFactor))
        let image: CGImage
        do {
            image = try await SCScreenshotManager.captureImage(contentFilter: SCContentFilter(desktopIndependentWindow: target), configuration: config)
        } catch {
            XCTFail("Synthetic fixture SCK capture failed (visible=\(window.isVisible), unoccluded=\(window.occlusionState.contains(.visible)), windowID=\(window.windowNumber)): \(error)")
            throw error
        }
        let bitmap = NSBitmapImageRep(cgImage: image)
        // Compare pixels, not bitmap row padding or container metadata.
        var pixels = Data()
        pixels.reserveCapacity(bitmap.pixelsWide * bitmap.pixelsHigh * 4)
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                let color = try XCTUnwrap(bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB))
                pixels.append(UInt8((color.redComponent * 255).rounded()))
                pixels.append(UInt8((color.greenComponent * 255).rounded()))
                pixels.append(UInt8((color.blueComponent * 255).rounded()))
                pixels.append(UInt8((color.alphaComponent * 255).rounded()))
            }
        }
        return (bitmap.pixelsWide, bitmap.pixelsHigh, pixels)
    }

    func testActualScrollViewFollowsGrowingReplyOnlyWhileReadingTheEnd() async throws {
        let restore = try configureTestDefaults(); defer { restore() }
        let f = fixture(); defer { f.router.stop() }
        for index in 0..<8 {
            try await emitPublicReply(f, user: "Public question \(index)", answer: String(repeating: "Public history \(index) words. ", count: 8))
        }
        let hosted = host(threadView(f)); defer { closeRenderingFixtureWindow(hosted.window) }
        try await waitUntil("actual scrollable thread document") {
            guard let scroll = self.nativeScrollView(in: hosted.view), let document = scroll.documentView else { return false }
            return document.bounds.height > scroll.documentVisibleRect.height + 100
        }
        let scroll = try XCTUnwrap(nativeScrollView(in: hosted.view))
        try await waitUntil("initial thread bottom") { self.distanceFromEnd(scroll) <= 26 }
        try f.transport.emit("bot-llm-started")
        var answer = ""
        for index in 0..<6 {
            let oldHeight = try XCTUnwrap(scroll.documentView).bounds.height
            answer += String(repeating: "Public streaming chunk \(index). ", count: 12)
            try f.transport.emit("bot-llm-text", text: String(repeating: "Public streaming chunk \(index). ", count: 12))
            try await waitUntil("streamed chunk retained") { f.conversation.entries.last?.text == answer }
            try await waitUntil("actual streamed row geometry grows") {
                (scroll.documentView?.bounds.height ?? 0) > oldHeight + 1
            }
            try await waitUntil("real view follows streaming growth") { self.distanceFromEnd(scroll) <= 26 }
        }
        try f.transport.emit("bot-llm-stopped")
        scrollToFraction(0.35, in: scroll)
        try await waitUntil("reader is above newest turn") { self.distanceFromEnd(scroll) > 100 }
        try await Task.sleep(for: .milliseconds(50)) // Let the real geometry callback receive the reader's scroll.
        let readingOffset = scroll.documentVisibleRect.minY
        try await emitPublicReply(f, user: "A new public question", answer: String(repeating: "Public answer arriving while reading history. ", count: 15))
        try await waitUntil("real New conversation control") { self.newTurnsButton(in: hosted.view) != nil }
        XCTAssertEqual(scroll.documentVisibleRect.minY, readingOffset, accuracy: 2,
                       "A new answer moved the actual reader viewport")
        let button = try XCTUnwrap(newTurnsButton(in: hosted.view))
        try press(button)
        try await waitUntil("actual New button returns to end") { self.distanceFromEnd(scroll) <= 26 && self.newTurnsButton(in: hosted.view) == nil }
        XCTAssertTrue(f.workspace.results.isEmpty)
        XCTAssertTrue(f.display.panels.isEmpty)
        XCTAssertEqual(f.transport.sentFrames, 0)
    }

    func testActualScrollViewKeepsRetainedReaderAnchorAtConversationCapacity() async throws {
        try await assertRetainedReaderAnchor(variableRemovedHeights: false)
    }

    func testActualScrollViewKeepsReaderAnchorWhenRemovedRowsHaveDifferentHeights() async throws {
        try await assertRetainedReaderAnchor(variableRemovedHeights: true)
    }

    private func assertRetainedReaderAnchor(variableRemovedHeights: Bool) async throws {
        let restore = try configureTestDefaults(); defer { restore() }
        let f = fixture(); defer { f.router.stop() }
        for index in 0..<AppTuning.maxConversationEntries {
            var text = "Public retained marker \(index)"
            if variableRemovedHeights && index < 3 {
                text += String(repeating: "\nPublic additional line in the oldest synthetic row.", count: 3 + index * 2)
            }
            try f.transport.emit("user-transcription", text: text, final: true)
        }
        try await waitUntil("full retained transcript") { f.conversation.entries.count == AppTuning.maxConversationEntries }
        let hosted = host(threadView(f)); defer { closeRenderingFixtureWindow(hosted.window) }
        try await waitUntil("actual retained scrollable document") {
            guard let scroll = self.nativeScrollView(in: hosted.view), let document = scroll.documentView else { return false }
            return document.bounds.height > scroll.documentVisibleRect.height + 100
        }
        let scroll = try XCTUnwrap(nativeScrollView(in: hosted.view))
        try await waitUntil("retention fixture initially settled at end") { self.distanceFromEnd(scroll) <= 26 }
        scrollToFraction(0.5, in: scroll)
        try await waitUntil("retained reader is scrolled up") { self.distanceFromEnd(scroll) > 100 }
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertGreaterThan(distanceFromEnd(scroll), 100, "The real reader must still be scrolled up before any arrival")
        let viewport = hosted.window.convertToScreen(hosted.view.convert(hosted.view.bounds, to: nil))
        let anchor = try XCTUnwrap(accessibilityObjects(hosted.view).first { object in
            guard self.label(object).hasPrefix("You: Public retained marker "), let rect = self.frame(object) else { return false }
            return viewport.insetBy(dx: 2, dy: 40).contains(rect)
        }, "Actual visible transcript row must provide the retained reader anchor")
        let anchorLabel = label(anchor)
        let anchorID = try XCTUnwrap(f.conversation.entries.first { "You: " + $0.text == anchorLabel }?.id)
        var observedHeightChanges = Set<Int>()
        for index in 0..<(variableRemovedHeights ? 3 : 1) {
            let before = try XCTUnwrap(frame(try XCTUnwrap(accessibilityObjects(hosted.view).first { self.label($0) == anchorLabel })))
            let oldDocumentHeight = try XCTUnwrap(scroll.documentView).bounds.height
            let oldOffset = scroll.documentVisibleRect.minY
            let firstID = try XCTUnwrap(f.conversation.entries.first?.id)
            try f.transport.emit("user-transcription", text: "Public added at capacity \(index)", final: true)
            try await waitUntil("retention replaced oldest identity") {
                f.conversation.entries.count == AppTuning.maxConversationEntries && f.conversation.entries.first?.id != firstID
            }
            do {
                try await waitUntil("capacity New button visible") { self.newTurnsButton(in: hosted.view) != nil }
            } catch {
                XCTFail("No New after retained arrival: variable heights=\(variableRemovedHeights), iteration=\(index), "
                    + "old offset=\(oldOffset), new offset=\(scroll.documentVisibleRect.minY), "
                    + "old document=\(oldDocumentHeight), new document=\(scroll.documentView?.bounds.height ?? 0), "
                    + "distance from end=\(self.distanceFromEnd(scroll))")
                throw error
            }
            if variableRemovedHeights {
                try await waitUntil("different-height retained document was laid out") {
                    (scroll.documentView?.bounds.height ?? oldDocumentHeight) < oldDocumentHeight - 1
                }
            }
            let retained = try XCTUnwrap(accessibilityObjects(hosted.view).first { self.label($0) == anchorLabel })
            let after = try XCTUnwrap(frame(retained))
            XCTAssertEqual(f.conversation.entries.first { $0.id == anchorID }?.text, String(anchorLabel.dropFirst(5)))
            XCTAssertEqual(after.midY, before.midY, accuracy: 2,
                "Retention shifted the same retained row by \(after.midY - before.midY)pt; "
                + "document height \(oldDocumentHeight)→\(scroll.documentView?.bounds.height ?? 0), "
                + "viewport offset \(oldOffset)→\(scroll.documentVisibleRect.minY)")
            observedHeightChanges.insert(Int((oldDocumentHeight - (scroll.documentView?.bounds.height ?? 0)).rounded()))
        }
        if variableRemovedHeights {
            XCTAssertGreaterThan(observedHeightChanges.count, 1,
                "The real layout must exercise different removed-row heights; one fixed adjustment cannot satisfy this fixture")
        }
        let newControl = try XCTUnwrap(newTurnsButton(in: hosted.view))
        XCTAssertEqual(label(newControl), "Show \(variableRemovedHeights ? 3 : 1) new conversation turns")
        try press(newControl)
        try await waitUntil("capacity New button returns to end") { self.distanceFromEnd(scroll) <= 26 && self.newTurnsButton(in: hosted.view) == nil }
        XCTAssertEqual(f.conversation.entries.last?.text, "Public added at capacity \(variableRemovedHeights ? 2 : 0)")
        XCTAssertEqual(f.transport.sentFrames, 0)
    }

}
