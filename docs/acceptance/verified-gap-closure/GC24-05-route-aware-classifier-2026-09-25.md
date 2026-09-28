# GC24-05 — Route-aware shared memory classifier

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree remains dirty.  
**State:** shared adapter implemented and tested in the isolated tree; live confidential route and durable admission stages remain open.

## Change

Production memory classification and synthetic provider-shadow evaluation now
use the same strict `ProviderClassifier` adapter through `jarvis.model_execution.execute_chat`.
It uses the selected resolved route, passes no Mortimer tools, requires a
nonempty response, caps output at 2,000 tokens, and accepts only the locked
`Classification.from_dict` schema and exact input key/order. A classifier
response cannot write to SQLite; the existing worker validates the complete
batch and stored evidence before applying metadata.

Live candidates are labeled `confidential`. The `memory_shadow` workload is a
separate approved-external route for the checked-in synthetic corpus only.
A test proves that an approved-external route is rejected before client
creation when asked to process confidential memory. The live adapter resolves
the configured memory workload and fails closed when model routing or an
adequate confidential route is unavailable; it does not fall back to the
heuristic and count that as a model success.

The periodic watcher and teardown drain run classification on a worker thread
with a worker-owned SQLite connection. The maintenance claim is committed
before provider execution, so no write transaction remains open during the
model call. Provider errors continue through the existing bounded retry path.
The synthetic runner now resolves the explicit `memory_shadow` workload and
uses the shared adapter; its dry-run path still does not read credentials or
call a provider. Model execution usage is recorded through the existing usage
ledger for production classification.

## Validation

- Full Python unit/integration suite: **2,836 passed, 4 skipped, 11 warnings,
  2 subtests passed** (`RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`).
- Memory, worker, policy and manifest tests: **258 passed**.
- Watcher, classifier and bot-wiring slice: **69 passed**.
- Ruff `F` and `I` checks on changed classifier/watcher/pipeline/runner/test
  files — passed.
- `python scripts/run_memory_provider_shadow.py --profile kimi-k3 --dry-run`
  selected the explicit Moonshot API profile, reported `provider_called: false`,
  and did not read credentials.
- `git diff --check` — passed.
- Unit adapter tests used a fake provider. No live model, vault, user-memory
  database, Mac runtime, or billable request was used.

## Remaining gates

This does not prove any live confidential route or SAYGM TEE claim. Current
configuration does not provide evidence that the production memory profile
resolves to a verified confidential route, so live provider classification
must remain fail-closed. The `memory_maintenance` queue also remains the
existing queue; the distinct additive admission-job, cursor/stage commit,
restart/idempotency/forget-race protocol required by the plan is not yet
implemented. Staged rollout and Mac observation remain disabled/open. See the
[current verified gaps plan](../../plans/MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md)
for the next GC24-05 steps.
