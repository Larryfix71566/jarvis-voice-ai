"""Offline full-pilot boundaries: real host SQL/MCP, inert operation transports.

These tests never invoke a model, VM, publication, production database or
production settings. A fake transport below is explicitly unit evidence and
cannot be used by the live entry point as a registry/SDK/admin substitute.
"""
import asyncio
from dataclasses import asdict
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import tarfile
import tempfile
from types import SimpleNamespace
import uuid

import pytest
import pytest_asyncio

from scripts import run_model_use_full_development_pilot as pilot


def synthetic_token():
    return 'jvt_' + 'a' * 43


def make_auth_db(path, *, name='service-bot', owner='larry', revoked=None):
    from jarvis.auth import hash_token
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE client_tokens(name,user_id,token_hash,revoked_at,last_used_at)')
        connection.execute('INSERT INTO client_tokens VALUES(?,?,?,?,?)',
                           (name, owner, hash_token(synthetic_token()), revoked, 'unchanged'))


def test_service_principal_is_actual_existing_hash_and_read_only(tmp_path):
    path = tmp_path / 'actual.db'
    make_auth_db(path)
    before = path.read_bytes()
    assert pilot.read_service_principal(path, synthetic_token()) == 'larry'
    assert path.read_bytes() == before
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT last_used_at FROM client_tokens').fetchone()[0] == 'unchanged'


@pytest.mark.parametrize('name,owner,revoked', [
    ('human', 'larry', None), ('service-bot', '../invalid', None), ('service-bot', 'larry', 'now'),
])
def test_service_identity_cannot_be_invented(tmp_path, name, owner, revoked):
    path = tmp_path / 'actual.db'
    make_auth_db(path, name=name, owner=owner, revoked=revoked)
    with pytest.raises(pilot.FullPilotUnavailable, match='service_identity_unverified'):
        pilot.read_service_principal(path, synthetic_token())


def test_duplicate_service_principal_refuses(tmp_path):
    path = tmp_path / 'actual.db'
    make_auth_db(path)
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO client_tokens SELECT * FROM client_tokens')
    with pytest.raises(pilot.FullPilotUnavailable, match='service_identity_unverified'):
        pilot.read_service_principal(path, synthetic_token())


@pytest.mark.asyncio
async def test_hash_copy_uses_private_real_db_and_actual_auth(tmp_path):
    from jarvis.storage_context import storage_scope
    from jarvis.auth import verify_bearer
    directory = tmp_path / 'owned'
    directory.mkdir()
    async with storage_scope(db_path=directory / 'pilot.db', costs_db_path=directory / 'costs.db'):
        pilot.seed_private_principal(directory, synthetic_token(), 'larry')
        identity = verify_bearer('Bearer ' + synthetic_token())
        assert identity.name == 'service-bot' and identity.user_id == 'larry'
        with pytest.raises(pilot.FullPilotUnavailable, match='new_private_auth_store_required'):
            pilot.seed_private_principal(directory, synthetic_token(), 'larry')
    assert synthetic_token().encode() not in (directory / 'pilot.db').read_bytes()


@pytest.mark.asyncio
async def test_real_source_pin_calls_installed_source_and_refuses_revision_drift(tmp_path):
    calls = []
    # Unit transport only: the live driver constructs actual sandbox.GitSource.
    def fetch(repository, branch, token):
        calls.append((repository, branch, token))
        return tmp_path, 'b' * 40
    runtime = SimpleNamespace(source=SimpleNamespace(fetch=fetch))
    pin = pilot.RealSourcePin(runtime, 'accepted-branch', 'a' * 40)
    with pytest.raises(pilot.FullPilotUnavailable, match='remote_source_revision_changed'):
        runtime.source.fetch(pilot.PROJECT, 'accepted-branch', 'unit-token')
    assert calls == [(pilot.PROJECT, 'accepted-branch', 'unit-token')]
    assert pin.root is None


def test_real_source_pin_cannot_substitute_another_repo(tmp_path):
    calls = []
    runtime = SimpleNamespace(source=SimpleNamespace(fetch=lambda *args: calls.append(args)))
    pilot.RealSourcePin(runtime, 'accepted', 'a' * 40)
    with pytest.raises(pilot.FullPilotUnavailable, match='remote_source_binding_changed'):
        runtime.source.fetch('foreign/repo', 'accepted', 'unit-token')
    assert calls == []


async def invoke_http(path, body=None, *, method='POST'):
    entered = []
    async def actual_app(scope, receive, send):
        entered.append(await receive())
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'{}'})
    case = {'goal': 'public exact task', 'target_path': 'mcp_servers/mcp_time/logic.py'}
    app = pilot.NonpublicationHTTP(actual_app, case, 'actual-run')
    outgoing = []
    incoming = [{'type': 'http.request', 'body': json.dumps(body or {}).encode(), 'more_body': False}]
    async def receive():
        return incoming.pop(0)
    async def send(value):
        outgoing.append(value)
    await app({'type': 'http', 'method': method, 'path': path}, receive, send)
    return entered, outgoing


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/api/selfedit/submit', '/api/selfedit/finish',
    '/api/plan/start', '/api/status/subscriptions', '/api/clipboard/read', '/api/commit'])
async def test_unrelated_admin_routes_never_enter_actual_app(path):
    entered, output = await invoke_http(path)
    assert entered == []
    assert output[0]['status'] == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['selfedit_finish', 'plan_start', 'screen_view', 'app_build_submit'])
async def test_shared_source_http_route_cannot_sneak_a_forbidden_tool(tool):
    entered, output = await invoke_http('/api/development/source/tool',
                                       {'tool_name': tool, 'developer_run_id': 'actual-run'})
    assert entered == [] and output[0]['status'] == 403


