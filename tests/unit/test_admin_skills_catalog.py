"""Read-only Skills catalog/detail API contract."""
from __future__ import annotations

from fastapi.testclient import TestClient

from jarvis.admin.server import app


def test_catalog_lists_registered_skills_with_unverified_readiness():
    response = TestClient(app).get("/api/skills")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 1
    assert len(data["catalog_revision"]) == 64
    assert data["capabilities"] == {
        "process_view": True, "activity_trace": True, "authoring": False,
    }
    assert {item["skill_id"] for item in data["items"]} >= {
        "current-weather-with-fahrenheit", "technical-plan-document",
    }
    by_id = {item["skill_id"]: item for item in data["items"]}
    assert all(by_id[name]["enabled"] for name in {
        "current-weather-with-fahrenheit", "git-history-and-status-review",
        "layered-geolocation", "technical-plan-document", "mcp-server-authoring",
    })
    assert by_id["skill-creator"]["enabled"] is False
    assert data["capabilities"]["authoring"] is False
    assert all(by_id[name]["readiness"] == "unknown" for name in {
        "current-weather-with-fahrenheit", "git-history-and-status-review",
        "layered-geolocation", "technical-plan-document", "mcp-server-authoring",
    })
    assert by_id["skill-creator"]["readiness"] == "blocked"
    assert "skill_disabled" in by_id["skill-creator"]["readiness_reasons"]
    assert all(isinstance(item["readiness_reasons"], list) for item in data["items"])
    assert all("revision_enforcement_disabled" in item["readiness_reasons"]
               for item in data["items"])
    assert all(item["revision"] for item in data["items"])
    assert "implementation-plan" in by_id["technical-plan-document"]["example_ids"]


def test_catalog_paginates_and_rejects_invalid_bounds():
    client = TestClient(app)
    page = client.get("/api/skills", params={"limit": 2})
    assert page.status_code == 200
    first = page.json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] == "2"
    second = client.get("/api/skills", params={
        "limit": 2, "cursor": first["next_cursor"],
    }).json()
    assert not ({item["skill_id"] for item in first["items"]}
                & {item["skill_id"] for item in second["items"]})
    assert client.get("/api/skills", params={"limit": 101}).status_code == 400
    assert client.get("/api/skills", params={"cursor": "../bad"}).status_code == 400


def test_skill_detail_contains_reviewed_process_not_instructions():
    skill_id = "technical-plan-document"
    response = TestClient(app).get(f"/api/skills/{skill_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["skill_id"] == skill_id
    assert data["process_kind"] == "linear"
    assert data["process_nodes"][0]["step_id"] == "establish-scope"
    assert data["readiness"] == "unknown"
    assert "model_route_compatibility_unverified" in data["readiness_reasons"]
    assert "body" not in data
    assert "Instructions" not in repr(data)
    assert len(data["revision"]) == 64


def test_skill_detail_is_revision_bound_and_does_not_accept_paths():
    client = TestClient(app)
    skill_id = "technical-plan-document"
    response = client.get(f"/api/skills/{skill_id}")
    revision = response.json()["revision"]
    assert client.get(f"/api/skills/{skill_id}", params={"revision": revision}).status_code == 200
    assert client.get(f"/api/skills/{skill_id}", params={"revision": "0" * 64}).status_code == 409
    assert client.get("/api/skills/../SKILL.md").status_code in {400, 404}


def test_skill_versions_reports_package_pin_and_only_callers_candidate_ledger(
    monkeypatch, tmp_path,
):
    import uuid

    from jarvis import skill_requests
    from jarvis.admin import server
    from jarvis.agent_skills import read_skill_registry

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "owner-a")
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id, "operation": "test",
        "skill_id": "technical-plan-document", "skill_revision": "a" * 64,
    }
    skill_requests.reserve("owner-a", payload)
    skill_requests.update(
        "owner-a", request_id, state="completed", candidate_revision="b" * 64,
        candidate_digest="c" * 64,
    )
    other_id = str(uuid.uuid4())
    skill_requests.reserve("owner-b", {
        **payload, "request_id": other_id,
    })
    skill_requests.update(
        "owner-b", other_id, state="completed", candidate_revision="d" * 64,
        candidate_digest="e" * 64,
    )

    result = TestClient(server.app).get("/api/skills/technical-plan-document/versions")
    assert result.status_code == 200
    body = result.json()
    _, pins, registry_version, _ = read_skill_registry()
    assert body["installed"]["declared_version"]
    assert len(body["installed"]["package_revision"]) == 64
    assert body["registry"]["schema_version"] == registry_version
    assert body["registry"]["active_pin"] == pins["technical-plan-document"]
    assert body["registry"]["pin_state"] == "matches_installed"
    assert body["installed"]["enabled"] is True
    assert [candidate["request_id"] for candidate in body["candidates"]] == [request_id]
    assert body["candidates"][0]["candidate_revision"] == "b" * 64
    assert all("user_id" not in candidate and "payload_digest" not in candidate
               for candidate in body["candidates"])
    assert "activation or rollback" in body["limitations"][-1]


def test_skill_versions_requires_authenticated_request_owner(monkeypatch):
    from jarvis.admin import server

    def unavailable(_request):
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="authenticated identity is unavailable")

    monkeypatch.setattr(server, "_skill_request_owner", unavailable)
    result = TestClient(server.app).get("/api/skills/technical-plan-document/versions")
    assert result.status_code == 503


def test_skill_example_preview_serves_only_declared_synthetic_matcher_cases():
    client = TestClient(app)
    response = client.get("/api/skills/technical-plan-document/examples/implementation-plan")
    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "skill_id": "technical-plan-document",
        "example_id": "implementation-plan",
        "request": "Write a model-ready implementation plan with explicit design decisions, phases and acceptance criteria.",
        "expect_selected": True,
        "synthetic": True,
    }
    assert client.get("/api/skills/technical-plan-document/examples/not-declared").status_code == 404
    assert client.get("/api/skills/../examples/implementation-plan").status_code in {400, 404}
