"""Unit tests for jarvis/memory.py (upgrade plan U2.5)."""

import json
import os

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.memory import (
    EMPTY_CONTEXT,
    _parse_update,
    render_memory_context,
    set_summary,
    update_memory_from_session,
    upsert_fact,
)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "mem.db"))
    c = get_conn(tmp_path / "mem.db")
    run_migrations(c)
    yield c
    c.close()


def _add_turn(conn, session_id, role, content):
    conn.execute(
        "INSERT INTO conversations (session_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?)",
        (session_id, role, content, now_iso()),
    )
    conn.commit()


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeCompletions:
    def __init__(self, payload):
        self._payload = payload

    async def create(self, **_kwargs):
        msg = _FakeMessage(self._payload)
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


class _FakeClient:
    def __init__(self, payload):
        self.chat = type("C", (), {"completions": _FakeCompletions(payload)})()


class _FakeSettings:
    openai_api_key = "k"
    openai_base_url = "http://unused"
    openai_model = "fake-model"


def _factory(payload):
    return lambda _settings: _FakeClient(payload)


# --- storage primitives -------------------------------------------------


def test_upsert_fact_replaces_by_key(conn):
    upsert_fact(conn, "user.name", "Larry", "s1")
    upsert_fact(conn, "user.name", "Lawrence", "s2")
    rows = conn.execute(
        "SELECT content FROM memories WHERE key = 'user.name'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["content"] == "Lawrence"


def test_set_summary_keeps_single_row(conn):
    set_summary(conn, "first", "s1")
    set_summary(conn, "second", "s2")
    rows = conn.execute(
        "SELECT content FROM memories WHERE kind = 'summary'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["content"] == "second"


# --- prompt rendering ---------------------------------------------------


def test_render_empty_context(conn):
    assert render_memory_context(conn) == EMPTY_CONTEXT


def test_render_facts_and_summary(conn):
    upsert_fact(conn, "user.name", "Larry", "s1")
    set_summary(conn, "Discussed the Jarvis upgrade plan.", "s1")
    rendered = render_memory_context(conn)
    assert "- user.name: Larry" in rendered
    assert "Previously discussed: Discussed the Jarvis upgrade plan." in rendered


def test_render_never_raises_on_broken_db(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "gone" / "x.db"))
    broken = get_conn(":memory:")  # no migrations applied -> no table
    assert render_memory_context(broken) == EMPTY_CONTEXT


# --- JSON parsing -------------------------------------------------------


def test_parse_update_strict_json():
    payload = json.dumps(
        {"facts": [{"key": "user.name", "value": "Larry"}], "summary": "s"}
    )
    assert _parse_update(payload) == {
        "facts": [("user.name", "Larry")],
        "observations": [],
        "summary": "s",
    }


def test_parse_update_strips_markdown_fence():
    payload = '```json\n{"facts": [], "summary": "hi"}\n```'
    assert _parse_update(payload) == {
        "facts": [],
        "observations": [],
        "summary": "hi",
    }


def test_parse_update_rejects_garbage():
    assert _parse_update("not json") is None
    assert _parse_update('{"facts": "no", "summary": 1}') is None
    assert _parse_update('[1, 2]') is None


def test_parse_update_drops_malformed_facts():
    payload = json.dumps(
        {
            "facts": [{"key": "a.b", "value": "v"}, {"key": "", "value": "x"},
                      "junk"],
            "summary": "s",
        }
    )
    assert _parse_update(payload)["facts"] == [("a.b", "v")]


# --- end-to-end session update ------------------------------------------


@pytest.mark.asyncio
async def test_update_from_session_applies_facts_and_summary(conn):
    _add_turn(conn, "s1", "user", "My name is Larry.")
    _add_turn(conn, "s1", "assistant", "Noted, Larry.")
    payload = json.dumps(
        {
            "facts": [{"key": "user.name", "value": "Larry"}],
            "summary": "User introduced himself as Larry.",
        }
    )
    ok = await update_memory_from_session(
        _FakeSettings(), "s1", client_factory=_factory(payload)
    )
    assert ok is True
    assert conn.execute(
        "SELECT content FROM memories WHERE key = 'user.name'"
    ).fetchone()["content"] == "Larry"
    assert "Larry" in render_memory_context(conn)


@pytest.mark.asyncio
async def test_update_skips_session_without_user_turns(conn):
    _add_turn(conn, "s2", "assistant", "Hello.")
    ok = await update_memory_from_session(
        _FakeSettings(), "s2", client_factory=_factory("{}")
    )
    assert ok is False
    assert render_memory_context(conn) == EMPTY_CONTEXT


@pytest.mark.asyncio
async def test_update_survives_unparseable_llm_output(conn):
    _add_turn(conn, "s3", "user", "Remember everything!")
    ok = await update_memory_from_session(
        _FakeSettings(), "s3", client_factory=_factory("sure thing boss")
    )
    assert ok is False
    assert render_memory_context(conn) == EMPTY_CONTEXT


@pytest.mark.asyncio
async def test_update_carries_previous_summary_into_prompt(conn):
    set_summary(conn, "Earlier we planned U1.", "s0")
    _add_turn(conn, "s4", "user", "Let's do memory next.")
    captured = {}

    class CapturingCompletions(_FakeCompletions):
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return await super().create(**kwargs)

    class CapturingClient:
        def __init__(self, payload):
            self.chat = type(
                "C", (), {"completions": CapturingCompletions(payload)}
            )()

    payload = json.dumps({"facts": [], "summary": "U1 planned; memory next."})

    def factory(_settings):
        return CapturingClient(payload)

    ok = await update_memory_from_session(
        _FakeSettings(), "s4", client_factory=factory
    )
    assert ok is True
    user_msg = captured["messages"][1]["content"]
    assert "Earlier we planned U1." in user_msg
    assert "memory next" in user_msg


def test_db_path_env_override_used(tmp_path, monkeypatch):
    """render/update must honor JARVIS_DB_PATH like the rest of jarvis."""
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "env.db"))
    run_migrations()
    assert os.path.exists(tmp_path / "env.db")


