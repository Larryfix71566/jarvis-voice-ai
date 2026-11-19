import SwiftUI
import JarvisKit

/// The three presentations of interface plan §4.1: full conversation (large
/// wave), wide (left voice rail + workspace) and compact (workspace over a
/// shallow bottom wave). Closure C2.3 makes the change between them a
/// 200 ms transition (AppTuning.layoutTransitionSeconds) that is skipped
/// under Reduce Motion, during a pointer drag, or while editing text.
enum AdaptiveLayoutMode: Equatable { case conversation, rail, bottom }

struct AdaptiveStageView: View {
    let voiceState: VoiceState
    let wideWindow: Bool
    /// Supplied by the command-console composition so navigation shares the
    /// same dispatcher as voice actions. Nil supports standalone previews.
    let coordinator: ConsoleActionCoordinator?
    /// Compact conversation is the startup presentation. The console action bar
    /// still lets the user expand it and AppStorage preserves that choice.
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = true
    /// This stage's identity for `WorkspaceStore.setQuietArrivals(_:owner:)`.
    @State private var arrivalOwner = UUID()
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(ConversationStore.self) private var conversation
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    /// Optional so fixtures that host the stage without them still render
    /// (same pattern as ConversationThreadView's approvals and agentRuns).
    @Environment(DisplayResultStore.self) private var displayResults: DisplayResultStore?
    @Environment(ConsoleNoticeState.self) private var notices: ConsoleNoticeState?

    init(voiceState: VoiceState, wideWindow: Bool,
         coordinator: ConsoleActionCoordinator? = nil) {
        self.voiceState = voiceState
        self.wideWindow = wideWindow
        self.coordinator = coordinator
    }

    // Closure C7: measured levels from the native path's own taps, sampled
    // app-scoped at ≤30 Hz by JarvisClient's AudioActivityObserver (the
    // generation lives there now, not in this view — gap G24). A nil
    // snapshot is still explicit: on the WebRTC path, with the meter
    // disabled, or between sessions the presentation reports the level as
    // unavailable rather than drawing silence.
    private func voicePresentation() -> VoicePresentationState {
        VoicePresentationState.derive(connection: client.state, microphoneEnabled: client.micEnabled,
            botSpeaking: client.botIsSpeaking, thinking: client.botIsThinking,
            snapshot: client.audioActivity, generation: client.audioActivityGeneration,
            now: ProcessInfo.processInfo.systemUptime)
    }

    /// ORB_SPEC item 8: pending draft, open approval or file-send offer.
    private var needsYou: Bool { displayResults?.hasPendingDraft ?? false }

    private var notConnected: Bool {
        if case .connected = client.state { return false }
        return true
    }

    /// Interface cleanup Phase 1: one line under the orb replaces OrbFieldView.
    private var orbStatusLine: some View {
        OrbStatusLine(
            status: OrbStatus.derive(connection: client.state, presentation: voicePresentation(),
                                     needsYou: needsYou,
                                     audioOutputNotice: notices?.audioOutputNotice,
                                     speakerGateNotice: notices?.speakerGateNotice,
                                     audioInputNotice: notices?.audioInputNotice),
            onConnect: { Task { await client.connect() } },
            onReconnectAudio: {
                notices?.clearAudioOutputNotice()
                Task { await client.reconnect() }
            },
            onDismissNotice: { notices?.clearAudioOutputNotice() })
    }

    /// Interface cleanup Phase 2: the orb is the microphone (click toggles,
    /// a 350 ms hold talks), so its slots pass `interactive: true`; the
    /// visible mute sits under the one status line so mute never depends on
    /// colour or animation alone. OrbMuteButton hides itself while offline.
    private var orbControls: some View {
        VStack(spacing: 4) {
            orbStatusLine
            OrbMuteButton()
        }
    }

    /// §4.1 (as amended by closure C2.5): the large wave is shown when the
    /// user has returned to conversation and has not chosen to keep the
    /// voice region compact. Returning to conversation does not discard the
    /// active result — it stays selected in history so "Return to
    /// workspace" resumes exactly where the user was.
    static func mode(showsConversation: Bool, compactConversation: Bool,
                     wideWindow: Bool, stageWidth: Double) -> AdaptiveLayoutMode {
        if showsConversation && !compactConversation { return .conversation }
        if wideWindow && stageWidth >= AdaptiveLayoutMetrics.minimumRailStageWidth { return .rail }
        return .bottom
    }

