"""Inert evidence only: no installed CLI inference, provider, VM or activation."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

import pytest
import yaml

from scripts import verify_claude_developer_capability as probe
from jarvis import model_routing as routing
from jarvis.model_execution import ModelExecutionRequest, ModelToolReference
from jarvis.privacy_policy import DataPolicy, issue_tool_result, make_tool_execution_scope
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.storage_context import storage_scope
from tests.unit.test_model_use_development_pilot import owned_pilot_source, bind_owned_pilot_source


@pytest.fixture(autouse=True)
def bind_owned_capability_source(owned_pilot_source, bind_owned_pilot_source, monkeypatch):
    """Use the exact frozen worker-owned fixture in parent and fresh children."""
    root = owned_pilot_source.root
    monkeypatch.setattr(probe, 'ROOT', root)
    monkeypatch.setattr(probe, '__file__', str(root / 'scripts/verify_claude_developer_capability.py'))


@pytest.fixture(autouse=True)
def isolation(tmp_path, monkeypatch):
    for key in ('JARVIS_MODEL_ACCESS_CONFIG', 'JARVIS_UPGRADE_MODELS', 'JARVIS_SERVICE_TOKEN',
                'JARVIS_MODEL_PROFILE_DEVELOPER', 'JARVIS_MODEL_ROUTE_DEVELOPER'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'unit.db'))
    monkeypatch.setenv('JARVIS_COSTS_DB', str(tmp_path / 'costs.db'))
    monkeypatch.setenv('JARVIS_VAULT_PATH', str(tmp_path / 'no-vault'))
    monkeypatch.setenv('JARVIS_VAULT_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_KEY_HEALTH_ENABLED', 'false')
    monkeypatch.setenv('JARVIS_SCREEN_ENABLED', 'false')
    token = current_sensitive_turn.set(SensitiveTurn())
    yield
    current_sensitive_turn.reset(token)


def test_default_dry_run_never_discovers_or_infers(monkeypatch, capsys):
    monkeypatch.setattr(probe, 'fresh_capture', lambda *a, **k: pytest.fail('inference'))
    assert probe.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['mode'] == 'dry' and result['production_route_ready'] is False
    assert result['developer_accepted'] is False


def test_capability_contract_binds_exact_owned_source(owned_pilot_source):
    root = owned_pilot_source.root
    assert probe.ROOT == probe.support().ROOT == root
    assert Path(probe.__file__) == root / 'scripts/verify_claude_developer_capability.py'
    contract = probe.frozen_contract('claude-opus', 'subscription')
    assert contract['source']['root'] == str(root)
    assert contract['source']['sha256'] == owned_pilot_source.fingerprints[probe.REFERENCE]
    assert contract['source']['sha256'] == probe.digest(
        (owned_pilot_source.original / probe.REFERENCE).read_bytes())
    assert contract['runner_sha256'] == owned_pilot_source.fingerprints[
        'scripts/verify_claude_developer_capability.py']
    for name, digest in contract['config_sha256'].items():
        assert digest == owned_pilot_source.fingerprints[name]
    for name, digest in contract['declarations']['declaration_source_sha256'].items():
        assert digest == owned_pilot_source.fingerprints[name]
    for name, digest in contract['effective_config_sha256'].items():
        relative = Path(name).resolve().relative_to(root)
        assert digest == owned_pilot_source.fingerprints[relative.as_posix()]
    for name in contract['config_environment'].values():
        assert Path(name).resolve().is_relative_to(root)
    assert contract['selection']['production_route_ready'] is False
    assert contract['declarations']['developer_accepted'] is False


def test_capability_contract_keeps_foreign_baseline_owner_refusal(owned_pilot_source, monkeypatch):
    """Only original metadata is simulated; the successful copy's reads are real."""
    support = probe.support()
    installed_read, installed_uid, installed_lstat = support._read, os.getuid, Path.lstat
    owned_agents = owned_pilot_source.root / 'config/agents.yaml'
    original_agents = owned_pilot_source.original / 'config/agents.yaml'
    observed = []
    def metadata(path, *args, **kwargs):
        info = installed_lstat(path, *args, **kwargs)
        if path in (owned_agents, original_agents):
            observed.append(path)
        if path == original_agents:
            fields = list(info)
            fields[4] = os.getuid() + 1
            return os.stat_result(fields)
        return info
    with monkeypatch.context() as check:
        check.setattr(Path, 'lstat', metadata)
        probe.frozen_contract('claude-opus', 'subscription')
        assert owned_agents in observed and original_agents not in observed
        check.setattr(support, 'ROOT', owned_pilot_source.original)
        with pytest.raises(support.DevelopmentPilotUnavailable, match='host_file_unverified'):
            probe.frozen_contract('claude-opus', 'subscription')
        assert original_agents in observed
        assert support._read is installed_read and os.getuid is installed_uid


def test_actual_owned_capability_cli_remains_dry(owned_pilot_source, tmp_path_factory):
    # The parent's notifier may create its autouse fixture's unit.db during
    # this test. Exercise that real poll, but keep the child's no-write oracle
    # in a separate directory; no child artifacts are exempted from it.
    parent_db = Path(os.environ['JARVIS_DB_PATH'])
    tmp_path = tmp_path_factory.mktemp('capability-dry-child')
    assert parent_db.is_relative_to(tmp_path_factory.getbasetemp())
    assert parent_db.parent != tmp_path
    from jarvis.admin.reminder_notifier import ReminderNotifier
    ReminderNotifier(post=lambda _: False).tick_once()
    assert parent_db.is_file()
    contract = probe.frozen_contract('claude-opus', 'subscription')
    runner = owned_pilot_source.root / 'scripts/verify_claude_developer_capability.py'
    result = subprocess.run([sys.executable, str(runner)], cwd=tmp_path,
        env=probe.worker_environment(tmp_path, contract), capture_output=True,
        text=True, timeout=5, check=True)
    assert json.loads(result.stdout) == {
        'record_kind': 'native40_capability_dry_run', 'model': contract['selection']['model'],
        'tools_under_test': True, 'production_route_ready': False,
        'developer_accepted': False, 'mode': 'dry',
    }
    assert list(tmp_path.iterdir()) == []


def test_static_selection_retains_ordinary_missing_tools_refusal():
    result = probe.selection('claude-opus', 'subscription')
    assert result['ordinary_route_refusal'] == 'route lacks required capabilities: tools'
    assert result['tools_under_test'] and result['production_route_ready'] is False
    with pytest.raises(routing.ModelRouteError, match='lacks required capabilities'):
        routing.resolve_model_route_checked('developer', explicit_profile='claude-opus', explicit_route='subscription')


def test_production_capture_parent_remains_fixed_mac_authority():
    assert probe.CAPTURE_PARENT == Path('/private/tmp')


def test_default_contract_hashes_loader_owned_registry_sources():
    from jarvis.agents.upgrade_agent import registry_source, load_registry_layers
    contract = probe.frozen_contract('claude-opus', 'subscription')
    layers = load_registry_layers()
    paths = {registry_source().absolute(), Path(layers['source']).absolute(),
             Path(layers['endpoints_source']).absolute()}
    assert all(contract['effective_config_sha256'][str(path)] == probe.digest(path.read_bytes()) for path in paths)
    assert contract['config_environment']['JARVIS_UPGRADE_MODELS'] == str(registry_source().absolute())


