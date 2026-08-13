# Hermes Agent Integration Plan

Status: **PARTIALLY IMPLEMENTED as of 2026-08-12. Phase 2 is live and verified. Phase 1 was attempted, found unsafe, and rolled back — Telegram gateway is stopped and its service uninstalled. Phases 3 and 4 were never started.**

## Implementation log (2026-08-12)

**Phase 1 — Telegram gateway: attempted, rolled back, not in use.**
All 4 low-risk MCP servers (`mortimer-time`, `mortimer-notes`, `mortimer-reminders`, `mortimer-system`) registered and verified connecting cleanly — that part of the design is sound and reusable. The gateway itself is not safe to run against a live Telegram bot yet:
- `hermes pairing approve` reads pending requests from the wrong internal storage path — confirmed by direct inspection of `~/.hermes/platforms/pairing/telegram-pending.json` vs. the CLI's lookup, which never found a record `list` plainly showed. Worked around via the `TELEGRAM_ALLOWED_USERS` env allowlist instead.
- `hermes tools disable ... --platform telegram` reported success and showed correctly "disabled" in `hermes tools list --platform telegram`, but the live gateway process still let a Telegram conversation invoke the built-in `terminal` and `code_execution` toolsets (ran `date` and raw Python respectively) — a real gap between reported config state and runtime enforcement, not a configuration mistake on our end.
- That same `code_execution` call also returned a system time off by several hours from the actual wall-clock time, independent of the enforcement bug.
- Net result: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` were removed from `~/.hermes/.env`, `hermes gateway stop` + `hermes gateway uninstall` were run, and no Telegram credential or launchd service remains active. Do not re-enable Telegram until Hermes's toolset-enforcement gap is confirmed fixed upstream (check Nous Research's GitHub issues/changelog first).

**Phase 2 — Cron: implemented and verified working.**
Deliberately built around the discovery that agent-mediated toolset scoping isn't trustworthy yet: the pilot job (`mortimer-daily-status`, id `a1b7973a9729`) uses `--no-agent` mode, which skips the LLM and tool-execution layer entirely. The script (`~/.hermes/scripts/mortimer_status.sh`) calls `mcp_servers/mcp_system/logic.py`'s `get_system_status()` directly via Mortimer's own project venv, with the project directory as an explicit `cd` target (not relying on Hermes's own interpreter/cwd resolution). Verified via `~/.hermes/cron/output/a1b7973a9729/2026-08-12_08-51-06.md`, which contains correct, real CPU/memory/disk/battery/uptime data. `hermes cron runs <job-name>` is unreliable (same display-value-isn't-the-lookup-key bug pattern as pairing) — use the job ID or `hermes cron list` to check status instead. The gateway process must be running for cron to tick (`hermes gateway install && hermes gateway start`), but is currently running with **zero messaging platforms enabled** (Telegram token removed), confirmed via `~/.hermes/logs/gateway.log` showing "No messaging platforms enabled" / "Gateway will continue running for cron job execution."

**Phases 3 and 4 — not started.** No net-new capability toolsets have been selected from the Phase 3 menu, and Phase 4 (skills) hardening was never begun. Both remain exactly as originally written below.

**Recommended pattern going forward:** any new automation should follow Phase 2's shape — `--no-agent` scripts calling Mortimer's own `logic.py` functions directly — rather than Phase 1's agent-mediated shape, until Hermes's enforcement bugs are resolved upstream.

---

## Purpose

Add Hermes Agent as an *additional*, optional interface layer alongside Mortimer — reachable via messaging platforms and cron — using Mortimer's existing MCP skill servers and Claude as the model. This does not replace, modify, or depend on any part of Mortimer's own bot pipeline, web console, or self-edit loop.

This plan is written to be executable by any model or engineer with no additional context beyond this document and the Mortimer `CLAUDE.md`. Every command is explicit. Every phase has its own rollback. Nothing is implied.

---

## 0. Non-negotiable guardrails (apply to every phase below)

These constraints exist because the original review flagged real security weaknesses in Hermes Agent's default configuration (CVE-2026-7396, CVE-2026-7397, CVE-2026-6829, plus 4 Critical / 9 High audit findings in unrestricted shell execution, unrestricted file read, and skill injection). The plan is deliberately scoped to avoid all of that surface area unless a phase explicitly says otherwise and gates it behind hardening steps.

1. **Hermes Agent is installed and configured entirely outside the Mortimer repo.** Its home is `~/.hermes/`. No step in this plan writes to, edits, or deletes anything inside `/Users/larryfix/Documents/jarvis-voice-ai-clean/`, including `.env`, `data/jarvis.db`, `config/*.yaml`, or any file under `jarvis/`, `mcp_servers/`, `web/`, or `scripts/`.
2. **Mortimer's MCP servers are consumed read-only, as external processes.** Hermes spawns its *own* subprocess copies of `mcp_servers/*/server.py` via `hermes mcp add`. This does not touch `config/mcp_servers.yaml` or the `SkillRegistry` Mortimer's own bot uses (`jarvis/skills/registry.py`). The two systems never share a running process.
3. **Mortimer's existing services are never started, stopped, or reconfigured by this plan.** That means the bot (`:7860`), the admin sidecar (`:7861`), the web console (`:5173`), and the wake-word sidecar (`:7862`) are out of scope entirely. If any step in this plan appears to require touching them, stop and flag it — that would be a plan defect, not something to work around.
4. **Every phase must end with a verification step that confirms Mortimer's existing stack is unaffected** — at minimum, `./scripts/run_bot.sh` (or `python3 -m jarvis.cli`) still starts cleanly and responds to a basic voice/text command exactly as it did before this plan was touched.
5. **Every phase is independently reversible.** Rollback instructions are given per phase and never require touching the Mortimer repo, because nothing in the Mortimer repo was touched.
6. **No secrets are ever written into this plan document or any file committed to the Mortimer repo.** Every command below uses a placeholder or a shell variable reference — substitute real values interactively in the terminal, never paste them into a file.
7. **`--yolo` mode is never used, at any point, in any phase.** It disables all of Hermes's approval/security checks wholesale.

---

## Phase 1 — Messaging gateway (Telegram first)

**Goal:** Reach Mortimer's own tools (time, notes, reminders, web search, system status) from a phone via Telegram, using Hermes as the bridge. Discord/Slack/WhatsApp follow the identical pattern once Telegram is proven — listed as Phase 1b, not built by default.

**Risk profile:** Low. The MCP servers registered in this phase (`mcp_time`, `mcp_notes`, `mcp_reminders`) have no filesystem-write-outside-DB, shell, or external-push capability. `mcp_web`, `mcp_git`, and `mcp_apps` are intentionally held back to 1c/1d since they carry search-cost, repo-write, and GitHub-push capability respectively.

### 1a. Prerequisites
- Confirm `hermes doctor` shows `✓ Anthropic API` (already true as of this session).
- Install optional messaging dependencies. Exact extras syntax should be confirmed at execution time via `hermes doctor` (it already names missing optional packages) — as of the last doctor run, `python-telegram-bot` was missing and `discord.py` was present:
  ```bash
  uv tool install --python 3.12 hermes-agent --with python-telegram-bot --with 'discord.py[voice]'
  ```
  (If `uv tool install --with` doesn't pick these up cleanly, fall back to `python3 -m pip install --user python-telegram-bot 'discord.py[voice]'` into the same environment `hermes doctor` reports as active.)

### 1b. Create the Telegram bot
- Larry does this manually via Telegram's BotFather (`/newbot`), and copies the resulting token. This is a human action — no tool can do this on your behalf.
- Add to `~/.hermes/.env` (append, do not overwrite the file):
  ```bash
  cat >> ~/.hermes/.env << 'EOF'
  TELEGRAM_BOT_TOKEN=<paste the real token here, not in this plan file>
  EOF
  ```

### 1c. Register Mortimer's low-risk MCP servers with Hermes
Repeat the pattern already proven working for `mcp_time`. Each command below must be run with the project's `.venv` path exactly as shown — do not substitute a different interpreter.

```bash
hermes mcp add mortimer-time --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_time.server"
```
*(Already done in the spike — skip if `hermes mcp list` shows it present.)*

```bash
hermes mcp add mortimer-notes --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_notes.server" --env JARVIS_DB_PATH=data/jarvis.db

