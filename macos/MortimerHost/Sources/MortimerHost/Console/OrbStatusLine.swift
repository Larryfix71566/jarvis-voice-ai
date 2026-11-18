import SwiftUI
import JarvisKit

/// Interface cleanup Phase 1 (docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md).
/// The one line of status under the orb. It replaces OrbFieldView's stack of
/// name, state label, captions, notices and agent chips. Pure value plus a
/// small view, so tests need no JarvisClient.
struct OrbStatus: Equatable {
    enum Tone: Equatable { case quiet, attention }
    enum Action: Equatable { case connect, reconnectAudio }

    let text: String
    let tone: Tone
    let action: Action?

    /// One line, highest priority first: not connected, the audio-output
    /// notice (it carries an action), needs-you, the speaker-gate notice, the
    /// audio-input notice, connecting, then the plain voice state.
    static func derive(connection: JarvisClient.ConnectionState,
                       presentation: VoicePresentationState,
                       needsYou: Bool,
                       audioOutputNotice: String?,
                       speakerGateNotice: String?,
                       audioInputNotice: String?) -> OrbStatus {
        switch connection {
        case .offline:
            return OrbStatus(text: "Not connected", tone: .quiet, action: .connect)
        case .failed:
            return OrbStatus(text: "Couldn't connect", tone: .attention, action: .connect)
        case .connecting, .connected:
            break
        }
        if let notice = audioOutputNotice {
            return OrbStatus(text: notice, tone: .attention, action: .reconnectAudio)
        }
        if needsYou {
            return OrbStatus(text: "Needs your approval", tone: .attention, action: nil)
        }
        if let notice = speakerGateNotice {
            return OrbStatus(text: notice, tone: .attention, action: nil)
        }
        if let notice = audioInputNotice {
            return OrbStatus(text: notice, tone: .quiet, action: nil)
        }
        if connection == .connecting {
            return OrbStatus(text: "Connecting", tone: .quiet, action: nil)
        }
        if let overlap = presentation.overlapLabel {
            return OrbStatus(text: "\(presentation.label) · \(overlap)", tone: .quiet, action: nil)
        }
        return OrbStatus(text: presentation.label, tone: .quiet, action: nil)
    }
}

struct OrbStatusLine: View {
    let status: OrbStatus
    var onConnect: () -> Void = {}
    var onReconnectAudio: () -> Void = {}
    var onDismissNotice: () -> Void = {}

    var body: some View {
        VStack(spacing: 8) {
            Text(status.text)
                .font(.callout)
                .foregroundStyle(status.tone == .attention ? AppTheme.attn : AppTheme.textDim)
                .multilineTextAlignment(.center)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(status.text)
                .accessibilityIdentifier("orb.status")
            if status.action == .connect {
                Button("Connect", action: onConnect)
                    .accessibilityLabel("Connect to Mortimer")
                    .accessibilityIdentifier("orb.connect")
            } else if status.action == .reconnectAudio {
                HStack(spacing: 8) {
                    Button("Reconnect", action: onReconnectAudio)
                    Button("Dismiss", action: onDismissNotice)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
    }
}
