import Foundation

/// Interface cleanup Phase 2, slice D: the current-tense working line shown
/// under the request. Maps the raw tool id (or, failing that, the agent id)
/// to a plain phrase. Both inputs are fixed ids from the bot, never the
/// run's task text, so the line cannot leak what the user said.
enum WorkingLine {
    static let thinking = "Thinking"
    static let starting = "Starting"
    static let fallback = "Working on it"

    static func phrase(tool: String?, agent: String?) -> String {
        let toolId = normalized(tool)
        if toolId.isEmpty { return starting }
        if let known = toolPhrase(toolId) { return known }
        return agentPhrase(normalized(agent)) ?? fallback
    }

    private static func normalized(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private static func has(_ id: String, _ parts: [String]) -> Bool {
        parts.contains { id.contains($0) }
    }

    /// Real ids: mcp_servers/*/server.py. Order matters (first match wins):
    /// specific families before generic words such as "search" or "write".
    private static func toolPhrase(_ id: String) -> String? {
        if has(id, ["weather"]) { return "Checking the weather" }
        if id.hasPrefix("app_") || has(id, ["app_builder"]) { return "Building the app" }
        if has(id, ["web_search", "tavily", "fetch", "research_", "sports_scores", "browse"]) {
            return "Searching the web"
        }
        if has(id, ["mail"]) { return "Reading your email" }
        if has(id, ["reminder"]) { return "Checking your reminders" }
        if has(id, ["calendar", "schedul", "get_current_time", "resolve_date", "date_add", "date_diff"]) {
            return "Checking your calendar"
        }
        if has(id, ["kb_", "memory_", "note", "knowledge", "search_sessions"]) { return "Searching your notes" }
        if id.hasPrefix("selfedit_") {
            return has(id, ["read", "status"]) ? "Reading the repository" : "Editing code"
        }
        if has(id, ["repo_write", "repo_commit", "commit", "push", "patch", "edit", "plan_"]) {
            return "Editing code"
        }
        if has(id, ["repo_", "git_", "github", "file_read", "read_file", "list_files"]) {
            return "Reading the repository"
        }
        if has(id, ["sandbox", "python", "run_code", "execute", "code_run"]) { return "Running code" }
        if has(id, ["runlog", "council_", "graph_view", "analy", "sql", "query", "data"]) {
            return "Analysing the data"
        }
        if has(id, ["system", "process", "disk", "battery", "status_", "log_search", "uptime"]) {
            return "Checking the Mac"
        }
        return nil
    }

    /// Ids from config/agents.yaml.
    private static func agentPhrase(_ agent: String) -> String? {
        switch agent {
        case "librarian": return "Looking that up"
        case "developer": return "Working on the code"
        case "analyst": return "Analysing"
        case "systems": return "Checking the Mac"
        case "scheduler": return "Checking your schedule"
        case "app_builder": return "Building the app"
        default: return nil
        }
    }
}
