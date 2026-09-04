"""Unit tests for scripts/cost_report.py's voice-transport split
(MORTIMER_SESSION_MISSES_PLAN.md S1). build_report() is exercised against
a temp ledger written through the real usage_ledger.record_call, so the
schema (quantity/unit) and the bucket vocabulary are the shipped ones, not
a fixture's idea of them. reported_cost is set on every row so the totals
are exact and independent of config/model_prices.yaml."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from jarvis import usage_ledger
from scripts import cost_report


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    db = tmp_path / "costs.db"
    monkeypatch.setattr(usage_ledger, "DB_PATH", db)
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {}})
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


def test_tts_and_stt_bucket_as_voice():
    assert cost_report.bucket_of("tts") == "voice"
    assert cost_report.bucket_of("stt") == "voice"
    assert cost_report.bucket_of("supervisor") == "supervisor"


def test_voice_bucket_and_split(ledger):
    conn = sqlite3.connect(ledger)
    try:
        report = cost_report.build_report(conn, _month())
    finally:
        conn.close()
    assert report["total_cost_usd"] == pytest.approx(0.27)
    assert report["voice_usd"] == pytest.approx(0.22)
    assert report["llm_usd"] == pytest.approx(0.05)
    assert report["per_bucket"]["voice"] == pytest.approx(0.22)
    assert report["per_bucket"]["supervisor"] == pytest.approx(0.05)
    voice = report["voice"]
    assert voice["tts_rows"] == 1 and voice["tts_chars"] == 2000
    assert voice["tts_usd"] == pytest.approx(0.20)
    assert voice["stt_rows"] == 1 and voice["stt_seconds"] == pytest.approx(156)
    assert voice["stt_usd"] == pytest.approx(0.02)


def test_report_without_voice_columns_still_builds(tmp_path):
    """A ledger no writer has touched since S1 landed lacks quantity/unit;
    the report must fall back to zeros, not fail (same shape as the
    plan_state guard)."""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, ts TEXT, month TEXT, "
        "session_id TEXT, rung TEXT, provider TEXT, model TEXT, input_tokens INTEGER, "
        "output_tokens INTEGER, cache_write_tokens INTEGER, cache_read_tokens INTEGER, "
        "reported_cost REAL, computed_cost REAL, gen_id TEXT);"
    )
    conn.execute(
        "INSERT INTO llm_calls (ts, month, rung, provider, model, input_tokens, output_tokens,"
        " cache_write_tokens, cache_read_tokens, reported_cost) VALUES "
        "(?, ?, 'supervisor', 'anthropic', 'm', 1, 1, 0, 0, 0.05)",
        (datetime.now(timezone.utc).isoformat(), _month()),
    )
    conn.commit()
    try:
        report = cost_report.build_report(conn, _month())
    finally:
        conn.close()
    assert report["voice_usd"] == 0
    assert report["llm_usd"] == pytest.approx(0.05)
    assert report["voice"]["tts_rows"] == 0 and report["voice"]["stt_rows"] == 0


def test_text_rendering_prints_the_voice_section(ledger, monkeypatch, capsys):
    monkeypatch.setattr(cost_report, "DB_PATH", ledger)
    monkeypatch.setattr(cost_report.sys, "argv", ["cost_report.py", _month()])
    cost_report.main()
    out = capsys.readouterr().out
    assert "voice transport (MORTIMER_SESSION_MISSES_PLAN.md):" in out
    assert "tts: 1 rows, 2,000 chars, $0.2000" in out
    assert "stt: 1 rows, 2.6 min, $0.0200" in out
    assert "llm $0.0500 vs voice $0.2200  (voice share 81%)" in out
