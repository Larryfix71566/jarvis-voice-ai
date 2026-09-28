from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jarvis import skill_step_checks
from jarvis.db import get_conn, run_migrations
from jarvis.runlog.prune import prune
from jarvis.runlog.store import RunLogger, get_skill_events
from jarvis.skill_step_checks import (
    RECEIPT_ISSUER,
    SkillStepCheckReceipt,
    SkillStepReceiptError,
    issue_host_controller_receipt,
    load_required_check_ids,
    validate_skill_step_receipt,
)

REVISION = "a" * 64
EXPECTED = {
    "user_id": "local",
    "run_id": "run-123",
    "request_id": "run-123",
    "skill_id": "sample-skill",
    "skill_revision": REVISION,
    "step_id": "verify-output",
    "attempt_id": "tool-call-1",
}
_DEFAULT_POLICY = skill_step_checks.SKILL_STEP_CHECKS_CONFIG
_DEFAULT_HOST_CHECKS = dict(skill_step_checks.HOST_CHECKS)
WEATHER_REVISION = "9064f3d61d680d8cbce9c4dda1b2d98b854624fce2b106f89cc7f13b4ace521e"
GIT_REVIEW_REVISION = "8794a16e69d4908ff12906e93b8b5cc01d0560c8c792d0ab43279c41ac1a5c7e"


@pytest.fixture(autouse=True)
def host_check_environment(tmp_path, monkeypatch):
    check_ids = ("artifact.exists", "artifact.matches_revision")
    policy_path = tmp_path / "host-check-policy.yaml"
    policy_path.write_text(policy(list(check_ids)), encoding="utf-8")
    monkeypatch.setattr(skill_step_checks, "SKILL_STEP_CHECKS_CONFIG", policy_path)
    monkeypatch.setattr(skill_step_checks, "HOST_CHECKS", {
        **_DEFAULT_HOST_CHECKS,
        check_ids[0]: lambda context: context.get("exists") is True,
        check_ids[1]: lambda context: context.get("revision_matches") is True,
    })


def policy(check_ids: list[str]) -> str:
    import yaml
    data = {
        "schema_version": 1,
        "required_checks": [{
            "skill_id": EXPECTED["skill_id"],
            "skill_revision": REVISION,
            "step_id": EXPECTED["step_id"],
            "check_ids": check_ids,
        }],
    }
    return yaml.safe_dump(data, sort_keys=False)


def raw_receipt(now: datetime, *, context=None) -> dict:
    fields = {
        "schema_version": 1,
        "receipt_id": str(uuid.uuid4()),
        "issuer": RECEIPT_ISSUER,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
        **EXPECTED,
    }
    return issue_host_controller_receipt(fields, context=context or {
        "exists": True, "revision_matches": True,
    })


def test_empty_default_policy_does_not_trust_natural_language_criteria():
    assert load_required_check_ids(
        "technical-plan-document", REVISION, "establish-scope",
        path=_DEFAULT_POLICY,
    ) == ()


def _weather_result():
    return {
        "city": "Camp Croft, United States",
        "requested_city": "Camp Croft",
        "source": "open-meteo",
        "units": "imperial",
        "current": {
            "temperature_f": 70.0, "temperature_c": 21.1,
            "condition": "Clear", "humidity_percent": 45, "wind_kph": 4,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        },
        "daily": [{
            "date": "2026-09-28", "max_f": 75.0, "min_f": 60.0,
            "max_c": 23.9, "min_c": 15.6, "precip_probability": 10,
            "condition": "Clear",
        }],
        "human": "In Camp Croft, United States it is currently 70°F and Clear.",
    }


