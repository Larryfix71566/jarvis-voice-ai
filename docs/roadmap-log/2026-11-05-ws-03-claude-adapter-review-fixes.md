---
date: 2026-11-05
system: claude
rows: [WS-03]
prs: [300, 302]
---

# WS-03 — adapter review findings fixed, 2026-11-05

System: Claude (Claude Code cloud session `session_01EHREEW5sYoAgS63MkPBzWs`).

Input: Kimi's independent exact-source review of #300 (head `d0317ad`, merged as `f874cf1`), posted by Larry as a comment on #302 on 2026-11-05.

Change, on `claude/ws03-adapter-review-fixes-20261105`, limited to `jarvis/skill_package_adapter.py` and `tests/unit/test_skill_package_adapter.py`:
- Baseline registry bytes are now judged by the runtime `read_skill_registry`, through an in-memory read-only stand-in. A registry it rejects blocks with `baseline_registry_invalid`.
- Once the validator runs, a missing or foreign receipt blocks with `validator_failed`, and any unknown check name blocks with the new code `validation_check_unrecognized`.

Evidence: all seven reported cases reproduced on main before the fix and are refused after it. Of the 15 new tests, 8 fail on the unfixed adapter. Adapter suite: 136 passed; with the skills suites: 328 passed.

Remaining: Kimi re-review at the fix PR's exact head; Larry's merge decision. No installation, activation or acceptance change; 2/12 stands.
