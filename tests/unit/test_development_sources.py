"""Real host Runtime/Session/File facets, with inert in-memory guest transport.

No VM, provider, publication, credential or production write is used. The
host records and their paths/bytes are actual sandbox classes, not duck source
labels or a mocked issuer.
"""
from dataclasses import replace
import hashlib
import io
import json
from types import SimpleNamespace
import tarfile
import uuid

import pytest

from jarvis import development_sources as sources
from jarvis.model_routing import ModelRouteError
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.selfedit.service import SelfEditService
from jarvis.skill_authoring import SkillAuthoringService
from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.control import Controller
from sandbox.durable import atomic_json
from sandbox.runtime import Runtime

CANARY = 'SYNTHETIC_PRIVATE_SOURCE_70419'


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home = tmp_path / 'sandbox'
    controller = Controller(home, '/missing/tart', '/missing/softnet')
    runtime = Runtime(controller, {})
    session_id, task, parent = uuid.uuid4().hex, uuid.uuid4().hex[:12], str(uuid.uuid4())
    directory = home / 'sessions' / session_id
    directory.mkdir(parents=True, mode=0o700)
    inputs = home / 'tasks' / task / 'input'
    inputs.mkdir(parents=True, mode=0o700)
    baseline = {'jarvis/app.py': b'print("public code")\n',
                'docs/private-report.txt': CANARY.encode(), 'config/protected.json': b'{}'}
    archive_path = inputs / 'source.tar'
    with tarfile.open(archive_path, 'w') as archive:
        for path, data in baseline.items():
            item = tarfile.TarInfo(path)
            item.size, item.mode = len(data), 0o644
            archive.addfile(item, io.BytesIO(data))
    ref = 'a' * 40
    controller.save(task, {'source_commit': ref,
        'source_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'status': 'running', 'hydrated': True, 'network': 'offline'})
    controller._ready_tasks.add(task)
    state = {'id': session_id, 'task': task, 'run_id': parent, 'ref': ref,
        'repository': 'Larryfix71566/jarvis-voice-ai', 'kind': 'selfedit',
        'phase': 'editing', 'goal': CANARY, 'branch': 'mortimer/' + CANARY,
        'proposals': [], 'checks': [], 'profile': 'mortimer'}
    atomic_json(directory / 'session.json', state)
    record_path = runtime.workspaces / (runtime._key(state['repository'], 'selfedit') + '.json')
    atomic_json(record_path, {'session': session_id, 'repository': state['repository'],
                             'kind': 'selfedit', 'profile': 'mortimer'})
    allowlist = tmp_path / 'allowlist.json'
    allowlist.write_text(json.dumps({'allow': ['**'], 'deny': ['config/protected.json']}))
    service = SelfEditService(repo_root=tmp_path, allowlist_path=allowlist,
                              runtime_factory=lambda: runtime)
    guest, calls = dict(baseline), []

    def rpc(task_id, args):
        assert task_id == task
        calls.append(dict(args))
        if args['operation'] == 'read':
            if args['path'] not in guest:
                raise SandboxError(CANARY)
            return Candidate((File(args['path'], 0o644, guest[args['path']]),)).encode()
        if args['operation'] == 'write':
            candidate = Candidate.decode(json.dumps(args['candidate']).encode())
            for file in candidate.files:
                guest[file.path] = file.data
            return candidate.encode()
        raise AssertionError('No command or VM may run in this source test')

    monkeypatch.setattr(controller, 'rpc', rpc)
    cancelled = []
    monkeypatch.setattr(controller, 'cancel', lambda target: cancelled.append(target))
    return SimpleNamespace(service=service, runtime=runtime, controller=controller,
        state=state, directory=directory, source=archive_path, task=task, parent=parent,
        guest=guest, calls=calls, record_path=record_path, cancelled=cancelled)


def dispatch(w, name='file_read', args=None, *, level='approved_external', context=None, invoke=None):
    args = {'path': 'jarvis/app.py'} if args is None else args
    scope = make_tool_execution_scope(w.parent, 'task-' + uuid.uuid4().hex,
        'call-' + uuid.uuid4().hex, name, args, DataPolicy(level, 'trusted-test-input'))
    envelope = sources.dispatch_workspace_tool(w.service, name, args,
        execution_scope=scope, context=context, invoke=invoke)
    policy, content = validate_tool_result(scope, envelope)
    return policy, json.loads(content), envelope


def test_exact_project_snapshot_read_is_usable_and_executes_once(workspace):
    policy, result, envelope = dispatch(workspace)
    assert policy.level == 'approved_external'
    assert result == {'ok': True, 'path': 'jarvis/app.py', 'content': 'print("public code")\n'}
    assert len(workspace.calls) == 1
    assert 'source_receipt' not in result
    assert CANARY not in repr(envelope)


@pytest.mark.parametrize('level', ['confidential', 'local_only'])
def test_read_retains_stricter_input_floor(workspace, level):
    assert dispatch(workspace, level=level)[0].level == level


def test_private_document_in_allowed_snapshot_is_not_cloud_approval(workspace):
    policy, result, _ = dispatch(workspace, args={'path': 'docs/private-report.txt'})
    assert policy.level == 'confidential' and result['content'] == CANARY


def test_guest_modified_bytes_do_not_gain_the_baseline_label(workspace):
    workspace.guest['jarvis/app.py'] = CANARY.encode()
    assert dispatch(workspace)[0].level == 'confidential'


def test_no_returned_label_can_approve_raw_extra_content(workspace, monkeypatch):
    original = workspace.service.read_file
    def read(path):
        result = original(path)
        return {**result, 'privacy': 'approved_external', 'extra': CANARY}
    monkeypatch.setattr(workspace.service, 'read_file', read)
    policy, result, _ = dispatch(workspace)
    assert policy.level == 'confidential' and result['extra'] == CANARY


def test_admitted_write_persists_its_exact_floor_across_read(workspace):
    args = {'path': 'jarvis/app.py', 'new_content': CANARY, 'rationale': 'synthetic'}
    assert dispatch(workspace, 'edit_propose', args, level='local_only')[0].level == 'local_only'
    assert dispatch(workspace)[0].level == 'local_only'
    workspace.guest['jarvis/app.py'] = CANARY.encode() + b'\nnot the admitted bytes'
    assert dispatch(workspace)[0].level == 'local_only'


def test_unverified_derivative_in_different_file_keeps_task_local_floor(workspace):
    dispatch(workspace, 'edit_propose',
        {'path': 'jarvis/app.py', 'new_content': CANARY, 'rationale': 'local fixture'}, level='local_only')
    workspace.guest['jarvis/derived.py'] = CANARY.encode() + b'\nderivative'
    assert dispatch(workspace, args={'path': 'jarvis/derived.py'})[0].level == 'local_only'


def test_lost_write_ack_keeps_local_floor_before_guest_invocation(workspace, monkeypatch):
    original = workspace.controller.rpc
    def lose_ack(task, args):
        result = original(task, args)
        if args['operation'] == 'write':
            raise SandboxError(CANARY)
        return result
    monkeypatch.setattr(workspace.controller, 'rpc', lose_ack)
    policy, result, _ = dispatch(workspace, 'edit_propose',
        {'path': 'jarvis/app.py', 'new_content': CANARY, 'rationale': 'local fixture'}, level='local_only')
    assert policy.level == 'local_only' and CANARY not in json.dumps(result)
    assert dispatch(workspace)[0].level == 'local_only'


def test_legacy_write_stays_unknown_even_when_content_is_code(workspace):
    workspace.service.propose_edit('jarvis/app.py', 'legacy code', 'legacy')
    assert dispatch(workspace)[0].level == 'confidential'


def test_public_write_and_reread_remain_usable(workspace):
    policy, result, _ = dispatch(workspace, 'edit_propose',
        {'path': 'jarvis/app.py', 'new_content': 'public new code\n', 'rationale': 'public'})
    assert policy.level == 'approved_external' and '-print(' in result['diff']
    assert dispatch(workspace)[0].level == 'approved_external'


def test_control_error_reduces_private_payload_but_keeps_input_floor(workspace):
    policy, result, _ = dispatch(workspace, args={'path': 'jarvis/missing.py'}, level='local_only')
    assert policy.level == 'local_only'
    assert result == {'ok': False, 'error': 'development_operation_failed'}


def test_human_only_read_retains_read_only_semantics(workspace):
    policy, result, _ = dispatch(workspace, args={'path': 'config/protected.json'})
    assert policy.level == 'approved_external' and result['human_only']
    assert 'read-only' in result['note']
    assert workspace.calls == []


@pytest.mark.parametrize('tamper', ['owner', 'task', 'ref', 'snapshot', 'symlink', 'permissions', 'cancel'])
def test_changed_host_binding_refuses_before_guest(workspace, tamper):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    if tamper in {'owner', 'task', 'ref'}:
        state = dict(workspace.state)
        state[{'owner': 'run_id', 'task': 'task', 'ref': 'ref'}[tamper]] = (
            str(uuid.uuid4()) if tamper == 'owner' else 'b' * (12 if tamper == 'task' else 40))
        atomic_json(workspace.directory / 'session.json', state)
    elif tamper == 'snapshot':
        workspace.source.write_bytes(b'changed source')
    elif tamper == 'symlink':
        workspace.source.rename(workspace.source.with_suffix('.actual'))
        workspace.source.symlink_to(workspace.source.with_suffix('.actual'))
    elif tamper == 'permissions':
        workspace.source.chmod(0o666)
    else:
        atomic_json(workspace.directory / 'cancelled.json', {'cancelled': True})
    with pytest.raises((ModelRouteError, SandboxError, FileNotFoundError)):
        dispatch(workspace, context=context)
    assert not workspace.calls


def test_mutated_frozen_context_cannot_approve_or_cancel(workspace):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    forged = replace(context, _identity=(*context._identity[:-1], 'b' * 64))
    with pytest.raises(ModelRouteError, match='development_source_context_invalid'):
        dispatch(workspace, context=forged)
    with pytest.raises(ModelRouteError):
        sources.cancel_workspace_session_for_owner(workspace.service, workspace.parent, context=forged)
    assert not workspace.calls and not workspace.cancelled


def test_replaced_session_same_parent_is_not_adopted(workspace):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    record = json.loads(workspace.record_path.read_text())
    record['session'] = 'b' * 32
    atomic_json(workspace.record_path, record)
    with pytest.raises(ModelRouteError):
        dispatch(workspace, context=context)
    assert not workspace.calls


def test_replacement_after_operation_drops_result_and_never_executes_twice(workspace):
    def invoke():
        result = workspace.service.read_file('jarvis/app.py')
        state = dict(workspace.state, run_id=str(uuid.uuid4()))
        atomic_json(workspace.directory / 'session.json', state)
        return result
    with pytest.raises(ModelRouteError):
        dispatch(workspace, invoke=invoke)
    assert len(workspace.calls) == 1


@pytest.mark.parametrize('field,value', [('run_id', str(uuid.uuid4())),
                                      ('task', 'b' * 12), ('ref', 'b' * 40)])
def test_same_session_owner_replacement_refuses_before_any_guest_write(workspace, field, value):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    def invoke():
        atomic_json(workspace.directory / 'session.json', {**workspace.state, field: value})
        return workspace.service.propose_edit('jarvis/app.py', CANARY, 'must never write')
    with pytest.raises(ModelRouteError):
        dispatch(workspace, 'edit_propose',
            {'path': 'jarvis/app.py', 'new_content': CANARY, 'rationale': 'must never write'},
            context=context, invoke=invoke)
    assert workspace.calls == []


def test_replaced_matching_snapshot_record_refuses_before_any_guest_write(workspace):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    def invoke():
        with tarfile.open(workspace.source, 'w') as archive:
            item = tarfile.TarInfo('jarvis/app.py')
            item.size, item.mode = len(CANARY), 0o644
            archive.addfile(item, io.BytesIO(CANARY.encode()))
        state = workspace.controller.read(workspace.task)
        state['source_sha256'] = hashlib.sha256(workspace.source.read_bytes()).hexdigest()
        workspace.controller.save(workspace.task, state)
        return workspace.service.propose_edit('jarvis/app.py', 'must never write', 'must never write')
    with pytest.raises(ModelRouteError):
        dispatch(workspace, 'edit_propose',
            {'path': 'jarvis/app.py', 'new_content': 'must never write', 'rationale': 'must never write'},
            context=context, invoke=invoke)
    assert workspace.calls == []


def test_status_is_payload_free_and_pinned_cancel_targets_exact_task(workspace):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    status = sources.workspace_status_for_owner(workspace.service, workspace.parent, context=context)
    assert status['phase'] == 'editing' and CANARY not in json.dumps(status)
    assert sources.cancel_workspace_session_for_owner(workspace.service, workspace.parent, context=context)['ok']
    assert workspace.cancelled == [workspace.task]


def test_foreign_repo_baseline_does_not_gain_registered_project_approval(workspace):
    state = dict(workspace.state, repository='other/private-app')
    atomic_json(workspace.directory / 'session.json', state)
    workspace.service._github_repo = state['repository']
    target = workspace.runtime.workspaces / (workspace.runtime._key(state['repository'], 'selfedit') + '.json')
    atomic_json(target, {'session': state['id'], 'repository': state['repository'],
                        'kind': 'selfedit', 'profile': 'mortimer'})
    assert dispatch(workspace)[0].level == 'confidential'


def test_creator_duck_service_gets_metadata_but_no_source_approval(workspace):
    owner, request, bot, run_id, job = 'owner', *(str(uuid.uuid4()) for _ in range(4))
    state = {'operation': 'draft', 'request_id': request, 'bot_session_id': bot,
             'developer_run_id': run_id, 'creator_revision': 'a' * 64,
             'skill_id': 'fixture-skill', 'sandbox_job_id': job}
    run = {'user_id': owner, 'session_id': bot, 'run_id': run_id,
           'agent': 'developer', 'status': 'running'}
    service = SimpleNamespace(read_file=lambda path: {'ok': True, 'content': CANARY})
    context = sources.creator_context(service, state, run)
    scope = make_tool_execution_scope(run_id, 'task', 'call', 'file_read',
        {'path': 'jarvis/app.py'}, DataPolicy('approved_external', 'unit'))
    envelope = sources.dispatch_workspace_tool(service, 'file_read', {'path': 'jarvis/app.py'},
        execution_scope=scope, context=context)
    assert context.as_metadata()['sandbox_job_id'] == job
    assert validate_tool_result(scope, envelope)[0].level == 'confidential'


@pytest.mark.parametrize('level', ['confidential', 'local_only'])
def test_host_floor_is_retained_even_when_caller_supplies_public_scope(workspace, monkeypatch, level):
    monkeypatch.setattr(sources, '_floor', lambda workload: DataPolicy(level, 'host-floor'))
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    assert dispatch(workspace, context=context)[0].level == level


def test_metadata_only_creator_retains_stricter_verified_host_floor(workspace, monkeypatch):
    monkeypatch.setattr(sources, '_floor', lambda workload: DataPolicy('local_only', 'host-floor'))
    owner, request, bot, run_id, job = 'owner', *(str(uuid.uuid4()) for _ in range(4))
    state = {'operation': 'draft', 'request_id': request, 'bot_session_id': bot,
        'developer_run_id': run_id, 'creator_revision': 'a' * 64,
        'skill_id': 'fixture-skill', 'sandbox_job_id': job}
    run = {'user_id': owner, 'session_id': bot, 'run_id': run_id,
           'agent': 'developer', 'status': 'running'}
    service = SimpleNamespace(read_file=lambda path: {'ok': True, 'content': CANARY})
    context = sources.creator_context(service, state, run)
    scope = make_tool_execution_scope(run_id, 'task', 'call', 'file_read',
        {'path': 'jarvis/app.py'}, DataPolicy('approved_external', 'unit'))
    envelope = sources.dispatch_workspace_tool(service, 'file_read', {'path': 'jarvis/app.py'},
        execution_scope=scope, context=context)
    assert validate_tool_result(scope, envelope)[0].level == 'local_only'


def test_cancelled_owner_remains_visible_as_safe_status_but_cannot_read(workspace):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    sources.cancel_workspace_session_for_owner(workspace.service, workspace.parent, context=context)
    status = sources.workspace_status_for_owner(workspace.service, workspace.parent, context=context)
    assert status['phase'] == 'cancelled' and not status['active']
    assert CANARY not in json.dumps(status)
    with pytest.raises(ModelRouteError):
        dispatch(workspace, context=context)


def test_validation_reports_installed_checks_without_guest_log_payload(workspace):
    policy, result, _ = dispatch(workspace, 'session_validate', {}, invoke=lambda: {
        'ok': False, 'checks': [{'name': 'backend', 'ok': False, 'output': CANARY},
                              {'name': CANARY, 'ok': False, 'output': CANARY}],
        'skill_validation': {'private_path': CANARY}, 'error': CANARY})
    assert policy.level == 'approved_external'
    assert result == {'ok': False, 'checks': [{'name': 'backend', 'ok': False,
                                             'output': 'See the saved sandbox check log.'}]}


def test_verified_published_handle_survives_terminal_status_without_other_payload(workspace):
    context = sources.assert_workspace_session_owner(workspace.service, workspace.parent)
    publication = {'ok': True, 'number': 14,
        'url': 'https://github.com/Larryfix71566/jarvis-voice-ai/pull/14',
        'commit': 'b' * 40, 'candidate': 'c' * 64}
    def invoke():
        atomic_json(workspace.directory / 'session.json',
                    dict(workspace.state, phase='published', publication=publication))
        return {**publication, 'pr_url': publication['url'], 'pr_number': 14, 'private': CANARY}
    policy, result, _ = dispatch(workspace, 'session_submit', {}, context=context, invoke=invoke)
    assert policy.level == 'approved_external' and result['pr_number'] == 14
    assert CANARY not in json.dumps(result)
    assert sources.workspace_status_for_owner(workspace.service, workspace.parent,
                                              context=context)['phase'] == 'published'


@pytest.mark.parametrize('field', ['pr_url', 'pr_number', 'url', 'number'])
def test_unmatched_publication_handle_does_not_approve_itself(workspace, field):
    publication = {'ok': True, 'number': 14,
        'url': 'https://github.com/Larryfix71566/jarvis-voice-ai/pull/14',
        'commit': 'b' * 40, 'candidate': 'c' * 64}
    def invoke():
        atomic_json(workspace.directory / 'session.json',
                    dict(workspace.state, phase='published', publication=publication))
        result = {**publication, 'pr_url': publication['url'], 'pr_number': 14}
        result[field] = 15 if field.endswith('number') else 'https://github.com/other/repo/pull/14'
        return result
    assert dispatch(workspace, 'session_submit', {}, invoke=invoke)[0].level == 'confidential'


def test_actual_creator_context_binds_distinct_run_and_sandbox_job(workspace):
    kind = 'skill-authoring-fixture-skill'
    live = dict(workspace.state, kind=kind)
    atomic_json(workspace.directory / 'session.json', live)
    record_path = workspace.runtime.workspaces / (workspace.runtime._key(live['repository'], kind) + '.json')
    atomic_json(record_path, {'session': live['id'], 'repository': live['repository'],
                             'kind': kind, 'profile': 'mortimer'})
    service = SkillAuthoringService('fixture-skill', repository=lambda: live['repository'],
        token=lambda: '', base_branch=lambda: 'main', runtime_factory=lambda: workspace.runtime,
        expected_job_id=workspace.parent)
    owner, request, bot, developer = 'owner', *(str(uuid.uuid4()) for _ in range(3))
    state = {'operation': 'draft', 'request_id': request, 'bot_session_id': bot,
        'developer_run_id': developer, 'creator_revision': 'a' * 64,
        'skill_id': 'fixture-skill', 'sandbox_job_id': workspace.parent,
        'sandbox_session_id': live['id'], 'sandbox_task_id': live['task'], 'source_commit': live['ref']}
    run = {'user_id': owner, 'session_id': bot, 'run_id': developer,
           'agent': 'developer', 'status': 'running'}
    context = sources.creator_context(service, state, run)
    metadata = context.as_metadata()
    assert metadata['developer_run_id'] != metadata['sandbox_job_id']
    assert metadata['sandbox_session_id'] == live['id']
    assert metadata['source_commit'] == live['ref']
    with pytest.raises(ModelRouteError, match='creator_source_context_invalid'):
        sources.creator_context(service, dict(state, source_commit='b' * 40), run)


def test_pending_write_and_source_record_symlink_never_approve_read(workspace):
    files = workspace.service._session()._files(workspace.state)
    with files._locked():
        journal = files._journal()
        journal['pending_edit'] = {'path': 'jarvis/app.py'}
        files._save(journal)
    assert dispatch(workspace)[0].level == 'confidential'
    record = workspace.record_path.with_suffix('.actual')
    workspace.record_path.rename(record)
    workspace.record_path.symlink_to(record)
    with pytest.raises(ModelRouteError):
        dispatch(workspace)
