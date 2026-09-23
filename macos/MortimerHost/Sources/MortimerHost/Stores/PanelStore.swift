import Foundation
import Observation
import JarvisKit

/// Stable identity for one detachable content window. The UUID is the
/// address used by WindowGroup and ScreenPlacement; titles and screen labels
/// are deliberately not identities.
struct ContentPanelID: Codable, Hashable, Sendable, Identifiable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) { self.rawValue = rawValue }
    var id: UUID { rawValue }
}

/// Closed content catalogue for detachable panels. These views reuse the
/// app-owned stores; they never create a second fetch, graph renderer, or
/// transcript owner.
enum PanelContent: Codable, Hashable, Sendable {
    case result(UUID)
    case sources(UUID)
    case comparison(UUID, UUID)
    case memoryGraph(String)
    case atlas
    case transcript

    var key: String {
        switch self {
        case .result(let id): return "result:\(id.uuidString)"
        case .sources(let id): return "sources:\(id.uuidString)"
        case .comparison(let a, let b): return "comparison:\(a.uuidString):\(b.uuidString)"
        case .memoryGraph(let key): return "memory:\(key)"
        case .atlas: return "atlas"
        case .transcript: return "transcript"
        }
    }

    static func parseTarget(_ target: String) -> PanelContent? {
        let value: String
        if target.hasPrefix("content:") {
            value = String(target.dropFirst("content:".count))
        } else {
            value = target
        }
        switch value {
        case "atlas": return target.hasPrefix("content:") ? .atlas : nil
        case "transcript": return target.hasPrefix("content:") ? .transcript : nil
        default: break
        }
        if value.hasPrefix("memory:") {
            let key = String(value.dropFirst("memory:".count))
            return key.isEmpty ? nil : .memoryGraph(key)
        }
        if value.hasPrefix("result:") {
            return UUID(uuidString: String(value.dropFirst("result:".count))).map(PanelContent.result)
        }
        if value.hasPrefix("sources:") {
            return UUID(uuidString: String(value.dropFirst("sources:".count))).map(PanelContent.sources)
        }
        if value.hasPrefix("comparison:") {
            let parts = value.dropFirst("comparison:".count).split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count == 2, let first = UUID(uuidString: String(parts[0])),
                  let second = UUID(uuidString: String(parts[1])) else { return nil }
            return .comparison(first, second)
        }
        return nil
    }
}

struct ContentPanelRecovery: Codable, Hashable, Sendable {
    let screenID: String
    let frame: CGRect
    let manualRevision: Int
}

struct ContentPanelRecord: Codable, Hashable, Sendable, Identifiable {
    let id: ContentPanelID
    let content: PanelContent
    let origin: String
    var screenID: String?
    var frame: CGRect?
    var manualRevision: Int
    var recovery: ContentPanelRecovery?
    var focused: Bool
    var fullscreen: Bool

    init(id: ContentPanelID = ContentPanelID(), content: PanelContent,
         origin: String, screenID: String? = nil) {
        self.id = id; self.content = content; self.origin = origin
        self.screenID = screenID; self.frame = nil; self.manualRevision = 0
        self.recovery = nil; self.focused = true; self.fullscreen = false
    }
}

enum ContentPanelOpenResult: Equatable, Sendable {
    case opened(ContentPanelID)
    case focused(ContentPanelID)
    case rejectedLimit(maximum: Int)
}

enum ConsolePanel: String, CaseIterable, Identifiable, Codable, Hashable, Sendable {
    case atlas, results, memory, output
    var id: String { rawValue }
}

@MainActor
@Observable
final class PanelStore {
    static let maxContentPanels = 6

    private(set) var detached: Set<ConsolePanel> = []
    private(set) var focused: ConsolePanel = .results
    private(set) var screenByPanel: [ConsolePanel: String] = [:]
    private(set) var fullscreen: Set<ConsolePanel> = []
    private(set) var contentRecords: [ContentPanelID: ContentPanelRecord] = [:]
    private(set) var focusedContentID: ContentPanelID?

