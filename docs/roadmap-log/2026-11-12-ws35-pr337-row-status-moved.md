---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [337]
---

# PR #337: WS-35 row status text moved out of `ROADMAP.md`

System: Claude, at Larry's request to clear the open PRs' conflicts (2026-11-12 18:10 and 18:15 UTC: "I am seeing conflicts in all remaining PR", "all still show conflicts unresolved").

Claude merged `next` at `c41004c` into this branch and set `ROADMAP.md` back to `next`'s version. Under the daily batch rule (§0 rule 16, #359) a PR records status only in its own log file and does not edit a row's Status, Where, Next step or Updated lines; the daily batch PR folds this text into the row after the PR merges. No code, test, workflow or other document changed in this step.

## WS-35 row lines this PR carried (verbatim, from head `fdbe9eac`)

- **Status:** in-progress; C1a source and verification delivered by #337 at `69f9805`; C10 baseline remains a merge gate. Review handoff recorded 2026-11-12; no merge or acceptance approval implied.
- **Where:** `codex/ws35-c1a-layout-removal-20261111` (#337) into `next` (C1a source `69f9805`); `codex/ws35-c10-baseline-20261111` (#335, C10 instructions); `codex/ws35-contract-review-20261111` (#334, contract review). Code items branch from `next`, except F1 from `main`.
- **Next step:** kimi: review #337. Kimi reviews C1a; Larry captures C10 before merge. The known separate F1 authority-prerequisite failure remains disclosed; no full-Host green claim. Other lane items retain their existing dependencies.
- **Updated:** 11-12
