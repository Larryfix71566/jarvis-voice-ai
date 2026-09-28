"""Authenticated, bounded evidence from the live voice SkillRegistry."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from jarvis import auth
from jarvis.admin.server import app
from jarvis.agent_skills import SKILLS_DIR
from jarvis.bot.skill_runtime_reporter import (
    inventory_payload,
    run_skill_runtime_reporter,
)
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.skill_catalog import inspect_package
from jarvis.skill_runtime import (
    MAX_RUNTIME_SESSIONS,
    MAX_TOOLS,
    clear_runtime_inventories,
    current_runtime_tools,
    runtime_owner,
    update_runtime_inventory,
)
from jarvis.skill_service import ToolInventory, evaluate_readiness


def _token(tmp_path, name: str, monkeypatch) -> str:
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "runtime-auth.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    token = auth.mint_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO client_tokens (user_id, name, token_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("larry", name, auth.hash_token(token), now_iso()),
        )
        conn.commit()
    return token


@pytest.fixture(autouse=True)
def clear_receipts():
    clear_runtime_inventories()
    yield
    clear_runtime_inventories()


def test_inventory_is_short_lived_and_conservative_across_live_sessions(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("jarvis.skill_runtime.time.monotonic", lambda: clock[0])
    update_runtime_inventory("00000000-0000-0000-0000-000000000001",
                             ["get_weather", "repo_read_file"], True, active=True)
    update_runtime_inventory("00000000-0000-0000-0000-000000000002",
                             ["get_weather"], True, active=True)
    assert current_runtime_tools() == frozenset({"get_weather"})

    update_runtime_inventory("00000000-0000-0000-0000-000000000002",
                             [], False, active=False)
    assert current_runtime_tools() == frozenset({"get_weather", "repo_read_file"})

    clock[0] += 46
    assert current_runtime_tools() is None


def test_capacity_overflow_makes_intersection_unknown_until_missing_runtime_is_stale(
    monkeypatch,
):
    clock = [100.0]
    monkeypatch.setattr("jarvis.skill_runtime.time.monotonic", lambda: clock[0])
    for index in range(MAX_RUNTIME_SESSIONS):
        update_runtime_inventory(
            f"00000000-0000-0000-0000-{index + 1:012d}",
            ["get_weather"], True, active=True,
        )
    assert current_runtime_tools() == frozenset({"get_weather"})

    with pytest.raises(ValueError, match="runtime_capacity_exceeded"):
        update_runtime_inventory(
            "00000000-0000-0000-0000-000000000099", [], True, active=True,
        )
    # Do not infer that the rejected ninth runtime has tools just because all
    # eight retained inventories report the same tool.
    assert current_runtime_tools() is None

    clock[0] += 46
    for index in range(MAX_RUNTIME_SESSIONS):
        update_runtime_inventory(
            f"00000000-0000-0000-0000-{index + 1:012d}",
            ["get_weather"], True, active=True,
        )
    assert current_runtime_tools() == frozenset({"get_weather"})


def test_incomplete_or_missing_runtime_evidence_stays_unknown():
    assert current_runtime_tools() is None


def test_runtime_owner_is_authenticated_scoped_and_cannot_be_replaced():
    runtime_id = "00000000-0000-0000-0000-000000000001"
    update_runtime_inventory(
        runtime_id, ["get_weather"], True, active=True, owner_id="larry",
    )
    assert runtime_owner(runtime_id) == "larry"
    with pytest.raises(ValueError, match="runtime_owner_mismatch"):
        update_runtime_inventory(
            runtime_id, [], False, active=False, owner_id="another-user",
        )
    assert runtime_owner(runtime_id) == "larry"
    update_runtime_inventory(
        runtime_id, [], False, active=False, owner_id="larry",
    )
    assert runtime_owner(runtime_id) is None


def test_live_receipt_only_resolves_discovered_tool_evidence():
    skill = inspect_package(SKILLS_DIR / "current-weather-with-fahrenheit")
    configured = ToolInventory(frozenset({"get_weather"}), complete=True)
    before = evaluate_readiness(
        skill,
        tool_inventory=configured,
        credential_presence={},
        revision_enforcement=False,
        route_compatible=True,
        sandbox_available=True,
    )
    assert "tool_runtime_unverified" in before.reason_codes

    update_runtime_inventory("00000000-0000-0000-0000-000000000001",
                             [], True, active=True)
    after = evaluate_readiness(
        skill,
        tool_inventory=configured,
        credential_presence={},
        runtime_tools=current_runtime_tools(),
        revision_enforcement=False,
        route_compatible=True,
        sandbox_available=True,
    )
    assert "required_tool_unavailable:get_weather" in after.reason_codes
    assert after.state == "blocked"
    update_runtime_inventory("00000000-0000-0000-0000-000000000001",
                             [], False, active=True)
    assert current_runtime_tools() is None


@pytest.mark.parametrize("runtime_id,tools,complete", [
    ("not-a-uuid", [], True),
    ("00000000-0000-0000-0000-000000000001", ["bad tool"], True),
    ("00000000-0000-0000-0000-000000000001", ["a"] * 257, True),
    ("00000000-0000-0000-0000-000000000001", ["same", "same"], True),
])
def test_inventory_rejects_malformed_or_oversized_data(runtime_id, tools, complete):
    with pytest.raises(ValueError):
        update_runtime_inventory(runtime_id, tools, complete, active=True)


def test_service_bot_only_can_submit_and_receipt_is_not_echoed(tmp_path, monkeypatch):
    service_token = _token(tmp_path, "service-bot", monkeypatch)
    client = TestClient(app)
    path = "/api/skills/runtime-inventory"
    payload = {
        "schema_version": 1,
        "runtime_id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "larry",
        "active": True,
        "complete": True,
        "tools": ["get_weather"],
    }

    assert client.post(path, json=payload).status_code == 401
    other_token = _token(tmp_path, "ordinary-client", monkeypatch)
    rejected = client.post(path, json=payload,
                           headers={"Authorization": f"Bearer {other_token}"})
    assert rejected.status_code == 403
    assert current_runtime_tools() is None

    accepted = client.post(path, json=payload,
                           headers={"Authorization": f"Bearer {service_token}"})
    assert accepted.status_code == 200
    assert accepted.json() == {"ok": True}
    assert current_runtime_tools() == frozenset({"get_weather"})


def test_endpoint_rejects_extra_fields_wrong_schema_and_oversized_tools(tmp_path, monkeypatch):
    token = _token(tmp_path, "service-bot", monkeypatch)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "schema_version": 1,
        "runtime_id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "larry",
        "active": True,
        "complete": True,
        "tools": [],
    }
    assert client.post("/api/skills/runtime-inventory",
                       json={**payload, "secret": "must-not-be-accepted"},
                       headers=headers).status_code == 422
    assert client.post("/api/skills/runtime-inventory",
                       json={**payload, "schema_version": 2},
                       headers=headers).status_code == 400
    assert client.post("/api/skills/runtime-inventory",
                       json={**payload, "tools": [f"tool_{n}" for n in range(MAX_TOOLS + 1)]},
                       headers=headers).status_code == 422
    assert current_runtime_tools() is None


def test_inventory_endpoint_bounds_runtime_id_and_each_tool_name(tmp_path, monkeypatch):
    token = _token(tmp_path, "service-bot", monkeypatch)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "schema_version": 1,
        "runtime_id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "larry",
        "active": True,
        "complete": True,
        "tools": ["get_weather"],
    }

    assert client.post(
        "/api/skills/runtime-inventory",
        json={**payload, "runtime_id": "x" * 37}, headers=headers,
    ).status_code == 422
    assert client.post(
        "/api/skills/runtime-inventory",
        json={**payload, "tools": ["x" * 129]}, headers=headers,
    ).status_code == 422
    assert current_runtime_tools() is None


def test_reporter_publishes_loaded_names_then_removes_receipt_on_cancel():
    class Registry:
        server_names = ["mcp-weather"]

        def tools_for(self, servers):
            assert servers == ["mcp-weather"]
            return ["get_weather"]

    sent = []

    async def send(payload):
        sent.append(payload)
        if payload["active"]:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_skill_runtime_reporter(
            Registry(), "00000000-0000-0000-0000-000000000001", send=send,
        ))
    assert sent == [
        inventory_payload("00000000-0000-0000-0000-000000000001",
                          ["get_weather"], active=True),
        inventory_payload("00000000-0000-0000-0000-000000000001",
                          [], active=False),
    ]