    func detach(_ panel: ConsolePanel) { detached.insert(panel) }
    func returnPanel(_ panel: ConsolePanel) { detached.remove(panel); screenByPanel.removeValue(forKey: panel); fullscreen.remove(panel) }
    func returnAll() { detached.removeAll(); screenByPanel.removeAll(); fullscreen.removeAll() }
    func focus(_ panel: ConsolePanel) { focused = panel }
    @discardableResult
    func move(_ panel: ConsolePanel, to screenID: String) -> Bool {
        guard !screenID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        detached.insert(panel)
        screenByPanel[panel] = String(screenID.prefix(120))
        return true
    }
    func setFullscreen(_ panel: ConsolePanel, enabled: Bool) {
        if enabled { fullscreen.insert(panel) } else { fullscreen.remove(panel) }
    }

    /// Open one exact content identity, or focus the existing panel. The
    /// sixth-panel ceiling is explicit: no implicit eviction can destroy
    /// content the user still has open.
    @discardableResult
    func openContent(_ content: PanelContent, origin: String,
                     screenID: String? = nil) -> ContentPanelOpenResult {
        if let existing = contentRecords.values.first(where: { $0.content == content }) {
            focusContent(existing.id)
            return .focused(existing.id)
        }
        guard contentRecords.count < Self.maxContentPanels else {
            return .rejectedLimit(maximum: Self.maxContentPanels)
        }
        let id = ContentPanelID()
        contentRecords[id] = ContentPanelRecord(id: id, content: content,
                                                origin: String(origin.prefix(120)),
                                                screenID: screenID.map { String($0.prefix(120)) })
        focusContent(id)
        return .opened(id)
    }

    func contentRecord(_ id: ContentPanelID) -> ContentPanelRecord? {
        contentRecords[id]
    }

    func contentRecord(for content: PanelContent) -> ContentPanelRecord? {
        contentRecords.values.first { $0.content == content }
    }

    func focusContent(_ id: ContentPanelID) {
        guard contentRecords[id] != nil else { return }
        for key in contentRecords.keys { contentRecords[key]?.focused = (key == id) }
        focusedContentID = id
    }

    func moveContent(_ id: ContentPanelID, to screenID: String) -> Bool {
        guard !screenID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              var record = contentRecords[id] else { return false }
        record.screenID = String(screenID.prefix(120))
        record.manualRevision += 1
        contentRecords[id] = record
        focusContent(id)
        return true
    }

    func updateContentFrame(_ id: ContentPanelID, frame: CGRect,
                            screenID: String? = nil, manual: Bool = true) {
        guard var record = contentRecords[id], frame.width > 0, frame.height > 0 else { return }
        record.frame = frame
        if let screenID { record.screenID = String(screenID.prefix(120)) }
        if manual { record.manualRevision += 1 }
        contentRecords[id] = record
    }

    func setContentFullscreen(_ id: ContentPanelID, enabled: Bool) {
        guard var record = contentRecords[id] else { return }
        record.fullscreen = enabled
        contentRecords[id] = record
        focusContent(id)
    }

    func returnContent(_ id: ContentPanelID) {
        contentRecords.removeValue(forKey: id)
        if focusedContentID == id { focusedContentID = contentRecords.keys.first }
        if let focusedContentID { focusContent(focusedContentID) }
    }

    func returnAllContent() {
        contentRecords.removeAll()
        focusedContentID = nil
    }

    var contentInventoryEntries: [JSONValue] {
        contentRecords.values.sorted { $0.id.rawValue.uuidString < $1.id.rawValue.uuidString }.map { record in
            .object([
                "id": .string(record.id.rawValue.uuidString),
                "kind": .string(record.content.key),
                "title": .string(record.origin),
                "screen_id": record.screenID.map { .string($0) } ?? .null,
            ])
        }
    }
}
