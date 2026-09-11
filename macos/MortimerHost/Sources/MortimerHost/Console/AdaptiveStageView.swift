import SwiftUI
import JarvisKit

struct AdaptiveStageView: View {
    let voiceState: VoiceState
    let wideWindow: Bool
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = false
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace

    // P0 has not yet proven an input/playout adapter. Missing measurements are
    // explicit; this fallback is not completion of dual-speaker metering.
    @State private var observationGeneration = UUID()
    private func voicePresentation() -> VoicePresentationState {
        VoicePresentationState.derive(connection: client.state, microphoneEnabled: client.micEnabled,
            botSpeaking: client.botIsSpeaking, thinking: client.botIsThinking,
            snapshot: nil, generation: observationGeneration, now: ProcessInfo.processInfo.systemUptime)
    }

    var body: some View {
        GeometryReader { geometry in
            if workspace.showsConversation && !compactConversation {
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
            } else if wideWindow && geometry.size.width >= AdaptiveLayoutMetrics.minimumRailStageWidth {
                HStack(spacing: 0) {
                    VStack(spacing: 0) {
                        VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse, presentation: voicePresentation)
                            .frame(height: 150)
                        OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true, presentation: voicePresentation())
                    }.frame(width: AdaptiveLayoutMetrics.voiceRailWidth)
                    Divider()
                    compactStageContent
                }
            } else {
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
