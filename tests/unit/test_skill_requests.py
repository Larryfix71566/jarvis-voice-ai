import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from jarvis import auth
from jarvis.admin import server
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.skill_catalog import list_catalog
from jarvis.skill_requests import SkillRequestError, get, reserve


def _catalog_revision():
    import hashlib
    entries = list_catalog()
    return hashlib.sha256("\n".join(
        f"{item.skill_id}:{item.revision or 'invalid'}:{int(item.enabled)}" for item in entries
    ).encode("utf-8")).hexdigest()


def _draft_payload(**overrides):
    return {
        "schema_version": 1,
        "operation": "draft",
        "request_id": str(uuid.uuid4()),
        "bot_session_id": "00000000-0000-0000-0000-000000000001",
        "expected_catalog_revision": _catalog_revision(),
        "skill_id": "request-test-skill",
        "skill_revision": None,
        "privacy_context": "standard",
        "task_brief": "Draft a small skill for local testing.",
        **overrides,
    }


def _sandbox_job(payload, owner="larry"):
    return get(owner, payload["request_id"])["sandbox_job_id"]


def test_developer_association_has_one_winner_and_does_not_revive_cancelled_work(tmp_path, monkeypatch):
    from jarvis.skill_requests import associate_developer_run, update
    from jarvis.skill_creator_agent import CREATOR_PACKAGE_REVISION

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    update("larry", payload["request_id"], state="drafting")
    run_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    barrier = threading.Barrier(2)

    def associate(run_id):
        barrier.wait()
        try:
            associate_developer_run(
                "larry", payload["request_id"], session_id=payload["bot_session_id"],
                run_id=run_id, creator_revision=CREATOR_PACKAGE_REVISION,
            )
            return run_id
        except SkillRequestError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = list(pool.map(associate, run_ids))
    assert sum(item is not None for item in winners) == 1
    winner = next(item for item in winners if item)
    assert get("larry", payload["request_id"])["developer_run_id"] == winner
    associate_developer_run(
        "larry", payload["request_id"], session_id=payload["bot_session_id"],
        run_id=winner, creator_revision=CREATOR_PACKAGE_REVISION,
    )
    update("larry", payload["request_id"], cancel_requested=True)
    with pytest.raises(SkillRequestError):
        associate_developer_run(
            "larry", payload["request_id"], session_id=payload["bot_session_id"],
            run_id=winner, creator_revision=CREATOR_PACKAGE_REVISION,
        )


def _mock_developer_creator(monkeypatch, payload, *, owner="larry", before=None,
                            status="ok"):
    from jarvis import skill_requests

    run_id = str(uuid.uuid4())

    def dispatch(user_id, state, _brief):
        assert user_id == owner
        skill_requests.update(user_id, state["request_id"], developer_run_id=run_id)
        if before is not None:
            before()
        return {"ok": True, "request_id": state["request_id"], "developer_run_id": run_id}

    monkeypatch.setattr(skill_requests, "_dispatch_developer_creator", dispatch)
    monkeypatch.setattr("jarvis.runlog.store.get_run", lambda requested: {"run": {
        "run_id": run_id, "agent": "developer", "user_id": owner,
        "session_id": payload["bot_session_id"], "status": status,
    }} if requested == run_id else None)


def test_request_receipt_is_user_scoped_and_rejects_payload_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    original, created = reserve("larry", payload)
    assert created is True
    assert get("larry", payload["request_id"])["state"] == "queued"
    assert get("another-user", payload["request_id"]) is None
    replay, created = reserve("larry", payload)
    assert created is False
    assert replay["job_id"] == original["job_id"]
    changed = {**payload, "task_brief": "A different goal."}
    with pytest.raises(SkillRequestError) as exc:
        reserve("larry", changed)
    assert exc.value.status_code == 409
    record = next(tmp_path.glob("skill-requests/*.json"))
    assert record.stat().st_mode & 0o777 == 0o600
    assert payload["task_brief"] not in record.read_text()
    assert "payload_digest" in json.loads(record.read_text())


def test_request_status_requires_canonical_uuid_and_hides_binding(tmp_path, monkeypatch):
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    status = get("larry", payload["request_id"])
    assert "payload_digest" not in status and "user_id" not in status
    assert status["request_id"] == payload["request_id"]
    with pytest.raises(SkillRequestError):
        get("larry", "../bad")


def test_skill_creator_draft_is_rejected_before_request_or_vm_startup(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload(skill_id="skill-creator")
    monkeypatch.setattr(
        skill_requests, "_service",
        lambda _slug: pytest.fail("creator self-modification must not allocate a sandbox"),
    )

    with pytest.raises(SkillRequestError, match="creator cannot modify its own package"):
        skill_requests.start_draft("larry", payload)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("claimed_state", ["starting", "testing"])
def test_queued_job_claim_is_atomic_across_independent_worker_locks(
        tmp_path, monkeypatch, claimed_state):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=2)
        return skill_requests._claim_queued_request(
            "larry", payload["request_id"], state_name=claimed_state,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _index: claim(), range(2)))

    assert sum(did_claim for _state, did_claim in claims) == 1
    assert get("larry", payload["request_id"])["state"] == claimed_state


def test_draft_runs_bounded_creator_and_requires_host_validation_receipt(tmp_path, monkeypatch):
    from jarvis import skill_requests
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    _mock_developer_creator(monkeypatch, payload)

    class Service:
        def start_session(self, brief, run_id):
            assert brief == payload["task_brief"]
            assert run_id == _sandbox_job(payload)
            return {"ok": True, "session_id": "session-1", "branch": "skill/new", "source_commit": "abc"}

        def status(self):
            return {"run_id": _sandbox_job(payload), "phase": "validated", "validated_ok": True,
                    "candidate": "b" * 64, "package_revision": "a" * 64}

    class Creator:
        cancel_requested = False
        def run(self, brief):
            assert brief == payload["task_brief"]
            return {"ok": True, "text": "untrusted model claim"}

    service = Service()
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: service)
    import jarvis.skill_creator_agent as creator_module
    monkeypatch.setattr(creator_module, "build_skill_creator_agent", lambda *_args, **_kwargs: (Creator(), "c" * 64))
    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])
    saved = get("larry", payload["request_id"])
    assert saved["state"] == "review_ready"
    assert saved["candidate_digest"] == "b" * 64
    assert saved["candidate_revision"] == "a" * 64
    assert "untrusted model claim" not in json.dumps(saved)


def test_draft_model_success_without_host_receipt_never_becomes_review_ready(tmp_path, monkeypatch):
    from jarvis import skill_requests
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    _mock_developer_creator(monkeypatch, payload)

    class Service:
        def start_session(self, *_args, **_kwargs): return {"ok": True, "session_id": "s"}
        def status(self): return {"run_id": _sandbox_job(payload), "phase": "drafting", "validated_ok": False}

    class Creator:
        cancel_requested = False
        def run(self, _brief): return {"ok": True, "text": "I validated it"}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    import jarvis.skill_creator_agent as creator_module
    monkeypatch.setattr(creator_module, "build_skill_creator_agent", lambda *_args, **_kwargs: (Creator(), "c" * 64))
    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])
    saved = get("larry", payload["request_id"])
    assert saved["state"] == "draft_needs_attention"
    assert saved.get("candidate_digest") is None


