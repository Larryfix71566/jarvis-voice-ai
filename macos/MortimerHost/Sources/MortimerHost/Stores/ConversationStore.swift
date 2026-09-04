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

    func set(_ next: [ConversationEntry]) {
        entries = Array(next.suffix(AppTuning.maxConversationEntries))
    }

    func clear() {
        entries = []
    }
}
