---
date: 2026-11-10
system: codex
rows: [WS-28]
prs: [295]
---

# WS-28: post-merge prune operator-report cross-review

Session reference: Codex 2026-11-10, branch `codex/ws28-ws32-cross-review-20261110`.
Reviewed merge: `4f2bc8337424ec397848b0e0d97821f1080527f5` (#295), against first parent
`2f2de4feb7ad5b4e4e826ccc84d2d01076ec3798`.
Tested main: `837bb041eaa1bb0b4ed476a859c266fd42f2fcdb`.
Verdict: **APPROVE** within the operator-report scope. Blocker: none. Should-fix: none. Nit: none.

## Source and scope

Read the complete `git diff 4f2bc83^1 4f2bc83 -- sandbox/`, the prior
2026-10-22 Claude cross-review, and the unchanged planning, deletion guard,
retention and issue accumulation paths. The only changed class method is
`Pruner.run`; its additions expose the existing retained entries in a separate
list. `main()` changes reporting and status. Eligibility, locks, leases,
corruption policy, `discard`, `reclaim`, `require_headroom`, and fingerprint
input selection are unchanged. `kept` retains its old entries and meaning:
retained entries plus planned deletions in dry runs, retained entries in real runs.
The entire sandbox tree is `e493cb466a7a4958a33c171a55ce7b2f70672d7a`
at both the merge and tested main.

At `sandbox/prune.py:327-358`, dry-run equality-based subtraction excludes all
copies of retained entries, not just the first. Planned entries and retained
entries have different reasons, and the actual planner keys records by task.
A synthetic report with `kept=[retained, retained, planned, planned]` and
`retained=[retained, retained]` prints exactly two planned lines and no retained
VM as would-delete. Additional fake-report cases checked clean exit 0,
issues-only exit 3, and failed-plus-issues exit 1: **3/3 passed**. No controller
operation ran in these supplemental checks.

Real-run regression uses fake Tart and a temporary home: a verification VM is
deleted, a development VM is retained, and the malformed session is reported.
The JSON regression parses stdout and checks `retained`; JSON output remains
valid. Failures are reported on stderr and take exit-status precedence.

## Exit 3 and the daily job

Exit 3 is appropriate even if safe deletions completed in the same pass: it
signals incomplete record health, not a transaction rollback. The daily
`sandbox-prune` job in `scripts/launchd_gen.py:53-55,77-87` invokes Python
directly at 04:20 with `StartCalendarInterval`, not `KeepAlive`. A nonzero exit
can therefore expose the record problem without the service-style immediate
restart loop. The next scheduled pass remains scheduled; completed deletions
are not undone. This is a source/configuration review, not a live launchd test.

## Fingerprint

`sandbox/verify.py:23-31` hashes `prune.py`. Recomputing the existing ordered
fingerprint algorithm directly from git blobs yields:

- Parent: `62019da52862d37e1e9c12b521849171440d27c57846a156c3e6994ee71d4b39`.
- Merge and tested main: `1532261b422c513c6890fbdab9b17e9a1bc03cd7d6b6205fed1154b9dd9f96f2`.

Current verifier receipts compare the computed value, and tests compute it
dynamically. No active pinned fingerprint or fixture needs updating. Historical
September acceptance JSON contains historical runner hashes; those are dated
evidence, not current pins, and must not be rewritten or treated as fresh acceptance.

## Tests and reproducibility

- `python3 -m unittest discover -s sandbox/tests -v`: **164 passed**, 4.302s.
- `bash -n sandbox/install-network-helper.sh sandbox/guest/*.sh`: **exit 0**.
- Parent/merge experiment: load `sandbox/prune.py` from `git show REF:sandbox/prune.py`
  into the imported module in memory, then load the complete merged
  `sandbox/tests/test_prune.py` into a fresh module and run
  `unittest.defaultTestLoader.loadTestsFromModule` with verbosity 2. No filtering,
  source edits or test edits. Parent's full 24-test module: **21 passed,
  2 failed, 1 error**, identically on the required rerun. Merge: **24 passed**.
- The dry-run separation and real-run report tests fail on the parent; the JSON
  retained-list test errors because `retained` is absent. All pass at the merge.
- Correction to the dispatch's red/green premise: `test_main_clean_pass_exits_zero`
  **already passes on the parent**, as expected for preserved clean-run behavior.
  It also passes at the merge. Thus three, not all four, detect the change.

Initial and final roadmap validation: 0 errors, 0 warnings; final `git diff --check`: clean. Main and Kimi #311/#315 heads
matched the supplied values. This review records evidence only; Claude's row
and plan are deliberately untouched, and Larry retains merge/acceptance authority.

Limits: source review only; no real prune or sandbox operation, no deployment,
no live or Mac acceptance. Tests used temporary homes and fake Tart.
