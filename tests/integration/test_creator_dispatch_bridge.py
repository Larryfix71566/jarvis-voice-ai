"""Exercise both authenticated HTTP apps and the real Developer run boundary.

Only model completion and sandbox file access are fakes. RunLogger, the live
session registry, delegate closure, durable request association, privacy
context, and both service-bot authorization checks are production code.
"""
import asyncio
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from jarvis import auth, skill_requests
from jarvis.admin.server import app as admin_app
from jarvis.agents.delegate import build_delegate_tool
from jarvis.authmw import BearerAuthMiddleware
from jarvis.bot import server
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.bot.skill_creator_dispatch import register_session, unregister_session
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.runlog.store import get_run, get_skill_events, list_skill_runs
from jarvis.skill_runtime import clear_runtime_inventories, update_runtime_inventory
from tests.integration.test_runlog_end_to_end import make_agent


@pytest.fixture
async def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "bridge.db"))
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    run_migrations()
    token = auth.mint_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO client_tokens (user_id, name, token_hash, created_at) VALUES (?, ?, ?, ?)",
            ("local", "service-bot", auth.hash_token(token), now_iso()),
        )
        conn.commit()
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr("jarvis.auth.service_headers", lambda: headers)
    owner = "creator-owner"
    session_id, request_id = str(uuid.uuid4()), str(uuid.uuid4())
    payload = {
        "operation": "draft", "request_id": request_id,
        "bot_session_id": session_id, "skill_id": "bridge-skill",
        "task_brief": "PRIVATE-BRIEF", "privacy_context": "standard",
    }
    state, _ = skill_requests.reserve(owner, payload)
    skill_requests.update(owner, request_id, state="drafting")
    sandbox_calls = []

    read_result = {"ok": True, "content": "PRIVATE-DRAFT-CONTENT"}

    def read_file(path):
        # No tool may execute before its actual Developer run is associated.
        associated = skill_requests.get(owner, request_id)["developer_run_id"]
        assert get_run(associated)["run"]["status"] == "running"
        sandbox_calls.append(path)
        return dict(read_result)

    monkeypatch.setattr(skill_requests, "_service", lambda _slug, **_kwargs: SimpleNamespace(
        status=lambda: {"run_id": state["sandbox_job_id"]}, read_file=read_file,
    ))
    clear_runtime_inventories()
    update_runtime_inventory(session_id, [], True, active=True, owner_id=owner)
    http_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: http_client(
        **kwargs, transport=httpx.ASGITransport(app=admin_app),
    ))
    bot_app = FastAPI()
    bot_app.add_middleware(BearerAuthMiddleware)
    bot_app.post("/dispatch")(server._dispatch_creator)
    bot_app.post("/cancel")(server._cancel_creator)
    events = []
    native_messages = []
    from jarvis.bot.pipeline import make_agent_event_handler

    async def send_message(_transport, message):
        native_messages.append(message)

    monkeypatch.setattr("jarvis.bot.pipeline.send_app_message", send_message)
    native_event_handler = make_agent_event_handler(object())

    def on_event(event):
        events.append(event)
        native_event_handler(event)

    holder = SensitiveTurn()

    def start(script):
        agent = make_agent(script, name="developer")
        _, delegate = build_delegate_tool(
            {"developer": agent}, on_event=on_event, session_id=session_id,
        )
        privacy_token = current_sensitive_turn.set(holder)
        try:
            register_session(session_id, owner, delegate.run_skill_creator)
        finally:
            current_sensitive_turn.reset(privacy_token)
        return agent

    async with http_client(
        transport=httpx.ASGITransport(app=bot_app), base_url="http://bot", headers=headers,
    ) as client:
        yield SimpleNamespace(
            start=start, client=client, events=events, holder=holder,
            owner=owner, session_id=session_id, request_id=request_id,
            sandbox_job_id=state["sandbox_job_id"], sandbox_calls=sandbox_calls,
            read_result=read_result,
            native_messages=native_messages,
            body={"owner_id": owner, "bot_session_id": session_id,
                  "request_id": request_id, "task_brief": "PRIVATE-BRIEF"},
        )
    unregister_session(session_id)
    clear_runtime_inventories()
    for task in list(server._creator_tasks):
        task.cancel()
    await asyncio.gather(*list(server._creator_tasks), return_exceptions=True)


