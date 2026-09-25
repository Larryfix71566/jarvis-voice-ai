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
`ModelExecutionRequest`/`execute_chat`. The `kb_digest` family now uses the
boundary whenever its existing background route resolves through model
routing. Procedure description, per-exchange extraction, and whole-session
memory fold-in also use the boundary when their background routes resolve.
All four retain their legacy direct-client paths while routing is disabled
and for their injected test seams. The other production call families have
not been migrated.

## Validation and limitations

- `py_compile` passed for the changed execution, routing, and test modules
  under the isolated CPython 3.12 environment.
- Twenty-two execution cases passed by direct invocation in an isolated
  harness. The harness supplied minimal pytest, YAML and JSON Schema stubs;
  therefore it does not validate compatibility with the actual locked
  `jsonschema` runtime and is **not** a pytest run. It does not substitute for
  the locked test environment.
- A real SQLite exercise verified unknown usage remains marked unknown with
  no computed zero cost, cache reads/writes split correctly, normalized
  execution metadata stores route/billing/duration/response ID, and the cost
  report groups subscription and API sources. This is a targeted database
  check, not the unit suite.
- Focused pytest files for the ledger and `kb_digest` migration were added but
  could not run here. This worktree's isolated Python lacks pytest, PyYAML,
  Pydantic and jsonschema; importing `jarvis.kb_digest` fails at the missing
  Pydantic dependency. Their files compile, but the production-call migration
  still needs the locked test environment before acceptance.
- A full offline sync of `requirements-lock.txt` could not complete because
  the cache lacks `torch==2.13.0`; installing the minimal test requirements
  offline also failed on uncached `Pygments` and PyYAML artifacts. No network
  dependency was fetched.
- One production family (`kb_digest`) now crosses the execution boundary only
  when the model-routing feature is enabled and the resolved route passes the
  privacy gate. The legacy path remains when routing is disabled. No provider
  route choices, runtime feature flags, prompts or tool execution policy were
  changed.
- A second family (`procedures_describe`) now crosses the same boundary under
  the resolved background route, with the existing JSON response parser and
  compatibility/test path retained. Source compiles; its focused pytest file
  cannot run because this environment lacks pytest and runtime dependencies.
  Nine of the 11 production call sites remained at this checkpoint.
- Per-exchange `memory_extraction` now crosses the boundary under its resolved
  memory route. The existing strict JSON parser and durable novelty-gated
  writes remain after a successful response. Source compiles; focused pytest
  cannot run because this environment lacks pytest and runtime dependencies.
  Eight of the 11 production call sites remained at this checkpoint.
- Whole-session `memory.update_memory_from_session` now crosses the same
  boundary behind its resolved memory route. Prompt selection (including the
  extraction-v2 kill switch), strict parser, and persistence behavior remain
  unchanged. Source compiles; focused pytest cannot run because this
  environment lacks pytest and runtime dependencies. Seven of the 11
  production call sites remained at this checkpoint.
- The capacity-enforcement `memory_merge` call now uses the shared boundary
  when the existing memory route resolves. Its prompt, output trimming,
  compatibility path, and reversible archive policy remain unchanged. Source
  compiles; focused pytest cannot run because this environment lacks pytest
  and runtime dependencies. Six of the 11 production call sites remain to
  migrate; supervisor voice traffic stays on its explicit legacy exception.

## Still required for GC24-02

Still migrate the remaining 6 production call sites/families; propagate
cancellation/timeout through their callers and prevent late UI/database writes;
add idempotent tool reconciliation; complete streaming progress/text/artifact
and tool-result events; and run focused and whole-project tests in the locked
isolated environment. GC24-03 remains a prerequisite for enabling a new route
with protected data.