def test_mac_system_text_encoding_is_derived_not_inherited(monkeypatch):
    monkeypatch.setattr(probe.sys, 'platform', 'darwin')
    expected = f'0x{os.getuid():X}:0x0:0x0'
    monkeypatch.delenv('__CF_USER_TEXT_ENCODING', raising=False)
    assert probe.system_text_encoding() == {'__CF_USER_TEXT_ENCODING': expected}
    monkeypatch.setenv('__CF_USER_TEXT_ENCODING', expected)
    assert probe.system_text_encoding() == {'__CF_USER_TEXT_ENCODING': expected}


@pytest.mark.parametrize('bad', ['', 'arbitrary', '0xFFFF:0x0:0x0', '0x1:0x8000100:0x0'])
def test_foreign_or_malformed_system_text_encoding_refuses(monkeypatch, bad):
    monkeypatch.setattr(probe.sys, 'platform', 'darwin')
    monkeypatch.setenv('__CF_USER_TEXT_ENCODING', bad)
    with pytest.raises(probe.CapabilityUnavailable, match='current_uid_system_text_encoding_required'):
        probe.system_text_encoding()


def owned_capture_parent(tmp_path, monkeypatch):
    """Use the unchanged receipt guard's project anchor, never global /tmp."""
    root = tmp_path / 'receipt-project'
    parent = root / 'docs/acceptance/model-use-enhancements/receipts'
    parent.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(probe, 'CAPTURE_PARENT', parent)
    monkeypatch.setattr(probe.support(), 'ROOT', root)
    return parent


@pytest.mark.parametrize('kwargs', [dict(profile='missing-model', route='subscription'),
    dict(profile='claude-opus', route='direct_api'),
    dict(profile='claude-opus', route='subscription', model='voice-replacement')])
def test_unknown_model_route_or_model_mismatch_cannot_substitute(kwargs):
    with pytest.raises((routing.ModelRouteError, probe.CapabilityUnavailable)):
        probe.selection(**kwargs)


@pytest.mark.parametrize('floor', ['confidential', 'local_only'])
def test_actual_effective_policy_override_refuses_before_cli(tmp_path, monkeypatch, floor):
    access = yaml.safe_load((probe.ROOT / 'config/model_access.yaml').read_text())
    access['workloads']['developer']['privacy'] = floor
    policy = tmp_path / 'effective-policy.json'
    policy.write_text(json.dumps(access))
    monkeypatch.setenv('JARVIS_MODEL_ACCESS_CONFIG', str(policy))
    assert routing.resolve_policy('developer', include_preferences=False).privacy == floor
    with pytest.raises(routing.ModelRouteError):
        probe.selection('claude-opus', 'subscription')


def test_effective_registry_override_binds_model_and_whole_registry(tmp_path, monkeypatch):
    profiles = yaml.safe_load((probe.ROOT / 'config/model_profiles.yaml').read_text())
    for profile in profiles['profiles']:
        if profile['name'] == 'claude-opus':
            profile['model'] = 'actual-configured-private-unit-model'
    path = tmp_path / 'model_profiles.yaml'
    path.write_text(yaml.safe_dump(profiles))
    (tmp_path / 'model_endpoints.yaml').write_bytes((probe.ROOT / 'config/model_endpoints.yaml').read_bytes())
    monkeypatch.setenv('JARVIS_UPGRADE_MODELS', str(path))
    result = probe.selection('claude-opus', 'subscription')
    assert result['model'] == 'actual-configured-private-unit-model'
    contract = probe.frozen_contract('claude-opus', 'subscription')
    assert contract['config_environment']['JARVIS_UPGRADE_MODELS'] == str(path)
    assert contract['effective_config_sha256'][str(path)] == probe.digest(path.read_bytes())
    with pytest.raises(probe.CapabilityUnavailable, match='requested_model_mismatch'):
        probe.selection('claude-opus', 'subscription', 'claude-opus')


@pytest.mark.parametrize('limits', [routing.WorkloadLimits(1), routing.WorkloadLimits(None, None, .01)])
def test_native_unsupported_effective_caps_are_not_cleared(monkeypatch, limits):
    original = routing.resolve_policy
    monkeypatch.setattr(routing, 'resolve_policy', lambda *a, **k: replace(original(*a, **k), limits=limits))
    with pytest.raises(probe.CapabilityUnavailable, match='native_provider_limits_unsupported'):
        probe.selection('claude-opus', 'subscription')


def test_inherited_sensitive_turn_or_typed_private_floor_refuses():
    with pytest.raises(routing.ModelRouteError):
        probe.selection('claude-opus', 'subscription', input_policy=DataPolicy('local_only', 'private-source'))
    with pytest.raises(probe.CapabilityUnavailable, match='typed_input_policy_required'):
        probe.selection('claude-opus', 'subscription', input_policy={'privacy': 'approved_external'})
    current_sensitive_turn.get().arm('private-fixture')
    with pytest.raises(routing.ModelRouteError):
        probe.selection('claude-opus', 'subscription')


def test_inherited_authentic_output_budget_refuses_without_null_clearing():
    from jarvis.model_budget import begin_model_task_budget
    budget = begin_model_task_budget('developer', str(uuid.uuid4()), routing.WorkloadLimits(3))
    with pytest.raises(probe.CapabilityUnavailable, match='native_provider_limits_unsupported'):
        probe.selection('claude-opus', 'subscription', task_budget=budget)
    with pytest.raises(Exception):
        probe.selection('claude-opus', 'subscription', task_budget=replace(budget, limits=routing.WorkloadLimits()))


@pytest.mark.parametrize('limits', [routing.WorkloadLimits(None, 60, .01), routing.WorkloadLimits(3, 60)])
def test_durable_caps_cannot_be_cleared_in_replaced_handle(limits):
    from jarvis.model_budget import begin_model_task_budget
    budget = begin_model_task_budget('developer', str(uuid.uuid4()), limits)
    for handle in (budget, replace(budget, limits=routing.WorkloadLimits(), spend_ceiling_usd=None)):
        with pytest.raises(probe.CapabilityUnavailable, match='native_provider_limits_unsupported'):
            probe.selection('claude-opus', 'subscription', task_budget=handle)


def test_old_authentic_transient_handle_retains_new_durable_restriction():
    from jarvis.model_budget import begin_model_task_budget
    parent = str(uuid.uuid4())
    old = begin_model_task_budget('developer', parent, routing.WorkloadLimits())
    assert old.scope_id is None
    begin_model_task_budget('developer', parent, routing.WorkloadLimits(None, 60, .01))
    with pytest.raises(probe.CapabilityUnavailable, match='native_provider_limits_unsupported'):
        probe.selection('claude-opus', 'subscription', task_budget=old)


def test_genuine_planning_to_developer_child_preserves_whole_deadline_path():
    from jarvis.model_budget import begin_model_task_budget, begin_model_child_budget
    parent = begin_model_task_budget('planning', str(uuid.uuid4()), routing.WorkloadLimits(None, 20))
    child = begin_model_child_budget(parent, 'developer', routing.WorkloadLimits(None, 60))
    result = probe.selection('claude-opus', 'subscription', task_budget=child)
    budgets, remaining = probe.task_budget_authority(child)
    assert result['tools_under_test'] and result['production_route_ready'] is False
    assert 0 < remaining <= 20 and any(b.workload == 'planning' for b in budgets)


