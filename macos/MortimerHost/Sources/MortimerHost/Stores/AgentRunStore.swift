import Foundation
import Observation
import JarvisKit

/// APP plan §3 P8 — the native port of web/src/agentRuns.ts, reducer
/// logic ported VERBATIM from applyServerMessage (agentRuns.ts:276-392)
/// and pinned by AgentRunStoreTests (§7.2). App-scope so run state
/// outlives any tab view (the exact reason the web made it a module
/// store, agentRuns.ts:9-11). Fed ONLY by AppMessageRouter (D10's
/// single-listener rule, §5 step 5).
struct ActivityLine: Equatable, Sendable {
    let tool: String
    let ok: Bool
    let latencyMs: Int
    let ts: Date
}

let RUN_STAGES = ["planning", "proposing", "validating", "submitting"]

struct AgentRun: Identifiable, Equatable, Sendable {
    let id: Int
    let name: String
    var displayName: String
    let runId: String              // "" for messages from a bot predating the field
    let task: String
    var tools: [String]
    var activity: [ActivityLine]
    var stage: Int                 // index into RUN_STAGES (self-edit runs only)
    let startedAt: Date
    var doneAt: Date?
    var ok: Bool
    var detail: String
    let model: String              // "" when the bot predates the field
    let modelFallback: Bool
    let modelUnusable: Bool
    let modelUnusableDetail: String
    var plannerModel: String       // sticks once seen (agentRuns.ts:327-341)
}

/// agentRuns.ts clamp()
func clampText(_ s: String, _ max: Int) -> String {
    let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
    return t.count > max ? String(t.prefix(max - 1)) + "…" : t
}

/// agentRuns.ts shortModel() — keep the identifying tail; full string
/// goes in help text so shortening never destroys information.
func shortModel(_ model: String, max: Int = 22) -> String {
    let tail = model.trimmingCharacters(in: .whitespaces).split(separator: "/").last.map(String.init) ?? ""
    return tail.count > max ? String(tail.prefix(max - 1)) + "…" : tail
}

/// agentRuns.ts toolStage()
func toolStage(_ tool: String) -> Int {
    let t = tool.lowercased()
    if t.range(of: "valid|test|pytest|check", options: .regularExpression) != nil { return 2 }
    if t.range(of: "submit|push|pull_request|\\bpr\\b", options: .regularExpression) != nil { return 3 }
    if t.range(of: "propos|write|edit|apply|patch|create", options: .regularExpression) != nil { return 1 }
    return 0
}

/// agentRuns.ts isSelfEditRun() — plan D9: `"developer".includes("develop")`
/// is true for EVERY developer run; the plan accepts that.
func isSelfEditRun(name: String, tools: [String]) -> Bool {
    let n = name.lowercased()
    return n.contains("self") || n.contains("edit") || n.contains("develop")
        || tools.contains { $0.lowercased().hasPrefix("selfedit") }
}

/// E5 — the durable per-agent completion record behind the satellite
/// tick + hover tooltip. Unlike `runs` (whose non-self-edit entries fade
/// 8s after success), this NEVER fades: the web's OrbField reads
/// lastRunFor from a store whose entries persist, and the tick is
/// history, not alarm (parity sweep 2026-08-30).
struct CompletedRun: Equatable, Sendable {
    let ok: Bool
    let task: String
    let startedAt: Date
    let doneAt: Date
}

@MainActor
@Observable
final class AgentRunStore {
    private(set) var runs: [AgentRun] = []   // oldest first (agentRuns.ts getRuns())
    /// The agent roster from the `.capability` message — agent-domain
    /// state, so it lives with the agent store (TopBarView's chip reads it).
    private(set) var capabilityAgents: [CapabilityAgent] = []
    /// Newest COMPLETED run per agent key — satellite tick + tooltip (E5).
    private(set) var lastCompleted: [String: CompletedRun] = [:]

    /// D7 — the topbar/tab live dot: any self-edit-shaped run in flight.
    var selfEditRunning: Bool {
        runs.contains { isSelfEditRun(name: $0.name, tools: $0.tools) && $0.doneAt == nil }
    }

    private var seq = 0
    private var liveRunIds: [String: Int] = [:]   // agent name -> LIVE run id
    private var fadeTasks: [Int: Task<Void, Never>] = [:]

    /// E5 — satellite click -> Runs tab pre-filter. One-shot slot, read
    /// and cleared by RunsTab on appear (consumeRequestedAgentFilter).
    var requestedAgentFilter: String?
    func consumeRequestedAgentFilter() -> String? {
        defer { requestedAgentFilter = nil }
        return requestedAgentFilter
    }

    private func clearTimer(_ id: Int) {
        fadeTasks[id]?.cancel()
        fadeTasks[id] = nil
    }

