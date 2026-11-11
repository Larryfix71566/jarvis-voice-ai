---
date: 2026-11-06
system: claude
rows: [WS-17]
prs: [309]
---

# WS-17 Kimi combined-main revalidation claim — 2026-11-06

System: Claude (Claude Code, Claude Duet thread). Workstream: WS-17.
Claim branch: `claude/ws17-kimi-revalidation-claim-20261106`.
Authority: Larry approved Kimi's combined-main validation on 2026-11-05; the
2026-11-05 claim and evidence state that any later code-changing merge needs
fresh validation. His merge of this claim is the dispatch under §0 rule 3.

## Facts checked at claim time

- Kimi's PASS (#305, merged as `e782048`) binds exact main `3695d78`.
- `origin/main` is now `78a8834ae37ab7d45d40a1782f34587ec2301cea` (merge of
  #301), after #304 merged as `5cd7532`.
- `git diff --stat 3695d78 78a8834 -- . ':!docs' ':!ROADMAP.md'`: 21 files,
  2,040 insertions, 38 deletions, including `jarvis/skill_package_adapter.py`,
  `jarvis/brief.py`, `jarvis/bot/*`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`,
  three MortimerHost display/console files, and their tests.
- `python3 scripts/check_roadmap.py` on `78a8834`: zero errors, zero warnings.

## Claim

After this claim lands, Kimi revalidates main at that moment, provided its tree
outside `docs/` and `ROADMAP.md` equals `78a8834`, with the same fourteen checks
as the 2026-11-05 run. Evidence goes on
`kimi/ws17-combined-main-revalidation-20261106` as a docs-only PR.

## Boundaries

No source, test, fixture, configuration, dependency, deployment, service,
installation, live inference or checkbox change. The combined-source
independent review, review of #301's WS-17-file Swift lines, the reviews of
#295/#296, loaded identity and every live gate stay open. Larry merges; Kimi
does not.

---

## Target correction after #290 — Kimi, session `20-34-29-68cd6dae`

#309 merged as `20e7bfc68b8f5fb57abc428b16a05cc4c9bfedf8`. Before Kimi could create the validation worktree, #290 merged as `137c6689d2d18f3765003aae1eeb610bd8945b0a`. The first binding attempt found `origin/main` `555fe86ab31968c2e6ae7f0f4843fd60e96b8a56`; its diff against `78a8834` outside `docs/` and `ROADMAP.md` was 59 files, +32,511/-477. Kimi stopped at the guard and ran no check.

Larry then directed Kimi to correct the blocker. Current main at preparation is `adc2b92948d7302765fceb9d233b0f72dcdb986e` (#308); its non-documentation tree equals #290 merge `137c668` (subsequent #307/#308 changes are documentation only). After this amendment lands, the target is main at that moment, provided its tree outside `docs/` and `ROADMAP.md` equals `adc2b92948d7302765fceb9d233b0f72dcdb986e`.

This changes registration documentation only. The fourteen checks, evidence branch, read-only scope and operational/live limits are unchanged. No source, test, fixture, configuration or dependency was edited, and no validation result is claimed by this rebind.

---

## Registration refresh after #312 and the November 10 merges — Kimi, session `20-34-29-68cd6dae`

#312 merged as `0a11a86587a7f0f3f97389db62f9425b8279df0c` after the initial #311 target correction. It changed 12 source/test files (+245/-23), invalidating the earlier `adc2b92` binding. The pre-refresh #311 `validate` job failed `tests/unit/test_roadmap_event.py::test_current_repository_complete_snapshot_survives_projection` and `tests/unit/test_roadmap_reader.py::test_real_repo_has_complete_card_count_and_bounded_snapshot` because the roadmap logs exceeded the former file limit; the tally was 2 failed, 7,774 passed, 141 skipped, 18 warnings and 583 subtests passed.

Before Kimi published a refreshed correction, main advanced to `a87256ad9e7966496542f2e7bf32582aa489cd10`. Relative to `0a11a86`, #315, #317, #320 and #323 changed seven non-documentation files (+274/-28): `AGENTS.md`, two workflows, `jarvis/app_build_contract.py` and three test files. Later documentation merges and the ROADMAP history archive are integrated without reverting them.

The corrected target is main after this amendment lands, provided its tree outside `docs/` and `ROADMAP.md` equals `a87256ad9e7966496542f2e7bf32582aa489cd10`. The original fourteen checks remain, with #317's blocking command added as a fifteenth check:

```sh
ruff check --isolated --select F821 --per-file-ignores "jarvis/bot/pipeline.py:F821" --per-file-ignores "tests/unit/test_mcp_mail_registry.py:F821" --per-file-ignores "tests/unit/test_phone_remote_service.py:F821" jarvis mcp_servers scripts services sandbox tests
```

Backend environment setup now uses `requirements-lock.txt` to match current CI. The weekly dependency-drift workflow is scheduled and non-blocking, so it is not an additional publication gate. This remains a documentation-only registration refresh: no source, test, fixture, configuration or dependency was edited in the PR delta, no local validation result is claimed, and any later code-changing merge requires another rebind.
