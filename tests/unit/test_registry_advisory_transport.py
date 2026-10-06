"""Known phase/cancellation boundaries through the actual host advisory bridge."""
import asyncio
import json
import uuid

import pytest

from jarvis import advisory_sources as sources
from jarvis.admin import server as admin
from jarvis.skills.registry import SkillRegistry
from tests.unit.test_advisory_source_bridge import advisory, immediate_workers
from tests.unit.test_council_budget_ownership import transport_env


@pytest.mark.parametrize('tamper', ['caller', 'phase', 'body'])
async def test_unverified_preparation_never_executes_or_launches_a_model(advisory, immediate_workers, monkeypatch, tamper):
    original = SkillRegistry._call_watching
    observed = []

    async def corrupt(self, server, session, name, arguments, *, meta=None):
        observed.append(meta['mortimer_advisory_source']['phase'])
        result = await original(self, server, session, name, arguments, meta=meta)
        if meta['mortimer_advisory_source']['phase'] == 'prepare':
            hidden = result.meta['mortimer_advisory_source']
            if tamper == 'caller':
                hidden['source_context']['caller_run_id'] = str(uuid.uuid4())
            elif tamper == 'phase':
                hidden['source_receipt']['phase'] = 'execute'
            else:
                result.structuredContent['ok'] = False
        return result

    monkeypatch.setattr(SkillRegistry, '_call_watching', corrupt)
    policy, result, _, _ = await advisory.registry_call(advisory.caller())
    assert result == {'ok': False, 'error': 'advisory_source_unavailable'}
    assert observed == ['associate', 'prepare']
    assert not advisory.state.sent and not advisory.state.clients
    assert admin._plan_job['state'] == 'idle'


async def test_cancelled_prepared_start_receives_ack_and_cannot_later_execute(advisory, monkeypatch):
    original = SkillRegistry._call_watching
    observed = []
    acknowledgements = []

    async def cancel(self, server, session, name, arguments, *, meta=None):
        phase = meta['mortimer_advisory_source']['phase']
        observed.append(phase)
        if phase == 'execute':
            raise asyncio.CancelledError()
        result = await original(self, server, session, name, arguments, meta=meta)
        if phase == 'cancel':
            acknowledgements.append(result.structuredContent)
        return result

    monkeypatch.setattr(SkillRegistry, '_call_watching', cancel)
    logger = advisory.caller()
    with pytest.raises(asyncio.CancelledError):
        await advisory.registry_call(logger)
    assert observed == ['associate', 'prepare', 'execute', 'cancel']
    assert acknowledgements == [{'ok': True, 'cancelled': True, 'action_run_id': logger.run_id}]
    assert admin._plan_job['state'] == 'idle'
    assert not advisory.state.sent and not advisory.state.clients
    assert len(admin._advisory_preparations) == 1
    context = next(iter(admin._advisory_preparations.values()))['context']
    assert context.cancel_event.is_set()


async def test_lost_actual_start_reply_cancels_owned_job_without_replaying_start(advisory, immediate_workers, monkeypatch):
    original = SkillRegistry._call_watching
    observed = []
    owned = []

    async def lost(self, server, session, name, arguments, *, meta=None):
        phase = meta['mortimer_advisory_source']['phase']
        observed.append(phase)
        result = await original(self, server, session, name, arguments, meta=meta)
        if phase == 'execute':
            assert result.structuredContent['started'] is True
            owned.extend(sources._active.values())
            raise OSError('SYNTHETIC_PRIVATE_TRANSPORT_CANARY')
        return result

    monkeypatch.setattr(SkillRegistry, '_call_watching', lost)
    policy, result, _, _ = await advisory.registry_call(advisory.caller())
    assert result == {'ok': False, 'error': 'advisory_source_unavailable'}
    assert observed == ['associate', 'prepare', 'execute', 'cancel']
    assert len(advisory.state.sent) == 1 and len(owned) == 1
    assert owned[0].cancel_event.is_set() and admin._plan_job['state'] == 'idle'
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(result)
