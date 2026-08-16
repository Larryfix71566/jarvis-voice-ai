"""Unit tests for jarvis/procedures.py
(MORTIMER_MEMORY_PROCEDURES_PLAN.md Part B, D9-D24, §7 verification).
"""

import json

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.procedures import (
    MAX_SOURCE_RUN_IDS,
    PROCEDURE_DEPRECATE_AFTER,
    PROCEDURE_PROMOTE_AFTER,
    _calibrate_populations,
    _cli_main,
    _explain,
    _load_successful_runs,
    _percentile,
    _pick_threshold,
    _tokens,
    learn_from_run,
    match_procedure,
)
from tests.unit.test_memory import _factory


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "proc.db"))
    c = get_conn(tmp_path / "proc.db")
    run_migrations(c)
    yield c
    c.close()


class _FakeSettings:
    openai_api_key = "k"
    openai_base_url = "http://unused"
    openai_model = "fake-model"
    jarvis_procedures_enabled = True


@pytest.fixture()
def enabled_settings(monkeypatch):
    settings = _FakeSettings()
    import jarvis.config as config_module
    monkeypatch.setattr(config_module, "load_settings", lambda: settings)
    return settings


@pytest.fixture()
def disabled_settings(monkeypatch):
    settings = _FakeSettings()
    settings.jarvis_procedures_enabled = False
    import jarvis.config as config_module
    monkeypatch.setattr(config_module, "load_settings", lambda: settings)
    return settings


def _insert_run(conn, run_id, agent, task, status, session_id="s1"):
    now = now_iso()
    conn.execute(
        "INSERT INTO agent_runs (run_id, session_id, agent, display_name, "
        "task, status, started_at, ended_at, latency_ms, tool_count, error, "
        "reply_preview, payload_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 10, "
        "0, ?, '', NULL)",
        (run_id, session_id, agent, agent.title(), task, status, now, now,
         None if status == "ok" else "FAILED: x"),
    )
    conn.commit()


def _insert_procedure(
    conn, agent, label, description, status="active", success=0, failure=0,
    source_run_ids=None, task_tokens=None,
):
    """`task_tokens` defaults to WEATHER_TASK's own tokens (D21: this is
    what a real candidate row created from WEATHER_TASK would have stored
    at creation time) so existing callers that don't pass it still get a
    matchable row. Pass task_tokens='' explicitly to simulate a pre-
    migration-0008 row (D24) — inert by design, never matchable."""
    if task_tokens is None:
        task_tokens = " ".join(sorted(_tokens(WEATHER_TASK)))
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO procedures (agent, label, description, status, "
        "success_count, failure_count, source_run_ids, created_at, "
        "updated_at, task_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (agent, label, description, status, success, failure,
         json.dumps(source_run_ids or []), now, now, task_tokens),
    )
    conn.commit()
    return cur.lastrowid


WEATHER_TASK = "look up the current weather conditions in tokyo japan"
WEATHER_LABEL = "weather lookup"
WEATHER_DESC = "used get_weather to check current weather conditions for a city"


# --- match_procedure ------------------------------------------------------


def test_match_procedure_finds_overlapping_active_row(conn):
    _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active")
    match = match_procedure("analyst", WEATHER_TASK)
    assert match is not None
    assert match["label"] == WEATHER_LABEL


def test_match_procedure_respects_agent_scope(conn):
    _insert_procedure(conn, "scheduler", WEATHER_LABEL, WEATHER_DESC, status="active")
    assert match_procedure("analyst", WEATHER_TASK) is None


def test_match_procedure_default_status_excludes_candidate(conn):
    _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="candidate")
    assert match_procedure("analyst", WEATHER_TASK) is None  # default status="active"


def test_match_procedure_status_none_finds_any_status(conn):
    _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="deprecated")
    match = match_procedure("analyst", WEATHER_TASK, status=None)
    assert match is not None


def test_match_procedure_unrelated_task_no_match(conn):
    _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active")
    assert match_procedure("analyst", "commit and push the repository changes") is None


def test_match_procedure_never_raises_on_empty_task(conn):
    _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active")
    assert match_procedure("analyst", "") is None


# --- learn_from_run: candidate creation (D14 step 4/5, D16) ---------------


