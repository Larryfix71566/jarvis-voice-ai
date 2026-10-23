---
date: 2026-10-23
system: kimi
rows: [WS-32]
prs: []
---

# WS-32 roadmap reader growth repair — claim only

Larry approved Kimi registration and this bounded claim on 2026-10-23.
Baseline: `c2e3c74a2f08dbe925303d19e6822383d53ddd73`.

An isolated exact-main worktree reproduced
`test_current_repository_complete_snapshot_survives_projection` and
`test_real_repo_has_complete_card_count_and_bounded_snapshot` failing because
`ROADMAP.md` is 259,344 bytes, over the generic 256,000-byte reader limit.
No source or test file was changed during diagnosis or registration.

The future `fix/ws32-roadmap-reader-limit-20261023` branch may add a separate
bounded roadmap read limit and focused regressions only after this claim lands.
It must preserve the generic per-file limit, existing path/secret guards,
stat-before-read and second-read race defenses, complete-workstream semantics,
512 KiB snapshot and 600 KiB display-event ceilings, and sensitive-turn rules.
No roadmap trimming, Base/UI/provider/configuration/credential/access change,
live test, deployment or acceptance closure is authorized.

This PR registers `kimi` in the shared protocol and workspace table and claims
WS-32 with after-merge lifecycle wording. The prospective merge tree is checked
as main so the distinct future implementation branch does not create a
claimed-but-merged branch error. Implementation remains unstarted until Larry
merges this registration and dispatches WS-32.

Validation: `git diff --check` passed; roadmap checker/plan-manifest tests
passed 43/43. Normal and prospective-main roadmap checks report no WS-32
finding, but both stop with the inherited WS-05 error: its status remains
`claimed` although #264's branch is merged. Per C1/C2, this is reported here
without editing another owner's row. The known oversize-roadmap reader failures
also remain inherited and are the subject of this claim, not fixed by it.
