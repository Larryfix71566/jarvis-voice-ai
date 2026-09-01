# Mortimer Optimization Plan — Cost, Memory, and Model Routing

Status: Rev 3.1 — 2026-09-01 (conflicts resolved + model-floor policy; see "Rev 3 resolutions" at the end)

**Standing policy (Larry, 2026-09-01) — the model floor:** the ONLY agent that may run Haiku is the voice agent (Supervisor). Every other agent — the five specialists and the planner/executor loop — runs at Sonnet-or-equivalent or above. Cost work on those agents is caching, context slimming, effort, and choosing *among* Sonnet-class-and-up models; it is never dropping below the floor. This overrides the earlier "Haiku is correct for the conversational agents" stance in `config/agents.yaml` and CLAUDE.md, and it is bound in CONFIG plus a test (Phase 0b item 5), not stored as a memory fact — a fact only persuades a model, it cannot bind a tool's behaviour (the same lesson as `jarvis_units`).
Scope: sub-agents and supervisor. Voice transport (STT/TTS/realtime) explicitly exempt — stays on native provider connections for latency.

Guiding order: **measure → cache → gate memory writes → route by capability → slim context → batch/local.**
Each phase has exit criteria; no phase starts until the prior phase's exit criteria are met (exceptions noted).

---

## Phase 0a — Diagnostic Findings (completed 2026-09-01)

Live diagnostics run against the repo before any implementation; these
supersede several assumptions the original plan carried.

**Resolved — no action needed:**
- OpenRouter chain works end-to-end in the running bot: vault →
  inject_env → process env → council calls all verified (or-gemini-flash
  won round e48cfbe1; or-grok-4.3 judged it).
- DeepSeek "never seen" was visibility, not failure: `or-deepseek`
  proposed and was scored in that round. Nothing outside the council
  assigns DeepSeek; council internals surface nowhere in the UI (see
  agent-card task below).
- `available_models()` lists all 13 profiles regardless of key presence —
  the picker was never filtering DeepSeek out.

**Root-caused — fixes queued in Phase 0b:**
- **kimi-k3 judge abstentions**: K3 is always-on thinking (probe: 39
  completion tokens to answer "OK"; 36s on a 2.3K-token judge task).
  Real judge workloads (8–15K tokens) project to 90–180s+ against
  `COUNCIL_MEMBER_TIMEOUT_S = 120`. Every K3 judge call in round
  e48cfbe1 timed out; `asyncio.TimeoutError` stringifies empty, hence
  the blank abstain reasons. The codebase already acknowledges this
  failure class for plan drafting (`PLANNING_MEMBER_TIMEOUT_S = 300`)
  but never extended it to judging.
- Same mechanism [likely] explains "kimi called frequently, never
  finishes" in the upgrade loop, where kimi-k3 is the default planner.

**Data points banked:**
- Council round records already carry per-round prompt/completion token
  totals — a baseline cost source that exists before the shim lands.
- An economy model (gemini-flash, mean 7.43) won a real planner round.
  Frontier-for-planning is adopted as default (below) but stays a
  measurable prior: `retry_validated` per round is the ground-truth
  check, revisit after ~a month of rounds.
- Second silent-degradation bug this month with the same shape (KB vault
  before, dead judge now): components failing quietly while the system
  reports success. Visible-abstention UI (below) is the structural
  answer.

## Phase 0b — Immediate Fixes (before or alongside instrumentation)

1. Commit or stash the pre-existing uncommitted `agents.yaml` +
   `pipeline.py` changes — every diff below gets noisier until done.
2. **K3 timeout pair:**
   - `config/upgrade_models.yaml`, kimi-k3 profile: add
     `timeout_s: 240` with a dated comment citing round e48cfbe1.
   - `jarvis/council/council.py` line ~249: honor it —
     `effective = max(timeout_s, float(profile.get("timeout_s", 0)))`
     then `asyncio.wait_for(..., timeout=effective)`. `max()` so a
     profile can buy more rope, never less; the planning pathway's 300s
     floor is untouched.
   - Accepted trade: escalation rounds including K3 as judge can run
     ~4 min wall time. If councils ever enter the interactive loop,
     revisit by pulling K3 from the judge tier instead.
