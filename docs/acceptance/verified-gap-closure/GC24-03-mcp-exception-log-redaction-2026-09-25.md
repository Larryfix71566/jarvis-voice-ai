# GC24-03 — MCP exception log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; shared working tree remains dirty.  
**State:** one exception-logging sink hardened and tested; GC24-03 remains open.

## Change

`SkillRegistry.call()` no longer writes raw MCP exception messages to the
application log. Its warning includes only the tool name, active run ID, and a
bounded exception-class code. The tool caller already receives only that
exception-class failure string, so this change preserves its result contract.

A canary test raises an exception containing `PRIVATE_CANARY_7fc19` and proves
that the captured log omits the message while retaining `RuntimeError` as the
error category.

## Validation

- Focused registry, run-log, SubAgent, and run-log integration tests:
  **104 passed**.
- Full Python unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,871 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on touched Python files — passed.
- `git diff --check` — passed.

This was an isolated dirty-tree test run. It used no provider, network, vault,
live database, installed Mac candidate, or production memory setting.

## Limits

This closes one raw-exception logging path only. It does not prove that MCP
tool-result bodies, provider errors, tool arguments, telemetry, provider
session state, direct/routed memory, supervisor/TTS, response rendering,
sharing, export, or durable writes obey their required policies. Continue the
complete GC24-03 source-to-sink inventory and negative canary suite.
