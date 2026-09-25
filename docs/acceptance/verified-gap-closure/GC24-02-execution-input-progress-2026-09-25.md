# GC24-02 — Execution input boundary progress

**Date:** 2026-09-25  
**Source baseline:** `4acb4dc2827f292f1236155e3c445d4ec4e9e5a0` (#90)
**State:** partial implementation; GC24-02 remains open.

## Implemented

`jarvis/model_execution.py` now:

- Preserves ordered typed system/user/assistant context messages and the
  legacy string-context form. Unsupported or mutable context fails closed.
- Accepts only bounded, normalized ephemeral attachments from the existing
  shared-content contract. It preserves text/image order, encodes images as
  data URLs, rejects duplicate IDs and checks the route's image capability.
- Combines request, context and attachment `DataPolicy` values with the
  existing strictest-policy rule before client construction. The output keeps
  the combined policy and existing task/parent/model/route/billing identity.
- Requires external attachments to carry approval bound to the resolved route
  and exact model identity; missing or mismatched approval fails before a
  client is created. Confidential/local sources remain restricted by policy.
- Rejects a resolved-workload mismatch, invalid task identity/deadline and
  malformed inputs before client construction.
- Applies an async request deadline. Timeout cancels the pending async call
  and returns no late result.
- Emits correlated `queued`, `started`, and terminal lifecycle events with a
  monotonic per-request sequence and inherited data policy. Timeout and caller
  cancellation produce distinct terminal events; provider exception details
  are not placed in events.
- Admits non-voice calls through a shared process controller: two total slots,
  at most one background slot, with waiting interactive work prioritized. The
  resolved route snapshots workload priority so later preference changes do
  not reclassify an in-flight request. The controller rejects a second event
  loop instead of silently splitting its process capacity limit.
- Accepts bounded output requirements and forwards a max-token limit only to
  adapters that can enforce it. Results carry token counts when the provider
  reports them; unavailable usage remains `null`, not zero.
- Accepts JSON-Schema-validated tool references from the trusted caller,
  forwards only those schemas, and rejects unrequested names, malformed
  arguments or arguments that fail the registered schema. It returns the
  provider call identity and arguments for the existing permission/sandbox
  owner; this module never invokes a tool. Tool lifecycle events expose only
  the tool name and call ID, not arguments.

At the `4acb4dc` source baseline, no production call site used
`ModelExecutionRequest`/`execute_chat`. Six background production call sites
now use the boundary when their existing route resolves: `kb_digest`,
procedure description, per-exchange extraction, whole-session memory fold-in,
capacity merge, and memory classification. Each retains its legacy direct-
client path while routing is disabled and its injected test seam. Four
production targets remain: delegated agent, planner, mixed voice/vision
pipeline, and council. The supervisor voice route is an explicit exception;
the offline evaluation helper is not a production caller.

## Validation and limitations

- `py_compile` passed for all changed source and test modules under isolated
  CPython 3.12.
- **254 focused pytest tests passed** across model execution, usage ledger,
  cost reporting, `kb_digest`, procedure description, memory extraction,
  whole-session memory fold-in, and memory sweep. The isolated venv received
  the pinned pytest/runtime packages needed for these tests; the complete
  `requirements-lock.txt` environment and full repository suite were not run.
- Twenty-two execution cases also passed earlier in a direct harness with
  stubbed pytest/YAML/JSON Schema. That harness is superseded by the real
  focused pytest result for the covered boundary cases.
- A real SQLite exercise verified unknown usage remains marked unknown with
  no computed zero cost, cache reads/writes split correctly, normalized
  execution metadata stores route/billing/duration/response ID, and the cost
  report groups subscription and API sources. This is a targeted database
  check, not the unit suite.
- All six migrated background call sites cross the boundary only when model
  routing is enabled and the resolved route passes the privacy gate. Legacy
  paths, injected test seams, existing prompt text/order, and current durable
  write/archive behavior remain in place. No route choices, feature flags, or
  tool execution policies changed.
- The static call-site audit reports 13/13 entries covered and zero
  review-required entries. This includes six migrated background calls, four
  remaining targets, the intentionally exempt supervisor voice path, one
  offline evaluation fixture, and the shared execution boundary itself.

The static inventory has 11 non-boundary production call sites: six migrated
background call sites, four remaining migration targets, and the supervisor's
intentional voice-path exception. The offline evaluation fixture and the
execution boundary itself account for the other two inventory entries. The
four remaining migration targets are the delegated agent, planner, mixed voice
and vision pipeline, and council.

## Still required for GC24-02

Still migrate the remaining four production targets; propagate
cancellation/timeout through their callers and prevent late UI/database writes;
add idempotent tool reconciliation; complete streaming progress/text/artifact
and tool-result events; and run focused and whole-project tests in the locked
isolated environment. GC24-03 remains a prerequisite for enabling a new route
with protected data.
