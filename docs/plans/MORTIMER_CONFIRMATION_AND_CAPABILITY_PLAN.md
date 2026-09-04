# Mortimer confirmation & capability plan

**Date:** 2026-08-18
**Branch:** feat/plan-review-and-docs
**Status:** IMPLEMENTED (acceptance checklist in tests/acceptance/).

---

## §1 What happened, exactly (the evidence this plan answers)

Two live investigations on 2026-08-17/18, both fully log-backed:

**Incident 1 — the silent capability hole.** Every developer run since
Part A of MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md landed had run
on the Haiku voice model, not `kimi-k3`: `MOONSHOT_API_KEY` was never in
the vault (the migration audit comments in `.env` prove it was absent from
`.env` on 2026-08-16), so `SubAgent.__init__`'s A1 resolution fell back —
one `subagent_model_profile_fallback` warning at boot, then silence.
Downstream, **every council round ever recorded is
`too_small, proposer_count=0`**: the economy tier (`kimi-k2`,
`gpt-4.1-mini`) had zero working keys, so the E1 escalation net has never
once fired. The `gpt-4.1-mini` registry profile is additionally a
landmine: `OPENAI_API_KEY` in this deployment is an Anthropic key aimed at
`https://api.anthropic.com/v1/` (see `.env`'s `OPENAI_BASE_URL`), so that
profile's `key_present=True` is a lie — calls to real `api.openai.com`
401. Three layers of graceful degradation stacked into a system that
looked alive and did nothing, with one log line as the only witness.
(The key itself was vaulted and verified working on 2026-08-18 —
`kimi-k3` now appears in the run log — but nothing prevents a recurrence,
and the council remains unformable.)

**Incident 2 — the confirmation death spiral.** With the model fixed,
Larry asked for a Weather.gov/RainViewer integration plan by voice.
Eighteen developer delegations between 01:16 and 01:41 UTC circled the
`plan_start` confirmation gate without ever passing it. Root cause is
structural, not a prompt bug: the two-phase pattern demands
"confirm=true only after the user explicitly agrees **in a new turn**" —
but each delegation constructs a **fresh, stateless SubAgent**. The
confirm turn always lands in an agent that never saw the preview, so it
either re-previews or refuses (run `1b724baf`, verbatim: "there is no
prior draft on file to confirm — this is a fresh request"). The one run
that broke through (`9e15f4c8`) did so by calling `confirm=false` then
`confirm=true` back-to-back in a single run — the model waving itself
through, defeating the gate's entire purpose. The gate is therefore
simultaneously **unpassable for legitimate confirmed requests and
trivially bypassable by the model**. The drafted plan then sat finished
in `_plan_job` behind two more gates (`plan_adopt` confirm →
`repo_commit_write` confirm) and was never written or displayed.

The contrast that names the fix: `repo_write_file` → `repo_commit_write`
works fine by voice because its pending state is a server-side
`action_id` in the DB that any later delegation can reference. The
boolean `confirm=true` pattern keeps its state in the agent's memory,
which is wiped every delegation.

**Locked policy (Larry, 2026-08-18):** "If I ask the interface to
produce a plan for a specified project or upgrade, it should be assumed
that I mean: present me with a plan document that I can review. There
doesn't need to be explicit authorization at every step — the plan
should be returned for review without any further interaction from me,
unless there are qualifying questions."

**Design principle this plan applies everywhere:** confirmation belongs
at consequential, hard-to-reverse boundaries only (opening a PR,
creating a GitHub repo, destroying session work). Authoring a document,
starting a sandboxed run, or spending a few minutes of tokens is not
such a boundary. And where a gate remains, its enforcement must not
depend on sub-agent memory.

---

## §2 Part F — frictionless planning (F1–F5)

### F1 — `plan_start` loses its confirmation entirely

`mcp_selfedit`'s `plan_start` drops the `confirm` parameter: calling it
starts the job immediately (same for review jobs via `review_path`).
`logic.plan_start` keeps its validation (empty goal, bad mode, unknown
profile — all still refuse with spoken-friendly errors) and posts
`/api/plan/start` directly. The reply is the "started, this takes a few
minutes" summary. `TOTAL_TOOLS` stays 55 (parameter removals only,
nothing added or dropped). The tool description and the developer prompt's planning
paragraph are rewritten with no confirmation language: a request for a
plan/spec/review IS the authorization.

Qualifying questions move to where they belong — the Supervisor: its
prompt gains one sentence: if a plan request's subject is genuinely
ambiguous (no identifiable project/upgrade/document), ask ONE clarifying
question before delegating; otherwise delegate immediately and say the
draft has started.

### F2 — auto-save on completion (no adopt gate, no draft gate)

When a planning job finishes, the sidecar saves the document itself —
deterministic post-processing of a user-requested job, not an LLM
choosing to write:

- `_run_plan_single` settling `done` → save.
- `plan_choose` (council mode) → after `record_user_choice`, save.
- Save = write `docs/plans/<slug>.md` (or `docs/reviews/<slug>.md` for a
  review job) directly from the sidecar process — plain file write, NOT
  the `repo_write_file` draft gate. The attribution-footer composition
  moves from `/api/plan/adopt` into one helper `_plan_footer(job)` used
  by both auto-save and F3's re-save, so footer logic still exists in
  exactly one place (P7's rule preserved: candidates on the ballot stay
  footer-free; only the saved artifact is stamped).
- The job dict gains `saved_path`; `GET /api/plan/job` exposes it.
- Slug collision: if the target file exists, append `-2`, `-3`, … —
  never overwrite an existing plan document.

Council mode keeps exactly ONE interaction — `plan_choose` between
candidates — because that is a genuine user decision, not bureaucracy.

### F3 — `plan_adopt` becomes a no-confirm re-save

`plan_adopt(path)` remains for the "save it somewhere else / save it
again" case: writes immediately to the given path (still footer-stamped
via `_plan_footer`), no confirm parameter, no draft. Path is validated
by the same rules as F2's writer (F5). `plan_status` says where the
document was auto-saved.

