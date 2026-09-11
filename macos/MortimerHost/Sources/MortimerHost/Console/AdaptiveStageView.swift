import SwiftUI
import JarvisKit

struct AdaptiveStageView: View {
    let voiceState: VoiceState
    let wideWindow: Bool
    @EnvironmentObject private var client: JarvisClient
    @Environment(WorkspaceStore.self) private var workspace

    var body: some View {
        GeometryReader { geometry in
            if workspace.showsConversation {
                ZStack {
                    VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse)
                    OrbFieldView(voiceState: voiceState, hidesLettering: true)
                    if let active = workspace.activeResult {
                        VStack {
                            HStack {
                                Spacer()
                                Button("Return to results") { workspace.select(active.id) }
                            }
                            Spacer()
                        }.padding(16)
                    }
                }
            } else if wideWindow && geometry.size.width >= 680 {
                HStack(spacing: 0) {
                    VStack(spacing: 0) {
                        VoiceWaveView(voiceState: voiceState, wakePulse: client.wakePulse)
                            .frame(height: 150)
                        OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true)
                    }.frame(width: 200)
                    Divider()
                    WorkspaceView()
                }
            } else {
                VStack(spacing: 0) {
                    WorkspaceView()
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
}