@pytest.mark.asyncio
async def test_exact_host_preview_is_replayed_byte_for_byte():
    body = {'goal': 'public exact task', 'run_id': 'actual-run',
            'target_paths': ['mcp_servers/mcp_time/logic.py']}
    entered, output = await invoke_http('/api/selfedit/stage', body)
    assert json.loads(entered[0]['body']) == body and output[0]['status'] == 200
    entered, output = await invoke_http('/api/selfedit/stage', {**body, 'goal': 're-derived different task'})
    assert entered == [] and output[0]['status'] == 403


@pytest.mark.asyncio
async def test_existing_start_after_preview_author_flag_is_kept():
    entered, output = await invoke_http('/api/selfedit/run', {'staging_id': 'actual-stage', 'author': True})
    assert entered and output[0]['status'] == 200
    entered, output = await invoke_http('/api/selfedit/run',
        {'staging_id': 'actual-stage', 'author': True, 'plan': 'unexpected planner bypass'})
    assert entered == [] and output[0]['status'] == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('tool,arguments', [
    ('screen_view', {}), ('runlog_detail', {'run_id': 'private'}),
    ('selfedit_finish', {}), ('selfedit_write', {'path': 'jarvis/private.py'}),
    ('repo_read_file', {'path': 'docs/private-report.md'}), ('selfedit_status', {'action_run_id': 'foreign'}),
])
async def test_private_and_publication_tools_refuse_before_transport(tool, arguments):
    from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
    calls = []
    async def inert_call(*args, **kwargs):
        calls.append(args)
    registry = SimpleNamespace(_call=inert_call)
    pilot.PilotToolGuard(registry, {'target_path': 'mcp_servers/mcp_time/logic.py'}, lambda: None, 'a' * 64)
    scope = make_tool_execution_scope('actual-run', 'actual-task', 'actual-call', tool, arguments,
                                     DataPolicy('approved_external', 'public-unit-case'))
    envelope = await registry._call(tool, arguments, execution_scope=scope)
    policy, content = validate_tool_result(scope, envelope)
    assert calls == [] and policy.level == 'approved_external'
    assert json.loads(content) == {'ok': False, 'error': 'outside_public_pilot'}


@pytest.mark.asyncio
async def test_allowed_write_forwards_exact_classified_scope_to_real_method():
    from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, issue_tool_result
    calls = []
    arguments = {'path': 'mcp_servers/mcp_time/logic.py', 'content': 'public edit', 'rationale': 'public rationale'}
    scope = make_tool_execution_scope('actual-run', 'actual-task', 'actual-call', 'selfedit_write', arguments,
                                     DataPolicy('approved_external', 'public-unit-case'))
    expected = issue_tool_result(scope, '{"ok":true}', scope.input_policy, 'unit-inert-transport')
    async def inert_call(tool, actual_args, servers, **kwargs):
        calls.append((tool, actual_args, servers, kwargs))
        return expected
    registry = SimpleNamespace(_call=inert_call)
    guard = pilot.PilotToolGuard(registry, {'target_path': arguments['path']}, lambda: None, 'a' * 64)
    result = await registry._call('selfedit_write', arguments, list(pilot.SERVERS), execution_scope=scope)
    assert result is expected
    assert calls == [('selfedit_write', arguments, list(pilot.SERVERS), {'execution_scope': scope})]
    assert guard.executed == ['selfedit_write']


@pytest.mark.asyncio
async def test_worker_drain_tracks_actual_thread_after_job_slot_says_ready():
    held = threading.Event()
    entered = threading.Event()
    admin = SimpleNamespace(_source_worker_target=lambda target: target,
        _opening_lock=threading.Lock(), _opening_job={'state': 'ready'})
    tracker = pilot.AuthoringWorkers(admin)
    def actual_target():
        entered.set()
        held.wait(2)
    target = admin._source_worker_target(actual_target)
    worker = threading.Thread(target=target)
    worker.start()
    assert entered.wait(1)
    try:
        assert await tracker.drain(.03) is False
        held.set()
        worker.join(1)
        assert await tracker.drain(.1) is True
    finally:
        held.set()
        worker.join(1)


def test_fresh_worker_environment_never_lends_parent_authority(tmp_path, monkeypatch):
    from jarvis.model_routing import WorkloadLimits
    # The real helper emits a private policy file. No process globals are changed.
    parent_before = dict(os.environ)
    environment = pilot.worker_environment(tmp_path, 'claude-opus', 'subscription', None,
                                          WorkloadLimits(deadline_seconds=300))
    assert dict(os.environ) == parent_before
    assert environment['JARVIS_DB_PATH'] == str(tmp_path / 'pilot.db')
    assert environment['JARVIS_COSTS_DB'] == str(tmp_path / 'costs.db')
    assert environment['MORTIMER_SANDBOX_HOME'] == str(tmp_path)
    assert environment['JARVIS_AUTH_ENABLED'] == 'true'
    assert environment['JARVIS_KEY_HEALTH_ENABLED'] == 'false'
    assert environment['JARVIS_REMINDER_NOTIFICATIONS_ENABLED'] == 'false'
    assert environment['JARVIS_SCREEN_ENABLED'] == 'false'


def concrete_child_policy(tmp_path, monkeypatch):
    import yaml
    from jarvis.model_routing import WorkloadLimits
    policy = yaml.safe_load((pilot.ROOT / 'config/model_access.yaml').read_text())
    policy['workloads']['developer'].update(deadline_seconds=60,
        max_output_tokens_per_call=8, max_estimated_spend_usd_per_task=.01)
    source = tmp_path / 'configured-policy.json'
    source.write_bytes(pilot.canonical(policy))
    monkeypatch.setenv('JARVIS_MODEL_ACCESS_CONFIG', str(source))
    directory = tmp_path / 'owned'
    directory.mkdir()
    environment = pilot.worker_environment(directory, 'claude-opus', 'subscription', None,
        WorkloadLimits(deadline_seconds=300, max_output_tokens_per_call=100,
                       max_estimated_spend_usd_per_task=.5))
    return Path(environment['JARVIS_MODEL_ACCESS_CONFIG'])