3. **Registry default flip:** `upgrade_models.yaml` `default: kimi-k3` →
   `default: claude-fable-5`, dated comment in house style. K3 stays in
   the registry and council; it stops being the default brain.

   **Blast radius (Rev 3, grep-confirmed):** `registry["default"]` is the
   final fallback for FOUR resolution paths, not one —
   `UpgradeAgent`/`AppBuildAgent` (the self-edit / app-build **edit
   loop**, via `JARVIS_UPGRADE_PROFILE`/`JARVIS_APPBUILD_PROFILE` →
   default), the planning pathway (`JARVIS_PLANNING_PROFILE` → default,
   `admin/server.py:644`), the site-research comparison writer
   (`admin/server.py:428`, same env), and the Edit-panel picker's initial
   selection. So this flip puts the *executor* loop on the most expensive
   profile in the registry until Phase 3 assigns it a Sonnet-class
   profile. That is accepted deliberately — quality-first while the
   ledger measures, exactly the "measure before down-tiering" order this
   plan is built on — with two conditions: (a) the executor rung IS
   measured from day one (the `upgrade_agent.py:469` patch is no longer
   deferred — see Phase 0 task 1), and (b) if `.env` already sets
   `JARVIS_UPGRADE_PROFILE` or `JARVIS_PLANNING_PROFILE`, those win over
   the default and this flip changes nothing for that path — check before
   assuming the flip took effect.
5. **Bind the model floor in config (pulled forward from Phase 3).**
   Policy first, measurement second — a floor is not something the eval
   ladder gets to discover.
   - `config/upgrade_models.yaml`: add the direct `claude-sonnet-5`
     profile (exact YAML in Phase 3) and delete `or-sonnet-5` in the same
     edit (identity-uniqueness test).
   - `config/agents.yaml`: `scheduler`, `librarian`, `analyst`, `systems`
     each gain `model_profile: claude-sonnet-5` and
     `on_profile_fallback: refuse`. `refuse`, not `warn`, deliberately:
     `warn` falls back to the voice model, which is Haiku, which is the
     one outcome the policy forbids — a floor that silently degrades is
     not a floor. Voice still boots on a fresh checkout with one key
     (the Supervisor never goes through this path); only delegations
     refuse, loudly, with the Agents-tab chip red. `developer` already
     sits above the floor (`claude-opus`, `refuse`).
   - Mechanical backstop, `tests/unit/test_model_floor.py`: every
     `sub_agents` entry declares a `model_profile`; the resolved
     profile's `model` string does not match `/haiku/i`; and
     `on_profile_fallback` is `refuse`. The Supervisor
     (`settings.openai_model`) is exempt by construction — it is not in
     `agents.yaml`.
   - Retire the two workflow drafts this replaces
     (`config/workflows/user-preference-model-defaults.yaml`,
     `user-preference-model-selection.yaml`) in the same commit — same
     rule as the units fact: once config binds it, a workflow that only
     persuades is dead weight, and under `MAX_INJECTED = 1` it can
     displace a workflow that still does something.
   - **Interpretation, stated so it can be vetoed in one line:** the
     floor is about AGENTS. The background maintenance rungs
     (`memory_merge`, `memory_classify`, `memory_extraction`,
     `kb_digest`, `procedures_describe`) are not agents — nobody
     delegates to them, they never speak to the user — and stay eligible
     for cheap/local models in Phases 3 and 5. If Larry means the floor
     to cover them too, delete this bullet and the Phase 5 local-model
     item narrows to the Supervisor alone.
   - Cost effect is expected and accepted: four agents move Haiku →
     Sonnet before the baseline is taken, so the baseline measures the
     policy-compliant system, not the one being retired. Patch the
     supervisor + base.py ledger sites first (checklist step 3) so the
     first Sonnet delegations are already recorded.
6. **Ledger on WAL from the first row** (moved here from "future work"):
   `council.py` and `upgrade_agent.py` write from the admin sidecar
   process; every other site writes from the bot process. Two writer
   processes exist from the first council round, so `usage_ledger._conn()`
   sets `journal_mode=WAL` + `busy_timeout` unconditionally and anchors
   `data/costs.db` to the repo root (not CWD — the two processes are
   launched by different scripts). Already in the Rev 3 `usage_ledger.py`.