async def test_real_bridge_binds_run_owner_and_forwards_scrubbed_lifecycle(bridge):
    agent = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "PRIVATE-ANSWER"),
    ])
    # This is a service request, not a child task of the voice pipeline.
    token = current_sensitive_turn.set(None)
    try:
        response = await bridge.client.post("/dispatch", json=bridge.body)
    finally:
        current_sensitive_turn.reset(token)
    assert response.status_code == 200, response.text
    run_id = response.json()["developer_run_id"]
    assert len({run_id, bridge.request_id, bridge.sandbox_job_id, bridge.session_id}) == 4
    run = get_run(run_id)["run"]
    assert (run["agent"], run["user_id"], run["session_id"], run["status"]) == (
        "developer", bridge.owner, bridge.session_id, "ok",
    )
    assert skill_requests.get(bridge.owner, bridge.request_id)["developer_run_id"] == run_id
    assert bridge.sandbox_calls == ["skills/bridge-skill/SKILL.md"]
    assert agent._registry.calls == []
    assert [e["type"] for e in bridge.events] == [
        "delegate_start", "agent_start", "agent_tool", "agent_tool_result",
        "agent_done", "delegate_done",
    ]
    assert all(e["run_id"] == run_id for e in bridge.events)
    assert "PRIVATE-" not in json.dumps(bridge.events)
    assert bridge.events[-1]["ok"] is True
    assert run_id not in server._creator_runs
    activity = list_skill_runs("skill-creator", user_id=bridge.owner)["runs"]
    assert [item["run_id"] for item in activity] == [run_id]
    events = get_skill_events(run_id, user_id=bridge.owner)["events"]
    assert events[0]["type"] == "skill_selected"
    assert events[0]["skill_id"] == "skill-creator"
    await asyncio.sleep(0)
    assert [(m["type"], m.get("state")) for m in bridge.native_messages] == [
        ("agent", "working"), ("agent_tool", None),
        ("agent_activity", None), ("agent", "done"),
    ]
    assert all(m["run_id"] == run_id for m in bridge.native_messages)
    assert "PRIVATE-" not in json.dumps(bridge.native_messages)


async def test_bridge_preserves_failed_tool_verdict(bridge):
    bridge.read_result.clear()
    bridge.read_result.update(ok=False, error="read refused")
    agent = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "Unable to read the file."),
    ])
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200
    run = get_run(response.json()["developer_run_id"])["run"]
    assert run["tools_failed"] == 1 and run["tools_ok"] == 0
    tool_event = next(e for e in bridge.events if e["type"] == "agent_tool_result")
    assert tool_event["ok"] is False
    sent = agent._client.chat.completions.requests[-1]
    receipt = json.loads(next(m["content"] for m in sent if m["role"] == "tool"))
    assert receipt == bridge.read_result


@pytest.mark.parametrize("tool_name", ["fake_tool", "skill_reference_read"])
async def test_scoped_bridge_never_exposes_or_executes_ambient_tools(bridge, monkeypatch, tool_name):
    matches = []
    monkeypatch.setattr("jarvis.agents.base.match_skill", lambda *_a: matches.append(True))
    monkeypatch.setattr("jarvis.agents.base.match_workflow", lambda *_a: matches.append(True))
    agent = bridge.start([("tool", tool_name, {}), ("text", "Not available.")])
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200
    assert matches == []
    assert agent._registry.calls == [] and bridge.sandbox_calls == []
    exposed = {spec["function"]["name"] for spec in agent._client.chat.completions.tool_schemas[0]}
    assert exposed == {"file_read", "edit_propose", "session_validate", "session_decline"}


@pytest.mark.parametrize("cause", ["wrong-owner", "protected", "missing-privacy"])
async def test_bridge_refuses_unowned_or_protected_context_before_provider(bridge, cause):
    agent = bridge.start([("text", "should never execute")])
    body = dict(bridge.body)
    if cause == "wrong-owner":
        body["owner_id"] = "another-owner"
    elif cause == "protected":
        bridge.holder.armed = True
    else:
        token = current_sensitive_turn.set(None)
        try:
            register_session(bridge.session_id, bridge.owner, lambda *_a, **_k: None)
        finally:
            current_sensitive_turn.reset(token)
    response = await bridge.client.post("/dispatch", json=body)
    assert response.status_code in {409, 503}
    assert agent._client.chat.completions.requests == []
    assert bridge.events == []
    assert bridge.sandbox_calls == []


async def test_bridge_cancels_exact_run_and_emits_one_terminal_event(bridge):
    bridge.start([("sleep", 30)])
    request = asyncio.create_task(bridge.client.post("/dispatch", json=bridge.body))
    for _ in range(100):
        associated = skill_requests.get(bridge.owner, bridge.request_id).get("developer_run_id")
        if associated and associated in server._creator_runs:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("Developer run was not associated")
    cancellation = {k: v for k, v in bridge.body.items() if k != "task_brief"}
    cancellation["developer_run_id"] = associated
    wrong = await bridge.client.post("/cancel", json={**cancellation, "request_id": str(uuid.uuid4())})
    assert wrong.status_code == 404
    assert get_run(associated)["run"]["status"] == "running"
    response = await bridge.client.post("/cancel", json=cancellation)
    assert response.status_code == 200
    assert (await request).status_code == 409
    assert get_run(associated)["run"]["status"] == "cancelled"
    terminal = [e for e in bridge.events if e["type"] == "delegate_done"]
    assert len(terminal) == 1
    assert terminal[0]["run_id"] == associated and terminal[0]["ok"] is False
