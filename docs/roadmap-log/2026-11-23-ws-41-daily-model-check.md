---
date: 2026-11-23
system: claude
rows: [WS-41]
prs: [409]
---

# 2026-11-23: Daily new-model check (WS-41)

- **System:** Claude (Claude Code cloud session), at the coordinator's request. Planned by Claude Opus 5.5; parsers, subscription lists, certify, propose and most tests by Sonnet helpers; detector, runner and integration by Opus.
- **Larry's words (UTC, Claude Duet channel):** 17:48:09 "We need to add a process to automatically keep in sync with new models when they come out as far as what we use for orchestration not sure how often we need to check so review and make recommendations"; 18:01:48 "Build the daily check".
- **Row:** no existing row covered key-free model discovery, so this PR adds the WS-41 block and its §3 config-key reservation; merging approves both.
- **Change:** new `jarvis/model_sync/` package, run at the end of the 06:30 `status-daily` job and by `scripts/sync_models.py`. Detects new models from Anthropic's release-notes feed and deprecations page, the Codex changelog and models page, the Kimi changelog, npm's newest CLI versions, four Claude alias probes on the subscription CLI and Codex `app-server` `model/list`; compares them with every model ID in tracked `config/*.yaml` and the voice workload; flags deprecations of pinned models (notice when first seen, task at 30 days left, urgent at 7); certifies a new candidate once per CLI version (exact-ID subscription probe, Codex receipt, voice bench p50 ≤ 1.2 s / p90 ≤ 3.5 s); on a pass opens one PR into `next` with the exact ID (GitHub REST with the Mac's token, else a patch file). Report at `GET /api/status/model-sync`, one spoken notice when something is new. No API key is used and no model is switched.
- **Verified here (Linux, Python 3.12):** `tests/unit/test_model_sync_*.py`; a `--detect-only` run against the live Anthropic pages and npm, and `model/list` against the official `@openai/codex@0.171.0` binary with no login (14 models, default `gpt-6.2-sol`). That run found Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5 (voice) and GPT-6.2 Astra as newer than what `next` pins, and both installed CLIs outside Mortimer's verified sets.
- **Not tested:** the Claude alias probe on Larry's login; Codex `model/list` on his ChatGPT login; the Codex and Kimi pages' live format (unreachable from the build container); the voice bench numbers; PR creation with the Mac's GitHub token.
- **Next actor:** Larry: merge, redeploy, run the Mac commands in the PR.