def test_weather_host_check_is_pinned_and_requires_complete_current_forecast():
    check_id = "weather.current_and_forecast_returned"
    assert load_required_check_ids(
        "current-weather-with-fahrenheit", WEATHER_REVISION, "retrieve-conditions",
        path=_DEFAULT_POLICY,
    ) == (check_id,)
    assert load_required_check_ids(
        "current-weather-with-fahrenheit", "b" * 64, "retrieve-conditions",
        path=_DEFAULT_POLICY,
    ) == ()
    checker = _DEFAULT_HOST_CHECKS[check_id]
    context = {
        "tool_name": "get_weather",
        "arguments": {"city": "Camp Croft", "days": 1},
        "result": json.dumps(_weather_result()),
    }
    assert checker(context) is True

    wrong_query = _weather_result()
    wrong_query["requested_city"] = "Somewhere Else"
    assert checker({**context, "result": json.dumps(wrong_query)}) is False

    short_forecast = _weather_result()
    assert checker({**context, "arguments": {"city": "Camp Croft", "days": 2},
                    "result": json.dumps(short_forecast)}) is False

    stale = _weather_result()
    stale["current"]["observed_at"] = "2000-01-01T00:00:00Z"
    assert checker({**context, "result": json.dumps(stale)}) is False

    forecast_fallback = _weather_result()
    forecast_fallback["source"] = "weather.gov-forecast"
    assert checker({**context, "result": json.dumps(forecast_fallback)}) is False

    incoherent = _weather_result()
    incoherent["current"]["temperature_f"] = 100
    assert checker({**context, "result": json.dumps(incoherent)}) is False

    inverted = _weather_result()
    inverted["daily"][0]["min_f"] = 80
    assert checker({**context, "result": json.dumps(inverted)}) is False

    missing_forecast = _weather_result()
    missing_forecast["daily"] = []
    assert checker({**context, "result": json.dumps(missing_forecast)}) is False
    assert checker({**context, "result": json.dumps({"error": "lookup failed"})}) is False
    assert checker({**context, "tool_name": "unrelated_tool"}) is False


def test_git_status_host_check_is_pinned_and_rejects_inconsistent_state():
    check_id = "repository.status_observed"
    assert load_required_check_ids(
        "git-history-and-status-review", GIT_REVIEW_REVISION,
        "inspect-repository", path=_DEFAULT_POLICY,
    ) == (check_id,)
    assert load_required_check_ids(
        "git-history-and-status-review", "c" * 64,
        "inspect-repository", path=_DEFAULT_POLICY,
    ) == ()
    checker = _DEFAULT_HOST_CHECKS[check_id]
    result = {
        "repository": "/workspace/project",
        "branch": "main",
        "upstream": "origin/main",
        "clean": False,
        "changed_files": ["src/main.py"],
        "ahead": 1,
        "behind": 0,
    }
    context = {
        "tool_name": "git_status", "arguments": {},
        "result": json.dumps(result),
    }
    assert checker(context) is True

    inconsistent = {**result, "clean": True}
    assert checker({**context, "result": json.dumps(inconsistent)}) is False
    missing_upstream = {**result, "upstream": ""}
    assert checker({**context, "result": json.dumps(missing_upstream)}) is False
    nonabsolute_repository = {**result, "repository": "project"}
    assert checker({**context, "result": json.dumps(nonabsolute_repository)}) is False
    assert checker({**context, "tool_name": "git_log"}) is False


def test_git_history_host_check_is_pinned_and_bounded_to_verified_commits():
    check_id = "repository.history_observed"
    assert load_required_check_ids(
        "git-history-and-status-review", GIT_REVIEW_REVISION,
        "inspect-history", path=_DEFAULT_POLICY,
    ) == (check_id,)
    assert load_required_check_ids(
        "git-history-and-status-review", "d" * 64,
        "inspect-history", path=_DEFAULT_POLICY,
    ) == ()
    checker = _DEFAULT_HOST_CHECKS[check_id]
    record = {
        "sha": "a" * 40, "date": "2026-09-28T12:30:00+00:00",
        "subject": "Add validated history inspection",
    }
    context = {
        "tool_name": "git_log", "arguments": {"n": 1},
        "result": json.dumps({
            "commits": [f"{'a' * 7} {record['date']} {record['subject']}"],
            "commit_records": [record],
        }),
    }
    assert checker(context) is True

    changed_human_row = json.loads(context["result"])
    changed_human_row["commits"][0] = "b" * 7 + " forged row"
    assert checker({**context, "result": json.dumps(changed_human_row)}) is False
    assert checker({**context, "arguments": {"n": 0}}) is False
    assert checker({**context, "result": json.dumps({"error": "git unavailable"})}) is False


