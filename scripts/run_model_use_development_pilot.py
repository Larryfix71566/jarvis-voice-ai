#!/usr/bin/env python3
"""Real sandbox substrate for WS-05; default dry, no Developer acceptance.

The four installed nonpublication Upgrade operations are an explicit subgate.
The six-server Developer registry and its native receipt remain a separate,
required phase. No result from this script can authorize that larger surface.
Candidate code is imported only by the independent offline verification guest.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CORPUS = ROOT / 'tests/fixtures/model_use_development_cases.json'
ORACLE = ROOT / 'scripts/model_use_development_oracle.py'
CORPUS_SHA256 = '6e3da0f9c65318a274a33187bcb26935856b2423a947b7d688ada9f957f0e867'
ORACLE_SHA256 = '38356175b9c32979316c6619ba408e4c43ecf38e9bc46bda080a700a7b5b6797'
OPERATIONS = ('file_read', 'edit_propose', 'session_validate', 'session_decline')
DEVELOPER_SERVERS = ('mcp-git', 'mcp-repo', 'mcp-selfedit', 'mcp-runlog', 'mcp-screen', 'mcp-status')
PROJECT = 'Larryfix71566/jarvis-voice-ai'


class DevelopmentPilotUnavailable(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def _read(path, *, limit=2 * 1024 * 1024):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > limit):
        raise DevelopmentPilotUnavailable('host_file_unverified')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if _pins(info) != _pins(opened):
            raise DevelopmentPilotUnavailable('host_file_changed')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(raw) > limit or _pins(after) != _pins(path.lstat()):
        raise DevelopmentPilotUnavailable('host_file_changed')
    if (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise DevelopmentPilotUnavailable('host_file_changed')
    return raw


def _pins(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _validate_spec(value):
    # Parse host metadata without importing an executable oracle module.
    if (type(value) is not dict or set(value) != {'version', 'cases'}
            or value['version'] != 'date-diff-oracle-v1' or type(value['cases']) is not list
            or not 1 <= len(value['cases']) <= 64):
        raise DevelopmentPilotUnavailable('oracle_spec_invalid')
    seen = set()
    for case in value['cases']:
        if type(case) is not dict:
            raise DevelopmentPilotUnavailable('oracle_spec_invalid')
        expected = 'expected_error' if 'expected_error' in case else 'expected'
        if (set(case) != {'id', 'timezone', 'a', 'b', expected}
                or type(case['id']) is not str or not case['id'].isascii()
                or not case['id'] or len(case['id']) > 80 or case['id'] in seen
                or type(case['timezone']) is not str or len(case['timezone']) > 80
                or any(item is not None and (type(item) is not str or len(item) > 256)
                       for item in (case['a'], case['b']))):
            raise DevelopmentPilotUnavailable('oracle_spec_invalid')
        seen.add(case['id'])
        if expected == 'expected_error':
            valid = case[expected] is True
        else:
            result = case[expected]
            valid = (type(result) is dict and set(result) == {'days', 'hours'}
                and type(result['days']) is int and type(result['hours']) is float
                and math.isfinite(result['hours']))
        if not valid:
            raise DevelopmentPilotUnavailable('oracle_spec_invalid')
    return value


class FrozenCorpus(dict):
    def __init__(self, case, oracle_raw, corpus_raw):
        super().__init__(case)
        self._oracle_raw = oracle_raw
        self._corpus_raw = corpus_raw


def _git(*args):
    try:
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(ROOT), *args],
                                       stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise DevelopmentPilotUnavailable('source_git_unavailable') from None


def load_corpus():
    raw, oracle = _read(CORPUS, limit=64 * 1024), _read(ORACLE, limit=64 * 1024)
    if _digest(raw) != CORPUS_SHA256 or _digest(oracle) != ORACLE_SHA256:
        raise DevelopmentPilotUnavailable('corpus_oracle_digest_mismatch')
    case = json.loads(raw)
    if (set(case) != {'version', 'case_id', 'target_path', 'goal', 'oracle_visibility', 'oracle'}
            or case['version'] != 'model-use-real-development-v1'
            or case['case_id'] != 'date-diff-mixed-awareness'
            or case['target_path'] != 'mcp_servers/mcp_time/logic.py'
            or case['oracle_visibility'] != 'public_known_tests'):
        raise DevelopmentPilotUnavailable('corpus_contract_mismatch')
    _validate_spec(case['oracle'])
    return FrozenCorpus(case, oracle, raw)


def upgrade_tools():
    from jarvis.agents.upgrade_agent import TOOL_SPECS
    by_name = {item['function']['name']: item for item in TOOL_SPECS}
    if not set(OPERATIONS).issubset(by_name):
        raise DevelopmentPilotUnavailable('installed_upgrade_schema_changed')
    return json.loads(json.dumps([by_name[name] for name in OPERATIONS]))


def full_registry_contract():
    """Pin installed declarations; live MCP discovery is still required."""
    agents = yaml.safe_load(_read(ROOT / 'config/agents.yaml'))['sub_agents']
    developer = next(item for item in agents if item['name'] == 'developer')
    names = tuple(developer['mcp_servers'])
    if names != DEVELOPER_SERVERS:
        raise DevelopmentPilotUnavailable('developer_server_contract_changed')
    configured = yaml.safe_load(_read(ROOT / 'config/mcp_servers.yaml'))['servers']
    entries = {item['name']: item for item in configured}
    tools, sources = [], {}
    for name in names:
        entry = entries[name]
        if entry['args'] != ['-m', 'mcp_servers.' + name.replace('-', '_') + '.server']:
            raise DevelopmentPilotUnavailable('developer_spawn_contract_changed')
        folder = ROOT / 'mcp_servers' / name.replace('-', '_')
        manifest = _read(folder / 'skill.yaml')
        declared = yaml.safe_load(manifest)['tools']
        if type(declared) is not list or not all(type(item) is str for item in declared):
            raise DevelopmentPilotUnavailable('developer_manifest_changed')
        tools.extend(declared)
        for path in (folder / 'skill.yaml', folder / 'server.py'):
            sources[path.relative_to(ROOT).as_posix()] = _digest(_read(path))
    if len(tools) != 40 or len(set(tools)) != 40:
        raise DevelopmentPilotUnavailable('developer_registry_count_changed')
    return {'operation_surface': 'developer_full_registry', 'servers': list(names),
            'declared_tool_names': tools, 'declared_tool_count': len(tools),
            'declaration_source_sha256': sources, 'live_schema_verified': False,
            'status': 'required_not_run', 'developer_accepted': False,
            'required_path': ['SkillRegistry.start', 'SkillRegistry.openai_tools',
                              'SubAgent.run', 'authenticated_workspace_source_transport',
                              'real_UpgradeAgent', 'independent_MORTIMER_verification'],
            'required_native_receipt': 'exact_actual_model_executable_discovered_40_schemas',
            'forbidden_substitutes': ['tool_specs_override', 'fake_tool_executor', 'four_tool_receipt',
                                     'public_fixture_receipt', 'text_only_receipt']}


def inspect_live_developer_registry(registry):
    """Scaffold boundary: an actual started registry, never an override menu."""
    from jarvis.skills.registry import SkillRegistry
    contract = full_registry_contract()
    if type(registry) is not SkillRegistry:
        raise DevelopmentPilotUnavailable('actual_developer_registry_required')
    from mcp import ClientSession
    generations = []
    for name in DEVELOPER_SERVERS:
        handle = registry._handles.get(name)
        if (handle is None or handle.state != 'up' or handle.task is None or handle.task.done()
                or not handle.ready.is_set() or handle.gone.is_set()
                or not isinstance(handle.session, ClientSession)
                or registry._sessions.get(name) is not handle.session
                or handle.entry.get('args') != ['-m', 'mcp_servers.' + name.replace('-', '_') + '.server']):
            raise DevelopmentPilotUnavailable('live_developer_registry_incomplete')
        generations.append((name, handle, handle.session))
    schemas = registry.openai_tools(list(DEVELOPER_SERVERS))
    expected = set(contract['declared_tool_names'])
    if (len(schemas) != 40 or {item['function']['name'] for item in schemas} != expected
            or not set(DEVELOPER_SERVERS).issubset(registry.server_names)):
        raise DevelopmentPilotUnavailable('live_developer_registry_incomplete')
    for name, handle, session in generations:
        if registry._handles.get(name) is not handle or handle.session is not session or handle.gone.is_set():
            raise DevelopmentPilotUnavailable('live_developer_registry_changed')
    references = [{'name': item['function']['name'], 'description': item['function']['description'],
                   'parameters': item['function']['parameters']} for item in schemas]
    return {**contract, 'live_schema_verified': True,
            'tool_schema_sha256': _digest(_canonical(references)),
            'status': 'schema_only_unverified_execution'}


@dataclass(frozen=True)
class HoldoutSnapshot:
    raw: bytes = field(repr=False)
    sha256: str
    path: Path = field(repr=False)
    pins: tuple = field(repr=False)


def _holdout_snapshot(path, expected_sha256, case):
    if path is None:
        if expected_sha256 is not None:
            raise DevelopmentPilotUnavailable('holdout_path_required')
        return None
    path = Path(path)
    if path.resolve().is_relative_to(ROOT.resolve()):
        raise DevelopmentPilotUnavailable('holdout_inside_developer_source')
    raw = _read(path, limit=64 * 1024)
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or '') or _digest(raw) != expected_sha256:
        raise DevelopmentPilotUnavailable('holdout_digest_mismatch')
    spec = _validate_spec(json.loads(raw))
    semantic = lambda item: _canonical({key: value for key, value in item.items() if key != 'id'})
    known = {semantic(item) for item in case['oracle']['cases']}
    if any(semantic(item) in known for item in spec['cases']):
        raise DevelopmentPilotUnavailable('holdout_copies_known_cases')
    info = path.lstat()
    return HoldoutSnapshot(raw, expected_sha256, path,
        (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns))


def _recheck_holdout(holdout):
    if holdout is None: return
    info = holdout.path.lstat()
    if ((info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != holdout.pins
            or _read(holdout.path, limit=64 * 1024) != holdout.raw):
        raise DevelopmentPilotUnavailable('holdout_source_changed')


def _source(source_ref, case):
    from sandbox.artifacts import Candidate, File, source_path_allowed
    from sandbox.profiles import MORTIMER
    commit = _git('rev-parse', '--verify', str(source_ref) + '^{commit}').decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', commit):
        raise DevelopmentPilotUnavailable('source_ref_invalid')
    origin = _git('config', '--get', 'remote.origin.url').decode().strip()
    if origin.removesuffix('.git') not in {'https://github.com/' + PROJECT, 'git@github.com:' + PROJECT}:
        raise DevelopmentPilotUnavailable('source_project_unverified')
    target = case['target_path']
    from jarvis.selfedit.allowlist import Allowlist
    if not source_path_allowed(target) or not Allowlist.load(ROOT / 'config/self_edit_allowlist.json').is_allowed(target):
        raise DevelopmentPilotUnavailable('case_path_forbidden')
    target_data = _git('show', commit + ':' + target)
    dependencies = Candidate(tuple(File(path, 0o644, _git('show', commit + ':' + path))
                                   for path in MORTIMER.dependencies))
    return commit, _digest(target_data), MORTIMER.dependency_key(dependencies)


def _image(image_home, image_id, dependency_key):
    from sandbox.profiles import MORTIMER
    if not re.fullmatch(r'[0-9a-f]{64}', image_id or ''):
        raise DevelopmentPilotUnavailable('explicit_image_required')
    home = Path(image_home).expanduser().resolve(strict=True)
    raw = _read(home / 'images' / image_id / 'image.json')
    record = json.loads(raw)
    identity = {key: record.get(key) for key in ('profile', 'dependencies', 'recipe', 'source', 'origin_image')}
    if (record.get('id') != image_id or record.get('profile') != MORTIMER.name
            or record.get('vm') != 'mortimer-image-' + image_id[:20]
            or _digest(json.dumps(identity, sort_keys=True).encode()) != image_id
            or record.get('dependencies') != dependency_key):
        raise DevelopmentPilotUnavailable('image_source_incompatible')
    return home, record, _digest(raw)


def inspect_development_pilot(*, source_ref, image_id, image_home, profile, route,
                              operation_surface='upgrade_nonpublication'):
    from jarvis.model_routing import inspect_route_choice
    from sandbox.profiles import MORTIMER
    from sandbox.verify import runner_fingerprint
    case = load_corpus()
    full = full_registry_contract()
    report = {'version': 'model-use-development-pilot-v1', 'workstream': 'WS-05',
              'mode': 'dry', 'operation_surface': operation_surface, 'developer_accepted': False,
              'mar_i_complete': False, 'full_registry': full, 'publication_allowed': False,
              'captured_at_utc': datetime.now(timezone.utc).isoformat(),
              'corpus_sha256': CORPUS_SHA256, 'oracle_sha256': ORACLE_SHA256,
              'harness_sha256': _digest(_read(Path(__file__))), 'target_path': case['target_path'],
              'oracle_visibility': 'public_known_tests', 'independent_holdout_verified': False,
              'profile': {'name': MORTIMER.name, 'sha256': MORTIMER.fingerprint,
                          'checks': [{'name': name, 'argv': list(argv)} for name, argv in MORTIMER.checks],
                          'runner_sha256': runner_fingerprint()},
              'handling': {'response_text_saved': False, 'provider_error_text_saved': False,
                           'candidate_executed_on_host': False, 'production_writes': False,
                           'settings_changed': False},
              'limitations': ['four real Upgrade operations are a substrate subgate, not full Developer acceptance',
                              'tracked public oracle is known-test quality, not an independent holdout',
                              'full actual six-server/40-schema MCP execution and own native receipt remain required',
                              'provider billing and account allowance are not established by usage counts']}
    if operation_surface == 'developer_full_registry':
        report.update(status='unavailable', reason='full_registry_implementation_required')
        return report
    if operation_surface != 'upgrade_nonpublication':
        raise DevelopmentPilotUnavailable('operation_surface_invalid')
    tools = upgrade_tools()
    report['tool_names'] = list(OPERATIONS)
    report['tool_schema_sha256'] = _digest(_canonical([
        {'name': item['function']['name'], 'description': item['function']['description'],
         'parameters': item['function']['parameters']} for item in tools]))
    commit, before, dependencies = _source(source_ref, case)
    home, image, image_record_digest = _image(image_home, image_id, dependencies)
    report.update(source_revision=commit, target_baseline_sha256=before,
                  source_dependency_sha256=dependencies, image_id=image_id,
                  image_record_sha256=image_record_digest, prepared_image_source=image['source'])
    policy, model, access = inspect_route_choice('developer', profile, route)
    report['selection'] = {'profile': profile, 'model': model['model'], 'identity': model.get('identity'),
                           'route': access.name, 'privacy': policy.privacy, 'billing': access.billing}
    report['selection_contract_sha256'] = _digest(_canonical({
        'policy': asdict(policy), 'profile': model, 'route': asdict(access), 'tools': tools}))
    report.update(status='dry_ready_unverified', source_scanner_verified=False,
                  image_stopped_verified=False, capability_verified=False, substrate_passed=False)
    return report


class FrozenLocalSource:
    """Driver-owned local Git-object source; Runtime still runs snapshot gates."""
    def __init__(self, commit):
        self.commit = commit
        self.root = ROOT.resolve(strict=True)
    def fetch(self, repository, branch, token):
        if (repository != PROJECT or branch != self.commit or ROOT.resolve(strict=True) != self.root
                or _git('rev-parse', '--verify', self.commit + '^{commit}').decode().strip() != self.commit):
            raise DevelopmentPilotUnavailable('frozen_source_binding_changed')
        return self.root, self.commit


_SESSION_KEYS = ('id', 'task', 'run_id', 'ref', 'image', 'repository', 'kind')
_TASK_KEYS = ('id', 'vm', 'image', 'purpose', 'profile', 'parent_task', 'source_commit',
              'source_sha256', 'source_files', 'source_bytes', 'candidate', 'profile_sha256', 'prepared')
_mutation_task = ContextVar('development_pilot_mutation_task', default=None)


@dataclass(frozen=True)
class TaskGeneration:
    task: str
    fields: tuple
    directory: tuple
    inputs: tuple


def _task_generation(controller, task, *, row=None):
    directory = controller.task_dir(task)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise DevelopmentPilotUnavailable('cleanup_task_owner_changed')
    row = json.loads(_read(directory / 'state.json')) if row is None else row
    if row.get('id') != task or row.get('vm') != 'mortimer-' + task:
        raise DevelopmentPilotUnavailable('cleanup_task_owner_changed')
    inputs = []
    for name in ('source.tar', 'baseline.json', 'candidate.json', 'hydrate.json'):
        path = directory / 'input' / name
        if path.exists() or path.is_symlink():
            inputs.append((name, _digest(_read(path, limit=64 * 1024 * 1024))))
    return TaskGeneration(task, tuple(row.get(key) for key in _TASK_KEYS),
                          (info.st_dev, info.st_ino, info.st_mode, info.st_uid), tuple(inputs))


class OwnedAllocations:
    """Retain only the actual installed allocator's exact task generations."""
    def __init__(self, runtime, *, run_id, source_ref, image_id, allowed):
        self.runtime, self.run_id, self.source_ref, self.image_id = runtime, run_id, source_ref, image_id
        self.tasks = {}
        self.session = self.identity = None
        create = runtime.images.create
        def allocated(image, repo, ref, profile, *, purpose='development', candidate=None,
                      task_id=None, parent_task=None):
            from sandbox.profiles import MORTIMER
            if (image != image_id or Path(repo).resolve() != ROOT.resolve() or ref != source_ref
                    or profile is not MORTIMER or purpose not in {'development', 'verification'}):
                raise DevelopmentPilotUnavailable('pilot_allocation_binding_changed')
            if purpose == 'development':
                if self.session is not None or parent_task is not None or candidate is not None or task_id is None:
                    raise DevelopmentPilotUnavailable('pilot_allocation_binding_changed')
                session = runtime.active(PROJECT, 'selfedit', allowed)
                if session is None:
                    raise DevelopmentPilotUnavailable('pilot_allocation_binding_changed')
                state = session._read()
                if (state.get('task') != task_id or state.get('run_id') != run_id
                        or state.get('ref') != ref or state.get('image') != image
                        or state.get('repository') != PROJECT or state.get('kind') != 'selfedit'):
                    raise DevelopmentPilotUnavailable('pilot_allocation_binding_changed')
                self.session = session
                self.identity = tuple(state.get(key) for key in _SESSION_KEYS)
            else:
                if (self.identity is None or parent_task != self.identity[1] or candidate is None):
                    raise DevelopmentPilotUnavailable('pilot_allocation_binding_changed')
            # The installed allocator accepts explicit IDs. Retain it before
            # entry so a partial create cannot escape the cleanup owner.
            task_id = task_id or uuid.uuid4().hex[:12]
            if task_id in self.tasks or (runtime.controller.home / 'tasks' / task_id).exists():
                raise DevelopmentPilotUnavailable('pilot_allocation_identity_reused')
            self.tasks[task_id] = None
            try:
                return create(image, repo, ref, profile, purpose=purpose, candidate=candidate,
                              task_id=task_id, parent_task=parent_task)
            finally:
                if (runtime.controller.home / 'tasks' / task_id / 'state.json').exists():
                    proof = _task_generation(runtime.controller, task_id)
                    row = dict(zip(_TASK_KEYS, proof.fields))
                    expected = {'image': image, 'purpose': purpose, 'profile': profile.name,
                                'parent_task': parent_task}
                    if (any(row.get(key) != value for key, value in expected.items())
                            or row.get('source_commit') not in {None, ref}
                            or (row.get('candidate') is not None and candidate is not None
                                and row['candidate'] != candidate.fingerprint)):
                        raise DevelopmentPilotUnavailable('pilot_allocation_binding_changed')
                    self.tasks[task_id] = proof
        runtime.images.create = allocated
        controller = runtime.controller
        read = controller.read
        def pinned_read(task):
            if _mutation_task.get() == task:
                # Return the same acquired record that passed the pin. A
                # second pathname read would reintroduce check-then-use.
                row = json.loads(_read(controller.task_dir(task) / 'state.json'))
                self.require(task, row=row)
                return row
            return read(task)
        controller.read = pinned_read
        for name in ('stop', 'destroy', 'cancel'):
            installed = getattr(controller, name)
            def mutation(task, _installed=installed):
                self.require(task)
                token = _mutation_task.set(task)
                try:
                    return _installed(task)
                finally:
                    _mutation_task.reset(token)
            setattr(controller, name, mutation)
        start = controller.start
        def ready_start(task, *, provisioning=False, headless=False):
            self.require(task)
            token = _mutation_task.set(task)
            try:
                result = start(task, provisioning=provisioning, headless=headless)
                _wait_boot(controller, task, lambda: self.require(task))
                return result
            finally:
                _mutation_task.reset(token)
        controller.start = ready_start

    def require(self, task, *, row=None):
        proof = self.tasks.get(task)
        if proof is None or _task_generation(self.runtime.controller, task, row=row) != proof:
            raise DevelopmentPilotUnavailable('cleanup_task_owner_changed')
        return proof


