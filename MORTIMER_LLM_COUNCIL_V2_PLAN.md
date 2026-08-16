# MORTIMER LLM COUNCIL V2 — hardening and completion plan

**Extends** `MORTIMER_LLM_COUNCIL_PLAN.md` (implemented 2026-08-16, r4).
That plan stays authoritative for everything this document does not touch.
Where this document changes a v1 decision, it says so explicitly (V2
supersedes D6.1's judge-assembly clause; V14 completes D2's E2 row). This
plan's decisions are numbered **V1–V14** — the v1 plan owns D1–D14, and
its D8.2 header explicitly reserves against a "D15", so V-numbers avoid
any collision.

Source: a post-implementation review (2026-08-16) that found two
conformance gaps against the approved v1 plan, several robustness risks,
and quality/visibility improvements. Two design forks were resolved with
Larry before this plan was written: E2 becomes a scope-advisor council
(V14), and thin tier-1 judge pools backfill from frontier (V8).

## Revision history

| # | Item | Closed by |
|---|---|---|
| 1 | Tier-1 winner carry-forward (v1 D4 requirement, never implemented) | **V1** |
| 2 | Judges never see the failure context (defect in v1 D6.1 itself) | **V2** |
| 3 | Kill-switch env read vs `.env` — verified, documentation only | **V3** |
| 4 | Label order leaks proposer identity | **V4** |
| 5 | Convene/reject HTTP endpoints block for minutes | **V5** |
| 6 | Parser silently mis-reads two-decimal scores | **V6** |
| 7 | Shadow judging adds up to 120 s to the live round | **V7** |
| 8 | Single-judge tier 1 is fragile | **V8** |
| 9 | No token accounting; §9 of v1 can't be answered from data | **V9** |
| 10 | Council retry can die on the iteration cap it didn't budget for | **V10** |
| 11 | `logs/council/` and both tables never pruned | **V11** |
| 12 | E1 rounds invisible in the UI; `run_id` never populated | **V12** |
| 13 | `--agreement` tiebreak approximation is removable | **V13** |
| 14 | E2 is a listed-but-inert trigger | **V14** |

---

## §0 Binding constraints

### §0.0 This plan assumes nothing about how capable you are

Every decision in this document has already been made. Your job is to
implement it exactly as written, not to improve on it.

**If you find yourself deciding something this document did not decide,
that is a defect in the document — stop and report it rather than
choosing.** Specifically: do not choose a shuffle algorithm, do not pick
the backfill source tier, do not invent a price table for token costs,
and do not decide what a scope council may execute. All four are
specified below.

### §0.1 Non-negotiable invariants (unchanged from v1)

1. **A council may rank, review, and advise. It may NEVER author a merged
   artifact.** V14's scope brief is advisory text; nothing in this plan
   executes a council output.
2. **No predictive gating.** Every trigger in this plan is an event that
   already happened (a second validation failure, a recorded decline, a
   human click).
3. **`config/upgrade_models.yaml` stays off the self-edit allowlist.**
4. **Never infer from prose what can be recorded as a fact.** V6 makes
   the parser stricter, never more lenient.
5. **A failed council member is an explicit abstention, never silently
   dropped.**
6. **Nothing here runs in the voice latency path.** V7 additionally
   removes shadow judging from the *retry* latency path.
7. **New for v2 — shadow scores never affect selection.** Every change in
   this plan preserves the `shadow = 0` filter before `select_winner`;
   V7 moves shadow work in time, not in effect.

---

## §1 Verified background

Line references verified 2026-08-16 against the implemented v1 code.
Re-verify anchors before editing — functions, not line numbers, are the
contract.

| Fact | Where |
|---|---|
| Escalation hook `_maybe_escalate`; stores `_pending_council_round_id` | `jarvis/agents/upgrade_agent.py` line 455; write-back at 487 |
| `run()` loop is `for _ in range(self.cfg["max_iterations"])`; escalation resets `repairs_used = 0` at line 444 | `jarvis/agents/upgrade_agent.py` `run()` at line 293 |
| `session_decline` handling (returns `declined=True`, ends session) | `jarvis/agents/upgrade_agent.py` inside `run()`'s tool dispatch, directly above the `session_validate` failure branch |
| `convene()` / `_convene_inner()` | `jarvis/council/council.py` lines 224 / 249 |
| Labels assigned `A, B, C…` in registry order after fan-out | `jarvis/council/council.py` line 182 (`_gather_proposals`) |
| Judge message = goal + proposals only (no failure context) | `jarvis/council/council.py` `_judge_user_message` line 145 |
| Shadow pass runs inline, `await`ed before the result returns | `jarvis/council/council.py` line 364 |
| `_write_payload` writes `round_start`…`round_end` JSONL | `jarvis/council/council.py` line 586 |
| `record_retry_validated` | `jarvis/council/council.py` line 510 |
| `_council_enabled()` reads `os.environ` directly | `jarvis/council/council.py` line 41 |
| Tier ladder `TIER_MEMBERS`, `resolve_members(…, exclude=)` | `jarvis/council/config.py` lines 59 / 140 |
| `resolve_tier_name_members` (raw tier-name resolution, never raises) | `jarvis/council/config.py` line 185 |
| Score regex `_SCORE_RE` | `jarvis/council/scoring.py` line 27 |
| Replay CLI `_do_replay`; payload readers filter records by `type` | `jarvis/council/__main__.py` line 87 |
| Agreement's registry-order approximation, documented | `jarvis/council/agreement.py` module docstring line 10 |
| Blocking endpoints `council_convene` / `selfedit_reject` | `jarvis/admin/server.py` lines 422 / 314 |
| Async-job precedent: `_run_job` dict + `_run_lock` + background thread + GET polling | `jarvis/admin/server.py` (`/api/selfedit/run`) |
| Runlog retention precedent: `prune(retention_days)` called once at bot startup | `jarvis/runlog/prune.py`; call site `jarvis/bot/pipeline.py` lines 363–374 |
| **Verified:** all launch scripts export `.env` into the process env (`set -a; . ./.env; set +a`) | `scripts/run_admin.sh`, `scripts/run_bot.sh` (and `mortimer.sh` invokes them) |
| Latest migration is `0009_council` | `jarvis/db.py` `MIGRATIONS` |
| Council UI (picker, convene, reject, score table) | `web/src/components/EditModePanel.tsx`; styles in `web/src/editmode.css` |
| Existing endpoint `GET /api/council/rounds` (already implemented, unused by UI) | `jarvis/admin/server.py` |