### F4 — completion is announced and displayed, not polled by voice

New `jarvis/bot/plan_watcher.py`, modeled directly on
`jarvis/bot/reminders_watcher.py` — the watcher that ALREADY injects
spoken announcements into a live session, with an is_connected gate —
same `start()/stop()/_run()/tick_once()` shape and
log-and-keep-going discipline (`memory_watcher.py` shares it): every
`PLAN_WATCH_INTERVAL_S = 5.0` it GETs the
sidecar's `/api/plan/job` (localhost, cheap; sidecar unreachable = skip
tick silently). On a state **transition** (dedupe key:
`(started_at, state)` — announce each at most once):

- `running → done` (single mode): speak a canned line via
  `TTSSpeakFrame` — the U5 `ui/noop` precedent: no LLM in the path —
  "The plan is ready and saved to <basename>. It's on your display." and
  push the document to the display layer.
- `running → awaiting_choice` (council mode): speak "N candidate plans
  are ready — say which one you'd like." and display the candidate list
  with advisory scores.
- `→ error`: speak the error summary once.

Display push reuses `jarvis/bot/display.py`'s existing app-message
machinery: a new pseudo-tool name `plan_ready` joins `DISPLAY_TOOLS`
with `DISPLAY_SURFACE["plan_ready"] = "window"` (an informational
document → the floating display window / popup, same surface as weather
and research), truncated at the existing `DOC_DISPLAY_MAX_CHARS`.
Kill switch: `JARVIS_PLAN_WATCHER_ENABLED` (default true), enforced at
the single registration site in `pipeline.py`, matching every other
watcher/feature switch in this codebase.

### F5 — the auto-save writer's own boundary

The sidecar's direct writer refuses any path outside `docs/plans/**`
and `docs/reviews/**` (normalized, no `..`, repo-relative). This is
narrower than the self-edit allowlist on purpose: F2/F3 write exactly
one kind of artifact. Everything else the planning pathway does remains
read-only.

---

## §3 Part G — the two-phase gate audit (G1–G3)

Full inventory of boolean-confirm tools and their dispositions:

