import Foundation
import Observation
import CryptoKit

enum AtlasCardKind: String, Codable, CaseIterable, Sendable {
    case result
    case memory
    case architecture
    case plan
    case run
    case memoryGraph

    var label: String {
        switch self {
        case .result: return "Result"
        case .memory: return "Memory"
        case .architecture: return "Architecture"
        case .plan: return "Plan"
        case .run: return "Run"
        case .memoryGraph: return "Memory graph"
        }
    }
}

struct AtlasCard: Identifiable, Equatable, Sendable {
    let id: UUID
    let title: String
    let summary: String
    let source: String?
    var group: String?
    let kind: AtlasCardKind
    let metadata: [String: String]

    init(id: UUID, title: String, summary: String, source: String?, group: String? = nil,
         kind: AtlasCardKind = .result, metadata: [String: String] = [:]) {
        self.id = id
        self.title = title
        self.summary = summary
        self.source = source
        self.group = group
        self.kind = kind
        self.metadata = metadata
    }
}

struct AtlasGridPosition: Equatable, Hashable, Sendable {
    let row: Int
    let column: Int
}

@MainActor
@Observable
final class AtlasStore {
    nonisolated static let defaultColumns = 3
    nonisolated static let maxVoiceRow = 100
    nonisolated static let maxVoiceColumn = 100
    nonisolated static let maxGroups = 12
    nonisolated static let maxGroupNameLength = 80
    private(set) var cards: [AtlasCard] = []
    private(set) var selectedID: UUID?
    private(set) var query = ""
    private(set) var groups: [String: Set<UUID>] = [:]
    private(set) var zoomScale: Double = 1
    private(set) var panOffset: CGSize = .zero
    private(set) var positions: [UUID: AtlasGridPosition] = [:]

    var cardsByKind: [AtlasCardKind: [AtlasCard]] {
        Dictionary(grouping: cards, by: \.kind)
    }

    var contextCards: [AtlasCard] { cards.filter { $0.kind != .result } }

