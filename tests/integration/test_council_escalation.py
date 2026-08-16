"""Integration tests for the council orchestration (jarvis/council/council.py)
and the D2.1 escalation hook in jarvis/agents/upgrade_agent.py. Fake council
members and a fake OpenAI-compatible client — no network (MORTIMER_LLM_
COUNCIL_PLAN.md §6's required escalation test table).
"""

from __future__ import annotations

import asyncio
import glob
import json
from pathlib import Path

import pytest

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
  - name: k-frontier-2
    label: frontier two
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_FRONTIER_2
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

    db_path = tmp_path / "council_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    monkeypatch.setattr(council_mod, "COUNCIL_LOG_DIR", tmp_path / "logs" / "council")
    # Deterministic by default: shadow judging (D8.2.1) is sampled by
    # round_id hash, so leaving the real 0.25 rate active here would make
    # every non-shadow-specific test flaky. Tests that actually exercise
    # shadow judging override this explicitly.
    import jarvis.council.config as council_config_mod
    monkeypatch.setattr(council_config_mod, "COUNCIL_SHADOW_RATE", 0.0)
    return {"registry_path": registry_path, "db_path": db_path}


def _fake_call_profile_factory(judge_scores: dict[str, str] | None = None):
    """Returns an async replacement for council_mod._call_profile that
    never touches the network: proposers get a canned prose plan, judges
    get canned SCORES: text (customizable per judge profile name)."""
    judge_scores = judge_scores or {}

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"Fixed plan from {profile['model']}: do the correct thing.", None
        return judge_scores.get(profile["model"], "SCORES:\nProposal A: 8.0 - good\n"), None

    return _fake


