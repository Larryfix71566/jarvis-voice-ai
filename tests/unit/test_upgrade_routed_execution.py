"""Enabled development runs use host-bound routes and synthetic source issuers."""
import asyncio
import json
import sys
import threading
import time
import uuid
from dataclasses import replace
from types import ModuleType, SimpleNamespace

import pytest

from jarvis import usage_ledger
from jarvis.agents import upgrade_agent as ua
from jarvis.model_execution import ModelToolCall
from jarvis.model_preferences import stage_preference, confirm_preference
from jarvis.model_budget import begin_model_task_budget
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits, ModelRouteError
from jarvis.privacy_policy import DataPolicy, issue_tool_result, make_tool_execution_scope
from tests.unit.test_development_sources import workspace as host_workspace


CANARY = "PRIVATE_DEVELOPMENT_SOURCE_44b8"


class WorkspaceFixture:
    """A unit fixture, deliberately not a production workspace authority."""
    def __init__(self, *, parent=None):
        self.branch = "fixture-branch" if parent else None
        self.parent = parent
        self.session_token = object()
        self.started = []
        self.cancelled = []
        self.calls = []

    def start_session(self, goal, *, run_id=None):
        self.started.append(run_id)
        self.parent, self.branch = run_id, "fixture-branch"
        self.session_token = object()
        return {"ok": True}

    def status(self):
        raise AssertionError("raw status must not reach an enabled sink: " + CANARY)

    @property
    def proposals(self):
        raise AssertionError("raw proposals must not reach an enabled sink: " + CANARY)

    def cancel(self):
        self.cancelled.append(self.parent)


class AsyncClient:
    async def close(self):
        return None


def result(*, text="done", calls=()):
    return SimpleNamespace(text=text, provider="openai", model="fixture-model",
        route="direct_api", billing="provider_api", prompt_tokens=1,
        completion_tokens=1, total_tokens=2, cache_read_tokens=None,
        cache_write_tokens=None, duration_ms=1, response_id="fixture-response",
        provider_extras={}, tool_calls=calls)


def tool(name="file_read", args=None, identity="fixture-call"):
    args = {"path": "docs/unit.txt"} if args is None else args
    return ModelToolCall(identity, name, args, json.dumps(args))


def route(*, privacy="approved_external", limits=WorkloadLimits(), native=False):
    return ResolvedModelRoute("developer", "claude-opus", "fixture-model",
        "subscription" if native else "openai", "",
        AccessRoute("subscription" if native else "direct_api",
                    "subscription_runtime" if native else "openai_compatible",
                    "subscription" if native else "provider_api", None, privacy,
                    capabilities=("text", "tools")), None, "openai/fixture-model",
        "interactive", limits=limits)


@pytest.fixture(autouse=True)
def isolated(fresh_db, monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-unused-key")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(ua, "record_execution_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: AsyncClient())


@pytest.fixture
def fixture_issuer(monkeypatch):
    """Explicit test-only issuer; no approval for a duck service in production."""
    module = ModuleType("jarvis.development_sources")

    def owner(service, parent_request_id):
        if service.parent != parent_request_id:
            raise ModelRouteError("development_session_owner_mismatch")
        return (service.parent, service.session_token)

    def check(service, parent_request_id, context):
        pinned = owner(service, parent_request_id)
        if context is not None and context != pinned:
            raise ModelRouteError("development_session_changed")

    def dispatch(service, name, args, *, execution_scope, context=None):
        check(service, execution_scope.parent_request_id, context)
        service.calls.append((name, args))
        payload = {"ok": True, "content": "public synthetic source"}
        return issue_tool_result(execution_scope, json.dumps(payload),
            DataPolicy("approved_external", "public-unit-fixture"), "unit-fixture")

    module.assert_workspace_session_owner = owner
    def cancel(service, parent_request_id, *, context=None):
        check(service, parent_request_id, context)
        service.cancel()
    module.cancel_workspace_session_for_owner = cancel
    def status(service, parent_request_id, *, context=None):
        check(service, parent_request_id, context)
        return {"phase": "editing", "proposal_count": len(service.calls)}
    module.workspace_status_for_owner = status
    module.dispatch_workspace_tool = dispatch
    monkeypatch.setitem(sys.modules, "jarvis.development_sources", module)
    return module


def prefer(workload, profile, access="direct_api"):
    return confirm_preference(stage_preference(workload, profile, access)["draft_id"])


