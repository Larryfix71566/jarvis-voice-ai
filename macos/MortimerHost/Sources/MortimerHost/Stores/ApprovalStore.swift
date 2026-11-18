import Foundation
import Combine
import Observation
import JarvisKit

/// C7a (contract 3.9): the open approvals the bot published for this
/// connection, keyed by `approval_id`, and the one-line outcomes the thread
/// shows when an item leaves. Everything impure (sending, the reply
/// timeout) is an injected closure so tests drive the store without a
/// JarvisClient; `bind(client:)` installs the real ones, the way
/// TypedComposerModel does.
///
/// The store never approves anything by itself. A decision is sent only
/// from `decide(_:_:)`, which only the thread's Approve and Decline buttons
/// call, and the bot owns the gate (contract 3.2).
@MainActor
@Observable
final class ApprovalStore {
    struct Session: Equatable {
        let sessionID: UUID
        let generation: UUID
    }

    /// One open approval as the thread shows it. `summary`, `agent` and
    /// `tool` are the bot's text and are rendered verbatim.
    struct Item: Identifiable, Equatable {
        let id: UUID
        let originRequestID: UUID?
        let agent: String
        let tool: String
        let summary: String
        let receivedAt: Date
        /// The decision waiting for `approval/result` or `approval/settled`.
        /// The buttons are disabled while it is set (contract 3.9).
        var inFlight: InFlight?
        /// One line under the item, e.g. after `not_ready`.
        var notice: String?

