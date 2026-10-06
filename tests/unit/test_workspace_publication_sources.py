"""Saved host PR metadata; no publication, provider or VM operation."""
import json

import pytest

from jarvis import development_sources as sources
from jarvis.privacy_policy import DataPolicy
from jarvis.runlog.store import get_run
from sandbox.durable import atomic_json
from tests.unit.test_development_sources import workspace
from tests.unit.test_workspace_source_bridge import bridge


def published(bridge, *, url=None):
    state = bridge.w.service._session()._read()
    proof = {'ok': True, 'number': 17,
             'url': url or 'https://github.com/Larryfix71566/jarvis-voice-ai/pull/17',
             'commit': 'b' * 40, 'candidate': 'c' * 64}
    atomic_json(bridge.w.directory / 'session.json', {**state, 'phase': 'published', 'publication': proof})
    return proof


async def test_exact_saved_publication_link_preserves_human_only_approval_notice(bridge):
    assert (await bridge.call('selfedit_write', {'path': 'config/protected.json',
        'content': '{"public": true}', 'rationale': 'fixture'}))[1]['ok']
    proof = published(bridge)
    policy, result, _ = await bridge.call('selfedit_status', {})
    assert policy.level == 'approved_external'
    assert result['pr_url'] == proof['url'] and result['pr_number'] == proof['number']
    assert result['commit'] == proof['commit'] and result['human_only'] is True
    assert 'approve and apply' in result['summary'] and 'do not merge' in result['summary']
    assert all(call['operation'] in {'write', 'read'} for call in bridge.w.calls)


async def test_forged_stored_url_cannot_approve_foreign_handle(bridge):
    proof = published(bridge, url='https://github.com/foreign/private-repo/pull/17')
    policy, result, _ = await bridge.call('selfedit_status', {})
    assert policy.level == 'approved_external'  # fixed status reduction only
    assert 'pr_url' not in result and proof['url'] not in json.dumps(result)


async def test_valid_saved_publication_keeps_private_candidate_and_goal_floor(bridge):
    assert (await bridge.call('selfedit_write', {'path': 'jarvis/app.py',
        'content': 'public fixture', 'rationale': 'fixture'}))[1]['ok']
    sources.retain_workspace_floor(get_run(bridge.w.parent)['run'], DataPolicy('local_only', 'private-goal'))
    proof = published(bridge)
    policy, result, _ = await bridge.call('selfedit_status', {})
    assert policy.level == 'local_only' and result['pr_url'] == proof['url']
    assert bridge.holder.is_armed() and proof['url'] not in json.dumps(bridge.logger._buffer)
