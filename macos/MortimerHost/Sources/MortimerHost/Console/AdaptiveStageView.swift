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
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = false
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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
                    ZStack {
                        VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse, presentation: voicePresentation)
                        OrbFieldView(voiceState: voiceState, hidesLettering: true, presentation: voicePresentation())
                        VStack {
                            HStack {
                                Spacer()
                                conversationControls
                            }
                            Spacer()
                        }.padding(16)
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
                                .frame(width: 140)
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
        Button("Memory graph") { workspace.openMemoryGraph() }
        if workspace.activeResult != nil || workspace.showsMemoryGraph {
            Button("Return to workspace") { workspace.returnToWorkspace() }
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
        } else { WorkspaceView() }
    }

}
