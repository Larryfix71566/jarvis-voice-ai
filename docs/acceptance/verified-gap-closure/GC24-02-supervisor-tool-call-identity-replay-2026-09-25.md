# GC24-02 — Supervisor tool-call identity replay guard

**Status:** Implemented and tested in the isolated worktree; not merged,
deployed, or live-voice accepted.

**Worktree:** `codex/isolated-20260924`  
**Base/current HEAD:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Changed source/tests:** `jarvis/agents/supervisor.py`,
`tests/unit/test_orchestrator.py`

## Change

The live Supervisor loop now validates every provider tool-call ID across the
whole response batch before dispatching any member. Missing, empty, oversized,
reused-across-rounds, or duplicate-within-batch IDs fail the turn closed using
the existing bounded `STUCK_MESSAGE`. The invalid assistant tool-call message
is not appended to conversation history, and no call from an invalid batch is
executed. Logs include only a fixed reason code, never the provider ID or
arguments. Valid calls continue through their existing direct or delegated
handler, preserving voice behavior and tool ownership.

This is request-turn replay prevention only. It does not provide durable
cross-process mutation receipts, identify semantic duplicate actions issued
with a new provider ID, roll back an action already completed, or close the
remaining cancellation/late-write lifecycle gaps.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_orchestrator.py tests/unit/test_supervisor_tool_registration.py -q --tb=short` — **36 passed**, 2 warnings.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **2,894 passed, 4 skipped, 11 warnings, 2 subtests**.
- `.venv/bin/ruff check --select F,I jarvis/agents/supervisor.py tests/unit/test_orchestrator.py` — passed.
- `git diff --check` — passed.

Regression tests cover repeated IDs across provider rounds, empty IDs, and a
duplicate-ID batch. The batch test verifies no partial dispatch occurs.

## Remaining GC24-02 work

Production text-delta consumption, complete terminal/tool/artifact ownership
across caller loops, downstream cancellation and late-write suppression,
durable unknown-mutation reconciliation, and further caller coverage remain
open. This receipt closes only the Supervisor's same-turn provider tool-call
identity replay gap.