def _wait_boot(controller, task, verify, *, timeout=90):
    """Wait for authoritative Tart state and guest readiness after Popen."""
    deadline = time.monotonic() + timeout
    waiting = threading.Event()
    try:
        while time.monotonic() < deadline:
            verify()
            state = controller.read(task)
            if ((controller.task_dir(task) / 'cancelled.json').exists()
                    or (state.get('parent_task') and
                        (controller.task_dir(state['parent_task']) / 'cancelled.json').exists())):
                raise DevelopmentPilotUnavailable('pilot_boot_cancelled')
            remaining = deadline - time.monotonic()
            observed = controller.command('list', '--source', 'local', '--format', 'json',
                capture_output=True, text=True, timeout=min(10, remaining))
            rows = [row for row in json.loads(observed.stdout) if row.get('Name') == state['vm']]
            if len(rows) > 1:
                raise DevelopmentPilotUnavailable('pilot_boot_identity_changed')
            if len(rows) == 1 and rows[0].get('State') == 'running':
                try:
                    result = controller.command('exec', state['vm'], '/usr/bin/true',
                        capture_output=True, timeout=min(10, max(.001, deadline - time.monotonic())))
                    verify()
                    if result.returncode == 0 and time.monotonic() < deadline:
                        return
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass
            waiting.wait(max(0, min(.25, deadline - time.monotonic())))
        raise DevelopmentPilotUnavailable('pilot_boot_readiness_timeout')
    except BaseException:
        controller.stop(task)
        raise


