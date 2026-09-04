"""Unit tests for jarvis/memory_extraction_worker.py (MORTIMER_OPTIMIZATION_PLAN.md
Phase 2, "Extraction Gate", task 1 -- the standalone per-exchange polling
service). Mirrors tests/unit/test_memory.py and
tests/unit/test_memory_extraction.py's fixture/fake-client conventions.
"""

from __future__ import annotations

import json

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.memory_extraction_worker import (
    _iso_minus,
    tick_once,
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
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


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


_EMPTY_PAYLOAD = json.dumps({"facts": [], "observations": []})


def _factory(payload):
    return lambda _settings: _FakeClient(payload)


def _fact_payload(key, value):
    return json.dumps({"facts": [{"key": key, "value": value}], "observations": []})


class _CapturingCompletions:
    def __init__(self, payload, sink):
        self._payload = payload
        self._sink = sink

    async def create(self, **kwargs):
        self._sink.append(kwargs["messages"][-1]["content"])
        msg = _FakeMessage(self._payload)
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


class _CapturingClient:
    def __init__(self, payload, sink):
        self.chat = type("C", (), {"completions": _CapturingCompletions(payload, sink)})()


def _capturing_factory(payload, sink):
    """Records the exchange text sent on every call (in order) into `sink`,
    so a test can assert WHICH user turn a pairing actually used, not just
    how many pairings happened."""
    return lambda _settings: _CapturingClient(payload, sink)


# --- tick_once: basic pairing -------------------------------------------


class TestTickOnceBasicPairing:
    @pytest.mark.asyncio
    async def test_no_new_rows_is_a_noop(self, conn):
        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        assert result == {"rows": 0, "exchanges": 0, "cursor": 0}

    @pytest.mark.asyncio
    async def test_complete_exchange_extracts_and_advances_cursor(self, conn):
        _add_turn(conn, "s1", "user", "My name is Larry.")
        reply_id = _add_turn(conn, "s1", "assistant", "Noted, Larry.")

        result = await tick_once(
            _FakeSettings(), client_factory=_factory(_fact_payload("user.name", "Larry"))
        )

        assert result["rows"] == 2
        assert result["exchanges"] == 1
        assert result["cursor"] == reply_id
        assert (
            conn.execute("SELECT content FROM memories WHERE key='user.name'").fetchone()[
                "content"
            ]
            == "Larry"
        )
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending"
        ).fetchone()["n"] == 0

    @pytest.mark.asyncio
    async def test_two_sessions_interleaved_both_extract(self, conn):
        _add_turn(conn, "s1", "user", "My name is Larry.")
        _add_turn(conn, "s2", "user", "Call me Lawrence in this session.")
        _add_turn(conn, "s1", "assistant", "Got it, Larry.")
        last_id = _add_turn(conn, "s2", "assistant", "Understood, Lawrence.")

        # Same payload for both -- distinguishing which session produced
        # which write isn't the point here, only that BOTH got processed.
        result = await tick_once(
            _FakeSettings(), client_factory=_factory(_fact_payload("user.name", "Larry"))
        )

        assert result["rows"] == 4
        assert result["exchanges"] == 2
        assert result["cursor"] == last_id

    @pytest.mark.asyncio
    async def test_tool_role_rows_do_not_break_pairing(self, conn):
        _add_turn(conn, "s1", "user", "Check the build status.")
        _add_turn(conn, "s1", "tool", "build: passing")
        reply_id = _add_turn(conn, "s1", "assistant", "The build is passing.")

        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert result["rows"] == 3
        assert result["exchanges"] == 1
        assert result["cursor"] == reply_id

    @pytest.mark.asyncio
    async def test_assistant_row_with_no_pending_user_is_skipped(self, conn):
        # A proactive assistant message (e.g. a reminder firing) with no
        # preceding user turn in this batch -- nothing to pair, nothing
        # to extract, but the row still advances the cursor.
        row_id = _add_turn(conn, "s1", "assistant", "Reminder: call the dentist.")

        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert result["rows"] == 1
        assert result["exchanges"] == 0
        assert result["cursor"] == row_id

    @pytest.mark.asyncio
    async def test_second_user_turn_supersedes_unanswered_first(self, conn):
        _add_turn(conn, "s1", "user", "What's the weather?")
        _add_turn(conn, "s1", "user", "Never mind, what's my calendar look like?")
        reply_id = _add_turn(conn, "s1", "assistant", "You have one meeting today.")

        sent: list[str] = []
        result = await tick_once(
            _FakeSettings(), client_factory=_capturing_factory(_EMPTY_PAYLOAD, sent)
        )

        assert result["exchanges"] == 1  # only one pairing, not two
        assert result["cursor"] == reply_id
        assert len(sent) == 1
        assert "what's my calendar look like" in sent[0]
        assert "What's the weather" not in sent[0]  # the superseded turn
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending"
        ).fetchone()["n"] == 0


