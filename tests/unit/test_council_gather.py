"""Unit tests for jarvis/council/council.py's _gather_scores (gap-closure
plan GC6(a), 2026-09-04). Same _call_profile monkeypatch seam
tests/integration/test_council_escalation.py already uses."""
from __future__ import annotations

import asyncio

import jarvis.council.council as council_mod


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
