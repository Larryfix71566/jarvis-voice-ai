import SwiftUI
import JarvisKit

/// WS-17 / Command Console plan §7.2, increment CC7a.1: the conversation
/// thread. Layout 2's stage shows both speakers' full text as transcript rows
/// (approved design A2, Larry 2026-09-30) instead of the last two captions
/// truncated to 160 characters, and spoken answers stop becoming workspace
/// results. Structured display payloads (weather, research, images, graph)
/// keep their own route unchanged.
///
/// On by default. `defaults write com.mortimer.host
/// mortimer.interface.conversationThread -bool false` restores the previous
/// stage and per-answer results until CC7a.4 removes the switch.
enum ConversationThread {
    static let flagKey = "mortimer.interface.conversationThread"

    static func isEnabled(_ defaults: UserDefaults = .standard) -> Bool {
        defaults.object(forKey: flagKey) as? Bool ?? true
    }

    /// Codex boundary 1 (CX-15): spoken answers become results only in the
    /// pre-CC7a layout-2 stage. Other layouts never routed them.
    static func routesSpokenAnswersToResults(layoutVersion: Int, threadEnabled: Bool) -> Bool {
        InterfaceLayoutVersion.resolve(layoutVersion) == 2 && !threadEnabled
    }

    static func showsThread(layoutVersion: Int, threadEnabled: Bool) -> Bool {
        InterfaceLayoutVersion.resolve(layoutVersion) == 2 && threadEnabled
    }

    struct Row: Identifiable, Equatable {
        let id: String
        let isUser: Bool
        let time: Date
        /// Full text, trimmed at the ends only. Never truncated.
        let text: String
        var speaker: String { isUser ? "YOU" : "MORTIMER" }
    }

    /// One row per transcript entry, in transcript order. Empty entries
    /// (a stream that has not produced text yet) are skipped.
    static func rows(_ entries: [ConversationEntry]) -> [Row] {
        entries.compactMap { entry in
            let text = entry.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { return nil }
            return Row(id: entry.id, isUser: entry.role == "user",
                       time: Date(timeIntervalSince1970: entry.createdAt), text: text)
        }
    }

    /// Within this many points of the end counts as reading the newest turn.
    static let bottomTolerance = 24.0

    static func isAtBottom(contentHeight: Double, visibleMaxY: Double) -> Bool {
        contentHeight - visibleMaxY <= bottomTolerance
    }

    /// The thread follows new turns only while Larry is at the bottom. When
    /// he has scrolled up to read, new turns are counted for a "New" button
    /// instead of moving the text under him.
    struct Follow: Equatable {
        private(set) var following = true
        private(set) var unseen = 0

        mutating func scrolled(atBottom: Bool) {
            following = atBottom
            if atBottom { unseen = 0 }
        }

        /// Returns whether the view should scroll to the newest row.
        mutating func rowsChanged(added: Int) -> Bool {
            if following { return true }
            unseen += max(0, added)
            return false
        }

        mutating func jumpedToEnd() {
            following = true
            unseen = 0
        }
    }
}

struct ConversationThreadView: View {
    @Environment(ConversationStore.self) private var conversation
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @State private var follow = ConversationThread.Follow()
    private static let endID = "conversation-thread-end"

    var body: some View {
        let rows = ConversationThread.rows(conversation.entries)
        ScrollViewReader { proxy in
            ZStack(alignment: .bottom) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if rows.isEmpty {
                            ContentUnavailableView("Ready", systemImage: "waveform",
                                description: Text("Use the microphone controls to start a conversation."))
                                .padding(.top, 40)
                        }
                        ForEach(rows) { row in
                            ConversationThreadRowView(row: row)
                        }
                        Color.clear.frame(height: 1).id(Self.endID)
                    }
                    .padding(.horizontal, AdaptiveLayoutMetrics.workspacePadding)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .defaultScrollAnchor(.bottom)
                .onScrollGeometryChange(for: Bool.self) { geometry in
                    ConversationThread.isAtBottom(contentHeight: Double(geometry.contentSize.height),
                                                  visibleMaxY: Double(geometry.visibleRect.maxY))
                } action: { _, atBottom in
                    follow.scrolled(atBottom: atBottom)
                }
                .onChange(of: rows.count) { old, new in
                    if follow.rowsChanged(added: new - old) { scrollToEnd(proxy) }
                }
                .onChange(of: rows.last?.text) { _, _ in
                    // A streaming answer grows in place; keep its end in view
                    // only while following.
                    if follow.following { scrollToEnd(proxy) }
                }

                if follow.unseen > 0 {
                    Button {
                        follow.jumpedToEnd()
                        scrollToEnd(proxy)
                    } label: {
                        Label(follow.unseen == 1 ? "1 new" : "\(follow.unseen) new", systemImage: "arrow.down")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(AppTheme.accent.opacity(0.85))
                    .padding(.bottom, 10)
                    .accessibilityLabel("Show \(follow.unseen) new conversation turns")
                }
            }
        }
        .accessibilityIdentifier("conversation-thread")
    }

    private func scrollToEnd(_ proxy: ScrollViewProxy) {
        if reduceMotion {
            proxy.scrollTo(Self.endID, anchor: .bottom)
        } else {
            withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(Self.endID, anchor: .bottom) }
        }
    }
}

/// Approved design A2: a speaker column (YOU / MORTIMER and the time) and
/// the full text at full width, one hairline between turns.
struct ConversationThreadRowView: View {
    let row: ConversationThread.Row

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.speaker)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .kerning(1.2)
                    .foregroundStyle(row.isUser ? AppTheme.accent : AppTheme.textDim)
                Text(row.time.formatted(date: .omitted, time: .shortened))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AppTheme.textDim)
            }
            .frame(width: 84, alignment: .leading)
            Text(row.text)
                .font(.system(size: 15))
                .foregroundStyle(AppTheme.text)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 9)
        .overlay(alignment: .bottom) {
            Rectangle().fill(AppTheme.hairline.opacity(0.6)).frame(height: 1)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(row.isUser ? "You" : "Mortimer"): \(row.text)")
    }
}