# --- tick_once: cross-poll pending-turn tracking -------------------------


class TestPendingAcrossPolls:
    @pytest.mark.asyncio
    async def test_dangling_user_turn_is_recovered_on_a_later_poll(self, conn):
        user_id = _add_turn(conn, "s1", "user", "My name is Larry.")

        first = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        assert first["exchanges"] == 0
        assert first["cursor"] == user_id  # cursor still advances
        pending = conn.execute(
            "SELECT * FROM memory_extraction_pending WHERE session_id='s1'"
        ).fetchone()
        assert pending is not None
        assert pending["user_content"] == "My name is Larry."
        assert pending["user_turn_id"] == user_id

        reply_id = _add_turn(conn, "s1", "assistant", "Noted, Larry.")
        second = await tick_once(
            _FakeSettings(), client_factory=_factory(_fact_payload("user.name", "Larry"))
        )
        assert second["exchanges"] == 1
        assert second["cursor"] == reply_id
        assert (
            conn.execute("SELECT content FROM memories WHERE key='user.name'").fetchone()[
                "content"
            ]
            == "Larry"
        )
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending"
        ).fetchone()["n"] == 0

    @pytest.mark.asyncio
    async def test_stale_pending_row_is_dropped_by_orphan_cleanup(self, conn, monkeypatch):
        # Simulates a sensitive-reply skip (jarvis/bot/transcript_log.py's
        # P2/P6 gate): a user row was persisted, its reply never was, and
        # the pending row is old enough to be considered abandoned.
        monkeypatch.setenv("JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S", "1")
        conn.execute(
            "INSERT INTO memory_extraction_pending "
            "(session_id, user_content, user_turn_id, first_seen_at) "
            "VALUES ('stale-session', 'orphaned question', 1, ?)",
            (_iso_minus(now_iso(), 3600),),  # an hour old
        )
        conn.commit()

        # Cleanup only runs when a tick has new rows to process.
        _add_turn(conn, "s1", "user", "hi")
        _add_turn(conn, "s1", "assistant", "hello")
        await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending WHERE session_id='stale-session'"
        ).fetchone()["n"] == 0

    @pytest.mark.asyncio
    async def test_fresh_pending_row_survives_cleanup(self, conn):
        _add_turn(conn, "s1", "user", "My name is Larry.")
        await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        # A second, unrelated tick with new activity must not sweep away
        # a pending row that isn't actually stale yet.
        _add_turn(conn, "s2", "user", "hi")
        _add_turn(conn, "s2", "assistant", "hello")
        await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending WHERE session_id='s1'"
        ).fetchone()["n"] == 1


# --- tick_once: tick-level failure isolation ------------------------------


class TestTickFailureIsolation:
    @pytest.mark.asyncio
    async def test_bad_tick_is_caught_and_reported(self, conn, monkeypatch):
        import jarvis.memory_extraction_worker as worker_mod

        def _boom(_rows):
            raise RuntimeError("pairing exploded")

        monkeypatch.setattr(worker_mod, "_group_by_session", _boom)
        _add_turn(conn, "s1", "user", "hi")

        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        assert result["error"] is True
        assert result["exchanges"] == 0


# --- _iso_minus ------------------------------------------------------------


class TestIsoMinus:
    def test_subtracts_seconds(self):
        before = _iso_minus("2026-09-02T12:00:00+00:00", 60)
        assert before == "2026-09-02T11:59:00+00:00"
