"""D8.2.3 — judge-tier validation metrics, D8.2.4's decision rule.

Pure: works entirely off already-extracted row dicts shaped like
council_rounds/council_scores columns (sqlite3.Row -> dict). No DB
connection, no network — jarvis/council/__main__.py (D8.2.2) is the only
caller that touches the database; it converts rows to plain dicts before
calling in here, and is where the DB reads and the CLI's `--replay`/
`--agreement` printing live.

MORTIMER_LLM_COUNCIL_V2_PLAN.md V13: `select_winner`'s D7 rule 4
(registry-order tiebreak) needs a fixed profile ordering. Migration
`0010`'s `council_rounds.registry_order` column (a JSON array, written by
`_write_round_row` from the live `registry_order` at convene() time) now
gives every v2 round its exact tiebreak order — read here, still without
a live registry lookup (this module's purity is unchanged: the order
comes from the already-fetched round row, not a fresh lookup).

Legacy fallback (pre-v2 rounds only, where the column is NULL): ties
broken purely by rule 4 use the order profiles happen to appear in the
round's rows. This only matters when a round is tied on mean AND min AND
variance — the rarest branch of an already-rare event — and only ever
nudges the *winner-agreement* denominator here, never the live selection
recorded in council_rounds (D7 already ran for real, with the true
registry order, at convene() time).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass

from jarvis.council.scoring import mean_of, select_winner
from jarvis.council.types import Proposal, Score

# ⚙ TUNING KNOB (D8.2.4) — provisional starting values, not calibrated.
# Do not hand-tune; see D8.2.4's "do not hand-tune" note.
COUNCIL_AGREEMENT_MIN_ROUNDS = 20
COUNCIL_AGREEMENT_FLOOR = 0.70
COUNCIL_ABSTENTION_CEILING = 0.15
COUNCIL_DISCRIMINATION_FLOOR = 0.5


@dataclass(frozen=True)
class AgreementReport:
    rounds_considered: int
    winner_agreement: float | None          # None iff rounds_considered == 0
    rank_correlation: float | None          # mean Spearman rho; None if no eligible rounds
    abstention_rate_by_tier: dict[str, float]
    discrimination_by_tier: dict[str, float]
    disagreement_cost: float | None         # None if no differing-winner round had a retry
    branch: str                             # D8.2.4's decision, human-readable
    recommend_promote: bool


def _spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation of two equal-length score vectors. Returns None
    if fewer than 3 pairs or if either vector is constant (undefined)."""
    if len(a) != len(b) or len(a) < 3:
        return None
    if len(set(a)) == 1 or len(set(b)) == 1:
        return None

    def _ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1  # 1-based, ties get the average rank
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    ra, rb = _ranks(a), _ranks(b)
    n = len(a)
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    return 1 - (6 * d2) / (n * (n * n - 1))


def _rows_for_round(score_rows: list[dict], round_id: str, *, shadow: bool) -> list[dict]:
    want = 1 if shadow else 0
    return [
        r for r in score_rows
        if r["round_id"] == round_id and int(r.get("shadow", 0) or 0) == want
    ]


def _to_proposals_and_scores(rows: list[dict]) -> tuple[list[Proposal], list[Score]]:
    labels_seen: dict[str, str] = {}
    for r in rows:
        labels_seen.setdefault(r["proposal_label"], r.get("proposal_profile") or "unknown")
    proposals = [
        Proposal(label=lbl, profile=prof, content="")
        for lbl, prof in labels_seen.items()
    ]
    scores = [
        Score(
            judge_profile=r["judge_profile"], proposal_label=r["proposal_label"],
            value=r.get("score"), justification=r.get("justification") or "",
            abstain_reason=r.get("abstain_reason"),
        )
        for r in rows
    ]
    return proposals, scores


