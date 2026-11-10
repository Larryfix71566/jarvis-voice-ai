---
date: 2026-11-10
system: codex
rows: [WS-32]
prs: [322]
---

# WS-32: Codex review of PR #322

System: Codex. Session reference: Larry's 2026-11-10 PR #322 review dispatch,
review branch `codex/ws32-pr322-review-20261110` (no verified chat URL available).
Larry explicitly assigned this cross-review and its single-file record; WS-32's
owner block and plan are deliberately not edited.

## Targets and verdict

**APPROVE** PR #322 at `fbce1e129b76318e0f4ecdd6f4917ef53a18c37b`.
Main tested: `a87256ad9e7966496542f2e7bf32582aa489cd10`.
Both refs matched the dispatch at the initial fetch and publication recheck.
The PR merges cleanly into that main, including ROADMAP.md. Tests below ran on
that uncommitted merge in a separate detached validation worktree, not on the
review-record branch. No modification of the reviewed PR was made.

Findings: **blocker: none; should-fix: none; nit: none**. The capacity limits below
are existing, enforced bounds, not guarantees that every 1 MiB file is readable.
No deployment, native UI acceptance or live-provider approval is implied.

## Integrity and consumers

- `jarvis/skills/registry.py:615-618` still binds declared bytes and content to
  the guarded disk file. Lines 632-647 enforce UTC timestamps (age between
  -5 and 300 seconds), rebuild `_roadmap_snapshot` from host reads, substitute
  only the validated timestamp, then require exact sorted JSON equality.
- A baseline real-roadmap result was accepted. Nine independent mutations were
  all refused with `tool_source_scope_invalid`: old `mortimer.roadmap.v1` plus
  forged cards, wrong SHA-256, extra key, missing key, removed logs, forged
  issues, timestamp in 2000, timestamp in 2100, and changed content. Reproduction:
  build a body with the current file bytes and `_roadmap_snapshot(root,text)`;
  copy it for each mutation; invoke `SkillRegistry._repo_source_refs` with a
  synthetic contract containing `repo_root=root`, tool `repo_read_file`, and
  arguments `{"path":"ROADMAP.md"}`. Existing classified-result and agent tests
  additionally prove rejection before publishing/history/model continuation.
- `jarvis/agents/base.py:175-190` expands only the verified content, then checks
  full snapshot shape and size. `jarvis/bot/display.py:209-219` expands compact
  reads and drops failed/oversized expansion. Display still accepts full v1
  intentionally for the already-expanded agent event; this is not a host bypass.
- `jarvis/bot/pipeline.py:489-506` validates the classified envelope before
  building display, refuses protected sources, and bounds escaped JSON at
  1200 KiB. `AppMessage.swift:220` accepts only full v1 and its decode path
  rejects invalid payloads. Source-schema reads are expanded before native
  delivery. A repository grep found the remaining native rendering, filtering,
  export, store and refresh readers consume this decoded full-v1 structure.
- AST comparison of all existing functions in `mcp_servers/mcp_repo/logic.py`
  found only `_roadmap_snapshot` changed; `expand_roadmap_snapshot` is the only
  added function. `repo_read_file`, `repo_search`, path guards, log discovery,
  and card parsing are unchanged. `jarvis/skills/registry.py` is byte-identical
  to main, including generic 256,000-byte limits and the 255-ref digest path.

## Capacity reproduction

These are exact last-accepted / first-refused **raw UTF-8 byte sizes** for the
specified synthetic growth, not universal ceilings. Read-result characters use
scoped canonical serialization: `json.dumps(body, sort_keys=True,
separators=(",",":"), ensure_ascii=True, allow_nan=False)`. Expanded snapshots
use `ensure_ascii=False`; pipeline payloads use `ensure_ascii=True` and ordinary
JSON spacing, matching the code. Display time was fixed at 1794328200 and timezone
at America/New_York to remove incidental length drift.

Today's main roadmap is 302,880 bytes: old read 827,266 characters. With the
**same main text and logs**, compact read is 379,360 characters. The actual merged
roadmap is 304,124 bytes and its compact read is 380,887 characters. Differences
from the author's 826,936/379,372 figures reflect different source/log snapshots;
the single-copy saving is reproduced, not asserted from the author's report.

| Growth | Main agent / console | Merged agent | Merged console refresh |
|---|---|---|---|
| ASCII prose after the document | 393,216 / 393,217 | 923,236 / 923,237 | 923,236 / 923,237 |
| ASCII plain line inside first card | 389,245 / 389,246 | 923,235 / 923,236 | 826,476 / 826,477 |
| ASCII parsed field inside first card | 360,458 / 360,459 | 923,235 / 923,236 | 565,301 / 565,302 |
| Emoji parsed field inside first card | 322,088 / 322,092 | 510,508 / 510,512 | 420,664 / 420,668 |

To reproduce: take the exact main/merged text and `_roadmap_snapshot` logs and
provenance; binary-search the number of `x` characters appended after the
file, inserted before its first card's closing `</details>`, or inserted as
`- **Review padding:** ` inside that card. Repeat the field with U+1F600 for
Unicode growth. Recompute SHA-256, raw size, old cards where applicable, result
JSON, expanded snapshot, and `build_display_payload` for every candidate.
Apply all three actual limits: raw cap, 1,000,000-character host result, and
1 MiB expanded / 1200 KiB escaped console payload. No content is truncated.

