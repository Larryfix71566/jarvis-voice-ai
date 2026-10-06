"""Ordinary MCP hidden receipts over real inert host workspace records."""
import asyncio
import json
import os
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from mcp.server.fastmcp import Context
from mcp.shared.context import RequestContext
from mcp.types import RequestParams

from jarvis import development_attestation as attestation, development_sources as sources
from jarvis.auth import ClientIdentity
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.db import get_conn, run_migrations
from jarvis.model_routing import ModelRouteError
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.runlog.context import run_logger_scope
from jarvis.runlog.store import RunLogger, get_run
from jarvis.skill_runtime import update_runtime_inventory
from jarvis.skills.registry import _ToolSourceContract
from jarvis.tenant import user_id_scope
from tests.unit.test_development_sources import workspace
from tests.unit.test_registry_source_policy import registry_for

CANARY = 'SYNTHETIC_PRIVATE_ORDINARY_SOURCE_93745'


@pytest.fixture
def bridge(workspace, tmp_path, monkeypatch):
    from jarvis.admin import server as admin
    from mcp_servers.mcp_selfedit import server

    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'database.sqlite'))
    monkeypatch.setenv('MORTIMER_SANDBOX_HOME', str(workspace.controller.home))
    monkeypatch.delenv('JARVIS_UPGRADE_PROFILE', raising=False)
    monkeypatch.setattr(attestation, '_issuers', {})
    monkeypatch.setattr(attestation, '_inflight_leases', set())
    monkeypatch.setattr(attestation, '_challenges', {})
    monkeypatch.setattr(admin, '_workspace_preparations', {})
    monkeypatch.setattr(admin, '_selfedit_service', workspace.service)
    monkeypatch.setattr(admin, 'auth_enabled', lambda: True)
    monkeypatch.setattr(admin, '_busy', lambda: False)
    monkeypatch.setattr(admin, '_opening_job', {'state': 'idle', 'run_id': None})
    monkeypatch.setattr(admin, '_run_job', {'state': 'idle', 'run_id': None})
    monkeypatch.setattr(admin, '_finish_job', {'state': 'idle', 'run_id': None})
    monkeypatch.setattr(admin, '_selfedit_stagings', {})
    monkeypatch.setattr(admin, 'selfedit_models', lambda: {'ok': True, 'models': [
        {'name': 'public-fixture', 'default': True, 'key_present': True}]})
    owner, session_id, parent = 'ordinary-owner', str(uuid.uuid4()), str(uuid.uuid4())
    run_migrations()
    with user_id_scope(owner):
        retained = RunLogger(workspace.parent, 'developer', 'Developer', 'public preview', session_id=session_id, root=tmp_path)
        retained.start()
        retained.finish('previewed')
        logger = RunLogger(parent, 'developer', 'Developer', 'public confirmation', session_id=session_id, root=tmp_path)
        logger.start()
    update_runtime_inventory(session_id, [], True, active=True, owner_id=owner)
    request = SimpleNamespace(scope={'client_identity': ClientIdentity('service-bot', 'service-owner')})
    calls = []

    class Admin:
        def post(self, path, json):
            calls.append((path, json))
            if path.endswith('/associate'):
                return admin.associate_workspace_source(admin.WorkspaceSourceAssociationIn(**json), request)
            if path.endswith('/prepare'):
                return admin.prepare_workspace_source(admin.WorkspaceSourcePrepareIn(**json), request)
            assert path.endswith('/tool')
            return admin.execute_workspace_source(admin.WorkspaceSourceToolIn(**json), request)

    monkeypatch.setattr(server, '_client', Admin())
    phases = []

    class Session:
        async def call_tool(self, name, arguments, *, meta=None):
            phases.append(meta['mortimer_development_source']['phase'] if meta else 'legacy')
            context = Context(request_context=RequestContext(1,
                RequestParams.Meta.model_validate(meta) if meta else None, None, None), fastmcp=server.mcp)
            values = dict(arguments)
            result = getattr(server, name)(**values, ctx=context)
            return result

    child = Session()
    registry = registry_for('selfedit_read', 'mcp-selfedit', child, pinned=True)
    registry._source_contracts['mcp-selfedit'] = _ToolSourceContract('mcp-selfedit',
        'mcp_servers.mcp_selfedit.server', child, local_admin=True)
    holder = SensitiveTurn()
    token = current_sensitive_turn.set(holder)

    async def call(name='selfedit_read', arguments=None, level='approved_external'):
        arguments = {'path': 'jarvis/app.py'} if arguments is None else arguments
        registry._tools[name] = ('mcp-selfedit', SimpleNamespace(name=name, inputSchema={}))
        scope = make_tool_execution_scope(parent, 'ordinary-task', 'call-' + uuid.uuid4().hex,
            name, arguments, DataPolicy(level, 'caller-input'))
        with run_logger_scope(logger):
            value = await registry.call_classified(name, arguments, execution_scope=scope)
        policy, content = validate_tool_result(scope, value)
        return policy, json.loads(content), value

    yield SimpleNamespace(w=workspace, admin=admin, request=request, logger=logger, retained=retained,
        owner=owner, session_id=session_id, parent=parent, registry=registry, child=child,
        phases=phases, calls=calls, call=call, holder=holder)
    current_sensitive_turn.reset(token)
    update_runtime_inventory(session_id, [], True, active=False, owner_id=owner)
    for issuer in attestation._issuers.values():
        os.close(issuer.lease)


