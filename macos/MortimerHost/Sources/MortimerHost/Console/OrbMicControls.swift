import SwiftUI
import JarvisKit

/// Interface cleanup Phase 2: the visible mute control beside the orb. Text
/// and symbol both change with state (never colour alone). Hidden unless
/// connected, so it never offers something that cannot work.
struct OrbMuteButton: View {
    @EnvironmentObject private var client: JarvisClient

    struct Presentation: Equatable {
        let title: String
        let symbol: String
        let accessibilityLabel: String
    }

    /// Pure decision, unit-tested. Nil = do not show.
    static func presentation(connected: Bool, micEnabled: Bool) -> Presentation? {
        guard connected else { return nil }
        return micEnabled
            ? Presentation(title: "Mute", symbol: "mic.fill", accessibilityLabel: "Mute microphone")
            : Presentation(title: "Unmute", symbol: "mic.slash.fill", accessibilityLabel: "Unmute microphone")
    }

    private var connected: Bool {
        if case .connected = client.state { return true }
        return false
    }

    var body: some View {
        if let p = Self.presentation(connected: connected, micEnabled: client.micEnabled) {
            Button {
                client.setMicEnabled(!client.micEnabled)
            } label: {
                Label(p.title, systemImage: p.symbol)
                    .font(.callout)
                    .foregroundStyle(client.micEnabled ? AppTheme.text : AppTheme.amber)
            }
            .buttonStyle(.bordered)
            .accessibilityLabel(p.accessibilityLabel)
            .accessibilityIdentifier("orb.mute")
            .help("Mute or unmute the microphone · hold Space or the orb to talk")
        }
    }
}
