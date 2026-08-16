"""Integration tests for jarvis/council/__main__.py (D8.2.2 --replay,
--agreement). Fake council members and a fake client — no network."""

from __future__ import annotations

import asyncio

import pytest

from jarvis.council import __main__ as cli
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
def cli_env(tmp_path, monkeypatch):
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(REGISTRY_YAML, encoding="utf-8")
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    for key in (
        "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1", "TESTKEY_FRONTIER_1",
    ):
        monkeypatch.setenv(key, "x")
    monkeypatch.delenv("JARVIS_COUNCIL_ENABLED", raising=False)

    db_path = tmp_path / "cli_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    monkeypatch.setattr(council_mod, "COUNCIL_LOG_DIR", tmp_path / "logs" / "council")
    import jarvis.council.config as council_config_mod
    monkeypatch.setattr(council_config_mod, "COUNCIL_SHADOW_RATE", 0.0)
    return {"db_path": db_path}


async def _fake_call_profile(profile, system_prompt, user_content, timeout_s):
    if system_prompt == council_mod.PROPOSER_PROMPT:
        return f"Fixed plan from {profile['model']}: do the correct thing.", None
    return "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n", None


def _run_live_round(monkeypatch) -> str:
    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile)
    result = asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix the thing", tier=1, context={},
    ))
    assert result is not None and result.winner is not None
    return result.round_id


def _score_row_count(db_path, round_id: str, *, shadow: int | None = None) -> int:
    conn = get_conn(db_path)
    try:
        if shadow is None:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM council_scores WHERE round_id = ?",
                (round_id,),
            ).fetchone()["n"]
        return conn.execute(
            "SELECT COUNT(*) AS n FROM council_scores WHERE round_id = ? AND shadow = ?",
            (round_id, shadow),
        ).fetchone()["n"]
    finally:
        conn.close()


def test_replay_dry_run_writes_nothing(cli_env, monkeypatch, capsys):
    round_id = _run_live_round(monkeypatch)
    before = _score_row_count(cli_env["db_path"], round_id)

    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile)
    rc = cli.main(["--replay", round_id, "--judges", "frontier", "--dry-run"])
    assert rc == 0

    after = _score_row_count(cli_env["db_path"], round_id)
    assert after == before

    out = capsys.readouterr().out
    assert "live winner" in out
    assert "replay winner" in out
    assert "--dry-run: nothing written" in out


def test_replay_without_dry_run_writes_only_shadow_rows(cli_env, monkeypatch):
    round_id = _run_live_round(monkeypatch)
    live_before = _score_row_count(cli_env["db_path"], round_id, shadow=0)

    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile)
    rc = cli.main(["--replay", round_id, "--judges", "frontier"])
    assert rc == 0

    live_after = _score_row_count(cli_env["db_path"], round_id, shadow=0)
    shadow_after = _score_row_count(cli_env["db_path"], round_id, shadow=1)
    assert live_after == live_before  # council_rounds/live scores untouched
    assert shadow_after > 0

    conn = get_conn(cli_env["db_path"])
    try:
        row = conn.execute(
            "SELECT winner_label FROM council_rounds WHERE round_id = ?", (round_id,)
        ).fetchone()
        assert row["winner_label"] == "Proposal A"  # unchanged by replay
    finally:
        conn.close()


def test_replay_unknown_round_errors(cli_env, monkeypatch):
    rc = cli.main(["--replay", "not-a-real-round", "--judges", "frontier"])
    assert rc == 1


def test_replay_requires_judges_flag(cli_env):
    rc = cli.main(["--replay", "some-round"])
    assert rc == 2


def test_v13_registry_order_persisted_and_replay_uses_it(cli_env, monkeypatch):
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V13 — the round row stores the
    registry order at convene() time, and --replay runs cleanly off it
    (rather than the live registry) without crashing."""
    round_id = _run_live_round(monkeypatch)

    conn = get_conn(cli_env["db_path"])
    try:
        row = conn.execute(
            "SELECT registry_order FROM council_rounds WHERE round_id = ?",
            (round_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["registry_order"] is not None
    import json as _json
    stored = _json.loads(row["registry_order"])
    assert stored == ["k-economy-1", "k-economy-2", "k-mid-1", "k-frontier-1"]

    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile)
    rc = cli.main(["--replay", round_id, "--judges", "frontier", "--dry-run"])
    assert rc == 0


def test_agreement_empty_db_reports_insufficient_data(cli_env, capsys):
    rc = cli.main(["--agreement"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "rounds considered      0" in out
    assert "insufficient data" in out


def test_agreement_token_line_sums_only_rounds_with_usage(cli_env, monkeypatch, capsys):
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V9 — the token summary line sums
    only rounds that reported usage, and its denominator is the full
    round set already considered by the report above it."""
    async def _with_usage(profile, system_prompt, user_content, timeout_s):
        if system_prompt == council_mod.PROPOSER_PROMPT:
            return "a plan", {"prompt_tokens": 10, "completion_tokens": 5}
        return (
            "SCORES:\nProposal A: 8.0 - good\nProposal B: 6.0 - ok\n",
            {"prompt_tokens": 30, "completion_tokens": 7},
        )

    monkeypatch.setattr(council_mod, "_call_profile", _with_usage)
    asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix", tier=1, context={},
    ))

    monkeypatch.setattr(council_mod, "_call_profile", _fake_call_profile)  # no usage
    asyncio.run(council_mod.convene(
        workflow="selfedit", placement="planner", trigger="E1",
        goal="fix again", tier=1, context={},
    ))

    rc = cli.main(["--agreement"])
    assert rc == 0
    out = capsys.readouterr().out
    # "rounds considered" is compute_agreement's own metric (shadowed
    # rounds only, D8.2.4) — separate from the token line's denominator,
    # which sums over the full round set (V9, both rounds here, neither
    # shadowed at COUNCIL_SHADOW_RATE=0.0).
    assert "total tokens          prompt=80 completion=24" in out
    assert "rounds with usage: 1/2" in out
