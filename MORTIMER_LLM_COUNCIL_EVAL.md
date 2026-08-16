# LLM Council — evaluation and proposed shape for Mortimer

**Status: SUPERSEDED by `MORTIMER_LLM_COUNCIL_PLAN.md` (2026-08-14).**
This document is retained as the evaluation record — the source-repo
analysis (§1–§3) and the log of options considered and rejected (§5's
threshold discussion). **Implement from the plan, not from this file.**
Where the two differ, the plan wins: it adds cost tiers, numeric scoring,
council logging, and UI-configurable membership, all of which postdate this
evaluation.

**Source reviewed:** `github.com/karpathy/llm-council` @ master (5 commits) —
`backend/council.py`, `backend/config.py`, `README.md`.

---

## §1 What the source repo actually does

Three stages, all over OpenRouter:

1. **First opinions** — the user query goes to N models in parallel
   (`query_models_parallel`), responses collected. Models that error are
   dropped silently (`if response is not None`).
2. **Review** — every model sees all responses, relabeled `Response A`,
   `Response B`, … so identities are hidden, and is asked to rank them.
   Rankings are parsed out of free text with a regex on a `FINAL RANKING:`
   marker; average rank across judges is the aggregate score.
3. **Chairman** — one designated model receives all Stage 1 responses plus
   all Stage 2 rankings and writes the single final answer.

It is explicitly a weekend hack: "99% vibe coded", "I'm not going to support
it in any way", no tests, storage is JSON files on disk.

## §2 The three ideas worth taking

Separable from the implementation, and all three are sound:

- **Anonymized peer review.** Hiding model identity before ranking so judges
  can't play favorites. Cheap, and it is the single most defensible piece of
  the design.
- **Parallel fan-out over a model registry.** Mortimer already has the
  registry half of this: `config/upgrade_models.yaml` carries four profiles
  (`kimi-k3`, `kimi-k2`, `claude-opus`, `gpt-4.1-mini`), and today exactly
  one is selected per session. Fanning out is a loop over config that already
  exists.
- **Making disagreement legible.** The side-by-side tab view is the real
  product insight — seeing *that* four models disagreed, and where, is more
  useful than any single synthesized answer.

## §3 What must NOT be copied, and why

**The Chairman must never synthesize code.** This is the load-bearing
objection and it is specific to Mortimer, not a criticism of the source repo
(where the output is prose and synthesis is perfectly reasonable).

Mortimer's Upgrade Agent does not emit prose. It emits `edit_propose` calls
carrying complete file contents, which then pass a real validation gate
(allowlist check → backend import → frontend build). If four models each
propose a different `SideDrawer.tsx` and a Chairman merges "the council's
collective wisdom" into one file, the result is a file that **no model wrote
and no validation run ever saw**. That is an authorship gap: output that
reads as authoritative while nothing grounds it.

That is the same failure class `MORTIMER_AGENT_TRUST_PLAN.md` Part A was
built to remove — §1.1's fabricated file contents, §1.2's `ok=1` sitting
next to a body that said `error`. Reintroducing it one layer up, in the
subsystem that edits Mortimer's own source, would undo that work in the
place where it matters most.

**Corollary rule for any council design here:** *a council may rank, review,
and advise; it may never author a merged artifact.* Every diff that reaches
the validation gate must be traceable to exactly one model that wrote it
whole.

**Secondary concern:** the ranking parser is a regex over `FINAL RANKING:`.
A model that formats its ranking slightly differently silently contributes
nothing to the aggregate — and `calculate_aggregate_rankings` cannot tell
"judge abstained" from "judge was dropped by the parser." Same shape as the
D1 problem: a silent parse failure masquerading as a clean result. Any port
needs an explicit unparseable-ranking outcome, counted and surfaced.

---

## §4 Proposed shape (selected 2026-08-14)

Two placements, both workflows (self-edit **and** app scaffolding), convened
by escalation-on-failure plus manual override (§5). No predictive gating.

