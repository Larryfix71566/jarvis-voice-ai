"""Integration tests for the planning pathway's council-parallel mode
(MORTIMER_PLANNING_PATHWAY_PLAN.md P7): jarvis/council/council.py's
draft_candidates + record_user_choice. Same fake-registry/fake-transport
pattern as tests/integration/test_council_escalation.py — no network.
"""

from __future__ import annotations

import asyncio
import glob
import json
from pathlib import Path

import pytest

from jarvis.council import agreement as agreement_mod
from jarvis.council import council as council_mod
from jarvis.db import get_conn, run_migrations

REGISTRY_YAML = """
default: k-mid-1

profiles:
  - name: k-economy-1
    label: economy one
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_ECON_1
    temperature: 0.2
    tier: economy
  - name: k-economy-2
    label: economy two
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_ECON_2
    temperature: 0.2
    tier: economy
  - name: k-mid-1
    label: mid one
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_MID_1
    temperature: 0.2
    tier: mid
  - name: k-frontier-1
    label: frontier one
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_FRONTIER_1
    temperature: 0.2
    tier: frontier
"""


@pytest.fixture()
def council_env(tmp_path, monkeypatch):
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(REGISTRY_YAML, encoding="utf-8")
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    for key in (
        "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1", "TESTKEY_FRONTIER_1",
    ):
        monkeypatch.setenv(key, "x")
    monkeypatch.delenv("JARVIS_COUNCIL_ENABLED", raising=False)

    db_path = tmp_path / "planning_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    monkeypatch.setattr(council_mod, "COUNCIL_LOG_DIR", tmp_path / "logs" / "council")
    return {"registry_path": registry_path, "db_path": db_path}


def _fake_call_profile(profile, system_prompt, user_content, timeout_s, rung=None):
    if system_prompt == council_mod.PLAN_AUTHOR_PROMPT:
        return f"Plan by {profile['model']}: do the thing.", None
    return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\nProposal C: 7.0 - fine\nProposal D: 5.0 - meh\n", None


async def _fake_call_profile_async(profile, system_prompt, user_content, timeout_s, rung=None):
    return _fake_call_profile(profile, system_prompt, user_content, timeout_s)


def test_draft_candidates_default_narrows_to_frontier_tier(council_env, monkeypatch):
    """MORTIMER_OPTIMIZATION_PLAN.md Phase 3 (2026-09-01) — superseded the
    original P7 default (FULL key-present registry, every spoken
    plan_start request bought a 13-drafts fan-out). No explicit `members`
    now resolves only PLANNING_DEFAULT_PROPOSER_TIERS (frontier);
    council_env's fixture registry has exactly one frontier profile."""
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None
    assert len(result.proposals) == 1
    assert {p.profile for p in result.proposals} == {"k-frontier-1"}


def test_draft_candidates_explicit_members_can_still_widen_beyond_frontier(
    council_env, monkeypatch,
):
    """The Phase 3 narrowing applies only to the no-selection DEFAULT —
    an explicit `members["proposers"]` (the console picker, D9) can still
    fan out to the full registry exactly as before."""
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates(
        "write a plan for X",
        members={"proposers": [
            "k-economy-1", "k-economy-2", "k-mid-1", "k-frontier-1",
        ]},
    ))
    assert result is not None
    assert len(result.proposals) == 4
    assert {p.profile for p in result.proposals} == {
        "k-economy-1", "k-economy-2", "k-mid-1", "k-frontier-1",
    }


def test_draft_candidates_never_selects_a_winner(council_env, monkeypatch):
    """P7's whole point: council never picks in this pathway. Proposers
    are narrowed here so at least one profile remains eligible to judge —
    with the full registry proposing (the default), nobody is left to
    judge, which is covered separately below."""
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates(
        "write a plan for X",
        members={"proposers": ["k-economy-1", "k-economy-2", "k-mid-1"]},
    ))
    assert result is not None
    assert result.winner is None
    assert "awaiting user choice" in result.select_reason
    assert len(result.scores) > 0  # judges DID score, advisorily
    assert {s.judge_profile for s in result.scores} == {"k-frontier-1"}


