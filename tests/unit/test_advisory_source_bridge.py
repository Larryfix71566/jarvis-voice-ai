"""Actual advisory workers, SDK MockTransport and host receipts; no network."""
import asyncio
import json
import os
import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from jarvis import advisory_sources as sources, development_attestation as attestation
from jarvis.admin import server as admin
from jarvis.auth import ClientIdentity
from jarvis.development_sources import retain_workspace_floor
from jarvis.model_budget import begin_model_task_budget, bind_model_task_budget_for_transport
from jarvis.model_routing import WorkloadLimits
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.runlog.store import RunLogger, get_run
from jarvis.runlog.context import run_logger_scope
from jarvis.skills.registry import _ToolSourceContract
from jarvis.skill_runtime import update_runtime_inventory
from jarvis.tenant import user_id_scope
from tests.unit.test_council_budget_ownership import transport_env, rows
from tests.unit.test_registry_source_policy import registry_for
from tests.unit.test_development_sources import workspace


@pytest.fixture
def advisory(transport_env, tmp_path, monkeypatch):
    home = tmp_path / 'sandbox'
    home.mkdir(mode=0o700)
    (home / '.source-authority').mkdir(mode=0o700)
    monkeypatch.setenv('MORTIMER_SANDBOX_HOME', str(home))
    monkeypatch.setenv('JARVIS_AUTH_ENABLED', 'true')
    monkeypatch.setattr(attestation, '_issuers', {})
    monkeypatch.setattr(attestation, '_inflight_leases', set())
    monkeypatch.setattr(attestation, '_challenges', {})
    monkeypatch.setattr(sources, '_issued', {})
    monkeypatch.setattr(sources, '_active', {})
    monkeypatch.setattr(sources, 'resolve_policy', admin.council_mod.resolve_policy)
    monkeypatch.setattr(admin, 'resolve_policy', admin.council_mod.resolve_policy)
    monkeypatch.setattr(admin, '_advisory_preparations', {})
    monkeypatch.setattr(admin, '_advisory_job_guards', {})
    for lock, slot in ((admin._plan_lock, admin._plan_job), (admin._research_lock, admin._research_job)):
        with lock:
            slot.update({key: None for key in slot})
            slot.update(state='idle', run_id=None)
    session = str(uuid.uuid4())
    update_runtime_inventory(session, [], True, active=True, owner_id='alice')
    request = SimpleNamespace(scope={'client_identity': ClientIdentity('service-bot', 'service-owner')})

    def caller(role='developer'):
        with user_id_scope('alice'):
            logger = RunLogger(str(uuid.uuid4()), role, 'Synthetic caller', 'public task', session_id=session, root=tmp_path)
            logger.start()
        return logger

    def body_for(logger, tool='plan_start', args=None, level='approved_external', binding=None):
        arguments = {'goal': 'public author goal', 'confirm': True} if args is None else args
        scope = make_tool_execution_scope(logger.run_id, 'task-' + uuid.uuid4().hex, 'call-' + uuid.uuid4().hex,
                                         tool, arguments, DataPolicy(level, 'host-input'))
        body = dict(owner_id='alice', bot_session_id=session, caller_run_id=logger.run_id,
            caller_agent=get_run(logger.run_id)['run']['agent'], tool_name=tool, arguments=arguments,
            task_id=scope.task_id, tool_call_id=scope.tool_call_id,
            challenge=attestation.new_source_challenge(), input_policy=level)
        if tool in {'plan_start', 'research_compare_start'}:
            workload = 'planning' if tool == 'plan_start' else 'council'
            with user_id_scope('alice'):
                if binding is None:
                    entered = time.time()
                    owner = begin_model_task_budget(body['caller_agent'], logger.run_id, WorkloadLimits(7, 60, .1), started_at=entered)
                    binding = bind_model_task_budget_for_transport(owner, workload,
                        transport_env.limits.get(workload, WorkloadLimits()), started_at=entered)
            body.update(owner_scope_id=binding.owner.scope_id, child_scope_id=binding.child.scope_id)
        return scope, body

    def prepare(scope, body):
        admin.associate_advisory_source(admin.AdvisorySourceIn(**body), request)
        pin = attestation.pin_source_authority()
        value = admin.prepare_advisory_source(admin.AdvisorySourceIn(**body), request)
        envelope = attestation.verify_advisory_source(pin, scope, value['source_receipt'],
            context=value['source_context'], challenge=body['challenge'], phase='prepare')
        policy, content = validate_tool_result(scope, envelope)
        assert json.loads(content) == {key: value[key] for key in ('ok', 'preparation_id', 'source_context')}
        return pin, value, policy

    def execute(scope, body, pin, prepared, phase='execute'):
        new = {**body, 'challenge': attestation.new_source_challenge(),
               'source_context': prepared['source_context'], 'preparation_id': prepared['preparation_id']}
        function = admin.execute_advisory_source if phase == 'execute' else admin.cancel_advisory_source
        result = function(admin.AdvisorySourceIn(**new), request)
        envelope = attestation.verify_advisory_source(pin, scope, result['source_receipt'],
            context=prepared['source_context'], challenge=new['challenge'], phase=phase)
        policy, content = validate_tool_result(scope, envelope)
        return policy, json.loads(content), new

    async def registry_call(logger, tool='plan_start', arguments=None, level='approved_external'):
        from mcp.server.fastmcp import Context
        from mcp.shared.context import RequestContext
        from mcp.types import RequestParams, CallToolResult
        from mcp_servers.mcp_selfedit import server as plan_server
        from mcp_servers.mcp_web import server as web_server
        from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
        arguments = {'goal': 'public author goal', 'confirm': True} if arguments is None else arguments
        scope = make_tool_execution_scope(logger.run_id, 'task-' + uuid.uuid4().hex,
            'call-' + uuid.uuid4().hex, tool, arguments, DataPolicy(level, 'host-input'))
        phases = []
        holder = SensitiveTurn()
        class Admin:
            def post(self, path, json):
                function = {'associate': admin.associate_advisory_source, 'prepare': admin.prepare_advisory_source,
                    'tool': admin.execute_advisory_source, 'cancel': admin.cancel_advisory_source}[path.rsplit('/', 1)[-1]]
                return function(admin.AdvisorySourceIn(**json), request)
        monkeypatch.setattr(plan_server, '_client', Admin())
        monkeypatch.setattr(web_server, '_admin_client', Admin())
        class Session:
            async def call_tool(self, name, values, *, meta=None):
                phase = meta['mortimer_advisory_source']['phase']
                phases.append((phase, holder.is_armed()))
                params = RequestParams.Meta.model_validate(meta)
                if name.startswith('plan_'):
                    ctx = Context(request_context=RequestContext(1, params, None, None), fastmcp=plan_server.mcp)
                    return await asyncio.to_thread(getattr(plan_server, name), **values, ctx=ctx)
                ctx = SimpleNamespace(request_context=SimpleNamespace(meta=params))
                result = await asyncio.to_thread(web_server._advisory_response, ctx, name, values)
                return CallToolResult(content=result.content, structuredContent=result.structured_content, _meta=result.meta)
        child = Session()
        server = 'mcp-selfedit' if tool.startswith('plan_') else 'mcp-web'
        module = 'mcp_servers.mcp_selfedit.server' if tool.startswith('plan_') else 'mcp_servers.mcp_web.server'
        registry = registry_for(tool, server, child, pinned=True)
        registry._source_contracts[server] = _ToolSourceContract(server, module, child, local_admin=True)
        with user_id_scope('alice'):
            owner = begin_model_task_budget(get_run(logger.run_id)['run']['agent'], logger.run_id,
                WorkloadLimits(7, 60, .1)) if tool in {'plan_start', 'research_compare_start'} else None
            token = current_sensitive_turn.set(holder)
            try:
                with run_logger_scope(logger):
                    envelope = await registry.call_classified(tool, arguments, execution_scope=scope,
                        task_budget=owner, task_started_at=time.time() if owner is not None else None)
            finally:
                current_sensitive_turn.reset(token)
        policy, content = validate_tool_result(scope, envelope)
        return policy, json.loads(content), phases, holder

    yield SimpleNamespace(state=transport_env, session=session, request=request, caller=caller,
                         body_for=body_for, prepare=prepare, execute=execute, registry_call=registry_call)
    update_runtime_inventory(session, [], True, active=False, owner_id='alice')
    for issuer in attestation._issuers.values():
        os.close(issuer.lease)


