import Foundation
import JarvisKit

/// WS-21 (`docs/plans/MORTIMER_SUPPORTING_DISPLAY_TRANSFER_PLAN.md` D1–D3):
/// the one route by which content reaches the supporting display. Voice
/// (`display_show`, `skill_display_transfer`) and the pointer menus both call
/// `transfer`, which validates the content and the destination before
/// anything opens, and reports success only once the display window is
/// presenting that content on that screen.
///
/// Larry, 10-03, on `63aaeef`: "put the radar on the external monitor"
/// opened an empty supporting display while Mortimer said it was there. The
/// voice command opened the window without assigning content and reported
/// success before the app confirmed anything (Codex's audit, F1/F2).
@MainActor
final class SupportingDisplayCoordinator {
    enum Outcome: Equatable {
        /// The display confirmed it is presenting `title` on `screen`.
        case presented(title: String, screen: String)
        /// The same content was already presented on that screen; nothing
        /// reopened.
        case alreadyShowing(title: String, screen: String)
        /// Refused before anything opened.
        case rejected(code: String, reason: String)
        /// Opened but not confirmed (timeout, disconnect, superseded).
        case failed(code: String, reason: String)

        var status: String {
            switch self {
            case .presented: return "ok"
            case .alreadyShowing: return "noop"
            case .rejected, .failed: return "error"
            }
        }

        var code: String {
            switch self {
            case .presented: return "display_presented"
            case .alreadyShowing: return "already_showing"
            case .rejected(let code, _), .failed(let code, _): return code
            }
        }

        var summary: String {
            switch self {
            case .presented(let title, let screen): return "\(Self.sentence(title)) is now on \(screen)."
            case .alreadyShowing(let title, let screen): return "\(Self.sentence(title)) is already on \(screen)."
            case .rejected(_, let reason), .failed(_, let reason): return reason
            }
        }

        static func sentence(_ text: String) -> String {
            text.prefix(1).uppercased() + text.dropFirst()
        }

        var succeeded: Bool {
            switch self {
            case .presented, .alreadyShowing: return true
            case .rejected, .failed: return false
            }
        }
    }

    /// The seams to AppKit and placement, injectable for tests.
    struct Environment {
        var screens: @MainActor () -> [PlacementScreen]
        var windowScreenID: @MainActor (HostWindowKind) -> String?
        var consoleScreenID: @MainActor () -> String?
        var preferredSupportingScreenID: @MainActor () -> String?
        var assignDisplay: @MainActor (String) -> Void
        var openDisplay: @MainActor () -> Void
        var closeDisplay: @MainActor () -> Void
        var layoutVersion: @MainActor () -> Int
        var pause: @MainActor () async -> Void
        var now: @MainActor () -> TimeInterval
        /// Inside the bot's 5 s wait for a console result.
        var confirmTimeout: TimeInterval = 3.5

        static func live(placement: WindowPlacement) -> Environment {
            Environment(
                screens: { ScreenPlacement.shared.currentScreens() },
                windowScreenID: { ScreenPlacement.shared.screenID(of: $0) },
                consoleScreenID: { ScreenPlacement.shared.consoleScreenID() },
                preferredSupportingScreenID: { ScreenPlacement.shared.preferredSupportingScreenID },
                assignDisplay: { _ = ScreenPlacement.shared.assignDisplay(to: $0) },
                openDisplay: { placement.openDisplay() },
                closeDisplay: { placement.closeDisplay() },
                layoutVersion: {
                    InterfaceLayoutVersion.resolve(
                        UserDefaults.standard.object(forKey: "mortimer.interface.layoutVersion") as? Int ?? 2)
                },
                pause: { _ = try? await Task.sleep(nanoseconds: 50_000_000) },
                now: { ProcessInfo.processInfo.systemUptime })
        }
    }

    private let workspace: WorkspaceStore
    private let display: DisplayWindowStore
    private let environment: Environment
    private var generation = 0
    /// Reports pointer-initiated failures, which have no voice reply.
    var onPointerFailure: (@MainActor (Outcome) -> Void)?

    init(workspace: WorkspaceStore, display: DisplayWindowStore, environment: Environment) {
        self.workspace = workspace
        self.display = display
        self.environment = environment
    }

    // MARK: Transfer

    /// Pointer entry point: the menus' "Show … on display". Runs the same
    /// transfer and reports a failure on screen, since there is no reply.
    func show(_ content: SupportingDisplayContent) {
        Task { @MainActor in
            let outcome = await transfer(content, screenID: nil)
            if !outcome.succeeded { onPointerFailure?(outcome) }
        }
    }