async def test_new_successful_run_no_match_creates_candidate(conn, enabled_settings):
    _insert_run(conn, "run-1", "analyst", WEATHER_TASK, "ok")
    payload = json.dumps({"label": WEATHER_LABEL, "description": WEATHER_DESC})

    await learn_from_run("run-1", "analyst", client_factory=_factory(payload))

    rows = conn.execute("SELECT * FROM procedures").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "candidate"
    assert row["success_count"] == 1
    assert row["failure_count"] == 0
    assert json.loads(row["source_run_ids"]) == ["run-1"]


async def test_failed_run_never_creates_candidate(conn, enabled_settings):
    _insert_run(conn, "run-2", "analyst", WEATHER_TASK, "failed")

    await learn_from_run("run-2", "analyst", client_factory=_factory("unused"))

    assert conn.execute("SELECT COUNT(*) c FROM procedures").fetchone()["c"] == 0


async def test_timeout_run_never_creates_candidate(conn, enabled_settings):
    _insert_run(conn, "run-3", "analyst", WEATHER_TASK, "timeout")

    await learn_from_run("run-3", "analyst", client_factory=_factory("unused"))

    assert conn.execute("SELECT COUNT(*) c FROM procedures").fetchone()["c"] == 0


async def test_unparseable_llm_output_creates_no_candidate(conn, enabled_settings):
    _insert_run(conn, "run-4", "analyst", WEATHER_TASK, "ok")

    await learn_from_run("run-4", "analyst", client_factory=_factory("not json"))

    assert conn.execute("SELECT COUNT(*) c FROM procedures").fetchone()["c"] == 0


# --- learn_from_run: reinforcement + promotion/deprecation (D14/D15) -----


async def test_three_net_successes_promote_candidate_to_active(conn, enabled_settings):
    pid = _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="candidate",
        success=1, failure=0, source_run_ids=["run-0"],
    )
    for i, run_id in enumerate(["run-1", "run-2"], start=1):
        _insert_run(conn, run_id, "analyst", WEATHER_TASK, "ok")
        await learn_from_run(run_id, "analyst", client_factory=_factory("unused"))

    row = conn.execute("SELECT * FROM procedures WHERE id = ?", (pid,)).fetchone()
    assert row["success_count"] == PROCEDURE_PROMOTE_AFTER
    assert row["status"] == "active"


async def test_three_net_failures_deprecate_active_procedure(conn, enabled_settings):
    # D15: deprecation requires failure_count >= PROCEDURE_DEPRECATE_AFTER
    # AND failure_count > success_count — an equal tally must not deprecate,
    # so this starts with fewer successes than the failures about to land.
    pid = _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
        success=2, failure=0, source_run_ids=["run-0"],
    )
    for i, run_id in enumerate(["run-1", "run-2", "run-3"], start=1):
        _insert_run(conn, run_id, "analyst", WEATHER_TASK, "failed")
        await learn_from_run(run_id, "analyst", client_factory=_factory("unused"))

    row = conn.execute("SELECT * FROM procedures WHERE id = ?", (pid,)).fetchone()
    assert row["failure_count"] == PROCEDURE_DEPRECATE_AFTER
    assert row["status"] == "deprecated"
    # A deprecated procedure must stop being returned to the retrieval path.
    assert match_procedure("analyst", WEATHER_TASK, status="active") is None


async def test_deprecated_row_reinforced_without_status_reviving(conn, enabled_settings):
    pid = _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="deprecated",
        success=2, failure=4, source_run_ids=["run-0"],
    )
    _insert_run(conn, "run-1", "analyst", WEATHER_TASK, "ok")

    await learn_from_run("run-1", "analyst", client_factory=_factory("unused"))

    rows = conn.execute("SELECT * FROM procedures").fetchall()
    assert len(rows) == 1  # no duplicate candidate spawned for the same task shape
    row = conn.execute("SELECT * FROM procedures WHERE id = ?", (pid,)).fetchone()
    assert row["success_count"] == 3
    assert row["status"] == "deprecated"  # never auto-revives


