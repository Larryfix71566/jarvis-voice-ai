"""Unit tests for jarvis/memory_sweep.py
(MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A1/A2/A3/A4/A5)."""

from __future__ import annotations

import json

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.memory import (
    MAX_CONTEXT_CHARS,
    MAX_PREFERENCE_FACTS,
    MAX_PROJECT_FACTS,
    archive_fact,
    render_memory_context,
    search_facts,
    upsert_fact,
)
from jarvis.memory_sweep import (
    CAPACITY_CAPS,
    SWEEP_MAX_ARCHIVES,
    _apply_classification,
    _parse_classification,
    _select_audience_candidates,
    _select_contradiction_pairs,
    enabled,
    list_open_reviews,
    resolve_review,
    run_auto_consolidation,
    run_capacity_enforcement,
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


# --- A1.5: capacity enforcement ladder (MORTIMER_MEMORY_CAPACITY_PLAN.md) --


def _unique_tokens_fact(conn, key, tier, i, n_tokens=6):
    """A fact guaranteed to share NO tokens with any other fact produced
    by this helper (every token embeds `i`), so propose_merges can never
    cluster it with anything — used to fill a tier past its cap without
    ever triggering rung (b)'s merge path or a real model call."""
    content = " ".join(f"tok{i}_{j}" for j in range(n_tokens))
    _fact(conn, key, content, tier)


async def test_enforcement_reaches_cap_without_llm(conn, monkeypatch):
    """M3(c) / superseded by W7 for `preference` specifically
    (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — a key-less/model-less
    environment still lands EXACTLY at the cap via mechanical age-out for
    `project`, the backstop that holds M1's invariant with zero API
    dependency. This test now exercises `project`, not `preference`: W7
    changed preference's behavior in this exact scenario (see
    test_preference_left_over_cap_when_merge_rung_unavailable below) because
    mechanical age-out is blind to importance and a live regression showed
    it silently archiving a stated user preference. `project` facts are
    largely re-derivable (git log, repo state) and keep the old backstop."""
    def _raise():
        raise RuntimeError("no key configured")

    monkeypatch.setattr("jarvis.config.load_settings", _raise)

    # A real mergeable cluster (would satisfy rung (b) if a model existed).
    _fact(conn, "project.mortimer.conciseness", "Status: short summaries", "project")
    _fact(conn, "project.mortimer.verbosity",
          "Status: short, terse, direct summaries with minimal detail",
          "project")
    # Fill the rest of the tier with facts that can never cluster.
    n_fill = MAX_PROJECT_FACTS + 5
    for i in range(n_fill):
        _unique_tokens_fact(conn, f"project.fill{i:02d}", "project", i)
    conn.commit()

    report = await run_capacity_enforcement(conn, ignore_boot_cap=True)

    assert report["project"]["after"] == MAX_PROJECT_FACTS
    assert report["project"]["merged"] == 0
    assert report["project"]["aged_out"] > 0
    live = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='fact' "
        "AND archived_at IS NULL AND COALESCE(tier,'project')='project'"
    ).fetchone()["n"]
    assert live == MAX_PROJECT_FACTS


async def test_preference_left_over_cap_when_merge_rung_unavailable(conn, monkeypatch, caplog):
    """W7 — the fix for the D0 regression: with no key/model available and
    no mergeable cluster, the preference tier is left OVER cap rather than
    mechanically aging out a fact that might be a stated preference.
    Nothing is archived; a WARNING names the tier and the overage."""
    def _raise():
        raise RuntimeError("no key configured")

    monkeypatch.setattr("jarvis.config.load_settings", _raise)

    n_fill = MAX_PREFERENCE_FACTS + 5
    for i in range(n_fill):
        _unique_tokens_fact(conn, f"user.preference.fill{i:02d}", "preference", i)
    conn.commit()

    import logging
    with caplog.at_level(logging.WARNING, logger="jarvis.memory_sweep"):
        report = await run_capacity_enforcement(conn, ignore_boot_cap=True)

    assert report["preference"]["aged_out"] == 0
    assert report["preference"]["merged"] == 0
    assert report["preference"]["after"] == n_fill  # untouched, still over cap
    assert report["preference"]["after"] > report["preference"]["cap"]
    live = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='fact' "
        "AND archived_at IS NULL AND COALESCE(tier,'project')='preference'"
    ).fetchone()["n"]
    assert live == n_fill
    assert any(
        "memory_enforce_preference_left_over_cap" in r.message for r in caplog.records
    )