def test_live_contract_binds_exact_merged_stronger_child_limits(tmp_path, monkeypatch):
    path = concrete_child_policy(tmp_path, monkeypatch)
    contract, before = pilot.selection_contract('claude-opus', 'subscription', policy_path=path)
    assert contract['policy']['limits'] == {'deadline_seconds': 60, 'max_output_tokens_per_call': 8,
                                          'max_estimated_spend_usd_per_task': .01}
    current = json.loads(path.read_bytes())
    current['workloads']['developer']['deadline_seconds'] = 61
    path.write_bytes(pilot.canonical(current))
    changed, after = pilot.selection_contract('claude-opus', 'subscription', policy_path=path)
    assert before != after
    assert changed['policy']['limits']['deadline_seconds'] == 61


def test_child_policy_drift_refuses_before_original_client_construction(tmp_path, monkeypatch):
    from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits, ModelRouteError
    path = concrete_child_policy(tmp_path, monkeypatch)
    monkeypatch.setenv('JARVIS_MODEL_ACCESS_CONFIG', str(path))
    helper = pilot.support()
    # Explicit inert metadata seam; no registry/SDK substitute enters live mode.
    monkeypatch.setattr(helper, 'inspect_live_developer_registry', lambda registry: {'declared_tool_names': []})
    registry = SimpleNamespace(openai_tools=lambda servers: [])
    contract, expected = pilot.selection_contract('claude-opus', 'subscription', policy_path=path)
    resolved = ResolvedModelRoute('developer', 'claude-opus', contract['model']['model'], 'anthropic',
        'subscription://claude', AccessRoute(**contract['route']), None, contract['model']['identity'],
        limits=WorkloadLimits(**contract['policy']['limits']))
    constructed = []
    async def loop(*args, **kwargs):
        return 'unused'
    agent = SimpleNamespace(_routed_client_for=lambda route: constructed.append(route),
                            _execution_client=lambda client: client, _loop=loop)
    guard = pilot.ModelContract(agent, registry, resolved, [], contract['policy'], expected,
                                pilot.digest(path.read_bytes()))
    current = json.loads(path.read_bytes())
    current['workloads']['developer']['deadline_seconds'] = 300
    path.write_bytes(pilot.canonical(current))
    with pytest.raises(ModelRouteError, match='full_pilot_model_contract_changed'):
        agent._routed_client_for(resolved)
    assert constructed == [] and guard.failed


@pytest.mark.asyncio
async def test_real_six_server_discovery_is_forty_unmodified_schemas(tmp_path, monkeypatch):
    import yaml
    from jarvis.skills.registry import SkillRegistry
    monkeypatch.setenv('JARVIS_VAULT_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_KEY_HEALTH_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_SCREEN_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_SERVICE_TOKEN', synthetic_token())
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'unit.db'))
    monkeypatch.setenv('JARVIS_TIMEZONE', 'UTC')
    monkeypatch.setenv('JARVIS_ADMIN_URL', 'http://127.0.0.1:1')
    config = yaml.safe_load((pilot.ROOT / 'config/mcp_servers.yaml').read_text())
    selected = [entry for entry in config['servers'] if entry['name'] in pilot.SERVERS]
    path = tmp_path / 'configured.json'
    path.write_bytes(pilot.canonical({'servers': selected}))
    registry = SkillRegistry(path)
    await registry.start()
    try:
        actual = pilot.support().inspect_live_developer_registry(registry)
        schemas = registry.openai_tools(list(pilot.SERVERS))
        assert actual['live_schema_verified'] is True
        assert len(schemas) == 40
        assert {item['function']['name'] for item in schemas} == set(actual['declared_tool_names'])
        assert actual['status'] == 'schema_only_unverified_execution'
        assert actual['developer_accepted'] is False
    finally:
        await registry.stop()


def test_full_worker_refuses_arbitrary_child_request_before_import_or_operations():
    with pytest.raises(pilot.FullPilotUnavailable, match='worker_request_invalid'):
        pilot.validate_worker_request({'directory': '/production', 'run_id': str(uuid.uuid4())})


def test_support_requires_committed_exact_bytes_before_live(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'ROOT', tmp_path)
    with pytest.raises(pilot.FullPilotUnavailable, match='reviewed_support_not_committed'):
        pilot._require_committed_support()


def test_owned_cli_turn_resets_its_token_on_failure_and_preserves_parent_holder():
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn, is_sensitive
    parent = SensitiveTurn()
    parent.arm('inherited-private-source', 'actual-parent')
    token = current_sensitive_turn.set(parent)
    try:
        with pytest.raises(RuntimeError):
            with pilot.owned_cli_turn() as holder:
                assert holder is parent and is_sensitive()
                raise RuntimeError('inert failure')
        assert current_sensitive_turn.get() is parent and parent.is_armed()
    finally:
        current_sensitive_turn.reset(token)


