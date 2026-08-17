# MORTIMER LLM COUNCIL — implementation plan

**Supersedes** `MORTIMER_LLM_COUNCIL_EVAL.md` (retained as the evaluation
record and rejected-options log; this document is what gets implemented).

**V2 plan (`MORTIMER_LLM_COUNCIL_V2_PLAN.md`) supersedes D6.1's
judge-assembly clause and completes D2's E2 row and D4's carry-forward.**
See that document for V1–V14; it is implemented in full (§5 steps 1–15).

**Implementation status (2026-08-16): implemented, §5 steps 1–13 complete,
all required tests green.** One design gap was found and resolved with
Larry during implementation — see "r3 → r4" below. §9's "to record on
completion" line (the full `--agreement` output once ≥20 shadowed rounds
exist) is still open; that requires real usage data and cannot be recorded
at implementation time.

## Revision history

**r1 → r2 (2026-08-14), self-audit before handoff.** Five gaps found and
closed. Each was a place the implementer would have had to decide something:

| # | Gap | Closed by |
|---|---|---|
| 1 | Module API named but not typed — `Proposal`/`Score`/`RoundResult` and three function signatures read by 3+ callers | **D1.1** — full dataclasses and signatures |
| 2 | Proposer and judge prompts described but not written — the highest-leverage text in the feature | **D6.1** — both prompts verbatim, plus the message-assembly rule |
| 3 | Escalation hook described in prose ("replace that dead end") with no code, in the one place a mistake breaks the existing agent loop | **D2.1** — literal replacement code, the `_maybe_escalate` helper, and the `asyncio.run` safety note |
| 4 | Tier↔escalation mapping stated in two sections, free to drift | **D4** — `tier = escalations_used + 1` computed in exactly one place; `tier_members()` raises on an undefined tier |
| 5 | Scoring tests listed the happy path and obvious failures, but not parser edge cases (unknown labels, duplicates, bare integers) or any escalation-path test | **§6** — two expanded test tables |

**r2 → r3 (2026-08-14), judge-tier validation added.** D5's `[guessing]`
claim (mid-tier judges can score code) was instrumented only passively, by
`retry_validated`. That is confounded: at tier 1 only mid-tier judges ever
score, so a bad pick is indistinguishable from a pick a better judge would
also have made.

| # | Change | Where |
|---|---|---|
| 6 | Shadow judging — score the same proposals with another tier, advisory only, deterministically sampled | **D8.2.1**, `shadow` + `judge_tier` columns in D8 |
| 7 | Offline replay CLI — re-score stored rounds retroactively, read-only | **D8.2.2**, `jarvis/council/__main__.py` |
| 8 | Winner agreement (not score agreement) as the primary metric, plus abstention rate and discrimination | **D8.2.3**, `jarvis/council/agreement.py` |
| 9 | Promotion thresholds fixed **before** data exists, with an explicit insufficient-data branch | **D8.2.4** |

**r3 → r4 (2026-08-16), found during implementation, resolved with
Larry.** D4's original tier-2 row had judges = `mid`, but tier-2 proposers
= `frontier` + `mid` — the `mid` tier appeared in both pools, contradicting
D5's disjoint-proposer/judge invariant (with today's single `mid` profile,
tier 2 would have had zero usable judges whenever it proposed).

