import Foundation
import JarvisKit

/// WS-17 / Command Console plan §7.2, increment CC7a.3: the Recents list
/// behind Results ▾. Approved design (Larry, 2026-09-30): PINNED, then
/// RECENT (about 10), numbered to match voice ("open number 3"), with an
/// unread dot and a "fresh" age.
///
/// The bound is a display limit only: results past it stay in
/// `WorkspaceStore` (its own retention is unchanged) and in Output, and are
/// listed under "Older". Voice resolves a spoken number or subject against
/// these entries to a result UUID, which stays the action protocol's
/// canonical target (Codex boundary 3, CX-15).
enum WorkspaceRecents {
    /// "About the last 10 unpinned."
    static let recentLimit = 10

    enum Section: String, Equatable { case pinned, recent, older }

    struct Entry: Identifiable, Equatable {
        let id: UUID
        /// The number shown in the menu and used by voice. Protected
        /// (local-only) results get none: voice never sees them, so they
        /// must not take a number Mortimer could be asked about.
        let number: Int?
        let section: Section
        let card: ConversationThread.Card
        /// Source age is independent of arrival time, which keeps the card
        /// and its Recents number in their original positions after refresh.
        let freshnessDate: Date
        let isUnread: Bool
        let isActive: Bool
        var receivedAt: Date { card.time }
        var isPrivate: Bool { card.isPrivate }
        /// "3  Weather · Folly Beach"; a private entry shows no number.
        var label: String { number.map { "\($0)  \(card.title)" } ?? card.title }
    }

    struct Listing: Equatable {
        let entries: [Entry]
        /// Unpinned results beyond the Recents bound, newest first.
        let olderEntries: [Entry]
        var older: [ConversationThread.Card] { olderEntries.map(\.card) }
        var pinned: [Entry] { entries.filter { $0.section == .pinned } }
        var recent: [Entry] { entries.filter { $0.section == .recent } }
        /// Pointer actions remain available for every retained result,
        /// including an open or compared Older item. Only `entries` supply
        /// voice numbers; Older controls must never expand that inventory.
        var actionableEntries: [Entry] { entries + olderEntries }
    }

    /// Pinned first, then the newest unpinned results, each newest first.
    /// Numbers run 1, 2, 3… down the list, skipping private entries.
    static func listing(results: [WorkspaceResult], pinned: Set<UUID>,
                        unread: Set<UUID>, active: UUID?,
                        limit: Int = recentLimit) -> Listing {
        let newestFirst = results.enumerated()
            .sorted { ($0.element.receivedAt, $0.offset) > ($1.element.receivedAt, $1.offset) }
            .map(\.element)
        let pinnedResults = newestFirst.filter { pinned.contains($0.id) }
        let unpinned = newestFirst.filter { !pinned.contains($0.id) }
        let shown = unpinned.prefix(max(0, limit))
        var next = 1
        var entries: [Entry] = []
        for (section, list) in [(Section.pinned, Array(pinnedResults)), (.recent, Array(shown))] {
            for result in list {
                let card = ConversationThread.card(result)
                var number: Int?
                if !card.isPrivate { number = next; next += 1 }
                entries.append(Entry(id: result.id, number: number, section: section, card: card,
                                     freshnessDate: freshnessDate(for: result),
                                     isUnread: unread.contains(result.id),
                                     isActive: active == result.id))
            }
        }
        let olderEntries = unpinned.dropFirst(shown.count).map { result in
            Entry(id: result.id, number: nil, section: .older,
                  card: ConversationThread.card(result),
                  freshnessDate: freshnessDate(for: result),
                  isUnread: unread.contains(result.id), isActive: active == result.id)
        }
        return Listing(entries: entries, olderEntries: olderEntries)
    }

    private static func freshnessDate(for result: WorkspaceResult) -> Date {
        guard let ts = result.payload.ts, ts.isFinite else { return result.receivedAt }
        return Date(timeIntervalSince1970: ts)
    }

