---
date: 2026-11-19
system: claude
rows: [WS-38]
prs: [425]
---

# 2026-11-19 · WS-38 1A per-tool backup paths

- **System:** Claude (Opus 5.5, Claude Code cloud session for Larry's Claude Duet channel). Plan by a Fable 5.2 helper agent; implementation by a Sonnet 5.5 helper agent.
- **Row:** WS-38, option 1A (design note §5). Built 2026-11-19 on branch `claude/ws38-fallbacks-20261119`; that session's push was refused, so neither it nor its docs-only claim PR for `main` was pushed. Landed via PR #425 into `next` (branch `claude/project-thread-b7mgnc`, 2026-11-26, applied to `next` at `50dd8ab` without conflicts, together with WS-37 Phase 3). The daily batch records Owner `claude` (1A) and Where.
- **Built:**
  - `jarvis/fallbacks.py` (new): the one gate, `may_fall_back(reason)`. A backup path is allowed only for a listed reason whose class is `transient` or `approach` and that is not in `NO_BACKUP_REASONS` (rate limit, rejected key, exhausted quota, rejected request, missing configuration, bad arguments: the second path would fail the same way). An unlisted reason or any `policy` reason is never allowed. `http_failure_reason` maps httpx failures to closed reasons. `PATHS` holds closed path codes per tool; `served`/`mark`/`read_served` put and read `served_by` and `fallback_after` in a result body.
  - `jarvis/toolresult.py`: eleven closed reasons (`upstream_*`, `tool_not_configured`, `invalid_arguments`); a listed `reason` key in a tool's body now decides the reason ahead of parsing `error`.
  - `jarvis/skills/registry.py`: the classified-mode failure reduction keeps the closed reason instead of always writing `tool_reported_failure` (raw text is still dropped). `_finish_invocation` logs `tool_path tool=… path=… after=…` and passes the path codes to the run log.
  - `jarvis/runlog/store.py`: `mcp_call` stores `served_by` and `fallback_after` in the run payload. No migration.
  - `mcp_servers/mcp_web/logic.py` `web_search`: Tavily's hosted MCP stays primary; REST runs only when the gate allows it after the MCP failure (timeout, unreachable, 5xx, 403 block, protocol error). A 401, 429 or quota status returns at once with its reason. Every failure carries a closed `reason`; a success says `served_by: tavily_mcp` or `tavily_rest` with `fallback_after`.
- **Weather:** not changed. The unmerged weather saved-card fix keeps its files. `PATHS` reserves `saved_card`/`live_fetch` for `local_weather`, `get_weather` and `get_weather_radar`, so that fix can swap its own hard-refusal set for `may_fall_back("weather_reuse_" + code)`. Open point for it: it lets `protected_result` fall back to live, while 2A's table classes `weather_reuse_protected_result` as `policy`.
- **Not built, needs Larry:** backups for `system_status`/`status_services`/`status_build`/`log_search` computed outside the admin sidecar (conflicts with spec L2 in `docs/plans/MORTIMER_SELF_SERVICE_ACCESS_IMPLEMENTATION_SPEC.md`); an ESPN MLB backup for `sports_scores` (a new unofficial endpoint).
- **Tests:** `tests/unit/test_fallbacks.py` (new, walks the whole reason table), plus additions to `test_toolresult.py`, `test_registry_source_policy.py`, `test_runlog_store.py`, `test_mcp_web_logic.py`. Full unit suite in the cloud: 8564 passed, 141 skipped, 1 error (`test_ws_transport`, same as the baseline before this change). Ruff F clean.
- **Untested:** live Tavily status codes from the Mac's network (432/433 as quota is from Tavily's docs, not observed); a live sub-agent run showing the new reasons and path codes.
- **2026-11-26 re-run on `next` 50dd8ab + this change:** ruff F clean, roadmap check 0/0, unit suite 8,904 passed, 141 skipped, 1 error (`test_ws_transport`, unchanged).
