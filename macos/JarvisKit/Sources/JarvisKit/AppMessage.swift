import Foundation

// MARK: - AppMessage (§3 N7)

/// The ten payload shapes the bot's data channel emits, plus `.unknown`
/// so an older client never loses a newer bot's message. Field types are
/// Swift; optionality mirrors the JSON exactly (`?` = the emitter can
/// omit it or send `null`).
public enum AppMessage: Sendable, Equatable {
    case agentWorking(AgentWorking)
    case agentDone(AgentDone)
    case agentTool(AgentTool)
    case agentActivity(AgentActivity)
    case display(DisplayPayload)
    case ui(UICommand)
    case voiceCatalog(VoiceCatalog)
    case voiceCurrent(String)
    case speakerGate(SpeakerGate)
    case capability([CapabilityAgent])
    case consoleHello(ConsoleHello)
    case consoleRequest(ConsoleRequest)
    case consoleResult(ConsoleResult)
    case inputAccept(InputAccept)
    case inputAck(InputAck)
    case inputReady(InputReady)
    case inputStatus(InputStatus)
    case inputOffer(InputOffer)
    case inputConsent(InputConsent)
    case unknown(type: String, raw: [String: JSONValue])
}

extension AppMessage: CustomDebugStringConvertible {
    /// N2 — MortimerHost's scrolling debug List is fed this verbatim, one
    /// line per decoded message.
    public var debugDescription: String {
        switch self {
        case .agentWorking(let w): return "agentWorking(\(w.name ?? "?"), task: \(w.task))"
        case .agentDone(let d): return "agentDone(\(d.name ?? "?"), ok: \(d.ok), detail: \(d.detail))"
        case .agentTool(let t): return "agentTool(\(t.name ?? "?"), tool: \(t.tool ?? "?"))"
        case .agentActivity(let a): return "agentActivity(\(a.tool), ok: \(a.ok), \(a.latencyMs)ms)"
        case .display(let p): return "display(kind: \(p.kind ?? "?"), surface: \(p.surface.rawValue))"
        case .ui(let c): return "ui(action: \(c.action), tab: \(c.tab ?? "-"))"
        case .voiceCatalog(let c): return "voiceCatalog(\(c.voices.count) voices, current: \(c.current ?? "-"))"
        case .voiceCurrent(let v): return "voiceCurrent(\(v))"
        // String.init is ambiguous against Double? here (many overloads);
        // the explicit closure picks String(Double) and compiles.
        case .speakerGate(let g): return "speakerGate(verdict: \(g.verdict), score: \(g.score.map { String($0) } ?? "nil"))"
        case .capability(let agents): return "capability(\(agents.count) agents)"
        case .consoleRequest(let request): return "consoleRequest(\(request.action.rawValue))"
        case .consoleHello(let hello): return "consoleHello(\(hello.actions.count) actions)"
        case .consoleResult(let result): return "consoleResult(\(result.status), code: \(result.code))"
        case .inputAccept(let accept): return "inputAccept(\(accept.transferID.uuidString))"
        case .inputAck(let ack): return "inputAck(\(ack.attachmentID.uuidString), sequence: \(ack.sequence))"
        case .inputReady(let ready): return "inputReady(\(ready.batchID.uuidString))"
        case .inputStatus(let status): return "inputStatus(\(status.status), code: \(status.code))"
        case .inputOffer(let offer): return "inputOffer(\(offer.batchID.uuidString))"
        case .inputConsent(let consent): return "inputConsent(\(consent.batchID.uuidString), approved: \(consent.approved))"
        case .unknown(let type, _): return "unknown(type: \(type))"
        }
    }
}

// MARK: - Payload members

public struct AgentWorking: Sendable, Equatable, Decodable {
    public let name: String?
    public let displayName: String?
    public let runId: String?
    public let task: String
    public let model: String?
    public let modelFallback: Bool
    public let modelUnusable: Bool
    public let modelUnusableDetail: String
    enum CodingKeys: String, CodingKey {
        case name, displayName = "display_name", runId = "run_id", task, model
        case modelFallback = "model_fallback", modelUnusable = "model_unusable"
        case modelUnusableDetail = "model_unusable_detail"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name)
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName)
        runId = try c.decodeIfPresent(String.self, forKey: .runId)
        task = try c.decodeIfPresent(String.self, forKey: .task) ?? ""
        model = try c.decodeIfPresent(String.self, forKey: .model)
        modelFallback = try c.decodeIfPresent(Bool.self, forKey: .modelFallback) ?? false
        modelUnusable = try c.decodeIfPresent(Bool.self, forKey: .modelUnusable) ?? false
        modelUnusableDetail = try c.decodeIfPresent(String.self, forKey: .modelUnusableDetail) ?? ""
    }
}

