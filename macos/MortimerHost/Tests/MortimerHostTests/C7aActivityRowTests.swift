import XCTest
import SwiftUI
import AppKit
import Vision
import JarvisKit
@testable import MortimerHost

@MainActor
private func c7aRenderedText(in view: NSView) throws -> String {
    let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
    view.cacheDisplay(in: view.bounds, to: bitmap)
    let image = try XCTUnwrap(bitmap.cgImage)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: image).perform([request])
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: " ").split(whereSeparator: \.isWhitespace).joined().lowercased()
}

/// C7a: the activity row, the inline approval row's placement and words,
/// Space beside push-to-talk, and the typed / approve turn binding.
@MainActor
final class C7aActivityRowTests: XCTestCase {
    private func row(_ id: String, user: Bool, at time: Double) -> ConversationThread.Row {
        ConversationThread.Row(id: id, isUser: user, time: Date(timeIntervalSince1970: time), text: id)
    }

    private func approval(_ id: UUID = UUID(), origin: UUID? = UUID(), at time: Double,
                          summary: String = "Start the plan for WS-36",
                          inFlight: ApprovalStore.InFlight? = nil) -> ApprovalStore.Item {
        ApprovalStore.Item(id: id, originRequestID: origin, agent: "Developer", tool: "plan_start",
                           summary: summary, receivedAt: Date(timeIntervalSince1970: time),
                           inFlight: inFlight, notice: nil)
    }

    private func run(_ id: Int, name: String = "developer", display: String = "Developer",
                     tools: [String] = [], started: Double, done: Double? = nil) -> AgentRun {
        AgentRun(id: id, name: name, displayName: display, runId: "run-\(id)", task: "private task words",
                 tools: tools, activity: [], stage: 0, startedAt: Date(timeIntervalSince1970: started),
                 doneAt: done.map(Date.init(timeIntervalSince1970:)), ok: false, detail: "",
                 model: "", modelFallback: false, modelUnusable: false, modelUnusableDetail: "",
                 plannerModel: "")
    }

    // MARK: Placement (contract 3.9)

    func testAnchoredApprovalSitsUnderTheTurnItArrivedIn() {
        let rows = [row("u1", user: true, at: 100), row("a1", user: false, at: 101),
                    row("u2", user: true, at: 200), row("a2", user: false, at: 201)]
        let first = approval(at: 150), current = approval(at: 250)
        let items = ConversationThread.items(rows: rows, cards: [], approvals: [current, first])
        XCTAssertEqual(items.map(\.id), ["u1", "a1", "approval-" + first.id.uuidString,
                                         "u2", "a2", "approval-" + current.id.uuidString])
    }

    func testApprovalWithNullOriginEndsTheThread() {
        let rows = [row("u1", user: true, at: 100), row("a1", user: false, at: 101)]
        let loose = approval(origin: nil, at: 50)
        let anchored = approval(at: 102)
        let items = ConversationThread.items(rows: rows, cards: [], approvals: [loose, anchored])
        XCTAssertEqual(items.last?.id, "approval-" + loose.id.uuidString)
        XCTAssertEqual(items.map(\.id).dropLast().last, "approval-" + anchored.id.uuidString)
    }

    func testSettledNoteKeepsTheItemsPlaceWithItsOwnIdentity() {
        let rows = [row("u1", user: true, at: 100), row("a1", user: false, at: 101),
                    row("u2", user: true, at: 200)]
        let id = UUID()
        let note = ApprovalStore.Note(id: id, time: Date(timeIntervalSince1970: 150), text: "Declined.")
        let items = ConversationThread.items(rows: rows, cards: [], approvalNotes: [note])
        XCTAssertEqual(items.map(\.id), ["u1", "a1", "approval-note-" + id.uuidString, "u2"])
        XCTAssertNotEqual("approval-" + id.uuidString, items[2].id)
    }

    // MARK: Activity row (box 192)

    func testActivityNamesTheNewestLiveRunAndItsLatestStep() throws {
        let runs = [run(1, display: "Researcher", tools: ["web_search"], started: 100),
                    run(2, display: "Developer", tools: ["repo_read_file", "plan_start"], started: 200),
                    run(3, display: "Scheduler", tools: ["calendar_list"], started: 300, done: 310)]
        let activity = try XCTUnwrap(ConversationThread.activity(runs: runs, thinking: true))
        XCTAssertEqual(activity.text, "Editing code")
        XCTAssertEqual(activity.runID, 2)
        XCTAssertEqual(activity.accessibilityLabel, "Developer is working: Editing code")
        XCTAssertFalse(activity.text.contains("private task words"))
    }

