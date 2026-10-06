"""Pinned host review bytes and original planning coordinator through real SDKs."""
import json
import threading
import uuid
from dataclasses import replace

import pytest
from fastapi import HTTPException

from jarvis.admin import server as admin
from jarvis import advisory_sources as sources
from jarvis.model_budget import begin_model_task_budget, bind_model_task_budget_for_transport
from jarvis.model_routing import WorkloadLimits
from jarvis.privacy_policy import DataPolicy
from jarvis.tenant import user_id_scope
from tests.unit.test_advisory_source_bridge import advisory, immediate_workers
from tests.unit.test_council_budget_ownership import transport_env, rows
from tests.unit.test_development_sources import workspace


@pytest.fixture
def review(advisory, workspace, monkeypatch):
    monkeypatch.setattr(admin, '_selfedit_service', workspace.service)
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(workspace.service.repo_root))
    root = workspace.service.repo_root
    (root / 'docs').mkdir()
    public = root / 'docs' / 'REPO_MAP.md'
    public.write_text('Public registered architecture reference.\n')
    private = root / 'docs' / 'private-report.md'
    private.write_text('PRIVATE_REVIEW_DOC_CANARY\n')
    advisory.state.limits['planning'] = WorkloadLimits(3, 60, .05)
    advisory.state.limits['council'] = WorkloadLimits(19, 90, .2)
    return public, private


def start(advisory, path='docs/REPO_MAP.md', *, mode='single', profile='economy-one'):
    logger = advisory.caller()
    scope, body = advisory.body_for(logger, args={'goal': 'Review this design', 'mode': mode,
        'profile': profile, 'review_path': path, 'confirm': True})
    pin, prepared, policy = advisory.prepare(scope, body)
    return logger, scope, body, pin, prepared, policy


def test_actual_verified_review_keeps_economy_adviser_and_all_three_budget_scopes(advisory, review, immediate_workers):
    logger, scope, body, pin, prepared, floor = start(advisory)
    assert floor.level == 'approved_external' and not advisory.state.sent
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == 'approved_external' and admin._plan_job['state'] == 'done'
    request, route, kwargs = advisory.state.captured[0]
    binding = kwargs['child_budget']
    assert request.parent_request_id == logger.run_id and request.workload == route.workload == 'council'
    assert route.profile_name == 'economy-one' and advisory.state.sent[0]['max_tokens'] == 3
    assert binding.owner.scope_id == prepared['source_context']['owner_scope_id']
    assert binding._ancestors[0].scope_id == prepared['source_context']['child_scope_id']
    assert binding.child.workload == 'council' and binding._ancestors[0].workload == 'planning'
    assert len(rows('model_call_budget_reservations')) == len(rows('llm_calls')) == 1
    assert len(rows('model_call_budget_reservation_scopes')) == 3
    assert 'Public registered architecture reference.' in advisory.state.sent[0]['messages'][1]['content']


def test_unknown_review_doc_is_confidential_before_execute_and_has_no_outbound(advisory, review, immediate_workers):
    _, scope, body, pin, prepared, floor = start(advisory, 'docs/private-report.md')
    assert floor.level == 'confidential' and not advisory.state.clients
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == 'confidential'
    assert admin._plan_job['state'] == 'error' and admin._plan_job['error'] == 'model_policy_refused'
    assert not advisory.state.sent and not advisory.state.clients


@pytest.mark.parametrize('change', ['bytes', 'inode', 'mode', 'root', 'service'])
def test_changed_prepared_review_source_refuses_before_dispatch(advisory, review, monkeypatch, change):
    _, scope, body, pin, prepared, _ = start(advisory)
    public = review[0]
    if change == 'bytes': public.write_text('PRIVATE_CHANGED_REVIEW_DOC_CANARY\n')
    if change == 'inode':
        public.rename(public.with_suffix('.old'))
        public.write_text('Public registered architecture reference.\n')
    if change == 'mode': public.chmod(0o600)
    if change == 'root': monkeypatch.setenv('JARVIS_REPO_ROOT', str(public.parent))
    if change == 'service': monkeypatch.setattr(admin, '_selfedit_service', object())
    with pytest.raises(HTTPException):
        advisory.execute(scope, body, pin, prepared)
    assert not advisory.state.sent and not advisory.state.clients and admin._plan_job['state'] == 'idle'


def test_installed_read_cannot_swap_doc_between_preflight_and_actual_thread_input(advisory, review, monkeypatch):
    _, scope, body, pin, prepared, _ = start(advisory)
    original = admin.repo_logic.repo_read_file
    reads = []
    def swapped(path):
        reads.append(path)
        value = original(path)
        # Execution preflight reads through the source module. The next read
        # is the installed original handler immediately before thread launch.
        if len(reads) == 2:
            return {**value, 'content': 'PRIVATE_UNVERIFIED_SECOND_READ_CANARY'}
        return value
    monkeypatch.setattr(admin.repo_logic, 'repo_read_file', swapped)
    _, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result == {'ok': False, 'error': 'advisory_operation_failed'}
    assert len(reads) == 2 and not advisory.state.clients


def test_requested_council_authors_reuse_original_planning_pool_and_choose_stays_owned(advisory, immediate_workers):
    advisory.state.limits['planning'] = WorkloadLimits(3, 60, .1)
    logger = advisory.caller()
    scope, body = advisory.body_for(logger, args={'goal': 'Public design plan', 'mode': 'council', 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == 'approved_external'
    assert admin._plan_job['state'] == 'awaiting_choice' and admin._plan_job['mode'] == 'council'
    authors = [item for item in advisory.state.captured if item[0].workload == 'planning']
    advisers = [item for item in advisory.state.captured if item[0].workload == 'council']
    assert authors and advisers
    assert all(item[1].profile_name.startswith('frontier') for item in authors)
    assert all(item[2]['child_budget'].child.scope_id == prepared['source_context']['child_scope_id'] for item in authors)
    assert all(item[2]['child_budget']._ancestors[0].scope_id == prepared['source_context']['child_scope_id'] for item in advisers)
    chosen = admin._plan_job['candidates'][0]
    scope, body = advisory.body_for(logger, 'plan_choose', {'label': chosen['label']})
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    assert admin._plan_job['state'] == 'done' and admin._plan_job['plan'] == chosen['content']


def test_context_source_rejects_extra_context_forged_proof_and_wrong_coordinator(advisory, review, immediate_workers):
    _, scope, body, pin, prepared, _ = start(advisory)
    source = admin._advisory_preparations[prepared['preparation_id']]['context']
    advisory.execute(scope, body, pin, prepared)
    context = dict(source._action.review.context)
    with pytest.raises(Exception):
        source.context_policy_for({**context, 'privacy': 'approved_external'})
    old = source._action.review
    source._action.review = replace(old, policy=DataPolicy('approved_external', 'forged'))
    try:
        with pytest.raises(Exception): source.context_policy_for(context)
    finally:
        source._action.review = old
    with user_id_scope('alice'):
        owner = begin_model_task_budget('developer', str(uuid.uuid4()), WorkloadLimits(9, 60, .1))
        foreign = bind_model_task_budget_for_transport(owner, 'planning', WorkloadLimits(4), started_at=owner.started_at)
        async def mismatch():
            await admin.council_mod.draft_candidates('Public goal', context=context, context_source=source,
                coordinator_budget=foreign, data_policy=DataPolicy('approved_external'))
        import asyncio
        with pytest.raises(Exception): asyncio.run(mismatch())
    assert len(advisory.state.sent) == 1
