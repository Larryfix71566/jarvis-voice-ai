import Foundation

/// Product-facing state for the unsigned scaffold. It deliberately has no live/connected case.
public enum PhoneAppPreviewState: Equatable, Sendable {
    case disconnected
    case demoInProgress
    case syntheticResult(readiness: String)
    case syntheticResults(items: [PhoneRemoteResultItem], cursor: String, hasMore: Bool)
    case syntheticCardResults(items: [PhoneRemoteResultItem], view: PhoneResultCardView?, ready: Bool, notice: String?)
    case syntheticError(message: String)
}

/// Foundation-only orchestration for the explicitly selected synthetic status demo.
/// The injected client owns checked JSON, exchange cancellation and transport draining.
@MainActor
public final class PhoneAppPreviewModel {
    public static let disconnectedNotice = "Disconnected from Mortimer. Synthetic preview only."

    public private(set) var state: PhoneAppPreviewState = .disconnected

    private let client: PhoneRemoteOperationsClient
    private var publicationID = UUID()
    private var requestInFlight = false
    private var lastCardView: PhoneResultCardView?
    private var resultsGeneration: String?
    private var resultsEpoch: String?
    private var lastAppliedSequence = 0
    private var resumeTraversalHighWater: Int?
    private var resultsByID: [String: PhoneRemoteResultItem] = [:]
    private var subscribers: [UUID: AsyncStream<PhoneAppPreviewState>.Continuation] = [:]

    public init(client: PhoneRemoteOperationsClient) {
        self.client = client
    }

    /// Emits the current state first. Views own the stream and can cancel observation freely.
    public func states() -> AsyncStream<PhoneAppPreviewState> {
        let id = UUID()
        return AsyncStream { continuation in
            subscribers[id] = continuation
            continuation.yield(state)
            continuation.onTermination = { [weak self] _ in
                Task { @MainActor in self?.subscribers.removeValue(forKey: id) }
            }
        }
    }

    /// Sends one status request only after an explicit user action. Repeated taps while busy
    /// are ignored; the client itself enforces its single-exchange/no-replay contract.
    public func runSyntheticDemo() async {
        guard !Task.isCancelled else { return }
        guard !requestInFlight else { return }
        requestInFlight = true
        let capturedPublicationID = publicationID
        publish(.demoInProgress)
        defer { requestInFlight = false }

        do {
            let clientState = await client.state
            let response: PhoneRemoteOperationResponse
            if clientState == .reconnecting {
                response = try await client.reconnect(.sessionStatus)
            } else {
                response = try await client.send(.sessionStatus)
            }
            guard publicationID == capturedPublicationID else { return }
            guard response.operation == .sessionStatus else {
                publish(.syntheticError(message: "The preview response did not match the requested operation."))
                return
            }
            guard response.status == .ok else {
                publish(.syntheticError(message: "Synthetic status returned \(response.status.rawValue)."))
                return
            }
            guard case .sessionStatus(let readiness) = response.payload else {
                publish(.syntheticError(message: "The preview response could not be displayed."))
                return
            }
            publish(.syntheticResult(readiness: readiness))
        } catch let error as PhoneRemoteOperationsClientError {
            guard publicationID == capturedPublicationID else { return }
            publish(.syntheticError(message: Self.safeMessage(for: error)))
        } catch {
            guard publicationID == capturedPublicationID else { return }
            publish(.syntheticError(message: "The synthetic preview could not complete."))
        }
    }

    /// Explicitly requests the complete bounded synthetic collection. It never
    /// runs as a side effect of opening the preview.
    public func runSyntheticResults() async {
        guard !Task.isCancelled, !requestInFlight else { return }
        requestInFlight = true
        let capturedPublicationID = publicationID
        resetResultTraversal()
        publish(.demoInProgress)
        defer { requestInFlight = false }
        do {
            let response = try await client.send(.resultsSnapshot)
            guard publicationID == capturedPublicationID else { return }
            guard response.operation == .resultsSnapshot, response.status == .ok,
                  case .resultsSnapshot(let snapshot) = response.payload else {
                publish(.syntheticError(message: "The synthetic results snapshot was unavailable."))
                return
            }
            guard Self.validSnapshotTransition(snapshot) else { return }
            resultsGeneration = snapshot.generation
            resultsEpoch = snapshot.collectionEpoch
            lastAppliedSequence = snapshot.contentWatermark
            resultsByID = Dictionary(uniqueKeysWithValues: snapshot.items.map { ($0.resultID, $0) })
            publish(.syntheticResults(items: snapshot.items, cursor: snapshot.cursor, hasMore: false))
        } catch let error as PhoneRemoteOperationsClientError {
            guard publicationID == capturedPublicationID else { return }
            publish(.syntheticError(message: Self.safeMessage(for: error)))
        } catch {
            guard publicationID == capturedPublicationID else { return }
            publish(.syntheticError(message: "The synthetic results preview could not complete."))
        }
    }