    func testActivityStartingThinkingAndIdle() {
        XCTAssertEqual(ConversationThread.activity(runs: [run(1, started: 1)], thinking: false)?.text,
                       "Starting")
        XCTAssertEqual(ConversationThread.activity(runs: [], thinking: true)?.text, "Thinking")
        XCTAssertNil(ConversationThread.activity(runs: [], thinking: true)?.runID)
        XCTAssertNil(ConversationThread.activity(runs: [run(1, started: 1, done: 2)], thinking: false))
        XCTAssertNil(ConversationThread.activity(runs: [], thinking: false))
    }

    func testActivityFallsBackToTheAgentId() {
        XCTAssertEqual(ConversationThread.activity(runs: [run(1, name: "developer", display: " ", started: 1)],
                                                   thinking: false)?.actor, "developer")
    }

    // MARK: Words, never colour alone (contract 3.9)

    func testApprovalLabelsCarryTheSummaryAndTheBadgeWords() {
        let item = approval(at: 1, summary: "Push branch claude/ws36")
        XCTAssertEqual(ApprovalRowText.containerLabel(item),
                       "Needs your approval from Developer · plan_start: Push branch claude/ws36")
        XCTAssertEqual(ApprovalRowText.approveLabel(item), "Approve: Push branch claude/ws36")
        XCTAssertEqual(ApprovalRowText.declineLabel(item), "Decline: Push branch claude/ws36")
        XCTAssertEqual(ApprovalRowText.badge, "Needs you")
    }

    // MARK: Space beside push-to-talk

    func testSpaceRoute() {
        typealias R = SpaceKeyRoute
        // Text editing always keeps Space.
        XCTAssertEqual(R.route(isKeyDown: true, isRepeat: false, typingTarget: true,
                               focusedControl: false, connected: true, owned: false), .passThrough)
        // A focused control (an approval button) gets Space instead of the mic.
        XCTAssertEqual(R.route(isKeyDown: true, isRepeat: false, typingTarget: false,
                               focusedControl: true, connected: true, owned: false), .passThrough)
        XCTAssertEqual(R.route(isKeyDown: false, isRepeat: false, typingTarget: false,
                               focusedControl: true, connected: true, owned: false), .passThrough)
        // Nothing focused: push-to-talk as before.
        XCTAssertEqual(R.route(isKeyDown: true, isRepeat: false, typingTarget: false,
                               focusedControl: false, connected: true, owned: false), .startTalking)
        XCTAssertEqual(R.route(isKeyDown: true, isRepeat: true, typingTarget: false,
                               focusedControl: false, connected: true, owned: false), .swallow)
        XCTAssertEqual(R.route(isKeyDown: true, isRepeat: false, typingTarget: false,
                               focusedControl: false, connected: false, owned: false), .swallow)
        // A press that started keeps its repeats and key up even if focus moved.
        XCTAssertEqual(R.route(isKeyDown: true, isRepeat: true, typingTarget: false,
                               focusedControl: true, connected: true, owned: true), .swallow)
        XCTAssertEqual(R.route(isKeyDown: false, isRepeat: false, typingTarget: false,
                               focusedControl: true, connected: true, owned: true), .stopTalking)
    }

    func testSpaceClaims() {
        SpaceKeyClaims.releaseAll()
        defer { SpaceKeyClaims.releaseAll() }
        let a = UUID(), b = UUID()
        SpaceKeyClaims.claim(a); SpaceKeyClaims.claim(b)
        SpaceKeyClaims.release(a)
        XCTAssertTrue(SpaceKeyClaims.isClaimed)
        SpaceKeyClaims.release(b)
        XCTAssertFalse(SpaceKeyClaims.isClaimed)
    }

    // MARK: Typed and approve turns come forward (C7b collision note)

    private func turn(_ request: UUID, sequence: Int, userID: String,
                      session: UUID, generation: UUID) -> [String: JSONValue] {
        ["type": .string("console/turn"), "version": .number(1),
         "session_id": .string(session.uuidString), "generation": .string(generation.uuidString),
         "request_id": .string(request.uuidString), "sequence": .number(Double(sequence)),
         "state": .string("started"), "input_timestamp": .string("typed"),
         "input_user_id": .string(userID)]
    }