def fixed_route(monkeypatch, selected):
    monkeypatch.setattr(ua, "resolve_model_route_checked", lambda *args, **kwargs: selected)


@pytest.mark.parametrize("kind,workload", [(ua.UpgradeAgent, "developer"),
                                         (ua.AppBuildAgent, "app_builder")])
def test_saved_profile_refreshes_between_runs_but_not_between_rounds(
    kind, workload, monkeypatch, fixture_issuer,
):
    prefer(workload, "claude-sonnet-5")
    workspace = WorkspaceFixture()
    agent = kind(workspace)
    seen = []

    async def execute(request, selected, **kwargs):
        seen.append((request, selected))
        if len(seen) == 1:
            prefer(workload, "claude-opus")
            return result(text="", calls=(tool(),))
        return result()

    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public fixture goal")["ok"]
    workspace.branch = None
    assert agent.run("another public fixture goal")["ok"]
    assert [selected.profile_name for _, selected in seen] == [
        "claude-sonnet-5", "claude-sonnet-5", "claude-opus"]
    assert seen[0][0].parent_request_id == seen[1][0].parent_request_id
    assert seen[2][0].parent_request_id != seen[0][0].parent_request_id
    assert workspace.started == [seen[0][0].parent_request_id, seen[2][0].parent_request_id]
    assert all(str(uuid.UUID(parent)) == parent for parent in workspace.started)
    assert seen[1][0].context[-1].data_policy.level == "approved_external"
    assert [request.temperature for request, _ in seen] == [None, None, None]


@pytest.mark.parametrize("kind,workload", [(ua.UpgradeAgent, "developer"),
                                         (ua.AppBuildAgent, "app_builder")])
def test_true_explicit_profile_beats_saved_choice_and_legacy_env(
    kind, workload, monkeypatch, fixture_issuer,
):
    prefer(workload, "claude-sonnet-5")
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "legacy-env-does-not-select-enabled-run")
    monkeypatch.setenv("JARVIS_APPBUILD_PROFILE", "legacy-app-env-does-not-select-enabled-run")
    workspace = WorkspaceFixture()
    agent = kind(workspace, profile="claude-opus")
    seen = []
    async def execute(request, selected, **kwargs):
        seen.append(selected.profile_name)
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    workspace.branch = None
    prefer(workload, "claude-fable-5")
    assert agent.run("public goal")["ok"]
    assert seen == ["claude-opus", "claude-opus"]


def test_checked_saygm_proof_is_required_again_for_reused_agent(monkeypatch, fixture_issuer):
    from jarvis.saygm import parse_catalog
    from jarvis import model_routing
    # Actual SAYGM catalog proof currently permits text only. This source-
    # free unit workload narrows its requirements rather than inventing
    # gateway tool acceptance to make a Developer route pass.
    access = model_routing.load_access_config()
    access["workloads"]["developer"]["capabilities"] = ["text"]
    monkeypatch.setattr(model_routing, "load_access_config", lambda *args, **kwargs: access)
    monkeypatch.setenv("SAYGM_API_KEY", "synthetic-unused-key")
    prefer("developer", "claude-opus", "saygm")
    calls = []
    def catalog(**kwargs):
        calls.append(kwargs)
        if len(calls) > 1:
            raise ModelRouteError("PRIVATE_CATALOG_FAILURE_88fa")
        return parse_catalog({"data": [{"id": "claude-opus-5", "tier": "public",
                                        "api_shapes": ["chat.completions"]}]})
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", catalog)
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace, tool_specs=[])
    executed = []
    async def execute(request, selected, **kwargs):
        executed.append(selected)
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    workspace.branch = None
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_route_unavailable"
    assert len(calls) == 2 and len(executed) == 1 and len(workspace.started) == 1
    assert "PRIVATE_CATALOG_FAILURE" not in json.dumps(refusal)