@pytest.mark.parametrize('limits', [routing.WorkloadLimits(3, 60), routing.WorkloadLimits(None, 60, .01)])
def test_genuine_child_cannot_drop_ancestor_provider_caps(limits):
    from jarvis.model_budget import begin_model_task_budget, begin_model_child_budget
    parent = begin_model_task_budget('planning', str(uuid.uuid4()), limits)
    child = begin_model_child_budget(parent, 'developer', routing.WorkloadLimits())
    with pytest.raises(probe.CapabilityUnavailable, match='native_provider_limits_unsupported'):
        probe.selection('claude-opus', 'subscription', task_budget=child)
    with pytest.raises(Exception):
        probe.selection('claude-opus', 'subscription',
            task_budget=replace(child, owner=replace(parent, limits=routing.WorkloadLimits())))


@pytest.fixture
def reference(tmp_path, monkeypatch):
    root = tmp_path / 'registered-project'
    (root / 'docs').mkdir(parents=True)
    path = root / probe.REFERENCE
    path.write_bytes(b'Public registered named reference.\n')
    monkeypatch.setattr(probe, 'ROOT', root)
    return path, probe.pin_reference()


@pytest.mark.parametrize('change', ['bytes', 'inode', 'mode', 'symlink'])
def test_reference_changes_refuse_even_with_same_name(reference, change):
    path, pin = reference
    if change == 'bytes': path.write_bytes(b'PRIVATE_CHANGED_SOURCE_CANARY')
    if change == 'inode':
        path.rename(path.with_suffix('.old')); path.write_bytes(pin.raw)
    if change == 'mode': path.chmod(0o600)
    if change == 'symlink':
        path.rename(path.with_suffix('.old')); path.symlink_to(path.with_suffix('.old'))
    with pytest.raises(probe.CapabilityUnavailable):
        probe.check_reference(pin)


def scope(name='repo_read_file', args=None, policy=None):
    return make_tool_execution_scope(str(uuid.uuid4()), 'capability:0', 'call-unit', name,
        args if args is not None else {'path': probe.REFERENCE}, policy or DataPolicy('approved_external', 'public-unit'))


class ReadRegistry:
    def __init__(self, pin, level='approved_external'):
        self.pin, self.level, self.calls = pin, level, []
    async def call_classified(self, name, arguments, servers, *, execution_scope):
        self.calls.append((name, arguments, servers))
        body = {'ok': True, 'path': probe.REFERENCE, 'bytes': len(self.pin.raw), 'content': self.pin.raw.decode()}
        return issue_tool_result(execution_scope, json.dumps(body), DataPolicy(self.level, 'unit-host-source'),
                                 'repository:' + probe.digest(self.pin.root.encode()))


async def test_real_sealed_source_is_checked_before_continuation(reference):
    _, pin = reference
    registry = ReadRegistry(pin)
    guard = probe.PublicReferenceGuard(registry, pin, lambda: None)
    content = await guard.call('repo_read_file', {'path': probe.REFERENCE}, scope())
    assert json.loads(content)['content'] == pin.raw.decode()
    assert len(registry.calls) == guard.reads == 1
    assert guard.source_evidence[0]['content_digest'] == probe.digest(content.encode())


@pytest.mark.parametrize('name,args', [('selfedit_finish', {}), ('screen_view', {}), ('runlog_detail', {}),
    ('commit', {'action_id': 1}), ('repo_read_file', {'path': '.env'}), ('repo_read_file', {'path': probe.REFERENCE, 'privacy': 'approved_external'})])
async def test_private_mutation_and_other_paths_never_enter_registry(reference, name, args):
    _, pin = reference
    registry = ReadRegistry(pin)
    guard = probe.PublicReferenceGuard(registry, pin, lambda: None)
    result = json.loads(await guard.call(name, args, scope(name, args)))
    assert result == {'error': 'outside_public_capability_probe', 'ok': False}
    assert registry.calls == [] and guard.refusals == 1


@pytest.mark.parametrize('level', ['confidential', 'local_only'])
async def test_private_source_result_never_reaches_continuation(reference, level):
    _, pin = reference
    guard = probe.PublicReferenceGuard(ReadRegistry(pin, level), pin, lambda: None)
    with pytest.raises(probe.CapabilityUnavailable, match='reference_source_protected'):
        await guard.call('repo_read_file', {'path': probe.REFERENCE}, scope())
    assert not guard.source_evidence


async def test_private_input_floor_refuses_before_registry(reference):
    _, pin = reference
    registry = ReadRegistry(pin)
    guard = probe.PublicReferenceGuard(registry, pin, lambda: None)
    with pytest.raises(probe.CapabilityUnavailable):
        await guard.call('repo_read_file', {'path': probe.REFERENCE}, scope(policy=DataPolicy('confidential')))
    assert not registry.calls


async def test_late_source_change_inside_actual_return_refuses(reference):
    path, pin = reference
    registry = ReadRegistry(pin)
    original = registry.call_classified
    async def changed(*a, **k):
        result = await original(*a, **k)
        path.write_bytes(b'PRIVATE_AFTER_READ_CANARY')
        return result
    registry.call_classified = changed
    guard = probe.PublicReferenceGuard(registry, pin, lambda: None)
    with pytest.raises(probe.CapabilityUnavailable):
        await guard.call('repo_read_file', {'path': probe.REFERENCE}, scope())
    assert not guard.source_evidence


async def test_provider_json_or_replaced_policy_cannot_issue_source_approval(reference):
    _, pin = reference
    registry = ReadRegistry(pin, 'confidential')
    original = registry.call_classified
    async def forged(*a, **k):
        result = await original(*a, **k)
        return replace(result, policy=DataPolicy('approved_external', 'provider-label'))
    registry.call_classified = forged
    guard = probe.PublicReferenceGuard(registry, pin, lambda: None)
    with pytest.raises(Exception):
        await guard.call('repo_read_file', {'path': probe.REFERENCE}, scope())
    assert not guard.source_evidence


def test_fresh_environment_does_not_mutate_or_borrow_parent_authority(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'PUBLIC_SYNTHETIC_NOT_A_KEY')
    monkeypatch.setenv('JARVIS_SERVICE_TOKEN', 'PUBLIC_SYNTHETIC_NOT_A_TOKEN')
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.invalid')
    before = dict(os.environ)
    contract = probe.frozen_contract('claude-opus', 'subscription')
    env = probe.worker_environment(tmp_path, contract)
    assert dict(os.environ) == before
    assert not {'OPENAI_API_KEY', 'JARVIS_SERVICE_TOKEN', 'HTTPS_PROXY'} & set(env)
    assert env['JARVIS_DB_PATH'] == str(tmp_path / 'probe.db')
    assert env['JARVIS_MODEL_ACCESS_CONFIG'] == contract['config_environment']['JARVIS_MODEL_ACCESS_CONFIG']


@pytest.fixture
def worker_boundary(tmp_path, monkeypatch):
    contract = probe.frozen_contract('claude-opus', 'subscription')
    parent = owned_capture_parent(tmp_path, monkeypatch)
    with tempfile.TemporaryDirectory(prefix='mortimer-native40-capability-', dir=parent) as temporary:
        directory = Path(temporary)
        directory.chmod(0o700)
        packet = {'contract': contract, 'timeout': 45, 'started_at': time.time()}
        request = directory / 'request.json'
        request.write_bytes(probe.canonical(packet)); request.chmod(0o600)
        env = probe.worker_environment(directory, contract)
        monkeypatch.chdir(directory)
        for key in list(os.environ): monkeypatch.delenv(key, raising=False)
        for key, value in env.items(): monkeypatch.setenv(key, value)
        yield request, packet