### Placement A — Council-as-Planner

Before any code is written, the *goal* fans out to N profiles asking for a
competing **implementation plan** (not a diff). Plans are anonymized and
peer-ranked. The winning plan becomes the brief handed to the single existing
Upgrade Agent, which does all editing through the unchanged
`edit_propose` → `session_validate` → `session_submit` path.

Prose synthesis is safe here precisely because the artifact is a plan.
Nothing the council produces is executed or written to disk.

Fit: plan quality is what determines whether a weaker implementer succeeds —
which is the standing rule this project already operates under.

### Placement B — Council-as-Reviewer

One agent writes the diff exactly as today. **After** `session_validate`
passes and **before** the PR is opened, the diff goes to N profiles for
anonymous review and ranking against a fixed rubric:

- correctness against the stated goal
- allowlist compliance (does it touch only what it claimed)
- scope creep (changes not explained by the rationale)
- whether the diff matches its own stated rationale

Reviews surface in the console's Edit panel before human approval. The
council advises; it never edits. `session_submit` remains gated on
validation, and merging remains human-only on GitHub.

### Explicitly deferred — Placement C (Council-as-Competitor)

N profiles each produce a complete, independently validated diff on its own
sandbox branch; the human picks one *whole* diff, never a merge. This is the
only variant where multi-model improves the code rather than the surrounding
judgment, and it respects the §3 authorship rule. Deferred on cost (N×
tokens **and** N× full validation runs, each including a frontend build) until
A and B have shown they pay for themselves.

### Not needed: OpenRouter