    func transfer(_ content: SupportingDisplayContent, screenID requested: String?) async -> Outcome {
        generation += 1
        let mine = generation

        // 1. Content: a live result that may leave this window.
        if case .result(let id) = content {
            guard let result = workspace.results.first(where: { $0.id == id }) else {
                return .rejected(code: "result_unavailable",
                                 reason: "That result is no longer open, so nothing was moved.")
            }
            guard !result.payload.isProtectedLocal else {
                return .rejected(code: "protected_result",
                                 reason: "That result stays in the main window on this Mac.")
            }
        }
        let title = Self.title(for: content, in: workspace)

        // 2. Destination: a connected screen the console is not on.
        let screens = environment.screens()
        // Mirrored displays share one placement ID and count once.
        guard Set(screens.map(\.id)).count > 1 else {
            return .rejected(code: "single_screen",
                             reason: "Only one display is connected, so there is no other screen to use.")
        }
        let consoleID = environment.consoleScreenID()
        let destination: PlacementScreen
        if let requested = requested?.trimmingCharacters(in: .whitespacesAndNewlines), !requested.isEmpty {
            guard let screen = screens.first(where: { $0.id == requested }) else {
                return .rejected(code: "screen_unavailable",
                                 reason: "That display isn't connected, so nothing was moved.")
            }
            guard screen.id != consoleID else {
                return .rejected(code: "console_screen",
                                 reason: "That is the screen the console is on; choose the other display.")
            }
            destination = screen
        } else {
            let candidates = screens.filter { $0.id != consoleID }
            let preferred = [environment.windowScreenID(.display), environment.preferredSupportingScreenID()]
                .compactMap { $0 }
            guard let chosen = preferred.lazy.compactMap({ id in candidates.first { $0.id == id } }).first
                    ?? candidates.first else {
                return .rejected(code: "single_screen",
                                 reason: "There is no screen other than the console's to use.")
            }
            destination = chosen
        }
        let screenName = Self.name(of: destination)

        // 3. Reuse: already presented there.
        if isPresented(content), environment.windowScreenID(.display) == destination.id {
            return .alreadyShowing(title: title, screen: screenName)
        }

        // 4. Apply.
        let wasOpen = display.isWindowOpen
        guard workspace.sendToDisplay(content) else {
            return .rejected(code: "result_unavailable",
                             reason: "That content can't be shown on the other display.")
        }
        environment.assignDisplay(destination.id)
        environment.openDisplay()

        // 5. Confirm.
        let deadline = environment.now() + environment.confirmTimeout
        while true {
            guard mine == generation else {
                return .failed(code: "superseded",
                               reason: "A newer display request replaced this one.")
            }
            if !environment.screens().contains(where: { $0.id == destination.id }) {
                undo(content, wasOpen: wasOpen)
                return .failed(code: "screen_disconnected",
                               reason: "\(Outcome.sentence(screenName)) disconnected before \(title) appeared on it, so it is back in the main window.")
            }
            if isPresented(content), environment.windowScreenID(.display) == destination.id {
                return .presented(title: title, screen: screenName)
            }
            if environment.now() >= deadline {
                undo(content, wasOpen: wasOpen)
                return .failed(code: "not_confirmed",
                               reason: "The other display didn't confirm it is showing \(title), so it is back in the main window.")
            }
            await environment.pause()
        }
    }

    /// What the display window renders right now (the main surface's own
    /// locator rule), and that the window is open.
    func isPresented(_ content: SupportingDisplayContent) -> Bool {
        display.isPresented(content, selection: workspace.supportingContent,
                            layoutVersion: environment.layoutVersion())
    }

    /// A failed transfer must not leave main pointing at an absent window or
    /// an empty window open.
    private func undo(_ content: SupportingDisplayContent, wasOpen: Bool) {
        if workspace.supportingContent == content { workspace.showOriginalDisplayPanels() }
        if !wasOpen { environment.closeDisplay() }
    }

    // MARK: Inventory (plan D6)

    /// The screens, as placement identifies them.
    func screensInventory() -> [JSONValue] {
        let consoleID = environment.consoleScreenID()
        let displayID = display.isWindowOpen ? environment.windowScreenID(.display) : nil
        return environment.screens().prefix(8).enumerated().map { index, screen -> JSONValue in
            .object([
                "id": .string(screen.id),
                "label": .string(screen.name.isEmpty ? "Display \(index + 1)" : screen.name),
                "index": .number(Double(index)),
                "primary": .bool(screen.isMain),
                "is_console": .bool(screen.id == consoleID),
                "is_supporting": .bool(screen.id == displayID),
            ])
        }
    }

    /// What the supporting display owns and where it is.
    func supportingDisplayInventory() -> JSONValue {
        let selection = workspace.supportingContent
        var content: JSONValue = .null
        var resultID: JSONValue = .null
        switch selection {
        case .result(let id):
            let protected = workspace.results.first(where: { $0.id == id })?.payload.isProtectedLocal ?? true
            content = .string("result")
            resultID = protected ? .null : .string(id.uuidString)
        case .memoryGraph: content = .string("memory_graph")
        case .skills: content = .string("skills")
        case .workflows: content = .string("workflows")
        case .skillDetail: content = .string("skill_detail")
        case nil: break
        }
        let open = display.isWindowOpen
        return .object([
            "open": .bool(open),
            "content": content,
            "result_id": resultID,
            "screen_id": open ? (environment.windowScreenID(.display).map(JSONValue.string) ?? .null) : .null,
            "presented": .bool(selection.map { isPresented($0) } ?? false),
        ])
    }

    // MARK: Names

    static func name(of screen: PlacementScreen) -> String {
        screen.name.isEmpty ? "the other display" : screen.name
    }

    static func title(for content: SupportingDisplayContent, in workspace: WorkspaceStore) -> String {
        switch content {
        case .result(let id):
            let title = workspace.results.first(where: { $0.id == id })?.payload.title?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return title.isEmpty ? "the result" : String(title.prefix(80))
        case .memoryGraph: return "the memory graph"
        case .skills: return "Skills"
        case .workflows: return "the workflows"
        case .skillDetail: return "the skill details"
        }
    }

    /// Parse a `display_show` target: a result UUID from the inventory, or
    /// one of the named views.
    static func content(forTarget target: String) -> SupportingDisplayContent? {
        switch target {
        case "memory_graph": return .memoryGraph
        case "skills": return .skills
        case "workflows": return .workflows
        default: return UUID(uuidString: target).map(SupportingDisplayContent.result)
        }
    }
}