async def test_source_run_ids_capped_oldest_dropped(conn, enabled_settings):
    pid = _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
        success=1, failure=0, source_run_ids=["run-seed"],
    )
    for i in range(MAX_SOURCE_RUN_IDS + 5):
        run_id = f"run-{i}"
        _insert_run(conn, run_id, "analyst", WEATHER_TASK, "ok")
        await learn_from_run(run_id, "analyst", client_factory=_factory("unused"))

    row = conn.execute("SELECT * FROM procedures WHERE id = ?", (pid,)).fetchone()
    ids = json.loads(row["source_run_ids"])
    assert len(ids) == MAX_SOURCE_RUN_IDS
    assert "run-seed" not in ids  # oldest dropped first
    assert ids[-1] == f"run-{MAX_SOURCE_RUN_IDS + 4}"  # most recent kept


# --- kill switch (D20) -----------------------------------------------------


async def test_procedures_enabled_false_learn_from_run_is_noop(conn, disabled_settings):
    _insert_run(conn, "run-1", "analyst", WEATHER_TASK, "ok")

    await learn_from_run("run-1", "analyst", client_factory=_factory(
        json.dumps({"label": WEATHER_LABEL, "description": WEATHER_DESC})
    ))

    assert conn.execute("SELECT COUNT(*) c FROM procedures").fetchone()["c"] == 0


async def test_learn_from_run_missing_run_id_is_noop(conn, enabled_settings):
    await learn_from_run("does-not-exist", "analyst", client_factory=_factory("unused"))
    assert conn.execute("SELECT COUNT(*) c FROM procedures").fetchone()["c"] == 0


# --- FTS5 UPDATE path (risk table: procedures_fts trigger correctness) ---


# --- D21/D22: task_tokens matching + symmetric score -----------------------


def test_pre_migration_row_with_empty_task_tokens_is_inert(conn):
    """D24: a row from before migration 0008 has task_tokens == '' and
    must never match — it is intentionally inert, not backfilled."""
    _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
        task_tokens="",
    )
    assert match_procedure("analyst", WEATHER_TASK) is None
    assert match_procedure("analyst", WEATHER_TASK, status=None) is None


def test_match_scores_against_task_tokens_not_label_description(conn):
    """D21: FTS recall still runs against label+description (unchanged —
    it only needs to generate a cheap candidate set), but the final
    accept/reject score is computed from the candidate's stored
    task_tokens, not from label+description token overlap. This candidate
    has just enough label/description overlap ("weather") to be recalled
    by FTS, but its label/description otherwise share almost nothing with
    the task — under the old (pre-D21) label+description scoring this
    would have scored far below threshold. Its task_tokens, however, is a
    near-exact match, so it must be found."""
    _insert_procedure(
        conn, "analyst", "weather", "some other completely different phrasing",
        status="active", task_tokens="weather tokyo current conditions look",
    )
    match = match_procedure("analyst", WEATHER_TASK)
    assert match is not None


def test_label_description_overlap_alone_is_not_enough(conn):
    """The inverse: label/description overlapping the task is no longer
    sufficient on its own if task_tokens does not overlap."""
    _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
        task_tokens="commit push repository branch",
    )
    assert match_procedure("analyst", WEATHER_TASK) is None


def test_symmetric_score_longer_task_containing_shorter_candidate(conn):
    """D22: a longer/more verbose task that fully contains a shorter
    candidate's tokens must score 1.0 (containment), not be penalised for
    the extra words the old asymmetric denominator would have divided by."""
    _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
        task_tokens="weather tokyo",
    )
    verbose_task = ("could you please look up the weather tokyo forecast "
                     "for me sometime this afternoon if you get a chance")
    match = match_procedure("analyst", verbose_task)
    assert match is not None


async def test_update_then_requery_through_fts_still_matches(conn, enabled_settings):
    """Risk table: procedures_fts's UPDATE trigger must keep the index in
    sync, not just INSERT — a counter-only UPDATE (no label/description
    change) must not break subsequent matching."""
    _insert_procedure(
        conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
        success=1, failure=0, source_run_ids=["run-0"],
    )
    _insert_run(conn, "run-1", "analyst", WEATHER_TASK, "ok")
    await learn_from_run("run-1", "analyst", client_factory=_factory("unused"))

    # Still findable after the UPDATE that just ran inside learn_from_run.
    match = match_procedure("analyst", WEATHER_TASK)
    assert match is not None
    assert match["success_count"] == 2


