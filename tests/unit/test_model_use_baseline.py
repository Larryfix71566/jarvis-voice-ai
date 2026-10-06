from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from scripts import capture_model_use_baseline as baseline


def create_ledger(path: Path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE llm_calls (ts TEXT, rung TEXT, input_tokens INTEGER, output_tokens INTEGER, "
                 "reported_cost REAL, computed_cost REAL, route_name TEXT, billing_source TEXT, duration_ms REAL, "
                 "usage_known INTEGER, cache_breakdown_known INTEGER, prompt TEXT)")
    conn.commit()
    return conn


def insert(conn, *, ts="2026-10-05T12:00:00+00:00", rung="analyst", route=None, billing=None, duration=None):
    conn.execute("INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (ts, rung, 10, 5, None, 0.01, route, billing, duration, 1, None,
                  "private prompt sentinel must never appear"))
    conn.commit()


def test_snapshot_includes_uncheckpointed_wal_and_never_changes_source(tmp_path):
    source = tmp_path / "costs.db"
    conn = create_ledger(source)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    insert(conn, route="direct_api", billing="provider_api", duration=800)
    before = baseline._signature(source)
    try:
        report = baseline.capture_ledger(source)
        assert baseline._signature(source) == before
        assert report["calls"] == 1
        assert report["snapshot"]["source_wal_present"] is True
        assert report["metadata_coverage"]["route_name"]["known_rows"] == 1
        assert report["route_billing_duration_groups"][0]["mean_duration_ms"] == 800
        assert "private prompt sentinel" not in json.dumps(report)
    finally:
        conn.close()


def test_changed_copy_is_retried_before_any_query(tmp_path, monkeypatch):
    source = tmp_path / "costs.db"
    conn = create_ledger(source)
    insert(conn)
    real_signature = baseline._signature
    observations = 0
    def changed_once(path):
        nonlocal observations
        observations += 1
        result = real_signature(path)
        if observations == 2:
            ino, size, modified = result[""]
            result[""] = (ino, size, modified + 1)
        return result
    monkeypatch.setattr(baseline, "_signature", changed_once)
    report = baseline.capture_ledger(source)
    assert report["snapshot"]["attempts"] == 2
    assert report["calls"] == 1
    conn.close()


def test_continuously_changing_source_is_refused(tmp_path, monkeypatch):
    source = tmp_path / "costs.db"
    source.write_bytes(b"not a database")
    ticks = iter(range(20))
    monkeypatch.setattr(baseline, "_signature", lambda path: {"": (1, 2, next(ticks))})
    monkeypatch.setattr(baseline.sqlite3, "connect", lambda *a, **k: pytest.fail("unstable snapshot queried"))
    with pytest.raises(baseline.BaselineUnavailable, match="source_changed"):
        baseline.capture_ledger(source)


def test_missing_source_is_not_created(tmp_path):
    path = tmp_path / "absent.db"
    with pytest.raises(baseline.BaselineUnavailable, match="ledger_missing"):
        baseline.capture_ledger(path)
    assert not path.exists()


def test_source_symlink_is_refused(tmp_path):
    actual = tmp_path / "actual.db"
    create_ledger(actual).close()
    source = tmp_path / "costs.db"
    source.symlink_to(actual)
    with pytest.raises(baseline.BaselineUnavailable, match="symlink"):
        baseline.capture_ledger(source)


def test_legacy_schema_keeps_missing_metrics_unknown_and_filters_window(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.execute("CREATE TABLE llm_calls (ts TEXT, rung TEXT)")
    conn.executemany("INSERT INTO llm_calls VALUES (?,?)", [
        ("2026-10-04T10:00:00+00:00", "supervisor"),
        ("2026-10-05T10:00:00+00:00", "tts"),
    ])
    conn.commit()
    report = baseline.summarize_ledger(conn, since="2026-10-05T00:00:00Z")
    assert report["calls"] == 1 and report["llm_calls"] == 0
    assert report["metadata_coverage"]["duration_ms"]["known_rows"] is None
    assert report["totals"]["estimated_cost_usd"] is None
    assert report["quality_scores_available"] is False
    conn.close()


def test_null_metadata_is_unknown_not_zero_latency_or_free_billing(tmp_path):
    conn = create_ledger(tmp_path / "nulls.db")
    insert(conn)
    report = baseline.summarize_ledger(conn)
    assert report["metadata_coverage"]["duration_ms"]["known_rows"] == 0
    group = report["route_billing_duration_groups"][0]
    assert group["route"] == group["billing_source"] == "unknown"
    assert group["mean_duration_ms"] is None
    conn.close()


def test_unrecognized_metadata_tags_and_source_errors_do_not_leak_text(tmp_path, capsys):
    conn = create_ledger(tmp_path / "costs.db")
    insert(conn, rung="secret-route-sentinel", route="secret-route-sentinel", billing="secret-route-sentinel")
    report = baseline.summarize_ledger(conn)
    assert "secret-route-sentinel" not in json.dumps(report)
    conn.close()
    bad = tmp_path / "bad.json"
    bad.write_text('{"secret-sentinel"')
    assert baseline.main(["--root", str(tmp_path), "--deployment-receipt", str(bad)]) == 1
    assert "secret-sentinel" not in capsys.readouterr().out


def test_output_inside_source_is_refused_before_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "capture_baseline", lambda *a, **k: pytest.fail("capture ran"))
    with pytest.raises(SystemExit):
        baseline.main(["--root", str(tmp_path), "--output", str(tmp_path / "receipt.json")])
    assert not (tmp_path / "receipt.json").exists()


def test_naive_window_timestamp_is_refused():
    with pytest.raises(baseline.BaselineUnavailable, match="timezone"):
        baseline.utc("2026-10-05T12:00:00")
