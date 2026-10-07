"""CC7a.3 causal regression checks through the actual production callbacks.

Extract the small nested callbacks from pipeline.py rather than booting STT,
MCP children or model clients. Their code is compiled unchanged, not copied into
a test implementation; the real action handler consumes their acknowledgement.
"""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid

import pytest

from jarvis.bot.console_actions import build_console_action_tool, handle_console_request

SESSION = "00000000-0000-4000-8000-00000000000a"
GENERATION = "00000000-0000-4000-8000-00000000000b"


def bridge():
    path = Path(__file__).resolve().parents[2] / "jarvis/bot/pipeline.py"
    tree = ast.parse(path.read_text())
    names = {"_unwrap_client_message", "await_console_result", "handle_console_result"}
    nodes = [node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert len(nodes) == 3
    waiters = {}
    namespace = dict(asyncio=asyncio, uuid=uuid, json=json, Any=Any,
                     runtime=SimpleNamespace(session_id=SESSION),
                     console_generation=GENERATION, console_waiters=waiters)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["await_console_result"], namespace["handle_console_result"], waiters


def native_reply(request, **payload):
    return {"type": "console/result", "version": 1,
            "session_id": SESSION, "generation": GENERATION,
            "request_id": request["request_id"], "status": "ok",
            "code": "applied", "summary": "Applied.", **payload}


def row(result_id, number, subject):
    return {"id": result_id, "number": number, "kind": "Weather",
            "subject": subject, "title": f"Weather · {subject}"}


def test_actual_fast_ack_preserves_choices_and_releases_waiter():
    async def run():
        prepare, callback, waiters = bridge()
        labels = ["2 Weather · Folly Beach · 5m", "4 Weather · Folly Beach · 1h"]
        async def send(request):
            assert request["request_id"] in waiters
            await callback(native_reply(request, status="needs_choice", code="ambiguous_result",
                summary="More than one result matches.", choices=[
                    {"id": str(uuid.uuid4()), "label": label} for label in labels]))
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, await_result=prepare)
        result = await handler({"action": "result_select", "target": str(uuid.uuid4())})
        assert all(label in result for label in labels)
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


def test_foundation_uppercase_uuid_replies_preserve_inventory_and_choices():
    async def run():
        prepare, callback, waiters = bridge()
        item = str(uuid.uuid4())
        async def send(request):
            reply = native_reply(request)
            for key in ("session_id", "generation", "request_id"):
                reply[key] = reply[key].upper()
            if request["action"] == "inventory":
                reply.update(code="inventory", data={"revision": 6, "results": [row(item, 1, "São Paulo")]})
            else:
                reply.update(status="needs_choice", choices=[{"id": item.upper(), "label": "1 Weather · São Paulo"}])
            await callback(reply)
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, revision=6, await_result=prepare)
        assert '"revision":6' in await handler({"action": "inventory"})
        reply = await handler({"action": "result_select", "target": "Sao Paulo weather", "inventory_revision": 6})
        assert "1 Weather · São Paulo" in reply
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


def test_old_observed_number_never_acquires_new_arrival_identity():
    async def run():
        prepare, callback, waiters = bridge()
        bravo, charlie = str(uuid.uuid4()), str(uuid.uuid4())
        current = {"revision": 2, "results": [row(bravo, 1, "Bravo")]}
        effects, sent = [], []
        async def send(request):
            sent.append(request)
            if request["action"] == "inventory":
                await callback(native_reply(request, code="inventory", data=current))
            else:
                outcome = handle_console_request(request, inventory=lambda: current,
                    apply=lambda r: (effects.append(r["target"]) or ("ok", "Closed.")))
                await callback(outcome)
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION,
            revision=lambda: current["revision"], await_result=prepare)
        await handler({"action": "inventory"})
        current = {"revision": 3, "results": [row(charlie, 1, "Charlie"), row(bravo, 2, "Bravo")]}
        reply = await handler({"action": "result_close", "target": "1", "inventory_revision": 2})
        assert "changed" in reply and effects == []
        assert sent[-1]["target"] == bravo and sent[-1]["revision"] == 2
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


