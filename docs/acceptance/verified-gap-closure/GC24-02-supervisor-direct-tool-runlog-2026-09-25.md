# GC24-02 receipt: direct Supervisor tool run logging

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base/source revision:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` plus the dirty isolated working-tree changes present during this run  
**Scope:** add per-invocation durable run identity, call correlation, redacted outcomes, and cancellation/unknown-outcome recording to the live Pipecat Supervisor direct-tool adapter.

## Change

The module-level `adapt_to_pipecat` adapter now creates one `RunLogger` for a
direct Supervisor tool invocation, carries Pipecat's `tool_call_id` into the
tool-call and tool-result events, and enters the existing logger context while
the handler runs so nested MCP calls share the same run. Supervisor calls are
marked sensitive, so arguments and returned content are not persisted. A
normal return is classified and durably recorded before the Pipecat result
callback is invoked. Cancellation or an exception after dispatch records a
metadata-only unknown outcome; cancellation is re-raised and no late result
callback is sent. Logging follows the existing setting and defaults off for
lightweight/older settings objects that do not define that field.

The adapter preserves existing tool registration names, handler arguments,
result callback behavior, and permission/action execution. It does not add an
execution path, make actions idempotent, or determine whether a cancelled
mutation committed.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_supervisor_tool_registration.py tests/unit/test_subagent.py tests/unit/test_runlog_store.py tests/unit/test_mcp_runlog_logic.py -q --tb=short` — **116 passed**, 2 warnings.
- `.venv/bin/python -m pytest tests/unit/test_supervisor_tool_registration.py tests/unit/test_speaker_gate.py tests/integration/test_bot_wiring.py -q --tb=short` — **73 passed**, 2 warnings.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **2,923 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `.venv/bin/ruff check --select F,I jarvis/bot/pipeline.py tests/unit/test_supervisor_tool_registration.py` — passed.
- `git diff --check -- jarvis/bot/pipeline.py tests/unit/test_supervisor_tool_registration.py` — passed.

Persistence tests read the actual SQLite and JSONL run record. They verify call
ID correlation; shared context for a nested MCP event; sensitive argument,
result, and exception-text redaction; unknown outcome on exception and on
cancellation (including a handler that catches cancellation and returns); no
result callback after cancellation; and normal tool behavior with logging
disabled.

## Remaining gates

- Action-specific reconciliation across a new provider call ID remains open;
  an unknown record is an operator signal, not idempotency or proof of the
  external side effect's state.
- Other provider/tool caller families still need lifecycle, cancellation,
  terminal-owner, and downstream late-write coverage.
- Live candidate voice-to-result-pane and physical Mac acceptance remain
  unverified. This is source/test evidence only; it does not establish merge,
  deployment, or release acceptance.
