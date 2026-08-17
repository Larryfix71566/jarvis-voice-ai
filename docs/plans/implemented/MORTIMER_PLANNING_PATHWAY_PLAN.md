# MORTIMER PLANNING PATHWAY — implementation plan

**Problem (from the 2026-08-17 morning session's logs).** Development
planning currently runs through the wrong lane: "write an
implementation plan" becomes an ordinary developer delegation, authored
single-shot by the SUPERVISOR'S voice-brain model (whatever
`OPENAI_MODEL` is — chosen for conversational latency, recorded
nowhere) inside the voice loop's budget. Observed: two 120s timeouts on
spec generation (runs `9ed79982`, `e097fc31`); zero authorship
attribution anywhere; three runs (`b8dc2f2f`, `1704ee40`, `9d96219b`)
that reported plans "written and committed" when `repo_write_file` had
only returned `{"ok": true, "pending": true}` DRAFTS that were never
executed — `jarvis/docs/GEOLOCATION_FRONTEND_HOOKS.md` does not exist
despite two "ok" runs claiming to have written it; and drafts asking
for confirmation of documents the user has never seen.

**Decisions locked with Larry (2026-08-17):** developer timeout 300s
(a hard stop stays — it is also hang recovery); attribution via run
records + council roster (NO authored-by footers inside docs); plan
review in both surfaces (full draft content in the drawer's Output tab,
`repo_read_file` renderable in the overlay/popup); and a dedicated
PLANNING PATHWAY for development work — interface upgrades (self-edit),
new apps, and standalone dev plans alike — in which the user either
names a single authoring model from the profile registry, or has the
council draft PARALLEL complete plans from which the USER (never the
judges) chooses. Judge scores, when present, are advisory columns on
the ballot. Unchosen candidates are retained.

**Principle check:** the council's founding rule — rank, review,
advise; never author the merged artifact — survives intact: in parallel
mode each candidate has exactly ONE author, judges only advise, and a
HUMAN selects. Attribution stays meaningful in both modes.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and
report it rather than choosing.

---

## §1 Decisions

### P1 — Developer timeout: 300s

`config/agents.yaml`: `developer.timeout_s: 120` → `300`, comment
updated (observed successful spec writes ran 70–95s; 300 is headroom,
and the hard stop remains the recovery path for a hung provider call —
removing it entirely was considered and rejected 2026-08-17). No other
agent changes.

### P2 — Pending-draft honesty (the phantom-completion fix)

Trust-plan D3/D4 extended one level up, in `jarvis/agents/base.py`:

1. **Constraint (prompt-level):** when a tool result's parsed body has
   `pending: true` (parse with `json.loads`, tolerate non-JSON =
   not-pending), the batch-failure machinery (F1) additionally appends,
   after the tool-response block, a system message (verbatim):
   `"The call(s) marked pending: true created DRAFTS awaiting the
   user's explicit confirmation — NOTHING has been written, committed,
   or pushed yet. You MUST describe these as drafts awaiting
   confirmation. Never state or imply the file was written or the
   action was performed."` One message per batch even with several
   drafts (same batching rule as F1).
2. **Backstop (mechanical):** `SubAgent._loop` counts
   `drafts_created` (results with `pending: true`) and
   `drafts_executed` (successful results whose tool is in
   `{"repo_commit_write", "commit", "push"}`) across the run. If
   `drafts_created > drafts_executed` at loop end, append to the reply
   (verbatim): `"\n\n[{n} draft(s) are awaiting your confirmation —
   nothing has been written yet.]"` with `n = drafts_created -
   drafts_executed`. Deliberately count-based and append-only: like D4
   it cannot be argued with by the model, and unlike a status flip it
   does not mark otherwise-useful runs failed.

### P3 — Run-level model attribution

- Migration `0011_run_model` in `jarvis/db.py`: `ALTER TABLE agent_runs
  ADD COLUMN model TEXT` (NULL on pre-migration rows, never
  backfilled — same discipline as `tools_ok`).
- `RunLogger` records `settings.openai_model` into the row at
  `run_start` (the logger is constructed in `SubAgent.run()` with
  settings in hand).
- Display: `python -m jarvis.runlog --run <id>` detail gains a
  `model` line; the Runs panel's expanded detail gains "model: {model}"
  (renders "—" when NULL). `GET /api/runs/{id}` passes it through
  automatically (the store returns row dicts).

### P4 — Council roster line

