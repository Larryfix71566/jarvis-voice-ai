"""Unit tests for jarvis/council/scoring.py — the full §6 scoring test
table from MORTIMER_LLM_COUNCIL_PLAN.md, plus the D5 judge/proposer
disjointness backstop. Pure, no network."""

from __future__ import annotations

from jarvis.council.scoring import (
    council_size_ok,
    mean_of,
    parse_scores,
    select_winner,
)
from jarvis.council.types import Proposal, Score

REGISTRY_ORDER = ["kimi-k2", "gpt-4.1-mini", "kimi-k3", "claude-opus"]


def _proposals(*profiles: str) -> list[Proposal]:
    labels = [chr(ord("A") + i) for i in range(len(profiles))]
    return [
        Proposal(label=f"Proposal {lbl}", profile=prof, content=f"content {lbl}")
        for lbl, prof in zip(labels, profiles)
    ]


def _score(judge: str, label: str, value: float | None, **kw) -> Score:
    return Score(judge_profile=judge, proposal_label=label, value=value, **kw)


# ---------------------------------------------------------------- parsing

def test_clean_scores_from_all_judges_correct_mean_and_winner():
    proposals = _proposals("kimi-k2", "gpt-4.1-mini")
    raw_j1 = "SCORES:\nProposal A: 8.0 - solid\nProposal B: 6.0 - weaker\n"
    raw_j2 = "SCORES:\nProposal A: 7.0 - good\nProposal B: 5.0 - weak\n"
    scores = (
        parse_scores("kimi-k3", raw_j1, ["Proposal A", "Proposal B"])
        + parse_scores("claude-opus", raw_j2, ["Proposal A", "Proposal B"])
    )
    assert mean_of("Proposal A", scores) == 7.5
    assert mean_of("Proposal B", scores) == 5.5
    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    assert winner is not None and winner.label == "Proposal A"
    assert "highest mean" in reason


def test_score_10_5_and_0_5_invalid_not_clamped():
    raw = "SCORES:\nProposal A: 10.5 - great\nProposal B: 0.5 - bad\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A", "Proposal B"])
    by_label = {s.proposal_label: s for s in scores}
    assert by_label["Proposal A"].value is None
    assert by_label["Proposal A"].abstain_reason is not None
    assert by_label["Proposal B"].value is None
    assert by_label["Proposal B"].abstain_reason is not None


def test_integer_score_no_decimal_parses_as_float():
    raw = "SCORES:\nProposal A: 8 - fine\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A"])
    assert scores[0].value == 8.0


# --------------------------------------------------- V6: strict decimals

