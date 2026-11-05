---
date: 2026-11-05
system: claude
rows: [WS-17]
prs: []
---

# WS-17 Kimi combined-main validation claim — 2026-11-05

System: Claude (Claude Code, Claude Duet thread). Workstream: WS-17.
Claim branch: `claude/ws17-kimi-validation-claim-20261105`.
Authority: Larry handed Claude the task of preparing Kimi's combined-main
validation and its roadmap hand-off on 2026-11-05; his merge of this claim is
the dispatch under §0 rule 3.

## Why

WS-17's next step on main asks for "exact combined-source independent review and
combined-main validation before any separately authorized operational recovery"
and keeps installation, restarts and live tests held. Codex, the usual actor, is
out of usage this week. The roadmap names no system as the only one allowed to
validate; Kimi recorded a local combined-main verification under WS-24 on
2026-10-26 at `5581d4f` (#279) on Larry's dispatch.

## Facts checked at claim time (origin/main `f874cf1`)

- `origin/main` is `f874cf1a757b03d98336aca36ef08fb13c15c7a6`, the merge of #300.
- `f874cf1` differs from #300's head `d0317ad` only in `ROADMAP.md`,
  `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` and one roadmap-log file.
  GitHub reports `validate`, `allowlist`, `policy-tests`, `knowledge-base` and
  `controller-tests` successful on `d0317ad` (Ubuntu CI).
- Between `5581d4f` and `f874cf1`, nothing changed under `macos/`, `web/`,
  `services/`, `scripts/`, `config/` or the requirements files; Python source
  and tests were added (WS-03 adapter, WS-23 evidence contract, WS-31 app-build
  contract, WS-04 contract test and fixture, WS-28 prune, WS-32 registry).
- The 10-26 Kimi run did not include the Swift suites. The last full native
  record in ROADMAP.md is MortimerHost 582 / five prerequisite skips / zero
  failures at `a672239` (10-22); three files under `macos/` changed after it.
- `python3 scripts/check_roadmap.py` on `f874cf1`: zero errors, zero warnings.

## Claim

After this claim lands, Kimi validates main at that moment, provided its tree
outside `docs/` and `ROADMAP.md` equals `f874cf1`. Checks: the gates in
`.github/workflows/validate.yml`, `knowledge-base.yml` and `sandbox.yml`, both
Swift suites, and the clean-environment full `pytest` of
`scripts/deploy_main.sh` phase A, all in a fresh Kimi worktree. Evidence goes on
`kimi/ws17-combined-main-validation-20261105` as a docs-only PR limited to the
WS-17 Kimi sub-section, dated WS-17 plan progress and WS-17 roadmap-log entries.

## Boundaries and remaining action

No source, test, fixture, configuration, dependency, deployment, service,
installation, live inference or checkbox change. The combined-source
independent review, the open reviews of merged #295/#296, loaded identity and
every live gate stay open. A later code-changing merge (for example draft #301)
needs a fresh validation. Larry merges; Kimi does not.
