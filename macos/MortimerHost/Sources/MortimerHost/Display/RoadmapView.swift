import Foundation
import SwiftUI
import JarvisKit

/// One deterministic projection for pointer, voice, rendering and export.
/// Source cards are immutable; no model classifies or edits their status.
struct RoadmapFilter: Equatable, Sendable {
    var owners: [String] = []
    var authors: [String] = []
    var states: [String] = []
    var topics: [String] = []
    var workstreams: [String] = []
    var checklist = "all"
    var blockers = false
    var period = "all"
    var evaluatedAt = Date()

    static let fields: Set<String> = ["operation", "owners", "authors", "states", "topics", "workstreams", "checklist", "blockers", "period"]
    static let arrayFields: Set<String> = ["owners", "authors", "states", "topics", "workstreams"]
    static let lifecycle: Set<String> = ["open", "completed", "proposed", "claimed", "in-progress", "review", "landed", "accepted", "blocked", "parked", "unclassified"]

    static func validArguments(_ args: [String: JSONValue]) -> Bool {
        guard Set(args.keys).isSubset(of: fields), let operation = args["operation"]?.stringValue,
              ["replace", "refine", "clear", "focus", "refresh"].contains(operation) else { return false }
        for key in arrayFields where args[key] != nil {
            guard case .array(let values) = args[key], values.count <= 4,
                  values.allSatisfy({ if case .string(let text) = $0 { return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && text.unicodeScalars.count <= 120 }; return false }) else { return false }
        }
        for key in ["owners", "authors"] {
            if let values = strings(args[key]), !values.allSatisfy({ ["codex", "claude", "larry", "unassigned"].contains($0) }) { return false }
        }
        if let values = strings(args["states"]), !values.allSatisfy({ lifecycle.contains($0) }) { return false }
        if let values = strings(args["workstreams"]), !values.allSatisfy({ $0.range(of: "^WS-[0-9]+$", options: .regularExpression) != nil }) { return false }
        if let value = args["checklist"], ![JSONValue.string("all"), .string("remaining"), .string("larry")].contains(value) { return false }
        if let value = args["period"], ![JSONValue.string("all"), .string("this_week"), .string("last_seven_days")].contains(value) { return false }
        if let value = args["blockers"], case .bool = value {} else if args["blockers"] != nil { return false }
        if ["clear", "refresh"].contains(operation) { return args.count == 1 }
        if operation == "focus" { return Set(args.keys) == ["operation", "workstreams"] && strings(args["workstreams"])?.count == 1 }
        return true
    }
    static func strings(_ value: JSONValue?) -> [String]? {
        guard case .array(let values) = value else { return nil }
        return values.compactMap(\.stringValue)
    }
    func applying(_ args: [String: JSONValue], to snapshot: RoadmapSnapshot, timezone: String?, now: Date = Date()) -> RoadmapFilter? {
        guard Self.validArguments(args) else { return nil }
        let operation = args["operation"]?.stringValue
        var next = operation == "refine" ? self : RoadmapFilter()
        if operation == "refresh" { next = self }
        if let ids = Self.strings(args["workstreams"]), !ids.allSatisfy({ id in snapshot.cards.contains { $0.id == id } }) { return nil }
        if let value = Self.strings(args["owners"]) { next.owners = value }
        if let value = Self.strings(args["authors"]) { next.authors = value }
        if let value = Self.strings(args["states"]) { next.states = value }
        if let value = Self.strings(args["topics"]) { next.topics = value }
        if let value = Self.strings(args["workstreams"]) { next.workstreams = value }
        if let value = args["checklist"]?.stringValue { next.checklist = value }
        if case .bool(let value) = args["blockers"] { next.blockers = value }
        if let value = args["period"]?.stringValue { next.period = value }
        guard next.period == "all" || timezone.flatMap(TimeZone.init(identifier:)) != nil else { return nil }
        next.evaluatedAt = now
        return next
    }
    var chips: [(String, String)] {
        var values: [(String, String)] = []
        for (key, items) in [("owners", owners), ("authors", authors), ("states", states), ("topics", topics), ("workstreams", workstreams)] where !items.isEmpty {
            values.append((key, "\(key): \(items.joined(separator: " or "))"))
        }
        if checklist != "all" { values.append(("checklist", "checklist: \(checklist)")) }
        if blockers { values.append(("blockers", "explicit blockers")) }
        if period != "all" { values.append(("period", period.replacingOccurrences(of: "_", with: " "))) }
        return values
    }
    static func containsWord(_ source: String, _ word: String) -> Bool {
        source.range(of: "\\b" + NSRegularExpression.escapedPattern(for: word) + "\\b", options: [.regularExpression, .caseInsensitive]) != nil
    }
    static func blockerEvidence(_ card: RoadmapSnapshot.Card) -> [String] {
        let current = [card.status, card.fields["Next step"] ?? ""] + card.checklist.filter { !$0.checked }.map(\.text)
        return current.flatMap { $0.components(separatedBy: ". ") }.filter { text in
            let keywords = ["blocked", "blocker", "blocking", "awaiting"]
            return keywords.contains { containsWord(text, $0) }
                && !["historical", "previous", "earlier", "resolved", "fixed", "cleared", "closed", "removed", "was", "were"].contains { containsWord(text, $0) }
                && text.range(of: "\\b(no|not)\\s+(?:(?:longer|remaining|known|current|open|active|unresolved)\\s+)*(blocked|blockers?|blocking)\\b", options: [.regularExpression, .caseInsensitive]) == nil
        }
    }
    static func ambiguousBlocker(_ card: RoadmapSnapshot.Card) -> Bool {
        let text = ([card.status, card.fields["Next step"] ?? ""] + card.checklist.filter { !$0.checked }.map(\.text)).joined(separator: " ")
        return blockerEvidence(card).isEmpty && ["blocked", "blocker", "blocking", "awaiting"].contains { containsWord(text, $0) }
    }
    static func readiness(_ text: String) -> String {
        if text.range(of: "\\b(not|never)\\s+(yet\\s+)?ready\\b", options: [.regularExpression, .caseInsensitive]) != nil { return "Prerequisites remain — see source" }
        if text.range(of: "\\b(after|until|awaiting|requires|prerequisite|blocked|depends)\\b", options: [.regularExpression, .caseInsensitive]) != nil { return "Prerequisites remain — see source" }
        if text.range(of: "\\bready (for Larry|now)\\b", options: [.regularExpression, .caseInsensitive]) != nil { return "Ready for Larry — explicitly stated" }
        return "Readiness not specified — check prerequisites"
    }
    func visibleChecklist(_ card: RoadmapSnapshot.Card) -> [RoadmapSnapshot.ChecklistItem] {
        card.checklist.filter { item in
            if checklist == "all" { return true }
            guard !item.checked else { return false }
            if checklist == "remaining" { return true }
            return Self.containsWord(item.text, "Larry") &&
                (item.section.localizedCaseInsensitiveContains("acceptance") ||
                 item.section.localizedCaseInsensitiveContains("decision"))
        }
    }
    func project(_ snapshot: RoadmapSnapshot, timezone: String?) -> RoadmapProjection {
        var logs = snapshot.logs
        var dateLabel: String?
        if period != "all", let zone = timezone.flatMap(TimeZone.init(identifier:)) {
            var calendar = Calendar(identifier: .gregorian); calendar.timeZone = zone; calendar.firstWeekday = 2
            let end = evaluatedAt
            let start = period == "this_week" ? calendar.dateInterval(of: .weekOfYear, for: end)!.start : end.addingTimeInterval(-7 * 86400)
            let formatter = DateFormatter(); formatter.calendar = calendar; formatter.timeZone = zone
            formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyy-MM-dd"
            let first = formatter.string(from: start), last = formatter.string(from: end)
            dateLabel = "\(first) – \(last), \(zone.identifier); logs record dates only, so boundary days are included"
            logs = logs.filter { $0.date >= first && $0.date <= last }
        }
        if period != "all", timezone.flatMap(TimeZone.init(identifier:)) == nil {
            logs = []
            dateLabel = "Configured timezone unavailable; no relative-date matches. Clear the date filter or refresh with a valid timezone."
        }
        let changed = Set(logs.flatMap(\.rows))
        let cards = snapshot.cards.filter { card in
            (owners.isEmpty || owners.contains { Self.containsWord(card.owner, $0) })
            && (authors.isEmpty || authors.contains { Self.containsWord(card.fields["Implemented by"] ?? "", $0) })
            && (states.isEmpty || states.contains { $0 == "open" ? card.lifecycle != "accepted" : (($0 == "completed" ? "accepted" : $0) == card.lifecycle) })
            && (topics.isEmpty || topics.contains { term in ([card.title] + ["Status", "Scope", "Next step", "Workstream"].compactMap { card.fields[$0] }).joined(separator: " ").localizedCaseInsensitiveContains(term) })
            && (workstreams.isEmpty || workstreams.contains(card.id))
            && (!blockers || !Self.blockerEvidence(card).isEmpty)
            && (checklist != "larry" || !visibleChecklist(card).isEmpty)
            && (period == "all" || changed.contains(card.id))
        }
        let ids = Set(cards.map(\.id))
        return RoadmapProjection(cards: cards, logs: period == "all" ? [] : logs.filter { !ids.isDisjoint(with: $0.rows) },
            dateLabel: dateLabel, total: snapshot.cards.count,
            unclassified: snapshot.cards.filter { $0.lifecycle == "unclassified" }.map(\.id),
            ambiguousBlockers: blockers ? snapshot.cards.filter(Self.ambiguousBlocker).map(\.id) : [])
    }
    func export(_ snapshot: RoadmapSnapshot, timezone: String?) -> String {
        let view = project(snapshot, timezone: timezone)
        var parts = ["Mortimer roadmap — \(view.cards.count)/\(view.total) workstreams", "Filters: " + (chips.isEmpty ? "All work" : chips.map(\.1).joined(separator: "; ")),
                     "Source: \(snapshot.provenance.path), local checkout \(snapshot.provenance.revision ?? "unknown"); SHA-256 \(snapshot.provenance.sha256); read \(snapshot.provenance.readAt); dirty: \(snapshot.provenance.dirty.map(String.init) ?? "unknown"). Not a GitHub-main or installed-build claim."]
        if let dates = view.dateLabel { parts.append(dates) }
        if !view.ambiguousBlockers.isEmpty { parts.append("Other blocker mentions excluded as resolved, historical or unclassified: " + view.ambiguousBlockers.joined(separator: ", ")) }
        for card in view.cards {
            // Filtered checklist export never falls back to raw details, which
            // would silently reintroduce excluded checkboxes or other cards.
            parts.append("\(card.id) — \(card.title)\nStatus: \(card.status)\nOwner: \(card.owner)\nNext step: \(card.fields["Next step"] ?? "Unspecified")")
            parts.append(contentsOf: Self.blockerEvidence(card).map { "Blocker evidence: \($0)" })
            parts.append(contentsOf: visibleChecklist(card).map { "[\($0.checked ? "x" : " ")] \($0.text)" })
            if checklist == "all" { parts.append(card.details) }
        }
        parts.append(contentsOf: view.logs.map { "Dated evidence: \($0.date) — \($0.title) (\($0.path); SHA-256 \($0.sha256))" })
        return parts.joined(separator: "\n\n")
    }
}