def test_missing_observation_and_ambiguous_subject_have_zero_sends():
    async def run():
        sent = []
        async def send(request):
            sent.append(request)
        async def ack(_request_id):
            return {"status": "ok", "data": {"revision": 4, "results": [
                row(str(uuid.uuid4()), 1, "Folly Beach"), row(str(uuid.uuid4()), 2, "Folly Beach")]}}
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, revision=4, await_result=ack)
        assert "inventory" in await handler({"action": "result_close", "target": "1"})
        assert sent == []
        await handler({"action": "inventory"})
        reply = await handler({"action": "result_close", "target": "Folly Beach", "inventory_revision": 4})
        assert "Choices:" in reply and "1  Weather" in reply and "2  Weather" in reply
        assert len(sent) == 1
        reply = await handler({"action": "result_close", "target": "1", "inventory_revision": 5})
        assert "Nothing changed" in reply and len(sent) == 1
    asyncio.run(run())


def test_compare_forwards_both_canonical_uuids_and_schema_fields():
    async def run():
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        sent = []
        async def send(request):
            sent.append(request)
        async def ack(_request_id):
            return {"status": "ok", "summary": "Comparison opened."}
        schema, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, revision=9, await_result=ack)
        fields = schema["function"]["parameters"]["properties"]
        assert {"secondary_target", "inventory_revision"} <= fields.keys()
        assert await handler({"action": "compare_set", "target": first,
                              "secondary_target": second}) == "Comparison opened."
        assert sent[0]["target"] == first and sent[0]["secondary_target"] == second
    asyncio.run(run())


@pytest.mark.parametrize("mixed", [False, True])
def test_explicit_stale_revision_is_kept_for_uuid_and_mixed_compare(mixed):
    async def run():
        prepare, callback, waiters = bridge()
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        current = {"revision": 2, "results": [row(first, 1, "First"), row(second, 2, "Second")]}
        sent, effects = [], []
        async def send(request):
            sent.append(request)
            if request["action"] == "inventory":
                await callback(native_reply(request, code="inventory", data=current))
            else:
                await callback(handle_console_request(request, inventory=lambda: current,
                    apply=lambda r: (effects.append(r) or ("ok", "Applied."))))
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION,
            revision=lambda: current["revision"], await_result=prepare)
        if mixed:
            await handler({"action": "inventory"})
        current = {**current, "revision": 3}
        args = {"action": "compare_set" if mixed else "result_close",
                "target": first, "inventory_revision": 2}
        if mixed:
            args["secondary_target"] = "2"
        assert "changed" in await handler(args)
        assert effects == [] and sent[-1]["revision"] == 2
        if mixed:
            assert sent[-1]["secondary_target"] == second
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


@pytest.mark.parametrize("change", [
    {"session_id": str(uuid.uuid4())}, {"generation": str(uuid.uuid4())},
    {"version": 2}, {"version": True}, {"request_id": str(uuid.uuid4())},
    {"choices": "wrong"}, {"choices": [{"id": "one", "label": 8}]},
    {"status": []}, {"status": {}},
])
def test_actual_callback_rejects_foreign_or_malformed_reply(change):
    async def run():
        prepare, callback, waiters = bridge()
        request = {"request_id": str(uuid.uuid4())}
        pending = prepare(request["request_id"])
        await callback(native_reply(request, **change))
        assert not pending.done()
        pending.cancel()
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["send_error", "cancel", "timeout"])
def test_waiter_is_released_on_every_non_success_exit(mode, monkeypatch):
    async def run():
        prepare, callback, waiters = bridge()
        async def send(_request):
            if mode == "send_error":
                raise RuntimeError("fixture send failed")
            if mode == "cancel":
                raise asyncio.CancelledError
        real_wait = asyncio.wait_for
        if mode == "timeout":
            async def short_wait(awaitable, timeout):
                return await real_wait(awaitable, 0.001)
            monkeypatch.setattr("jarvis.bot.console_actions.asyncio.wait_for", short_wait)
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, await_result=prepare)
        if mode == "send_error":
            with pytest.raises(RuntimeError):
                await handler({"action": "view_set", "target": "atlas"})
        elif mode == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await handler({"action": "view_set", "target": "atlas"})
        else:
            assert "couldn't confirm" in await handler({"action": "view_set", "target": "atlas"})
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