def test_owned_worker_boundary_accepts_exact_isolation(worker_boundary, monkeypatch):
    # Pytest adds this after the fixture yields; it is intentionally not part
    # of the production fresh-worker environment.
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    probe.validate_worker_boundary(*worker_boundary)


@pytest.mark.parametrize('change', ['cwd', 'mode', 'db', 'token', 'keyhealth', 'screen', 'admin'])
def test_direct_worker_cannot_borrow_ambient_authority(worker_boundary, monkeypatch, change):
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    request, packet = worker_boundary
    if change == 'cwd': monkeypatch.chdir(probe.CAPTURE_PARENT)
    elif change == 'mode': request.parent.chmod(0o755)
    else:
        key, value = {'db': ('JARVIS_DB_PATH', '/private/tmp/unowned.db'),
            'token': ('JARVIS_SERVICE_TOKEN', 'PUBLIC_SYNTHETIC'), 'keyhealth': ('JARVIS_KEY_HEALTH_ENABLED', 'true'),
            'screen': ('JARVIS_SCREEN_ENABLED', 'true'), 'admin': ('JARVIS_ADMIN_URL', 'http://foreign.invalid')}[change]
        monkeypatch.setenv(key, value)
    with pytest.raises(probe.CapabilityUnavailable): probe.validate_worker_boundary(request, packet)


@pytest.mark.parametrize('case', ['positive', 'foreign_uid', 'malformed', 'extra_environment'])
def test_actual_new_python_worker_checks_system_marker_only(worker_boundary, case):
    request, packet = worker_boundary
    environment = probe.worker_environment(request.parent, packet['contract'])
    program = r'''
import json, os, sys
from pathlib import Path
from scripts import verify_claude_developer_capability as cap
# macOS normalizes an inherited forged marker at exec; create the inverse
# after that OS startup but before this exact application boundary check.
if sys.argv[2]=='foreign_uid': os.environ['__CF_USER_TEXT_ENCODING']=f'0x{os.getuid()+1:X}:0x0:0x0'
if sys.argv[2]=='malformed': os.environ['__CF_USER_TEXT_ENCODING']='not-a-system-marker'
if sys.argv[2]=='extra_environment': os.environ['UNAPPROVED_EXTRA_AUTHORITY']='PUBLIC_SYNTHETIC_NOT_A_CREDENTIAL'
request=Path(sys.argv[1]);packet=json.loads(request.read_bytes())
# The production constant remains fixed; this inert test uses only the
# pytest-owned project receipt anchor already captured by worker_boundary.
cap.CAPTURE_PARENT=request.parent.parent
try:
    cap.validate_worker_boundary(request,packet)
except cap.CapabilityUnavailable as exc:
    print('REFUSED:'+str(exc))
else:
    print('BOUNDARY_ACCEPTED_NO_NATIVE_OR_MCP')
'''
    import subprocess
    result = subprocess.run([sys.executable, '-c', program, str(request), case],
        cwd=request.parent, env=environment, capture_output=True, text=True, timeout=5, check=True)
    if case == 'positive': assert result.stdout.strip() == 'BOUNDARY_ACCEPTED_NO_NATIVE_OR_MCP'
    else: assert result.stdout.startswith('REFUSED:') and 'BOUNDARY_ACCEPTED' not in result.stdout
    assert not (request.parent/'probe.db').exists() and not (request.parent/'mcp-discovery.json').exists()
    assert not (request.parent/'result.json').exists()


def test_no_clobber_reservation_precedes_any_live_capture(tmp_path, monkeypatch):
    contract = probe.frozen_contract('claude-opus', 'subscription')
    parent = owned_capture_parent(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'frozen_contract', lambda *a, **k: contract)
    with tempfile.TemporaryDirectory(prefix='native40-receipt-', dir=parent) as temporary:
        output = Path(temporary) / 'receipt.json'
        output.write_bytes(b'owned previous evidence')
        monkeypatch.setattr(probe, 'fresh_capture', lambda *a, **k: pytest.fail('inference'))
        assert probe.main(['--live', '--output', str(output)]) == 2
        assert output.read_bytes() == b'owned previous evidence'


@pytest.mark.asyncio
async def test_actual_six_mcp_discovery_and_guarded_reference_need_no_service_identity(tmp_path, monkeypatch):
    from jarvis.skills.registry import SkillRegistry
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(probe.ROOT))
    monkeypatch.setenv('JARVIS_ADMIN_URL', 'http://127.0.0.1:1')
    monkeypatch.setenv('JARVIS_TIMEZONE', 'UTC')
    data = yaml.safe_load((probe.ROOT / 'config/mcp_servers.yaml').read_text())
    selected = [entry for entry in data['servers'] if entry['name'] in probe.support().DEVELOPER_SERVERS]
    path = tmp_path / 'six.json'
    path.write_bytes(probe.canonical({'servers': selected}))
    registry = SkillRegistry(path)
    owners = []
    try:
        await registry.start()
        owners = list(registry._handles.values())
        actual = probe.support().inspect_live_developer_registry(registry)
        schemas = registry.openai_tools(list(probe.support().DEVELOPER_SERVERS))
        refs = probe.references(schemas)
        assert schemas == await probe.installed_schemas()
        assert len(refs) == 40 and {item.name for item in refs} == set(actual['declared_tool_names'])
        guard = probe.PublicReferenceGuard(registry, probe.pin_reference(), lambda: None)
        result = await guard.call('repo_read_file', {'path': probe.REFERENCE}, scope())
        assert json.loads(result)['path'] == probe.REFERENCE and guard.reads == 1
        assert 'JARVIS_SERVICE_TOKEN' not in os.environ
    finally:
        await registry.stop()
    assert all(owner.task.done() for owner in owners)


def session():
    request = ModelExecutionRequest('developer', 'native-unit:0', str(uuid.uuid4()), '',
        tools=(ModelToolReference('repo_read_file', {'type': 'object', 'properties': {'path': {'type': 'string'}}}),),
        data_policy=DataPolicy('approved_external'), timeout_s=5)
    return probe.observed_session_type()(request, SimpleNamespace(model='unit-model'),
        {'messages': [{'role': 'user', 'content': 'Public inert frame.'}]}, '/NOT-A-CLI')


@pytest.mark.parametrize('kind', ['model', 'bytes', 'bash'])
async def test_actual_native_parser_observer_refuses_model_output_or_builtin_drift(kind):
    from jarvis.subscription import SubscriptionCapabilityError
    native = session()
    reader = asyncio.StreamReader(limit=2 * probe.OUTPUT_BYTES)
    model = 'foreign-model' if kind == 'model' else 'unit-model'
    blocks = [{'type': 'text', 'text': 'x' * probe.OUTPUT_BYTES}] if kind == 'bytes' else [
        {'type': 'tool_use', 'id': 'call-native', 'name': 'Bash', 'input': {'command': 'inert forbidden'}}]
    reader.feed_data(probe.canonical({'type': 'assistant', 'message': {'model': model, 'content': blocks}}) + b'\n')
    reader.feed_eof()
    native.process = SimpleNamespace(stdout=reader)
    await native._stdout()
    failure = await native.queue.get()
    assert isinstance(failure, (probe.CapabilityUnavailable, SubscriptionCapabilityError, Exception))
    assert not native.pending and native.call_count == 0
    if kind == 'bash':
        assert isinstance(failure, SubscriptionCapabilityError) and native.observed_native_tools == ['Bash']
    native.process = None
    await native.close()


