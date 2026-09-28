"""Unit tests for jarvis/memory_extraction_worker.py (MORTIMER_OPTIMIZATION_PLAN.md
Phase 2, "Extraction Gate", task 1 -- the standalone per-exchange polling
service). Mirrors tests/unit/test_memory.py and
tests/unit/test_memory_extraction.py's fixture/fake-client conventions.
"""

from __future__ import annotations

import json
import multiprocessing
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

import pytest

from jarvis import memory_extraction_worker
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.memory_admission import (
    claim_due_jobs,
    enqueue_exchange,
    reclaim_abandoned_jobs,
    save_classification,
    save_extracted_candidates,
)
from jarvis.memory_automation import (
    Classification,
    EvidenceStatus,
    MemoryType,
    Provenance,
    Scope,
)
from jarvis.memory_extraction_worker import (
    _iso_minus,
    process_admission_jobs,
    tick_once,
)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "mem.db"))
    c = get_conn(tmp_path / "mem.db")
    run_migrations(c)
    yield c
    c.close()


def _add_turn(conn, session_id, role, content):
    conn.execute(
        "INSERT INTO conversations (session_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?)",
        (session_id, role, content, now_iso()),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeCompletions:
    def __init__(self, payload):
        self._payload = payload

    async def create(self, **_kwargs):
        msg = _FakeMessage(self._payload)
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


class _FakeClient:
    def __init__(self, payload):
        self.chat = type("C", (), {"completions": _FakeCompletions(payload)})()


class _FakeSettings:
    openai_api_key = "k"
    openai_base_url = "http://unused"
    openai_model = "fake-model"


class _AutomationSettings(_FakeSettings):
    jarvis_memory_automation_enabled = True
    jarvis_memory_automation_shadow = False
    jarvis_memory_automation_stage = "explicit_preferences"


def _apply_admission_in_process(db_path, job_id, claimed_at, inserted, resume, results):
    """Pause an independent apply worker after inserting, before commit."""
    conn = get_conn(db_path)

    def pause_inside_transaction():
        inserted.set()
        if not resume.wait(timeout=15):
            raise TimeoutError("cross-process forget test did not release apply")
        return 0

    conn.create_function("pause_admission_apply", 0, pause_inside_transaction)
    try:
        result = memory_extraction_worker._apply_job_atomically(
            conn, job_id=job_id, expected_claimed_at=claimed_at,
            settings=_AutomationSettings(),
            now_iso_value="2026-09-25T12:00:05+00:00",
        )
        results.put({"applied": result})
    except BaseException as exc:
        results.put({"error": type(exc).__name__})
        raise
    finally:
        conn.close()


def _forget_admission_in_process(db_path, delete_started, results):
    """Issue forget in a distinct process while an apply transaction is open."""
    from jarvis.memory import delete_fact

    conn = get_conn(db_path)
    conn.set_trace_callback(
        lambda sql: delete_started.set()
        if sql.lstrip().upper().startswith("DELETE FROM MEMORIES") else None
    )
    try:
        result = delete_fact(conn, "user.preference.response_style")
        conn.commit()
        results.put({"forgot": result})
    except BaseException as exc:
        results.put({"error": type(exc).__name__})
        raise
    finally:
        conn.close()


class _ShadowAutomationSettings(_AutomationSettings):
    jarvis_memory_automation_shadow = True
    jarvis_memory_automation_stage = "shadow"


_EMPTY_PAYLOAD = json.dumps({"facts": [], "observations": []})


def _factory(payload):
    return lambda _settings: _FakeClient(payload)


def _fact_payload(key, value):
    return json.dumps({"facts": [{"key": key, "value": value}], "observations": []})


class _CapturingCompletions:
    def __init__(self, payload, sink):
        self._payload = payload
        self._sink = sink

    async def create(self, **kwargs):
        self._sink.append(kwargs["messages"][-1]["content"])
        msg = _FakeMessage(self._payload)
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


class _CapturingClient:
    def __init__(self, payload, sink):
        self.chat = type("C", (), {"completions": _CapturingCompletions(payload, sink)})()


def _capturing_factory(payload, sink):
    """Records the exchange text sent on every call (in order) into `sink`,
    so a test can assert WHICH user turn a pairing actually used, not just
    how many pairings happened."""
    return lambda _settings: _CapturingClient(payload, sink)


# --- tick_once: the tick must not hold its own write lock across extractions


class TestTickDoesNotDeadlockItself:
    """Item 13 (2026-09-17). Before the per-session commit, a multi-session
    batch lost every extraction after the first session that touched
    memory_extraction_pending: that INSERT/DELETE opened a transaction on the
    tick's connection, and extract_from_exchange's own connection then waited
    the full busy timeout for a lock the same thread was holding. 28 of 122
    exchanges on the 2026-09-16 backfill, all inside a write."""

    async def test_a_later_sessions_fact_lands_despite_an_earlier_pending_write(self, conn):
        # Session A: two user turns, no reply. Nothing to extract, but the
        # trailing user turn makes the tick write to the pending table --
        # which is what takes the lock.
        _add_turn(conn, "sess-a", "user", "first thing")
        _add_turn(conn, "sess-a", "user", "second thing, still no reply")
        # Session B, processed after A, has an exchange whose extraction
        # must WRITE a fact through its own connection.
        _add_turn(conn, "sess-b", "user", "I drive a 1969 Camaro")
        _add_turn(conn, "sess-b", "assistant", "Noted.")

        started = time.perf_counter()
        result = await tick_once(
            _FakeSettings(),
            client_factory=_factory(_fact_payload("user.car", "1969 Camaro")),
        )
        elapsed = time.perf_counter() - started

        assert result["exchanges"] == 1
        row = conn.execute("SELECT content FROM memories WHERE key='user.car'").fetchone()
        assert row is not None and row["content"] == "1969 Camaro", (
            "session B's fact was lost to a lock the tick itself was holding")
        # A self-deadlock stalls for the whole 5 s busy timeout per blocked
        # write before failing; a healthy tick is milliseconds.
        assert elapsed < 4.0
        pending = conn.execute(
            "SELECT session_id FROM memory_extraction_pending").fetchall()
        assert [r["session_id"] for r in pending] == ["sess-a"], (
            "the pending write itself still landed")


class TestAdmissionApplyRollback:
    def test_forget_racing_apply_does_not_leave_admitted_memory(
        self, conn, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "forget-apply-race", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "forget-apply-race", "assistant", "Understood.")
        job_id, created = enqueue_exchange(
            conn, user_id="local", session_id="forget-apply-race",
            user_turn_id=user_turn, assistant_turn_id=assistant_turn,
            policy_version="b1", now_iso="2026-09-25T12:00:00+00:00",
        )
        assert created
        conn.commit()
        extract_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:00:00+00:00",
        )[0]
        candidates = {
            "facts": [{"key": "user.preference.response_style",
                       "value": "I prefer concise answers"}],
            "observations": [],
        }
        assert save_extracted_candidates(
            conn, job_id=job_id, candidates=candidates,
            now_iso="2026-09-25T12:00:01+00:00",
            expected_claimed_at=extract_claim["claimed_at"],
        )
        classify_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:00:02+00:00",
        )[0]
        classification = {
            "key": "user.preference.response_style",
            "scope": "subject", "memory_type": "explicit_preference",
            "provenance": "user", "evidence_status": "explicit",
            "confidence": 1.0, "evidence": [str(user_turn)],
            "reason_code": "explicit", "subject": None, "project": None,
            "valid_from": None, "valid_until": None,
        }
        assert save_classification(
            conn, job_id=job_id, classifications=[classification],
            now_iso="2026-09-25T12:00:03+00:00",
            expected_claimed_at=classify_claim["claimed_at"],
        )
        apply_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:00:04+00:00",
        )[0]

        wrote_fact = Event()
        allow_apply_commit = Event()
        forget_delete_started = Event()
        original_admit = memory_extraction_worker.admit_fact_candidate

        def write_then_pause(*args, **kwargs):
            outcome = original_admit(*args, **kwargs)
            assert outcome == "inserted"
            wrote_fact.set()
            assert allow_apply_commit.wait(timeout=5)
            return outcome

        monkeypatch.setattr(memory_extraction_worker, "admit_fact_candidate",
                            write_then_pause)

        def apply_on_worker_connection():
            worker_conn = get_conn(tmp_path / "mem.db")
            try:
                return memory_extraction_worker._apply_job_atomically(
                    worker_conn, job_id=job_id,
                    expected_claimed_at=apply_claim["claimed_at"],
                    settings=_AutomationSettings(),
                    now_iso_value="2026-09-25T12:00:05+00:00",
                )
            finally:
                worker_conn.close()

        result = {}
        apply_thread = Thread(target=lambda: result.setdefault("applied", apply_on_worker_connection()))
        apply_thread.start()
        assert wrote_fact.wait(timeout=5)

        def forget_on_second_connection():
            from jarvis.memory import delete_fact

            forget_conn = get_conn(tmp_path / "mem.db")
            try:
                forget_conn.set_trace_callback(
                    lambda sql: forget_delete_started.set()
                    if sql.lstrip().upper().startswith("DELETE FROM MEMORIES")
                    else None
                )
                result = delete_fact(forget_conn, "user.preference.response_style")
                forget_conn.commit()
                return result
            finally:
                forget_conn.close()

        forget_result = {}
        forget_thread = Thread(
            target=lambda: forget_result.setdefault("forgot", forget_on_second_connection())
        )
        forget_thread.start()
        assert forget_delete_started.wait(timeout=5)
        allow_apply_commit.set()
        apply_thread.join(timeout=5)
        forget_thread.join(timeout=5)
        assert not apply_thread.is_alive()
        assert not forget_thread.is_alive()
        assert result["applied"] is True
        assert forget_result["forgot"] is True

        verify_conn = get_conn(tmp_path / "mem.db")
        assert verify_conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert verify_conn.execute(
            "SELECT status FROM memory_admission_jobs WHERE id=?", (job_id,),
        ).fetchone()["status"] == "complete"
        verify_conn.close()

    def test_forget_racing_apply_across_processes_leaves_no_memory(
        self, conn, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "cross-process-forget", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "cross-process-forget", "assistant", "Understood.")
        job_id, created = enqueue_exchange(
            conn, user_id="local", session_id="cross-process-forget",
            user_turn_id=user_turn, assistant_turn_id=assistant_turn,
            policy_version="b1", now_iso="2026-09-25T12:00:00+00:00",
        )
        assert created
        conn.commit()
        extract_claim = claim_due_jobs(conn, now_iso="2026-09-25T12:00:00+00:00")[0]
        candidates = {
            "facts": [{"key": "user.preference.response_style",
                       "value": "I prefer concise answers"}],
            "observations": [],
        }
        assert save_extracted_candidates(
            conn, job_id=job_id, candidates=candidates,
            now_iso="2026-09-25T12:00:01+00:00",
            expected_claimed_at=extract_claim["claimed_at"],
        )
        classify_claim = claim_due_jobs(conn, now_iso="2026-09-25T12:00:02+00:00")[0]
        classification = {
            "key": "user.preference.response_style", "scope": "subject",
            "memory_type": "explicit_preference", "provenance": "user",
            "evidence_status": "explicit", "confidence": 1.0,
            "evidence": [str(user_turn)], "reason_code": "explicit",
            "subject": None, "project": None, "valid_from": None,
            "valid_until": None,
        }
        assert save_classification(
            conn, job_id=job_id, classifications=[classification],
            now_iso="2026-09-25T12:00:03+00:00",
            expected_claimed_at=classify_claim["claimed_at"],
        )
        apply_claim = claim_due_jobs(conn, now_iso="2026-09-25T12:00:04+00:00")[0]
        db_path = tmp_path / "mem.db"
        conn.execute(
            "CREATE TRIGGER pause_admission_insert AFTER INSERT ON memories "
            "WHEN NEW.key='user.preference.response_style' BEGIN "
            "SELECT pause_admission_apply(); END"
        )
        conn.commit()

        context = multiprocessing.get_context("spawn")
        inserted = context.Event()
        resume = context.Event()
        delete_started = context.Event()
        results = context.Queue()
        apply_worker = context.Process(
            target=_apply_admission_in_process,
            args=(str(db_path), job_id, apply_claim["claimed_at"], inserted, resume, results),
        )
        forget_worker = context.Process(
            target=_forget_admission_in_process,
            args=(str(db_path), delete_started, results),
        )
        apply_worker.start()
        try:
            assert inserted.wait(timeout=15), "apply worker did not reach its insert transaction"
            forget_worker.start()
            assert delete_started.wait(timeout=15), "forget worker did not issue its delete"
        finally:
            resume.set()
            for worker in (apply_worker, forget_worker):
                if worker.pid is not None:
                    worker.join(timeout=20)
                    if worker.is_alive():
                        worker.terminate()
                        worker.join(timeout=5)

        outcomes = [results.get(timeout=5) for _ in range(2)]
        results.close()
        assert apply_worker.exitcode == 0
        assert forget_worker.exitcode == 0
        assert {tuple(item.items()) for item in outcomes} == {
            (("applied", True),), (("forgot", True),),
        }
        verify_conn = get_conn(db_path)
        assert verify_conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert verify_conn.execute(
            "SELECT status FROM memory_admission_jobs WHERE id=?", (job_id,),
        ).fetchone()["status"] == "complete"
        verify_conn.close()

    def test_stale_apply_claim_cannot_apply_after_lease_recovery(self, conn):
        user_turn = _add_turn(conn, "stale-apply", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "stale-apply", "assistant", "Understood.")
        job_id, created = enqueue_exchange(
            conn, user_id="local", session_id="stale-apply",
            user_turn_id=user_turn, assistant_turn_id=assistant_turn,
            policy_version="b1", now_iso="2026-09-25T12:00:00+00:00",
        )
        assert created
        conn.commit()

        extract_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:00:00+00:00",
        )[0]
        candidates = {
            "facts": [{"key": "user.preference.response_style",
                       "value": "I prefer concise answers"}],
            "observations": [],
        }
        assert save_extracted_candidates(
            conn, job_id=job_id, candidates=candidates,
            now_iso="2026-09-25T12:00:01+00:00",
            expected_claimed_at=extract_claim["claimed_at"],
        )
        classify_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:00:02+00:00",
        )[0]
        classification = {
            "key": "user.preference.response_style",
            "scope": "subject", "memory_type": "explicit_preference",
            "provenance": "user", "evidence_status": "explicit",
            "confidence": 1.0, "evidence": [str(user_turn)],
            "reason_code": "explicit", "subject": None, "project": None,
            "valid_from": None, "valid_until": None,
        }
        assert save_classification(
            conn, job_id=job_id, classifications=[classification],
            now_iso="2026-09-25T12:00:03+00:00",
            expected_claimed_at=classify_claim["claimed_at"],
        )
        stale_apply_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:00:04+00:00",
        )[0]
        stale_claimed_at = stale_apply_claim["claimed_at"]

        assert reclaim_abandoned_jobs(
            conn, now_iso="2026-09-25T12:04:05+00:00", lease_timeout_s=180,
        ) == 1
        current_apply_claim = claim_due_jobs(
            conn, now_iso="2026-09-25T12:05:06+00:00",
        )[0]
        current_claimed_at = current_apply_claim["claimed_at"]
        assert current_claimed_at != stale_claimed_at

        assert not memory_extraction_worker._apply_job_atomically(
            conn, job_id=job_id, expected_claimed_at=stale_claimed_at,
            settings=_AutomationSettings(), now_iso_value="2026-09-25T12:05:07+00:00",
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        current = conn.execute(
            "SELECT status,stage,claimed_at FROM memory_admission_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        assert (current["status"], current["stage"], current["claimed_at"]) == (
            "running", "apply", current_claimed_at,
        )

        assert memory_extraction_worker._apply_job_atomically(
            conn, job_id=job_id, expected_claimed_at=current_claimed_at,
            settings=_AutomationSettings(), now_iso_value="2026-09-25T12:05:08+00:00",
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT status FROM memory_admission_jobs WHERE id=?", (job_id,),
        ).fetchone()["status"] == "complete"

    @pytest.mark.asyncio
    async def test_apply_failure_rolls_back_memory_shadow_and_completion(
        self, conn, monkeypatch, caplog
    ):
        """A failure after a memory write must roll back the whole apply unit."""
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "rollback-session", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "rollback-session", "assistant",
                                   "Understood.")
        await tick_once(_AutomationSettings())

        assert process_admission_jobs(
            _AutomationSettings(), extractor=lambda *_: {
                "facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": [],
            },
        )["extracted"] == 1

        def classifier(candidates, *, policy_version):
            assert policy_version == "b1"
            return [Classification(
                key=candidates[0].key, scope=Scope.SUBJECT,
                memory_type=MemoryType.EXPLICIT_PREFERENCE,
                provenance=Provenance.USER,
                evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                evidence=(str(user_turn),), reason_code="explicit",
            )]

        assert process_admission_jobs(
            _AutomationSettings(), classifier=classifier,
        )["classified"] == 1

        job_id = conn.execute(
            "SELECT id FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()["id"]
        original_admit = memory_extraction_worker.admit_fact_candidate

        def write_then_fail(*args, **kwargs):
            outcome = original_admit(*args, **kwargs)
            assert outcome == "inserted"
            # Raise after the fact and its recurrence data have been written,
            # while _apply_job_atomically still owns the transaction.
            raise RuntimeError("injected apply interruption")

        monkeypatch.setattr(memory_extraction_worker, "admit_fact_candidate",
                            write_then_fail)
        result = process_admission_jobs(_AutomationSettings())

        assert result["failed"] == 1
        assert "memory_admission_stage_failed stage=apply error_type=RuntimeError" in caplog.text
        assert "injected apply interruption" not in caplog.text
        assert str(job_id) not in caplog.text
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_recall_events WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 0
        job = conn.execute(
            "SELECT status,stage,attempts,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert job["status"] == "pending"
        assert job["stage"] == "apply"
        assert job["attempts"] == 1
        assert job["candidate_json"] is not None
        assert job["classification_json"] is not None

        # A later worker process can claim the durable retry and finish once.
        monkeypatch.setattr(memory_extraction_worker, "admit_fact_candidate",
                            original_admit)
        retried = process_admission_jobs(
            _AutomationSettings(), now_iso_value="2099-01-01T00:00:00+00:00",
        )
        assert retried["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 1
        completed = conn.execute(
            "SELECT status,stage,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert completed["status"] == "complete"
        assert completed["stage"] == "apply"
        assert completed["candidate_json"] is None
        assert completed["classification_json"] is None

    @pytest.mark.asyncio
    async def test_process_exit_after_completion_update_rolls_back_and_retries(
        self, conn, monkeypatch, tmp_path
    ):
        """Completion update and memory writes commit or roll back as one unit."""
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "completion-crash", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "completion-crash", "assistant",
                                   "Understood.")
        await tick_once(_AutomationSettings())
        assert process_admission_jobs(
            _AutomationSettings(), extractor=lambda *_: {
                "facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": [],
            },
        )["extracted"] == 1

        def classifier(candidates, *, policy_version):
            assert policy_version == "b1"
            return [Classification(
                key=candidates[0].key, scope=Scope.SUBJECT,
                memory_type=MemoryType.EXPLICIT_PREFERENCE,
                provenance=Provenance.USER,
                evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                evidence=(str(user_turn),), reason_code="explicit",
            )]

        assert process_admission_jobs(
            _AutomationSettings(), classifier=classifier,
        )["classified"] == 1

        child_program = """
import os
from jarvis import memory_extraction_worker as worker

class Settings:
    jarvis_memory_automation_enabled = True
    jarvis_memory_automation_shadow = False
    jarvis_memory_automation_stage = "explicit_preferences"

real_get_conn = worker.get_conn
class CrashBeforeCompletionCommit:
    def __init__(self, connection):
        self.connection = connection
        self.armed = False
    def execute(self, sql, parameters=()):
        result = self.connection.execute(sql, parameters)
        if "SET status='complete'" in sql:
            self.armed = True
        return result
    def commit(self):
        if self.armed:
            os._exit(79)
        self.connection.commit()
    def __getattr__(self, name):
        return getattr(self.connection, name)

worker.get_conn = lambda db_path=None: CrashBeforeCompletionCommit(
    real_get_conn(db_path),
)
worker.process_admission_jobs(Settings())
raise SystemExit("the injected completion-boundary exit did not run")
"""
        child_env = {
            "JARVIS_DB_PATH": str(tmp_path / "mem.db"),
            "JARVIS_MEMORY_AUTOMATION_ENABLED": "true",
            "PYTHONNOUSERSITE": "1",
        }
        child = subprocess.run(
            [sys.executable, "-c", child_program], cwd=Path.cwd(),
            env=child_env, capture_output=True, text=True, timeout=20,
            check=False,
        )
        assert child.returncode == 79, child.stderr

        # SQLite must undo the fact, shadow record, and uncommitted completion.
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 0
        interrupted = conn.execute(
            "SELECT status,stage,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert interrupted["status"] == "running"
        assert interrupted["stage"] == "apply"
        assert interrupted["candidate_json"] is not None
        assert interrupted["classification_json"] is not None

        recovered_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        assert process_admission_jobs(
            _AutomationSettings(), now_iso_value=recovered_at.isoformat(),
        )["recovered"] == 1
        retried_at = recovered_at + timedelta(minutes=2)
        assert process_admission_jobs(
            _AutomationSettings(), now_iso_value=retried_at.isoformat(),
        )["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 1
        completed = conn.execute(
            "SELECT status,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert completed["status"] == "complete"
        assert completed["candidate_json"] is None
        assert completed["classification_json"] is None


class TestAdmissionEnqueueCrashRecovery:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("crash_point", "exit_code", "persisted_jobs"),
        [("before_session_commit", 73, 0), ("after_session_commit", 74, 1)],
    )
    async def test_poll_crash_keeps_enqueue_and_cursor_idempotent(
        self, conn, monkeypatch, tmp_path, crash_point, exit_code, persisted_jobs
    ):
        """The cursor may lag a durable enqueue, but replay must remain idempotent."""
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        _add_turn(conn, "enqueue-crash", "user", "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "enqueue-crash", "assistant", "Understood.")

        child_program = """
import asyncio
import os
import sys
from jarvis import memory_extraction_worker as worker

class Settings:
    jarvis_memory_automation_enabled = True
    jarvis_memory_automation_shadow = False
    jarvis_memory_automation_stage = "explicit_preferences"

point = sys.argv[1]
if point == "before_session_commit":
    original = worker.enqueue_exchange
    def enqueue_then_exit(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(73)
    worker.enqueue_exchange = enqueue_then_exit
else:
    def exit_before_cursor_commit(*_args, **_kwargs):
        os._exit(74)
    worker._set_cursor = exit_before_cursor_commit

asyncio.run(worker.tick_once(Settings(), db_path=os.environ["JARVIS_DB_PATH"]))
raise SystemExit("the injected poll exit did not run")
"""
        child_env = {
            "JARVIS_DB_PATH": str(tmp_path / "mem.db"),
            "JARVIS_MEMORY_AUTOMATION_ENABLED": "true",
            "PYTHONNOUSERSITE": "1",
        }
        child = subprocess.run(
            [sys.executable, "-c", child_program, crash_point],
            cwd=Path.cwd(), env=child_env, capture_output=True, text=True,
            timeout=20, check=False,
        )
        assert child.returncode == exit_code, child.stderr

        cursor = conn.execute(
            "SELECT last_processed_conversation_id FROM memory_extraction_cursor "
            "WHERE id=1"
        ).fetchone()[0]
        assert cursor == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_jobs"
        ).fetchone()[0] == persisted_jobs
        if persisted_jobs:
            # Avoid invoking the model adapter while this test exercises only
            # transcript replay and queue idempotency.
            conn.execute(
                "UPDATE memory_admission_jobs SET next_attempt_at=?",
                ("2099-01-01T00:00:00+00:00",),
            )
            conn.commit()

        # Replay the same transcript window. A pre-commit crash creates the
        # missing enqueue; a post-commit/pre-cursor crash hits the idempotency
        # key and must not duplicate the already durable job.
        replay = await tick_once(_AutomationSettings())
        assert replay["cursor"] == assistant_turn
        assert replay["exchanges"] == (1 if persisted_jobs == 0 else 0)
        jobs = conn.execute(
            "SELECT status,stage,user_turn_id,assistant_turn_id "
            "FROM memory_admission_jobs"
        ).fetchall()
        assert len(jobs) == 1
        assert (jobs[0]["status"], jobs[0]["stage"]) == ("pending", "extract")
        assert jobs[0]["assistant_turn_id"] == assistant_turn
        assert jobs[0]["user_turn_id"] < assistant_turn
        assert conn.execute(
            "SELECT last_processed_conversation_id FROM memory_extraction_cursor "
            "WHERE id=1"
        ).fetchone()[0] == assistant_turn


class TestAdmissionStageCrashRecovery:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("stage", "exit_code"), [("extract", 75), ("classify", 76)])
    async def test_committed_stage_survives_worker_exit_and_resumes(
        self, conn, monkeypatch, tmp_path, stage, exit_code
    ):
        """A worker exit after a durable stage commit resumes at the next stage."""
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, f"{stage}-crash", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, f"{stage}-crash", "assistant",
                                   "Understood.")
        await tick_once(_AutomationSettings())

        if stage == "classify":
            assert process_admission_jobs(
                _AutomationSettings(), extractor=lambda *_: {
                    "facts": [{"key": "user.preference.response_style",
                               "value": "I prefer concise answers"}],
                    "observations": [],
                },
            )["extracted"] == 1

        child_program = """
import os
import sys
from jarvis import memory_extraction_worker as worker
from jarvis.memory_automation import (
    Classification, EvidenceStatus, MemoryType, Provenance, Scope,
)

class Settings:
    jarvis_memory_automation_enabled = True
    jarvis_memory_automation_shadow = False
    jarvis_memory_automation_stage = "explicit_preferences"

stage = sys.argv[1]
if stage == "extract":
    original = worker.save_extracted_candidates
    def commit_then_exit(*args, **kwargs):
        saved = original(*args, **kwargs)
        if saved:
            os._exit(75)
        return saved
    worker.save_extracted_candidates = commit_then_exit
    def extract(*_args):
        return {"facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": []}
    worker.process_admission_jobs(Settings(), extractor=extract)
else:
    original = worker.save_classification
    def commit_then_exit(*args, **kwargs):
        saved = original(*args, **kwargs)
        if saved:
            os._exit(76)
        return saved
    worker.save_classification = commit_then_exit
    source_turn = sys.argv[2]
    def classify(candidates, *, policy_version):
        return [Classification(
            key=candidates[0].key, scope=Scope.SUBJECT,
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            provenance=Provenance.USER,
            evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
            evidence=(source_turn,), reason_code="explicit",
        )]
    worker.process_admission_jobs(Settings(), classifier=classify)
raise SystemExit("the injected stage exit did not run")
"""
        child_env = {
            "JARVIS_DB_PATH": str(tmp_path / "mem.db"),
            "JARVIS_MEMORY_AUTOMATION_ENABLED": "true",
            "PYTHONNOUSERSITE": "1",
        }
        child_args = [sys.executable, "-c", child_program, stage]
        if stage == "classify":
            child_args.append(str(user_turn))
        child = subprocess.run(
            child_args, cwd=Path.cwd(), env=child_env,
            capture_output=True, text=True, timeout=20, check=False,
        )
        assert child.returncode == exit_code, child.stderr

        job = conn.execute(
            "SELECT status,stage,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        if stage == "extract":
            assert (job["status"], job["stage"]) == ("pending", "classify")
            assert job["candidate_json"] is not None
            assert job["classification_json"] is None

            def classifier(candidates, *, policy_version):
                assert policy_version == "b1"
                return [Classification(
                    key=candidates[0].key, scope=Scope.SUBJECT,
                    memory_type=MemoryType.EXPLICIT_PREFERENCE,
                    provenance=Provenance.USER,
                    evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                    evidence=(str(user_turn),), reason_code="explicit",
                )]

            assert process_admission_jobs(
                _AutomationSettings(), classifier=classifier,
            )["classified"] == 1
        else:
            assert (job["status"], job["stage"]) == ("pending", "apply")
            assert job["candidate_json"] is not None
            assert job["classification_json"] is not None

        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert process_admission_jobs(_AutomationSettings())["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 1
        completed = conn.execute(
            "SELECT status,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert completed["status"] == "complete"
        assert completed["candidate_json"] is None
        assert completed["classification_json"] is None


class TestAdmissionStageCommitCrashRecovery:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("stage", "exit_code"), [("extract", 77), ("classify", 78)])
    async def test_uncommitted_stage_transition_rolls_back_then_retries(
        self, conn, monkeypatch, tmp_path, stage, exit_code
    ):
        """Exiting at the stage-save commit boundary leaves no partial transition."""
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, f"{stage}-transaction-crash", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, f"{stage}-transaction-crash", "assistant",
                                   "Understood.")
        await tick_once(_AutomationSettings())

        if stage == "classify":
            assert process_admission_jobs(
                _AutomationSettings(), extractor=lambda *_: {
                    "facts": [{"key": "user.preference.response_style",
                               "value": "I prefer concise answers"}],
                    "observations": [],
                },
            )["extracted"] == 1

        child_program = """
import os
import sys
from jarvis import memory_extraction_worker as worker
from jarvis.memory_automation import (
    Classification, EvidenceStatus, MemoryType, Provenance, Scope,
)

class Settings:
    jarvis_memory_automation_enabled = True
    jarvis_memory_automation_shadow = False
    jarvis_memory_automation_stage = "explicit_preferences"

stage = sys.argv[1]
source_turn = sys.argv[2]
exit_code = int(sys.argv[3])
real_get_conn = worker.get_conn
class CrashOnStageCommit:
    def __init__(self, connection):
        self.connection = connection
        self.armed = False
    def execute(self, sql, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        if ((stage == "extract" and "SET candidate_json=" in sql)
                or (stage == "classify" and "SET classification_json=" in sql)):
            self.armed = True
        return cursor
    def commit(self):
        if self.armed:
            os._exit(exit_code)
        self.connection.commit()
    def __getattr__(self, name):
        return getattr(self.connection, name)

worker.get_conn = lambda db_path=None: CrashOnStageCommit(real_get_conn(db_path))
if stage == "extract":
    def extract(*_args):
        return {"facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": []}
    worker.process_admission_jobs(Settings(), extractor=extract)
else:
    def classify(candidates, *, policy_version):
        return [Classification(
            key=candidates[0].key, scope=Scope.SUBJECT,
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            provenance=Provenance.USER,
            evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
            evidence=(source_turn,), reason_code="explicit",
        )]
    worker.process_admission_jobs(Settings(), classifier=classify)
raise SystemExit("the injected transaction-boundary exit did not run")
"""
        child_env = {
            "JARVIS_DB_PATH": str(tmp_path / "mem.db"),
            "JARVIS_MEMORY_AUTOMATION_ENABLED": "true",
            "PYTHONNOUSERSITE": "1",
        }
        child = subprocess.run(
            [sys.executable, "-c", child_program, stage, str(user_turn),
             str(exit_code)], cwd=Path.cwd(), env=child_env,
            capture_output=True, text=True, timeout=20, check=False,
        )
        assert child.returncode == exit_code, child.stderr

        interrupted = conn.execute(
            "SELECT status,stage,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert interrupted["status"] == "running"
        assert interrupted["stage"] == stage
        assert (interrupted["candidate_json"] is not None) == (stage == "classify")
        assert interrupted["classification_json"] is None
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0

        recovered_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        recovery = process_admission_jobs(
            _AutomationSettings(), now_iso_value=recovered_at.isoformat(),
        )
        assert recovery["recovered"] == 1
        retry_at = recovered_at + timedelta(minutes=2)
        if stage == "extract":
            retried = process_admission_jobs(
                _AutomationSettings(), now_iso_value=retry_at.isoformat(),
                extractor=lambda *_: {
                    "facts": [{"key": "user.preference.response_style",
                               "value": "I prefer concise answers"}],
                    "observations": [],
                },
            )
            assert retried["extracted"] == 1
            assert process_admission_jobs(
                _AutomationSettings(),
                now_iso_value=(retry_at + timedelta(minutes=2)).isoformat(),
                classifier=lambda candidates, **_: [Classification(
                    key=candidates[0].key, scope=Scope.SUBJECT,
                    memory_type=MemoryType.EXPLICIT_PREFERENCE,
                    provenance=Provenance.USER,
                    evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                    evidence=(str(user_turn),), reason_code="explicit",
                )],
            )["classified"] == 1
        else:
            def classifier(candidates, *, policy_version):
                assert policy_version == "b1"
                return [Classification(
                    key=candidates[0].key, scope=Scope.SUBJECT,
                    memory_type=MemoryType.EXPLICIT_PREFERENCE,
                    provenance=Provenance.USER,
                    evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                    evidence=(str(user_turn),), reason_code="explicit",
                )]
            retried = process_admission_jobs(
                _AutomationSettings(), now_iso_value=retry_at.isoformat(),
                classifier=classifier,
            )
            assert retried["classified"] == 1

        assert process_admission_jobs(
            _AutomationSettings(),
            now_iso_value=(retry_at + timedelta(minutes=4)).isoformat(),
        )["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 1
        done = conn.execute(
            "SELECT status FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert done["status"] == "complete"

    @pytest.mark.asyncio
    async def test_process_exit_during_apply_rolls_back_and_reclaims_job(
        self, conn, monkeypatch, tmp_path
    ):
        """An abrupt worker death rolls back apply and lease recovery resumes it."""
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "crash-session", "user",
                              "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "crash-session", "assistant",
                                   "Understood.")
        await tick_once(_AutomationSettings())
        assert process_admission_jobs(
            _AutomationSettings(), extractor=lambda *_: {
                "facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": [],
            },
        )["extracted"] == 1

        def classifier(candidates, *, policy_version):
            assert policy_version == "b1"
            return [Classification(
                key=candidates[0].key, scope=Scope.SUBJECT,
                memory_type=MemoryType.EXPLICIT_PREFERENCE,
                provenance=Provenance.USER,
                evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                evidence=(str(user_turn),), reason_code="explicit",
            )]

        assert process_admission_jobs(
            _AutomationSettings(), classifier=classifier,
        )["classified"] == 1

        child_program = """
import os
from jarvis import memory_extraction_worker as worker

class Settings:
    jarvis_memory_automation_enabled = True
    jarvis_memory_automation_shadow = False
    jarvis_memory_automation_stage = "explicit_preferences"

original = worker.admit_fact_candidate
def write_then_exit(*args, **kwargs):
    outcome = original(*args, **kwargs)
    if outcome != "inserted":
        raise RuntimeError("expected the fault-injection fact write")
    os._exit(73)

worker.admit_fact_candidate = write_then_exit
worker.process_admission_jobs(Settings())
raise SystemExit("the injected worker exit did not run")
"""
        child_env = {
            "JARVIS_DB_PATH": str(tmp_path / "mem.db"),
            "JARVIS_MEMORY_AUTOMATION_ENABLED": "true",
            "PYTHONNOUSERSITE": "1",
        }
        child = subprocess.run(
            [sys.executable, "-c", child_program], cwd=Path.cwd(),
            env=child_env, capture_output=True, text=True, timeout=20,
            check=False,
        )
        assert child.returncode == 73, child.stderr

        # Opening the parent's connection forces SQLite journal recovery after
        # the child exited while its write transaction was still open.
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_recall_events WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 0
        interrupted = conn.execute(
            "SELECT status,stage,candidate_json,classification_json,claimed_at "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert interrupted["status"] == "running"
        assert interrupted["stage"] == "apply"
        assert interrupted["candidate_json"] is not None
        assert interrupted["classification_json"] is not None

        recovered_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        recovered = process_admission_jobs(
            _AutomationSettings(), now_iso_value=recovered_at.isoformat(),
        )
        assert recovered["recovered"] == 1
        retried_at = recovered_at + timedelta(minutes=2)
        retried = process_admission_jobs(
            _AutomationSettings(), now_iso_value=retried_at.isoformat(),
        )
        assert retried["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 1
        completed = conn.execute(
            "SELECT status,candidate_json,classification_json "
            "FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()
        assert completed["status"] == "complete"
        assert completed["candidate_json"] is None
        assert completed["classification_json"] is None


# --- tick_once: basic pairing -------------------------------------------


class TestTickOnceBasicPairing:
    @pytest.mark.asyncio
    async def test_no_new_rows_is_a_noop(self, conn):
        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        assert result == {"rows": 0, "exchanges": 0, "cursor": 0}

    @pytest.mark.asyncio
    async def test_complete_exchange_extracts_and_advances_cursor(self, conn):
        user_id = _add_turn(conn, "s1", "user", "My name is Larry.")
        reply_id = _add_turn(conn, "s1", "assistant", "Noted, Larry.")

        result = await tick_once(
            _FakeSettings(), client_factory=_factory(_fact_payload("user.name", "Larry"))
        )

        assert result["rows"] == 2
        assert result["exchanges"] == 1
        assert result["cursor"] == reply_id
        assert (
            conn.execute("SELECT content FROM memories WHERE key='user.name'").fetchone()[
                "content"
            ]
            == "Larry"
        )
        assert conn.execute(
            "SELECT source_turn_id FROM memories WHERE key='user.name'"
        ).fetchone()[0] == str(user_id)
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending"
        ).fetchone()["n"] == 0

    @pytest.mark.asyncio
    async def test_automation_path_stages_before_cursor_and_resumes_all_stages(
        self, conn, monkeypatch
    ):
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "s1", "user", "I prefer concise answers.")
        assistant_turn = _add_turn(conn, "s1", "assistant", "Understood.")

        staged = await tick_once(_AutomationSettings())
        assert staged["cursor"] == assistant_turn
        assert staged["exchanges"] == 1
        job = conn.execute("SELECT * FROM memory_admission_jobs").fetchone()
        assert job["stage"] == "extract" and job["status"] == "pending"
        assert job["user_turn_id"] == user_turn
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0

        extracted = process_admission_jobs(
            _AutomationSettings(), extractor=lambda *_: {
                "facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": [],
            },
        )
        assert extracted["extracted"] == 1
        assert conn.execute(
            "SELECT stage,status FROM memory_admission_jobs"
        ).fetchone()["stage"] == "classify"

        def classifier(candidates, *, policy_version):
            assert policy_version == "b1"
            assert len(candidates) == 1
            return [Classification(
                key=candidates[0].key, scope=Scope.SUBJECT,
                memory_type=MemoryType.EXPLICIT_PREFERENCE,
                provenance=Provenance.USER,
                evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                evidence=(str(user_turn),), reason_code="explicit",
            )]

        classified = process_admission_jobs(_AutomationSettings(), classifier=classifier)
        assert classified["classified"] == 1
        assert conn.execute(
            "SELECT stage,status FROM memory_admission_jobs"
        ).fetchone()["stage"] == "apply"
        applied = process_admission_jobs(_AutomationSettings())
        assert applied["applied"] == 1
        memory = conn.execute(
            "SELECT content,memory_type,evidence_status,source_turn_id "
            "FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()
        assert memory["content"] == "I prefer concise answers"
        assert memory["memory_type"] == "explicit_preference"
        assert memory["evidence_status"] == "explicit"
        assert memory["source_turn_id"] == str(user_turn)
        job = conn.execute("SELECT status,candidate_json,classification_json FROM memory_admission_jobs").fetchone()
        assert job["status"] == "complete"
        assert job["candidate_json"] is None and job["classification_json"] is None
        shadow = conn.execute(
            "SELECT classification_json FROM memory_admission_shadow"
        ).fetchone()
        assert "I prefer concise answers" not in shadow["classification_json"]

    @pytest.mark.asyncio
    async def test_echo_facts_are_filtered_before_durable_classification(
        self, conn, monkeypatch
    ):
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(
            conn, "echo-session", "user", "Hello? I prefer concise answers."
        )
        _add_turn(
            conn, "echo-session", "assistant",
            "Hi Larry, you are in Spartanburg. I have your preferences saved.",
        )
        await tick_once(_AutomationSettings())

        result = process_admission_jobs(
            _AutomationSettings(), extractor=lambda *_: {
                "facts": [
                    {"key": "user.name", "value": "Larry"},
                    {"key": "user.location.home", "value": "Spartanburg"},
                    {"key": "user.preference.concise", "value": "Prefers concise answers"},
                ],
                "observations": [],
            },
        )
        assert result["extracted"] == 1
        job = conn.execute(
            "SELECT stage,candidate_json FROM memory_admission_jobs"
        ).fetchone()
        assert job["stage"] == "classify"
        candidates = json.loads(job["candidate_json"])
        assert candidates == {
            "facts": [{"key": "user.preference.concise", "value": "Prefers concise answers"}],
            "observations": [],
        }
        assert str(user_turn) not in job["candidate_json"]
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0

    @pytest.mark.asyncio
    async def test_shadow_stage_never_admits_candidate_to_live_memory(self, conn, monkeypatch):
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "shadow-session", "user", "I prefer short replies.")
        assistant_turn = _add_turn(conn, "shadow-session", "assistant", "Understood.")
        await tick_once(_ShadowAutomationSettings())

        assert process_admission_jobs(
            _ShadowAutomationSettings(), extractor=lambda *_: {
                "facts": [{"key": "user.preference.response_style",
                           "value": "I prefer short replies"}],
                "observations": [],
            },
        )["extracted"] == 1

        def classifier(candidates, *, policy_version):
            return [Classification(
                key=candidates[0].key, scope=Scope.SUBJECT,
                memory_type=MemoryType.EXPLICIT_PREFERENCE,
                provenance=Provenance.USER,
                evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                evidence=(str(user_turn),), reason_code="explicit",
            )]

        assert process_admission_jobs(
            _ShadowAutomationSettings(), classifier=classifier,
        )["classified"] == 1
        assert process_admission_jobs(_ShadowAutomationSettings())["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_admission_shadow"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT status FROM memory_admission_jobs WHERE assistant_turn_id=?",
            (assistant_turn,),
        ).fetchone()[0] == "complete"

    @pytest.mark.asyncio
    async def test_live_admission_requires_classifier_to_cite_current_user_turn(
        self, conn, monkeypatch
    ):
        monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
        user_turn = _add_turn(conn, "evidence-session", "user", "I prefer concise answers.")
        _add_turn(conn, "evidence-session", "assistant", "Understood.")
        await tick_once(_AutomationSettings())
        process_admission_jobs(
            _AutomationSettings(), extractor=lambda *_: {
                "facts": [{"key": "user.preference.response_style",
                           "value": "I prefer concise answers"}],
                "observations": [],
            },
        )

        def classifier(candidates, *, policy_version):
            return [Classification(
                key=candidates[0].key, scope=Scope.SUBJECT,
                memory_type=MemoryType.EXPLICIT_PREFERENCE,
                provenance=Provenance.USER,
                evidence_status=EvidenceStatus.EXPLICIT, confidence=1.0,
                evidence=(), reason_code="explicit",
            )]

        assert process_admission_jobs(
            _AutomationSettings(), classifier=classifier,
        )["classified"] == 1
        assert process_admission_jobs(_AutomationSettings())["applied"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memories WHERE key='user.preference.response_style'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT status FROM memory_admission_jobs WHERE user_turn_id=?", (user_turn,),
        ).fetchone()[0] == "complete"

    @pytest.mark.asyncio
    async def test_two_sessions_interleaved_both_extract(self, conn):
        _add_turn(conn, "s1", "user", "My name is Larry.")
        _add_turn(conn, "s2", "user", "Call me Lawrence in this session.")
        _add_turn(conn, "s1", "assistant", "Got it, Larry.")
        last_id = _add_turn(conn, "s2", "assistant", "Understood, Lawrence.")

        # Same payload for both -- distinguishing which session produced
        # which write isn't the point here, only that BOTH got processed.
        result = await tick_once(
            _FakeSettings(), client_factory=_factory(_fact_payload("user.name", "Larry"))
        )

        assert result["rows"] == 4
        assert result["exchanges"] == 2
        assert result["cursor"] == last_id

    @pytest.mark.asyncio
    async def test_tool_role_rows_do_not_break_pairing(self, conn):
        _add_turn(conn, "s1", "user", "Check the build status.")
        _add_turn(conn, "s1", "tool", "build: passing")
        reply_id = _add_turn(conn, "s1", "assistant", "The build is passing.")

        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert result["rows"] == 3
        assert result["exchanges"] == 1
        assert result["cursor"] == reply_id

    @pytest.mark.asyncio
    async def test_assistant_row_with_no_pending_user_is_skipped(self, conn):
        # A proactive assistant message (e.g. a reminder firing) with no
        # preceding user turn in this batch -- nothing to pair, nothing
        # to extract, but the row still advances the cursor.
        row_id = _add_turn(conn, "s1", "assistant", "Reminder: call the dentist.")

        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert result["rows"] == 1
        assert result["exchanges"] == 0
        assert result["cursor"] == row_id

    @pytest.mark.asyncio
    async def test_second_user_turn_supersedes_unanswered_first(self, conn):
        _add_turn(conn, "s1", "user", "What's the weather?")
        _add_turn(conn, "s1", "user", "Never mind, what's my calendar look like?")
        reply_id = _add_turn(conn, "s1", "assistant", "You have one meeting today.")

        sent: list[str] = []
        result = await tick_once(
            _FakeSettings(), client_factory=_capturing_factory(_EMPTY_PAYLOAD, sent)
        )

        assert result["exchanges"] == 1  # only one pairing, not two
        assert result["cursor"] == reply_id
        assert len(sent) == 1
        assert "what's my calendar look like" in sent[0]
        assert "What's the weather" not in sent[0]  # the superseded turn
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending"
        ).fetchone()["n"] == 0


# --- tick_once: cross-poll pending-turn tracking -------------------------


class TestPendingAcrossPolls:
    @pytest.mark.asyncio
    async def test_dangling_user_turn_is_recovered_on_a_later_poll(self, conn):
        user_id = _add_turn(conn, "s1", "user", "My name is Larry.")

        first = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        assert first["exchanges"] == 0
        assert first["cursor"] == user_id  # cursor still advances
        pending = conn.execute(
            "SELECT * FROM memory_extraction_pending WHERE session_id='s1'"
        ).fetchone()
        assert pending is not None
        assert pending["user_content"] == "My name is Larry."
        assert pending["user_turn_id"] == user_id

        reply_id = _add_turn(conn, "s1", "assistant", "Noted, Larry.")
        second = await tick_once(
            _FakeSettings(), client_factory=_factory(_fact_payload("user.name", "Larry"))
        )
        assert second["exchanges"] == 1
        assert second["cursor"] == reply_id
        assert (
            conn.execute("SELECT content FROM memories WHERE key='user.name'").fetchone()[
                "content"
            ]
            == "Larry"
        )
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending"
        ).fetchone()["n"] == 0

    @pytest.mark.asyncio
    async def test_stale_pending_row_is_dropped_by_orphan_cleanup(self, conn, monkeypatch):
        # Simulates a sensitive-reply skip (jarvis/bot/transcript_log.py's
        # P2/P6 gate): a user row was persisted, its reply never was, and
        # the pending row is old enough to be considered abandoned.
        monkeypatch.setenv("JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S", "1")
        conn.execute(
            "INSERT INTO memory_extraction_pending "
            "(session_id, user_content, user_turn_id, first_seen_at) "
            "VALUES ('stale-session', 'orphaned question', 1, ?)",
            (_iso_minus(now_iso(), 3600),),  # an hour old
        )
        conn.commit()

        # Cleanup only runs when a tick has new rows to process.
        _add_turn(conn, "s1", "user", "hi")
        _add_turn(conn, "s1", "assistant", "hello")
        await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending WHERE session_id='stale-session'"
        ).fetchone()["n"] == 0

    @pytest.mark.asyncio
    async def test_fresh_pending_row_survives_cleanup(self, conn):
        _add_turn(conn, "s1", "user", "My name is Larry.")
        await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        # A second, unrelated tick with new activity must not sweep away
        # a pending row that isn't actually stale yet.
        _add_turn(conn, "s2", "user", "hi")
        _add_turn(conn, "s2", "assistant", "hello")
        await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))

        assert conn.execute(
            "SELECT COUNT(*) AS n FROM memory_extraction_pending WHERE session_id='s1'"
        ).fetchone()["n"] == 1


# --- tick_once: tick-level failure isolation ------------------------------


class TestTickFailureIsolation:
    @pytest.mark.asyncio
    async def test_bad_tick_is_caught_and_reported_without_exception_content(
        self, conn, monkeypatch, caplog
    ):
        import jarvis.memory_extraction_worker as worker_mod

        def _boom(_rows):
            raise RuntimeError("WORKER_CANARY_61BE /tmp/private/conversation.db")

        monkeypatch.setattr(worker_mod, "_group_by_session", _boom)
        _add_turn(conn, "s1", "user", "hi")

        result = await tick_once(_FakeSettings(), client_factory=_factory(_EMPTY_PAYLOAD))
        assert result["error"] is True
        assert result["exchanges"] == 0
        assert "memory_extraction_tick_failed" in caplog.text
        assert "RuntimeError" in caplog.text
        assert "WORKER_CANARY_61BE" not in caplog.text
        assert "/tmp/private/conversation.db" not in caplog.text


# --- _iso_minus ------------------------------------------------------------


class TestIsoMinus:
    def test_subtracts_seconds(self):
        before = _iso_minus("2026-09-02T12:00:00+00:00", 60)
        assert before == "2026-09-02T11:59:00+00:00"


@pytest.mark.parametrize(
    ("setting", "reader"),
    [
        ("JARVIS_MEMORY_EXTRACTION_POLL_INTERVAL_S", "_poll_interval_s"),
        ("JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S", "_orphan_timeout_s"),
    ],
)
def test_invalid_worker_setting_log_omits_raw_value(setting, reader, monkeypatch, caplog):
    secret_like_value = "CONFIG_CANARY_29D0 /private/user/settings"
    monkeypatch.setenv(setting, secret_like_value)
    getattr(memory_extraction_worker, reader)()
    assert "invalid " + setting in caplog.text
    assert secret_like_value not in caplog.text
    assert "/private/user/settings" not in caplog.text
