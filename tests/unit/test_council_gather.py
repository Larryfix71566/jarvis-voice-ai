"""Unit tests for jarvis/council/council.py's _gather_scores (gap-closure
plan GC6(a), 2026-09-04). Same _call_profile monkeypatch seam
tests/integration/test_council_escalation.py already uses."""
from __future__ import annotations

import asyncio

import pytest

import jarvis.council.council as council_mod
from jarvis.council.types import Proposal, RoundResult, Score
from jarvis.model_routing import ModelRouteError
from jarvis.privacy_policy import DataPolicy


def test_timeout_abstain_reason_names_the_exception(monkeypatch):
    """str(asyncio.TimeoutError()) is empty, which hid a dead judge for two
    weeks (kimi-k3 abstained on every proposal in three rounds with
    abstain_reason == "judge call failed: " -- indistinguishable from any
    other silent failure). The exception TYPE must survive even when its
    message doesn't."""
    async def _fake(profile, system_prompt, user_content, timeout_s, rung=None):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(council_mod, "_call_profile", _fake)

    scores, usage = asyncio.run(council_mod._gather_scores(
        ["j1"], {"j1": {"api_key_env": "X"}}, "judge content", ["A"],
        shadow=False, rung="council",
    ))

    assert len(scores) == 1
    assert scores[0].abstain_reason == "judge call failed: TimeoutError: "


def test_stricter_council_policy_rejects_external_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    profile = {
        "name": "test-profile", "model": "test-model",
        "api_key_env": "OPENAI_API_KEY", "base_url": "https://example.invalid/v1",
    }
    with pytest.raises(ModelRouteError, match="requires 'local_only'"):
        asyncio.run(council_mod._call_profile(
            profile, "system", "private", 1,
            rung="council",
            data_policy=DataPolicy("local_only", "private-test"),
        ))


def test_policy_protected_council_payload_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(council_mod, "COUNCIL_LOG_DIR", tmp_path / "council")
    proposal = Proposal("Proposal A", "p1", "PRIVATE_PROPOSAL")
    score = Score("judge", "Proposal A", 8.0, "PRIVATE_JUSTIFICATION")
    result = RoundResult(
        round_id="round-1", winner=proposal, winner_mean=8.0,
        select_reason="PRIVATE_REASON", proposals=[proposal], scores=[score],
    )
    council_mod._write_payload(
        round_id="round-1", workflow="test", placement="doc", trigger="test",
        tier=1, goal="PRIVATE_GOAL", context={"secret": "PRIVATE_CONTEXT"},
        proposals=[proposal], live_scores=[score], result=result,
        started_at="2026-09-20T00:00:00+00:00", ended_at="2026-09-20T00:00:01+00:00",
        data_policy=DataPolicy("confidential", "test"),
    )
    payload = (tmp_path / "council" / "2026-09-20" / "round-1.jsonl").read_text()
    assert "PRIVATE_" not in payload
    assert "<policy-protected>" in payload