async def test_actual_native_hook_observation_is_bound_and_forgery_refuses():
    from jarvis import subscription_tools as native_module
    native = session()
    future = asyncio.get_running_loop().create_future(); future.set_result('public result')
    pending = native_module._Pending('call-unit', 'repo_read_file', {'path': probe.REFERENCE}, future,
        native.task_id, claimed=True, constraints=probe.CONSTRAINT)
    native.completed[pending.call_id] = pending
    written = []
    async def write(value): written.append(value)
    native._write_native = write
    event = {'request_id': 'hook-unit', 'request': {'subtype': 'hook_callback',
        'callback_id': native_module._POST_TOOL_CALLBACK, 'tool_use_id': 'call-unit', 'input': {
        'hook_event_name': 'PostToolUse', 'tool_use_id': 'call-unit',
        'tool_name': 'mcp__mortimer__repo_read_file', 'tool_input': {'path': probe.REFERENCE}}}}
    await native._post_tool_hook(event)
    assert pending.hook_done and len(written) == len(native.hook_evidence) == 1
    assert native.hook_evidence[0]['constraints_sha256'] == probe.digest(probe.CONSTRAINT.encode())
    with pytest.raises(native_module.SubscriptionCapabilityError): await native._post_tool_hook(event)
    assert len(written) == 1
    await native.close()


@pytest.mark.asyncio
async def test_loopback_rejects_negative_lengths_and_drains_actual_thread(tmp_path):
    from urllib.parse import urlsplit
    refs = (ModelToolReference('repo_read_file', {'type': 'object', 'properties': {}}),)
    async with storage_scope(db_path=tmp_path / 'loop.db', costs_db_path=tmp_path / 'loop-costs.db') as stores:
        async with probe.loopback_fixture(tmp_path, 'unit-model', refs) as fixture:
            endpoint = urlsplit(fixture['environment']['ANTHROPIC_BASE_URL'])
            reader, writer = await asyncio.open_connection('127.0.0.1', endpoint.port)
            writer.write(b'POST /messages HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: -1\r\nConnection: close\r\n\r\n')
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), timeout=3)
            writer.close(); await writer.wait_closed()
            assert response.startswith(b'HTTP/1.0 413') and not fixture['observations']
        assert fixture['closed']
    assert stores.cleanup_verified and stores.pending_workers == 0


@pytest.fixture
async def captured(tmp_path):
    """In-memory validation fixture; fake executable cannot approve real CLI."""
    from jarvis.subscription_tools import (PROTOCOL, NATIVE_CONTROL_CONTRACT, NATIVE_PROTOCOL_SOURCE,
        NATIVE_ISOLATION_ENV, _claude_tool_argv)
    from jarvis.subscription import _json_digest
    contract = probe.frozen_contract('claude-opus', 'subscription')
    binary = tmp_path / 'INERT-NOT-AN-INSTALLED-CLI'
    binary.write_bytes(b'UNIT VALIDATION FIXTURE, NEVER EXECUTED')
    identity = {'path': str(binary), 'version': '2.1.290 (Claude Code)', 'sha256': probe.digest(binary.read_bytes())}
    contract['runtime'] = identity
    contract['host_limits'] = probe.diagnostic_host_limits(45)
    schemas = await probe.installed_schemas()
    refs = probe.references(schemas)
    names = [ref.name for ref in refs]
    pin = probe.pin_reference()
    sources = []
    def phase(tools):
        parent = str(uuid.uuid4())
        hooks, calls = [], []
        for index, tool in enumerate(tools):
            task = f'native-capability:{parent}:{index}'
            call_id = 'unit-' + uuid.uuid4().hex
            args = {'path': probe.REFERENCE} if tool == 'repo_read_file' else {}
            content = json.dumps({'ok': True, 'path': probe.REFERENCE, 'bytes': len(pin.raw),
                'content': pin.raw.decode()}) if tool == 'repo_read_file' else '{"error":"outside_public_capability_probe","ok":false}'
            source_scope = 'repository:' + probe.digest(pin.root.encode()) if tool == 'repo_read_file' else 'host-generated-capability-refusal'
            execution_scope = make_tool_execution_scope(parent, task, call_id, tool, args, DataPolicy('approved_external'))
            envelope = issue_tool_result(execution_scope, content, DataPolicy('approved_external'), source_scope)
            sources.append({'parent_request_id': parent, 'task_id': task, 'tool_call_id': call_id, 'tool': tool,
                'argument_digest': execution_scope.argument_digest, 'policy': 'approved_external', 'content': content,
                'content_digest': envelope.content_digest, 'source_scope': source_scope})
            hooks.append({'request_id': 'hook-' + call_id, 'parent_request_id': parent, 'task_id': task,
                'tool_call_id': call_id, 'tool': tool, 'arguments_sha256': probe.digest(probe.canonical(args)),
                'constraints_sha256': probe.digest(probe.CONSTRAINT.encode()), 'hook_done': True})
            calls.append({'tool_call_id': call_id, 'name': 'mcp__mortimer__' + tool,
                          'arguments_sha256': probe.digest(probe.canonical(args))})
        return {'native_tool_call_observed': True, 'unknown_tool_rejected': True,
            'system_constraints_observed': True, 'terminal_success_without_error_items': True,
            'cleanup_verified': True, 'observed_models': [contract['selection']['model']],
            'parent_request_id': parent, 'origin_task_id': f'native-capability:{parent}:0',
            'hook_evidence': hooks, 'native_calls': calls, 'native_tool_names': [call['name'] for call in calls],
            'output_bytes': 100}
    # Match the observed 2.1.290 sorted API menu; Registry/argv order stays above.
    packets = lambda count: [dict(names=probe.wire_tool_names(refs), schemas_match=True,
        model=contract['selection']['model'], canary_absent=True, synthetic_auth_only=True,
        constraint_present=True) for _ in range(count)]
    negative_parent = str(uuid.uuid4())
    observations = {'live': phase(['repo_read_file']), 'isolation': phase(['repo_read_file', 'selfedit_finish']),
        'negative': {'parent_request_id': negative_parent, 'origin_task_id': f'native-capability:{negative_parent}:0',
                     'observed_models': [contract['selection']['model']],
                     'native_tool_names': ['Bash'], 'unadvertised_host_tool_rejected': True,
                     'native_calls': [{'tool_call_id': 'unit-bash', 'name': 'Bash',
                         'arguments_sha256': probe.digest(probe.canonical({'command': 'inert synthetic negative'}))}],
                     'native_host_ingress_count': 0, 'cleanup_verified': True, 'output_bytes': 100},
        'isolation_http': packets(3), 'negative_http': packets(1), 'sources': sources}
    proof = {'schema_version': 1, 'provider': 'claude', 'model': contract['selection']['model'],
        'frozen_contract': contract, 'executable': identity, 'schemas': schemas, 'tool_names': names,
        'servers': list(probe.support().DEVELOPER_SERVERS), 'protocol': PROTOCOL,
        'record_kind': 'installed_cli_exact_schema_protocol_evidence', 'runtime_receipt': True,
        'tools_under_test': True, 'tool_schema_sha256': _json_digest([{'name': ref.name,
            'description': ref.description, 'parameters': dict(ref.parameters)} for ref in refs]),
        'invocation_sha256': _json_digest(_claude_tool_argv(identity['path'], contract['selection']['model'],
            '<mcp-config>', '<system-prompt>', names)),
        'control_protocol_sha256': _json_digest(NATIVE_CONTROL_CONTRACT),
        'isolation_env_sha256': _json_digest(NATIVE_ISOLATION_ENV), 'protocol_source': NATIVE_PROTOCOL_SOURCE,
        'observations': observations, 'host_limits': dict(contract['host_limits']),
        **{name: True for name in ('native_tool_call_observed', 'unknown_tool_rejected', 'unadvertised_host_tool_rejected',
            'unadvertised_host_tool_side_effect_absent', 'customization_canaries_absent', 'builtins_disabled',
            'system_constraints_observed', 'terminal_success_without_error_items', 'api_credentials_absent',
            'private_mutation_refused_before_ingress', 'native_cleanup_verified', 'storage_cleanup_verified', 'registry_cleanup_verified')},
        **{name: False for name in ('production_route_ready', 'developer_accepted', 'workload_quality_accepted',
            'mar_i_complete', 'billing_verified', 'full_profile_verified', 'provider_token_or_spend_bound_verified')}}
    return proof, contract, schemas


