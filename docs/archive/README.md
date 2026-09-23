# Archive

Documents that no longer describe current or pending work. Archived 2026-09-22
against `main` @ `88b206f`. Kept for decision history; nothing here is a
source of truth for how the system works today. Paths mirror where each file
used to live (`docs/archive/plans/X` was `docs/plans/X`).

Moved with `git mv`; `git log --follow <path>` shows each file's full history.

| Document | Why archived | Current source |
|---|---|---|
| `plans/GEOLOCATION_BACKEND_SPEC.md` | Own header: SUPERSEDED, never built as written | `jarvis/ambient_weather.py` |
| `plans/GEOLOCATION_DEVELOPMENT_PLAN.md` | Own header: SUPERSEDED, never built as written | `jarvis/ambient_weather.py` |
| `plans/INTERVAL_POLLING_CAPABILITY.md` | Own header: NOT IMPLEMENTED, orphaned | none |
| `plans/MORTIMER_RESUME_PLAN.md` | Own header: SUPERSEDED 2026-08-21 by the reliability overhaul | `CLAUDE.md` (barge-in survival) |
| `plans/MORTIMER_SELFEDIT_AUTHORING_PLAN.md` | Own header: HISTORICAL DRAFT, workflow superseded | `sandbox/README.md`, `sandbox/runtime.py`, `sandbox/session.py` |
| `plans/MORTIMER_DRAWER_POPOUT_PLAN.md` | Implemented in the frozen `web/` console only; own header says superseded | `macos/MortimerHost` |
| `plans/PLAN_AUTHOR_BRIEF.md` | Prompt for the 2026-08-26 plan-writing round, not a plan; targets a `/home/claude/repo` snapshot | — |
| `plans/optimization_rev3_files/` | Rev 3.2 readiness checklist and bundle (2026-09-01); the plan is now Rev 3.6 | `docs/plans/MORTIMER_OPTIMIZATION_PLAN.md` |
| `acceptance/adaptive-interface/C10-consolidation-candidate.md` | Candidate "pending publication"; published in #79 and superseded by #80 | `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` |
| `acceptance/adaptive-interface/production-local-patches/` | Inventory of five production patches; all reconciled into `main` in #79 (`94a5641`) | `RELEASE_READINESS.md` completed items |
| `acceptance/adaptive-interface/P0-P1-progress.md`, `P3-progress.md`, `P4-progress.md`, `P5-progress.md`, `P6-interim-checks.md` | 2026-09-11 in-progress phase logs, superseded by the closure records C0–C8 | `C*-*.md`, `RELEASE_READINESS.md` |
| `acceptance/adaptive-interface/P2-additive-observation-design.md` | Own header: RETIRED 2026-09-11 by closure decision L1 | `docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` |
| `acceptance/adaptive-interface/P2-window-visibility-investigation.md` | Resolved by #69/#70 (passing receipt `a56c192c…` at `8c1fb5a`) | `C5-verification-runner.md` |
| `reviews/ARCHITECTURE_SNAPSHOT_2026-09-04.*` | Point-in-time snapshot | `docs/ARCHITECTURE.md` |
| `reviews/GRAPH_LAYER_PLAN_REEVALUATION_2026-09-04.md` | Pre-implementation re-evaluation; the graph layer shipped 2026-09-05 | `docs/plans/MORTIMER_GRAPH_LAYER_PLAN.md` |

Historical records elsewhere (closure plan steps, gap-closure `git add`
commands, the plan-review move log) keep the paths they had when they were
written. Use this table to find the file.