def test_draft_lost_start_response_is_reconciled_by_stable_run_id(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)

    class Service:
        def start_session(self, *_args, **_kwargs):
            # Model an exception after sandbox allocation but before the host
            # receives the successful start receipt.
            raise TimeoutError("lost start response")

        def status(self):
            return {"run_id": _sandbox_job(payload), "phase": "editing",
                    "active": True, "branch": "mortimer/skill/working"}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])

    uncertain = get("larry", payload["request_id"])
    assert uncertain["state"] == "needs_reconciliation"
    assert uncertain["result_code"] == "sandbox_start_result_uncertain"

    recovered = skill_requests.reconcile("larry", payload["request_id"])
    assert recovered["state"] == "drafting"
    assert recovered["branch"] == "mortimer/skill/working"


def test_draft_uncertain_start_without_matching_run_stays_reconciliation_only(
    tmp_path, monkeypatch,
):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    skill_requests.update("larry", payload["request_id"],
                          state="needs_reconciliation",
                          result_code="sandbox_start_result_uncertain")
    status_calls = []

    class Service:
        def start_session(self, *_args, **_kwargs):
            pytest.fail("uncertain starts must never be automatically repeated")

        def status(self):
            status_calls.append(True)
            return {"active": False, "phase": "idle"}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    recovered = skill_requests.reconcile("larry", payload["request_id"])
    assert recovered["state"] == "needs_reconciliation"
    assert recovered["result_code"] == "sandbox_start_result_uncertain"
    assert status_calls == [True]


def test_draft_cancel_during_start_prevents_creator_from_running(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    cancel_request = {
        "schema_version": 1, "operation": "cancel", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": payload["expected_catalog_revision"],
        "skill_id": payload["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": payload["request_id"],
    }

    class Service:
        cancelled = False

        def start_session(self, *_args, **_kwargs):
            cancelled, created = skill_requests.cancel_job("larry", cancel_request)
            assert created is True
            assert cancelled["state"] == "cancelled"
            return {"ok": True, "session_id": "session-1"}

        def status(self):
            return {
                "run_id": _sandbox_job(payload),
                "phase": "cancelled" if self.cancelled else "drafting",
                "active": not self.cancelled,
            }

        def cancel(self):
            self.cancelled = True
            return {"ok": True}

    service = Service()
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: service)
    import jarvis.skill_creator_agent as creator_module
    monkeypatch.setattr(
        creator_module, "build_skill_creator_agent",
        lambda *_args, **_kwargs: pytest.fail("cancelled draft must not start creator"),
    )

    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])

    saved = get("larry", payload["request_id"])
    assert saved["state"] == "cancelled"
    assert saved["result_code"] == "cancelled_before_authoring"
    assert saved.get("candidate_digest") is None


def test_failed_sandbox_cancel_remains_pending_for_reconciliation(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    cancel_request = {
        "schema_version": 1, "operation": "cancel", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": payload["expected_catalog_revision"],
        "skill_id": payload["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": payload["request_id"],
    }

    class Service:
        def start_session(self, *_args, **_kwargs):
            cancelled, created = skill_requests.cancel_job("larry", cancel_request)
            assert created is True
            assert cancelled["state"] == "cancel_requested"
            return {"ok": True, "session_id": "session-1"}

        def status(self):
            return {
                "run_id": _sandbox_job(payload), "phase": "drafting",
                "active": True,
            }

        def cancel(self):
            return {"ok": False, "error": "synthetic stop failure"}

    service = Service()
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: service)
    import jarvis.skill_creator_agent as creator_module
    monkeypatch.setattr(
        creator_module, "build_skill_creator_agent",
        lambda *_args, **_kwargs: pytest.fail("pending cancellation must not start creator"),
    )

    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])

    saved = get("larry", payload["request_id"])
    assert saved["state"] == "cancel_requested"
    assert saved["result_code"] == "cancellation_needs_reconciliation"
    assert saved.get("candidate_digest") is None


def test_stale_cancellation_never_stops_replacement_skill_session():
    from jarvis.skill_requests import _cancel_service_session

    class Service:
        cancel_calls = 0

        def status(self):
            return {"run_id": "replacement-run", "phase": "editing", "active": True}

        def cancel(self):
            self.cancel_calls += 1
            return {"ok": True}

    service = Service()
    assert _cancel_service_session(service, "old-run") is False
    assert service.cancel_calls == 0


def test_cancelled_replacement_run_does_not_confirm_old_draft_cancellation(
        tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    _mock_developer_creator(
        monkeypatch, payload,
        before=lambda: skill_requests.update(
            "larry", payload["request_id"],
            state="cancel_requested", cancel_requested=True,
        ),
    )

    class Service:
        def start_session(self, *_args, **_kwargs):
            return {"ok": True, "session_id": "old-session"}

        def status(self):
            return {"run_id": "replacement-run", "phase": "cancelled", "active": False}

        def cancel(self):
            pytest.fail("a stale request must not cancel the replacement run")

    class Creator:
        cancel_requested = False

        def run(self, _brief):
            self.cancel_requested = True
            skill_requests.update(
                "larry", payload["request_id"],
                state="cancel_requested", cancel_requested=True,
            )
            return {"ok": False}

    service = Service()
    creator = Creator()
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: service)
    import jarvis.skill_creator_agent as creator_module
    monkeypatch.setattr(
        creator_module, "build_skill_creator_agent",
        lambda *_args, **_kwargs: (creator, "c" * 64),
    )

    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])

    saved = get("larry", payload["request_id"])
    assert saved["state"] == "cancel_requested"
    assert saved["result_code"] == "cancellation_needs_reconciliation"
    assert saved.get("candidate_digest") is None


def test_draft_worker_does_not_attach_replacement_run_receipt(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    _mock_developer_creator(monkeypatch, payload)

    class Service:
        def start_session(self, *_args, **_kwargs):
            return {"ok": True, "session_id": "old-session"}

        def status(self):
            return {
                "run_id": "replacement-run", "phase": "validated",
                "validated_ok": True, "candidate": "b" * 64,
                "package_revision": "a" * 64,
            }

    class Creator:
        cancel_requested = False

        def run(self, _brief):
            return {"ok": True}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    import jarvis.skill_creator_agent as creator_module
    monkeypatch.setattr(
        creator_module, "build_skill_creator_agent",
        lambda *_args, **_kwargs: (Creator(), "c" * 64),
    )

    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])

    saved = get("larry", payload["request_id"])
    assert saved["state"] == "draft_needs_attention"
    assert saved["result_code"] == "sandbox_run_mismatch"
    assert saved.get("candidate_digest") is None
    assert saved.get("candidate_revision") is None


