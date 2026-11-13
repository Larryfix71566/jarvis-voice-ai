import Foundation
import Combine
import Observation
import JarvisKit

/// C7b (contract 2): the typed-request composer's state and send path.
/// Everything impure (sending, adding the user's line, the reply timeout)
/// is an injected closure so tests drive the model without a JarvisClient;
/// `bind(client:)` installs the real ones.
@MainActor
@Observable
final class TypedComposerModel {
    struct Session: Equatable {
        let sessionID: UUID
        let generation: UUID
    }

    struct Pending: Equatable {
        let requestID: UUID
        let session: Session
        let text: String
        let source: TypedRequest.Source
        let sentAt: Double
    }

    static let replyTimeoutNanoseconds: UInt64 = 10_000_000_000
    /// The bot's reply cache keeps a request id for 300 s.
    static let retryWindowSeconds: Double = 300
    static let connectReason = "Connect to Mortimer to type a request."
    static let staleReason = "This session is no longer current. Reconnect to Mortimer."

    var draft = ""
    private(set) var session: Session?
    private(set) var pending: [UUID: Pending] = [:]
    private(set) var notice: String?
    private(set) var focusRequest = 0
    private var sessionStale = false
    private var lastUnanswered: Pending?

    // Wiring (bind(client:) in the app; closures in tests).
    var transmit: ((ClientMessage) -> Void)?
    var appendUserEntry: ((String, Double) -> Void)?
    /// Called with the request id when a reply is awaited; the app arms the
    /// 10 s timeout here. Tests leave it nil and call `expire(_:)` directly.
    var armTimeout: ((UUID) -> Void)?

    @ObservationIgnored private var subscription: JarvisSubscription?
    @ObservationIgnored private var identitySink: AnyCancellable?

    // MARK: - Derived state

    var isSendingDraft: Bool {
        pending.values.contains { $0.source == .composer }
    }

    var disabledReason: String? {
        if transmit == nil { return "Typing is not connected." }
        if session == nil && sessionStale { return Self.staleReason }
        if session == nil { return Self.connectReason }
        return nil
    }

    var canSubmit: Bool {
        disabledReason == nil && !isSendingDraft
            && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    // MARK: - Wiring

    func bind(client: JarvisClient) {
        guard subscription == nil else { return }
        transmit = { [weak client] message in client?.send(message) }
        appendUserEntry = { [weak client] text, sentAt in
            client?.appendTypedUserEntry(text, sentAt: sentAt)
        }
        armTimeout = { [weak self] id in
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: TypedComposerModel.replyTimeoutNanoseconds)
                self?.expire(id)
            }
        }
        subscription = client.subscribe { [weak self] message in
            if case .turnResult(let result) = message { self?.receive(result) }
        }
        identitySink = client.$consoleSessionID
            .combineLatest(client.$consoleGeneration)
            .sink { [weak self] pair in
                guard let self else { return }
                if let sessionID = pair.0, let generation = pair.1 {
                    self.sessionChanged(sessionID: sessionID, generation: generation)
                } else {
                    self.sessionEnded()
                }
            }
    }

    /// Command-K: focus only, never sends.
    func requestFocus() {
        focusRequest += 1
    }

    // MARK: - Session identity

    func sessionChanged(sessionID: UUID, generation: UUID) {
        let next = Session(sessionID: sessionID, generation: generation)
        if session != next { dropPending() }
        session = next
        sessionStale = false
    }

    func sessionEnded() {
        dropPending()
        session = nil
        sessionStale = false
    }

    private func dropPending() {
        let hadPending = !pending.isEmpty
        pending = [:]
        lastUnanswered = nil
        if hadPending { notice = "Not sent: the connection changed. Send again." }
    }

    // MARK: - Sending

    @discardableResult
    func submitDraft(now: Date = Date()) -> UUID? {
        guard !isSendingDraft else { return nil }
        return send(text: draft, source: .composer, now: now)
    }

    @discardableResult
    func send(text: String, source: TypedRequest.Source, now: Date = Date()) -> UUID? {
        guard let session, let transmit else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        if let rejection = Self.localRejection(trimmed) {
            notice = rejection
            return nil
        }
        let sentAt = now.timeIntervalSince1970
        let requestID = reusableID(session: session, text: trimmed, source: source, sentAt: sentAt)
        lastUnanswered = nil
        pending[requestID] = Pending(requestID: requestID, session: session, text: trimmed,
                                     source: source, sentAt: sentAt)
        notice = nil
        transmit(.typedRequest(TypedRequest(
            sessionID: session.sessionID, generation: session.generation,
            requestID: requestID, text: trimmed, source: source)))
        armTimeout?(requestID)
        return requestID
    }

    private func reusableID(session: Session, text: String,
                            source: TypedRequest.Source, sentAt: Double) -> UUID {
        if let last = lastUnanswered, last.session == session, last.text == text,
           last.source == source, sentAt - last.sentAt <= Self.retryWindowSeconds {
            return last.requestID
        }
        return UUID()
    }

    // MARK: - Replies

    func receive(_ result: TurnResult) {
        guard result.version == 1, let entry = pending[result.requestID] else { return }
        if result.code == "stale_session" {
            receiveStale(result)
            return
        }
        let reply = Session(sessionID: result.sessionID, generation: result.generation)
        guard reply == entry.session else { return }
        pending[result.requestID] = nil
        if result.isAccepted {
            lastUnanswered = nil
            appendUserEntry?(entry.text, entry.sentAt)
            if entry.source == .composer,
               draft.trimmingCharacters(in: .whitespacesAndNewlines) == entry.text {
                draft = ""
            }
            notice = nil
        } else {
            notice = Self.reason(forCode: result.code)
        }
    }

    private func receiveStale(_ result: TurnResult) {
        pending[result.requestID] = nil
        lastUnanswered = nil
        let reply = Session(sessionID: result.sessionID, generation: result.generation)
        if reply == session {
            notice = "The connection changed while sending. Send again."
        } else {
            session = nil
            sessionStale = true
        }
    }

    func expire(_ requestID: UUID) {
        guard let entry = pending[requestID] else { return }
        pending[requestID] = nil
        lastUnanswered = entry
        notice = "No answer from Mortimer. Send again."
    }

    // MARK: - Wording

    static func localRejection(_ trimmed: String) -> String? {
        if trimmed.unicodeScalars.count > TypedRequest.maxScalars {
            return "That is too long. 4,000 characters at most."
        }
        if trimmed.lowercased().hasPrefix("[system]") {
            return "A request can't start with [system]."
        }
        return nil
    }

    static func reason(forCode code: String) -> String {
        switch code {
        case "invalid_text": return "Mortimer can't take that text. Remove unusual characters or shorten it."
        case "not_ready": return "Mortimer wasn't ready. Try again."
        case "disabled": return "Typed requests are turned off."
        case "duplicate": return "Mortimer already has that request."
        case "stale_session": return staleReason
        default: return "Mortimer didn't accept that request."
        }
    }
}