---

## Phase 0 — Instrumentation & Baseline Evidence

**Goal:** Replace priors with measurements. Every later phase's savings claim gets verified against this baseline.

**Tasks**
1. **Usage-logging shim.** Thin wrapper at the LLM client factory: logs `ts, rung, provider, model, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, reported_cost, session_id` per call to the cost ledger (see Cost Tracking design, separate doc/decision). **Rev 3: 13 call sites, not 11, and a closed rung vocabulary** (`usage_ledger.RUNGS`): the sidecar's own edit-loop completion (`upgrade_agent.py:469` → `selfedit_executor` / `appbuild_executor`, the "double-count" worry was a different-process misread) joins the set, and `council._call_profile` gains a `rung` kwarg so its four callers are labelled truthfully — `council` (escalations), `planning` (draft_candidates + single-mode author), `research` (site comparison). Without this, the entire planner/executor split in Phase 3 would have been invisible in the one report meant to justify it.
2. **OpenRouter activity puller.** Pull per-generation stats for the slice already routed through OpenRouter (model, native token counts, cost, cached_tokens, cache_discount). This settles cache-passthrough behavior for existing routed traffic without waiting on the shim.
3. **Provider console snapshot.** Record current-month Anthropic/OpenAI usage: input:output token ratio, per-model spend. One-time manual pull; establishes the input-dominance number.
4. **Rung frequency mining.** From Mortimer's existing structured logs: calls per session per rung (supervisor turns vs sweep/merge/extraction/council/developer). Denominator for sub-agent share of spend.
5. **Baseline report.** Analyzer joins 1–4: total spend/mo, input vs output share, per-rung share, prefix share of input (system+tools+memory block size vs total), cache hit status on routed calls.

**Assumptions under test**
- A1: input tokens are 70–85% of spend
- A2: majority of each input is repeated prefix
- A3: sub-agents are a meaningful share (~30%) of spend
- A5: prompt caching survives the OpenRouter path (cached_tokens > 0 on routed Claude/Gemini calls)

**Exit criteria:** one week of shim data; baseline report generated; A1/A2/A3/A5 each marked confirmed/refuted with numbers.

**Quick win allowed during Phase 0:** run Graphify on the repo and wire the output into the developer agent's context. Zero integration risk, independent of everything else.

---

## Phase 1 — Prompt Caching

**Goal:** Stop paying full price for the repeated prefix. Projected: largest single lever (prior: 45–65% of total bill; replace with Phase 0 numbers).

**Tasks**
1. Reorder prompt assembly so stable content leads: system prompt / persona / tool + skill definitions first; volatile content (memory context, transcript) last.
2. Insert cache breakpoints after the stable block. Respect per-model minimum cacheable sizes.
3. Sticky sessions on routed calls: pass a stable session id per conversation so repeat calls land on the same provider cache; consider 1-hour TTL for long sessions where the write premium is amortized.
4. Verification gate: assert `cache_read_tokens > 0` (native) / `cached_tokens > 0` (routed) on second-turn calls; alert in logs if a session runs cold — caching failures are silent by default and must not be.
5. Decision from A5: any model whose cache discount does NOT provably pass through OpenRouter moves its calls to the native key. Caching beats gateway convenience at ~10x the stakes.

**Non-goals:** do not slim or reword the stable cached block — it costs ~10% of base once cached; capability risk isn't worth pennies.

## Phase 1b — Effort Control (added 2026-09-01)

**Goal:** Stop paying default-high adaptive-thinking depth on rungs that don't need it. Discovered post-plan: Claude 5-class models think adaptively at effort=high **by default**, thinking tokens bill as output tokens, and none of the eleven call sites sets effort — so every rung, including trivial dispatch (scheduler, systems), may be spending unrequested reasoning depth today.

