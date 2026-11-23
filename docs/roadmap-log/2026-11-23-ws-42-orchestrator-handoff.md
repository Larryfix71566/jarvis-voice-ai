---
date: 2026-11-23
system: claude
rows: [WS-42]
prs: []
---

# 2026-11-23: hand_off tool and text orchestrator (WS-42)

- **System:** Claude (Claude Code cloud session), at the coordinator's request. Planned by Claude Fable 5.2; implemented by Claude Sonnet 5.5.
- **Larry's words (UTC, Claude Duet channel):** 19:18 "splitting the orchastrator from the voice, is that feasible? I think if it is we get better orchastration by using different more capable models for decision making?"; 19:19 "Write the design"; later "Option b approved" and "run now".
- **Row:** no existing row covered routing decisions off the voice model, so this PR adds the WS-42 block and its §3 config-key reservation; merging approves both.
- **Change:** with `JARVIS_ORCHESTRATOR_ENABLED` on, the voice model calls `hand_off` (one optional note) instead of `delegate_task`. New `jarvis/agents/orchestration.py` asks the `orchestration` workload (`claude-fable-5-2`, subscription text path) for one JSON decision of 0-4 steps or a question, validates it on the host, and runs each step through the existing delegate handler. A routing failure starts no work and returns a tagged FAILED string. The voice prompt template with the flag on drops its routing rules (they move to `ORCHESTRATOR_PROMPT`); with the flag off the template and tool menu are byte-identical to a469553. `delegate.py` is unchanged. The new profile adds one line to the model list in the voice prompt and the console picker even with the flag off.
- **Verified here (Linux, Python 3.12):** the new `tests/unit/test_orchestration_*.py` with a stubbed client (no network, no real model call); the model-registry, catalog, prompt, tool-schema and failure-class tests; the full unit suite and `tests/integration/test_bot_wiring.py` (counts in the PR).
- **Not tested:** a real Fable 5.2 call; whether the installed `claude` CLI runs `claude-fable-5-2`; hand-off latency; the routing eval through the orchestrator; two parallel steps queueing behind the shared two-slot model admission controller.
- **Next actor:** Larry: merge, set the flag, check the CLI and one live hand-off.