    func testExpectedTypedTurnBecomesCurrent() {
        let arrivals = CurrentRequestArrivals()
        let session = UUID(), generation = UUID(), typed = UUID(), turnID = UUID()
        arrivals.expect(.typed, id: typed)
        arrivals.receiveTurn(turn(turnID, sequence: 1, userID: "typed:" + typed.uuidString.lowercased(),
                                  session: session, generation: generation),
                             sessionID: session, generation: generation)
        XCTAssertTrue(arrivals.canPresent(turnID, tool: "weather_report"))
    }

    func testExpectedApprovalTurnBecomesCurrentOnce() {
        let arrivals = CurrentRequestArrivals()
        let session = UUID(), generation = UUID(), approvalID = UUID()
        arrivals.expect(.approval, id: approvalID)
        let first = UUID(), second = UUID()
        arrivals.receiveTurn(turn(first, sequence: 1, userID: "approval:" + approvalID.uuidString,
                                  session: session, generation: generation),
                             sessionID: session, generation: generation)
        XCTAssertTrue(arrivals.canPresent(first, tool: "plan_start"))
        arrivals.receiveTurn(turn(second, sequence: 2, userID: "approval:" + approvalID.uuidString,
                                  session: session, generation: generation),
                             sessionID: session, generation: generation)
        XCTAssertFalse(arrivals.canPresent(second, tool: "plan_start"), "An expectation is consumed once")
    }

    func testUnexpectedTypedTurnStaysPending() {
        let arrivals = CurrentRequestArrivals()
        let session = UUID(), generation = UUID(), turnID = UUID()
        arrivals.expect(.typed, id: UUID())
        arrivals.receiveTurn(turn(turnID, sequence: 1, userID: "typed:" + UUID().uuidString,
                                  session: session, generation: generation),
                             sessionID: session, generation: generation)
        XCTAssertFalse(arrivals.canPresent(turnID, tool: "weather_report"))
    }

    func testExpectedInputParsing() {
        let id = UUID()
        XCTAssertEqual(CurrentRequestArrivals.expectedInput(fromUserID: "typed:" + id.uuidString.lowercased()),
                       CurrentRequestArrivals.ExpectedInput(kind: .typed, id: id))
        XCTAssertEqual(CurrentRequestArrivals.expectedInput(fromUserID: "approval:" + id.uuidString),
                       CurrentRequestArrivals.ExpectedInput(kind: .approval, id: id))
        XCTAssertNil(CurrentRequestArrivals.expectedInput(fromUserID: "voice:" + id.uuidString))
        XCTAssertNil(CurrentRequestArrivals.expectedInput(fromUserID: "typed:nope"))
        XCTAssertNil(CurrentRequestArrivals.expectedInput(fromUserID: "synthetic-user"))
    }

    func testComposerReportsTheRequestIdItSends() throws {
        let model = TypedComposerModel()
        var sent: [UUID] = []
        var told: [UUID] = []
        model.transmit = { message in
            if case .typedRequest(let request) = message { sent.append(request.requestID) }
        }
        model.appendUserEntry = { _, _ in }
        model.didSend = { told.append($0) }
        model.sessionChanged(sessionID: UUID(), generation: UUID())
        model.draft = "what is the weather"
        let id = try XCTUnwrap(model.submitDraft())
        XCTAssertEqual(told, [id])
        XCTAssertEqual(sent, [id])
    }

    // MARK: Rendered

    func testRenderedThreadShowsNeedsYouSummaryButtonsAndActivity() throws {
        _ = NSApplication.shared
        let conversation = ConversationStore()
        conversation.set([try JSONDecoder().decode(ConversationEntry.self, from: JSONSerialization.data(
            withJSONObject: ["id": "u1", "role": "user", "text": "Plan the next step", "createdAt": 100.0]))])
        let approvals = ApprovalStore()
        let session = UUID(), generation = UUID()
        approvals.sessionChanged(sessionID: session, generation: generation)
        approvals.receive(ApprovalPending(sessionID: session, generation: generation, approvalID: UUID(),
                                          originRequestID: UUID(), agent: "Developer", tool: "plan_start",
                                          summary: "Approval summary marker", ts: 100, expiresAt: 400),
                          now: Date(timeIntervalSince1970: 200))
        let view = NSHostingView(rootView: ConversationThreadView(thinking: true)
            .environment(conversation)
            .environment(WorkspaceStore())
            .environment(approvals)
            .environment(AgentRunStore())
            .environment(\.mortimerReduceMotion, true)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 760, height: 520)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let text = try c7aRenderedText(in: view)
        for expected in ["approvalsummarymarker", "approve", "decline", "thinking"] {
            XCTAssertTrue(text.contains(expected), "missing \(expected) in rendered thread: \(text)")
        }
    }
}
