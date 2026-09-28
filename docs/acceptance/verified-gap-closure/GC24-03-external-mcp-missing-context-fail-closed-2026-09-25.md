# GC24-03 — External MCP fails closed without sensitivity context

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/current source:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` plus dirty isolated-tree changes. This is not a commit, merge, candidate, or release receipt.

## Gap and change

`SensitiveTurn.is_sensitive()` already treats an unset `current_sensitive_turn`
as sensitive, but `SkillRegistry.call` previously checked the mutable holder
directly and allowed external MCP servers when it was absent. The registry
now uses the single fail-closed policy function. External MCP calls are
blocked before the child session receives arguments when sensitivity context
is missing or explicitly armed. An explicitly initialized, unarmed turn can
still call the external server. Local-only tools retain their existing path.

The run-ID-injection tests now establish an explicit unarmed context when
they intend to test external self-edit tool delivery; this matches production
session initialization instead of relying on an unset context.

## Verification

- Focused registry, SubAgent, and Supervisor tool suites:
  `./.venv/bin/python -m pytest tests/unit/test_registry.py tests/unit/test_subagent.py tests/unit/test_supervisor_tool_registration.py -q --tb=short`
  — **92 passed, 2 warnings**.
- Full Python unit/integration suite:
  `./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,940 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on changed Python files and `git diff --check` pass.

## Limits and next work

This proves only the registry boundary for the four external MCP servers.
It does not complete source-to-sink coverage for direct provider calls,
continuations, memory, supervisor/TTS, provider-session persistence,
protected result sharing/export, telemetry, or all direct-mode paths. The
global GC24-03 phase remains open; exact confidential-route eligibility is
also still unproven under GC24-04.
