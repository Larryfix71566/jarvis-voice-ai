"""Crash-safe queue primitives for staged automatic-memory admission."""
import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.memory import delete_fact
from jarvis.memory_admission import (
    AdmissionJobError,
    cancel_jobs_for_key,
    cancel_jobs_for_turn,
    cancel_user_jobs,
    claim_due_jobs,
    complete_job,
    enqueue_exchange,
    enqueue_finished_session_exchanges,
    fail_or_retry_job,
    reclaim_abandoned_jobs,
    save_classification,
    save_extracted_candidates,
)

NOW = "2026-09-25T12:00:00+00:00"


def _claim_from_process(db_path, start, ready, results):
    """Claim one admission job in an independent spawned worker process."""
    conn = None
    try:
        conn = get_conn(db_path)
        ready.set()
        if not start.wait(timeout=15):
            raise TimeoutError("multi-process claim race was not released")
        rows = claim_due_jobs(conn, now_iso=NOW)
        results.put([int(row["id"]) for row in rows])
    except BaseException as exc:  # deliver child failures to the parent test
        results.put({"error": type(exc).__name__})
        raise
    finally:
        if conn is not None:
            conn.close()


def _forget_or_reclaim_from_process(db_path, start, ready, results, *, forget):
    """Race lease recovery against user forget using separate processes."""
    conn = None
    try:
        conn = get_conn(db_path)
        ready.set()
        if not start.wait(timeout=15):
            raise TimeoutError("forget/reclaim race was not released")
        if forget:
            from jarvis.memory import delete_fact

            result = delete_fact(conn, "user.style.concise")
            conn.commit()
            results.put({"forgot": result})
        else:
            result = reclaim_abandoned_jobs(
                conn, now_iso="2026-09-25T12:10:00+00:00", lease_timeout_s=180,
            )
            results.put({"reclaimed": result})
    except BaseException as exc:  # deliver child failures to the parent test
        results.put({"error": type(exc).__name__})
        raise
    finally:
        if conn is not None:
            conn.close()


def _classification(key):
    return {
        "key": key, "scope": "global", "memory_type": "fact",
        "provenance": "user", "evidence_status": "tentative",
        "confidence": 0.5, "evidence": [],
        "reason_code": "insufficient_evidence",
    }


def _exchange(conn, *, session="s1", user_id="local"):
    user_id_turn = conn.execute(
        "INSERT INTO conversations(session_id,role,content,created_at,user_id) "
        "VALUES (?,?,?,?,?)", (session, "user", "I prefer concise answers", NOW, user_id),
    ).lastrowid
    assistant_id_turn = conn.execute(
        "INSERT INTO conversations(session_id,role,content,created_at,user_id) "
        "VALUES (?,?,?,?,?)", (session, "assistant", "Understood", NOW, user_id),
    ).lastrowid
    return user_id_turn, assistant_id_turn


def _db(tmp_path):
    conn = get_conn(tmp_path / "admission.db")
    run_migrations(conn)
    return conn


def _enqueue(conn, *, now=NOW, user="local", session="s1"):
    user_turn_id, assistant_turn_id = _exchange(conn, session=session, user_id=user)
    job_id, created = enqueue_exchange(
        conn, user_id=user, session_id=session, user_turn_id=user_turn_id,
        assistant_turn_id=assistant_turn_id, policy_version="b1", now_iso=now,
    )
    conn.commit()
    return job_id, created, user_turn_id, assistant_turn_id


def test_migration_adds_staging_only_admission_queue(tmp_path):
    conn = _db(tmp_path)
    columns = {row["name"] for row in conn.execute(
        "PRAGMA table_info(memory_admission_jobs)"
    )}
    assert {
        "idempotency_key", "user_id", "session_id", "user_turn_id",
        "assistant_turn_id", "policy_version", "stage", "status",
        "candidate_json", "classification_json", "attempts",
        "next_attempt_at", "claimed_at", "last_error_code",
    } <= columns
    assert conn.execute("SELECT count(*) FROM memory_admission_jobs").fetchone()[0] == 0


def test_enqueue_is_idempotent_and_verifies_source_identity(tmp_path):
    conn = _db(tmp_path)
    job_id, created, user_turn, assistant_turn = _enqueue(conn)
    same_id, duplicate_created = enqueue_exchange(
        conn, user_id="local", session_id="s1", user_turn_id=user_turn,
        assistant_turn_id=assistant_turn, policy_version="b1", now_iso=NOW,
    )
    assert (job_id, created, same_id, duplicate_created) == (job_id, True, job_id, False)
    with pytest.raises(AdmissionJobError, match="source identity"):
        enqueue_exchange(
            conn, user_id="local", session_id="wrong", user_turn_id=user_turn,
            assistant_turn_id=assistant_turn, policy_version="b1", now_iso=NOW,
        )
    assert conn.execute("SELECT count(*) FROM memory_admission_jobs").fetchone()[0] == 1