@pytest.fixture
def immediate_workers(monkeypatch):
    class Thread:
        def __init__(self, *, target, args=(), kwargs=None, daemon):
            self.target, self.args, self.kwargs = target, args, kwargs or {}
        def start(self):
            self.target(*self.args, **self.kwargs)
    monkeypatch.setattr(admin, 'threading', SimpleNamespace(Thread=Thread, Event=threading.Event))


def test_actual_voice_author_uses_original_parent_child_and_configured_model_floor(advisory, immediate_workers):
    advisory.state.limits['planning'] = WorkloadLimits(19, 90, .2)
    logger = advisory.caller()
    scope, body = advisory.body_for(logger)
    pin, prepared, floor = advisory.prepare(scope, body)
    assert floor.level == 'approved_external' and not advisory.state.sent
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == 'approved_external'
    assert admin._plan_job['state'] == 'done' and len(advisory.state.sent) == 1
    request, route, kwargs = advisory.state.captured[0]
    assert request.parent_request_id == logger.run_id and request.workload == route.workload == 'planning'
    assert route.profile_name == 'frontier-one' and advisory.state.sent[0]['max_tokens'] == 7
    assert kwargs['child_budget'].owner.scope_id == body['owner_scope_id']
    assert kwargs['child_budget'].child.scope_id == body['child_scope_id']
    assert len(rows('llm_calls')) == len(rows('model_call_budget_reservations')) == 1


