---
date: 2026-11-19
system: claude
rows: [WS-38]
prs: []
---

# 2026-11-19: Mortimer's tone, dry humor and sarcasm (WS-38)

- **System:** Claude (Claude Code cloud session), at the coordinator's request. Planned by Claude Opus 5.5, implemented by a Sonnet helper, checked by Opus.
- **Larry's words (UTC, Claude Duet channel), 02:56:45:** "I would also like mortimer to have the ability to be sarchastic when answering me, humor is fine for our interactions".
- **Row:** no existing row covered the Supervisor persona, so this PR adds the WS-38 block and the `JARVIS_PERSONALITY` §3 reservation with the change; merging approves both.
- **Change:** the Supervisor persona sentence in `jarvis/prompts.py` is now "a precise, calm personal AI assistant with the dry wit of a long-serving butler", followed by a `Tone:` paragraph (`TONE_PLAYFUL`): answer first, joke second, at most one short clause; facts, numbers and specialist results stated plainly; no humor for failures, previews and confirmations, anything that spends, sends, deletes or changes something, safety, health or money, or a stressed or rushed user; tease the situation, never Larry or anyone else; every existing rule still binds a joke; "drop the jokes" or a `user.style` memory turns it off. `JARVIS_PERSONALITY` (`playful` default, `formal`) is read into `Settings.jarvis_personality` and passed to `build_supervisor_prompt` by `jarvis/bot/pipeline.py` and `jarvis/agents/supervisor.py`. `formal` reproduces the previous prompt byte for byte (checked against `b1f25e3`'s `SUPERVISOR_PROMPT`). No other rule, addendum, tool, model or voice changes.
- **Tests (Linux, Python 3.12, `requirements-lock.txt`):** new WS-38 cases in `tests/unit/test_prompts.py` (18) and `tests/unit/test_config.py` (4). Prompts, config, supervisor registration and `tests/integration/test_bot_wiring.py`: 196 passed. Full `tests/unit`: 8449 passed, 141 skipped, 1 error; the error is `tests/unit/test_ws_transport.py::test_build_websocket_transport_wraps_the_fastapi_transport`, the same pre-existing one recorded on `0fffa48` in `2026-11-18-ws-34-c3-composed-answers-default-on.md`, and that file passes alone (8 passed). Ruff F clean.
- **Not tested:** live conversation with a model; whether the jokes land is Larry's call.
- **Takes effect:** after the bot is redeployed on a commit that includes this change. No app rebuild.
- **Next actor:** Larry: merge, redeploy the bot, then talk to Mortimer. `JARVIS_PERSONALITY=formal` in `.env` turns it off.