@pytest_asyncio.fixture
async def actual_developer_sdk_unit(tmp_path, monkeypatch):
    """Actual roster/MCP/SQL with only the provider HTTP transport inert."""
    import httpx
    from openai import AsyncOpenAI
    import yaml
    from jarvis.config import Settings
    from jarvis.agents.base import load_sub_agents
    from jarvis.agents.upgrade_agent import load_model_registry
    from jarvis.db import get_conn, run_migrations
    from jarvis.skills.registry import SkillRegistry
    from jarvis.storage_context import storage_scope
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('JARVIS_VAULT_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_KEY_HEALTH_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_SCREEN_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_SENSITIVE_GUARD_ENABLED', 'true')
    monkeypatch.setenv('JARVIS_MODEL_ROUTING_ENABLED', '0')
    monkeypatch.setenv('JARVIS_SERVICE_TOKEN', synthetic_token())
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'actual-private.db'))
    monkeypatch.setenv('JARVIS_TIMEZONE', 'UTC')
    monkeypatch.setenv('JARVIS_ADMIN_URL', 'http://127.0.0.1:1')
    data = yaml.safe_load((pilot.ROOT / 'config/mcp_servers.yaml').read_text())
    selected = [item for item in data['servers'] if item['name'] in pilot.SERVERS]
    path = tmp_path / 'six-real-servers.json'
    path.write_bytes(pilot.canonical({'servers': selected}))
    registry = SkillRegistry(path)
    calls = []
    model = load_model_registry()['profiles']['claude-opus']['model']
    async def sdk_transport(request):
        payload = json.loads(request.content)
        calls.append(('sdk', payload))
        return httpx.Response(200, json={'id': 'inert-unit-response', 'object': 'chat.completion',
            'created': 1, 'model': payload['model'],
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'PUBLIC_UNIT_ASSOCIATION_OK'},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    client = AsyncOpenAI(api_key='unit', base_url='https://unit.example/v1',
                        http_client=httpx.AsyncClient(transport=httpx.MockTransport(sdk_transport)))
    settings = Settings(_env_file=None, openai_api_key='unit', deepgram_api_key='unit',
        elevenlabs_api_key='unit', openai_model=model, jarvis_procedures_enabled=False,
        jarvis_model_routing_enabled=False, jarvis_runlog_enabled=True)
    async with storage_scope(db_path=tmp_path / 'actual-private.db', costs_db_path=tmp_path / 'actual-costs.db'):
        connection = get_conn()
        try:
            run_migrations(connection)
        finally:
            connection.close()
        await registry.start()
        try:
            actual = pilot.support().inspect_live_developer_registry(registry)
            assert actual['live_schema_verified'] and len(registry.openai_tools(list(pilot.SERVERS))) == 40
            # Existing test-only SDK factory seam; the live driver uses none.
            agent = load_sub_agents(settings, registry, client_factory=lambda _settings: client)['developer']
            assert tuple(agent.mcp_servers) == pilot.SERVERS
            yield agent, registry, calls
        finally:
            await registry.stop()
            await client.close()


@pytest.mark.asyncio
async def test_owned_cli_holder_reaches_actual_developer_association_before_inert_sdk(actual_developer_sdk_unit):
    from jarvis.bot.sensitive_turn import current_sensitive_turn, is_sensitive, arm_from_text
    from jarvis.runlog.store import get_run
    agent, registry, calls = actual_developer_sdk_unit
    inherited = current_sensitive_turn.get()
    # The actual live CLI entry begins with no holder; retain and restore this
    # regression condition without replacing the is_sensitive implementation.
    empty = current_sensitive_turn.set(None)
    run_id, session_id = str(uuid.uuid4()), str(uuid.uuid4())
    async def associate(actual_run):
        row = get_run(actual_run)['run']
        assert row['agent'] == 'developer' and row['status'] == 'running'
        assert row['run_id'] == run_id and row['session_id'] == session_id
        assert len(registry.openai_tools(list(pilot.SERVERS))) == 40
        assert not is_sensitive()
        calls.append(('association', actual_run))
        return True
    try:
        assert is_sensitive() is True
        with pilot.owned_cli_turn():
            assert not is_sensitive()
            assert arm_from_text('Explain this public timezone utility.', run_id) is False
            reply = await agent.run('Explain this public timezone utility.', run_id=run_id,
                                    session_id=session_id, on_run_created=associate)
        assert current_sensitive_turn.get() is None
        assert reply == 'PUBLIC_UNIT_ASSOCIATION_OK'
        assert [kind for kind, _ in calls] == ['association', 'sdk']
        assert len(calls[1][1]['tools']) == 40
        assert get_run(run_id)['run']['status'] == 'ok'
    finally:
        current_sensitive_turn.reset(empty)
    assert current_sensitive_turn.get() is inherited


@pytest.mark.asyncio
@pytest.mark.parametrize('protection', ['armed', 'temporary', 'detected'])
async def test_owned_cli_holder_keeps_stricter_actual_developer_rejection(actual_developer_sdk_unit, protection):
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn, arm_from_text, is_sensitive
    agent, _registry, calls = actual_developer_sdk_unit
    holder = SensitiveTurn()
    if protection == 'armed':
        holder.arm('inherited-private-source', 'actual-parent')
    elif protection == 'temporary':
        holder.arm_temporary_content()
    token = current_sensitive_turn.set(holder)
    associated = []
    try:
        with pilot.owned_cli_turn() as actual:
            assert actual is holder
            if protection == 'detected':
                assert arm_from_text('my account number is 000123456789') is True
            assert is_sensitive() is True
            reply = await agent.run('Read the public timezone utility.',
                on_run_created=lambda run_id: associated.append(run_id))
        assert reply.startswith('FAILED:')
        assert associated == [] and calls == []
        assert holder.is_armed() and current_sensitive_turn.get() is holder
    finally:
        current_sensitive_turn.reset(token)


@pytest.mark.parametrize('witness,value', [
    ('/private/tmp/test_ws05_full_receipt_boolean_witness.py', 1),
    ('/private/tmp/test_ws05_full_receipt_boolean_witness.py', 'true'),
    ('/private/tmp/test_ws05_full_receipt_structured_witness.py', True),
])
def test_original_public_parent_witness_now_returns_fixed_refusal(tmp_path, monkeypatch, capsys, witness, value):
    """Run the original causal body unchanged; invert only its bad-outcome claim."""
    expected_hashes = {
        '/private/tmp/test_ws05_full_receipt_boolean_witness.py': '0caa84b92e16add480950384da4a56e5d4628667d852504cecc3ddf5581bc143',
        '/private/tmp/test_ws05_full_receipt_structured_witness.py': '85204ccf87599aedca3b68a588c94d9a1e533c6b85a545d6702c56e735c233d0',
    }
    path = Path(witness)
    if not path.exists():
        pytest.skip('reviewer causal witness is a local diagnostic, not a repository prerequisite')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hashes[witness]
    spec = importlib.util.spec_from_file_location('unchanged_full_receipt_witness', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = pilot.main
    returns = []
    def observed_main(argv):
        result = original(argv)
        returns.append(result)
        return result
    monkeypatch.setattr(pilot, 'main', observed_main)
    name = ('test_nonboolean_refused_child_is_acknowledged_as_full_success' if value is not True
            else 'test_minimal_true_pass_with_no_run_registry_verification_or_quality_is_accepted')
    # The original public output contract allows /private/tmp; pytest's
    # default macOS folder is elsewhere. Keep the original output gate too.
    with tempfile.TemporaryDirectory(prefix='full-receipt-inverse-', dir='/private/tmp') as owned:
        with pytest.raises(AssertionError):
            getattr(module, name)(Path(owned), monkeypatch, value, capsys)
        assert returns == [2]
        report = json.loads((Path(owned) / 'new-receipt.json').read_bytes())
        assert report['full_developer_passed'] is False
        assert report['parent_receipt_verified'] is False
        assert report['status'] == 'cleanup_unverified'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hashes[witness]


def typed_control():
    expected = {'operation_surface': 'developer_full_registry', 'selection': {'model': 'unit'},
                'full_developer_passed': False}
    request = {'run_id': str(uuid.uuid4())}
    child = {**expected, 'mode': 'live', 'status': 'unavailable', 'parent_request_id': request['run_id'],
             'production_bot_session': False, 'developer_accepted': False, 'mar_i_complete': False,
             'cleanup': {'verified': False}, 'private_transport_cleanup': False}
    return expected, request, child


@pytest.mark.parametrize('status,rc', [('unavailable', 2), ('quality_failed', 2), ('cleanup_unverified', 2)])
def test_honest_typed_refusal_does_not_require_success_artifacts(status, rc):
    expected, request, child = typed_control()
    child['status'] = status
    assert pilot.validate_child_control(child, rc, expected, request) is False


@pytest.mark.parametrize('flag', [1, 'true', None, {}, []])
def test_acceptance_flag_never_coerces_to_boolean(flag):
    expected, request, child = typed_control()
    child['full_developer_passed'] = flag
    with pytest.raises(pilot.FullPilotUnavailable, match='worker_receipt_boolean_invalid'):
        pilot.validate_child_control(child, 2, expected, request)


@pytest.mark.parametrize('field', ['cleanup', 'verification', 'full_registry', 'quality'])
def test_nested_acceptance_flags_are_exact_booleans(field):
    expected, request, child = typed_control()
    child[field] = {'verified': 1} if field == 'cleanup' else {'passed': 'true'}
    with pytest.raises(pilot.FullPilotUnavailable, match='worker_receipt_boolean_invalid'):
        pilot.validate_child_control(child, 2, expected, request)


@pytest.mark.parametrize('passed,status,rc', [
    (True, 'unavailable', 0), (True, 'full_developer_passed', 2),
    (False, 'full_developer_passed', 2), (False, 'unavailable', 0), (False, 'dry_ready_unverified', 0),
])
def test_status_and_child_exit_must_match_exact_success_flag(passed, status, rc):
    expected, request, child = typed_control()
    child.update(full_developer_passed=passed, status=status)
    with pytest.raises(pilot.FullPilotUnavailable, match='worker_receipt_status_invalid'):
        pilot.validate_child_control(child, rc, expected, request)


def backed_success(tmp_path, registry):
    """Complete offline evidence with real host encoders/SQL, inert guest logs.

    This proves the parent's validation path accepts a complete, consistent
    artifact set. It is explicitly not model/VM/quality acceptance evidence.
    """
    from sandbox.artifacts import Candidate, File
    from sandbox.control import Controller
    from sandbox.durable import atomic_bytes, atomic_json
    from sandbox.profiles import MORTIMER
    from sandbox.verify import runner_fingerprint
    from jarvis.db import get_conn
    from jarvis.auth import hash_token
    from jarvis.runlog.store import RunLogger
    from jarvis.tenant import user_id_scope
    helper = pilot.support()
    case = helper.load_corpus()
    home = tmp_path / 'owned-image-home'
    directory = home / 'pilots' / uuid.uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    controller = Controller(home, '/inert/tart', '/inert/softnet')
    run_id, session_id = str(uuid.uuid4()), str(uuid.uuid4())
    sid, attempt, image = uuid.uuid4().hex, uuid.uuid4().hex, 'd' * 64
    dev, verifier = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
    source_ref = 'c' * 40
    declarations = helper.inspect_live_developer_registry(registry)
    schemas = registry.openai_tools(list(pilot.SERVERS))
    record, selection_sha = pilot.selection_contract('claude-opus', 'direct_api')
    profile, route, policy = record['model'], record['route'], record['policy']
    resolved = {'workload': 'developer', 'profile_name': 'claude-opus', 'model': profile['model'],
                'provider': profile['provider'], 'base_url': route['base_url'], 'route': route,
                'api_key_env': route['credential_env'], 'identity': profile['identity'],
                'priority': policy['priority'], 'limits': policy['limits']}
    source_files = [File(path, 0o644, (pilot.ROOT / path).read_bytes()) for path in MORTIMER.dependencies]
    source_files.append(File(case['target_path'], 0o644, b'public original fixture\n'))
    baseline = Candidate(tuple(source_files))
    candidate = Candidate(tuple(File(file.path, file.mode, b'public nonempty fixture edit\n')
        if file.path == case['target_path'] else file for file in baseline.files))
    source_buffer = io.BytesIO()
    with tarfile.open(fileobj=source_buffer, mode='w') as archive:
        for file in baseline.files:
            member = tarfile.TarInfo(file.path)
            member.mode, member.size = file.mode, len(file.data)
            archive.addfile(member, io.BytesIO(file.data))
    source = source_buffer.getvalue()
    for task, purpose, parent in ((dev, 'development', None), (verifier, 'verification', dev)):
        inputs = home / 'tasks' / task / 'input'
        inputs.mkdir(parents=True, mode=0o700)
        atomic_bytes(inputs / 'source.tar', source)
        controller.save(task, {'id': task, 'vm': 'mortimer-' + task, 'image': image, 'purpose': purpose,
            'parent_task': parent, 'profile': MORTIMER.name, 'status': 'deleted', 'source_commit': source_ref,
            'source_sha256': pilot.digest(source), 'source_files': len(baseline.files),
            'source_bytes': sum(len(file.data) for file in baseline.files),
            'candidate': baseline.fingerprint if parent is None else candidate.fingerprint,
            'profile_sha256': MORTIMER.fingerprint, 'prepared': True, 'hydrated': True,
            'worker': 'mortimer-dev', 'network': 'offline'})
    candidates = home / 'tasks' / dev / 'candidates'
    candidates.mkdir(mode=0o700)
    atomic_bytes(candidates / (candidate.fingerprint + '.json'), candidate.encode())
    session_dir = home / 'sessions' / sid
    session_dir.mkdir(parents=True, mode=0o700)
    state = {'id': sid, 'task': dev, 'run_id': run_id, 'ref': source_ref, 'image': image,
             'repository': pilot.PROJECT, 'kind': 'selfedit', 'phase': 'reverted'}
    atomic_json(session_dir / 'session.json', state)
    workspaces = directory / 'workspaces'
    workspaces.mkdir(mode=0o700)
    key = pilot.digest((pilot.PROJECT.casefold() + '\0selfedit').encode())
    atomic_json(workspaces / (key + '.json'), {'repository': pilot.PROJECT, 'kind': 'selfedit',
                                            'profile': MORTIMER.name, 'session': sid})
    atomic_json(directory / 'full-allocations.json', {'schema_version': 1, 'session_id': sid,
        'run_id': run_id, 'source_ref': source_ref, 'image_id': image,
        'identity': [state.get(name) for name in helper._SESSION_KEYS],
        'tasks': {task: asdict(helper._task_generation(controller, task)) for task in (dev, verifier)}})
    schema = {'schema_version': 1, 'servers': list(pilot.SERVERS), 'schemas': schemas,
              'declaration_source_sha256': declarations['declaration_source_sha256']}
    atomic_json(directory / 'full-registry.json', schema)
    model = {'route': resolved, 'schemas': schemas, 'runtime': None}
    atomic_json(directory / 'full-model-contract.json', model)
    evidence_dir = home / 'tasks' / dev / 'verification' / attempt
    evidence_dir.mkdir(parents=True, mode=0o700)
    checks = []
    for name, argv in MORTIMER.checks:
        log = ('inert guest check: ' + name + '\n').encode()
        atomic_bytes(evidence_dir / (name + '.log'), log)
        checks.append({'name': name, 'argv': list(argv), 'passed': True, 'returncode': 0,
                       'log_sha256': pilot.digest(log)})
    desktop = b'desktop=visible\n'
    atomic_bytes(evidence_dir / 'desktop-probe.log', desktop)
    saved = {'attempt': attempt, 'candidate': candidate.fingerprint, 'baseline': baseline.fingerprint,
        'source_commit': source_ref, 'image': image, 'profile': MORTIMER.fingerprint,
        'runner': runner_fingerprint(), 'development_task': dev, 'verification_task': verifier,
        'passed': True, 'source_unchanged': True, 'status': 'passed', 'checks': checks,
        'desktop_probe': {'passed': True, 'returncode': 0, 'log_sha256': pilot.digest(desktop)}}
    atomic_json(evidence_dir / 'receipt.json', saved)
    holdout = tmp_path / 'outside-source-holdout.json'
    spec = {'version': 'date-diff-oracle-v1', 'cases': [{'id': 'independent-unit', 'timezone': 'UTC',
        'a': '2026-01-01T00:00:00+00:00', 'b': '2026-01-01T02:00:00+00:00',
        'expected': {'days': 0, 'hours': 2.0}}]}
    holdout.write_bytes(pilot.canonical(spec))
    holdout.chmod(0o600)
    oracle_dir = session_dir / 'pilot-oracle'
    oracle_dir.mkdir(mode=0o700)
    quality = []
    for kind, raw_spec, outside in (('known', helper._canonical(case['oracle']), False),
                                    ('external', holdout.read_bytes(), True)):
        ids = [item['id'] for item in json.loads(raw_spec)['cases']]
        results = []
        for phase, passed in (('baseline', False), ('candidate', True)):
            oracle = {'version': 'date-diff-oracle-result-v1', 'phase': phase,
                'spec_sha256': pilot.digest(raw_spec), 'corpus_sha256': helper.CORPUS_SHA256,
                'case_id': case['case_id'], 'oracle_sha256': helper.ORACLE_SHA256,
                'cases': [{'id': identifier, 'passed': passed} for identifier in ids], 'passed': passed}
            raw = pilot.canonical(oracle)
            atomic_bytes(oracle_dir / ('pilot-' + kind + '-' + phase + '.log'), raw)
            results.append({'phase': phase, 'passed': passed, 'returncode': 0 if passed else 1,
                            'log_sha256': pilot.digest(raw), 'case_count': len(ids)})
        quality.append({'kind': kind, 'outside_developer_source': outside,
                        'spec_sha256': pilot.digest(raw_spec), 'checks': results})
    with user_id_scope('larry'):
        log = RunLogger(run_id, 'developer', 'Developer', 'public unit fixture', session_id=session_id,
                        enabled=True, model=profile['model'])
        log.start()
        for tool in ('selfedit_read', 'selfedit_write'):
            log.tool_call(tool, {'path': case['target_path']}, tool_call_id=tool)
            log.tool_result(tool, '{"ok":true}', 1, True, tool_call_id=tool)
        log.finish('public fixture completed')
    connection = get_conn()
    try:
        connection.execute('INSERT INTO client_tokens(user_id,name,token_hash,created_at) VALUES(?,?,?,?)',
                           ('larry', 'service-bot', hash_token(synthetic_token()), 'unit-date'))
        connection.commit()
        with sqlite3.connect(directory / 'pilot.db') as copy:
            connection.backup(copy)
    finally:
        connection.close()
    operator = tmp_path / 'operator-issued-unit.db'
    make_auth_db(operator)
    expected = {'target_path': case['target_path'], 'source_dependency_sha256': MORTIMER.dependency_key(baseline),
                'target_baseline_sha256': pilot.digest(b'public original fixture\n'),
                'selection': {'model': profile['model']}}
    request = {'run_id': run_id, 'directory': str(directory), 'image_home': str(home), 'profile': 'claude-opus',
               'image_id': image, 'source_ref': source_ref, 'external_holdout': str(holdout),
               'external_holdout_sha256': pilot.digest(holdout.read_bytes()), 'service_auth_db': str(operator)}
    value = {'actual_selection_verified': True, 'independent_holdout_verified': True,
        'private_transport_cleanup': True, 'registry_cleanup': True, 'publication_allowed': False,
        'origin': 'actual_owned_cli_runtime', 'cleanup': {'verified': True, 'owned_tasks': [dev, verifier]},
        'full_registry': declarations, 'registry_evidence_sha256': pilot.digest((directory / 'full-registry.json').read_bytes()),
        'model_contract_sha256': pilot.digest(pilot.canonical(model)), 'actual_run': {
            'run_id': run_id, 'session_id': session_id, 'agent': 'developer', 'user_id': 'larry',
            'model': profile['model'], 'status': 'ok'}, 'session_id': session_id, 'owner_id': 'larry',
        'tool_execution': ['selfedit_read', 'selfedit_write'], 'verification': {name: saved[name] for name in
            ('attempt', 'candidate', 'baseline', 'source_commit', 'image', 'profile', 'runner',
             'development_task', 'verification_task', 'passed')}, 'quality': quality,
        'target_candidate_sha256': pilot.digest(b'public nonempty fixture edit\n'),
        'heldout_input': {'sha256': request['external_holdout_sha256'], 'prepared_before_model': True,
                          'outside_developer_source': True, 'model_input_contains_holdout': False}}
    value['verification']['checks'] = [{name: check[name] for name in
                                        ('name', 'passed', 'returncode', 'log_sha256')} for check in checks]
    return value, expected, request, record


@pytest.mark.asyncio
async def test_complete_typed_success_requires_and_accepts_backed_host_artifacts(tmp_path, actual_developer_sdk_unit):
    _agent, registry, _calls = actual_developer_sdk_unit
    value, expected, request, contract = backed_success(tmp_path, registry)
    expected.update(operation_surface='developer_full_registry')
    value.update(operation_surface='developer_full_registry', mode='live', status='full_developer_passed',
                 full_developer_passed=True, production_bot_session=False, developer_accepted=False,
                 mar_i_complete=False, parent_request_id=request['run_id'], selection=expected['selection'],
                 target_baseline_sha256=expected['target_baseline_sha256'],
                 source_dependency_sha256=expected['source_dependency_sha256'])
    assert pilot.validate_child_control(value, 0, expected, request) is True
    assert pilot.validate_success_evidence(value, expected, request, contract) is True
    # This is an offline structural proof; no model/VM acceptance is asserted.
    assert value['developer_accepted'] is False and value['mar_i_complete'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('missing', ['actual_run', 'full_registry', 'verification', 'quality', 'heldout_input'])
async def test_success_summary_cannot_replace_a_required_evidence_section(tmp_path, actual_developer_sdk_unit, missing):
    _agent, registry, _calls = actual_developer_sdk_unit
    value, expected, request, contract = backed_success(tmp_path, registry)
    value.pop(missing)
    with pytest.raises(pilot.FullPilotUnavailable, match='worker_success_evidence_invalid'):
        pilot.validate_success_evidence(value, expected, request, contract)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['model', 'schema', 'run', 'source', 'nonempty', 'required_check',
                                    'check_log', 'holdout', 'cleanup', 'desktop_marker',
                                    'verifier_candidate', 'unresolved_event'])
async def test_complete_evidence_rejects_independent_boundary_damage(tmp_path, actual_developer_sdk_unit, damage):
    from sandbox.durable import atomic_json
    _agent, registry, _calls = actual_developer_sdk_unit
    value, expected, request, contract = backed_success(tmp_path, registry)
    directory, home = Path(request['directory']), Path(request['image_home'])
    verification = value['verification']
    if damage == 'model':
        model = json.loads((directory / 'full-model-contract.json').read_bytes())
        model['route']['model'] = 'different-model'
        atomic_json(directory / 'full-model-contract.json', model)
        value['model_contract_sha256'] = pilot.digest(pilot.canonical(model))
    elif damage == 'schema':
        schema = json.loads((directory / 'full-registry.json').read_bytes())
        schema['schemas'].pop()
        atomic_json(directory / 'full-registry.json', schema)
        value['registry_evidence_sha256'] = pilot.digest((directory / 'full-registry.json').read_bytes())
    elif damage == 'run':
        with sqlite3.connect(directory / 'pilot.db') as connection:
            connection.execute('UPDATE agent_runs SET status=? WHERE run_id=?', ('failed', request['run_id']))
    elif damage == 'source':
        (home / 'tasks' / verification['development_task'] / 'input/source.tar').write_bytes(b'wrong archive')
    elif damage == 'nonempty':
        value['target_candidate_sha256'] = expected['target_baseline_sha256']
    elif damage == 'required_check':
        value['verification']['checks'].pop()
    elif damage == 'check_log':
        (home / 'tasks' / verification['development_task'] / 'verification' /
         verification['attempt'] / 'backend.log').write_bytes(b'changed passing log')
    elif damage == 'holdout':
        value['quality'][1]['checks'][1]['passed'] = False
    elif damage == 'desktop_marker':
        evidence = home / 'tasks' / verification['development_task'] / 'verification' / verification['attempt']
        raw = b'no visible worker desktop\n'
        (evidence / 'desktop-probe.log').write_bytes(raw)
        saved = json.loads((evidence / 'receipt.json').read_bytes())
        saved['desktop_probe']['log_sha256'] = pilot.digest(raw)
        atomic_json(evidence / 'receipt.json', saved)
    elif damage == 'verifier_candidate':
        task = verification['verification_task']
        path = home / 'tasks' / task / 'state.json'
        state = json.loads(path.read_bytes())
        state['candidate'] = verification['baseline']
        atomic_json(path, state)
        allocations = json.loads((directory / 'full-allocations.json').read_bytes())
        allocations['tasks'][task] = asdict(pilot.support()._task_generation(pilot.EvidenceLocations(home), task))
        atomic_json(directory / 'full-allocations.json', allocations)
    elif damage == 'unresolved_event':
        with sqlite3.connect(directory / 'pilot.db') as connection:
            sequence = connection.execute('SELECT MAX(seq)+1 FROM agent_events WHERE run_id=?',
                                          (request['run_id'],)).fetchone()[0]
            connection.execute('INSERT INTO agent_events(run_id,seq,type,tool,tool_call_id,created_at) VALUES(?,?,?,?,?,?)',
                (request['run_id'], sequence, 'tool_call', 'selfedit_write', 'actual-unresolved', 'unit-date'))
    else:
        task = verification['verification_task']
        path = home / 'tasks' / task / 'state.json'
        state = json.loads(path.read_bytes())
        state['status'] = 'running'
        atomic_json(path, state)
    with pytest.raises(pilot.FullPilotUnavailable, match='worker_success_evidence_invalid'):
        pilot.validate_success_evidence(value, expected, request, contract)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['honest', 'desktop-marker', 'verifier-candidate', 'unresolved-event'])
async def test_original_public_semantic_probe_honest_case_and_exact_inverses(
        actual_developer_sdk_unit, monkeypatch, capsys, damage):
    """Preserve the original public-main proof; invert only false successes."""
    path = Path('/private/tmp/test_ws05_full_parent_semantic_probes.py')
    expected_sha = 'b709a46e19f8a125841f1a714a7405fc30a3b6982357cb9765d155475d2966c8'
    if not path.exists():
        pytest.skip('reviewer semantic proof is local diagnostic material')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha
    spec = importlib.util.spec_from_file_location('unchanged_full_semantic_proof', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = pilot.main
    returns = []
    def observed_main(argv):
        result = original(argv)
        returns.append(result)
        return result
    monkeypatch.setattr(pilot, 'main', observed_main)
    with tempfile.TemporaryDirectory(prefix='full-semantic-inverse-', dir='/private/tmp') as owned:
        invocation = module.test_public_parent_artifact_consistency(
            Path(owned), actual_developer_sdk_unit, monkeypatch, capsys, damage)
        if damage == 'honest':
            await invocation
            assert returns == [0]
            report = json.loads((Path(owned) / 'owned-result.json').read_bytes())
            assert report['full_developer_passed'] is True and report['parent_receipt_verified'] is True
        else:
            with pytest.raises(AssertionError):
                await invocation
            assert returns == [2]
            report = json.loads((Path(owned) / 'owned-result.json').read_bytes())
            assert report['full_developer_passed'] is False and report['parent_receipt_verified'] is False
        assert report['developer_accepted'] is False and report['mar_i_complete'] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha


@pytest.mark.asyncio
async def test_actual_extra_call_with_corresponding_result_is_not_unresolved(tmp_path, actual_developer_sdk_unit):
    _agent, registry, _calls = actual_developer_sdk_unit
    value, expected, request, contract = backed_success(tmp_path, registry)
    with sqlite3.connect(Path(request['directory']) / 'pilot.db') as connection:
        sequence = connection.execute('SELECT MAX(seq)+1 FROM agent_events WHERE run_id=?',
                                      (request['run_id'],)).fetchone()[0]
        for offset, kind in enumerate(('tool_call', 'tool_result')):
            connection.execute('INSERT INTO agent_events(run_id,seq,type,tool,tool_call_id,created_at) VALUES(?,?,?,?,?,?)',
                (request['run_id'], sequence + offset, kind, 'selfedit_write', 'actual-resolved', 'unit-date'))
    assert pilot.validate_success_evidence(value, expected, request, contract) is True