/// The worked example (review F8): every non-optional scalar decodes with
/// decodeIfPresent and a stated default rather than throwing on a
/// missing key, because §7 tests older emitters that omit fields.
public struct AgentDone: Sendable, Equatable, Decodable {
    public let name: String?
    public let displayName: String?
    public let ok: Bool
    public let detail: String
    enum CodingKeys: String, CodingKey { case name, displayName = "display_name", ok, detail }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name       = try c.decodeIfPresent(String.self, forKey: .name)
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName)
        ok         = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? true       // agentRuns.ts:362
        detail     = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""   // clamp is server-side
    }
}

public struct AgentTool: Sendable, Equatable, Decodable {
    public let name: String?
    public let displayName: String?
    public let tool: String?
    enum CodingKeys: String, CodingKey { case name, displayName = "display_name", tool }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name)
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName)
        tool = try c.decodeIfPresent(String.self, forKey: .tool)
    }
}

public struct AgentActivity: Sendable, Equatable, Decodable {
    public let name: String?
    public let runId: String?
    public let tool: String
    public let ok: Bool
    public let latencyMs: Int
    /// Present only when `tool` is `selfedit_start` or `selfedit_status`
    /// (pipeline.py:206-211).
    public let plannerModel: String?
    enum CodingKeys: String, CodingKey {
        case name, runId = "run_id", tool, ok, latencyMs = "latency_ms", plannerModel = "planner_model"
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name)
        runId = try c.decodeIfPresent(String.self, forKey: .runId)
        tool = try c.decodeIfPresent(String.self, forKey: .tool) ?? ""
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        latencyMs = try c.decodeIfPresent(Int.self, forKey: .latencyMs) ?? 0
        plannerModel = try c.decodeIfPresent(String.self, forKey: .plannerModel)
    }
}

public enum DisplaySurface: String, Sendable, Equatable {
    case drawer, window
}

public struct DisplayLink: Sendable, Equatable, Codable {
    public let label: String?
    public let url: String
}

/// Every member from web/src/displayResults.ts:15-48, cross-checked
/// against jarvis/bot/display.py:6-13 and the two direct-tool emitters
/// in jarvis/bot/handoff_tools.py.
public struct DisplayPayload: Sendable, Equatable, Decodable {
    /// In-memory presentation of the assistant's existing transcript. This
    /// creates no transport event, persistence, or additional model request.
    public init(responseText: String, timestamp: Double) {
        kind = "text"; title = "Mortimer response"; body = responseText
        images = nil; basemapImages = nil; links = nil; agent = "Mortimer"
        runID = nil; ts = timestamp; surface = .window; tool = nil
        commands = nil; note = nil; expectOutput = nil; content = nil
        chars = nil; truncated = nil
    }

    public let kind: String?
    public let title: String?
    public let body: String?
    public let images: [String]?
    public let basemapImages: [String]?
    public let links: [DisplayLink]?
    public let agent: String?
    /// Agent run that produced this payload. Used only for presentation
    /// grouping; it is never treated as content identity.
    public let runID: String?
    /// Epoch SECONDS, not ms (displayResults.ts:28).
    public let ts: Double?
    /// Absent/unrecognised -> .drawer (display.py:60-92, App.tsx:238-240).
    public var surface: DisplaySurface
    public let tool: String?
    public let commands: [String]?
    public let note: String?
    public let expectOutput: Bool?
    /// Clipboard text — must never be persisted (displayResults.ts:42-45).
    public let content: String?
    public let chars: Int?
    public let truncated: Bool?