async def test_real_registry_receipts_reach_actual_author_worker_and_preserve_off_body(advisory, immediate_workers):
    logger = advisory.caller()
    policy, result, phases, holder = await advisory.registry_call(logger)
    assert result['started'] and policy.level == 'approved_external' and not holder.is_armed()
    assert [phase for phase, _ in phases] == ['associate', 'prepare', 'execute']
    assert len(advisory.state.sent) == 1
    assert advisory.state.captured[0][0].parent_request_id == logger.run_id
    assert 'source_receipt' not in result and 'owner_scope_id' not in result


async def test_real_registry_private_preparation_arms_before_actual_execute(advisory, immediate_workers):
    logger = advisory.caller()
    retain_workspace_floor(get_run(logger.run_id)['run'], DataPolicy('local_only', 'host-acquired'))
    policy, result, phases, holder = await advisory.registry_call(logger)
    assert result['started'] and policy.level == 'local_only' and holder.is_armed()
    assert phases[-1] == ('execute', True)
    assert not advisory.state.sent and not advisory.state.clients


def test_retained_status_uses_new_live_caller_without_resetting_completed_origin(advisory, immediate_workers):
    origin = advisory.caller()
    scope, body = advisory.body_for(origin)
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    origin.finish('completed')
    caller = advisory.caller()
    before = rows('model_task_budgets')
    scope, body = advisory.body_for(caller, 'plan_status', {'action_run_id': origin.run_id})
    pin, prepared, _ = advisory.prepare(scope, body)
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['job']['plan'] == admin._plan_job['plan'] and policy.level == 'approved_external'
    assert prepared['source_context']['origin_run_id'] == origin.run_id
    assert prepared['source_context']['caller_run_id'] == caller.run_id
    assert rows('model_task_budgets') == before and len(advisory.state.sent) == 1


@pytest.mark.parametrize('tamper', ['owner', 'child', 'agent', 'review'])
def test_untrusted_budget_role_and_unreadable_review_refuse_before_work(advisory, tamper):
    logger = advisory.caller()
    scope, body = advisory.body_for(logger)
    if tamper == 'owner': body['owner_scope_id'] = uuid.uuid4().hex
    if tamper == 'child': body['child_scope_id'] = uuid.uuid4().hex
    if tamper == 'agent': body['caller_agent'] = 'analyst'
    if tamper == 'review': body['arguments']['review_path'] = 'docs/private.md'
    with pytest.raises(HTTPException):
        advisory.prepare(scope, body)
    assert not advisory.state.clients and not advisory.state.sent and admin._plan_job['state'] == 'idle'


def test_floor_strengthened_after_prepare_precedes_worker_model_admission(advisory, immediate_workers):
    logger = advisory.caller()
    scope, body = advisory.body_for(logger)
    pin, prepared, _ = advisory.prepare(scope, body)
    retain_workspace_floor(get_run(logger.run_id)['run'], DataPolicy('local_only', 'host-acquired'))
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == 'local_only'
    assert admin._plan_job['state'] == 'error' and admin._plan_job['error'] == 'model_policy_refused'
    assert not advisory.state.clients and not advisory.state.sent


