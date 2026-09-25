# GC24-00 — Main refresh after PR #90

**Recorded:** 2026-09-25  
**Purpose:** Update the source baseline for the verified gap-closure plan after
the selected orb-shell change merged concurrently. This is a repository
inspection receipt, not a live Mac or runtime acceptance receipt.

## Source identity

- Main commit inspected: `4acb4dc2827f292f1236155e3c445d4ec4e9e5a0`
  (`Replace the orb's glass shell with the crystal design`, PR #90).
- The isolated Codex branch is `codex/isolated-20260924`, at
  `a1c0cef` when this refresh was recorded, two local documentation commits
  ahead and one commit behind its then-known `origin/main`.
- The isolated worktree also contains uncommitted GC24-02 executor changes and
  documentation. Those edits are not in `4acb4dc` and are not part of this
  main-source inventory.
- PR #90 touches orb visuals, native tests, and the orb acceptance/plan
  documents. It does not change `jarvis/model_execution.py`,
  `tests/unit/test_model_execution.py`, model routing, memory admission, or
  Atlas lifecycle sources.

## Verified change and preserved design

PR #90 implements the selected Crystal option A shell and records acceptance
of the updated appearance. It replaces the earlier translucent blue shell
with the paired-pane crystal treatment, strip light, dark wall line, speaker
colored wall glow and visible standby shell. It retains the established
atom/comet, speaker distinction, connected-idle behavior and compact layout
contracts. The closure plan treats the renderer as accepted design and does
not authorize another orb redesign.

The merge commit reports MortimerHost **258 executed, 3 skipped, 0 failures**;
JarvisKit **199 passed, 0 failures**; Crystal p95 **13.59 ms at 1440×220**.
These are results reported by the merge commit, not test runs performed in
this worktree. No Python suite result was reported by this commit.

## Still unverified

- The installed/running app path, bundle hash, backend process revision and
  effective runtime gates were not inspected. The current app must not be
  inferred from the repository HEAD.
- Placement, Reduce Motion behavior and rollback are still open in the Crystal
  acceptance record.
- Main advanced after this worktree's prior baseline. Re-read `origin/main`
  before rebasing or creating a PR; do not reset or write to shared branches.
- Missing physical hardware/provider observations remain acceptance blockers;
  they do not block independent source implementation.

## Next action

Proceed with GC24-02's shared execution contract after reviewing any newly
arrived source diff. Do not edit the Crystal renderer as part of gap closure.
GC24-00 remains open until the exact candidate runtime and effective settings
are recorded; the source refresh alone does not close it.
