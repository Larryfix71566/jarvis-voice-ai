# GC24-03 receipt — procedures, skills, usage, and shared-content log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD at start:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** verified in the dirty isolated tree; pre-existing shared-content
and test work was preserved.

## Change

Procedure match/learn/usage failures now log only the event and bounded
exception class; raw agent, task, run, procedure IDs, exception text, and
tracebacks are omitted. Skill config and parsing diagnostics no longer log
local paths, YAML/parser messages, frontmatter values, skill names, or script
paths; invalid-skill diagnostics retain only a problem count. TTS/LLM usage
and shared-content usage-persistence catches log bounded exception classes
without session IDs, usage data, provider messages, or tracebacks.

All catches retain their prior best-effort behavior. The shared-content
analysis answer remains returned to its existing caller if usage recording
fails; usage accounting semantics are unchanged.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_procedures.py tests/unit/test_agent_skills.py tests/unit/test_usage_watcher.py tests/unit/test_shared_content.py --tb=short`
  — **131 passed, 1 existing dependency deprecation warning**.
- `./.venv/bin/ruff check --select F,I jarvis/procedures.py jarvis/agent_skills.py jarvis/bot/usage_watcher.py jarvis/bot/shared_content.py tests/unit/test_procedures.py tests/unit/test_agent_skills.py tests/unit/test_usage_watcher.py tests/unit/test_shared_content.py`
  — passed.
- `./.venv/bin/python -m compileall -q jarvis/procedures.py jarvis/agent_skills.py jarvis/bot/usage_watcher.py jarvis/bot/shared_content.py tests/unit/test_procedures.py tests/unit/test_agent_skills.py tests/unit/test_usage_watcher.py tests/unit/test_shared_content.py`
  — passed.
- `git diff --check` — passed.
- Canary tests cover procedure task/run/ID failures, invalid skill config and
  frontmatter, TTS/LLM usage failures, and shared-content usage persistence.

## Still open

This receipt closes only the listed Python logging paths. It does not prove
privacy of procedure/skill content injected into prompts or provider/model
data flow. The repository-wide residual scan found additional key-health,
MCP vault, MCP registry, config-bridge, workflow-path, and console-validation
logs; those are tracked as slice F in the
[remaining exception-log redaction plan](../../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md).
The complete GC24-03 source-to-sink audit remains open.