async def test_new_developer_turn_reads_exact_retained_project_bytes_before_sinks(bridge):
    policy, result, envelope = await bridge.call()
    assert policy.level == 'approved_external'
    assert result == {'ok': True, 'path': 'jarvis/app.py', 'content': 'print("public code")\n'}
    assert bridge.parent != bridge.w.parent
    assert bridge.phases == ['associate', 'prepare', 'execute']
    assert len(bridge.w.calls) == 1 and not bridge.holder.is_armed()
    assert 'source_receipt' not in result and '_seal' not in json.dumps(result)
    assert 'print("public code")' not in repr(envelope)
    assert get_run(bridge.parent)['run']['status'] == 'running'


async def test_actual_private_read_remains_protected_before_early_mcp_buffer(bridge):
    policy, result, _ = await bridge.call(arguments={'path': 'docs/private-report.txt'})
    assert policy.level == 'confidential' and result['content'].startswith('SYNTHETIC_PRIVATE_SOURCE')
    assert bridge.holder.is_armed() and bridge.logger._sensitive
    assert 'SYNTHETIC_PRIVATE_SOURCE' not in json.dumps(bridge.logger._buffer)


async def test_human_only_proposal_preserves_exact_installed_spoken_transform(bridge):
    policy, result, _ = await bridge.call('selfedit_write', {'path': 'config/protected.json',
        'content': '{"public": true}\n', 'rationale': 'public fixture'})
    assert policy.level == 'approved_external', result
    assert result['proposal'] is True and 'Larry to approve' in result['summary']
    assert result['summary'].endswith('Keep writing the rest, then call selfedit_finish.')
    assert bridge.w.guest['config/protected.json'] == b'{}'
    assert bridge.w.guest[result['proposal_file']].startswith(b'HUMAN-ONLY PROPOSAL')


@pytest.mark.parametrize('field', ['user_id', 'session_id', 'agent', 'status'])
async def test_unrelated_current_caller_is_refused_before_admin_or_guest(bridge, field):
    replacement = {'user_id': 'other-owner', 'session_id': str(uuid.uuid4()),
                   'agent': 'research', 'status': 'completed'}[field]
    with get_conn() as conn:
        conn.execute('UPDATE agent_runs SET ' + field + '=? WHERE run_id=?', (replacement, bridge.parent))
        conn.commit()
    policy, result, _ = await bridge.call()
    assert result == {'ok': False, 'error': 'workspace_source_unavailable'}
    assert not bridge.calls and not bridge.w.calls


@pytest.mark.parametrize('field', ['user_id', 'session_id', 'agent'])
async def test_retained_foreign_job_never_becomes_new_caller_scope(bridge, field):
    replacement = {'user_id': 'other-owner', 'session_id': str(uuid.uuid4()), 'agent': 'research'}[field]
    with get_conn() as conn:
        conn.execute('UPDATE agent_runs SET ' + field + '=? WHERE run_id=?', (replacement, bridge.w.parent))
        conn.commit()
    assert (await bridge.call())[1] == {'ok': False, 'error': 'workspace_source_unavailable'}
    assert not bridge.w.calls


