# Cross-system plan evaluation: Claude vs Codex

**Date:** 2026-09-27, 17:00 EDT
**Question asked by Larry:** are Claude and Codex doing conflicting work, and is a shared roadmap the right fix?
**Method:** read-only inspection of the production checkout `~/jarvis-voice-ai-clean` and Codex's workspace `~/Documents/Codex/2026-09-09/can/work/`. File contents, file sizes, file modification times, and git metadata files (`HEAD`, `FETCH_HEAD`, `logs/HEAD`, worktree `.git` pointers) were read directly. **No git command was run** against either checkout.

Confidence tags: **[certain]** = read directly from a file. **[likely]** = inferred from file modification times, which show when a file was last written but not what changed. **[untested]** = not checked; the test that would settle it is named.

---

## 1. Verdict

You are right that the two systems collide. They already have: see F1. A roadmap file is necessary, but a file alone will not stop it. Three things cause the collisions, and a document only addresses the first:

1. **No shared record of who owns what.** Each system writes its own plans and status files in its own checkout. [certain]
2. **Codex works in a long-lived, uncommitted worktree that has not merged main since it was created (09-24).** Its plans describe a `main` that no longer exists. [certain]
3. **Neither system has a rule that forbids editing another system's files.** Codex has no repo instruction file at all: there is no `AGENTS.md` in either tree. [certain]

The roadmap in this change fixes (1). The protocol in `AGENTS.md` and the `CLAUDE.md` block fix (3). (2) needs one action from you: have Codex merge `main` before it does anything else (§4).

---

## 2. State of each tree

| | Production checkout (`~/jarvis-voice-ai-clean`) | Codex worktree (`codex-isolated-20260924`) |
|---|---|---|
| Commit | `0b76f49` (detached HEAD = `origin/main`, fetched 09-25 22:14) [certain] | branch `codex/isolated-20260924`, base `977f50b`, with a large uncommitted change set [certain, from its own plans and receipts] |
| Last write | 09-25 22:14 | **09-27 16:56, i.e. Codex was writing while this review ran** (`jarvis/admin/server.py`, `jarvis/skill_requests.py`) [certain] |
| Plans in `docs/plans/` | 45 | 58: **16 exist only here** [certain] |
| DB migrations | `0025_notices`, `0026_expire_retired_actions`, `0027_notice_memory_review` [certain] | `0025_memory_admission_jobs` … `0031_client_tokens` (7 new) [certain] |
| Pushed to GitHub | yes | no. Its plans say "Leave work uncommitted and unpushed." [certain] |

