# GC24-03 agent, event, and findings log redaction

**Date:** 2026-09-25  
**Scope:** bounded logging paths in SubAgent procedure/skill/workflow matching,
agent event callbacks, specialist findings reads, upgrade-agent callbacks, and
supervisor event callbacks. This is a partial GC24-03 receipt.

## Change and privacy boundary

These paths now log bounded exception class information rather than raw
exception messages or tracebacks. Findings read failures no longer log an
agent-supplied path or raw reason text. The behavior that reports the
underlying operation's failure to its caller remains intact; only diagnostic
logging is narrowed. Canary tests verify that sentinel exception, task, path,
and reason payloads do not appear in captured logs.

Files covered include `jarvis/agents/base.py`, `delegate.py`,
`upgrade_agent.py`, and `supervisor.py`, with corresponding unit tests in
`tests/unit/test_subagent.py`, `test_delegate.py`,
`test_upgrade_agent.py`, and `test_supervisor_tool_registration.py`.

## Verification

- Focused suite: **165 passed, 2 warnings**.
- Full unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,877 passed, 4 skipped, 11 warnings, 2 subtests**.
- Ruff `F`/`I` checks on touched implementation and test files: passed.
- `git diff --check`: passed.

This receipt closes only the listed agent/delegation/event/findings log paths.
It does not close GC24-03: the complete source-to-sink audit and negative
canaries for provider continuations, memory, supervisor/TTS, sharing/export,
telemetry, persistence, display, direct mode, and remaining logs are still
required. These results describe the dirty isolated worktree only; they do not
establish deployment or Mac candidate acceptance.
