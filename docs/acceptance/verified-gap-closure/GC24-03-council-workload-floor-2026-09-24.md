# GC24-03 — Council workload privacy floor and early-exit redaction

**Date:** 2026-09-24  
**Branch:** `codex/isolated-20260924`  
**Source:** `977f50b` plus the uncommitted isolated worktree changes.  
**State:** verified implementation slice; GC24-03 remains open.

## Gap closed by this slice

Council and planning previously treated request-level `data_policy` as
optional. Without that field, durable council records could lack the
configured workload privacy floor. The policy resolver now reads the static
workload policy without applying route preferences, then combines it with a
caller-supplied policy using the existing strictest-policy rule. An explicit
less restrictive request label cannot weaken the configured floor.

The effective policy reaches proposer, judge, planning, and shadow model
continuations and the council persistence helpers. Every `_finalize_too_small`
path now carries the same policy into the round row, covering exits before or
after provider fan-out. Protected goals and reasons are redacted on those
paths as well. No provider fallback or model substitution was added.

## Validation

- Focused council/planning/CLI suites: **78 passed**.
- `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q`:
  **2,816 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `scripts/audit_model_call_sites.py --require-covered`: **25 entries,
  0 review-required**, secret-free.
- `PYTHONPATH=. .venv/bin/python tests/evals/sub_agent_evals.py`: exited 0.
- `tests/unit/test_plan_manifests.py`: **7 passed**; Ruff import sorting and
  `git diff --check`: passed.
- The new negative tests prove that configured protected council policy
  rejects an `approved_external` route before provider-client construction,
  that an explicit weaker request label cannot lower the workload floor, and
  that a protected planning goal is redacted from the SQLite too-small row.
- `git diff --check`: passed.

## Limits and next action

This closes only the council workload-policy and early-exit persistence slice.
The end-to-end GC24-03 source/sink inventory and negative canaries for memory,
attachments, tools, supervisor context, TTS, response sharing, exports,
usage/run logs, provider-session persistence, and direct/routing-disabled
callers remain open. The test run is against a dirty isolated source tree; it
does not prove merge, Mac deployment, provider capability, or live acceptance.
