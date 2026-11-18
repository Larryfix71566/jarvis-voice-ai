---
date: 2026-11-18
system: claude
rows: [WS-17, WS-34, WS-35, WS-36]
prs: [383]
---

# 2026-11-18: non-production, no freeze, optional review

- **System:** Claude (Claude Code cloud session), at the coordinator's request.
- **Rows:** §0 rules 14, 15 and 16 and joint-working rule C3; `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`; `AGENTS.md` and `CLAUDE.md`, to keep them in agreement.
- **Larry's words (UTC, Claude Duet channel):**
  - 01:22:44: "ok, I dont really want to waste time on this. I wan to get to the enhanced developement and then test from there. I want it to be noted in the roadmpa and new development plan that we are working on a nonprod application. we dont need precasutions afforded a prod app"
  - 01:26:12: "Yes, skip reviews". This answered the coordinator's question about reviewing #378 and dropping the outside review for #379 and #375. This PR records it as a general rule under the non-production direction. Larry can narrow it.

## Change

- **Rule 15:** the code-only freeze is replaced with a non-production rule.
  - Lifted: the `main` freeze and acceptance-fixes-by-name, deploy holds, frozen-build revalidation reviews before a deploy, and cross-system review before merge.
  - Kept: Larry merges every PR, no system reviews its own work, boxes are ticked only with evidence, and rule 7.
- **Rule 14 and C3:** review before merge is optional, and Larry merges at his discretion.
- **Rule 16:** a review of the daily batch by another system is optional.
- **Plan:** the header, Larry's direction, §1, §2, the §3 table, the C10 and F1 rows, §5 and §8 now point acceptance at the enhanced build from `next`.

## Frozen-build acceptance at the stop (for the daily batch to fold)

These are from `docs/acceptance/mac-acceptance-2026-11-11.md`.

- **§1 deploy and prepare:**
  - M2: deploy of `7e8adc9` done (2026-11-16).
  - M6 and M7: pass.
  - 548 and 802: no recorded result.
- **Sitting 1:** box 201 (the roadmap view) failed. Larry saw a wall of text, and a refresh didn't change the format. The coordinator read Mortimer's log, which showed both reads displayed as `kind=markdown`. Per Larry, this was not investigated.
- **Moved to the enhanced build on `next`:** sittings 1 and 2, and C10's full scene.

No box is ticked by this PR.

## Remaining

- Merge `main` into `next` after this merges, so that `next` carries #379, #381 and these rules.
- The daily batch folds the results above into WS-17, WS-34 to WS-36 and the plan's progress log. That covers the rows' "acceptance fixes branch from `main`" wording and WS-17's "freeze-build deployment" next step.