def test_v6_two_decimal_places_is_abstention_not_misread():
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V6 — "7.44" must not be silently
    misread as "7.4" with "4" leaking into the justification."""
    raw = "SCORES:\nProposal A: 7.44 - great\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A"])
    assert scores[0].value is None
    assert scores[0].abstain_reason is not None


def test_v6_trailing_bare_dot_is_abstention():
    raw = "SCORES:\nProposal A: 8. - fine\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A"])
    assert scores[0].value is None
    assert scores[0].abstain_reason is not None


def test_v6_out_of_range_two_decimals_is_abstention():
    raw = "SCORES:\nProposal A: 10.55 - great\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A"])
    assert scores[0].value is None
    assert scores[0].abstain_reason is not None


def test_v6_regression_valid_formats_still_parse():
    cases = {
        "Proposal A: 8\n": 8.0,
        "Proposal A: 8.0\n": 8.0,
        "Proposal A: 10.0\n": 10.0,
        "Proposal A: 8 - fine\n": 8.0,
        "Proposal A: 8.0 — fine\n": 8.0,
        "Proposal A: 7.4 - one-line justification\n": 7.4,
    }
    for raw, expected in cases.items():
        scores = parse_scores("kimi-k3", "SCORES:\n" + raw, ["Proposal A"])
        assert scores[0].value == expected, raw


def test_judge_returns_prose_with_no_scores_block_is_abstention():
    raw = "I think proposal A is better but I won't say why."
    scores = parse_scores("kimi-k3", raw, ["Proposal A", "Proposal B"])
    assert all(s.value is None for s in scores)
    assert all(s.abstain_reason for s in scores)


def test_judge_scores_2_of_3_one_abstention():
    raw = "SCORES:\nProposal A: 7.0 - ok\nProposal C: 6.0 - ok\n"
    scores = parse_scores(
        "kimi-k3", raw, ["Proposal A", "Proposal B", "Proposal C"]
    )
    by_label = {s.proposal_label: s for s in scores}
    assert by_label["Proposal A"].value == 7.0
    assert by_label["Proposal C"].value == 6.0
    assert by_label["Proposal B"].value is None
    assert by_label["Proposal B"].abstain_reason is not None


def test_unknown_label_ignored_real_labels_still_abstain():
    raw = "SCORES:\nProposal Z: 9.0 - not real\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A"])
    assert len(scores) == 1
    assert scores[0].proposal_label == "Proposal A"
    assert scores[0].value is None


def test_duplicate_label_first_occurrence_wins():
    raw = "SCORES:\nProposal A: 7.0 - first\nProposal A: 9.0 - second\n"
    scores = parse_scores("kimi-k3", raw, ["Proposal A"])
    assert len(scores) == 1
    assert scores[0].value == 7.0
    assert scores[0].justification == "first"


def test_parse_scores_always_returns_len_labels_items():
    cases = [
        "SCORES:\nProposal A: 7.0 - x\n",
        "no scores here at all",
        "",
        "SCORES:\nProposal Q: 9.0 - unknown label\n",
        "SCORES:\nProposal A: 99.9 - out of range\n",
    ]
    labels = ["Proposal A", "Proposal B", "Proposal C"]
    for raw in cases:
        scores = parse_scores("kimi-k3", raw, labels)
        assert len(scores) == len(labels)


# ------------------------------------------------------------- selection

def test_exact_tie_on_mean_broken_by_min_score():
    proposals = _proposals("kimi-k2", "gpt-4.1-mini")
    scores = [
        _score("kimi-k3", "Proposal A", 8.0),
        _score("claude-opus", "Proposal A", 6.0),   # mean 7.0, min 6.0
        _score("kimi-k3", "Proposal B", 7.5),
        _score("claude-opus", "Proposal B", 6.5),   # mean 7.0, min 6.5
    ]
    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    assert winner.label == "Proposal B"
    assert "minimum" in reason


def test_tie_on_mean_and_min_broken_by_variance():
    # Both proposals: mean 7.0, min 6.0 — differ only in variance.
    proposals = _proposals("kimi-k2", "gpt-4.1-mini")
    scores = [
        _score("j1", "Proposal A", 6.0),
        _score("j2", "Proposal A", 6.0),
        _score("j3", "Proposal A", 9.0),   # mean 7.0, min 6.0
        _score("j1", "Proposal B", 6.0),
        _score("j2", "Proposal B", 7.5),
        _score("j3", "Proposal B", 7.5),   # mean 7.0, min 6.0
    ]
    import statistics
    var_a = statistics.pvariance([6.0, 6.0, 9.0])
    var_b = statistics.pvariance([6.0, 7.5, 7.5])
    assert var_a != var_b  # sanity: the construction actually differs on variance

    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    expected_label = "Proposal A" if var_a < var_b else "Proposal B"
    assert winner.label == expected_label
    assert "variance" in reason


def test_tie_on_all_three_broken_by_registry_order_stable():
    proposals = _proposals("kimi-k3", "kimi-k2")  # kimi-k2 is earlier in REGISTRY_ORDER
    scores = [
        _score("j1", "Proposal A", 7.0),
        _score("j1", "Proposal B", 7.0),
    ]
    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    assert winner.label == "Proposal B"  # kimi-k2 is earlier in REGISTRY_ORDER
    assert "registry order" in reason
    # Stable across repeated calls with identical input.
    winner2, reason2 = select_winner(proposals, scores, REGISTRY_ORDER)
    assert winner2.label == winner.label
    assert reason2 == reason


def test_proposal_with_zero_valid_scores_ineligible():
    proposals = _proposals("kimi-k2", "gpt-4.1-mini")
    scores = [
        _score("j1", "Proposal A", 7.0),
        _score("j1", "Proposal B", None, abstain_reason="bad format"),
    ]
    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    assert winner.label == "Proposal A"


def test_all_proposals_unscored_round_fails():
    proposals = _proposals("kimi-k2", "gpt-4.1-mini")
    scores = [
        _score("j1", "Proposal A", None, abstain_reason="x"),
        _score("j1", "Proposal B", None, abstain_reason="x"),
    ]
    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    assert winner is None
    assert "no proposal" in reason


def test_judge_equals_proposer_scores_excluded_by_construction():
    proposals = _proposals("kimi-k2", "gpt-4.1-mini")
    scores = [
        # kimi-k2 both proposed AND is recorded as a judge here — its
        # score must never count (D5 backstop).
        _score("kimi-k2", "Proposal B", 9.0),
        _score("claude-opus", "Proposal A", 8.0),
    ]
    winner, reason = select_winner(proposals, scores, REGISTRY_ORDER)
    # Proposal B's only score came from its own proposer and must be
    # excluded, leaving it with zero valid scores.
    assert winner.label == "Proposal A"


def test_council_size_ok_one_proposer_refuses():
    assert council_size_ok(1, 1, min_proposers=2, min_judges=1) is False


def test_council_size_ok_meets_floor():
    assert council_size_ok(2, 1, min_proposers=2, min_judges=1) is True


def test_council_size_ok_zero_judges_refuses():
    assert council_size_ok(3, 0, min_proposers=2, min_judges=1) is False