def test_late_validation_receipt_cannot_resurrect_cancelled_draft(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    def cancel_draft():
        cancelled, created = skill_requests.cancel_job("larry", cancel_request)
        assert created is True
        assert cancelled["state"] == "cancelled"
    _mock_developer_creator(monkeypatch, payload, before=cancel_draft)
    cancel_request = {
        "schema_version": 1, "operation": "cancel", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": payload["expected_catalog_revision"],
        "skill_id": payload["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": payload["request_id"],
    }

    class Service:
        cancelled = False

        def start_session(self, *_args, **_kwargs):
            return {"ok": True, "session_id": "session-1"}

        def status(self):
            return {
                "run_id": _sandbox_job(payload),
                "phase": "cancelled" if self.cancelled else "validated",
                "validated_ok": True, "candidate": "b" * 64,
                "package_revision": "a" * 64, "active": not self.cancelled,
            }

        def cancel(self):
            self.cancelled = True
            return {"ok": True}

    service = Service()
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: service)

    skill_requests._run_draft("larry", payload["request_id"], payload["task_brief"])

    saved = get("larry", payload["request_id"])
    assert saved["state"] == "cancelled"
    assert saved["result_code"] == "creator_cancelled"
    assert saved.get("candidate_digest") is None


def test_late_offline_validation_result_cannot_complete_unconfirmed_cancel(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    skill_requests.update("larry", parent["request_id"], state="drafting", sandbox_session_id="session-1")
    test_request = {
        "schema_version": 1, "operation": "test", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": parent["expected_catalog_revision"],
        "skill_id": parent["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": parent["request_id"],
        "example_ids": ["safe-case"], "scope": "offline",
    }
    reserved, created = reserve("larry", test_request)
    assert created is True
    assert reserved["parent_job_id"] == _sandbox_job(parent)
    cancel_request = {
        "schema_version": 1, "operation": "cancel", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": parent["expected_catalog_revision"],
        "skill_id": parent["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": test_request["request_id"],
    }

    class Service:
        def status(self):
            return {"run_id": _sandbox_job(parent), "phase": "drafting", "active": True}

        def cancel(self):
            return {"ok": False, "error": "stop not confirmed"}

        def validate(self, **bindings):
            self.bindings = bindings
            result, created = skill_requests.cancel_job("larry", cancel_request)
            assert created is True
            assert result["state"] == "cancel_requested"
            return {"ok": True, "skill_validation": {"package_revision": "a" * 64}}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug, **_kwargs: Service())
    skill_requests._run_offline_validation("larry", test_request["request_id"], parent["skill_id"])

    saved = get("larry", test_request["request_id"])
    assert saved["state"] == "cancel_requested"
    assert saved["result_code"] == "cancellation_needs_reconciliation"
    assert saved.get("candidate_revision") is None


def test_offline_validation_does_not_attach_replacement_run_receipt(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    reserve("larry", payload)
    skill_requests.update(
        "larry", payload["request_id"], state="testing",
    )

    class Service:
        status_calls = 0

        def status(self):
            self.status_calls += 1
            if self.status_calls == 1:
                return {"run_id": _sandbox_job(parent), "phase": "drafting"}
            return {
                "run_id": "replacement-run", "phase": "validated",
                "validated_ok": True, "candidate": "b" * 64,
                "package_revision": "a" * 64,
            }

        def validate(self, **bindings):
            self.bindings = bindings
            return {"ok": True, "skill_validation": {
                "candidate_digest": "b" * 64, "package_revision": "a" * 64,
            }}

    service = Service()
    monkeypatch.setattr(skill_requests, "_service", lambda _slug, **_kwargs: service)
    skill_requests._run_offline_validation(
        "larry", payload["request_id"], parent["skill_id"],
    )

    saved = get("larry", payload["request_id"])
    assert saved["state"] == "needs_reconciliation"
    assert saved["result_code"] == "offline_validation_run_mismatch"
    assert saved.get("candidate_digest") is None
    assert saved.get("candidate_revision") is None


@pytest.mark.parametrize("bad_status", [
    {"validated_ok": False},
    {"candidate": "c" * 64},
    {"package_revision": "c" * 64},
    {"package_revision": None},
])
def test_validation_result_requires_matching_durable_evidence(tmp_path, monkeypatch, bad_status):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    reserve("larry", payload)

    class Service:
        validated = False

        def status(self):
            if not self.validated:
                return {"run_id": _sandbox_job(parent), "phase": "drafting"}
            return {"run_id": _sandbox_job(parent), "phase": "validated",
                    "validated_ok": True, "candidate": "b" * 64,
                    "package_revision": "a" * 64, **bad_status}

        def validate(self, **bindings):
            self.bindings = bindings
            self.validated = True
            return {"ok": True, "skill_validation": {
                "candidate_digest": "b" * 64, "package_revision": "a" * 64,
            }}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug, **_kwargs: Service())
    skill_requests._run_offline_validation("larry", payload["request_id"], parent["skill_id"])
    state = get("larry", payload["request_id"])
    assert state["state"] == "failed"
    assert state["result_code"] == "offline_validation_failed"
    assert state["candidate_digest"] is None
    assert state["candidate_revision"] is None


def test_offline_validation_cancel_reconcile_requires_matching_terminal_run(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = {
        "schema_version": 1, "operation": "test", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": parent["expected_catalog_revision"],
        "skill_id": parent["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": parent["request_id"],
        "example_ids": ["safe-case"], "scope": "offline",
    }
    reserve("larry", payload)
    skill_requests.update("larry", payload["request_id"], cancel_requested=True,
                          state="cancel_requested")

    class Service:
        def cancel(self): return {"ok": True}
        def status(self):
            return {"run_id": "a-different-run", "phase": "cancelled", "active": False}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    reconciled = skill_requests.reconcile("larry", payload["request_id"])
    assert reconciled["state"] == "cancel_requested"
    assert reconciled["result_code"] == "cancellation_needs_reconciliation"


def test_draft_reconcile_does_not_overwrite_cancel_arriving_during_status(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("larry", payload)
    skill_requests.update("larry", payload["request_id"], state="drafting")
    status_entered = threading.Event()
    release_status = threading.Event()
    status_calls = 0

    class Service:
        def status(self):
            nonlocal status_calls
            status_calls += 1
            if status_calls == 1:
                status_entered.set()
                assert release_status.wait(timeout=2)
                return {"run_id": _sandbox_job(payload), "phase": "drafting", "active": True}
            return {"run_id": _sandbox_job(payload), "phase": "cancelled", "active": False}

        def cancel(self):
            return {"ok": True}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    reconciler = threading.Thread(
        target=skill_requests.reconcile, args=("larry", payload["request_id"]),
    )
    reconciler.start()
    assert status_entered.wait(timeout=2)
    skill_requests.update(
        "larry", payload["request_id"], state="cancel_requested", cancel_requested=True,
    )
    release_status.set()
    reconciler.join(timeout=2)

    saved = get("larry", payload["request_id"])
    assert not reconciler.is_alive()
    assert saved["state"] == "cancelled"
    assert saved["result_code"] == "creator_cancelled"
    assert saved["cancel_requested"] is True


def _offline_test_payload(parent):
    return {
        "schema_version": 1, "operation": "test", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": parent["expected_catalog_revision"],
        "skill_id": parent["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": parent["request_id"],
        "example_ids": ["safe-case"], "scope": "offline",
    }


def test_validation_keeps_host_owned_origin_across_replay(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    skill_requests.update("larry", parent["request_id"],
                          developer_run_id="actual-developer", creator_revision="a" * 64)
    payload = _offline_test_payload(parent)
    payload["originating_developer_run_id"] = "client-forged"
    payload["originating_creator_revision"] = "b" * 64
    state, created = reserve("larry", payload)
    assert created
    assert state["originating_developer_run_id"] == "actual-developer"
    assert state["originating_creator_revision"] == "a" * 64
    assert "validation_attempt_id" not in state
    skill_requests.update("larry", parent["request_id"],
                          developer_run_id="later-run", creator_revision="c" * 64)
    replay, created = reserve("larry", payload)
    assert not created
    assert replay == state


@pytest.mark.parametrize("invalid_parent", ["missing", "other-owner", "other-skill", "legacy"])
def test_validation_does_not_invent_origin(tmp_path, monkeypatch, invalid_parent):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    owner = "someone-else" if invalid_parent == "other-owner" else "larry"
    if invalid_parent != "missing":
        reserve(owner, parent)
        if invalid_parent != "legacy":
            skill_requests.update(owner, parent["request_id"],
                                  developer_run_id="actual-developer", creator_revision="a" * 64)
    payload = _offline_test_payload(parent)
    if invalid_parent == "other-skill":
        payload["skill_id"] = "different-skill"
    payload["originating_developer_run_id"] = "client-forged"
    state, _ = reserve("larry", payload)
    assert "originating_developer_run_id" not in state
    assert "originating_creator_revision" not in state


def test_validation_worker_cannot_touch_replacement_sandbox(tmp_path, monkeypatch):
    from jarvis import skill_requests
    from jarvis.skill_authoring import SkillAuthoringService
    from tests.sandbox_fakes import FakeRuntime

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "requests"))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    reserve("larry", payload)
    runtime = FakeRuntime(tmp_path)
    kwargs = dict(repository=lambda: "owner/repo", token=lambda: "host-token",
                  base_branch=lambda: "main", runtime_factory=lambda: runtime)
    original = SkillAuthoringService(parent["skill_id"], **kwargs)
    assert original.start_session("Original", run_id=_sandbox_job(parent))["ok"]
    replacement = SkillAuthoringService(parent["skill_id"], **kwargs)

    def factory(slug, *, expected_job_id):
        assert expected_job_id == _sandbox_job(parent)
        service = SkillAuthoringService(slug, expected_job_id=expected_job_id, **kwargs)
        status = service.status
        first = True

        def replace_after_baseline():
            nonlocal first
            result = status()
            if first:
                first = False
                assert original.cancel()["ok"]
                assert replacement.start_session("Replacement", run_id="replacement-job")["ok"]
            return result

        service.status = replace_after_baseline
        return service

    monkeypatch.setattr(skill_requests, "_service", factory)
    skill_requests._run_offline_validation("larry", payload["request_id"], parent["skill_id"])
    saved = get("larry", payload["request_id"])
    assert saved["state"] == "needs_reconciliation"
    assert saved["result_code"] == "offline_validation_run_mismatch"
    assert replacement.status()["phase"] == "editing"
    assert replacement.status()["run_id"] == "replacement-job"


def test_queued_offline_validation_restarts_once_after_process_restart(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    reserve("larry", payload)
    calls = []
    attempts_seen_by_validator = []

    class Service:
        def status(self):
            calls.append("status")
            if len(calls) == 1:
                return {"run_id": _sandbox_job(parent), "phase": "drafting",
                        "candidate": "b" * 64}
            return {"run_id": _sandbox_job(parent), "phase": "validated",
                    "validated_ok": True, "candidate": "b" * 64,
                    "package_revision": "a" * 64, **self.bindings}

        def validate(self, **bindings):
            self.bindings = bindings
            before = get("larry", payload["request_id"])
            attempts_seen_by_validator.append(before["validation_attempt_id"])
            assert str(uuid.UUID(before["validation_attempt_id"])) == before["validation_attempt_id"]
            assert before["validation_started_at"]
            assert before["state"] == "testing"
            calls.append("validate")
            return {"ok": True, "skill_validation": {
                "candidate_digest": "b" * 64, "package_revision": "a" * 64,
            }}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug, **_kwargs: Service())
    resumed = skill_requests.reconcile("larry", payload["request_id"])
    thread = skill_requests._jobs[skill_requests._key("larry", payload["request_id"])]
    thread.join(timeout=2)

    saved = get("larry", payload["request_id"])
    assert resumed["state"] == "testing"
    assert saved["state"] == "completed"
    assert saved["candidate_digest"] == "b" * 64
    assert saved["candidate_revision"] == "a" * 64
    assert calls.count("validate") == 1
    assert attempts_seen_by_validator == [saved["validation_attempt_id"]]
    assert skill_requests.reconcile("larry", payload["request_id"])["validation_attempt_id"] == saved["validation_attempt_id"]
    assert calls.count("validate") == 1


def test_offline_validation_duplicate_uuid_starts_at_most_one_worker(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    threads = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            threads.append((target, args, daemon))

        def start(self):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(skill_requests.threading, "Thread", FakeThread)
    first, first_created = skill_requests.start_offline_validation("larry", payload)
    replay, replay_created = skill_requests.start_offline_validation("larry", payload)

    assert first_created is True
    assert replay_created is False
    assert first["request_id"] == replay["request_id"] == payload["request_id"]
    assert first["state"] == replay["state"] == "testing"
    assert len(threads) == 1

    changed = {**payload, "example_ids": ["different-case"]}
    with pytest.raises(SkillRequestError) as exc:
        skill_requests.start_offline_validation("larry", changed)
    assert exc.value.status_code == 409
    assert len(threads) == 1


def test_cancel_duplicate_uuid_does_not_repeat_cancel_side_effect(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    skill_requests.update("larry", parent["request_id"], state="drafting",
                          sandbox_session_id="session-1")
    payload = {
        "schema_version": 1, "operation": "cancel", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": parent["expected_catalog_revision"],
        "skill_id": parent["skill_id"], "skill_revision": None,
        "privacy_context": "standard", "job_id": parent["request_id"],
    }
    states = [
        {"run_id": _sandbox_job(parent), "phase": "editing", "active": True},
        {"run_id": _sandbox_job(parent), "phase": "editing", "active": True},
        {"run_id": _sandbox_job(parent), "phase": "cancelled", "active": False},
    ]

    class Service:
        def status(self):
            return states.pop(0)

        def cancel(self):
            return {"ok": True}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    first, created = skill_requests.cancel_job("larry", payload)
    replay, replay_created = skill_requests.cancel_job("larry", payload)

    assert created is True and replay_created is False
    assert first["state"] == replay["state"] == "cancelled"
    assert states == []

    changed = {**payload, "job_id": str(uuid.uuid4())}
    with pytest.raises(SkillRequestError) as exc:
        skill_requests.cancel_job("larry", changed)
    assert exc.value.status_code == 409


def test_testing_offline_validation_recovers_only_matching_new_receipt(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    reserve("larry", payload)
    skill_requests.update(
        "larry", payload["request_id"], state="testing",
        validation_baseline_phase="drafting",
        validation_baseline_candidate="b" * 64,
    )

    class Service:
        def status(self):
            return {"run_id": _sandbox_job(parent), "phase": "validated",
                    "validated_ok": True, "candidate": "b" * 64,
                    "package_revision": "a" * 64}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    recovered = skill_requests.reconcile("larry", payload["request_id"])

    assert recovered["state"] == "completed"
    assert recovered["candidate_digest"] == "b" * 64
    assert recovered["candidate_revision"] == "a" * 64
    assert recovered["result_code"] == "offline_validation_passed"


def test_testing_offline_validation_mismatch_or_old_receipt_stays_uncertain(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent = _draft_payload()
    reserve("larry", parent)
    payload = _offline_test_payload(parent)
    reserve("larry", payload)
    skill_requests.update(
        "larry", payload["request_id"], state="testing",
        validation_baseline_phase="validated",
        validation_baseline_candidate="b" * 64,
    )

    class Service:
        def status(self):
            return {"run_id": _sandbox_job(parent), "phase": "validated",
                    "validated_ok": True, "candidate": "b" * 64,
                    "package_revision": "a" * 64}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    recovered = skill_requests.reconcile("larry", payload["request_id"])
    assert recovered["state"] == "needs_reconciliation"
    assert recovered["result_code"] == "offline_validation_result_uncertain"
    assert recovered.get("candidate_revision") is None

    # A terminal receipt from another sandbox run cannot satisfy this request.
    skill_requests.update("larry", payload["request_id"], state="testing",
                          validation_baseline_phase="drafting")
    class OtherRunService:
        def status(self):
            return {"run_id": str(uuid.uuid4()), "phase": "validated",
                    "validated_ok": True, "candidate": "b" * 64,
                    "package_revision": "a" * 64}
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: OtherRunService())
    mismatched = skill_requests.reconcile("larry", payload["request_id"])
    assert mismatched["state"] == "needs_reconciliation"
    assert mismatched["result_code"] == "offline_validation_run_mismatch"
    assert mismatched.get("candidate_revision") is None

    # Records created by the older worker have no pre-validation snapshot;
    # a matching but possibly stale service receipt is not enough to succeed.
    skill_requests.update("larry", payload["request_id"], state="testing",
                          validation_baseline_phase=None,
                          validation_baseline_candidate=None)
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    legacy = skill_requests.reconcile("larry", payload["request_id"])
    assert legacy["state"] == "needs_reconciliation"
    assert legacy["result_code"] == "offline_validation_result_uncertain"


def test_draft_api_returns_stable_receipt_and_replays_same_request(tmp_path, monkeypatch):
    from jarvis import skill_requests
    from jarvis.skill_runtime import update_runtime_inventory
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    payload = _draft_payload()
    update_runtime_inventory(
        payload["bot_session_id"], [], True, active=True, owner_id="larry",
    )
    def finish(owner, request_id, _brief):
        skill_requests.update(owner, request_id, state="drafting")
        with skill_requests._jobs_lock:
            skill_requests._jobs.pop(skill_requests._key(owner, request_id), None)
    monkeypatch.setattr(skill_requests, "_run_draft", finish)
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    client = TestClient(server.app)
    first = client.post("/api/skills/requests", json=payload)
    assert first.status_code == 202
    assert first.json()["job_id"] == payload["request_id"]
    changed = {**payload, "task_brief": "different"}
    assert client.post("/api/skills/requests", json=changed).status_code == 409
    replay = client.post("/api/skills/requests", json=payload)
    assert replay.status_code == 202
    assert replay.json()["replayed"] is True


def test_draft_api_refuses_stale_or_cross_owner_bot_session(tmp_path, monkeypatch):
    from jarvis import skill_requests
    from jarvis.skill_runtime import clear_runtime_inventories, update_runtime_inventory

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    clear_runtime_inventories()
    monkeypatch.setattr(
        skill_requests, "start_draft",
        lambda *_args, **_kwargs: pytest.fail("must not enqueue unowned session request"),
    )
    client = TestClient(server.app)
    cross_owner = _draft_payload()
    update_runtime_inventory(
        cross_owner["bot_session_id"], [], True, active=True, owner_id="another-user",
    )
    assert client.post("/api/skills/requests", json=cross_owner).status_code == 409

    clear_runtime_inventories()
    stale_session = _draft_payload()
    assert client.post("/api/skills/requests", json=stale_session).status_code == 409
    assert not list((tmp_path / "sandbox").glob("skill-requests/*.json"))
    clear_runtime_inventories()


def test_request_api_rejects_unknown_fields_stale_catalog_and_protected_content(
    tmp_path, monkeypatch,
):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")

    # This is the first worker boundary. If a protected request ever reaches
    # it, the private task brief could flow into the creator/model process.
    # Fail loudly rather than relying only on the durable-state assertion below.
    worker_starts = []
    def forbidden_worker_start(*_args, **_kwargs):
        worker_starts.append(True)
        raise AssertionError("protected skill request must not start a worker")
    monkeypatch.setattr(skill_requests, "start_draft", forbidden_worker_start)

    client = TestClient(server.app)
    payload = _draft_payload(extra_instruction="must not be accepted")
    assert client.post("/api/skills/requests", json=payload).status_code == 422
    payload = _draft_payload(expected_catalog_revision="0" * 64)
    assert client.post("/api/skills/requests", json=payload).status_code == 409
    canary = "PROTECTED_SKILL_BRIEF_CANARY"
    payload = _draft_payload(privacy_context="protected", task_brief=canary)
    response = client.post("/api/skills/requests", json=payload)
    assert response.status_code == 409
    assert "protected" in response.json()["detail"]
    assert canary not in response.text
    assert worker_starts == []
    assert not list(tmp_path.rglob("*.json")), "protected requests must not reserve durable state"


def test_request_api_rejects_invalid_operation_fields_and_live_testing(monkeypatch):
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    client = TestClient(server.app)
    payload = _draft_payload(job_id=str(uuid.uuid4()))
    assert client.post("/api/skills/requests", json=payload).status_code == 400
    payload = {
        "schema_version": 1, "operation": "test", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": _catalog_revision(), "skill_id": "skill-creator",
        "skill_revision": None, "privacy_context": "standard", "job_id": str(uuid.uuid4()),
        "example_ids": ["safe-case"], "scope": "live",
    }
    response = client.post("/api/skills/requests", json=payload)
    assert response.status_code == 409
    assert "disabled" in response.json()["detail"]


def test_activation_and_rollback_requests_fail_closed_without_required_evidence(
    tmp_path, monkeypatch,
):
    from jarvis.skill_requests import list_for_skill

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    skill = next(item for item in list_catalog() if item.skill_id == "technical-plan-document")
    assert skill.revision

    # A passing offline package validation is deliberately not the live paired
    # evaluation plus blinded human review required before activation review.
    evidence_id = str(uuid.uuid4())
    reserve("larry", {
        "schema_version": 1, "operation": "test", "request_id": evidence_id,
        "expected_catalog_revision": _catalog_revision(), "skill_id": skill.skill_id,
        "skill_revision": None, "privacy_context": "standard", "scope": "offline",
        "example_ids": ["safe-case"], "job_id": str(uuid.uuid4()),
    })
    from jarvis.skill_requests import update
    update("larry", evidence_id, state="completed", candidate_revision=skill.revision)

    client = TestClient(server.app)
    expected = {
        "request_activation": "accepted live evaluation and blinded human review evidence is required",
        "request_rollback": "no previously accepted package and registry revision is recorded",
    }
    request_ids = []
    for operation, detail in expected.items():
        request_id = str(uuid.uuid4())
        request_ids.append(request_id)
        response = client.post("/api/skills/requests", json={
            "schema_version": 1, "operation": operation, "request_id": request_id,
            "expected_catalog_revision": _catalog_revision(),
            "skill_id": skill.skill_id, "skill_revision": skill.revision,
            "privacy_context": "standard", "review_artifact_ref": evidence_id,
        })
        assert response.status_code == 409
        assert response.json()["detail"] == detail
        assert get("larry", request_id) is None

    saved = list_for_skill("larry", skill.skill_id)
    assert [item["request_id"] for item in saved] == [evidence_id]
    assert all(request_id not in {item["request_id"] for item in saved}
               for request_id in request_ids)


def test_publish_request_is_explicit_and_binds_reviewed_candidate(monkeypatch):
    from jarvis import skill_requests
    captured = {}

    def start(owner, payload):
        captured.update(owner=owner, payload=payload)
        return ({"request_id": payload["request_id"], "state": "publishing"}, True)

    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    monkeypatch.setattr(skill_requests, "start_publish", start)
    payload = {
        "schema_version": 1, "operation": "request_publish", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": _catalog_revision(), "skill_id": "new-skill",
        "skill_revision": "a" * 64, "candidate_digest": "b" * 64,
        "privacy_context": "standard", "review_artifact_ref": str(uuid.uuid4()),
    }
    response = TestClient(server.app).post("/api/skills/requests", json=payload)
    assert response.status_code == 202
    assert response.json()["state"] == "publishing"
    assert captured["owner"] == "larry"
    assert captured["payload"]["candidate_digest"] == "b" * 64


def test_request_publish_rejects_missing_or_malformed_candidate_binding(monkeypatch):
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    client = TestClient(server.app)
    payload = {
        "schema_version": 1, "operation": "request_publish", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": _catalog_revision(), "skill_id": "new-skill",
        "skill_revision": "a" * 64, "candidate_digest": "not-a-digest",
        "privacy_context": "standard", "review_artifact_ref": str(uuid.uuid4()),
    }
    assert client.post("/api/skills/requests", json=payload).status_code == 400


def test_publish_is_owner_bound_digest_bound_and_idempotent(tmp_path, monkeypatch):
    from jarvis import skill_requests
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    draft_id = str(uuid.uuid4())
    draft_payload = _draft_payload(request_id=draft_id, skill_id="new-skill")
    reserve("owner", draft_payload)
    skill_requests.update(
        "owner", draft_id, state="review_ready",
        candidate_digest="b" * 64, candidate_revision="a" * 64,
    )
    publish_payload = {
        "schema_version": 1, "operation": "request_publish", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": _catalog_revision(), "skill_id": "new-skill",
        "skill_revision": "a" * 64, "candidate_digest": "b" * 64,
        "privacy_context": "standard", "review_artifact_ref": draft_id,
    }
    calls = []
    parent_state = {"state": "review_ready"}
    monkeypatch.setattr(skill_requests, "reconcile", lambda owner, request_id: {
        "request_id": request_id, "operation": "draft", "state": parent_state["state"],
        "skill_id": "new-skill", "candidate_digest": "b" * 64,
        "candidate_revision": "a" * 64,
    })

    class FakeThread:
        def __init__(self, *, target, args, daemon): calls.append((target, args, daemon))
        def start(self): pass
        def is_alive(self): return True

    monkeypatch.setattr(skill_requests.threading, "Thread", FakeThread)
    first, created = skill_requests.start_publish("owner", publish_payload)
    parent_state["state"] = "pr_open"
    replay, created_again = skill_requests.start_publish("owner", publish_payload)
    assert created is True and created_again is False
    assert first["state"] == replay["state"] == "publishing"
    assert len(calls) == 1

    mismatch = {**publish_payload, "request_id": str(uuid.uuid4()), "candidate_digest": "c" * 64}
    with pytest.raises(SkillRequestError) as exc:
        skill_requests.start_publish("owner", mismatch)
    assert exc.value.status_code == 409
    assert get("owner", mismatch["request_id"]) is None


def test_distinct_publish_request_ids_for_one_candidate_claim_only_one_worker(
        tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    draft_id = str(uuid.uuid4())
    draft_payload = _draft_payload(request_id=draft_id, skill_id="new-skill")
    reserve("owner", draft_payload)
    skill_requests.update(
        "owner", draft_id, state="review_ready",
        candidate_digest="b" * 64, candidate_revision="a" * 64,
    )
    payloads = [{
        "schema_version": 1, "operation": "request_publish",
        "request_id": str(uuid.uuid4()), "expected_catalog_revision": _catalog_revision(),
        "skill_id": "new-skill", "skill_revision": "a" * 64,
        "candidate_digest": "b" * 64, "privacy_context": "standard",
        "review_artifact_ref": draft_id,
    } for _ in range(2)]
    both_reconciled = threading.Barrier(2)

    def reconcile(_owner, request_id):
        assert request_id == draft_id
        both_reconciled.wait(timeout=2)
        return {
            "request_id": draft_id, "operation": "draft", "state": "review_ready",
            "skill_id": "new-skill", "candidate_digest": "b" * 64,
            "candidate_revision": "a" * 64,
        }

    calls = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            calls.append((target, args, daemon))
        def start(self):
            pass
        def is_alive(self):
            return True

    monkeypatch.setattr(skill_requests, "reconcile", reconcile)
    real_thread = threading.Thread
    monkeypatch.setattr(skill_requests.threading, "Thread", FakeThread)

    def submit(payload):
        try:
            return skill_requests.start_publish("owner", payload)
        except SkillRequestError as exc:
            return exc

    results = [None, None]
    workers = [
        real_thread(target=lambda index=index: results.__setitem__(index, submit(payloads[index])))
        for index in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)
    assert all(not worker.is_alive() for worker in workers)

    assert sum(isinstance(result, tuple) and result[1] for result in results) == 1
    refusals = [result for result in results if isinstance(result, SkillRequestError)]
    assert len(refusals) == 1 and refusals[0].status_code == 409
    assert len(calls) == 1
    request_records = [
        json.loads(path.read_text())
        for path in (tmp_path / "skill-requests").glob("*.json")
    ]
    publish_records = [record for record in request_records
                       if record.get("operation") == "request_publish"]
    assert len(publish_records) == 1


def _reviewed_publish_setup(tmp_path, skill_requests):
    parent_id = str(uuid.uuid4())
    parent_payload = _draft_payload(request_id=parent_id, skill_id="new-skill")
    reserve("owner", parent_payload)
    skill_requests.update(
        "owner", parent_id, state="review_ready",
        candidate_digest="b" * 64, candidate_revision="a" * 64,
    )
    publish_payload = {
        "schema_version": 1, "operation": "request_publish",
        "request_id": str(uuid.uuid4()), "expected_catalog_revision": _catalog_revision(),
        "skill_id": "new-skill", "skill_revision": "a" * 64,
        "candidate_digest": "b" * 64, "privacy_context": "standard",
        "review_artifact_ref": parent_id,
    }
    monkeypatch_reconcile = lambda _owner, _request_id: get("owner", parent_id)
    return parent_id, publish_payload, monkeypatch_reconcile


def _cancel_publish_payload(publish_payload):
    return {
        "schema_version": 1, "operation": "cancel", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": publish_payload["expected_catalog_revision"],
        "skill_id": publish_payload["skill_id"],
        "skill_revision": publish_payload["skill_revision"],
        "privacy_context": "standard", "job_id": publish_payload["request_id"],
    }


def test_cancel_publish_while_status_is_pending_prevents_late_submit(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id, payload, parent_reconcile = _reviewed_publish_setup(tmp_path, skill_requests)
    monkeypatch.setattr(skill_requests, "reconcile", parent_reconcile)
    status_entered = threading.Event()
    allow_status_return = threading.Event()
    finished = threading.Event()
    submits = []

    class Service:
        def status(self):
            status_entered.set()
            assert allow_status_return.wait(timeout=3)
            return {
                "run_id": get("owner", parent_id)["sandbox_job_id"], "phase": "validated", "validated_ok": True,
                "candidate": "b" * 64, "package_revision": "a" * 64,
            }

        def submit(self):
            submits.append("submit")
            return {"ok": True, "pr_url": "https://github.com/example/repo/pull/42"}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    original_run = skill_requests._run_publish

    def tracked_run(*args):
        try:
            original_run(*args)
        finally:
            finished.set()

    monkeypatch.setattr(skill_requests, "_run_publish", tracked_run)
    job, started = skill_requests.start_publish("owner", payload)
    assert started and job["state"] == "publishing"
    assert status_entered.wait(timeout=3)

    cancel_record, _created = skill_requests.cancel_job(
        "owner", _cancel_publish_payload(payload),
    )
    assert cancel_record["state"] == "cancelled"
    allow_status_return.set()
    assert finished.wait(timeout=3)

    saved = get("owner", payload["request_id"])
    assert saved["state"] == "cancelled"
    assert saved["result_code"] == "publication_cancelled_before_submit"
    assert submits == []


def test_cancel_publish_after_submit_barrier_fails_closed_and_keeps_uncertain_result(
        tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id, payload, parent_reconcile = _reviewed_publish_setup(tmp_path, skill_requests)
    monkeypatch.setattr(skill_requests, "reconcile", parent_reconcile)
    submit_entered = threading.Event()
    allow_submit_return = threading.Event()
    finished = threading.Event()

    class Service:
        def status(self):
            return {
                "run_id": get("owner", parent_id)["sandbox_job_id"], "phase": "validated", "validated_ok": True,
                "candidate": "b" * 64, "package_revision": "a" * 64,
            }

        def submit(self):
            submit_entered.set()
            assert allow_submit_return.wait(timeout=3)
            return {"ok": False, "error": "response lost after provider accepted request"}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    original_run = skill_requests._run_publish

    def tracked_run(*args):
        try:
            original_run(*args)
        finally:
            finished.set()

    monkeypatch.setattr(skill_requests, "_run_publish", tracked_run)
    job, started = skill_requests.start_publish("owner", payload)
    assert started and job["state"] == "publishing"
    assert submit_entered.wait(timeout=3)
    assert get("owner", payload["request_id"])["state"] == "publication_submitting"

    cancel_payload = _cancel_publish_payload(payload)
    with pytest.raises(SkillRequestError, match="publication may have started") as exc:
        skill_requests.cancel_job("owner", cancel_payload)
    assert exc.value.status_code == 409
    allow_submit_return.set()
    assert finished.wait(timeout=3)

    saved = get("owner", payload["request_id"])
    cancel_record = get("owner", cancel_payload["request_id"])
    assert saved["state"] == "publication_needs_reconciliation"
    assert saved["result_code"] == "publication_result_uncertain"
    assert saved.get("cancel_requested") is None
    assert cancel_record["state"] == "failed"


@pytest.mark.parametrize("recovery_entry", ["reconcile", "start_publish"])
def test_queued_publish_reserved_before_worker_claim_recovers_once(
        tmp_path, monkeypatch, recovery_entry):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id, payload, _parent_reconcile = _reviewed_publish_setup(tmp_path, skill_requests)
    payload_digest = skill_requests._canonical_digest(payload)
    assert skill_requests._claim_parent_publication(
        "owner", parent_id, payload["request_id"], payload_digest,
        payload["candidate_digest"], payload["skill_revision"],
    )
    reserved, created = reserve("owner", payload)
    assert created is True and reserved["state"] == "queued"
    assert reserved["parent_job_id"] == get("owner", parent_id)["sandbox_job_id"]
    assert reserved["candidate_digest"] == payload["candidate_digest"]
    assert reserved["candidate_revision"] == payload["skill_revision"]

    launches = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            launches.append((target, args, daemon))

        def start(self):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(skill_requests.threading, "Thread", FakeThread)
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: type("Service", (), {
        "status": lambda self: {
            "run_id": get("owner", parent_id)["sandbox_job_id"], "phase": "validated", "validated_ok": True,
            "candidate": "b" * 64, "package_revision": "a" * 64,
        },
    })())

    if recovery_entry == "reconcile":
        recovered = skill_requests.reconcile("owner", payload["request_id"])
    else:
        recovered, started = skill_requests.start_publish("owner", payload)
        assert started is True
    assert recovered["state"] == "publishing"
    assert len(launches) == 1
    assert launches[0][1] == ("owner", payload["request_id"], get("owner", parent_id)["sandbox_job_id"])

    if recovery_entry == "reconcile":
        replay = skill_requests.reconcile("owner", payload["request_id"])
    else:
        replay, started_again = skill_requests.start_publish("owner", payload)
        assert started_again is False
    assert replay["state"] == "publishing"
    assert len(launches) == 1


def test_ambiguous_publication_is_reconciled_without_repeating_submit(tmp_path, monkeypatch):
    from jarvis import skill_requests
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    draft_id = str(uuid.uuid4())
    draft_payload = _draft_payload(request_id=draft_id, skill_id="new-skill")
    reserve("owner", draft_payload)
    payload = {
        "schema_version": 1, "operation": "request_publish", "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": _catalog_revision(), "skill_id": "new-skill",
        "skill_revision": "a" * 64, "candidate_digest": "b" * 64,
        "privacy_context": "standard", "review_artifact_ref": draft_id,
    }
    reserve("owner", payload)
    skill_requests.update("owner", payload["request_id"], state="publishing",
                          parent_request_id=draft_id, parent_job_id=get("owner", draft_id)["sandbox_job_id"], candidate_digest="b" * 64,
                          candidate_revision="a" * 64)
    calls = []

    class Service:
        def status(self):
            return {"run_id": get("owner", draft_id)["sandbox_job_id"], "phase": "publication_pending", "candidate": "b" * 64,
                    "package_revision": "a" * 64, "validated_ok": True}
        def submit(self): calls.append("submit"); return {"ok": True, "pr_url": "https://github.com/org/repo/pull/1"}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    skill_requests._run_publish("owner", payload["request_id"], get("owner", draft_id)["sandbox_job_id"])
    saved = get("owner", payload["request_id"])
    assert saved["state"] == "publication_needs_reconciliation"
    assert calls == []


def test_publish_worker_recovers_matching_preexisting_published_draft(tmp_path, monkeypatch):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    draft_id = str(uuid.uuid4())
    draft_payload = _draft_payload(request_id=draft_id)
    reserve("owner", draft_payload)
    skill_requests.update(
        "owner", draft_id, state="review_ready",
        candidate_digest="b" * 64, candidate_revision="a" * 64,
    )
    publish_payload = {
        "schema_version": 1, "operation": "request_publish",
        "request_id": str(uuid.uuid4()), "skill_id": "request-test-skill",
    }
    reserve("owner", publish_payload)
    skill_requests.update(
        "owner", publish_payload["request_id"], state="publishing",
        parent_request_id=draft_id, parent_job_id=get("owner", draft_id)["sandbox_job_id"], candidate_digest="b" * 64,
        candidate_revision="a" * 64,
    )
    calls = []

    class Service:
        def status(self):
            return {
                "run_id": get("owner", draft_id)["sandbox_job_id"], "phase": "published",
                "candidate": "b" * 64, "package_revision": "a" * 64,
                "pr_url": "https://github.com/example/repo/pull/42", "pr_number": 42,
            }

        def submit(self):
            calls.append("submit")
            raise AssertionError("published result must be reconciled without resubmitting")

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    skill_requests._run_publish("owner", publish_payload["request_id"], get("owner", draft_id)["sandbox_job_id"])

    publish_state = get("owner", publish_payload["request_id"])
    assert publish_state["state"] == "completed"
    assert publish_state["pr_url"].endswith("/42")
    assert get("owner", draft_id)["state"] == "pr_open"
    assert calls == []


@pytest.mark.parametrize("candidate,revision,expected_state", [
    ("b" * 64, "a" * 64, "pr_open"),
    ("c" * 64, "a" * 64, "publication_needs_reconciliation"),
    ("b" * 64, "d" * 64, "publication_needs_reconciliation"),
])
def test_review_ready_draft_reconciles_only_its_exact_published_candidate(
        tmp_path, monkeypatch, candidate, revision, expected_state):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    payload = _draft_payload()
    reserve("owner", payload)
    skill_requests.update(
        "owner", payload["request_id"], state="review_ready",
        candidate_digest="b" * 64, candidate_revision="a" * 64,
    )

    class Service:
        def status(self):
            return {
                "run_id": _sandbox_job(payload, "owner"), "phase": "published",
                "candidate": candidate, "package_revision": revision,
                "pr_url": "https://github.com/example/repo/pull/42", "pr_number": 42,
            }

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    result = skill_requests.reconcile("owner", payload["request_id"])

    assert result["state"] == expected_state
    if expected_state == "pr_open":
        assert result["pr_url"].endswith("/42")
    else:
        assert "pr_url" not in result


def test_review_ready_status_returns_only_exact_bounded_diff(monkeypatch):
    from jarvis import skill_requests
    request_id = str(uuid.uuid4())
    monkeypatch.setattr(server, "_skill_request_owner", lambda _request: "larry")
    monkeypatch.setattr(skill_requests, "reconcile", lambda _owner, _id: {
        "operation": "draft", "state": "review_ready", "skill_id": "new-skill",
        "candidate_digest": "b" * 64, "candidate_revision": "a" * 64,
        "sandbox_job_id": "sandbox-run",
    })
    monkeypatch.setattr(skill_requests, "_service", lambda _slug: type("Service", (), {
        "status": lambda self: {
            "run_id": "sandbox-run", "candidate": "b" * 64, "package_revision": "a" * 64,
            "goal": "private task brief", "proposals": [{"path": "skills/new-skill/SKILL.md",
                "rationale": "private rationale", "diff": "--- a\n+++ b\n"}],
        },
    })())
    response = TestClient(server.app).get(f"/api/skills/requests/{request_id}")
    assert response.status_code == 200
    assert response.json()["review"]["files"] == [{"path": "skills/new-skill/SKILL.md", "diff": "--- a\n+++ b\n"}]
    assert "private task brief" not in response.text
    assert "private rationale" not in response.text


def test_authenticated_request_status_is_scoped_to_bearer_user(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path / "sandbox"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    tokens = {name: auth.mint_token() for name in ("owner", "other")}
    with get_conn() as conn:
        for name, token in tokens.items():
            conn.execute(
                "INSERT INTO client_tokens (user_id, name, token_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, name, auth.hash_token(token), now_iso()),
            )
        conn.commit()
    payload = _draft_payload()
    reserve("owner", payload)
    client = TestClient(server.app)
    owned = client.get(
        f"/api/skills/requests/{payload['request_id']}",
        headers={"Authorization": f"Bearer {tokens['owner']}"},
    )
    hidden = client.get(
        f"/api/skills/requests/{payload['request_id']}",
        headers={"Authorization": f"Bearer {tokens['other']}"},
    )
    assert owned.status_code == 200
    assert owned.json()["state"] == "queued"
    assert hidden.status_code == 404
