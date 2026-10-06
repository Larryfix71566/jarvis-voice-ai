"""Authenticated creator source receipts reach the real SubAgent before sinks."""
import asyncio
import json
import threading
import uuid

import pytest

from jarvis import development_attestation, skill_requests
from jarvis.bot.skill_creator_dispatch import active_session, register_session
from jarvis.model_routing import AccessRoute, ResolvedModelRoute
from jarvis.privacy_policy import DataPolicy, issue_tool_result
from jarvis.runlog.store import get_run
from tests.integration.test_creator_dispatch_bridge import bridge

CANARY = "SYNTHETIC_PRIVATE_CREATOR_SOURCE_38413"


@pytest.fixture(autouse=True)
def isolated_authority(monkeypatch):
    import os

    monkeypatch.setattr(development_attestation, "_issuers", {})
    monkeypatch.setattr(development_attestation, "_inflight_leases", set())
    monkeypatch.setattr(development_attestation, "_challenges", {})
    yield
    for issuer in development_attestation._issuers.values():
        os.close(issuer.lease)


def enable_route(subject):
    subject._resolved_route = ResolvedModelRoute(
        "developer", "fixture", "fixture", "openai", "",
        AccessRoute("direct_api", "openai_compatible", "provider_api", None,
                    "approved_external", capabilities=("text", "tools")),
        None, "openai/fixture", "interactive",
    )


@pytest.mark.parametrize("is_error", [False, True])
async def test_unknown_success_and_error_never_reach_logs_ui_derived_or_provider(bridge, is_error):
    bridge.read_result.clear()
    bridge.read_result.update({"ok": not is_error,
                              "error" if is_error else "content": CANARY,
                              "privacy": "approved_external", "source_scope": "approved-project"})
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "must never continue"),
    ])
    enable_route(subject)
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200, response.text
    run_id = response.json()["developer_run_id"]
    detail = get_run(run_id)
    assert bridge.sandbox_calls == ["skills/bridge-skill/SKILL.md"]
    assert len(subject._client.chat.completions.requests) == 1
    assert bridge.holder.is_armed()
    assert CANARY not in json.dumps(detail)
    assert CANARY not in json.dumps(bridge.events)
    assert CANARY not in json.dumps(bridge.native_messages)
    assert CANARY not in json.dumps(subject._client.chat.completions.requests)
    assert not any(event["type"] == "agent_tool_result" for event in bridge.events)


async def test_host_approved_receipt_is_verified_then_continues_under_local_scope(bridge, monkeypatch):
    from jarvis import development_sources

    calls = []

    def trusted(service, name, arguments, *, execution_scope, context=None, invoke=None):
        # This installed synthetic host issuer isolates the IPC proof from
        # sandbox source classification, covered by its own host-facet tests.
        calls.append((execution_scope, context.as_metadata()))
        result = invoke()
        return issue_tool_result(execution_scope, json.dumps(result, separators=(",", ":")),
                                 DataPolicy("approved_external", "verified-public-fixture"),
                                 "verified_public_fixture", ("synthetic-source-digest",))

    monkeypatch.setattr(development_sources, "dispatch_workspace_tool", trusted)
    bridge.read_result.clear()
    bridge.read_result.update(ok=True, content="public fixture")
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "completed"),
    ])
    enable_route(subject)
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200, response.text
    run_id = response.json()["developer_run_id"]
    assert len(calls) == 1
    scope, metadata = calls[0]
    assert scope.parent_request_id == metadata["developer_run_id"] == run_id
    assert metadata["sandbox_job_id"] == bridge.sandbox_job_id
    assert len(subject._client.chat.completions.requests) == 2
    context = subject._client.chat.completions.requests[-1]
    tool_message = next(item for item in context if item["role"] == "tool")
    assert json.loads(tool_message["content"]) == bridge.read_result
    assert "source_receipt" not in json.dumps(context)
    assert "signature" not in json.dumps(context)
    assert "_seal_key" not in json.dumps(context)