async def test_cross_evidence_validator_accepts_only_complete_inert_binding(captured):
    value, contract, schemas = captured
    probe.validate_capture(value, contract, expected_schemas=schemas)
    assert value['developer_accepted'] is value['mar_i_complete'] is False


@pytest.mark.parametrize('change', ['source_parent', 'source_task', 'source_toolcall', 'source_args',
    'source_content', 'source_scope', 'hook_parent', 'hook_task', 'hook_toolcall', 'hook_args',
    'native_args', 'menu', 'model', 'string_bool', 'quality'])
async def test_complete_looking_unrelated_source_hook_menu_or_claim_refuses(captured, change):
    value, contract, schemas = captured
    source = value['observations']['sources'][0]
    hook = value['observations']['live']['hook_evidence'][0]
    if change.startswith('source_'):
        key = {'source_parent': 'parent_request_id', 'source_task': 'task_id', 'source_toolcall': 'tool_call_id',
            'source_args': 'argument_digest', 'source_content': 'content', 'source_scope': 'source_scope'}[change]
        source[key] = 'UNRELATED_COMPLETE_LOOKING_UNIT_VALUE'
        if key == 'content': source['content_digest'] = probe.digest(source['content'].encode())
    elif change.startswith('hook_'):
        key = {'hook_parent': 'parent_request_id', 'hook_task': 'task_id', 'hook_toolcall': 'tool_call_id',
            'hook_args': 'arguments_sha256'}[change]
        hook[key] = 'UNRELATED_UNIT_VALUE'
    elif change == 'native_args': value['observations']['live']['native_calls'][0]['arguments_sha256'] = '0' * 64
    elif change == 'menu': value['schemas'] = list(reversed(value['schemas']))
    elif change == 'model': value['model'] = 'voice-replacement'
    elif change == 'string_bool': value['native_tool_call_observed'] = 'true'
    elif change == 'quality': value['developer_accepted'] = True
    with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
        probe.validate_capture(value, contract, expected_schemas=schemas)


@pytest.mark.parametrize('missing', ['sources', 'live', 'isolation_http', 'negative'],
    ids=['missing_sources', 'missing_native_round', 'missing_isolation_http', 'missing_negative'])
async def test_incomplete_proof_cannot_be_published(captured, missing):
    value, contract, schemas = captured
    value['observations'].pop(missing)
    with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
        probe.validate_capture(value, contract, expected_schemas=schemas)


@pytest.mark.parametrize('change', ['false_final_constraint', 'missing_final_constraint', 'missing_host_limits',
    'infinite_deadline', 'longer_deadline', 'shorter_deadline', 'wrong_output_bound', 'wrong_tool_bound',
    'bool_tool_bound', 'duplicate_hooks', 'empty_hook', 'unsafe_hook'])
async def test_parent_rejects_missing_or_forged_host_constraints(captured, change):
    value, contract, schemas = captured
    if change == 'false_final_constraint': value['observations']['isolation_http'][-1]['constraint_present'] = False
    elif change == 'missing_final_constraint': value['observations']['isolation_http'][-1].pop('constraint_present')
    elif change == 'missing_host_limits': value.pop('host_limits')
    elif change == 'duplicate_hooks':
        hooks = value['observations']['isolation']['hook_evidence']
        hooks[1]['request_id'] = hooks[0]['request_id']
    elif change in ('empty_hook', 'unsafe_hook'):
        value['observations']['live']['hook_evidence'][0]['request_id'] = '' if change == 'empty_hook' else 'hook\nforged'
    else:
        key, bad = {'infinite_deadline': ('deadline_seconds', float('inf')),
            'longer_deadline': ('deadline_seconds', 46), 'shorter_deadline': ('deadline_seconds', 44),
            'wrong_output_bound': ('observed_output_bytes_per_round', probe.OUTPUT_BYTES + 1),
            'wrong_tool_bound': ('native_tool_calls_per_round', 3),
            'bool_tool_bound': ('native_tool_calls_per_round', True)}[change]
        value['host_limits'][key] = bad
    with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
        probe.validate_capture(value, contract, expected_schemas=schemas)


@pytest.mark.parametrize('phase', ['live', 'isolation', 'negative'], ids=['public_round', 'isolated_round', 'bash_round'])
@pytest.mark.parametrize('bad', [None, -1, 0, True, float('nan'), probe.OUTPUT_BYTES + 1])
async def test_all_rounds_require_real_bounded_output_byte_counts(captured, phase, bad):
    value, contract, schemas = captured
    if bad is None: value['observations'][phase].pop('output_bytes')
    else: value['observations'][phase]['output_bytes'] = bad
    with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
        probe.validate_capture(value, contract, expected_schemas=schemas)


async def test_expired_entry_never_creates_worker_or_samples_cli(monkeypatch):
    contract = probe.frozen_contract('claude-opus', 'subscription')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', lambda *a, **k: pytest.fail('worker'))
    from jarvis import subscription_tools
    monkeypatch.setattr(subscription_tools, 'claude_tool_runtime_identity', lambda: pytest.fail('CLI'))
    with pytest.raises(probe.CapabilityUnavailable, match='host_deadline_exhausted'):
        await probe.fresh_capture(contract, .01, time.time() - 1)


def inert_worker_parent(monkeypatch):
    """Only lifecycle is substituted; the child is a real owned Python process."""
    from jarvis import subscription_tools
    frozen = {'selection': {'profile': 'claude-opus', 'model': 'INERT-NO-NATIVE-CLI',
        'policy': {'limits': {'deadline_seconds': None}}}}
    monkeypatch.setattr(probe, 'selection', lambda *a, **k: {})
    monkeypatch.setattr(probe, 'frozen_contract', lambda *a, **k: frozen)
    async def schemas(): return []
    monkeypatch.setattr(probe, 'installed_schemas', schemas)
    monkeypatch.setattr(subscription_tools, 'claude_tool_runtime_identity',
        lambda: {'path': '/INERT-NO-CLI', 'version': 'INERT', 'sha256': '0' * 64})
    return frozen