def _worker_environment(directory, profile, route, capability_receipt, limits, *, parent_policy=None):
    from jarvis.model_routing import POLICY_PATH_ENV, workload_limits_from_policy
    path = Path(os.environ.get(POLICY_PATH_ENV) or ROOT / 'config/model_access.yaml')
    policy = yaml.safe_load(_read(path))
    configured = {**policy.get('defaults', {}), **policy['workloads']['developer']}
    existing = workload_limits_from_policy(configured)
    chosen = policy['workloads']['developer']
    for field in ('max_output_tokens_per_call', 'deadline_seconds', 'max_estimated_spend_usd_per_task'):
        values = [value for value in (getattr(existing, field), getattr(limits, field),
                  getattr(parent_policy.limits, field) if parent_policy is not None else None) if value is not None]
        chosen[field] = min(values) if values else None
    if parent_policy is not None:
        from jarvis.privacy_policy import DataPolicy, strictest
        chosen['privacy'] = strictest(DataPolicy(configured['privacy'], 'current-pilot-policy'),
            DataPolicy(parent_policy.privacy, 'captured-parent-policy')).level
    chosen.update(profile=profile, route=route, fallback_routes=[])
    path = directory / 'model-access.json'
    path.write_bytes(_canonical(policy)); path.chmod(0o600)
    changes = {'JARVIS_MODEL_ROUTING_ENABLED': '1',
               'JARVIS_MODEL_ACCESS_CONFIG': str(path), 'JARVIS_MODEL_PROFILE_DEVELOPER': profile,
               'JARVIS_MODEL_ROUTE_DEVELOPER': route, 'JARVIS_REPO_ROOT': str(ROOT)}
    if capability_receipt is not None:
        from jarvis.subscription_tools import TOOL_CAPABILITY_RECEIPT_ENV
        changes[TOOL_CAPABILITY_RECEIPT_ENV] = str(capability_receipt)
    # This mapping is supplied only to a fresh exec process. It never lends
    # routing or storage authority to threads in the calling application.
    return {**os.environ, **changes}


