# Mortimer gap closure — the thirteen gaps from the 2026-09-04 architecture snapshot

**Status:** **IMPLEMENTED (code) 2026-09-04 — §8 VERIFICATION ALL BUT COMPLETE, 2026-09-05.** All GC items are in the tree: GC1b (`VALIDATE_PYTEST_TIMEOUT_S` 900), GC2 (REPO_MAP), GC3 (ROADMAP), GC4 (web freeze — **scope amended 09-05, see below**), GC5 (`bot/pipeline.py:1130`), GC6 (judge error string, `temperature: null`, `agreement.py:188`), GC7 (`backup_db.py`, `launchd_gen.py`), GC8 (`jarvis/tenant.py`), GC9 (migration 0021 + `reminder_notifier.py` + `notify.py`), GC10 (root `.wav` gone).

**§8 RESULTS (Larry's hardware, 2026-09-05).** §8.2 PASS. §8.4 **COMPLETE** — first backups ever, verified (`integrity_check ok`, 36/36 rounds, 414/414 runs); launchd live, five pids, both supervision proofs (`mortimer.sh` exits 3; killing the bot respawns it in <10 s); vault key exported off-machine. §8.5 **MEASURED** — voice $0.2239 vs LLM $0.3647, ratio **0.61**, so snapshot item 9 did NOT hold; but 09-03 measured 3-4x on a conversational workload, so it swings with the session and is n=1 both ways - do not buy hardware on it. §8.7 **COMPLETE** — `d6e0059b` replayed, five frontier judges, `superseded shadow rows: 20`, frontier abstention 0.4 -> 0.0. §8.8 **COMPLETE**. §8.9 **COMPLETE** — notified at +76 s while disconnected, spoken exactly once on reconnect. §8.10 **COMPLETE** — audit first: `git ls-files -- '*.wav'` returned nothing, so GC10's removal was already total and this step's `git rm --cached` had nothing to act on; cleared ~26 MB of `_to_delete` and `_to_delete_tarballs`, and added `Claude outputs/` to `.gitignore` since the desktop app writes downloads into the repo root on every save.

**PRECONDITION §8.4 DID NOT STATE, and it cost a broken install: the repo MUST NOT live under `~/Documents`.** That folder is TCC-protected. Terminal.app holds a grant — which is why `./scripts/mortimer.sh` always worked — but a launchd-spawned process inherits none and cannot even `getcwd` into the repo. The first install took the whole stack down with six jobs `loaded (idle)` and logs saying only `Operation not permitted`. The 03:15 backup would have failed identically, silently, forever. **Repo moved to `~/jarvis-voice-ai-clean`** rather than granting Full Disk Access to `/bin/bash` and `/usr/bin/python3`. The backup job now runs `/usr/bin/python3`, not uv's relocatable managed interpreter, with `test_backup_db_uses_only_stdlib` enforcing what makes that safe.

**GC4 SCOPE AMENDED 2026-09-05 (`634d629`).** As written, the freeze refused a goal whose paths were ALL under `web/`; a MIXED goal could still edit the deprecated client by naming one other file, and `test_mixed_goal_is_not_refused_by_this_rule` asserted that as correct. "Frozen except when bundled with other changes" is not frozen — and it was the only reason validation still had to build `web/`. `preflight` now refuses **any** goal naming a `web/` path, and the `npm ci` + `npm run build` stanza is gone from `validate()`. It had no gate at all, unlike the `core_imports` check directly above it; `node_modules/` is gitignored so a fresh worktree pulled the whole tree every run, up to 600 s twice before pytest started; and any npm failure for an environmental reason failed validation, exhausted the single auto-repair, and convened an E1 council over a component nobody runs.

**§8.6 TIMEOUT DECISION (Larry, 09-05): `VALIDATE_PYTEST_TIMEOUT_S` STAYS AT 900.** Do not treat the 52.8 s suite time as headroom. That is the warm, in-place, idle number; the gate runs pytest in a FRESH worktree with no `__pycache__`. A wall-clock test failed at 0.173 s against a 0.14 s bound purely because uv was installing packages, and the suite stretched 51 s -> 85.6 s under that load. Round `e48cfbe1` died on the old 300 s timeout and nobody ever established whether pytest or the frontend build consumed it. Collect timing from several successful self-edits first.

**STILL OPEN:** §8.3 speaker gate (offline); §8.6 self-edit half (staging TTL 600 s — re-stage and confirm promptly; use a `docs/` goal, `macos/**` never reaches validation); the GC6(d) edit itself (`config/upgrade_models.yaml` is human-only). **GC6(d) evidence says DEMOTE:** kimi-k3 produced 12 nulls in 24 rows (50%), alternating not trending — failed 08-23 x2, worked 08-30 x2, failed 09-01, worked 09-05 — while every other mid judge is at zero (or-gpt-5.1 0/24, or-grok-4.3 0/24, or-sonnet-5 0/20, claude-sonnet-5 0/4). **100% of mid-tier abstentions ever are kimi-k3.** Caveat: demotion moves it to the proposer pool rather than fixing it; a 50% timeout rate against one provider suggests the timeout is too tight for Moonshot, and GC6(a) means the next failure will finally carry a real error string.

**DEFECTS FOUND BY RUNNING THIS PLAN, none of them in it.** (1) `jarvis/council/__main__.py` never loaded vault credentials, so `--replay` — GC6(b)'s own repair tool — was dead since it was written; fixed `0084d23`. (2) Validation built the frozen web client on every self-edit; fixed `634d629` (above). (3) A barge-in during a delegation duplicated the next write — one store request produced two `delegate_task` calls and two notes; fixed `2a13857`. (4) `requirements.txt` line 1 had NO version pin, so the venv rebuild during the move resolved pipecat 1.8.1 and dropped the ElevenLabs SDK; pinned `54abcd6`. **This project has no `pyproject.toml` — `uv sync` does not work; rebuild with `uv venv --python 3.12` then `uv pip install -r requirements-lock.txt`.** Original header: DRAFT for Larry's approval, 2026-09-04.
**2026-09-10 re-audit (in progress).** This audit checks the implementation
against the current sandbox architecture; the 09-05 results above remain
historical evidence, not fresh acceptance of every subsequent change.

- GC1: the initial complete-suite attempt was deliberately interrupted after
  diagnosing repeated PyPI update checks in MCP startup. The diagnostic measured
  30.46 seconds with checks enabled versus 0.40 seconds disabled. Mortimer MCP
  services now default `FASTMCP_CHECK_FOR_UPDATES=off` at package initialization;
  dependency updates remain a maintenance action. The final candidate suite and
  two alternate-order runs remain required. Three MCP integration tests now
  restore their temporary database environment setting.
- GC1b: the effective full-unit gate moved to `sandbox/verify.py`. Both baseline
  and candidate backend checks retain 900 seconds; the other verification
  checks keep their existing budgets. The regression is now
  `sandbox/tests/test_verify.py::VerificationTests::test_mortimer_full_unit_gates_keep_900_second_timeout`.
- GC2: the repository map now names the VM controller and current workspace
  adapter, removes nonexistent app-build-agent references, and describes
  backup retention as 14 snapshots per database.
- GC5/GC9: transient announcement failures retry on the next poll instead of
  terminating the watcher. Failed reminder posts leave `notified_at` unset and
  do not prevent other reminders from being posted. Successful announcements
  retain their existing deduplication rules. Candidate regression checks pending.
- GC7: candidate backups publish a checked SQLite snapshot atomically, so a
  failed retry cannot overwrite a good same-minute backup. Sources open
  read-only and all connections close explicitly. Candidate WAL/failure tests pending.
- GC7/GC8 host evidence: read-only inspection of the closed 2026-09-10 03:15
  snapshots found six backups per database and `PRAGMA quick_check = ok` for
  both newest snapshots. All 15 non-FTS application tables and the cost-ledger
  table have `user_id TEXT NOT NULL DEFAULT 'local'`. This proves the saved
  snapshot schema; no live database or vault was modified.
- GC12: `JARVIS_KEYHEALTH_NOTICE_ENABLED=off` now disables construction,
  consistently with the reminder notifier. Expanded wiring tests pending.

**Author / origin:** Larry, 2026-09-04: *"build an implementation plan for the gaps you identified first. I want to close all the gaps and I want the plan to be run by Sonnet."* Scope decisions taken the same day: freeze `web/` now (MortimerHost is the daily driver); **full `user_id` on every table** with backfill `'local'`; fix the six standing test failures and raise the self-edit pytest gate to 900 s (never a fast subset — CI and the gate must agree).
**Roadmap constraints this plan is bound by:** C3 (nothing financial); K2 (no new MCP servers; one new optional env name declared where read); the self-edit deny tier — every step is a human PR.
**Contracts this plan INTRODUCES:** GC-T — the tenant column contract (§3 GC8): every table carries `user_id TEXT NOT NULL DEFAULT 'local'`; `jarvis.tenant.current_user_id()` is the one reader of `JARVIS_USER_ID`; `tests/unit/test_tenant_columns.py` fails when a future migration creates a table without the column. Consumed by the subscription track (unwritten) — this plan adds the column, **not** per-user filtering.
**Contracts this plan CONSUMES:** K2 — `JARVIS_USER_ID` is bridged into the bot's environment only; no MCP server declares it in this plan (GC8). `MORTIMER_GRAPH_LAYER_PLAN.md` GL9 (council `run_id` seam — gap 7c is closed there, not restated here); `MORTIMER_SESSION_MISSES_PLAN.md` §8 (gap 6's checklist — referenced, not restated).
**Two phases, two branches, in this order:** Phase A lands on `feat/t4a-security-hardening` and makes gap 1's PR mergeable; Larry merges; Phase B lands on `feat/gap-closure` cut from `main` afterwards. Phase B must not start before the merge — its migration numbers assume `0019` is the last on `main`.