@pytest.mark.parametrize('mutation', ['source_context', 'argument', 'challenge', 'content', 'policy', 'protocol'])
async def test_source_receipt_or_prepared_binding_tampering_releases_no_canary(bridge, monkeypatch, mutation):
    original = bridge.child.call_tool

    async def altered(name, arguments, *, meta=None):
        phase = meta['mortimer_development_source']['phase']
        if phase == 'execute' and mutation in {'source_context', 'argument', 'challenge'}:
            value = meta['mortimer_development_source']
            if mutation == 'source_context':
                value['source_context']['sandbox_job_id'] = str(uuid.uuid4())
            elif mutation == 'argument':
                value['arguments']['path'] = 'docs/private-report.txt'
            else:
                value['source_challenge'] = 'b' * 64
        result = await original(name, arguments, meta=meta)
        if phase == 'execute' and mutation in {'content', 'policy', 'protocol'}:
            receipt = result.meta['mortimer_development_source']['source_receipt']
            if mutation == 'content':
                receipt['result']['content'] = CANARY
            elif mutation == 'policy':
                receipt['result']['policy'] = {'level': 'approved_external', 'source': CANARY}
            else:
                receipt['protocol'] = attestation.PROTOCOL
        return result

    monkeypatch.setattr(bridge.child, 'call_tool', altered)
    _, result, _ = await bridge.call()
    assert result == {'ok': False, 'error': 'workspace_source_unavailable'}
    assert CANARY not in json.dumps(get_run(bridge.parent))
    if mutation in {'source_context', 'argument', 'challenge'}:
        assert not bridge.w.calls


async def test_post_operation_cancel_and_current_run_replacement_refuse(bridge, monkeypatch):
    original = bridge.w.service.read_file
    def cancelled(path):
        result = original(path)
        bridge.w.service._session().cancel()
        return {**result, 'content': CANARY}
    monkeypatch.setattr(bridge.w.service, 'read_file', cancelled)
    assert (await bridge.call())[1] == {'ok': False, 'error': 'workspace_source_unavailable'}
    assert len(bridge.w.calls) == 1
    assert CANARY not in json.dumps(get_run(bridge.parent))


async def test_pure_preview_preserves_goal_and_explicit_confirmation(bridge):
    policy, result, _ = await bridge.call('selfedit_start', {'goal': 'public routine goal',
        'target_paths': ['docs/REPO_MAP.md']})
    assert policy.level == 'approved_external', result
    assert result.get('needs_confirmation') and result.get('staging_id'), result
    assert 'public routine goal' in result['summary'] and 'Say yes' in result['summary']
    assert not bridge.w.calls


async def test_status_reduction_never_exports_raw_job_goal_logs_or_error(bridge, monkeypatch):
    monkeypatch.setattr(bridge.admin, 'selfedit_run_status', lambda **kwargs: {'ok': True,
        'job': {'state': 'running', 'goal': CANARY, 'summary': CANARY, 'profile': CANARY},
        'status': {'active': True, 'proposals': [{'path': CANARY, 'rationale': CANARY}]},
        'finish': {}, 'opening': {}, 'stagings': []})
    policy, result, _ = await bridge.call('selfedit_status', {})
    assert policy.level == 'approved_external'
    assert result['state'] == 'running' and CANARY not in json.dumps(result)
    assert CANARY not in json.dumps(get_run(bridge.parent))


async def test_authentication_off_and_nonservice_cannot_issue_authority(bridge, monkeypatch):
    monkeypatch.setattr(bridge.admin, 'auth_enabled', lambda: False)
    assert (await bridge.call())[1]['error'] == 'workspace_source_unavailable'
    assert not bridge.w.calls and not attestation._issuers


def test_floor_journal_is_monotonic_content_free_and_owner_bound(bridge):
    attestation.ensure_admin_source_authority()
    run = get_run(bridge.w.parent)['run']
    sources.retain_workspace_floor(run, DataPolicy('local_only', 'caller'))
    sources.retain_workspace_floor(run, DataPolicy('approved_external', 'forged-public-label'))
    assert sources.workspace_floor(run).level == 'local_only'
    current = get_run(bridge.parent)['run']
    context = sources.ordinary_context(bridge.w.service, current, run,
        workspace_kind='selfedit', lineage_id=bridge.w.state['id'])
    assert context.input_floor.level == 'local_only'
    record = sources._workspace_floor_path(run)
    assert record.stat().st_mode & 0o777 == 0o600
    assert CANARY not in record.read_text() and 'source' not in record.read_text()
    context_pin = context._journal_pins[-1]
    assert context_pin[3] is not None
    duplicate = record.with_suffix('.replacement')
    duplicate.write_bytes(record.read_bytes())
    duplicate.chmod(0o600)
    duplicate.replace(record)
    with pytest.raises(ModelRouteError, match='workspace_source_floor_changed'):
        sources._verify_workspace_floor_pins(context)


