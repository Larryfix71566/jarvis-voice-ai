import Foundation
import Combine
import JarvisKit

/// APP plan §3 P8/P14, §5 step 5 — the ONE messageStream() consumer that
/// feeds the stores (the native form of the web's single-listener rule,
/// agentRuns.ts D10). Started at app scope, before any tab view exists,
/// so no message is missed while a tab is unmounted (§11 item 6).
///
/// Dispatch: agent*/capability → AgentRunStore; display → split by
/// payload.surface (window → DisplayWindowStore, drawer → the Output
/// tab's DisplayResultStore — the decoder already defaults nil/unknown
/// to .drawer, CORE N7); voice*/speakerGate stay with their owners
/// (JarvisClient publishes voices/currentVoice itself); ui belongs to
/// UICommandRouter and MicControls' owner (JarvisClient), never here.
@MainActor
final class AppMessageRouter {
    private var task: Task<Void, Never>?
    private var transcriptSink: AnyCancellable?
    private let responseRouter = ResponseResultRouter()
    private var stateSink: AnyCancellable?
    private var audioOutputSink: AnyCancellable?
    private var audioInputSink: AnyCancellable?
    private var lastState: JarvisClient.ConnectionState = .offline
    // Phase 2 D4 (D-L6): answers the bot's location/request for this session.
    private let locator = DeviceLocator()

