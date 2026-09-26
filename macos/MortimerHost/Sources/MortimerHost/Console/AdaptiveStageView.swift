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
    /// same dispatcher as voice actions. Nil preserves legacy previews.
    let coordinator: ConsoleActionCoordinator?
    /// Compact conversation is the startup presentation. The button below
    /// still lets the user expand it and AppStorage preserves that choice.
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = true
    @AppStorage("mortimer.interface.layoutVersion") private var layoutVersion = 2
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(ConversationStore.self) private var conversation
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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
                        HStack {
                            Text("Command Center")
                                .font(.system(size: 24, weight: .semibold))
                            Spacer()
                            conversationControls
                        }
                        .padding(.horizontal, AdaptiveLayoutMetrics.workspacePadding)
                        .padding(.top, AdaptiveLayoutMetrics.workspacePadding)
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 10) {
                                if conversation.entries.isEmpty {
                                    ContentUnavailableView("Ready", systemImage: "waveform",
                                        description: Text("Use the microphone controls to start a conversation."))
                                } else {
                                    ForEach(InterfaceLayoutVersion.resolve(layoutVersion) == 2 ? conversation.latestCaptions : conversation.entries) { entry in
                                        Text(InterfaceLayoutVersion.resolve(layoutVersion) == 2 ? ConversationStore.liveCaption(entry.text) : entry.text)
                                            .font(.system(size: 15))
                                            .textSelection(.enabled)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                            .padding(12)
                                            .background(AppTheme.panel.opacity(0.7))
                                            .clipShape(RoundedRectangle(cornerRadius: 10))
                                    }
                                }
                            }
                            .padding(AdaptiveLayoutMetrics.workspacePadding)
                        }
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
                            OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true, presentation: voicePresentation())
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
                            OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true, presentation: voicePresentation())
                        }.frame(height: 180)
                    }
                }
            }
            .animation(AdaptiveTransition.animation(reduceMotion: reduceMotion), value: mode)
        }
    }

    @ViewBuilder
    private var conversationControls: some View {
        Button(compactConversation ? "Expand voice" : "Keep voice compact") {
            compactConversation.toggle()
        }
        Button("Knowledge Atlas") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "atlas") }
            else { workspace.openAtlas() }
        }
        Button("Memory graph") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "memory") }
            else { workspace.openMemoryGraph() }
        }
        Button("Workflows") {
            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "workflows") }
            else { workspace.openWorkflows() }
        }
        if workspace.activeResult != nil || workspace.showsMemoryGraph {
            Button("Return to workspace") {
                if let coordinator { _ = coordinator.executePointer(.viewSet, target: "results") }
                else { workspace.returnToWorkspace() }
            }
        }
    }

    @ViewBuilder
    private var compactStageContent: some View {
        if workspace.showsConversation {
            VStack(alignment: .leading, spacing: 16) {
                HStack { conversationControls; Spacer(minLength: 0) }
                Spacer()
                Text("Conversation").font(.title2)
                Text("Use the microphone controls to talk. Your results stay available in the workspace.")
                    .foregroundStyle(AppTheme.textDim)
                Spacer()
            }
            .padding(AdaptiveLayoutMetrics.workspacePadding)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        } else { WorkspaceView(coordinator: coordinator) }
    }

}