def test_missing_parent_symlink_cannot_hide_retained_private_floor(bridge):
    attestation.ensure_admin_source_authority()
    run = get_run(bridge.w.parent)['run']
    sources.retain_workspace_floor(run, DataPolicy('local_only', 'private-goal'))
    path = sources._workspace_floor_path(run)
    parent = path.parent
    backup = parent.with_name(parent.name + '-backup')
    parent.rename(backup)
    parent.symlink_to(parent.with_name('missing-directory'), target_is_directory=True)
    with pytest.raises(ModelRouteError):
        sources.workspace_floor(run)


@pytest.mark.parametrize('ancestor', ['owner', 'workspace-floors'])
def test_missing_earlier_ancestor_symlink_cannot_hide_retained_private_floor(bridge, ancestor):
    attestation.ensure_admin_source_authority()
    run = get_run(bridge.w.parent)['run']
    sources.retain_workspace_floor(run, DataPolicy('local_only', 'private-goal'))
    path = sources._workspace_floor_path(run)
    parent = path.parent.parent if ancestor == 'owner' else path.parent.parent.parent
    backup = parent.with_name(parent.name + '-backup')
    parent.rename(backup)
    parent.symlink_to(parent.with_name('missing-directory'), target_is_directory=True)
    with pytest.raises(ModelRouteError):
        sources.workspace_floor(run)


async def test_retained_local_goal_floor_survives_new_turn_without_any_file_write(bridge):
    attestation.ensure_admin_source_authority()
    sources.retain_workspace_floor(get_run(bridge.w.parent)['run'], DataPolicy('local_only', 'private-goal'))
    policy, result, _ = await bridge.call('selfedit_status', {})
    assert policy.level == 'local_only' and result['ok']
    assert not bridge.w.calls
    assert sources.workspace_floor(get_run(bridge.parent)['run']).level == 'local_only'
    assert bridge.holder.is_armed()


@pytest.mark.parametrize('mutation', ['replace', 'symlink', 'hardlink', 'invalid-json', 'wrong-owner', 'wrong-session'])
async def test_floor_journal_replacement_or_forged_binding_fails_before_guest(bridge, monkeypatch, mutation):
    original = bridge.child.call_tool
    async def changed(name, arguments, *, meta=None):
        result = await original(name, arguments, meta=meta)
        if meta['mortimer_development_source']['phase'] == 'prepare':
            path = sources._workspace_floor_path(get_run(bridge.parent)['run'])
            replacement = path.with_suffix('.replacement')
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            if mutation == 'replace':
                replacement.replace(path)
            elif mutation == 'symlink':
                path.unlink()
                path.symlink_to(replacement)
            elif mutation == 'hardlink':
                os.link(path, replacement.with_suffix('.hardlink'))
            elif mutation == 'invalid-json':
                path.write_text('{')
            else:
                value = json.loads(path.read_text())
                value['owner_id' if mutation == 'wrong-owner' else 'bot_session_id'] = 'other-owner' if mutation == 'wrong-owner' else str(uuid.uuid4())
                path.write_text(json.dumps(value))
        return result
    monkeypatch.setattr(bridge.child, 'call_tool', changed)
    policy, result, _ = await bridge.call()
    assert result.get('ok') is False and not bridge.w.calls