def _abstention_rate_by_tier(score_rows: list[dict]) -> dict[str, float]:
    """% of (judge, proposal) pairs that abstained, split by judge_tier.
    Live and shadow rows are combined — the question is whether a TIER
    can produce parseable scores at all, not whether a given instance
    happened to be live or shadow."""
    by_tier: dict[str, list[dict]] = {}
    for r in score_rows:
        by_tier.setdefault(r.get("judge_tier") or "unknown", []).append(r)
    return {
        tier: sum(1 for r in rows if r.get("score") is None) / len(rows)
        for tier, rows in by_tier.items() if rows
    }


def _discrimination_by_tier(score_rows: list[dict]) -> dict[str, float]:
    """Mean, per judge_tier, of the stdev of one judge's valid scores
    within one round. A judge that scores everything the same has stdev
    0 and is not discriminating between proposals."""
    groups: dict[tuple[str, str, str], list[float]] = {}
    for r in score_rows:
        if r.get("score") is None:
            continue
        key = (r.get("judge_tier") or "unknown", r["round_id"], r["judge_profile"])
        groups.setdefault(key, []).append(r["score"])
    stdevs_by_tier: dict[str, list[float]] = {}
    for (tier, _round_id, _judge), values in groups.items():
        if len(values) < 2:
            continue
        stdevs_by_tier.setdefault(tier, []).append(statistics.pstdev(values))
    return {tier: statistics.fmean(vals) for tier, vals in stdevs_by_tier.items() if vals}


def _decide(
    rounds_considered: int, winner_agreement: float | None,
    mid_abstention: float | None, mid_discrimination: float | None,
    *, min_rounds: int, agreement_floor: float, abstention_ceiling: float,
    discrimination_floor: float,
) -> tuple[str, bool]:
    """D8.2.4's decision rule, fixed in advance. Returns (branch text,
    recommend_promote)."""
    if rounds_considered < min_rounds:
        return (
            f"insufficient data — {rounds_considered} shadowed rounds "
            f"(need >= {min_rounds}); keep mid-tier and keep collecting",
            False,
        )
    reasons: list[str] = []
    if winner_agreement is not None and winner_agreement < agreement_floor:
        reasons.append(f"winner agreement {winner_agreement:.2f} < {agreement_floor}")
    if mid_abstention is not None and mid_abstention > abstention_ceiling:
        reasons.append(f"mid-tier abstention rate {mid_abstention:.2f} > {abstention_ceiling}")
    if mid_discrimination is not None and mid_discrimination < discrimination_floor:
        reasons.append(
            f"mid-tier discrimination {mid_discrimination:.2f} < {discrimination_floor}"
        )
    if reasons:
        return "promote judges mid -> frontier: " + "; ".join(reasons), True
    return (
        f"keep judges at mid — {rounds_considered} shadowed rounds, all metrics healthy",
        False,
    )