def _owned_directory(home, identifier):
    if not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise DevelopmentPilotUnavailable('pilot_storage_owner_invalid')
    parent = home / 'pilots'
    parent.mkdir(mode=0o700, exist_ok=True)
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise DevelopmentPilotUnavailable('pilot_storage_owner_invalid')
    directory = parent / identifier
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise DevelopmentPilotUnavailable('pilot_storage_owner_invalid')
    return directory


async def run_owned_upgrade(agent, goal, data_policy, directory, *, drain_timeout_s=10, status=None):
    """Retain the real synchronous Upgrade worker and its isolated stores."""
    from jarvis.storage_context import storage_scope, state_to_thread
    storage = None
    try:
        async with storage_scope(db_path=directory / 'pilot.db', costs_db_path=directory / 'costs.db',
                model_preferences_enabled=False, drain_timeout_s=drain_timeout_s) as storage:
            worker = asyncio.create_task(state_to_thread(agent.run, goal, data_policy=data_policy))
            try:
                result = await asyncio.shield(worker)
            except asyncio.CancelledError:
                agent.request_cancel()
                # Retain the actual concurrent future, not only its asyncio
                # wrapper, until the executing host thread completes.
                try:
                    await asyncio.wait_for(asyncio.shield(worker), timeout=drain_timeout_s)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                raise
    finally:
        if status is not None:
            status.update(verified=bool(storage and storage.cleanup_verified),
                          pending_workers=storage.pending_workers if storage is not None else 0)
    if not storage.cleanup_verified:
        raise DevelopmentPilotUnavailable('pilot_storage_cleanup_unverified')
    return result, {'verified': True, 'pending_workers': storage.pending_workers}


class FrozenPlannerGuard:
    """Check the actual installed per-run snapshot before client creation."""
    def __init__(self, agent, resolved, selected, registry, tools, *, native_identity=None):
        from jarvis.model_routing import ModelRouteError
        from jarvis.subscription import COMMAND_ENV
        from jarvis.subscription_tools import TOOLS_ENABLED_ENV, TOOL_CAPABILITY_RECEIPT_ENV
        self.failed = False
        self.verified = False
        self.route = resolved
        self.registry = _canonical(registry)
        self.tools = _canonical(tools)
        self.policy_level = selected.privacy
        self.temperature, self.effort = agent.cfg.get('temperature'), agent.cfg.get('effort')
        self.native_identity = _canonical(native_identity) if native_identity is not None else None
        names = {'JARVIS_MODEL_ROUTING_ENABLED', 'JARVIS_MODEL_ACCESS_CONFIG', 'JARVIS_UPGRADE_MODELS',
            'JARVIS_MODEL_PROFILE_DEVELOPER', 'JARVIS_MODEL_ROUTE_DEVELOPER',
            'JARVIS_MODEL_PREFERENCES_ENABLED', 'JARVIS_SUBSCRIPTION_TEXT_ENABLED', 'PATH',
            TOOLS_ENABLED_ENV, TOOL_CAPABILITY_RECEIPT_ENV, *COMMAND_ENV.values()}
        names.update(name for name in (resolved.api_key_env, resolved.route.credential_env) if name)
        # Credential values remain in this private process-memory closure;
        # neither values nor their hashes enter the receipt.
        self.environment = {name: os.environ.get(name) for name in names}
        self.native_receipt = None
        if self.native_identity is not None:
            path = Path(self.environment[TOOL_CAPABILITY_RECEIPT_ENV])
            self.native_receipt = (path, _digest(_read(path)))
        if agent._resolved_route != resolved:
            raise DevelopmentPilotUnavailable('pilot_model_contract_changed')
        installed_prepare, installed_completion = agent._prepare_run_snapshot, agent._routed_completion
        def prepare(**kwargs):
            installed_prepare(**kwargs)
            self.verify(agent)
        async def completion(request):
            self.verify(agent, request)
            return await installed_completion(request)
        agent._prepare_run_snapshot, agent._routed_completion = prepare, completion
        self.error = ModelRouteError

    def verify(self, agent, request=None):
        from jarvis.agents.upgrade_agent import load_model_registry
        try:
            snapshot = agent._run_snapshot
            if (snapshot is None or snapshot.route != self.route
                    or snapshot.parent_request_id != agent._run_id
                    or snapshot.budget.parent_request_id != agent._run_id
                    or snapshot.budget.limits != self.route.limits
                    or snapshot.policy.level != self.policy_level
                    or snapshot.temperature != self.temperature or snapshot.effort != self.effort
                    or _canonical(agent._tool_specs) != self.tools
                    or _canonical(load_model_registry(agent._registry_path)) != self.registry
                    or any(os.environ.get(name) != value for name, value in self.environment.items())
                    or (request is not None and (request.get('model') != self.route.model
                        or _canonical(request.get('tools')) != self.tools))):
                raise ValueError()
            if self.native_identity is not None:
                from jarvis.model_execution import ModelToolReference
                from jarvis.subscription_tools import _validate_native_receipt
                tools = json.loads(self.tools)
                references = tuple(ModelToolReference(item['function']['name'], item['function']['parameters'],
                    item['function']['description']) for item in tools)
                actual = _validate_native_receipt(self.route.model, list(OPERATIONS), references)
                if (_canonical(actual) != self.native_identity
                        or _digest(_read(self.native_receipt[0])) != self.native_receipt[1]):
                    raise ValueError()
            self.verified = True
        except Exception:
            self.failed = True
            raise self.error('pilot_model_contract_changed') from None


