# Daily new-model check (WS-41)

**Status:** built on `claude/ws41-model-sync-20261123` into `next` (2026-11-23).
**Asked by:** Larry, 2026-11-23 17:48 UTC in his Claude Duet channel: "We need to add a process to automatically keep in sync with new models when they come out as far as what we use for orchestration not sure how often we need to check so review and make recommendations". After the review he said at 18:01 UTC: "Build the daily check".
**Review it implements:** the model-sync recommendation of 2026-11-23 (option A: Mortimer's own `status-daily` job, daily detect, benchmark on change, propose by PR, Larry merges).

## 1. What it does

Every morning at 06:30, inside the existing `com.mortimer.status-daily` launchd job, after the status snapshot and the harness brief:

1. **Detect** (no API key anywhere, no paid call):
   - Public pages, fixed allowlist, HTTPS, no redirects, no proxy, no cookies:
     - Anthropic release-notes feed `https://platform.claude.com/docs/en/release-notes/feed.xml` (launches).
     - Anthropic deprecations `https://platform.claude.com/docs/en/about-claude/model-deprecations.md` (state table and retirement dates).
     - Codex changelog `https://learn.chatgpt.com/docs/changelog` and models page `https://learn.chatgpt.com/docs/models.md` (launches, retirements).
     - Kimi platform changelog `https://platform.kimi.ai/docs/platform-changelog` (launches).
     - npm `latest` for `@anthropic-ai/claude-code` and `@openai/codex` (newest CLI versions).
   - Subscription side, on the Mac's own logins:
     - One alias probe each for `opus`, `sonnet`, `haiku`, `fable` through the Claude CLI on the same restricted argv as the subscription route, reading which model ran (`modelUsage`). Four tiny calls of subscription quota a day.
     - `claude --version`.
     - `codex app-server` `model/list` (no inference).
     - Kimi: no non-interactive list exists; reported as unsupported.
   - Pins: every model ID in tracked `config/*.yaml` (not `config/generated/`), the voice model (`OPENAI_MODEL`), and the verified CLI version sets.
2. **Decide** (pure): a finding per
   - `new_model`: a newer release in the same lineage (vendor + family, `jarvis/model_sync/ids.py`) as a pinned model;
   - `deprecation`: a pinned model on the deprecations table, with days left and a level (`notice` when first seen or more than 30 days out, `task` at 30 days or less, `urgent` at 7 days or less, `retired` after the date);
   - `cli_behind`: installed CLI older than npm latest, or not in Mortimer's verified set;
   - `codex_default_changed`: `model/list`'s default isn't the pinned Codex model.
3. **Certify** only a `new_model` (or a deprecation's replacement) that is new since the last run, once per candidate per CLI version:
   - exact-ID subscription probe (Claude or Codex), required;
   - Codex: `scripts/verify_subscription_capability.py` receipt, required;
   - voice pin: subscription voice bench, p50 ≤ 1.2 s and p90 ≤ 3.5 s over 5 short voice prompts (the `scripts/latency_probe.py` gates), required for the voice role;
   - Claude tool roles: the live receipt (`scripts/verify_claude_developer_capability.py --live`) is listed as a manual step in the PR, because it is gated on the pinned CLI.
4. **Propose** on a pass: one PR into `next` per candidate, editing the exact old ID to the exact new ID in the tracked config files that pin it, never an alias. It uses the GitHub REST API with `JARVIS_GITHUB_TOKEN` (else `GITHUB_TOKEN`); with no token it writes a patch under `data/status/model-sync/proposals/` instead. It never edits the Mac's checkout, never changes `.env`, and never switches a model. The voice model lives in `.env`, so a voice change is a written instruction, not a PR.
5. **Report:** `data/status/model-sync.json` (atomic), readable at `GET /api/status/model-sync`; one spoken notice after the next greeting when there is something new, an escalation step on a deprecation, or a PR. Nothing new, no notice.

`python scripts/sync_models.py` runs the same thing by hand (`--detect-only` skips probes, certification and PRs).

## 2. Module contracts (`jarvis/model_sync/`)

All results are JSON-serialisable dicts. Nothing raises out of the public functions; failures are recorded.

- `ids.py`: `parse`, `find_ids`, `is_newer`, `newest`, `same_model`.
- `sources.py`: `PUBLIC_SOURCES`, `fetch_public(name)`, parsers, `collect_public(fetch=...) -> {"sources": {name: {ok, error, fetched_at, sha256}}, "launches": [{model, vendor, date, source}], "deprecations": [{model, state, deprecated, retirement, replacement, source}], "cli_latest": {"claude": str|None, "codex": str|None}}`.
- `subscription_lists.py`: `collect_subscriptions(probe_aliases=True) -> {"claude": {"version", "aliases": {alias: {ok, model, models, category}}}, "codex": {ok, models: [{id, display_name, is_default, hidden}], default, error}, "kimi": {ok: False, category: "unsupported"}}`.
- `pins.py`: `collect_pins() -> {"models": [{model, file, line, context}], "voice": {model, source}|None, "cli": {"claude": [...], "codex": [...]}}`.
- `detect.py`: `detect(public, subs, pins, *, today) -> list[finding]`.
- `certify.py`: `certify(candidate, *, status_dir, ...) -> {model, steps: [{name, ok, detail}], passed, manual: [str]}`.
- `propose.py`: `propose(old, new, files, evidence, *, status_dir, ...) -> {status, url, branch, patch}`.
- `run.py`: `run_daily(status_dir, ...)`, state in `data/status/model-sync-state.json`.

## 3. Not verified here (run on the Mac)

The Claude alias probe through the restricted argv, `codex app-server` `model/list` on the ChatGPT login, the voice bench numbers, the Codex and Kimi pages' live formats (unreachable from the build container), and PR creation with the Mac's token. The Mac commands are in the PR.

## 4. Progress log

- 2026-11-23: built (this PR).
