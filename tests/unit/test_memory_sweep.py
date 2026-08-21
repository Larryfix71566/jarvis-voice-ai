"""Unit tests for jarvis/memory_sweep.py
(MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A1/A2/A3/A4/A5)."""

from __future__ import annotations

import json

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.memory import archive_fact, render_memory_context, upsert_fact
from jarvis.memory_sweep import (
    SWEEP_MAX_ARCHIVES,
    _apply_classification,
    _parse_classification,
    _select_audience_candidates,
    _select_contradiction_pairs,
    enabled,
    list_open_reviews,
    resolve_review,
    run_auto_consolidation,
    run_sweep,
    run_stale_sweep,
)
from tests.unit.test_memory import _factory


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "sweep.db"))
    c = get_conn(tmp_path / "sweep.db")
    run_migrations(c)
    yield c
    c.close()


def _fact(conn, key, content, tier=None):
    conn.execute(
        "INSERT INTO memories (kind, key, content, created_at, updated_at, tier) "
        "VALUES ('fact', ?, ?, ?, ?, ?)",
        (key, content, now_iso(), now_iso(), tier),
    )


# --- A1: auto-consolidation ---------------------------------------------


def test_kept_fact_is_longest_content(conn):
    """The 2026-08-20 cluster-26 lesson: keep the longest content, not
    the overlap scorer's suggested_survivor pick. Both keys contain
    'preference' so mixed_content_warning's preference-topic marker
    (both contents say "prefers") does not fire — that hazard is tested
    separately below."""
    _fact(conn, "user.preference.conciseness", "Larry prefers short answers", "preference")
    _fact(conn, "user.preference.verbosity",
          "Larry prefers short, terse, direct answers with minimal detail",
          "preference")
    conn.commit()
    result = run_auto_consolidation(conn)
    assert "user.preference.conciseness" in result["archived"]
    survivor = conn.execute(
        "SELECT archived_at, became FROM memories WHERE key = ?",
        ("user.preference.conciseness",),
    ).fetchone()
    assert survivor["archived_at"] is not None
    assert survivor["became"] == "auto-consolidated:user.preference.verbosity"


def test_mixed_content_blocks_auto_archive(conn):
    """The Fahrenheit-inside-a-location hazard stays a hard stop for A1:
    a 'user.location*' key whose content carries a preference topic
    ('prefers') the key doesn't advertise."""
    _fact(conn, "user.location", "Spartanburg prefers Fahrenheit for all displays always", "preference")
    _fact(conn, "user.location.note", "Spartanburg prefers Fahrenheit for all displays every time", "preference")
    conn.commit()
    result = run_auto_consolidation(conn)
    assert result["archived"] == []
    reviews = list_open_reviews(conn)
    assert any(r["kind"] == "cluster" for r in reviews)


def test_sweep_archives_at_most_the_cap(conn):
    """Bounded damage per boot — many small 2-fact clusters, cap holds."""
    for i in range(SWEEP_MAX_ARCHIVES + 5):
        _fact(conn, f"user.preference.thing_{i}_a", f"Larry always wants option {i} enabled please yes",
              "preference")
        _fact(conn, f"user.preference.thing_{i}_b", f"Larry always wants option {i} enabled please yes indeed",
              "preference")
    conn.commit()
    result = run_auto_consolidation(conn)
    assert len(result["archived"]) <= SWEEP_MAX_ARCHIVES


def test_auto_archive_uses_archive_not_delete(conn):
    _fact(conn, "user.style.a", "Larry prefers short concise replies always", "preference")
    _fact(conn, "user.style.b", "Larry prefers short concise replies every time always", "preference")
    conn.commit()
    run_auto_consolidation(conn)
    rows = conn.execute("SELECT key FROM memories WHERE kind='fact'").fetchall()
    assert len(rows) == 2  # both rows still present — archived, not deleted


def test_identity_is_never_auto_archived(conn):
    _fact(conn, "user.location", "Spartanburg South Carolina always current device location", "identity")
    _fact(conn, "user.location.alt", "Spartanburg South Carolina current device location always", "identity")
    conn.commit()
    result = run_auto_consolidation(conn)
    assert result["archived"] == []
    live = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='fact' AND archived_at IS NULL"
    ).fetchone()["n"]
    assert live == 2


# --- A4: system staleness -------------------------------------------------


def test_system_stale_never_touches_other_tiers(conn):
    old = now_iso()
    conn.execute(
        "INSERT INTO memories (kind, key, content, created_at, updated_at, tier) "
        "VALUES ('fact', 'mortimer.build.status', 'old build info', ?, '2020-01-01T00:00:00+00:00', 'system')",
        (old,),
    )
    _fact(conn, "user.preference.old", "an old but still-true preference", "preference")
    conn.execute(
        "UPDATE memories SET updated_at = '2020-01-01T00:00:00+00:00' "
        "WHERE key = 'user.preference.old'"
    )
    conn.commit()
    archived = run_stale_sweep(conn, stale_days=45)
    assert archived == ["mortimer.build.status"]
    pref = conn.execute(
        "SELECT archived_at FROM memories WHERE key='user.preference.old'"
    ).fetchone()
    assert pref["archived_at"] is None


# --- A2/A5: classification parsing (pure) ---------------------------------


def test_contradiction_verdict_unparseable_is_distinct():
    result = _parse_classification("not json at all")
    assert result == {"pairs": {}, "audiences": {}}

    result2 = _parse_classification(json.dumps({
        "pairs": [{"a": "k1", "b": "k2", "verdict": "maybe-ish"}],
        "audiences": [{"key": "k3", "audience": "somewhere-else"}],
    }))
    assert result2["pairs"][frozenset(("k1", "k2"))] == "distinct"
    assert result2["audiences"]["k3"] == "interaction"