# --- U2.6: tendency learning (observations -> promotion) -----------------

from jarvis.memory import (  # noqa: E402
    PROMOTE_AFTER,
    add_observation,
    delete_fact,
    promote_observations,
)


def test_observation_does_not_promote_below_threshold(conn):
    add_observation(conn, "user.style.brevity", "asked for a shorter reply", "s1")
    add_observation(conn, "user.style.brevity", "again wanted it brief", "s2")
    assert promote_observations(conn) == []
    assert render_memory_context(conn) == EMPTY_CONTEXT


def test_observation_promotes_at_threshold(conn):
    for i in range(PROMOTE_AFTER):
        add_observation(
            conn, "user.style.brevity", f"preferred brief answer {i}", f"s{i}"
        )
    promoted = promote_observations(conn)
    assert promoted == ["user.style.brevity"]
    rendered = render_memory_context(conn)
    assert "- user.style.brevity:" in rendered


def test_promotion_requires_distinct_sessions(conn):
    for i in range(PROMOTE_AFTER + 2):
        add_observation(conn, "user.style.tone", f"observation {i}", "same-session")
    assert promote_observations(conn) == []


def test_explicit_fact_overrides_stale_observations(conn):
    upsert_fact(conn, "user.style.format", "User said: always bullet lists.", "s9")
    # Older observations (earlier timestamps) must not clobber the explicit fact.
    for i in range(PROMOTE_AFTER):
        add_observation(conn, "user.style.format", f"seemed to like prose {i}", f"s{i}")
    assert promote_observations(conn) == []
    assert conn.execute(
        "SELECT content FROM memories WHERE key = 'user.style.format'"
    ).fetchone()["content"] == "User said: always bullet lists."


def test_delete_fact_forgets_fact_and_evidence(conn):
    upsert_fact(conn, "user.style.brevity", "prefers short", "s1")
    add_observation(conn, "user.style.brevity", "obs", "s1")
    assert delete_fact(conn, "user.style.brevity") is True
    assert conn.execute(
        "SELECT COUNT(*) c FROM memories WHERE key = 'user.style.brevity'"
    ).fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM observations WHERE key = 'user.style.brevity'"
    ).fetchone()["c"] == 0
    assert delete_fact(conn, "user.style.brevity") is False  # already gone


@pytest.mark.asyncio
async def test_update_stores_observations_and_promotes(conn):
    # Two prior sessions of evidence already logged.
    add_observation(conn, "user.style.brevity", "wanted it short", "old1")
    add_observation(conn, "user.style.brevity", "wanted it short", "old2")
    _add_turn(conn, "s7", "user", "Just give me the short version.")
    payload = json.dumps(
        {
            "facts": [],
            "observations": [
                {"key": "user.style.brevity", "value": "asked for the short version"}
            ],
            "summary": "User keeps asking for brevity.",
        }
    )
    ok = await update_memory_from_session(
        _FakeSettings(), "s7", client_factory=_factory(payload)
    )
    assert ok is True
    rendered = render_memory_context(conn)
    assert "- user.style.brevity:" in rendered  # promoted by the third sighting


def test_parse_update_tolerates_missing_observations_key():
    payload = json.dumps({"facts": [], "summary": "s"})
    assert _parse_update(payload) == {
        "facts": [],
        "observations": [],
        "summary": "s",
    }