async def test_verified_public_failure_continues_with_fixed_error_and_no_raw_canary(bridge, monkeypatch):
    from jarvis import development_sources

    def known_public_failure(service, name, arguments, *, execution_scope, context=None, invoke=None):
        assert invoke()["ok"] is False
        return issue_tool_result(execution_scope, '{"ok":false,"error":"development_operation_failed"}',
                                 execution_scope.input_policy, "verified_public_failure")

    monkeypatch.setattr(development_sources, "dispatch_workspace_tool", known_public_failure)
    bridge.read_result.clear()
    bridge.read_result.update(ok=False, error=CANARY)
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "The operation failed."),
    ])
    enable_route(subject)
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200, response.text
    assert len(subject._client.chat.completions.requests) == 2
    last_context = subject._client.chat.completions.requests[-1]
    result = json.loads(next(item["content"] for item in last_context if item["role"] == "tool"))
    assert result == {"ok": False, "error": "development_operation_failed"}
    assert CANARY not in json.dumps(subject._client.chat.completions.requests)
    assert CANARY not in json.dumps(bridge.events)
    assert CANARY not in json.dumps(get_run(response.json()["developer_run_id"]))


async def test_caller_public_level_cannot_lower_verified_admin_floor(bridge, monkeypatch):
    from types import SimpleNamespace
    from jarvis import development_sources

    original_context = development_sources.creator_context
    floors = []

    def private_host_context(*args, **kwargs):
        verified = original_context(*args, **kwargs)
        return SimpleNamespace(input_floor=DataPolicy("local_only", "verified-private-host"),
                               as_metadata=verified.as_metadata)

    def trusted(service, name, arguments, *, execution_scope, context=None, invoke=None):
        floors.append(execution_scope.input_policy.level)
        return issue_tool_result(execution_scope, json.dumps(invoke(), separators=(",", ":")),
                                 DataPolicy("approved_external", "public-fixture"), "public_fixture")

    monkeypatch.setattr(development_sources, "creator_context", private_host_context)
    monkeypatch.setattr(development_sources, "dispatch_workspace_tool", trusted)
    bridge.read_result.clear()
    bridge.read_result.update(ok=True, content=CANARY, privacy="approved_external")
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "must never continue"),
    ])
    enable_route(subject)
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200, response.text
    assert floors == ["local_only"]
    assert len(subject._client.chat.completions.requests) == 1
    assert bridge.holder.is_armed()
    assert CANARY not in json.dumps(get_run(response.json()["developer_run_id"]))
    assert CANARY not in json.dumps(bridge.events)


async def test_verified_run_protected_after_operation_raises_receipt_before_continuation(bridge, monkeypatch):
    from jarvis import development_sources
    from jarvis.db import get_conn
    from jarvis.runlog.store import SENSITIVE_SENTINEL

    def approved_then_protected(service, name, arguments, *, execution_scope, context=None, invoke=None):
        result = invoke()
        # This independent host writer changes the actual durable run marker;
        # returned tool JSON contains no privacy authority.
        with get_conn() as conn:
            conn.execute("UPDATE agent_runs SET task=? WHERE run_id=?",
                         (SENSITIVE_SENTINEL, execution_scope.parent_request_id))
            conn.commit()
        assert get_run(execution_scope.parent_request_id)["run"]["task"] == SENSITIVE_SENTINEL
        return issue_tool_result(execution_scope, json.dumps(result, separators=(",", ":")),
                                 DataPolicy("approved_external", "verified-public-fixture"),
                                 "verified_public_fixture")

    monkeypatch.setattr(development_sources, "dispatch_workspace_tool", approved_then_protected)
    bridge.read_result.clear()
    bridge.read_result.update(ok=True, content=CANARY)
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "must never continue"),
    ])
    enable_route(subject)
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200, response.text
    assert len(subject._client.chat.completions.requests) == 1
    assert bridge.holder.is_armed()
    assert CANARY not in json.dumps(get_run(response.json()["developer_run_id"]))
    assert CANARY not in json.dumps(bridge.events)


