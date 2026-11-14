---
date: 2026-11-13
system: claude
rows: [WS-34]
prs: [372]
---

# WS-34 C1b: remove web/, MortimerShell, GlassSpike and VPIOBench

Row: WS-34. Plan item: C1b (`docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4; Larry's decision 3, "delete all", 2026-11-11 02:35:41 UTC). Reviewer: Codex.

## What this PR does

- Deletes `web/`, `macos/MortimerShell`, `macos/GlassSpike` and `macos/VPIOBench`, plus `scripts/run_web.sh` and `scripts/build_shell.sh`.
- Removes the frontend build steps from `.github/workflows/validate.yml` (setup-node through `npm run build`). This is the last of the plan's validate.yml hand-offs (A1, B1, B5, then C1b).
- Updates what referred to them: `scripts/mortimer.sh`, `scripts/deploy_main.sh`, `scripts/run_kb.sh`, `scripts/validate.yml`, `Procfile`, `.gitignore`, `jarvis/agents/upgrade_agent.py` (planner prompt), `tests/unit/test_agents_yaml_frontend_parity.py`, `tests/unit/test_plan_manifests.py`, and the docs (`CLAUDE.md`, `README.md`, `docs/REPO_MAP.md`, `docs/ARCHITECTURE.md`, `macos/README.md`).

## Human-only part (Larry commits)

`config/self_edit_allowlist.json`, `jarvis/selfedit/allowlist.py`, `jarvis/selfedit/service.py`, `sandbox/**` (profiles, guest scripts, README) and four tests that pin them go to Larry as a patch: `/mnt/project-files/mortimer/c1b-larry-human-only-2026-11-12.patch` (14 files). It still applies cleanly to this branch after merging `next` at `6a7ac28`.

## Overlaps

- `scripts/deploy_main.sh` is in WS-17's bounded scope (Codex); this PR changes only the two web lines the plan names.
- `scripts/mortimer.sh` is also changed by the B2 follow-up PR (client header on the health check). Whichever merges second needs `next` merged in.