def _oracle_result(check, log_path, raw_spec, phase, case):
    try:
        raw = _read(log_path, limit=64 * 1024)
        value = json.loads(raw)
        expected = {'version', 'cases', 'passed', 'phase', 'spec_sha256',
                    'corpus_sha256', 'case_id', 'oracle_sha256'}
        spec = _validate_spec(json.loads(raw_spec))
        ids = [item['id'] for item in spec['cases']]
        outcomes = value['cases']
        if (type(value) is not dict or set(value) != expected
                or value['version'] != 'date-diff-oracle-result-v1'
                or value['phase'] != phase or value['spec_sha256'] != _digest(raw_spec)
                or value['corpus_sha256'] != CORPUS_SHA256 or value['case_id'] != case['case_id']
                or value['oracle_sha256'] != ORACLE_SHA256
                or type(outcomes) is not list or len(outcomes) != len(ids)
                or any(type(item) is not dict or set(item) != {'id', 'passed'}
                       or item['id'] != identifier or type(item['passed']) is not bool
                       for identifier, item in zip(ids, outcomes))
                or type(value['passed']) is not bool
                or value['passed'] != all(item['passed'] for item in outcomes)
                or type(check['returncode']) is not int or check['returncode'] != (0 if value['passed'] else 1)
                or check['passed'] is not value['passed'] or check['log_sha256'] != _digest(raw)):
            raise ValueError()
        return {'phase': phase, 'passed': value['passed'], 'returncode': check['returncode'],
                'log_sha256': check['log_sha256'], 'case_count': len(ids)}
    except Exception:
        raise DevelopmentPilotUnavailable('oracle_result_invalid') from None


def _oracle_checks(runtime, session, receipt, case, *, holdout=None):
    from sandbox.artifacts import Candidate
    from sandbox.control import GUEST_INPUT
    from sandbox.durable import atomic_bytes
    from sandbox.profiles import PYTHON, MORTIMER
    if (type(case) is not FrozenCorpus or _digest(case._oracle_raw) != ORACLE_SHA256
            or _digest(case._corpus_raw) != CORPUS_SHA256 or case != json.loads(case._corpus_raw)):
        raise DevelopmentPilotUnavailable('corpus_oracle_digest_mismatch')
    state = session._read()
    task = receipt['verification_task']
    proof = runtime.controller.read(task)
    if (proof.get('parent_task') != state['task'] or proof.get('purpose') != 'verification'
            or proof.get('image') != state['image'] or proof.get('source_commit') != state['ref']):
        raise DevelopmentPilotUnavailable('oracle_guest_owner_changed')
    specs = [('known', _canonical(case['oracle']), False)]
    if holdout is not None:
        _recheck_holdout(holdout)
        # It is confined to the offline guest and never enters model input.
        specs.append(('external', holdout.raw, True))
    inputs = runtime.controller.task_dir(task) / 'input'
    atomic_bytes(inputs / 'pilot-oracle.py', case._oracle_raw, mode=0o644)
    outcomes = []
    try:
        runtime.controller.start(task, provisioning=False, headless=False)
        runtime.verifier.wait_ready(task)
        for name, raw, external in specs:
            atomic_bytes(inputs / ('pilot-' + name + '.json'), raw, mode=0o644)
            checks = []
            for phase in ('baseline', 'candidate'):
                argv = (PYTHON, '-I', GUEST_INPUT + '/pilot-oracle.py', '--phase', phase,
                        '--spec', GUEST_INPUT + '/pilot-' + name + '.json', '--spec-sha256', _digest(raw))
                check = runtime.verifier.run_check(task, 'pilot-' + name + '-' + phase, argv,
                    session.directory / 'pilot-oracle', 60)
                checks.append(_oracle_result(check,
                    session.directory / 'pilot-oracle' / ('pilot-' + name + '-' + phase + '.log'), raw, phase, case))
            outcomes.append({'kind': name, 'outside_developer_source': external,
                             'spec_sha256': _digest(raw), 'checks': checks})
        captured = Candidate.decode(runtime.controller.rpc(task, {'operation': 'capture',
            'baseline_paths': [file.path for file in session._files(state).baseline.files]}))
        if captured.fingerprint != receipt['candidate']:
            raise DevelopmentPilotUnavailable('oracle_candidate_changed')
    finally:
        runtime.controller.stop(task)
    runtime.verifier.receipt(session._files(session._read()), state['image'], MORTIMER)
    return outcomes


@contextmanager
def _pin_cleanup_session(session, identity, source_pin):
    from sandbox.session import pin_source_identity
    installed_read = session._read
    def owner_read():
        state = installed_read()
        if tuple(state.get(key) for key in _SESSION_KEYS) != identity:
            raise DevelopmentPilotUnavailable('cleanup_session_owner_changed')
        return state
    session._read = owner_read
    try:
        with pin_source_identity(session, source_pin):
            yield
    finally:
        session._read = installed_read