`EditModePanel.tsx`'s round view (above the score table): one line
computed client-side from the already-fetched scores + result —
`Proposers: <distinct proposal_profile, registry order as received> ·
Judges: <distinct judge_profile where shadow=0>` plus
`· Shadow: <distinct judge_profile where shadow=1>` when present. No
backend change; the data has been in `council_scores` since v1.

### P5 — Draft review content in the Output tab

`jarvis/bot/display.py`: the draft formatters gain full content —
`repo_write_file` joins `DISPLAY_TOOLS`/`DISPLAY_SURFACE` (surface
`"drawer"`) with formatter `_fmt_repo_write_draft`: kind `"markdown"`,
title `Repo — draft {action} {path}`, body = the draft's full content
from `arguments["content"]`, truncated at 30,000 chars with a
`"\n\n… (truncated for display — the draft itself is complete)"`
suffix when over. The existing `_fmt_git_draft` (prepare_commit/push)
keeps its summary form (commits list files; there is no single
document to show). Result: the amber attention dot now points at a
fully reviewable document.

### P6 — `repo_read_file` display formatter

`repo_read_file` joins `DISPLAY_TOOLS` with surface `"window"`
(informational — overlay/popup, parkable on the second screen):
formatter `_fmt_repo_read`: kind `"markdown"`, title `Repo — {path}`,
body = `data["content"]` (same 30,000-char display truncation as P5).
"Show me the geolocation plan" then renders the committed doc through
the entire existing display pipeline.

### P7 — The planning pathway

**Job model.** A new sidecar background job slot in
`jarvis/admin/server.py`: `_plan_lock` / `_plan_job` (the `_run_job` /
`_council_job` shape, one planning job at a time):

```python
_plan_job = {
    "state": "idle",  # idle | running | awaiting_choice | done | error
    "mode": None,      # "single" | "council"
    "goal": None,
    "profile": None,   # single mode: the author
    "round_id": None,  # council mode
    "candidates": None,  # council mode: [{"label", "profile", "content",
                         #   "advisory_mean": float|None}] — full plans
    "plan": None,      # the final chosen/authored plan text
    "author": None,    # profile name of the chosen/single author
    "error": None, "started_at": None, "finished_at": None,
}
```

**Endpoints:**

