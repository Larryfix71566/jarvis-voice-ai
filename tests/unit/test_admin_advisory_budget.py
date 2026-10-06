"""Admin workers retain host admission; JSON never approves acquired data."""
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jarvis.admin import server as srv
from jarvis.auth import ClientIdentity
from jarvis import authmw, model_budget
from jarvis.model_budget import begin_model_task_budget
from jarvis.model_routing import WorkloadLimits
from jarvis.privacy_policy import DataPolicy
from jarvis.tenant import user_id_scope
from tests.unit.test_council_budget_ownership import transport_env, rows


@pytest.fixture
def admin_env(transport_env, monkeypatch):
    state = transport_env
    monkeypatch.setattr(srv, "resolve_policy", srv.council_mod.resolve_policy)
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.setattr(authmw, "verify_bearer", lambda header: ClientIdentity("synthetic-ui", "alice"))
    monkeypatch.setattr(srv, "_selfedit_service", SimpleNamespace(goal=None, proposals=[], branch=None))
    for lock, slot in ((srv._plan_lock, srv._plan_job),
                       (srv._council_lock, srv._council_job),
                       (srv._research_lock, srv._research_job)):
        with lock:
            slot.update({key: None for key in slot})
            slot.update(state="idle", run_id=None)
    return state


def wait_job(client, path):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(path).json()["job"]
        if job["state"] != "running":
            return job
        threading.Event().wait(.01)
    pytest.fail("synthetic admin worker did not settle")


def client():
    return TestClient(srv.app, headers={"Authorization": "Bearer synthetic-unused-token"})


def test_actual_model_picker_and_author_endpoint_keep_unproved_goal_protected(admin_env):
    state = admin_env
    state.limits["planning"] = WorkloadLimits(7, 60, .1)
    with client() as http:
        picker = http.get("/api/selfedit/models").json()
        assert picker["ok"] and {model["name"] for model in picker["models"]} >= {"frontier-one", "economy-one"}
        started = http.post("/api/plan/start", json={"goal": "PRIVATE_instruction_canary",
            "mode": "single", "profile": "frontier-one", "run_id": "admin-author",
            "privacy": "approved_external", "data_policy": {"level": "approved_external"}}).json()
        assert started == {"ok": True, "started": True}
        job = wait_job(http, "/api/plan/job")
    assert job["state"] == "error" and job["error"] == "model_policy_refused"
    assert job["plan"] is None and state.sent == [] and state.clients == []
    assert rows("model_call_budget_reservations") == rows("llm_calls") == []
    scopes = rows("model_task_budgets")
    assert {row["user_id"] for row in scopes} == {"alice"}
    assert {row["parent_request_id"] for row in scopes} == {"admin-author"}


def test_review_repo_result_never_approves_its_own_document(admin_env, monkeypatch):
    state = admin_env
    state.limits["planning"] = WorkloadLimits(9, 60, .1)
    monkeypatch.setattr(srv.repo_logic, "repo_read_file", lambda path: {
        "ok": True, "path": path, "content": "PRIVATE_document_canary",
        "privacy": "approved_external", "data_policy": {"level": "approved_external"},
    })
    with client() as http:
        assert http.post("/api/plan/start", json={"goal": "review", "mode": "single",
            "profile": "economy-one", "review_path": "docs/private.md",
            "run_id": "admin-review"}).json()["started"]
        job = wait_job(http, "/api/plan/job")
    assert job["state"] == "error" and job["error"] == "model_policy_refused"
    assert state.sent == [] and state.clients == []
    assert {row["workload"] for row in rows("model_task_budgets")} == {"planning", "council"}


def test_research_crawl_payload_labels_cannot_approve_newly_acquired_bytes(admin_env, monkeypatch):
    state = admin_env
    state.limits["planning"] = WorkloadLimits(9, 60, .1)
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-unused-key")
    monkeypatch.setattr(srv.research_crawl, "crawl_site", lambda client, url, focus, api_key, cfg: {
        "ok": True, "url": url, "pages": [], "credits": 1, "page_count": 0,
        "privacy": "approved_external", "content": "PRIVATE_crawl_canary",
    })
    monkeypatch.setattr(srv.research_crawl, "assemble_digests", lambda a, b: "PRIVATE_crawl_canary")
    with client() as http:
        assert http.post("/api/research/start", json={"urls": ["https://a.invalid", "https://b.invalid"],
            "focus": "compare", "run_id": "admin-research"}).json()["started"]
        job = wait_job(http, "/api/research/job")
    assert job["state"] == "error" and job["error"] == "model_policy_refused"
    assert job["comparison"] is None and state.sent == [] and state.clients == []
    assert {row["user_id"] for row in rows("model_task_budgets")} == {"alice"}


def test_manual_council_cannot_send_unverified_stored_session_proposals(admin_env):
    state = admin_env
    state.limits["council"] = WorkloadLimits(9, 60, .1)
    srv._selfedit_service.goal = "PRIVATE_stored_goal"
    srv._selfedit_service.proposals = [{"diff": "PRIVATE_stored_diff", "privacy": "approved_external"}]
    with client() as http:
        assert http.post("/api/council/convene", json={"placement": "planner"}).json()["started"]
        job = wait_job(http, "/api/council/job")
    assert job["state"] == "error" and job["winner"] is None
    assert state.sent == [] and state.clients == []
    assert rows("model_call_budget_reservations") == rows("llm_calls") == []