def test_git_status_receipt_passes_without_persisting_repository_path(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_step_checks, "SKILL_STEP_CHECKS_CONFIG", _DEFAULT_POLICY)
    monkeypatch.setattr(skill_step_checks, "HOST_CHECKS", _DEFAULT_HOST_CHECKS)
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    runlog = RunLogger(
        "git-status-run", "developer", "Developer", "review local status",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("git-history-and-status-review", GIT_REVIEW_REVISION,
                       "skill_selected")
    runlog.skill_event(
        "git-history-and-status-review", GIT_REVIEW_REVISION,
        "skill_step_started", step_id="inspect-repository",
        attempt_id="call-git-status-1", status="running",
    )
    repository_path = "/Users/example/private/project"
    context = {
        "tool_name": "git_status", "arguments": {},
        "result": json.dumps({
            "repository": repository_path, "branch": "main",
            "upstream": "origin/main", "clean": False,
            "changed_files": ["src/app.py"], "ahead": 0, "behind": 1,
        }),
    }

    assert skill_step_checks.record_verified_tool_step(
        runlog, skill_id="git-history-and-status-review",
        skill_revision=GIT_REVIEW_REVISION, step_id="inspect-repository",
        attempt_id="call-git-status-1", context=context,
    ) is True
    page = get_skill_events("git-status-run", db_path=db_path)
    finished = [event for event in page["events"]
                if event["type"] == "skill_step_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "passed"
    assert finished[0]["evidence_refs"][0]["kind"] == "check_receipt_id"
    assert repository_path not in json.dumps(page)


def test_weather_tool_result_receipt_persists_pass_without_weather_content(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_step_checks, "SKILL_STEP_CHECKS_CONFIG", _DEFAULT_POLICY)
    monkeypatch.setattr(skill_step_checks, "HOST_CHECKS", _DEFAULT_HOST_CHECKS)
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    runlog = RunLogger(
        "weather-run", "developer", "Developer", "weather request",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("current-weather-with-fahrenheit", WEATHER_REVISION,
                       "skill_selected")
    runlog.skill_event(
        "current-weather-with-fahrenheit", WEATHER_REVISION,
        "skill_step_started", step_id="retrieve-conditions",
        attempt_id="call-weather-1", status="running",
    )
    context = {
        "tool_name": "get_weather",
        "arguments": {"city": "Camp Croft", "days": 1},
        "result": json.dumps(_weather_result()),
    }
    assert skill_step_checks.record_verified_tool_step(
        runlog, skill_id="current-weather-with-fahrenheit",
        skill_revision=WEATHER_REVISION, step_id="retrieve-conditions",
        attempt_id="call-weather-1", context=context,
    ) is True
    page = get_skill_events("weather-run", db_path=db_path)
    finished = [event for event in page["events"]
                if event["type"] == "skill_step_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "passed"
    assert finished[0]["evidence_refs"][0]["kind"] == "check_receipt_id"
    assert "Camp Croft" not in json.dumps(page)
    conn = get_conn(db_path)
    try:
        receipt_row = conn.execute(
            "SELECT receipt_sha256 FROM skill_step_check_receipts WHERE run_id=?",
            ("weather-run",),
        ).fetchone()
        assert receipt_row is not None
        assert "Camp Croft" not in str(receipt_row["receipt_sha256"])
    finally:
        conn.close()


def test_weather_host_check_failure_never_issues_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_step_checks, "SKILL_STEP_CHECKS_CONFIG", _DEFAULT_POLICY)
    monkeypatch.setattr(skill_step_checks, "HOST_CHECKS", _DEFAULT_HOST_CHECKS)
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    runlog = RunLogger(
        "weather-run", "developer", "Developer", "weather request",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("current-weather-with-fahrenheit", WEATHER_REVISION,
                       "skill_selected")
    runlog.skill_event(
        "current-weather-with-fahrenheit", WEATHER_REVISION,
        "skill_step_started", step_id="retrieve-conditions",
        attempt_id="call-weather-2", status="running",
    )
    incomplete = _weather_result()
    incomplete["daily"] = []
    accepted = skill_step_checks.record_verified_tool_step(
        runlog, skill_id="current-weather-with-fahrenheit",
        skill_revision=WEATHER_REVISION, step_id="retrieve-conditions",
        attempt_id="call-weather-2", context={
            "tool_name": "get_weather", "arguments": {"city": "Camp Croft"},
            "result": json.dumps(incomplete),
        },
    )
    assert accepted is False
    runlog.skill_event(
        "current-weather-with-fahrenheit", WEATHER_REVISION,
        "skill_step_finished", step_id="retrieve-conditions",
        attempt_id="call-weather-2", status="unknown",
    )
    page = get_skill_events("weather-run", db_path=db_path)
    finished = [event for event in page["events"]
                if event["type"] == "skill_step_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "unknown"


def test_mapping_is_exactly_bound_to_revision_step_and_check_set(tmp_path):
    path = tmp_path / "checks.yaml"
    path.write_text(policy(["artifact.exists", "artifact.matches_revision"]), encoding="utf-8")
    ids = load_required_check_ids(
        EXPECTED["skill_id"], REVISION, EXPECTED["step_id"], path=path,
    )
    assert ids == ("artifact.exists", "artifact.matches_revision")
    assert load_required_check_ids(
        EXPECTED["skill_id"], "b" * 64, EXPECTED["step_id"], path=path,
    ) == ()


def test_duplicate_yaml_policy_keys_fail_closed(tmp_path):
    path = tmp_path / "checks.yaml"
    path.write_text(
        "schema_version: 1\nschema_version: 1\nrequired_checks: []\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillStepReceiptError, match="duplicate_check_policy_key"):
        load_required_check_ids("sample-skill", REVISION, "verify-output", path=path)


def test_policy_schema_version_requires_json_integer(tmp_path):
    path = tmp_path / "checks.yaml"
    path.write_text("schema_version: true\nrequired_checks: []\n", encoding="utf-8")
    with pytest.raises(SkillStepReceiptError, match="invalid_check_policy"):
        load_required_check_ids("sample-skill", REVISION, "verify-output", path=path)


def test_valid_receipt_must_match_all_identity_and_required_checks():
    now = datetime.now(timezone.utc)
    receipt = SkillStepCheckReceipt.from_mapping(raw_receipt(now))
    validate_skill_step_receipt(
        receipt, expected=EXPECTED,
        required_check_ids=("artifact.exists", "artifact.matches_revision"), now=now,
    )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda data: data.update(issuer="model"), "invalid_receipt_issuer"),
        (lambda data: data.update(attempt_id="wrong-attempt"), "receipt_signature_invalid"),
        (lambda data: data.update(expires_at="2020-01-01T00:00:00Z"), "receipt_signature_invalid"),
        (lambda data: data["outcomes"].reverse(), "receipt_signature_invalid"),
    ],
)
def test_invalid_receipts_fail_closed(mutate, reason):
    now = datetime.now(timezone.utc)
    data = raw_receipt(now)
    mutate(data)
    with pytest.raises(SkillStepReceiptError, match=reason):
        receipt = SkillStepCheckReceipt.from_mapping(data)
        validate_skill_step_receipt(
            receipt, expected=EXPECTED,
            required_check_ids=("artifact.exists", "artifact.matches_revision"), now=now,
        )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("schema_version", True, "unsupported_receipt_schema"),
        ("issued_at", 1, "invalid_receipt_time"),
        ("expires_at", None, "invalid_receipt_time"),
    ],
)
def test_receipt_envelope_rejects_python_coercions_and_malformed_time(
    field, value, reason,
):
    data = raw_receipt(datetime.now(timezone.utc))
    data[field] = value
    with pytest.raises(SkillStepReceiptError, match=reason):
        SkillStepCheckReceipt.from_mapping(data)


def test_receipt_validation_rejects_malformed_expected_identity_and_checks():
    now = datetime.now(timezone.utc)
    receipt = SkillStepCheckReceipt.from_mapping(raw_receipt(now))
    with pytest.raises(SkillStepReceiptError, match="invalid_expected_identity"):
        validate_skill_step_receipt(
            receipt, expected={**EXPECTED, "attempt_id": 4},
            required_check_ids=("artifact.exists", "artifact.matches_revision"),
            now=now,
        )
    with pytest.raises(SkillStepReceiptError, match="invalid_required_check_ids"):
        validate_skill_step_receipt(
            receipt, expected=EXPECTED,
            required_check_ids=("artifact.exists", "artifact.exists"), now=now,
        )


def test_receipt_validation_rejects_naive_validation_clock():
    now = datetime.now(timezone.utc)
    receipt = SkillStepCheckReceipt.from_mapping(raw_receipt(now))
    with pytest.raises(SkillStepReceiptError, match="validation_time_must_be_utc"):
        validate_skill_step_receipt(
            receipt, expected=EXPECTED,
            required_check_ids=("artifact.exists", "artifact.matches_revision"),
            now=now.replace(tzinfo=None),
        )


def test_failed_or_missing_checks_never_pass():
    now = datetime.now(timezone.utc)
    with pytest.raises(SkillStepReceiptError, match="required_check_failed"):
        raw_receipt(now, context={"exists": False, "revision_matches": True})


def test_receipt_check_set_must_match_required_check_order(tmp_path, monkeypatch):
    path = tmp_path / "wrong-order.yaml"
    path.write_text(policy(["artifact.matches_revision", "artifact.exists"]), encoding="utf-8")
    monkeypatch.setattr(skill_step_checks, "SKILL_STEP_CHECKS_CONFIG", path)
    now = datetime.now(timezone.utc)
    receipt = SkillStepCheckReceipt.from_mapping(raw_receipt(now))
    with pytest.raises(SkillStepReceiptError, match="receipt_check_set_mismatch"):
        validate_skill_step_receipt(
            receipt, expected=EXPECTED,
            required_check_ids=("artifact.exists", "artifact.matches_revision"), now=now,
        )


def test_expired_controller_receipt_is_refused():
    now = datetime.now(timezone.utc)
    data = raw_receipt(now - timedelta(minutes=3))
    receipt = SkillStepCheckReceipt.from_mapping(data)
    with pytest.raises(SkillStepReceiptError, match="receipt_expired"):
        validate_skill_step_receipt(
            receipt, expected=EXPECTED,
            required_check_ids=("artifact.exists", "artifact.matches_revision"), now=now,
        )


def test_runlogger_accepts_exact_receipt_once_and_scrubs_it_when_protected(
    tmp_path, monkeypatch,
):
    check_ids = ["artifact.exists", "artifact.matches_revision"]
    policy_path = tmp_path / "checks.yaml"
    policy_path.write_text(policy(check_ids), encoding="utf-8")
    monkeypatch.setattr(
        "jarvis.skill_step_checks.SKILL_STEP_CHECKS_CONFIG", policy_path,
    )
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    runlog = RunLogger(
        "run-123", "developer", "Developer", "test task",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("sample-skill", REVISION, "skill_selected")
    runlog.skill_event(
        "sample-skill", REVISION, "skill_step_started",
        step_id="verify-output", attempt_id="tool-call-1", status="running",
    )
    raw = raw_receipt(datetime.now(timezone.utc))
    assert runlog.accept_skill_step_check_receipt(raw) == "accepted"
    assert runlog.accept_skill_step_check_receipt(raw) == "already_accepted"
    second_receipt = raw_receipt(datetime.now(timezone.utc))
    assert runlog.accept_skill_step_check_receipt(second_receipt) == "attempt_already_accepted"

    page = get_skill_events("run-123", db_path=db_path)
    finished = [event for event in page["events"] if event["type"] == "skill_step_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "passed"
    assert finished[0]["evidence_refs"] == [
        {"kind": "check_receipt_id", "id": raw["receipt_id"]},
    ]

    runlog.mark_sensitive()
    conn = get_conn(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM skill_step_check_receipts WHERE run_id=?",
            ("run-123",),
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert [event["type"] for event in get_skill_events("run-123", db_path=db_path)["events"]] == [
        "protected_activity",
    ]


def test_runlogger_refuses_receipt_without_started_attempt(tmp_path, monkeypatch):
    check_ids = ["artifact.exists", "artifact.matches_revision"]
    policy_path = tmp_path / "checks.yaml"
    policy_path.write_text(policy(check_ids), encoding="utf-8")
    monkeypatch.setattr(
        "jarvis.skill_step_checks.SKILL_STEP_CHECKS_CONFIG", policy_path,
    )
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    runlog = RunLogger(
        "run-123", "developer", "Developer", "test task",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("sample-skill", REVISION, "skill_selected")
    result = runlog.accept_skill_step_check_receipt(raw_receipt(datetime.now(timezone.utc)))
    assert result == "attempt_not_started"


def test_runlogger_does_not_repopulate_trace_after_protected_marker(tmp_path):
    policy_path = tmp_path / "checks.yaml"
    policy_path.write_text(
        policy(["artifact.exists", "artifact.matches_revision"]),
        encoding="utf-8",
    )
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    runlog = RunLogger(
        "run-123", "developer", "Developer", "test task",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("sample-skill", REVISION, "skill_selected")
    runlog.skill_event(
        "sample-skill", REVISION, "skill_step_started",
        step_id="verify-output", attempt_id="tool-call-1", status="running",
    )
    # Model a protected transition that committed after the receipt caller's
    # in-memory check but before its database transaction began.
    conn = get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO skill_events (user_id, run_id, request_id, event_id, seq, "
            "schema_version, occurred_at, type, status, evidence_refs) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 'protected_activity', 'unknown', '[]')",
            ("local", "run-123", "run-123", str(uuid.uuid4()), 50,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    assert runlog.accept_skill_step_check_receipt(
        raw_receipt(datetime.now(timezone.utc)),
    ) == "protected"
    conn = get_conn(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM skill_step_check_receipts WHERE run_id=?",
            ("run-123",),
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert get_skill_events("run-123", db_path=db_path)["events"][0]["type"] == (
        "protected_activity"
    )


def test_retention_pruning_removes_accepted_step_receipts(tmp_path, monkeypatch):
    policy_path = tmp_path / "checks.yaml"
    policy_path.write_text(policy(["artifact.exists", "artifact.matches_revision"]), encoding="utf-8")
    monkeypatch.setattr(
        "jarvis.skill_step_checks.SKILL_STEP_CHECKS_CONFIG", policy_path,
    )
    db_path = tmp_path / "runlog.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    runlog = RunLogger(
        "run-123", "developer", "Developer", "test task",
        db_path=db_path, root=tmp_path / "logs",
    )
    runlog.start()
    runlog.skill_event("sample-skill", REVISION, "skill_selected")
    runlog.skill_event(
        "sample-skill", REVISION, "skill_step_started",
        step_id="verify-output", attempt_id="tool-call-1", status="running",
    )
    assert runlog.accept_skill_step_check_receipt(
        raw_receipt(datetime.now(timezone.utc)),
    ) == "accepted"

    conn = get_conn(db_path)
    try:
        conn.execute(
            "UPDATE agent_runs SET started_at=? WHERE run_id=?",
            ((datetime.now(timezone.utc) - timedelta(days=60)).isoformat(), "run-123"),
        )
        conn.commit()
    finally:
        conn.close()
    prune(30, db_path=db_path, root=tmp_path)
    conn = get_conn(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM skill_step_check_receipts WHERE run_id=?",
            ("run-123",),
        ).fetchone()[0] == 0
    finally:
        conn.close()
