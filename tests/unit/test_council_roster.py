"""Unit tests for jarvis/council/council.py's roster assembly
(MORTIMER_OPTIMIZATION_PLAN.md "Interface Task — Council Roster on the
Agent Card"). Pure: `build_roster` does no I/O, so these tests hand it
rows rather than a database.

The primary fixture is NOT invented. It is round e48cfbe1's real shape,
read out of Larry's data/jarvis.db on 2026-09-03: four proposers, four
mid-tier judges, and `kimi-k3` abstaining on every single proposal with
`judge call failed: ` — the exact silent pool degradation the Interface
Task exists to surface. A hand-tuned fixture could not have told us the
abstain_reason arrives with an empty error string after the colon, which
is what makes the reason worth printing on the card at all.
"""

from __future__ import annotations

import pytest

from jarvis.council.council import build_roster

STARTED = "2026-09-01T02:17:21.374092+00:00"

# The real round's council_rounds row (columns build_roster reads).
REAL_ROUND = {
    "round_id": "e48cfbe1060b4e009087a3ca2ea2d64b",
    "run_id": None,
    "workflow": "selfedit",
    "placement": "planner",
    "trigger": "E1",
    "tier": 1,
    "goal": "pytest: timed out after 300s",
    "proposer_count": 4,
    "proposers_attempted": 4,
    "judge_count": 4,
    "judges_attempted": 4,
    "abstentions": 4,
    "winner_profile": "or-gemini-flash",
    "winner_label": "Proposal A",
    "winner_mean": 7.433333333333334,
    "select_reason": "highest mean score (7.4)",
    "status": "ok",
    "started_at": STARTED,
    "ended_at": "2026-09-01T02:21:00.594092+00:00",
    "latency_ms": 219220,
    "prompt_tokens": 37433,
    "completion_tokens": 14273,
}

_PROPOSALS = [
    ("Proposal A", "or-gemini-flash"),
    ("Proposal B", "or-deepseek"),
    ("Proposal C", "or-gpt-5-mini"),
    ("Proposal D", "kimi-k2"),
]
# judge -> its four scores, in _PROPOSALS order. None == abstained.
_REAL_SCORES = {
    "kimi-k3": [None, None, None, None],
    "or-gpt-5.1": [6.8, 8.7, 7.4, 5.9],
    "or-sonnet-5": [7.0, 4.0, 4.8, 8.7],
    "or-grok-4.3": [8.5, 2.5, 9.0, 4.0],
}


def _score_row(judge, label, profile, value, *, shadow=0, reason=None, tier="mid"):
    return {
        "round_id": REAL_ROUND["round_id"],
        "judge_profile": judge,
        "judge_tier": tier,
        "shadow": shadow,
        "proposal_label": label,
        "proposal_profile": profile,
        "score": value,
        "abstain_reason": reason,
        "justification": "",
        "created_at": STARTED,
    }


def real_scores() -> list[dict]:
    rows = []
    for judge, values in _REAL_SCORES.items():
        for (label, profile), value in zip(_PROPOSALS, values):
            rows.append(_score_row(
                judge, label, profile, value,
                reason="judge call failed: " if value is None else None,
            ))
    return rows


# --------------------------------------------------------- the real round


def test_the_real_round_reports_the_dead_judge_as_degradation():
    """The whole point of the card: kimi-k3 failed on all four proposals
    on 2026-09-01 and nothing surfaced it. The roster must say so, and
    must carry the reason text, not just a count."""
    roster = build_roster(REAL_ROUND, real_scores())

    assert roster["degraded"] is True
    dead = [r for r in roster["degraded_reasons"] if "kimi-k3" in r]
    assert len(dead) == 1
    assert "abstained on every proposal" in dead[0]
    assert "judge call failed:" in dead[0]

    k3 = next(j for j in roster["judges"] if j["profile"] == "kimi-k3")
    assert k3["all_abstained"] is True
    assert k3["scored"] == 0 and k3["abstained"] == 4
    assert k3["abstain_reasons"] == ["judge call failed:"]