**Tasks**
1. Add `jarvis/effort.py` (resolve per-rung effort: explicit config → JARVIS_EFFORT_<RUNG> env → JARVIS_EFFORT_DEFAULT → none/provider default).
2. Add `effort:` to agents.yaml per sub-agent and optionally per upgrade_models.yaml profile; env vars for the loose background rungs. Starting defaults: low for scheduler/systems and sweep rungs, medium for supervisor/librarian/analyst/extraction/digest, unset (provider default) for developer and council frontier members.
3. Wire `extra_body_for()` into the same eleven call sites as the cost shim.
4. **Verification gate first:** one test call per provider confirming the extra_body shape is accepted (no 400) and changes behavior — the Anthropic-compat key shape is inferred from the documented thinking pattern, not directly documented for effort. JARVIS_EFFORT_DEFAULT stays unset until this passes.
5. **Cache rule:** effort is static per rung, never varied per call. **Rev 3 wording:** the effort↔cache-invalidation interaction is documented for the native Messages API's thinking parameters; whether it holds for the effort field *through the OpenAI-compatible endpoint this repo uses* is the same class of inference as the key shape in task 4, and gets the same gate — the task-4 session also toggles effort between two otherwise-identical turns and records whether `cache_read_tokens` drops to zero. Static-per-rung is the safe default either way (it cannot hurt the cache); it is promoted from "safe default" to "requirement" only if that check shows an effect. Set once, revisit only at phase boundaries using the baseline report's thinking-token data.

**Exit criteria:** effort set on all non-frontier rungs; no 400s; measured output-token reduction on low/medium rungs vs baseline; cache hit rate unaffected; effort↔cache interaction recorded as observed/not-observed.

**Exit criteria:** cache hit rate >80% on supervisor turns in-session; measured input-cost reduction reported against Phase 0 baseline.

---

## Phase 2 — Memory Write-Path Redesign (Extraction Gate)

**Goal:** Stop treating every utterance as memory. Shrink the candidate pool at the source; make the sweep a janitor, not a load-bearing component.

**Design (agreed):** the unit of memory is the *fact*, not the utterance. No inline gate on the latency path.