    func removeRun(id: Int) {
        if let run = runs.first(where: { $0.id == id }), liveRunIds[run.name] == id {
            liveRunIds[run.name] = nil
        }
        clearTimer(id)
        runs.removeAll { $0.id == id }
    }

    /// agentRuns.ts insertRun() — plan D8a: non-self-edit replaces the
    /// agent's previous card; self-edit APPENDS, evicting the oldest
    /// COMPLETED run past maxAgentRuns; a live run is never evicted.
    private func insert(_ run: AgentRun, into list: [AgentRun]) -> [AgentRun] {
        if !isSelfEditRun(name: run.name, tools: run.tools) {
            return list.filter { $0.name != run.name } + [run]
        }
        var next = list + [run]
        while next.filter({ $0.name == run.name }).count > AppTuning.maxAgentRuns {
            guard let victim = next.first(where: { $0.name == run.name && $0.doneAt != nil }) else {
                break   // all in flight — never evict a live run
            }
            clearTimer(victim.id)
            next.removeAll { $0.id == victim.id }
        }
        return next
    }

    /// The ONLY mutator from RTVI events — applyServerMessage, ported.
    func apply(_ message: AppMessage) {
        switch message {
        case .agentWorking(let w):
            guard let name = w.name else { return }
            let displayName = (w.displayName?.isEmpty == false) ? w.displayName! : name
            if let prevId = liveRunIds[name] { clearTimer(prevId) }
            seq += 1
            let id = seq
            liveRunIds[name] = id
            let run = AgentRun(
                id: id, name: name, displayName: displayName,
                runId: w.runId ?? "",
                task: clampText(w.task, 200),
                tools: [], activity: [], stage: 0,
                startedAt: Date(), doneAt: nil, ok: false, detail: "",
                model: w.model ?? "",
                modelFallback: w.modelFallback,
                modelUnusable: w.modelUnusable,
                modelUnusableDetail: w.modelUnusableDetail,
                plannerModel: ""
            )
            runs = insert(run, into: runs)

        case .agentActivity(let a):
            guard let name = a.name else { return }
            // Matched by backend run_id when both sides carry one, else
            // by the agent's live run — the same fallback agent_tool uses.
            let runId = a.runId ?? ""
            let line = ActivityLine(tool: a.tool, ok: a.ok, latencyMs: a.latencyMs, ts: Date())
            // G7 — planner_model sticks once seen; never cleared by a
            // later line that didn't report one.
            let plannerModel = (a.plannerModel?.isEmpty == false) ? a.plannerModel : nil
            runs = runs.map { r in
                let match = (!runId.isEmpty && !r.runId.isEmpty)
                    ? r.runId == runId
                    : r.name == name && r.doneAt == nil
                guard match else { return r }
                var next = r
                next.activity = Array((r.activity + [line]).suffix(AppTuning.maxActivity))
                next.plannerModel = plannerModel ?? r.plannerModel
                return next
            }

        case .agentTool(let t):
            guard let name = t.name, let tool = t.tool else { return }
            let displayName = (t.displayName?.isEmpty == false) ? t.displayName! : name
            runs = runs.map { r in
                guard r.name == name && r.doneAt == nil else { return r }
                var next = r
                next.displayName = displayName
                next.tools = Array((r.tools + [tool]).suffix(AppTuning.maxTools))
                next.stage = max(r.stage, toolStage(tool))
                return next
            }

        case .agentDone(let done):
            guard let name = done.name else { return }
            let displayName = (done.displayName?.isEmpty == false) ? done.displayName! : name
            let ok = done.ok               // decoder already defaults missing to true (agentRuns.ts:362)
            let detail = clampText(done.detail, 300)
            runs = runs.map { r in
                guard r.name == name && r.doneAt == nil else { return r }
                var next = r
                next.displayName = displayName
                next.doneAt = Date()
                next.ok = ok
                next.detail = detail
                // E5 — record the completion durably (survives the 8s
                // fade below; the satellite tick reads this).
                lastCompleted[name] = CompletedRun(
                    ok: ok, task: r.task, startedAt: r.startedAt, doneAt: next.doneAt!
                )
                return next
            }
            // D8: self-edit runs are exempt from the success fade — the
            // tab is a deliberately opened reading surface.
            guard ok, let id = liveRunIds[name],
                  let settled = runs.first(where: { $0.id == id }),
                  !isSelfEditRun(name: settled.name, tools: settled.tools) else { return }
            clearTimer(id)
            fadeTasks[id] = Task { [weak self] in
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.doneFadeSeconds * 1_000_000_000))
                guard !Task.isCancelled else { return }
                self?.removeRun(id: id)
            }

        case .capability(let agents):
            capabilityAgents = agents

        default:
            break
        }
    }
}