        var isBusy: Bool { inFlight != nil }
        /// "Developer · plan_start", the item's name in the thread.
        var title: String {
            [agent, tool].map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }.joined(separator: " · ")
        }
    }

    struct InFlight: Equatable {
        let requestID: UUID
        let decision: ApprovalDecide.Decision
    }

    /// The one line left in the thread where an item was. Fixed app text,
    /// never bot text (contract 3.9: "uses no bot text").
    struct Note: Identifiable, Equatable {
        let id: UUID
        let time: Date
        let text: String
    }

    static let replyTimeoutNanoseconds: UInt64 = 10_000_000_000
    static let maxNotes = 20

    private(set) var items: [Item] = []
    private(set) var notes: [Note] = []
    private(set) var session: Session?

    // Wiring (bind(client:) in the app; closures in tests).
    var transmit: ((ClientMessage) -> Void)?
    var armTimeout: ((UUID) -> Void)?
    /// Called with the approval id when an approve is sent, so the router
    /// can bring that turn's answer to the front (`approval:<id>`, 3.8).
    var didSendApprove: ((UUID) -> Void)?

    @ObservationIgnored private var subscription: JarvisSubscription?
    @ObservationIgnored private var identitySink: AnyCancellable?

    var hasOpenItems: Bool { !items.isEmpty }

    // MARK: - Wiring

    func bind(client: JarvisClient) {
        guard subscription == nil else { return }
        transmit = { [weak client] message in client?.send(message) }
        armTimeout = { [weak self] id in
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: ApprovalStore.replyTimeoutNanoseconds)
                self?.expire(requestID: id)
            }
        }
        subscription = client.subscribe { [weak self] message in
            self?.receive(message)
        }
        identitySink = client.$consoleSessionID
            .combineLatest(client.$consoleGeneration)
            .sink { [weak self] pair in
                guard let self else { return }
                if let sessionID = pair.0, let generation = pair.1 {
                    self.sessionChanged(sessionID: sessionID, generation: generation)
                } else {
                    // Disconnect clears the store (contract 3.9).
                    self.sessionEnded()
                }
            }
    }

    func receive(_ message: AppMessage) {
        switch message {
        case .approvalPending(let pending): receive(pending)
        case .approvalSettled(let settled): receive(settled)
        case .approvalResult(let result): receive(result)
        default: break
        }
    }

    // MARK: - Session identity

    func sessionChanged(sessionID: UUID, generation: UUID) {
        let next = Session(sessionID: sessionID, generation: generation)
        if session != next { items = []; notes = [] }
        session = next
    }

    func sessionEnded() {
        items = []
        notes = []
        session = nil
    }

    // MARK: - Bot messages

    func receive(_ pending: ApprovalPending, now: Date = Date()) {
        guard let session,
              pending.isValid(sessionID: session.sessionID, generation: session.generation) else { return }
        let item = Item(id: pending.approvalID, originRequestID: pending.originRequestID,
                        agent: pending.agent, tool: pending.tool, summary: pending.summary,
                        receivedAt: now, inFlight: nil, notice: nil)
        if let index = items.firstIndex(where: { $0.id == item.id }) {
            items[index] = item
        } else {
            items.append(item)
        }
    }

    func receive(_ settled: ApprovalSettled, now: Date = Date()) {
        guard settled.version == 1, let session,
              settled.sessionID == session.sessionID, settled.generation == session.generation,
              ApprovalSettled.states.contains(settled.state) else { return }
        // A settle for an unknown id is ignored (3.5).
        remove(settled.approvalID, note: Self.note(forState: settled.state), now: now)
    }

    func receive(_ result: ApprovalResult, now: Date = Date()) {
        guard result.version == 1,
              let index = items.firstIndex(where: { $0.inFlight?.requestID == result.requestID }),
              items[index].id == result.approvalID else { return }
        if result.code == "stale_session" {
            // 3.7: the one code accepted with a differing session; clear.
            items = []
            notes = []
            if let session, Session(sessionID: result.sessionID, generation: result.generation) != session {
                self.session = nil
            }
            return
        }
        guard let session, result.sessionID == session.sessionID,
              result.generation == session.generation else { return }
        let decision = items[index].inFlight?.decision
        if result.isAccepted {
            // `approval/settled` follows and removes the item; keep the
            // buttons disabled until it does.
            return
        }
        switch result.code {
        case "unknown_approval", "already_settled":
            remove(result.approvalID, note: "No longer waiting.", now: now)
        case "expired":
            remove(result.approvalID, note: Self.note(forState: "expired"), now: now)
        case "not_ready":
            // 3.8 rule 4: nothing settled, the item stays open; a second
            // tap is a new decision with a new request id.
            items[index].inFlight = nil
            items[index].notice = decision == .decline
                ? "Mortimer couldn't take that. Try again."
                : "Mortimer couldn't start it. Try again."
        default:
            // duplicate, protected_turn, disabled: the item stays and the
            // buttons come back; settled (if any) is the bot's to send.
            items[index].inFlight = nil
            items[index].notice = Self.reason(forCode: result.code)
        }
    }

    // MARK: - Decisions

    /// Send one decision for one open item. Returns the request id, or nil
    /// when nothing was sent (no session, no item, already in flight).
    @discardableResult
    func decide(_ approvalID: UUID, _ decision: ApprovalDecide.Decision) -> UUID? {
        guard let session, let transmit,
              let index = items.firstIndex(where: { $0.id == approvalID }),
              items[index].inFlight == nil else { return nil }
        let requestID = UUID()
        items[index].inFlight = InFlight(requestID: requestID, decision: decision)
        items[index].notice = nil
        if decision == .approve { didSendApprove?(approvalID) }
        transmit(.approvalDecide(ApprovalDecide(
            sessionID: session.sessionID, generation: session.generation,
            requestID: requestID, approvalID: approvalID, decision: decision)))
        armTimeout?(requestID)
        return requestID
    }

    /// No reply within the timeout: the buttons come back. A retry is a new
    /// tap and a new request id (3.7).
    func expire(requestID: UUID) {
        guard let index = items.firstIndex(where: { $0.inFlight?.requestID == requestID }) else { return }
        items[index].inFlight = nil
        items[index].notice = "No answer from Mortimer. Try again."
    }

    // MARK: - Helpers

    private func remove(_ approvalID: UUID, note: String, now: Date) {
        guard let index = items.firstIndex(where: { $0.id == approvalID }) else { return }
        let item = items.remove(at: index)
        notes.append(Note(id: item.id, time: item.receivedAt, text: note))
        if notes.count > Self.maxNotes { notes.removeFirst(notes.count - Self.maxNotes) }
    }

    /// Contract 3.9: expired and superseded say which; declined is the one
    /// line "Declined."
    static func note(forState state: String) -> String {
        switch state {
        case "approved": return "Approved."
        case "declined": return "Declined."
        case "resolved": return "Done by voice."
        case "superseded": return "Replaced by a newer request."
        case "expired": return "Expired before an answer."
        default: return "No longer waiting."
        }
    }

    static func reason(forCode code: String) -> String {
        switch code {
        case "protected_turn": return "This one needs your answer by voice."
        case "disabled": return "Approvals in the app are turned off. Answer by voice."
        case "duplicate": return "Mortimer already has that answer."
        default: return "Mortimer didn't take that. Try again."
        }
    }
}
