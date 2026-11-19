---
date: 2026-11-19
system: claude
rows: [WS-38]
prs: []
---

# 2026-11-19 · WS-38 2A failure classes and reason codes

- **System:** Claude (Opus 5.5, Claude Code cloud session for Larry's Claude Duet channel).
- **Row:** WS-38, option 2A only, claimed via #403. Branch `claude/ws38-failure-classes-20261119` into `next`.
- **Larry's words (UTC, Claude Duet channel):** 03:28:05: "Yes, start there".
- **Built:**
  - `jarvis/toolresult.py`: every failed `ToolOutcome` carries `failure_class` (`transient`, `approach`, `policy`) and a closed `reason` from one table, `REASON_CLASSES`. An unlisted failure gets `tool_reported_failure`, class `approach`. Free text never becomes a reason.
  - `jarvis/skills/registry.py`: the registry's own failure category decides the reason; `mcp_call` logs the closed reason.
  - `jarvis/agents/base.py`: the failure constraint adds a class note; a policy note forbids getting the same thing another way or proposing a code change to remove the guard. An identical (tool, arguments) repeat after an `approach` or `policy` failure with a listed reason is refused before dispatch. An all-failed reply ends with a `[failure class: …; reason: …]` tag.
  - `jarvis/agents/delegate.py`: known whole-run failures (rounds exhausted, timeout, private route) get the same tag.
  - `jarvis/runlog/store.py`: a failed `tool_result` keeps `reason` and `failure_class` in the run payload even when the result is redacted. No migration; the DB `result_preview` is unchanged.
  - `jarvis/bot/pipeline.py`: only the Supervisor tool wrapper's `runlog.tool_result` call passes the reason, so a private Supervisor `local_weather` failure (the 9:51 PM case) is logged with its reason.
  - `jarvis/voice_workflows.py` and `config/workflows/voice-explain-failure.yaml`: a `reasoned` result kind, and the workflow reports a tagged reason instead of sending a developer to read the log.
- **Not changed:** `weather_tool.py`, `weather_reuse.py`, the named-weather registry block (the weather saved-card fix owns them). Both `weather_reuse_invalid_request` (approach) and `weather_reuse_not_requested` (policy) are in the table.
- **Deviation from the design note:** the tag is appended, not a `FAILED[class:reason]:` prefix, because `delegate.py`, `runlog/store.py` and `voice_workflows.py` test `startswith("FAILED:")`.
- **Untested:** live voice runs on the Mac. Unit tests cover the classifier, the repeat block, redacted reasons, tags and result kinds.
