import SwiftUI
import JarvisKit

struct AdaptiveStageView: View {
    let voiceState: VoiceState
    let wideWindow: Bool
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = false
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace

    var body: some View {
        GeometryReader { geometry in
            if workspace.showsConversation && !compactConversation {
                ZStack {
                    VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse)
                    OrbFieldView(voiceState: voiceState, hidesLettering: true)
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
                        VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse)
                            .frame(height: 150)
                        OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true)
                    }.frame(width: AdaptiveLayoutMetrics.voiceRailWidth)
                    Divider()
                    compactStageContent
                }
            } else {
                VStack(spacing: 0) {
                    compactStageContent
                    Divider()
                    HStack(spacing: 0) {
                        VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse)
                            .frame(width: 140)
                        OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true)
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
