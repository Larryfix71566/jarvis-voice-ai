import asyncio
import uuid

from jarvis.bot.console_actions import build_console_action_tool, handle_console_request


def request(revision=3, action="inventory"):
    return {"type":"console/request", "version":1, "session_id":str(uuid.uuid4()),
            "generation":str(uuid.uuid4()), "request_id":str(uuid.uuid4()),
            "revision":revision, "action":action, "args":{}}


def test_inventory_is_bounded_to_the_supplied_snapshot():
    result = handle_console_request(request(), inventory=lambda: {"revision":3, "results":[]})
    assert result["status"] == "ok" and result["data"]["revision"] == 3


def test_stale_request_never_calls_mutation():
    calls = []
    stale = request(2, "result_select")
    stale["target"] = "result-1"
    result = handle_console_request(stale, inventory=lambda: {"revision":3},
                                    apply=lambda _: calls.append(1))
    assert result["code"] == "stale_selection" and not calls


def test_unwired_action_is_truthfully_unsupported():
    result = handle_console_request(request(action="atlas_fit"), inventory=lambda: {"revision":3})
    assert result["status"] == "unsupported"


def test_voice_console_action_uses_shared_request_shape():
    sent = []
    async def push(message):
        sent.append(message)
    schema, handler = build_console_action_tool(
        push,
        session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002",
    )
    assert schema["function"]["name"] == "console_action"
    result = asyncio.run(handler({"action": "view_set", "target": "atlas"}))
    assert "submitted" in result and sent[0]["type"] == "console/request"


def test_voice_console_action_reports_native_ack_and_timeout_honestly():
    sent = []

    async def push(message):
        sent.append(message)

    async def ack(request_id):
        assert request_id == sent[0]["request_id"]
        return {"status": "ok", "summary": "Atlas is open."}

    _, handler = build_console_action_tool(
        push,
        session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002",
        await_result=ack,
    )
    assert asyncio.run(handler({"action": "view_set", "target": "atlas"})) == "Atlas is open."

    async def timeout(_request_id):
        return None

    _, handler = build_console_action_tool(
        push,
        session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002",
        await_result=timeout,
    )
    assert "couldn't confirm" in asyncio.run(handler({"action": "view_set", "target": "atlas"}))


def test_voice_inventory_returns_bounded_snapshot_and_current_revision():
    sent = []
    async def push(message):
        sent.append(message)

    async def ack(_request_id):
        return {"status": "ok", "summary": "Console inventory ready.",
                "data": {"revision": 8, "results": [{"id": "r1", "title": "Research"}]}}

    revision = [8]
    _, handler = build_console_action_tool(
        push,
        session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002",
        revision=lambda: revision[0], await_result=ack,
    )
    text = asyncio.run(handler({"action": "inventory"}))
    assert '"revision":8' in text and sent[0]["revision"] == 8


def test_display_show_failure_is_relayed_not_reported_as_done():
    """WS-21 D3: Mortimer says content is on the other screen only when the
    app confirmed it; a failure's reason is what the Supervisor gets."""
    sent = []

    async def push(message):
        sent.append(message)

    async def refused(_request_id):
        return {"status": "error", "code": "screen_unavailable",
                "summary": "That display isn't connected, so nothing was moved."}

    async def confirmed(_request_id):
        return {"status": "ok", "code": "display_presented",
                "summary": "Weather is now on DELL U2720Q."}

    ids = dict(session_id="00000000-0000-4000-8000-000000000001",
               generation="00000000-0000-4000-8000-000000000002")
    _, failing = build_console_action_tool(push, await_result=refused, **ids)
    target = str(uuid.uuid4())
    reply = asyncio.run(failing({"action": "display_show", "target": target,
                                 "args": {"screen_id": "nope"}}))
    assert reply == "That display isn't connected, so nothing was moved."
    assert sent[0]["action"] == "display_show" and sent[0]["args"] == {"screen_id": "nope"}
    _, working = build_console_action_tool(push, await_result=confirmed, **ids)
    assert asyncio.run(working({"action": "display_show", "target": target})) == "Weather is now on DELL U2720Q."


def test_display_show_with_no_reply_is_not_reported_as_done():
    async def push(_message):
        return None

    async def silent(_request_id):
        return None

    _, handler = build_console_action_tool(
        push, session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002", await_result=silent)
    assert asyncio.run(handler({"action": "display_show", "target": str(uuid.uuid4())})) == \
        "I couldn't confirm that console action."


def test_result_actions_accept_a_spoken_number_or_subject():
    """CC7a.3: a Recents number or subject is a valid target string; the app
    resolves it to the result UUID, and the request shape is unchanged."""
    sent = []

    async def push(message):
        sent.append(message)

    async def opened(_request_id):
        if sent[-1]["action"] == "inventory":
            return {"status": "ok", "code": "inventory", "data": {
                "revision": 0, "results": [{"id": result_id, "number": 3,
                    "kind": "Weather", "subject": "Folly Beach", "title": "Folly Beach weather"}]}}
        return {"status": "ok", "code": "applied", "summary": "Console action applied."}

    _, handler = build_console_action_tool(
        push, session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002", await_result=opened)
    result_id = str(uuid.uuid4())
    asyncio.run(handler({"action": "inventory"}))
    for target in ("3", "Folly Beach weather"):
        assert asyncio.run(handler({"action": "result_select", "target": target, "inventory_revision": 0})) == \
            "Console action applied."
    assert [m["target"] for m in sent[1:]] == [result_id, result_id]


def test_ambiguous_result_reference_returns_the_choices_to_ask_about():
    """CC7a.3: needs_choice means nothing changed; the Supervisor gets the
    numbered labels so Mortimer can ask which one."""
    async def push(_message):
        return None

    async def ambiguous(_request_id):
        return {"status": "needs_choice", "code": "ambiguous_result",
                "summary": "More than one result matches. Ask which one, by number.",
                "choices": [{"id": str(uuid.uuid4()), "label": "2  Weather · Folly Beach · 5m"},
                            {"id": str(uuid.uuid4()), "label": "4  Weather · Folly Beach · 1h"}]}

    _, handler = build_console_action_tool(
        push, session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002", await_result=ambiguous)
    # Stable UUIDs do not need an observed snapshot; native clarification
    # replies must still retain their labels through legacy injected seams.
    reply = asyncio.run(handler({"action": "result_select", "target": str(uuid.uuid4())}))
    assert reply.startswith("More than one result matches.")
    assert "2  Weather · Folly Beach · 5m; 4  Weather · Folly Beach · 1h" in reply