def test_contradiction_verdict_parses_valid_json():
    result = _parse_classification(json.dumps({
        "pairs": [{"a": "k1", "b": "k2", "verdict": "contradictory"}],
        "audiences": [{"key": "k3", "audience": "task-rule"}],
    }))
    assert result["pairs"][frozenset(("k1", "k2"))] == "contradictory"
    assert result["audiences"]["k3"] == "task-rule"


# --- A2: pair selection + "classified once" cache -------------------------


def test_a_pair_is_classified_once(conn):
    _fact(conn, "user.style.a", "Larry wants short terse spoken replies", "preference")
    _fact(conn, "user.style.b", "Larry wants long detailed robust replies", "preference")
    conn.commit()
    pairs = _select_contradiction_pairs(conn)
    assert len(pairs) == 1
    a, b = pairs[0]
    from jarvis.memory_sweep import _queue_if_new
    _queue_if_new(conn, "contradiction", [a["key"], b["key"]], "test")
    conn.commit()
    pairs_again = _select_contradiction_pairs(conn)
    assert pairs_again == []


def test_dismissed_reviews_do_not_requeue(conn):
    _fact(conn, "user.style.a", "Larry wants short terse spoken replies", "preference")
    _fact(conn, "user.style.b", "Larry wants long detailed robust replies", "preference")
    conn.commit()
    pairs = _select_contradiction_pairs(conn)
    a, b = pairs[0]
    from jarvis.memory_sweep import _queue_if_new
    _queue_if_new(conn, "contradiction", [a["key"], b["key"]], "test")
    conn.commit()
    review = list_open_reviews(conn)[0]
    resolve_review(conn, review["id"], "dismiss")
    conn.commit()
    assert list_open_reviews(conn) == []
    assert _select_contradiction_pairs(conn) == []  # never re-queued


# --- A5: audience classification application -------------------------------


def test_identity_audience_is_always_interaction(conn):
    _fact(conn, "user.location", "Spartanburg current device location rule", "identity")
    conn.commit()
    candidates = _select_audience_candidates(conn)
    applied = _apply_classification(
        conn, [], {}, candidates, {"user.location": "task-rule"},
    )
    assert applied["identity_forced"] == 1
    row = conn.execute(
        "SELECT audience FROM memories WHERE key='user.location'"
    ).fetchone()
    assert row["audience"] == "interaction"
    assert list_open_reviews(conn) == []  # never queued — mechanical override


def test_task_rule_verdict_queues_never_acts(conn):
    _fact(conn, "user.preference.git_workflow",
          "always run tests before committing changes", "preference")
    conn.commit()
    candidates = _select_audience_candidates(conn)
    applied = _apply_classification(
        conn, [], {}, candidates,
        {"user.preference.git_workflow": "task-rule"},
    )
    assert applied["task_rule_queued"] == 1
    row = conn.execute(
        "SELECT audience, archived_at FROM memories "
        "WHERE key='user.preference.git_workflow'"
    ).fetchone()
    assert row["audience"] is None       # not acted on automatically
    assert row["archived_at"] is None    # not archived either
    reviews = list_open_reviews(conn)
    assert len(reviews) == 1
    assert reviews[0]["kind"] == "audience"


def test_unclassified_audience_reaches_the_prompt(conn):
    """A5 fail-open: a fact with audience IS NULL (never classified, or
    classified 'task-rule'/'implemented' and therefore left NULL) still
    renders — silently dropping a real preference is the worse error."""
    _fact(conn, "user.preference.terse", "Larry wants terse spoken replies", "preference")
    conn.commit()
    text = render_memory_context(conn)
    assert "user.preference.terse" in text


def test_interaction_audience_reaches_the_prompt(conn):
    _fact(conn, "user.preference.terse", "Larry wants terse spoken replies", "preference")
    conn.execute(
        "UPDATE memories SET audience='interaction' WHERE key='user.preference.terse'"
    )
    conn.commit()
    text = render_memory_context(conn)
    assert "user.preference.terse" in text


# --- kill switch + entry point ---------------------------------------------


def test_sweep_disabled_touches_nothing(conn, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_SWEEP_ENABLED", "false")
    assert enabled() is False
    _fact(conn, "user.style.a", "Larry prefers short concise replies always", "preference")
    _fact(conn, "user.style.b", "Larry prefers short concise replies every time always", "preference")
    conn.commit()

    import asyncio

    result = asyncio.run(run_sweep(db_path=None))
    assert result == {"enabled": False}
    live = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE archived_at IS NULL"
    ).fetchone()["n"]
    assert live == 2  # nothing touched


@pytest.mark.asyncio
async def test_run_sweep_end_to_end_with_fake_model(conn, monkeypatch, tmp_path):
    db_path = tmp_path / "sweep.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    real_conn = get_conn(db_path)
    run_migrations(real_conn)
    _fact(real_conn, "user.style.a", "Larry prefers short concise replies always", "preference")
    _fact(real_conn, "user.style.b", "Larry prefers short concise replies every time indeed", "preference")
    real_conn.commit()
    real_conn.close()

    class _FakeSettings:
        openai_api_key = "k"
        openai_base_url = "http://unused"
        openai_model = "fake-model"

    payload = json.dumps({"pairs": [], "audiences": []})
    result = await run_sweep(
        db_path=str(db_path), settings=_FakeSettings(), client_factory=_factory(payload),
    )
    assert result.get("enabled") is not False
    assert "archived" in result
