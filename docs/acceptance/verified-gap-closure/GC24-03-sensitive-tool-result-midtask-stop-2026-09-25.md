# GC24-03 — Stop external continuations after a sensitive tool result

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/current source:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` plus dirty isolated-tree changes. This is not a commit, merge, candidate, or release receipt.

## Gap and change

An otherwise public SubAgent or voice-Supervisor task could read a local tool
result containing a recognized financial detail, then place that detail into
the next external provider request. SubAgents now scan tool arguments/results
with the existing `arm_from_text` detector. Once a result arms the turn, the
SubAgent stops before a non-confidential provider continuation, upgrades its
run logger to redact later payloads, and emits only allow-listed activity
metadata. The live Supervisor stops before a subsequent voice-model request
and removes that tool round's arguments/results from retained history.

The voice Supervisor is still the documented voice-provider exception for
its initial request; this change does not claim the whole voice conversation
is local or private. Detection is limited to the existing financial-detail
patterns. It is not a general-purpose classifier for every private, medical,
identity, or proprietary string. Those sources and route rules remain open
under GC24-03/04.

## Verification

- Focused SubAgent, Supervisor, and run-log tests:
  `./.venv/bin/python -m pytest tests/unit/test_subagent.py tests/unit/test_orchestrator.py tests/unit/test_runlog_store.py -q --tb=short`
  — **127 passed**.
- Full Python unit/integration suite:
  `./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,943 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on changed Python files and `git diff --check` pass.

## Limits and next work

This prevents the tested financial-detail canaries from entering a later
SubAgent provider request and prevents their raw tool round from remaining in
Supervisor history. It does not prove all sensitive source types, every
provider-specific continuation, memory or UI/export sinks, or live voice
behavior. Complete the full source-to-sink inventory and expand canaries
without weakening the existing voice exception or privacy thresholds.