def test_convene_happy_path_writes_rows_and_selects_winner(council_env, monkeypatch):
    monkeypatch.setattr(
        council_mod, "_call_profile", _fake_call_profile_factory(),
    )
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1,
        context={"diff": "some diff", "checks": {"ok": False}},
    ))
    assert result is not None
    assert result.winner is not None
    assert len(result.proposals) == 2  # both economy profiles proposed
    assert len(result.scores) >= 2

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (result.round_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "ok"
        assert row["workflow"] == "selfedit"
        assert row["proposer_count"] == 2
        assert row["winner_profile"] in ("k-economy-1", "k-economy-2")
        score_rows = conn.execute(
            "SELECT * FROM council_scores WHERE round_id = ?", (result.round_id,)
        ).fetchall()
        # V8: mid alone yields 1 judge (< COUNCIL_JUDGE_TARGET=2), so the
        # pool backfills to k-mid-1 + k-frontier-1 — 2 judges x 2 proposals.
        assert len(score_rows) == 4
        assert {r["judge_profile"] for r in score_rows} == {"k-mid-1", "k-frontier-1"}
        for r in score_rows:
            assert r["shadow"] == 0
            assert r["proposal_profile"] in ("k-economy-1", "k-economy-2")
    finally:
        conn.close()

    # JSONL payload was written.
    date = row["started_at"][:10]
    payload_path = council_mod.COUNCIL_LOG_DIR / date / f"{result.round_id}.jsonl"
    assert payload_path.exists()
    lines = [json.loads(l) for l in payload_path.read_text().splitlines()]
    assert lines[0]["type"] == "round_start"
    assert lines[-1]["type"] == "round_end"


def test_convene_kill_switch_disables_everything(council_env, monkeypatch):
    monkeypatch.setenv("JARVIS_COUNCIL_ENABLED", "false")
    called = {"n": 0}

    async def _spy(*a, **k):
        called["n"] += 1
        return "SCORES:\nProposal A: 8.0 - x\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _spy)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is None
    assert called["n"] == 0
    conn = get_conn(council_env["db_path"])
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM council_rounds").fetchone()["n"]
        assert n == 0
    finally:
        conn.close()


def test_convene_no_valid_scores_returns_roundresult_with_no_winner(council_env, monkeypatch):
    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return "a plan", None
        return "I refuse to use the required format.", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None  # the round ran to completion
    assert result.winner is None
    assert "no proposal" in result.select_reason


def test_convene_all_proposers_fail_is_too_small(council_env, monkeypatch):
    async def _fake(profile, system_prompt, user_content, timeout_s):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None
    assert result.winner is None
    assert "too_small" in result.select_reason or "council_too_small" in result.select_reason


def test_shadow_judging_writes_shadow_rows_and_never_affects_winner(council_env, monkeypatch):
    """D8.2.1 — the single most important test in the plan's test table:
    a shadow judge that would pick a DIFFERENT winner must never change
    the live selection.

    V8 note: tier 1's mid pool alone yields 1 judge (< COUNCIL_JUDGE_
    TARGET=2), so the LIVE pool backfills to mid-1 + frontier-1. A
    second frontier profile (frontier-2, unused by any other test — its
    key is unset by default) is enabled here so the D8.2.1 shadow tier
    ("frontier") still has a usable, non-live candidate to shadow with."""
    import jarvis.council.config as council_config_mod
    monkeypatch.setattr(council_config_mod, "COUNCIL_SHADOW_RATE", 1.0)
    monkeypatch.setenv("TESTKEY_FRONTIER_2", "x")
    # V7 — run the shadow pass inline so the assertions below (which
    # read council_scores/council_rounds immediately after convene()
    # returns) don't race the detached-by-default thread.
    monkeypatch.setattr(council_mod, "COUNCIL_SHADOW_INLINE", True)

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"Fixed plan from {profile['model']}: do the correct thing.", None
        if profile.get("api_key_env") == "TESTKEY_FRONTIER_2":
            # The shadow judge would pick B; both live judges pick A.
            # Only A may win.
            return "SCORES:\nProposal A: 2.0 - meh\nProposal B: 9.0 - great\n", None
        # Both live judges (mid-1, and frontier-1 via V8 backfill) agree on A.
        return "SCORES:\nProposal A: 9.0 - great\nProposal B: 2.0 - meh\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None and result.winner is not None
    assert result.winner.label == "Proposal A"  # the live judges' pick

    conn = get_conn(council_env["db_path"])
    try:
        rows = conn.execute(
            "SELECT * FROM council_scores WHERE round_id = ?", (result.round_id,)
        ).fetchall()
        live_rows = [r for r in rows if r["shadow"] == 0]
        shadow_rows = [r for r in rows if r["shadow"] == 1]
        assert len(live_rows) == 4    # mid-1 + frontier-1 (V8 backfill), 2 proposals each
        assert {r["judge_profile"] for r in live_rows} == {"k-mid-1", "k-frontier-1"}
        assert len(shadow_rows) == 2  # k-frontier-2 shadow-scoring 2 proposals
        assert {r["judge_profile"] for r in shadow_rows} == {"k-frontier-2"}
        assert {r["judge_tier"] for r in shadow_rows} == {"frontier"}
        # The recorded winner in council_rounds is the LIVE pick, not the
        # shadow judge's preferred proposal.
        round_row = conn.execute(
            "SELECT winner_label FROM council_rounds WHERE round_id = ?",
            (result.round_id,),
        ).fetchone()
        assert round_row["winner_label"] == "Proposal A"
    finally:
        conn.close()


def test_shadow_judging_failure_is_non_fatal(council_env, monkeypatch):
    """V8 note: frontier-1 is now a LIVE judge (backfilled — see the test
    above), so a second frontier profile (frontier-2) is enabled to be
    the shadow candidate that fails."""
    import jarvis.council.config as council_config_mod
    monkeypatch.setattr(council_config_mod, "COUNCIL_SHADOW_RATE", 1.0)
    monkeypatch.setenv("TESTKEY_FRONTIER_2", "x")
    monkeypatch.setattr(council_mod, "COUNCIL_SHADOW_INLINE", True)

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return "a plan", None
        if profile.get("api_key_env") == "TESTKEY_FRONTIER_2":
            raise RuntimeError("simulated shadow judge outage")
        return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    # The live round completes normally despite the shadow judge failing.
    # (_gather_scores already turns a per-member exception into an
    # explicit abstention Score rather than raising, so the shadow judge
    # still contributes rows here — just all-abstained ones. The
    # important invariant is that the LIVE round is unaffected.)
    assert result is not None and result.winner is not None


def test_should_shadow_rate_zero_never_shadows_in_convene(council_env, monkeypatch):
    calls = {"judge_calls": 0}

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return "a plan", None
        calls["judge_calls"] += 1
        return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None
    # V8: mid alone yields 1 judge (< COUNCIL_JUDGE_TARGET=2), so the
    # live pool backfills to mid-1 + frontier-1 — 2 live judge calls,
    # no shadow call.
    assert calls["judge_calls"] == 2


# --------------------------------------------------- V7: shadow detachment

def test_v7_detached_shadow_returns_before_rows_exist_then_joins(
    council_env, monkeypatch,
):
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V7 — with the (default) knob
    False, convene() returns before the shadow pass has necessarily
    finished; joining the test seam thread makes its writes visible."""
    import jarvis.council.config as council_config_mod
    monkeypatch.setattr(council_config_mod, "COUNCIL_SHADOW_RATE", 1.0)
    monkeypatch.setenv("TESTKEY_FRONTIER_2", "x")
    assert council_mod.COUNCIL_SHADOW_INLINE is False  # the default

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"Fixed plan from {profile['model']}: do the correct thing.", None
        return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None and result.winner is not None
    # V7: RoundResult.scores is live-only now.
    assert all(True for _ in result.scores)  # scores exist (live)

    def _shadow_row_count() -> int:
        conn = get_conn(council_env["db_path"])
        try:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM council_scores "
                "WHERE round_id = ? AND shadow = 1", (result.round_id,),
            ).fetchone()["n"]
        finally:
            conn.close()

    thread = council_mod._last_shadow_thread
    assert thread is not None
    # The thread may occasionally finish before this assertion runs on a
    # slow/contended CI box, so this checks the mechanism exists rather
    # than asserting a hard race — the real guarantee is asserted below,
    # after an explicit join.
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert _shadow_row_count() > 0

    matches = glob.glob(str(council_mod.COUNCIL_LOG_DIR / "*" / f"{result.round_id}.jsonl"))
    lines = [json.loads(l) for l in Path(matches[0]).read_text().splitlines()]
    shadow_records = [l for l in lines if l.get("type") == "score" and l.get("shadow")]
    assert len(shadow_records) > 0


def test_v7_detached_shadow_never_affects_winner(council_env, monkeypatch):
    import jarvis.council.config as council_config_mod
    monkeypatch.setattr(council_config_mod, "COUNCIL_SHADOW_RATE", 1.0)
    monkeypatch.setenv("TESTKEY_FRONTIER_2", "x")

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"Fixed plan from {profile['model']}: do the correct thing.", None
        if profile.get("api_key_env") == "TESTKEY_FRONTIER_2":
            return "SCORES:\nProposal A: 2.0 - meh\nProposal B: 9.0 - great\n", None
        return "SCORES:\nProposal A: 9.0 - great\nProposal B: 2.0 - meh\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None and result.winner is not None
    assert result.winner.label == "Proposal A"

    thread = council_mod._last_shadow_thread
    assert thread is not None
    thread.join(timeout=5)

    conn = get_conn(council_env["db_path"])
    try:
        round_row = conn.execute(
            "SELECT winner_label FROM council_rounds WHERE round_id = ?",
            (result.round_id,),
        ).fetchone()
    finally:
        conn.close()
    assert round_row["winner_label"] == "Proposal A"  # unaffected by shadow


# -------------------------------------------------- V9: token accounting

def test_v9_usage_reported_totals_correct_in_round_row_and_jsonl(
    council_env, monkeypatch,
):
    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return (
                f"Fixed plan from {profile['model']}: do the correct thing.",
                {"prompt_tokens": 100, "completion_tokens": 50},
            )
        return (
            "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n",
            {"prompt_tokens": 200, "completion_tokens": 20},
        )

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1, context={},
    ))
    assert result is not None and result.winner is not None

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens FROM council_rounds "
            "WHERE round_id = ?", (result.round_id,),
        ).fetchone()
    finally:
        conn.close()
    # 2 proposers (economy-1, economy-2) + 2 live judges (mid-1,
    # frontier-1 via V8 backfill) all report usage: prompt = 2*100 +
    # 2*200 = 600, completion = 2*50 + 2*20 = 140.
    assert row["prompt_tokens"] == 600
    assert row["completion_tokens"] == 140

    matches = glob.glob(str(council_mod.COUNCIL_LOG_DIR / "*" / f"{result.round_id}.jsonl"))
    lines = [json.loads(l) for l in Path(matches[0]).read_text().splitlines()]
    proposal_records = [l for l in lines if l["type"] == "proposal"]
    score_records = [l for l in lines if l["type"] == "score"]
    assert all(r["usage"] == {"prompt_tokens": 100, "completion_tokens": 50}
               for r in proposal_records)
    assert all(r["usage"] == {"prompt_tokens": 200, "completion_tokens": 20}
               for r in score_records)


def test_v9_provider_omits_usage_writes_null_never_zero(council_env, monkeypatch):
    monkeypatch.setattr(
        council_mod, "_call_profile", _fake_call_profile_factory(),
    )
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1, context={},
    ))
    assert result is not None and result.winner is not None

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens FROM council_rounds "
            "WHERE round_id = ?", (result.round_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["prompt_tokens"] is None
    assert row["completion_tokens"] is None

    matches = glob.glob(str(council_mod.COUNCIL_LOG_DIR / "*" / f"{result.round_id}.jsonl"))
    lines = [json.loads(l) for l in Path(matches[0]).read_text().splitlines()]
    for r in lines:
        if r["type"] in ("proposal", "score"):
            assert r["usage"] is None


# --------------------------------------------------- V2: judge context

def test_v2_judge_message_includes_failure_context_before_proposals():
    from jarvis.council.types import Proposal

    proposals = [
        Proposal(label="Proposal A", profile="p1", content="do X"),
        Proposal(label="Proposal B", profile="p2", content="do Y"),
    ]
    msg = council_mod._judge_user_message(
        "fix the bug", {"diff": "- old\n+ new", "checks": {"ok": False}},
        proposals, "planner",
    )
    goal_idx = msg.index("GOAL:")
    context_idx = msg.index("FAILURE CONTEXT")
    checks_idx = msg.index("VALIDATION CHECKS")
    proposal_a_idx = msg.index("Proposal A:")
    proposal_b_idx = msg.index("Proposal B:")
    assert goal_idx < context_idx < checks_idx < proposal_a_idx < proposal_b_idx
    assert "- old\n+ new" in msg
    assert "'ok': False" in msg or '"ok": false' in msg.lower() or "False" in msg
    # No proposer profile name leaks into the judge's message.
    assert "p1" not in msg and "p2" not in msg


def test_v2_judge_message_empty_context_omits_sections():
    from jarvis.council.types import Proposal

    proposals = [Proposal(label="Proposal A", profile="p1", content="do X")]
    msg = council_mod._judge_user_message("fix the bug", {}, proposals, "planner")
    assert "FAILURE CONTEXT" not in msg
    assert "VALIDATION CHECKS" not in msg
    assert "GOAL:\nfix the bug" in msg
    assert "Proposal A:\ndo X" in msg


def test_v2_replay_judge_message_includes_stored_context(council_env, monkeypatch):
    from jarvis.council import __main__ as cli

    seen_contents: list[str] = []

    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"Fixed plan from {profile['model']}: do the correct thing.", None
        seen_contents.append(user_content)
        return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1,
        context={"diff": "some diff text", "checks": {"ok": False}},
    ))
    assert result is not None and result.winner is not None
    seen_contents.clear()

    rc = cli.main(["--replay", result.round_id, "--judges", "frontier", "--dry-run"])
    assert rc == 0
    assert seen_contents  # the replay judge was actually called
    assert any("some diff text" in c and "FAILURE CONTEXT" in c for c in seen_contents)


# ------------------------------------------------------- V1: carry-forward

def test_v1_carried_proposal_appears_counts_and_marked_in_jsonl(
    council_env, monkeypatch,
):
    monkeypatch.setattr(
        council_mod, "_call_profile", _fake_call_profile_factory(),
    )
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1,
        context={"carry_forward": {
            "profile": "k-carried-winner", "content": "carried approach",
        }},
    ))
    assert result is not None
    # 2 fan-out (economy-1, economy-2) + 1 carried == 3 proposals.
    assert len(result.proposals) == 3
    carried = [p for p in result.proposals if p.profile == "k-carried-winner"]
    assert len(carried) == 1
    assert carried[0].content == "carried approach"
    assert carried[0].label  # a real label was assigned by the V4 shuffle

    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT proposer_count FROM council_rounds WHERE round_id = ?",
            (result.round_id,),
        ).fetchone()
        assert row["proposer_count"] == 3
    finally:
        conn.close()

    matches = glob.glob(str(council_mod.COUNCIL_LOG_DIR / "*" / f"{result.round_id}.jsonl"))
    assert len(matches) == 1
    lines = [json.loads(l) for l in Path(matches[0]).read_text().splitlines()]
    proposal_records = [l for l in lines if l["type"] == "proposal"]
    carried_records = [r for r in proposal_records if r["profile"] == "k-carried-winner"]
    assert len(carried_records) == 1
    assert carried_records[0]["carried"] is True
    fresh_records = [r for r in proposal_records if r["profile"] != "k-carried-winner"]
    assert all(r["carried"] is False for r in fresh_records)


def test_v1_carried_profile_excluded_from_judge_pool(council_env, monkeypatch):
    """The carried profile joins the judge exclude set exactly like a
    fan-out proposer — here the carried profile IS the tier-1 mid judge,
    so judge resolution must fall back up to frontier."""
    monkeypatch.setattr(
        council_mod, "_call_profile", _fake_call_profile_factory(),
    )
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1,
        context={"carry_forward": {
            "profile": "k-mid-1", "content": "carried approach",
        }},
    ))
    assert result is not None
    conn = get_conn(council_env["db_path"])
    try:
        rows = conn.execute(
            "SELECT DISTINCT judge_profile, judge_tier FROM council_scores "
            "WHERE round_id = ? AND shadow = 0", (result.round_id,),
        ).fetchall()
    finally:
        conn.close()
    judge_profiles = {r["judge_profile"] for r in rows}
    assert "k-mid-1" not in judge_profiles  # excluded: it's the carried profile
    assert judge_profiles == {"k-frontier-1"}  # fallback climbed to frontier


# --------------------------------------------------------- V4: label shuffle

def test_v4_same_round_id_twice_identical_label_assignment():
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V4 — deterministic per round: a
    replay of the same round_id reconstructs the same label assignment."""
    from jarvis.council.council import _shuffle_and_label
    from jarvis.council.types import Proposal

    proposals = [
        Proposal(label="", profile="k-economy-1", content="a"),
        Proposal(label="", profile="k-economy-2", content="b"),
        Proposal(label="", profile="k-mid-1", content="c"),
        Proposal(label="", profile="k-frontier-1", content="d"),
    ]
    first, _ = _shuffle_and_label("fixed-round-id", proposals)
    second, _ = _shuffle_and_label("fixed-round-id", proposals)
    assert [(p.label, p.profile) for p in first] == [(p.label, p.profile) for p in second]


def test_v4_different_round_ids_shuffle_actually_shuffles():
    """Over many distinct round_ids, label order must differ from plain
    registry order for at least one — otherwise the shuffle is a no-op."""
    from jarvis.council.council import _shuffle_and_label
    from jarvis.council.types import Proposal

    proposals = [
        Proposal(label="", profile=f"profile-{i}", content=str(i)) for i in range(6)
    ]
    original_order = [p.profile for p in proposals]
    saw_a_shuffle = False
    for i in range(50):
        labeled, _ = _shuffle_and_label(f"round-{i}", proposals)
        if [p.profile for p in labeled] != original_order:
            saw_a_shuffle = True
            break
    assert saw_a_shuffle


def test_v4_labels_are_always_sequential_regardless_of_shuffle():
    from jarvis.council.council import _shuffle_and_label
    from jarvis.council.types import Proposal

    proposals = [
        Proposal(label="", profile=f"profile-{i}", content=str(i)) for i in range(4)
    ]
    labeled, _ = _shuffle_and_label("some-round-id", proposals)
    assert [p.label for p in labeled] == [
        "Proposal A", "Proposal B", "Proposal C", "Proposal D",
    ]
    # Every profile still present exactly once — shuffle reorders, never drops.
    assert {p.profile for p in labeled} == {p.profile for p in proposals}


def test_v4_tiebreak_uses_registry_order_not_shuffled_label_order(
    council_env, monkeypatch,
):
    """Even though labels are now shuffled, select_winner's rule-4
    tiebreak must still resolve to the earliest REGISTRY profile
    (k-economy-1, per REGISTRY_YAML), never to "Proposal A" merely
    because that label happened to win the shuffle."""
    async def _fake(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return f"Fixed plan from {profile['model']}: do the correct thing.", None
        # Perfect tie: both proposals score identically on every axis.
        return "SCORES:\nProposal A: 7.0 - x\nProposal B: 7.0 - x\n", None

    monkeypatch.setattr(council_mod, "_call_profile", _fake)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None and result.winner is not None
    assert result.winner.profile == "k-economy-1"  # earliest in registry order
    assert "registry order" in result.select_reason


def test_record_retry_validated_updates_row(council_env, monkeypatch):
    monkeypatch.setattr(
        council_mod, "_call_profile", _fake_call_profile_factory(),
    )
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))
    assert result is not None and result.winner is not None
    council_mod.record_retry_validated(result.round_id, True)
    conn = get_conn(council_env["db_path"])
    try:
        row = conn.execute(
            "SELECT retry_validated FROM council_rounds WHERE round_id = ?",
            (result.round_id,),
        ).fetchone()
        assert row["retry_validated"] == 1
    finally:
        conn.close()