def test_draft_candidates_default_frontier_only_leaves_the_rest_as_judges(
    council_env, monkeypatch,
):
    """MORTIMER_OPTIMIZATION_PLAN.md Phase 3 side effect, worth pinning:
    before, the default (full registry proposing) left the disjoint-
    proposer/judge invariant with nobody eligible to judge, so advisory
    scoring was always empty. Now that the default proposer set narrows
    to frontier only, the rest of the key-present registry (economy-1,
    economy-2, mid-1 in this fixture) is eligible to judge — advisory
    scoring actually has something to do by default now."""
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None
    assert {s.judge_profile for s in result.scores} == {
        "k-economy-1", "k-economy-2", "k-mid-1",
    }


def test_draft_candidates_writes_planning_workflow_row(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (result.round_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["workflow"] == "planning"
    assert row["placement"] == "doc"
    assert row["status"] == "awaiting_user"
    assert row["winner_profile"] is None
    assert row["winner_label"] is None


def test_draft_candidates_judge_false_skips_scoring(council_env, monkeypatch):
    calls = {"judge_calls": 0}

    async def _fake(profile, system_prompt, user_content, timeout_s, rung=None):
        if system_prompt == council_mod.PLAN_AUTHOR_PROMPT:
            return f"Plan by {profile['model']}.", None
        calls["judge_calls"] += 1
        return "SCORES:\nProposal A: 8.0 - good\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X", judge=False))
    assert result is not None
    assert calls["judge_calls"] == 0
    assert result.scores == []


def test_draft_candidates_members_narrows_proposers(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates(
        "write a plan for X", members={"proposers": ["k-economy-1", "k-mid-1"]},
    ))
    assert result is not None
    assert {p.profile for p in result.proposals} == {"k-economy-1", "k-mid-1"}


def test_draft_candidates_kill_switch_disables(council_env, monkeypatch):
    monkeypatch.setenv("JARVIS_COUNCIL_ENABLED", "false")
    called = {"n": 0}

    async def _spy(*a, **k):
        called["n"] += 1
        return "x", None

    monkeypatch.setattr(council_mod, "_call_profile", _spy)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is None
    assert called["n"] == 0