def test_teardown_stages_finished_pairs_idempotently_without_cursor_changes(tmp_path):
    conn = _db(tmp_path)
    _exchange(conn, session="teardown")
    _exchange(conn, session="other")
    conn.execute(
        "INSERT INTO conversations(session_id,role,content,created_at,user_id) "
        "VALUES (?,?,?,?,?)", ("teardown", "user", "superseded", NOW, "local"),
    )
    conn.execute(
        "INSERT INTO conversations(session_id,role,content,created_at,user_id) "
        "VALUES (?,?,?,?,?)", ("teardown", "user", "latest", NOW, "local"),
    )
    conn.execute(
        "INSERT INTO conversations(session_id,role,content,created_at,user_id) "
        "VALUES (?,?,?,?,?)", ("teardown", "assistant", "reply", NOW, "local"),
    )
    conn.commit()

    first = enqueue_finished_session_exchanges(
        conn, session_id="teardown", policy_version="b1", now_iso=NOW,
    )
    second = enqueue_finished_session_exchanges(
        conn, session_id="teardown", policy_version="b1", now_iso=NOW,
    )

    jobs = conn.execute(
        "SELECT user_turn_id,assistant_turn_id FROM memory_admission_jobs "
        "WHERE session_id='teardown' ORDER BY id"
    ).fetchall()
    assert first == 2 and second == 0
    assert len(jobs) == 2
    assert conn.execute(
        "SELECT last_processed_conversation_id FROM memory_extraction_cursor WHERE id=1"
    ).fetchone()[0] == 0


def test_claims_are_single_owner_across_worker_connections(tmp_path):
    db_path = tmp_path / "shared.db"
    first = get_conn(db_path)
    run_migrations(first)
    job_id, *_ = _enqueue(first)
    second = get_conn(db_path)
    assert [row["id"] for row in claim_due_jobs(first, now_iso=NOW)] == [job_id]
    assert claim_due_jobs(second, now_iso=NOW) == []


