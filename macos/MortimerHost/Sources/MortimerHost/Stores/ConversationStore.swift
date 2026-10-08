import Foundation
import Observation
import JarvisKit

struct CachedResultReference: Identifiable, Equatable {
    let id: UUID
    let resultID: UUID
    let runID: String?
    let time: Date
    let text: String
}

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
    /// Presentation-only references share this conversation owner. They
    /// contain no raw cached source, transcript injection or persistence.
    private(set) var cachedReferences: [CachedResultReference] = []

    /// The pre-CC7a conversation surface: a live caption of the last two
    /// entries. Used only when the conversation thread is switched off
    /// (ConversationThread.flagKey); the thread shows every entry in full.
    var latestCaptions: [ConversationEntry] { Array(entries.suffix(2)) }

    static func liveCaption(_ text: String, limit: Int = 160) -> String {
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        return normalized.count > limit ? "…" + String(normalized.suffix(limit - 1)) : normalized
    }

    func set(_ next: [ConversationEntry]) {
        entries = Array(next.suffix(AppTuning.maxConversationEntries))
        if entries.isEmpty { cachedReferences = [] }
        else if let oldest = entries.first?.createdAt {
            cachedReferences.removeAll { $0.time.timeIntervalSince1970 < oldest }
        }
    }

    func recordCachedResult(_ result: WorkspaceResult, fetchedAt: Double,
                            requestID: UUID, runID: String?, now: Date = Date()) {
        guard result.payload.dataPolicy == "approved_external", !result.payload.isProtectedLocal,
              fetchedAt.isFinite, fetchedAt <= now.timeIntervalSince1970,
              now.timeIntervalSince1970 - fetchedAt <= 900 else { return }
        let minutes = max(0, Int((now.timeIntervalSince1970 - fetchedAt) / 60))
        let age = minutes == 0 ? "just now" : "\(minutes)m ago"
        let clock = Date(timeIntervalSince1970: fetchedAt).formatted(date: .omitted, time: .shortened)
        recordReference(result, requestID: requestID, runID: runID, now: now,
            text: "Reopened \(referenceTitle(result)) · from \(clock) · cached \(age)")
    }

    /// D2: a real newer public source refresh references the same card. A
    /// display replay, malformed cache metadata or policy change is never
    /// described as an update. The clock comes from source-fetch provenance.
    func recordUpdatedResult(_ result: WorkspaceResult, previousFetchedAt: Double?,
                             now: Date = Date()) {
        guard result.payload.dataPolicy == "approved_external", !result.payload.isProtectedLocal,
              let source = result.payload.weatherSource,
              let fetchedAt = result.payload.ts, let expiry = result.payload.freshUntil,
              fetchedAt.isFinite, expiry.isFinite, now.timeIntervalSince1970.isFinite,
              fetchedAt <= now.timeIntervalSince1970, expiry > now.timeIntervalSince1970,
              expiry >= fetchedAt, expiry <= fetchedAt + 900 else { return }
        let units = source["weather"]?["units"]?.stringValue ?? ""
        let complete = source["weather"]?.objectValue != nil
            ? ["metric", "imperial"].contains(units)
                && WorkspaceStore.weatherSourceIsComplete(source, tool: "get_weather", days: 1, units: units)
            : WorkspaceStore.weatherSourceIsComplete(source, tool: "get_weather_radar", days: 1, units: "imperial")
        guard complete else { return }
        if let previousFetchedAt {
            guard previousFetchedAt.isFinite, fetchedAt > previousFetchedAt else { return }
        }
        let clock = Date(timeIntervalSince1970: fetchedAt).formatted(date: .omitted, time: .shortened)
        recordReference(result, requestID: UUID(), runID: result.payload.runID, now: now,
            text: "Updated \(referenceTitle(result)) · \(clock)", updating: true)
    }

    private func referenceTitle(_ result: WorkspaceResult) -> String {
        String((result.payload.title ?? "Weather").prefix(120))
    }

    private func recordReference(_ result: WorkspaceResult, requestID: UUID,
                                 runID: String?, now: Date, text: String, updating: Bool = false) {
        guard !cachedReferences.contains(where: { $0.id == requestID }) else { return }
        if let runID, let index = cachedReferences.firstIndex(where: { $0.runID == runID }) {
            // A paired cached/fetched run keeps one line at its original
            // position, updating that same result's final refresh outcome.
            let existing = cachedReferences[index]
            guard updating, existing.resultID == result.id else { return }
            cachedReferences[index] = CachedResultReference(id: existing.id, resultID: existing.resultID,
                runID: runID, time: existing.time, text: text)
            return
        }
        cachedReferences.append(CachedResultReference(id: requestID, resultID: result.id,
            runID: runID, time: now, text: text))
        cachedReferences = Array(cachedReferences.suffix(AppTuning.maxConversationEntries))
    }

    func clear() {
        entries = []
        cachedReferences = []
    }
}