def test_draft_candidates_no_usable_proposer_is_too_small(council_env, monkeypatch):
    for key in (
        "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1", "TESTKEY_FRONTIER_1",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None
    assert result.winner is None
    assert "no usable proposers" in result.select_reason


def test_record_user_choice_sets_winner_and_status(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None
    label = result.proposals[0].label
    expected_profile = result.proposals[0].profile

    council_mod.record_user_choice(result.round_id, label)

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (result.round_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["winner_label"] == label
    assert row["winner_profile"] == expected_profile
    assert row["select_reason"] == "user choice"
    assert row["status"] == "ok"


def test_record_user_choice_unknown_round_is_noop(council_env):
    # Must not raise — best-effort, matching every other D8 writer.
    council_mod.record_user_choice("does-not-exist", "Proposal A")


def test_record_user_choice_unknown_label_is_noop(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None
    council_mod.record_user_choice(result.round_id, "Proposal Z")

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT winner_label, status FROM council_rounds WHERE round_id = ?",
            (result.round_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["winner_label"] is None
    assert row["status"] == "awaiting_user"


def test_unchosen_candidates_remain_in_payload_and_scores(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates(
        "write a plan for X",
        members={"proposers": ["k-economy-1", "k-economy-2", "k-mid-1"]},
    ))
    assert result is not None
    chosen_label = result.proposals[0].label
    council_mod.record_user_choice(result.round_id, chosen_label)

    conn = get_conn(council_env["db_path"])
    try:
        score_rows = conn.execute(
            "SELECT DISTINCT proposal_label FROM council_scores WHERE round_id = ?",
            (result.round_id,),
        ).fetchall()
    finally:
        conn.close()
    all_labels = {p.label for p in result.proposals}
    assert {r["proposal_label"] for r in score_rows} == all_labels  # unchosen kept

    matches = glob.glob(str(council_mod.COUNCIL_LOG_DIR / "*" / f"{result.round_id}.jsonl"))
    lines = [json.loads(l) for l in Path(matches[0]).read_text().splitlines()]
    proposal_records = [l for l in lines if l["type"] == "proposal"]
    assert {r["label"] for r in proposal_records} == all_labels


def test_planning_rounds_excluded_from_compute_agreement(council_env, monkeypatch):
    """P7 — workflow='planning' rounds must never count toward the
    council's judge-quality agreement metrics."""
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None

    conn = get_conn(council_env["db_path"])
    try:
        round_rows = [
            dict(r) for r in conn.execute("SELECT * FROM council_rounds").fetchall()
        ]
        # Simulate a shadow row on the planning round to prove the filter
        # actively excludes it even if one somehow existed (belt-and-
        # suspenders — draft_candidates itself never writes shadow rows).
        conn.execute(
            "INSERT INTO council_scores (round_id, judge_profile, judge_tier, "
            "shadow, proposal_label, proposal_profile, score, created_at) "
            "VALUES (?, 'k-frontier-1', 'frontier', 1, ?, ?, 9.0, "
            "'2026-01-01T00:00:00+00:00')",
            (result.round_id, result.proposals[0].label, result.proposals[0].profile),
        )
        conn.commit()
        score_rows = [
            dict(r) for r in conn.execute("SELECT * FROM council_scores").fetchall()
        ]
    finally:
        conn.close()

    report = agreement_mod.compute_agreement(score_rows, round_rows, min_rounds=1)
    assert report.rounds_considered == 0


# ------------------------------------------------ review mode (R1/R3)
# MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R1/R3 — draft_candidates' additive
# `context` param: when context["document"] is present this is a REVIEW
# job (PLAN_REVIEW_PROMPT instead of PLAN_AUTHOR_PROMPT, placement=
# "review" instead of "doc"). convene() itself is untouched by this.

def _fake_call_profile_review(profile, system_prompt, user_content, timeout_s, rung=None):
    if system_prompt == council_mod.PLAN_REVIEW_PROMPT:
        return f"Review by {profile['model']}: looks fine.", None
    if system_prompt == council_mod.PLAN_AUTHOR_PROMPT:
        return f"Plan by {profile['model']}: do the thing.", None
    return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\nProposal C: 7.0 - fine\nProposal D: 5.0 - meh\n", None


async def _fake_call_profile_review_async(profile, system_prompt, user_content, timeout_s, rung=None):
    return _fake_call_profile_review(profile, system_prompt, user_content, timeout_s)


def test_draft_candidates_review_context_uses_review_prompt(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_review_async)
    result = asyncio.run(council_mod.draft_candidates(
        "review the geolocation plan",
        members={"proposers": ["k-economy-1", "k-economy-2", "k-mid-1"]},
        context={"document": "PLAN CONTENT HERE", "document_path": "docs/plans/x.md"},
    ))
    assert result is not None
    assert len(result.proposals) == 3
    for p in result.proposals:
        assert p.content.startswith("Review by")


def test_draft_candidates_review_writes_placement_review(council_env, monkeypatch):
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_review_async)
    result = asyncio.run(council_mod.draft_candidates(
        "review the geolocation plan",
        context={"document": "PLAN CONTENT HERE", "document_path": "docs/plans/x.md"},
    ))
    assert result is not None

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (result.round_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["workflow"] == "planning"
    assert row["placement"] == "review"


def test_draft_candidates_review_context_injected_into_proposer_message(
    council_env, monkeypatch,
):
    """R3 — the document lands in the proposer's user message via the
    same _proposer_user_message assembly convene() uses."""
    seen: dict[str, str] = {}

    async def _fake(profile, system_prompt, user_content, timeout_s, rung=None):
        seen[profile["name"]] = user_content
        return _fake_call_profile_review(profile, system_prompt, user_content, timeout_s)

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.draft_candidates(
        "review the geolocation plan",
        members={"proposers": ["k-economy-1"]},
        context={"document": "PLAN CONTENT HERE", "document_path": "docs/plans/x.md"},
    ))
    assert result is not None
    assert "DOCUMENT UNDER REVIEW (docs/plans/x.md):" in seen["k-economy-1"]
    assert "PLAN CONTENT HERE" in seen["k-economy-1"]


def test_draft_candidates_without_context_still_uses_author_prompt(council_env, monkeypatch):
    """Backward compatibility (R2/R3): omitting context entirely (the
    existing call shape) still authors, unaffected by the review branch."""
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile_review_async)
    result = asyncio.run(council_mod.draft_candidates("write a plan for X"))
    assert result is not None
    for p in result.proposals:
        assert p.content.startswith("Plan by")

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (result.round_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["placement"] == "doc"


def test_convene_never_passes_document_context_unaffected(council_env, monkeypatch):
    """R3 — convene() (the escalation path) never sets context['document'],
    so its message assembly is untouched by the review branch."""
    async def _fake(profile, system_prompt, user_content, timeout_s, rung=None):
        assert "DOCUMENT UNDER REVIEW" not in user_content
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"corrected approach by {profile['model']}", None
        return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1,
        context={"diff": "some diff", "checks": "some checks"},
    ))
    assert result is not None
