import Foundation
import Observation
import JarvisKit

/// APP plan §3 P8/P16 — the native conversationFeed.ts. Mirrors
/// JarvisClient.transcript (bounded at maxConversationEntries, oldest
/// dropped). LIVE since 2026-08-30: JarvisClient aggregates the bot's
/// own RTVI user-transcription / bot-llm-text frames (the live session
/// disproved CORE correction 6), so the Log tab's bubbles and the
/// stage's captions light up with no backend change.
@MainActor
@Observable
final class ConversationStore {
    private(set) var entries: [ConversationEntry] = []

    /// The conversation surface is a live caption, not a second response
    /// reader. The full transcript remains available in the Log tab.
    var latestCaptions: [ConversationEntry] { Array(entries.suffix(2)) }

    static func liveCaption(_ text: String, limit: Int = 160) -> String {
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        return normalized.count > limit ? "…" + String(normalized.suffix(limit - 1)) : normalized
    }

    func set(_ next: [ConversationEntry]) {
        entries = Array(next.suffix(AppTuning.maxConversationEntries))
    }

    func clear() {
        entries = []
    }
}