# --- D23: --explain / --calibrate CLI --------------------------------------


class TestPercentile:
    def test_single_value(self):
        assert _percentile([0.5], 50) == 0.5
        assert _percentile([0.5], 90) == 0.5

    def test_matches_known_values(self):
        data = [1, 2, 3, 4, 5]
        assert _percentile(data, 0) == 1
        assert _percentile(data, 50) == 3
        assert _percentile(data, 100) == 5

    def test_interpolates(self):
        data = [1, 2, 3, 4]
        # (n-1)*pct/100 = 3*0.25 = 0.75 -> between index 0 and 1
        assert _percentile(data, 25) == pytest.approx(1.75)


class TestPickThreshold:
    def test_branch1_clean_separation(self):
        matched = [0.9, 0.8, 0.85, 0.95]
        unmatched = [0.1, 0.05, 0.15, 0.2]
        value, branch = _pick_threshold(matched, unmatched)
        assert "branch 1" in branch
        assert 0.20 <= value <= 0.60

    def test_branch2_overlap_midpoint(self):
        matched = [0.3, 0.4, 0.5]
        unmatched = [0.2, 0.35, 0.45]
        value, branch = _pick_threshold(matched, unmatched)
        assert "branch 2" in branch

    def test_branch3_empty_unmatched(self):
        value, branch = _pick_threshold([0.5, 0.6], [])
        assert "branch 3" in branch
        assert value == 0.35

    def test_branch3_empty_matched(self):
        value, branch = _pick_threshold([], [0.5, 0.6])
        assert "branch 3" in branch
        assert value == 0.35

    def test_clamped_to_bounds(self):
        # A branch-1 value below 0.20 or above 0.60 must be clamped.
        value, _ = _pick_threshold([0.99, 0.99, 0.99], [0.01, 0.01, 0.01])
        assert value <= 0.60
        value, _ = _pick_threshold([0.15, 0.16], [0.01, 0.01])
        assert value >= 0.20


class TestCalibratePopulations:
    def _run(self, run_id, agent, task, tools):
        return {"run_id": run_id, "agent": agent, "task": task, "tools": tools}

    def test_identical_tool_sequence_is_matched(self):
        runs = [
            self._run("r1", "analyst", WEATHER_TASK, ["get_weather"]),
            self._run("r2", "analyst", "weather forecast for osaka", ["get_weather"]),
        ]
        matched, unmatched = _calibrate_populations(runs)
        assert len(matched) == 1
        assert unmatched == []

    def test_disjoint_tool_sequence_is_unmatched(self):
        runs = [
            self._run("r1", "analyst", WEATHER_TASK, ["get_weather"]),
            self._run("r2", "analyst", "commit changes", ["git_status", "prepare_commit"]),
        ]
        matched, unmatched = _calibrate_populations(runs)
        assert matched == []
        assert len(unmatched) == 1

    def test_partial_tool_overlap_is_neither_population(self):
        runs = [
            self._run("r1", "analyst", "a", ["get_weather", "web_search"]),
            self._run("r2", "analyst", "b", ["web_search", "get_weather"]),  # different order
        ]
        matched, unmatched = _calibrate_populations(runs)
        assert matched == []  # order differs, not identical sequence
        assert unmatched == []  # shares 'web_search', not disjoint either

    def test_empty_tool_sequences_excluded_from_both_populations(self):
        runs = [
            self._run("r1", "analyst", "a", []),
            self._run("r2", "analyst", "b", []),
        ]
        matched, unmatched = _calibrate_populations(runs)
        assert matched == []
        assert unmatched == []

    def test_different_agents_never_paired(self):
        runs = [
            self._run("r1", "analyst", WEATHER_TASK, ["get_weather"]),
            self._run("r2", "scheduler", WEATHER_TASK, ["get_weather"]),
        ]
        matched, unmatched = _calibrate_populations(runs)
        assert matched == []
        assert unmatched == []


