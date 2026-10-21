---
date: 2026-10-20
system: codex
rows: [WS-29]
prs: []
---

# WS-29 — Claude implementation-readiness review

Larry supplied Claude's review after the original constraint plan merged in PR #227 and asked that the accepted direction remain implementable after current acceptance testing. Codex checked each point against main `e52bdae289c76a477c23d911ecc8c889f3cdff7d` and amended the existing WS-29 plan rather than creating a second plan.

- Confirmed the prompt-budget collision: `AGENT_DISCIPLINE` is 546 characters against its 550-character cap, non-developer conversational prompts remain capped below 1,200 characters by `tests/unit/test_prompts.py`, and the nine policy rows contain 1,637 characters of current step text before wrappers or completion criteria. SC0 now requires a measured per-policy budget ledger and consolidation before any cap increase.
- Added a backstop column for all 23 definitions. The review's general concern was correct, but source inspection narrowed several examples: Tier-B `plan_path` and `ProgressWatcher` are partial backstops, while the legacy Git `prepare_commit` entry point is retired and returns `sandbox_required`. Prompt-only behavior is labeled as such and cannot be counted as mechanically enforced.
- Named the existing paired corpus: `tests/evals/voice_workflow_eval.py`, `tests/evals/voice_workflow_cases.yaml`, and `tests/fixtures/voice_failures.yaml`. The plan preserves `prior`, `require_tool`, `require_action`, and trigger coverage, and requires a bounded provider-route/data/call-count/spend approval record before either live baseline or candidate evaluation.
- Added request-start binding of the exact method body or digest as well as its revision/configuration, preventing event-time rereads from changing an in-flight request.
- Added Skills README checklist item 7 as an enable gate, with at least two positive and two negative `--explain` cases plus an all-enabled-package displacement matrix. AT-19 makes incumbent displacement and event-only leakage explicit acceptance failures under `MAX_INJECTED = 1`.
- Changed the first pilot from the machinery-heavy planning path to the leaf `diagnose-before-proposing` method. Planning consolidation follows only after that seam passes; retirement moves to SC7.

This slice changes documentation only. It makes no provider calls, enables no skills or workflows, changes no prompt/runtime/configuration, and closes no acceptance gate. The existing acceptance-first start gate remains authoritative.

Validation at preparation: `git diff --check`; all 23 disposition rows remain present; SC0–SC7 and AT-01–AT-19 are present; relative links resolve; and `python3 scripts/check_roadmap.py` retains the one pre-existing WS-17 stale-review finding for merged PR #226 with no WS-29 error. Runtime and live-model tests were not run for this documentation-only amendment.
