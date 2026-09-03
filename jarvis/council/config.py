"""D4 tier ladder + D8.2.1 shadow-judging knobs + D12 tuning knobs.

Membership resolution: which registry profiles participate in a given
escalation tier and role, applying D4's ladder, D9's optional UI-narrowed
selection, and D4's "degenerate tier" fallback.

Wire-format note (closes a gap between D9 and D10): D9 says the backend
"enforces [the minimum member count] again," which only means something if
the UI's per-tier selection actually reaches the backend. D10's endpoint
table lists `POST /api/council/convene` with body `{placement, goal?}` —
terse, not exhaustive. `resolve_members` below accepts an optional
`selected` mapping (tier name -> list of profile names), passed through
from that endpoint's optional `members` field (jarvis/admin/server.py),
matching the `mortimer.council.<tier>` localStorage shape the picker
already uses (D9). This is the minimal completion of a wire format two
decisions already name; it invents no new selection semantics.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from jarvis.agents.upgrade_agent import available_models

# ⚙ TUNING KNOB (D12)
COUNCIL_MAX_ESCALATIONS = 2
COUNCIL_MIN_PROPOSERS = 2
COUNCIL_MIN_JUDGES = 1

# ⚙ TUNING KNOB — MORTIMER_LLM_COUNCIL_V2_PLAN.md V8 (resolved with Larry,
# 2026-08-16). Target judge-pool size. When a tier's judge resolution
# yields fewer than this, backfill from tiers ABOVE the role's highest
# tier name in _TIER_ORDER (never below: judges are never cheaper than
# the tier the ladder assigned). Distinct from COUNCIL_MIN_JUDGES (=1),
# which remains the hard floor for convening at all.
COUNCIL_JUDGE_TARGET = 2

# ⚙ TUNING KNOB — MORTIMER_LLM_COUNCIL_V2_PLAN.md V10. Extra loop
# iterations granted per successful escalation, so a council-guided
# retry cannot be starved by budget the failed attempts already spent.
# Bounded: at most COUNCIL_MAX_ESCALATIONS grants per session (i.e. +8
# with the defaults). The wall-clock bound (max_session_minutes) is
# deliberately NOT extended — it is the outer safety net and stays
# absolute.
COUNCIL_RETRY_EXTRA_ITERATIONS = 4

# ⚙ TUNING KNOB — MORTIMER_PLANNING_PATHWAY_PLAN.md P7. Per-member-call
# timeout for the planning pathway (single-mode and council-parallel
# draft_candidates alike): a full implementation-plan document takes
# longer to write than a corrective brief, so this is deliberately looser
# than COUNCIL_MEMBER_TIMEOUT_S (120s, jarvis/council/council.py) — a plan
# is a document, not a brief.
PLANNING_MEMBER_TIMEOUT_S = 300.0

# ⚙ TUNING KNOB — MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R3. The sidecar
# truncates a review document to this many characters BEFORE building the
# council context, so a reviewer never receives an unbounded document; the
# truncation suffix instructs the reviewer to flag it in its verdict.
PLAN_REVIEW_DOC_MAX_CHARS = 60_000

# ⚙ TUNING KNOB (D8.2.1) — fraction of rounds that also get a shadow judge
# pass. 0.0 disables shadow judging entirely. 1.0 shadows every round.
COUNCIL_SHADOW_RATE = 0.25

# Which tier shadows which. A tier absent from this map is never shadowed.
COUNCIL_SHADOW_TIERS: dict[int, str] = {1: "frontier"}

# ⚙ TUNING KNOB (D8.2.4) — judge-tier promotion decision. Provisional
# starting values, not calibrated; see D8.2.4 for the full rule and the
# "do not hand-tune" note.
COUNCIL_AGREEMENT_MIN_ROUNDS = 20
COUNCIL_AGREEMENT_FLOOR = 0.70
COUNCIL_ABSTENTION_CEILING = 0.15
COUNCIL_DISCRIMINATION_FLOOR = 0.5

# D4 — the tier ladder. tier = escalations_used + 1, computed in exactly
# one place: UpgradeAgent._maybe_escalate (D2.1) — EXCEPT for
# placement="planner" escalations specifically, which add
# COUNCIL_PLANNER_START_TIER instead of 1 (see below). No other code
# derives a tier; this module only resolves what a given tier NUMBER
# means.
#
# Deviation from the plan's original D4 table, resolved with Larry
# 2026-08-16: the plan as written had tier 2 judges = "mid", but tier 2
# proposers = "frontier" + "mid" — the mid tier appeared in both pools,
# which contradicts D5's disjoint-proposer/judge invariant (today's
# registry has exactly one mid profile, so tier 2 would have zero usable
# judges whenever it proposed). Resolution: tier 2 judges = "frontier"
# only. Disjointness is additionally enforced per-member, not just per
# tier name — see `exclude` below — so this holds even if a tier name is
# ever expanded to overlap again.
TIER_MEMBERS: dict[int, dict[str, list[str]]] = {
    1: {"proposers": ["economy"], "judges": ["mid"]},
    2: {"proposers": ["frontier", "mid"], "judges": ["frontier"]},
}

# ⚙ TUNING KNOB — MORTIMER_OPTIMIZATION_PLAN.md Phase 3. UpgradeAgent
# ._maybe_escalate's placement="planner" round (E1: a self-edit's own
# validation failed twice, asking a council for help) starts its FIRST
# escalation at this tier instead of tier 1 — i.e.
# tier = escalations_used + COUNCIL_PLANNER_START_TIER, for that one call
# site only. placement="scope" (_maybe_scope_council, E2) is untouched:
# it always convenes at tier 1, deliberately, per V14.
#
# Consequence, stated directly because it is easy to miss: with
# COUNCIL_MAX_ESCALATIONS=2 and TIER_MEMBERS only defining tiers 1-2, a
# SECOND placement="planner" escalation in the same session computes
# tier=3, which does not exist — resolve_members() raises, caught by
# _maybe_escalate's broad except, and the session ends exactly as it does
# when the council is unavailable. Starting at the top of the ladder
# therefore caps this escalation to ONE real attempt per session, not
# two. That is the intended trade (Larry 2026-09-01, Phase 3 design): a
# frontier council that already failed once is not fixed by reconvening
# the same frontier council; the second failure should end in a human
# re-plan, not a second identical round. If usage data says otherwise,
# this is a one-constant change (extend TIER_MEMBERS with a tier 3, or
# lower this back to 1).
COUNCIL_PLANNER_START_TIER = 2

# ⚙ TUNING KNOB — MORTIMER_OPTIMIZATION_PLAN.md Phase 3. jarvis.council.
# council.draft_candidates' default proposer set (used only when the
# caller passes no explicit `members`) is narrowed to profiles whose
# registry `tier:` is in this list. Before this, the default was the
# FULL key-present registry (Larry 2026-08-17, "the user is paying
# deliberate attention here" — true for the planning pathway's own
# human-reviewed record_user_choice flow, but the voice `plan_start`
# path never passes `members` either, so every SPOKEN plan request was
# buying a full-registry fan-out — 13 drafts, per the optimization
# audit). An explicit `members["proposers"]` selection (the console
# picker, or any future caller) is NOT restricted by this list — it can
# still widen past frontier to the full registry, exactly as before;
# only the no-selection DEFAULT narrows.
PLANNING_DEFAULT_PROPOSER_TIERS: list[str] = ["frontier"]

# ⚙ TUNING KNOB — MORTIMER_OPTIMIZATION_PLAN.md Phase 3, Rev 3.3 (2026-09-03).
# draft_candidates' default JUDGE set (no explicit `members["judges"]`) is
# capped at this many profiles. Before this the default judge pool was
# "every key-present profile not proposing", uncapped — harmless while the
# default proposer set was the whole registry (nobody was left to judge),
# but the Phase 3 narrowing to frontier-only proposers silently turned the
# ~10 remaining profiles into ~10 judge calls per spoken plan request, each
# carrying every frontier draft as input: MORE planning-rung spend, not
# less, for scores that are advisory-only in this pathway (the user picks
# the winner via record_user_choice). Two is COUNCIL_JUDGE_TARGET's value on
# purpose ("a second opinion, not a panel"), kept as its own constant so
# the planning pathway can diverge from the escalation ladder without
# touching V8. An explicit members["judges"] selection is NOT capped.
PLANNING_DEFAULT_JUDGE_LIMIT = 2

# Which tiers that capped default draws from, in preference order. Mid-tier
# judges scoring frontier drafts is the plan's own "third-lineage judge via
# the V8 backfill (or-gpt-5.1, mid)" shape; a frontier profile that is not
# proposing is the next best; economy last — a flash model scoring fable/
# deepseek drafts is mostly noise, but still better than no advisory score
# when that is all that has a key. Within a tier, registry order. Profiles
# with no `tier:` never judge by default (they never propose by default
# either, per PLANNING_DEFAULT_PROPOSER_TIERS).
PLANNING_DEFAULT_JUDGE_TIERS: list[str] = ["mid", "frontier", "economy"]

# Ascending cost, used only by the degenerate-tier fallback below.
_TIER_ORDER = ["economy", "mid", "frontier"]

# --- Tier-2 frontier partition (Larry 2026-08-19, option b) ------------
#
# THE BUG THIS FIXES. Tier 2 lists "frontier" for BOTH roles: proposers
# ["frontier", "mid"], judges ["frontier"]. Proposers therefore take every
# frontier profile, and per-member disjointness (`exclude`) then removes
# every one of them from the judge pool. _fallback_up cannot rescue it —
# frontier is the top of _TIER_ORDER, so there is nowhere above to climb.
# resolve_members raised NoUsableProfilesError and convene() turned that
# into _finalize_too_small, meaning a SECOND escalation silently declined
# to convene the very council it exists to convene. Measured 2026-08-19:
# tier 1 resolved 4 proposers and 4 judges; tier 2 resolved 9 proposers
# and then failed. This was latent from the start — the pre-OpenRouter
# registry (2 frontier, 1 mid) produced the identical zero — and it went
# unseen because tier 2 needs two validation failures plus a failed repair
# to fire at all.
#
# THE FIX. At a partitioned tier, the named tier's usable membership is
# SPLIT between the two roles instead of being offered whole to both:
# judges are reserved first, and whatever remains proposes (alongside the
# other proposer tier names, which are untouched). Disjointness then holds
# by construction rather than by exclusion-after-the-fact, which is what
# made the pools collide in the first place.
#
# Judges are reserved rather than proposers because a round with no judges
# cannot happen at all, while a round with fewer proposers merely has less
# to choose from. Reserve COUNCIL_JUDGE_TARGET, but never so many that no
# frontier profile is left to propose — tier 2's whole purpose is frontier
# PROPOSALS, and a partition that reserved all of them would fix the crash
# by defeating the tier.
TIER_PARTITION: dict[int, str] = {2: "frontier"}


def _partition_judges(names: list[str], seed: str | None = None) -> list[str]:
    """Which of a partitioned tier's usable profiles are reserved as judges.

    Deterministic, and seeded per round rather than fixed, reusing V4's
    approach exactly (SHA256 of the round id into a LOCAL random.Random,
    never the global module) — one idea applied twice, not two that can
    drift. A fixed split would make the same two models the permanent
    arbiters of every tier-2 winner, which is a systematic taste bias the
    council exists to avoid; rotating per round spreads it while keeping
    any single round reproducible for --replay.

    Falls back to registry order when no seed is supplied, so callers that
    do not have a round id (tests, --agreement) still get a stable answer.
    """
    if len(names) < 2:
        return list(names)
    reserved = min(COUNCIL_JUDGE_TARGET, len(names) - 1)
    ordered = list(names)
    if seed is not None:
        rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())
        rng.shuffle(ordered)
    return sorted(ordered[:reserved])


def tier_members(tier: int) -> dict[str, list[str]]:
    """Tier -> {'proposers': [tier names], 'judges': [tier names]}.
    Raises KeyError for an undefined tier — loud, never a silent fallback
    to a cheaper or more expensive council than intended."""
    return TIER_MEMBERS[tier]


class NoUsableProfilesError(RuntimeError):
    """Raised when a role has no usable profile at any tier reachable by
    the D4 fallback. Caller (council.py) must catch this and treat it the
    same as any other convene() failure — return None (D13)."""


def _profiles_for_tier_name(
    tier_name: str, registry_path: str | None = None
) -> list[dict[str, Any]]:
    """Registry profiles whose config `tier:` field equals `tier_name`, in
    registry order."""
    return [
        m for m in available_models(registry_path)
        if m.get("tier") == tier_name
    ]


def _usable_profiles_for_tier_name(
    tier_name: str, *, registry_path: str | None,
    selected: dict[str, list[str]] | None,
    exclude: set[str] | None = None,
) -> list[str]:
    """D9's picker rules applied to one tier name: narrow to the UI
    selection if one was given (empty/absent selection falls back to the
    tier's full registry membership), drop any profile whose API key is
    not present (a missing key must never silently shrink a council,
    §0.1.5 — it is filtered here so the caller can still fall back to the
    next tier up), and drop anything in `exclude` (D5's per-member
    disjointness enforcement: a name already used as a proposer in this
    round is never eligible to judge in it, even if its tier name is
    also a judge tier name)."""
    profiles = _profiles_for_tier_name(tier_name, registry_path)
    picked = (selected or {}).get(tier_name) or []
    if picked:
        profiles = [p for p in profiles if p["name"] in picked]
    exclude = exclude or set()
    return [
        p["name"] for p in profiles
        if p["key_present"] and p["name"] not in exclude
    ]


def _fallback_up(
    tier_name: str, *, registry_path: str | None,
    selected: dict[str, list[str]] | None,
    exclude: set[str] | None = None,
) -> list[str]:
    """D4's degenerate-tier rule: climb _TIER_ORDER from `tier_name`
    (exclusive) until a tier name with at least one usable profile is
    found. Returns [] if none exists. Also the mechanism that rescues a
    tier name emptied out by `exclude` (D5 disjointness), not just one
    emptied by a missing key — both are "no usable profile at this tier
    name," so both use the same fallback."""
    if tier_name not in _TIER_ORDER:
        return []
    for candidate in _TIER_ORDER[_TIER_ORDER.index(tier_name) + 1:]:
        names = _usable_profiles_for_tier_name(
            candidate, registry_path=registry_path, selected=selected,
            exclude=exclude,
        )
        if names:
            return names
    return []


def resolve_members(
    tier: int,
    role: str,
    *,
    registry_path: str | None = None,
    selected: dict[str, list[str]] | None = None,
    exclude: set[str] | None = None,
    seed: str | None = None,
) -> list[str]:
    """Resolve the actual profile names for one role ('proposers' |
    'judges') at one escalation tier. Never returns a duplicate name.

    `exclude` (D5): names that may never appear in the result even if
    otherwise eligible — council.py passes the already-resolved proposer
    set when resolving judges, so a model that proposed in this round can
    never also judge it, regardless of whether the tier ladder's tier
    NAMES happen to overlap for this tier number.

    `seed` (2026-08-19): the round id, used only to rotate TIER_PARTITION's
    judge reservation. Both roles of one round MUST be resolved with the
    same seed or the partition they agree on differs between the two calls
    and the split stops being a split. council.py passes round_id to both.

    Raises NoUsableProfilesError if, after D4's degenerate-tier fallback,
    no profile at all is usable for this role. Never convenes a council
    with zero candidates for a role silently (D7's size floor still runs
    on top of this in council.py)."""
    tier_names = tier_members(tier)[role]

    # TIER_PARTITION — split a tier that both roles claim, BEFORE anything
    # else looks at it. Done as an addition to `exclude` rather than as a
    # filter on the result so that _fallback_up and V8's backfill both see
    # a pool that is already correctly restricted; filtering afterwards
    # would let the fallback re-admit a profile the partition just gave to
    # the other role.
    part_tier = TIER_PARTITION.get(tier)
    if part_tier is not None:
        # The partition basis is the tier's FULL usable membership, so
        # `exclude` is deliberately not passed here. It is passed on the
        # judges call (council.py hands over the resolved proposer set), and
        # letting it shrink the basis would make _partition_judges reserve
        # from an already-halved pool: measured 2026-08-19, 5 frontier
        # profiles yielded 3 proposers and then only ONE judge, because the
        # judges call saw a pool of 2 and reserved min(2, 2-1) = 1. The
        # split must be computed identically for both roles or it is not a
        # split. `selected` and key-presence still apply — those narrow what
        # is genuinely available, rather than describing the other role.
        pool = _usable_profiles_for_tier_name(
            part_tier, registry_path=registry_path, selected=selected,
        )
        reserved = set(_partition_judges(pool, seed))
        other = set(pool) - reserved
        # judges get the reservation, proposers get the remainder.
        exclude = (exclude or set()) | (other if role == "judges" else reserved)

    out: list[str] = []
    seen: set[str] = set()
    for tier_name in tier_names:
        names = _usable_profiles_for_tier_name(
            tier_name, registry_path=registry_path, selected=selected,
            exclude=exclude,
        )
        if not names:
            names = _fallback_up(
                tier_name, registry_path=registry_path, selected=selected,
                exclude=exclude,
            )
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V8 — judge-pool backfill. Judges
    # only: a thin judge pool (today, tier 1's single mid profile) makes
    # one abstention fail the round and leaves the min/variance
    # tiebreaks inert with n=1. Walk _TIER_ORDER strictly above the
    # highest tier name this role actually resolved from, and top up
    # with usable profiles (same `selected`/`exclude` rules) until
    # COUNCIL_JUDGE_TARGET is reached or the ladder runs out. Exhaustion
    # below the target is NOT an error — the round convenes with what
    # exists; only zero usable judges (checked below, unchanged) raises.
    if role == "judges" and len(out) < COUNCIL_JUDGE_TARGET:
        known = [t for t in tier_names if t in _TIER_ORDER]
        if known:
            highest_idx = max(_TIER_ORDER.index(t) for t in known)
            for candidate in _TIER_ORDER[highest_idx + 1:]:
                if len(out) >= COUNCIL_JUDGE_TARGET:
                    break
                names = _usable_profiles_for_tier_name(
                    candidate, registry_path=registry_path, selected=selected,
                    exclude=exclude,
                )
                for n in names:
                    if len(out) >= COUNCIL_JUDGE_TARGET:
                        break
                    if n not in seen:
                        seen.add(n)
                        out.append(n)

    if not out:
        raise NoUsableProfilesError(
            f"no usable profile for role={role!r} at tier={tier}"
        )
    return out


def resolve_tier_name_members(
    tier_name: str,
    *,
    registry_path: str | None = None,
    selected: dict[str, list[str]] | None = None,
    exclude: set[str] | None = None,
) -> list[str]:
    """D8.2.1 — usable profiles for one raw tier NAME (economy/mid/
    frontier), independent of the escalation ladder. Used for shadow
    judging, where the shadow tier is looked up directly (D8.2.1's
    `COUNCIL_SHADOW_TIERS`), not via `tier_members()`'s tier-NUMBER
    mapping. Unlike `resolve_members`, this never raises and never
    climbs the degenerate-tier fallback — D8.2.1 says a shadow judge
    failure (including "nobody usable") is non-fatal and simply skips
    shadowing that round; returns [] rather than
    NoUsableProfilesError."""
    return _usable_profiles_for_tier_name(
        tier_name, registry_path=registry_path, selected=selected, exclude=exclude,
    )


def should_shadow(round_id: str, tier: int) -> bool:
    """Deterministic sampling (D8.2.1): hash the round_id, compare to the
    rate. Same round_id always yields the same answer, so behaviour is
    reproducible and testable without monkeypatching random()."""
    if tier not in COUNCIL_SHADOW_TIERS or COUNCIL_SHADOW_RATE <= 0.0:
        return False
    if COUNCIL_SHADOW_RATE >= 1.0:
        return True
    digest = hashlib.sha256(round_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return bucket < COUNCIL_SHADOW_RATE


def shadow_tier_name(tier: int) -> str | None:
    """Which tier NAME (economy/mid/frontier) shadows the given escalation
    tier, or None if that tier is never shadowed (D8.2.1)."""
    return COUNCIL_SHADOW_TIERS.get(tier)