    /// Applies a fully checked page in one publication. A reset clears all old
    /// cards before another explicit snapshot can be requested.
    public func resumeSyntheticResults() async {
        guard !Task.isCancelled, !requestInFlight,
              case .syntheticResults(_, let cursor, _) = state else { return }
        requestInFlight = true
        let capturedPublicationID = publicationID
        defer { requestInFlight = false }
        do {
            let response = try await client.send(.resultsResume(cursor: cursor))
            guard publicationID == capturedPublicationID else { return }
            guard response.operation == .resultsResume, response.status == .ok,
                  case .resultsResume(let page) = response.payload else {
                publish(.syntheticError(message: "The synthetic results update was unavailable."))
                return
            }
            if page.resetRequired {
                resetResultTraversal()
                publish(.disconnected)
                return
            }
            guard let nextCursor = page.cursor, let hasMore = page.hasMore else {
                publish(.syntheticError(message: "The synthetic results page was incomplete."))
                return
            }
            guard let generation = resultsGeneration, let epoch = resultsEpoch,
                  page.generation == generation, page.collectionEpoch == epoch,
                  let watermark = page.contentWatermark, watermark >= lastAppliedSequence else { return }
            if let resumeTraversalHighWater, watermark != resumeTraversalHighWater { return }
            var nextSequence = lastAppliedSequence
            var merged = resultsByID
            for event in page.events {
                guard nextSequence < Int.max, event.sequence == nextSequence + 1,
                      event.sequence <= watermark else { return }
                if let prior = merged[event.item.resultID] {
                    guard event.item.revision >= prior.revision,
                          event.item.revision != prior.revision || event.item == prior else { return }
                }
                merged[event.item.resultID] = event.item
                nextSequence = event.sequence
            }
            guard merged.count <= 25,
                  (hasMore && page.events.count == 25 && nextSequence < watermark)
                    || (!hasMore && nextSequence == watermark) else {
                return
            }
            let ordered = merged.values.sorted { $0.resultID.utf8.lexicographicallyPrecedes($1.resultID.utf8) }
            resultsByID = merged
            lastAppliedSequence = nextSequence
            resumeTraversalHighWater = hasMore ? (resumeTraversalHighWater ?? watermark) : nil
            publish(.syntheticResults(items: ordered, cursor: nextCursor, hasMore: hasMore))
        } catch let error as PhoneRemoteOperationsClientError {
            guard publicationID == capturedPublicationID else { return }
            publish(.syntheticError(message: Self.safeMessage(for: error)))
        } catch {
            guard publicationID == capturedPublicationID else { return }
            publish(.syntheticError(message: "The synthetic results update could not complete."))
        }
    }

    /// One explicit, bounded snapshot -> view synchronization. Never retries an action.
    public func refreshSyntheticCards() async {
        guard !Task.isCancelled, !requestInFlight else { return }
        requestInFlight = true
        let captured = publicationID
        publishCardState(ready: false)
        defer { requestInFlight = false }
        do {
            let response: PhoneRemoteOperationResponse
            if await client.state == .reconnecting { response = try await client.reconnect(.resultsSnapshot) }
            else { response = try await client.send(.resultsSnapshot) }
            guard publicationID == captured, !Task.isCancelled else { return }
            guard response.status == .ok, case .resultsSnapshot(let snapshot) = response.payload,
                  Self.validSnapshotTransition(snapshot) else { maskCardFailure(); return }
            resultsGeneration = snapshot.generation; resultsEpoch = snapshot.collectionEpoch
            resultsByID = Dictionary(uniqueKeysWithValues: snapshot.items.map { ($0.resultID, $0) })
            lastAppliedSequence = snapshot.contentWatermark; resumeTraversalHighWater = nil
            let viewResponse = try await client.send(.resultsView(generation: snapshot.generation,
                                                               collectionEpoch: snapshot.collectionEpoch))
            guard publicationID == captured, !Task.isCancelled else { return }
            guard viewResponse.status == .ok, case .resultCardView(let view) = viewResponse.payload else {
                maskCardFailure(); return
            }
            guard acceptCardView(view, allowNewIdentity: true) else {
                publishCardState(ready: false, notice: "Results changed. Refresh to sync."); return
            }
            publishCardState(ready: true)
        } catch {
            guard publicationID == captured else { return }
            if !Task.isCancelled, let failure = error as? PhoneRemoteOperationsClientError,
               failure == .transportFailure {
                publishCardState(ready: false, notice: "View change could not be confirmed. Refresh to check.")
            } else {
                // Malformed/correlation and terminal client failures are
                // observable failures, not permission to retain content.
                maskCardFailure()
            }
        }
    }