    enum CodingKeys: String, CodingKey {
        case kind, title, body, images
        case basemapImages = "basemap_images"
        case links, agent, runID = "run_id", ts, surface, tool, commands, note
        case expectOutput = "expect_output"
        case content, chars, truncated
    }

    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        kind = try c.decodeIfPresent(String.self, forKey: .kind)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        body = try c.decodeIfPresent(String.self, forKey: .body)
        images = try c.decodeIfPresent([String].self, forKey: .images)
        basemapImages = try c.decodeIfPresent([String].self, forKey: .basemapImages)
        links = try c.decodeIfPresent([DisplayLink].self, forKey: .links)
        agent = try c.decodeIfPresent(String.self, forKey: .agent)
        runID = try c.decodeIfPresent(String.self, forKey: .runID)
        ts = try c.decodeIfPresent(Double.self, forKey: .ts)
        // Two decoder rules (§3 N7): unrecognised keys (incl. a nested
        // "type") are ignored by construction (Codable only reads the
        // keys it declares); surface defaults to .drawer for nil/unknown.
        let rawSurface = try c.decodeIfPresent(String.self, forKey: .surface)
        surface = DisplaySurface(rawValue: rawSurface ?? "") ?? .drawer
        tool = try c.decodeIfPresent(String.self, forKey: .tool)
        commands = try c.decodeIfPresent([String].self, forKey: .commands)
        note = try c.decodeIfPresent(String.self, forKey: .note)
        expectOutput = try c.decodeIfPresent(Bool.self, forKey: .expectOutput)
        content = try c.decodeIfPresent(String.self, forKey: .content)
        chars = try c.decodeIfPresent(Int.self, forKey: .chars)
        truncated = try c.decodeIfPresent(Bool.self, forKey: .truncated)
    }
}

public struct UICommand: Sendable, Equatable, Decodable {
    public let action: String
    public let tab: String?
    enum CodingKeys: String, CodingKey { case action, tab }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        action = try c.decodeIfPresent(String.self, forKey: .action) ?? ""
        tab = try c.decodeIfPresent(String.self, forKey: .tab)
    }
}

public struct Voice: Sendable, Equatable, Decodable {
    public let id: String
    /// Present in the payload because it comes straight out of
    /// config/voices.yaml; the web client ignores it.
    public let elevenlabsVoiceID: String?
    public let label: String
    enum CodingKeys: String, CodingKey {
        case id, elevenlabsVoiceID = "elevenlabs_voice_id", label
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? ""
        elevenlabsVoiceID = try c.decodeIfPresent(String.self, forKey: .elevenlabsVoiceID)
        label = try c.decodeIfPresent(String.self, forKey: .label) ?? ""
    }
}

public struct VoiceCatalog: Sendable, Equatable, Decodable {
    public let voices: [Voice]
    public let current: String?
    enum CodingKeys: String, CodingKey { case voices, current }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        voices = try c.decodeIfPresent([Voice].self, forKey: .voices) ?? []
        current = try c.decodeIfPresent(String.self, forKey: .current)
    }
}

public struct SpeakerGate: Sendable, Equatable, Decodable {
    /// Always "dropped" today.
    public let verdict: String
    /// nil when speaker_gate.py:339 sends None (no score).
    public let score: Double?
    public let nearThreshold: Bool
    enum CodingKeys: String, CodingKey { case verdict, score, nearThreshold = "near_threshold" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        verdict = try c.decodeIfPresent(String.self, forKey: .verdict) ?? ""
        score = try c.decodeIfPresent(Double.self, forKey: .score)
        nearThreshold = try c.decodeIfPresent(Bool.self, forKey: .nearThreshold) ?? false
    }
}

public struct CapabilityAgent: Sendable, Equatable, Decodable {
    public let name: String
    public let displayName: String
    public let profile: String?
    public let resolvedModel: String?
    public let fallback: Bool
    enum CodingKeys: String, CodingKey {
        case name, displayName = "display_name", profile
        case resolvedModel = "resolved_model", fallback
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName) ?? ""
        profile = try c.decodeIfPresent(String.self, forKey: .profile)
        resolvedModel = try c.decodeIfPresent(String.self, forKey: .resolvedModel)
        fallback = try c.decodeIfPresent(Bool.self, forKey: .fallback) ?? false
    }
}

/// NOT an AppMessage case (§3 N7's "Not an app message"). Client-js
/// *session* state (conversationFeed.ts:28-33). Against today's bot the
/// array this feeds stays empty (correction 6: this bot emits neither
/// user- nor bot-transcription) — declared and decodable so a future
/// backend change (adding RTVIObserver to jarvis/bot/pipeline.py, R-N6)
/// lights it up with no JarvisKit change.
public struct ConversationEntry: Sendable, Equatable, Codable, Identifiable {
    public let id: String
    public let role: String   // "user" | "assistant"
    public let createdAt: Double
    public let text: String
}