**Tasks**
1. **Async post-turn extraction worker.** New service (Procfile entry now, launchd later). Consumes finished exchanges (utterance + Mortimer's response + any user correction); emits zero-to-N structured candidates: `content, tier, entities[], provenance(stated|inferred), source_turn`.
2. Commands flow through the same pass — embedded durables ("Mom's birthday June 3") extract even when the command path already executed. Chitchat/queries yield empty lists; the empty list *is* the classification.
3. **Novelty gate at admission.** Candidate's entities matched against the store before write; duplicates increment a recurrence counter on the existing fact instead of inserting.
4. **Staging + promotion.** Identity/people/projects/policies: admit on first mention. Tastes/passing mentions: staging tier; promote on second occurrence; expire unrepeated after N days.
5. Extractor model: start on a cheap tier (candidate for Phase 3 eval); judged on JSON-schema adherence and precision, not fluency.

**Exit criteria:** preference-tier growth rate flattened; sweep merge rung firing rarely; no observed loss of facts Larry actually stated (spot-check via librarian session).

---

## Phase 3 — Model Routing & Down-Tiering

**Goal:** Cheapest model per rung that clears the quality bar. Provider chosen by feature dependency, not loyalty.

**Developer work gets a specific strategy (decided 2026-09-01, made concrete in Rev 3): planner/executor split — mapped onto the THREE mechanisms that already exist, no new agent.**

Rev 2 said "planner" and "executor" without naming which code they were.
The repo already has three distinct things a model does on developer
work, each with its own model-resolution path, and the split is a
*reassignment of those three*, not a fourth:

| Role | Existing mechanism | Process | Model comes from | Phase 3 assignment |
|---|---|---|---|---|
| **Planner** | planning pathway — `POST /api/plan/start`, `council.draft_candidates`, single-mode `PLAN_AUTHOR_PROMPT`; plus E1 escalation rounds (`placement="planner"`) | sidecar | `JARVIS_PLANNING_PROFILE` → registry `default` | **frontier** (default = `claude-fable-5` after Phase 0b) |
| **Executor** | `UpgradeAgent` / `AppBuildAgent` edit loop (`upgrade_agent.py`, `run()` → propose/validate/submit) | sidecar | `JARVIS_UPGRADE_PROFILE` / `JARVIS_APPBUILD_PROFILE` → registry `default` | **`claude-sonnet-5` direct** (new profile, below) — set via the two env vars, **not** by changing `default` |
| **Dispatcher + small edits** | `developer` SubAgent (`config/agents.yaml`, `model_profile: claude-opus` today) — reads, investigations, dictated single-file `repo_write_file` edits, and *launching* `plan_start`/`selfedit_start`/`app_build_start` | bot | `agents.yaml` `model_profile` | stays `claude-opus` through baseline; eval-ladder candidate for `claude-sonnet-5` — the floor, not below it — like every other agent — it is by construction the "single-file, non-design-bearing" executor, since those edits already happen inside it |

Consequences that fall out of the table:
- **The developer SubAgent is NOT split in two.** Supervisor routing is
  untouched, the routing eval is untouched, and "plan-first vs
  execute-directly" is already the developer prompt's own rule
  (`DEVELOPER_CORE` routes multi-file work to `selfedit_start`, small
  dictated edits to `repo_write_file`). Phase 3 changes which *model*
  sits at each of the three seats, not the seats.
- **Executor selection is env, not `default`.** Setting
  `JARVIS_UPGRADE_PROFILE=claude-sonnet-5` and
  `JARVIS_APPBUILD_PROFILE=claude-sonnet-5` leaves `default` free to keep
  meaning "planning-quality", which is what the planning pathway and the
  research writer fall through to. Changing `default` to Sonnet instead
  would silently down-tier plan authoring too.
- **Planner round-one membership.** Two code changes, both in
  `jarvis/council/`: (1) `draft_candidates` gets a config constant
  `PLANNING_DEFAULT_PROPOSER_TIERS = ["frontier"]` used when the caller
  passes no `members` (today it fans out to *all 13* key-present
  profiles — the voice `plan_start` path never passes `members`, so every
  spoken plan request currently buys 13 drafts; the console picker can
  still widen it explicitly); judges stay "whatever usable profiles are
  not proposing", unchanged. (2) `UpgradeAgent._maybe_escalate` starts
  `placement="planner"` rounds at **tier 2** (`COUNCIL_PLANNER_START_TIER
  = 2` in `council/config.py`; scope rounds stay tier 1). With
  `COUNCIL_MAX_ESCALATIONS = 2` and the "tiers strictly ascending, never
  repeating" invariant, that means a planner-placement escalation happens
  **once** per run; a second failure ends the session as a third failure
  does today. [likely] That is the right trade: a frontier council that
  already failed once is not fixed by reconvening the same frontier
  council, and under the split the thing that failed validation is the
  executor's rendering of a plan — the recovery is a human re-plan, not
  a second identical round. If a month of `retry_validated` data says
  otherwise, it is a one-constant change to allow a tier-2 repeat.
- **Preferred proposers:** `claude-fable-5` + `or-deepseek-v4-pro`
  (both `tier: frontier` in the registry today); third-lineage judge
  drawn by the existing partition (`or-grok-4.6` frontier, or
  `or-gpt-5.1` mid via the V8 backfill). The identity-uniqueness rule
  already prevents self-judging. For self-edits, user choice via
  `draft_candidates → record_user_choice` remains the preferred judge.
- **Executor profile — swap, no backfill needed.** Add to
  `config/upgrade_models.yaml`:
  ```yaml
  - name: claude-sonnet-5
    label: "Claude Sonnet 5 — direct Anthropic; the executor tier"
    provider: anthropic
    model: claude-sonnet-5
    identity: anthropic/claude-sonnet-5
    base_url: https://api.anthropic.com/v1/
    api_key_env: ANTHROPIC_API_KEY
    temperature: null      # D-003; same family that rejects it on opus
    tier: mid
  ```
  and **delete** `or-sonnet-5` in the same edit — same `identity`, so
  `tests/unit/test_model_registry.py` fails if both exist. Rev 2's
  "backfill the lost mid-tier judge slot" is withdrawn: the identity AND
  the tier are preserved (both `mid`), only the route changes, so the
  mid judge pool is exactly as deep after the swap as before. Registry
  rule honoured: a model reachable directly does not keep an OpenRouter
  route.
- **The executor's escalation rule is load-bearing.** The invariant is
  NOT "the spec is complete" — no spec is. It is: all irreversible /
  architectural decisions live in the plan, and when reality diverges
  from the spec the executor **stops and reports, never bridges the
  gap.** That paragraph goes into `UpgradeAgent`'s system prompt
  (`jarvis/prompts.py`, the single source of truth) and is injected
  only when a `plan`/`plan_path` was supplied — an unplanned single-file
  self-edit has nothing to diverge from.
- **Spec requirements** for executability (enforced by
  `PLAN_AUTHOR_PROMPT`, not by the executor): exact files/functions
  with signatures, data shapes at boundaries, mechanical acceptance
  criteria (feeds the existing validation gates), explicit non-goals,
  named divergence triggers.
- **Effort alignment (Phase 1b):** planning rung high/max; executor
  rungs medium/low — the spec already did the thinking; developer
  SubAgent per the eval ladder.
- **Instrument escalation rate from day one.** Chronic escalations mean
  under-specified plans (a planner-prompt problem), which looks
  identical to executor incapability unless measured. Two ground truths,
  both already recorded: `retry_validated` per round (did a high-scoring
  plan actually execute clean) and the ledger's `selfedit_executor` /
  `appbuild_executor` rows per run (how much executor spend a plan
  consumed before it landed or died).

**Tasks (all rungs) — under the model floor.** For the five specialists
and the planner/executor seats the ladder is **frontier → Sonnet-class**
and stops there; the "small open-weight" step below applies only to the
Supervisor (Phase 5 local) and the background maintenance rungs.
1. **Per-rung eval sets.** 20–50 real examples per rung mined from logs: utterance→intent, exchange→extracted facts, fact-pair→merge/don't. 
2. **Capability ladder.** Run frontier → mid-tier → small open-weight per rung (simple harness or promptfoo). Pick cheapest passing model; record next tier up as fallback.
3. **Routing config in `agents.yaml`** (commit the pending changes first): per-rung `model, provider, fallback`. Routing changes become config edits, not code changes.
4. **Provider balance rules:**
   - Needs caching or batch → native key (supervisor; async rungs headed to batch).
   - Cheap open-weight models → OpenRouter credits (fee is noise at that price tier).
   - Frontier calls needing neither → OpenRouter BYOK or native; default OpenRouter for failover, native key stays in vault as escape hatch.
5. Priors to test, not trust: intent/entity-matching solved by 1–8B class (Supervisor-local and background rungs only — never an agent); extraction is mid-tier; developer agent stays frontier for planning, Sonnet for execution; council placed by eval within its tier rules.

**Exit criteria:** every rung has an eval-backed model assignment in agents.yaml, none below the floor for an agent (`test_model_floor.py` green); measured agent spend reduction vs baseline coming from caching/effort/context, not tier; zero quality regressions on eval sets.

---

## Interface Task (parallel track, any time after Phase 0b) — Council Roster on the Agent Card

Decided 2026-09-01. Every council round record already carries proposer
profiles, judge profiles, per-judge scores, abstain reasons, winner, mean,
and token totals (`get_round()` returns all of it) — this is a surfacing
task, not a data task.

- Primary chip stays the WINNER's resolved profile (preserves the
  model-discipline rule: the chip names what actually proceeds).