def test_disclosure_does_not_store_a_truncated_unseen_tail():
    async def run():
        sent = []
        ids = [str(uuid.uuid4()) for _ in range(150)]
        rows = [row(result_id, 1 if i == 0 else None, f"Place {i} " + "x" * 100)
                for i, result_id in enumerate(ids)]
        async def send(request):
            sent.append(request)
        async def ack(_request_id):
            return {"status": "ok", "data": {"revision": 1, "results": rows}}
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, await_result=ack)
        reply = await handler({"action": "inventory"})
        shown = json.loads(reply.split(". ", 1)[1])
        assert shown["results_omitted"] > 0 and len(json.dumps(shown, separators=(",", ":"))) <= 12000
        rows[0]["id"] = str(uuid.uuid4())  # A published caller cannot mutate the observed copy.
        await handler({"action": "result_close", "target": "1", "inventory_revision": 1})
        assert sent[-1]["target"] == ids[0]
    asyncio.run(run())


def test_second_inventory_never_rebinds_an_unversioned_or_old_number():
    async def run():
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        current = {"revision": 1, "results": [row(first, 1, "Alpha")]}
        sent = []
        async def send(request):
            sent.append(request)
        async def ack(_request_id):
            if sent[-1]["action"] == "inventory":
                return {"status": "ok", "code": "inventory", "data": current}
            return {"status": "ok", "summary": "Closed."}
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION,
            revision=lambda: current["revision"], await_result=ack)
        await handler({"action": "inventory"})
        current = {"revision": 2, "results": [row(second, 1, "Bravo")]}
        await handler({"action": "inventory"})
        for args in ({"action": "result_close", "target": "1"},
                     {"action": "result_close", "target": "1", "inventory_revision": 1}):
            assert "Nothing changed" in await handler(args)
            assert len(sent) == 2
        assert await handler({"action": "result_close", "target": "1", "inventory_revision": 2}) == "Closed."
        assert sent[-1]["target"] == second and sent[-1]["revision"] == 2
    asyncio.run(run())


def native_large_inventory():
    """20 pinned + 10 recent, with the coordinator's other real metadata shapes."""
    results = []
    for i in range(30):
        subject = (f"Place {i + 1} " + "forecast details " * 10)[:120]
        results.append({**row(str(uuid.uuid4()), i + 1, subject),
            "title": (f"Weather report {i + 1} " + "conditions and forecast " * 8)[:120],
            "index": i, "pinned": i < 20, "unread": True, "can_connections": False})
    return {"revision": 8, "mode": "conversation", "active_result_id": None,
        "comparison": None, "focused_panel_id": None, "results": results,
        "skills": [{"id": f"skill-{i}", "name": "Weather research " * 4,
            "category": "research", "installation": "installed", "enabled": True,
            "readiness": "ready", "example_ids": [f"example-{j}-" + "a" * 50 for j in range(12)]}
            for i in range(6)],
        "screens": [{"id": str(uuid.uuid4()), "label": "Built-in Display", "is_console": True},
                    {"id": str(uuid.uuid4()), "label": "DELL U2720Q", "is_supporting": True}],
        "supporting_display": {"open": False, "content": None, "presented": False},
        "panels": [{"id": name, "kind": name, "title": name.title(), "screen_id": None}
                   for name in ("sidecar", "results", "memory", "atlas")],
        "attachments": [], "selection": {"graph_id": None, "node_id": None}}