def test_prepare_receipt_cannot_be_verified_as_execute(advisory):
    logger = advisory.caller()
    scope, body = advisory.body_for(logger)
    admin.associate_advisory_source(admin.AdvisorySourceIn(**body), advisory.request)
    pin = attestation.pin_source_authority()
    prepared = admin.prepare_advisory_source(admin.AdvisorySourceIn(**body), advisory.request)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_advisory_source(pin, scope, prepared['source_receipt'],
            context=prepared['source_context'], challenge=body['challenge'], phase='execute')
    attestation.verify_advisory_source(pin, scope, prepared['source_receipt'],
        context=prepared['source_context'], challenge=body['challenge'], phase='prepare')


def test_cancelled_old_worker_cannot_publish_over_replacement_action(advisory, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    workers = []
    def thread_factory(*args, **kwargs):
        worker = threading.Thread(*args, **kwargs)
        workers.append(worker)
        return worker
    monkeypatch.setattr(admin, 'threading', SimpleNamespace(Thread=thread_factory, Event=threading.Event))
    async def inert_completion(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait)
        return 'PRIVATE_OLD_ACTION_CANARY', None
    monkeypatch.setattr(admin.council_mod, '_call_profile', inert_completion)
    logger = advisory.caller()
    scope, body = advisory.body_for(logger)
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    try:
        assert entered.wait(2)
        policy, result, _ = advisory.execute(scope, body, pin, prepared, phase='cancel')
        assert result['cancelled'] and policy.level == 'approved_external'
        assert admin._plan_job['state'] == 'idle'
        with admin._plan_lock:
            admin._plan_job.update(state='running', run_id=str(uuid.uuid4()), plan='new action intact')
    finally:
        release.set()
        for worker in workers:
            worker.join(2)
    assert len(workers) == 1 and not workers[0].is_alive()
    assert admin._plan_job['state'] == 'running' and admin._plan_job['plan'] == 'new action intact'


def test_actual_analyst_unknown_crawl_bytes_stay_confidential_without_provider(advisory, immediate_workers, monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-unused')
    monkeypatch.setattr(admin.research_crawl, 'crawl_site', lambda client, url, *args: {
        'ok': True, 'url': url, 'pages': [], 'credits': 1, 'page_count': 0,
        'privacy': 'approved_external', 'content': 'PRIVATE_CRAWL_CANARY'})
    monkeypatch.setattr(admin.research_crawl, 'assemble_digests', lambda *args: 'PRIVATE_CRAWL_CANARY')
    logger = advisory.caller('analyst')
    scope, body = advisory.body_for(logger, 'research_compare_start',
        {'urls': ['https://a.invalid', 'https://b.invalid'], 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == 'confidential'
    assert prepared['source_context']['caller_agent'] == 'analyst'
    assert admin._research_job['state'] == 'error' and admin._research_job['error'] == 'model_policy_refused'
    assert not advisory.state.clients and not advisory.state.sent


@pytest.mark.parametrize('private', [False, True])
def test_exact_owned_generated_plan_save_preserves_policy_in_actual_guest_and_next_read(
    advisory, workspace, immediate_workers, monkeypatch, tmp_path, private,
):
    monkeypatch.setattr(admin, '_selfedit_service', workspace.service)
    monkeypatch.setattr(admin, 'authoring_enabled', lambda: True)
    monkeypatch.setattr(admin, '_busy', lambda: False)
    with user_id_scope('alice'):
        target = RunLogger(workspace.parent, 'developer', 'Actual workspace job', 'public task',
                           session_id=advisory.session, root=tmp_path)
        target.start()
    if private:
        async def local_inert_author(*args, **kwargs):
            assert kwargs['data_policy'].level == 'local_only'
            return 'PRIVATE_GENERATED_PLAN_CANARY', None
        monkeypatch.setattr(admin.council_mod, '_call_profile', local_inert_author)
    logger = advisory.caller()
    scope, body = advisory.body_for(logger, level='local_only' if private else 'approved_external')
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    scope, body = advisory.body_for(logger, 'plan_adopt', {'path': 'docs/plans/public-plan.md', 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['saved_to_sandbox'] and not result['published']
    expected = 'local_only' if private else 'approved_external'
    assert policy.level == expected and ('PRIVATE_GENERATED_PLAN_CANARY' in result['diff']) == private
    written = workspace.guest['docs/plans/public-plan.md']
    assert written.startswith(b'PRIVATE_GENERATED_PLAN_CANARY' if private else b'Synthetic member plan')
    journal = json.loads((workspace.controller.task_dir(workspace.task) / 'files.json').read_text())
    assert journal['source_floor'] == expected
    from jarvis import development_sources as development
    next_caller = advisory.caller()
    development.retain_workspace_floor(get_run(next_caller.run_id)['run'],
        development.workspace_floor(get_run(workspace.parent)['run']))
    context = development.ordinary_context(workspace.service, get_run(next_caller.run_id)['run'],
        get_run(workspace.parent)['run'], workspace_kind='selfedit', lineage_id=workspace.state['id'])
    args = {'path': 'docs/plans/public-plan.md'}
    scope = make_tool_execution_scope(next_caller.run_id, 'new-task', 'new-call', 'file_read', args, DataPolicy('approved_external'))
    with user_id_scope('alice'):
        envelope = development.dispatch_workspace_tool(workspace.service, 'file_read', args, execution_scope=scope, context=context)
    assert validate_tool_result(scope, envelope)[0].level == expected


def test_changed_plan_content_after_prepare_refuses_before_guest_save(advisory, workspace, immediate_workers, monkeypatch, tmp_path):
    monkeypatch.setattr(admin, '_selfedit_service', workspace.service)
    monkeypatch.setattr(admin, 'authoring_enabled', lambda: True)
    with user_id_scope('alice'):
        logger = RunLogger(workspace.parent, 'developer', 'Actual workspace job', 'public task',
                           session_id=advisory.session, root=tmp_path)
        logger.start()
    caller = advisory.caller()
    scope, body = advisory.body_for(caller)
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    scope, body = advisory.body_for(caller, 'plan_adopt', {'path': 'docs/plans/public-plan.md', 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    admin._plan_job['plan'] = 'PRIVATE_REPLACED_PLAN_CANARY'
    with pytest.raises(HTTPException):
        advisory.execute(scope, body, pin, prepared)
    assert not workspace.calls and 'docs/plans/public-plan.md' not in workspace.guest


def test_source_endpoints_reject_nonservice_identity_before_signer(advisory):
    logger = advisory.caller()
    scope, body = advisory.body_for(logger)
    request = SimpleNamespace(scope={'client_identity': ClientIdentity('native-client', 'alice')})
    for function in (admin.associate_advisory_source, admin.prepare_advisory_source,
                     admin.execute_advisory_source, admin.cancel_advisory_source):
        with pytest.raises(HTTPException) as error:
            function(admin.AdvisorySourceIn(**body), request)
        assert error.value.status_code == 403
    assert not attestation._issuers and not advisory.state.clients


def test_actual_analyst_save_uses_genuine_target_developer_job_and_confidential_floor(
    advisory, workspace, immediate_workers, monkeypatch, tmp_path,
):
    monkeypatch.setattr(admin, '_selfedit_service', workspace.service)
    monkeypatch.setattr(admin, 'authoring_enabled', lambda: True)
    monkeypatch.setattr(admin, '_busy', lambda: False)
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-unused')
    monkeypatch.setattr(admin.research_crawl, 'crawl_site', lambda client, url, *args: {
        'ok': True, 'url': url, 'pages': [], 'credits': 1, 'page_count': 0})
    monkeypatch.setattr(admin.research_crawl, 'assemble_digests', lambda *args: 'PRIVATE_CRAWL_CANARY')
    async def compliant_inert_comparison(*args, **kwargs):
        assert kwargs['data_policy'].level == 'confidential'
        return 'PRIVATE_GENERATED_COMPARISON', None
    monkeypatch.setattr(admin.council_mod, '_call_profile', compliant_inert_comparison)
    with user_id_scope('alice'):
        target = RunLogger(workspace.parent, 'developer', 'Actual workspace job', 'public task',
                           session_id=advisory.session, root=tmp_path)
        target.start()
    caller = advisory.caller('analyst')
    scope, body = advisory.body_for(caller, 'research_compare_start',
        {'urls': ['https://a.invalid', 'https://b.invalid'], 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    scope, body = advisory.body_for(caller, 'research_save', {'path': 'docs/research/comparison.md', 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert policy.level == 'confidential' and result['saved_to_sandbox']
    assert prepared['source_context']['caller_agent'] == 'analyst'
    assert prepared['source_context']['origin_run_id'] == caller.run_id != workspace.parent
    assert workspace.service._session()._read()['run_id'] == workspace.parent
    assert get_run(workspace.parent)['run']['agent'] == 'developer'
    assert workspace.guest['docs/research/comparison.md'].startswith(b'PRIVATE_GENERATED_COMPARISON')
    journal = json.loads((workspace.controller.task_dir(workspace.task) / 'files.json').read_text())
    assert journal['source_floor'] == 'confidential' and not advisory.state.sent


@pytest.mark.parametrize('changed', ['owner', 'session', 'role'])
def test_adoption_refuses_unverified_target_actor_before_any_guest_write(
    advisory, workspace, immediate_workers, monkeypatch, tmp_path, changed,
):
    monkeypatch.setattr(admin, '_selfedit_service', workspace.service)
    monkeypatch.setattr(admin, 'authoring_enabled', lambda: True)
    with user_id_scope('alice'):
        target = RunLogger(workspace.parent, 'developer', 'Actual target', 'public task',
                           session_id=advisory.session, root=tmp_path)
        target.start()
    from jarvis.db import get_conn
    field, value = {'owner': ('user_id', 'foreign-owner'), 'session': ('session_id', str(uuid.uuid4())),
                    'role': ('agent', 'analyst')}[changed]
    with get_conn() as connection:
        connection.execute(f'UPDATE agent_runs SET {field}=? WHERE run_id=?', (value, workspace.parent))
    caller = advisory.caller()
    scope, body = advisory.body_for(caller)
    pin, prepared, _ = advisory.prepare(scope, body)
    advisory.execute(scope, body, pin, prepared)
    scope, body = advisory.body_for(caller, 'plan_adopt', {'path': 'docs/plans/public-plan.md', 'confirm': True})
    pin, prepared, _ = advisory.prepare(scope, body)
    _, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result == {'ok': False, 'error': 'advisory_operation_failed'}
    assert not workspace.calls and 'docs/plans/public-plan.md' not in workspace.guest


def test_raw_council_candidates_cannot_approve_choose_through_json_labels(advisory, monkeypatch):
    recorded = []
    monkeypatch.setattr(admin.council_mod, 'record_user_choice', lambda *args: recorded.append(args))
    admin._plan_job.update(state='awaiting_choice', run_id=str(uuid.uuid4()), round_id='unverified-round',
        candidates=[{'label': 'Proposal A', 'profile': 'frontier-one', 'content': 'PRIVATE_CANDIDATE_CANARY',
                     'privacy': 'approved_external'}])
    caller = advisory.caller()
    scope, body = advisory.body_for(caller, 'plan_choose', {'label': 'Proposal A'})
    with pytest.raises(HTTPException):
        advisory.prepare(scope, body)
    assert not recorded and not advisory.state.clients


def test_actual_crawl_retains_origin_evidence_and_never_approves_returned_url_labels():
    from jarvis.research import crawl
    result = crawl.crawl_site(SimpleNamespace(post=lambda *args, **kwargs: (200, {
        'results': [{'url': 'http://127.0.0.1/private', 'raw_content': 'PRIVATE_CRAWL_CANARY',
                     'privacy': 'approved_external'}], 'usage': {'credits': 1}})),
        'https://public.invalid', 'public comparison', 'synthetic-unused')
    assert result._source_evidence.requested_url == 'https://public.invalid'
    assert result._source_evidence.transport_endpoint == crawl.TAVILY_CRAWL_URL
    assert result._source_evidence.page_origin_verified is False
    assert crawl.crawl_source_policy(result).level == 'confidential'
    assert '_source_evidence' not in json.dumps(result) and 'synthetic-unused' not in repr(result._source_evidence)


def test_forged_crawl_json_labels_cannot_approve_unknown_acquired_bytes():
    from jarvis.research import crawl
    assert crawl.crawl_source_policy({'ok': True, 'privacy': 'approved_external',
        'source_policy': {'level': 'approved_external'}, 'page_origin_verified': True,
        'content': 'PRIVATE_CRAWL_CANARY'}).level == 'confidential'