class TestLoadSuccessfulRuns:
    def test_reads_task_agent_and_tool_sequence_from_payload(self, conn, tmp_path):
        payload_rel = "logs/agents/2026-08-14/r1.jsonl"
        payload_file = tmp_path / payload_rel
        payload_file.parent.mkdir(parents=True)
        payload_file.write_text(
            "\n".join(json.dumps(r) for r in [
                {"type": "run_start", "task": WEATHER_TASK},
                {"type": "tool_call", "tool": "get_weather"},
                {"type": "tool_result", "tool": "get_weather", "ok": True},
                {"type": "run_end", "status": "ok"},
            ]) + "\n"
        )
        now = now_iso()
        conn.execute(
            "INSERT INTO agent_runs (run_id, agent, display_name, task, "
            "status, started_at, tool_count, payload_path) VALUES "
            "('r1', 'analyst', 'Analyst', ?, 'ok', ?, 1, ?)",
            (WEATHER_TASK, now, payload_rel),
        )
        conn.commit()

        runs = _load_successful_runs(db_path=tmp_path / "proc.db", root=tmp_path)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "r1"
        assert runs[0]["agent"] == "analyst"
        assert runs[0]["task"] == WEATHER_TASK
        assert runs[0]["tools"] == ["get_weather"]

    def test_failed_runs_excluded(self, conn, tmp_path):
        now = now_iso()
        conn.execute(
            "INSERT INTO agent_runs (run_id, agent, display_name, task, "
            "status, started_at, tool_count, payload_path) VALUES "
            "('r1', 'analyst', 'Analyst', 'x', 'failed', ?, 0, NULL)",
            (now,),
        )
        conn.commit()
        runs = _load_successful_runs(db_path=tmp_path / "proc.db", root=tmp_path)
        assert runs == []

    def test_missing_payload_file_degrades_to_empty_tools(self, conn, tmp_path):
        now = now_iso()
        conn.execute(
            "INSERT INTO agent_runs (run_id, agent, display_name, task, "
            "status, started_at, tool_count, payload_path) VALUES "
            "('r1', 'analyst', 'Analyst', 'x', 'ok', ?, 0, "
            "'logs/agents/2026-08-14/gone.jsonl')",
            (now,),
        )
        conn.commit()
        runs = _load_successful_runs(db_path=tmp_path / "proc.db", root=tmp_path)
        assert len(runs) == 1
        assert runs[0]["tools"] == []


class TestExplainCli:
    def test_explain_prints_score_and_shared_tokens(self, conn, capsys):
        _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active")
        _explain(None, WEATHER_TASK, db_path=None)
        out = capsys.readouterr().out
        assert "task tokens" in out
        assert "score=" in out
        assert "PASS" in out

    def test_explain_scopes_to_agent(self, conn, capsys):
        _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active")
        _insert_procedure(conn, "scheduler", WEATHER_LABEL, WEATHER_DESC, status="active")
        _explain("scheduler", WEATHER_TASK, db_path=None)
        out = capsys.readouterr().out
        assert "agent=scheduler" in out
        assert "agent=analyst" not in out

    def test_explain_no_procedures(self, conn, capsys):
        _explain(None, WEATHER_TASK, db_path=None)
        out = capsys.readouterr().out
        assert "no stored procedures" in out

    def test_explain_flags_empty_task_tokens_as_pre_migration(self, conn, capsys):
        _insert_procedure(
            conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active",
            task_tokens="",
        )
        _explain(None, WEATHER_TASK, db_path=None)
        out = capsys.readouterr().out
        assert "pre-migration-0008" in out


class TestCliMain:
    def test_explain_flag_dispatches(self, conn, capsys):
        _insert_procedure(conn, "analyst", WEATHER_LABEL, WEATHER_DESC, status="active")
        rc = _cli_main(["--explain", WEATHER_TASK])
        assert rc == 0
        assert "task tokens" in capsys.readouterr().out

    def test_no_args_prints_help_and_returns_nonzero(self, capsys):
        rc = _cli_main([])
        assert rc == 1
        assert "usage" in capsys.readouterr().out.lower()

    def test_calibrate_flag_dispatches(self, conn, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        rc = _cli_main(["--calibrate"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MATCHED" in out
        assert "UNMATCHED" in out
        assert "selected PROCEDURE_MATCH_THRESHOLD" in out
