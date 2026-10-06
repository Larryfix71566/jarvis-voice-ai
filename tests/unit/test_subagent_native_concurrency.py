"""Actual SubAgent/execute_chat admission with real native clients and inert runners.

No subprocess, provider, VM, production state or publication is used.
"""
import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jarvis import model_execution, subscription, usage_ledger
from jarvis.agents import base
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_routing import AccessRoute, ResolvedModelRoute

CLIENTS = [
    (subscription.SubscriptionTextClient, 'subscription_runtime',
     'anthropic/native-fixture', '_run_claude_response_async'),
    (subscription.CodexSubscriptionTextClient, 'codex_subscription_runtime',
     'openai/native-fixture', '_run_codex_response_async'),
]
LATE_RESULT = 'PRIVATE_LATE_NATIVE_RESULT_315b'


@pytest.fixture
def native_owner(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'preferences.db'))
    monkeypatch.setenv('JARVIS_VAULT_PATH', str(tmp_path / 'no.vault'))
    monkeypatch.setenv('JARVIS_MODEL_ROUTING_ENABLED', '1')
    monkeypatch.setenv('JARVIS_MODEL_PREFERENCES_ENABLED', '0')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-unused-key')
    monkeypatch.setenv('JARVIS_COUNCIL_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_WORKFLOWS_ENABLED', 'false')
    monkeypatch.setattr(usage_ledger, 'DB_PATH', tmp_path / 'costs.db')
    settings = SimpleNamespace(
        openai_model='unused', openai_api_key='synthetic',
        openai_base_url='http://unused', jarvis_timezone='UTC',
        jarvis_runlog_enabled=False, jarvis_procedures_enabled=False,
        jarvis_model_routing_enabled=True,
    )
    created, recorded = [], []
    selected = {}
    admission = model_execution.ModelAdmissionController()
    monkeypatch.setattr(model_execution, '_PROCESS_ADMISSION', admission)
    monkeypatch.setattr(base, 'resolve_model_route_checked',
                        lambda *args, **kwargs: selected['route'])
    monkeypatch.setattr(base, 'record_execution_result',
                        lambda *args, **kwargs: recorded.append((args, kwargs)))
    token = current_sensitive_turn.set(SensitiveTurn())

    def build(client_type, adapter, identity):
        selected['route'] = ResolvedModelRoute(
            'developer', 'native', 'native-fixture', 'subscription', '',
            AccessRoute('subscription', adapter, 'subscription', None,
                        'approved_external', capabilities=('text',)),
            None, identity, 'interactive',
        )
        def factory(_route):
            client = client_type('native-fixture')
            created.append(client)
            return client
        monkeypatch.setattr(base, 'make_route_client', factory)
        return base.SubAgent('developer', 'Developer', 'synthetic fixture', [],
                             settings, SimpleNamespace(), model_profile='claude-opus',
                             on_profile_fallback='refuse')

    yield SimpleNamespace(build=build, selected=selected, created=created,
                          recorded=recorded, admission=admission)
    current_sensitive_turn.reset(token)


async def run(subject, events=None):
    return await subject.run('public synthetic task', tool_specs_override=[],
                             on_event=events.append if events is not None else None)


async def drain(tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('client_type,adapter,identity,runner', CLIENTS)
async def test_active_subagent_result_is_suppressed_after_shared_native_cleanup_failure(
    native_owner, monkeypatch, client_type, adapter, identity, runner,
):
    fixture = native_owner
    subject = fixture.build(client_type, adapter, identity)
    first_entered, second_entered, fail, release = (asyncio.Event() for _ in range(4))
    calls, tasks, events = [], [], []

    async def inert(*args):
        calls.append(args)
        if len(calls) == 1:
            first_entered.set()
            await fail.wait()
            raise subscription.SubscriptionRuntimeError('PRIVATE_CLEANUP_315b', category='cleanup')
        second_entered.set()
        await release.wait()
        return subscription._response(LATE_RESULT, {})

    monkeypatch.setattr(subscription, runner, inert)
    try:
        first = asyncio.create_task(run(subject))
        tasks.append(first)
        await asyncio.wait_for(first_entered.wait(), 2)
        second = asyncio.create_task(run(subject, events))
        tasks.append(second)
        await asyncio.wait_for(second_entered.wait(), 2)
        fail.set()
        first_result = await asyncio.wait_for(first, 2)
        assert first_result.startswith('FAILED:')
        assert len(fixture.created) == 1 and fixture.created[0].cleanup_unverified
        assert subject._native_cleanup_quarantined == {id(fixture.created[0])}
        release.set()
        second_result = await asyncio.wait_for(second, 2)
        assert second_result.startswith('FAILED:')
        assert LATE_RESULT not in second_result
        assert not any(event.get('type') == 'agent_done' for event in events)
        assert LATE_RESULT not in json.dumps(events)
        assert fixture.recorded == []
        assert len(calls) == 2
    finally:
        release.set()
        fail.set()
        await drain(tasks)
    assert fixture.admission.active_counts == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('client_type,adapter,identity,runner', CLIENTS)
async def test_queued_subagent_never_starts_shared_native_runner_after_quarantine(
    native_owner, monkeypatch, client_type, adapter, identity, runner,
):
    fixture = native_owner
    subject = fixture.build(client_type, adapter, identity)
    first_entered, fail, background_held, release_background = (
        asyncio.Event() for _ in range(4)
    )
    calls, tasks, events = [], [], []

    async def inert(*args):
        calls.append(args)
        if len(calls) == 1:
            first_entered.set()
            await fail.wait()
            raise subscription.SubscriptionRuntimeError('PRIVATE_CLEANUP_315b', category='cleanup')
        return subscription._response(LATE_RESULT, {})

    async def occupy_background_capacity():
        async with fixture.admission.slot('background'):
            background_held.set()
            await release_background.wait()

    monkeypatch.setattr(subscription, runner, inert)
    try:
        blocker = asyncio.create_task(occupy_background_capacity())
        tasks.append(blocker)
        await asyncio.wait_for(background_held.wait(), 2)
        first = asyncio.create_task(run(subject))
        tasks.append(first)
        await asyncio.wait_for(first_entered.wait(), 2)
        # Priority is a per-run snapshot; the native owner key remains identical.
        fixture.selected['route'] = replace(fixture.selected['route'], priority='background')
        second = asyncio.create_task(run(subject, events))
        tasks.append(second)
        async with asyncio.timeout(2):
            while not fixture.admission._waiters:
                await asyncio.sleep(.001)
        fail.set()
        first_result = await asyncio.wait_for(first, 2)
        assert first_result.startswith('FAILED:')
        assert len(calls) == 1 and len(fixture.created) == 1
        assert fixture.created[0].cleanup_unverified
        assert subject._native_cleanup_quarantined == {id(fixture.created[0])}
        release_background.set()
        await blocker
        second_result = await asyncio.wait_for(second, 2)
        assert second_result.startswith('FAILED:')
        assert LATE_RESULT not in second_result
        assert len(calls) == 1  # No runner starts after admission releases.
        assert not any(event.get('type') == 'agent_done' for event in events)
        assert LATE_RESULT not in json.dumps(events)
        assert fixture.recorded == []
        assert len(fixture.created) == 1
    finally:
        fail.set()
        release_background.set()
        await drain(tasks)
    assert fixture.admission.active_counts == (0, 0)
