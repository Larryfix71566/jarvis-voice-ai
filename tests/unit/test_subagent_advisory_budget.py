"""The real SubAgent carries its original host budget only to advisory IPC."""
import json
import time

import pytest

from jarvis import usage_ledger
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_budget import TaskBudget
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits
from jarvis.privacy_policy import DataPolicy, issue_tool_result
from tests.unit.test_subagent import FakeRegistry, make_agent


@pytest.mark.parametrize('agent,server,tool', [
    ('developer', 'mcp-selfedit', 'plan_start'),
    ('analyst', 'mcp-web', 'research_compare_start'),
])
async def test_real_loop_forwards_original_host_budget_without_provider_metadata(agent, server, tool, monkeypatch, tmp_path):
    monkeypatch.setattr(usage_ledger, 'DB_PATH', tmp_path / 'costs.db')
    seen = []

    class Registry(FakeRegistry):
        def openai_tools(self, server_names=None):
            return [{'type': 'function', 'function': {'name': tool, 'description': 'inert fixture',
                    'parameters': {'type': 'object', 'properties': {}}}}]

        async def call_classified(self, name, arguments, server_names, *, execution_scope,
                                  task_budget, task_started_at):
            assert name == tool and server_names == [server]
            assert type(task_budget) is TaskBudget
            assert task_budget.workload == agent
            assert task_budget.parent_request_id == execution_scope.parent_request_id
            assert task_budget.started_at == task_started_at
            seen.append((task_budget, task_started_at))
            return issue_tool_result(execution_scope, '{"ok":true,"started":true}',
                DataPolicy('approved_external', 'host-generated-fixture-status'), 'fixture')

    subject, provider = make_agent([('tool', tool, {}), ('text', 'completed')], name=agent, registry=Registry())
    subject.mcp_servers = [server]
    subject._resolved_route = ResolvedModelRoute(agent, 'fixture', 'fixture-model', 'openai', '',
        AccessRoute('direct_api', 'openai_compatible', 'provider_api', None, 'approved_external'),
        None, 'fixture/model', 'interactive', limits=WorkloadLimits(deadline_seconds=30))
    before = time.time()
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        assert await subject.run('public fixture', run_id='host-budget-parent') == 'completed'
    finally:
        current_sensitive_turn.reset(token)
    assert len(seen) == 1 and before <= seen[0][1] <= time.time()
    assert len(provider.requests) == 2
    serialized = json.dumps(provider.requests)
    assert 'task_budget' not in serialized and 'scope_id' not in serialized
    assert 'max_estimated_spend' not in serialized and 'task_started_at' not in serialized


async def test_ordinary_classified_tools_keep_their_existing_call_contract():
    class Registry(FakeRegistry):
        async def call_classified(self, name, arguments, server_names, *, execution_scope):
            return issue_tool_result(execution_scope, '{"ok":true}',
                DataPolicy('approved_external', 'host-generated-fixture-status'), 'fixture')
    subject, provider = make_agent([('tool', 'fake_tool', {}), ('text', 'completed')], registry=Registry())
    subject._resolved_route = ResolvedModelRoute('scheduler', 'fixture', 'fixture-model', 'openai', '',
        AccessRoute('direct_api', 'openai_compatible', 'provider_api', None, 'approved_external'),
        None, 'fixture/model', 'interactive')
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        assert await subject.run('public fixture') == 'completed'
    finally:
        current_sensitive_turn.reset(token)
    assert len(provider.requests) == 2


async def test_legacy_advisory_call_uses_existing_plain_registry_without_host_transport():
    subject, provider = make_agent([('tool', 'plan_start', {}), ('text', 'completed')])
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        assert await subject.run('public fixture') == 'completed'
    finally:
        current_sensitive_turn.reset(token)
    assert len(provider.requests) == 2
    assert subject._registry.calls[0][0] == 'plan_start'