**Terminology** is unchanged from v1 (round, member, proposal, proposer,
judge). New in v2: a **carried proposal** (V1) is a proposal injected
into a round from a previous round rather than generated by fan-out; a
**scope council** (V14) is a round with `placement='scope'`.

---

## §2 Scope

**In scope:** the fourteen V-decisions below; migration `0010`; UI
changes confined to `EditModePanel.tsx` + `editmode.css`; one new module
`jarvis/council/prune.py`.

**Out of scope, explicitly:**
- Placement C (Council-as-Competitor) — still deferred.
- App-scaffolding triggers — v1 D14 still applies; do not invent one.
- Dollar-cost estimation. V9 records **tokens**, which are facts from the
  API response. Prices change and per-provider price tables are a
  maintenance liability; converting tokens to dollars is a reporting
  concern for a future plan, not this one.
- Cross-process threading of the voice-path `run_id` into the sidecar
  (V12 explicitly decides *against* it — see V12).
- Any change to `session_submit`'s gate or human-merges-on-GitHub.

---

## §3 Decisions

### V1 — Carry the tier-1 winner into tier 2 (v1 D4 conformance)

v1 D4: *"At tier 2 the tier-1 winning proposal is carried forward as an
additional candidate."* Not implemented. Fix:

**State.** `UpgradeAgent` gains `self._last_council_winner:
tuple[str, str] | None = None` (profile, content), initialised in
`__init__` and reset to `None` at the top of `run()` alongside
`_escalations_used`. In `_maybe_escalate`, after a successful convene
(`result.winner is not None`), set
`self._last_council_winner = (result.winner.profile,
result.winner.content)` — immediately before the existing
`self._pending_council_round_id = result.round_id` line. When building
`context` for a convene at `tier >= 2` and `self._last_council_winner is
not None`, add:

```python
context["carry_forward"] = {
    "profile": self._last_council_winner[0],
    "content": self._last_council_winner[1],
}
```

**Consumption, in `_convene_inner` (council.py).** Ordering matters:
judge resolution currently happens BEFORE proposal fan-out (§1's line
anchors), and the carried profile must be excluded from the judge pool —
so read the carry from context **early**, next to the existing
`selected = context.get("members")` line:

```python
carry = context.get("carry_forward") if isinstance(context, dict) else None
carry_profile = {str(carry["profile"])} if carry and carry.get("profile") else set()
```

and pass `exclude=set(proposer_names) | carry_profile` when resolving
judges. Then, after `_gather_proposals` returns and before the
post-fan-out size check:

```python
if carry and carry.get("content"):
    proposals.append(Proposal(
        label="",  # real label assigned by the V4 shuffle below
        profile=str(carry.get("profile") or "unknown"),
        content=str(carry["content"]),
    ))
```

(If V4's shuffle is implemented first — it should be, per §5 — labels for
ALL proposals, fan-out and carried alike, are assigned in one place after
the shuffle, so the empty label above is never observable. If you find
yourself writing a second label-assignment site, stop: that is the V4
design being violated.)

**Rules:**
- The carried proposal counts toward `proposer_count` and toward the
  post-fan-out `council_size_ok` check (it is a real candidate).
- Its `profile` joins the judge-pool `exclude` set, exactly like a
  fan-out proposer (the `carry_profile` set above). With today's
  registry this is a no-op — tier-1 winners are economy-authored and
  tier-2 judges are frontier — but the rule is per-member by design,
  v1 r3→r4.
- If the carried profile ALSO proposed fresh in this round, keep both
  proposals. Judges score proposals, not models; two proposals from one
  author are two candidates. `select_winner`'s D5 backstop already
  excludes that profile's *scores*, not its proposals.
- The JSONL `proposal` record for a carried proposal gains `"carried":
  true`; fan-out proposals gain `"carried": false`. The
  `council_scores.proposal_profile` column needs no change.

