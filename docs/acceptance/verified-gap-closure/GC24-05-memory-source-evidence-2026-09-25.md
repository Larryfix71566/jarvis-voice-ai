# GC24-05 — Verify classifier evidence against stored user turns

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree is dirty.  
**State:** bounded GC24-05 policy fix implemented and tested; production model-backed admission remains open.

## Gap addressed

The classifier worker accepted evidence IDs directly from model output, even
when those IDs were not among the candidate's source turns. It also used
recall-ledger rows without distinguishing a repeated user statement from a
memory merely inserted into a prompt. This could falsely promote a candidate
as explicit or independently corroborated. In addition, a provider response
could label a tool-originated candidate as user-authored.

The worker now builds candidate evidence by resolving stored source IDs to
actual `conversations` rows whose role is `user`. Recall entries contribute
evidence only for `exact_update` and `near_duplicate`, never `used_for`.
Provider evidence must be unique and a subset of those verified IDs; invalid
or fabricated citations fail the batch and enter the existing bounded retry
path. Corroborated classifications need at least two cited user turns from
two distinct stored sessions; otherwise they are reduced to tentative and
cannot pass the corroborated rollout stage. Assistant, tool, and quoted
document provenance cannot be upgraded by classifier output.

Per-exchange extraction now persists the originating user-turn ID on new or
updated facts. If another admission path changes fact content without
providing a new source ID, the previous source ID is cleared so stale evidence
cannot be attributed to changed content. Explicit heuristic classifications
now use the B7 confidence floor of `1.0`.

No candidate text was added to the shadow ledger. No rollout stage, provider,
database, voice path, or user-facing behavior was enabled or changed.

## Validation

- Memory-focused regression set (all eleven `test_*memory*` unit modules):
  **267 passed** before the final evidence-specific cases were added.
- Final focused memory automation/extraction set:
  **89 passed**.
- Complete Python unit and integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q`
  — **2,833 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F` and import-order (`I`) checks on changed Python files — passed.
  The repository-wide rules selected for these legacy memory modules report
  existing style/deprecation debt outside this change; no broad reformat was
  applied.
- `git diff --check` — passed.

## Still open

This does not connect a model-backed classifier to the production watcher or
make the provider shadow runner use that same production adapter. It does not
prove semantic evidence entailment beyond the verified source-turn mapping,
add durable staged admission jobs, or complete B5/B9 rollout and Mac
observation. Production automation remains fail-closed until those gates are
complete. No live database or provider was used.

**Next action:** add the single route-aware classifier adapter on the existing
shared execution boundary and use it from both production classification and
synthetic shadow evaluation. Keep the worker off the voice event loop, use the
existing memory workload and privacy policy, and retain shadow-only behavior
until its acceptance gates pass.
