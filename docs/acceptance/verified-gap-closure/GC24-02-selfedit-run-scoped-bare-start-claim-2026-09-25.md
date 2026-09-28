# GC24-02 receipt — run-scoped claim for bare self-edit start

**Date:** 2026-09-25  
**Scope:** deprecated bare-goal `/api/selfedit/run` calls made through the
MCP SubAgent registry with its injected owner `run_id`.  
**Status:** isolated source and focused tests verified; not a candidate,
deployment, or release acceptance.

## Contract basis

`MORTIMER_GRAPH_LAYER_PLAN.md` GL9 defines the registry behavior: for
`selfedit_start`, `plan_start`, and `app_build_start`, `SkillRegistry.call()`
injects the current SubAgent `RunLogger.run_id` and removes the field from the
model-visible schema. The run ID is therefore the owning execution identity
for this trusted MCP caller. Existing plan and app-build start claims already
use that same run-scoped identity pattern. This receipt does not reinterpret
an arbitrary user-supplied goal, provider call ID, or argument hash as an
action identity.

## Change and boundaries

- The bare legacy route uses the injected `run_id` as its claim key in the
  separate `mcp-selfedit.run_start` scope. Staged preview IDs continue using
  `mcp-selfedit.staged_start`; the two identity classes cannot collide by
  scope.
- The claim is made before authoring-session or upgrade-worker dispatch.
  Replays return `started: false` and do not launch another operation.
- Status lookup checks the live job/opening owner, then the appropriate
  durable claim scope after the in-memory slot has moved.
- Calls that arrive without a registry-injected `run_id` preserve legacy
  behavior and remain unclaimed. Direct use of the bare endpoint therefore
  does not gain a global exactly-once guarantee.
- This local claim prevents duplicate dispatch for one owner ID; it cannot
  reverse an external side effect already committed by a dispatched tool.

## Verification

Focused command:

```text
./.venv/bin/pytest -q tests/unit/test_admin_selfedit.py tests/integration/test_selfedit_end_to_end.py tests/unit/test_mcp_selfedit_logic.py tests/unit/test_run_id_injection.py
```

Result: **157 passed**, one existing Starlette/httpx deprecation warning.
The end-to-end fixture now polls the existing asynchronous opening status
when VM setup returns `opening`, rather than assuming setup finishes within a
fixed short join interval.

## Still open

This closes only injected-run-ID legacy self-edit starts. Bare calls without
that ID and other mutating caller families remain open. Full provider/tool
loop terminal ownership, downstream cancellation and late-write suppression,
and live candidate voice-to-result acceptance remain separate GC24-02 gates.