def _cleanup(runtime, session, identity, *, allocations=None):
    state = session._read()
    if tuple(state.get(key) for key in _SESSION_KEYS) != identity or state.get('id') != session.id:
        raise DevelopmentPilotUnavailable('cleanup_session_owner_changed')
    parent = state['task']
    # No task discovery: only allocations retained before installed create.
    owned = list(allocations.tasks) if allocations is not None else [parent]
    if allocations is not None and (allocations.session is not session or allocations.identity != identity):
        raise DevelopmentPilotUnavailable('cleanup_session_owner_changed')
    has_task = (runtime.controller.home / 'tasks' / parent / 'state.json').is_file()
    record = runtime.controller.read(parent) if has_task else {}
    source = runtime.controller.home / 'tasks' / parent / 'input/source.tar'
    baseline = session._files(state).baseline.fingerprint if source.is_file() else None
    pin = (state['id'], parent, state.get('run_id'), state['ref'], state['repository'].casefold(),
           state['kind'], record.get('source_sha256'), baseline)
    failures = []
    with _pin_cleanup_session(session, identity, pin):
        # cancel deliberately does not acquire this lock itself. Teardown
        # runs after the retained Upgrade worker has completed.
        try:
            with session._locked():
                if tuple(session._read().get(key) for key in _SESSION_KEYS) != identity:
                    raise DevelopmentPilotUnavailable('cleanup_session_owner_changed')
                session.cancel()
        except BaseException as exc:
            failures.append(type(exc).__name__)
        try:
            # Installed revert reacquires the mutation lock and reads the
            # pinned actor at its actual mutation boundary.
            session.revert()
        except BaseException as exc:
            failures.append(type(exc).__name__)
    for child in owned:
        if child == parent:
            continue
        try:
            if allocations is None:
                raise DevelopmentPilotUnavailable('cleanup_identity_unverified')
            allocations.require(child)
            row = runtime.controller.read(child)
            if row.get('status') in {'running', 'provisioning'}:
                runtime.controller.stop(child)
            runtime.controller.destroy(child)
        except BaseException as exc:
            failures.append(type(exc).__name__)
    verified = not failures
    for task in owned:
        try:
            if allocations is not None:
                allocations.require(task)
            verified = runtime.controller.read(task).get('status') == 'deleted' and verified
        except BaseException:
            verified = False
    return {'owned_tasks': owned, 'verified': verified, 'failure_categories': failures}


def _run_owned_development_pilot(*, mode='dry', source_ref, image_id, image_home, profile, route,
                          operation_surface='upgrade_nonpublication', capability_receipt=None,
                          external_holdout=None, external_holdout_sha256=None, limits=None,
                          directory=None, run_id=None):
    if mode not in {'dry', 'live'}:
        raise DevelopmentPilotUnavailable('mode_invalid')
    report = inspect_development_pilot(source_ref=source_ref, image_id=image_id, image_home=image_home,
        profile=profile, route=route, operation_surface=operation_surface)
    if mode == 'dry' or report['status'] == 'unavailable': return report
    from jarvis.model_routing import WorkloadLimits, resolve_model_route_checked, resolve_policy
    from jarvis.privacy_policy import DataPolicy, assert_route_allowed
    from sandbox.control import Controller
    from sandbox.runtime import Runtime
    from jarvis.selfedit.service import SelfEditService
    from jarvis.agents.upgrade_agent import UpgradeAgent, SYSTEM_PROMPT, load_model_registry
    limits = WorkloadLimits(deadline_seconds=1800) if limits is None else limits
    if type(limits) is not WorkloadLimits or limits.deadline_seconds is None:
        raise DevelopmentPilotUnavailable('explicit_model_deadline_required')
    home = Path(image_home).resolve(strict=True)
    settings = json.loads(_read(home / 'settings.json'))
    if (settings.get('version') != 1 or type(settings.get('tart')) is not str
            or type(settings.get('softnet')) is not str or type(settings.get('images')) is not dict):
        raise DevelopmentPilotUnavailable('installed_sandbox_settings_invalid')
    run_id = run_id or str(uuid.uuid4())
    if str(uuid.UUID(run_id)) != run_id:
        raise DevelopmentPilotUnavailable('pilot_origin_invalid')
    directory = Path(directory) if directory is not None else home / 'pilots' / uuid.uuid4().hex
    if (directory.parent != home / 'pilots' or not re.fullmatch(r'[0-9a-f]{32}', directory.name)
            or directory.is_symlink()):
        raise DevelopmentPilotUnavailable('pilot_storage_owner_invalid')
    directory = _owned_directory(home, directory.name)
    runtime = session = agent = allocations = None
    report.update(mode='live', status='unavailable', parent_request_id=run_id, substrate_passed=False,
                  cleanup={'verified': False}, capability_verified=False)
    case = load_corpus()
    # Freeze unseen input before any model/client or development operation.
    holdout = _holdout_snapshot(external_holdout, external_holdout_sha256, case)
    if holdout is not None:
        report['heldout_input'] = {'sha256': holdout.sha256, 'prepared_before_model': True,
                                  'outside_developer_source': True, 'model_input_contains_holdout': False}
    try:
        # The installed Upgrade path reads process routing configuration.
        # A live public caller enters through a fresh CLI process; this
        # internal function is also the explicit inert SDK test seam.
        if os.environ.get('JARVIS_MODEL_ROUTING_ENABLED') != '1':
            raise DevelopmentPilotUnavailable('owned_routed_process_required')
        async def execute():
            from jarvis.storage_context import storage_scope
            async with storage_scope(db_path=directory / 'pilot.db', costs_db_path=directory / 'costs.db',
                                     model_preferences_enabled=False) as stores:
                nonlocal runtime, session, agent, allocations
                registry = load_model_registry()
                tools = upgrade_tools()
                selected = resolve_policy('developer', explicit_profile=profile, include_preferences=False)
                if selected.route != route:
                    raise DevelopmentPilotUnavailable('owned_routed_process_required')
                for name in ('max_output_tokens_per_call', 'deadline_seconds', 'max_estimated_spend_usd_per_task'):
                    required, actual = getattr(limits, name), getattr(selected.limits, name)
                    if required is not None and (actual is None or actual > required):
                        raise DevelopmentPilotUnavailable('owned_routed_process_limits_mismatch')
                resolved = resolve_model_route_checked('developer', explicit_profile=profile, explicit_route=route)
                assert_route_allowed(resolved.route, DataPolicy('approved_external', 'sha-pinned-public-pilot-case'))
                if resolved.route.adapter in {'subscription_runtime', 'codex_subscription_runtime'}:
                    if resolved.route.adapter != 'subscription_runtime':
                        raise DevelopmentPilotUnavailable('native_developer_runtime_unverified')
                    from jarvis.model_execution import ModelToolReference
                    from jarvis.subscription_tools import _validate_native_receipt
                    references = tuple(ModelToolReference(item['function']['name'], item['function']['parameters'],
                        item['function']['description']) for item in upgrade_tools())
                    identity = _validate_native_receipt(resolved.model, list(OPERATIONS), references)
                    report['native_runtime'] = identity
                    report['capability_receipt_sha256'] = _digest(_read(Path(capability_receipt)))
                report['capability_verified'] = True
                controller = Controller(home, settings['tart'], settings['softnet'])
                runtime = Runtime(controller, {'mortimer': image_id})
                runtime.workspaces = directory / 'workspaces'; runtime.workspaces.mkdir(mode=0o700)
                runtime.source = FrozenLocalSource(report['source_revision'])
                class NonpublishingService(SelfEditService):
                    def submit(self, *args, **kwargs):
                        return {'ok': False, 'error': 'Publication is outside this pilot.'}
                service = NonpublishingService(repo_root=ROOT, github_repo=PROJECT,
                    base_ref=report['source_revision'], runtime_factory=lambda: runtime)
                allocations = OwnedAllocations(runtime, run_id=run_id, source_ref=report['source_revision'],
                                               image_id=image_id, allowed=service._allowed)
                agent = UpgradeAgent(service, profile=profile, run_id=run_id, tool_specs=tools,
                    system_prompt=SYSTEM_PROMPT + '\nPILOT: session_submit is not advertised. Never publish. '
                        'After all installed validation checks pass, report the result and stop.')
                contract = FrozenPlannerGuard(agent, resolved, selected, registry, tools,
                                              native_identity=report.get('native_runtime'))
                report['model_contract_sha256'] = _digest(_canonical({'route': asdict(resolved),
                    'temperature': contract.temperature, 'effort': contract.effort,
                    'tools': tools, 'runtime': report.get('native_runtime')}))
                report['storage_cleanup'] = {'verified': False}
                result, report['storage_cleanup'] = await run_owned_upgrade(agent, case['goal'],
                    DataPolicy('approved_external', 'sha-pinned-public-pilot-case'), directory,
                    status=report['storage_cleanup'])
                if contract.failed:
                    raise DevelopmentPilotUnavailable('pilot_model_contract_changed')
                if contract.verified:
                    report['actual_selection_verified'] = True
                session = allocations.session
                if session is None: raise DevelopmentPilotUnavailable('pilot_session_not_created')
                state = session._read()
                report['source_scanner_verified'] = True
                report['result_policy'] = agent.result_policy.level
                report['agent'] = {'ok': bool(result.get('ok')), 'cancelled': bool(result.get('cancelled')),
                                  'submitted': bool(result.get('submitted')), 'cleanup_unverified': bool(result.get('cleanup_unverified'))}
                if result.get('submitted') or result.get('cleanup_unverified') or not result.get('ok'):
                    raise DevelopmentPilotUnavailable('pilot_agent_did_not_finish_verified')
                files = session._files(state)
                candidate = files.frozen()
                baseline = {file.path: file for file in files.baseline.files}
                current = {file.path: file for file in candidate.files}
                changed = {path for path in set(baseline) | set(current) if baseline.get(path) != current.get(path)}
                if changed != {case['target_path']} or not state.get('proposals'):
                    raise DevelopmentPilotUnavailable('nonempty_exact_target_edit_required')
                receipt = runtime.verifier.receipt(files, image_id, session.profile)
                report['verification'] = {key: receipt[key] for key in ('attempt', 'candidate', 'baseline',
                    'source_commit', 'image', 'profile', 'runner', 'development_task', 'verification_task', 'passed')}
                report['verification']['checks'] = [{key: check[key] for key in ('name', 'passed', 'returncode', 'log_sha256')}
                                                    for check in receipt['checks']]
                report['target_candidate_sha256'] = _digest(current[case['target_path']].data)
                outcomes = _oracle_checks(runtime, session, receipt, case, holdout=holdout)
                report['quality'] = outcomes
                known = outcomes[0]['checks']
                report['known_test_quality_passed'] = not known[0]['passed'] and known[1]['passed']
                report['independent_holdout_verified'] = len(outcomes) == 2 and outcomes[1]['checks'][1]['passed']
                report['substrate_passed'] = report['known_test_quality_passed']
                report['status'] = 'substrate_passed' if report['substrate_passed'] else 'quality_failed'
            if not stores.cleanup_verified:
                raise DevelopmentPilotUnavailable('pilot_storage_cleanup_unverified')
        asyncio.run(execute())
    except BaseException as exc:
        report.update(status='unavailable', reason=exc.code if isinstance(exc, DevelopmentPilotUnavailable) else 'pilot_boundary_refused',
                      error_category=type(exc).__name__, substrate_passed=False)
    finally:
        if runtime is not None:
            try:
                if report.get('storage_cleanup', {}).get('pending_workers', 0):
                    raise DevelopmentPilotUnavailable('pilot_worker_cleanup_pending')
                if session is None:
                    session = allocations.session if allocations is not None else None
                if session is not None:
                    if allocations is None or allocations.identity is None:
                        raise DevelopmentPilotUnavailable('cleanup_identity_unverified')
                    report['cleanup'] = _cleanup(runtime, session, allocations.identity, allocations=allocations)
                    if report['cleanup'].get('verified') is not True:
                        report.update(status='cleanup_unverified', substrate_passed=False,
                                      known_test_quality_passed=False, independent_holdout_verified=False)
                else: report['cleanup'] = {'verified': True, 'owned_tasks': []}
            except BaseException as exc:
                report.update(status='cleanup_unverified', substrate_passed=False,
                              known_test_quality_passed=False, independent_holdout_verified=False,
                              cleanup={'verified': False, 'error_category': type(exc).__name__})
        else:
            report['cleanup'] = {'verified': True, 'owned_tasks': []}
    return report


