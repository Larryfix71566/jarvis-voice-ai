"""B5/M0-M5 acceptance fixtures for the automated-memory contract."""
import json
from pathlib import Path
import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.memory import retrieve_automated_memory_context
from jarvis.memory_automation import (
    Candidate, Classification, EvidenceStatus, MemoryType, Provenance, Scope,
    apply_scoped_correction, bounded_candidates, classify_threshold,
    enqueue_maintenance, heuristic_classifier, maintenance_budget_remaining,
    normalize_rollout_stage, process_classification_jobs, RolloutStage,
)
from jarvis.memory_automation_eval import (
    PROVIDER_CLASSIFIER_SYSTEM_PROMPT, ProviderClassifier, evaluate_memory_cases, measure_shadow,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "memory_automation_cases.json"


def test_acceptance_fixture_is_versioned_and_complete():
    payload = json.loads(FIXTURE.read_text())
    assert payload["version"] == "memory-automation-b1"
    assert len(payload["cases"]) == 8


def test_offline_benchmark_has_a_zero_regression_receipt():
    payload = json.loads(FIXTURE.read_text())
    receipt = evaluate_memory_cases(payload["cases"])
    assert receipt.passed
    assert receipt.total_cases == 8
    assert receipt.passed_cases == 8
    assert receipt.privacy_regressions == 0


def test_provider_prompt_locks_contract_enums_and_strict_json():
    prompt = PROVIDER_CLASSIFIER_SYSTEM_PROMPT
    for value in ("explicit_preference", "temporary_context", "quoted_document",
                  "insufficient_evidence", "strict\nJSON"):
        assert value in prompt
    assert "do not use synonyms" in prompt


def test_shadow_measurement_uses_one_frozen_corpus_and_reports_deltas():
    payload = json.loads(FIXTURE.read_text())
    measurement = measure_shadow(payload["cases"],
                                 baseline_classifier=heuristic_classifier,
                                 candidate_classifier=heuristic_classifier)
    assert measurement.no_regression
    assert measurement.baseline.total_cases == measurement.candidate.total_cases == 8
    assert measurement.baseline_ms >= 0 and measurement.candidate_ms >= 0


@pytest.mark.parametrize("temperature", [0, None])
def test_provider_classifier_validates_order_and_records_bounded_usage(temperature):
    class Usage:
        prompt_tokens = 11
        completion_tokens = 7
        total_tokens = 18

    class Message:
        content = '[{"key":"user.units","scope":"global","memory_type":"explicit_preference",' \
                  '"provenance":"user","evidence_status":"explicit","confidence":1.0,' \
                  '"evidence":["turn-1"],"reason_code":"explicit"}]'

    class Response:
        choices = [type("Choice", (), {"message": Message()})()]
        usage = Usage()

    class Completions:
        def create(self, **kwargs):
            assert kwargs.get("temperature") == temperature
            assert ("temperature" in kwargs) == (temperature is not None)
            assert kwargs["max_tokens"] == 2000
            assert "user.units" in kwargs["messages"][1]["content"]
            return Response()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    provider = ProviderClassifier(client, model="shadow-test", temperature=temperature)
    result = provider([Candidate("user.units", "I prefer metric units", ("turn-1",), ("s1",))])
    assert result[0].memory_type is MemoryType.EXPLICIT_PREFERENCE
    assert provider.usage() == {
        "calls": 1, "prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
    }


def test_explicit_preference_is_immediate_and_replay_is_idempotent():
    result = heuristic_classifier([
        Candidate("user.units", "I prefer metric units", ("turn-1",), ("session-1",))
    ])[0]
    assert result.memory_type is MemoryType.EXPLICIT_PREFERENCE
    assert result.evidence_status is EvidenceStatus.EXPLICIT
    assert len(bounded_candidates([Candidate("user.units", "I prefer metric units", ("turn-1",), ("session-1",))] * 2)) == 2


def test_model_json_boundary_decodes_only_the_locked_shape():
    payload = {
        "key": "user.units", "scope": "global", "memory_type": "fact",
        "provenance": "user", "evidence_status": "explicit",
        "confidence": 1.0, "evidence": ["turn-1"],
        "reason_code": "explicit",
    }
    assert Classification.from_dict(payload).key == "user.units"
    payload["unexpected"] = "reject"
    try:
        Classification.from_dict(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown classifier fields must fail closed")


def test_model_json_boundary_rejects_nonfinite_or_string_confidence():
    base = {
        "key": "user.units", "scope": "global", "memory_type": "fact",
        "provenance": "user", "evidence_status": "explicit",
        "confidence": 1.0, "evidence": ["turn-1"], "reason_code": "explicit",
    }
    for value in (float("nan"), float("inf"), "1.0", True):
        with pytest.raises(ValueError):
            Classification.from_dict({**base, "confidence": value})


def test_inference_needs_independent_sessions_and_unknown_is_quiet():
    assert classify_threshold(explicit=False, independent_sessions=1, confidence=.95) is EvidenceStatus.TENTATIVE
    assert classify_threshold(explicit=False, independent_sessions=2, confidence=.80) is EvidenceStatus.CORROBORATED
    uncertain = heuristic_classifier([
        Candidate("user.theme", "Maybe I prefer dark mode", ("turn-1",), ("s1",))
    ])[0]
    assert uncertain.evidence_status is EvidenceStatus.TENTATIVE
    assert uncertain.reason_code == "insufficient_evidence"


def test_scoped_correction_retains_reversible_history(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    old = conn.execute(
        "INSERT INTO memories(kind,key,content,source_session_id,created_at,updated_at,user_id) VALUES ('fact','user.location','Home: Greenville','s1','2026-01-01','2026-01-01','local')"
    ).lastrowid
    correction = Classification("user.location", Scope.GLOBAL, MemoryType.FACT,
                                Provenance.USER, EvidenceStatus.EXPLICIT, 1.0,
                                ("turn-2",), "explicit")
    new = apply_scoped_correction(conn, memory_id=old, content="Home: Charleston",
                                  source_session_id="s2", classification=correction,
                                  now_iso="2026-02-01T00:00:00Z")
    rows = conn.execute("SELECT content,archived_at,supersedes_id FROM memories WHERE key='user.location' ORDER BY id").fetchall()
    assert new != old and rows[0]["archived_at"] and rows[1]["supersedes_id"] == old


def test_processor_accepts_provider_json_and_applies_metadata(tmp_path, monkeypatch):
    from jarvis.memory import upsert_fact
    from jarvis.memory_automation import enqueue_maintenance, process_classification_jobs
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "true")
    upsert_fact(conn, "user.units", "metric", "s1")

    def classifier(items, *, policy_version):
        return [{"key": items[0].key, "scope": "global", "memory_type": "fact",
                 "provenance": "user", "evidence_status": "explicit",
                 "confidence": 1.0, "evidence": ["turn-1"],
                 "reason_code": "explicit"}]

    from jarvis.db import now_iso
    result = process_classification_jobs(conn, now_iso=now_iso(), classifier=classifier)
    assert result == {"claimed": 1, "applied": 1, "failed": 0}
    assert conn.execute("SELECT evidence_status FROM memories WHERE key='user.units'").fetchone()[0] == "explicit"


def test_processor_enforces_assistant_source_attribution(tmp_path):
    from jarvis.memory_automation import enqueue_maintenance, process_classification_jobs
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    memory_id = conn.execute(
        "INSERT INTO memories(kind,key,content,source_session_id,created_at,updated_at,user_id,provenance) "
        "VALUES ('fact','assistant.claim','I can always do this','s1',?,?, 'local','assistant')",
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    ).lastrowid
    enqueue_maintenance(conn, memory_id=memory_id, revision=1, policy_version="b1",
                        operation="classify", now_iso="2026-01-01T00:00:00Z")

    def classifier(items, *, policy_version):
        return [Classification(items[0].key, Scope.GLOBAL, MemoryType.EXPLICIT_PREFERENCE,
                               Provenance.USER, EvidenceStatus.EXPLICIT, 1.0, (), "explicit")]

    result = process_classification_jobs(conn, now_iso="2026-01-01T00:01:00Z", classifier=classifier)
    assert result == {"claimed": 1, "applied": 1, "failed": 0}
    row = conn.execute("SELECT provenance,evidence_status,confidence FROM memories WHERE id=?", (memory_id,)).fetchone()
    assert row["provenance"] == "assistant"
    assert row["evidence_status"] == "unknown" and row["confidence"] == 0.0


def test_processor_folds_recall_ledger_sessions_into_classifier_evidence(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    memory_id = conn.execute(
        "INSERT INTO memories(kind,key,content,source_session_id,source_turn_id,"
        "created_at,updated_at,user_id) VALUES ('fact','user.units','metric',"
        "'session-new','turn-new',?,?, 'local')",
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    ).lastrowid
    conn.execute(
        "INSERT INTO memory_recall_events(session_id,source_turn,key,outcome,created_at,user_id) "
        "VALUES (?,?,?,?,?,?)",
        ("session-old", 12, "user.units", "exact_update", "2026-01-02T00:00:00Z", "local"),
    )
    enqueue_maintenance(conn, memory_id=memory_id, revision=1, policy_version="b1",
                        operation="classify", now_iso="2026-01-03T00:00:00Z")
    seen = []

    def classifier(items, *, policy_version):
        seen.append(items[0])
        return [Classification(items[0].key, Scope.GLOBAL, MemoryType.FACT,
                               Provenance.USER, EvidenceStatus.CORROBORATED, 0.8,
                               items[0].source_turn_ids, "repeat_independent")]

    result = process_classification_jobs(conn, now_iso="2026-01-03T00:01:00Z",
                                         classifier=classifier)
    assert result == {"claimed": 1, "applied": 1, "failed": 0}
    assert seen[0].session_ids == ("session-new", "session-old")
    assert seen[0].source_turn_ids == ("turn-new", "12")


def test_classifier_redaction_never_rewrites_stored_content(tmp_path, monkeypatch):
    """Provider safety redaction is a transport boundary, not a memory edit."""
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    monkeypatch.setenv("JARVIS_MEMORY_AUTOMATION_ENABLED", "false")
    memory_id = conn.execute(
        "INSERT INTO memories(kind,key,content,source_session_id,created_at,updated_at,user_id) "
        "VALUES ('fact','project.token_note','api_key=super-secret','s1',?,?, 'local')",
        ("2026-09-17T11:00:00Z", "2026-09-17T11:00:00Z"),
    ).lastrowid
    enqueue_maintenance(conn, memory_id=memory_id, revision=1, policy_version="b1",
                        operation="classify", now_iso="2026-09-17T11:00:00Z")

    def classifier(items, *, policy_version):
        # The classifier only sees the redacted candidate.
        assert "super-secret" not in items[0].content
        return [Classification(items[0].key, Scope.PROJECT, MemoryType.FACT,
                               Provenance.USER, EvidenceStatus.EXPLICIT, 1.0,
                               ("turn-1",), "explicit")]

    now = "2026-09-17T12:00:00Z"
    result = process_classification_jobs(conn, now_iso=now, classifier=classifier)
    assert result == {"claimed": 1, "applied": 1, "failed": 0}
    row = conn.execute("SELECT content, scope FROM memories WHERE key='project.token_note'").fetchone()
    assert row["content"] == "api_key=super-secret"
    assert row["scope"] == "project"


def test_shadow_processing_never_changes_live_memory_metadata(tmp_path):
    """B6 shadow mode is observational: the live row remains byte-for-byte stable."""
    from jarvis.memory import upsert_fact
    from jarvis.memory_automation import process_classification_jobs
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    upsert_fact(conn, "user.units", "metric", "s1")
    before = dict(conn.execute(
        "SELECT content,scope,memory_type,provenance,evidence_status,confidence,updated_at "
        "FROM memories WHERE key='user.units'"
    ).fetchone())
    memory_id = conn.execute("SELECT id FROM memories WHERE key='user.units'").fetchone()[0]
    # A process-wide test environment may have enabled admission automation
    # for an earlier case; isolate this shadow receipt to the job we enqueue.
    conn.execute("DELETE FROM memory_maintenance")
    enqueue_maintenance(conn, memory_id=memory_id, revision=1, policy_version="b1",
                        operation="classify", now_iso="2026-09-17T11:59:00Z")

    def classifier(items, *, policy_version):
        return [{"key": items[0].key, "scope": "project", "memory_type": "decision",
                 "provenance": "assistant", "evidence_status": "disputed",
                 "confidence": 0.1, "evidence": ["shadow-turn"],
                 "reason_code": "insufficient_evidence"}]

    result = process_classification_jobs(conn, now_iso="2026-09-17T12:00:00Z",
                                         classifier=classifier, shadow=True)
    after = dict(conn.execute(
        "SELECT content,scope,memory_type,provenance,evidence_status,confidence,updated_at "
        "FROM memories WHERE key='user.units'"
    ).fetchone())
    assert result == {"claimed": 1, "applied": 1, "failed": 0}
    assert after == before
    assert conn.execute("SELECT status FROM memory_maintenance").fetchone()[0] == "done"
    shadow = conn.execute(
        "SELECT memory_id,content_revision,policy_version,candidate_digest,classification_json "
        "FROM memory_classification_shadow"
    ).fetchone()
    assert shadow["memory_id"] == memory_id
    assert shadow["content_revision"] == 1
    assert shadow["policy_version"] == "b1"
    assert len(shadow["candidate_digest"]) == 64
    assert "metric" not in shadow["classification_json"]
    assert "shadow-turn" not in shadow["classification_json"]


def test_retrieval_filters_expired_disputed_and_unrelated(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    conn.executemany(
        "INSERT INTO memories(kind,key,content,created_at,updated_at,user_id,evidence_status,valid_until) VALUES ('fact',?,?,?,?,?,?,?)",
        [
            ("user.units", "metric units", "2026-01-01", "2026-01-01", "local", "explicit", None),
            ("project.secret", "unrelated project", "2026-01-01", "2026-01-01", "local", "explicit", None),
            ("user.old", "expired units", "2026-01-01", "2026-01-01", "local", "explicit", "2000-01-01T00:00:00Z"),
            ("user.disputed", "metric dispute", "2026-01-01", "2026-01-01", "local", "disputed", None),
        ],
    )
    found = retrieve_automated_memory_context(conn, "units", session_id="s2", source_turn=4)
    assert len(found) == 1 and found[0]["content"] == "metric units"
    event = conn.execute("SELECT outcome,session_id,source_turn FROM memory_recall_events").fetchone()
    assert event["outcome"] == "used_for" and event["session_id"] == "s2" and event["source_turn"] == 4


def test_daily_budget_is_durable(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    for i in range(3):
        enqueue_maintenance(conn, memory_id=i + 1, revision=1, policy_version="b1",
                            operation="classify", now_iso=f"2026-03-01T00:0{i}:00Z")
    budget = maintenance_budget_remaining(conn, day="2026-03-01")
    assert budget["candidates_used"] == 3 and budget["calls_used"] == 3
    assert budget["candidates_remaining"] == 97 and budget["calls_remaining"] == 2


def test_classifier_worker_does_not_claim_after_daily_call_budget(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    # Five prior classify jobs consume the complete daily model-call budget.
    for i in range(5):
        enqueue_maintenance(conn, memory_id=i + 1, revision=1,
                            policy_version="b1", operation="classify",
                            now_iso=f"2026-03-02T00:0{i}:00Z")
    calls = []
    result = process_classification_jobs(
        conn, now_iso="2026-03-02T01:00:00Z",
        classifier=lambda *_args, **_kwargs: calls.append(1), shadow=True,
    )
    assert result == {"claimed": 0, "applied": 0, "failed": 0}
    assert calls == []
    assert conn.execute("SELECT COUNT(*) FROM memory_maintenance WHERE status='queued'").fetchone()[0] == 5


def test_staged_rollout_admits_only_explicit_preferences_then_corroborated(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    rows = []
    for key, content in (("user.preference.units", "metric"),
                         ("project.rule", "use the compact layout")):
        row = conn.execute(
            "INSERT INTO memories(kind,key,content,created_at,updated_at,user_id) "
            "VALUES ('fact',?,?,?,?,?)",
            (key, content, "2026-01-01", "2026-01-01", "local"),
        )
        rows.append(int(row.lastrowid))
    for memory_id in rows:
        enqueue_maintenance(conn, memory_id=memory_id, revision=1,
                            policy_version="b1", operation="classify",
                            now_iso="2026-01-01T00:00:00Z")

    def classifier(items, *, policy_version):
        return [Classification(
            item.key,
            Scope.GLOBAL if item.key.startswith("user.") else Scope.PROJECT,
            MemoryType.EXPLICIT_PREFERENCE if item.key.startswith("user.") else MemoryType.TASK_RULE,
            Provenance.USER,
            EvidenceStatus.EXPLICIT if item.key.startswith("user.") else EvidenceStatus.TENTATIVE,
            1.0 if item.key.startswith("user.") else 0.6,
            item.source_turn_ids,
            "explicit" if item.key.startswith("user.") else "insufficient_evidence",
        ) for item in items]

    result = process_classification_jobs(
        conn, now_iso="2026-01-01T00:01:00Z", classifier=classifier,
        rollout_stage=RolloutStage.EXPLICIT_PREFERENCES,
    )
    assert result == {"claimed": 2, "applied": 2, "failed": 0}
    rows_after = conn.execute(
        "SELECT key, memory_type, evidence_status FROM memories ORDER BY id"
    ).fetchall()
    assert rows_after[0]["memory_type"] == "explicit_preference"
    assert rows_after[0]["evidence_status"] == "explicit"
    # The tentative task rule is complete in the shadow ledger, but does not
    # become live metadata before the final corroboration stage.
    assert rows_after[1]["memory_type"] == "fact"
    assert rows_after[1]["evidence_status"] == "unknown"
    shadow = conn.execute(
        "SELECT classification_json FROM memory_classification_shadow "
        "WHERE memory_id=?", (rows[1],)
    ).fetchone()
    assert shadow is not None and '"rollout_stage":"explicit_preferences"' in shadow[0]


def test_rollout_stage_decoder_fails_closed():
    assert normalize_rollout_stage("shadow") is RolloutStage.SHADOW
    assert normalize_rollout_stage("corroborated_inferences") is RolloutStage.CORROBORATED_INFERENCES
    with pytest.raises(ValueError):
        normalize_rollout_stage("all_at_once")


def test_missing_memory_job_is_reported_as_failed_without_retry_mutation(tmp_path):
    conn = get_conn(tmp_path / "memory.db")
    run_migrations(conn)
    enqueue_maintenance(conn, memory_id=9999, revision=1, policy_version="b1",
                        operation="classify", now_iso="2026-03-03T00:00:00Z")
    calls = []
    result = process_classification_jobs(
        conn, now_iso="2026-03-03T00:01:00Z",
        classifier=lambda items, **_: calls.append(items) or [],
    )
    assert result == {"claimed": 1, "applied": 0, "failed": 1}
    row = conn.execute("SELECT status, attempts, last_error_code FROM memory_maintenance").fetchone()
    assert row["status"] == "queued" and row["attempts"] == 1
    assert row["last_error_code"] == "missing_memory"


def test_shadow_cli_requires_explicit_route_and_dry_run_never_loads_secrets(monkeypatch, capsys):
    import runpy
    import sys
    script = Path(__file__).parents[2] / "scripts/run_memory_provider_shadow.py"
    module = runpy.run_path(str(script))
    main = module["main"]
    def forbidden():
        pytest.fail("dry-run must not open credentials")
    monkeypatch.setitem(main.__globals__, "inject_env", forbidden)
    monkeypatch.setenv("OPENAI_MODEL", "supervisor-only")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://wrong.example/v1")
    monkeypatch.setattr(sys, "argv", [str(script), "--dry-run"])
    with pytest.raises(SystemExit) as missing:
        main()
    assert missing.value.code == 2
    monkeypatch.setattr(sys, "argv", [str(script), "--profile", "kimi-k3", "--dry-run"])
    assert main() == 0
    route = json.loads(capsys.readouterr().out)
    assert route["provider"] == "moonshot"
    assert route["api_key_env"] == "MOONSHOT_API_KEY"
    assert route["model"] != "supervisor-only"
    assert route["base_url"] != "https://wrong.example/v1"
    assert route["provider_called"] is False
    monkeypatch.setattr(sys, "argv", [str(script), "--profile", "missing", "--dry-run"])
    with pytest.raises(SystemExit) as unknown:
        main()
    assert unknown.value.code == 2
