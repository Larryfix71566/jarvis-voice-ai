import uuid
import asyncio
from jarvis.bot.console_actions import handle_console_request, build_console_action_tool


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
