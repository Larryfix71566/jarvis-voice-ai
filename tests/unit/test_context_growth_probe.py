"""context_growth_probe unit tests (plan Phase 6, step 6a)."""

from jarvis.db import get_conn, now_iso, run_migrations
from scripts.context_growth_probe import (
    _approx_system_prompt,
    list_sessions,
    measure_session,
    render_table,
)


def _seed(db_path, session_id, turns):
    with get_conn(db_path) as conn:
        for role, content in turns:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, now_iso()),
            )


def test_approx_system_prompt_renders_without_error():
    prompt = _approx_system_prompt()
    assert "Mortimer" in prompt
    assert "scheduler" in prompt.lower()
    assert len(prompt) > 500


def test_measure_session_cumulative_grows_monotonically(tmp_path):
    db = tmp_path / "growth.db"
    run_migrations(get_conn(db))
    _seed(db, "s1", [
        ("user", "hello"),
        ("assistant", "hi there, how can I help"),
        ("user", "what time is it"),
        ("assistant", "it is three PM"),
    ])

    curve = measure_session("s1", str(db))
    assert len(curve) == 4
    cumulative = [row["cumulative_tokens"] for row in curve]
    assert cumulative == sorted(cumulative)  # strictly non-decreasing
    assert cumulative[0] > 0  # system prompt baseline included
    assert cumulative[-1] > cumulative[0]  # actually grew


def test_measure_session_includes_system_prompt_baseline(tmp_path):
    db = tmp_path / "growth2.db"
    run_migrations(get_conn(db))
    _seed(db, "s1", [("user", "hi")])

    curve = measure_session("s1", str(db))
    system_baseline = curve[0]["cumulative_tokens"] - curve[0]["turn_tokens"]
    assert system_baseline > 100  # the real prompt is not tiny


def test_measure_session_empty_for_unknown_session(tmp_path):
    db = tmp_path / "growth3.db"
    run_migrations(get_conn(db))
    assert measure_session("nonexistent", str(db)) == []


def test_list_sessions_orders_by_turn_count(tmp_path):
    db = tmp_path / "growth4.db"
    run_migrations(get_conn(db))
    _seed(db, "small", [("user", "a"), ("assistant", "b")])
    _seed(db, "big", [("user", "a"), ("assistant", "b"), ("user", "c"),
                      ("assistant", "d")])

    sessions = list_sessions(str(db))
    assert sessions[0]["session_id"] == "big"
    assert sessions[0]["n"] == 4
    assert sessions[1]["session_id"] == "small"
    assert sessions[1]["n"] == 2


def test_render_table_contains_all_turns():
    curve = [
        {"turn": 1, "role": "user", "turn_tokens": 2, "cumulative_tokens": 10,
         "content_preview": "hi"},
        {"turn": 2, "role": "assistant", "turn_tokens": 5, "cumulative_tokens": 15,
         "content_preview": "hello there"},
    ]
    table = render_table(curve)
    assert "hi" in table
    assert "hello there" in table
    assert "10" in table
    assert "15" in table