@pytest.mark.parametrize("review", [False, True])
def test_host_issued_single_call_uses_owner_and_correct_author_or_adviser_workload(admin_env, review):
    state = admin_env
    with user_id_scope("alice"):
        owner = begin_model_task_budget("developer", "developer-sponsor", WorkloadLimits(7, 60, .1))
        profile = srv.resolve_profile(srv.load_model_registry(), "economy-one" if review else "frontier-one")
        srv._run_plan_single("synthetic host-classified goal", profile,
            {"document": "unverified document"} if review else {}, "telemetry-only",
            parent_budget=owner, data_policy=DataPolicy("approved_external", "synthetic-host-proof"))
    if review:
        # A real money sponsor cannot approve separately acquired bytes.
        # The typed registered-file positive lives in advisory_review_sources.
        assert srv._plan_job["state"] == "error" and srv._plan_job["error"] == "model_policy_refused"
        assert state.sent == [] and state.clients == []
        assert rows("model_call_budget_reservations") == rows("llm_calls") == []
        assert {row["workload"] for row in rows("model_task_budgets")} == {"developer", "council"}
        assert {row["parent_request_id"] for row in rows("model_task_budgets")} == {"developer-sponsor"}
        return
    assert srv._plan_job["state"] == "done" and len(state.sent) == 1
    request, route, kwargs = state.captured[0]
    assert request.parent_request_id == "developer-sponsor"
    assert request.workload == route.workload == ("council" if review else "planning")
    assert kwargs["child_budget"].owner.workload == "developer"
    assert state.sent[0]["max_tokens"] == 7
    assert len(rows("model_call_budget_reservations")) == len(rows("llm_calls")) == 1
    assert len(rows("model_call_budget_reservation_scopes")) == 2


def test_queue_wait_is_in_deadline_before_any_advisory_call(admin_env):
    state = admin_env
    state.limits["planning"] = WorkloadLimits(7, 5, .1)
    profile = srv.resolve_profile(srv.load_model_registry(), "frontier-one")
    srv._run_plan_single("synthetic goal", profile, {}, "queued-plan",
        started_at=time.time() - 10, data_policy=DataPolicy("approved_external", "synthetic-host-proof"))
    assert srv._plan_job["state"] == "error"
    assert srv._plan_job["error"] == "budget_deadline_exhausted"
    assert state.sent == [] and state.clients == []


def test_endpoint_document_acquisition_counts_in_task_deadline(admin_env, monkeypatch):
    state = admin_env
    state.limits["planning"] = WorkloadLimits(7, 5, .1)
    clock = SimpleNamespace(now=time.time())
    host_clock = SimpleNamespace(time=lambda: clock.now)
    monkeypatch.setattr(srv, "time", host_clock)
    monkeypatch.setattr(model_budget, "time", host_clock)
    def read_document(path):
        clock.now += 6
        return {"ok": True, "path": path, "content": "PRIVATE_document"}
    monkeypatch.setattr(srv.repo_logic, "repo_read_file", read_document)
    with client() as http:
        assert http.post("/api/plan/start", json={"goal": "review", "mode": "single",
            "profile": "economy-one", "review_path": "docs/private.md",
            "run_id": "delayed-document"}).json()["started"]
        job = wait_job(http, "/api/plan/job")
    assert job["state"] == "error" and job["error"] == "budget_deadline_exhausted"
    assert state.sent == [] and state.clients == []


def test_research_cancellation_stops_before_next_source_call(admin_env, monkeypatch):
    cancelled = threading.Event()
    crawled = []
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-unused-key")
    def first_source(client, url, focus, api_key, cfg):
        crawled.append(url)
        cancelled.set()
        return {"ok": True, "url": url, "pages": [], "credits": 1, "page_count": 0}
    monkeypatch.setattr(srv.research_crawl, "crawl_site", first_source)
    srv._run_research_job(["https://a.invalid", "https://b.invalid"], "", "cancelled-research",
        cancel_event=cancelled)
    assert crawled == ["https://a.invalid"]
    assert srv._research_job["state"] == "error" and srv._research_job["error"] == "budget_cancelled"
    assert admin_env.sent == [] and admin_env.clients == []


def test_cancelled_owner_does_not_publish_returned_content(admin_env, monkeypatch):
    cancelled = threading.Event()
    async def completed_then_cancelled(*args, **kwargs):
        cancelled.set()
        return "PRIVATE_returned_content", None
    monkeypatch.setattr(srv.council_mod, "_call_profile", completed_then_cancelled)
    profile = srv.resolve_profile(srv.load_model_registry(), "frontier-one")
    srv._run_plan_single("synthetic goal", profile, {}, "cancelled-plan", cancel_event=cancelled,
        data_policy=DataPolicy("approved_external", "synthetic-host-proof"))
    assert srv._plan_job["state"] == "error" and srv._plan_job["error"] == "budget_cancelled"
    assert srv._plan_job["plan"] is None