def test_enabled_timeout_refuses_without_implicit_failover(monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    calls = []
    monkeypatch.setattr(agent, "_next_failover_profile", lambda: pytest.fail("implicit failover"))
    async def execute(*args, **kwargs):
        calls.append(True)
        raise TimeoutError(CANARY)
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_execution_unavailable"
    assert calls == [True] and refusal["failovers"] == [] and refusal["status"] == {}
    assert CANARY not in json.dumps(refusal)


def test_unlabeled_plan_is_confidential_before_session_or_model(monkeypatch):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    monkeypatch.setattr(ua, "execute_chat", lambda *args, **kwargs: pytest.fail("model called"))
    refusal = agent.run("public goal", plan=CANARY)
    assert refusal["failure_code"] == "development_route_unavailable"
    assert workspace.started == [] and CANARY not in json.dumps(refusal)


@pytest.mark.parametrize("name,payload", [
    ("file_read", {"ok": True, "content": CANARY}),
    ("edit_propose", {"ok": True, "diff": CANARY}),
    ("session_validate", {"ok": False, "checks": [CANARY]}),
    ("session_submit", {"ok": True, "pr_url": CANARY}),
    ("session_decline", {"ok": False, "declined": True, "reason": CANARY}),
])
def test_private_tool_result_never_reaches_branch_council_history_or_sink(
    name, payload, monkeypatch, fixture_issuer, caplog,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    calls, events = [], []
    def dispatch(service, name, args, *, execution_scope, context=None):
        return issue_tool_result(execution_scope, json.dumps(payload), DataPolicy(), "unit-private")
    fixture_issuer.dispatch_workspace_tool = dispatch
    async def execute(*args, **kwargs):
        calls.append(True)
        return result(text="", calls=(tool(name, {}),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    monkeypatch.setattr(agent, "_maybe_scope_council", lambda **kwargs: pytest.fail("private council"))
    monkeypatch.setattr(agent, "_maybe_escalate", lambda **kwargs: pytest.fail("private council"))
    refusal = agent.run("public goal", events.append)
    assert not refusal["ok"] and calls == [True]
    assert refusal["status"] == {} and refusal["submitted"] is None
    assert agent._submit_result is None and agent._approved_proposals == []
    assert CANARY not in json.dumps([refusal, events]) and CANARY not in caplog.text


@pytest.mark.parametrize("forgery", ["raw_json", "different_scope"])
def test_tool_result_requires_exact_call_seal(forgery, monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    def dispatch(service, name, args, *, execution_scope, context=None):
        if forgery == "raw_json":
            return {"ok": True, "content": CANARY, "privacy": "approved_external"}
        other = make_tool_execution_scope(execution_scope.parent_request_id,
            execution_scope.task_id, "other-call", name, args, execution_scope.input_policy)
        return issue_tool_result(other, json.dumps({"ok": True, "content": CANARY}),
                                 DataPolicy("approved_external", "unit"), "unit")
    fixture_issuer.dispatch_workspace_tool = dispatch
    async def execute(*args, **kwargs):
        return result(text="", calls=(tool(),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_execution_unavailable"
    assert CANARY not in json.dumps(refusal)


@pytest.mark.parametrize("parent", ["other-parent", None])
def test_existing_session_is_never_adopted_from_a_returned_status(
    parent, monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture(parent=parent)
    workspace.branch = "existing-branch"
    agent = ua.UpgradeAgent(workspace, run_id="requested-parent")
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: pytest.fail("model constructed"))
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_execution_unavailable"
    assert workspace.started == [] and workspace.calls == [] and workspace.cancelled == []
    assert refusal["session_started"] is False


def test_same_owner_resume_retains_parent_and_task_budget(monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture(parent="requested-parent")
    agent = ua.UpgradeAgent(workspace, run_id="requested-parent")
    selected = route(limits=WorkloadLimits(60, 10, .2))
    fixed_route(monkeypatch, selected)
    calls = []
    async def execute(request, selected, **kwargs):
        calls.append((request, selected, kwargs["task_budget"]))
        return result(text="", calls=(tool(),)) if len(calls) == 1 else result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    assert workspace.started == []
    assert calls[0][2] is calls[1][2]
    assert all(request.parent_request_id == "requested-parent" for request, _, _ in calls)
    assert calls[0][0].task_id != calls[1][0].task_id
    assert all(selected.limits == WorkloadLimits(60, 10, .2) for _, selected, _ in calls)


@pytest.mark.parametrize("limits", [WorkloadLimits(40), WorkloadLimits(None, None, .1)])
def test_native_unsupported_caps_refuse_before_session_or_client(limits, monkeypatch):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(native=True, limits=limits))
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: pytest.fail("native constructed"))
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "budget_unsupported_route" and workspace.started == []


def test_deadline_cancels_inflight_planner_and_never_ledgers_late_result(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(limits=WorkloadLimits(deadline_seconds=.04)))
    ended, recorded = [], []
    monkeypatch.setattr(ua, "record_execution_result", lambda *args, **kwargs: recorded.append(True))
    async def execute(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            ended.append(True)
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "budget_deadline_exhausted"
    assert ended == [True] and recorded == []
    assert workspace.cancelled == workspace.started


def test_late_synchronous_tool_result_is_discarded_after_owner_cancel(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(limits=WorkloadLimits(deadline_seconds=.04)))
    def dispatch(service, name, args, *, execution_scope, context=None):
        time.sleep(.08)
        return issue_tool_result(execution_scope, json.dumps({"ok": True, "content": CANARY}),
                                 DataPolicy("approved_external", "unit"), "unit")
    fixture_issuer.dispatch_workspace_tool = dispatch
    calls = []
    async def execute(*args, **kwargs):
        calls.append(True)
        return result(text="", calls=(tool(),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "budget_deadline_exhausted" and calls == [True]
    assert CANARY not in json.dumps(refusal) and workspace.cancelled == workspace.started


def test_native_cleanup_failure_quarantines_same_agent_even_after_route_change(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(native=True))
    made = []
    class Unverified:
        async def close(self):
            raise RuntimeError(CANARY)
    client = Unverified()
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: made.append(True) or client)
    async def execute(*args, **kwargs):
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    first = agent.run("public goal")
    assert first["failure_code"] == "development_cleanup_unverified"
    assert first["submitted"] is None and CANARY not in json.dumps(first)
    assert first["cleanup_unverified"] and first["outcome_unknown"]
    assert agent._routed_client is client and agent._quarantined_clients == [client]
    fixed_route(monkeypatch, route())
    workspace.branch = None
    refusal = agent.run("another public goal")
    assert refusal["failure_code"] == "development_route_unavailable"
    assert made == [True] and len(workspace.started) == 1


def test_tool_outside_narrower_spec_is_not_dispatched(monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace, tool_specs=[ua.TOOL_SPECS[0]])
    async def execute(*args, **kwargs):
        return result(text="", calls=(tool("session_submit", {}),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_execution_unavailable"
    assert workspace.calls == []


def test_native_reopen_cannot_clear_persisted_spend_cap(monkeypatch):
    begin_model_task_budget("developer", "persisted-parent", WorkloadLimits(60, None, .1))
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace, run_id="persisted-parent")
    fixed_route(monkeypatch, route(native=True))
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: pytest.fail("native constructed"))
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "budget_unsupported_route" and workspace.started == []


def test_private_history_keeps_its_policy_through_council_and_summary(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(privacy="confidential"))
    def dispatch(service, name, args, *, execution_scope, context=None):
        payload = {"ok": True, "diff": CANARY} if name == "edit_propose" else {
            "ok": False, "checks": [CANARY]}
        return issue_tool_result(execution_scope, json.dumps(payload), DataPolicy(), "unit-private")
    fixture_issuer.dispatch_workspace_tool = dispatch
    seen = []
    async def execute(request, selected, **kwargs):
        seen.append(request)
        number = len(seen)
        if number == 1:
            return result(text="", calls=(tool("edit_propose", {"path": "docs/unit.txt",
                "new_content": "synthetic", "rationale": "synthetic edit"}),))
        if number <= 3:
            return result(text="", calls=(tool("session_validate", {}, f"validate-{number}"),))
        return result(text=CANARY)
    councils = []
    async def convene(**kwargs):
        councils.append(kwargs)
        return SimpleNamespace(winner=SimpleNamespace(profile="unit-independent", content="unit advice"),
                               round_id="unit-round")
    monkeypatch.setattr(ua, "execute_chat", execute)
    monkeypatch.setattr("jarvis.council.council.convene", convene)
    report = agent.run("confidential fixture goal", data_policy=DataPolicy())
    assert report["ok"] and report["summary"] == CANARY
    assert report["status"] == {"phase": "editing", "proposal_count": 0}
    assert agent.result_policy.level == "confidential"
    assert councils[0]["context"]["privacy"] == "confidential"
    assert councils[0]["context"]["diff"][0]["diff"] == CANARY
    assert councils[0]["run_id"] == seen[0].parent_request_id
    assert all(item.data_policy.level == "confidential" for request in seen for item in request.context)


def test_council_is_cancelled_by_shared_run_deadline_before_advice_sink(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(limits=WorkloadLimits(deadline_seconds=.05)))
    def dispatch(service, name, args, *, execution_scope, context=None):
        return issue_tool_result(execution_scope, json.dumps({"ok": False, "declined": True,
            "reason": "synthetic decline"}), DataPolicy("approved_external", "unit"), "unit")
    fixture_issuer.dispatch_workspace_tool = dispatch
    async def execute(*args, **kwargs):
        return result(text="", calls=(tool("session_decline", {}),))
    ended = []
    async def convene(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            ended.append(True)
    monkeypatch.setattr(ua, "execute_chat", execute)
    monkeypatch.setattr("jarvis.council.council.convene", convene)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "budget_deadline_exhausted" and ended == [True]
    assert workspace.cancelled == workspace.started


@pytest.mark.parametrize("limits", [WorkloadLimits(60), WorkloadLimits(None, None, .1)])
def test_capped_run_refuses_council_without_child_budget_binding(limits, monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(limits=limits))
    def dispatch(service, name, args, *, execution_scope, context=None):
        return issue_tool_result(execution_scope, json.dumps({"ok": False, "declined": True,
            "reason": "synthetic decline"}), DataPolicy("approved_external", "unit"), "unit")
    fixture_issuer.dispatch_workspace_tool = dispatch
    async def execute(*args, **kwargs):
        return result(text="", calls=(tool("session_decline", {}),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    monkeypatch.setattr("jarvis.council.council.convene", lambda **kwargs: pytest.fail("unbound council spend"))
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_council_budget_unavailable"
    assert not refusal["ok"] and not refusal.get("declined")


def test_verified_submission_survives_uncertain_native_cleanup(monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(native=True))
    class Unverified:
        async def close(self):
            raise RuntimeError(CANARY)
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: Unverified())
    def dispatch(service, name, args, *, execution_scope, context=None):
        return issue_tool_result(execution_scope, json.dumps({"ok": True,
            "pr_url": "https://github.com/unit/project/pull/7"}),
            DataPolicy("approved_external", "unit"), "unit")
    fixture_issuer.dispatch_workspace_tool = dispatch
    calls = []
    async def execute(*args, **kwargs):
        calls.append(True)
        return result(text="", calls=(tool("session_submit", {}),)) if len(calls) == 1 else result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    events = []
    refusal = agent.run("public goal", events.append)
    assert refusal["failure_code"] == "development_cleanup_unverified"
    assert refusal["submitted"] is True and refusal["pr_url"].endswith("/pull/7")
    assert refusal["outcome_unknown"] and refusal["cleanup_unverified"]
    done = [event for event in events if event["type"] == "agent_done"]
    assert len(done) == 1 and done[0]["ok"] is False and done[0]["cleanup_unverified"]


def test_long_tool_history_retains_privacy_without_recursive_metadata_growth(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    agent.cfg["max_iterations"] = 26
    calls = []
    async def execute(request, selected, **kwargs):
        calls.append(request)
        return result(text="", calls=(tool(identity=f"call-{len(calls)}"),)) if len(calls) <= 24 else result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    report = agent.run("public goal")
    assert report["ok"] and len(calls) == 25 and len(workspace.calls) == 24
    assert all(len(request.data_policy.source) < 100 for request in calls)
    assert all(request.data_policy.level == "approved_external" for request in calls)


def test_global_off_reused_agent_restores_legacy_contract_without_budget_or_sources(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    async def execute(*args, **kwargs):
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    workspace.branch = None
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "0")
    monkeypatch.setattr(ua, "begin_model_task_budget", lambda *args, **kwargs: pytest.fail("off budget authority"))
    monkeypatch.setattr(ua, "resolve_model_route_checked", lambda *args, **kwargs: pytest.fail("off route resolver"))
    workspace.status = lambda: {"legacy": True}
    monkeypatch.setattr(WorkspaceFixture, "proposals", property(lambda self: []))
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="legacy done", tool_calls=[]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr(agent, "_build_client", lambda *args, **kwargs: client)
    report = agent.run("legacy public goal")
    assert report["ok"] and report["summary"] == "legacy done" and report["status"] == {"legacy": True}
    assert workspace.started[-1] is None and agent._resolved_route is None


def test_same_parent_replacement_job_is_refused_before_next_model_round(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    original = fixture_issuer.dispatch_workspace_tool
    def dispatch(service, name, args, *, execution_scope, context=None):
        envelope = original(service, name, args, execution_scope=execution_scope, context=context)
        service.session_token = object()  # Separate host job, same parent text.
        return envelope
    fixture_issuer.dispatch_workspace_tool = dispatch
    calls = []
    async def execute(*args, **kwargs):
        calls.append(True)
        return result(text="", calls=(tool(),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_execution_unavailable"
    assert calls == [True] and len(workspace.calls) == 1


def test_cancel_before_enabled_run_does_not_adopt_or_cancel_foreign_session(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture(parent="foreign-parent")
    agent = ua.UpgradeAgent(workspace, run_id="requested-parent")
    agent.request_cancel()
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: pytest.fail("model constructed"))
    report = agent.run("public goal")
    assert report["cancelled"] and not report["session_started"]
    assert workspace.cancelled == [] and workspace.started == []


def test_route_privacy_does_not_relabel_public_input_without_source_policy(
    monkeypatch, fixture_issuer,
):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(privacy="confidential"))
    seen = []
    async def execute(request, selected, **kwargs):
        seen.append(request)
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    assert seen[0].data_policy.level == "approved_external"
    assert agent.result_policy.level == "approved_external"


def test_capped_run_with_council_disabled_can_finish_declined(monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixed_route(monkeypatch, route(limits=WorkloadLimits(60, None, .1)))
    monkeypatch.setenv("JARVIS_COUNCIL_ENABLED", "false")
    def dispatch(service, name, args, *, execution_scope, context=None):
        return issue_tool_result(execution_scope, json.dumps({"ok": False, "declined": True,
            "reason": "synthetic decline"}), DataPolicy("approved_external", "unit"), "unit")
    fixture_issuer.dispatch_workspace_tool = dispatch
    async def execute(*args, **kwargs):
        return result(text="", calls=(tool("session_decline", {}),))
    monkeypatch.setattr(ua, "execute_chat", execute)
    monkeypatch.setattr("jarvis.council.council.convene", lambda **kwargs: pytest.fail("disabled council"))
    report = agent.run("public goal")
    assert report["declined"] and not report["ok"] and "failure_code" not in report
    assert report["summary"] == "synthetic decline"


def test_task_deadline_includes_slow_route_verification_before_workspace_or_client(monkeypatch):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    def checked(*args, **kwargs):
        time.sleep(.08)
        return route(limits=WorkloadLimits(deadline_seconds=.04))
    monkeypatch.setattr(ua, "resolve_model_route_checked", checked)
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: pytest.fail("expired client"))
    monkeypatch.setattr(ua, "execute_chat", lambda *args, **kwargs: pytest.fail("expired model"))
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "budget_deadline_exhausted"
    assert workspace.started == [] and not refusal["session_started"]


def test_native_actual_close_request_protocol_preserves_owner(monkeypatch, fixture_issuer):
    from jarvis.subscription_tools import ClaudeSubscriptionToolClient
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace, run_id="requested-parent")
    fixed_route(monkeypatch, route(native=True))
    client = ClaudeSubscriptionToolClient("fixture-model")
    ended = []
    class Session:
        async def close(self):
            ended.append(True)
    # Only the actual client's local ownership registry is exercised; no
    # process/session start or native capability/provider operation occurs.
    client.sessions["requested-parent"] = Session()
    unrelated = Session()
    client.sessions["unrelated-parent"] = unrelated
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: client)
    async def execute(*args, **kwargs):
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    assert ended == [True] and client.sessions == {"unrelated-parent": unrelated}
    assert not client.cleanup_unverified
    assert agent._routed_client is None and agent._quarantined_clients == []


@pytest.mark.parametrize("codex", [False, True])
def test_exact_native_text_client_is_stateless_after_success(codex, monkeypatch, fixture_issuer):
    from jarvis.subscription import SubscriptionTextClient, CodexSubscriptionTextClient
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace, tool_specs=[])
    selected = route(native=True)
    selected = replace(selected, route=replace(selected.route, capabilities=("text",)))
    fixed_route(monkeypatch, selected)
    client = (CodexSubscriptionTextClient if codex else SubscriptionTextClient)("fixture-model")
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: client)
    async def execute(*args, **kwargs):
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    assert agent.run("public goal")["ok"]
    assert agent._routed_client is None and agent._quarantined_clients == []


def test_trusted_stateless_native_cleanup_error_quarantines_owner_across_runs(
    monkeypatch, fixture_issuer,
):
    from jarvis.subscription import SubscriptionTextClient, SubscriptionRuntimeError
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace, tool_specs=[])
    selected = route(native=True)
    selected = replace(selected, route=replace(selected.route, capabilities=("text",)))
    fixed_route(monkeypatch, selected)
    client = SubscriptionTextClient("fixture-model")
    made = []
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: made.append(True) or client)
    async def execute(*args, **kwargs):
        raise SubscriptionRuntimeError(CANARY, category="cleanup")
    monkeypatch.setattr(ua, "execute_chat", execute)
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_cleanup_unverified"
    assert refusal["cleanup_unverified"] and refusal["outcome_unknown"]
    assert agent._routed_client is client and agent._quarantined_clients == [client]
    workspace.branch = None
    again = agent.run("another public goal")
    assert again["failure_code"] == "development_route_unavailable" and made == [True]
    assert CANARY not in json.dumps([refusal, again])


@pytest.mark.parametrize("path,allowed", [("jarvis/app.py", True),
                                         ("docs/private-report.txt", False)])
def test_actual_installed_issuer_guards_upgrade_history_and_safe_status(
    path, allowed, host_workspace, monkeypatch, caplog,
):
    """Actual Runtime/Session/File adapters use only inert guest transport."""
    host = host_workspace
    agent = ua.UpgradeAgent(host.service, run_id=host.parent)
    fixed_route(monkeypatch, route())
    seen, events = [], []
    async def execute(request, selected, **kwargs):
        seen.append(request)
        return result(text="", calls=(tool(args={"path": path}),)) if len(seen) == 1 else result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    report = agent.run("public synthetic goal", events.append)
    assert bool(report["ok"]) is allowed and len(host.calls) == 1
    private = host.state["goal"]
    assert private not in json.dumps([report, events]) and private not in caplog.text
    assert all(private not in item.content for request in seen for item in request.context)
    if allowed:
        assert len(seen) == 2
        assert json.loads(seen[1].context[-1].content)["content"] == 'print("public code")\n'
        assert seen[1].context[-1].data_policy.level == "approved_external"
        assert report["status"]["session_id"] == host.state["id"]
        assert report["status"]["proposal_count"] == 0
        assert "goal" not in report["status"] and "branch" not in report["status"]
    else:
        assert len(seen) == 1 and report["failure_code"] == "development_execution_unavailable"
        assert report["submitted"] is None and agent.result_policy.level == "confidential"


def test_actual_terminal_status_retains_only_fixed_control_metadata(host_workspace, monkeypatch):
    from sandbox.durable import atomic_json
    host = host_workspace
    agent = ua.UpgradeAgent(host.service, run_id=host.parent)
    fixed_route(monkeypatch, route())
    async def execute(*args, **kwargs):
        atomic_json(host.directory / "session.json", {**host.state, "phase": "published"})
        return result()
    monkeypatch.setattr(ua, "execute_chat", execute)
    report = agent.run("public synthetic goal")
    assert report["ok"] and report["status"]["phase"] == "published"
    assert report["status"]["active"] is False and report["submitted"] is False
    assert host.state["goal"] not in json.dumps(report) and host.calls == []


def test_actual_owner_cancel_keeps_cancelled_status_without_private_source(
    host_workspace, monkeypatch,
):
    host = host_workspace
    agent = ua.UpgradeAgent(host.service, run_id=host.parent)
    fixed_route(monkeypatch, route())
    async def execute(*args, **kwargs):
        agent.request_cancel()
        return result(text=CANARY)
    monkeypatch.setattr(ua, "execute_chat", execute)
    report = agent.run("public synthetic goal")
    assert report["cancelled"] and report["status"]["phase"] == "cancelled"
    assert report["status"]["active"] is False and host.cancelled == [host.task]
    assert host.calls == [] and CANARY not in json.dumps(report)
    assert host.state["goal"] not in json.dumps(report)


def test_typed_host_owner_floor_is_joined_before_first_model(monkeypatch, fixture_issuer):
    workspace = WorkspaceFixture()
    agent = ua.UpgradeAgent(workspace)
    fixture_issuer.assert_workspace_session_owner = lambda service, parent: SimpleNamespace(input_floor=DataPolicy())
    monkeypatch.setattr(ua, "make_route_client", lambda *args, **kwargs: pytest.fail("private owner sent externally"))
    refusal = agent.run("public goal")
    assert refusal["failure_code"] == "development_execution_unavailable"
    assert workspace.started and agent.result_policy.level == "confidential"