async def test_preference_still_merges_when_model_available(conn):
    """W7 does not disable rung (b) for preference — merging still runs
    normally, and only the FALLBACK to mechanical age-out is suppressed."""
    _fact(conn, "user.preference.conciseness", "Larry prefers short answers", "preference")
    _fact(conn, "user.preference.verbosity",
          "Larry prefers short, terse, direct answers with minimal detail",
          "preference")
    n_fill = MAX_PREFERENCE_FACTS - 1
    for i in range(n_fill):
        _unique_tokens_fact(conn, f"user.preference.fill{i:02d}", "preference", i)
    conn.commit()

    rewritten = "Larry prefers short, terse, direct spoken answers."
    report = await run_capacity_enforcement(
        conn, client_factory=_factory(rewritten), ignore_boot_cap=True,
    )

    assert report["preference"]["merged"] == 1
    assert report["preference"]["aged_out"] == 0
    assert report["preference"]["after"] == MAX_PREFERENCE_FACTS


async def test_enforcement_never_touches_identity(conn):
    """M3: identity is never a target — CAPACITY_CAPS omits it entirely,
    over any size."""
    assert "identity" not in CAPACITY_CAPS
    for i in range(50):
        _unique_tokens_fact(conn, f"user.identity.item{i:02d}", "identity", i)
    conn.commit()

    await run_capacity_enforcement(conn, ignore_boot_cap=True)

    live = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='fact' "
        "AND archived_at IS NULL AND COALESCE(tier,'project')='identity'"
    ).fetchone()["n"]
    assert live == 50


async def test_merge_archives_sources_with_became(conn):
    """M3(b): reversibility — merge sources are archived `became=merged:
    <kept_key>`, never deleted, and the survivor's content is the model's
    rewrite."""
    _fact(conn, "user.preference.conciseness", "Larry prefers short answers", "preference")
    _fact(conn, "user.preference.verbosity",
          "Larry prefers short, terse, direct answers with minimal detail",
          "preference")
    # One fact over cap, via the mergeable pair above.
    n_fill = MAX_PREFERENCE_FACTS - 1
    for i in range(n_fill):
        _unique_tokens_fact(conn, f"user.preference.fill{i:02d}", "preference", i)
    conn.commit()

    rewritten = "Larry prefers short, terse, direct spoken answers."
    report = await run_capacity_enforcement(
        conn, client_factory=_factory(rewritten), ignore_boot_cap=True,
    )

    assert report["preference"]["merged"] == 1
    assert report["preference"]["after"] == MAX_PREFERENCE_FACTS

    rows = {
        r["key"]: dict(r)
        for r in conn.execute(
            "SELECT key, content, archived_at, became FROM memories "
            "WHERE key IN ('user.preference.conciseness', "
            "'user.preference.verbosity')"
        ).fetchall()
    }
    archived_rows = [r for r in rows.values() if r["archived_at"] is not None]
    survivor_rows = [r for r in rows.values() if r["archived_at"] is None]
    assert len(archived_rows) == 1
    assert len(survivor_rows) == 1
    assert archived_rows[0]["became"].startswith("merged:")
    assert survivor_rows[0]["content"] == rewritten


