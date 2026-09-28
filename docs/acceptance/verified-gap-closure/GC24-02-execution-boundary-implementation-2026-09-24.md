# GC24-02 — Execution boundary implementation progress

**Date:** 2026-09-24  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree is dirty.  
**State:** implementation progress; GC24-02 remains open.

## Implemented in this isolated tree

- Routed callers include the memory/digest/procedure families, delegated-agent tool loop, council proposer/judge/planning/shadow calls, and upgrade planner. Routing-disabled compatibility paths and the explicit voice-supervisor exception remain.
- Planner cancellation now returns its structured cancellation result. If cancellation races successful provider completion, it prevents usage/result recording and prevents returned tool calls from reaching the sandbox executor.
- Tool history rejects duplicate call IDs even when an earlier result already closed the call, and rejects a provider response that reuses a tool-call ID from request history. These checks fail closed before transmission for malformed input or before any tool caller receives the response. This is request-history replay protection, not durable recovery after a process crash.
- The execution boundary emits ordered, policy-carrying `progress` events for `provider_request` and `response_received`; event sink errors remain isolated from execution. These contain no text or provider payload.
- Delivery of `queued` is inside the deadline/cancellation guard. A regression
  test cancels an async observer while it handles `queued` and proves the
  request emits exactly one subsequent `cancelled` terminal event with
  monotonic sequence numbers.
- **2026-09-25 follow-up:** opt-in token streaming now crosses the shared
  execution boundary. `stream_text=True` is accepted only for a route that
  explicitly advertises `streaming`; only the three direct Anthropic profiles
  set that capability in `config/upgrade_models.yaml`. The native Anthropic
  shim translates `messages.stream()` text/tool-input events into the existing
  OpenAI-shaped chunk contract. The boundary emits policy-labeled text deltas,
  aggregates text/usage and tool-call fragments for its compatibility result,
  validates complete tool calls only after a finish marker, and closes the
  stream on normal completion, malformed/incomplete output, deadline or
  cancellation. SAYGM, subscription, local and other unverified profiles do
  not gain streaming capability by default.
- Shared-content vision and production screen analysis use the provider-neutral execution boundary. Image approval binds to the selected route/model; normalized source identity, policy, and size limits are retained. Screen capture guards, temporary-file cleanup, and the screen-off kill switch remain.
- Shared-content routing is resolved for each offer rather than only at connection setup. The exact server-side route snapshot is keyed to that offer's batch ID, disclosed before consent, and reused at execution; cancellation and completion discard the snapshot. A preference change during a connected session applies to the next offer, while an approved batch remains bound to the route that was disclosed.
- Shared-content cancellation cancels its active provider task and returns a cancellation status. Route/profile disclosure shows the selected model, route, and billing source.
- Call-site audit v2 classifies 25 entries (13 provider adapters and 12 shared-boundary callers) with zero review-required entries.

## Validation on this snapshot

- `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q` — **2,813 passed, 4 skipped, 11 warnings, 2 subtests passed** on the current tree.
- `RUN_LIVE=0 .venv/bin/python -m pytest tests/evals/sub_agent_evals.py -q` — **13 passed**.
- `.venv/bin/python scripts/audit_model_call_sites.py --require-covered` — **25 entries; 0 review-required**. Use the isolated `.venv` interpreter; the host script shebang selected an incompatible interpreter and gave a false parse error for `jarvis/bot/bot.py`.
- `.venv/bin/python scripts/latency_probe.py --budget tests/fixtures/latency_sample.log` — passed; non-delegated p50 1,153 ms, delegated p50 1,412 ms, overall p90 1,353 ms.
- Focused planner cancellation suite — **46 passed**; focused boundary/shared-content/vision set — **95 passed**; bot wiring — **32 passed**; combined screen/shared-content/bot-wiring — **80 passed**; environment/snapshot checks — **41 passed**; route-per-offer, shared-content, bot-wiring, and global-name checks — **168 passed**.
- GC24-03 sensitive routed-SubAgent privacy checks: **72 passed** across SubAgent, agent-event, and privacy-policy suites. See the [GC24-03 progress receipt](GC24-03-sensitive-routed-subagent-2026-09-24.md).
- Focused execution/shared-content/wiring regression — **78 passed**; planner cancellation suite — **46 passed**; SubAgent evaluation — **13 passed**. Ruff import sorting, Python compilation, `git diff --check`, and the seven plan-manifest checks passed on the final edited files.
- Follow-up for queued-observer cancellation:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit/test_model_execution.py -q`
  — **30 passed**.
- Boundary/caller integration regression:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit/test_model_execution.py tests/unit/test_subagent.py tests/unit/test_upgrade_agent.py tests/integration/test_planning_council.py -q`
  — **148 passed**. After lint cleanup, the focused boundary suite reran at
  **30 passed**; `.venv/bin/ruff check jarvis/model_execution.py tests/unit/test_model_execution.py`
  and `git diff --check` pass.
- Streaming implementation regression:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit/test_model_execution.py tests/unit/test_anthropic_shim.py tests/unit/test_model_routing.py -q`
  — **126 passed** (rerun 2026-09-25 after the event-sink policy guard). The broader boundary/caller regression passed **239
  tests**. The final full Python unit/integration run after all streaming
  changes and tests passed **2,829 tests, 4 skipped, 11 warnings and 2
  subtests**.
  Ruff passes on all six changed Python source/test files; `git diff --check`
  passes.
- **2026-09-25 final validation refresh:**
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q`
  — **2,829 passed, 4 skipped, 11 warnings, 2 subtests passed**;
  the focused execution/Anthropic-shim/routing set — **126 passed**;
  targeted Ruff — passed; `git diff --check` — passed. These checks validate
  the current isolated source snapshot only; they do not close production
  event consumption or live candidate acceptance.
- SDK API shape checked against the installed lock versions and official
  examples: [Anthropic Python SDK streaming example](https://github.com/anthropics/anthropic-sdk-python/blob/main/examples/messages_stream.py)
  and [OpenAI Python SDK streaming example](https://github.com/openai/openai-python/blob/main/examples/streaming.py).

## Remaining limits

- Per-offer route selection has unit-level coverage, but has not yet been exercised with a live connected Mac session and a preference change between two offers.
- GC24-02 remains open: no production caller currently requests
  `stream_text=True`, and UI/result consumers are not wired to these deltas;
  artifacts and tool-result events across whole caller/tool loops remain
  unimplemented; exactly-once terminal ownership across the complete tool loop,
  late UI/database-write suppression, and durable tool-result reconciliation
  across task/process recovery remain open. Stream/tool output here is
  synthetic-test evidence only. The queued observer test closes only the
  pre-start cancellation hole; the call-ID guard prevents reuse within a
  validated history/response but not crash recovery.
- The static audit is coverage evidence, not proof that enabled routing has been accepted on the Mac. No merge, deployment, live-provider run, or physical-device acceptance is claimed here.
- GC24-03 end-to-end policy checks at every transmission/result sink, provider subscription/SAYGM capability gates, automated-memory production admission, Atlas freshness, exact-candidate build, Mac journeys, pilots, rollback, and release remain open under their respective requirements.

## Next action

Exercise per-offer vision routing on the Mac, then finish shared lifecycle/cancellation/reconciliation semantics. Update the authoritative status and rerun affected tests and audits. Do not enable protected-content routes until GC24-03 negative sink canaries pass.
