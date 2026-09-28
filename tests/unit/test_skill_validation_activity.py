import json
import uuid

import pytest

from jarvis import skill_requests as requests
from jarvis.db import get_conn, run_migrations
from jarvis.runlog.store import RunLogger, get_skill_events
from jarvis.skill_authoring import SkillAuthoringService
from jarvis.skill_creator_agent import CREATOR_PACKAGE_REVISION
from jarvis.skill_validation_activity import sync_validation_activity
from jarvis.tenant import user_id_scope
from tests.sandbox_fakes import FakeRuntime
from tests.unit.test_skill_authoring_service import _draft_valid_weather_skill


@pytest.fixture
def validation(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "activity.db"))
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    run_migrations()
    runtime = FakeRuntime(tmp_path)
    kwargs = {"repository": lambda: "owner/repo", "token": lambda: "host-token",
              "base_branch": lambda: "main", "runtime_factory": lambda: runtime}
    service = SkillAuthoringService("weather-brief", **kwargs)
    assert _draft_valid_weather_skill(service)["ok"]
    runtime.current.state["run_id"] = "sandbox-job"
    parent_id, test_id = str(uuid.uuid4()), str(uuid.uuid4())
    requests.reserve("owner", {"operation": "draft", "request_id": parent_id,
                               "skill_id": "weather-brief", "bot_session_id": "session"})
    requests.update("owner", parent_id, state="drafting", sandbox_job_id=runtime.current.state["run_id"])
    with user_id_scope("owner"):
        run = RunLogger("creator-run", "developer", "Developer", "Create skill",
                        session_id="session", root=tmp_path / "logs")
        run.start()
        requests.associate_developer_run("owner", parent_id, session_id="session",
                                         run_id=run.run_id, creator_revision=CREATOR_PACKAGE_REVISION)
        run.skill_event("skill-creator", CREATOR_PACKAGE_REVISION, "skill_selected")
        run.finish("Draft ready")
    requests.reserve("owner", {"operation": "test", "request_id": test_id,
                               "skill_id": "weather-brief", "job_id": parent_id})
    monkeypatch.setattr(requests, "_service", lambda slug, **opts: SkillAuthoringService(slug, **kwargs, **opts))
    return test_id, parent_id, run, service


def _events():
    return get_skill_events("creator-run", user_id="owner")["events"]


def _terminal_row():
    with get_conn() as conn:
        return dict(conn.execute("SELECT * FROM agent_runs WHERE run_id='creator-run'").fetchone())


def _complete(test_id, service):
    state = requests.get("owner", test_id)
    assert service.validate(validation_request_id=test_id,
                            validation_attempt_id=state["validation_attempt_id"])["ok"]
    status = service.status()
    requests.update("owner", test_id, state="completed", result_code="offline_validation_passed",
                    candidate_digest=status["candidate"], candidate_revision=status["package_revision"])


def _attempt(test_id):
    requests.update("owner", test_id, state="testing", validation_attempt_id=str(uuid.uuid4()),
                    validation_started_at=requests._now())


def test_worker_attaches_verified_result_to_finished_run_once(validation):
    test_id, _, _, _ = validation
    before = _terminal_row()
    requests._run_offline_validation("owner", test_id, "weather-brief")
    assert requests.get("owner", test_id)["state"] == "completed"
    assert [(e["type"], e["status"]) for e in _events()] == [
        ("skill_selected", "unknown"), ("skill_step_started", "running"),
        ("skill_step_finished", "passed"),
    ]
    assert _terminal_row() == before
    requests.reconcile("owner", test_id)
    requests.reconcile("owner", test_id)
    assert len(_events()) == 3
    assert _terminal_row() == before


def test_recovery_never_fabricates_missing_started_event(validation):
    test_id, _, _, service = validation
    _attempt(test_id)
    _complete(test_id, service)
    assert sync_validation_activity("owner", test_id) == "attempt_not_started"
    assert len(_events()) == 1


def test_restart_attaches_existing_attempt_without_rerunning_validator(validation):
    test_id, _, _, service = validation
    before = _terminal_row()
    _attempt(test_id)
    assert sync_validation_activity("owner", test_id, start=True) == "recorded"
    requests.update("owner", test_id, validation_baseline_phase="editing",
                    validation_baseline_candidate=service.status()["candidate"])
    state = requests.get("owner", test_id)
    assert service.validate(validation_request_id=test_id,
                            validation_attempt_id=state["validation_attempt_id"])["ok"]
    runtime = service._runtime()
    events_before = list(runtime.events)
    assert requests.reconcile("owner", test_id)["state"] == "completed"
    assert _events()[-1]["status"] == "passed"
    assert runtime.events == events_before
    assert _terminal_row() == before


def test_other_owner_cannot_attach_activity(validation):
    test_id, _, _, _ = validation
    _attempt(test_id)
    assert sync_validation_activity("another-owner", test_id, start=True) == "unbound"
    assert len(_events()) == 1


@pytest.mark.parametrize("mutation", ["cancelled", "protected", "wrong-run", "wrong-pin",
                                     "bad-receipt", "wrong-attempt", "wrong-request"])
def test_late_pass_refuses_invalid_or_private_context(validation, mutation):
    test_id, _, run, service = validation
    _attempt(test_id)
    assert sync_validation_activity("owner", test_id, start=True) == "recorded"
    _complete(test_id, service)
    if mutation == "cancelled":
        requests.update("owner", test_id, state="cancelled", cancel_requested=True)
    elif mutation == "protected":
        run.mark_sensitive()
    elif mutation == "wrong-run":
        requests.update("owner", test_id, originating_developer_run_id="other-run")
    elif mutation == "wrong-pin":
        requests.update("owner", test_id, originating_creator_revision="b" * 64)
    elif mutation == "bad-receipt":
        receipt = service._session().directory / "skill-authoring-validation.json"
        receipt.write_text('{"passed":true}')
    else:
        path = service._session().directory / "skill-authoring-validation.json"
        receipt = json.loads(path.read_text())
        key = "validation_attempt_id" if mutation == "wrong-attempt" else "validation_request_id"
        receipt[key] = str(uuid.uuid4())
        path.write_text(json.dumps(receipt))
    assert sync_validation_activity("owner", test_id) != "accepted"
    assert not any(e["type"] == "skill_step_finished" and e["status"] == "passed" for e in _events())


def test_failed_validation_is_visible_without_changing_terminal_run(validation):
    test_id, _, _, _ = validation
    before = _terminal_row()
    _attempt(test_id)
    assert sync_validation_activity("owner", test_id, start=True) == "recorded"
    requests.update("owner", test_id, state="failed", result_code="offline_validation_failed")
    assert sync_validation_activity("owner", test_id) == "recorded"
    assert sync_validation_activity("owner", test_id) == "already_recorded"
    assert _events()[-1]["status"] == "failed"
    assert _terminal_row() == before
