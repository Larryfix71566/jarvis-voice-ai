"""Unit tests for jarvis/costs_api.py's LLM-vs-voice split
(MORTIMER_SESSION_MISSES_PLAN.md S5). Rows are written through the real
usage_ledger.record_call with reported_cost set, so totals are exact and
independent of config/model_prices.yaml."""

from __future__ import annotations

import pytest

from jarvis import costs_api, usage_ledger


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    db = tmp_path / "costs.db"
    monkeypatch.setattr(usage_ledger, "DB_PATH", db)
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {}})
    monkeypatch.setattr(costs_api, "DB_PATH", db)
    monkeypatch.setattr(costs_api, "BUDGET", 0.0)
    usage_ledger.record_call(
        rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
        input_tokens=6, output_tokens=24, reported_cost=0.05,
    )
    usage_ledger.record_call(
        rung="tts", provider="elevenlabs", model="eleven_flash_v2_5",
        quantity=2000, unit="chars", reported_cost=0.20,
    )
    usage_ledger.record_call(
        rung="stt", provider="deepgram", model="flux-general-en",
        quantity=156, unit="seconds", reported_cost=0.02,
    )
    return db


def test_summary_exposes_voice_and_llm_split(ledger):
    s = costs_api._summary(costs_api._month_now())
    assert s["total_usd"] == pytest.approx(0.27)
    assert s["voice_usd"] == pytest.approx(0.22)
    assert s["llm_usd"] == pytest.approx(0.05)
    # The voice rungs ride by_rung by construction — the Costs tab's
    # rungBreakdown needs no change.
    assert {r["rung"] for r in s["by_rung"]} == {"supervisor", "tts", "stt"}


def test_summary_text_speaks_the_voice_share(ledger):
    text = costs_api.summary_text()
    assert "About 0.22 dollars of that was voice" in text
    assert "text to speech and transcription" in text


def test_summary_text_omits_voice_sentence_when_none(tmp_path, monkeypatch):
    db = tmp_path / "costs.db"
    monkeypatch.setattr(usage_ledger, "DB_PATH", db)
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {}})
    monkeypatch.setattr(costs_api, "DB_PATH", db)
    monkeypatch.setattr(costs_api, "BUDGET", 0.0)
    usage_ledger.record_call(
        rung="supervisor", provider="anthropic", model="m",
        input_tokens=1, output_tokens=1, reported_cost=0.05,
    )
    assert "voice" not in costs_api.summary_text()


def test_empty_ledger_summary_has_zero_voice_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(costs_api, "DB_PATH", tmp_path / "missing.db")
    s = costs_api._summary("2026-09")
    assert s["voice_usd"] == 0.0 and s["llm_usd"] == 0.0