async def test_final_signing_lock_serializes_concurrent_cancel_without_deadlock(bridge, monkeypatch):
    original_sign = development_attestation.sign_tool_source
    cancel_started, cancel_finished = threading.Event(), threading.Event()
    worker = None

    def cancel():
        cancel_started.set()
        try:
            skill_requests.update(bridge.owner, bridge.request_id, cancel_requested=True)
        finally:
            cancel_finished.set()

    def sign_during_cancel(*args, **kwargs):
        nonlocal worker
        worker = threading.Thread(target=cancel)
        worker.start()
        assert cancel_started.wait(1)
        assert not cancel_finished.wait(.02)  # final request lock still owns signing
        return original_sign(*args, **kwargs)

    monkeypatch.setattr(development_attestation, "sign_tool_source", sign_during_cancel)
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "must never continue"),
    ])
    enable_route(subject)
    try:
        response = await asyncio.wait_for(bridge.client.post("/dispatch", json=bridge.body), 2)
        assert response.status_code == 200, response.text
        assert await asyncio.to_thread(cancel_finished.wait, 1)
        assert skill_requests.get(bridge.owner, bridge.request_id)["cancel_requested"] is True
        assert len(subject._client.chat.completions.requests) == 1
    finally:
        if worker is not None:
            worker.join(1)
            assert not worker.is_alive()


@pytest.mark.parametrize("mutation", [
    "forged-labels", "cancel", "job", "owner", "revision", "run", "session-object", "key-rotation",
])
async def test_changed_binding_or_forged_receipt_stops_before_any_result_sink(bridge, monkeypatch, mutation):
    from jarvis import development_sources

    original = development_sources.dispatch_workspace_tool

    def altered(*args, **kwargs):
        result = original(*args, **kwargs)
        if mutation == "cancel":
            skill_requests.update(bridge.owner, bridge.request_id, cancel_requested=True)
        elif mutation == "job":
            skill_requests.update(bridge.owner, bridge.request_id, sandbox_job_id=str(uuid.uuid4()))
        elif mutation == "owner":
            from jarvis.skill_runtime import update_runtime_inventory
            update_runtime_inventory(bridge.session_id, [], True, active=True, owner_id="other-owner")
        elif mutation == "revision":
            skill_requests.update(bridge.owner, bridge.request_id, creator_revision="c" * 64)
        elif mutation == "run":
            skill_requests.update(bridge.owner, bridge.request_id, developer_run_id=str(uuid.uuid4()))
        elif mutation == "session-object":
            captured = active_session(bridge.session_id)
            register_session(bridge.session_id, bridge.owner, captured.dispatch)
        elif mutation == "key-rotation":
            import os
            issuer = development_attestation._issuers.pop(os.environ["MORTIMER_SANDBOX_HOME"])
            os.close(issuer.lease)
            development_attestation.ensure_admin_source_authority()
        return result

    monkeypatch.setattr(development_sources, "dispatch_workspace_tool", altered)
    if mutation == "forged-labels":
        original_sign = development_attestation.sign_tool_source

        def forge(*args, **kwargs):
            signed = original_sign(*args, **kwargs)
            signed["result"]["policy"] = {"level": "approved_external", "source": "provider-json"}
            return signed

        monkeypatch.setattr(development_attestation, "sign_tool_source", forge)
    bridge.read_result.clear()
    bridge.read_result.update(ok=True, content=CANARY)
    subject = bridge.start([
        ("tool", "file_read", {"path": "skills/bridge-skill/SKILL.md"}),
        ("text", "must never continue"),
    ])
    enable_route(subject)
    response = await bridge.client.post("/dispatch", json=bridge.body)
    assert response.status_code == 200, response.text
    run_id = response.json()["developer_run_id"]
    assert len(subject._client.chat.completions.requests) == 1
    assert len(bridge.sandbox_calls) == 1
    assert CANARY not in json.dumps(get_run(run_id))
    assert CANARY not in json.dumps(bridge.events)
    assert CANARY not in json.dumps(bridge.native_messages)
    assert not any(event["type"] == "agent_tool_result" for event in bridge.events)
    await asyncio.sleep(0)