**Corrections to the snapshot (verified against source while writing):**
- Snapshot §0 item 11 said a reminder due while no client is attached is "spoken never, not later". Wrong: `jarvis/bot/reminders_watcher.py:64-66` skips the tool call while disconnected precisely so `delivered` is not set, and the docstring (`:12-15`) says accumulated reminders are spoken on the first tick after reconnect. The real gap is narrower — **no notification reaches Larry while no client is attached** — and that is what GC9 closes.
- Snapshot §0 item 7 said the shadow-judge `temperature` failure is fixed in config "[likely]". The corrupting rows are from ONE round (`d6e0059b`, 2026-08-23) and no shadowed round has run since `temperature: null` landed; the fix is unverified, and the historical rows still poison `--agreement`. GC6 closes both halves.
- Snapshot §0 item 2 said the six failures make the self-edit gate unpassable. Five of the six live under `tests/integration/`, which neither the gate (`pytest tests/unit`) nor CI's `Unit tests` step runs — so the gate was broken by the 300-s timeout, not by those failures. GC1 still fixes all six (they are real order-dependence bugs); GC1b fixes the gate.
- Snapshot §0 item 2's "6 standing failures" appear in Larry's real-venv full runs (`6 failed / 2156 passed`, 2026-09-03); memory from 09-03 also records some of them passing in the full run and failing in isolation. Both cannot be true of the same suite on the same day — GC1's procedure starts by establishing which is true today rather than assuming.

---

## §0 Binding constraints for the implementing model

1. **Git.** If you are running natively on Larry's Mac (a terminal or Claude Code in the checkout), read-only git is allowed: `git status`, `git ls-files`, `git log`, `git diff`. **Never** `git add`, `commit`, `checkout`, `rm`, `stash`, or `push` — Larry commits, using the lists in §12. If you are running through the Cowork device shell or a cloud sandbox with the repo mounted, run **no git command at all**, not even `git status` — it leaves an unremovable `index.lock` (six incidents). If you are unsure which you are, you are the second case.
2. **Run `pytest tests/unit tests/integration -q` before every checkpoint.** After GC1 the expected result is 0 failures; until GC1 is done, report the exact failing names against the six in §1.
3. **Backups before migrations.** GC7's backup script must exist and have been run once by Larry (§8.4) before GC8's migration is applied to `data/jarvis.db`. The plan's step order enforces this; do not reorder.
4. **No new process, no new port, no new MCP server.** The launchd agents wrap the six existing `run_*.sh`/`run_kb.sh` scripts.
5. **Kill switches are read in exactly one place each**, named in §6.
6. **Every number lives in §6.**
7. **Nothing in this plan filters reads or writes by `user_id`.** GC8 adds the column and the contract only. If you find yourself adding `WHERE user_id = ?`, stop — that is the subscription track's work.
8. **`macos/**`, `config/upgrade_models.yaml`, `config/skills.yaml`, `config/upgrade_agent.yaml`, `config/self_edit_allowlist.json`, `.github/**` are human-only.** GC6's kimi-k3 tier change and GC10's `git rm --cached` are written as Larry's commands, not yours.
9. Where a claim cites `path:line`, lines are from `baa9838`. If the text has moved, search for the quoted text; if it is gone, stop and report.
10. **Docs are regenerated from the tree, not from memory.** GC2's `REPO_MAP.md` is written from a fresh `find`/`ls` of the repo you are in, and stays under `REPO_MAP_MAX_CHARS` (`jarvis/repo_map.py:18`, 8,000) — `load_repo_map_suffix` truncates anything longer silently.

## §1 What exists today (verified, path:line) and the gap, per item

| # | Gap (snapshot §0) | What exists | Owner in this plan |
|---|---|---|---|
| 1 | 49 commits on `feat/t4a-security-hardening` never merged or CI'd; `main` @ `47f674c` | `.github/workflows/validate.yml` runs only on `pull_request` to `main` (`:1-3`); gates: allowlist → import smoke → `pytest tests/unit -q` → `tests/evals/sub_agent_evals.py` → latency budget → `npm run build` | **Larry** (§8.1), after Phase A |
| 2 | Self-edit gate 4 probably unpassable: `pytest tests/unit -q` with `VALIDATE_PYTEST_TIMEOUT_S = 300` (`jarvis/selfedit/service.py:51`, used `:561-563`) against ~2,156 tests with 6 standing failures; the self-edit run that convened council round `e48cfbe1` died on "pytest: timed out after 300s" | the six: `tests/integration/test_bot_wiring.py` ×4, `tests/integration/test_procedures_end_to_end.py` (one), `tests/unit/test_registry.py` (one) — five of six live under `tests/integration`, so the self-edit gate and CI's `Unit tests` step (both `tests/unit` only) never saw them; the 300-s timeout, not the failures, is what broke the gate | **Sonnet** GC1 |
| 3 | `docs/REPO_MAP.md` (5,185 chars) and `CLAUDE.md` (edited 09-01) name none of `usage_ledger`, `costs_api`, `memory_extraction*`, `kb_digest`, `effort`, `anthropic_shim`, `sensitive*`, `usage_watcher`, `mcp_kb` | `REPO_MAP.md` injected into developer + UpgradeAgent prompts via `load_repo_map_suffix` (`jarvis/repo_map.py:21`) | **Sonnet** GC2 |
| 4 | Web/Swift divergence: Costs tab and council roster are Swift-only; `web/` still launched by `scripts/mortimer.sh:111-112,132,136` | `web/src/components/SideDrawer.tsx:33-40` `TabKey` has seven tabs; `MortimerHost` builds and passes tests (09-03) | **Sonnet** GC4 (freeze) |
| 5 | Single-key blast radius on `ANTHROPIC_API_KEY`, refuse mode, no degraded-mode announcement | `jarvis/keyhealth.py` `verdict()/detail()/is_unusable()` (`:74-90`), background probe at boot (`:169`); `SubAgent.model_unusable` (`jarvis/agents/base.py:310`) reddens the chip; a refused delegation IS spoken (`REFUSED:` string) but only when one is attempted | **Sonnet** GC5 |
| 6 | Session Misses §8 verification + speaker-gate `verify --windowed` unrun | stack restarted 16:12 EDT 09-03, no session since (`logs/bot.log` is the startup banner) | **Larry** (§8.2–8.3) |
| 7 | Council data: (a) `kimi-k3` abstained on every proposal in 3 rounds (`57fe41f0` 08-23, `d6e0059b` 08-23, `e48cfbe1` 09-01) with `abstain_reason = "judge call failed: "` — empty because `asyncio.TimeoutError` stringifies empty at `jarvis/council/council.py:497-504`; (b) both Anthropic shadow judges 400'd on `temperature` in round `d6e0059b` (shadow=1 rows), and `agreement.py` reads those rows (`_rows_for_round`, `:92-96`); (c) `council_rounds.run_id` NULL everywhere | (c) is `MORTIMER_GRAPH_LAYER_PLAN.md` GL9 | **Sonnet** GC6 for (a)(b); (c) by reference |
| 8 | No process supervision (`nohup` + 6-s liveness check, `scripts/mortimer.sh:117-134`); backups are hand-copied `.bak` files (`data/jarvis.db.bak-*`, `costs.db.pre-purge-*`) | `scripts/run_*.sh` each `exec` their process; `run_kb.sh` execs `mortimer-vault serve`; `run_bot.sh` is started behind `wait_for.sh` (`mortimer.sh:105`) | **Sonnet** GC7; Larry installs (§8.4) |
| 9 | TTS is the larger cost line [n=1] | `scripts/cost_report.py:136-147` already prints the voice-transport section; `GET /costs/summary` carries `voice_usd` | **Larry** measures (§8.5); no code |
| 10 | Single-tenant: no `user_id` anywhere in `jarvis/db.py`; `JARVIS_USER_NAME` is a display name | 16 tables (`grep CREATE TABLE jarvis/db.py`); `memories` has `UNIQUE INDEX idx_memories_fact_key ON memories(key) WHERE kind='fact'` (`:74`) and `upsert_fact` uses `ON CONFLICT(key) WHERE kind = 'fact'` (`jarvis/memory.py:672-673`); `costs.db`'s `llm_calls` owns its own schema in `jarvis/usage_ledger.py:_conn` (`:169-200`, in-place `ALTER` pattern) | **Sonnet** GC8 |
| 11 | T2/T5/T3/T6 have no code; reminders unreachable while no client attached | own plans (`MORTIMER_REMOTE_ACCESS_PLAN.md`, `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md`, `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md`, `MORTIMER_SKILL_AUTHORING_PLAN.md`); reminders: `get_due_reminders` marks delivered atomically (`mcp_servers/mcp_reminders/logic.py:239-252`); `reminders.delivered` column (`jarvis/db.py:34`) | tracks by reference (§3 GC11); reminders **Sonnet** GC9 |
| 12 | Doc drift: root `ROADMAP.md` (08-18) still says "Electron-first wrapper, never a rewrite"; approved plans still read DRAFT; two things named "vault"; `Procfile` TODO | status lines listed in §5 step 3 | **Sonnet** GC3 |
| 13 | Hygiene: `s1.wav s2.wav s3.wav tv.wav` at root, `testrmdir/`, `zzz_test_old/`, `_to_delete_tarballs/`, `web/dist_verify*/`, stale `.overmind.sock`, `.env.bak-haiku` (keys commented out — verified) | `.gitignore` ignores `_to_delete/`, `_to_delete_tarballs/`, `.env.*`; does NOT ignore `*.wav` | **Sonnet** GC10; Larry deletes |