struct RoadmapProjection {
    let cards: [RoadmapSnapshot.Card]
    let logs: [RoadmapSnapshot.Log]
    let dateLabel: String?
    let total: Int
    let unclassified: [String]
    let ambiguousBlockers: [String]
}

struct RoadmapView: View {
    let result: WorkspaceResult
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace
    @State private var topic = ""
    @State private var filterError: String?
    private var snapshot: RoadmapSnapshot { result.payload.roadmap! }
    private var filter: RoadmapFilter { result.roadmapFilter }
    private var projection: RoadmapProjection { filter.project(snapshot, timezone: result.payload.roadmapTimezone) }
    private func apply(_ args: [String: JSONValue]) {
        let applied: Bool
        if let coordinator {
            let outcome = coordinator.executePointer(.roadmapControl, target: result.id.uuidString, args: args)
            applied = outcome == .applied || outcome == .pendingUser
        } else { applied = workspace.applyRoadmapFilter(result.id, args: args) }
        filterError = applied ? nil : "That filter or refresh is unavailable. The current view is unchanged."
    }
    private func toggleFacet(_ key: String, _ value: String, values: [String]) {
        let next = values.contains(value) ? values.filter { $0 != value } : values + [value]
        apply(["operation": .string("refine"), key: .array(next.map(JSONValue.string))])
    }
    var body: some View {
        ScrollViewReader { scroll in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("Roadmap · \(projection.cards.count)/\(projection.total) workstreams").font(.headline).accessibilityLabel("Roadmap · \(projection.cards.count)/\(projection.total) workstreams")
                        Spacer()
                        Button("Refresh") { apply(["operation": .string("refresh")]) }.disabled(coordinator == nil)
                        Button("Clear filters") { apply(["operation": .string("clear")]) }
                    }
                    Text("Local checkout: \(snapshot.provenance.revision.map { String($0.prefix(12)) } ?? "unknown") · \(snapshot.provenance.dirty == true ? "modified" : (snapshot.provenance.dirty == false ? "clean" : "dirty state unknown"))\nRead \(snapshot.provenance.readAt) · Not verified against GitHub main or installed app").font(.caption).textSelection(.enabled)
                    DisclosureGroup("Source fingerprint") {
                        Text("\(snapshot.provenance.path)\nSHA-256: \(snapshot.provenance.sha256)\nRepository identity: \(snapshot.provenance.repositoryID)").font(.caption).textSelection(.enabled)
                    }
                    if let filterError { Text(filterError).font(.callout) }
                    if let status = workspace.roadmapRefreshStatus[result.id] { Text(status).font(.callout).accessibilityLabel(status) }
                    HStack {
                        Menu("Filter") {
                            Button("Open work") { apply(["operation": .string("replace"), "states": .array([.string("open")])]) }
                            Button("Accepted work") { apply(["operation": .string("replace"), "states": .array([.string("accepted")])]) }
                            Button("Explicit blockers") { apply(["operation": .string("replace"), "blockers": .bool(true)]) }
                            Button("Larry's remaining acceptance") { apply(["operation": .string("replace"), "checklist": .string("larry")]) }
                            Menu("Current owners (OR)") {
                                ForEach(["codex", "claude", "larry", "unassigned"], id: \.self) { owner in
                                    Button("\(filter.owners.contains(owner) ? "✓ " : "")\(owner)") { toggleFacet("owners", owner, values: filter.owners) }
                                }
                            }
                            Menu("Historical implemented by (OR)") {
                                ForEach(["codex", "claude", "larry", "unassigned"], id: \.self) { author in
                                    Button("\(filter.authors.contains(author) ? "✓ " : "")\(author)") { toggleFacet("authors", author, values: filter.authors) }
                                }
                            }
                            Menu("Lifecycle (OR, up to four)") {
                                ForEach(RoadmapFilter.lifecycle.sorted(), id: \.self) { state in
                                    Button("\(filter.states.contains(state) ? "✓ " : "")\(state)") { toggleFacet("states", state, values: filter.states) }
                                }
                            }
                            Menu("Workstreams (OR, up to four)") {
                                ForEach(snapshot.cards) { card in
                                    Button("\(filter.workstreams.contains(card.id) ? "✓ " : "")\(card.id)") { toggleFacet("workstreams", card.id, values: filter.workstreams) }
                                }
                            }
                            Menu("Checklist") {
                                ForEach(["all", "remaining", "larry"], id: \.self) { mode in
                                    Button(mode) { apply(["operation": .string("refine"), "checklist": .string(mode)]) }
                                }
                            }
                            Button("This week") { apply(["operation": .string("refine"), "period": .string("this_week")]) }
                            Button("Last seven days") { apply(["operation": .string("refine"), "period": .string("last_seven_days")]) }
                        }
                        TextField("Topics (separate with ; for OR)", text: $topic).onSubmit {
                            let terms = topic.split(separator: ";").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
                            apply(["operation": .string("refine"), "topics": .array(terms.map(JSONValue.string))])
                        }
                        Menu("Focus workstream") {
                            ForEach(snapshot.cards) { card in Button(card.id) { apply(["operation": .string("focus"), "workstreams": .array([.string(card.id)])]) } }
                        }
                    }
                    ForEach(filter.chips, id: \.0) { key, label in
                        Button("\(label) ×") {
                            let empty: JSONValue = RoadmapFilter.arrayFields.contains(key) ? .array([]) : (key == "blockers" ? .bool(false) : .string("all"))
                            apply(["operation": .string("refine"), key: empty])
                        }.accessibilityLabel("Remove filter: \(label)")
                    }
                    if let dates = projection.dateLabel { Text(dates).font(.caption) }
                    ForEach(snapshot.issues, id: \.self) { Text($0).font(.caption) }
                    if !projection.unclassified.isEmpty { Text("Unclassified lifecycle: \(projection.unclassified.joined(separator: ", ")). Original status retained.").font(.caption) }
                    if !projection.ambiguousBlockers.isEmpty { Text("Other blocker mentions excluded as resolved, historical or unclassified: \(projection.ambiguousBlockers.joined(separator: ", "))").font(.caption) }
                    if projection.cards.isEmpty { Text("No workstreams match these filters. Clear filters to see all work.") }
                    ForEach(projection.cards) { card in
                        DisclosureGroup(isExpanded: Binding(get: { workspace.roadmapExpanded[result.id, default: []].contains(card.id) }, set: { workspace.setRoadmapExpanded(result.id, card: card.id, expanded: $0) })) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Status: \(card.status)\nOwner: \(card.owner)").textSelection(.enabled)
                                Text("Next: \(card.fields["Next step"] ?? "Not specified")").textSelection(.enabled)
                                ForEach(Array(RoadmapFilter.blockerEvidence(card).enumerated()), id: \.offset) { _, text in Text("Blocker evidence: \(text)") }
                                Text("\(filter.visibleChecklist(card).count)/\(card.checklist.count) checklist items").font(.caption)
                                ForEach(Array(filter.visibleChecklist(card).enumerated()), id: \.offset) { _, item in
                                    Text("\(item.checked ? "☑" : "☐") \(item.text)" + (filter.checklist == "larry" ? "\n\(RoadmapFilter.readiness(item.text))" : "")).textSelection(.enabled)
                                }
                                if filter.checklist == "all" { Text(verbatim: card.details).font(.caption).textSelection(.enabled) }
                            }
                        } label: { Text(card.title).font(.headline) }
                        .padding(12).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12)).id(card.id)
                    }
                    ForEach(Array(projection.logs.enumerated()), id: \.offset) { _, entry in Text("\(entry.date) · \(entry.title)\n\(entry.path)").font(.caption).textSelection(.enabled) }
                }.padding(12)
            }.onChange(of: filter.workstreams) { _, ids in if let first = ids.first { scroll.scrollTo(first, anchor: .top) } }
        }
    }
}
