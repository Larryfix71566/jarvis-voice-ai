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
    private var stateSink: AnyCancellable?
    private var audioOutputSink: AnyCancellable?
    private var audioInputSink: AnyCancellable?
    private var lastState: JarvisClient.ConnectionState = .offline

    func start(
        client: JarvisClient,
        agentRuns: AgentRunStore,
        displayResults: DisplayResultStore,
        displayWindow: DisplayWindowStore,
        workspace: WorkspaceStore? = nil,
        conversation: ConversationStore? = nil,
        drawer: DrawerState? = nil,
        notices: ConsoleNoticeState? = nil
    ) {
        guard task == nil else { return }
        // ConversationStore mirrors JarvisClient.transcript (P8/P16) —
        // now live: JarvisClient aggregates the bot's own RTVI
        // user-transcription / bot-llm-text frames (2026-08-30).
        if let conversation {
            transcriptSink = client.$transcript.sink { entries in
                conversation.set(entries)
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
        task = Task {
            for await message in client.messageStream() {
                switch message {
                case .agentWorking, .agentDone, .agentTool, .agentActivity, .capability:
                    // E3: delegation tick / outcome tones (OrbField.tsx:125-127).
                    if case .agentWorking = message { Sounds.play(.tick) }
                    if case .agentDone(let done) = message { Sounds.play(done.ok ? .done : .fail) }
                    agentRuns.apply(message)
                case .display(let payload):
                    let result = WorkspaceResult(payload: payload)
                    workspace?.receive(result)
                    switch payload.surface {
                    case .window: displayWindow.apply(payload, workspaceID: result.id)
                    case .drawer:
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

    func stop() {
        task?.cancel()
        task = nil
        transcriptSink = nil
        stateSink = nil
        audioOutputSink = nil
        audioInputSink = nil
    }
}