/// Decodes pipecat's RTVI transcription frames
/// (pipecat/processors/frameworks/rtvi/models.py:444 user-transcription,
/// :511 bot-transcription) into a ConversationEntry. Unit-tested for
/// shape only (§7.8) — this bot emits neither today, so there is no
/// end-to-end test and none should be added (it would silently pass by
/// never running).
public enum RTVITranscription {
    struct Wire: Decodable {
        let text: String?
        let userId: String?
        let timestamp: String?
        let final: Bool?
        enum CodingKeys: String, CodingKey {
            case text, userId = "user_id", timestamp, final
        }
    }

    public static func decodeUserTranscription(from data: Data) throws -> ConversationEntry {
        let w = try JSONDecoder().decode(Wire.self, from: data)
        return ConversationEntry(
            id: UUID().uuidString,
            role: "user",
            createdAt: Date().timeIntervalSince1970,
            text: w.text ?? ""
        )
    }

    public static func decodeBotTranscription(from data: Data) throws -> ConversationEntry {
        let w = try JSONDecoder().decode(Wire.self, from: data)
        return ConversationEntry(
            id: UUID().uuidString,
            role: "assistant",
            createdAt: Date().timeIntervalSince1970,
            text: w.text ?? ""
        )
    }
}

// MARK: - Decoding entry point

public extension AppMessage {
    /// Decode ONE data-channel text frame.
    /// Accepts the server envelope written by _wrap_rtvi (jarvis/bot/pipeline.py)
    ///   {"id":…, "label":"rtvi-ai", "type":"server-message", "data": <payload>}
    /// and, defensively, a bare payload (the envelope is a client-js
    /// workaround, D-005 — a future bot may drop it).
    /// Returns nil for a signalling frame or a frame with no "type".
    static func decode(frame data: Data) throws -> AppMessage? {
        let root = try JSONDecoder().decode(JSONValue.self, from: data)
        guard case .object(let obj) = root, let t = obj["type"]?.stringValue else { return nil }
        if t == "signalling" { return nil }                 // connection.py:349
        let payloadValue: JSONValue
        if t == "server-message", let d = obj["data"] { payloadValue = d } else { payloadValue = root }
        guard case .object(let p) = payloadValue, let kind = p["type"]?.stringValue else { return nil }
        let payload = try JSONEncoder().encode(payloadValue)
        let dec = JSONDecoder()
        switch kind {
        case "agent":
            switch p["state"]?.stringValue {
            case "working": return .agentWorking(try dec.decode(AgentWorking.self, from: payload))
            case "done":    return .agentDone(try dec.decode(AgentDone.self, from: payload))
            default:        return .unknown(type: kind, raw: p)
            }
        case "agent_tool":     return .agentTool(try dec.decode(AgentTool.self, from: payload))
        case "agent_activity": return .agentActivity(try dec.decode(AgentActivity.self, from: payload))
        case "display":
            guard let d = p["display"] else { return .unknown(type: kind, raw: p) }
            return .display(try dec.decode(DisplayPayload.self, from: JSONEncoder().encode(d)))
        case "ui":             return .ui(try dec.decode(UICommand.self, from: payload))
        case "voice/catalog":  return .voiceCatalog(try dec.decode(VoiceCatalog.self, from: payload))
        case "voice/current":  return .voiceCurrent(p["voice"]?.stringValue ?? "")
        case "speaker_gate":   return .speakerGate(try dec.decode(SpeakerGate.self, from: payload))
        case "capability":
            guard let a = p["agents"] else { return .capability([]) }
            return .capability(try dec.decode([CapabilityAgent].self, from: JSONEncoder().encode(a)))
        case "console/request":
            return .consoleRequest(try dec.decode(ConsoleRequest.self, from: payload))
        case "console/hello":
            return .consoleHello(try dec.decode(ConsoleHello.self, from: payload))
        case "console/result":
            return .consoleResult(try dec.decode(ConsoleResult.self, from: payload))
        case "input/accept":
            return .inputAccept(try dec.decode(InputAccept.self, from: payload))
        case "input/ack":
            return .inputAck(try dec.decode(InputAck.self, from: payload))
        case "input/ready":
            return .inputReady(try dec.decode(InputReady.self, from: payload))
        case "input/status":
            return .inputStatus(try dec.decode(InputStatus.self, from: payload))
        case "input/offer":
            return .inputOffer(try dec.decode(InputOffer.self, from: payload))
        case "input/consent":
            return .inputConsent(try dec.decode(InputConsent.self, from: payload))
        default:               return .unknown(type: kind, raw: p)
        }
    }
}
