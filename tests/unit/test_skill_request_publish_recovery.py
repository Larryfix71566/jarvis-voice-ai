"""Fake-service recovery tests for digest-bound Skills PR receipts."""
from __future__ import annotations

import uuid

import pytest

from jarvis.skill_requests import get, reconcile, reserve, update


def _publish_request(parent_id: str) -> dict:
    return {
        "schema_version": 1,
        "operation": "request_publish",
        "request_id": str(uuid.uuid4()),
        "expected_catalog_revision": "c" * 64,
        "skill_id": "request-test-skill",
        "skill_revision": "a" * 64,
        "candidate_digest": "b" * 64,
        "privacy_context": "standard",
        "review_artifact_ref": parent_id,
    }


def test_restart_recovery_does_not_accept_published_receipt_for_other_candidate(
    tmp_path, monkeypatch,
):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id = str(uuid.uuid4())
    request = _publish_request(parent_id)
    reserve("larry", request)
    update("larry", request["request_id"], state="publishing",
           parent_job_id=parent_id, candidate_digest="b" * 64,
           candidate_revision="a" * 64)

    class Service:
        def status(self):
            return {
                "run_id": parent_id,
                "phase": "published",
                "candidate": "d" * 64,
                "package_revision": "e" * 64,
                "pr_url": "https://github.com/org/repo/pull/42",
                "pr_number": 42,
            }

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    recovered = reconcile("larry", request["request_id"])

    assert recovered["state"] == "publication_needs_reconciliation"
    assert recovered["result_code"] == "published_candidate_mismatch"
    assert recovered.get("pr_url") is None
    assert get("larry", request["request_id"])["state"] == "publication_needs_reconciliation"


def test_publish_worker_does_not_complete_from_mismatched_published_receipt(
    tmp_path, monkeypatch,
):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id = str(uuid.uuid4())
    request = _publish_request(parent_id)
    reserve("larry", request)
    update("larry", request["request_id"], state="publishing",
           parent_job_id=parent_id, candidate_digest="b" * 64,
           candidate_revision="a" * 64)

    class Service:
        def status(self):
            return {
                "run_id": parent_id,
                "phase": "published",
                "candidate": "b" * 64,
                "package_revision": "z" * 64,
                "pr_url": "https://github.com/org/repo/pull/42",
                "pr_number": 42,
            }

        def submit(self):
            raise AssertionError("an already-published session must not be resubmitted")

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    skill_requests._run_publish("larry", request["request_id"], parent_id)
    saved = get("larry", request["request_id"])

    assert saved["state"] == "publication_needs_reconciliation"
    assert saved["result_code"] == "published_candidate_mismatch"
    assert saved.get("pr_url") is None


def test_restart_recovery_accepts_published_receipt_for_exact_reviewed_candidate(
    tmp_path, monkeypatch,
):
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id = str(uuid.uuid4())
    request = _publish_request(parent_id)
    reserve("larry", request)
    update("larry", request["request_id"], state="publishing",
           parent_job_id=parent_id, candidate_digest="b" * 64,
           candidate_revision="a" * 64)
    reserve("larry", {
        **request,
        "operation": "draft",
        "request_id": parent_id,
        "skill_revision": None,
        "candidate_digest": "b" * 64,
        "review_artifact_ref": None,
    })
    update("larry", parent_id, state="review_ready",
           candidate_digest="b" * 64, candidate_revision="a" * 64)

    class Service:
        def status(self):
            return {
                "run_id": parent_id,
                "phase": "published",
                "candidate": "b" * 64,
                "package_revision": "a" * 64,
                "pr_url": "https://github.com/org/repo/pull/42",
                "pr_number": 42,
            }

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    recovered = reconcile("larry", request["request_id"])

    assert recovered["state"] == "completed"
    assert recovered["result_code"] == "review_pr_open"
    assert recovered["pr_url"] == "https://github.com/org/repo/pull/42"
    assert get("larry", parent_id)["state"] == "pr_open"


def test_restart_after_submit_barrier_never_repeats_submit_for_pre_submit_phase(
    tmp_path, monkeypatch,
):
    """A crash after the barrier is ambiguous even if sandbox still says validated."""
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id = str(uuid.uuid4())
    request = _publish_request(parent_id)
    reserve("larry", request)
    update(
        "larry", request["request_id"], state="publication_submitting",
        parent_job_id=parent_id, candidate_digest="b" * 64,
        candidate_revision="a" * 64, submit_started_at="2026-09-28T00:00:00+00:00",
    )

    class Service:
        def status(self):
            return {
                "run_id": parent_id, "phase": "validated", "validated_ok": True,
                "candidate": "b" * 64, "package_revision": "a" * 64,
            }

        def submit(self):
            raise AssertionError("ambiguous submit must never be repeated during recovery")

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    recovered = reconcile("larry", request["request_id"])

    assert recovered["state"] == "publication_needs_reconciliation"
    assert recovered["result_code"] == "publication_result_uncertain"
    assert recovered.get("pr_url") is None


@pytest.mark.parametrize("worker_running", [False, True])
def test_publication_status_outage_does_not_leave_dead_worker_looking_active(
    tmp_path, monkeypatch, worker_running,
):
    """A restart plus status outage is uncertain, while a live worker may retry."""
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id = str(uuid.uuid4())
    request = _publish_request(parent_id)
    reserve("larry", request)
    update("larry", request["request_id"], state="publishing",
           parent_job_id=parent_id, candidate_digest="b" * 64,
           candidate_revision="a" * 64)

    class UnavailableService:
        def status(self):
            raise OSError("sandbox status temporarily unavailable")

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: UnavailableService())
    monkeypatch.setattr(skill_requests, "_job_running", lambda _owner, _id: worker_running)

    recovered = reconcile("larry", request["request_id"])

    if worker_running:
        assert recovered["state"] == "publishing"
    else:
        assert recovered["state"] == "publication_needs_reconciliation"
        assert recovered["result_code"] == "publication_status_unavailable"
    assert get("larry", request["request_id"])["state"] == recovered["state"]


def test_publish_worker_treats_success_without_pr_url_as_uncertain(
    tmp_path, monkeypatch,
):
    """A positive publisher flag without its durable PR locator is not completion."""
    from jarvis import skill_requests

    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(tmp_path))
    parent_id = str(uuid.uuid4())
    draft = {
        "schema_version": 1, "operation": "draft", "request_id": parent_id,
        "expected_catalog_revision": "c" * 64, "skill_id": "request-test-skill",
        "privacy_context": "standard",
    }
    reserve("larry", draft)
    update(
        "larry", parent_id, state="review_ready",
        candidate_digest="b" * 64, candidate_revision="a" * 64,
    )
    request = _publish_request(parent_id)
    reserve("larry", request)
    update(
        "larry", request["request_id"], state="publishing",
        parent_job_id=parent_id, candidate_digest="b" * 64,
        candidate_revision="a" * 64,
    )
    submits = []

    class Service:
        def status(self):
            return {
                "run_id": parent_id, "phase": "validated", "validated_ok": True,
                "candidate": "b" * 64, "package_revision": "a" * 64,
            }

        def submit(self):
            submits.append(True)
            return {"ok": True, "pr_url": ""}

    monkeypatch.setattr(skill_requests, "_service", lambda _slug: Service())
    skill_requests._run_publish("larry", request["request_id"], parent_id)

    recovered = get("larry", request["request_id"])
    assert submits == [True]
    assert recovered["state"] == "publication_needs_reconciliation"
    assert recovered["result_code"] == "publication_result_uncertain"
    assert recovered.get("pr_url") is None
    assert get("larry", parent_id)["state"] == "review_ready"