| # | Change | Where |
|---|---|---|
| 10 | Tier 2 judges = `frontier`, not `mid` | **D4**'s `TIER_MEMBERS` table, `jarvis/council/config.py` |
| 11 | Disjointness enforced per-member (not just per tier name) via a new `exclude` parameter, with the existing degenerate-tier fallback reused for names emptied by exclusion, not just by a missing key | **D4** (`config.py`'s `resolve_members`/`_usable_profiles_for_tier_name`) |

---

## §0 Binding constraints

### §0.0 This plan assumes nothing about how capable you are

Every decision in this document has already been made. Your job is to
implement it exactly as written, not to improve on it.

**If you find yourself deciding something this document did not decide, that
is a defect in the document — stop and report it rather than choosing.**
Specifically: do not invent a scoring formula, do not pick a tie-break rule,
do not choose which models go in which tier, and do not decide what counts as
a failure. All four are specified below. If a section seems to require
judgement, it is under-specified and you should say so.

### §0.1 Non-negotiable invariants

These come from `MORTIMER_AGENT_TRUST_PLAN.md` and the self-edit plan. A
change that violates any of them is wrong even if tests pass.

1. **A council may rank, review, and advise. It may NEVER author a merged
   artifact.** Every diff reaching `session_validate` must be traceable to
   exactly one model that wrote it whole. There is no Chairman that merges
   code. (Eval §3 — this is the whole reason the source repo's Stage 3 is not
   being ported.)
2. **No predictive gating.** The council convenes on events that have already
   happened, never on an estimate of how hard something will be. Threshold
   gating was considered and rejected (Eval §5).
3. **`config/upgrade_models.yaml` stays off the self-edit allowlist.** The
   agent must not be able to re-point its own brain, directly or through a
   UI that writes to that file (D9 below).
4. **Never infer from prose what can be recorded as a fact.** Same principle
   as `jarvis/toolresult.py`. Applies to declines (D3) and to score parsing
   (D6).
5. **A failed council must never be silently smaller.** A member that errors,
   times out, or returns an unparseable score is recorded as an explicit
   abstention, never dropped. (This is the source repo's
   `if response is not None` bug — Eval §3.)
6. **Nothing here runs in the voice latency path.** The self-edit loop is
   already async via the admin sidecar. Council work happens there.

---

## §1 Verified background

Read these before implementing. Line references verified 2026-08-14.

| Fact | Where |
|---|---|
| Upgrade Agent loop, tool dispatch, `repairs_used` counter | `jarvis/agents/upgrade_agent.py` — `run()` at line 259, `_dispatch()` at 344 |
| The exact escalation hook: double-validation-failure early return | `jarvis/agents/upgrade_agent.py` lines 316–334 |
| Closed toolset (4 tools) | `jarvis/agents/upgrade_agent.py` `TOOL_SPECS` line 83 |
| Planner registry: load / resolve / list | `jarvis/agents/upgrade_agent.py` lines 154–201 |
| Four profiles today | `config/upgrade_models.yaml` — `kimi-k3`, `kimi-k2`, `claude-opus`, `gpt-4.1-mini` |
| Self-edit service, session state, validation gate | `jarvis/selfedit/service.py` |
| Allowlist deny list includes `config/upgrade_models.yaml` | `config/self_edit_allowlist.json` line 20 |
| Admin sidecar owns the self-edit service; `/api/selfedit/*` | `jarvis/admin/server.py` |
| Run-log schema, `RunLogger`, `agent_runs` / `agent_events` | `jarvis/runlog/store.py`, `jarvis/db.py` `MIGRATION_0006` |
| Latest migration is `0008_tool_outcomes` | `jarvis/db.py` `MIGRATIONS` |
| Run-log CLI table renderer | `jarvis/runlog/cli.py` `_print_table` |
| Edit panel — the only UI surface for self-edit | `web/src/components/EditModePanel.tsx` |
| Drawer localStorage convention (`mortimer.drawer.*`) | `web/src/components/SideDrawer.tsx` |

**Terminology.** A **round** is one full council invocation (propose →
score → select). A **member** is one profile participating in a round. A
**proposal** is one member's output. **Proposer** and **judge** are roles a
member holds within a round; they are disjoint (D5).

---

## §2 Scope

**In scope:** a `jarvis/council/` module; escalation and manual convening for
the self-edit loop; numeric scoring with a deterministic winner; cost tiers;
council logging; UI membership selection and review display.

**Out of scope, explicitly:**
- Placement C (Council-as-Competitor) — deferred, Eval §4.
- App-scaffolding escalation triggers — undefined, see D14. The council
  module is built workflow-agnostic so this can be added without redesign,
  but no `mcp_apps` wiring ships in this plan.
- OpenRouter. Not needed; profiles are already OpenAI-compatible.
- Any change to `session_submit`'s validation gate or to human-merges-on-
  GitHub.

---

## §3 Decisions

### D1 — The council module is transport-free and workflow-agnostic

New package `jarvis/council/`:

| File | Contents |
|---|---|
| `types.py` | `Proposal`, `Score`, `RoundResult` dataclasses |
| `scoring.py` | pure functions: parse, aggregate, select winner |
| `council.py` | orchestration: fan-out, anonymize, score, select |
| `config.py` | tier ladder + membership resolution |

`scoring.py` must import nothing from `openai`, `jarvis.selfedit`, or
`jarvis.agents`. It is pure data-in/data-out so the entire selection path is
unit-testable without network. This mirrors the `logic.py` / `server.py`
split used across `mcp_servers/*`.

*Rationale:* the selection rule is the part most likely to be subtly wrong,
and the part where a bug is least visible. It must be testable in isolation.

**D1.1 — Public API, specified member by member.** These signatures are read
by more than one caller (the escalation hook, the manual-convene endpoint,
and the tests) and are therefore fixed here, not left to the implementer.

```python
# jarvis/council/types.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Proposal:
    label: str            # "Proposal A" — assigned by council.py, never by a model
    profile: str          # registry profile name, e.g. "kimi-k2"
    content: str          # the proposed approach, prose only, never file contents

@dataclass(frozen=True)
class Score:
    judge_profile: str
    proposal_label: str
    value: float | None   # None == abstained
    justification: str = ""
    abstain_reason: str | None = None   # non-None iff value is None

@dataclass(frozen=True)
class RoundResult:
    round_id: str
    winner: Proposal | None      # None iff the round failed
    winner_mean: float | None
    select_reason: str           # which D7 branch decided it, or why it failed
    proposals: list[Proposal] = field(default_factory=list)
    scores: list[Score] = field(default_factory=list)
    abstentions: int = 0
    tier: int = 1
```

```python
# jarvis/council/scoring.py  — pure, no I/O, no network
def parse_scores(judge_profile: str, raw: str,
                 labels: list[str]) -> list[Score]:
    """Parse one judge's raw output into exactly one Score per label in
    `labels`. A label the judge did not score, or scored invalidly, yields
    a Score with value=None and a populated abstain_reason. Never returns
    fewer than len(labels) items, and never raises."""

def select_winner(proposals: list[Proposal],
                  scores: list[Score],
                  registry_order: list[str]) -> tuple[Proposal | None, str]:
    """Apply D7's four rules in order. Returns (winner, reason). Returns
    (None, reason) iff no proposal has at least one valid score.
    `registry_order` is profile names in config order — rule 4's tiebreak.
    Deterministic: identical inputs always yield an identical winner."""

def mean_of(label: str, scores: list[Score]) -> float | None:
    """Mean of valid scores for `label`; None if it has none."""
```

```python
# jarvis/council/council.py
async def convene(*, workflow: str, placement: str, trigger: str,
                  goal: str, tier: int, context: dict,
                  run_id: str | None = None) -> RoundResult | None:
    """Run one council round. Returns None on ANY failure (D13) — callers
    treat None as 'proceed with the ordinary failure path'. Never raises.
    `context` carries placement-specific input (for E1: keys 'diff' and
    'checks'). Writes the D8 rows and JSONL itself."""
```

### D2 — Escalation triggers (the automatic path)

The council convenes only after a run has demonstrably failed:

| # | Trigger | Detection |
|---|---|---|
| E1 | validation failed AND the single repair attempt also failed | `upgrade_agent.py` line 318 `repairs_used > 1` branch |
| E2 | the agent declined the goal as off-allowlist | the new `session_decline` tool (D3) |
| E3 | the human rejected the diff | new Edit-panel action posting to a new endpoint (D10) |

At E1 the session is already lost — the current code returns
`{"ok": False, "summary": "validation failed twice…"}` and stops. Escalation
replaces that dead end. There is nothing to regress.

**Council input at escalation:** the original goal, the failing diff
(`service.proposals`), and the validation `checks` output. Each proposer
returns a *corrected approach in prose* — never file contents. The winning
approach becomes the brief for **one** retry through the normal single-agent
path.

**D2.1 — The E1 hook, as literal code.** `UpgradeAgent.run()` currently
returns at line ~333 when `repairs_used > 1`. Replace that early return's
body with the following. Everything else in `run()` is unchanged.

```python
# was: return {"ok": False, "summary": summary, "status": ...}
council_brief = self._maybe_escalate(
    goal=goal, trigger="E1",
    context={"diff": self.service.proposals,
             "checks": result.get("checks")},
)
if council_brief is None:
    self._emit(on_event, {"type": "agent_done", "ok": False})
    return {"ok": False, "summary": summary,
            "status": self.service.status()}
# Retry once with the council's winning approach as added context.
messages.append({
    "role": "system",
    "content": (
        "A council of models reviewed this failure. Their "
        "highest-scored corrected approach follows. Follow it, then "
        "validate again.\n\n" + council_brief
    ),
})
repairs_used = 0          # the retry gets its own repair budget
continue                  # resume the outer `for` loop
```

And the helper, on `UpgradeAgent`:

```python
def _maybe_escalate(self, *, goal: str, trigger: str,
                    context: dict) -> str | None:
    """Returns the winning proposal's content, or None to fall through
    to the ordinary failure path. Never raises (D13)."""
    if self._escalations_used >= COUNCIL_MAX_ESCALATIONS:
        return None
    tier = self._escalations_used + 1          # 1st -> tier 1, 2nd -> tier 2
    self._escalations_used += 1
    try:
        from jarvis.council.council import convene
        result = asyncio.run(convene(
            workflow="selfedit", placement="planner", trigger=trigger,
            goal=goal, tier=tier, context=context,
        ))
    except Exception:                           # noqa: BLE001
        logger.warning("council_escalation_failed", exc_info=True)
        return None
    if result is None or result.winner is None:
        return None
    return result.winner.content
```

Initialise `self._escalations_used = 0` in `__init__`, and reset it to `0`
at the top of `run()` so a reused agent instance starts clean.

**Note on `asyncio.run`:** `UpgradeAgent.run()` is synchronous and is already
called from a background thread by the admin sidecar (`_run_agent` in
`jarvis/admin/server.py`), so there is no running event loop on that thread
and `asyncio.run` is safe. Do not convert `UpgradeAgent.run()` to async —
that would change its contract with the sidecar.

### D3 — `session_decline(reason)` becomes a real tool

Add a fifth entry to `TOOL_SPECS`:

```python
{
    "type": "function",
    "function": {
        "name": "session_decline",
        "description": "Decline the goal because it requires changes "
                       "outside the self-edit allowlist. Provide the "
                       "reason. Use this INSTEAD of replying in prose "
                       "that you cannot do it.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
},
```

Dispatch in `_dispatch`:

```python
if name == "session_decline":
    return {"ok": False, "declined": True,
            "reason": str(args.get("reason", ""))}
```

In `run()`, a `declined` result ends the session immediately with
`{"ok": False, "declined": True, "summary": reason, ...}`.

Append to `SYSTEM_PROMPT` rule 2: *"When you decline, you MUST call
`session_decline` with the reason. Do not decline in prose alone."*

*Rationale:* a decline currently exits as `ok=True` with prose explaining the
refusal — structurally identical to success, so `agent_runs` records it as a
success. Detecting it by reading text would be the keyword-matching mistake
invariant §0.1.4 forbids. This is independently worth doing for run-log
honesty.

### D4 — Tier ladder: cost rises only after demonstrated difficulty

Add `tier` to each profile in `config/upgrade_models.yaml`
(`economy` | `mid` | `frontier`):

| Profile | tier |
|---|---|
| `gpt-4.1-mini` | `economy` |
| `kimi-k2` | `economy` |
| `kimi-k3` | `mid` |
| `claude-opus` | `frontier` |

The ladder (tier-2 judges corrected 2026-08-16 — r3→r4 above):

| Tier | When | Proposers | Judges |
|---|---|---|---|
| 0 | normal run | single model (unchanged default) | — |
| 1 | first escalation | all `economy` profiles | all `mid` profiles |
| 2 | tier-1 retry also failed | all `frontier` + all `mid` | all `frontier` |

Judges = `frontier` (not `mid` as originally drafted) because `mid`
appears in tier 2's proposer pool too, and D5 requires proposers and
judges be disjoint within a round. Disjointness is enforced per-member
(`resolve_members`'s `exclude` parameter, `jarvis/council/config.py`), so
this holds even if a tier name is later expanded to overlap again.

At tier 2 the tier-1 **winning proposal is carried forward** as an additional
candidate. It costs nothing (already generated) and occasionally the cheap
proposal was right and the retry failed for an unrelated reason.

**Hard bound:** at most **two** escalations per session, tiers strictly
ascending, never repeating a tier. If the tier-2 retry fails, the session
ends and reports exactly as today. This is a counter on the session, not a
judgement.

**Single source of truth for the mapping.** `tier = escalations_used + 1`,
computed in exactly one place — `_maybe_escalate` (D2.1). No other code
derives a tier. `COUNCIL_MAX_ESCALATIONS = 2` (D12) is what makes "at most
two" and "tiers 1 and 2" the same statement; if that constant changes,
`tier_members()` below must gain a tier definition to match, or the run
fails loudly rather than silently reusing tier 2.

```python
# jarvis/council/config.py
TIER_MEMBERS: dict[int, dict[str, list[str]]] = {
    1: {"proposers": ["economy"], "judges": ["mid"]},
    2: {"proposers": ["frontier", "mid"], "judges": ["mid"]},
}

def tier_members(tier: int) -> dict[str, list[str]]:
    """Tier -> {'proposers': [tier names], 'judges': [tier names]}.
    Raises KeyError for an undefined tier — loud, never a silent
    fallback to a cheaper or more expensive council than intended."""
    return TIER_MEMBERS[tier]
```

*Rationale:* difficulty is measured by how many times the problem has already
defeated us — an observed fact, not a prediction. Frontier pricing is paid
only by problems that have beaten two cheaper attempts.

**Degenerate tiers.** If a tier has no profiles with a present API key,
fall back to the next tier up. If no tier has any usable profile, do not
convene — return the ordinary failure and log `council_unavailable`. Never
convene a council of one (D7).

### D5 — Proposers and judges are disjoint within a round

A model that proposed in a round does not judge in that round.

*Rationale:* two benefits. Cost — judging reads many tokens and writes few,
so mid-tier judges are materially cheaper than frontier ones. Bias — a model
cannot score its own proposal at all, which is stronger than relying on
anonymisation to hold.

**[guessing] Stated uncertainty, deliberately instrumented:** there is no
measurement showing mid-tier judges score *code* proposals as reliably as
frontier judges. The reasoning (evaluation is easier than generation) is
sound in general but code review has failure modes where a weaker judge
confidently scores a broken proposal highly.

**D8.2 is the apparatus that settles this**, and D8.2.4 fixes the promotion
thresholds in advance so the answer cannot be rationalised after the fact.
Start judges at `mid`. **Do not promote judges to frontier without running
`python -m jarvis.council --agreement` and hitting one of D8.2.4's
branches** — not on intuition, not because a single round looked wrong.

### D6 — Scoring: 1.0–10.0 in tenths, parsed strictly

Each judge scores **every proposal it did not write**, anonymised as
`Proposal A`, `Proposal B`, … The required output format, stated verbatim in
the judge prompt:

```
SCORES:
Proposal A: 7.4 — one-line justification
Proposal B: 8.1 — one-line justification
```

Parsing rule, implemented in `scoring.py`:

```python
_SCORE_RE = re.compile(
    r"^Proposal ([A-Z]):\s*(\d{1,2}(?:\.\d)?)\s*(?:—|-|–)?\s*(.*)$",
    re.MULTILINE,
)
```

- A score outside `[1.0, 10.0]` is **invalid**, not clamped.
- A judge whose output yields no valid scores, or that errors or times out,
  is recorded as an **abstention** with a reason. It is never silently
  dropped (invariant §0.1.5).
- A judge that scores only some proposals abstains **only on the ones it
  missed**; its valid scores still count.

*Rationale:* ordinal ranking (the source repo's approach) discards magnitude
— it cannot distinguish "A barely edged out B" from "A is excellent, B is
broken." Tenths make exact ties uncommon without pretending they are
impossible (D7).

**D6.1 — The two prompts, verbatim.** Copy these exactly. They are the
highest-leverage text in the feature and are not left to the implementer.

```python
# jarvis/council/council.py

PROPOSER_PROMPT = """You are one member of a council of AI models advising on \
a software change to the Mortimer codebase.

A previous attempt at this goal FAILED. You are being asked for a corrected \
approach.

Your output is a PLAN IN PROSE, read by another model that will write the \
actual code. Therefore:
- Do NOT output file contents, diffs, or code blocks longer than a few \
illustrative lines.
- DO state: what went wrong, what to do differently, which files to touch, \
and in what order.
- Be concrete and specific. Vague advice ("refactor carefully") is useless \
to the implementer.
- If you believe the goal cannot be achieved within the stated constraints, \
say so plainly and explain why — that is a valid and useful answer.

Keep your response under 400 words."""

JUDGE_PROMPT = """You are evaluating competing proposals for how to fix a \
failed software change.

You did NOT write any of these proposals. Judge them on merit alone.

Score EVERY proposal listed below on a scale of 1.0 to 10.0, using ONE \
decimal place. Use the full range: 1.0 means actively harmful, 5.0 means \
mediocre, 10.0 means excellent. Avoid clustering every proposal around the \
same value — the point of this exercise is to discriminate between them.

Judge on:
- Does it correctly diagnose why the previous attempt failed?
- Would following it actually fix the problem?
- Is it specific enough for another model to implement without guessing?
- Does it stay within the stated constraints?

Your response MUST end with a section in EXACTLY this format:

SCORES:
Proposal A: 7.4 - one-line justification
Proposal B: 8.1 - one-line justification

One line per proposal. Score every proposal shown. Do not add any other \
text after the SCORES section."""
```

**Assembly rule.** The proposer message is
`PROPOSER_PROMPT` as `system`, then a `user` message containing: the goal,
then `context["diff"]`, then `context["checks"]`. The judge message is
`JUDGE_PROMPT` as `system`, then a `user` message containing the goal
followed by each proposal rendered as `Proposal <label>:\n<content>`, in
label order. Labels are assigned `A`, `B`, `C`, … in registry order, and
**no proposer profile name ever appears in a judge's message.**

### D7 — Deterministic winner selection

`select_winner(scores) -> (winner_label, reason)` applies, strictly in order:

1. Highest **mean** score across judges that scored it.
2. Highest **minimum** score. *(Rewards the proposal no judge thought was
   bad — the right property when the artifact is code.)*
3. Lowest **variance**. *(Judges agreed.)*
4. **Registry order** in `upgrade_models.yaml` — arbitrary but fixed, so
   identical inputs always yield an identical winner.

A proposal with **zero** valid scores is not eligible to win. If no proposal
has any valid score, the round fails: log it and return the ordinary failure.

**Council size floor:** a round requires **≥2 proposers and ≥1 judge**. Below
that, do not convene — a one-member council is a slow single model, and a
zero-judge council has no selection basis. Log `council_too_small`.

**What is submitted is the highest-scoring PROPOSAL, not "the best model."**
Scores attach to anonymised proposals; identity is unmasked only after
selection. Selecting by model identity would leak identity back into the
decision and violate invariant §0.1.1.

### D8 — Council logging (new tables, migration `0009`)

Council rounds are delegations in all but name. Reuse the run-log's
two-tier shape rather than inventing new storage.

```sql
CREATE TABLE IF NOT EXISTS council_rounds (
  round_id TEXT PRIMARY KEY,
  run_id TEXT,                       -- the agent run that triggered it
  workflow TEXT NOT NULL,            -- 'selfedit' | 'apps'
  placement TEXT NOT NULL,           -- 'planner' | 'reviewer'
  trigger TEXT NOT NULL,             -- 'E1' | 'E2' | 'E3' | 'manual'
  tier INTEGER NOT NULL,             -- 1 | 2
  goal TEXT NOT NULL,
  proposer_count INTEGER NOT NULL,
  judge_count INTEGER NOT NULL,
  abstentions INTEGER NOT NULL DEFAULT 0,
  winner_profile TEXT,               -- unmasked AFTER selection
  winner_label TEXT,                 -- 'Proposal A'
  winner_mean REAL,
  select_reason TEXT,                -- which D7 branch decided it
  retry_validated INTEGER,           -- 1|0|NULL: did the retry pass? (D8.1)
  status TEXT NOT NULL,              -- running | ok | failed | too_small
  started_at TEXT NOT NULL,
  ended_at TEXT,
  latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_council_rounds_run ON council_rounds(run_id);

CREATE TABLE IF NOT EXISTS council_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  round_id TEXT NOT NULL,
  judge_profile TEXT NOT NULL,
  judge_tier TEXT NOT NULL,          -- 'economy'|'mid'|'frontier' (D8.2)
  shadow INTEGER NOT NULL DEFAULT 0, -- 1 == advisory only, excluded from
                                     -- selection (D8.2). Live scores are 0.
  proposal_label TEXT NOT NULL,
  proposal_profile TEXT NOT NULL,    -- unmasked at write time, post-selection
  score REAL,                        -- NULL == abstained
  abstain_reason TEXT,               -- NULL unless score IS NULL
  justification TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_council_scores_round ON council_scores(round_id);
CREATE INDEX IF NOT EXISTS idx_council_scores_shadow
  ON council_scores(round_id, shadow);
```

**`shadow` is load-bearing, not cosmetic.** Every read path that computes a
winner MUST filter `WHERE shadow = 0`. A shadow score that leaks into
selection would silently make a tier-1 round frontier-judged, destroying the
comparison the column exists to enable. `select_winner` (D7) never sees
shadow scores — `council.py` filters them out before calling it.

Append `("0009_council", MIGRATION_0009)` to `MIGRATIONS` in `jarvis/db.py`.
**One migration, both tables** — the same D24 rule from the trust plan: two
migrations from one plan is how a half-applied schema happens.

Full proposal texts go to `logs/council/<date>/<round_id>.jsonl`, mirroring
`logs/agents/`. SQLite holds bounded previews only.

**D8.1 — `retry_validated` is the whole point.** After a council round's
retry finishes, write back whether it passed validation. This is the only
way to answer "is the council earning its cost" from data instead of
assertion. Same discipline as `--calibrate`: ship the measurement with the
feature.

**`retry_validated` alone does NOT answer the judge-tier question** — see
D8.2. It tells you the winner failed; it cannot tell you whether a better
judge would have picked a different winner, because at tier 1 only mid-tier
judges ever score. That confound is what D8.2 removes.

### D8.2 — Judge-tier validation: can lesser models score?

*(Numbered under D8 because it is the logging decision extended, and so the
document reads in order. Referred to throughout as D8.2; there is no D15.)*

D5 asserts mid-tier judges are good enough and flags it `[guessing]`. This
decision is the apparatus that settles it from data. Two mechanisms, both
operating on **proposals that already exist**, so neither pays for extra
proposal generation.

#### D8.2.1 Shadow judging (online)

When a round runs, additionally score the same anonymised proposals with a
judge from a different tier. Shadow scores are written with `shadow = 1` and
**never affect selection**. The round proceeds byte-identically to how it
would have without shadowing.

```python
# jarvis/council/config.py

# ⚙ TUNING KNOB — fraction of rounds that also get a shadow judge pass.
# 0.0 disables shadow judging entirely. 1.0 shadows every round.
COUNCIL_SHADOW_RATE = 0.25

# Which tier shadows which. A tier absent from this map is never shadowed.
COUNCIL_SHADOW_TIERS: dict[int, str] = {1: "frontier"}
```

Sampling is deterministic per round, not random-per-process, so a replay of
the same round makes the same choice:

```python
def should_shadow(round_id: str, tier: int) -> bool:
    """Deterministic sampling: hash the round_id, compare to the rate.
    Same round_id always yields the same answer, so behaviour is
    reproducible and testable without monkeypatching random()."""
    if tier not in COUNCIL_SHADOW_TIERS or COUNCIL_SHADOW_RATE <= 0.0:
        return False
    if COUNCIL_SHADOW_RATE >= 1.0:
        return True
    digest = hashlib.sha256(round_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return bucket < COUNCIL_SHADOW_RATE
```

A shadow-judge failure is non-fatal and never degrades the round: catch,
log `council_shadow_failed`, continue. The live result is unaffected.

#### D8.2.2 Offline replay (free, retroactive)

Every round's full proposal texts are already in
`logs/council/<date>/<round_id>.jsonl` (D8). Replay re-scores stored
proposals with a different judge lineup and reports whether the winner
changes. It costs only judge calls, needs no live failure, and works on
rounds logged before the question was even asked.

```
python -m jarvis.council --replay <round_id> --judges frontier
python -m jarvis.council --agreement            # the summary report
python -m jarvis.council --agreement --since 30d
```

`--replay` prints, for one round: the live winner, the replayed winner,
both score tables side by side, and whether they agree.

**Replay is strictly read-only.** It never writes to `council_rounds`, never
mutates a stored winner, and never triggers a retry. It writes replay scores
only with `shadow = 1`, or with `--dry-run` writes nothing at all.

#### D8.2.3 The metric — winner agreement, not score agreement

Judges can disagree on absolute numbers and still agree on the ranking.
Selection consumes only the winner, so that is the primary metric.

`--agreement` reports, over all rounds having both live and shadow scores:

| Metric | Definition |
|---|---|
| **winner agreement** | % of rounds where the shadow lineup's `select_winner` picks the same proposal as the live lineup. **Primary.** |
| **rank correlation** | mean Spearman ρ between live and shadow orderings, over rounds with ≥3 scored proposals |
| **abstention rate by tier** | % of (judge, proposal) pairs that abstained, split by `judge_tier` — a judge that can't produce parseable scores is unusable regardless of its taste |
| **discrimination** | stdev of each judge tier's scores within a round. A judge that scores everything 7.5 is not judging. |
| **disagreement cost** | of rounds where winners differed, the `retry_validated` rate of the live (mid) pick. Populated only where a retry ran. |

Spearman ρ is computed inline (stdlib only, no scipy):

```python
def _spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation of two equal-length score vectors. Returns None
    if fewer than 3 pairs or if either vector is constant (undefined)."""
```

#### D8.2.4 The decision rule — stated in advance, not after seeing data

Deciding what counts as "good enough" *after* looking at the numbers is how
a desired conclusion gets rationalised. The thresholds are therefore fixed
here, before any data exists:

Promote judges from `mid` to `frontier` **iff, over ≥20 rounds with shadow
scores**, ANY of:

- winner agreement **< 0.70**, or
- mid-tier abstention rate **> 0.15**, or
- mid-tier discrimination (mean within-round stdev) **< 0.5**

Otherwise keep judges at `mid`. If fewer than 20 shadowed rounds exist, the
answer is **"insufficient data — keep mid-tier and keep collecting"**, never
a judgement call on a small sample. `--agreement` prints which branch applies
and the round count, so the reader does not re-derive it.

**Do not hand-tune these three numbers.** They are provisional starting
values chosen to be decidable, not calibrated — same status as
`PROCEDURE_MATCH_THRESHOLD` before `--calibrate` existed. Changing them
requires a documented reason and a note in §9, not a hunch.

*Rationale:* D5's cost saving is real only if mid-tier judges pick the same
winners. This is the cheapest possible way to find out — it reuses proposals
already generated and, via replay, works retroactively on data already on
disk. Shipping the tier split without this would be asserting the saving
rather than verifying it.

### D9 — UI membership selection, without a self-edit hole

**Registry stays where it is.** `config/upgrade_models.yaml` defines which
profiles exist, their endpoints, keys and tiers. It remains off the
allowlist. The UI can never define a new endpoint or point at a new key.

**Selection is stored separately:** `localStorage` under
`mortimer.council.*`, matching the existing `mortimer.drawer.*` convention.
The UI chooses only *which existing profiles participate*.

Picker rules, all mandatory:
- Profiles with `key_present: false` are **shown but not selectable**
  (`available_models()` already returns this flag). A missing key must never
  silently shrink a council — invariant §0.1.5.
- **Minimum 2 selectable members** enforced in the UI; the backend enforces
  it again (D7).
- Selection is per-tier: the user picks which profiles are eligible at each
  tier. An empty selection for a tier falls back to that tier's full
  registry membership.

*Rationale:* if membership lived in `upgrade_models.yaml` and the UI could
write it, the console would become a path for the agent to edit its own model
config — quietly undoing invariant §0.1.3.

### D10 — Endpoints and UI surface

Admin sidecar (`jarvis/admin/server.py`), all thin pass-throughs:

| Endpoint | Purpose |
|---|---|
| `POST /api/council/convene` | manual convene; body `{placement, goal?}` |
| `GET /api/council/round/{round_id}` | round detail incl. per-judge scores |
| `GET /api/council/rounds` | recent rounds |
| `POST /api/selfedit/reject` | E3 — human rejects the diff, triggers escalation |

UI lives in `web/src/components/EditModePanel.tsx` (the existing self-edit
surface): the membership picker, a "convene the council" button, a "reject"
button, and the score table with per-judge justifications. Reviews render
where the user already approves diffs — no new panel.

### D11 — Kill switch

`JARVIS_COUNCIL_ENABLED` (default `true`), a `Settings` field in
`jarvis/config.py`, matching `jarvis_procedures_enabled` /
`jarvis_runlog_enabled`. Enforced at exactly **one** place — the top of
`council.convene()` — so disabling it means no fan-out, no logging, no cost.
Escalation then falls through to today's behaviour.

### D12 — Tuning knobs

| Constant | Value | Module |
|---|---|---|
| `COUNCIL_MAX_ESCALATIONS` | `2` | `jarvis/council/config.py` |
| `COUNCIL_MIN_PROPOSERS` | `2` | `jarvis/council/config.py` |
| `COUNCIL_MIN_JUDGES` | `1` | `jarvis/council/config.py` |
| `COUNCIL_MEMBER_TIMEOUT_S` | `120` | `jarvis/council/council.py` |
| `COUNCIL_SCORE_MIN` / `_MAX` | `1.0` / `10.0` | `jarvis/council/scoring.py` |
| `COUNCIL_PREVIEW_CHARS` | `2000` | `jarvis/council/council.py` |
| `COUNCIL_SHADOW_RATE` | `0.25` | `jarvis/council/config.py` (D8.2.1) |
| `COUNCIL_SHADOW_TIERS` | `{1: "frontier"}` | `jarvis/council/config.py` (D8.2.1) |
| `COUNCIL_AGREEMENT_MIN_ROUNDS` | `20` | `jarvis/council/config.py` (D8.2.4) |
| `COUNCIL_AGREEMENT_FLOOR` | `0.70` | `jarvis/council/config.py` (D8.2.4) |
| `COUNCIL_ABSTENTION_CEILING` | `0.15` | `jarvis/council/config.py` (D8.2.4) |
| `COUNCIL_DISCRIMINATION_FLOOR` | `0.5` | `jarvis/council/config.py` (D8.2.4) |

### D13 — Failure isolation

A council failure must never be worse than no council. `convene()` catches
everything and returns `None` on failure; every caller treats `None` as
"proceed with the ordinary failure path." Mirrors `jarvis/procedures.py`'s
best-effort contract. One `WARNING` log per failure, never an exception into
the agent loop.

### D14 — App-scaffolding triggers are NOT defined here

`mcp_apps` has no validation gate equivalent to `session_validate`, so
"what counts as a failed scaffold" has no honest answer yet. The council
module is built workflow-agnostic (`workflow` column in D8) so this can be
added later without redesign, but **no `mcp_apps` wiring ships in this plan.**

**Do not invent a trigger for it.** If asked to extend the council to app
scaffolding, that is a new plan.

---

## §4 Files

**New:** `jarvis/council/{__init__,types,scoring,council,config}.py`;
`jarvis/council/__main__.py` (D8.2.2 CLI: `--replay`, `--agreement`);
`jarvis/council/agreement.py` (D8.2.3 metrics, pure — no network);
`tests/unit/test_council_scoring.py`; `tests/unit/test_council_config.py`;
`tests/unit/test_council_agreement.py`;
`tests/integration/test_council_escalation.py`;
`tests/acceptance/llm-council.md`.

**Modified:** `jarvis/db.py` (migration `0009`);
`jarvis/agents/upgrade_agent.py` (D3 tool, escalation hooks);
`config/upgrade_models.yaml` (`tier` field); `jarvis/config.py` (kill switch);
`jarvis/admin/server.py` (D10 endpoints);
`web/src/components/EditModePanel.tsx` (picker + reject + scores);
`.env.example`; `CLAUDE.md`.

---

## §5 Implementation order

1. `jarvis/db.py` migration `0009` + `tests/unit/test_db.py` update
   (add `"0009_council"` to `EXPECTED_MIGRATION_IDS`, plus a column test
   mirroring `test_migration_0008_columns_and_defaults`).
2. `jarvis/council/types.py` (D1.1 dataclasses), `config.py` (D4 tier ladder,
   `tier_members()`, membership resolution).
3. `jarvis/council/scoring.py` (D6 parser, D7 selection) + **the full §6
   scoring test table, before any network code exists.**
4. `jarvis/council/council.py` (D6.1 prompts, fan-out, anonymise, orchestrate,
   write D8 rows + JSONL).
5. D3 `session_decline` tool + dispatch + `SYSTEM_PROMPT` line + tests.
6. D2.1 escalation hook in `upgrade_agent.py` (`_maybe_escalate`,
   `_escalations_used`) + the §6 escalation test table.
7. `jarvis/config.py` kill switch (D11) + `.env.example` entry.
8. `jarvis/council/agreement.py` (D8.2.3 metrics + `_spearman`) +
   `tests/unit/test_council_agreement.py` — pure, testable from fixture rows
   with no network and no live rounds.
9. D8.2.1 shadow judging in `council.py` (`should_shadow`, shadow write path,
   the `shadow = 0` selection filter) + tests.
10. `jarvis/council/__main__.py` — D8.2.2 `--replay` and `--agreement`.
11. Admin endpoints (D10) + tests.
12. `EditModePanel.tsx` (D9 picker, reject button, score table).
13. Docs: `CLAUDE.md` council section, `tests/acceptance/llm-council.md`.

Step 3 before step 4 is deliberate: the selection rule is the highest-risk,
lowest-visibility logic and must be proven pure before anything calls it.
Step 8 before step 9 for the same reason — the agreement metrics are pure
and must be proven against fixtures before any shadow score is collected,
so a metric bug can never be mistaken for a judge-quality finding.

---

## §6 Verification

1. `pytest tests/unit tests/integration -q` — all green.
2. `python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog"`.
3. `python scripts/init_db.py` on a fresh DB — `0009` applies cleanly.
4. `cd web && npm run build` and `npm run lint` — zero errors.
5. `RUN_LIVE=1 python -m tests.evals.routing_eval` — **compare against a
   baseline run on the same machine**, do not treat 90% as absolute. See the
   note in `MORTIMER_AGENT_TRUST_PLAN.md` §10: the gate was already unmet on
   `main` before that plan, and run-to-run variance exceeds the effect size.
6. `tests/acceptance/llm-council.md` — manual checklist.

**Required scoring tests** (`scoring.py`, no network):

| Case | Expected |
|---|---|
| clean scores from all judges | correct mean, correct winner |
| exact tie on mean | broken by min score |
| tie on mean AND min | broken by variance |
| tie on all three | broken by registry order, stable across runs |
| score `10.5` / `0.5` | invalid, recorded as abstention, NOT clamped |
| integer score `8` (no decimal) | valid, parsed as `8.0` |
| judge returns prose with no `SCORES:` block | abstention with reason |
| judge scores 2 of 3 proposals | 2 counted, 1 abstention |
| judge emits an unknown label (`Proposal Z`) | ignored; the real labels still abstain |
| duplicate label from one judge (`Proposal A` twice) | first occurrence wins, second ignored |
| proposal with zero valid scores | ineligible to win |
| all proposals unscored | round fails, no winner, `select_reason` explains |
| 1 proposer | refuses to convene (`council_too_small`) |
| judge == proposer in same round | rejected by construction (D5) |
| `parse_scores` always returns `len(labels)` items | invariant, every case above |

**Required escalation tests** (`tests/integration/test_council_escalation.py`,
with a fake council and fake client — no network):

| Case | Expected |
|---|---|
| validation fails twice, council returns a winner | one retry runs, brief injected as a `system` message |
| validation fails twice, `convene()` returns `None` | falls through to today's failure return, unchanged |
| third failure after two escalations | no third council; session ends and reports |
| escalations use tier 1 then tier 2 | never the same tier twice |
| `JARVIS_COUNCIL_ENABLED=false` | no fan-out, no rows written, today's behaviour exactly |
| `session_decline` called | session ends `ok=False, declined=True`; E2 fires |

**Required judge-tier validation tests** (D8.2 — `test_council_agreement.py`
is pure and runs off fixture rows; the shadow-path cases live in
`test_council_escalation.py`):

| Case | Expected |
|---|---|
| **shadow scores never affect the winner** | round with shadow scores that would pick a different winner still selects the live winner — the single most important test in this table |
| `select_winner` is called with shadow rows filtered out | asserted directly, not inferred from the winner |
| `should_shadow` is deterministic | same `round_id` → same answer across calls and processes |
| `COUNCIL_SHADOW_RATE = 0.0` | never shadows; no extra judge calls issued |
| `COUNCIL_SHADOW_RATE = 1.0` | always shadows |
| tier absent from `COUNCIL_SHADOW_TIERS` | never shadowed |
| shadow judge raises / times out | live round completes normally, `council_shadow_failed` logged, no shadow rows |
| winner agreement, identical winners | `1.0` |
| winner agreement, all winners differ | `0.0` |
| Spearman on identical orderings | `1.0` |
| Spearman on exactly reversed orderings | `-1.0` |
| Spearman with a constant vector | `None`, not a crash or a fake `0.0` |
| Spearman with < 3 pairs | `None` |
| abstention rate splits by `judge_tier` | mid and frontier reported separately |
| discrimination on a judge scoring all `7.5` | stdev `0.0`, below floor |
| `--agreement` with 19 shadowed rounds | reports "insufficient data", names the count, recommends no change |
| `--agreement` with 20+ rounds, agreement `0.65` | recommends promoting judges (D8.2.4 branch 1) |
| `--agreement` with 20+ rounds, all metrics healthy | recommends keeping `mid`, names the branch |
| `--replay --dry-run` | writes nothing; DB row count unchanged before/after |
| `--replay` without `--dry-run` | writes only `shadow=1` rows; `council_rounds` untouched |

---

## §7 Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Mid-tier judges misjudge code | **Medium** | D8.2 shadow judging + `--agreement`; D8.2.4 fixes the promotion thresholds in advance so the call can't be rationalised after the fact |
| A shadow score leaks into selection, silently invalidating every comparison | **Medium** | `shadow` column indexed and filtered in `council.py` before `select_winner`; first test in the D8.2 table asserts it directly |
| Shadow judging quietly doubles judge spend | Low | `COUNCIL_SHADOW_RATE = 0.25` samples; `0.0` disables; replay (D8.2.2) is the free path and works retroactively |
| Agreement metrics are themselves buggy, producing a false judge-quality verdict | Medium | `agreement.py` is pure and built (step 8) with fixture tests *before* any shadow data is collected |
| Council costs exceed value | Medium | Zero cost on the happy path; D8 makes spend measurable |
| Escalation loop | Low | `COUNCIL_MAX_ESCALATIONS = 2`, strictly ascending tiers |
| A member's failure silently shrinks the council | Medium | Explicit abstentions (D6), never dropped |
| UI membership becomes a self-edit hole | Low | D9 — registry off-allowlist, selection in localStorage |
| Score parser too strict | Medium | Abstention is explicit and counted, so over-strictness is *visible* rather than silent |

---

## §8 Rollback

`JARVIS_COUNCIL_ENABLED=false` disables all council behaviour at one
enforcement point (D11); escalation reverts to today's report-and-stop.
Migration `0009` only adds tables — nothing reads them when disabled, so no
schema rollback is required. `session_decline` (D3) is independently
desirable and should stay even if the council is abandoned.

---

## §9 Approval

- [ ] Larry has read §0–§3 and approves.
- [ ] Implementation may begin.

**To record on completion:** observed cost per escalated session; whether
tier 2 was ever reached; and — once ≥20 shadowed rounds exist — the full
`python -m jarvis.council --agreement` output, including which D8.2.4 branch
applied and the resulting judge-tier decision. Record the output verbatim
rather than a summary of it, the same way `--calibrate`'s populations were
recorded in `MORTIMER_AGENT_TRUST_PLAN.md` §10.

**Do not record a judge-tier verdict before 20 shadowed rounds exist.**
"Insufficient data" is the correct answer until then, and D8.2.4 says so.