async def test_output_overflow_retains_exact_unresolved_worker_and_readers(tmp_path, monkeypatch):
    frozen = inert_worker_parent(monkeypatch)
    owned_capture_parent(tmp_path, monkeypatch)
    real_spawn = asyncio.create_subprocess_exec
    read_fd, write_fd = os.pipe()
    owned = {}
    async def spawn(*args, **kwargs):
        process = await real_spawn(sys.executable, '-u', '-c',
            "import os,signal; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "os.write(2,b'ACTUAL_CHILD_READY\\n'); "
            "[os.write(1,b'X'*65536) for _ in range(17)]; os.read(int(__import__('sys').argv[1]),1)",
            str(read_fd), pass_fds=(read_fd,), **kwargs)
        assert await asyncio.wait_for(process.stderr.readline(), 5) == b'ACTUAL_CHILD_READY\n'
        owned.update(process=process, directory=Path(kwargs['cwd']))
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(probe, 'WORKER_DRAIN_SECONDS', .01)
    owner = None
    try:
        with pytest.raises(probe.WorkerCleanupUnavailable) as failure:
            await probe.fresh_capture(frozen, 10, time.time())
        owner = failure.value.ownership
        assert owner.process is owned['process'] and owner.directory == owned['directory']
        assert probe._WORKER_QUARANTINE[str(owner.directory)] is owner
        assert owner.stop_requested and owner.quarantine and owner.process.returncode is None
        assert not owner.lifetime.done() and all(not reader.done() for reader in owner.readers)
        record = json.loads((owner.directory / 'quarantine.json').read_bytes())
        assert record['worker_pid'] == owner.process.pid and record['scratch_retained'] is True
        assert record['cleanup_verified'] is False and record['evidence_published'] is True
        assert record['readers_done'] is record['process_exited'] is False
        assert (owner.directory / 'request.json').is_file() and not (owner.directory / 'result.json').exists()
        os.write(write_fd, b'R')
        await asyncio.wait_for(asyncio.shield(owner.lifetime), 5)
        assert owner.process.returncode == 0 and all(reader.done() for reader in owner.readers)
        assert owner.cleanup_verified is False  # actual drain is not native protocol success
    finally:
        os.close(read_fd); os.close(write_fd)
        process = owned.get('process')
        if process is not None and process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        if owner is not None:
            await asyncio.gather(owner.lifetime, return_exceptions=True)
            probe._WORKER_QUARANTINE.pop(str(owner.directory), None)


async def test_explicit_cancel_drains_signal_aware_real_worker_before_return(tmp_path, monkeypatch):
    frozen = inert_worker_parent(monkeypatch)
    owned_capture_parent(tmp_path, monkeypatch)
    real_spawn = asyncio.create_subprocess_exec
    read_fd, write_fd = os.pipe()
    ack_read, ack_write = os.pipe()
    entered = asyncio.Event()
    owned = {}
    async def spawn(*args, **kwargs):
        program = r"""
import os, signal, sys
def cancel(*args): os.write(int(sys.argv[2]),b'S')
signal.signal(signal.SIGTERM,cancel)
os.write(2,b'ACTUAL_CHILD_READY\n')
os.read(int(sys.argv[1]),1)
"""
        process = await real_spawn(sys.executable, '-u', '-c', program, str(read_fd), str(ack_write),
            pass_fds=(read_fd, ack_write), **kwargs)
        assert await asyncio.wait_for(process.stderr.readline(), 5) == b'ACTUAL_CHILD_READY\n'
        owned.update(process=process, directory=Path(kwargs['cwd']))
        entered.set()
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    task = asyncio.create_task(probe.fresh_capture(frozen, 10, time.time()))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        assert await asyncio.wait_for(asyncio.to_thread(os.read, ack_read, 1), 5) == b'S'
        assert not task.done() and owned['process'].returncode is None
        os.write(write_fd, b'R')
        with pytest.raises(asyncio.CancelledError): await asyncio.wait_for(task, 5)
        assert owned['process'].returncode == 0
        assert str(owned['directory']) not in probe._WORKER_QUARANTINE
        assert owned['directory'].is_dir()  # failed/cancelled work remains auditable
        assert not (owned['directory'] / 'result.json').exists()
    finally:
        for descriptor in (read_fd, write_fd, ack_read, ack_write): os.close(descriptor)
        process = owned.get('process')
        if process is not None and process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_actual_signal_worker_retains_blocked_store_operation_until_drained(tmp_path):
    """Cancel only after actual worker ingress; release the actual pipe last."""
    read_fd, write_fd = os.pipe()
    program = '''
import asyncio, os, sys
from pathlib import Path
from scripts import verify_claude_developer_capability as probe
from jarvis.storage_context import storage_scope, state_to_thread
root = Path(sys.argv[1])
descriptor = int(sys.argv[2])
async def held_acquire(directory, contract, timeout, started_at):
    async with storage_scope(db_path=root/'unit.db', costs_db_path=root/'costs.db') as stores:
        def blocked():
            print('ACTUAL_WORKER_ENTERED', flush=True)
            os.read(descriptor, 1)
            print('ACTUAL_WORKER_RETURNED', flush=True)
        try:
            await state_to_thread(blocked)
        finally:
            print('CANCELLATION_DRAIN_STARTED', flush=True)
    assert stores.cleanup_verified and stores.pending_workers == 0
probe.acquire = held_acquire
async def run():
    try:
        await probe.worker_acquire(root, dict(contract={},timeout=5,started_at=0))
    except asyncio.CancelledError:
        print('CANCELLED_AFTER_DRAIN', flush=True)
asyncio.run(run())
'''
    env = probe.worker_environment(tmp_path)
    process = await asyncio.create_subprocess_exec(sys.executable, '-c', program, str(tmp_path), str(read_fd),
        env=env, cwd=str(tmp_path), pass_fds=(read_fd,), stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True)
    os.close(read_fd)
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b'ACTUAL_WORKER_ENTERED\n'
        process.send_signal(signal.SIGTERM)
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b'CANCELLATION_DRAIN_STARTED\n'
        assert process.returncode is None  # actual pipe operation still owns its stores
        os.write(write_fd, b'R')
        stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
        assert process.returncode == 0, stderr
        assert b'ACTUAL_WORKER_RETURNED' in stdout and b'CANCELLED_AFTER_DRAIN' in stdout
    finally:
        os.close(write_fd)
        from jarvis.subscription import _terminate_async
        await _terminate_async(process)


def test_wire_advertisement_sorts_names_without_reordering_registry_refs():
    refs = (ModelToolReference('z_tool', {'type': 'object', 'properties': {'z': {'type': 'integer'}}}),
            ModelToolReference('a_tool', {'type': 'object', 'properties': {'a': {'type': 'string'}}}))
    tools = [{'name': 'mcp__mortimer__' + ref.name, 'input_schema': dict(ref.parameters)} for ref in reversed(refs)]
    assert [ref.name for ref in refs] == ['z_tool', 'a_tool']
    assert probe.wire_tool_names(refs) == ['mcp__mortimer__a_tool', 'mcp__mortimer__z_tool']
    observed = probe.tool_menu_observation(tools, refs)
    assert observed == {'names': probe.wire_tool_names(refs), 'schemas_match': True}


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'swapped_schema', 'missing_schema', 'non_dict', 'non_list'])
def test_api_schema_authority_is_exact_name_not_position(change):
    refs = (ModelToolReference('z_tool', {'type': 'object', 'properties': {'z': {'type': 'integer'}}}),
            ModelToolReference('a_tool', {'type': 'object', 'properties': {'a': {'type': 'string'}}}))
    tools = [{'name': 'mcp__mortimer__' + ref.name, 'input_schema': dict(ref.parameters)} for ref in reversed(refs)]
    if change == 'duplicate': tools[0] = dict(tools[1])
    elif change == 'unknown': tools[0]['name'] = 'not-advertised'
    elif change == 'swapped_schema': tools[0]['input_schema'], tools[1]['input_schema'] = tools[1]['input_schema'], tools[0]['input_schema']
    elif change == 'missing_schema': tools[0].pop('input_schema')
    elif change == 'non_dict': tools[0] = None
    elif change == 'non_list': tools = {}
    assert probe.tool_menu_observation(tools, refs)['schemas_match'] is False