    func start(
        client: JarvisClient,
        agentRuns: AgentRunStore,
        displayResults: DisplayResultStore,
        displayWindow: DisplayWindowStore,
        workspace: WorkspaceStore? = nil,
        conversation: ConversationStore? = nil,
        drawer: DrawerState? = nil,
        attachments: AttachmentStore? = nil,
        notices: ConsoleNoticeState? = nil,
        consoleCoordinator: ConsoleActionCoordinator? = nil
    ) {
        guard task == nil else { return }
        // ConversationStore mirrors JarvisClient.transcript (P8/P16) —
        // now live: JarvisClient aggregates the bot's own RTVI
        // user-transcription / bot-llm-text frames (2026-08-30).
        transcriptSink = client.$transcript.sink { [weak self] entries in
            conversation?.set(entries)
            let layout = UserDefaults.standard.object(forKey: "mortimer.interface.layoutVersion") as? Int ?? 2
            if InterfaceLayoutVersion.resolve(layout) == 2, let workspace {
                let previousRevision = workspace.consoleRevision
                self?.responseRouter.receive(entries, workspace: workspace, display: displayWindow)
                if workspace.consoleRevision != previousRevision {
                    consoleCoordinator?.publishInventory()
                }
            }
        }
        // E3 sound hooks on connection transitions: boot on
        // connecting → live (OrbField.tsx:95), fail on an error state
        // (App.tsx:209 — the error banner has a voice too).
        stateSink = client.$state.sink { [weak self] next in
            Task { @MainActor in
                guard let self else { return }
                let prev = self.lastState
                self.lastState = next
                if case .connecting = prev, case .connected = next { Sounds.play(.boot) }
                if case .failed = next { Sounds.play(.fail) }
                // A reconnect (ours or the user's) makes the audio-output
                // notice moot — playout re-opens on the current device.
                if case .connecting = next { notices?.clearAudioOutputNotice() }
            }
        }
        #if os(macOS)
        // 2026-09-05 — default output device changed under a live session
        // (AirPods). JarvisClient only publishes; the chip with the
        // Reconnect action is OrbFieldView's.
        audioOutputSink = client.$audioOutputChange.sink { change in
            Task { @MainActor in
                guard let change else { return }
                Sounds.play(.tick)
                notices?.showAudioOutputNotice(change.noticeText)
            }
        }
        // 2026-09-05 — connect() repointed the default input to a
        // rate-matching mic (AirPods 24 kHz-mic fix). Informational chip.
        audioInputSink = client.$audioInputChange.sink { change in
            Task { @MainActor in
                guard let change else { return }
                notices?.showAudioInputNotice(change.noticeText)
            }
        }
        #endif
        let locator = self.locator
        task = Task {
            for await message in client.messageStream() {
                switch message {
                case .agentWorking, .agentDone, .agentTool, .agentActivity, .capability:
                    // E3: delegation tick / outcome tones (OrbField.tsx:125-127).
                    if case .agentWorking = message { Sounds.play(.tick) }
                    if case .agentDone(let done) = message { Sounds.play(done.ok ? .done : .fail) }
                    agentRuns.apply(message)
                case .voiceCatalog:
                    // The bot sends voice/catalog on every connect, so the
                    // channel is open: announce that this client can answer
                    // location requests (the bot never asks otherwise).
                    locator.start()
                    client.send(.locationHello(LocationHello(authorization: locator.authorization)))
                case .locationRequest(let request):
                    locator.answer(request) { result in
                        client.send(.locationResult(result))
                        guard result.ok, let lat = result.lat, let lon = result.lon else { return }
                        Task { _ = try? await client.admin.reportDeviceLocation(
                            lat: lat, lon: lon, label: result.label ?? "") }
                    }
                case .consoleResult(let result):
                    // Acknowledgement is retained for the shared console
                    // surface. It is deliberately not converted to an
                    // optimistic UI mutation; the coordinator applies state
                    // only after validating the same request locally.
                    notices?.showConsoleResult(result)
                case .consoleHello(let hello):
                    // Capability negotiation is explicit. The client echoes
                    // only the bounded operations it understands and never
                    // treats a server advertisement as user authority.
                    client.send(.consoleReady(sessionID: hello.sessionID,
                                               generation: hello.generation,
                                               actions: hello.actions,
                                               inputTypes: hello.inputTypes))
                    client.setConsoleIdentity(sessionID: hello.sessionID, generation: hello.generation,
                                               inputProfile: hello.inputProfile)
                    consoleCoordinator?.publishInventory()
                case .consoleRequest(let request):
                    // A voice-issued console_action arrives as the same
                    // versioned request used by pointer controls. Execute it
                    // through the app-scoped coordinator and acknowledge the
                    // actual local outcome; no view has a second dispatcher.
                    guard client.consoleSessionID == request.sessionID,
                          client.consoleGeneration == request.generation else {
                        let stale = ConsoleResult(
                            sessionID: request.sessionID, generation: request.generation,
                            requestID: request.requestID, status: "error",
                            code: "stale_session",
                            summary: "This console session is no longer current.")
                        notices?.showConsoleResult(stale)
                        client.send(.consoleResult(stale))
                        break
                    }
                    guard let consoleCoordinator else { break }
                    let outcome = consoleCoordinator.execute(request)
                    let status: String
                    let code: String
                    let summary: String
                    switch outcome {
                    case .applied: status = "ok"; code = "applied"; summary = "Console action applied."
                    case .noop: status = "noop"; code = "no_change"; summary = "That console action changed nothing."
                    case .pendingUser: status = "pending_user"; code = "user_action_required"; summary = "The requested system action is waiting for your choice."
                    case .unsupported: status = "unsupported"; code = "unsupported"; summary = "That console action is unavailable here."
                    case .capacity: status = "error"; code = "panel_limit"; summary = "Return a panel before opening another."
                    case .invalid: status = "error"; code = "invalid_target"; summary = "That console target is no longer available."
                    case .stale: status = "error"; code = "stale_selection"; summary = "The console changed; please choose the item again."
                    }
                    let result = ConsoleResult(sessionID: request.sessionID,
                                                generation: request.generation,
                                                requestID: request.requestID,
                                                status: status, code: code,
                                                summary: summary)
                    notices?.showConsoleResult(result)
                    client.send(.consoleResult(result))
                    consoleCoordinator.publishInventory()
                case .inputStatus(let status):
                    // The staged tray is ephemeral. Clear it only after a
                    // terminal analysis/cancel response; intermediate
                    // manifest/chunk acknowledgements leave retryable UI in
                    // place, and failures remain visible to the user.
                    if status.code == "analysis_complete" || status.status == "cancelled" {
                        attachments?.clear()
                    } else if status.status == "error" {
                        attachments?.stageError(status.summary)
                    }
                case .inputOffer(let offer):
                    // Voice analysis offers are data-only until the user
                    // approves them in the tray. Reject stale offers before
                    // exposing the provider/question to the UI.
                    guard client.consoleSessionID == offer.sessionID,
                          client.consoleGeneration == offer.generation else { break }
                    attachments?.presentOffer(offer)
                case .inputConsent(let consent):
                    guard client.consoleSessionID == consent.sessionID,
                          client.consoleGeneration == consent.generation else { break }
                    attachments?.presentConsent(consent)
                case .display(let payload):
                    let result = WorkspaceResult(payload: payload)
                    // Window-routed content has one renderer at a time. Keep
                    // the workspace as the fallback when no supporting
                    // display is open; while the display is live its view
                    // yields through the locator in WorkspaceView.
                    switch payload.surface {
                    case .window:
                        // An exact repeat is already represented by the same
                        // external renderer and workspace row. Reusing that
                        // owner prevents repeated graph/display requests from
                        // growing a second history while still allowing a
                        // distinct file in one Developer run to append a new
                        // section and workspace row.
                        let existingID = displayWindow.presentedWorkspaceID(for: payload)
                            .flatMap { id in workspace?.containsResult(id) == true ? id : nil }
                        let workspaceID = existingID ?? result.id
                        if existingID == nil { workspace?.receive(result) }
                        let panelID = displayWindow.apply(payload, workspaceID: workspaceID)
                        if let workspace {
                            if Self.isMemoryGraphPayload(payload) {
                                workspace.openMemoryGraph()
                                _ = workspace.sendToDisplay(.memoryGraph)
                            } else if let ownerID = displayWindow.workspaceID(for: panelID) {
                                _ = workspace.sendToDisplay(.result(ownerID))
                            } else {
                                _ = workspace.sendToDisplay(.result(result.id))
                            }
                        }
                    case .drawer:
                        workspace?.receive(result)
                        displayResults.apply(payload, workspaceID: result.id)
                        // D31's three-case auto-open rule (App.tsx:247-254),
                        // drawer-routed results only: closed → open on
                        // Output; open elsewhere → dot; open on Output →
                        // nothing extra, the item just appears.
                        if let drawer {
                            if !drawer.isOpen && !drawer.isPoppedOut {
                                drawer.setTab("output")
                                drawer.isOpen = true
                            } else if drawer.activeTab != "output" {
                                drawer.outputDot = true
                            }
                        }
                    }
                    consoleCoordinator?.publishInventory()
                case .speakerGate(let gate):
                    // F4 — a near-threshold drop (plausibly Larry, not the
                    // TV) surfaces a brief auto-fading chip; TV drops
                    // (near_threshold false) render NOTHING (App.tsx:227-236).
                    if gate.nearThreshold == true {
                        notices?.showSpeakerGateNotice("Voice not recognized — try again")
                    }
                default:
                    break
                }
            }
        }
    }

    private static func isMemoryGraphPayload(_ payload: DisplayPayload) -> Bool {
        let values = [payload.kind, payload.title, payload.tool]
            .compactMap { $0?.lowercased() }
        if values.contains(where: { $0.contains("memory_graph") || $0.contains("memory graph") }) {
            return true
        }
        return payload.images?.contains { image in
            image.lowercased().contains("/graph/memory")
        } == true
    }

    func stop() {
        task?.cancel()
        task = nil
        transcriptSink = nil
        stateSink = nil
        audioOutputSink = nil
        audioInputSink = nil
    }
}