- Below it, a compact roster: proposers with mean scores (winner
  highlighted), judges listed separately, and abstentions VISIBLE with
  reasons — `kimi-k3 ✗ (judge failed)` four times on last night's card
  would have surfaced the timeout bug at a glance. Silent pool
  degradation is the same failure class the launcher work fixed for
  services.
- Round token totals on the card — council card and cost card converge
  on the same numbers.
- Implementation shape: small endpoint over list_rounds/get_round (or
  the existing admin API if rounds are exposed there) + one SwiftUI
  view. Well-bounded, visual, low-risk — a good first task for the
  planner/executor loop itself once Phase 0b + the cost shim land.

## Phase 4 — Context Slimming via Graph Memory

**Goal:** Replace the flat char-budget memory dump (currently 8K chars every turn, full price) with retrieval of only the relevant subgraph. Fixes the near-duplicate blindness structurally.

**Design (Graphify pattern, not the package):** entity-anchored store — facts attach to entity nodes with typed edges and provenance tags (stated/inferred). Token-overlap near-dupes ("dark roast" / "dark coffee") become structurally visible as same-node attachments.

**Tasks**
1. Migrate memory store to entities + edges + provenance (NetworkX + existing vault-backed storage; refactor of memory.py, no new dependency service).
2. Context builder v2: traverse from entities in the current utterance (+ always-on core: identity, standing policies) instead of top-N-by-tier truncation. Hard token budget retained as a ceiling, not the selection mechanism.
3. Phase 2's novelty gate re-pointed at the graph (entity match becomes a node lookup).
4. Keep the volatile memory block **after** the cache breakpoint (it varies per turn by design).