def run_development_pilot(*, mode='dry', source_ref, image_id, image_home, profile, route,
                          operation_surface='upgrade_nonpublication', capability_receipt=None,
                          external_holdout=None, external_holdout_sha256=None, limits=None):
    """Public live entry: a fresh CLI process owns its routing configuration."""
    if mode not in {'dry', 'live'}:
        raise DevelopmentPilotUnavailable('mode_invalid')
    report = inspect_development_pilot(source_ref=source_ref, image_id=image_id, image_home=image_home,
        profile=profile, route=route, operation_surface=operation_surface)
    if mode == 'dry' or report['status'] == 'unavailable':
        return report
    from jarvis.model_routing import WorkloadLimits, inspect_route_choice
    from sandbox.durable import atomic_json
    limits = WorkloadLimits(deadline_seconds=1800) if limits is None else limits
    if type(limits) is not WorkloadLimits or limits.deadline_seconds is None:
        raise DevelopmentPilotUnavailable('explicit_model_deadline_required')
    home = Path(image_home).resolve(strict=True)
    directory = _owned_directory(home, uuid.uuid4().hex)
    run_id = str(uuid.uuid4())
    request = {'source_ref': report['source_revision'], 'image_id': image_id, 'image_home': str(home),
        'profile': profile, 'route': route, 'operation_surface': operation_surface,
        'capability_receipt': str(capability_receipt) if capability_receipt is not None else None,
        'external_holdout': str(external_holdout) if external_holdout is not None else None,
        'external_holdout_sha256': external_holdout_sha256,
        'limits': {name: getattr(limits, name) for name in ('max_output_tokens_per_call', 'deadline_seconds',
                                                         'max_estimated_spend_usd_per_task')},
        'directory': str(directory), 'run_id': run_id}
    path = directory / 'worker-request.json'
    atomic_json(path, request)
    try:
        tools = upgrade_tools()
        parent_policy, model, access = inspect_route_choice('developer', profile, route)
        parent_contract = {'policy': asdict(parent_policy), 'profile': model,
                           'route': asdict(access), 'tools': tools}
        if _digest(_canonical(parent_contract)) != report['selection_contract_sha256']:
            raise DevelopmentPilotUnavailable('pilot_model_contract_changed')
        # Freeze the original model/endpoint/schema contract. Only the
        # monotonic child restrictions may change the expected policy hash.
        parent_contract = json.loads(_canonical(parent_contract))
        environment = _worker_environment(directory, profile, route, capability_receipt, limits,
                                          parent_policy=parent_policy)
        access_config = json.loads(_read(Path(environment['JARVIS_MODEL_ACCESS_CONFIG'])))
        child_policy, child_model, child_access = inspect_route_choice('developer', profile, route,
            access_config=access_config, registry={'profiles': {profile: parent_contract['profile']}})
        if (child_model != parent_contract['profile'] or asdict(child_access) != asdict(access)
                or any(parent_value is not None and (child_value is None or child_value > parent_value)
                       for name in ('max_output_tokens_per_call', 'deadline_seconds', 'max_estimated_spend_usd_per_task')
                       for parent_value, child_value in [(getattr(parent_policy.limits, name), getattr(child_policy.limits, name))])):
            raise DevelopmentPilotUnavailable('pilot_model_contract_changed')
        parent_contract['policy'] = asdict(child_policy)
        report['selection_contract_sha256'] = _digest(_canonical(parent_contract))
        report['selection']['privacy'] = child_policy.privacy
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--owned-worker', str(path)],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=limits.deadline_seconds + 8400, check=False)
        if len(result.stdout) > 512 * 1024:
            raise DevelopmentPilotUnavailable('pilot_worker_receipt_invalid')
        value = json.loads(result.stdout)
        bound = ('operation_surface', 'source_revision', 'image_id', 'corpus_sha256', 'oracle_sha256',
                 'harness_sha256', 'tool_schema_sha256', 'profile', 'target_baseline_sha256',
                 'source_dependency_sha256', 'image_record_sha256', 'selection', 'selection_contract_sha256')
        if (type(value) is not dict or any(value.get(name) != report[name] for name in bound)
                or value.get('parent_request_id') != run_id or value.get('developer_accepted') is not False
                or value.get('mar_i_complete') is not False
                or (value.get('status') == 'substrate_passed' and value.get('actual_selection_verified') is not True)
                or result.returncode != (0 if value.get('status') == 'substrate_passed' else 2)):
            raise DevelopmentPilotUnavailable('pilot_worker_receipt_invalid')
        return value
    except (OSError, ValueError, subprocess.SubprocessError, DevelopmentPilotUnavailable) as exc:
        return {**report, 'mode': 'live', 'status': 'cleanup_unverified', 'parent_request_id': run_id,
                'reason': exc.code if isinstance(exc, DevelopmentPilotUnavailable) else 'pilot_worker_unverified',
                'substrate_passed': False, 'known_test_quality_passed': False,
                'cleanup': {'verified': False}, 'outcome_unknown': True}