def test_a_healthy_judge_is_not_flagged():
    roster = build_roster(REAL_ROUND, real_scores())
    healthy = next(j for j in roster["judges"] if j["profile"] == "or-grok-4.3")
    assert healthy["all_abstained"] is False
    assert healthy["scored"] == 4 and healthy["abstained"] == 0
    assert healthy["abstain_reasons"] == []
    assert not any("or-grok-4.3" in r for r in roster["degraded_reasons"])


def test_means_match_the_winner_the_round_actually_selected():
    """The roster's mean must be the mean that chose the winner — if this
    drifts, the card contradicts the chip above it."""
    roster = build_roster(REAL_ROUND, real_scores())
    winner = next(p for p in roster["proposers"] if p["is_winner"])
    assert winner["profile"] == "or-gemini-flash"
    assert winner["mean"] == pytest.approx(REAL_ROUND["winner_mean"])
    assert sum(1 for p in roster["proposers"] if p["is_winner"]) == 1


def test_proposers_are_ranked_best_first():
    roster = build_roster(REAL_ROUND, real_scores())
    assert [p["profile"] for p in roster["proposers"]] == [
        "or-gemini-flash",   # 7.43
        "or-gpt-5-mini",     # 7.07
        "kimi-k2",           # 6.20
        "or-deepseek",       # 5.07
    ]
    assert [p["mean"] for p in roster["proposers"]] == sorted(
        [p["mean"] for p in roster["proposers"]], reverse=True
    )


def test_every_proposer_records_who_scored_and_who_abstained():
    roster = build_roster(REAL_ROUND, real_scores())
    for proposer in roster["proposers"]:
        # three live judges scored, kimi-k3 abstained, on every proposal
        assert proposer["scored_by"] == 3
        assert proposer["abstained_by"] == 1


def test_round_level_facts_are_passed_through_for_the_chip():
    roster = build_roster(REAL_ROUND, real_scores())
    assert roster["round_id"] == REAL_ROUND["round_id"]
    assert roster["winner_profile"] == "or-gemini-flash"
    assert roster["placement"] == "planner"
    assert roster["tier"] == 1
    assert roster["latency_ms"] == 219220
    assert roster["abstentions"] == 4
    assert roster["tokens"] == {
        "prompt": 37433, "completion": 14273, "total": 51706,
    }


# ------------------------------------------------------------- shadow pass


def test_shadow_scores_never_reach_the_numbers():
    """V7: the shadow pass never merged into the live result, so it must
    not move a mean or an abstention count here either — but the shadow
    lineup is still named, so a shadow judge is visible."""
    rows = real_scores()
    rows += [
        _score_row("or-shadow-judge", label, profile, 10.0, shadow=1)
        for label, profile in _PROPOSALS
    ]
    roster = build_roster(REAL_ROUND, rows)

    assert [j["profile"] for j in roster["shadow_judges"]] == ["or-shadow-judge"]
    assert "or-shadow-judge" not in {j["profile"] for j in roster["judges"]}
    # A shadow 10.0 on every proposal would drag every mean upward.
    winner = next(p for p in roster["proposers"] if p["is_winner"])
    assert winner["mean"] == pytest.approx(REAL_ROUND["winner_mean"])
    assert roster["abstentions"] == 4
    # A healthy shadow judge is not a degradation.
    assert not any("shadow" in r for r in roster["degraded_reasons"])


def test_a_dead_shadow_judge_is_degradation_and_says_it_is_shadow():
    """Also real, also found 2026-09-03: claude-opus and claude-fable-5
    abstained on EVERY shadow score ever recorded, all of them
    `temperature is deprecated for this model`. The shadow pass is what
    agreement.py reads, so a dead shadow judge silently rots the
    agreement data — but it must not read as a judge that voted."""
    reason = (
        "judge call failed: Error code: 400 - {'error': {'code': "
        "'invalid_request_error', 'message': '`temperature` is deprecated "
        "for this model.'}}"
    )
    rows = real_scores()
    rows += [
        _score_row("claude-opus", label, profile, None, shadow=1, reason=reason)
        for label, profile in _PROPOSALS
    ]
    roster = build_roster(REAL_ROUND, rows)

    shadow = next(j for j in roster["shadow_judges"] if j["profile"] == "claude-opus")
    assert shadow["all_abstained"] is True
    assert shadow["abstain_reasons"] == [reason]

    flagged = [r for r in roster["degraded_reasons"] if "claude-opus" in r]
    assert len(flagged) == 1
    assert flagged[0].startswith("shadow judge claude-opus")
    assert "temperature" in flagged[0]
    # It never becomes a live judge, and never moves a live number.
    assert "claude-opus" not in {j["profile"] for j in roster["judges"]}
    assert roster["abstentions"] == 4