Landed on `main` after Codex's base and **absent from Codex's tree** [certain, by file listing]:
`jarvis/status/` (whole package), `jarvis/notices.py`, `jarvis/voice_workflows.py`, `jarvis/bot/voice_guidance.py`, `jarvis/bot/status_tool.py`, `jarvis/bot/follow_up.py`, `jarvis/bot/device_location.py`, `jarvis/skills/shared.py`, `jarvis/selfedit/proposals.py`, `scripts/deploy_main.sh`, `docs/plans/MORTIMER_VOICE_WORKFLOWS_PLAN.md`, `docs/plans/MORTIMER_WORKFLOW_VIEWER_PLAN.md`.
That is the self-service access work (#86's files, merged as-is) and the rest of the 09-25 voice-workflows landing (phases 1–4, workflow viewer, #80 privacy fix, DEPLOY-MAIN).

---

## 3. Findings

### F1: a real collision already happened (24 Sep) [certain]
`scripts/deploy_main.sh` lines 62–67 record it. Codex had 9 tracked edits and a half-applied orb-crystal change **in the production checkout**. The deploy's `checkout -f` discarded Codex's edits, and the build failed. The guard added afterwards refuses to deploy while production holds work that is not on main.
**Rule this implies:** no system edits `~/jarvis-voice-ai-clean`. Production is deploy-only.

### F2: database migration IDs collide: blocker for merging Codex's work [certain]
`main` and Codex's tree both define `0025`, `0026` and `0027`, with different contents. Migrations are tracked by their full id string (`jarvis/db.py`, `run_migrations`), so nothing is silently skipped. However, the numbering is the ordering contract ("applied strictly in list order"), and the `MIGRATIONS` list will conflict textually.
Knock-on: Codex rewrote the Remote Access plan's cross-plan guard from "REMOTE owns `0016_client_tokens`; MAIL moves to `0017`" to "REMOTE owns `0031`; MAIL `0032`". Both numbers were computed from Codex's tree, not from main.
**Resolution:** keep main's `0025`–`0027`, which may already be applied to the production database. Codex renumbers its seven migrations to `0028`–`0034` when it merges main. Future numbers are reserved in `ROADMAP.md` §3 before anyone writes one.
Before renaming anything, confirm that Codex's ids never ran against production's `data/jarvis.db` **[untested]**. Test: `SELECT id FROM migrations ORDER BY id;` on the production database. None of the seven Codex ids should appear.

### F3: 24 source files changed on both sides [likely]
These files were rewritten on main between `4acb4dc` and `0b76f49`, and were also written in Codex's worktree after it was created (09-24 20:26):
`jarvis/anthropic_shim.py`, `config.py`, `db.py`, `keyhealth.py`, `memory.py`, `memory_automation.py`, `memory_extraction.py`, `memory_sweep.py`, `model_routing.py`, `usage_ledger.py`, `vault.py`, `workflows.py`, `admin/server.py`, `agents/base.py`, `agents/delegate.py`, `agents/supervisor.py`, `agents/upgrade_agent.py`, `bot/console_actions.py`, `bot/handoff_tools.py`, `bot/pipeline.py`, `bot/progress_watcher.py`, `council/council.py`, `graphs/__init__.py`, `skills/registry.py`.
This list comes from modification times. The merge itself is the test.
Size of the gap on two of them: `skills/registry.py` is 40.8 KB on main (the supervised registry from #86) and 21.2 KB in Codex's tree. `admin/server.py` is 109.7 KB on main and 173.8 KB in Codex's tree. [certain for sizes]

### F4: `jarvis/workflows.py`: each side has a fix the other lacks [certain, diffed]
- **Main** adds `triggers`, `priority` and `draft` (Voice Workflows D1/D3, Workflow Viewer D-V1).
- **Codex** removes the file path and traceback from `workflow_parse_failed` / `workflow_invalid` logs (GC24-03 privacy). Main still logs `path=%s` with `logger.exception`.

A conflict resolution that takes either side whole loses the other side's fix. This is the pattern to watch in all 24 files from F3.

### F5: two features add a new console view through the same five Swift files [certain on files; product call is yours]
- Claude's **Workflow Viewer** (landed) edits `WorkspaceStore`, `ConsoleActionCoordinator` (`view_set`), `WorkspaceView`, `CommandConsoleView` and `AdminAPI.swift`, plus `bot/console_actions.py` and `admin/server.py` (`/api/workflows`).
- Codex's **Skills Workspace** (in progress, edited today) edits the same five Swift files, plus `bot/console_actions.py` and `admin/server.py` (`/api/skills*`).

Both are "browse the procedures Mortimer follows" surfaces. **Decision for Larry:** keep two separate views, or make Skills Workspace absorb the Workflow Viewer as one tab. Either way, Skills Workspace must be rebased onto the view-mode enum that main now has.

### F6: Codex's 16 new plans are blind to what landed on main [certain]
Not one of them mentions Voice Workflows, #86 / self-service access, or the notices outbox. Two of them name `4acb4dc` (main at PR #90) as their source baseline. They were written against a main that has since moved.

### F7: plan sprawl inside Codex: 13 overlapping "gap" plans in ~24 hours [certain]
`VERIFIED_GAP_CLOSURE`, `NEWLY_VERIFIED_GAPS`, `REMAINING_GAPS_IMPLEMENTATION`, `GAPS_…_2026-09-25`, `REVIEW_GAPS`, `REVIEWED_GAPS`, `POST_REVIEW_GAP_CLOSURE`, `IMPLEMENTATION_GAPS_EXECUTION`, `REMAINING_GAPS_EXECUTION`, `FRESH_REVIEW`, `CURRENT_REVIEW_GAPS`, `NEXT_GAPS`, `MODEL_NEUTRAL_GAP`. Most describe themselves as the execution index or the task order, and they supersede each other in prose ("supersedes stale next-action statements here").
**Resolution:** one canonical plan for the workstream (`MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md`, the only one with an author line and the GC24 ids). Fold the others into it as dated progress entries, or archive them.

### F8: the same areas are being worked from three directions [certain]
| Area | Claude (on main) | Codex (worktree) |
|---|---|---|
| Memory admission | D-L7 echo guard in `memory_extraction.py`; memory-review notices (`0027`) | GC24-05: new `memory_admission.py`, migrations `0025`–`0027` |
| Privacy | #80 fix: a preference can never lower a workload's privacy (`model_preferences.py`) | GC24-03: log redaction across ~40 sinks; sensitive-route floors |
| Resilience / status | #86: supervised MCP registry, notices outbox, status tools | GC24-02: execution lifecycle, cancellation, action claims |

No line-level clash was found in `model_preferences.py`: Codex's copy is untouched since the worktree was created. [certain] The risk is design drift: two memory-admission paths, and two privacy audits with no shared list.

### F9: Remote Access (T2) is being built from a plan still marked DRAFT [certain for the header]
Codex added `jarvis/auth.py`, `authmw.py`, `bind.py`, `urls.py`, `bot/server.py` and migration `0031_client_tokens` (last edit today, 16:32). The plan header still reads "DRAFT for Larry's approval, 2026-08-26". **Decision for Larry:** confirm that T2 is approved to build.

### F10: attribution is already unreliable [certain]
`MORTIMER_VOICE_WORKFLOWS_PLAN.md` D-L5 calls #86 "Codex's PR #86". The PR body file (`~/Documents/Codex/…/PR86_BODY.md`) ends with the Claude Code footer and a `claude.ai/code` session link. Its branches were built inside Codex's checkout. If the systems can't tell whose work is whose now, they can't avoid each other later. Every row in the roadmap therefore records the system explicitly.

### F11: Codex has no repo instructions; Claude's are 177 KB [certain]
There is no `AGENTS.md` at the root of main or of Codex's tree. `CLAUDE.md` is 177 KB. A coordination rule buried in either will not be followed. The protocol therefore lives in a short `AGENTS.md`, a short block at the top of `CLAUDE.md`, and `ROADMAP.md`.

### F12: six places claim to hold status, and they disagree [certain]
`ROADMAP.md` (deferred features), `docs/plans/MORTIMER_PLATFORM_ROADMAP.md`, `docs/acceptance/IMPLEMENTATION_STATUS.md` (7 KB on main vs **50 KB in Codex's tree**, a forked copy), four per-feature `STATUS.md` files, every plan's status header, and `CLAUDE.md`.
Example of drift: the Voice Workflows plan header still says "Phase 1 READY FOR HANDOFF … BUILT in the VM", but that work is on main.

---

## 4. Checked and **not** a conflict

- **`jarvis/subscription.py`.** Voice Workflows §9 listed "Codex's in-flight work on `subscription.py`: Unknown". Main's copy has not changed since 09-23. Codex's GC24-04 rewrite (8.8 KB → 19.1 KB) keeps `_run_claude`, `_run_codex` and `SubscriptionRuntimeError` with the same signatures, and those are the names main's `jarvis/status/subscriptions.py` imports. [certain for signatures]
  Behaviour after the merge is **[untested]**. Test: the status/subscription unit tests on the merged tree, then ask Mortimer "Is Fable available on my Claude subscription?"
- **Orb renderer.** Codex's GC24-00 receipt explicitly forbids editing the Crystal renderer. [certain]

---

## 5. What I did not read

- Codex's conversation logs (`~/.codex/sessions`) and the second worktree `codex-wip-20260924` beyond its top level.
- The GitHub PR list: open PRs are not visible without credentials.
- The production database.
- The `MortimerSandbox` VM images.

If Codex holds plans only in chat and not on disk, this review missed them. Ask Codex to list its open tasks against `ROADMAP.md` §2 as its first action.

---

## 6. Order of operations (recommended)

1. **Let Codex finish its current slice, then pause it.** It was writing at 16:56 today.
2. **Land the coordination files on main** (`ROADMAP.md`, `AGENTS.md`, the `CLAUDE.md` block, this review). Use a docs-only PR from a clean worktree, never from production.
3. **Codex's first task:** commit its worktree on `codex/isolated-20260924` (no push needed yet), merge `origin/main`, renumber migrations per F2, and resolve F3/F4 keeping both sides' fixes. Report the result in `ROADMAP.md` WS-01.
4. **Consolidate Codex's gap plans** per F7.
5. **Your decisions:** F5 (one library view or two), F9 (is T2 approved?), and the proposed owners in `ROADMAP.md` §2.

---

## 7. Addendum: Larry's decisions and the memory-admission detail (2026-09-27, later)

**F5, decided:** workflows and skills are different objects, so they get **separate views**. The Workflow Viewer stays as landed. Skills Workspace adds its own `skills` view mode beside `workflows` in the shared Swift files, and must not replace or restyle the viewer. Layout options (navigation placement, Display menu entry, voice name, how a skill links to its related workflows) go to Larry before any Swift UI is built.

**F9, decided (revised later the same day):** Codex keeps owning remote access (T2) and keeps building it on its branch. Turning it on remains an undecided roadmap item. That makes the code safe to merge only if it is dormant, which it is not today:

- `jarvis/auth.py`: `auth_enabled()` returns true unless `JARVIS_AUTH_ENABLED` is exactly "false". `jarvis/authmw.py` rejects every HTTP and WebSocket request without a valid token, loopback included, with no exempt routes. `.env.example` does not set the flag. [certain, read from Codex's tree]
- Main callers that send no token would then fail. `jarvis/bot/status_tool.py` builds `httpx.AsyncClient(base_url=…, timeout=…)` with no headers, so `system_status` would report "the admin sidecar is not reachable". `scripts/deploy_main.sh` phase D requires 200 from `/api/health` and 200/307 from the bot, so it would stop with "services did not come healthy". [certain from code; not run. Test: start the merged tree with no token and `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:7861/api/health`, expecting 401]
- The native app is already ready. `JarvisHTTP.swift` sends a Keychain bearer token on every request, and the Workflow Viewer's `/api/workflows` call goes through it. [certain]
- The route inventory is stale. Codex's `admin/server.py` has 64 route decorators; main's has 68, including 10 that Codex's copy lacks (`/api/status/*` and `/api/workflows`). The middleware still covers them, but the plan's route table and any count-based test need updating. [certain]
- Product tension: tokens are created only by CLI (`python -m jarvis.auth add`), by design. That clashes with the no-shell-commands principle behind the voice-workflows decisions D-L2/D-L5. This is Larry's call when T2 is decided.

Recommended resolution: Codex adds the service token to `status_tool.py` and the deploy health checks, keeps both sides' header changes in `mcp_selfedit/logic.py`, updates the route inventory, and ships with auth **off by default** until Larry turns T2 on. Off also forces a loopback bind (`jarvis/bind.py`), which is exactly today's behaviour. The cost is that the "typo leaves auth on" safety of the true default doesn't apply until then.

**F8, memory admission: verified detail.** Memory writes happen in three stages. Each side has changed a different stage without knowing about the other's changes:

| Stage | Main (Claude, landed 09-25) | Codex's worktree (GC24-05, in progress) |
|---|---|---|
| 1. Extract: turn an exchange into fact candidates | Echo guard: `echoes_reply` rejects a candidate whose words came from Mortimer's reply and not Larry's (`memory_extraction.py`, reason `echo_of_reply`). Location facts are rejected too. [certain] | **No echo guard.** Codex's `memory_extraction.py` has no `echoes_reply` / `echo_of_reply`. [certain] |
| 2. Admit or classify: decide whether a candidate becomes a memory | Unchanged from before: heuristic admission in `admit_fact_candidate` | New `memory_admission.py`: a durable queue (extract → classify → apply), with retries, budgets and forget handling. A model classifier runs only on a verified confidential route; there is none today, so it fails closed. Migrations `0025`–`0027` (to become `0028`–`0030`). [certain] |
| 3. Maintain: resolve conflicts afterwards | Auto-settle in the sweep: one model call decides which of two contradicting facts Larry actually said; the loser is archived, Larry hears a notice, and `memory_restore` brings it back (`memory_sweep.py`, migration `0027_notice_memory_review`). [certain from the plan; live behaviour untested per its own note] | **No auto-settle.** Codex's `memory_sweep.py` is 48.2 KB against main's 63.9 KB. [certain for sizes; that the gap is auto-settle is inferred from where it was added] |
| Provenance | `source_turn` / `source_turn_id` on each fact, cleared when anything other than extraction rewrites it | `source_turn_id` carried per fact, plus evidence rules that reject provider output claiming assistant or quoted text as the user's |

Why it needs one owner:

- **Two model calls judge facts, under different privacy rules.** [certain, from code] Claude's settle, like the existing extraction and sweep calls, uses `make_memory_async_client`: the `JARVIS_MEMORY_PROFILE` route, which defaults to `claude-sonnet-5` over the direct Anthropic API. With routing off (production today, per the #80 section of the Voice Workflows plan), no privacy-route check applies, so memory facts and their exchanges go to that API. Codex's classifier refuses to run without a verified confidential route. The same data would therefore be judged under two different rules. Stricter isn't wrong, but one rule has to be chosen for the whole pipeline.
- **Order matters.** If Codex's queue lands without the echo guard, Mortimer's own words can be admitted again, which is the "Spartanburg" loop D-L7 closed. If the queue runs the classifier before extraction's rejections, the guard never sees those candidates.
- **Two provenance implementations** write the same `source_turn_id` column with different rules.

The decisions needed: the pipeline order (recommended: extract with the echo guard → Codex's queue and classifier → Claude's settle as maintenance), which system owns the memory pipeline end to end, and one privacy rule for every memory model call (direct API as today, or confidential-only as in Codex's design).

---
*Reviewer: Claude (Cowork), 2026-09-27. Read-only. No git commands were run against either checkout.*
