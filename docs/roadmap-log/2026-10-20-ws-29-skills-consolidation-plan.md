---
date: 2026-10-20
system: codex
rows: [WS-29]
prs: []
---

# WS-29 — Skills consolidation, after acceptance

Larry accepted Option 2 and requested an implementation plan at the end of the shared roadmap, executable by any capable model after acceptance testing is complete.

- Added the final WS-29 section and [canonical plan](../plans/MORTIMER_SKILLS_CONSOLIDATION_IMPLEMENTATION_PLAN.md), based on main `b136a2a66032b17082776a01353abe67e352c31e`.
- Reusable methods consolidate into Skills; standing policies remain independently applied; host voice-event routing, permissions, privacy, durable state and verification evidence remain authoritative.
- The plan maps all 23 legacy definitions, includes seven implementation increments and 18 acceptance criteria, and specifies compatibility, staged rollout, rollback and model-neutral handoff.
- Documentation scope is only these two new files and the appended roadmap section. Existing roadmap text/checklists, owners, production and runtime files are unchanged. No shared identifiers reserved; no code, provider calls, activation, merge or deployment implied by plan creation.
- Baseline check: `python3 scripts/check_roadmap.py` reports one pre-existing error, WS-17 `review` on an already merged branch (#226, `4b73fed`). WS-29 does not own that status correction. The same finding must remain the only checker error after this documentation change.
- Local validation passed: `git diff --check`; exact preservation of the prior roadmap prefix and every existing acceptance checkbox; unique WS-29 ID; all 23 legacy definitions mapped; SC0–SC6 and AT-01–AT-18 present; all relative links in the new documents resolve. The roadmap checker reports exactly the same one baseline finding and no new finding. Runtime tests were not run for this documentation-only change.
- Remaining action: existing owners complete acceptance; Larry records closeout and dispatches a fresh WS-29 owner/branch/scope. No model may begin implementation early or equate source tests with live acceptance.
