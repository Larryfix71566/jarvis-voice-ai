# GC24-02 — Execution input boundary progress

**Date:** 2026-09-25  
**Source baseline:** `4acb4dc2827f292f1236155e3c445d4ec4e9e5a0` (#90)
**State:** partial implementation; GC24-02 remains open.

> Historical worktree snapshot. The current caller-migration and validation state is recorded in the [GC24-02 implementation receipt](GC24-02-execution-boundary-implementation-2026-09-24.md); this receipt remains for provenance only.

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
  thread-safe process counters are shared by async callers and synchronous
  workers using different event loops, so one caller cannot create a second
  capacity pool. The resolved route snapshots workload priority so later
  preference changes do not reclassify an in-flight request.
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
`ModelExecutionRequest`/`execute_chat`. Eight production call sites now use
the boundary when their existing route resolves: `kb_digest`, procedure
description, per-exchange extraction, whole-session memory fold-in, capacity
merge, memory classification, delegated-agent tool loop, and council
proposer/judge/planning/shadow calls. Each retains its legacy path while
routing is disabled. Two targets remain: planner and mixed voice/vision
pipeline. The supervisor voice route is an explicit exception; the offline
evaluation helper is not a production caller.

## Validation and limitations

- The isolated venv was synced from `requirements-lock.txt`.
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q`:
  **2,801 passed, 4 skipped, 11 warnings, and 2 subtests passed**. The four
  skips remain skips, not Mac display acceptance.
- `RUN_LIVE=0 .venv/bin/python -m pytest tests/evals/sub_agent_evals.py -q`:
  **13 passed**. `scripts/latency_probe.py --budget
  tests/fixtures/latency_sample.log`: all existing p50/p90 thresholds passed
  (non-delegated p50 1,153 ms; delegated p50 1,412 ms; overall p90 1,353 ms).
- `py_compile` passed for the changed execution-boundary, SubAgent, council,
  and test modules under isolated CPython 3.12.
- Twenty-two execution cases also passed earlier in a direct harness with
  stubbed pytest/YAML/JSON Schema. That harness is superseded by the real
  focused pytest result for the covered boundary cases.
- The delegated-agent loop carries ordered system/user/assistant messages,
  assistant tool-call requests, tool results, raw argument serialization, and
  bounded provider metadata (including `thought_signature`) through typed
  context records. The existing registry remains the sole tool source and
  executor; request schemas are validated before provider calls. Anthropic
  effort remains limited to the existing approved output-effort parameter.
- A real SQLite exercise verified unknown usage remains marked unknown with
  no computed zero cost, cache reads/writes split correctly, normalized
  execution metadata stores route/billing/duration/response ID, and the cost
  report groups subscription and API sources. This is a targeted database
  check, not the unit suite.
- All eight migrated call sites cross the boundary only when model routing is
  enabled and the resolved route passes the privacy gate. Legacy paths,
  injected test seams, existing prompt text/order, and current durable
  write/archive behavior remain in place. No route choices, feature flags, or
  tool execution policies changed.
- The static call-site audit reports 13/13 entries covered and zero
  review-required entries. This includes eight migrated calls, two
  remaining targets, the intentionally exempt supervisor voice path, one
  offline evaluation fixture, and the shared execution boundary itself.

The static inventory has 11 non-boundary production call sites: eight
migrated call sites, two remaining migration targets, and the supervisor's
intentional voice-path exception. The offline evaluation fixture and the
execution boundary itself account for the other two inventory entries. The
remaining targets are planner and mixed voice/vision pipeline.

## Additional isolated-worktree progress

The delegated-agent loop now preserves ordered assistant tool-call messages,
tool results, raw JSON argument serialization, and bounded provider metadata
through the typed boundary records. Registered tool schemas are validated
before the provider call; actual invocation remains with the existing
registry. Focused SubAgent and execution-boundary suites pass (76 tests).

Council proposer, judge, planning, and shadow calls now cross the same
execution boundary when model routing is enabled; the disabled-routing path
retains the existing synchronous adapter. Routed council calls preserve
system/user message order, configured temperature, the established profile
timeout floor, approved Anthropic effort settings, policy, usage, and billing
metadata. Focused boundary and council suites pass (112 tests). The shared
static audit reports 13/13 covered with zero review-required entries.

Accordingly, eight production sites now use the boundary under the routing
gate. Planner and mixed voice/vision remain the two caller migration targets;
the supervisor remains the explicit voice-path exception. These are
isolated-worktree changes. Full locked unit/integration and sub-agent
evaluation suites pass for this tree, but merge, deployment, and enabled-mode
Mac acceptance remain open. Streaming lifecycle events, downstream
cancellation, late-write prevention, and idempotent tool reconciliation
remain open.

## Still required for GC24-02

Still migrate the planner and mixed voice/vision targets; propagate
cancellation/timeout through their callers and prevent late UI/database writes;
add idempotent tool reconciliation; complete streaming progress/text/artifact
and tool-result events. GC24-03 remains a prerequisite for enabling a new
route with protected data.