async def test_actual_local_only_floor_precedes_lost_ack_write_and_later_read(bridge, monkeypatch):
    attestation.ensure_admin_source_authority()
    sources.retain_workspace_floor(get_run(bridge.w.parent)['run'], DataPolicy('local_only', 'private-goal'))
    original = bridge.w.controller.rpc
    observed = []
    def lost(task, call):
        result = original(task, call)
        if call['operation'] == 'write':
            journal = json.loads((bridge.w.controller.task_dir(task) / 'files.json').read_text())
            observed.append(journal['source_floor'])
            raise RuntimeError(CANARY)
        return result
    monkeypatch.setattr(bridge.w.controller, 'rpc', lost)
    policy, result, _ = await bridge.call('selfedit_write', {'path': 'jarvis/app.py',
        'content': 'print("private goal derivative")\n', 'rationale': 'fixture'})
    assert policy.level == 'local_only' and result['ok'] is False
    assert observed == ['local_only']
    assert CANARY not in json.dumps(result) and CANARY not in json.dumps(get_run(bridge.parent))
    assert sources.workspace_floor(get_run(bridge.parent)['run']).level == 'local_only'
    monkeypatch.setattr(bridge.w.controller, 'rpc', original)
    fresh = current_sensitive_turn.set(SensitiveTurn())
    try:
        assert (await bridge.call())[0].level == 'local_only'
    finally:
        current_sensitive_turn.reset(fresh)


@pytest.mark.parametrize('path,level', [('docs/REPO_MAP.md', 'approved_external'),
                                       ('docs/private-plan.txt', 'confidential')])
async def test_seeded_start_threads_actual_host_plan_policy_without_provider(bridge, monkeypatch, path, level):
    from mcp_servers.mcp_repo import logic as repo_logic
    root = bridge.w.service.repo_root
    (root / 'docs').mkdir()
    (root / path).write_text('public plan fixture' if level == 'approved_external' else CANARY)
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(root))
    launched = []
    class Thread:
        def __init__(self, *, target, args, daemon, kwargs=None):
            launched.append((target, args, kwargs or {}))
        def start(self):
            pass  # An inert captured worker; no agent/provider/VM invocation.
    monkeypatch.setattr(bridge.admin.threading, 'Thread', Thread)
    monkeypatch.setattr(bridge.admin, '_make_agent', lambda *args: SimpleNamespace(model_label=lambda: 'public-fixture'))
    policy, result, _ = await bridge.call('selfedit_start', {'goal': 'public seeded goal', 'confirm': True,
                                                         'plan_path': path})
    assert result['ok'] is True and len(launched) == 1, result
    assert policy.level == level
    _, worker_args, kwargs = launched[0]
    assert worker_args[2] == ('public plan fixture' if level == 'approved_external' else CANARY)
    assert kwargs['plan_policy'].level == level
    assert kwargs['data_policy'].level == 'approved_external'
    assert sources.workspace_floor(get_run(bridge.parent)['run']).level == level
    assert not bridge.w.calls


async def test_changed_plan_bytes_cannot_reuse_earlier_approved_source_policy(bridge, monkeypatch):
    from mcp_servers.mcp_repo import logic as repo_logic
    root = bridge.w.service.repo_root
    (root / 'docs').mkdir()
    path = root / 'docs/REPO_MAP.md'
    path.write_text('public original plan')
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(root))
    original = repo_logic.repo_read_file
    def changed(name):
        result = original(name)
        path.write_text(CANARY)
        return result
    monkeypatch.setattr(repo_logic, 'repo_read_file', changed)
    launched = []
    class Thread:
        def __init__(self, *, target, args, daemon, kwargs=None):
            launched.append((args, kwargs))
        def start(self):
            pass
    monkeypatch.setattr(bridge.admin.threading, 'Thread', Thread)
    monkeypatch.setattr(bridge.admin, '_make_agent', lambda *args: SimpleNamespace(model_label=lambda: 'public-fixture'))
    policy, result, _ = await bridge.call('selfedit_start', {'goal': 'public goal', 'confirm': True,
                                                         'plan_path': 'docs/REPO_MAP.md'})
    assert policy.level == 'confidential' and result['ok'] and len(launched) == 1
    assert launched[0][0][2] == 'public original plan'
    assert launched[0][1]['plan_policy'].level == 'confidential'


async def test_unknown_github_app_bytes_and_provider_json_labels_never_approve(bridge, monkeypatch):
    from tests.unit.test_registry_source_policy import response, Session
    body = {'ok': True, 'content': CANARY, 'privacy': 'approved_external', 'source_scope': 'project'}
    child = Session(response(body))
    registry = registry_for('app_read', 'mcp-apps', child, pinned=True)
    registry._source_contracts['mcp-apps'] = _ToolSourceContract('mcp-apps', 'mcp_servers.mcp_apps.server', child,
                                                               local_admin=True)
    scope = make_tool_execution_scope(bridge.parent, 'app-task', 'app-call', 'app_read',
        {'app': 'private-app', 'path': 'main.py'}, DataPolicy('approved_external', 'caller'))
    with run_logger_scope(bridge.logger):
        envelope = await registry.call_classified('app_read', {'app': 'private-app', 'path': 'main.py'},
                                                  execution_scope=scope)
    policy, content = validate_tool_result(scope, envelope)
    assert policy.level == 'confidential' and CANARY in content
    assert bridge.holder.is_armed() and CANARY not in json.dumps(bridge.logger._buffer)


