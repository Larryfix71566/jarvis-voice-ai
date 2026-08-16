# Acceptance checklist — agent trust (tool-result honesty, local repo access, operational hygiene, procedures matching)

Manual checklist for `MORTIMER_AGENT_TRUST_PLAN.md`. Parts A–D (D1–D24) are
all implemented. Requires a live voice session (`./scripts/mortimer.sh`)
unless otherwise noted.

## Part A — tool-result honesty

- [ ] Temporarily break a tool a sub-agent would call (e.g. point
  `GITHUB_TOKEN` at an invalid value) and ask for something that requires
  it. Confirm the spoken/console reply does NOT describe data as if it
  were retrieved — it should say the call failed, not invent a plausible-
  sounding answer.
- [ ] With the same broken tool as the run's ONLY tool call, confirm the
  run's reply is the `ALL_TOOLS_FAILED` override, not the model's own
  wording — check `python -m jarvis.runlog --run <id>` for the injected
  `role: "system"` constraint message immediately after the failed
  `tool_result`.
- [ ] Run a task that calls two tools where only one fails (partial
  failure). Confirm the D4 all-failed override does NOT fire — the reply
  should still reflect whatever the successful tool returned.
- [ ] Check `sqlite3 data/jarvis.db "select tools_ok, tools_failed from
  agent_runs order by started_at desc limit 5"` — confirm real runs show
  non-NULL integers that match what actually happened, and that rows from
  before this migration show NULL (never a fabricated 0).
- [ ] Trigger an invalid `GITHUB_TOKEN` against `mcp-apps` (401/403) and
  confirm the error message explicitly does NOT mention the admin sidecar
  — this is the exact historical misdiagnosis D8 exists to prevent.
- [ ] Run `python scripts/check_env.py` with a dead `GITHUB_TOKEN`. Confirm
  it reports `[WARN]` (not `[PASS]`, not a required `[FAIL]`) and the
  overall `RESULT: PASS` is unaffected — GitHub is never a required check.
- [ ] Run `python scripts/check_env.py` with network access to
  `api.github.com` blocked. Confirm it reports `[WARN]` with
  "could not verify" wording, never `[PASS]` for something never actually
  reached.

## Part B — local repo access (mcp-repo)

- [ ] Ask the Developer sub-agent to read a file from the repo by a
  relative path (e.g. "read README.md"). Confirm it uses `repo_read_file`,
  not `app_read` (GitHub) — check the tool name in
  `python -m jarvis.runlog --run <id>`.
- [ ] Ask it to read `.env` or `.git/config`. Confirm the tool call is
  refused with a "not readable through this tool" error, and the refusal
  is spoken/shown, not silently swallowed.
- [ ] Ask it to write a new file. Confirm it calls `repo_write_file`
  first (nothing written yet), reads back a summary, and only calls
  `repo_commit_write` after explicit confirmation — same two-phase pattern
  as `mcp-git`'s commit flow.
- [ ] Ask it to overwrite `config/agents.yaml` or `CLAUDE.md`. Confirm the
  write is refused with "not writable through this tool (protected
  configuration)" at the `repo_write_file` preview step, before any
  confirmation is even asked for.
- [ ] Confirm a request to "create a new GitHub repo for this app" still
  routes to `mcp-apps`/`app_create`, not `mcp-repo` — the local/GitHub
  distinction in tool descriptions (D14) must not cause the reverse
  confusion either.

## Part C — operational hygiene

- [ ] Manually create a stale lock: `touch .git/index.lock`, then ask the
  Developer sub-agent to commit. Confirm the error names the lock path,
  its age, and the exact `rm` command — and that the file is NOT deleted
  automatically. Remove it manually afterward (`rm .git/index.lock`).
- [ ] Kill the bot process mid-delegation (e.g. `kill -9` while a sub-agent
  run is `status='running'`), then restart via `./scripts/mortimer.sh`.
  Confirm `sqlite3 data/jarvis.db "select run_id, status from agent_runs
  where run_id='<killed run id>'"` shows `orphaned` after the next
  startup, and check `logs/bot.log` for a `runlog_reconcile_orphaned`
  line.
- [ ] Start the admin sidecar (`./scripts/run_admin.sh`) and confirm
  `logs/admin.log` is non-empty within 5 seconds, containing at minimum
  an `admin_sidecar_startup` line with host/port/repo root.
- [ ] Trigger a self-edit run (`POST /api/selfedit/run` or via voice) and
  confirm `logs/admin.log` shows a `selfedit_state_transition` line for
  each state change (running → done/error).
- [ ] Hit a 5xx from the admin sidecar (e.g. a malformed request that the
  handler doesn't catch) and confirm an `admin_5xx` line appears in
  `logs/admin.log` naming the method and path.
- [ ] Trigger a display-worthy tool result (e.g. "what's the weather in
  Tokyo") and confirm `logs/bot.log` shows a `display_payload` line
  naming the tool, surface, agent, and kind.
- [ ] Change the voice from the console's picker. Confirm the voice
  actually changes (this is the only feature that flows through
  `app-message`) — this exercises the D19 deletion path.
- [ ] On a clean boot, confirm `grep -c ERROR logs/bot.log` returns `0`
  even when `deepfilternet`/`pyrnnoise` are not installed (should be
  `WARNING`, not `ERROR`).

## Part D — procedures matching

- [ ] Run `python -m jarvis.procedures --calibrate` and confirm it prints
  both populations' percentile tables and a branch decision, without
  raising, regardless of corpus size.
- [ ] Run `python -m jarvis.procedures --explain "<some real task text>"
  --agent developer` and confirm it lists every stored `developer`
  procedure with a score, shared tokens, and PASS/fail — including any
  pre-migration-0008 rows flagged as permanently unmatchable.
- [ ] Ask the same kind of question of the same specialist three times
  across separate sessions. Confirm a `candidate` procedure reaches
  `active` on the third success, and that its `task_tokens` column is
  non-empty (`sqlite3 data/jarvis.db "select label, task_tokens from
  procedures order by id desc limit 3"`).
- [ ] Confirm a fourth, similarly-worded request's sub-agent transcript
  shows the hint message injected — same check as before, now backed by
  task-shape matching instead of label/description matching.
- [ ] Confirm a request that is topically DIFFERENT from an existing
  procedure's task, but happens to share wording with that procedure's
  `label`/`description`, does NOT match — this is the D21 regression the
  old label+description scoring was vulnerable to.
