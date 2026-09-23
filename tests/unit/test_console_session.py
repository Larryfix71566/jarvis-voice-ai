import uuid

from jarvis.bot.console_session import ConsoleSession


def request(session, request_id=None, revision=None, action="help"):
    return {
        "type": "console/request", "version": 1,
        "session_id": session.session_id, "generation": session.generation,
        "request_id": request_id or str(uuid.uuid4()),
        "revision": session.revision if revision is None else revision,
        "action": action, "target": None, "args": {},
    }


def test_session_replays_duplicate_request_without_reapplying():
    session = ConsoleSession()
    calls = []
    msg = request(session)
    first = session.accept(msg, inventory=lambda: {"revision": 0},
                           apply=lambda _: (calls.append(1) or "ok", "done"))
    second = session.accept(msg, inventory=lambda: {"revision": 0},
                            apply=lambda _: (calls.append(1) or "ok", "done"))
    assert first == second and calls == [1]


def test_session_rejects_stale_revision_and_generation():
    session = ConsoleSession()
    stale = session.accept(request(session, revision=4), inventory=lambda: {"revision": 0})
    assert stale["code"] == "stale_selection"
    session.rotate_generation()
    old = request(session)
    old["generation"] = str(uuid.uuid4())
    assert session.accept(old, inventory=lambda: {"revision": session.revision})["code"] == "stale_session"


def test_session_replay_cache_is_bounded_and_expires():
    now = [100.0]
    session = ConsoleSession(response_cache_limit=2, response_cache_ttl_s=5.0,
                             _clock=lambda: now[0])
    calls = []

    def apply(_):
        calls.append(1)
        return "ok", "done"

    first = request(session)
    session.accept(first, inventory=lambda: {"revision": 0}, apply=apply)
    second = request(session)
    session.accept(second, inventory=lambda: {"revision": 0}, apply=apply)
    third = request(session)
    session.accept(third, inventory=lambda: {"revision": 0}, apply=apply)
    # The newest response still replays without side effects.
    session.accept(second, inventory=lambda: {"revision": 0}, apply=apply)
    assert len(calls) == 3
    # Adding a fourth response evicts the oldest entry.
    session.accept(first, inventory=lambda: {"revision": 0}, apply=apply)
    assert len(calls) == 4
    now[0] += 6.0
    session.accept(third, inventory=lambda: {"revision": 0}, apply=apply)
    assert len(calls) == 5


def test_session_uses_latest_native_inventory_and_revision():
    session = ConsoleSession()
    session.update_inventory({"revision": 3, "mode": "atlas", "results": []})
    assert session.revision == 3
    seen = []
    msg = request(session, action="inventory")
    result = session.accept(msg, inventory=lambda: {"revision": 0},
                             apply=lambda value: seen.append(value))
    assert result["status"] == "ok"
    assert result["data"]["mode"] == "atlas"


def test_session_accepts_the_negotiated_generation():
    session = ConsoleSession()
    msg = request(session, action="help")
    result = session.accept(msg, inventory=lambda: {"revision": 0},
                             apply=lambda _: ("ok", "ready"))
    assert result["status"] == "ok"
