import Foundation
import JarvisKit

/// Closed action catalogue shared by pointer and voice adapters. Keeping the
/// registry in the host makes capability discovery deterministic and prevents
/// a view from claiming an action the coordinator cannot execute.
struct ConsoleActionDescriptor: Equatable, Sendable {
    let action: ConsoleAction
    let requiresTarget: Bool
    let enabled: Bool
}

struct ConsoleActionRegistry: Sendable {
    private let descriptors: [ConsoleActionDescriptor]

    init(enabled: Set<ConsoleAction> = Set(ConsoleAction.allCases)) {
        descriptors = ConsoleAction.allCases.map {
            ConsoleActionDescriptor(action: $0,
                                    requiresTarget: Self.targetActions.contains($0),
                                    enabled: enabled.contains($0))
        }
    }

    var enabledActions: Set<ConsoleAction> {
        Set(descriptors.filter(\.enabled).map(\.action))
    }

    func descriptor(for action: ConsoleAction) -> ConsoleActionDescriptor? {
        descriptors.first { $0.action == action }
    }

    /// Validate the native half of the wire contract before a request reaches
    /// any store. The Python decoder protects the server boundary, but the
    /// app must repeat the closed-field and finite-value checks because a
    /// stale or hand-built request can arrive from an older server/client.
    func validate(_ request: ConsoleRequest, currentRevision: Int? = nil) -> Bool {
        guard let descriptor = descriptor(for: request.action), descriptor.enabled else { return false }
        if let currentRevision, request.revision != currentRevision { return false }
        if descriptor.requiresTarget && request.target?.isEmpty != false { return false }
        if Self.secondaryTargetActions.contains(request.action),
           request.secondaryTarget?.isEmpty != false { return false }
        if request.action == .atlasMove,
           request.args["relation"] != nil,
           request.secondaryTarget?.isEmpty != false { return false }
        guard request.revision >= 0 else { return false }
        guard request.target.map({ $0.count <= 120 }) ?? true,
              request.secondaryTarget.map({ $0.count <= 120 }) ?? true else { return false }

        let fields = Self.argumentFields[request.action] ?? []
        guard Set(request.args.keys).isSubset(of: fields) else { return false }
        for value in request.args.values {
            switch value {
            case .number(let number):
                guard number.isFinite else { return false }
            case .string(let text):
                guard text.count <= 2_000 else { return false }
            case .array(let values):
                guard values.count <= 4 else { return false }
            default:
                break
            }
        }
        guard Self.argumentsAreWellTyped(request) else { return false }
        if request.action == .atlasMove {
            let hasRelation = request.args["relation"] != nil
            let hasRow = request.args["row"] != nil
            let hasColumn = request.args["column"] != nil
            guard hasRelation != (hasRow || hasColumn), hasRow == hasColumn else { return false }
            for key in ["row", "column"] where request.args[key] != nil {
                guard let value = request.args[key]?.intValue,
                      (1...AtlasStore.maxVoiceRow).contains(value) else { return false }
            }
        }
        if request.action == .graphSearch,
           let query = request.args["query"]?.stringValue,
           query.count > 200 { return false }
        if request.action == .graphFocus,
           let depth = request.args["depth"]?.intValue,
           !(1...4).contains(depth) { return false }
        return true
    }

    /// Compatibility overload retained for existing callers and tests.
    func validate(_ request: ConsoleRequest) -> Bool { validate(request, currentRevision: nil) }

    private static let argumentFields: [ConsoleAction: Set<String>] = [
        .inventory: ["scope", "cursor"],
        .viewSet: ["mode"], .resultMode: ["mode"], .compareSide: ["side"],
        .contentScroll: ["panel", "direction", "viewport"],
        .sourceSelect: ["source", "index"], .sourceOpen: ["source", "index"],
        .sourceInspector: ["open"], .imageSelect: ["index"],
        .atlasZoom: ["direction"], .atlasPan: ["direction"],
        .atlasMove: ["relation", "row", "column"], .groupCreate: ["name"],
        .groupRename: ["name"], .groupAssign: ["group"],
        .groupRemoveCard: ["group"], .graphSearch: ["query"],
        .graphFocus: ["depth"], .graphFilter: ["kind", "visible"], .graphGroup: ["collapsed"],
        .graphInspector: ["open"], .graphOriginal: ["enabled"],
        .graphMoveNode: ["x", "y"], .panelMove: ["screen_id"],
        .panelFullscreen: ["enabled"], .sidecarWidth: ["points"],
        .sidecarText: ["size"], .sidecarScrollTabs: ["direction"],
        .appearanceSet: ["layout"], .consoleCaption: ["expanded"],
        .consoleStatus: ["open"], .waveTuningSet: ["key", "value"],
        .sharePreview: ["format", "scope", "ordinal"], .shareSource: ["source", "index"],
        .inputPaste: ["format"], .inputChoose: ["format"],
        .inputQuestion: ["question"], .inputNewConversation: ["confirmed"],
        .sharedContent: ["attachment_ids", "question"],
    ]

    private static func argumentsAreWellTyped(_ request: ConsoleRequest) -> Bool {
        func string(_ key: String) -> Bool {
            guard let value = request.args[key] else { return true }
            if case .string = value { return true }
            return false
        }
        func number(_ key: String) -> Bool {
            guard let value = request.args[key] else { return true }
            if case .number(let n) = value { return n.isFinite }
            return false
        }
        func bool(_ key: String) -> Bool {
            guard let value = request.args[key] else { return true }
            if case .bool = value { return true }
            return false
        }
        let stringFields = ["scope", "cursor", "mode", "side", "panel", "direction",
                            "source", "relation", "name", "group", "query", "kind",
                            "screen_id", "key", "format", "question", "scope"]
        guard stringFields.allSatisfy(string), ["viewport", "points", "x", "y", "value"].allSatisfy(number),
              ["open", "visible", "collapsed", "enabled", "expanded", "confirmed"].allSatisfy(bool) else { return false }
        if let value = request.args["index"] { guard value.intValue != nil else { return false } }
        if let value = request.args["ordinal"] { guard value.intValue != nil else { return false } }
        if let value = request.args["row"] { guard value.intValue != nil else { return false } }
        if let value = request.args["column"] { guard value.intValue != nil else { return false } }
        if let value = request.args["size"] { guard value.intValue != nil else { return false } }
        if let value = request.args["depth"] { guard value.intValue != nil else { return false } }
        if let value = request.args["layout"] { guard value.intValue != nil else { return false } }
        if let value = request.args["attachment_ids"] {
            guard case .array(let values) = value, (1...4).contains(values.count),
                  values.allSatisfy({ if case .string = $0 { return true }; return false }) else { return false }
        }
        return true
    }

    private static let targetActions: Set<ConsoleAction> = [
        // Targets are required only where the action cannot safely use the
        // current selection. Enum-like values remain arguments (with the
        // legacy target fallback retained by the coordinator).
        .resultSelect, .resultPin, .resultUnpin, .resultClose, .resultMode,
        .compareSet, .groupRename, .groupAssign, .groupRemoveCard, .groupDissolve,
        .atlasMove, .graphFocus, .graphSelect, .graphSelectEdge, .graphFilter,
        .graphGroup, .graphPath, .graphCenter, .graphMoveNode,
        .panelDetach, .panelMove, .panelReturn, .panelClose, .panelFocus,
        .panelFullscreen, .inputRemove,
    ]

    private static let secondaryTargetActions: Set<ConsoleAction> = [
        .compareSet, .graphPath,
    ]
}