    /// The "fresh" age: "now", "4m", "2h", "3d".
    static func age(of date: Date, now: Date = Date()) -> String {
        let elapsed = now.timeIntervalSince(date)
        guard elapsed.isFinite else { return "unknown" }
        let seconds = max(0, elapsed)
        if seconds < 60 { return "now" }
        let unit: (seconds: Double, suffix: String)
        if seconds < 3_600 { unit = (60, "m") }
        else if seconds < 86_400 { unit = (3_600, "h") }
        else { unit = (86_400, "d") }
        guard let count = Int(exactly: (seconds / unit.seconds).rounded(.down)) else { return "unknown" }
        return "\(count)\(unit.suffix)"
    }

    enum Resolution: Equatable {
        case result(UUID)
        /// More than one entry matches; Mortimer asks which.
        case ambiguous([Entry])
        case none
    }

    /// Resolve a spoken reference against the Recents entries: a number
    /// ("3", "#3", "number 3") or a subject ("Folly Beach", "the Folly
    /// Beach weather"). Private entries never match. A subject matches when
    /// every word of it appears in the entry's kind, subject or title; an
    /// exact subject wins over a partial one. More than one match is
    /// ambiguous and is never acted on.
    static func resolve(_ reference: String, in entries: [Entry],
                        titles: [UUID: String] = [:]) -> Resolution {
        let candidates = entries.filter { !$0.isPrivate }
        let spoken = normalized(reference)
        if let number = spokenNumber(spoken) {
            guard let entry = candidates.first(where: { $0.number == number }) else { return .none }
            return .result(entry.id)
        }
        let words = significantWords(spoken)
        guard !words.isEmpty else { return .none }
        let matches = candidates.filter { entry in
            let haystack = Set(significantWords(normalized(
                [entry.card.kind, entry.card.subject, titles[entry.id] ?? ""].joined(separator: " "))))
            return words.allSatisfy(haystack.contains)
        }
        // Exact: the spoken words, less the entry's kind ("weather",
        // "research"), are its subject.
        let exact = matches.filter { entry in
            let kind = Set(significantWords(normalized(entry.card.kind)))
            return words.filter { !kind.contains($0) } == significantWords(normalized(entry.card.subject))
        }
        if exact.count == 1 { return .result(exact[0].id) }
        switch matches.count {
        case 0: return .none
        case 1: return .result(matches[0].id)
        default: return .ambiguous(matches)
        }
    }

    /// The choices offered back when a reference is ambiguous: the result
    /// UUID (the canonical target) and what Larry sees in the menu.
    static func choices(_ entries: [Entry], now: Date = Date()) -> [ConsoleChoice] {
        entries.prefix(10).map { entry in
            ConsoleChoice(id: entry.id.uuidString,
                          label: "\(entry.label) · \(age(of: entry.freshnessDate, now: now))")
        }
    }

    // MARK: Matching helpers

    private static let fillerWords: Set<String> = [
        "the", "a", "an", "of", "for", "in", "at", "on", "to", "my", "that", "this",
        "result", "results", "card", "one", "show", "open", "again", "number", "no",
    ]

    private static func normalized(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .replacingOccurrences(of: "[^a-z0-9#]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
    }

    private static func significantWords(_ text: String) -> [String] {
        text.split(separator: " ").map(String.init).filter { !fillerWords.contains($0) }
    }

    private static let numberWords: [String: Int] = [
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "first": 1,
        "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    ]

    /// "3", "#3", "number 3", "no 3", "number three". Anything with other
    /// words is a subject, not a number.
    private static func spokenNumber(_ text: String) -> Int? {
        var words = text.split(separator: " ").map(String.init)
        if words.first == "number" || words.first == "no" { words.removeFirst() }
        guard words.count == 1 else { return nil }
        let word = words[0].hasPrefix("#") ? String(words[0].dropFirst()) : words[0]
        if let value = Int(word), value > 0 { return value }
        return numberWords[word]
    }
}