    public func performCardAction(_ action: PhoneResultCardAction, resultID: String) async {
        guard !Task.isCancelled, !requestInFlight,
              case .syntheticCardResults(_, let current, true, _) = state,
              let view = current, view.allowedOperations.contains(action),
              let target = view.target(for: resultID) else { return }
        requestInFlight = true
        let captured = publicationID
        publishCardState(ready: false)
        defer { requestInFlight = false }
        do {
            let response = try await client.send(.resultCard(action, target))
            guard publicationID == captured, !Task.isCancelled else { return }
            guard response.status == .ok, case .resultCardView(let updated) = response.payload else {
                if response.reason == .requestConflict || response.reason == .requestCapacity {
                    publishCardState(ready: false, notice: "Results changed. Refresh to sync.")
                } else { maskCardFailure() }
                return
            }
            guard response.operation == action.operation, acceptCardView(updated, allowNewIdentity: false) else {
                publishCardState(ready: false, notice: "Results changed. Refresh to sync."); return
            }
            publishCardState(ready: true)
        } catch {
            guard publicationID == captured else { return }
            if !Task.isCancelled, let failure = error as? PhoneRemoteOperationsClientError,
               failure == .transportFailure {
                publishCardState(ready: false, notice: "View change could not be confirmed. Refresh to check.")
            } else {
                // Malformed/correlation and terminal client failures are
                // observable failures, not permission to retain content.
                maskCardFailure()
            }
        }
    }

    private func acceptCardView(_ view: PhoneResultCardView, allowNewIdentity: Bool) -> Bool {
        guard view.generation == resultsGeneration, view.collectionEpoch == resultsEpoch,
              view.cards.count == resultsByID.count,
              view.cards.allSatisfy({ resultsByID[$0.resultID]?.revision == $0.resultRevision }) else { return false }
        if let old = lastCardView {
            let sameIdentity = old.generation == view.generation && old.collectionEpoch == view.collectionEpoch && old.viewID == view.viewID
            guard sameIdentity || allowNewIdentity else { return false }
            if sameIdentity {
                guard view.viewRevision >= old.viewRevision,
                      view.viewRevision != old.viewRevision || view == old else { return false }
            }
        } else if !allowNewIdentity { return false }
        lastCardView = view
        return true
    }

    private func publishCardState(ready: Bool, notice: String? = nil) {
        let items = resultsByID.values.sorted { $0.resultID < $1.resultID }
        publish(.syntheticCardResults(items: items, view: lastCardView, ready: ready, notice: notice))
    }

    private func maskCardFailure() {
        resetResultTraversal()
        publish(.syntheticError(message: "View change could not be confirmed. Refresh to check."))
    }

    /// Invalidates publication synchronously. The caller cancels its task; the checked client
    /// then retains the transport exchange until actual completion before another request.
    public func cancelDemo() {
        publicationID = UUID()
        resetResultTraversal()
        publish(.disconnected)
    }

    /// A scene transition away from active is an observable local privacy event.
    public func applicationDidLoseForeground() {
        cancelDemo()
    }

    private func resetResultTraversal() {
        lastCardView = nil
        resultsGeneration = nil
        resultsEpoch = nil
        lastAppliedSequence = 0
        resumeTraversalHighWater = nil
        resultsByID.removeAll(keepingCapacity: false)
    }

    private static func validSnapshotTransition(_ snapshot: PhoneRemoteResultsSnapshot) -> Bool {
        snapshot.contentWatermark >= 0 && snapshot.items.count <= 25
            && snapshot.items.map(\.resultID) == snapshot.items.map(\.resultID).sorted()
            && Set(snapshot.items.map(\.resultID)).count == snapshot.items.count
    }

    private func publish(_ newState: PhoneAppPreviewState) {
        state = newState
        for continuation in subscribers.values { continuation.yield(newState) }
    }

    private static func safeMessage(for error: PhoneRemoteOperationsClientError) -> String {
        switch error {
        case .busy: return "A synthetic preview is already in progress."
        case .reconnectRequired, .reconnectUnavailable: return "The synthetic exchange was interrupted; select preview again to retry status."
        case .ended: return "The synthetic preview session has ended."
        case .invalidRequest: return "The synthetic request was invalid."
        case .cancelled: return "The synthetic preview was cancelled."
        case .transportFailure: return "The synthetic transport failed."
        case .malformedResponse: return "The synthetic response was invalid."
        }
    }
}
