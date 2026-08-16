"""Unit tests for jarvis/council/agreement.py (D8.2.3 metrics, D8.2.4
decision rule). Pure, fixture-based — no DB, no network, built before any
real shadow data exists (MORTIMER_LLM_COUNCIL_PLAN.md §5 step 8 rationale).
"""

from __future__ import annotations

import json

from jarvis.council.agreement import _spearman, compute_agreement


def _score_row(
    round_id, judge_profile, judge_tier, proposal_label, proposal_profile,
    score, *, shadow=0, abstain_reason=None, justification="",
):
    return {
        "round_id": round_id, "judge_profile": judge_profile,
        "judge_tier": judge_tier, "shadow": shadow,
        "proposal_label": proposal_label, "proposal_profile": proposal_profile,
        "score": score, "abstain_reason": abstain_reason,
        "justification": justification,
    }


def _round_row(round_id, winner_label=None, retry_validated=None):
    return {"round_id": round_id, "winner_label": winner_label,
            "retry_validated": retry_validated}


# ------------------------------------------------------------- _spearman

def test_spearman_identical_orderings():
    assert _spearman([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_spearman_exactly_reversed():
    assert _spearman([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == -1.0


def test_spearman_constant_vector_is_none():
    assert _spearman([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None


def test_spearman_fewer_than_3_pairs_is_none():
    assert _spearman([1.0, 2.0], [2.0, 1.0]) is None


# ------------------------------------------------------- winner agreement

def _round_with_shadow(round_id, live_scores, shadow_scores):
    """live_scores/shadow_scores: {label: (profile, judge, score)}"""
    rows = []
    for label, (profile, judge, score) in live_scores.items():
        rows.append(_score_row(round_id, judge, "mid", label, profile, score, shadow=0))
    for label, (profile, judge, score) in shadow_scores.items():
        rows.append(_score_row(round_id, judge, "frontier", label, profile, score, shadow=1))
    return rows


def test_winner_agreement_identical_winners_is_1():
    score_rows = _round_with_shadow(
        "r1",
        {"Proposal A": ("kimi-k2", "kimi-k3", 9.0), "Proposal B": ("gpt-4.1-mini", "kimi-k3", 4.0)},
        {"Proposal A": ("kimi-k2", "claude-opus", 8.5), "Proposal B": ("gpt-4.1-mini", "claude-opus", 3.0)},
    )
    round_rows = [_round_row("r1", winner_label="Proposal A")]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.rounds_considered == 1
    assert report.winner_agreement == 1.0


def test_winner_agreement_all_winners_differ_is_0():
    score_rows = _round_with_shadow(
        "r1",
        {"Proposal A": ("kimi-k2", "kimi-k3", 9.0), "Proposal B": ("gpt-4.1-mini", "kimi-k3", 4.0)},
        {"Proposal A": ("kimi-k2", "claude-opus", 3.0), "Proposal B": ("gpt-4.1-mini", "claude-opus", 9.0)},
    )
    round_rows = [_round_row("r1", winner_label="Proposal A")]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.winner_agreement == 0.0


# --------------------------------------------------------- abstention/discrimination

def test_abstention_rate_splits_by_tier():
    score_rows = [
        _score_row("r1", "kimi-k3", "mid", "Proposal A", "kimi-k2", 7.0),
        _score_row("r1", "kimi-k3", "mid", "Proposal B", "gpt-4.1-mini", None, abstain_reason="x"),
        _score_row("r1", "claude-opus", "frontier", "Proposal A", "kimi-k2", 8.0, shadow=1),
        _score_row("r1", "claude-opus", "frontier", "Proposal B", "gpt-4.1-mini", 6.0, shadow=1),
    ]
    round_rows = [_round_row("r1")]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.abstention_rate_by_tier["mid"] == 0.5
    assert report.abstention_rate_by_tier["frontier"] == 0.0


def test_discrimination_all_same_score_is_zero_stdev():
    score_rows = [
        _score_row("r1", "kimi-k3", "mid", "Proposal A", "kimi-k2", 7.5),
        _score_row("r1", "kimi-k3", "mid", "Proposal B", "gpt-4.1-mini", 7.5),
        _score_row("r1", "kimi-k3", "mid", "Proposal C", "claude-opus", 7.5, shadow=0),
    ]
    round_rows = [_round_row("r1")]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.discrimination_by_tier["mid"] == 0.0


# ------------------------------------------------------------- decision rule

def _healthy_round(round_id):
    """A round where live and shadow agree perfectly, no abstentions,
    good discrimination."""
    return _round_with_shadow(
        round_id,
        {"Proposal A": ("kimi-k2", "kimi-k3", 9.0), "Proposal B": ("gpt-4.1-mini", "kimi-k3", 3.0)},
        {"Proposal A": ("kimi-k2", "claude-opus", 8.8), "Proposal B": ("gpt-4.1-mini", "claude-opus", 3.2)},
    ), _round_row(round_id, winner_label="Proposal A")


def test_agreement_19_rounds_is_insufficient_data():
    score_rows: list[dict] = []
    round_rows: list[dict] = []
    for i in range(19):
        rows, rrow = _healthy_round(f"r{i}")
        score_rows.extend(rows)
        round_rows.append(rrow)
    report = compute_agreement(score_rows, round_rows)
    assert report.rounds_considered == 19
    assert "insufficient data" in report.branch
    assert "19" in report.branch
    assert report.recommend_promote is False


def test_agreement_20_rounds_low_agreement_recommends_promote():
    score_rows: list[dict] = []
    round_rows: list[dict] = []
    # 13 agree, 7 disagree -> winner agreement ~0.65 < 0.70 floor.
    for i in range(13):
        rows, rrow = _healthy_round(f"agree-{i}")
        score_rows.extend(rows)
        round_rows.append(rrow)
    for i in range(7):
        rows = _round_with_shadow(
            f"disagree-{i}",
            {"Proposal A": ("kimi-k2", "kimi-k3", 9.0), "Proposal B": ("gpt-4.1-mini", "kimi-k3", 3.0)},
            {"Proposal A": ("kimi-k2", "claude-opus", 2.0), "Proposal B": ("gpt-4.1-mini", "claude-opus", 9.0)},
        )
        score_rows.extend(rows)
        round_rows.append(_round_row(f"disagree-{i}", winner_label="Proposal A"))
    report = compute_agreement(score_rows, round_rows)
    assert report.rounds_considered == 20
    assert report.winner_agreement == 13 / 20
    assert report.recommend_promote is True
    assert "promote" in report.branch


def test_agreement_20_rounds_all_healthy_recommends_keep_mid():
    score_rows: list[dict] = []
    round_rows: list[dict] = []
    for i in range(20):
        rows, rrow = _healthy_round(f"r{i}")
        score_rows.extend(rows)
        round_rows.append(rrow)
    report = compute_agreement(score_rows, round_rows)
    assert report.rounds_considered == 20
    assert report.winner_agreement == 1.0
    assert report.recommend_promote is False
    assert "keep" in report.branch.lower()


# --------------------------------------------------- V13: registry_order

def _tied_round_with_a_shadow_only_profile(round_id):
    """A perfect tie (mean/min/variance identical, all scores 7.0) where
    LIVE only ever saw two proposals (alpha, beta) and SHADOW saw a
    third (gamma) that live never proposed. The row-order approximation
    builds its registry_order purely from `live_proposals`, so gamma —
    absent from it — always sorts last (`order = len(registry_order)`)
    regardless of where it truly belongs; a profile that should win a
    tie can never win under the approximation. This is exactly the
    "not possible without a registry lookup" gap V13 closes: with a
    stored true order that ranks gamma first, the shadow side genuinely
    prefers gamma, which the approximation could never surface."""
    live_rows = [
        _score_row(round_id, "kimi-k3", "mid", "Proposal A", "alpha", 7.0, shadow=0),
        _score_row(round_id, "kimi-k3", "mid", "Proposal B", "beta", 7.0, shadow=0),
    ]
    shadow_rows = [
        _score_row(round_id, "claude-opus", "frontier", "Proposal A", "alpha", 7.0, shadow=1),
        _score_row(round_id, "claude-opus", "frontier", "Proposal B", "beta", 7.0, shadow=1),
        _score_row(round_id, "claude-opus", "frontier", "Proposal C", "gamma", 7.0, shadow=1),
    ]
    return live_rows + shadow_rows


def test_v13_no_stored_order_uses_legacy_approximation():
    score_rows = _tied_round_with_a_shadow_only_profile("r1")
    round_rows = [_round_row("r1")]  # no registry_order key at all — pre-v2 shape
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    # gamma is invisible to the approximation (built from live only) and
    # always sorts last, so it can never win the tie — live and shadow
    # both land on alpha, masking the fact that a real judge scored
    # gamma just as highly.
    assert report.winner_agreement == 1.0


def test_v13_stored_registry_order_reveals_the_true_shadow_preference():
    score_rows = _tied_round_with_a_shadow_only_profile("r1")
    round_rows = [
        {**_round_row("r1"), "registry_order": json.dumps(["gamma", "alpha", "beta"])},
    ]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    # With the true order, live (which never saw gamma) still ties
    # alpha/beta -> alpha; shadow now correctly resolves its tie to
    # gamma (earliest in the true order) — a real disagreement the
    # approximation was masking.
    assert report.winner_agreement == 0.0


def test_v13_null_registry_order_falls_back_without_crashing():
    score_rows = _tied_round_with_a_shadow_only_profile("r1")
    round_rows = [{**_round_row("r1"), "registry_order": None}]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.rounds_considered == 1  # ran to completion, no crash
    assert report.winner_agreement == 1.0  # same legacy behavior as absent-key


def test_v13_malformed_registry_order_falls_back_without_crashing():
    score_rows = _tied_round_with_a_shadow_only_profile("r1")
    round_rows = [{**_round_row("r1"), "registry_order": "not valid json"}]
    report = compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.rounds_considered == 1  # ran to completion, no crash
    assert report.winner_agreement == 1.0


def test_agreement_zero_rounds():
    report = compute_agreement([], [])
    assert report.rounds_considered == 0
    assert report.winner_agreement is None
    assert "insufficient data" in report.branch