async def test_system_tier_archives_on_sight(conn):
    """M4: system's live cap is 0 — every live system fact is archived,
    no merge rung involved (a merge would need a model call for facts the
    prompt never sees)."""
    for i in range(4):
        _unique_tokens_fact(conn, f"mortimer.config.item{i:02d}", "system", i)
    conn.commit()

    report = await run_capacity_enforcement(conn, ignore_boot_cap=True)

    assert report["system"]["before"] == 4
    assert report["system"]["after"] == 0
    assert report["system"]["merged"] == 0
    assert report["system"]["aged_out"] == 4
    rows = conn.execute(
        "SELECT became FROM memories WHERE kind='fact' "
        "AND COALESCE(tier,'project')='system'"
    ).fetchall()
    assert all(r["became"] == "aged-out" for r in rows)


async def test_enforce_cli_ignores_boot_archive_cap(conn):
    """M5: ignore_boot_cap=True (the --enforce CLI path) drains a tier
    fully in one pass, past SWEEP_MAX_ARCHIVES — the per-boot cap that
    protects an UNATTENDED sweep does not apply to an explicit, attended
    invocation."""
    n_over = SWEEP_MAX_ARCHIVES + 10  # comfortably past the boot cap
    for i in range(MAX_PROJECT_FACTS + n_over):
        _unique_tokens_fact(conn, f"project.item{i:03d}", "project", i)
    conn.commit()

    report = await run_capacity_enforcement(conn, ignore_boot_cap=True)

    assert report["project"]["aged_out"] > SWEEP_MAX_ARCHIVES
    assert report["project"]["after"] == MAX_PROJECT_FACTS


async def test_full_store_fits_prompt_budget(conn, caplog):
    """M1/M2: a store with every capped tier sitting exactly AT its cap
    (identity uncapped, sized realistically) renders with ZERO facts
    dropped — the invariant this whole plan exists to hold."""
    for i in range(8):
        _fact(conn, f"user.identity.item{i:02d}", "x" * 50, "identity")
    for i in range(MAX_PREFERENCE_FACTS):
        _fact(conn, f"user.preference.item{i:02d}", "x" * 50, "preference")
    for i in range(MAX_PROJECT_FACTS):
        _fact(conn, f"project.item{i:02d}", "x" * 50, "project")
    conn.commit()

    rendered = render_memory_context(conn)
    lines = [l for l in rendered.split("\n") if l.startswith("- ")]
    assert len(lines) == 8 + MAX_PREFERENCE_FACTS + MAX_PROJECT_FACTS
    assert "memory_context_facts_dropped" not in caplog.text
    assert len(rendered) <= MAX_CONTEXT_CHARS + 100  # slack for the summary line


def test_memory_search_finds_archived(conn):
    """M6: the recall path for demoted facts — an archived fact (merged
    or aged out, never deleted) is still fully searchable by key/content
    substring."""
    upsert_fact(conn, "user.preference.old_thing", "Larry liked the old dashboard layout", "s1")
    conn.commit()
    archive_fact(conn, "user.preference.old_thing", "aged-out")
    conn.commit()

    live_hits = search_facts(conn, "dashboard")
    assert len(live_hits) == 1
    assert live_hits[0]["key"] == "user.preference.old_thing"
    assert live_hits[0]["archived"] is True

    key_hits = search_facts(conn, "old_thing")
    assert any(r["key"] == "user.preference.old_thing" for r in key_hits)


async def test_enforcement_queues_nothing_for_plain_overflow(conn):
    """M7: capacity is arithmetic, not judgment — plain over-cap overflow
    with no mergeable cluster is aged out silently, never queued for
    Larry (contrast with A1's mixed-content-hazard queue, which this
    rung never touches)."""
    for i in range(MAX_PROJECT_FACTS + 6):
        _unique_tokens_fact(conn, f"project.item{i:02d}", "project", i)
    conn.commit()

    await run_capacity_enforcement(conn, ignore_boot_cap=True)

    assert list_open_reviews(conn) == []


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