def test_simultaneous_worker_connections_claim_job_once(tmp_path):
    db_path = tmp_path / "concurrent-claims.db"
    setup = get_conn(db_path)
    run_migrations(setup)
    job_id, *_ = _enqueue(setup)
    setup.close()

    gate = Barrier(2)

    def claim_after_barrier():
        worker_conn = get_conn(db_path)
        try:
            gate.wait(timeout=5)
            return [row["id"] for row in claim_due_jobs(worker_conn, now_iso=NOW)]
        finally:
            worker_conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [future.result(timeout=10) for future in (
            pool.submit(claim_after_barrier), pool.submit(claim_after_barrier),
        )]

    assert sorted(first + second) == [job_id]
    inspect = get_conn(db_path)
    row = inspect.execute(
        "SELECT status,stage,claimed_at FROM memory_admission_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert row["status"] == "running"
    assert row["stage"] == "extract"


def test_independent_worker_processes_claim_job_once(tmp_path):
    db_path = tmp_path / "multiprocess-claims.db"
    setup = get_conn(db_path)
    run_migrations(setup)
    job_id, *_ = _enqueue(setup)
    setup.close()

    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ready_events = [context.Event(), context.Event()]
    results = context.Queue()
    workers = [
        context.Process(
            target=_claim_from_process,
            args=(str(db_path), start, ready_events[index], results),
        )
        for index in range(2)
    ]
    workers[0].start()
    first_ready = ready_events[0].wait(timeout=15)
    if first_ready:
        workers[1].start()
    second_ready = first_ready and ready_events[1].wait(timeout=15)
    start.set()
    claimed = []
    try:
        for worker in workers:
            if worker.pid is not None:
                worker.join(timeout=20)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
        claimed = [results.get(timeout=5) for worker in workers if worker.pid is not None]
    finally:
        results.close()

    assert first_ready and second_ready
    assert len(claimed) == 2
    assert all(worker.exitcode == 0 for worker in workers)
    assert all(isinstance(item, list) for item in claimed), claimed
    assert sorted(job for batch in claimed for job in batch) == [job_id]

    inspect = get_conn(db_path)
    row = inspect.execute(
        "SELECT status,stage,claimed_at FROM memory_admission_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert row["status"] == "running"
    assert row["stage"] == "extract"
    assert row["claimed_at"] == NOW


def test_forget_wins_against_cross_process_lease_reclaim(tmp_path):
    db_path = tmp_path / "multiprocess-forget-reclaim.db"
    setup = get_conn(db_path)
    run_migrations(setup)
    job_id, *_ = _enqueue(setup)
    setup.execute(
        "UPDATE memory_admission_jobs SET status='running',stage='classify',"
        "candidate_json=?,claimed_at=?,updated_at=? WHERE id=?",
        ('{"facts":[{"key":"user.style.concise","value":"Concise"}],'
         '"observations":[]}', "2026-09-25T12:00:00+00:00", NOW, job_id),
    )
    setup.commit()
    setup.close()

    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ready_events = [context.Event(), context.Event()]
    results = context.Queue()
    workers = [
        context.Process(
            target=_forget_or_reclaim_from_process,
            args=(str(db_path), start, ready_events[index], results),
            kwargs={"forget": forget},
        )
        for index, forget in enumerate((True, False))
    ]
    workers[0].start()
    first_ready = ready_events[0].wait(timeout=15)
    if first_ready:
        workers[1].start()
    second_ready = first_ready and ready_events[1].wait(timeout=15)
    start.set()
    try:
        for worker in workers:
            if worker.pid is not None:
                worker.join(timeout=20)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
        outcomes = [results.get(timeout=5) for worker in workers if worker.pid is not None]
    finally:
        results.close()

    assert first_ready and second_ready
    assert len(outcomes) == 2
    assert all(worker.exitcode == 0 for worker in workers)
    assert {next(iter(item)) for item in outcomes} == {"forgot", "reclaimed"}
    assert not any("error" in item for item in outcomes)
    assert next(item["reclaimed"] for item in outcomes if "reclaimed" in item) in {0, 1}

    inspect = get_conn(db_path)
    row = inspect.execute(
        "SELECT status,stage,candidate_json,classification_json,claimed_at "
        "FROM memory_admission_jobs WHERE id=?", (job_id,),
    ).fetchone()
    assert row["status"] == "cancelled"
    assert row["candidate_json"] is None
    assert row["classification_json"] is None
    assert row["claimed_at"] is None


def test_stages_commit_and_terminal_success_drops_payloads(tmp_path):
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    claimed = claim_due_jobs(conn, now_iso=NOW)
    assert [row["id"] for row in claimed] == [job_id]
    assert claimed[0]["status"] == "running"
    assert not conn.in_transaction

    candidates = {"facts": [{"key": "user.style.concise", "value": "Prefers concise answers"}],
                  "observations": []}
    assert save_extracted_candidates(conn, job_id=job_id,
                                     candidates=candidates, now_iso=NOW)
    row = conn.execute("SELECT stage,status,candidate_json FROM memory_admission_jobs WHERE id=?",
                       (job_id,)).fetchone()
    assert (row["stage"], row["status"]) == ("classify", "pending")
    assert json.loads(row["candidate_json"]) == candidates

    claimed = claim_due_jobs(conn, now_iso=NOW)
    classified = [_classification("user.style.concise")]
    assert save_classification(conn, job_id=job_id,
                               classifications=classified, now_iso=NOW)
    row = conn.execute("SELECT stage,status,classification_json FROM memory_admission_jobs WHERE id=?",
                       (job_id,)).fetchone()
    assert (row["stage"], row["status"]) == ("apply", "pending")
    assert json.loads(row["classification_json"]) == classified

    claim_due_jobs(conn, now_iso=NOW)
    assert complete_job(conn, job_id=job_id, now_iso=NOW)
    row = conn.execute("SELECT status,candidate_json,classification_json FROM memory_admission_jobs WHERE id=?",
                       (job_id,)).fetchone()
    assert (row["status"], row["candidate_json"], row["classification_json"]) == (
        "complete", None, None,
    )


def test_classification_must_match_candidate_keys_and_order(tmp_path):
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    claim_due_jobs(conn, now_iso=NOW)
    candidates = {"facts": [{"key": "a", "value": "A"}, {"key": "b", "value": "B"}],
                  "observations": []}
    assert save_extracted_candidates(conn, job_id=job_id,
                                     candidates=candidates, now_iso=NOW)
    claim_due_jobs(conn, now_iso=NOW)
    with pytest.raises(AdmissionJobError, match="keys/order"):
        save_classification(conn, job_id=job_id,
                            classifications=[_classification("b"), _classification("a")],
                            now_iso=NOW)
    row = conn.execute("SELECT stage,status,classification_json FROM memory_admission_jobs WHERE id=?",
                       (job_id,)).fetchone()
    assert (row["stage"], row["status"], row["classification_json"]) == (
        "classify", "running", None,
    )


def test_retry_schedule_is_bounded_and_keeps_stage_payload(tmp_path):
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    for attempt, (expected, stamp) in enumerate((
        ("pending", "2099-01-01T00:00:00+00:00"),
        ("pending", "2099-01-01T00:01:00+00:00"),
        ("failed", "2099-01-01T00:06:00+00:00"),
    ), start=1):
        claim_due_jobs(conn, now_iso=stamp)
        assert fail_or_retry_job(conn, job_id=job_id,
                                 now_iso=stamp,
                                 error_code="provider_unavailable")
        row = conn.execute("SELECT status,attempts,last_error_code FROM memory_admission_jobs WHERE id=?",
                           (job_id,)).fetchone()
        assert (row["status"], row["attempts"], row["last_error_code"]) == (
            expected, attempt, "provider_unavailable",
        )


def test_forget_cancels_inflight_claim_and_removes_payload(tmp_path):
    conn = _db(tmp_path)
    job_id, _, user_turn, _ = _enqueue(conn)
    claim_due_jobs(conn, now_iso=NOW)
    assert cancel_jobs_for_turn(conn, user_id="local", session_id="s1",
                                user_turn_id=user_turn, now_iso=NOW) == 1
    row = conn.execute("SELECT status,candidate_json,classification_json FROM memory_admission_jobs WHERE id=?",
                       (job_id,)).fetchone()
    assert (row["status"], row["candidate_json"], row["classification_json"]) == (
        "cancelled", None, None,
    )
    assert not save_extracted_candidates(
        conn, job_id=job_id, candidates={"facts": [], "observations": []}, now_iso=NOW,
    )


def test_forgetting_admitted_fact_cancels_its_source_exchange(tmp_path):
    conn = _db(tmp_path)
    job_id, _, user_turn, _ = _enqueue(conn)
    conn.execute(
        "INSERT INTO memories(kind,key,content,source_session_id,source_turn_id,created_at,updated_at,user_id) "
        "VALUES ('fact','user.style.concise','Prefers concise answers','s1',?,?,?,'local')",
        (str(user_turn), NOW, NOW),
    )
    conn.commit()
    assert delete_fact(conn, "user.style.concise")
    row = conn.execute(
        "SELECT status,candidate_json,classification_json FROM memory_admission_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert (row["status"], row["candidate_json"], row["classification_json"]) == (
        "cancelled", None, None,
    )


def test_forgetting_candidate_key_cancels_staged_job_before_memory_exists(tmp_path):
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    claim_due_jobs(conn, now_iso=NOW)
    assert save_extracted_candidates(
        conn, job_id=job_id,
        candidates={"facts": [{"key": "user.style.concise", "value": "Concise"}],
                    "observations": []},
        now_iso=NOW,
    )

    assert delete_fact(conn, "user.style.concise") is False
    row = conn.execute(
        "SELECT status,candidate_json,classification_json FROM memory_admission_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert (row["status"], row["candidate_json"], row["classification_json"]) == (
        "cancelled", None, None,
    )


def test_cancel_jobs_for_key_only_cancels_matching_key(tmp_path):
    conn = _db(tmp_path)
    first, *_ = _enqueue(conn, session="s1")
    second, *_ = _enqueue(conn, session="s2")
    for job_id, key in ((first, "user.style.concise"), (second, "user.name")):
        claim_due_jobs(conn, now_iso=NOW)
        assert save_extracted_candidates(
            conn, job_id=job_id,
            candidates={"facts": [{"key": key, "value": "candidate"}],
                        "observations": []},
            now_iso=NOW,
        )
    assert cancel_jobs_for_key(
        conn, user_id="local", key="user.style.concise", now_iso=NOW,
    ) == 1
    statuses = [row["status"] for row in conn.execute(
        "SELECT status FROM memory_admission_jobs ORDER BY id"
    )]
    assert statuses == ["cancelled", "pending"]


def test_cancel_all_user_jobs_purges_failed_and_pending_staging(tmp_path):
    conn = _db(tmp_path)
    first, *_ = _enqueue(conn, session="s1")
    second, *_ = _enqueue(conn, session="s2")
    claim_due_jobs(conn, now_iso=NOW, limit=20)
    fail_or_retry_job(conn, job_id=first, now_iso=NOW, error_code="test")
    assert cancel_user_jobs(conn, user_id="local", now_iso=NOW) == 2
    rows = conn.execute(
        "SELECT status,candidate_json,classification_json FROM memory_admission_jobs ORDER BY id"
    ).fetchall()
    assert all(row["status"] == "cancelled" and row["candidate_json"] is None
               and row["classification_json"] is None for row in rows)


def test_reclaim_abandoned_job_uses_retry_policy(tmp_path):
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    claim_due_jobs(conn, now_iso=NOW)
    assert reclaim_abandoned_jobs(
        conn, now_iso="2026-09-25T12:04:00+00:00", lease_timeout_s=180,
    ) == 1
    row = conn.execute("SELECT status,attempts,last_error_code FROM memory_admission_jobs WHERE id=?",
                       (job_id,)).fetchone()
    assert (row["status"], row["attempts"], row["last_error_code"]) == (
        "pending", 1, "worker_interrupted",
    )


def test_stale_extractor_cannot_write_after_claim_is_recovered(tmp_path):
    db_path = tmp_path / "admission.db"
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    first_claim = claim_due_jobs(conn, now_iso=NOW)[0]
    old_claim = first_claim["claimed_at"]
    conn.close()

    conn = get_conn(db_path)
    assert reclaim_abandoned_jobs(
        conn, now_iso="2026-09-25T12:04:00+00:00", lease_timeout_s=180,
    ) == 1
    replacement = claim_due_jobs(
        conn, now_iso="2026-09-25T12:05:01+00:00",
    )[0]
    new_claim = replacement["claimed_at"]
    assert new_claim != old_claim

    candidates = {"facts": [{"key": "user.style.concise", "value": "Concise"}],
                  "observations": []}
    assert not save_extracted_candidates(
        conn, job_id=job_id, candidates=candidates,
        now_iso="2026-09-25T12:05:02+00:00",
        expected_claimed_at=old_claim,
    )
    assert not fail_or_retry_job(
        conn, job_id=job_id, now_iso="2026-09-25T12:05:02+00:00",
        error_code="late_provider_error", expected_claimed_at=old_claim,
    )
    row = conn.execute(
        "SELECT status,stage,attempts,candidate_json FROM memory_admission_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert (row["status"], row["stage"], row["attempts"], row["candidate_json"]) == (
        "running", "extract", 1, None,
    )
    assert save_extracted_candidates(
        conn, job_id=job_id, candidates=candidates,
        now_iso="2026-09-25T12:05:03+00:00",
        expected_claimed_at=new_claim,
    )


def test_stale_classifier_cannot_advance_reclaimed_job(tmp_path):
    db_path = tmp_path / "admission.db"
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    claim = claim_due_jobs(conn, now_iso=NOW)[0]
    candidates = {"facts": [{"key": "user.style.concise", "value": "Concise"}],
                  "observations": []}
    assert save_extracted_candidates(
        conn, job_id=job_id, candidates=candidates, now_iso=NOW,
        expected_claimed_at=claim["claimed_at"],
    )
    first_classifier_claim = claim_due_jobs(
        conn, now_iso="2026-09-25T12:00:01+00:00",
    )[0]
    old_claim = first_classifier_claim["claimed_at"]
    conn.close()

    conn = get_conn(db_path)
    assert reclaim_abandoned_jobs(
        conn, now_iso="2026-09-25T12:04:01+00:00", lease_timeout_s=180,
    ) == 1
    replacement = claim_due_jobs(
        conn, now_iso="2026-09-25T12:05:02+00:00",
    )[0]
    new_claim = replacement["claimed_at"]
    classification = [_classification("user.style.concise")]

    assert not save_classification(
        conn, job_id=job_id, classifications=classification,
        now_iso="2026-09-25T12:05:03+00:00",
        expected_claimed_at=old_claim,
    )
    row = conn.execute(
        "SELECT status,stage,classification_json FROM memory_admission_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert (row["status"], row["stage"], row["classification_json"]) == (
        "running", "classify", None,
    )
    assert save_classification(
        conn, job_id=job_id, classifications=classification,
        now_iso="2026-09-25T12:05:04+00:00",
        expected_claimed_at=new_claim,
    )


def test_payload_limits_and_json_types_are_enforced(tmp_path):
    conn = _db(tmp_path)
    job_id, *_ = _enqueue(conn)
    claim_due_jobs(conn, now_iso=NOW)
    with pytest.raises(AdmissionJobError, match="requires facts and observations"):
        save_extracted_candidates(conn, job_id=job_id,
                                  candidates={"facts": "bad", "observations": []},
                                  now_iso=NOW)
    with pytest.raises(AdmissionJobError, match="exceeds staging quota"):
        save_extracted_candidates(
            conn, job_id=job_id,
            candidates={"facts": [{"key": "k", "value": "x" * 70_000}],
                        "observations": []}, now_iso=NOW,
        )
