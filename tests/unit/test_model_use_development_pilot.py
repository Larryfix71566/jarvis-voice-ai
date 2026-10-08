"""Real pilot boundary tests: tmp Git/inert host facets, never VM/provider."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace
import asyncio
import threading
import uuid

import pytest

from scripts import run_model_use_development_pilot as pilot
from scripts import model_use_development_oracle as oracle
from tests.unit.test_development_sources import workspace
from tests.unit.test_council_budget_ownership import transport_env


_FROZEN_PILOT_SOURCE = Path(pilot.__file__).resolve().parents[1]


def _copy_owned_pilot_source(source, destination):
    """Copy this test's frozen source bytes, never a candidate or runtime tree.

    Hydrated verification source deliberately belongs to the administrator.
    These host-simulation fixtures need new current-UID files before entering
    the unchanged host ownership guards; they do not adopt the baseline files.
    """
    from sandbox.artifacts import Candidate, File, source_path_allowed
    from sandbox.profiles import MORTIMER
    packages = {'jarvis', 'sandbox', 'mcp_servers', 'config', 'scripts'}
    fixed = set(MORTIMER.dependencies) | {
        'tests/fixtures/model_use_development_cases.json',
        'docs/REPO_MAP.md',
        'docs/acceptance/model-use-enhancements/receipts/mar-f-claude-native-fixture-capability-2026-10-05.json',
    }
    def selected(name):
        return (name.split('/')[0] in packages or name in fixed) and source_path_allowed(name)
    if (source / '.git').exists():
        # Local inventory only. No remote, safe-directory waiver or untracked
        # author's files are admitted into the fixture snapshot.
        raw = subprocess.check_output(['git', '--no-optional-locks', '-C', str(source), 'ls-files', '-z'])
        names = [name for name in raw.decode().split('\0') if name and selected(name)]
    else:
        # The immutable hydration archive has no Git metadata. Walk only the
        # same bounded source packages and named test/dependency inputs.
        names = []
        for package in sorted(packages):
            for directory, folders, files in os.walk(source / package, followlinks=False):
                folders[:] = [name for name in folders if not name.startswith('.')
                    and name not in {'__pycache__', 'node_modules', 'data', 'logs', 'runtime', 'outputs'}]
                for leaf in files:
                    name = (Path(directory) / leaf).relative_to(source).as_posix()
                    if selected(name):
                        names.append(name)
        names.extend(name for name in fixed if (source / name).is_file())
    assert names and len(names) == len(set(names))
    frozen = []
    for name in sorted(names):
        original = source / name
        before = original.lstat()
        assert stat.S_ISREG(before.st_mode) and not original.is_symlink()
        assert original.resolve().is_relative_to(source.resolve())
        raw = original.read_bytes()
        assert pilot._pins(original.lstat()) == pilot._pins(before)
        frozen.append(File(name, 0o755 if before.st_mode & 0o111 else 0o644, raw))
    # Reuse the real source path, size and credential-fixture scanner. This
    # fixture grants no new source exclusions or secret-pattern exemptions.
    Candidate(tuple(frozen))
    fingerprints = {}
    for file in frozen:
        copied = destination / file.path
        copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        copied.write_bytes(file.data)
        copied.chmod(0o500 if file.mode == 0o755 else 0o400)
        fingerprints[file.path] = digest(file.data)
        assert digest(copied.read_bytes()) == fingerprints[file.path]
        assert copied.lstat().st_uid == os.getuid() and copied.lstat().st_nlink == 1
    # A real local commit supplies the existing committed-support guard. The
    # temp index has no remotes or inherited hooks/global Git configuration.
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    prefix = ['git', '-C', str(destination), '-c', 'core.hooksPath=' + os.devnull]
    for command in (['init', '-q'], ['add', '--force', '.'],
                    ['-c', 'user.name=WS05 fixture', '-c', 'user.email=fixture@example.invalid',
                     'commit', '-q', '-m', 'Frozen owned host-simulation source']):
        subprocess.run(prefix + command, env=environment, check=True, capture_output=True)
    # MCP's real child-env allowlist intentionally does not forward arbitrary
    # Python flags. Keep source directories unwritable so child imports cannot
    # place bytecode or other mutable outputs among the frozen inputs.
    for directory in destination.rglob('*'):
        if directory.is_dir() and '.git' not in directory.relative_to(destination).parts:
            directory.chmod(0o500)
    destination.chmod(0o500)
    return SimpleNamespace(root=destination, original=source, fingerprints=fingerprints)


@pytest.fixture(scope='session')
def owned_pilot_source(tmp_path_factory):
    """One source copy for both pilot modules; mutable unit outputs stay away."""
    key = '_ws05_owned_frozen_pilot_source'
    snapshot = getattr(tmp_path_factory, key, None)
    if snapshot is None:
        destination = tmp_path_factory.mktemp('ws05-owned-frozen-source')
        destination.chmod(0o700)
        snapshot = _copy_owned_pilot_source(_FROZEN_PILOT_SOURCE, destination)
        setattr(tmp_path_factory, key, snapshot)
    try:
        yield snapshot
        for name, expected in snapshot.fingerprints.items():
            copied = snapshot.root / name
            assert copied.lstat().st_uid == os.getuid() and copied.lstat().st_nlink == 1
            assert copied.lstat().st_mode & 0o022 == 0
            assert digest(copied.read_bytes()) == expected, name
        actual = {path.relative_to(snapshot.root).as_posix() for path in snapshot.root.rglob('*')
                  if path.is_file() and '.git' not in path.relative_to(snapshot.root).parts}
        assert actual == set(snapshot.fingerprints), 'mutable outputs entered the frozen source fixture'
    finally:
        # All test-owned children are stopped before session teardown. Restore
        # directory write access solely for pytest's eventual temp cleanup.
        snapshot.root.chmod(0o700)
        for directory in snapshot.root.rglob('*'):
            if directory.is_dir() and '.git' not in directory.relative_to(snapshot.root).parts:
                directory.chmod(0o700)


@pytest.fixture(autouse=True)
def bind_owned_pilot_source(owned_pilot_source, monkeypatch):
    """Bind only test globals/child imports; restore them after every case."""
    from scripts import run_model_use_full_development_pilot as full
    from jarvis.agents import base, upgrade_agent
    from jarvis import model_routing
    from jarvis.skills import registry
    root = owned_pilot_source.root
    for module, relative in ((pilot, 'scripts/run_model_use_development_pilot.py'),
                             (full, 'scripts/run_model_use_full_development_pilot.py'),
                             (base, 'jarvis/agents/base.py'), (upgrade_agent, 'jarvis/agents/upgrade_agent.py')):
        monkeypatch.setattr(module, '__file__', str(root / relative))
    monkeypatch.setattr(pilot, 'ROOT', root)
    monkeypatch.setattr(pilot, 'CORPUS', root / 'tests/fixtures/model_use_development_cases.json')
    monkeypatch.setattr(pilot, 'ORACLE', root / 'scripts/model_use_development_oracle.py')
    monkeypatch.setattr(full, 'ROOT', root)
    monkeypatch.setattr(registry, 'REPO_ROOT', root)
    monkeypatch.setattr(model_routing, 'DEFAULT_POLICY_PATH', root / 'config/model_access.yaml')
    for name in ('DEFAULT_CONFIG_PATH', 'DEFAULT_CONFIG_DIR', 'DEFAULT_ENDPOINTS_PATH',
                 'DEFAULT_PROFILES_PATH', 'DEFAULT_REGISTRY_PATH'):
        original = getattr(upgrade_agent, name)
        monkeypatch.setattr(upgrade_agent, name, root / 'config' /
            (original.name if name != 'DEFAULT_CONFIG_DIR' else ''))
    # Fresh inspection children and actual MCP discovery import this exact
    # baseline copy. The parent's sys.path and original source are untouched.
    monkeypatch.setenv('PYTHONPATH', str(root))
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')


def digest(raw): return hashlib.sha256(raw).hexdigest()


def test_foreign_owned_baseline_metadata_refuses_but_exact_private_copy_passes(
        tmp_path, monkeypatch, owned_pilot_source):
    """Host equivalent of admin-source/worker-UID separation, without chown.

    Only the immutable original tree's lstat owner is simulated. The UID
    resolver, strict reader and copied-file metadata stay entirely real.
    """
    original = tmp_path / 'hydrated-immutable-baseline'
    original.mkdir(mode=0o700)
    for name, fingerprint in owned_pilot_source.fingerprints.items():
        source = owned_pilot_source.root / name
        target = original / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(source.read_bytes())
        target.chmod(stat.S_IMODE(source.stat().st_mode))
        assert digest(target.read_bytes()) == fingerprint
    assert not (original / '.git').exists()
    installed_lstat, installed_uid, installed_read = Path.lstat, os.getuid, pilot._read
    foreign_uid = os.getuid() + 1
    def foreign_baseline_lstat(path, *args, **kwargs):
        info = installed_lstat(path, *args, **kwargs)
        if path.is_relative_to(original) and stat.S_ISREG(info.st_mode):
            fields = list(info)
            fields[4] = foreign_uid
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(Path, 'lstat', foreign_baseline_lstat)
    corpus = original / 'tests/fixtures/model_use_development_cases.json'
    assert corpus.lstat().st_uid == foreign_uid and corpus.lstat().st_uid != os.getuid()
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='host_file_unverified'):
        pilot._read(corpus)
    copied = tmp_path / 'current-worker-owned-source'
    copied.mkdir(mode=0o700)
    snapshot = _copy_owned_pilot_source(original, copied)
    assert snapshot.fingerprints == owned_pilot_source.fingerprints
    for name, fingerprint in snapshot.fingerprints.items():
        path = copied / name
        assert path.lstat().st_uid == os.getuid() and path.lstat().st_nlink == 1
        assert digest(pilot._read(path, limit=32 * 1024 * 1024)) == fingerprint
    assert pilot._read(copied / corpus.relative_to(original)) == corpus.read_bytes()
    # The unchanged guard still rejects unsafe current-owner files too.
    unsafe = tmp_path / 'group-writable-corpus.json'
    unsafe.write_bytes(corpus.read_bytes()); unsafe.chmod(0o620)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='host_file_unverified'):
        pilot._read(unsafe)
    assert os.getuid is installed_uid and pilot._read is installed_read


def oracle_result(case, raw_spec, phase, passed):
    spec = json.loads(raw_spec)
    return {'version': 'date-diff-oracle-result-v1', 'phase': phase,
        'spec_sha256': digest(raw_spec), 'corpus_sha256': pilot.CORPUS_SHA256,
        'oracle_sha256': pilot.ORACLE_SHA256, 'case_id': case['case_id'],
        'cases': [{'id': item['id'], 'passed': passed} for item in spec['cases']], 'passed': passed}


def setup_parent(workspace):
    from sandbox.durable import atomic_json
    session = workspace.service._session()
    state = session._read()
    state['image'] = 'a' * 64
    atomic_json(session.directory / 'session.json', state)
    row = workspace.controller.read(state['task'])
    row.update(id=state['task'], vm='mortimer-' + state['task'], image=state['image'],
               purpose='development', status='stopped')
    workspace.controller.save(state['task'], row)
    identity = tuple(state.get(key) for key in pilot._SESSION_KEYS)
    allocations = pilot.OwnedAllocations(workspace.runtime, run_id=state['run_id'],
        source_ref=state['ref'], image_id=state['image'], allowed=workspace.service._allowed)
    allocations.session, allocations.identity = session, identity
    allocations.tasks[state['task']] = pilot._task_generation(workspace.controller, state['task'])
    return session, state, identity, allocations


def add_task(controller, **fields):
    task = uuid.uuid4().hex[:12]
    (controller.home / 'tasks' / task / 'input').mkdir(parents=True, mode=0o700)
    controller.save(task, {'id': task, 'vm': 'mortimer-' + task, 'status': 'stopped', **fields})
    return task


def inert_command(*args, **kwargs):
    assert args[0] == 'list', args
    return SimpleNamespace(returncode=0, stdout='[]')


@pytest.fixture
def git_source(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    real = pilot.ROOT
    from sandbox.profiles import MORTIMER
    paths = [*MORTIMER.dependencies, 'mcp_servers/mcp_time/logic.py', 'config/self_edit_allowlist.json']
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((real / path).read_bytes())
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)
    git('init'); git('config', 'user.email', 'synthetic@example.invalid'); git('config', 'user.name', 'Synthetic')
    git('remote', 'add', 'origin', 'https://github.com/' + pilot.PROJECT + '.git')
    git('add', '.'); git('commit', '-m', 'public immutable source')
    commit = git('rev-parse', 'HEAD').decode().strip()
    monkeypatch.setattr(pilot, 'ROOT', root)
    return root, commit


def image(tmp_path, dependencies):
    identity = {'profile': 'mortimer', 'dependencies': dependencies,
                'recipe': 'a' * 64, 'source': 'b' * 40, 'origin_image': 'public-base'}
    identifier = digest(json.dumps(identity, sort_keys=True).encode())
    home = tmp_path / 'home'
    directory = home / 'images' / identifier
    directory.mkdir(parents=True, mode=0o700)
    (directory / 'image.json').write_text(json.dumps({'id': identifier,
        'vm': 'mortimer-image-' + identifier[:20], **identity}))
    return home, identifier


def test_new_corpus_and_guest_oracle_are_sha_pinned(monkeypatch, tmp_path):
    assert pilot.load_corpus()['target_path'] == 'mcp_servers/mcp_time/logic.py'
    changed = tmp_path / 'case.json'
    changed.write_bytes(pilot.CORPUS.read_bytes() + b' ')
    monkeypatch.setattr(pilot, 'CORPUS', changed)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='corpus_oracle_digest_mismatch'):
        pilot.load_corpus()


def test_four_installed_operations_cannot_claim_full_developer_registry():
    from jarvis.agents.upgrade_agent import TOOL_SPECS
    tools = pilot.upgrade_tools()
    assert [tool['function']['name'] for tool in tools] == list(pilot.OPERATIONS)
    assert all(tool in TOOL_SPECS for tool in tools)
    assert 'session_submit' not in pilot.OPERATIONS
    full = pilot.full_registry_contract()
    assert full['declared_tool_count'] == 40 and len(full['servers']) == 6
    assert full['status'] == 'required_not_run' and not full['developer_accepted'] and not full['live_schema_verified']
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='actual_developer_registry_required'):
        pilot.inspect_live_developer_registry(SimpleNamespace(openai_tools=lambda _: tools))


def test_real_partial_registry_refuses_instead_of_borrowing_four_tool_receipt():
    from jarvis.skills.registry import SkillRegistry
    registry = SkillRegistry(pilot.ROOT / 'config/mcp_servers.yaml')
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='live_developer_registry_incomplete'):
        pilot.inspect_live_developer_registry(registry)


def test_full_registry_scaffold_does_not_touch_image_source_or_clients(monkeypatch):
    monkeypatch.setattr(pilot, '_source', lambda *args: pytest.fail('source accessed'))
    monkeypatch.setattr(pilot, '_image', lambda *args: pytest.fail('image accessed'))
    report = pilot.run_development_pilot(mode='live', operation_surface='developer_full_registry',
        source_ref='HEAD', image_id=None, image_home=None, profile='claude-opus', route='subscription')
    assert report['reason'] == 'full_registry_implementation_required'
    assert not report['developer_accepted'] and not report['mar_i_complete']


def test_actual_local_source_and_image_require_frozen_compatible_identity(git_source, tmp_path):
    root, commit = git_source
    case = pilot.load_corpus()
    actual, before, dependencies = pilot._source(commit, case)
    assert actual == commit and before == digest((root / case['target_path']).read_bytes())
    home, identifier = image(tmp_path, dependencies)
    assert pilot._image(home, identifier, dependencies)[1]['id'] == identifier
    adapter = pilot.FrozenLocalSource(commit)
    assert adapter.fetch(pilot.PROJECT, commit, 'unused') == (root, commit)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='frozen_source_binding_changed'):
        adapter.fetch('foreign/repository', commit, 'unused')
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='image_source_incompatible'):
        pilot._image(home, identifier, 'f' * 64)


def test_unknown_project_origin_cannot_acquire_standing_project_grant(git_source):
    root, commit = git_source
    subprocess.run(['git', '-C', str(root), 'remote', 'set-url', 'origin', 'https://github.com/foreign/private.git'], check=True)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='source_project_unverified'):
        pilot._source(commit, pilot.load_corpus())


def test_oracle_never_imports_candidate_on_host(monkeypatch, tmp_path):
    monkeypatch.delenv('MORTIMER_SANDBOX_GUEST', raising=False)
    monkeypatch.setattr(oracle.importlib, 'import_module', lambda _: pytest.fail('host candidate import'))
    with pytest.raises(SystemExit) as caught:
        oracle.main(['--phase', 'candidate', '--spec', str(tmp_path / 'none'), '--spec-sha256', '0' * 64])
    assert caught.value.code == 2


def test_known_test_oracle_strictly_scores_behavior_and_redacts_errors():
    case = pilot.load_corpus()
    calls = []
    original = os.environ.get('JARVIS_TIMEZONE')
    def broken(a, b):
        calls.append((a, b))
        raise RuntimeError('PRIVATE_ORACLE_CANARY_942c')
    result = oracle.evaluate(broken, case['oracle'])
    assert len(calls) == 9 and not result['passed']
    assert 'PRIVATE_ORACLE_CANARY_942c' not in json.dumps(result)
    assert os.environ.get('JARVIS_TIMEZONE') == original
    bad = {'version': 'date-diff-oracle-v1', 'cases': [{**case['oracle']['cases'][0],
        'expected': {'days': True, 'hours': 36.0}}]}
    with pytest.raises(ValueError, match='oracle_spec_invalid'): oracle.validate_spec(bad)


def test_frozen_corpus_reproduces_real_intended_mixed_awareness_failure():
    from mcp_servers.mcp_time.logic import date_diff
    result = oracle.evaluate(date_diff, pilot.load_corpus()['oracle'])
    matched = {item['id']: item['passed'] for item in result['cases']}
    assert matched['aware-positive'] and matched['aware-negative'] and matched['explicit-offsets']
    assert not matched['naive-left'] and not matched['naive-right'] and not result['passed']


def outside_spec(tmp_path):
    spec = {'version': 'date-diff-oracle-v1', 'cases': [
        {'id': 'external-sealed-case', 'timezone': 'UTC', 'a': '2031-02-03T00:00:00',
         'b': '2031-02-03T12:00:00+00:00', 'expected': {'days': 0, 'hours': 12.0}}]}
    path = tmp_path / 'outside.json'
    raw = pilot._canonical(spec)
    path.write_bytes(raw)
    return path, digest(raw)


def test_outside_holdout_is_frozen_before_model_and_replacement_refuses(git_source, tmp_path):
    path, sha = outside_spec(tmp_path)
    snapshot = pilot._holdout_snapshot(path, sha, pilot.load_corpus())
    assert 'external-sealed-case' not in repr(snapshot)
    pilot._recheck_holdout(snapshot)
    path.rename(path.with_suffix('.old'))
    path.write_bytes(snapshot.raw)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='holdout_source_changed'):
        pilot._recheck_holdout(snapshot)


def test_inside_source_or_renamed_known_case_is_never_independent_holdout(git_source, tmp_path):
    root, _ = git_source
    case = pilot.load_corpus()
    same = {**case['oracle']['cases'][0], 'id': 'renamed-copy'}
    raw = pilot._canonical({'version': 'date-diff-oracle-v1', 'cases': [same]})
    outside = tmp_path / 'copied.json'; outside.write_bytes(raw)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='holdout_copies_known_cases'):
        pilot._holdout_snapshot(outside, digest(raw), case)
    inside = root / 'holdout.json'; inside.write_bytes(raw)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='holdout_inside_developer_source'):
        pilot._holdout_snapshot(inside, digest(raw), case)


def test_mortimer_profile_keeps_all_twelve_checks_and_original_fingerprint():
    from sandbox.profiles import MORTIMER
    assert len(MORTIMER.checks) == 12 and MORTIMER.requires_graphics
    names = [name for name, _ in MORTIMER.checks]
    assert {'backend', 'baseline-backend', 'native-app', 'baseline-native-app', 'knowledge-base', 'web'} <= set(names)


def test_native_public_fixture_receipt_cannot_approve_actual_upgrade_operations(monkeypatch):
    from jarvis import subscription_tools
    from jarvis.model_execution import ModelToolReference
    receipt = pilot.ROOT / 'docs/acceptance/model-use-enhancements/receipts/mar-f-claude-native-fixture-capability-2026-10-05.json'
    value = json.loads(receipt.read_bytes())
    monkeypatch.setenv(subscription_tools.TOOLS_ENABLED_ENV, '1')
    monkeypatch.setenv(subscription_tools.TOOL_CAPABILITY_RECEIPT_ENV, str(receipt))
    monkeypatch.setattr(subscription_tools, 'claude_tool_runtime_identity', lambda: value['executable'])
    tools = tuple(ModelToolReference(tool['function']['name'], tool['function']['parameters'],
        tool['function']['description']) for tool in pilot.upgrade_tools())
    with pytest.raises(subscription_tools.SubscriptionCapabilityError, match='does not match this request'):
        subscription_tools._validate_native_receipt(value['model'], list(pilot.OPERATIONS), tools)


def test_fresh_worker_environment_cannot_lower_private_policy_or_configured_limits(git_source, tmp_path):
    from jarvis.model_routing import WorkloadLimits, resolve_policy
    root, _ = git_source
    import yaml
    policy = yaml.safe_load((Path(pilot.__file__).resolve().parents[1] / 'config/model_access.yaml').read_bytes())
    policy['workloads']['developer'].update(privacy='local_only', max_output_tokens_per_call=7,
        deadline_seconds=15, max_estimated_spend_usd_per_task=.5)
    (root / 'config/model_access.yaml').write_text(json.dumps(policy))
    directory = tmp_path / 'owned-state'; directory.mkdir(mode=0o700)
    original = dict(os.environ)
    from jarvis import usage_ledger
    previous = usage_ledger.DB_PATH
    environment = pilot._worker_environment(directory, 'claude-opus', 'direct_api', None, WorkloadLimits(100, 60, 10))
    actual = resolve_policy('developer', include_preferences=False, path=environment['JARVIS_MODEL_ACCESS_CONFIG'])
    assert actual.privacy == 'local_only'
    assert actual.limits == WorkloadLimits(7, 15, .5)
    assert dict(os.environ) == original and usage_ledger.DB_PATH == previous
    assert environment.get('JARVIS_DB_PATH') == original.get('JARVIS_DB_PATH')
    assert environment.get('JARVIS_COSTS_DB') == original.get('JARVIS_COSTS_DB')


def test_fresh_worker_uses_actual_selected_private_config_without_borrowing_environment(git_source, tmp_path, monkeypatch):
    import yaml
    from jarvis.model_routing import WorkloadLimits, resolve_policy, POLICY_PATH_ENV
    policy = yaml.safe_load((Path(pilot.__file__).resolve().parents[1] / 'config/model_access.yaml').read_bytes())
    policy['workloads']['developer'].update(privacy='local_only', deadline_seconds=8)
    selected = tmp_path / 'selected-policy.json'; selected.write_bytes(pilot._canonical(policy))
    monkeypatch.setenv(POLICY_PATH_ENV, str(selected))
    directory = tmp_path / 'owned'; directory.mkdir(mode=0o700)
    original = dict(os.environ)
    environment = pilot._worker_environment(directory, 'claude-opus', 'direct_api', None,
                                            WorkloadLimits(deadline_seconds=60))
    actual = resolve_policy('developer', path=environment[POLICY_PATH_ENV], include_preferences=False)
    assert actual.privacy == 'local_only' and actual.limits.deadline_seconds == 8
    assert dict(os.environ) == original


def test_public_live_entry_uses_fresh_exec_and_refuses_unbound_terminal_receipt(git_source, tmp_path, monkeypatch):
    from jarvis.model_routing import WorkloadLimits, POLICY_PATH_ENV
    monkeypatch.setenv(POLICY_PATH_ENV, str(Path(pilot.__file__).resolve().parents[1] / 'config/model_access.yaml'))
    monkeypatch.setattr(pilot, 'ROOT', Path(pilot.__file__).resolve().parents[1])
    monkeypatch.setattr(pilot, '_source', lambda *args: ('c' * 40, 'd' * 64, 'e' * 64))
    monkeypatch.setattr(pilot, '_image', lambda *args: (tmp_path, {'source': 'b' * 40}, 'f' * 64))
    observed = []
    original = dict(os.environ)
    def child(command, *, env, **kwargs):
        observed.append((command, env))
        assert command[1] == str(Path(pilot.__file__).resolve())
        assert command[2] == '--owned-worker' and kwargs['stderr'] == subprocess.DEVNULL
        request = json.loads(Path(command[3]).read_bytes())
        assert request['source_ref'] == 'c' * 40 and request['image_id'] == 'a' * 64
        assert request['run_id'] and env['JARVIS_MODEL_ROUTING_ENABLED'] == '1'
        assert dict(os.environ) == original
        return SimpleNamespace(returncode=0, stdout=b'{"status":"substrate_passed"}')
    monkeypatch.setattr(pilot.subprocess, 'run', child)
    report = pilot.run_development_pilot(mode='live', source_ref='HEAD', image_id='a' * 64,
        image_home=tmp_path, profile='claude-opus', route='direct_api', limits=WorkloadLimits(deadline_seconds=60))
    assert len(observed) == 1 and dict(os.environ) == original
    assert report['status'] == 'cleanup_unverified' and report['reason'] == 'pilot_worker_receipt_invalid'
    assert not report['substrate_passed'] and not report['cleanup']['verified']


@pytest.mark.parametrize('limits_case', ['default', 'explicit_stricter', 'configured_stronger'])
def test_actual_fresh_child_merged_policy_receipt_matches_parent_without_inference(
        tmp_path, monkeypatch, limits_case):
    """A real fresh process inspects policy; no SDK, VM, or acceptance pass."""
    import yaml
    from jarvis.model_routing import WorkloadLimits
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'default': 'frontier-one', 'profiles': [{
        'name': 'frontier-one', 'model': 'frontier-one', 'identity': 'openai/frontier-one',
        'provider': 'openai', 'api_key_env': 'OPENAI_API_KEY', 'base_url': 'https://fixture.invalid/v1',
        'tier': 'frontier', 'temperature': None}]}))
    policy = yaml.safe_load((pilot.ROOT / 'config/model_access.yaml').read_bytes())
    fields = ('max_output_tokens_per_call', 'deadline_seconds', 'max_estimated_spend_usd_per_task')
    policy['workloads']['developer'].update(dict.fromkeys(fields))
    expected, requested = (None, 1800, None), None
    if limits_case == 'explicit_stricter':
        requested = WorkloadLimits(9, 60, .75); expected = (9, 60, .75)
    if limits_case == 'configured_stronger':
        policy['workloads']['developer'].update(dict(zip(fields, (7, 15, .5))))
        requested = WorkloadLimits(100, 60, 10); expected = (7, 15, .5)
    path = tmp_path / 'policy.json'; path.write_bytes(pilot._canonical(policy))
    for name, value in {'JARVIS_UPGRADE_MODELS': str(registry), 'JARVIS_MODEL_ACCESS_CONFIG': str(path),
        'JARVIS_MODEL_PREFERENCES_ENABLED': '0', 'JARVIS_MODEL_ROUTING_ENABLED': '1'}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(pilot, '_source', lambda *args: ('c' * 40, 'd' * 64, 'e' * 64))
    monkeypatch.setattr(pilot, '_image', lambda *args: (tmp_path, {'source': 'b' * 40}, 'f' * 64))
    installed_run = subprocess.run
    child_limits = []
    code = '''
import json,sys
from pathlib import Path
from dataclasses import asdict
from scripts import run_model_use_development_pilot as pilot
from jarvis.model_routing import resolve_policy
request=json.loads(Path(sys.argv[1]).read_bytes())
pilot._source=lambda *args: ('c'*40,'d'*64,'e'*64)
pilot._image=lambda *args: (Path(request['image_home']),{'source':'b'*40},'f'*64)
report=pilot.inspect_development_pilot(source_ref=request['source_ref'],image_id=request['image_id'],
    image_home=request['image_home'],profile=request['profile'],route=request['route'])
report.update(mode='live',status='unavailable',reason='inert_inspection_only',substrate_passed=False,
    parent_request_id=request['run_id'],cleanup={'verified':True,'owned_tasks':[]},
    inspected_limits=asdict(resolve_policy('developer',include_preferences=False).limits))
print(json.dumps(report,sort_keys=True,separators=(',',':')))
raise SystemExit(2)
'''
    def execute_fresh_inspection(command, **kwargs):
        assert command[2] == '--owned-worker'
        result = installed_run([command[0], '-c', code, command[3]], cwd=pilot.ROOT, **kwargs)
        child_limits.append(json.loads(result.stdout)['inspected_limits'])
        return result
    monkeypatch.setattr(pilot.subprocess, 'run', execute_fresh_inspection)
    environment = dict(os.environ)
    report = pilot.run_development_pilot(mode='live', source_ref='HEAD', image_id='a' * 64,
        image_home=tmp_path, profile='frontier-one', route='direct_api', limits=requested)
    assert child_limits == [dict(zip(fields, expected))]
    assert report['reason'] == 'inert_inspection_only', report
    assert 'actual_selection_verified' not in report
    assert not report['substrate_passed'] and not report['developer_accepted'] and not report['mar_i_complete']
    assert dict(os.environ) == environment


def test_worker_cannot_widen_captured_parent_limits_or_privacy_after_config_changes(tmp_path, monkeypatch):
    import yaml
    from jarvis.model_routing import WorkloadLimits, resolve_policy
    policy = yaml.safe_load((pilot.ROOT / 'config/model_access.yaml').read_bytes())
    policy['workloads']['developer'].update(privacy='local_only', deadline_seconds=15,
        max_output_tokens_per_call=7, max_estimated_spend_usd_per_task=.5)
    path = tmp_path / 'policy.json'; path.write_bytes(pilot._canonical(policy))
    monkeypatch.setenv('JARVIS_MODEL_ACCESS_CONFIG', str(path))
    parent = resolve_policy('developer', include_preferences=False)
    policy['workloads']['developer'].update(privacy='approved_external', deadline_seconds=None,
        max_output_tokens_per_call=None, max_estimated_spend_usd_per_task=None)
    path.write_bytes(pilot._canonical(policy))
    directory = tmp_path / 'worker'; directory.mkdir(mode=0o700)
    environment = dict(os.environ)
    child = pilot._worker_environment(directory, parent.profile, parent.route, None,
        WorkloadLimits(100, 60, 10), parent_policy=parent)
    actual = resolve_policy('developer', include_preferences=False, path=child['JARVIS_MODEL_ACCESS_CONFIG'])
    assert actual.privacy == 'local_only' and actual.limits == WorkloadLimits(7, 15, .5)
    assert dict(os.environ) == environment


def test_private_pilot_directory_cannot_adopt_symlinked_storage(tmp_path):
    foreign = tmp_path / 'foreign'; foreign.mkdir(mode=0o700)
    home = tmp_path / 'sandbox'; home.mkdir(mode=0o700)
    (home / 'pilots').symlink_to(foreign, target_is_directory=True)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='pilot_storage_owner_invalid'):
        pilot._owned_directory(home, 'a' * 32)
    assert list(foreign.iterdir()) == []


def test_cleanup_rejects_changed_actual_host_actor_before_cancel(workspace, monkeypatch):
    session = workspace.service._session()
    row = session._read()
    identity = tuple(row.get(key) for key in ('id', 'task', 'run_id', 'ref', 'image', 'repository', 'kind'))
    changed = dict(row); changed['run_id'] = 'foreign-parent'
    monkeypatch.setattr(session, '_read', lambda: changed)
    monkeypatch.setattr(session, 'cancel', lambda: pytest.fail('foreign actor cancelled'))
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='cleanup_session_owner_changed'):
        pilot._cleanup(workspace.runtime, session, identity)


def test_cleanup_rechecks_actual_cancel_and_revert_owner_under_mutation_lock(workspace, monkeypatch):
    from sandbox.durable import atomic_json
    session, state, identity, allocations = setup_parent(workspace)
    foreign = add_task(workspace.controller, image=state['image'], purpose='development',
                       source_commit='f' * 40, parent_task=None)
    replacement = {**state, 'task': foreign, 'run_id': str(uuid.uuid4()), 'ref': 'f' * 40}
    cancel = session.cancel
    def replaced_cancel():
        atomic_json(session.directory / 'session.json', replacement)
        return cancel()
    monkeypatch.setattr(session, 'cancel', replaced_cancel)
    monkeypatch.setattr(workspace.controller, 'command', inert_command)
    result = pilot._cleanup(workspace.runtime, session, identity, allocations=allocations)
    assert workspace.cancelled == [] and not result['verified']
    assert workspace.controller.read(foreign)['status'] == 'stopped'
    assert workspace.controller.read(state['task'])['status'] == 'stopped'


def test_cleanup_ignores_unretained_wrong_source_same_parent_child(workspace, monkeypatch):
    session, state, identity, allocations = setup_parent(workspace)
    foreign = add_task(workspace.controller, image=state['image'], purpose='verification',
                       source_commit='f' * 40, parent_task=state['task'])
    monkeypatch.setattr(workspace.controller, 'command', inert_command)
    result = pilot._cleanup(workspace.runtime, session, identity, allocations=allocations)
    assert result['verified'] and result['owned_tasks'] == [state['task']]
    assert workspace.cancelled == [state['task']]
    assert workspace.controller.read(foreign)['status'] == 'stopped'
    assert workspace.controller.read(state['task'])['status'] == 'deleted'


def test_actual_destroy_reads_retained_task_generation_inside_its_lock(workspace, monkeypatch):
    session, state, identity, allocations = setup_parent(workspace)
    monkeypatch.setattr(workspace.controller, 'command', inert_command)
    destroy = workspace.controller.destroy
    def changed_before_destroy(task):
        row = workspace.controller.read(task)
        row['source_commit'] = 'f' * 40
        workspace.controller.save(task, row)
        return destroy(task)
    monkeypatch.setattr(workspace.controller, 'destroy', changed_before_destroy)
    result = pilot._cleanup(workspace.runtime, session, identity, allocations=allocations)
    assert not result['verified']
    assert workspace.controller.read(state['task'])['status'] == 'stopped'


@pytest.mark.parametrize('defect', ['empty', 'no_cases', 'wrong_phase', 'wrong_spec', 'wrong_corpus',
                                  'wrong_oracle', 'duplicate_id', 'integer_bool', 'inconsistent_rc'])
def test_oracle_quality_requires_exact_complete_json_and_exit_consistency(tmp_path, defect):
    case = pilot.load_corpus()
    spec = pilot._canonical(case['oracle'])
    value = oracle_result(case, spec, 'candidate', True)
    if defect == 'no_cases': value['cases'] = []
    if defect == 'wrong_phase': value['phase'] = 'baseline'
    if defect == 'wrong_spec': value['spec_sha256'] = 'f' * 64
    if defect == 'wrong_corpus': value['corpus_sha256'] = 'f' * 64
    if defect == 'wrong_oracle': value['oracle_sha256'] = 'f' * 64
    if defect == 'duplicate_id': value['cases'][-1]['id'] = value['cases'][0]['id']
    if defect == 'integer_bool': value['cases'][0]['passed'] = 1
    raw = b'\n' if defect == 'empty' else pilot._canonical(value) + b'\n'
    path = tmp_path / 'oracle.log'; path.write_bytes(raw)
    check = {'returncode': 1 if defect == 'inconsistent_rc' else 0,
             'passed': defect != 'inconsistent_rc', 'log_sha256': digest(raw)}
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='oracle_result_invalid'):
        pilot._oracle_result(check, path, spec, 'candidate', case)


@pytest.mark.parametrize('phase,passed', [('baseline', False), ('candidate', True)])
def test_oracle_valid_complete_output_retains_expected_baseline_candidate_semantics(tmp_path, phase, passed):
    case = pilot.load_corpus(); spec = pilot._canonical(case['oracle'])
    raw = pilot._canonical(oracle_result(case, spec, phase, passed)) + b'\n'
    path = tmp_path / 'oracle.log'; path.write_bytes(raw)
    check = {'returncode': 0 if passed else 1, 'passed': passed, 'log_sha256': digest(raw)}
    result = pilot._oracle_result(check, path, spec, phase, case)
    assert result['passed'] is passed and result['case_count'] == 9


def test_oracle_delivers_verified_raw_snapshot_after_path_replacement(workspace, tmp_path, monkeypatch):
    session, state, _, allocations = setup_parent(workspace)
    case = pilot.load_corpus()
    child = add_task(workspace.controller, image=state['image'], purpose='verification',
                     source_commit=state['ref'], parent_task=state['task'])
    changed = tmp_path / 'replaced.py'; changed.write_bytes(b'raise SystemExit(0)\n')
    monkeypatch.setattr(pilot, 'ORACLE', changed)
    class StopBeforeBoot(Exception): pass
    monkeypatch.setattr(workspace.controller, 'start', lambda *args, **kwargs: (_ for _ in ()).throw(StopBeforeBoot()))
    stopped = []
    monkeypatch.setattr(workspace.controller, 'stop', lambda task: stopped.append(task))
    with pytest.raises(StopBeforeBoot):
        pilot._oracle_checks(workspace.runtime, session, {'verification_task': child}, case)
    actual = (workspace.controller.task_dir(child) / 'input/pilot-oracle.py').read_bytes()
    assert actual == case._oracle_raw and digest(actual) == pilot.ORACLE_SHA256
    assert actual != changed.read_bytes() and stopped == [child]


def test_digest_refusal_precedes_any_host_oracle_import(tmp_path, monkeypatch):
    import builtins
    actual_import = builtins.__import__
    imports = []
    def check_import(name, *args, **kwargs):
        if 'model_use_development_oracle' in name:
            imports.append(name)
        return actual_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', check_import)
    path = tmp_path / 'unverified.py'; path.write_bytes(b'raise RuntimeError("should never execute")\n')
    monkeypatch.setattr(pilot, 'ORACLE', path)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='corpus_oracle_digest_mismatch'):
        pilot.load_corpus()
    assert imports == []


def test_boot_wait_requires_actual_tart_running_and_guest_readiness(tmp_path, monkeypatch):
    from sandbox.control import Controller
    controller = Controller(tmp_path / 'sandbox', '/missing/tart', '/missing/softnet')
    task = add_task(controller, purpose='development', network='offline', prepared=True)
    row = controller.read(task); row['status'] = 'running'; controller.save(task, row)
    clock = iter([0, 0, 0, .1, .1, .1, .1, .1])
    monkeypatch.setattr(pilot.time, 'monotonic', lambda: next(clock))
    observed = []
    class NoDelay:
        def wait(self, seconds):
            assert seconds > 0
    monkeypatch.setattr(pilot.threading, 'Event', NoDelay)
    def command(*args, **kwargs):
        observed.append(args)
        if args[0] == 'list':
            state = 'stopped' if sum(item[0] == 'list' for item in observed) == 1 else 'running'
            return SimpleNamespace(returncode=0, stdout=json.dumps([{'Name': row['vm'], 'State': state}]))
        assert args == ('exec', row['vm'], '/usr/bin/true')
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(controller, 'command', command)
    pilot._wait_boot(controller, task, lambda: None)
    assert [item[0] for item in observed] == ['list', 'list', 'exec']


def test_boot_timeout_stops_exact_task_without_marking_ready(tmp_path, monkeypatch):
    from sandbox.control import Controller
    controller = Controller(tmp_path / 'sandbox', '/missing/tart', '/missing/softnet')
    task = add_task(controller, purpose='development', prepared=True)
    clock = iter([0, 0, .01, 1, 1])
    monkeypatch.setattr(pilot.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(controller, 'command', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='[]'))
    stopped = []
    monkeypatch.setattr(controller, 'stop', lambda actual: stopped.append(actual))
    class NoDelay:
        def wait(self, seconds): pass
    monkeypatch.setattr(pilot.threading, 'Event', NoDelay)
    with pytest.raises(pilot.DevelopmentPilotUnavailable, match='pilot_boot_readiness_timeout'):
        pilot._wait_boot(controller, task, lambda: None, timeout=.1)
    assert stopped == [task] and not controller.ready(task)


async def test_upgrade_storage_context_is_local_and_worker_cancel_is_causally_drained(tmp_path):
    from jarvis import db, usage_ledger
    from jarvis.storage_context import costs_path
    from jarvis.privacy_policy import DataPolicy
    entered, release, cancelled, finished = (threading.Event() for _ in range(4))
    observed = []
    class RealSynchronousBoundary:
        def run(self, goal, *, data_policy):
            observed.append((db._default_db_path(), usage_ledger.DB_PATH,
                             costs_path(usage_ledger.DB_PATH), dict(os.environ)))
            entered.set()
            assert release.wait(2)
            finished.set()
            return {'cancelled': cancelled.is_set()}
        def request_cancel(self):
            cancelled.set(); release.set()
    environment, ledger = dict(os.environ), usage_ledger.DB_PATH
    status = {}
    task = asyncio.create_task(pilot.run_owned_upgrade(RealSynchronousBoundary(), 'public goal',
        DataPolicy('approved_external', 'test'), tmp_path, status=status))
    assert await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and finished.is_set() and status == {'verified': True, 'pending_workers': 0}
    assert observed == [(tmp_path / 'pilot.db', ledger, tmp_path / 'costs.db', environment)]
    assert dict(os.environ) == environment and usage_ledger.DB_PATH == ledger


def test_existing_receipt_path_is_refused_before_any_live_action(tmp_path, monkeypatch):
    output = tmp_path / 'existing.json'; output.write_text('protected')
    monkeypatch.setattr(pilot, 'run_development_pilot', lambda **kwargs: pytest.fail('live action before output validation'))
    with pytest.raises(SystemExit) as caught:
        pilot.main(['--mode', 'live', '--source-ref', 'HEAD', '--image-id', 'a' * 64,
            '--image-home', str(tmp_path), '--profile', 'claude-opus', '--route', 'subscription', '--output', str(output)])
    assert caught.value.code == 2 and output.read_text() == 'protected'


def _mac_only_receipt_race_witness(tmp_path, monkeypatch):
    # Match the independent oldbug witness: create output during the run.
    directory = Path('/private/tmp') / ('ws05-receipt-repair-' + uuid.uuid4().hex)
    directory.mkdir(mode=0o700)
    output = directory / 'receipt.json'
    try:
        def completed_run(**kwargs):
            output.write_text('existing protected receipt')
            return {'status': 'dry_ready_unverified', 'developer_accepted': False, 'mar_i_complete': False}
        monkeypatch.setattr(pilot, 'run_development_pilot', completed_run)
        with pytest.raises(SystemExit) as caught:
            pilot.main(['--mode', 'dry', '--source-ref', 'HEAD', '--image-id', 'a' * 64,
                '--image-home', str(directory), '--profile', 'claude-opus', '--route', 'direct_api',
                '--output', str(output)])
        assert caught.value.code == 2 and output.read_text() == 'existing protected receipt'
        assert list(directory.iterdir()) == [output]
    finally:
        output.unlink(missing_ok=True); directory.rmdir()


def test_receipt_created_after_preflight_is_preserved_atomically(tmp_path, monkeypatch):
    # Exercise the same competing-artifact race in the real permitted repo
    # receipt anchor. The test-owned root exists on macOS and Linux alike.
    monkeypatch.setattr(pilot, 'ROOT', tmp_path)
    directory = tmp_path / 'docs/acceptance/model-use-enhancements/receipts' / (
        'ws05-receipt-repair-' + uuid.uuid4().hex)
    directory.mkdir(parents=True, mode=0o700)
    output = directory / 'receipt.json'
    competed, attempted_links = [], []
    installed_link = pilot.os.link
    try:
        def completed_run(**kwargs):
            output.write_text('existing protected receipt')
            output.chmod(0o600)
            info = output.lstat()
            competed.append((info.st_dev, info.st_ino, info.st_mode))
            return {'status': 'dry_ready_unverified', 'developer_accepted': False, 'mar_i_complete': False}
        def attempted_link(source, destination, **kwargs):
            attempted_links.append((source, destination))
            return installed_link(source, destination, **kwargs)
        monkeypatch.setattr(pilot, 'run_development_pilot', completed_run)
        monkeypatch.setattr(pilot.os, 'link', attempted_link)
        with pytest.raises(SystemExit) as caught:
            pilot.main(['--mode', 'dry', '--source-ref', 'HEAD', '--image-id', 'a' * 64,
                '--image-home', str(directory), '--profile', 'claude-opus', '--route', 'direct_api',
                '--output', str(output)])
        assert caught.value.code == 2 and output.read_text() == 'existing protected receipt'
        assert len(attempted_links) == 1 and attempted_links[0][1] == output.name
        info = output.lstat()
        assert competed == [(info.st_dev, info.st_ino, info.st_mode)]
        assert info.st_mode & 0o777 == 0o600 and directory.stat().st_mode & 0o777 == 0o700
        assert list(directory.iterdir()) == [output]
    finally:
        output.unlink(missing_ok=True); directory.rmdir()


def test_receipt_race_fixture_without_macos_temp_root_preserves_old_witness_and_inverse(tmp_path, monkeypatch):
    """Offline Linux-equivalent filesystem prerequisite; no provider or VM.

    Keep the previous body unchanged above. Simulate the same missing macOS
    directory from the actual Ubuntu CI log, then run the repaired artifact
    race under that restriction. The publication guard itself stays real.
    """
    installed_mkdir = Path.mkdir
    missing_root_attempts = []
    def mkdir_without_macos_root(path, *args, **kwargs):
        if path.parent == Path('/private/tmp'):
            missing_root_attempts.append(path)
            raise FileNotFoundError(2, 'No such file or directory', str(path))
        return installed_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', mkdir_without_macos_root)
    with pytest.raises(FileNotFoundError) as caught:
        _mac_only_receipt_race_witness(tmp_path, monkeypatch)
    assert Path(caught.value.filename) == missing_root_attempts[0]
    assert len(missing_root_attempts) == 1
    test_receipt_created_after_preflight_is_preserved_atomically(tmp_path, monkeypatch)
    assert len(missing_root_attempts) == 1


def test_successful_receipt_publication_is_exclusive_owner_mode_and_no_temporary_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'ROOT', tmp_path)
    output = tmp_path / 'docs/acceptance/model-use-enhancements/receipts/receipt.json'
    with pilot._receipt_publication(output) as publish:
        publish({'status': 'dry_ready_unverified', 'developer_accepted': False})
    info = output.lstat()
    assert info.st_mode & 0o777 == 0o600 and info.st_nlink == 1
    assert json.loads(output.read_bytes())['status'] == 'dry_ready_unverified'
    assert list(output.parent.iterdir()) == [output]


def test_receipt_parent_replacement_does_not_follow_foreign_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'ROOT', tmp_path)
    parent = tmp_path / 'docs/acceptance/model-use-enhancements/receipts/owned'
    parent.mkdir(parents=True, mode=0o700)
    foreign = tmp_path / 'foreign'; foreign.mkdir(mode=0o700)
    output = parent / 'receipt.json'
    with pilot._receipt_publication(output) as publish:
        old = parent.with_name('old-owned')
        parent.rename(old)
        parent.symlink_to(foreign, target_is_directory=True)
        with pytest.raises(pilot.DevelopmentPilotUnavailable, match='new_owned_receipt_path_required'):
            publish({'status': 'dry_ready_unverified'})
    assert list(foreign.iterdir()) == [] and list(old.iterdir()) == []


def test_receipt_parent_swap_inside_atomic_link_is_not_acknowledged(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'ROOT', tmp_path)
    parent = tmp_path / 'docs/acceptance/model-use-enhancements/receipts/owned'
    parent.mkdir(parents=True, mode=0o700)
    foreign = tmp_path / 'foreign'; foreign.mkdir(mode=0o700)
    old = parent.with_name('old-owned')
    output = parent / 'receipt.json'
    installed_link = pilot.os.link
    called = []
    def replace_then_link(source, destination, **kwargs):
        parent.rename(old)
        parent.symlink_to(foreign, target_is_directory=True)
        called.append(True)
        return installed_link(source, destination, **kwargs)
    monkeypatch.setattr(pilot.os, 'link', replace_then_link)
    with pilot._receipt_publication(output) as publish:
        with pytest.raises(pilot.DevelopmentPilotUnavailable, match='new_owned_receipt_path_required'):
            publish({'status': 'dry_ready_unverified', 'developer_accepted': False})
    assert called == [True] and not output.exists()
    assert json.loads((old / 'receipt.json').read_bytes())['status'] == 'dry_ready_unverified'
    assert list(foreign.iterdir()) == [] and list(old.iterdir()) == [old / 'receipt.json']


@pytest.mark.parametrize('scenario', ['public_pass', 'private_read', 'backend_failure', 'empty_oracle',
                                    'cleanup_false', 'registry_model_drift', 'preparation_unavailable'])
def test_actual_runtime_session_upgrade_sdk_and_all_profile_gates_are_wired(
        transport_env, git_source, tmp_path, monkeypatch, scenario):
    """Protocol wiring only: real classes/SDK, inert guest and MockTransport.

    The simulated guest results do not establish real VM or model quality.
    Even a passing substrate report must keep full Developer acceptance false.
    """
    import httpx
    import openai
    import jarvis.agents.upgrade_agent as upgrade
    from sandbox.artifacts import Candidate, File
    from sandbox.control import Controller
    from sandbox.profiles import MORTIMER
    from jarvis.model_routing import WorkloadLimits
    root, commit = git_source
    transport_env.limits['developer'] = WorkloadLimits(deadline_seconds=60)
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(root))
    case = pilot.load_corpus()
    private_read = scenario == 'private_read'
    if private_read:
        (root / 'docs').mkdir()
        (root / 'docs/private-report.txt').write_text('PRIVATE_PILOT_ACQUIRED_CANARY_51af')
        subprocess.run(['git', '-C', str(root), 'add', 'docs/private-report.txt'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-m', 'unclassified source fixture'], check=True, capture_output=True)
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip()
    real = Path(upgrade.__file__).resolve().parents[2]
    for relative in ('config/agents.yaml', 'config/mcp_servers.yaml', 'config/model_access.yaml', 'config/upgrade_agent.yaml'):
        destination = root / relative
        destination.write_bytes((real / relative).read_bytes())
    for name in pilot.DEVELOPER_SERVERS:
        for leaf in ('skill.yaml', 'server.py'):
            relative = Path('mcp_servers') / name.replace('-', '_') / leaf
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((real / relative).read_bytes())
    dependencies = pilot._source(commit, case)[2]
    home, identifier = image(tmp_path, dependencies)
    (home / 'settings.json').write_text(json.dumps({'version': 1, 'tart': '/missing/tart',
        'softnet': '/missing/softnet', 'images': {'mortimer': identifier}}))
    guest_files, virtual_vms, guest_checks = {}, {'mortimer-image-' + identifier[:20]: 'stopped'}, []
    original_target = (root / case['target_path']).read_text()
    replacement = original_target.replace('from datetime import datetime, timedelta',
        'from datetime import datetime, timedelta, timezone').replace(
            '    total_seconds = (b - a).total_seconds()',
            '    if a.tzinfo is None:\n        a = a.replace(tzinfo=_tz())\n'
            '    if b.tzinfo is None:\n        b = b.replace(tzinfo=_tz())\n'
            '    total_seconds = (b.astimezone(timezone.utc) - a.astimezone(timezone.utc)).total_seconds()')

    def command(self, *args, **kwargs):
        if args[0] == 'list':
            return SimpleNamespace(returncode=0, stdout=json.dumps([{'Name': key, 'State': value}
                for key, value in virtual_vms.items()]))
        if args[0] == 'clone': virtual_vms[args[2]] = 'stopped'
        if args[0] == 'stop': virtual_vms[args[1]] = 'stopped'
        if args[0] == 'delete': virtual_vms.pop(args[1], None)
        assert args[0] in {'clone', 'set', 'stop', 'delete', 'exec'}
        return SimpleNamespace(returncode=0, stdout='')

    def start(self, task, *, provisioning=False, headless=True):
        assert not provisioning
        row = self.read(task); row.update(status='running', network='offline')
        self.save(task, row); virtual_vms[row['vm']] = 'running'

    def rpc(self, task, request):
        if task not in guest_files:
            candidate = Candidate.decode((self.task_dir(task) / 'input/candidate.json').read_bytes())
            guest_files[task] = {file.path: file for file in candidate.files}
        files = guest_files[task]
        operation = request['operation']
        if operation == 'capture': return Candidate(tuple(files.values())).encode()
        if operation == 'read': return Candidate((files[request['path']],)).encode()
        if operation == 'write':
            changed = Candidate.decode(json.dumps(request['candidate']).encode())
            files.update({file.path: file for file in changed.files})
            return changed.encode()
        pytest.fail('unexpected file transport operation')

    def guest(self, task, args, **kwargs):
        text = ' '.join(args)
        guest_checks.append(text)
        oracle_phase = '--phase baseline' in text
        gate_failed = scenario == 'backend_failure' and ' -m pytest tests/unit -q' in text
        if '--spec-sha256' in text and scenario != 'empty_oracle':
            phase = 'baseline' if oracle_phase else 'candidate'
            spec = pilot._canonical(case['oracle'])
            result = oracle_result(case, spec, phase, not oracle_phase)
            return SimpleNamespace(returncode=1 if oracle_phase else 0,
                stdout=pilot._canonical(result), stderr=b'')
        return SimpleNamespace(returncode=1 if oracle_phase or gate_failed else 0,
            stdout=b'desktop=visible\n' if kwargs.get('binary') else '', stderr=b'' if kwargs.get('binary') else '')

    monkeypatch.setattr(Controller, 'command', command)
    monkeypatch.setattr(Controller, 'start', start)
    monkeypatch.setattr(Controller, 'rpc', rpc)
    monkeypatch.setattr(Controller, 'guest', guest)
    requests = []
    clients = []
    async def response(request):
        body = json.loads(request.content); requests.append(body)
        sequence = [('file_read', {'path': 'docs/private-report.txt' if private_read else case['target_path']}),
                    ('edit_propose', {'path': case['target_path'], 'new_content': replacement, 'rationale': 'Fix mixed awareness'}),
                    ('session_validate', {})]
        index = len(requests) - 1
        message = {'role': 'assistant', 'content': 'Verified without publishing.'}
        if index < len(sequence):
            name, args = sequence[index]
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'call-' + str(index), 'type': 'function',
                'function': {'name': name, 'arguments': json.dumps(args)}}]}
        return httpx.Response(200, json={'id': 'inert-sdk-response', 'object': 'chat.completion',
            'created': 1, 'model': body['model'], 'choices': [{'index': 0, 'finish_reason': 'stop', 'message': message}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    def factory(*args, **kwargs):
        client = openai.AsyncOpenAI(api_key='synthetic-unused', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(response)))
        clients.append(client)
        return client
    monkeypatch.setattr(upgrade, 'make_route_client', factory)
    if scenario == 'registry_model_drift':
        original_owned_upgrade = pilot.run_owned_upgrade
        async def replace_registry_and_run(*args, **kwargs):
            path = Path(os.environ['JARVIS_UPGRADE_MODELS'])
            registry = json.loads(path.read_bytes())
            selected = next(row for row in registry['profiles'] if row['name'] == 'frontier-one')
            selected.update(model='causally-substituted-model', identity='openai/causally-substituted-model')
            path.write_text(json.dumps(registry))
            return await original_owned_upgrade(*args, **kwargs)
        monkeypatch.setattr(pilot, 'run_owned_upgrade', replace_registry_and_run)
    if scenario == 'preparation_unavailable':
        original_owned_upgrade = pilot.run_owned_upgrade
        async def unavailable_preparation(*args, **kwargs):
            # Real checked route preparation fails before assigning a run
            # snapshot; successful preflight must not become a verified flag.
            key = os.environ.pop('OPENAI_API_KEY')
            try:
                return await original_owned_upgrade(*args, **kwargs)
            finally:
                os.environ['OPENAI_API_KEY'] = key
        monkeypatch.setattr(pilot, 'run_owned_upgrade', unavailable_preparation)
    if scenario == 'cleanup_false':
        original_cleanup = pilot._cleanup
        def false_cleanup(*args, **kwargs):
            result = original_cleanup(*args, **kwargs)
            assert result['verified']
            return {**result, 'verified': False}
        monkeypatch.setattr(pilot, '_cleanup', false_cleanup)
    environment = dict(os.environ)
    report = pilot._run_owned_development_pilot(mode='live', source_ref=commit, image_id=identifier,
        image_home=home, profile='frontier-one', route='direct_api', limits=WorkloadLimits(deadline_seconds=60))
    assert dict(os.environ) == environment
    if scenario == 'preparation_unavailable':
        assert clients == [] and requests == [] and not report['substrate_passed']
        assert 'actual_selection_verified' not in report
        assert report['cleanup'] == {'verified': True, 'owned_tasks': []}
        return
    if scenario == 'registry_model_drift':
        assert clients == [] and requests == []
        assert report['reason'] == 'pilot_model_contract_changed' and not report['substrate_passed']
        assert report['selection']['model'] == 'frontier-one' and report['selection']['identity'] == 'openai/frontier-one'
        assert 'actual_selection_verified' not in report
        assert report['cleanup'] == {'verified': True, 'owned_tasks': []}
        # The public fresh entry must also preserve the honest failed inner
        # receipt, never turn its originally requested identity into a pass.
        path = Path(os.environ['JARVIS_UPGRADE_MODELS'])
        registry = json.loads(path.read_bytes())
        selected = next(row for row in registry['profiles'] if row['name'] == 'frontier-one')
        selected.update(model='frontier-one', identity='openai/frontier-one')
        path.write_text(json.dumps(registry))
        original_subprocess = pilot.subprocess.run
        def deliver_inner_receipt(command, **kwargs):
            if len(command) < 3 or command[2] != '--owned-worker':
                return original_subprocess(command, **kwargs)
            request = json.loads(Path(command[3]).read_bytes())
            return SimpleNamespace(returncode=2, stdout=pilot._canonical({**report, 'parent_request_id': request['run_id']}))
        monkeypatch.setattr(pilot.subprocess, 'run', deliver_inner_receipt)
        public = pilot.run_development_pilot(mode='live', source_ref=commit, image_id=identifier,
            image_home=home, profile='frontier-one', route='direct_api', limits=WorkloadLimits(deadline_seconds=60))
        assert not public['substrate_passed'] and public['reason'] == 'pilot_model_contract_changed'
        return
    assert clients and all(client.is_closed() for client in clients)
    if private_read:
        assert not report['substrate_passed'] and report['result_policy'] == 'confidential'
        assert len(requests) == 1 and report['cleanup']['verified']
        assert len(report['cleanup']['owned_tasks']) == 1 and 'verification' not in report
        assert 'PRIVATE_PILOT_ACQUIRED_CANARY_51af' not in json.dumps(report)
        assert all('PRIVATE_PILOT_ACQUIRED_CANARY_51af' not in json.dumps(body) for body in requests)
        return
    if scenario == 'backend_failure':
        assert not report['substrate_passed'] and report['status'] == 'unavailable'
        assert report['cleanup']['verified'] and len(report['cleanup']['owned_tasks']) == 2
        assert not any('--phase candidate' in check for check in guest_checks)
        assert 'Verified without publishing.' not in json.dumps(report)
        return
    if scenario == 'empty_oracle':
        assert report['reason'] == 'oracle_result_invalid' and not report['substrate_passed']
        assert report['cleanup']['verified'] and len(report['cleanup']['owned_tasks']) == 2
        return
    if scenario == 'cleanup_false':
        assert report['status'] == 'cleanup_unverified' and not report['substrate_passed']
        assert not report['known_test_quality_passed'] and not report['independent_holdout_verified']
        assert not report['cleanup']['verified']
        return
    assert report['substrate_passed'], report
    assert len(requests) == 4
    assert len(report['verification']['checks']) == len(MORTIMER.checks) == 12
    assert report['cleanup']['verified'] and len(report['cleanup']['owned_tasks']) == 2
    assert all('session_submit' not in {tool['function']['name'] for tool in body['tools']} for body in requests)
    assert not report['developer_accepted'] and not report['mar_i_complete'] and not report['independent_holdout_verified']
    assert report['full_registry']['status'] == 'required_not_run'
    assert report['target_candidate_sha256'] != report['target_baseline_sha256']
    assert any('--phase baseline' in check for check in guest_checks)
    assert any('--phase candidate' in check for check in guest_checks)
    assert 'Verified without publishing.' not in json.dumps(report)
