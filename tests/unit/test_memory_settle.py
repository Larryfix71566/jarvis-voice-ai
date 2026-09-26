"""W10 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4, Larry 2026-09-25: age-aware
memory) — the sweep settles open contradiction reviews correct-first:
a memory built from Mortimer's own words loses, two that can both be true
are both kept, a real conflict keeps the newer and archives the older, and
anything the check cannot answer stays open."""

from __future__ import annotations

import json

import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.memory import render_memory_context, restore_fact
from jarvis.memory_sweep import (
    _parse_settlement,
    run_sweep,
    settle_open_reviews,
)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "settle.db"))
    monkeypatch.delenv("JARVIS_MEMORY_AUTO_SETTLE", raising=False)
    c = get_conn(tmp_path / "settle.db")
    run_migrations(c)
    yield c
    c.close()


class _Settings:
    openai_api_key = "k"
    openai_base_url = "http://unused"
    openai_model = "fake-model"


class _Client:
    """Answers with `reply` (a dict per review id, or raw text) and keeps
    every request so a test can see what the check was shown."""

    def __init__(self, reply):
        self.reply = reply
        self.requests: list[dict] = []
        self.base_url = "http://unused"
        outer = self

        class _Completions:
            async def create(self, **kwargs):
                outer.requests.append(kwargs)
                if isinstance(outer.reply, Exception):
                    raise outer.reply
                text = outer.reply if isinstance(outer.reply, str) else json.dumps(
                    {"reviews": [{"id": i, **a} for i, a in outer.reply.items()]})
                msg = type("M", (), {"content": text})()
                return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

        self.chat = type("Chat", (), {"completions": _Completions()})()

    def payload(self) -> dict:
        return json.loads(self.requests[-1]["messages"][1]["content"])


def _exchange(conn, session, larry, mortimer):
    conn.execute("INSERT INTO conversations (session_id, role, content, created_at) "
                 "VALUES (?, 'user', ?, '2026-09-17T18:00:00+00:00')", (session, larry))
    cur = conn.execute("INSERT INTO conversations (session_id, role, content, created_at) "
                       "VALUES (?, 'assistant', ?, '2026-09-17T18:00:01+00:00')", (session, mortimer))
    return cur.lastrowid


def _fact(conn, key, content, updated_at, source_turn=None, seen=1):
    conn.execute(
        "INSERT INTO memories (kind, key, content, created_at, updated_at, tier, provenance, "
        "source_turn, recurrence_count) VALUES ('fact', ?, ?, ?, ?, 'preference', 'stated', ?, ?)",
        (key, content, updated_at, updated_at, source_turn, seen))


def _review(conn, keys, kind="contradiction"):
    cur = conn.execute(
        "INSERT INTO memory_reviews (kind, keys_json, detail, status, created_at) "
        "VALUES (?, ?, 'd', 'open', '2026-09-18T00:00:00+00:00')", (kind, json.dumps(keys)))
    conn.commit()
    return cur.lastrowid


def _live(conn, key):
    row = conn.execute("SELECT archived_at, became FROM memories WHERE key = ?", (key,)).fetchone()
    return row["archived_at"] is None, row["became"]


def _status(conn, review_id):
    return conn.execute("SELECT status FROM memory_reviews WHERE id = ?", (review_id,)).fetchone()[0]


def _pair(conn):
    """The shape of review 112 on the live store (2026-09-25 copy): one fact
    Larry said, one that came only from Mortimer's reply."""
    said = _exchange(conn, "s1", "Just do it yourself, don't hand me instructions.", "Understood.")
    echoed = _exchange(conn, "s2", "Can you not?",
                       "I'll stop looking things up and answer from what I know.")
    _fact(conn, "user.style.do_it", "wants the assistant to do tasks itself",
          "2026-09-17T18:02:35+00:00", said)
    _fact(conn, "user.style.no_lookups", "prefers the assistant not look things up",
          "2026-09-17T18:02:28+00:00", echoed)
    return _review(conn, ["user.style.do_it", "user.style.no_lookups"])