    var visibleCards: [AtlasCard] {
        guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return cards }
        let needle = query.lowercased()
        return cards.filter { $0.title.lowercased().contains(needle) || $0.summary.lowercased().contains(needle) }
    }

    func replace(_ cards: [AtlasCard]) {
        let oldPositions = positions
        self.cards = cards
        positions = [:]
        for card in cards {
            if let previous = oldPositions[card.id], !positions.values.contains(previous) {
                positions[card.id] = previous
            } else if let next = firstFreePosition() {
                positions[card.id] = next
            }
        }
        selectedID = selectedID.flatMap { id in cards.contains { $0.id == id } ? id : nil }
        groups = groups.mapValues { ids in ids.filter { id in cards.contains { card in card.id == id } } }
    }

    /// Replace only research results while retaining the current context
    /// projection. Context is refreshed independently from result arrival.
    func replaceResults(_ results: [AtlasCard]) {
        replace(results: results, context: contextCards)
    }

    /// Replace the read-only context projection while retaining result cards.
    func replaceContext(_ context: [AtlasCard]) {
        replace(results: cards.filter { $0.kind == .result }, context: context)
    }

    func replace(results: [AtlasCard], context: [AtlasCard]) {
        var seen = Set<UUID>()
        let merged = (results + context).filter { seen.insert($0.id).inserted }
        replace(merged)
    }

    /// Stable, process-independent identity for read-only context cards. This
    /// keeps positions, selection and groups intact across Atlas refreshes.
    nonisolated static func stableID(namespace: String, key: String) -> UUID {
        let bytes = Array(SHA256.hash(data: Data("\(namespace):\(key)".utf8)))
        return UUID(uuid: (bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5],
                           bytes[6], bytes[7], bytes[8], bytes[9], bytes[10], bytes[11],
                           bytes[12], bytes[13], bytes[14], bytes[15]))
    }
    func select(_ id: UUID?) { guard id == nil || cards.contains(where: { $0.id == id }) else { return }; selectedID = id }
    func setQuery(_ value: String) { query = String(value.prefix(200)) }
    func fit() { query = ""; zoomScale = 1; panOffset = .zero }
    @discardableResult
    func zoom(_ direction: String) -> Bool {
        switch direction {
        case "in": zoomScale = min(2, zoomScale * 1.25)
        case "out": zoomScale = max(0.25, zoomScale * 0.8)
        case "reset": zoomScale = 1
        default: return false
        }
        return true
    }
    @discardableResult
    func pan(_ direction: String, amount: Double = 80) -> Bool {
        guard amount.isFinite, amount > 0 else { return false }
        switch direction {
        case "up": panOffset.height += amount
        case "down": panOffset.height -= amount
        case "left": panOffset.width += amount
        case "right": panOffset.width -= amount
        default: return false
        }
        return true
    }
    func arrange() {
        positions = [:]
        for card in cards {
            positions[card.id] = firstFreePosition() ?? AtlasGridPosition(row: Self.maxVoiceRow, column: Self.maxVoiceColumn)
        }
        reorderCardsByPosition()
    }
    func assign(_ id: UUID, to group: String) {
        let group = String(group.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maxGroupNameLength))
        guard cards.contains(where: { $0.id == id }), !group.isEmpty,
              groups[group] != nil || groups.count < Self.maxGroups else { return }
        for existing in groups.keys { groups[existing]?.remove(id) }
        groups[group, default: []].insert(id)
        if let index = cards.firstIndex(where: { $0.id == id }) { cards[index].group = group }
    }

    @discardableResult
    func createGroup(_ name: String) -> Bool {
        let name = String(name.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maxGroupNameLength))
        guard !name.isEmpty, groups[name] == nil, groups.count < Self.maxGroups else { return false }
        groups[name] = []
        return true
    }

    @discardableResult
    func renameGroup(_ old: String, to new: String) -> Bool {
        let new = String(new.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maxGroupNameLength))
        guard !old.isEmpty, !new.isEmpty, old != new, groups[old] != nil, groups[new] == nil else { return false }
        let ids = groups.removeValue(forKey: old) ?? []
        groups[new] = ids
        for index in cards.indices where ids.contains(cards[index].id) { cards[index].group = new }
        return true
    }

    @discardableResult
    func remove(_ id: UUID, from group: String) -> Bool {
        guard var ids = groups[group], ids.remove(id) != nil else { return false }
        groups[group] = ids
        if let index = cards.firstIndex(where: { $0.id == id }), cards[index].group == group { cards[index].group = nil }
        return true
    }

    @discardableResult
    func dissolveGroup(_ group: String) -> Bool {
        guard let ids = groups.removeValue(forKey: group) else { return false }
        for index in cards.indices where ids.contains(cards[index].id) { cards[index].group = nil }
        return true
    }

    @discardableResult
    func move(_ id: UUID, relativeTo other: UUID, relation: String) -> Bool {
        guard id != other, cards.contains(where: { $0.id == id }),
              cards.contains(where: { $0.id == other }),
              let target = positions[other], ["before", "after", "left", "right"].contains(relation) else { return false }
        if relation == "before" || relation == "after" {
            var ordered = orderedCardsByPosition().filter { $0.id != id }
            guard let index = ordered.firstIndex(where: { $0.id == other }) else { return false }
            ordered.insert(cards.first(where: { $0.id == id })!, at: relation == "before" ? index : index + 1)
            assignDefaultPositions(to: ordered)
            return true
        }
        let occupied = Set(positions.filter { $0.key != id }.values)
        guard let destination: AtlasGridPosition = {
            switch relation {
            case "before": return firstFreeBefore(target, occupied: occupied)
            case "after": return firstFreeAfter(target, occupied: occupied)
            case "left": return firstFreeSide(target, columnDelta: -1, occupied: occupied)
            case "right": return firstFreeSide(target, columnDelta: 1, occupied: occupied)
            default: return nil
            }
        }() else { return false }
        positions[id] = destination
        reorderCardsByPosition()
        return true
    }

    @discardableResult
    func move(_ id: UUID, row: Int, column: Int) -> Bool {
        guard cards.contains(where: { $0.id == id }),
              (1...Self.maxVoiceRow).contains(row),
              (1...Self.maxVoiceColumn).contains(column) else { return false }
        let destination = AtlasGridPosition(row: row, column: column)
        guard !positions.contains(where: { $0.key != id && $0.value == destination }) else { return false }
        positions[id] = destination
        reorderCardsByPosition()
        return true
    }

    func position(of id: UUID) -> AtlasGridPosition? { positions[id] }

    private func firstFreePosition(maxColumn: Int = 3) -> AtlasGridPosition? {
        for row in 1...Self.maxVoiceRow {
            for column in 1...min(maxColumn, Self.maxVoiceColumn) {
                let candidate = AtlasGridPosition(row: row, column: column)
                if !positions.values.contains(candidate) { return candidate }
            }
        }
        return nil
    }

    private func firstFreeBefore(_ target: AtlasGridPosition, occupied: Set<AtlasGridPosition>) -> AtlasGridPosition? {
        var row = target.row, column = target.column
        for _ in 0..<Self.maxVoiceRow * Self.maxVoiceColumn {
            if column == 1 { row -= 1; column = Self.maxVoiceColumn } else { column -= 1 }
            guard row >= 1 else { return nil }
            let candidate = AtlasGridPosition(row: row, column: column)
            if !occupied.contains(candidate) { return candidate }
        }
        return nil
    }

    private func firstFreeAfter(_ target: AtlasGridPosition, occupied: Set<AtlasGridPosition>) -> AtlasGridPosition? {
        var row = target.row, column = target.column
        for _ in 0..<Self.maxVoiceRow * Self.maxVoiceColumn {
            if column == Self.maxVoiceColumn { row += 1; column = 1 } else { column += 1 }
            guard row <= Self.maxVoiceRow else { return nil }
            let candidate = AtlasGridPosition(row: row, column: column)
            if !occupied.contains(candidate) { return candidate }
        }
        return nil
    }

    private func firstFreeSide(_ target: AtlasGridPosition, columnDelta: Int,
                               occupied: Set<AtlasGridPosition>) -> AtlasGridPosition? {
        var row = target.row, column = target.column + columnDelta
        if column < 1 { column = 1; row += 1 }
        if column > Self.maxVoiceColumn { column = Self.maxVoiceColumn; row += 1 }
        while row <= Self.maxVoiceRow {
            let candidate = AtlasGridPosition(row: row, column: column)
            if !occupied.contains(candidate) { return candidate }
            row += 1
        }
        return nil
    }

    private func reorderCardsByPosition() {
        cards = orderedCardsByPosition()
    }

    private func orderedCardsByPosition() -> [AtlasCard] {
        cards.sorted {
            let left = positions[$0.id] ?? AtlasGridPosition(row: Self.maxVoiceRow, column: Self.maxVoiceColumn)
            let right = positions[$1.id] ?? AtlasGridPosition(row: Self.maxVoiceRow, column: Self.maxVoiceColumn)
            return (left.row, left.column, $0.id.uuidString) < (right.row, right.column, $1.id.uuidString)
        }
    }

    private func assignDefaultPositions(to ordered: [AtlasCard]) {
        positions = [:]
        cards = ordered
        for card in ordered {
            positions[card.id] = firstFreePosition() ?? AtlasGridPosition(row: Self.maxVoiceRow, column: Self.maxVoiceColumn)
        }
    }
}