hermes mcp add mortimer-reminders --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_reminders.server" --env JARVIS_DB_PATH=data/jarvis.db --env JARVIS_TIMEZONE=America/New_York

hermes mcp add mortimer-system --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_system.server"
```

For each `hermes mcp add`, when it prompts "Enable all N tools?", confirm `y` and read the discovered tool list against the corresponding `mcp_servers/<name>/server.py` file to confirm nothing unexpected was exposed.

### 1d. (Optional, higher risk — do not do without separate approval) Web, git, and app-dev servers
```bash
hermes mcp add mortimer-web --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_web.server" --env TAVILY_API_KEY=$TAVILY_API_KEY

hermes mcp add mortimer-git --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_git.server" --env JARVIS_DB_PATH=data/jarvis.db

hermes mcp add mortimer-apps --command /bin/bash --args -c "cd /Users/larryfix/Documents/jarvis-voice-ai-clean && exec .venv/bin/python -m mcp_servers.mcp_apps.server" --env GITHUB_TOKEN=$GITHUB_TOKEN --env GITHUB_OWNER=$GITHUB_OWNER
```
`mortimer-git` and `mortimer-apps` give a Telegram conversation the ability to push commits and create GitHub repos on Larry's behalf. Flag this explicitly at approval time — recommend leaving these out of Phase 1 entirely and revisiting only if there's a real use case for triggering git/GitHub actions from a phone.

### 1e. Access control
- Telegram: use Hermes's DM pairing flow (`hermes pairing`) so only Larry's Telegram account is authorized — do not leave the bot open to any user who finds it.
- If Discord is added later (1b'): set `DISCORD_ALLOWED_USERS=<Larry's numeric Discord user ID>` in `~/.hermes/.env`, per the existing Hermes docs.

