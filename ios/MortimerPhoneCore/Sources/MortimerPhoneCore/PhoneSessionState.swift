public enum PhoneSessionState: Equatable, Sendable {
    case idle
    case requesting(requestID: String)
    case reconnecting
    case ready(requestID: String)
    case denied
    case unavailable
    case incompatible
    case ended
}

public enum PhoneSessionAction: Sendable {
    case beginRequest(requestID: String)
    case transportInterrupted
    case reconnectRequested(requestID: String)
    case response(requestID: String, status: PhoneRemoteStatus)
    case end
}

public struct PhoneSessionStateMachine: Sendable {
    public private(set) var state: PhoneSessionState = .idle
    private var usedRequestIDs = Set<String>()

    public init() {}

    /// Applies local lifecycle events. A reconnecting session only resumes after
    /// the caller supplies a new explicit `reconnectRequested` action.
    public mutating func apply(_ action: PhoneSessionAction) {
        switch action {
        case .beginRequest(let requestID):
            guard state != .ended, usedRequestIDs.insert(requestID).inserted else { return }
            state = .requesting(requestID: requestID)
        case .transportInterrupted:
            guard isRequesting || isReady else { return }
            state = .reconnecting
        case .reconnectRequested(let requestID):
            guard state == .reconnecting, usedRequestIDs.insert(requestID).inserted else { return }
            state = .requesting(requestID: requestID)
        case .response(let requestID, let status):
            guard state == .requesting(requestID: requestID) else { return }
            switch status {
            case .ok: state = .ready(requestID: requestID)
            case .denied: state = .denied
            case .unavailable: state = .unavailable
            case .incompatible: state = .incompatible
            }
        case .end:
            state = .ended
        }
    }

    private var isRequesting: Bool {
        if case .requesting = state { return true }
        return false
    }

    private var isReady: Bool {
        if case .ready = state { return true }
        return false
    }
}
