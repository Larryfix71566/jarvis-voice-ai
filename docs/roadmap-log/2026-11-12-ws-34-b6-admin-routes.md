---
date: 2026-11-12
system: claude
rows: [WS-34]
prs: [353]
---

# PR #353: B6, admin server split into route modules

Under the batch rule (#359) this PR no longer edits `ROADMAP.md` or `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`: both now match the PR base `next` at `c41004c`. The status text it used to carry is below.

## What changed

The 88 route handlers of `jarvis/admin/server.py` moved verbatim into 13 modules under `jarvis/admin/routes/` (core, ambient, knowledge, council, status, research, plan, appbuild, skills_creator, skills, selfedit_session, selfedit_run, sources). `server.py` keeps helpers, state, models and middleware: 5,579 lines to 2,835. Handlers reach helpers and state through `srv.<name>` at call time, so tests that monkeypatch the server module still reach them.

## Evidence

- Route, middleware and attribute dumps before and after: 88 to 88 routes, 4 to 4 middleware, 321 to 322 attributes (`_new_staging_id`, kept in `server.py` because `tests/unit/test_prompts.py` reads that file's text). The `python -m` launch was checked.
- `pytest tests/unit`, before and after: the same failure set (60 env-only failures in `test_mcp_mail_logic.py` and one order-dependent `test_ws_transport.py` error); passed count 7,812 before, 7,826 after, with the tests the branch added. Integration: 198 passed, 4 skipped, before and after. No test file edited.
- After merging `next` at `c41004c`: admin, request-guard and self-edit unit tests pass here; CI on the PR head is the gate.

## Left

- Review by Codex (the item's named reviewer), then Larry merges into `next`.
- A docs follow-up pointing `CLAUDE.md` and `docs/REPO_MAP.md` at `jarvis/admin/routes/`.
- Next actor: Codex (review).