### 1f. Start and verify
```bash
hermes gateway setup   # first-time interactive wizard
hermes gateway         # starts the gateway
```
- Send a test message from Telegram: "what time is it" → expect a `mcp_time`-derived, correct answer.
- Send: "what's in my notes" → expect a `mcp_notes`-derived answer (or a clean "no notes yet" if empty — not a hallucinated one).
- **Mortimer verification:** separately, in a terminal, run `python3 -m jarvis.cli` (or `./scripts/run_bot.sh`) and confirm it starts and responds normally. This confirms Phase 1 changed nothing about Mortimer's own stack.

### 1g. Rollback
```bash
hermes gateway stop
hermes mcp remove mortimer-time mortimer-notes mortimer-reminders mortimer-system
# (and mortimer-web / mortimer-git / mortimer-apps if 1d was done)
```
Remove the `TELEGRAM_BOT_TOKEN` line from `~/.hermes/.env`. Nothing in the Mortimer repo requires touching.

---

## Phase 2 — Cron / scheduled automation

**Goal:** Give Mortimer's tool ecosystem scheduled, unattended runs (e.g. a daily system-status check) — a capability Mortimer doesn't have today (its `ReminderWatcher` only fires on user-created reminders, not arbitrary scheduled agent tasks).

**Depends on:** Phase 1 completed (for a delivery target) — a cron job with no messaging gateway to deliver to just logs locally, which is still useful but less immediately visible.

### 2a. Confirm capability
```bash
hermes cron --help
```
Read the actual output before writing any job — the exact subcommand flags were not verified in the research/spike pass and must not be guessed. `croniter` is already confirmed present via `hermes doctor`.

### 2b. Define one pilot job (not more, until this is proven)
Example: a daily 8am system-status check, delivered to Telegram (once Phase 1 exists). The exact `hermes cron add` invocation should be constructed from the real `--help` output in 2a, targeting:
- Prompt: "Check mortimer-system's status tool and report CPU/memory/disk/battery/uptime."
- Toolset: `mortimer-system` only — no other MCP server needed for this job.
- Delivery: the Telegram gateway configured in Phase 1.

### 2c. Verify
- Confirm the job fires once on schedule (or trigger it manually if `hermes cron run <job>` exists) and produces a correct, tool-derived report.
- Confirm Mortimer's own `jarvis/bot/reminders_watcher.py` continues to operate unaffected — it reads `data/jarvis.db` on its own 30-second poll loop; Hermes's cron reads its own separate `~/.hermes/state.db`. The two never share state, so there is no collision to test for, only to confirm by inspection that no step above wrote to `data/jarvis.db` outside of the MCP servers' normal tool behavior.

### 2d. Rollback
```bash
hermes cron remove <job-name>
```

---

## Phase 3 — Net-new capability toolsets (menu, not a build — pick before proceeding)

These are capabilities Mortimer does not have today. None should be enabled by default; each requires its own external account/key and carries its own risk profile. Treat this as a menu — tell me which (if any) you want before any of this is implemented.

