"""D1 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4): scripts/replay_extraction.py
replays the extractions a locked database lost on 2026-09-16, dated to when
each exchange happened and decided correct-first against what is stored."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis.db import get_conn, run_migrations

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import replay_extraction as rx  # noqa: E402


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "replay.db"))
    monkeypatch.delenv("JARVIS_MEMORY_ECHO_GUARD", raising=False)
    c = get_conn(tmp_path / "replay.db")
    run_migrations(c)
    yield c
    c.close()


class _Settings:
    openai_api_key = "k"
    openai_base_url = "http://unused"
    openai_model = "fake-model"


def _factory(facts_by_user: dict[str, list[dict]]):
    """A model that extracts `facts_by_user[<user line>]` from an exchange."""
    class _Completions:
        async def create(self, **kwargs):
            exchange = kwargs["messages"][1]["content"]
            user = exchange.split("\n")[0][len("USER: "):]
            text = json.dumps({"facts": facts_by_user.get(user, []), "observations": [
                {"key": "user.habit.x", "value": "y"}]})
            msg = type("M", (), {"content": text})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": _Completions()})(),
                                 "base_url": "http://unused"})()
    return lambda _settings: client


def _exchange(conn, session, user, reply, at):
    conn.execute("INSERT INTO conversations (session_id, role, content, created_at) "
                 "VALUES (?, 'user', ?, ?)", (session, user, at))
    cur = conn.execute("INSERT INTO conversations (session_id, role, content, created_at) "
                       "VALUES (?, 'assistant', ?, ?)", (session, reply, at))
    conn.commit()
    return cur.lastrowid


def _fact(conn, key, content, updated_at, archived_at=None, tier="preference"):
    conn.execute("INSERT INTO memories (kind, key, content, created_at, updated_at, tier, "
                 "archived_at, became) VALUES ('fact', ?, ?, ?, ?, ?, ?, ?)",
                 (key, content, updated_at, updated_at, tier, archived_at,
                  "deleted:stale" if archived_at else None))
    conn.commit()


WHEN = "2026-09-13T20:52:09.919547+00:00"


def test_failed_exchanges_are_read_once_each_oldest_first(tmp_path):
    log = tmp_path / "extractor.launchd.log"
    log.write_text(
        "2026-09-16 12:39:33,572 ERROR jarvis.memory_extraction: memory_extraction_failed "
        "session=b source_turn=2889\n"
        "Traceback (most recent call last):\n"
        "sqlite3.OperationalError: database is locked\n"
        "2026-09-16 12:39:17,619 ERROR jarvis.memory_extraction: memory_extraction_failed "
        "session=a source_turn=2872\n"
        "2026-09-16 12:40:00,000 INFO jarvis.memory_extraction: memory_exchange_extracted "
        "session=c source_turn=2900 facts=1\n", encoding="utf-8")
    again = tmp_path / "extractor.launchd.log.1"
    again.write_text("x memory_extraction_failed session=b source_turn=2889\n", encoding="utf-8")
    assert rx.failed_exchanges([str(log), str(again)]) == [("a", 2872), ("b", 2889)]


def test_correct_first_decisions(conn):
    when = datetime(2026, 9, 13, 20, 52, tzinfo=timezone.utc)
    user, reply = "I prefer metric units and short replies", "Noted."
    _fact(conn, "user.pref.newer", "old words", "2026-09-20T00:00:00+00:00")
    _fact(conn, "user.pref.older", "old words", "2026-09-01T00:00:00+00:00")
    _fact(conn, "user.pref.gone_before", "x", "2026-09-01T00:00:00+00:00",
          archived_at="2026-09-05T00:00:00+00:00")
    _fact(conn, "user.pref.gone_after", "x", "2026-09-01T00:00:00+00:00",
          archived_at="2026-09-20T00:00:00+00:00")
    _fact(conn, "user.preference.replies", "prefers short replies and metric units",
          "2026-09-01T00:00:00+00:00")

    def d(key, value, u=user):
        return rx.decide(conn, key, value, when, u, reply)

    assert d("user.pref.brand_new", "likes chess") == ("insert", "new")
    assert d("user.pref.newer", "prefers metric") == ("skip", "a newer statement is stored")
    assert d("user.pref.older", "prefers metric") == \
        ("update", "this exchange is newer than the stored fact")
    assert d("user.pref.gone_before", "prefers metric") == \
        ("revive", "archived before this exchange, which restated it")
    assert d("user.pref.gone_after", "prefers metric") == ("skip", "archived after this exchange")
    assert d("user.preference.other_name", "prefers short replies and metric units")[1] == \
        "similar fact stored: user.preference.replies"
    # D-L7 still applies: words only Mortimer said are not Larry's fact.
    assert rx.decide(conn, "user.pref.echo", "wants weekly digests", when,
                     "Sure.", "I'll send you weekly digests.") == ("skip", "echo_of_reply")


async def test_dry_run_writes_nothing_and_apply_dates_writes_to_the_exchange(conn):
    turn = _exchange(conn, "s1", "I prefer metric units", "Noted.", WHEN)
    _fact(conn, "user.pref.units", "imperial", "2026-09-01T00:00:00+00:00")
    factory = _factory({"I prefer metric units": [
        {"key": "user.pref.units", "value": "metric"},
        {"key": "user.pref.chess", "value": "likes chess on weekends"},
    ]})
    lines: list[str] = []
    before = [tuple(r) for r in conn.execute("SELECT * FROM memories ORDER BY id")]
    totals = await rx.replay(conn, [("s1", turn)], _Settings(), write=False,
                             client_factory=factory, out=lines.append)
    assert [tuple(r) for r in conn.execute("SELECT * FROM memories ORDER BY id")] == before
    assert totals["update"] == 1 and totals["insert"] == 1 and totals["observations"] == 1
    assert any("update user.pref.units = 'metric'" in line for line in lines)
    assert lines[-1].startswith("Dry run (nothing written)")

    await rx.replay(conn, [("s1", turn)], _Settings(), write=True, client_factory=factory,
                    out=lambda _l: None)
    rows = {r["key"]: dict(r) for r in conn.execute(
        "SELECT key, content, created_at, updated_at, source_turn, source_session_id, "
        "archived_at FROM memories WHERE kind = 'fact'")}
    assert rows["user.pref.units"]["content"] == "metric"
    assert rows["user.pref.units"]["updated_at"] == WHEN          # the exchange's time,
    assert rows["user.pref.units"]["created_at"] == "2026-09-01T00:00:00+00:00"
    assert rows["user.pref.chess"]["created_at"] == WHEN           # not the replay's
    assert rows["user.pref.chess"]["source_turn"] == turn
    assert rows["user.pref.chess"]["source_session_id"] == "s1"
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0

    # Once is enough: a second --apply finds everything stored as new.
    again = await rx.replay(conn, [("s1", turn)], _Settings(), write=True,
                            client_factory=factory, out=lambda _l: None)
    assert again["skip"] == 2 and again["insert"] == again["update"] == 0


async def test_a_missing_or_mismatched_exchange_is_reported_not_guessed(conn):
    turn = _exchange(conn, "s1", "hello", "hi", WHEN)
    lines: list[str] = []
    totals = await rx.replay(conn, [("other-session", turn), ("s1", 99999)], _Settings(),
                             write=True, client_factory=_factory({}), out=lines.append)
    assert totals["missing"] == 2 and totals["exchanges"] == 0
    assert "no exchange for session other-session" in lines[0]


# ---- 2026-09-25 adversarial review (dd86c55): each reproduced a defect.


def test_an_archived_key_is_not_revived_when_a_similar_fact_is_live(conn):
    when = datetime(2026, 9, 14, tzinfo=timezone.utc)
    _fact(conn, "user.preference.coffee", "takes coffee black with no sugar", "2026-09-10T00:00:00+00:00")
    _fact(conn, "user.preference.coffee_style", "takes coffee black, no sugar",
          "2026-09-01T00:00:00+00:00", archived_at="2026-09-12T00:00:00+00:00")
    assert rx.decide(conn, "user.preference.coffee_style", "takes coffee black, no sugar", when,
                     "I take my coffee black, no sugar.", "Okay.") == \
        ("skip", "similar fact stored: user.preference.coffee")


def test_a_restatement_after_the_exchange_is_not_overwritten(conn):
    from jarvis.memory_extraction import admit_fact_candidate

    t0 = _exchange(conn, "s0", "Use Fahrenheit for temperatures.", "Okay.", "2026-09-10T00:00:00+00:00")
    conn.execute("INSERT INTO memories (kind, key, content, created_at, updated_at, tier, source_turn, "
                 "last_seen_at) VALUES ('fact', 'user.preference.units', 'prefers Fahrenheit for "
                 "temperatures', '2026-09-10T00:00:00+00:00', '2026-09-10T00:00:00+00:00', "
                 "'preference', ?, '2026-09-10T00:00:00+00:00')", (t0,))
    t2 = _exchange(conn, "s2", "Temperatures in Fahrenheit please.", "Sure.", "2026-09-20T00:00:00+00:00")
    assert admit_fact_candidate(conn, "user.preference.temperature_unit",
                                "prefers temperatures in Fahrenheit", "s2", t2).startswith("near_duplicate")
    when = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert rx.decide(conn, "user.preference.units", "prefers Celsius for temperatures", when,
                     "Actually use Celsius for temperatures.", "Okay.") == \
        ("skip", "a newer statement is stored")
    with pytest.raises(ValueError, match="refusing to move it back"):
        rx.apply(conn, "update", "user.preference.units", "prefers Celsius", when, "s1", 99)


async def test_one_key_twice_in_an_exchange_is_one_write_and_a_bad_exchange_does_not_stop_the_rest(conn):
    t1 = _exchange(conn, "s1", "Call me Larry. My name is Larry.", "Hi Larry.", "2026-09-14T00:00:00+00:00")
    t2 = _exchange(conn, "s2", "I like jazz records.", "Nice.", "2026-09-15T00:00:00+00:00")
    factory = _factory({
        "Call me Larry. My name is Larry.": [{"key": "user.nickname", "value": "wants to be called Larry"},
                                             {"key": "user.nickname", "value": "goes by Larry"}],
        "I like jazz records.": [{"key": "user.preference.music", "value": "likes jazz records"}],
    })
    totals = await rx.replay(conn, [("s1", t1), ("s2", t2)], _Settings(), write=True,
                             client_factory=factory, out=lambda _l: None)
    assert totals["insert"] == 2 and totals["failed"] == 0
    rows = dict(conn.execute("SELECT key, content FROM memories WHERE kind = 'fact'").fetchall())
    assert rows == {"user.nickname": "goes by Larry", "user.preference.music": "likes jazz records"}

    # A write that fails rolls back that exchange only.
    t3 = _exchange(conn, "s3", "I collect stamps.", "Neat.", "2026-09-16T00:00:00+00:00")
    t4 = _exchange(conn, "s4", "I run on Sundays.", "Great.", "2026-09-16T01:00:00+00:00")
    factory2 = _factory({"I collect stamps.": [{"key": "user.hobby.stamps", "value": "collects stamps"}],
                         "I run on Sundays.": [{"key": "user.habit.running", "value": "runs on Sundays"}]})
    real_apply = rx.apply

    def flaky(conn_, action, key, *args):
        if key == "user.hobby.stamps":
            raise RuntimeError("disk full")
        return real_apply(conn_, action, key, *args)

    rx.apply = flaky
    try:
        lines: list[str] = []
        totals = await rx.replay(conn, [("s3", t3), ("s4", t4)], _Settings(), write=True,
                                 client_factory=factory2, out=lines.append)
    finally:
        rx.apply = real_apply
    assert totals["failed"] == 1
    assert any("rolled back" in line for line in lines)
    keys = {r[0] for r in conn.execute("SELECT key FROM memories WHERE kind = 'fact'")}
    assert "user.hobby.stamps" not in keys and "user.habit.running" in keys