*Rationale:* already paid for, and occasionally the cheap proposal was
right while the retry failed for an unrelated reason (v1 D4's own words).

### V2 — Judges see the failure context (supersedes v1 D6.1's judge-assembly clause)

v1's judge rubric asks "does it correctly diagnose why the previous
attempt failed?" while v1 D6.1 gives judges only the goal and the
proposals. A judge cannot verify a diagnosis it cannot see. This was a
defect in the v1 plan that carried into code.

`_judge_user_message` changes signature (final shape in the §3 signature
ledger — it also gains `placement` from V14) and, for every non-scope
placement, assembles in this exact order:

```
GOAL:
<goal>

FAILURE CONTEXT — the attempt being corrected:
<context["diff"]>          (section omitted when key absent/None)

VALIDATION CHECKS:
<context["checks"]>        (section omitted when key absent/None)

Proposal A:
<content>

Proposal B:
<content>
```

Both call sites update: `_convene_inner` (live + shadow share
`judge_user_content`, so one change covers both) and
`jarvis/council/__main__.py`'s `_do_replay`. For replay, the context
comes from the stored `round_start` JSONL record's `"context"` field
(already written by `_write_payload`); a payload whose `round_start`
lacks usable context replays with the sections omitted — old rounds
degrade gracefully rather than erroring. The invariant **"no proposer
profile name ever appears in a judge's message"** still holds: `diff`
and `checks` come from the self-edit service and contain no council
member names.

`JUDGE_PROMPT` text is unchanged — its rubric was always right; the
input was wrong.

**How the assembly functions branch (also load-bearing for V14):** both
`_proposer_user_message` and `_judge_user_message` gain a `placement`
parameter and branch on it at exactly one point each — `placement ==
"scope"` uses V14's GOAL / DECLINE REASON / ALLOWLIST template; every
other placement uses this decision's GOAL / FAILURE CONTEXT / CHECKS
template. Do not branch on which context keys happen to be present —
placement is the declared intent, context keys are just its payload, and
keying off payload shape is exactly the inference-from-prose mistake
§0.1.4 exists to prevent.

### V3 — Kill-switch env path: verified, document only

Investigated (review item 3): `scripts/run_admin.sh` and
`scripts/run_bot.sh` both `set -a; . ./.env; set +a` before exec, so
`.env` values ARE process-environment values in every documented launch
path, and `_council_enabled()`'s direct `os.environ` read is correct.
The residual gap is only someone running `python3 -m jarvis.admin.server`
bare, which is not a documented launch path.

**No code change.** Two documentation edits:
1. `_council_enabled()`'s docstring gains: *"The launch scripts export
   `.env` into the process environment (`set -a`), so a `.env`-only
   setting reaches this read in every documented launch path. If you run
   the module directly without the scripts, the variable must be a real
   environment variable."*
2. `.env.example`'s `JARVIS_COUNCIL_ENABLED` comment gains: *"read from
   the process environment; the run scripts export this file"*.

### V4 — Deterministic per-round label shuffle

Labels are currently assigned `A, B, C…` in registry order, which is
stable and knowable — a judge that knows the registry can de-anonymise
by position. Fix: shuffle proposal order deterministically per round
before assigning labels.

In `_convene_inner`, after fan-out (and after V1's carried-proposal
append), replace label assignment inside `_gather_proposals` with a
single labeling step in `_convene_inner`:

```python
import random  # module-level import

rng = random.Random(int.from_bytes(
    hashlib.sha256(round_id.encode("utf-8")).digest()[:8], "big"))
rng.shuffle(proposals)
proposals = [
    Proposal(label=f"Proposal {chr(ord('A') + i)}",
             profile=p.profile, content=p.content)
    for i, p in enumerate(proposals)
]
```

`_gather_proposals` therefore no longer assigns labels — it returns
`Proposal` objects with `label=""` and this is the ONLY place labels are
created. Add `hashlib` to council.py's imports.

**Properties, all load-bearing:**
- Seeded by `round_id` (same derivation family as `should_shadow`), so a
  replay of the same round reconstructs the same labels — required
  because `--replay` re-reads proposals from JSONL where labels are
  already fixed; the shuffle only runs at original convene time, never
  at replay time.
- `random.Random(seed)` instance, never the global `random` module — no
  cross-contamination with other code, no monkeypatching needed in tests.
- `select_winner`'s rule-4 tiebreak still uses **registry** order (the
  `registry_order` argument is unchanged) — the shuffle hides identity
  from judges; it must not make the tiebreak nondeterministic.

### V5 — Non-blocking convene: the sidecar job pattern

`POST /api/council/convene` and `POST /api/selfedit/reject` currently
hold the HTTP request open for the full round (minutes with real
models); browser fetches will time out. Reuse the sidecar's existing
async-job pattern (`_run_job` + `_run_lock` + daemon thread + GET
polling), which the codebase already trusts.

**New module-level state in `jarvis/admin/server.py`:**

```python
_council_lock = threading.Lock()
_council_job: dict[str, Any] = {
    "state": "idle",   # idle | running | done | error
    "trigger": None,    # 'manual' | 'E3'
    "goal": None,
    "round_id": None,
    "winner": None,     # {"profile": ..., "content": ...} | None
    "winner_mean": None,
    "select_reason": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}
```

**Endpoint changes:**