| Capability | What it needs | Notes |
|---|---|---|
| `image_gen` | Nous Portal subscription or an image-gen provider key | Net-new — Mortimer has no image generation today |
| `vision` | Provider key (varies) | Net-new — Mortimer has no image-understanding today |
| `homeassistant` | A running Home Assistant instance + long-lived access token | Only relevant if Larry runs Home Assistant |
| `spotify` | Spotify Developer app + OAuth | Net-new |
| `video` / `video_gen` | Provider key (varies) | Net-new, likely the most expensive per-use |
| `browser` / `browser-cdp` | `agent-browser` (Node.js) — `hermes doctor` shows this dependency already satisfied on Larry's machine, but the tool-availability check still reported it unmet; this discrepancy should be re-checked live (`hermes tools browser --help` or equivalent) before assuming it works, not assumed from this document | Enables autonomous web browsing — meaningfully expands attack surface (the CVE audit's shell/file findings are more relevant here than anywhere else in this plan) |
| `computer_use` | Platform-specific system permissions | Broadest attack surface of anything on this list — do not enable without a dedicated, separate risk review |

**No implementation steps are written for this phase.** Once you tell me which (if any) of these you actually want, I'll write a scoped sub-plan for just those, at the same level of detail as Phases 1–2.

---

## Phase 4 — Skills system (hardening-first; gated)

**Goal:** Evaluate Hermes's autonomous skill-creation/improvement loop — the most genuinely novel capability reviewed, and also the subsystem the CSA/Nous audit flagged as a Critical persistent-injection vector (agent-written skill files auto-load and execute in future sessions; the write sandbox is opt-in, not default).

**This phase does not start with a skill. It starts with hardening, and a skill is only added after 4a is fully verified.**

### 4a. Mandatory pre-conditions (must all be true before 4b)
1. Install Docker Desktop if not already present (`hermes doctor` currently shows `⚠ docker not found`).
2. Switch Hermes's execution backend from `local` to `docker`:
   ```bash
   hermes config set terminal.backend docker
   ```
   (Confirm the exact config key via `hermes config --help` / `hermes doctor` before running — don't assume the key name is exactly right without checking.)
3. Set a write-safe root so any tool/skill write is confined to an isolated directory, never the Mortimer repo or home directory broadly:
   ```bash
   mkdir -p ~/.hermes/sandbox
   echo 'HERMES_WRITE_SAFE_ROOT=/Users/larryfix/.hermes/sandbox' >> ~/.hermes/.env
   ```
4. Confirm `--yolo` has never been used (per guardrail 7, global to this plan).
5. Disable or avoid the automatic community skill curator (`hermes curator`) — only hand-authored, manually reviewed skills are permitted under this plan. Per the CSA audit, the highest-risk field in any skill manifest is `setup.commands` — read it in full before installing any skill, community or self-authored.

### 4b. Pilot skill (only after 4a is verified)
- One narrow, manually-authored, read-only skill — e.g., "summarize `mortimer-notes` output in bullet form" — with no `setup.commands` requiring shell execution.
- Verify the skill file is written only under `~/.hermes/sandbox` / `~/.hermes/skills/`, never inside the Mortimer repo.

### 4c. Rollback
```bash
hermes skills remove <name>
```
Skills live entirely under `~/.hermes/` by design — removal never touches Mortimer.

---

## Explicitly out of scope (skip — for traceability, not for implementation)

- **Hermes's own `web` search toolset** — redundant with Mortimer's existing `mcp_web` (Tavily-backed); would require a second, separate set of search-provider keys for no functional gain.
- **Hermes's own `tts` toolset** — redundant with Mortimer's existing ElevenLabs pipeline, which is already paid for and higher quality than Hermes's free defaults.
- **Hermes's `delegation`/subagent system as a replacement for Mortimer's Supervisor/sub-agent roster** — would duplicate and potentially conflict with the deliberate per-agent tool permissioning already defined in `config/agents.yaml`. Not proposed for removal or replacement anywhere in this plan.

---

## What needs your approval before any work begins

1. Which phase(s) to execute — Phase 1 and 2 are the low-risk recommendation; Phase 3 needs you to pick specific capabilities (or none); Phase 4 needs explicit go-ahead given it's the highest-risk item reviewed.
2. Within Phase 1: Telegram only, or Telegram + Discord (1b')? And do you want 1d (git/GitHub-capable servers) included, or held back?
3. Within Phase 4, if approved at all: confirmation you're willing to install Docker Desktop as a prerequisite, since local-backend skill execution is explicitly not recommended.

No command in this document has been run. Nothing changes until you say which phases to proceed with.