@pytest.mark.parametrize("scope", [None, "results", "all"])
def test_actual_large_native_ack_discloses_every_number_and_can_target_thirty(scope):
    async def run():
        prepare, callback, waiters = bridge()
        data = native_large_inventory()
        sent = []
        assert 12000 < len(json.dumps(data)) < 32 * 1024
        async def send(request):
            sent.append(request)
            await callback(native_reply(request, code="inventory", data=data)
                if request["action"] == "inventory" else native_reply(request, summary="Opened thirty."))
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION,
            revision=8, await_result=prepare)
        args = {"action": "inventory", "args": {"scope": scope} if scope is not None else {}}
        reply = await handler(args)
        disclosed = json.loads(reply.split(". ", 1)[1])
        assert disclosed["scope"] == "results" and disclosed["revision"] == 8
        assert {entry["number"] for entry in disclosed["results"]} == set(range(1, 31))
        assert {"skills", "screens", "panels"} <= set(disclosed["omitted_fields"])
        assert len(json.dumps(disclosed, separators=(",", ":"), ensure_ascii=True)) <= 12000
        assert "index" not in disclosed["results"][0] and "can_connections" not in disclosed["results"][0]
        assert await handler({"action": "result_select", "target": "30", "inventory_revision": 8}) == "Opened thirty."
        assert sent[-1]["target"] == data["results"][29]["id"]
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


@pytest.mark.parametrize("scope", [None, "all", "nodes", "sources", "groups", "attachments"])
def test_small_inventory_keeps_existing_other_surface_metadata(scope):
    async def run():
        data = {"revision": 3, "results": [], "screens": [{"id": "display-1"}],
                "skills": [{"id": "weather"}], "panels": [], "selection": {"node_id": "n1"}}
        async def send(_request):
            return None
        async def ack(_request_id):
            return {"status": "ok", "data": data}
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION, await_result=ack)
        reply = await handler({"action": "inventory", "args": {"scope": scope} if scope is not None else {}})
        assert json.loads(reply.split(". ", 1)[1]) == data
    asyncio.run(run())


@pytest.mark.parametrize("scope", ["screens", "panels"])
def test_large_inventory_other_scope_projects_only_actual_metadata(scope):
    async def run():
        data = native_large_inventory()
        async def send(_request):
            return None
        async def ack(_request_id):
            return {"status": "ok", "data": data}
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION, await_result=ack)
        reply = await handler({"action": "inventory", "args": {"scope": scope}})
        actual = json.loads(reply.split(". ", 1)[1])
        assert actual[scope] == data[scope] and actual["revision"] == data["revision"]
        assert actual["scope"] == scope and "results" not in actual and "skills" not in actual
        if scope == "screens":
            assert actual["supporting_display"] == data["supporting_display"]
        else:
            assert actual["focused_panel_id"] == data["focused_panel_id"]
    asyncio.run(run())


@pytest.mark.parametrize("scope", ["banana", [], {}])
def test_unknown_inventory_scope_has_no_send_or_effect(scope):
    async def run():
        sent = []
        _, handler = build_console_action_tool(sent.append, session_id=SESSION, generation=GENERATION)
        assert "unsupported inventory scope" in await handler({"action": "inventory", "args": {"scope": scope}})
        assert sent == []
    asyncio.run(run())


@pytest.mark.parametrize("action", [[], {}])
def test_non_string_action_is_refused_without_sending(action):
    async def run():
        sent = []
        _, handler = build_console_action_tool(sent.append, session_id=SESSION, generation=GENERATION)
        assert "action must be a string" in await handler({"action": action})
        assert sent == []
    asyncio.run(run())


def test_unicode_numbered_inventory_over_budget_refuses_without_caching():
    async def run():
        prepare, callback, waiters = bridge()
        rows = [{**row(str(uuid.uuid4()), i + 1, "界" * 60), "title": "界" * 60,
                 "pinned": i < 20, "unread": False} for i in range(30)]
        data = {"revision": 7, "results": rows}
        assert 12000 < len(json.dumps(data, ensure_ascii=True)) < 32 * 1024
        sent = []
        async def send(request):
            sent.append(request)
            await callback(native_reply(request, code="inventory", data=data))
        _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION,
            revision=7, await_result=prepare)
        reply = await handler({"action": "inventory", "args": {"scope": "results"}})
        assert "size limit" in reply and "界" not in reply
        assert "Nothing changed" in await handler({"action": "result_close", "target": "30", "inventory_revision": 7})
        assert len(sent) == 1
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())
