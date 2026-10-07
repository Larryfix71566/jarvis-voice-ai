"""CC7a.3 causal regression checks through the actual production callbacks.

Extract the small nested callbacks from pipeline.py rather than booting STT,
MCP children or model clients. Their code is compiled unchanged, not copied into
a test implementation; the real action handler consumes their acknowledgement.
"""
import ast
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid

import pytest

from jarvis.bot.console_actions import build_console_action_tool, handle_console_request, _disclosed_inventory
from jarvis.bot.console_protocol import MAX_MESSAGE
from jarvis.bot.console_protocol import validate_inventory
from jarvis.bot.console_session import ConsoleSession

SESSION = "00000000-0000-4000-8000-00000000000a"
GENERATION = "00000000-0000-4000-8000-00000000000b"


def bridge(*, with_sender=False):
    path = Path(__file__).resolve().parents[2] / "jarvis/bot/pipeline.py"
    tree = ast.parse(path.read_text())
    names = {"_unwrap_client_message", "await_console_result", "handle_console_result", "_send_ui_message", "handle_console"}
    nodes = [node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert len(nodes) == 5
    waiters = {}
    namespace = dict(asyncio=asyncio, uuid=uuid, json=json, os=os, Any=Any,
                     MAX_MESSAGE=MAX_MESSAGE, _disclosed_inventory=_disclosed_inventory,
                     validate_inventory=validate_inventory,
                     console_session=ConsoleSession(session_id=SESSION, generation=GENERATION),
                     console_inventory_revision={"value": 0},
                     _log_console_validation_failure=lambda *_: None,
                     runtime=SimpleNamespace(session_id=SESSION),
                     transport=object(),
                     console_generation=GENERATION, console_waiters=waiters)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    if with_sender:
        return (namespace["await_console_result"], namespace["handle_console_result"], waiters,
                namespace["_send_ui_message"], namespace)
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


def test_actual_hundred_row_inventory_projects_before_shared_reply_budget():
    async def run():
        prepare, callback, waiters, send_ui, namespace = bridge(with_sender=True)
        data = native_large_inventory()
        rows = data["results"]
        for i in range(30, 100):
            rows.append({**row(str(uuid.uuid4()), None, (f"Older place {i} " + "forecast details " * 10)[:120]),
                "title": (f"Older weather report {i} " + "conditions and forecast " * 8)[:120],
                "index": i, "pinned": False, "unread": False, "can_connections": False})
        sent, lengths = [], {}
        async def send(_transport, request):
            sent.append(request)
            if request["action"] == "inventory":
                reply = native_reply(request, code="inventory", data=data)
                lengths["spaced_ascii"] = len(json.dumps(reply, ensure_ascii=True).encode("utf-8"))
                lengths["compact_utf8"] = len(json.dumps(reply, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                assert lengths["spaced_ascii"] > MAX_MESSAGE
                assert lengths["compact_utf8"] > MAX_MESSAGE
                await callback(reply)
            else:
                await callback(native_reply(request, summary="Opened thirty."))
        namespace["send_app_message"] = send
        _, handler = build_console_action_tool(send_ui, session_id=SESSION, generation=GENERATION,
            revision=8, await_result=prepare)
        # This deadline proves the callback fulfilled the real pending Future,
        # rather than the handler reaching its five-second timeout.
        reply = await asyncio.wait_for(handler({"action": "inventory"}), timeout=0.25)
        disclosed = json.loads(reply.split(". ", 1)[1])
        assert disclosed["scope"] == "results"
        assert {r["number"] for r in disclosed["results"] if r.get("number") is not None} == set(range(1, 31))
        assert disclosed["results_omitted"] > 0 and len(disclosed["results"]) >= 30
        assert await handler({"action": "result_select", "target": "30", "inventory_revision": 8}) == "Opened thirty."
        assert sent[-1]["target"] == data["results"][29]["id"]
        print(f"100-row inventory ACK bytes: {lengths}; shared ceiling: {MAX_MESSAGE}; disclosed rows: {len(disclosed['results'])}")
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


@pytest.mark.parametrize("prior_omitted", [0, 25])
def test_explicit_results_hundred_row_ack_preserves_preprojection_omissions(prior_omitted):
    async def run():
        prepare, callback, waiters, send_ui, ns = bridge(with_sender=True)
        original = hundred_row_inventory()
        if prior_omitted:
            original["results_omitted"] = prior_omitted
        projected = []
        async def send(_transport, request):
            await callback(native_reply(request, code="inventory", data=original))
            projected.append(waiters[request["request_id"]].result()["data"])
        ns["send_app_message"] = send
        _, handler = build_console_action_tool(send_ui, session_id=SESSION,
            generation=GENERATION, revision=8, await_result=prepare)
        reply = await asyncio.wait_for(handler({"action": "inventory", "args": {"scope": "results"}}), 0.25)
        disclosed = json.loads(reply.split(". ", 1)[1])
        assert disclosed == projected[0]
        assert disclosed["results_omitted"] == prior_omitted + 100 - len(disclosed["results"])
        assert disclosed["results_omitted"] > 0
        assert {"skills", "screens", "panels"} <= set(disclosed["omitted_fields"])
        assert not {"scope", "results_omitted", "omitted_fields"}.intersection(disclosed["omitted_fields"])
        assert _disclosed_inventory(disclosed, scope="results")[0] == disclosed
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


@pytest.mark.parametrize("metadata", [
    {"results_omitted": True}, {"results_omitted": -1}, {"results_omitted": 2.5},
    {"results_omitted": "68"}, {"omitted_fields": "skills"}, {"omitted_fields": [False]},
])
def test_malformed_prior_projection_metadata_is_not_disclosed_or_cached(metadata):
    async def run():
        sent = []
        async def send(request):
            sent.append(request)
        async def ack(_request_id):
            return {"status": "ok", "data": {"revision": 8,
                "results": [row(str(uuid.uuid4()), 1, "Weather")], **metadata}}
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, revision=8, await_result=ack)
        reply = await handler({"action": "inventory", "args": {"scope": "results"}})
        assert "unavailable" in reply
        assert "Nothing changed" in await handler({"action": "result_close", "target": "1", "inventory_revision": 8})
        assert len(sent) == 1
    asyncio.run(run())


@pytest.mark.parametrize("scope", ["screens", "panels"])
def test_actual_sender_preserves_requested_scope_before_large_ack_guard(scope):
    async def run():
        prepare, callback, waiters, send_ui, namespace = bridge(with_sender=True)
        data = native_large_inventory()
        data["results"] += [{**row(str(uuid.uuid4()), None, "older " + "x" * 110),
            "title": "Older weather " + "x" * 106, "pinned": False, "unread": False}
            for _ in range(70)]
        async def send(_transport, request):
            assert waiters[request["request_id"]]._mortimer_inventory_scope == scope
            reply = native_reply(request, code="inventory", data=data)
            assert len(json.dumps(reply, separators=(",", ":")).encode()) > MAX_MESSAGE
            await callback(reply)
        namespace["send_app_message"] = send
        _, handler = build_console_action_tool(send_ui, session_id=SESSION,
            generation=GENERATION, revision=8, await_result=prepare)
        reply = await asyncio.wait_for(handler({"action": "inventory", "args": {"scope": scope}}), 0.25)
        actual = json.loads(reply.split(". ", 1)[1])
        assert actual[scope] == data[scope] and actual["scope"] == scope
        assert actual["revision"] == 8 and "results" not in actual
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


def test_scoped_reply_without_results_does_not_replace_observed_result_ids():
    async def run():
        result_id, sent = str(uuid.uuid4()), []
        async def send(request):
            sent.append(request)
        async def ack(_request_id):
            request = sent[-1]
            if request["action"] != "inventory":
                return {"status": "ok", "summary": "Closed."}
            data = ({"revision": 3, "screens": [{"id": "screen-1"}], "scope": "screens"}
                if request["args"].get("scope") == "screens" else
                {"revision": 3, "results": [row(result_id, 1, "Weather")]})
            return {"status": "ok", "data": data}
        _, handler = build_console_action_tool(send, session_id=SESSION,
            generation=GENERATION, revision=3, await_result=ack)
        await handler({"action": "inventory", "args": {"scope": "results"}})
        assert '"screens"' in await handler({"action": "inventory", "args": {"scope": "screens"}})
        assert await handler({"action": "result_close", "target": "1", "inventory_revision": 3}) == "Closed."
        assert sent[-1]["target"] == result_id
    asyncio.run(run())


def test_genuinely_over_budget_noninventory_reply_is_not_reduced_or_accepted():
    async def run():
        prepare, callback, waiters = bridge()
        request = {"request_id": str(uuid.uuid4())}
        pending = prepare(request["request_id"])
        await callback(native_reply(request, code="weather_reused", data={"source": "x" * MAX_MESSAGE}))
        assert not pending.done()
        # Even a nominal inventory cannot hide an oversized non-data field.
        await callback(native_reply(request, code="inventory", data=native_large_inventory(),
            summary="x" * MAX_MESSAGE))
        assert not pending.done()
        pending.cancel()
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


def passive_inventory(inventory_data, **overrides):
    return {"type": "console/inventory", "version": 1,
        "session_id": SESSION.upper(), "generation": GENERATION.upper(),
        "revision": 8, "data": inventory_data, **overrides}


def hundred_row_inventory():
    data = native_large_inventory()
    data["results"] += [{**row(str(uuid.uuid4()), None, "older " + "x" * 110),
        "title": "Older weather " + "x" * 106, "pinned": False, "unread": False}
        for _ in range(70)]
    return data


def test_passive_hundred_row_inventory_updates_latest_not_observed_revision(monkeypatch):
    async def run():
        monkeypatch.setenv("JARVIS_COMMAND_CONSOLE_ENABLED", "true")
        prepare, callback, waiters, send_ui, ns = bridge(with_sender=True)
        data = hundred_row_inventory()
        packet = passive_inventory(data)
        raw_compact = len(json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        raw_repr = len(repr(packet))
        assert raw_compact > MAX_MESSAGE and raw_repr > MAX_MESSAGE
        await ns["handle_console"](packet)
        assert ns["console_inventory_revision"]["value"] == 8
        stored = ns["console_session"].inventory
        assert stored["scope"] == "results" and stored["results_omitted"] > 0
        assert {r["number"] for r in stored["results"] if r.get("number") is not None} == set(range(1, 31))
        sent = []
        async def send(_transport, request):
            sent.append(request)
            await callback(native_reply(request, code="inventory", data=data)
                if request["action"] == "inventory" else native_reply(request, summary="Opened."))
        ns["send_app_message"] = send
        _, handler = build_console_action_tool(send_ui, session_id=SESSION, generation=GENERATION,
            revision=lambda: ns["console_inventory_revision"]["value"], await_result=prepare)
        # Passive updates are not an inventory disclosure to the model.
        assert "Nothing changed" in await handler({"action": "result_close", "target": "30", "inventory_revision": 8})
        assert sent == []
        # A stable UUID still uses the latest validated passive revision.
        assert await handler({"action": "result_select", "target": data["results"][-1]["id"]}) == "Opened."
        assert sent[-1]["revision"] == 8
        await asyncio.wait_for(handler({"action": "inventory", "args": {"scope": "results"}}), 0.25)
        assert await handler({"action": "result_select", "target": "30", "inventory_revision": 8}) == "Opened."
        assert sent[-1]["target"] == data["results"][29]["id"]
        print(f"100-row passive inventory bytes: repr={raw_repr}, compact_utf8={raw_compact}; shared ceiling={MAX_MESSAGE}")
        await asyncio.sleep(0)
        assert waiters == {}
    asyncio.run(run())


@pytest.mark.parametrize("changes", [
    {"session_id": str(uuid.uuid4())}, {"generation": str(uuid.uuid4())},
    {"version": 2}, {"version": True}, {"revision": True}, {"revision": 8.5},
    {"data": []}, {"unknown": "x" * MAX_MESSAGE},
])
def test_invalid_passive_inventory_never_updates_latest_or_snapshot(changes, monkeypatch):
    async def run():
        monkeypatch.setenv("JARVIS_COMMAND_CONSOLE_ENABLED", "true")
        _, _, _, _, ns = bridge(with_sender=True)
        await ns["handle_console"](passive_inventory(hundred_row_inventory(), **changes))
        assert ns["console_inventory_revision"]["value"] == 0
        assert ns["console_session"].inventory is None
    asyncio.run(run())


def test_unprojectable_numbered_passive_inventory_is_rejected_not_truncated(monkeypatch):
    async def run():
        monkeypatch.setenv("JARVIS_COMMAND_CONSOLE_ENABLED", "true")
        _, _, _, _, ns = bridge(with_sender=True)
        data = native_large_inventory()
        data["results"] = [{**row(str(uuid.uuid4()), i + 1, "界" * 120),
            "title": "界" * 120} for i in range(30)]
        # SkillsStore's existing wire ceiling is 32 catalogue entries. This
        # legal outer metadata makes the original publication exceed budget;
        # its thirty numbered Unicode rows cannot fit the voice disclosure.
        data["skills"] = [{**data["skills"][i % 6], "id": f"skill-{i}"} for i in range(32)]
        assert len(json.dumps(passive_inventory(data), ensure_ascii=False, separators=(",", ":")).encode()) > MAX_MESSAGE
        await ns["handle_console"](passive_inventory(data))
        assert ns["console_inventory_revision"]["value"] == 0
        assert ns["console_session"].inventory is None
    asyncio.run(run())