| Endpoint | Behaviour |
|---|---|
| `POST /api/plan/start {goal, mode, profile?, members?}` | validates (goal required; mode `single` requires a usable profile — explicit, else the P7 default; mode `council` optional members narrowing, same shape as council convene); refuses if a planning job is running; launches the daemon thread; returns `{"ok": true, "started": true}` |
| `GET /api/plan/job` | polling target; `candidates` content included only in `awaiting_choice`/`done` |
| `POST /api/plan/choose {label}` | council mode, state `awaiting_choice` only: records the choice (`council.record_user_choice`), sets `plan`/`author`, state → `done` |
| `POST /api/plan/adopt {path?}` | state `done` only: creates a draft-gated repo write of `plan` at `path` (default `docs/plans/<slugified-goal>.md`) via `mcp_servers.mcp_repo.logic`'s draft function (the SAME actions-table gate voice uses — the sidecar imports mcp_repo logic exactly as it already imports mcp_git logic); returns the action summary. Adoption APPENDS the attribution footer (below) to the plan text before drafting. Confirmation happens through the existing confirm paths (voice `repo_commit_write`, or P7's panel confirm button which calls the same logic function) |
| `POST /api/plan/cancel` | any non-idle state → idle (candidates remain in the council round's log) |

**Single mode:** one completion call to the named profile (the
`upgrade_models.yaml` registry, key-checked) with a locked
`PLAN_AUTHOR_PROMPT` ("write a complete, self-contained implementation
plan document in markdown for: {goal} …" — full text authored at
implementation in `jarvis/prompts.py`, the single source of truth for
prompts). Per-call timeout `PLANNING_MEMBER_TIMEOUT_S = 300.0`
(`jarvis/council/config.py`, beside `COUNCIL_MEMBER_TIMEOUT_S` — a
plan is a document, not a brief).

**Council-parallel mode:** new PUBLIC functions in
`jarvis/council/council.py` (additive; `convene()`/`select_winner`
untouched — self-edit escalation behavior cannot change):

```python
async def draft_candidates(goal: str, *, members: dict | None = None,
                           judge: bool = True) -> RoundResult | None
def record_user_choice(round_id: str, label: str) -> None
```

`draft_candidates` fans out every usable proposer profile (members
narrowing honored; proposer set = the FULL registry's key-present
profiles by default, not tier-1 only — the user is paying deliberate
attention here) with the `PLAN_AUTHOR_PROMPT`; when `judge=True`, the
existing judge machinery scores the candidates (V4 label shuffle, V6
parsing, V2-style context) and the scores are stored/returned as
ADVISORY (`advisory_mean` per candidate); `select_winner` is NOT
called; the round row is written with `workflow="planning"`,
`placement="doc"`, `status="awaiting_user"`, `winner_*` NULL.
`record_user_choice` sets `winner_label`/`winner_profile`/
`select_reason="user choice"`/`status="ok"` on the round — the
existing Recent Rounds UI and `--agreement` queries then see a
completed round (agreement metrics already filter by workflow where it
matters; `workflow="planning"` rounds are additionally EXCLUDED from
`compute_agreement`'s corpus — user choices are not judge-quality
evidence). Unchosen candidates persist in `council_scores`
(proposal rows) and the round JSONL — the road not taken stays
readable.

**Default profile:** `JARVIS_PLANNING_PROFILE` env (documented in
`.env.example`); absent → the upgrade registry's default profile
(same resolution `POST /api/selfedit/run` uses).

**Feeding self-edit:** `POST /api/selfedit/run` gains optional
`plan: str` — when present, `UpgradeAgent.run()` injects it as a
system message before planning begins (the same injection point the
council's escalation brief already uses). The Edit panel's chosen-plan
view gains "Start self-edit with this plan" wiring goal+plan through.
App scaffolds consume plans the same way a human would — paste/refer —
no `mcp_apps` change in this plan.

**Voice tools:** `mcp_servers/mcp_selfedit/server.py` (already the
sidecar's thin voice client) gains four tools — `plan_start(goal,
mode="single", profile="", confirm=False)` (confirm-gated like
`selfedit_start`), `plan_status()`, `plan_choose(label)`,
`plan_adopt(path="", confirm=False)` — thin HTTP passthroughs.
`skill.yaml` updated; `tests/integration/test_registry.py`'s
`TOTAL_TOOLS` 44 → 48 and the selfedit count comment 5 → 9.

**UI:** `EditModePanel.tsx` gains a "Planning" card above the council
card: goal input; mode toggle (single profile select — reusing the
models list — vs "council: parallel drafts" with the existing
membership picker); Start; 3s job polling (the established pattern);
in `awaiting_choice`, candidates render as tabs (label + author +
advisory score when judged), full markdown content in a scrollable
`<pre>`, a "Choose this plan" button per candidate; in `done`, the
chosen plan with "Adopt as draft" (path input, default prefilled) and
"Start self-edit with this plan" buttons. Adopt → the P5 draft review
flow (amber dot, Output tab, confirm).

**Routing:** the developer sub-agent's prompt (`jarvis/prompts.py`)
gains (verbatim): `"For implementation plans, specifications, or
design documents, never author the document yourself in this
conversation — call plan_start (choosing mode and profile per the
user's words) and report its status. Quick factual summaries are still
yours."` The Supervisor needs no rule change (rule 8 already sends
development to developer).

**Attribution footer (amended 2026-08-17 — supersedes the earlier
no-footers choice, which predated this pathway).** Larry's requirement
is durable identification of the authoring model; the transient
`_plan_job` slot is overwritten by the next job, so single-mode
authorship would otherwise persist nowhere. Every ADOPTED plan document
therefore ends with (verbatim format):

```
---
*Drafted by {profile} ({provider_model_string}) — {YYYY-MM-DD}.*
```

Council mode appends after the model line: ` Selected by Larry from
{n} council candidates (round {round_id}).` The footer is appended at
ADOPTION (one place: the adopt endpoint), never during drafting — so
candidates on the ballot stay footer-free and byte-comparable, and a
plan that is never adopted stamps nothing.

### P8 — What this plan deliberately does NOT do

- No authored-by footers in NON-plan documents the developer writes in
  ordinary delegations — the footer is the adopt endpoint's act, not a
  general writing habit (P3's run records cover ordinary writes).
- No automatic council review of single-author plans, and no
  auto-triggering of the council for anything — convening stays
  deliberate (the user picks council mode).
- No change to `convene()`/`select_winner`/self-edit escalation.
- No removal of the developer's ability to write ordinary files — P7's
  routing rule is about plan/spec DOCUMENTS.
- No planning-job runlog rows (it is not a delegation; its record is
  `_plan_job` + the council round + the adopted draft).

---

## §2 Files

**Modified:** `config/agents.yaml` (P1); `jarvis/agents/base.py` (P2);
`jarvis/db.py` (P3 migration 0011); `jarvis/runlog/store.py` (P3 — the
`INSERT INTO agent_runs` at line ~245 gains the `model` column, with
the value threaded from `RunLogger`'s constructor in
`jarvis/runlog/__init__.py`, which `SubAgent.run()` constructs with
settings in hand) + `jarvis/runlog/cli.py` +
`web/src/components/RunsPanel.tsx` (P3 display);
`web/src/components/EditModePanel.tsx` (P4 roster, P7 Planning card);
`jarvis/bot/display.py` (P5, P6); `jarvis/admin/server.py` (P7
endpoints/job); `jarvis/council/council.py` + `jarvis/council/
config.py` + `jarvis/council/agreement.py` (P7 draft_candidates /
timeout / planning-workflow exclusion); `jarvis/prompts.py` (P7
prompts + developer routing); `mcp_servers/mcp_selfedit/server.py` +
`skill.yaml` (P7 tools); `jarvis/agents/upgrade_agent.py` +
`POST /api/selfedit/run` (P7 plan param); `.env.example`, `CLAUDE.md`.

**New:** `tests/unit/test_admin_plan.py`,
`tests/acceptance/planning-pathway.md`; test updates:
`test_db.py` (0011), `test_subagent.py` (P2), `test_display.py`
(P5/P6), `test_registry.py` (counts), `test_council_*` (draft_
candidates + agreement exclusion), `test_upgrade_agent.py` (plan
param), `test_runlog_store.py` (model column).

---

## §3 Implementation order

1. P1 (one line) + P2 + tests — the honesty fix ships first.
2. P3 migration + stamps + displays + tests.
3. P5 + P6 display formatters + tests.
4. P7 council pieces (`draft_candidates`, `record_user_choice`,
   timeout, agreement exclusion) + tests.
5. P7 sidecar job + endpoints + `test_admin_plan.py`.
6. P7 selfedit `plan` param + mcp_selfedit tools + registry counts.
7. P7 Edit panel Planning card + P4 roster; build/lint.
8. Prompts/routing; docs; acceptance checklist; full suite.

---

## §4 Verification (tests/acceptance/planning-pathway.md, key items)

- [ ] Re-run yesterday's failure: "write a backend spec … and commit
      it" — the agent now SAYS the draft awaits confirmation (P2), the
      Output tab shows the full document (P5), amber until confirmed.
- [ ] "Show me the geolocation plan" renders the committed doc in the
      overlay/popup (P6).
- [ ] Runs panel detail shows the model for new runs; old rows show —
      (P3).
- [ ] Single-mode plan: "have claude-opus plan X" → job runs minutes
      without timeout, panel shows author, adopt → draft → confirm →
      file exists.
- [ ] Council mode: parallel candidates appear with authors + advisory
      scores; choosing one completes the round; the round view shows
      the full roster (P4); unchosen candidates remain readable in the
      round log.
- [ ] Chosen plan feeds a self-edit run via the panel button.
- [ ] `--agreement` output unchanged by planning rounds (excluded).
- [ ] Full pytest + web build/lint clean; routing eval unaffected.

---

## §5 Risks

| Risk | Level | Mitigation |
|---|---|---|
| P2 backstop misfires on non-draft `pending` fields | Low | Only `pending: true` at the result's top level counts; tools are ours and use it only for drafts |
| Parallel full-doc fan-out is slow/expensive | Medium | Deliberate user choice (council mode is opt-in per job); 300s per member; one job at a time |
| `awaiting_user` rounds pollute council metrics | Low | Explicit `workflow="planning"` exclusion in `compute_agreement` (tested) |
| Registry tool-count churn breaks tests | Certain | Counts updated in the same commit (test_registry comment discipline) |
| Sidecar writing repo drafts widens surface | Low | Same `mcp_repo.logic` draft→confirm gate as voice; no new write primitive |

---

## §6 Rollback

P1 is a config value; P2–P6 revert file-by-file (additive column stays,
harmless); P7 is additive machinery behind new endpoints/tools — with
the Planning card and mcp tools reverted, nothing reaches it. No kill
switch: the pathway only runs when explicitly started.

---

## §7 Approval

- [x] Larry approves.
- [x] Implementation may begin.
- [x] Implemented 2026-08-17: all of P1-P8 done, tests green (unit +
      integration), web build (tsc)/lint clean. See CLAUDE.md's
      "Planning pathway" section and tests/acceptance/planning-pathway.md.