def _worker_main(path):
    """Private fresh-exec entry, with no process environment mutation."""
    from jarvis.model_routing import WorkloadLimits
    value = json.loads(_read(path, limit=64 * 1024))
    fields = {'source_ref', 'image_id', 'image_home', 'profile', 'route', 'operation_surface',
              'capability_receipt', 'external_holdout', 'external_holdout_sha256', 'limits', 'directory', 'run_id'}
    if type(value) is not dict or set(value) != fields or Path(value['directory']) != Path(path).parent:
        raise DevelopmentPilotUnavailable('pilot_worker_request_invalid')
    value['limits'] = WorkloadLimits(**value['limits'])
    report = _run_owned_development_pilot(mode='live', **value)
    print(json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return 0 if report['status'] == 'substrate_passed' else 2


@contextmanager
def _receipt_publication(output):
    """Pin the original parent inode and atomically publish without replace."""
    output = Path(output).absolute()
    permitted = ROOT / 'docs/acceptance/model-use-enhancements/receipts'
    if '..' in output.parts:
        raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
    if output.is_relative_to(permitted):
        anchor = ROOT
    elif output.is_relative_to(Path('/private/tmp')):
        anchor = Path('/private/tmp')
    else:
        raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors, chain = [], []
    temporary = None
    created_identity = None
    file_descriptor = None
    try:
        descriptor = os.open(anchor, flags)
        descriptors.append(descriptor)
        anchor_info = os.fstat(descriptor)
        def directory_identity(info):
            return info.st_dev, info.st_ino, info.st_mode, info.st_uid
        if anchor != Path('/private/tmp') and (anchor_info.st_uid != os.getuid() or anchor_info.st_mode & 0o022):
            raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
        for name in output.parent.relative_to(anchor).parts:
            try:
                os.mkdir(name, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(name, flags, dir_fd=descriptor)
            descriptors.append(child)
            info = os.fstat(child)
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
            chain.append((descriptor, name, directory_identity(info)))
            descriptor = child
        def check_parent():
            if directory_identity(anchor.lstat()) != directory_identity(anchor_info):
                raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
            for parent, name, identity in chain:
                if directory_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity:
                    raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
        check_parent()
        try:
            os.stat(output.name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
        def publish(value):
            nonlocal temporary, file_descriptor, created_identity
            raw = _canonical(value) + b'\n'
            check_parent()
            name = '.mortimer-receipt-' + uuid.uuid4().hex + '.tmp'
            file_descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                      0o600, dir_fd=descriptor)
            temporary = name
            info = os.fstat(file_descriptor)
            created_identity = (info.st_dev, info.st_ino)
            os.fchmod(file_descriptor, 0o600)
            with os.fdopen(file_descriptor, 'wb', closefd=False) as stream:
                stream.write(raw); stream.flush(); os.fsync(file_descriptor)
            info = os.fstat(file_descriptor)
            saved = os.stat(temporary, dir_fd=descriptor, follow_symlinks=False)
            if (_pins(info) != _pins(saved) or info.st_uid != os.getuid() or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != len(raw)):
                raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
            check_parent()
            # link is atomic and refuses every existing final entry,
            # including a dangling symlink. Never unlink the final name.
            os.link(temporary, output.name, src_dir_fd=descriptor, dst_dir_fd=descriptor,
                    follow_symlinks=False)
            os.unlink(temporary, dir_fd=descriptor)
            temporary = None
            os.fsync(descriptor)
            info = os.fstat(file_descriptor)
            final = os.stat(output.name, dir_fd=descriptor, follow_symlinks=False)
            if _pins(info) != _pins(final) or final.st_nlink != 1 or stat.S_IMODE(final.st_mode) != 0o600:
                raise DevelopmentPilotUnavailable('new_owned_receipt_path_required')
            # A completed substitution at the link boundary must not be
            # acknowledged as publication at the originally requested path.
            check_parent()
        yield publish
    except (OSError, ValueError):
        raise DevelopmentPilotUnavailable('new_owned_receipt_path_required') from None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary is not None:
            # Cleanup never follows a replaced parent path or touches output.
            try:
                info = os.stat(temporary, dir_fd=descriptors[-1], follow_symlinks=False)
                if (info.st_dev, info.st_ino) == created_identity:
                    os.unlink(temporary, dir_fd=descriptors[-1])
                    os.fsync(descriptors[-1])
            except FileNotFoundError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if values[:1] == ['--owned-worker']:
        if len(values) != 2:
            raise DevelopmentPilotUnavailable('pilot_worker_request_invalid')
        return _worker_main(Path(values[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('dry', 'live'), default='dry')
    parser.add_argument('--operation-surface', choices=('upgrade_nonpublication', 'developer_full_registry'), default='upgrade_nonpublication')
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--image-home', type=Path, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--route', required=True)
    parser.add_argument('--capability-receipt', type=Path)
    parser.add_argument('--external-holdout', type=Path)
    parser.add_argument('--external-holdout-sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output
    values = vars(args); values.pop('output')
    try:
        with _receipt_publication(output) as publish:
            try: report = run_development_pilot(**values)
            except BaseException as exc:
                report = {'status': 'unavailable', 'reason': exc.code if isinstance(exc, DevelopmentPilotUnavailable) else 'pilot_boundary_refused',
                          'error_category': type(exc).__name__, 'developer_accepted': False, 'mar_i_complete': False}
            publish(report)
    except DevelopmentPilotUnavailable:
        parser.exit(2, 'new_owned_receipt_path_required\n')
    return 0 if report.get('status') in {'dry_ready_unverified', 'substrate_passed'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
