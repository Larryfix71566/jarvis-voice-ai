import Foundation

/// Versioned Command Console messages. Presentation clients must reject
/// unknown actions before sending; the bot remains the authority for state.
public enum ConsoleAction: String, Codable, Sendable, CaseIterable {
    case inventory, help, viewSet = "view_set", resultSelect = "result_select"
    case resultClose = "result_close", resultPin = "result_pin", resultUnpin = "result_unpin"
    case resultNext = "result_next", resultPrevious = "result_previous", resultMode = "result_mode"
    case compareSet = "compare_set", compareEnd = "compare_end", compareSide = "compare_side"
    case contentScroll = "content_scroll", sourceSelect = "source_select", sourceOpen = "source_open"
    case sourceInspector = "source_inspector", imageSelect = "image_select"
    case atlasFit = "atlas_fit", atlasArrange = "atlas_arrange", atlasZoom = "atlas_zoom"
    case atlasPan = "atlas_pan", atlasMove = "atlas_move", groupCreate = "group_create"
    case groupRename = "group_rename", groupAssign = "group_assign", groupRemoveCard = "group_remove_card"
    case groupDissolve = "group_dissolve", graphSearch = "graph_search", graphFocus = "graph_focus"
    case graphSelect = "graph_select", graphSelectEdge = "graph_select_edge", graphBack = "graph_back"
    case graphFit = "graph_fit", graphReset = "graph_reset", graphRetry = "graph_retry"
    case graphZoom = "graph_zoom", graphPan = "graph_pan", graphFilter = "graph_filter"
    case graphGroup = "graph_group", graphPath = "graph_path", graphPathClear = "graph_path_clear"
    case graphInspector = "graph_inspector", graphOriginal = "graph_original", graphCenter = "graph_center"
    case graphMoveNode = "graph_move_node", panelDetach = "panel_detach", panelMove = "panel_move"
    case panelReturn = "panel_return", panelClose = "panel_close", panelFocus = "panel_focus"
    case panelFullscreen = "panel_fullscreen", panelsReturnAll = "panels_return_all"
    case sidecarWidth = "sidecar_width", sidecarText = "sidecar_text", sidecarScrollTabs = "sidecar_scroll_tabs"
    case appearanceSet = "appearance_set", consoleCaption = "console_caption", consoleStatus = "console_status"
    case waveTuningOpen = "wave_tuning_open", waveTuningSet = "wave_tuning_set", resetLayout = "reset_layout"
    case sharePreview = "share_preview", shareCopy = "share_copy", shareSave = "share_save"
    case sharePicker = "share_picker", shareCancel = "share_cancel", shareSource = "share_source"
    case inputPaste = "input_paste", inputChoose = "input_choose", inputRemove = "input_remove"
    case inputClear = "input_clear", inputPreview = "input_preview", inputQuestion = "input_question"
    case inputCancel = "input_cancel", inputNewConversation = "input_new_conversation"
    case exportFolderChoose = "export_folder_choose", exportFolderClear = "export_folder_clear"
    case sharedContent = "shared_content"
}

public struct ConsoleHello: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let actions: [String]
    public let inputTypes: [String]
    public let inputProfile: ConsoleInputProfile?

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, actions
        case inputTypes = "input_types", inputProfile = "input_profile"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? "console/hello"
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? 1
        sessionID = try c.decode(UUID.self, forKey: .sessionID)
        generation = try c.decode(UUID.self, forKey: .generation)
        actions = Array((try c.decodeIfPresent([String].self, forKey: .actions) ?? []).prefix(100)).map { String($0.prefix(80)) }
        inputTypes = Array((try c.decodeIfPresent([String].self, forKey: .inputTypes) ?? []).prefix(8)).map { String($0.prefix(80)) }
        inputProfile = try c.decodeIfPresent(ConsoleInputProfile.self, forKey: .inputProfile)
    }
}

public struct ConsoleInputProfile: Codable, Sendable, Equatable {
    public let id: String
    public let label: String
    public init(id: String, label: String) {
        self.id = String(id.prefix(120)); self.label = String(label.prefix(120))
    }
}

public struct ConsoleReady: Codable, Sendable, Equatable {
    public let type = "console/ready"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let actions: [String]
    public let inputTypes: [String]
    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, actions
        case inputTypes = "input_types"
    }
    public init(sessionID: UUID, generation: UUID, actions: [String], inputTypes: [String]) {
        self.sessionID = sessionID; self.generation = generation
        self.actions = Array(actions.prefix(100)).map { String($0.prefix(80)) }
        self.inputTypes = Array(inputTypes.prefix(8)).map { String($0.prefix(80)) }
    }
}

/// Native-owned, privacy-safe inventory snapshot.  The snapshot contains
/// bounded identifiers and labels only; result bodies, clipboard text, local
/// paths and image bytes never cross this boundary.
public struct ConsoleInventory: Codable, Sendable, Equatable {
    public let type = "console/inventory"
    public let version = 1
    public let sessionID: UUID
    public let generation: UUID
    public let revision: Int
    public let data: JSONValue

    public init(sessionID: UUID, generation: UUID, revision: Int,
                data: JSONValue) {
        self.sessionID = sessionID
        self.generation = generation
        self.revision = max(0, revision)
        self.data = data
    }

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation, revision, data
    }
}

public struct ConsoleRequest: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let revision: Int
    public let action: ConsoleAction
    public let target: String?
    public let secondaryTarget: String?
    public let args: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", revision, action, target
        case secondaryTarget = "secondary_target", args
    }

    public init(sessionID: UUID, generation: UUID, requestID: UUID,
                revision: Int, action: ConsoleAction, target: String? = nil,
                secondaryTarget: String? = nil,
                args: [String: JSONValue] = [:]) {
        self.type = "console/request"; self.version = 1
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.revision = revision
        self.action = action; self.target = target
        self.secondaryTarget = secondaryTarget; self.args = args
    }
}

public struct ConsoleResult: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let sessionID: UUID
    public let generation: UUID
    public let requestID: UUID
    public let status: String
    public let code: String
    public let summary: String
    public let choices: [ConsoleChoice]?
    public let data: JSONValue?

    public init(sessionID: UUID, generation: UUID, requestID: UUID,
                status: String, code: String, summary: String,
                choices: [ConsoleChoice]? = nil, data: JSONValue? = nil) {
        self.type = "console/result"; self.version = 1
        self.sessionID = sessionID; self.generation = generation
        self.requestID = requestID; self.status = status; self.code = code
        self.summary = String(summary.prefix(240)); self.choices = choices; self.data = data
    }

    enum CodingKeys: String, CodingKey {
        case type, version, sessionID = "session_id", generation
        case requestID = "request_id", status, code, summary
        case choices, data
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? "console/result"
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? 1
        sessionID = try c.decode(UUID.self, forKey: .sessionID)
        generation = try c.decode(UUID.self, forKey: .generation)
        requestID = try c.decode(UUID.self, forKey: .requestID)
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? "error"
        code = try c.decodeIfPresent(String.self, forKey: .code) ?? "invalid"
        summary = String((try c.decodeIfPresent(String.self, forKey: .summary) ?? "").prefix(240))
        choices = try c.decodeIfPresent([ConsoleChoice].self, forKey: .choices)
        data = try c.decodeIfPresent(JSONValue.self, forKey: .data)
    }
}

public struct ConsoleChoice: Codable, Sendable, Equatable {
    public let id: String
    public let label: String
}