@pytest.mark.parametrize('count', [0, 1, 2, 3])
async def test_parent_negative_http_count_accepts_only_one_or_two(captured, count):
    value, contract, schemas = captured
    packet = value['observations']['negative_http'][0]
    value['observations']['negative_http'] = [dict(packet) for _ in range(count)]
    if count in (1, 2):
        probe.validate_capture(value, contract, expected_schemas=schemas)
    else:
        with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
            probe.validate_capture(value, contract, expected_schemas=schemas)


@pytest.mark.parametrize('change', ['registry_order', 'duplicate', 'unknown', 'schema', 'extra_bash_call', 'host_ingress', 'bool_ingress'])
async def test_parent_retains_sorted_full_menu_and_single_bash_zero_ingress(captured, change):
    value, contract, schemas = captured
    packet = value['observations']['negative_http'][0]
    if change == 'registry_order':
        packet['names'] = ['mcp__mortimer__' + name for name in value['tool_names']]
        assert packet['names'] != sorted(packet['names'])
    elif change == 'duplicate': packet['names'][0] = packet['names'][1]
    elif change == 'unknown': packet['names'][0] = 'mcp__mortimer__not-advertised'
    elif change == 'schema': packet['schemas_match'] = False
    elif change == 'extra_bash_call': value['observations']['negative']['native_calls'] *= 2
    else: value['observations']['negative']['native_host_ingress_count'] = True if change == 'bool_ingress' else 1
    with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
        probe.validate_capture(value, contract, expected_schemas=schemas)


@pytest.mark.parametrize('stream', [False, True])
async def test_actual_negative_handler_emits_one_bash_then_done_and_refuses_third(tmp_path, monkeypatch, stream):
    """Exercise the installed handler with in-memory streams, no socket/CLI."""
    import io
    refs = (ModelToolReference('z_tool', {'type': 'object', 'properties': {'z': {'type': 'integer'}}}),
            ModelToolReference('a_tool', {'type': 'object', 'properties': {'a': {'type': 'string'}}}))
    created = []
    class InertServer:
        def __init__(self, address, handler):
            assert address == ('127.0.0.1', 0)
            self.handler, self.server_port = handler, 43121
            created.append(self)
        def serve_forever(self, **kwargs): pass
        def shutdown(self): pass
        def server_close(self): pass
    monkeypatch.setattr(probe.http.server, 'HTTPServer', InertServer)
    packet = {'model': 'unit-model', 'stream': stream, 'system': probe.CONSTRAINT,
        'tools': [{'name': 'mcp__mortimer__' + ref.name, 'input_schema': dict(ref.parameters)} for ref in reversed(refs)]}
    raw = json.dumps(packet).encode()
    async with storage_scope(db_path=tmp_path / 'inert.db', costs_db_path=tmp_path / 'inert-costs.db') as stores:
        async with probe.loopback_fixture(tmp_path, 'unit-model', refs, bash=True) as fixture:
            def request():
                handler = created[0].handler.__new__(created[0].handler)
                handler.path = '/v1/messages'
                handler.headers = {'Content-Length': str(len(raw)), 'x-api-key': 'native40-synthetic-not-a-key'}
                handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
                statuses = []
                handler.send_response = statuses.append
                handler.send_error = statuses.append
                handler.send_header = lambda *args: None
                handler.end_headers = lambda: None
                handler.do_POST()
                return statuses, handler.wfile.getvalue()
            first_status, first = request()
            second_status, second = request()
            assert first_status == second_status == [200]
            if stream:
                def event(raw, kind):
                    for entry in raw.decode().split('\n\n'):
                        if entry.startswith('event: ' + kind + '\n'):
                            return json.loads(entry.split('data: ', 1)[1])
                    pytest.fail('missing event')
                assert event(first, 'content_block_start')['content_block']['name'] == 'Bash'
                assert event(first, 'message_delta')['delta']['stop_reason'] == 'tool_use'
                assert event(second, 'content_block_start')['content_block']['type'] == 'text'
                assert event(second, 'content_block_delta')['delta'] == {'type': 'text_delta', 'text': probe.DONE}
                assert event(second, 'message_delta')['delta']['stop_reason'] == 'end_turn'
            else:
                assert json.loads(first)['content'][0]['name'] == 'Bash'
                assert json.loads(first)['stop_reason'] == 'tool_use'
                assert json.loads(second)['content'] == [{'type': 'text', 'text': probe.DONE}]
                assert json.loads(second)['stop_reason'] == 'end_turn'
            assert len(fixture['observations']) == 2 and probe.verified_loopback(fixture, 'unit-model')
            assert not fixture['canary'].exists()
            third_status, third = request()
            assert third_status == [409] and third == b''
            assert len(fixture['observations']) == 3 and not probe.verified_loopback(fixture, 'unit-model')
        assert fixture['closed'] is True
    assert stores.cleanup_verified and stores.pending_workers == 0


@pytest.mark.parametrize('change', ['missing_model', 'missing_parent', 'missing_origin', 'wrong_model',
    'wrong_origin', 'malformed_parent', 'nonstring_parent', 'noncanonical_parent', 'live_parent', 'isolation_parent'])
async def test_negative_round_requires_exact_model_and_distinct_canonical_parent(captured, change):
    value, contract, schemas = captured
    negative = value['observations']['negative']
    if change.startswith('missing_'):
        negative.pop({'missing_model': 'observed_models', 'missing_parent': 'parent_request_id',
                      'missing_origin': 'origin_task_id'}[change])
    elif change == 'wrong_model': negative['observed_models'] = ['unobserved-model']
    elif change == 'wrong_origin': negative['origin_task_id'] = 'native-capability:unrelated:0'
    else:
        parent = {'malformed_parent': 'not-a-uuid', 'nonstring_parent': None,
            'noncanonical_parent': '00000000-0000-4000-8000-00000000000A',
            'live_parent': value['observations']['live']['parent_request_id'],
            'isolation_parent': value['observations']['isolation']['parent_request_id']}[change]
        negative['parent_request_id'] = parent
        negative['origin_task_id'] = f'native-capability:{parent}:0'
    with pytest.raises(probe.CapabilityUnavailable, match='worker_result_invalid'):
        probe.validate_capture(value, contract, expected_schemas=schemas)


async def test_distinct_negative_session_can_reuse_an_opaque_native_call_id(captured):
    value, contract, schemas = captured
    live = value['observations']['live']
    negative = value['observations']['negative']
    assert negative['parent_request_id'] not in (live['parent_request_id'], value['observations']['isolation']['parent_request_id'])
    negative['native_calls'][0]['tool_call_id'] = live['native_calls'][0]['tool_call_id']
    probe.validate_capture(value, contract, expected_schemas=schemas)