| Tool | Action | Disposition |
| --- | --- | --- |
| `plan_start` | start a drafting job | **gate removed** (F1) |
| `plan_adopt` | write a docs file | **gate removed** (F3) |
| `selfedit_start` | start a sandboxed edit run | **gate removed** (G1) |
| `app_build_start` | clone + edit an app workspace | **gate removed** (G1) |
| `selfedit_validate` | read-only checks | no gate today — unchanged |
| `selfedit_submit` | open a PR on Mortimer | **gate kept**, prompt-fixed (G2) |
| `app_build_submit` | open a PR on an app repo | **gate kept**, prompt-fixed (G2) |
| `app_create` | create a real GitHub repo | **gate kept**, prompt-fixed (G2) |
| `selfedit_revert` | destroy session work | **gate kept**, prompt-fixed (G2) |
| `prepare_commit`/`commit`, `repo_write_file`/`repo_commit_write` | repo writes | already `action_id`-based — **unchanged** |

### G1 — start gates removed

`selfedit_start` and `app_build_start` drop `confirm`: they start
immediately. Rationale: a self-edit run works on a sandbox branch and an
app build works in a disposable workspace clone — nothing user-visible
mutates until the SUBMIT boundary, which keeps its gate. The runs cost
minutes and tokens, which is exactly the cost the user accepted by
asking. Both tools keep their validation (unknown profile, missing goal,
busy slot) and their "started, ask me for status" reply.

### G2 — remaining gates: enforcement moves to the layer that heard the user

The four kept gates keep their two-phase tool shape (`confirm=false`
preview → `confirm=true` execute — the mechanics are self-contained per
call and work across delegations; run `9e15f4c8` proved it). What breaks
is the sub-agent prompt demanding the agent itself have witnessed the
user's confirmation, which a fresh delegation never has. Fix, in
`jarvis/prompts.py`'s developer prompt (one rule, applied to all four):

> When a delegated task states that the user has already confirmed the
> action, call the tool with confirm set to true directly — do not
> preview again. The Supervisor is the layer that heard the user; a
> fresh delegation asserting confirmation IS the confirmation reaching
> you.

And the matching Supervisor-side rule: only assert prior confirmation in
a delegation when the user actually confirmed **that specific action**
in this conversation; never to bypass a gate the user hasn't passed.
This is a trust statement, not a loophole: the Supervisor conversation
is the ONLY place user confirmation exists; pretending the sub-agent
can verify it independently is the fiction that caused the spiral.

### G3 — explicit non-goals

Merging PRs stays human-on-GitHub, always. Repo-write `action_id` gates
are untouched. No auto-submit of anything: submit tools still require
the user's word. `selfedit_revert` keeps its gate because it destroys
work. The wake word, vault, and registry deny rules are untouched.

---

## §4 Part H — loud capability degradation (H1–H3)

### H1 — fallback becomes refusable, per agent

`config/agents.yaml` gains an optional per-agent key
`on_profile_fallback: warn | refuse` (default `warn` = today's
behavior). `SubAgent.__init__` records the fallback fact
(`self._profile_fallback: str | None` — the failed profile name) instead
of only logging; with `refuse`, `delegate_task` returns immediately —
before the run starts, no run-log row wasted:
`REFUSED: the developer's assigned model (kimi-k3) is unavailable —
<key_env> is missing. Fix the key (python -m jarvis.vault set <key_env>)
or change model_profile in config/agents.yaml.` The developer entry sets
`refuse`: a Haiku developer run is worse than no run — it produces
plausible-looking failures that misdirect debugging (incident 1's exact
cost). Conversational agents stay `warn` (they run correctly on the
voice model by design).

### H2 — the capability report reaches the console

At client connect, alongside the existing boot messages, the bot sends
one RTVI app message `{"type": "capability", "agents": [{name,
profile, resolved_model, fallback: bool}]}` built from the constructed
sub-agents. The console topbar shows an amber warning chip (existing
`--attn` semantics from the engagement layer) when any agent reports
`fallback: true` — hover text names the agent, the dead profile, and the
missing key env. One new small component; no polling; disappears when a
restart resolves cleanly. `scripts/check_env.py` gains a "model
registry" section: for each profile, key env present/absent — so the
preflight humans already run surfaces the hole before boot does.

### H3 — the council becomes formable on the keys that exist

`config/upgrade_models.yaml` changes:

- **Remove `gpt-4.1-mini`** — no real OpenAI key exists in this
  deployment, and the profile's `key_present=True` via the
  Anthropic-valued `OPENAI_API_KEY` makes it actively misleading (§1).
- **Add `claude-haiku`** (model `claude-haiku-4-5`, tier `economy`) and
  **`claude-sonnet`** (model `claude-sonnet-5`, tier `mid`), both
  `api_key_env: ANTHROPIC_API_KEY`, same base_url as the existing
  `claude-opus` entry.

