// HostView.swift
// G1(b) harness UI (§5 step 14 / §3 N2). Deliberately unstyled — this is
// a debug harness proving JarvisKit, not a product view.

import SwiftUI
import JarvisKit

struct HostView: View {
    @ObservedObject var client: JarvisClient

    @State private var messages: [String] = []
    @State private var subscription: JarvisSubscription?

    private var micBinding: Binding<Bool> {
        Binding(get: { client.micEnabled }, set: { client.setMicEnabled($0) })
    }

    private var wakeBinding: Binding<Bool> {
        Binding(
            get: { client.wakeWordOn },
            set: { newValue in Task { await client.setWakeWord(newValue) } }
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                connectButton
                Text(String(describing: client.state))
                    .font(.system(.body, design: .monospaced))
                Spacer()
                debugMenu
            }

            Toggle("Mic", isOn: micBinding)
            Toggle("Wake word", isOn: wakeBinding)
                .disabled(!client.wakeWordAvailable)

            Text(debugAudioStatsLine)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)

            Divider()

            List(messages.indices, id: \.self) { index in
                Text(messages[index])
                    .font(.system(.caption, design: .monospaced))
            }
        }
        .padding(16)
        .frame(minWidth: 480, minHeight: 420)
        .onAppear(perform: subscribeToMessages)
    }

    private var connectButton: some View {
        Button(client.state == .offline || isFailed ? "Connect" : "Disconnect") {
            Task {
                if client.state == .offline || isFailed {
                    await client.connect()
                } else {
                    await client.disconnect()
                }
            }
        }
    }

    private var isFailed: Bool {
        if case .failed = client.state { return true }
        return false
    }

    private var debugAudioStatsLine: String {
        let s = client.debugAudioStats
        let lastPing = s.lastKeepAliveAt.map { "\($0)" } ?? "-"
        return "sentBytes=\(s.sentBytes) sentPacketsLastSecond=\(s.sentPacketsLastSecond) micTrackEnabled=\(s.micTrackEnabled) lastKeepAliveAt=\(lastPing)"
    }

    private var debugMenu: some View {
        Menu("Debug") {
            Button("Clear stored token") {
                KeychainStore.setToken(nil, for: client.config.botURL)
            }
        }
    }

    private func subscribeToMessages() {
        guard subscription == nil else { return }
        subscription = client.subscribe { message in
            messages.append(message.debugDescription)
            // Same bounded-history discipline as the rest of the package
            // (JarvisTuning.maxHostMessages, §6).
            if messages.count > JarvisTuning.maxHostMessages {
                messages.removeFirst(messages.count - JarvisTuning.maxHostMessages)
            }
        }
    }
}