def compute_agreement(
    score_rows: list[dict], round_rows: list[dict],
    *, min_rounds: int = COUNCIL_AGREEMENT_MIN_ROUNDS,
    agreement_floor: float = COUNCIL_AGREEMENT_FLOOR,
    abstention_ceiling: float = COUNCIL_ABSTENTION_CEILING,
    discrimination_floor: float = COUNCIL_DISCRIMINATION_FLOOR,
) -> AgreementReport:
    """The `--agreement` report (D8.2.3/D8.2.4). `score_rows` and
    `round_rows` are plain dicts shaped like council_scores/council_rounds
    columns — the caller (jarvis/council/__main__.py) is responsible for
    fetching them, this function never touches a database."""
    # MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — planning rounds are a human
    # choosing among candidates, never judge-quality evidence (draft_
    # candidates never calls select_winner). Filtered once, here, so every
    # metric below (agreement, abstention, discrimination) is automatically
    # excluded rather than needing its own guard. In practice a planning
    # round never has shadow=1 rows (draft_candidates never runs the
    # shadow pass — that lives inside _convene_inner only), so this is
    # belt-and-suspenders against a future caller writing shadow scores
    # for one.
    planning_round_ids = {r["round_id"] for r in round_rows if r.get("workflow") == "planning"}
    score_rows = [r for r in score_rows if r["round_id"] not in planning_round_ids]

    round_ids_with_shadow = sorted({
        r["round_id"] for r in score_rows if int(r.get("shadow", 0) or 0) == 1
    })
    retry_validated_by_round = {
        r["round_id"]: r.get("retry_validated") for r in round_rows
    }
    # V13 — prefer the stored registry order per round; None (pre-v2
    # rows) falls back to the legacy row-order approximation below.
    stored_registry_order_by_round: dict[str, list[str] | None] = {}
    for r in round_rows:
        raw = r.get("registry_order")
        if raw:
            try:
                stored_registry_order_by_round[r["round_id"]] = json.loads(raw)
                continue
            except (TypeError, ValueError):
                pass
        stored_registry_order_by_round[r["round_id"]] = None

    agree_count = 0
    rank_corrs: list[float] = []
    disagree_validated: list[bool] = []

    for round_id in round_ids_with_shadow:
        live_rows = _rows_for_round(score_rows, round_id, shadow=False)
        shadow_rows = _rows_for_round(score_rows, round_id, shadow=True)
        if not live_rows or not shadow_rows:
            continue
        live_proposals, live_scores = _to_proposals_and_scores(live_rows)
        shadow_proposals, shadow_scores = _to_proposals_and_scores(shadow_rows)
        # V13: prefer the stored order; pre-v2 rounds (None) fall back
        # to the legacy row-order approximation (see module docstring).
        registry_order = stored_registry_order_by_round.get(round_id)
        if registry_order is None:
            registry_order = [p.profile for p in live_proposals]

        live_winner, _ = select_winner(live_proposals, live_scores, registry_order)
        shadow_winner, _ = select_winner(shadow_proposals, shadow_scores, registry_order)
        live_label = live_winner.label if live_winner else None
        shadow_label = shadow_winner.label if shadow_winner else None

        if live_label is not None and live_label == shadow_label:
            agree_count += 1
        elif live_label is not None and shadow_label is not None:
            rv = retry_validated_by_round.get(round_id)
            if rv is not None:
                disagree_validated.append(bool(rv))

        common_labels = sorted(
            {p.label for p in live_proposals} & {p.label for p in shadow_proposals}
        )
        if len(common_labels) >= 3:
            live_means = [mean_of(lbl, live_scores) for lbl in common_labels]
            shadow_means = [mean_of(lbl, shadow_scores) for lbl in common_labels]
            if all(v is not None for v in live_means) and all(v is not None for v in shadow_means):
                rho = _spearman(live_means, shadow_means)  # type: ignore[arg-type]
                if rho is not None:
                    rank_corrs.append(rho)

    rounds_considered = len(round_ids_with_shadow)
    winner_agreement = (agree_count / rounds_considered) if rounds_considered else None
    rank_correlation = statistics.fmean(rank_corrs) if rank_corrs else None
    disagreement_cost = (
        sum(1 for v in disagree_validated if v) / len(disagree_validated)
        if disagree_validated else None
    )

    abstention_rate_by_tier = _abstention_rate_by_tier(score_rows)
    discrimination_by_tier = _discrimination_by_tier(score_rows)

    branch, recommend_promote = _decide(
        rounds_considered, winner_agreement,
        abstention_rate_by_tier.get("mid"), discrimination_by_tier.get("mid"),
        min_rounds=min_rounds, agreement_floor=agreement_floor,
        abstention_ceiling=abstention_ceiling, discrimination_floor=discrimination_floor,
    )

    return AgreementReport(
        rounds_considered=rounds_considered, winner_agreement=winner_agreement,
        rank_correlation=rank_correlation,
        abstention_rate_by_tier=abstention_rate_by_tier,
        discrimination_by_tier=discrimination_by_tier,
        disagreement_cost=disagreement_cost, branch=branch,
        recommend_promote=recommend_promote,
    )
