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
  not reclassify an in-flight request.

The repository search at the source baseline found no production call site for
`ModelExecutionRequest`/`execute_chat`; this code currently fixes the boundary
contract only. It does not yet put existing direct-API model traffic through
this boundary.

## Validation and limitations

- `py_compile` passed for the changed execution, routing, and test modules
  under the isolated CPython 3.12 environment.
- Fifteen execution cases passed by direct invocation in an isolated harness. The
  harness supplied the minimal `pytest.mark.asyncio`/`pytest.raises` behavior
  and an unused YAML-import stub because this environment's package cache lacks
  PyYAML, pytest's Pygments dependency and the locked PyTorch wheel. This is
  **not** a pytest run and does not substitute for running the test file with
  the locked project environment.
- A full offline sync of `requirements-lock.txt` could not complete because
  the cache lacks `torch==2.13.0`; installing the minimal test requirements
  offline also failed on uncached `Pygments` and PyYAML artifacts. No network
  dependency was fetched.
- No production call sites, prompts, tool loops, route choices or runtime
  settings changed. Context was not yet migrated through the boundary.

## Still required for GC24-02

Still add typed tool references/output requirements; connect the executor to
production call sites; propagate cancellation/timeout through callers and
prevent late UI/database writes; add idempotent tool reconciliation; and run
focused and whole-project tests in the locked isolated environment. Lifecycle
events currently report request start and terminal outcome, not streamed text,
progress, tool events or artifacts. GC24-03 remains a prerequisite for
enabling a new route with protected data.