Resulting tiers: economy = `kimi-k2`, `claude-haiku`; mid = `kimi-k3`,
`claude-sonnet`; frontier = `claude-opus`, `claude-fable-5`. A tier-1
round now fields ≥2 proposers and ≥2 judges from the two working
providers — and remains formable on Anthropic alone if the Moonshot key
ever disappears again (the disjointness rule is per-profile, not
per-provider; `resolve_members`'s `exclude` already guarantees a model
never judges its own proposal). Registry default stays `kimi-k3`.
`config/upgrade_models.yaml` stays off the self-edit allowlist.

Verification for H3 is empirical, not assumed: one manual
`POST /api/council/convene` (Edit panel) must produce a round with
`proposer_count >= 2` and a winner — the first formed round in this
deployment's history.

---

## §5 Files

**Part F:** `mcp_servers/mcp_selfedit/{logic.py,server.py}` (F1/F3
signatures + descriptions); `jarvis/admin/server.py` (F2 auto-save +
`_plan_footer` + `saved_path`, F3 adopt rewrite, F5 path check);
`jarvis/bot/plan_watcher.py` (new, F4); `jarvis/bot/pipeline.py` (F4
registration + kill switch); `jarvis/bot/display.py` (F4 `plan_ready`
surface); `jarvis/prompts.py` (F1 developer paragraph + Supervisor
qualifying-question rule); `.env.example`
(`JARVIS_PLAN_WATCHER_ENABLED`).
**Part G:** `mcp_servers/mcp_selfedit/{logic.py,server.py}`
(`selfedit_start` confirm removal); `mcp_servers/mcp_apps/{logic.py,
server.py}` (`app_build_start` confirm removal); `jarvis/prompts.py`
(G2 rules, both layers).
**Part H:** `config/agents.yaml` + `jarvis/agents/base.py` +
`jarvis/agents/delegate.py` (H1); `jarvis/bot/pipeline.py` +
`web/src/components/CapabilityChip.tsx` (new) wired into the topbar in
`App.tsx` (H2); `scripts/check_env.py` (H2);
`config/upgrade_models.yaml` (H3).
**Tests:** `tests/unit/test_plan_watcher.py` (new: tick dedupe, canned
announcements, sidecar-down silence);
`tests/unit/test_admin_plan.py` (auto-save single + council, slug
collision, footer once, F5 boundary); `tests/unit/test_mcp_apps_logic.py`
+ selfedit-side tests (signature updates); `tests/unit/test_subagent.py`
+ `test_delegate.py` (H1 refuse mode); routing-eval additions pinning
that "draft a plan for X" delegates once with no confirmation language.
**Docs:** CLAUDE.md (planning pathway + model discipline paragraphs
updated), `tests/acceptance/confirmation-and-capability.md` (new).

---

## §6 Implementation order

1. F2 + F5 + F3 (sidecar auto-save; the core payoff) + tests.
2. F1 + G1 (gate removals, both servers) + prompt rewrites + tests.
3. F4 watcher + display surface + kill switch + tests.
4. G2 prompt rules (both layers) + routing-eval cases.
5. H3 registry change; **restart stack; run one manual convene round —
   must form** (first empirical council verification ever).
6. H1 refuse mode + tests; H2 capability chip + check_env section.
7. Docs, acceptance checklist, full pytest + `npm run build`/lint,
   `RUN_LIVE=1 routing_eval` ≥ 90% (prompts changed — mandatory this
   time), **restart the bot** (prompts/config read at boot).
8. Live acceptance: "draft a plan for adding X" by voice → zero further
   interactions → voice announcement + display window shows the plan +
   `docs/plans/<slug>.md` exists with footer. Then the same for a
   council-mode request with exactly one interaction (the choice).

## §7 Rollback

Every part is independently revertible: F4 by its kill switch; F1/F3/G1
by restoring the `confirm` parameters (one commit); F2 by restoring the
adopt-gated flow; H1 defaults to `warn` (removing the yaml key restores
today's behavior exactly); H3 by restoring the registry file. No
migrations, no data-shape changes anywhere in this plan.

## §8 Approval

- [ ] Larry approves.
- [ ] Implementation may begin.
