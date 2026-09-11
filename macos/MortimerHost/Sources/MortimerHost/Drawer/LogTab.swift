import SwiftUI
import JarvisKit

/// The Log tab, matched to web/src/components/Transcript.tsx (E7, parity
/// sweep 2026-08-30): spoken bubbles (now LIVE — JarvisClient aggregates
/// the bot's own RTVI transcription/llm-text frames) interleaved with
/// run-event chips ("→ Analyst" at start, "✓/✗ Analyst" at completion),
/// ordered by timestamp so the Log tells the session's story, not just
/// its words. Auto-scrolls to the newest entry.
struct LogTab: View {
    @Environment(DrawerModels.self) private var models
    @Environment(ConversationStore.self) private var conversation
    @Environment(AgentRunStore.self) private var agentRuns

    private enum Tone { case start, ok, fail }

    private enum LogItem: Identifiable {
        case bubble(ConversationEntry)
        case chip(id: String, at: Date, label: String, tone: Tone)

        var id: String {
            switch self {
            case .bubble(let entry): return "c-\(entry.id)"
            case .chip(let id, _, _, _): return id
            }
        }

        var timestamp: Date {
            switch self {
            case .bubble(let entry): return Date(timeIntervalSince1970: entry.createdAt)
            case .chip(_, let at, _, _): return at
            }
        }
    }

    /// Transcript.tsx:37-62 — one flow item per message, plus a start
    /// chip per run and a completion chip per settled run.
    private var items: [LogItem] {
        let bubbles = conversation.entries.map(LogItem.bubble)
        let chips = agentRuns.runs.flatMap { run -> [LogItem] in
            var out: [LogItem] = [
                .chip(id: "r-\(run.id)-start", at: run.startedAt,
                      label: "→ \(run.displayName)", tone: .start)
            ]
            if let doneAt = run.doneAt {
                out.append(.chip(id: "r-\(run.id)-done", at: doneAt,
                                 label: "\(run.ok ? "✓" : "✗") \(run.displayName)",
                                 tone: run.ok ? .ok : .fail))
            }
            return out
        }
        return (bubbles + chips).sorted { $0.timestamp < $1.timestamp }
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 8) {
                    if items.isEmpty {
                        Text("TRANSCRIPT WILL APPEAR HERE ONCE YOU START TALKING.")
                            .font(.system(size: 11, design: .monospaced))
                            .kerning(1.5)
                            .foregroundStyle(AppTheme.textDim)
                            .multilineTextAlignment(.center)
                            .padding(.top, 60)
                    }
                    ForEach(items) { item in
                        switch item {
                        case .bubble(let entry):
                            bubble(entry)
                        case .chip(_, _, let label, let tone):
                            chip(label, tone: tone)
                        }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(16)
                .frame(maxWidth: .infinity)
            }
            .preserveDrawerScroll("transcript")
            .onChange(of: items.count) { _, _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onAppear {
                if models.scrollOffsets["transcript"] == nil { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }

    /// The mission-log bubbles (App.css .bubble-*): Mortimer left with a
    /// cyan left rule, You right with a hairline right rule; meta line
    /// "You/Mortimer · time".
    private func bubble(_ entry: ConversationEntry) -> some View {
        let isUser = entry.role == "user"
        let time = Date(timeIntervalSince1970: entry.createdAt)
            .formatted(date: .omitted, time: .standard)
        return HStack {
            if isUser { Spacer(minLength: 80) }
            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                Text("\(isUser ? "You" : "Mortimer") · \(time)")
                    .font(.system(size: 10, design: .monospaced))
                    .kerning(1.4)
                    .textCase(.uppercase)
                    .foregroundStyle(isUser ? AppTheme.textDim : AppTheme.accent.opacity(0.75))
                Text(entry.text)
                    .font(.system(size: 14))
                    .foregroundStyle(isUser ? AppTheme.textDim : AppTheme.text)
                    .multilineTextAlignment(isUser ? .trailing : .leading)
            }
            .padding(isUser ? .trailing : .leading, 14)
            .overlay(
                Rectangle()
                    .fill(isUser ? AppTheme.hairline : AppTheme.accentDim)
                    .frame(width: 2),
                alignment: isUser ? .trailing : .leading
            )
            if !isUser { Spacer(minLength: 80) }
        }
        .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
    }

    /// E7 chips (command-deck.css .transcript-chip): small centred mono
    /// markers, cyan on success, red on failure.
    private func chip(_ label: String, tone: Tone) -> some View {
        Text(label)
            .font(.system(size: 10, design: .monospaced))
            .kerning(0.8)
            .foregroundStyle(tone == .ok ? AppTheme.accent
                             : tone == .fail ? AppTheme.red : AppTheme.textDim)
            .padding(.horizontal, 10)
            .padding(.vertical, 2)
            .background(Color(red: 30 / 255, green: 36 / 255, blue: 43 / 255).opacity(0.4))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(AppTheme.hairline, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