The source repo uses OpenRouter to reach many vendors through one API.
Mortimer's `upgrade_models.yaml` profiles are already OpenAI-compatible
endpoints with per-profile `base_url` and `api_key_env`. The council is a
fan-out loop over config that exists — no new vendor, no new dependency, no
new key. (Adding OpenRouter as an *additional* profile later remains an
option; it just isn't a prerequisite.)

---

## §5 When the council convenes

**Threshold gating was considered and rejected** (2026-08-14). At review time
a numeric rule over the diff is computable, but at planner time the file list
does not exist yet — only the goal string — so any planner-side threshold is
keyword-matching over prose dressed up as a rule. Adding a scoping pre-flight
to predict the file set would make the gate depend on a prediction that can
be silently wrong. Both placements are instead gated on **events that have
already happened**, which need no prediction at all.

Two convening paths, and nothing else fires the council.

### §5.1 Escalation — the automatic path

The council convenes only after a run has demonstrably failed. Every trigger
is a recorded fact, not an inference:

| # | Trigger | Where it already exists |
|---|---|---|
| E1 | validation failed, and the single allowed repair attempt also failed | `upgrade_agent.py` — the `repairs_used > 1` early return (currently "stop and report") |
| E2 | the agent declined the goal as off-allowlist | needs a new explicit signal — see §5.2 |
| E3 | the human rejected the diff in the Edit panel | new UI action; an explicit click, so unambiguous |

E1 is the cleanest hook in the codebase: `UpgradeAgent.run()` already detects
double-validation-failure and returns
`{"ok": False, "summary": "validation failed twice; session ended without
submitting…"}`. Escalation replaces that dead end with a council round —
the session is already lost at that point, so there is nothing to regress.

**What the council receives (selected):** the original goal, the failing
diff, and the validation `checks` output. Each member proposes a corrected
approach; members rank each other's proposals anonymously; the winner becomes
the brief for **one** retry by the normal single-agent path.

This preserves the §3 authorship rule exactly: the council produces a
*brief*, never a diff. The retry runs through the unchanged
`edit_propose` → `session_validate` → `session_submit` gate, authored whole by
one model.

**Hard bound — one escalation per session, full stop.** Council → retry →
fail → council → … is an obvious runaway. If the post-council retry also
fails, the session ends and reports, exactly as it does today. This is a
counter on the session, not a judgment call.

### §5.2 E2 needs a code change, and it is worth making

Detecting "the agent declined" from its prose summary would be the same
keyword-matching mistake the threshold rule was rejected for. The agent's
decline currently exits as a normal no-tool-call reply (`ok=True`) whose
*text* explains the refusal — indistinguishable, structurally, from success.

**Fix:** add a fifth tool, `session_decline(reason)`, to `TOOL_SPECS`, and
instruct the agent (rule 2 of `SYSTEM_PROMPT` already tells it to decline
off-allowlist goals) to call it rather than merely saying so. A decline
becomes a recorded event with a reason string, and E2 becomes as
deterministic as E1.

This is the same principle as `jarvis/toolresult.py`: do not infer from prose
what can be recorded as a fact. It is a small change, and it improves the
run log independently of the council — declines currently look like
successes in `agent_runs`.

### §5.3 Manual convene — the override

Council on request, at either placement, with no automatic trigger:

- **Before planning** — "convene the council on this" by voice, or an Edit
  panel control, fans the goal out for competing plans (Placement A).
- **On a finished diff** — a "get second opinions" control runs Placement B's
  anonymous review against the rubric before you approve the PR.

Escalation covers "this turned out to be hard"; manual covers "I suspect this
is hard." Neither guesses.

### §5.4 What is deliberately not covered

A plausible-but-subtly-wrong plan that validates cleanly and that you approve
will never trigger the council. Escalation is reactive by construction, and
that is the accepted trade for removing prediction. Manual convene is the
mitigation, and it depends on your judgment, not the system's. Placement A
always-on (previously "Option 3") remains the answer if that gap turns out to
matter — revisit once escalation runs have shown whether council plans
actually beat single-model plans.

---

## §6 Cost

Escalation makes the cost profile self-limiting in a way the threshold design
never could: **a run that succeeds costs exactly what it costs today.** Zero
council overhead on the happy path, because the council only exists after a
failure that has already occurred.

Per escalated session, with N=3 council members:

- N proposals against the failure context + N anonymous rankings ≈ 6 extra
  calls, plus one normal retry run.
- Bounded at exactly one escalation per session (§5.1), so the worst case per
  session is fixed rather than open-ended.

Manual convene costs the same per invocation, but only when you ask.

None of this sits in the voice latency path — the self-edit loop already runs
async in the background via the admin sidecar's `/api/selfedit/run` plus
polling, so the per-turn latency budget that governs the bot pipeline does
not apply.

---

## §7 Open questions before an implementation plan

0. **App scaffolding needs its own escalation triggers.** E1–E3 (§5.1) are
   defined against the self-edit loop's validation gate. `mcp_apps` app
   creation has no equivalent gate, so "what counts as a failed scaffold" is
   undefined — likely candidates are a failed `app_create` (now surfaced
   honestly by D8's 401/403 work) or a human rejection. This is the largest
   remaining gap in the design and should be settled before planning.

1. **Council size and membership.** All four registry profiles, or a subset?
   Should the council be *required* to span vendors (Moonshot + Anthropic +
   OpenAI) so a single provider outage or single-family bias can't dominate?
2. **Judge eligibility.** May a model rank its own (anonymized) output?
   Karpathy's version allows it. Excluding self-votes is a one-line change
   and removes a bias vector — but shrinks the judge pool.
3. **Tie-breaking.** Average rank can tie. Needs a deterministic tiebreak
   (registry order? cheapest profile? highest-ranked judge's preference?).
4. **Where reviews surface.** The console's Edit panel is the obvious home;
   the side drawer's Output tab is the other candidate given it already
   handles work-product display.
5. **Kill switch.** Assume `JARVIS_COUNCIL_ENABLED=false`, matching the
   existing `JARVIS_PROCEDURES_ENABLED` / `JARVIS_RUNLOG_ENABLED` convention.
6. **Run-log integration.** Council rounds are delegations in all but name.
   Reusing `agent_runs`/`agent_events` would make them reviewable via
   `python -m jarvis.runlog` for free, rather than inventing a second
   storage shape.
