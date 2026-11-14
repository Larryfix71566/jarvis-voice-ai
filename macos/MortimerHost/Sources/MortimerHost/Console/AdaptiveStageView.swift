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
                                      presentation: voicePresentation)
                            .frame(minHeight: 150, maxHeight: 220)
                    }
                case .rail:
                    HStack(spacing: 0) {
                        VStack(spacing: 0) {
                            VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse, presentation: voicePresentation)
                                .frame(height: 150)
                            OrbFieldView(voiceState: voiceState, hidesLettering: true, presentation: voicePresentation())
                        }.frame(width: AdaptiveLayoutMetrics.voiceRailWidth)
                        Divider()
                        compactStageContent
                    }
                case .bottom:
                    VStack(spacing: 0) {
                        compactStageContent
                        Divider()
                        HStack(spacing: 0) {
                            VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse, presentation: voicePresentation)
                                // Keep the compact rail shallow while giving
                                // the measured lobe enough horizontal travel
                                // to remain legible at the default width.
                                .frame(minWidth: 220, idealWidth: 240, maxWidth: 280)
                            OrbFieldView(voiceState: voiceState, hidesLettering: true, presentation: voicePresentation())
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
            ConversationThreadView(coordinator: coordinator)
        } else {
            GeometryReader { geometry in
                if geometry.size.width >= 900 {
                    HStack(spacing: 12) {
                        ConversationThreadView(coordinator: coordinator)
                            .frame(minWidth: 280, maxWidth: .infinity)
                        Divider()
                        ResultCarouselView(coordinator: coordinator, showsActions: false)
                            .frame(minWidth: 480, maxWidth: .infinity)
                    }
                } else {
                    VStack(spacing: 8) {
                        ConversationThreadView(coordinator: coordinator)
                            .frame(maxHeight: max(120, geometry.size.height * 0.32))
                        Divider()
                        ResultCarouselView(coordinator: coordinator, showsActions: false)
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