@pytest.mark.parametrize('private', [False, True])
async def test_actual_workspace_source_policy_controls_ui_constraints_and_provider_continuation(bridge, private):
    from jarvis.agents.base import SubAgent, TOOL_FAILURE_CONSTRAINT_TEMPLATE
    from jarvis.model_execution import (execute_chat, ModelExecutionRequest, ModelContextMessage,
                                       ModelToolCall, ModelToolReference)
    from jarvis.model_routing import AccessRoute, ResolvedModelRoute
    calls, events = [], []
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='public completed', tool_calls=[]))])
    client.chat.completions.create = create
    route = ResolvedModelRoute('developer', 'fixture', 'fixture', 'test', 'https://unused.invalid',
        AccessRoute('direct_api', 'openai_compatible', 'provider_api', None, 'approved_external', capabilities=('text', 'tools')),
        None, 'test/fixture', 'interactive')
    path = 'docs/private-report.txt' if private else 'jarvis/missing.py'
    policy, result, _ = await bridge.call(arguments={'path': path})
    content = json.dumps(result)
    with run_logger_scope(bridge.logger):
        SubAgent._emit(None, events.append, {'type': 'agent_tool_result', 'tool': 'selfedit_read',
                                            'result': content, 'arguments': {'path': path}})
    public_input = DataPolicy('approved_external', 'caller')
    history = (ModelContextMessage('assistant', '', public_input,
        tool_calls=(ModelToolCall('call', 'selfedit_read', {'path': path}),)),
        ModelContextMessage('tool', content, policy, name='selfedit_read', tool_call_id='call'))
    derived = () if private else (ModelContextMessage('system', TOOL_FAILURE_CONSTRAINT_TEMPLATE.format(
        tool_name='selfedit_read', error=result['error']), policy),)
    request = ModelExecutionRequest('developer', 'continued-task', bridge.parent, 'public task',
        context=history + derived, tools=(ModelToolReference('selfedit_read',
        {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}),), data_policy=public_input)
    if private:
        with pytest.raises(ModelRouteError):
            await execute_chat(request, route, client_factory=lambda _: pytest.fail('private source built a provider'))
        assert calls == [] and derived == ()
        assert events == [{'type': 'agent_tool_result', 'tool': 'selfedit_read', 'run_id': bridge.parent}]
    else:
        await execute_chat(request, route, client_factory=lambda _: client)
        assert len(calls) == 1 and result == {'ok': False, 'error': 'development_operation_failed'}
    canary = 'SYNTHETIC_PRIVATE_SOURCE_70419'
    assert canary not in repr(calls) + repr(events) + repr(derived) + repr(bridge.logger._buffer)
    assert 'source_receipt' not in repr(calls) and 'canonical_refs' not in repr(calls)


@pytest.mark.parametrize('forged', [False, True])
async def test_retired_app_writer_fixed_host_refusal_preserves_useful_guidance(bridge, forged):
    from mcp_servers.development_boundary import sandbox_required
    from tests.unit.test_registry_source_policy import response, Session
    body = sandbox_required(application=True)
    if forged:
        body['error'] += CANARY
    child = Session(response(body))
    registry = registry_for('app_write_file', 'mcp-apps', child, pinned=True)
    arguments = {'app': 'public-fixture', 'path': 'src/app.py', 'content': 'public fixture'}
    scope = make_tool_execution_scope(bridge.parent, 'app-task', 'app-call', 'app_write_file', arguments,
                                     DataPolicy('approved_external', 'caller'))
    with run_logger_scope(bridge.logger):
        envelope = await registry.call_classified('app_write_file', arguments, execution_scope=scope)
    policy, content = validate_tool_result(scope, envelope)
    assert policy.level == ('confidential' if forged else 'approved_external')
    if not forged:
        assert json.loads(content) == sandbox_required(application=True)