    var body: some View {
        GeometryReader { geometry in
            let mode = Self.mode(showsConversation: workspace.showsConversation,
                                 compactConversation: compactConversation,
                                 wideWindow: wideWindow, stageWidth: geometry.size.width)
            Group {
                switch mode {
                case .conversation:
                    VStack(spacing: 0) {
                        conversationAndResults
                        Divider()
                        VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse,
                                      needsYou: needsYou, interactive: true,
                                      presentation: voicePresentation)
                            .frame(minHeight: 150, maxHeight: 220)
                        orbControls
                    }
                case .rail:
                    HStack(spacing: 0) {
                        VStack(spacing: 0) {
                            VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse,
                                          needsYou: needsYou, interactive: true,
                                      presentation: voicePresentation)
                                .frame(height: AdaptiveLayoutMetrics.railOrbSlotHeight)
                            orbControls
                            Spacer(minLength: 0)
                        }.frame(width: AdaptiveLayoutMetrics.voiceRailWidth)
                        Divider()
                        compactStageContent
                    }
                case .bottom:
                    VStack(spacing: 0) {
                        compactStageContent
                        Divider()
                        HStack(spacing: 0) {
                            VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse,
                                          needsYou: needsYou, interactive: true,
                                      presentation: voicePresentation)
                                // Keep the compact rail shallow while giving
                                // the measured lobe enough horizontal travel
                                // to remain legible at the default width.
                                .frame(minWidth: 220, idealWidth: 240, maxWidth: 280)
                            orbControls
                        }.frame(height: 180)
                    }
                }
            }
            .animation(AdaptiveTransition.animation(reduceMotion: reduceMotion), value: mode)
        }
        // C5 always keeps transcript arrivals quiet unless the router has
        // attested the still-active request. Stage ownership remains paired.
        .onAppear { workspace.setQuietArrivals(true, owner: arrivalOwner) }
        .onDisappear { workspace.releaseQuietArrivals(owner: arrivalOwner) }
    }

    /// C5 owns this content slot only. Voice/orb slots above stay unchanged.
    private var compactStageContent: some View {
        VStack(spacing: 0) {
            if workspace.showsSkills || workspace.showsMemoryGraph || workspace.showsAtlas
                || workspace.showsWorkflows || workspace.comparisonResult != nil {
                ArrivalNoticeView(coordinator: coordinator)
            }
            stageBody
        }
    }

    @ViewBuilder
    private var conversationAndResults: some View {
        if workspace.carouselResults.isEmpty {
            ConversationThreadView(coordinator: coordinator, thinking: client.botIsThinking, offline: notConnected)
        } else {
            GeometryReader { geometry in
                if geometry.size.width >= 900 {
                    HStack(spacing: 12) {
                        ConversationThreadView(coordinator: coordinator, thinking: client.botIsThinking, offline: notConnected)
                            .frame(minWidth: 280, maxWidth: .infinity)
                        Divider()
                        ResultCarouselView(coordinator: coordinator, showsActions: false,
                                           glowActivity: voicePresentation().activity)
                            .frame(minWidth: 480, maxWidth: .infinity)
                    }
                } else {
                    VStack(spacing: 8) {
                        ConversationThreadView(coordinator: coordinator, thinking: client.botIsThinking, offline: notConnected)
                            .frame(maxHeight: max(120, geometry.size.height * 0.32))
                        Divider()
                        ResultCarouselView(coordinator: coordinator, showsActions: false,
                                           glowActivity: voicePresentation().activity)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var stageBody: some View {
        if workspace.showsSkills {
            SkillsWorkspaceView(coordinator: coordinator)
        } else if !workspace.showsMemoryGraph && !workspace.showsAtlas
                    && !workspace.showsWorkflows && workspace.comparisonResult == nil {
            conversationAndResults
        } else { WorkspaceView(coordinator: coordinator, showsControls: false) }
    }

}