| Endpoint | New behaviour |
|---|---|
| `POST /api/council/convene` | validates as today (placement, goal), then: refuse with `"a council round is already in progress"` if `_council_job["state"] == "running"`; otherwise set the job to `running`, start a daemon thread that runs `asyncio.run(convene(...))`, settle the job (`done` with round/winner fields, or `error`), and return `{"ok": True, "started": True}` immediately |
| `GET /api/council/job` | **new** — returns `{"ok": True, "job": dict(_council_job)}` (the polling target, mirroring `GET /api/selfedit/run`) |
| `POST /api/selfedit/reject` | the **revert stays synchronous** (it is fast and its result must be in the response); the E3 council moves to the same background job slot (`trigger='E3'`, goal = the rejected session's goal, context captured **before** the revert clears `service.proposals`); response becomes `{"ok": True, "reverted": …, "council_started": bool}` |
| `GET /api/council/round/{id}`, `GET /api/council/rounds` | unchanged |

One council job at a time is a deliberate bound, matching the one-run-
at-a-time `_run_job` rule. A `convene()` that returns `None` settles the
job as `error` with `"council unavailable — see admin sidecar logs"`; a
`RoundResult` with `winner=None` settles as `done` with
`winner=None` and the `select_reason` populated (the round *ran*; it
just selected nobody — same distinction `_maybe_escalate` makes).

**UI:** `EditModePanel.tsx`'s `onConvene` and `onReject` switch from
awaiting the result in one fetch to: fire the POST, then poll
`GET /api/council/job` every 3 s (same interval as the existing
`startPolling`) until `state` is `done`/`error`, then render exactly what
they render today (winner card via the job fields, score table via the
existing `loadCouncilRound(round_id)`). The E1 path (`_maybe_escalate`)
is unchanged — it already runs inside a background thread and *needs*
the result synchronously to inject the brief.

### V6 — Strict decimal parsing

`Proposal A: 7.44 - good` currently parses as `7.4` with `4 - good`
leaking into the justification. Consistent with "out-of-range is an
abstention, never clamped": a malformed score is an abstention, never a
silent partial read. Replace `_SCORE_RE` with:

```python
_SCORE_RE = re.compile(
    r"^Proposal ([A-Z]):\s*(\d{1,2}(?:\.\d)?)(?=\s|$)\s*(?:—|-|–)?\s*(.*)$",
    re.MULTILINE,
)
```

The lookahead `(?=\s|$)` requires the numeric token to end at whitespace
or end-of-line, and regex backtracking cannot rescue `7.44` (neither
`7.4`-then-`4` nor `7`-then-`.` satisfies the lookahead), so the whole
line fails to match and the label falls through to `parse_scores`'
existing "judge did not score this proposal" abstention — no new code
path. Behaviour that must NOT change: `8`, `8.0`, `10.0`, `8 - fine`,
and `8.0 — fine` all still parse. New required behaviour: `7.44`,
`8.`, and `10.55` yield abstentions.

### V7 — Shadow judging off the live path

The shadow pass currently delays `convene()`'s return by up to
`COUNCIL_MEMBER_TIMEOUT_S` for a purely advisory measurement. Move the
network calls and writes to a detached thread.

**Why a thread and not an asyncio task:** `convene()` runs under
`asyncio.run(...)` (both in `_maybe_escalate` and in V5's job thread);
that event loop closes the moment `convene()` returns, killing any
pending task. A daemon `threading.Thread` running its own
`asyncio.run(_shadow_pass(...))` survives the caller's loop.

**Mechanics:**
1. Extract the shadow logic into a coroutine
   `_shadow_pass(round_id, shadow_judge_names, profiles_by_name,
   judge_user_content, labels, profile_tiers, label_to_profile,
   payload_path)` that: gathers shadow scores (`shadow=True`), writes
   them via `_write_score_rows(..., shadow=True)`, and **appends** its
   score records to the round's existing JSONL file (open mode `"a"`,
   same record shape with `"shadow": true`). Record order in the JSONL
   is not semantic — all readers (`_load_payload` consumers) filter by
   `type`, verified in §1 — so shadow records landing after `round_end`
   is correct, not a compromise.
2. In `_convene_inner`, the *decision* (`should_shadow`, tier-name
   resolution, exclusion set) stays inline and cheap; only the launch
   changes:

```python
# ⚙ TUNING KNOB — True runs the shadow pass inline (tests; deterministic
# CLI runs). False (default) detaches it so the live result returns
# without waiting on an advisory measurement.
COUNCIL_SHADOW_INLINE = False
```

   When `COUNCIL_SHADOW_INLINE` is true, `await _shadow_pass(...)` as
   today. Otherwise `threading.Thread(target=lambda:
   asyncio.run(_shadow_pass(...)), daemon=True).start()`.
3. **Semantic change, documented:** `RoundResult.scores` now contains
   live scores only (shadow scores are no longer merged into the
   result), and `_write_payload` no longer takes `shadow_scores` (the
   pass appends its own). No production caller reads shadow scores from
   `RoundResult` — verify with a grep before relying on this, and update
   the D1.1 comment on the dataclass field to say "live scores only; the
   shadow pass writes independently (V7)".
4. Existing shadow tests set `COUNCIL_SHADOW_INLINE = True` via
   monkeypatch and keep their current assertions; add one new test that
   with the knob False, `convene()` returns before shadow rows exist
   (assert zero `shadow=1` rows immediately after return, then join the
   thread via a test seam — expose the started thread on a module-level
   `_last_shadow_thread` variable assigned just after `.start()`, tests
   `join(timeout=5)` it and then assert rows exist).

### V8 — Tier-1 judge backfill from frontier (resolved with Larry, 2026-08-16)

With today's registry the mid tier has one profile; one abstention fails
the round and the min/variance tiebreaks are inert with n=1.

```python
# jarvis/council/config.py
# ⚙ TUNING KNOB — target judge-pool size. When a tier's judge resolution
# yields fewer than this, backfill from tiers ABOVE the role's highest
# tier name in _TIER_ORDER (never below: judges are never cheaper than
# the tier the ladder assigned). Distinct from COUNCIL_MIN_JUDGES (=1),
# which remains the hard floor for convening at all.
COUNCIL_JUDGE_TARGET = 2
```

In `resolve_members`, only when `role == "judges"`: after the existing
per-tier-name resolution and fallback produce `out`, if `len(out) <
COUNCIL_JUDGE_TARGET`, walk `_TIER_ORDER` strictly above the highest
tier name in `tier_names` (for tier 1 that means: judges resolved from
`mid`, backfill walks `frontier` only) and append usable profiles
(respecting `selected` and `exclude`, skipping names already in `out`)
until `len(out) == COUNCIL_JUDGE_TARGET` or the ladder is exhausted.
Exhaustion below the target is NOT an error — the round convenes with
what exists; only `len(out) == 0` raises `NoUsableProfilesError` as
today. Proposer resolution is untouched.

Interaction with V1: the judge `exclude` set (proposers + carried
profile) applies to backfill candidates identically — a frontier profile
that proposed at tier 2 cannot be backfilled as a judge.

### V9 — Token accounting (tokens, not dollars — see §2)

`_call_profile` changes return type to `tuple[str, dict | None]`:
`(content, usage)` where `usage = {"prompt_tokens": int,
"completion_tokens": int}` taken from `response.usage` when present,
else `None` (some OpenAI-compatible providers omit it; never fabricate).
Both `_gather_proposals` and `_gather_scores` (and `_do_replay`) update
to unpack the tuple; each accumulates the usages it saw.

**How usage flows out of the gather helpers** (this is a multi-consumer
contract; fixed here, not left open): both gather helpers change return
type to a tuple —

```python
async def _gather_proposals(...) -> tuple[list[Proposal], dict]
async def _gather_scores(...)   -> tuple[list[Score], dict]
```

where the second element is always
`{"prompt_tokens": int, "completion_tokens": int, "reported_calls": int}`
— sums over only the member calls whose response carried usage, with
`reported_calls` counting them. `_convene_inner` sums the dicts from the
proposer pass and the live-judge pass; if the combined `reported_calls`
is `0`, it writes NULLs to the round row (unknown, never zero).
`_do_replay` unpacks and **discards** usage — replay must never write to
`council_rounds` (v1 D8.2.2's read-only rule), and recording replay
token spend is out of scope.

**Storage:**
- Migration `0010` (V13 shares it — ONE migration for this plan, per the
  D24 rule) adds to `council_rounds`: `prompt_tokens INTEGER`,
  `completion_tokens INTEGER` (nullable; pre-v2 rows stay NULL, readers
  treat NULL as "unknown", never zero — same discipline as
  `tools_ok`/`tools_failed`).
- `_convene_inner` sums usage across all proposer and live-judge calls
  and writes the totals in `_write_round_row`. The V7 shadow pass adds
  its own usage afterward via one `UPDATE council_rounds SET
  prompt_tokens = COALESCE(prompt_tokens,0) + ?, completion_tokens =
  COALESCE(completion_tokens,0) + ? WHERE round_id = ?` (best-effort,
  same try/except-log pattern as its other writes).
- JSONL: each `proposal` and `score` record gains a `"usage"` field
  (the dict or `null`).
- CLI: `python -m jarvis.council --agreement` output gains one line,
  `total tokens          prompt=<sum> completion=<sum> (rounds with
  usage: <n>/<total>)`, summed over the same round set it already
  reports on. This is what lets v1 §9's "observed cost per escalated
  session" be recorded from data.

### V10 — Escalation extends the iteration budget

`run()`'s loop is `for _ in range(max_iterations)`; a tier-2 escalation
late in a session can win a council round and then die on the iteration
cap before the retry acts, wasting the entire council spend.

Restructure the loop header — the ONLY structural change to `run()`:

```python
iterations_used = 0
iterations_budget = self.cfg["max_iterations"]
while iterations_used < iterations_budget:
    iterations_used += 1
    ...  # existing body, unchanged
```

At the escalation-success site (immediately after `repairs_used = 0`,
before `break`):

```python
iterations_budget += COUNCIL_RETRY_EXTRA_ITERATIONS
```

```python
# jarvis/council/config.py
# ⚙ TUNING KNOB — extra loop iterations granted per successful
# escalation, so a council-guided retry cannot be starved by budget the
# failed attempts already spent. Bounded: at most COUNCIL_MAX_ESCALATIONS
# grants per session (i.e. +8 with the defaults).
COUNCIL_RETRY_EXTRA_ITERATIONS = 4
```

Import it lazily inside `run()` alongside the existing lazy council
imports (same circular-import rationale as `_maybe_escalate`'s). The
wall-clock bound (`max_session_minutes`) is deliberately NOT extended —
it is the outer safety net and stays absolute. The existing test
asserting `client.calls == agent.cfg["max_iterations"]` remains valid:
without an escalation the budget never grows.

### V11 — Council retention pruning

New module `jarvis/council/prune.py`, a structural copy of
`jarvis/runlog/prune.py`: `prune(retention_days, db_path=None,
root=None) -> dict` deletes `council_scores` then `council_rounds` rows
older than the cutoff (by `started_at`) and `logs/council/<date>/`
directories older than the cutoff, returns `{"rounds_deleted": n,
"dirs_deleted": n}`, `retention_days <= 0` disables and returns zeros,
never raises to the caller.

```python
# jarvis/config.py
# LLM Council v2 (V11) — retention for council_rounds/council_scores and
# logs/council/, pruned once at bot startup beside the runlog prune.
# Deliberately much longer than the runlog's 30 days: D8.2.4's judge-tier
# decision needs >= 20 SHADOWED rounds, which accumulate slowly (25%
# sample of escalated rounds only) — pruning faster than they accumulate
# would permanently starve the measurement. <= 0 disables.
jarvis_council_retention_days: int = 180
```

Call site: `jarvis/bot/pipeline.py`, immediately after the existing
`prune_runlog` block (lines 363–374), same try/except-log shape, one
INFO line `council_prune rounds_deleted=%d dirs_deleted=%d`.
`.env.example` gains the commented variable with the starvation warning.

### V12 — Round visibility in the UI; `run_id` documented as reserved

**Visibility.** The council section in `EditModePanel.tsx` gains a
"Recent rounds" `<details>` block (collapsed by default, below the score
table): on expand, fetch `GET /api/council/rounds?limit=10` (endpoint
already exists, currently unused by any UI) and render one row per
round — local time (reuse the panel's fetch/render idioms), `trigger`,
`tier`, `status`, `winner_profile ?? "—"`, `retry_validated` rendered as
`✓`/`✗`/`—`. Clicking a row calls the existing `loadCouncilRound(round_id)`
so the existing score table shows that round. This is what makes
E1-triggered rounds (which happen inside a background agent run)
reachable without the CLI.

**`run_id`.** Decision: do NOT thread the voice-path run identifier
across the HTTP boundary into the sidecar. The delegate `run_id` lives
in the bot process; the sidecar's `UpgradeAgent` runs behind
`POST /api/selfedit/run` with no such identifier, and inventing a
cross-process correlation protocol is a plan of its own. Instead the
column's meaning is documented where it is defined: update the
`council_rounds` schema comment in `jarvis/db.py` (comment-only — no
migration; SQLite comments live in our source, not the DB) from
`-- the agent run that triggered it` to `-- reserved: agent-run
correlation for future workflows (e.g. apps). NULL for all selfedit
rounds — the sidecar has no run_id (LLM_COUNCIL_V2 V12).` and mirror
one sentence in CLAUDE.md's council section.

### V13 — Exact replay tiebreaks: persist the registry order

`agreement.py` documents an approximation: registry order for the rule-4
tiebreak is reconstructed from row order. Remove it:

- Migration `0010` (shared with V9) adds `council_rounds.registry_order
  TEXT` — a JSON array of profile names in registry order, written by
  `_write_round_row` from the `registry_order` local already computed in
  `_convene_inner`. Also add `"registry_order"` to the JSONL
  `round_start` record.
- `compute_agreement` reads it: when a round's row has non-NULL
  `registry_order`, `json.loads` it and pass it to both `select_winner`
  calls; when NULL (pre-v2 rounds), fall back to the current
  approximation. Update the module docstring: the approximation is now
  the legacy fallback, not the design.
- `_do_replay` likewise prefers the stored order (from the round row it
  already loads) over the live registry — a replay of an old round must
  tiebreak with the registry *as it was*, not as it is.

### V14 — E2 becomes a scope-advisor council (resolved with Larry, 2026-08-16)

A decline is recorded (v1 D3, working) but nothing convenes — and the
standard proposer prompt would be wrong anyway: there is no failed diff
to correct, and a council cannot move a goal onto the allowlist. The
useful question is *which subset of the goal is achievable*, and that is
what E2 now asks. **The brief is advisory only: it is returned and
displayed, never auto-executed. The session still ends declined. You
decide whether to re-run with a narrowed goal.**

**Two new prompts in `jarvis/council/council.py`, verbatim:**

```python
SCOPE_ADVISOR_PROMPT = """You are one member of a council of AI models \
advising on the Mortimer voice assistant's self-edit system.

The self-edit agent DECLINED the goal below because it requires changes \
outside its allowlist. Your job is to analyse scope, not to write code.

You are given the goal, the agent's stated reason for declining, and the \
allowlist configuration (allow patterns and deny patterns; deny always \
wins).

Your output is a SCOPING ANALYSIS IN PROSE, read by a human deciding what \
to do next. State:
- Which specific parts of the goal fall OUTSIDE the allowlist, and which \
deny/allow patterns they hit.
- Which subset of the goal IS achievable entirely within the allowlist, \
if any. Be honest: "none of it" is a valid and useful answer.
- A suggested rephrasing of the goal narrowed to the achievable subset, \
written so it could be given to the agent as-is.
- What the human would need to develop themselves for the remainder.

Do NOT output file contents, diffs, or code. Keep your response under \
300 words."""

SCOPE_JUDGE_PROMPT = """You are evaluating competing scoping analyses of \
a goal that a self-edit agent declined as outside its allowlist.

You did NOT write any of these analyses. Judge them on merit alone.

Score EVERY proposal listed below on a scale of 1.0 to 10.0, using ONE \
decimal place. Use the full range and avoid clustering scores.

Judge on:
- Does it correctly identify which parts of the goal are inside vs \
outside the allowlist, per the patterns shown?
- Is the proposed achievable subset genuinely achievable within the \
allowlist as written?
- Is the suggested narrowed goal concrete enough to hand to the agent \
without edits?
- Is it honest where the answer is "none of this is achievable"?

Your response MUST end with a section in EXACTLY this format:

SCORES:
Proposal A: 7.4 - one-line justification
Proposal B: 8.1 - one-line justification

One line per proposal. Score every proposal shown. Do not add any other \
text after the SCORES section."""
```

**Placement plumbing.** `placement='scope'` selects the prompt pair:
`_convene_inner` picks `(SCOPE_ADVISOR_PROMPT, SCOPE_JUDGE_PROMPT)` when
`placement == "scope"`, else the existing pair — one selection site, at
the top of `_convene_inner`, passed down to the gather helpers (add a
`system_prompt` parameter to each rather than letting them import the
constant). User-message assembly for scope, replacing the diff/checks
sections in BOTH the proposer and judge messages:

```
GOAL:
<goal>

DECLINE REASON:
<context["reason"]>

SELF-EDIT ALLOWLIST (deny always wins):
<context["allowlist"]>
```

**Trigger, in `run()`'s `session_decline` handling** (the block that
currently returns `declined=True` immediately). Before returning:

```python
scope_brief = None
if not self._scope_council_used:
    self._scope_council_used = True
    try:
        allowlist_text = (
            self.service.repo_root / "config" / "self_edit_allowlist.json"
        ).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — best-effort context
        allowlist_text = "(allowlist file unavailable)"
    scope_brief = self._maybe_scope_council(
        goal=goal, reason=reason, allowlist=allowlist_text)
if scope_brief:
    reason = (reason + "\n\n[Council scope advice]\n" + scope_brief)
return {"ok": False, "declined": True, "summary": reason,
        "status": self.service.status()}
```

with a new helper `_maybe_scope_council(self, *, goal, reason,
allowlist) -> str | None` shaped exactly like `_maybe_escalate` (lazy
imports, `asyncio.run`, catches everything, returns
`result.winner.content` or `None`) but calling `convene(
workflow="selfedit", placement="scope", trigger="E2", goal=goal, tier=1,
context={"reason": reason, "allowlist": allowlist})`.

**Rules:**
- `self._scope_council_used` initialised `False` in `__init__`, reset in
  `run()` — at most ONE scope council per run, by counter, not judgment.
- E2 does NOT touch `_escalations_used` — there is no retry loop to
  bound; the escalation ladder is for E1 only. Scope councils are always
  tier 1 (there is no "second failure" concept for a decline).
- The kill switch, size floor, logging, shadow sampling, and V4 shuffle
  all apply unchanged — a scope round is an ordinary round with a
  different prompt pair and placement string.
- Surfacing needs no UI work: the brief rides in `summary`, which the
  job polling already displays; V12's rounds list shows the round itself
  (`trigger='E2'`, `placement='scope'`).

### Signature ledger — final shapes after ALL v2 changes

Several decisions touch the same functions. This ledger is the single
source of truth for the end state; if a decision above seems to imply a
different shape, this table wins and the discrepancy should be reported
as a plan defect.

```python
# jarvis/council/council.py
async def _call_profile(profile, system_prompt, user_content,
                        timeout_s) -> tuple[str, dict | None]          # V9

def _proposer_user_message(goal: str, context: dict,
                           placement: str) -> str                       # V2/V14

def _judge_user_message(goal: str, context: dict,
                        proposals: list[Proposal],
                        placement: str) -> str                          # V2/V14

async def _gather_proposals(names, profiles_by_name, user_content,
                            system_prompt) -> tuple[list[Proposal], dict]
                                # V9 usage dict; V14 system_prompt;
                                # V4: returned Proposals have label=""

async def _gather_scores(judge_names, profiles_by_name,
                         judge_user_content, labels, *, shadow,
                         system_prompt) -> tuple[list[Score], dict]     # V9/V14

async def _shadow_pass(round_id, shadow_judge_names, profiles_by_name,
                       judge_user_content, labels, profile_tiers,
                       label_to_profile, payload_path) -> None          # V7

def _write_round_row(*, ..., prompt_tokens: int | None,
                     completion_tokens: int | None,
                     registry_order: list[str], ...) -> None            # V9/V13

def _write_payload(*, ..., live_scores: list[Score], ...) -> None
                                # V7: shadow_scores parameter REMOVED;
                                # V9: records carry "usage";
                                # V13: round_start carries "registry_order";
                                # V1: proposal records carry "carried"

# RoundResult (types.py): fields unchanged; `scores` now documented as
# live-only (V7). convene()'s public signature is UNCHANGED (v1 D1.1
# still binds it) — everything v2 needs rides in `context`.

# jarvis/council/config.py — new constants only:
COUNCIL_JUDGE_TARGET = 2                    # V8
COUNCIL_RETRY_EXTRA_ITERATIONS = 4          # V10
# council.py: COUNCIL_SHADOW_INLINE = False # V7

# jarvis/council/prune.py
def prune(retention_days: int, db_path=None, root=None) -> dict         # V11
    # returns {"rounds_deleted": n, "dirs_deleted": n}

# jarvis/agents/upgrade_agent.py — new members:
self._last_council_winner: tuple[str, str] | None                       # V1
self._scope_council_used: bool                                          # V14
def _maybe_scope_council(self, *, goal: str, reason: str,
                         allowlist: str) -> str | None                  # V14
```

---

## §4 Files

**New:**
- `jarvis/council/prune.py` (V11)
- `tests/unit/test_council_prune.py` (V11)

**Modified:**
- `jarvis/db.py` — migration `0010_council_v2`: `council_rounds` gains
  `prompt_tokens INTEGER`, `completion_tokens INTEGER` (V9),
  `registry_order TEXT` (V13); `run_id` schema comment rewrite (V12)
- `jarvis/council/council.py` — V1 carry consumption, V2 judge assembly,
  V4 shuffle + single labeling site, V7 `_shadow_pass` +
  `COUNCIL_SHADOW_INLINE` + `_last_shadow_thread`, V9 usage capture +
  round-row totals, V13 `registry_order` write, V14 prompt pair +
  placement selection + scope assembly
- `jarvis/council/config.py` — V8 `COUNCIL_JUDGE_TARGET` + backfill in
  `resolve_members`, V10 `COUNCIL_RETRY_EXTRA_ITERATIONS`
- `jarvis/council/scoring.py` — V6 regex
- `jarvis/council/agreement.py` — V13 stored-order preference + docstring
- `jarvis/council/__main__.py` — V2 replay context, V9 token line in
  `--agreement`, V13 stored-order preference in `_do_replay`
- `jarvis/agents/upgrade_agent.py` — V1 `_last_council_winner` +
  carry-forward context, V10 while-loop budget, V14
  `_scope_council_used` + `_maybe_scope_council` + decline-block change
- `jarvis/admin/server.py` — V5 `_council_job`/`_council_lock`, convene
  job thread, `GET /api/council/job`, reject restructure
- `jarvis/config.py` — V11 `jarvis_council_retention_days`
- `jarvis/bot/pipeline.py` — V11 prune call site
- `web/src/components/EditModePanel.tsx` — V5 polling, V12 rounds list
- `web/src/editmode.css` — V12 rounds-list styles (follow existing
  `.editmode-council-*` conventions)
- `.env.example` — V3 note, V11 variable
- `CLAUDE.md` — council section updated for V5 endpoints, V8 backfill,
  V12 run_id note, V14 E2 behaviour
- `MORTIMER_LLM_COUNCIL_PLAN.md` — header note: "V2 plan
  (`MORTIMER_LLM_COUNCIL_V2_PLAN.md`) supersedes D6.1's judge-assembly
  clause and completes D2's E2 row and D4's carry-forward"
- `tests/acceptance/llm-council.md` — new v2 section (checklist items
  for V1, V5, V12, V14 behaviours)
- Existing test files touched: `tests/unit/test_db.py` (0010),
  `tests/unit/test_council_scoring.py` (V6),
  `tests/unit/test_council_config.py` (V8),
  `tests/unit/test_council_agreement.py` (V13),
  `tests/unit/test_upgrade_agent.py` (V1, V10, V14),
  `tests/unit/test_admin_council.py` (V5),
  `tests/integration/test_council_escalation.py` (V1, V2, V4, V7),
  `tests/integration/test_council_cli.py` (V2, V9, V13)

---

## §5 Implementation order

1. Migration `0010_council_v2` + `test_db.py` update (all three columns,
   one migration — V9/V13; V12's comment rewrite rides along).
2. V6 strict regex + its scoring tests (pure, no dependents).
3. V4 shuffle + single labeling site + tests. **Before V1**, so the
   carried proposal never needs its own labeling logic.
4. V1 carry-forward (agent state + council consumption) + tests.
5. V2 judge assembly (council + replay) + tests.
6. V8 judge backfill + config tests.
7. V9 usage capture (transport, gathers, round row, JSONL, `--agreement`
   line) + tests.
8. V13 registry-order persistence + agreement/replay preference + tests.
9. V7 shadow detachment (`_shadow_pass`, knob, thread seam) + tests.
   After V9 so the shadow pass's usage-UPDATE lands on columns that
   exist; after V2 so it inherits the corrected judge message.
10. V10 iteration budget + tests.
11. V14 scope council (prompts, placement plumbing, agent trigger) +
    tests.
12. V11 retention (`prune.py`, config field, pipeline call site) + tests.
13. V5 sidecar job pattern + `test_admin_council.py` rewrite of the two
    affected endpoints' tests.
14. V12 UI rounds list + V5 UI polling (one `EditModePanel.tsx` pass),
    `npm run build` + `lint`.
15. Docs: `.env.example`, CLAUDE.md, v1 plan header note, acceptance
    checklist. V3's two documentation edits.

Steps 2–8 are backend-pure and each independently verifiable; 9–13
touch concurrency and process boundaries and come after the pure logic
is proven; UI last, docs after behaviour is final.

---

## §6 Verification

1. `pytest tests/unit tests/integration -q` — green (the pre-existing
   `test_mcp_web_server` live-network failure is a known sandbox
   artifact, not a gate).
2. `python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog,
   jarvis.council, jarvis.council.__main__, jarvis.council.prune"`.
3. `python scripts/init_db.py` on a fresh DB — `0010` applies; also
   apply `0010` over a DB created at `0009` (upgrade path).
4. `cd web && npm run build && npm run lint` — zero errors.
5. `tests/acceptance/llm-council.md` v2 section — manual.

**Required new/changed tests** (one regression test per closed gap,
minimum):

| V | Case | Expected |
|---|---|---|
| V1 | tier-2 convene with `carry_forward` in context | carried proposal appears with a label, counts in `proposer_count`, JSONL record has `carried: true` |
| V1 | carried profile also in judge tier | that profile excluded from judges |
| V1 | second escalation in `test_upgrade_agent.py` | tier-2 `convene` receives `context["carry_forward"]` with the tier-1 winner's content |
| V2 | judge message with diff+checks context | both sections present, in order, before proposals; no profile names anywhere |
| V2 | judge message with empty context | sections omitted, no placeholder text |
| V2 | `--replay` of a round whose JSONL has context | replay judge message includes it |
| V4 | same `round_id` twice | identical label assignment (deterministic) |
| V4 | two different `round_id`s over many trials | label orders differ for at least one (shuffle actually shuffles) |
| V4 | winner selection with shuffled labels | tiebreak still uses registry order, not label order |
| V6 | `7.44`, `8.`, `10.55` | abstention each, reason populated |
| V6 | `8`, `8.0`, `10.0`, `8 - fine` | still parse (regression guard) |
| V7 | `COUNCIL_SHADOW_INLINE=True` | existing shadow tests pass unchanged |
| V7 | `COUNCIL_SHADOW_INLINE=False` | `convene()` returns with zero shadow rows; after joining `_last_shadow_thread`, shadow rows exist and JSONL contains appended shadow records |
| V7 | shadow-never-affects-winner | re-asserted under the detached path |
| V8 | mid yields 1 judge, frontier available | judges = [mid, frontier], in that order |
| V8 | mid yields 2 judges | no backfill (frontier not consulted) |
| V8 | backfill candidate is in `exclude` | skipped |
| V8 | backfill exhausted below target | round still convenes (≥1 judge) |
| V9 | fake client returns usage | round row totals correct; JSONL records carry usage |
| V9 | provider omits usage | NULLs, never zeros |
| V9 | `--agreement` token line | present, sums only rounds with usage |
| V10 | no escalation | iteration cap unchanged (`client.calls == max_iterations` — existing test still green) |
| V10 | escalation succeeds | budget grows by exactly `COUNCIL_RETRY_EXTRA_ITERATIONS`, once per escalation |
| V11 | rounds older than cutoff | rows + score rows + date dirs deleted; newer untouched |
| V11 | `retention_days=0` | no-op, zeros returned |
| V13 | round with stored `registry_order` | agreement + replay use it |
| V13 | pre-v2 round (NULL) | falls back to approximation, no crash |
| V14 | `session_decline` fires | one scope council convenes (`trigger='E2'`, `placement='scope'`, tier 1); summary contains the brief; session still ends `declined=True` |
| V14 | scope council returns None | plain decline summary, unchanged from today |
| V14 | second decline same run | no second scope council (`_scope_council_used`) |
| V14 | scope round | `_escalations_used` untouched |
| V14 | kill switch off | no scope council, no rows |
| V5 | POST convene | returns immediately (`started: true`); polling reaches `done` with winner fields |
| V5 | second convene while running | refused |
| V5 | reject | revert result synchronous in response; council lands in the job |
| V5 | convene returns None | job settles `error`; `winner=None` round settles `done` with reason |

---

## §7 Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| V7's detached thread races the process exit (bot/sidecar shutdown mid-shadow) | Medium | Daemon thread + best-effort writes: a killed shadow pass loses only advisory rows, never live data; `council_shadow_failed` logging covers the observable half |
| V10's while-loop restructure breaks an untested `run()` path | Medium | The change is mechanical (counter for range); the existing iteration-bound test pins the no-escalation behaviour byte-for-byte |
| V5 job pattern diverges from `_run_job` semantics | Low | Same lock/dict/thread/poll shape, copied deliberately; tests mirror `test_admin_selfedit.py`'s |
| V14's allowlist-in-prompt grows the context (large deny lists) | Low | The allowlist file is small today; it is data already public to the agent; no truncation logic — if it ever grows pathological, that is a new decision, report it |
| V8 backfill quietly raises tier-1 cost | Low | Only fires when mid < 2 usable judges; `judge_tier` column makes the frontier judge's presence visible in every score row |
| V9 usage fields differ across providers | Medium | Only `prompt_tokens`/`completion_tokens` read, `None` on any shape mismatch — never a crash, never a fabricated number |
| V11 prunes shadowed rounds before the 20-round D8.2.4 threshold is reached | Low | 180-day default chosen for exactly this; the risk note lives in the config comment and `.env.example` where the knob would be turned |
| Migration 0010 applied to a live DB mid-write | Low | Additive `ALTER TABLE ... ADD COLUMN` only, idempotent via the migrations table, same as 0008 |

---

## §8 Rollback

`JARVIS_COUNCIL_ENABLED=false` still disables every council behaviour at
the single `convene()` enforcement point — including V14's scope council
and V5's job-backed convenes (the job settles `error`/`None`-equivalent
immediately). Migration `0010` is additive; nothing needs schema
rollback. Each V is independently revertible: V4/V6 are pure-function
changes guarded by tests; V7 reverts by setting `COUNCIL_SHADOW_INLINE =
True`; V10 reverts by setting `COUNCIL_RETRY_EXTRA_ITERATIONS = 0`; V11
by `jarvis_council_retention_days <= 0`. V5 is the only change that
alters an HTTP contract (`convene` response shape) — the UI and endpoint
change land in adjacent steps (13–14) and revert together.

---

## §9 Approval

**Implementation status (2026-08-16): implemented, §5 steps 1–15
complete, all required tests green** (821 passed, 3 skipped, 1 live-only
test deselected; `npm run build` and `npm run lint` clean). See §6's
verification table — every row exercised by the automated suite. §9's
three "to record on completion" items below remain open: they require
real usage data (an actual escalated session, an actual V8 backfill
firing, an actual scope-council decline) and cannot be recorded at
implementation time, same caveat as v1's outstanding `--agreement`
obligation.

- [ ] Larry has read §0–§3 and approves.
- [ ] Implementation may begin.

**To record on completion:** the V9 token totals for the first real
escalated session (this finally answers v1 §9's "observed cost per
escalated session" line); whether V8's backfill ever fired (visible as
frontier `judge_tier` rows on tier-1 rounds); and the first scope-council
brief produced by a real decline, verbatim. The v1 plan's outstanding
`--agreement` recording obligation (≥20 shadowed rounds) is unchanged
and carries forward.
