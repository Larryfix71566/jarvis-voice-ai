---
date: 2026-11-18
system: claude
rows: [WS-34]
prs: []
---

# 2026-11-18: composed answers default on (C3)

- **System:** Claude (Claude Code cloud session), at the coordinator's request.
- **Larry's words (UTC, Claude Duet channel), 14:53:35:** "Open the PR". This answered the coordinator's question whether to push this change and open its PR into `next`.
- **Why now:** the bot's kill switch said "default OFF until the app understands `answer_id` (C4)". The app reads `answer_id`, `answer_revision` and `layout` since C4 #366 and C5 #370, both in `next` and in the `8d3be6d` build deployed on the Mac.
  - Decoder: `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift:266-373`, `ComposedAnswerLayout.swift`.
  - Router and stores: `AppMessageRouter.swift:289-298`, `WorkspaceStore.swift:402-418`, `DisplayResultStore.swift:56-65`.
  - Renderer: `DisplayContentView.swift:29-30`. A layout the app cannot read is dropped and the legacy fields render (`AppMessage.swift:356-374`).
- **Change:** `composed_answers_enabled()` in `jarvis/bot/compose.py` is on when `JARVIS_COMPOSED_ANSWERS_ENABLED` is unset or blank. `false`, `0`, `no` or `off` (any case, trimmed) keep the legacy payload at every display site. Still read once per pipeline at `jarvis/bot/pipeline.py:1499`. No new config key.
- **Tests (Linux, Python 3.12, `requirements-lock.txt`):** `tests/unit/test_compose.py::test_flag_values` updated. Compose, schema, templates, display, speaker gate, global names and `tests/integration/test_bot_wiring.py`: 569 passed. Full `tests/unit`: 8368 passed, 141 skipped, 1 error, the same counts as `0fffa48` without the change. The error on `0fffa48` is `tests/unit/test_ws_transport.py::test_build_websocket_transport_wraps_the_fastapi_transport`; that file passes alone (8 passed). Ruff F clean on the changed files.
- **Not tested:** Swift tests (no Swift toolchain in the session); the Mac app with live composed payloads from the bot.
- **Takes effect:** after the bot is redeployed on a commit that includes this change. No app rebuild.
- **Next actor:** Larry: merge, redeploy, then the carousel test.
