import SwiftUI

struct VoiceConsoleView: View {
    let voiceState: VoiceState
    var presentation: (() -> VoicePresentationState)? = nil

    var body: some View {
        VoiceWaveView(voiceState: voiceState, presentation: presentation)
            .frame(minWidth: 220, idealWidth: 280, maxWidth: 420,
                   minHeight: 120, idealHeight: 180)
            .accessibilityElement(children: .contain)
    }
}