At the merged ASCII field console boundary, expanded sizes are 1,048,576 and
1,048,578 bytes; accepted pipeline payload is 1,051,991 bytes, below 1,228,800.
For emoji-field growth, the pipeline cap binds first: expanded sizes are only
759,302 / 759,310 bytes, but escaped payloads are 1,228,781 / 1,228,805 bytes.
Thus the author's approximately 559 KB console and 902 KB agent observations
are plausible for their card-copy workload, not universal byte promises.

An additional end-to-end synthetic temporary-repo `call_classified` check
confirmed a canonical read of exactly 1,000,000 characters is accepted, while
1,000,001 returns only `{"ok":false,"error":"tool_reported_failure"}`. The
1 MiB raw cap is safe under the unchanged host bound: excessive escaped output
is refused whole before downstream consumption. Native UI behavior at these
ceilings was not exercised; the source and payload guards were.

## Commands and validation results

All worktrees and evidence are below `~/Documents/Codex/2026-09-09/can/work/`.
`REVIEW=codex-ws32-pr322-review-20261110`,
`VALIDATION=codex-ws32-pr322-validation-20261110`, and
`EVIDENCE=codex-ws32-pr322-evidence-20261110` name sibling directories there.
`PY` is the existing `codex-isolated-20260924/.venv/bin/python` (Python 3.12);
no package installation was performed. Python suites used `env -i`, standard
system PATH, `PYTHONDONTWRITEBYTECODE=1`, and HOME/TMPDIR inside EVIDENCE,
**outside** either Git worktree. No test filters were used.

1. `git fetch origin`; `git fetch origin pull/322/head:pr322`; `git rev-parse
   origin/main pr322`: exact refs above. Read AGENTS.md, CLAUDE.md, ROADMAP.md
   sections 0/2/4, docs/README.md, ARCHITECTURE.md, REPO_MAP.md and the allowlist
   sequence; inspected with `sed`, `head`, `grep` and `git show`.
2. `git worktree add -b codex/ws32-pr322-review-20261110 "$REVIEW" origin/main`;
   `python3 scripts/check_roadmap.py`: **0 errors, 0 warnings**.
3. `git diff origin/main...pr322` (all nine files); source reads with `sed` and
   `git grep` for roadmap/schema readers; AST comparison via Python and
   `git show origin/main:<path>`: integrity/consumer results above.
4. `git worktree add --detach "$VALIDATION" origin/main`; in that worktree,
   `git merge --no-commit --no-ff pr322`: **clean merge**.
5. `$PY -m pytest tests/unit/test_roadmap_reader.py
   tests/unit/test_roadmap_event.py tests/unit/test_registry_source_policy.py
   tests/unit/test_mcp_repo_logic.py -q`: **198 passed**, 2 warnings, 9.73s.
6. `$PY -m pytest tests/unit -q`: **7,820 passed, 141 skipped, 583 subtests
   passed**, 19 warnings, 215.44s. No failure, so no rerun needed. Skips are not
   claimed as passes; this does not claim the author's integration-suite tally.
7. `python3 scripts/check_roadmap.py`; `git diff --check` on the merge:
   **0 errors, 0 warnings; clean**.
8. `$PY "$EVIDENCE/red_tests.py"` from unchanged main, twice: **20 failed,
   178 passed** both times (10.27s, 9.46s). The temporary pytest collector loads
   each complete changed test module with `git show pr322:tests/unit/<file>`;
   it does not select/filter tests or alter source. All four full files run.
   Failures cover the default cap, >384 KiB reads, compact schema/expansion,
   content binding, complete events, and large classified reads. The expected
   old-code failures disappear on the merged PR (command 5). Existing above-cap
   and generic-file refusal tests still pass on old main as expected.
9. `PYTHONPATH=. $PY "$EVIDENCE/integrity_probe.py"`: baseline accepted and
   **9/9 mutations refused**, as described above.
10. `$PY "$EVIDENCE/measure_limits.py" "$VALIDATION" "$REVIEW"` and
    `$PY "$EVIDENCE/measure_limits.py" "$REVIEW"`; `$PY
    "$EVIDENCE/host_boundary.py"`: serializer/parser binary searches and
    end-to-end boundary smoke described above. An initial measurement used
    legacy JSON spacing; the host smoke detected it, all scoped measurements
    were corrected and rerun, and only corrected figures are reported here.
11. `swift test --package-path macos/JarvisKit --scratch-path
    "$EVIDENCE/swift-integrity-build" --skip-update
    --disable-automatic-resolution`: **239 tests passed, 0 failures** on Apple
    Swift 6.4.2, including all four RoadmapPayloadTests. No app was launched.
12. Publication recheck: `git fetch origin`; `git ls-remote origin
    refs/heads/main refs/pull/322/head`; `gh pr view 322 --json
    number,state,headRefOid,baseRefName,statusCheckRollup,url`: unchanged refs,
    PR OPEN, all five checks SUCCESS (allowlist, knowledge-base,
    controller-tests, policy-tests, validate).

Read-only shell heredoc/initial Swift attempts encountered local sandbox
restrictions, then permitted commands succeeded. These were invocation issues,
not test failures. Progress inspection used `tail`/`ls`; no product state was
changed. Final docs-only checker/diff validation and publication are performed
on the review-record branch; only this file is included.

Limits: source review and offline synthetic/native-package tests only; no real
prune/sandbox operation, deployment, app/service restart, provider calls, vault
or Keychain access, or Mac UI/live acceptance. No checkbox ticked and no PR
merged. Larry retains merge authority.