async def test_a_memory_built_from_mortimers_words_is_archived(conn):
    review = _pair(conn)
    client = _Client({review: {"a_stated": True, "b_stated": False, "both_hold": False}})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _live(conn, "user.style.no_lookups") == (False, f"not-stated:review-{review}")
    assert _live(conn, "user.style.do_it") == (True, None)
    assert _status(conn, review) == "resolved"
    assert result["settled"] == 1 and result["left_open"] == 0
    # The check saw both exchanges, Larry's words and Mortimer's reply.
    shown = client.payload()["reviews"][0]
    assert shown["b"]["exchanges"] == [{"larry": "Can you not?",
                                        "mortimer": "I'll stop looking things up and answer from what I know."}]
    assert "not-stated" not in json.dumps(shown)
    # One notice line names what was archived and how to undo it.
    assert "user.style.no_lookups" in result["notice"]
    assert "came from my own words" in result["notice"]
    assert "restore" in result["notice"]
    assert "no_lookups" not in render_memory_context(conn)


async def test_a_fact_whose_first_exchange_is_lost_is_never_archived_as_not_stated(conn):
    # research_display on the live store: seen twice, one recorded turn —
    # "Larry never said it" cannot be concluded from half the record.
    review = _pair(conn)
    conn.execute("UPDATE memories SET recurrence_count = 2 WHERE key = 'user.style.no_lookups'")
    client = _Client({review: {"a_stated": True, "b_stated": False, "both_hold": True}})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _live(conn, "user.style.no_lookups") == (True, None)
    assert _status(conn, review) == "dismissed"   # fell through to both_hold
    assert result["kept_both"] == 1 and result["archived"] == []
    assert result["notice"] == ""                # nothing changed, nothing to say


async def test_a_fact_with_no_recorded_exchange_is_never_archived_as_not_stated(conn):
    _fact(conn, "user.a", "short answers", "2026-09-10T00:00:00+00:00")
    _fact(conn, "user.b", "long answers", "2026-09-12T00:00:00+00:00")
    review = _review(conn, ["user.a", "user.b"])
    client = _Client({review: {"a_stated": False, "b_stated": False, "both_hold": False}})
    await settle_open_reviews(conn, _Settings(), lambda _s: client)
    # Neither could be judged unstated, so the conflict rule decides: newer wins.
    assert _live(conn, "user.b") == (True, None)
    assert _live(conn, "user.a") == (False, "reviewed:kept:user.b")


async def test_two_memories_that_can_both_be_true_are_both_kept(conn):
    review = _pair(conn)
    client = _Client({review: {"a_stated": True, "b_stated": True, "both_hold": True}})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _live(conn, "user.style.do_it")[0] and _live(conn, "user.style.no_lookups")[0]
    assert _status(conn, review) == "dismissed"
    assert result["kept_both"] == 1


async def test_a_real_conflict_keeps_the_newer_memory(conn):
    review = _pair(conn)   # do_it is newer (18:02:35 vs 18:02:28)
    client = _Client({review: {"a_stated": True, "b_stated": True, "both_hold": False}})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _live(conn, "user.style.do_it") == (True, None)
    assert _live(conn, "user.style.no_lookups") == (False, "reviewed:kept:user.style.do_it")
    assert _status(conn, review) == "resolved"
    assert "newer memory user.style.do_it says otherwise" in result["notice"]


async def test_a_conflict_between_equally_old_memories_stays_open(conn):
    _fact(conn, "user.a", "x y z", "2026-09-10T00:00:00+00:00")
    _fact(conn, "user.b", "x y w", "2026-09-10T00:00:00+00:00")
    review = _review(conn, ["user.a", "user.b"])
    client = _Client({review: {"a_stated": True, "b_stated": True, "both_hold": False}})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _status(conn, review) == "open" and result["left_open"] == 1


