---
date: 2026-11-10
system: codex
rows: [WS-32]
prs: [296]
---

# WS-32: post-merge host-verifier limit cross-review

Session reference: Codex 2026-11-10, branch `codex/ws28-ws32-cross-review-20261110`.
Reviewed registry delta: `e54795eb1d985e29638df08bcb9a4f56661480ea` (#296),
against first parent `4f2bc8337424ec397848b0e0d97821f1080527f5`.
Tested main: `837bb041eaa1bb0b4ed476a859c266fd42f2fcdb`.
Verdict: **APPROVE**, still valid on tested main. Blocker: none. Should-fix: none. Nit: none.

## Source classification review

As WS-05 reviewer, read the complete `git diff e54795e^1 e54795e -- jarvis/ tests/`
and the full merged `_repo_source_refs`. The three changed source lines import
`ROADMAP_READ_MAX_BYTES`, select it only for the resolved canonical roadmap, and
use that selected bound for the existing host stat-size comparison. The
`repo_search` verifier retains `REPO_READ_MAX_BYTES` (256,000 bytes); all other
paths and source-classification rules, including `_invoke`'s weather hook, are
unchanged by #296. Stat size, reported byte count, canonical returned path and
content are checked against the same resolved `expected` path. Existing
multiple filesystem reads are unchanged; this review does not claim new atomic
snapshot or race guarantees.

At `jarvis/skills/registry.py:603-622`, canonical means the **resolved target**,
not the spelling of the request. This distinction matters to the dispatch:
`./ROADMAP.md` and an in-repo alias symlink to canonical `ROADMAP.md` can satisfy
the canonical test, but they select the same file, not a different file with a
larger allowance. A symlink named `ROADMAP.md` targeting `other.md` instead gets
the generic limit. Nested roadmap files and distinct case variants do not get
the exception. Outside-repo targets are rejected before reading their contents.
This follows the existing resolver's intended semantics, not a new bypass.

Synthetic checks used a temporary repository, a 2,000-byte file, generic cap
1,000 and roadmap cap 4,000, with exact body bytes/content and resolved path:

- `ROADMAP.md`, `./ROADMAP.md`, and `alias.md -> ROADMAP.md`: accepted with the
  same canonical reference to root `ROADMAP.md`.
- `roadmap.md`, `nested/ROADMAP.md`, `other.md`: refused.
- `outside.md` resolving outside the repository: `RepoPathError`, before file read.
- Root `ROADMAP.md -> other.md`: refused under the generic cap.

The later #312 difference is precisely the additional `len(refs) > 255`
roadmap-log digest branch. `git diff e54795e 837bb04 -- jarvis/skills/registry.py`
shows no changes to #296's import, bound selection or size-check lines. #312's
behavior is outside this review's verdict scope.

## Red/green and mutation checks

Executed the complete **71-test merged-era source-policy module**, loaded from
`git show e54795e:tests/unit/test_registry_source_policy.py` in memory using a
pytest module collector. Loaded `_repo_source_refs` from each commit's AST in
memory. No tests filtered and no tracked source/test files edited.

- Parent `e54795e^1`: **1 failed, 70 passed**, identical on rerun. Only
  `test_canonical_roadmap_between_generic_and_roadmap_limits_is_attested` fails.
- Merge `e54795e`: **71 passed**.
- Mutation: replace only `expected.stat().st_size > read_max_bytes` with `False`
  in the in-memory merged method. **2 failed, 69 passed**, identical on rerun.
  Failures are exactly `test_canonical_roadmap_above_roadmap_limit_is_refused`
  and `test_non_roadmap_file_keeps_generic_limit_at_host`.
- Each historical run emitted one pytest assertion-rewrite warning because
  `anyio` was already imported by the experiment harness.

Initial comparisons ran the full current 88-test module against
historical methods before matching test vintage: parent **8 failed/80 passed**,
merge **7 failed/81 passed**, mutation **9 failed/79 passed**, each reproduced
on its rerun. The seven shared failures exercise #312's later aggregate-log
commitment, absent from historical methods. The merged-era experiment above
isolates #296 without filtering tests; these seven are not #296 regressions.

## Main validation

Used existing Python 3.12 dependencies with temporary HOME/TMPDIR and no live
execution; no dependency installation was needed.

- `python -m pytest tests/unit/test_registry_source_policy.py tests/unit/test_mcp_repo_logic.py tests/unit/test_roadmap_reader.py tests/unit/test_roadmap_event.py -q`:
  **184 passed, 2 deprecation warnings**, 12.21s.
- `python -m pytest tests/unit -q`: **7,802 passed, 141 skipped, 19 warnings, 583 subtests passed**, 211.96s, after moving synthetic temporary files outside the repository.
- Initial full-suite run and its required identical rerun each reported
  **3 failed, 7,799 passed, 141 skipped, 19 warnings, 583 subtests passed**
  (214.87s and 211.26s). The temporary HOME/TMPDIR was mistakenly inside the
  worktree. This made git discover the enclosing repository in tests that
  expected a non-repository directory, and made the weather-source scanner
  see copied fixture sources. The three failures were
  `test_status_explicitly_rejects_non_repository_root`,
  `test_support_requires_committed_exact_bytes_before_live`, and
  `test_weathergov_module_is_the_only_implementation`. Scratch files were then
  moved to a sibling directory under the same permitted `can/work` location;
  the unchanged full command was rerun with temporary HOME/TMPDIR there.
  No reviewed code or tests were changed to address these environment artifacts.

Initial and final `python3 scripts/check_roadmap.py`: 0 errors, 0 warnings; final `git diff --check`: clean. Main and Kimi
#311/#315 heads matched the dispatch. Only this log and the WS-28 review log
are proposed; no ROADMAP, Atlas/REA plans, Kimi files, reviewed source or tests
are changed. Claude updates its own rows after Larry merges this documentation.

Limits: source review only; no real prune or sandbox operation, no deployment,
no live or Mac acceptance.