**Exit criteria:** average memory-context tokens per turn reduced ≥50% vs the 8K-char dump with no observed recall failures over a week of use.

**Dependency note:** benefits from Phase 2 being done (clean candidates in, clean graph out), but can start once the extraction worker's entity field is stable.

---

## Phase 5 — Batch, Mac mini, Local Endgame

**Goal:** Squeeze the async tail and align with the hosting migration.

**Tasks**
1. Move latency-insensitive rungs (memory sweep, consolidation, staging promotion review) to native Batch APIs — flat ~50% off those calls. (Not available via OpenRouter; these rungs sit on native keys per Phase 3 rules.)
2. Services → launchd agents on the Mac mini; vault injection verified under launchd (shell-rc env vars do not survive — all keys in vault per standing policy).
3. Local model serving for the rungs the Phase 3 eval showed are small-model-solvable — the Supervisor (intent/dispatch; Larry's stated near-term goal) and background rungs (entity match, possibly extraction). Bill for those → $0. An AGENT moves local only if a local model is demonstrably Sonnet-equivalent on that agent's eval set (plausible for large open-weight models on the Mac mini; not assumed) — the floor applies to local models exactly as to hosted ones.
4. Re-run the Phase 0 analyzer monthly; costs regress silently otherwise.

**Exit criteria:** async rungs on batch or local; monthly cost report trending; total reduction vs Phase 0 baseline reported.

---

## Risks & Watch Items

- **Silent cache failure** (Phase 1): the most expensive quiet bug available. Mitigated by the verification gate; never assume from config.
- **Extraction over-admission** (Phase 2): a sloppy extractor recreates the bloat one layer down. Precision-weighted eval; staging tier absorbs mistakes.
- **Eval set too small/stale** (Phase 3): 20 examples can flatter a small model. Refresh sets from live logs before any tier demotion of a user-facing rung.
- **Graph migration data loss** (Phase 4): migrate additively — old store read-only until the graph passes a week of parallel operation.
- **agents.yaml + pipeline.py uncommitted changes**: commit or revert before Phase 3 touches routing config. Unreviewed diffs under a refactor is how regressions hide.

## Savings Ledger (fill from measurements)

| Lever | Prior (unvalidated) | Measured baseline share | Measured after | 
|---|---|---|---|
| Caching stable prefix | 45–65% of total | — | — |
| Volatile-context slimming | 10–15% of total | — | — |
| Right-sizing agents WITHIN the Sonnet+ band (was "down-tiering") | lower than Rev 2's ~25%; the floor removes the Haiku option and Phase 0b raises four agents first | — | — |
| Batch async rungs | 50% of those calls | — | — |
| Stacked | 75–90% total | — | — |

---

## Rev 3 resolutions (2026-09-01) — what changed from Rev 2 and why

Each item was a conflict either between two parts of Rev 2 or between
Rev 2 and the repo as it actually is (every claim below was grep-verified
against the working tree on Larry's machine).

1. **Two writer processes, not one.** `council.py` (and `upgrade_agent.py`)
   are imported and run by `jarvis/admin/server.py` — the sidecar — while
   the other sites live in the bot. README said "enable WAL if a future
   concurrent writer needs it"; the second writer arrives with the first
   council round. **Resolved:** `usage_ledger._conn()` sets WAL +
   `busy_timeout` unconditionally and anchors the DB path to the repo
   root (two launch scripts, two CWDs). `costs_api.py` reads with a
   timeout for the same reason.
2. **Planner/executor named two systems as if they were one.** Rev 2's
   Phase 3 never said whether "executor" meant the `developer` SubAgent
   (bot, `agents.yaml`) or the `UpgradeAgent` loop (sidecar,
   `upgrade_models.yaml`). **Resolved:** the three-seat table above.
   Planner = planning pathway (`JARVIS_PLANNING_PROFILE` → `default`),
   executor = `UpgradeAgent`/`AppBuildAgent` (`JARVIS_UPGRADE_PROFILE` /
   `JARVIS_APPBUILD_PROFILE`, set explicitly — never via `default`),
   `developer` SubAgent = dispatcher, unsplit, eval-laddered like any rung.
3. **Phase 0b's `default` flip and Phase 3's executor tier pulled in
   opposite directions.** Flipping `default` to Fable puts the executor
   loop on the priciest profile until Phase 3. **Resolved:** accepted as
   the measured interim (quality-first while the ledger fills), made
   honest by (a) patching `upgrade_agent.py:469` now — the "double-count
   with base.py" rationale for deferring it was a different-process
   misread — and (b) stating the flip's full blast radius (edit loop,
   planning, research writer, picker default).
4. **`_call_profile` labelled four workflows "council".** Escalation
   rounds, planning drafts, the single-mode plan author and the research
   comparison writer all route through it. **Resolved:** `rung` kwarg,
   default `"council"`, threaded by the three non-council callers.
   Without it, A3 and the whole Phase 3 justification would have been
   computed from mislabelled rows.
5. **A3's operational definition didn't match its statement.**
   `cost_report.py` computed "sub-agent share" as everything-but-
   supervisor, folding memory sweeps, kb digests, planning and council
   into "sub-agents". **Resolved:** closed rung vocabulary
   (`usage_ledger.RUNGS`) + `cost_report.BUCKETS`; A3 is the five
   specialists, and a separate `A3_non_supervisor_share` keeps the
   broader number visible.
6. **Effort↔cache invalidation asserted as documented while the effort
   key itself was marked inferred.** **Resolved:** same gate, same
   session — toggle effort across two identical turns and record whether
   `cache_read_tokens` collapses. Static-per-rung stays the default
   because it is safe, not because it is proven required.
7. **"Backfill the lost mid-tier judge" after the Sonnet swap.** The swap
   preserves identity and tier; the mid pool depth is unchanged.
   **Withdrawn.**
8. **Planner round-one frontier membership had no mechanism.** Rev 2 said
   "draw the frontier pool from round one" with nothing to implement it.
   **Resolved:** `PLANNING_DEFAULT_PROPOSER_TIERS = ["frontier"]` for
   `draft_candidates` when no `members` are passed (also stops every
   spoken plan request buying 13 drafts), and `COUNCIL_PLANNER_START_TIER
   = 2` for `placement="planner"` escalations — one escalation per run
   under the never-repeat invariant, flagged [likely] and revisitable on
   `retry_validated` evidence.

9. **Model floor (Larry, 2026-09-01, Rev 3.1).** The extracted workflow
   draft `user-preference-model-defaults.yaml` surfaced a standing rule
   the plan contradicted: only the voice agent may run Haiku; every other
   agent is Sonnet-or-better. **Resolved:** bound in config + a test in
   Phase 0b item 5 (four agents → `claude-sonnet-5` direct with `refuse`),
   the Sonnet profile pulled forward from Phase 3, the Phase 3 ladder
   floored at Sonnet for agents, Phase 5 local serving scoped to the
   Supervisor and background rungs, the two model-preference workflow
   drafts retired, and the savings-ledger prior for "down-tiering"
   reduced accordingly. One interpretation flagged for veto: background
   maintenance rungs are not agents and stay below the floor.

Not changed, deliberately: the Phase order, the exit criteria, the
Interface Task, Phases 2/4/5. Nothing there conflicted with the repo.