@pytest.mark.parametrize("reply", [
    RuntimeError("provider down"),
    "not json",
    json.dumps({"reviews": [{"id": 1, "a_stated": "yes", "b_stated": True, "both_hold": True}]}),
    json.dumps({"reviews": [{"id": 1, "a_stated": True, "b_stated": True}]}),
    json.dumps({"reviews": []}),
])
async def test_anything_the_check_cannot_answer_stays_open(conn, reply):
    review = _pair(conn)
    assert review == 1
    result = await settle_open_reviews(conn, _Settings(), lambda _s: _Client(reply))
    assert _status(conn, review) == "open"
    assert _live(conn, "user.style.do_it")[0] and _live(conn, "user.style.no_lookups")[0]
    assert result["left_open"] == 1 and result["notice"] == ""


async def test_the_kill_switch_settles_nothing(conn, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_AUTO_SETTLE", "false")
    review = _pair(conn)
    client = _Client({review: {"a_stated": True, "b_stated": False, "both_hold": False}})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert result["enabled"] is False and client.requests == []
    assert _status(conn, review) == "open"


async def test_only_contradictions_are_settled(conn):
    _pair(conn)
    conn.execute("UPDATE memory_reviews SET status = 'dismissed'")
    audience = _review(conn, ["user.style.do_it"], kind="audience")
    cluster = _review(conn, ["user.style.do_it", "user.style.no_lookups"], kind="cluster")
    client = _Client({})
    await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert client.requests == []
    assert _status(conn, audience) == "open" and _status(conn, cluster) == "open"


async def test_a_review_whose_fact_is_gone_is_closed_without_a_model_call(conn):
    review = _pair(conn)
    conn.execute("UPDATE memories SET archived_at = '2026-09-20T00:00:00+00:00', "
                 "became = 'deleted:stale' WHERE key = 'user.style.no_lookups'")
    client = _Client({})
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert client.requests == []
    assert _status(conn, review) == "resolved" and result["stale_closed"] == 1
    assert _live(conn, "user.style.do_it") == (True, None)


async def test_a_fact_archived_by_an_earlier_review_closes_the_next_one(conn):
    # prefers_no_lookups sits in three of the four open reviews on the live
    # store; once one review archives it the others have nothing left to settle.
    first = _pair(conn)
    third = _exchange(conn, "s3", "Check the live system, not cached data.", "Will do.")
    _fact(conn, "user.style.live_checks", "check live systems rather than cached data",
          "2026-09-23T01:44:58+00:00", third)
    second = _review(conn, ["user.style.live_checks", "user.style.no_lookups"])
    client = _Client({
        first: {"a_stated": True, "b_stated": False, "both_hold": False},
        second: {"a_stated": True, "b_stated": True, "both_hold": False},
    })
    result = await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _live(conn, "user.style.no_lookups") == (False, f"not-stated:review-{first}")
    assert _live(conn, "user.style.live_checks") == (True, None)
    assert _status(conn, second) == "resolved"
    assert result["settled"] == 1 and result["stale_closed"] == 1
    assert [k for k, _c, _w in result["archived"]] == ["user.style.no_lookups"]


async def test_a_settled_memory_can_be_restored(conn):
    review = _pair(conn)
    client = _Client({review: {"a_stated": True, "b_stated": False, "both_hold": False}})
    await settle_open_reviews(conn, _Settings(), lambda _s: client)
    restored = restore_fact(conn, "user.style.no_lookups")
    assert restored["ok"] is True and restored["was"] == f"not-stated:review-{review}"
    assert _live(conn, "user.style.no_lookups") == (True, None)
    # The review is closed for good: the next sweep does not re-archive it.
    client2 = _Client({})
    await settle_open_reviews(conn, _Settings(), lambda _s: client2)
    assert client2.requests == [] and _live(conn, "user.style.no_lookups") == (True, None)


def test_parse_settlement_drops_malformed_entries():
    text = json.dumps({"reviews": [
        {"id": 1, "a_stated": True, "b_stated": None, "both_hold": False},
        {"id": True, "a_stated": True, "b_stated": True, "both_hold": True},
        {"id": 3, "a_stated": 1, "b_stated": True, "both_hold": True},
        {"id": 4, "a_stated": True, "b_stated": True, "both_hold": "no"},
        "junk",
    ]})
    assert _parse_settlement(text) == {1: {"a_stated": True, "b_stated": None, "both_hold": False}}
    assert _parse_settlement("```json\n{\"reviews\": []}\n```") == {}
    assert _parse_settlement(None) == {}


async def test_run_sweep_queues_one_notice_after_it_commits(tmp_path, monkeypatch):
    db_path = tmp_path / "sweep.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.delenv("JARVIS_MEMORY_AUTO_SETTLE", raising=False)
    monkeypatch.delenv("JARVIS_NOTICES_ENABLED", raising=False)
    c = get_conn(db_path)
    run_migrations(c)
    review = _pair(c)
    c.commit()
    c.close()

    def factory(_settings):
        # The contradiction/audience pass and the settle pass share the client.
        return _Client(json.dumps({
            "pairs": [], "audiences": [],
            "reviews": [{"id": review, "a_stated": True, "b_stated": False, "both_hold": False}],
        }))

    summary = await run_sweep(db_path=str(db_path), settings=_Settings(), client_factory=factory)
    assert summary["settled"] == 1
    c = get_conn(db_path)
    try:
        notices = [dict(r) for r in c.execute("SELECT kind, source, text, delivered_at FROM notices")]
        assert len(notices) == 1
        assert notices[0]["kind"] == "memory_review" and notices[0]["source"] == "memory_sweep"
        assert "user.style.no_lookups" in notices[0]["text"] and notices[0]["delivered_at"] is None
        assert c.execute("SELECT archived_at FROM memories WHERE key = 'user.style.no_lookups'"
                         ).fetchone()[0] is not None
    finally:
        c.close()


async def test_settle_preview_prints_decisions_and_writes_nothing(tmp_path, monkeypatch, capsys):
    import jarvis.config
    import jarvis.memory_sweep as sweep

    live = tmp_path / "live.db"
    copy = tmp_path / "copy.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(live))
    monkeypatch.delenv("JARVIS_MEMORY_AUTO_SETTLE", raising=False)
    c = get_conn(copy)
    run_migrations(c)
    review = _pair(c)
    c.commit()
    c.close()
    client = _Client({review: {"a_stated": True, "b_stated": False, "both_hold": False}})
    monkeypatch.setattr(jarvis.config, "load_settings", lambda: _Settings())
    monkeypatch.setattr(sweep, "make_memory_async_client",
                        lambda _s: (client, type("Route", (), {"model": "m"})()))

    result = await sweep._run_settle_preview(str(copy))
    out = capsys.readouterr().out
    assert f"review {review}: not_stated -> archive user.style.no_lookups" in out
    assert "nothing was written" in out and "notice: Memory tidy-up" in out
    assert result["settled"] == 1
    c = get_conn(copy)
    try:
        assert c.execute("SELECT status FROM memory_reviews").fetchone()[0] == "open"
        assert c.execute("SELECT COUNT(*) FROM memories WHERE archived_at IS NOT NULL").fetchone()[0] == 0
    finally:
        c.close()

    with pytest.raises(SystemExit, match="refusing the live database"):
        await sweep._run_settle_preview(str(live))


# ---- 2026-09-25 adversarial review (dd86c55): each case below reproduced a
# defect in that commit and now pins its fix.


def test_words_not_from_the_exchange_make_the_evidence_incomplete(conn):
    # A remember-tool correction or a capacity merge rewrites the fact; the
    # exchange on record no longer holds its words, so "Larry never said
    # it" cannot be concluded from it.
    from jarvis.memory import upsert_fact
    from jarvis.memory_extraction import admit_fact_candidate
    from jarvis.memory_sweep import _fact_evidence

    turn = _exchange(conn, "s1", "I take my coffee black.", "Noted.")
    assert admit_fact_candidate(conn, "user.preference.coffee", "takes coffee black", "s1", turn) == "inserted"
    assert _fact_evidence(conn, "user.preference.coffee")["complete"] is True
    upsert_fact(conn, "user.preference.coffee", "takes coffee with oat milk now", "s3")   # remember
    ev = _fact_evidence(conn, "user.preference.coffee")
    assert ev["complete"] is False
    # The same words again (no change) keep the exchange's claim.
    turn2 = _exchange(conn, "s4", "Black coffee for me.", "Okay.")
    assert admit_fact_candidate(conn, "user.preference.tea", "drinks green tea", "s4", turn2) == "inserted"
    upsert_fact(conn, "user.preference.tea", "drinks green tea", "s5")
    assert _fact_evidence(conn, "user.preference.tea")["complete"] is True


def test_a_fact_something_was_merged_into_is_never_complete(conn):
    # Merges from before upsert_fact cleared source_turn left it pointing
    # at an exchange that holds only part of the merged words.
    from jarvis.memory_sweep import _fact_evidence

    turn = _exchange(conn, "s1", "Weather in Fahrenheit.", "Okay.")
    _fact(conn, "user.preference.weather", "wants weather in Fahrenheit with the hourly forecast",
          "2026-09-10T00:00:00+00:00", turn)
    _fact(conn, "user.preference.hourly", "wants the hourly forecast", "2026-09-09T00:00:00+00:00")
    conn.execute("UPDATE memories SET archived_at = '2026-09-10T00:00:00+00:00', "
                 "became = 'merged:user.preference.weather' WHERE key = 'user.preference.hourly'")
    assert _fact_evidence(conn, "user.preference.weather")["complete"] is False


async def test_the_settle_call_holds_no_write_lock(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "lock.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.delenv("JARVIS_MEMORY_AUTO_SETTLE", raising=False)
    c = get_conn(db_path)
    run_migrations(c)
    _fact(c, "user.style.check_online", "wants current facts checked online before answering",
          "2026-09-17T18:00:00+00:00")
    _fact(c, "user.style.from_memory", "prefers replies straight from memory",
          "2026-09-17T19:00:00+00:00")
    _fact(c, "user.style.gone", "x y z", "2026-09-01T00:00:00+00:00")
    review = _review(c, ["user.style.check_online", "user.style.from_memory"])
    c.execute("UPDATE memories SET archived_at = '2026-09-02T00:00:00+00:00' WHERE key = 'user.style.gone'")
    _review(c, ["user.style.gone", "user.style.from_memory"])      # stale: closed by settle
    c.commit()
    c.close()
    probe: list[str] = []

    class _Probe(_Client):
        def __init__(self):
            super().__init__({review: {"a_stated": None, "b_stated": None, "both_hold": True}})
            inner = self.chat.completions

            class _Wrapped:
                async def create(self, **kwargs):
                    if kwargs["messages"][0]["content"].startswith("You check the long-term memory"):
                        other = sqlite3.connect(db_path, timeout=0.3)
                        try:
                            other.execute("INSERT INTO conversations (session_id, role, content, "
                                          "created_at) VALUES ('live', 'user', 'hi', 'x')")
                            other.commit()
                            probe.append("ok")
                        except sqlite3.OperationalError as exc:
                            probe.append(str(exc))
                        finally:
                            other.close()
                        return await inner.create(**kwargs)
                    msg = type("M", (), {"content": json.dumps({"pairs": [], "audiences": []})})()
                    return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

            self.chat = type("Chat", (), {"completions": _Wrapped()})()

    summary = await run_sweep(db_path=str(db_path), settings=_Settings(),
                              client_factory=lambda _s: _Probe())
    assert probe == ["ok"]
    assert summary["settled"] == 1


async def test_a_restatement_in_other_words_counts_as_newer(conn):
    from jarvis.memory_extraction import admit_fact_candidate

    t0 = _exchange(conn, "s0", "Keep answers short.", "Will do.")
    _fact(conn, "user.style.short_answers", "wants short spoken answers", "2026-09-01T00:00:00+00:00", t0)
    t1 = _exchange(conn, "s1", "Give me the full detail.", "Okay.")
    _fact(conn, "user.style.full_detail", "wants full detailed answers", "2026-09-10T00:00:00+00:00", t1)
    t2 = _exchange(conn, "s2", "Short answers, please, I mean it.", "Understood.")
    assert admit_fact_candidate(conn, "user.style.brief", "wants short spoken answers please",
                                "s2", t2).startswith("near_duplicate:user.style.short_answers")
    review = _review(conn, ["user.style.short_answers", "user.style.full_detail"])
    client = _Client({review: {"a_stated": True, "b_stated": True, "both_hold": False}})
    await settle_open_reviews(conn, _Settings(), lambda _s: client)
    assert _live(conn, "user.style.short_answers") == (True, None)
    assert _live(conn, "user.style.full_detail") == (False, "reviewed:kept:user.style.short_answers")


def test_the_notice_always_fits_and_keeps_the_restore_sentence():
    from jarvis.memory_sweep import _settle_notice
    from jarvis.notices import MAX_NOTICE_CHARS

    archived = [(f"user.preference.some_rather_long_key_number_{i}",
                 f"old statement number {i} about how the assistant should behave in general",
                 "newer memory user.style.wants_actual_availability says otherwise")
                for i in range(6)]
    text = _settle_notice(archived, kept_both=2)
    assert len(text) <= MAX_NOTICE_CHARS
    assert text.endswith("Any of them comes back if you ask me to restore it.")
    assert "can both be true" in text and "more;" not in text
    shown = sum(f"number_{i} " in text for i in range(6))
    assert shown >= 1 and f"and {6 - shown} more." in text
    one = _settle_notice(archived[:1], kept_both=0)
    assert "more" not in one and len(one) <= MAX_NOTICE_CHARS


def test_the_settle_rung_is_known_to_the_cost_ledger():
    from jarvis.usage_ledger import RUNGS
    from scripts.cost_report import BUCKETS

    assert "memory_settle" in RUNGS
    assert "memory_settle" in BUCKETS["background"]


async def test_a_restored_fact_is_not_the_next_one_aged_out(conn):
    from jarvis.memory import MAX_PROJECT_FACTS
    from jarvis.memory_sweep import run_capacity_enforcement

    for i in range(MAX_PROJECT_FACTS):
        at = f"2026-09-2{i % 5}T0{i}:00:00+00:00"
        conn.execute("INSERT INTO memories (kind, key, content, created_at, updated_at, tier) "
                     "VALUES ('fact', ?, ?, ?, ?, 'project')",
                     (f"project.p{i}", f"distinct project fact {i} zeta{i} omega{i}", at, at))
    conn.execute("INSERT INTO memories (kind, key, content, created_at, updated_at, tier, archived_at, "
                 "became) VALUES ('fact', 'project.old_plan', 'the lighthouse app ships in October', "
                 "'2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00', 'project', "
                 "'2026-09-01T00:00:00+00:00', 'aged-out')")
    conn.commit()
    assert restore_fact(conn, "project.old_plan")["ok"]

    def no_model(_settings):
        raise RuntimeError("no model")

    report = await run_capacity_enforcement(conn, _Settings(), no_model)
    assert report["project"]["aged_out"] == 1
    assert _live(conn, "project.old_plan") == (True, None)
    assert _live(conn, "project.p0") == (False, "aged-out")   # least recently seen instead