# ------------------------------------------- D5: a judge that also proposed


def test_a_judge_that_also_proposed_is_shown_but_never_counted():
    """select_winner's D5 backstop drops such a judge's scores; the
    roster drops them from the mean for the same reason, and then says
    so out loud — the construction bug is the finding."""
    rows = real_scores()
    rows += [
        _score_row("or-gemini-flash", label, profile, 10.0)
        for label, profile in _PROPOSALS
    ]
    roster = build_roster(REAL_ROUND, rows)

    listed = next(j for j in roster["judges"] if j["profile"] == "or-gemini-flash")
    assert listed["also_proposed"] is True
    assert roster["degraded"] is True
    assert any(
        "or-gemini-flash" in r and "also proposed" in r
        for r in roster["degraded_reasons"]
    )
    # Its 10.0s must not have moved a single mean.
    winner = next(p for p in roster["proposers"] if p["is_winner"])
    assert winner["mean"] == pytest.approx(REAL_ROUND["winner_mean"])


# ----------------------------------------------------- structural failures


def test_members_that_returned_nothing_are_degradation():
    row = dict(REAL_ROUND, proposers_attempted=6, judges_attempted=5)
    roster = build_roster(row, real_scores())
    assert roster["degraded"] is True
    assert "2 of 6 proposers returned nothing" in roster["degraded_reasons"]
    assert "1 of 5 judges returned nothing" in roster["degraded_reasons"]


def test_a_non_ok_status_is_degradation():
    roster = build_roster(dict(REAL_ROUND, status="too_small"), [])
    assert roster["degraded"] is True
    assert "round status: too_small" in roster["degraded_reasons"]


def test_a_round_with_no_scores_renders_empty_rather_than_raising():
    """The three oldest real rounds are status='too_small' with zero
    scores and NULL attempted counts — the card must render them."""
    row = dict(
        REAL_ROUND, status="too_small", proposer_count=0, judge_count=0,
        proposers_attempted=None, judges_attempted=None,
        winner_profile=None, winner_label=None, winner_mean=None,
        prompt_tokens=None, completion_tokens=None,
    )
    roster = build_roster(row, [])
    assert roster["proposers"] == []
    assert roster["judges"] == []
    assert roster["abstentions"] == 0
    assert roster["tokens"] == {"prompt": 0, "completion": 0, "total": 0}
    # NULL attempted counts must not read as "everyone returned nothing".
    assert not any("returned nothing" in r for r in roster["degraded_reasons"])


def test_a_healthy_round_is_not_degraded():
    """The negative case — without it, `degraded` could be hardcoded True
    and every test above would still pass."""
    rows = [
        _score_row(judge, label, profile, 7.0)
        for judge in ("or-gpt-5.1", "or-sonnet-5")
        for label, profile in _PROPOSALS
    ]
    roster = build_roster(REAL_ROUND, rows)
    assert roster["degraded"] is False
    assert roster["degraded_reasons"] == []


def test_a_row_written_before_migration_0018_has_no_retry_outcome():
    """REAL_ROUND deliberately omits `retry_outcome` — Larry's live
    database had not run 0018 when this fixture was read. Reading the
    column with [] instead of .get would KeyError on every historical
    round, which is most of them."""
    roster = build_roster(REAL_ROUND, real_scores())
    assert roster["retry_outcome"] is None

    migrated = build_roster(
        dict(REAL_ROUND, retry_outcome="no_retry:prose_end"), real_scores()
    )
    assert migrated["retry_outcome"] == "no_retry:prose_end"
