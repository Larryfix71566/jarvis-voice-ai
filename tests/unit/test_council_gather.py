"""Unit tests for jarvis/council/council.py's _gather_scores (gap-closure
plan GC6(a), 2026-09-04). Same _call_profile monkeypatch seam
tests/integration/test_council_escalation.py already uses."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import jarvis.council.council as council_mod
from jarvis.council.types import Proposal, RoundResult, Score
from jarvis.model_routing import AccessRoute, ModelRouteError, ResolvedModelRoute
from jarvis.privacy_policy import DataPolicy


def test_council_safe_failure_log_redacts_exception(caplog):
    council_mod._log_safe_failure(
        "council_test_failure",
        RuntimeError("COUNCIL_CONTENT_CANARY_385A /private/council/prompt"),
    )
    assert "council_test_failure" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "COUNCIL_CONTENT_CANARY_385A" not in caplog.text
    assert "/private/council/prompt" not in caplog.text
    assert "Traceback" not in caplog.text


def test_too_small_round_log_omits_round_id_and_reason(monkeypatch, caplog):
    round_id = "PRIVATE_COUNCIL_ROUND_CANARY"
    reason = "PRIVATE_PROVIDER_REASON_CANARY /private/provider/detail"
    persisted = {}
    monkeypatch.setattr(
        council_mod, "_write_round_row",
        lambda **kwargs: persisted.update(kwargs),
    )

    with caplog.at_level("INFO", logger="jarvis.council.council"):
        result = council_mod._finalize_too_small(
            round_id=round_id, run_id=None, workflow="test", placement="planner",
            trigger="unit", tier=1, goal="goal", proposer_count=0,
            judge_count=0, reason=reason, started_at="2026-09-25T00:00:00Z",
        )

    assert "council_too_small" in caplog.text
    assert round_id not in caplog.text
    assert "PRIVATE_PROVIDER_REASON_CANARY" not in caplog.text
    assert "/private/provider/detail" not in caplog.text
    assert persisted["round_id"] == round_id
    assert persisted["select_reason"] == reason
    assert result.select_reason == reason


@pytest.mark.asyncio
async def test_convene_failure_keeps_fail_open_behavior_and_redacts_log(
    monkeypatch, caplog,
):
    async def fail_inner(**_kwargs):
        raise RuntimeError("COUNCIL_CONTENT_CANARY_385A")

    monkeypatch.setattr(council_mod, "_council_enabled", lambda: True)
    monkeypatch.setattr(council_mod, "_convene_inner", fail_inner)
    result = await council_mod.convene(
        workflow="test", placement="planner", trigger="E1", goal="goal",
        tier=1, context={},
    )
    assert result is None
    assert "council_convene_failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "COUNCIL_CONTENT_CANARY_385A" not in caplog.text
    assert "Traceback" not in caplog.text


def test_council_policy_inherits_workload_privacy_and_only_tightens(monkeypatch):
    resolutions = []

    def resolve_policy(workload, **kwargs):
        resolutions.append((workload, kwargs))
        return SimpleNamespace(
            privacy={"council": "confidential", "planning": "local_only"}[workload]
        )

    monkeypatch.setattr(
        council_mod, "resolve_policy", resolve_policy,
    )
    assert council_mod._context_data_policy({}, workload="council") == DataPolicy(
        "confidential", "council-workload:council",
    )
    assert council_mod._context_data_policy(
        {"privacy": "approved_external"}, workload="council",
    ).level == "confidential"
    assert council_mod._context_data_policy(
        {"privacy": "confidential"}, workload="planning",
    ).level == "local_only"
    assert resolutions
    assert all(kwargs == {"include_preferences": False} for _, kwargs in resolutions)


def test_timeout_abstain_reason_names_the_exception(monkeypatch):
    """str(asyncio.TimeoutError()) is empty, which hid a dead judge for two
    weeks (kimi-k3 abstained on every proposal in three rounds with
    abstain_reason == "judge call failed: " -- indistinguishable from any
    other silent failure). The exception TYPE must survive even when its
    message doesn't."""
    async def _fake(profile, system_prompt, user_content, timeout_s, rung=None, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(council_mod, "_call_profile", _fake)

    scores, usage = asyncio.run(council_mod._gather_scores(
        ["j1"], {"j1": {"api_key_env": "X"}}, "judge content", ["A"],
        shadow=False, rung="council",
    ))

    assert len(scores) == 1
    assert scores[0].abstain_reason == "judge call failed: TimeoutError: "


def test_proposer_failure_log_omits_exception_message(monkeypatch, caplog):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("PROPOSER_CONTENT_CANARY_09E1 /private/council/draft")

    monkeypatch.setattr(council_mod, "_call_profile", fail)
    proposals, usage = asyncio.run(council_mod._gather_proposals(
        ["profile-a"], {"profile-a": {"api_key_env": "X"}},
        "synthetic goal", rung="council",
    ))

    assert proposals == []
    assert usage["reported_calls"] == 0
    assert "council_proposer_failed profile=profile-a error_type=RuntimeError" in caplog.text
    assert "PROPOSER_CONTENT_CANARY_09E1" not in caplog.text
    assert "/private/council/draft" not in caplog.text
    assert "Traceback" not in caplog.text


def test_judge_failure_log_omits_exception_message(monkeypatch, caplog):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("JUDGE_CONTENT_CANARY_9B02 /private/council/response")

    monkeypatch.setattr(council_mod, "_call_profile", fail)
    scores, usage = asyncio.run(council_mod._gather_scores(
        ["judge-a"], {"judge-a": {"api_key_env": "X"}},
        "synthetic input", ["A"], shadow=False, rung="council",
    ))

    assert len(scores) == 1 and scores[0].value is None
    assert usage["reported_calls"] == 0
    assert "council_judge_failed profile=judge-a shadow=False error_type=RuntimeError" in caplog.text
    assert "JUDGE_CONTENT_CANARY_9B02" not in caplog.text
    assert "/private/council/response" not in caplog.text
    assert "Traceback" not in caplog.text


def test_stricter_council_policy_rejects_external_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    profile = {
        "name": "test-profile", "model": "test-model",
        "api_key_env": "OPENAI_API_KEY", "base_url": "https://example.invalid/v1",
    }
    with pytest.raises(ModelRouteError, match="requires 'local_only'"):
        asyncio.run(council_mod._call_profile(
            profile, "system", "private", 1,
            rung="council",
            data_policy=DataPolicy("local_only", "private-test"),
        ))


def test_routed_council_call_uses_shared_execution_boundary(monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    route = ResolvedModelRoute(
        workload="council", profile_name="test-profile", model="test-model",
        provider="openai", base_url="https://example.invalid/v1/",
        route=AccessRoute(
            "direct_api", "openai_compatible", "provider_api", "OPENAI_API_KEY",
            "approved_external", capabilities=("text",),
        ),
        api_key_env="OPENAI_API_KEY", identity="openai/test-model",
        priority="background",
    )
    monkeypatch.setattr(council_mod, "resolve_model_route_checked", lambda *a, **k: route)
    captured = {}

    async def fake_execute(request, resolved):
        captured["request"] = request
        captured["route"] = resolved
        return SimpleNamespace(
            text="proposal text", prompt_tokens=12, completion_tokens=5,
        )

    recorded = []
    monkeypatch.setattr(council_mod, "execute_chat", fake_execute)
    monkeypatch.setattr(
        council_mod, "record_execution_result",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )
    profile = {
        "name": "test-profile", "model": "test-model", "temperature": 0.2,
    }

    result, usage = asyncio.run(council_mod._call_profile(
        profile, "fixed system", "proposal input", 3.0, rung="council-proposer",
    ))

    assert result == "proposal text"
    assert usage == {"prompt_tokens": 12, "completion_tokens": 5}
    request = captured["request"]
    assert request.workload == "council"
    assert request.temperature == 0.2
    assert request.timeout_s == 3.0
    assert [(item.role, item.content) for item in request.context] == [
        ("system", "fixed system"), ("user", "proposal input"),
    ]
    assert captured["route"] is route
    assert recorded[0][0][0] == "council-proposer"


def test_routed_council_protected_policy_rejects_external_before_client(monkeypatch):
    monkeypatch.setattr(
        council_mod, "resolve_policy",
        lambda workload, **kwargs: SimpleNamespace(privacy="confidential"),
    )
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    route = ResolvedModelRoute(
        workload="council", profile_name="test-profile", model="test-model",
        provider="openai", base_url="https://example.invalid/v1/",
        route=AccessRoute(
            "direct_api", "openai_compatible", "provider_api", "OPENAI_API_KEY",
            "approved_external", capabilities=("text",),
        ),
        api_key_env="OPENAI_API_KEY", identity="openai/test-model",
        priority="background",
    )
    monkeypatch.setattr(council_mod, "resolve_model_route_checked", lambda *a, **k: route)
    monkeypatch.setattr(
        "jarvis.model_execution.make_route_client",
        lambda *_args, **_kwargs: pytest.fail("protected request reached client construction"),
    )
    profile = {"name": "test-profile", "model": "test-model"}
    with pytest.raises(ModelRouteError, match="requires 'confidential'"):
        asyncio.run(council_mod._call_profile(
            profile, "private system", "private content", 2,
            rung="council-proposer",
            data_policy=council_mod._context_data_policy({}, workload="council"),
        ))


def test_policy_protected_council_payload_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(council_mod, "COUNCIL_LOG_DIR", tmp_path / "council")
    proposal = Proposal("Proposal A", "p1", "PRIVATE_PROPOSAL")
    score = Score("judge", "Proposal A", 8.0, "PRIVATE_JUSTIFICATION")
    result = RoundResult(
        round_id="round-1", winner=proposal, winner_mean=8.0,
        select_reason="PRIVATE_REASON", proposals=[proposal], scores=[score],
    )
    council_mod._write_payload(
        round_id="round-1", workflow="test", placement="doc", trigger="test",
        tier=1, goal="PRIVATE_GOAL", context={"secret": "PRIVATE_CONTEXT"},
        proposals=[proposal], live_scores=[score], result=result,
        started_at="2026-09-20T00:00:00+00:00", ended_at="2026-09-20T00:00:01+00:00",
        data_policy=DataPolicy("confidential", "test"),
    )
    payload = (tmp_path / "council" / "2026-09-20" / "round-1.jsonl").read_text()
    assert "PRIVATE_" not in payload
    assert "<policy-protected>" in payload