## §2 Non-goals

- No per-user filtering, auth, or session→user binding (subscription track). No `users` table beyond the column contract.
- No web (`web/src`) feature work; the freeze is the point. `web/` is not deleted (T1.4 owns that after G1(e)).
- No change to the council's pool membership by code (`config/upgrade_models.yaml` is human-only); the kimi-k3 edit is Larry's, given verbatim.
- No local TTS/STT, no Mac mini work, no T2/T3/T5/T6 implementation — those plans stand.
- No rewriting of CLAUDE.md's existing paragraphs; GC2 adds and corrects, it does not condense.
- No `xfail`/`skip` on any of the six failing tests.
- No new drawer tab, panel, or UI for the degraded-mode notice — it is spoken once and logged.

## §3 Decisions

**GC1 — Fix the six failures by finding the polluter, never by quarantining.** Procedure (deterministic; run on Larry's real venv):
1. `pytest tests/unit tests/integration -q -p no:randomly 2>&1 | tail -40` (the command that produced "6 failed / 2156 passed") → record the failing set F.
2. For each `t ∈ F`: `pytest "<t>" -q`. Record ALONE = pass|fail.
3. If ALONE = fail: the test is wrong or the code is wrong on its own. Read the assertion; if it asserts a value that a later plan changed (e.g. a count, a rule number, a constant), update the assertion to the current truth and cite the plan that changed it in a comment; if the code is wrong, fix the code. No third option.
4. If ALONE = pass: it is order-dependent. Find the polluter by bisection over the files collected before `t` (unit first, then integration): `pytest <first half of those files> "<t>" -q`; halve the prefix until one file P makes `t` fail. In P, look for (in this order) `os.environ[...] =` without `monkeypatch.setenv`, a module-level singleton mutated without reset (`jarvis.keyhealth` has `reset_for_tests()` `:92` — the model to copy), `sys.modules` edits, a global `SkillRegistry`/`Settings` instance cached by `functools.lru_cache`, or a file written under the repo root. Fix P so it cleans up (`monkeypatch`, a `reset_for_tests()` you add beside the singleton, `tmp_path`). Never fix `t` to tolerate the pollution.
5. Repeat step 1 until F is empty; then run the full suite twice more with a different seed (`-p randomly` if installed, else reverse file order via `pytest $(ls -r tests/unit/test_*.py) -q`) — both must be 0 failures. Gate for every later step and for §8.1: `pytest tests/unit tests/integration -q` → 0 failed (the gate and CI run the unit subset by design; the full command is the plan's bar).
*Why:* a gate that reads "6 failed" is a gate nobody trusts, and every one of these order-dependence bugs is a real shared-state bug in the code under test.

**GC1b — `VALIDATE_PYTEST_TIMEOUT_S` 300 → 900** (`jarvis/selfedit/service.py:51`) and CI is unchanged. Measured suite time on Larry's Mac is recorded in §8.6; if it exceeds 600 s the plan's number stands and Larry is told, because the alternative (a subset) is forbidden by CLAUDE.md's "must not disagree about what passing means".

**GC2 — `docs/REPO_MAP.md` is regenerated from the tree and kept under 8,000 chars; `CLAUDE.md` gains one paragraph per undocumented subsystem.** REPO_MAP: keep its first 8 lines (the "may lag reality" preamble), then rewrite "Top-level layout" and the per-package sections from `find jarvis mcp_servers scripts config docs macos web/src tests -maxdepth 2` — one line per module, ≤ 90 chars, module name + purpose in ≤ 10 words. Must list: `jarvis/usage_ledger.py`, `costs_api.py`, `memory_extraction.py`, `memory_extraction_worker.py`, `kb_digest.py`, `effort.py`, `anthropic_shim.py`, `sensitive.py`, `bot/sensitive_turn.py`, `bot/usage_watcher.py`, `bot/late_result.py`, `bot/costs_tool.py`, `tenant.py` (GC8), `mcp_servers/mcp_kb`, `scripts/cost_report.py`, `scripts/pull_openrouter_activity.py`, `scripts/backup_db.py` (GC7), `scripts/launchd_gen.py` (GC7). Verify with `python -c "from pathlib import Path; from jarvis.repo_map import load_repo_map_suffix as f; assert len(Path('docs/REPO_MAP.md').read_text()) <= 8000; s=f(); assert 'usage_ledger' in s"` (the suffix adds an ~85-char header AFTER the cap, `repo_map.py:34-41`, so the file length is the number that matters). CLAUDE.md: append under "## Architecture" five paragraphs titled **Usage ledger and costs**, **Memory extraction worker (Phase 2)**, **Effort control and the native Anthropic paths**, **Knowledge-base service (mcp-kb)**, **Sensitive-turn suppression (T4a)** — each ≤ 12 lines, each naming the module, the kill switch, the plan that introduced it, and the one thing a future editor must not do (copied from that plan's own "never" sentence). Also correct the CI sentence at `CLAUDE.md:69` ("currently non-blocking") to "blocking", which `validate.yml` and `CLAUDE.md:97` already say. *Why:* the developer's 25-iteration budget exists because it rediscovered the tree; a map that omits Phases 0–4 recreates the problem it was built to solve.

**GC3 — Doc drift closed by edits with dates, never by deletion.** Root `ROADMAP.md`: replace the "Native macOS shell (Electron-first wrapper, never a rewrite)" bullet with "Native macOS client: SUPERSEDED 2026-08-25 by the full-Swift decision (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` T1, `docs/plans/MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`)". Plan status lines: `MORTIMER_PLATFORM_ROADMAP.md` → "**Status:** APPROVED by Larry 2026-08-26 (was DRAFT); track plans written 2026-08-26/27."; `MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md` → "**Status:** APPROVED and IMPLEMENTED 2026-08-22 (F1–F11); §6 effectiveness protocol still unrun — gate off."; `MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md` → "**Status:** IMPLEMENTED 2026-08-22 (G1–G12)."; `MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md` → check `tests/acceptance/confirmation-and-capability.md` exists (it does) and `jarvis/bot/display.py` carries the `tool` field (it does, `:157-164`) → "**Status:** IMPLEMENTED (acceptance checklist in tests/acceptance/)."; `MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md` → CLAUDE.md documents W1–W8 as built → "**Status:** IMPLEMENTED 2026-08-22 (W1–W8, see CLAUDE.md)."; `MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md` → "**Status:** IMPLEMENTED 2026-08-21/22; Tier 2 gate OFF pending §6."; `MORTIMER_RESUME_PLAN.md` → "**Status:** SUPERSEDED 2026-08-21 by the reliability overhaul (barge-in survival, CLAUDE.md)". `Procfile`: replace the TODO line with "# vault: = the KNOWLEDGE-BASE service (~/mortimer-vault, :8484), not jarvis/vault.py (the secrets vault). Names collide; see CLAUDE.md 'Two vaults'." CLAUDE.md gains a two-line **Two vaults** note under Known deviations. *Why:* a plan whose header lies is read by the next planner (human or model) as current state — that is how the snapshot's own author got item 11 half wrong.

**GC4 — Freeze `web/`: not launched, not deleted, not extended.** `scripts/mortimer.sh`: remove the `run_web.sh` launch, its `rotate_log web`, its `check web` line and the "Open http://localhost:5173" line; replace the final echo with "Open MortimerHost (macos/MortimerHost, `swift run` or Xcode). Web console fallback: ./scripts/run_web.sh". `Procfile` comment gains "web: (frozen 2026-09-04 — run_web.sh by hand only)". `web/README.md` (create if absent) top line: "**FROZEN 2026-09-04.** No new features; MortimerHost is the daily driver (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` G1(e) clock starts at this commit). Deleted by T1.4." `config/self_edit_allowlist.json` is human-only, so the allowlist entry `web/src/**` stays; instead `SelfEditService.preflight` (`jarvis/selfedit/service.py`, `def preflight`) gains one rule inserted immediately after `tiers = self.allowlist.classify(paths)` (literal): `if paths and all(p == "web" or p.startswith("web/") for p in paths): result.update(ok=False, error="web/ is frozen (2026-09-04): interface work goes to macos/MortimerHost, which is a human PR."); return result` — `paths and` keeps a goal naming no files passing (`test_goal_naming_no_files_passes_through`), and `result` still carries `tiers` because `server.py:795` reads `flight["tiers"]` on refusal. Two existing tests assert a web goal passes and must change their goal to `docs/README.md`: `tests/unit/test_selfedit_service.py::test_routine_goal_passes_without_plan` and `tests/unit/test_admin_selfedit.py:487`. `web/README.md` EXISTS (Vite template text): prepend the freeze paragraph above its first line. `mortimer.sh`'s `stop_all` keeps `pkill -f "vite"` (`:46`, a hand-started `run_web.sh` must still stop) and `logs` keeps tailing `logs/web.log` (`:71`, `tail -f` tolerates a missing file). G1(e)'s five-day clock: Larry records the start date in `web/README.md` when he merges. *Why:* the divergence already exists; a second UI is only worth maintaining if it is the one being used, and the decision was made on 08-25.

**GC5 — Degraded mode is announced once per session and documented as an accepted risk.** New `jarvis/bot/keyhealth_notice.py`: `KeyHealthNotice(inject: InjectFn, agents: list[SubAgent], is_connected: ConnectedFn, interval_s=KEYHEALTH_NOTICE_INTERVAL_S)` modeled on `RemindersWatcher` (start/stop/tick_once). `tick_once`: if not connected → return; compute `unusable = sorted({(a.name, a.model_unusable_detail) for a in agents if a.model_unusable})`; if `unusable` and `unusable != self._last_spoken`: inject `KEYHEALTH_TEMPLATE.format(agents=", ".join(names), detail=<first detail>)` and set `_last_spoken = unusable`; if `unusable` is empty and `_last_spoken` was non-empty: inject `KEYHEALTH_RECOVERED_TEMPLATE` and clear. Templates (`jarvis/prompts.py`, beside `CONTEXT_TEMPLATE`'s siblings): `KEYHEALTH_TEMPLATE = "[system] These specialists cannot run right now — the provider refused their API credential ({detail}): {agents}. Tell the user once, briefly, and do not delegate to them until told otherwise."` (`detail` is `keyhealth.detail()`'s free-form probe message, e.g. `HTTP 401 …`, truncated to 120 chars); `KEYHEALTH_RECOVERED_TEMPLATE = "[system] Specialist credentials are working again. Tell the user briefly."` Wiring: `sub_agents` is a local of `build_pipeline` (`pipeline.py:359`) and not reachable at `:1114`, so `Runtime` (`:133`) gains `sub_agents: dict = field(default_factory=dict)` and `keyhealth_notice: Any = None`; set `runtime.sub_agents = sub_agents` immediately after `:359`; in `run_session` beside `RemindersWatcher` (`:1114-1117`) construct `KeyHealthNotice(inject=inject_context, agents=list(runtime.sub_agents.values()), is_connected=lambda: client_connected["value"])`, assign it to `runtime.keyhealth_notice`, `start()` it, and `await runtime.keyhealth_notice.stop()` in the session `finally` (`:1264`) beside the watcher's stop. Kill switch `JARVIS_KEYHEALTH_NOTICE_ENABLED` (default true) read once in `run_session` exactly where `JARVIS_PROGRESS_UPDATES_ENABLED` is read; off → not constructed, `runtime.keyhealth_notice` stays `None`. Scope: **once per connection** — `_last_spoken` lives on the instance, the instance lives with the session, so a reconnect re-announces a still-broken key by design (a user reconnecting has not necessarily heard the earlier sentence). CLAUDE.md gains a paragraph **Single-key blast radius (accepted risk, 2026-09-04)** stating: one `ANTHROPIC_API_KEY` carries voice, five specialists, developer, planner default, vision and extraction; refuse mode is deliberate (model floor); the announcement is this notice; the mitigation on the table is a second direct route for the mid tier, which Larry has not chosen. *Why:* the chip is red only when the drawer is open; a spoken sentence is the only surface a voice user reliably has.

**GC6 — Council data quality.** (a) `jarvis/council/council.py:497-504` and the matching proposer branch (`:416`): `abstain_reason=f"judge call failed: {type(exc).__name__}: {exc}"` — an empty `str(exc)` can no longer erase the cause; same for the proposer failure log line. (b) `jarvis/council/agreement.py::compute_agreement` (`:182`), immediately after the planning-round filter at `:203` and BEFORE any metric reads `score_rows` (`_abstention_rate_by_tier`/`_discrimination_by_tier` at `:272-273` read the raw rows, so a dedup inside `_rows_for_round` alone would leave the poisoned abstentions counted): among rows with the same `(round_id, judge_profile, proposal_label, shadow)`, keep only the row with the greatest `created_at` (a `--replay` writes fresh `shadow=1` rows for a judge; the newest supersedes the failed original by construction); `AgreementReport` gains `superseded_shadow_rows: int = 0` set to the number dropped. (c) `_do_agreement` (`jarvis/council/__main__.py:217`) prints one line `superseded shadow rows: {report.superseded_shadow_rows}`. (d) kimi-k3: **Larry's decision at approval** — default is keep; the one-line alternative is `tier: mid` → `tier: economy` on the `kimi-k3` profile in `config/upgrade_models.yaml` (human-only), which removes it from the mid judge pool without deleting it. The plan does not make that edit. *Why:* (a) is the bug that hid a dead judge for two weeks; (b) is what makes the historical corruption repairable by the CLI that already exists (`--replay d6e0059b --judges frontier`, §8.7) instead of by hand-editing rows.

**GC7 — Backups and supervision, both file-driven, both installable by one command.**
- `scripts/backup_db.py`: for each of `data/jarvis.db`, `data/costs.db` → `sqlite3.connect(src).backup(sqlite3.connect(dst))` (stdlib, WAL-safe) into `data/backups/<name>.<YYYYMMDD-HHMM>.db`; then `python -m jarvis.vault export-key` is NOT run automatically (it prints a secret) — the script prints a reminder instead; prune to `BACKUP_KEEP` newest per db; exit non-zero on any failure. No secrets touched.
- `scripts/launchd_gen.py`: writes `~/Library/LaunchAgents/com.mortimer.<svc>.plist` for `svc ∈ {vault, bot, extractor, admin, costs, backup}` from one template (literal in §5 step 8): `ProgramArguments` = `["/bin/bash","-c","cd <repo> && ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && exec ./scripts/run_bot.sh"]` for bot, `exec ./scripts/run_<svc>.sh` for the others (`run_kb.sh` for vault), `["<repo>/.venv/bin/python","scripts/backup_db.py"]` with `StartCalendarInterval {Hour: 3, Minute: 15}` for backup; `KeepAlive true` + `RunAtLoad true` for the five services; `StandardOutPath`/`StandardErrorPath` → `<repo>/logs/<svc>.launchd.log`; `WorkingDirectory` = repo; `EnvironmentVariables` = `{"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"}` only (secrets come from the vault at process start, as today). `--install` runs `launchctl bootstrap gui/$UID <plist>` per file; `--uninstall` runs `bootout`; `--status` runs `launchctl print gui/$UID/com.mortimer.<svc>` and prints running/not for each.
- `scripts/mortimer.sh`: at the top of `start` and `stop`, `if launchctl print "gui/$(id -u)/com.mortimer.bot" >/dev/null 2>&1; then echo "Mortimer is under launchd — use: python scripts/launchd_gen.py --status | --uninstall, or launchctl kickstart -k gui/$(id -u)/com.mortimer.bot"; exit 3; fi`. Two managers never fight over the same processes.
*Why:* KeepAlive is hardware-independent; the mini move changes nothing about it. Backups are a two-line stdlib call; the reason they don't exist is that nobody wrote the two lines.

**GC8 — Tenant column on every table (contract GC-T).** `jarvis/db.py` `MIGRATION_0020_user_id` (literal in §5 step 9), wrapped in `BEGIN; … COMMIT;` because `run_migrations` runs `executescript` and records the id only after success (`db.py:609-614`) — without the transaction a mid-script ALTER failure would leave earlier columns added and `0020` unrecorded, and every later boot would die on "duplicate column name": `ALTER TABLE <t> ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'` for every table except `migrations`; then `DROP INDEX idx_memories_fact_key; CREATE UNIQUE INDEX idx_memories_fact_key ON memories(user_id, key) WHERE kind = 'fact';` and `jarvis/memory.py:672-673` `ON CONFLICT(key) WHERE kind = 'fact'` → `ON CONFLICT(user_id, key) WHERE kind = 'fact'` (the INSERT does not set `user_id`, so the DEFAULT applies and behaviour is unchanged — pinned by a test). `jarvis/usage_ledger.py:_conn` gains the same in-place `ALTER` for `llm_calls`. New `jarvis/tenant.py`: `DEFAULT_USER_ID = "local"`, `current_user_id() -> str` reading `JARVIS_USER_ID` (strip; empty → default; validated `^[a-z0-9][a-z0-9_-]{0,63}$` else default with one WARNING). `jarvis/config.py` gains `jarvis_user_id: str = "local"` beside `jarvis_user_name` (`:82`), and `bridge_settings_to_env` (`:265-272`) gains `os.environ.setdefault("JARVIS_USER_ID", settings.jarvis_user_id)` beside the `JARVIS_UNITS` line, with `JARVIS_USER_ID` added to the `_dotenv_values` fallback name list (`:288`) — so the bot process sees it the way it sees `JARVIS_UNITS`. MCP children do NOT see it yet: K2 forwards only `BASE_ENV_KEYS` (`registry.py:49`) plus declared `optional_env`, and no server declares it — that declaration is the subscription track's, made per server when a server first needs the value. No code in this plan calls `current_user_id()`; it exists so the reader has one home. `tests/unit/test_tenant_columns.py`: after `run_migrations`, every table in `sqlite_master` except `migrations`, names starting with `sqlite_` (`sqlite_sequence` exists in every DB with AUTOINCREMENT), and `*_fts*` has a `user_id` column with `dflt_value = "'local'"` and `notnull = 1` — a future migration that creates a table without it fails this test. `test_db.py`'s `EXPECTED_MIGRATION_IDS` gains `0020_user_id` (and `0021_reminders_notified`, GC9). FTS virtual tables (`conversations_fts`, `procedures_fts`) are external-content over columns that do not change — untouched. *Why "column only":* Larry chose full coverage now so that no table added between now and the subscription track lacks the key; filtering is the track's work and would need auth first (T2).

**GC9 — Reminder notification while no client is attached.** The bot's `RemindersWatcher` cannot do this: it is built inside `run_session` (`jarvis/bot/pipeline.py:1114`) and stopped in that session's `finally` (`:1264`), and `run_session` runs per WebRTC connection (`jarvis/bot/bot.py:44`) — while no client is attached there is no watcher at all. The persistent process is the admin sidecar, which already imports `mcp_servers.mcp_reminders.logic` in-process for `/api/ambient` (`jarvis/admin/server.py:1383`). So: `MIGRATION_0021_reminders_notified`: `ALTER TABLE reminders ADD COLUMN notified_at TEXT;`. `mcp_servers/mcp_reminders/logic.py` gains two plain functions (NOT tools — no `server.py`/`skill.yaml`/`TOTAL_TOOLS` change): `peek_due_reminders(grace_s: float) -> dict` returning `{"reminders": [{"id": int, "message": str, "due_at": str}]}` for `status='pending' AND due_at <= (now − grace_s) AND delivered = 0 AND notified_at IS NULL ORDER BY due_at ASC`, and `mark_notified(ids: list[int]) -> dict` returning `{"marked": N}` after `UPDATE reminders SET notified_at = ? WHERE id IN (...)` — `delivered` untouched. New `jarvis/admin/reminder_notifier.py`: `ReminderNotifier(interval_s=REMINDER_NOTIFY_INTERVAL_S, grace_s=REMINDER_NOTIFY_GRACE_S, post=post_notification)` — a daemon `threading.Thread` with `start()`, `stop()` (sets an `Event`), and `tick_once()` (public, never raises): `rows = logic.peek_due_reminders(grace_s)["reminders"]`; for each: `if self._post(row["message"]): logic.mark_notified([row["id"]])`. Started at module top of `jarvis/admin/server.py` next to the existing background-thread slots, only when `JARVIS_REMINDER_NOTIFICATIONS_ENABLED` (read once there) is true. The grace (`REMINDER_NOTIFY_GRACE_S = 60`, §6) is what prevents a double signal: a connected bot's watcher polls every 30 s and marks `delivered = 1` first; the sidecar only notifies reminders that have been due for a full minute with nobody having spoken them. `delivered` stays 0 after a notification, so the reminder is still spoken on the next connect (the watcher docstring's promise holds). `post_notification(message: str) -> bool` in new `jarvis/notify.py` (literal in §5 step 10): `osascript -e 'display notification "<msg>" with title "Mortimer"'` as fixed argv, never a shell (the `pbcopy` precedent, CLAUDE.md handoff loop); the message is truncated to `NOTIFY_MAX_CHARS` and AppleScript-escaped (`\` → `\\`, `"` → `\"`); returns `returncode == 0`; on any exception logs and returns False (then `mark_notified` is NOT called, so it retries next tick). Adversarial cases the test must pass: message `he said "hi" \ bye` → argv element 3 is exactly `display notification "he said \"hi\" \\ bye" with title "Mortimer"`; a 600-char message is truncated to `NOTIFY_MAX_CHARS`; `osascript` missing (`FileNotFoundError`) → False, no exception, `mark_notified` not called. *Why the sidecar:* it is the one always-on process on the Mac that already talks to the reminders table; the bot's watcher semantics are untouched.

**GC10 — Hygiene by moving, never deleting.** Sonnet: `mkdir -p _to_delete/2026-09-04` and `mv` there: `s1.wav s2.wav s3.wav tv.wav testrmdir zzz_test_old web/dist_verify web/dist_verify2 .overmind.sock .env.bak-haiku`; leave `_to_delete_tarballs/` (already ignored) and `web/dist_build/` (check `web/vite.config.ts` for a reference first; move only if unreferenced). Append to `.gitignore`: `*.wav` (with the comment "speaker/eval captures live under data/; a WAV at the root is a stray") and `web/dist_verify*/`. Larry: if `git ls-files -- s1.wav s2.wav s3.wav tv.wav` prints any of them, `git rm --cached <those>` in the same commit; then `rm -rf _to_delete/2026-09-04` after the merge. *Why:* the sandbox cannot delete, and a moved file is a reversible decision.

**GC11 — Tracks by reference, with their gates restated in one line each.** T2 remote access/auth: `MORTIMER_REMOTE_ACCESS_PLAN.md`, gate G2, first in the W1 wave, prerequisite for iOS, the brief, and Tailscale. T5 mail/calendar/brief: `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md`, W2, needs T2's service token (K1). T3 mini + local models: `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md`, needs hardware; its cost premise is re-ranked by §8.5's measurement before purchase. T6: `MORTIMER_SKILL_AUTHORING_PLAN.md` (W0 with T4a). This plan changes none of their text; it adds one line to `MORTIMER_PLATFORM_ROADMAP.md` §5 (Sequence): "2026-09-04: gap-closure plan lands before W1; G1(e) clock starts at the web freeze commit."

**GC12 — Kill switches added by this plan:** `JARVIS_KEYHEALTH_NOTICE_ENABLED` (GC5), `JARVIS_REMINDER_NOTIFICATIONS_ENABLED` (GC9). `JARVIS_USER_ID` is a setting, not a switch. `mcp-reminders`'s `skill.yaml` declares nothing new (the sidecar, not the server, reads the switch).

## §4 Files (complete manifest)

**Create**
- `jarvis/tenant.py`; `jarvis/notify.py`; `jarvis/bot/keyhealth_notice.py`; `jarvis/admin/reminder_notifier.py`
- `scripts/backup_db.py`; `scripts/launchd_gen.py`; `scripts/launchd/com.mortimer.template.plist` (the template `launchd_gen.py` reads)
- `tests/unit/test_tenant.py`, `tests/unit/test_tenant_columns.py`, `tests/unit/test_notify.py`, `tests/unit/test_reminder_notifier.py`, `tests/unit/test_keyhealth_notice.py`, `tests/unit/test_backup_db.py`, `tests/unit/test_launchd_gen.py`, `tests/unit/test_mortimer_sh_guard.py` (shell script under `bash -n` + a grep for the launchd guard), `tests/unit/test_web_freeze_preflight.py`
- `_to_delete/2026-09-04/` (moved files; gitignored)

**Modify**
- `jarvis/db.py` — `MIGRATION_0020_user_id`, `MIGRATION_0021_reminders_notified`, `MIGRATIONS` list
- `jarvis/memory.py` — `upsert_fact` conflict target (`:672-673`)
- `jarvis/usage_ledger.py` — `_conn` in-place `user_id` ALTER
- `jarvis/config.py` — `jarvis_user_id`
- `jarvis/prompts.py` — `KEYHEALTH_TEMPLATE`, `KEYHEALTH_RECOVERED_TEMPLATE`
- `jarvis/bot/pipeline.py` — `Runtime` gains `sub_agents` and `keyhealth_notice`; construct `KeyHealthNotice` in `run_session`, stop it in the `finally` (GC5)
- `jarvis/admin/server.py` — start `ReminderNotifier` at module top behind its switch (GC9)
- `jarvis/council/council.py` — exception text at `:416` and `:504`
- `jarvis/council/agreement.py` — supersession in `compute_agreement`, `AgreementReport.superseded_shadow_rows`; `jarvis/council/__main__.py` — the "superseded shadow rows" line
- `tests/unit/test_council_gather.py` (create) — GC6(a)
- `jarvis/selfedit/service.py` — `VALIDATE_PYTEST_TIMEOUT_S`; `preflight` web-freeze rule
- `mcp_servers/mcp_reminders/logic.py` — `peek_due_reminders`, `mark_notified` (plain functions, not tools)
- `scripts/mortimer.sh` — web launch removed; launchd guard
- `web/README.md` — freeze paragraph prepended (file exists)
- `tests/unit/test_admin_selfedit.py` — the web-goal fixture at `:487` → `docs/README.md`
- `Procfile`, `ROADMAP.md`, `CLAUDE.md`, `docs/REPO_MAP.md`, `.gitignore`
- `docs/plans/MORTIMER_PLATFORM_ROADMAP.md`, `MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md`, `MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md`, `MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md`, `MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md`, `MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md`, `MORTIMER_RESUME_PLAN.md` — status lines only
- `tests/unit/test_db.py` — `EXPECTED_MIGRATION_IDS`, `test_migration_0020_user_id_everywhere`, `test_migration_0021_notified_at`
- `tests/unit/test_memory.py` — `test_upsert_fact_conflict_still_updates_with_default_user`
- `tests/unit/test_reminder_notifier.py` (create) — GC9 thread
- `tests/unit/test_mcp_reminders_logic.py` — `peek`/`mark_notified`
- `tests/unit/test_council_agreement.py` — supersession
- `tests/unit/test_selfedit_service.py` — timeout constant, preflight rule, `test_routine_goal_passes_without_plan` goal → `docs/README.md`
- The six failing test files and/or their polluters (GC1) — named in the implementer's report

**Delete** — nothing (moves only, GC10).

## §5 Implementation steps, in order

**Phase A — on `feat/t4a-security-hardening` (makes gap 1's PR green)**

**Step 1 — GC1: the six failures.** Follow GC1's five-step procedure verbatim. Report: for each failure, ALONE result, polluter file (if any), the one-line cause, the fix. Gate: `pytest tests/unit tests/integration -q` → `0 failed` twice in different orders.

**Step 2 — GC1b.** `VALIDATE_PYTEST_TIMEOUT_S = 900` with the comment "2026-09-04: 2,150+ tests; the self-edit run that convened council round e48cfbe1 timed out here at 300 s (gap-closure plan GC1b). CI runs the same command with no timeout." Test: `test_selfedit_service.py::test_pytest_gate_timeout_is_900`.

**Step 3 — GC2 + GC3 docs.** REPO_MAP regeneration (GC2 procedure + assertion), five CLAUDE.md paragraphs + the CI sentence fix + **Two vaults** note, ROADMAP.md bullet, the seven plan status lines, Procfile TODO line. Test: `tests/unit/test_repo_map.py` (exists? else create) `test_repo_map_under_cap_and_names_phase_modules` — `len(REPO_MAP.md text) <= 8000` and `load_repo_map_suffix()` contains each name in GC2's list.

**Step 4 — Hand to Larry: §8.1 (PR → main).** Phase B does not start until `main` contains Phase A.

**Phase B — on `feat/gap-closure` cut from `main`**

**Step 5 — GC7 backups first.** `scripts/backup_db.py` (literal):
```python
#!/usr/bin/env python3
"""Nightly SQLite backups (gap-closure plan GC7). stdlib only; WAL-safe via
sqlite3.Connection.backup. Never touches secrets: prints a reminder to run
`python -m jarvis.vault export-key` by hand instead."""
from __future__ import annotations
import sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DBS = ("data/jarvis.db", "data/costs.db")
BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_KEEP = 14          # §6

def backup_one(src: Path, stamp: str) -> Path:
    dst = BACKUP_DIR / f"{src.stem}.{stamp}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)
    return dst

def prune(stem: str, keep: int) -> list[Path]:
    files = sorted(BACKUP_DIR.glob(f"{stem}.*.db"))
    doomed = files[:-keep] if len(files) > keep else []
    for f in doomed:
        f.unlink()
    return doomed

def main() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    rc = 0
    for rel in DBS:
        src = ROOT / rel
        if not src.exists():
            print(f"skip {rel}: missing"); continue
        try:
            dst = backup_one(src, stamp)
            gone = prune(src.stem, BACKUP_KEEP)
            print(f"ok {rel} -> {dst.relative_to(ROOT)} (pruned {len(gone)})")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {rel}: {type(exc).__name__}: {exc}", file=sys.stderr); rc = 1
    print("reminder: the vault key is NOT backed up here — run `python -m jarvis.vault export-key` once and store it off-machine.")
    return rc

if __name__ == "__main__":
    sys.exit(main())
```
`data/backups/` is covered by `.gitignore`'s `data/*.db`? No — that pattern is one level; add `data/backups/` to `.gitignore`. Tests: `test_backup_db.py::test_backup_creates_copy_with_same_rows`, `::test_prune_keeps_newest_n`, `::test_missing_db_is_skipped_not_failed`.

**Step 6 — GC7 launchd.** Template `scripts/launchd/com.mortimer.template.plist` (literal):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.mortimer.__SVC__</string>
  <key>ProgramArguments</key><array>__ARGS__</array>
  <key>WorkingDirectory</key><string>__REPO__</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StandardOutPath</key><string>__REPO__/logs/__SVC__.launchd.log</string>
  <key>StandardErrorPath</key><string>__REPO__/logs/__SVC__.launchd.log</string>
  __SCHEDULE__
</dict></plist>
```
`launchd_gen.py`: `SERVICES = {"vault": "exec ./scripts/run_kb.sh", "bot": "./scripts/wait_for.sh 127.0.0.1 8484 30 vault && exec ./scripts/run_bot.sh", "extractor": "exec ./scripts/run_memory_extractor.sh", "admin": "exec ./scripts/run_admin.sh", "costs": "exec ./scripts/run_costs.sh"}`; each becomes `__ARGS__` = the XML-escaped list `["/bin/bash", "-c", f"cd {repo} && {cmd}"]` rendered as one `<string>{xml.sax.saxutils.escape(arg)}</string>` per element (so `&&` becomes `&amp;&amp;` — a raw `&&` inside `<string>` is invalid XML and `launchctl bootstrap` rejects the file) and `__SCHEDULE__` = `<key>KeepAlive</key><true/><key>RunAtLoad</key><true/>`; `backup` becomes `__ARGS__` = `<string>__REPO__/.venv/bin/python</string><string>scripts/backup_db.py</string>` and `__SCHEDULE__` = `<key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>15</integer></dict>`. Every substituted value (`__REPO__`, every arg) goes through `xml.sax.saxutils.escape`. CLI: `--write` (default) writes to `~/Library/LaunchAgents/`; `--install` = write → `launchctl bootout gui/<uid>/com.mortimer.<svc>` (failure ignored — not loaded yet) → `launchctl bootstrap gui/<uid> <path>` each (bootstrap fails if already loaded, hence the bootout first); `--uninstall` = `bootout` each; `--status` = `launchctl print gui/<uid>/com.mortimer.<svc>` parsed to `loaded (pid N)` / `loaded (idle)` / `not loaded` per service; `--dry-run` prints the plists to stdout and writes nothing; `--hour INT` (default 3) / `--minute INT` (default 15) set the backup schedule. Subprocess calls are fixed argv. Tests (`test_launchd_gen.py`): rendered bot plist contains `wait_for.sh`, `&amp;&amp;`, never a bare ` && `, and `<true/>` KeepAlive; backup plist has `StartCalendarInterval` (hour/minute from flags) and no KeepAlive; a repo path containing `&` is escaped; `--dry-run` writes nothing (tmp `HOME`); every plist parses with `plistlib.loads`. `mortimer.sh` guard per GC7 — `test_mortimer_sh_guard.py`: `bash -n scripts/mortimer.sh` exits 0 and the file contains `com.mortimer.bot`.

**Step 7 — GC4 web freeze.** `mortimer.sh` edits (GC4), `Procfile` line, `web/README.md` prepend, `preflight` rule, the two fixture goal changes. Test: `test_web_freeze_preflight.py::test_goal_touching_only_web_is_refused` (goal "change web/src/App.tsx colours" → `ok False`, error contains "frozen"), `::test_mixed_goal_is_not_refused_by_this_rule` (goal naming `web/src/x.ts` and `jarvis/prompts.py` passes this rule and falls through to the tier logic).

**Step 8 — GC5 degraded-mode notice.** Module, templates, wiring, kill switch, CLAUDE.md paragraph. Tests (`test_keyhealth_notice.py`, fake agents with `name`, `model_unusable`, `model_unusable_detail`): disconnected → no inject; one unusable → exactly one inject containing the agent name and detail; same state next tick → no second inject; recovered → the recovered template once; switch off → in `tests/integration/test_bot_wiring.py`, using its existing `run_session` + `fire_disconnect` harness (`:660-705`), monkeypatch `jarvis.bot.pipeline.KeyHealthNotice` with a recording fake and assert it is never constructed under `JARVIS_KEYHEALTH_NOTICE_ENABLED=false` and constructed exactly once without it.

**Step 9 — GC8 tenant column (only after Larry confirms §8.4 ran once).** `MIGRATION_0020_user_id` (literal):
```sql
BEGIN;
ALTER TABLE notes ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE reminders ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE actions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memories ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE observations ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE agent_runs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE agent_events ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE procedures ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE council_rounds ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE council_scores ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_reviews ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_extraction_cursor ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_extraction_pending ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_recall_events ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
DROP INDEX IF EXISTS idx_memories_fact_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_fact_key
  ON memories(user_id, key) WHERE kind = 'fact';
COMMIT;
```
(15 tables = all 16 `CREATE TABLE`s minus `migrations`; verify the count against `grep -c "CREATE TABLE IF NOT EXISTS" jarvis/db.py` before applying — if a table has been added since `baa9838`, add it to both this migration and the expected list.) `jarvis/memory.py` conflict target; `usage_ledger._conn` gains `if "user_id" not in cols: conn.execute("ALTER TABLE llm_calls ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")`; `jarvis/tenant.py` (literal):
```python
"""Tenant identity (gap-closure plan GC8, contract GC-T). Column-only today:
every table carries user_id DEFAULT 'local'; nothing filters by it yet."""
from __future__ import annotations
import logging, os, re
logger = logging.getLogger(__name__)
DEFAULT_USER_ID = "local"
USER_ID_ENV = "JARVIS_USER_ID"
_VALID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

def current_user_id() -> str:
    raw = (os.environ.get(USER_ID_ENV) or "").strip()
    if not raw:
        return DEFAULT_USER_ID
    if not _VALID.match(raw):
        logger.warning("tenant_user_id_invalid value=%r using default", raw)
        return DEFAULT_USER_ID
    return raw
```
Tests: `test_tenant_columns.py` (GC8), `test_tenant.py` (empty/unset → `local`; `Larry` (uppercase) → `local` + warning; `larry-air` → itself; 65 chars → `local`), `test_db.py` additions including `test_migration_0020_is_atomic` (monkeypatch the migration text to name a bogus table mid-list → `run_migrations` raises, no table gained `user_id`, `0020` absent from `migrations`), `test_memory.py::test_upsert_fact_conflict_still_updates_with_default_user` (insert key K twice → one row, content updated, `user_id == 'local'`), `tests/unit/test_usage_ledger.py::test_llm_calls_gains_user_id` (existing costs.db without the column → `_conn()` adds it).

**Step 10 — GC9 reminders notification.** Migration `0021`; the two logic functions with the literal SQL and return shapes from GC9; `jarvis/notify.py` (literal):
```python
"""macOS user notification via osascript (gap-closure plan GC9). Fixed argv,
never a shell — the pbcopy/pbpaste precedent (CLAUDE.md, handoff loop)."""
from __future__ import annotations
import logging, subprocess
logger = logging.getLogger(__name__)
NOTIFY_TIMEOUT_S = 5.0     # §6
NOTIFY_MAX_CHARS = 200     # §6

def _as_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

def build_argv(message: str, title: str = "Mortimer") -> list[str]:
    msg = message[:NOTIFY_MAX_CHARS]
    return ["osascript", "-e", f"display notification {_as_str(msg)} with title {_as_str(title)}"]

def post_notification(message: str, title: str = "Mortimer") -> bool:
    try:
        proc = subprocess.run(build_argv(message, title), check=False,
                              timeout=NOTIFY_TIMEOUT_S, capture_output=True)
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001 — a notification must never crash the notifier
        logger.warning("notify_failed error=%s", type(exc).__name__)
        return False
```
`jarvis/admin/reminder_notifier.py` (literal):
```python
"""Sidecar-side reminder notifier (gap-closure plan GC9). The bot's
RemindersWatcher lives inside a WebRTC session; this thread lives as long
as the sidecar, and only ever sets reminders.notified_at — never delivered."""
from __future__ import annotations
import logging, threading
from typing import Callable
from mcp_servers.mcp_reminders import logic
from jarvis.notify import post_notification
logger = logging.getLogger(__name__)
REMINDER_NOTIFY_INTERVAL_S = 30.0   # §6
REMINDER_NOTIFY_GRACE_S = 60.0      # §6

class ReminderNotifier:
    def __init__(self, interval_s: float = REMINDER_NOTIFY_INTERVAL_S,
                 grace_s: float = REMINDER_NOTIFY_GRACE_S,
                 post: Callable[[str], bool] = post_notification):
        self._interval_s, self._grace_s, self._post = interval_s, grace_s, post
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="reminder-notifier", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_s):
            self.tick_once()

    def tick_once(self) -> int:
        """Notify every due-but-unspoken reminder once. Returns the count. Never raises."""
        try:
            rows = logic.peek_due_reminders(self._grace_s).get("reminders") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("reminder_notifier_peek_failed error=%s", type(exc).__name__)
            return 0
        sent = 0
        for row in rows:
            if self._post(str(row.get("message", ""))):
                try:
                    logic.mark_notified([int(row["id"])])
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("reminder_notifier_mark_failed id=%s error=%s", row.get("id"), type(exc).__name__)
        return sent
```
In `jarvis/admin/server.py`, at module top beside the other background-thread slots: `_reminder_notifier = ReminderNotifier()` and `if os.environ.get("JARVIS_REMINDER_NOTIFICATIONS_ENABLED", "").strip().lower() not in ("0", "false", "no", "off"): _reminder_notifier.start()` (the same four falsy spellings as `jarvis/skills/registry.py:68-72`). Tests: `test_notify.py` (the three adversarial cases from GC9, on `build_argv` and on `post_notification` with `subprocess.run` monkeypatched), `tests/unit/test_reminder_notifier.py` (temp DB via `JARVIS_DB_PATH`; a recording `post` fake: one reminder due 2 min ago → `post` called once, `notified_at` set, `delivered` still 0; a reminder due 10 s ago → not notified (grace); `post` returns False → `notified_at` stays NULL; a second `tick_once` → `post` not called again; `delivered = 1` rows never notified), `test_mcp_reminders_logic.py` (`peek` excludes delivered, notified, and inside-grace rows; `mark_notified` leaves `delivered` 0), `test_db.py::test_migration_0021_notified_at`.

**Step 11 — GC6 council.** Exception text (both sites), agreement supersession in `compute_agreement` (literal, after `:203`): `before = len(score_rows); keep = {}; for r in sorted(score_rows, key=lambda r: r["created_at"] or ""): keep[(r["round_id"], r["judge_profile"], r["proposal_label"], int(r.get("shadow", 0) or 0))] = r; score_rows = list(keep.values()); superseded = before - len(score_rows)`, threaded into the report field; the CLI line. Tests: `test_council_agreement.py::test_newest_shadow_row_supersedes_older_for_same_judge_and_label` (two shadow rows same judge/label, older NULL score, newer 7.0 → abstention rate counts 0, report field 1), `::test_superseded_count_reported`; new `tests/unit/test_council_gather.py::test_timeout_abstain_reason_names_the_exception` — monkeypatch `jarvis.council.council._call_profile` to raise `asyncio.TimeoutError()` and call `_gather_scores` directly (the seam `tests/integration/test_council_escalation.py:194/278` already uses) → every returned `Score` has `abstain_reason == "judge call failed: TimeoutError: "`.

**Step 12 — GC10 hygiene + GC11 roadmap line.** Moves, `.gitignore` lines (`*.wav`, `web/dist_verify*/`, `data/backups/`), the roadmap §5 line.

**Step 13 — Full suite + report.** `pytest tests/unit tests/integration -q` (0 failed, no live), `bash -n scripts/mortimer.sh`, `python scripts/launchd_gen.py --dry-run | head`, `python scripts/check_skills.py`. Hand Larry §12.

## §6 Tuning knobs

| Constant | Where | Default | Env override |
|---|---|---|---|
| `VALIDATE_PYTEST_TIMEOUT_S` | `sandbox/verify.py` (moved 2026-09-10) | 900 | — |
| `KEYHEALTH_NOTICE_INTERVAL_S` | `jarvis/bot/keyhealth_notice.py` | 30.0 | — |
| kill switch | `jarvis/bot/pipeline.py` (construction) | true | `JARVIS_KEYHEALTH_NOTICE_ENABLED` |
| `BACKUP_KEEP` | `scripts/backup_db.py` | 14 | — |
| backup schedule | `scripts/launchd_gen.py` | 03:15 daily | `--hour/--minute` flags |
| `NOTIFY_TIMEOUT_S` / `NOTIFY_MAX_CHARS` | `jarvis/notify.py` | 5.0 / 200 | — |
| `REMINDER_NOTIFY_INTERVAL_S` / `REMINDER_NOTIFY_GRACE_S` | `jarvis/admin/reminder_notifier.py` | 30.0 / 60.0 | — |
| kill switch | `jarvis/admin/server.py` (module top) | true | `JARVIS_REMINDER_NOTIFICATIONS_ENABLED` |
| `DEFAULT_USER_ID` | `jarvis/tenant.py` | `local` | `JARVIS_USER_ID` (validated) |
| dependency-update banner | `mcp_servers/__init__.py` (default only) | `off` | `FASTMCP_CHECK_FOR_UPDATES` |
| `REPO_MAP_MAX_CHARS` | `jarvis/repo_map.py:18` (unchanged) | 8000 | — |

## §7 Tests — by file and function

Named in §5 per step; the complete list: `test_selfedit_service.py::test_pytest_gate_timeout_is_900`; `test_repo_map.py::test_repo_map_under_cap_and_names_phase_modules`; `test_backup_db.py` ×3; `test_launchd_gen.py` ×4; `test_mortimer_sh_guard.py` ×1; `test_web_freeze_preflight.py` ×2; `test_keyhealth_notice.py` ×5; `test_tenant_columns.py` ×1; `test_tenant.py` ×4; `test_db.py` +2 (`EXPECTED_MIGRATION_IDS` gains `0020_user_id`, `0021_reminders_notified`; `test_migration_0020_user_id_everywhere` checks `PRAGMA table_info` for every table with the same exclusions as `test_tenant_columns.py`; `test_migration_0021_notified_at`); `test_memory.py` +1; `test_usage_ledger.py` +1; `test_notify.py` ×3; `test_reminder_notifier.py` ×5; `test_mcp_reminders_logic.py` +2; `test_council_agreement.py` +2; `tests/unit/test_council_gather.py` ×1; `tests/integration/test_bot_wiring.py` +1 (GC5 switch). Plus whatever GC1 touches, each with a one-line comment naming the polluter it fixed.

## §8 Verification Larry runs on his hardware

1. **Gap 1 — merge.** After Phase A: `git checkout feat/t4a-security-hardening && pytest tests/unit tests/integration -q` → 0 failed; `git push`; open the PR to `main` on GitHub; CI green on all six gates; merge (no squash — the 49 commits are the audit trail). Then `git checkout main && git pull --ff-only && git checkout -b feat/gap-closure`. If CI's `Unit tests` step fails on a test that passes locally, paste the CI log into the next session — that is a GC1-class polluter that only shows on Linux collection order.
2. **Gap 6 — one real session.** `./scripts/mortimer.sh`; connect from MortimerHost; run `MORTIMER_SESSION_MISSES_PLAN.md` §8 steps 1, 3–7 exactly as written there; then `uv run python scripts/cost_report.py` and note `voice_usd` vs LLM for the session.
3. **Gap 6 — speaker gate.** `source .venv/bin/activate && python -m jarvis.speaker verify --windowed data/speaker_captures/*.wav` → every Larry file `best_window ≥ 0.40`, every TV/other file `< 0.40`. Pass → set `JARVIS_SPEAKER_GATE_ENABLED=true` and restart; fail → append the numbers to `MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md` §6 and leave the gate off.
4. **Gap 8 — backups, then supervision.** `python scripts/backup_db.py` → two `ok` lines and files under `data/backups/`. Only after this: `python scripts/launchd_gen.py --dry-run` (read it), `./scripts/mortimer.sh stop`, `python scripts/launchd_gen.py --install`, `python scripts/launchd_gen.py --status` → five `loaded (pid N)` lines and `backup: loaded (idle)`; `./scripts/mortimer.sh` → exits 3 with the launchd message. Kill the bot (`kill <pid>`) → `--status` shows it back within 10 s. `python -m jarvis.vault export-key` once, store the output off-machine.
5. **Gap 9 — measure before deciding.** After 8.2, `curl -s localhost:8487/costs/summary` → if `voice_usd / llm_usd ≥ 2` for the session, record it in `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md`'s header as "cost premise re-ranked 2026-09: TTS first" before any hardware purchase; if `< 2`, record that the snapshot's item 9 did not hold.
6. **Gap 2 — the gate.** Time the suite: `time pytest tests/unit -q` — record the wall time in this file's header. Then one voice self-edit (any small `docs/` goal) → `selfedit validate` reaches `pytest ok`.
7. **Gap 7 — council.** `python -m jarvis.council --replay d6e0059b91a14893959b3cb322fc5b1c --judges frontier` → both Anthropic judges return scores (no `temperature` error); `python -m jarvis.council --agreement` shows `superseded shadow rows: N` where N = 4 × the number of frontier judges that answered (≥ 8; 20 if all five frontier profiles have keys) and both Anthropic judges present in the tier table. Decide kimi-k3 (GC6d) and, if demoting, make the one-line `tier:` edit yourself.
8. **Gap 10 — migration on the live DB.** `python scripts/init_db.py` → applies `0020`, `0021`; `sqlite3 data/jarvis.db "PRAGMA table_info(memories)"` shows `user_id`; `./scripts/mortimer.sh` (or `launchctl kickstart -k` the bot and admin) — one turn of conversation; `python -m jarvis.runlog` shows a new run.
9. **Gap 11 reminders.** Set a reminder for two minutes out by voice, disconnect the client, wait ~3.5 minutes (due + 60 s grace + one 30 s tick) — a macOS notification "Mortimer" appears (grant the permission prompt the first time); reconnect — Mortimer speaks it once.
10. **Gap 13.** `git ls-files -- s1.wav s2.wav s3.wav tv.wav`; `git rm --cached` any listed; `rm -rf _to_delete/2026-09-04` after merge.

## §9 Rollback

- GC1/GC1b: revert the commits; the gate returns to 300 s (do not — nothing depends on 300).
- GC4: `./scripts/run_web.sh` still works by hand; remove the preflight rule to un-freeze.
- GC5: `JARVIS_KEYHEALTH_NOTICE_ENABLED=false`.
- GC7: `python scripts/launchd_gen.py --uninstall`, then `./scripts/mortimer.sh` works as before; backups are files under `data/backups/` — delete if unwanted.
- GC8: SQLite cannot drop a column before 3.35 and the project does not depend on that; the column is inert (DEFAULT, never filtered) — leave it. If a restore is needed: stop the stack, copy `data/backups/jarvis.<stamp>.db` over `data/jarvis.db`, restart; the migration re-applies on next `init_db` (it is `IF NOT EXISTS`-safe only for the index; the ALTERs will fail on a DB that already has the column — `run_migrations` records `0020` as applied on first success, so a restored pre-0020 DB simply re-runs it).
- GC9: `JARVIS_REMINDER_NOTIFICATIONS_ENABLED=false`; the `notified_at` column is inert.
- GC6: revert; `--agreement` returns to reading every row.
- GC10: `mv _to_delete/2026-09-04/* .` restores everything.

## §10 Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | A GC1 failure is a real product bug whose fix is out of scope | medium | fix it if ≤ 30 lines; else report with the root cause and STOP that item — never `xfail` |
| 2 | launchd-managed processes lose `mortimer.sh`'s log rotation | certain | `.launchd.log` files are separate; add `newsyslog`-style rotation later; documented in §8.4 |
| 3 | `osascript` notifications require Notification permission for the calling app (the sidecar's python, under Terminal or launchd) | medium | first notification prompts; §8.9 verifies; failure path is silent + logged, delivered semantics untouched |
| 4 | `ALTER TABLE ... NOT NULL DEFAULT` on 15 tables in one migration on a live WAL DB | low | §0.3 backup gate; ALTERs are metadata-only in SQLite |
| 5 | `ON CONFLICT(user_id, key)` requires the partial unique index to match exactly | low | pinned by `test_upsert_fact_conflict_still_updates_with_default_user` |
| 6 | Freezing web strands a feature Larry uses only there | low | nothing is deleted; `run_web.sh` remains; the preflight rule is one function |
| 7 | KeyHealth notice speaks on a transient `unreachable` | none | `model_unusable` is False for `unreachable`/`unknown` by design (`base.py:316-318`) |
| 8 | CI on Linux orders tests differently and exposes a polluter GC1 missed | medium | §8.1's instruction: paste the CI log; treat as GC1 step 4 |

## §11 Self-audit (9-item taxonomy)

1. Contracts typed: GC-T (column, default, reader function, test); `KeyHealthNotice` constructor and templates; `peek_due_reminders`/`mark_notified` SQL and return shapes (`{"reminders": [...]}` / `{"marked": N}`, matching `get_due_reminders`'s key-only dict at `logic.py:252`); `build_argv` output literal; launchd template literal.
2. Lifecycle: `KeyHealthNotice._last_spoken` is per connection (the instance lives with `run_session`), so a reconnect re-announces — stated in GC5; notifications dedup by `notified_at` in the DB, not in memory (survives restarts).
3. Applied values: `user_id` via DEFAULT only; `notified_at` set only on a successful `osascript`; the launchd guard exits 3.
4. Contradictions checked: GC9 vs the watcher docstring (delivered semantics preserved — stated in both); GC4 vs the allowlist (allowlist untouched, preflight rule instead — stated in GC4 and step 7); no tool count change in this plan (GC9 adds plain functions, not tools) — the Graph plan's 64→66 stands alone.
5. Copy: every spoken/logged sentence is literal (GC4 error, GC5 templates, GC6 abstain text, GC7 guard message, backup reminder line).
6. Initialization: notice and notifications flags read once at pipeline construction; `tenant.current_user_id` reads env per call (cheap, and MCP children need it live).
7. Every column populated: `user_id` by DEFAULT; `notified_at` by `mark_notified`; `EXPECTED_MIGRATION_IDS` updated in the same step as the migrations.
8. No judgment: GC1 is a procedure with a bisection rule and a forbidden outcome; kimi-k3 is explicitly Larry's; the web freeze rule is a path predicate.
9. Drift: every file in §5 is in §4; step 9's table list matches `grep -c` with the verification instruction; phase order stated in the header, §0.3, §5 step 4, §8.1.

## §12 Approval checklist and Larry's commit lists

- [ ] Larry approves GC1–GC12; decides GC6d (kimi-k3 keep/demote).
- [ ] **Phase A commit** (on `feat/t4a-security-hardening`): `git add jarvis/selfedit/service.py docs/REPO_MAP.md CLAUDE.md ROADMAP.md Procfile docs/plans/MORTIMER_PLATFORM_ROADMAP.md docs/plans/MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md docs/plans/MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md docs/plans/MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md docs/plans/MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md docs/plans/MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md docs/plans/MORTIMER_RESUME_PLAN.md docs/plans/MORTIMER_GAP_CLOSURE_PLAN.md tests/unit/test_selfedit_service.py tests/unit/test_repo_map.py` **plus the GC1 files the implementer names**. Then §8.1.
- [ ] **Phase B commit** (on `feat/gap-closure`): `git add jarvis/tenant.py jarvis/notify.py jarvis/bot/keyhealth_notice.py jarvis/admin/reminder_notifier.py jarvis/admin/server.py jarvis/bot/pipeline.py jarvis/db.py jarvis/memory.py jarvis/usage_ledger.py jarvis/config.py jarvis/prompts.py jarvis/council/council.py jarvis/council/agreement.py jarvis/council/__main__.py jarvis/selfedit/service.py mcp_servers/mcp_reminders scripts/backup_db.py scripts/launchd_gen.py scripts/launchd scripts/mortimer.sh web/README.md Procfile CLAUDE.md .gitignore docs/plans/MORTIMER_PLATFORM_ROADMAP.md tests/unit/test_tenant.py tests/unit/test_tenant_columns.py tests/unit/test_notify.py tests/unit/test_keyhealth_notice.py tests/unit/test_backup_db.py tests/unit/test_launchd_gen.py tests/unit/test_mortimer_sh_guard.py tests/unit/test_web_freeze_preflight.py tests/unit/test_db.py tests/unit/test_memory.py tests/unit/test_usage_ledger.py tests/unit/test_reminder_notifier.py tests/unit/test_mcp_reminders_logic.py tests/unit/test_council_agreement.py tests/unit/test_council_gather.py tests/unit/test_selfedit_service.py tests/unit/test_admin_selfedit.py tests/integration/test_bot_wiring.py` and any `git rm --cached` from §8.10.
- [ ] Larry runs §8.2–8.10 and records: suite wall time, the §8.5 ratio, the speaker-gate verdict, the G1(e) start date (in `web/README.md`).
