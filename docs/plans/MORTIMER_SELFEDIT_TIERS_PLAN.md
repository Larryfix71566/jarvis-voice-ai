# Mortimer Self-Edit Tiers — make self-edit useful without letting it destroy itself

**Status:** IMPLEMENTED (status line added 2026-09-17; the document had
none). `jarvis/selfedit/allowlist.py` classifies paths into the tiers
(`classify()` groups `denied` / `core` / the rest), `jarvis/selfedit/service.py:132–153`
returns them from the preview, and `mcp_servers/mcp_selfedit/logic.py:188`
applies the Tier B rule — a preview that names core paths must say so before
anything is staged. Both files cite this plan by name at the site that
implements it.


*Larry, 2026-08-31: "if we continue to deny everything we want to do self-edit wise
then a self-edit is not useful, we have to structure the self-edit so that we can
make changes/upgrades without running into dead ends while still limiting the
ability of the interface to destroy itself."*

## 1. The reframe

The deny list was doing a job the human merge already does. Mortimer cannot merge.
A bad change to `jarvis/bot/display.py` lives on a sandbox branch in an isolated
worktree (since f4a3e5b), passes or fails the validation gates, and lands as a PR a
human reads. The running bot is untouched until the human merges *and* restarts.
So for most of `jarvis/`, denying edits did not prevent self-destruction — it
prevented the loop from proposing anything that matters. 2026-08-30: three
self-edit runs in a row were correctly declined by the planner ("display.py is not
on the allowlist"), each after confirm + staging + ~2.5 minutes of planner time.

What the deny list *should* protect has a precise definition: **files whose
corruption the loop cannot recover from, because they are the loop.**

## 2. Three tiers

| Tier | Where | Rule |
|---|---|---|
| **0 — human-only** (`deny`) | `jarvis/selfedit/**`, `jarvis/admin/**`, `jarvis/agents/upgrade_agent.py`, `jarvis/agents/workspace.py`, `jarvis/db.py` (migrations), `jarvis/vault.py`, `config/self_edit_allowlist.json`, `config/upgrade_agent.yaml`, `config/upgrade_models.yaml`, `config/skills.yaml`, `skills/**`, `scripts/mortimer.sh`, `scripts/run_admin.sh`, `scripts/check_allowlist.py`, `.github/**`, `requirements*`, `web/package*.json`, `.env*`, `data/**`, `*.vault`, `DEVIATIONS.md`, `macos/**` | Refused by the tool at write time and at preview. A broken Tier-0 file cannot be repaired by the next self-edit — that is the only genuine "destroy itself" case. `macos/**` is here for a different reason: no `swift build` gate exists, so an edit there would be unvalidated by construction; it moves to Tier B the day such a gate exists. |
| **B — core, with ceremony** (`core`) | `jarvis/**` (everything not denied or routine), `scripts/**` | Editable. A plan document is **required at preview** (refused before staging otherwise). Validation gains a fifth gate, `core_imports`: `import jarvis.bot.pipeline, jarvis.bot.display, jarvis.agents.base, jarvis.agents.delegate, jarvis.agents.supervisor, jarvis.skills.registry` in the session worktree. The PR body gets a **CORE CHANGE** block and the spoken submit notice says so. The human runs the branch and holds a real conversation before merging — the last gate, as always. |
| **A — routine** (`allow`) | `web/src/**`, `web/public/**`, `config/**`, `jarvis/prompts.py`, `jarvis/skills/**`, `jarvis/services/**`, `mcp_servers/**`, `tests/**`, `docs/**`, `*.md` | Unchanged. |

Precedence for a path on several lists: **deny > allow (routine) > core**.
`jarvis/prompts.py` is on allow and matches `jarvis/**`; it stays routine.

## 3. Pre-flight at preview

`POST /api/selfedit/stage` now runs `SelfEditService.preflight(goal, has_plan)`
before creating a staging record: it extracts the repo paths the goal text names
(`jarvis/selfedit/allowlist.py`'s `extract_paths` — slashed paths and known
source suffixes, URLs/versions ignored), classifies them, and refuses in one
sentence when a Tier-0 file is named or a Tier-B file is named without a
`plan_path`. `mcp_selfedit`'s preview summary says "this touches the voice/agent
core (…)" so the user hears it before saying yes. Extraction is best-effort — a
goal that names no files passes through, and the planner's own allowlist check
still governs every write.

## 4. What does not change

- One session at a time; sandbox branch from `origin/main`; rollback tag; human
  merge only; no force-push. The worktree isolation from f4a3e5b is the
  precondition that makes Tier B safe.
- The allowlist file itself, the model registry, and loop bounds stay human-only.
- `scripts/check_allowlist.py` (CI) uses the same `Allowlist` and is unchanged in
  behaviour: `is_allowed` is "not denied and (routine or core)".

## 5. Files

`jarvis/selfedit/allowlist.py` (tiers, `classify`, `extract_paths`),
`config/self_edit_allowlist.json` (`core` list; `jarvis/bot|agents|wakeword`
leave `deny`), `jarvis/selfedit/service.py` (`core_imports` gate,
`_core_change_block`, `preflight`), `jarvis/admin/server.py` (stage pre-flight,
`tiers`/`core_change` in the staging response), `mcp_servers/mcp_selfedit/logic.py`
(spoken core note), `jarvis/agents/upgrade_agent.py` (SYSTEM_PROMPT rule 2 names
the tiers and tells the planner NOT to decline a core goal for being "not UI").
Tests: `test_selfedit_allowlist.py`, `test_selfedit_service.py`,
`test_admin_selfedit.py`.

*Drafted by Claude Fable 5 with Larry — 2026-08-31.*
