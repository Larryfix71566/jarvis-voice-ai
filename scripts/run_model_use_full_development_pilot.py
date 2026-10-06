#!/usr/bin/env python3
"""WS-05 full Developer acceptance through the installed forty-tool path.

Dry by default. Live work enters a fresh CLI process, not the production bot.
The actual SkillRegistry, SubAgent, authenticated sidecar, GitSource, Runtime,
Session and twelve-check verifier remain the execution path. This bounded
public case never publishes and never executes a private capability. Offline
unit transports are separate evidence, never a live acceptance receipt.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager, closing, contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SERVERS = ('mcp-git', 'mcp-repo', 'mcp-selfedit', 'mcp-runlog', 'mcp-screen', 'mcp-status')
PROJECT = 'Larryfix71566/jarvis-voice-ai'
ALLOWED_TOOLS = frozenset({'repo_read_file', 'selfedit_read', 'selfedit_write', 'selfedit_status'})
HTTP_ROUTES = frozenset({
    ('POST', '/api/skills/runtime/inventory'),
    ('POST', '/api/selfedit/stage'), ('POST', '/api/selfedit/run'),
    ('GET', '/api/selfedit/status'), ('GET', '/api/selfedit/file'),
    ('POST', '/api/selfedit/write'),
    ('POST', '/api/development/source/associate'),
    ('POST', '/api/development/source/prepare'),
    ('POST', '/api/development/source/tool'),
})


class FullPilotUnavailable(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def support():
    """Use reviewed shared corpus/guest oracle helpers, never its source shim."""
    from scripts import run_model_use_development_pilot as helper
    return helper


def _require_committed_support():
    helper = support()
    paths = ('scripts/run_model_use_development_pilot.py', 'scripts/model_use_development_oracle.py',
             'tests/fixtures/model_use_development_cases.json')
    for relative in paths:
        try:
            committed = subprocess.check_output(
                ['git', '--no-optional-locks', '-C', str(ROOT), 'show', 'HEAD:' + relative],
                stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise FullPilotUnavailable('reviewed_support_not_committed') from None
        if committed != helper._read(ROOT / relative):
            raise FullPilotUnavailable('reviewed_support_changed')
    return {relative: digest(helper._read(ROOT / relative)) for relative in paths}


def selection_contract(profile, route, *, policy_path=None):
    """Inspect one concrete policy, including its exact effective task limits."""
    from jarvis.model_routing import inspect_route_choice
    policy, model, access = inspect_route_choice('developer', profile, route, policy_path=policy_path)
    record = {'policy': asdict(policy), 'model': model, 'route': asdict(access)}
    return record, digest(canonical(record))


def inspect_full_pilot(*, source_ref, source_branch, image_id, image_home, profile, route):
    helper = support()
    case = helper.load_corpus()
    report = helper.inspect_development_pilot(source_ref=source_ref, image_id=image_id,
        image_home=image_home, profile=profile, route=route)
    report.update(version='model-use-full-development-pilot-v1',
                  operation_surface='developer_full_registry',
                  harness_sha256=digest(helper._read(Path(__file__))),
                  source_branch=source_branch, developer_accepted=False, mar_i_complete=False,
                  full_developer_passed=False, publication_allowed=False,
                  origin='actual_owned_cli_runtime', production_bot_session=False,
                  limitations=['this public nonpublication case does not certify private tools or account allowance',
                               'full live forty-schema native receipt is required for subscription execution',
                               'independent external holdout and all twelve checks are mandatory'])
    report.pop('tool_names', None)
    report.pop('tool_schema_sha256', None)
    report.pop('substrate_passed', None)
    report.pop('selection_contract_sha256', None)
    contract, report['selection_contract_sha256'] = selection_contract(profile, route)
    report['effective_limits'] = contract['policy']['limits']
    if (not isinstance(source_branch, str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.-]{0,180}', source_branch)
            or '..' in source_branch or '//' in source_branch
            or source_branch.endswith(('/', '.', '.lock'))
            or any(part.startswith('.') for part in source_branch.split('/'))):
        raise FullPilotUnavailable('remote_source_branch_required')
    report['target_path'] = case['target_path']
    report['status'] = 'dry_ready_unverified'
    return report


def read_service_principal(auth_db, token):
    """Read the actual existing service principal without touching last_used."""
    from jarvis.auth import hash_token, parse_bearer
    from jarvis.tenant import is_valid_user_id
    if parse_bearer('Bearer ' + (token or '')) != token:
        raise FullPilotUnavailable('existing_service_token_required')
    path = Path(auth_db).resolve(strict=True)
    if not path.is_file():
        raise FullPilotUnavailable('service_identity_unverified')
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.25)) as connection:
            connection.execute('PRAGMA query_only=ON')
            rows = list(connection.execute(
                'SELECT name,user_id FROM client_tokens WHERE token_hash=? AND revoked_at IS NULL',
                (hash_token(token),)))
    except sqlite3.Error:
        raise FullPilotUnavailable('service_identity_unverified') from None
    if len(rows) != 1 or rows[0][0] != 'service-bot' or not is_valid_user_id(rows[0][1]):
        raise FullPilotUnavailable('service_identity_unverified')
    return rows[0][1]


def seed_private_principal(directory, token, owner):
    """Copy only the proven principal hash into a new private store; mint nothing."""
    from jarvis.auth import hash_token
    from jarvis.db import get_conn, now_iso, run_migrations
    path = directory / 'pilot.db'
    if path.exists():
        raise FullPilotUnavailable('new_private_auth_store_required')
    with closing(get_conn()) as connection:
        run_migrations(connection)
        connection.execute('INSERT INTO client_tokens(user_id,name,token_hash,created_at) VALUES(?,?,?,?)',
                           (owner, 'service-bot', hash_token(token), now_iso()))
        connection.commit()


class NonpublicationHTTP:
    """A task-local narrowing outside the unmodified authenticated admin app."""
    def __init__(self, app, case, run_id):
        self.app, self.case, self.run_id = app, case, run_id

    async def __call__(self, scope, receive, send):
        refused = scope['type'] == 'http' and (scope['method'], scope['path']) not in HTTP_ROUTES
        original_receive = receive
        if scope['type'] == 'http' and scope['method'] == 'POST' and not refused:
            chunks, complete, size = [], False, 0
            while not complete:
                chunk = await receive()
                chunks.append(chunk)
                size += len(chunk.get('body', b''))
                complete = not chunk.get('more_body', False)
                if chunk['type'] != 'http.request' or size > 2 * 1024 * 1024:
                    refused = True
                    break
            try:
                value = json.loads(b''.join(item.get('body', b'') for item in chunks))
                path = scope['path']
                if path.startswith('/api/development/source/'):
                    refused = (value.get('tool_name') not in {'selfedit_read', 'selfedit_write', 'selfedit_status'}
                        or value.get('developer_run_id') != self.run_id)
                elif path == '/api/selfedit/stage':
                    refused = (value.get('goal') != self.case['goal'] or value.get('run_id') != self.run_id
                               or value.get('target_paths') != [self.case['target_path']])
                elif path == '/api/selfedit/run':
                    refused = set(value) != {'staging_id', 'author'} or value.get('author') is not True
                elif path == '/api/selfedit/write':
                    refused = value.get('path') != self.case['target_path']
            except (ValueError, TypeError, AttributeError):
                refused = True
            replay = iter(chunks)
            async def receive():
                try:
                    return next(replay)
                except StopIteration:
                    return await original_receive()
        if refused:
            raw = b'{"ok":false,"error":"outside_public_pilot"}'
            await send({'type': 'http.response.start', 'status': 403,
                        'headers': [(b'content-type', b'application/json')]})
            await send({'type': 'http.response.body', 'body': raw})
            return
        await self.app(scope, receive, send)


@asynccontextmanager
async def private_admin(service, case, run_id):
    """Run actual HTTP/auth handlers; import-time probes must already be off."""
    import httpx
    import uvicorn
    from jarvis.admin import server as admin
    if (os.environ.get('JARVIS_AUTH_ENABLED') != 'true'
            or os.environ.get('JARVIS_KEY_HEALTH_ENABLED') != 'false'
            or os.environ.get('JARVIS_REMINDER_NOTIFICATIONS_ENABLED') != 'false'):
        raise FullPilotUnavailable('owned_admin_environment_required')
    # The constructor at module import has not adopted any Runtime. Never
    # query it: status() would resolve production's global workspace records.
    if admin._selfedit_service._installed_runtime is not None:
        raise FullPilotUnavailable('foreign_workspace_detected')
    admin._selfedit_service = service
    tracker = AuthoringWorkers(admin)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    actual = uvicorn.Server(uvicorn.Config(NonpublicationHTTP(admin.app, case, run_id), log_level='critical',
        access_log=False, lifespan='off'))
    worker = asyncio.create_task(actual.serve(sockets=[sock]))
    deadline = asyncio.get_running_loop().time() + 10
    try:
        while not actual.started:
            if worker.done() or asyncio.get_running_loop().time() >= deadline:
                raise FullPilotUnavailable('private_admin_not_started')
            await asyncio.sleep(.025)
        # This mutation is in the single fresh owned process, before MCP spawn.
        os.environ['JARVIS_ADMIN_URL'] = 'http://127.0.0.1:' + str(port)
        from jarvis.auth import service_headers
        async with httpx.AsyncClient(base_url=os.environ['JARVIS_ADMIN_URL'],
                headers=service_headers(), trust_env=False, follow_redirects=False, timeout=30) as client:
            denied = await client.get('/api/selfedit/status', headers={'Authorization': ''})
            if denied.status_code != 401:
                raise FullPilotUnavailable('actual_bearer_auth_not_enforced')
            yield client, admin, tracker
    finally:
        actual.should_exit = True
        try:
            await asyncio.wait_for(asyncio.shield(worker), 10)
            tracker.transport_cleanup = True
        except BaseException:
            actual.force_exit = True
            raise FullPilotUnavailable('private_admin_cleanup_unverified') from None
        finally:
            sock.close()


class AuthoringWorkers:
    """Retain the actual background target beyond its job-slot state."""
    def __init__(self, admin):
        self.admin, self.events = admin, []
        self.transport_cleanup = False
        original = admin._source_worker_target
        def target(operation):
            installed = original(operation)
            done = threading.Event()
            self.events.append(done)  # before Thread.start, not after entry
            def run(*args, **kwargs):
                try:
                    return installed(*args, **kwargs)
                finally:
                    done.set()
            return run
        admin._source_worker_target = target

    async def drain(self, timeout=20):
        with self.admin._opening_lock:
            if self.admin._opening_job.get('state') == 'starting':
                self.admin._opening_job['cancel_requested'] = True
        deadline = asyncio.get_running_loop().time() + timeout
        while not all(event.is_set() for event in self.events):
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(.05)
        return True


class RealSourcePin:
    """Observe the real GitSource fetch; refuse remote drift before allocation."""
    def __init__(self, runtime, branch, revision):
        self.root = None
        original = runtime.source.fetch
        def fetch(repository, actual_branch, token):
            if repository != PROJECT or actual_branch != branch:
                raise FullPilotUnavailable('remote_source_binding_changed')
            root, ref = original(repository, actual_branch, token)
            if ref != revision:
                raise FullPilotUnavailable('remote_source_revision_changed')
            root = Path(root).resolve(strict=True)
            if self.root is not None and self.root != root:
                raise FullPilotUnavailable('remote_source_binding_changed')
            self.root = root
            return root, ref
        runtime.source.fetch = fetch


class Allocations:
    """Pin only IDs returned by the actual allocator, including partial create."""
    def __init__(self, runtime, source, run_id, revision, image_id, allowed, evidence_directory):
        helper = support()
        self.runtime, self.tasks, self.session, self.identity = runtime, {}, None, None
        def save_evidence():
            from sandbox.durable import atomic_json
            atomic_json(evidence_directory / 'full-allocations.json', {
                'schema_version': 1, 'run_id': run_id, 'source_ref': revision, 'image_id': image_id,
                'session_id': self.session.id if self.session is not None else None,
                'identity': list(self.identity) if self.identity is not None else None,
                'tasks': {task: asdict(proof) if proof is not None else None
                          for task, proof in self.tasks.items()}})
        original = runtime.images.create
        def create(image, repo, ref, profile, *, purpose='development', candidate=None,
                   task_id=None, parent_task=None):
            from sandbox.profiles import MORTIMER
            if (source.root is None or Path(repo).resolve() != source.root or ref != revision
                    or image != image_id or profile is not MORTIMER):
                raise FullPilotUnavailable('allocation_source_changed')
            if purpose == 'development':
                if self.session is not None or parent_task is not None or candidate is not None or task_id is None:
                    raise FullPilotUnavailable('allocation_owner_changed')
                session = runtime.active(PROJECT, 'selfedit', allowed)
                state = session._read() if session is not None else {}
                if (state.get('run_id') != run_id or state.get('task') != task_id
                        or state.get('ref') != revision or state.get('image') != image_id):
                    raise FullPilotUnavailable('allocation_owner_changed')
                self.session = session
                self.identity = tuple(state.get(key) for key in helper._SESSION_KEYS)
            elif (purpose != 'verification' or self.identity is None
                  or parent_task != self.identity[1] or candidate is None):
                raise FullPilotUnavailable('allocation_owner_changed')
            task_id = task_id or uuid.uuid4().hex[:12]
            if task_id in self.tasks or (runtime.controller.home / 'tasks' / task_id).exists():
                raise FullPilotUnavailable('allocation_identity_reused')
            self.tasks[task_id] = None
            save_evidence()
            try:
                return original(image, repo, ref, profile, purpose=purpose, candidate=candidate,
                                task_id=task_id, parent_task=parent_task)
            finally:
                if (runtime.controller.task_dir(task_id) / 'state.json').exists():
                    proof = helper._task_generation(runtime.controller, task_id)
                    row = dict(zip(helper._TASK_KEYS, proof.fields))
                    if (row.get('image') != image or row.get('purpose') != purpose
                            or row.get('parent_task') != parent_task or row.get('profile') != profile.name
                            or row.get('source_commit') not in {None, ref}
                            or (candidate is not None and row.get('candidate') not in {None, candidate.fingerprint})):
                        raise FullPilotUnavailable('allocation_owner_changed')
                    self.tasks[task_id] = proof
                    save_evidence()
        runtime.images.create = create
        controller = runtime.controller
        original_read = controller.read
        def read(task):
            if helper._mutation_task.get() == task:
                row = json.loads(helper._read(controller.task_dir(task) / 'state.json'))
                self.require(task, row=row)
                return row
            return original_read(task)
        controller.read = read
        for name in ('start', 'stop', 'destroy', 'cancel'):
            method = getattr(controller, name)
            def mutation(task, *args, _method=method, _name=name, **kwargs):
                self.require(task)
                handle = helper._mutation_task.set(task)
                try:
                    result = _method(task, *args, **kwargs)
                    if _name == 'start':
                        helper._wait_boot(controller, task, lambda: self.require(task))
                    return result
                finally:
                    helper._mutation_task.reset(handle)
            setattr(controller, name, mutation)

    def require(self, task, *, row=None):
        helper = support()
        proof = self.tasks.get(task)
        if proof is None or helper._task_generation(self.runtime.controller, task, row=row) != proof:
            raise FullPilotUnavailable('allocation_owner_changed')
        return proof


class PilotToolGuard:
    """Keep all discovered schemas; deny unrelated operations before MCP ingress."""
    def __init__(self, registry, case, contract_check, baseline_sha256):
        self.executed = []
        original = registry._call
        async def call(tool, arguments, server_names=None, *, execution_scope=None, **kwargs):
            from jarvis.privacy_policy import issue_tool_result
            contract_check()
            allowed = tool in ALLOWED_TOOLS
            if tool in {'repo_read_file', 'selfedit_read', 'selfedit_write'}:
                allowed = allowed and arguments.get('path') == case['target_path']
            if tool == 'repo_read_file' and allowed:
                allowed = digest(support()._read(ROOT / case['target_path'])) == baseline_sha256
            elif tool == 'selfedit_status':
                allowed = allowed and not any(arguments.values())
            if not allowed:
                if execution_scope is None:
                    raise FullPilotUnavailable('classified_tool_scope_required')
                return issue_tool_result(execution_scope, '{"error":"outside_public_pilot","ok":false}',
                                         execution_scope.input_policy, 'host-generated-pilot-refusal')
            value = await original(tool, arguments, server_names, execution_scope=execution_scope, **kwargs)
            self.executed.append(tool)
            return value
        registry._call = call


class ModelContract:
    """Check actual per-run routes and SDK requests; never replace a provider."""
    def __init__(self, agent, registry, resolved, schemas, expected_policy,
                 expected_selection, policy_sha256, native_identity=None):
        helper = support()
        self.failed = False
        self.resolved = resolved
        self.schemas = helper._canonical(schemas)
        self.registry = registry
        from jarvis.agents.upgrade_agent import load_model_registry
        self.models = helper._canonical(load_model_registry())
        self.environment = dict(os.environ)
        self.native_identity = native_identity
        self.expected_policy = expected_policy
        self.expected_selection = expected_selection
        self.policy_path = Path(os.environ['JARVIS_MODEL_ACCESS_CONFIG'])
        self.policy_sha256 = policy_sha256
        if asdict(resolved.limits) != expected_policy['limits']:
            self.refuse()
        self.wrapped_clients = set()
        original_route = agent._routed_client_for
        original_execution = agent._execution_client
        original_loop = agent._loop
        def routed(route):
            self.check()
            if route != resolved:
                self.refuse()
            return original_route(route)
        def execution(client):
            self.check()
            result = original_execution(client)
            if id(result) not in self.wrapped_clients:
                original_create = result.chat.completions.create
                async def create(**kwargs):
                    self.check()
                    if (kwargs.get('model') != resolved.model
                            or helper._canonical(kwargs.get('tools')) != self.schemas):
                        self.refuse()
                    return await original_create(**kwargs)
                result.chat.completions.create = create
                self.wrapped_clients.add(id(result))
            return result
        async def loop(*args, **kwargs):
            self.check()
            if kwargs.get('resolved_route') != resolved or kwargs.get('model') != resolved.model:
                self.refuse()
            return await original_loop(*args, **kwargs)
        agent._routed_client_for = routed
        agent._execution_client = execution
        agent._loop = loop

    def refuse(self):
        from jarvis.model_routing import ModelRouteError
        self.failed = True
        raise ModelRouteError('full_pilot_model_contract_changed')

    def check(self):
        helper = support()
        from jarvis.agents.upgrade_agent import load_model_registry
        try:
            actual = helper.inspect_live_developer_registry(self.registry)
            if (helper._canonical(self.registry.openai_tools(list(SERVERS))) != self.schemas
                    or helper._canonical(load_model_registry()) != self.models
                    or os.environ != self.environment
                    or digest(helper._read(self.policy_path)) != self.policy_sha256):
                raise ValueError()
            policy, selected = selection_contract(self.resolved.profile_name, self.resolved.route.name,
                                                  policy_path=self.policy_path)
            if policy['policy'] != self.expected_policy or selected != self.expected_selection:
                raise ValueError()
            if self.native_identity is not None:
                from jarvis.model_execution import ModelToolReference
                from jarvis.subscription_tools import _validate_native_receipt
                schemas = json.loads(self.schemas)
                references = tuple(ModelToolReference(item['function']['name'], item['function']['parameters'],
                    item['function']['description']) for item in schemas)
                identity = _validate_native_receipt(self.resolved.model, actual['declared_tool_names'], references)
                if canonical(identity) != canonical(self.native_identity):
                    raise ValueError()
        except Exception:
            self.refuse()


async def post_ok(client, path, body):
    response = await client.post(path, json=body)
    if response.status_code != 200:
        raise FullPilotUnavailable('authenticated_admin_request_refused')
    value = response.json()
    if value.get('ok') is not True:
        raise FullPilotUnavailable('authenticated_admin_operation_refused')
    return value


async def inventory_loop(client, session_id, owner, tools, stop):
    while not stop.is_set():
        await post_ok(client, '/api/skills/runtime/inventory', {'schema_version': 1,
            'runtime_id': session_id, 'owner_id': owner, 'tools': tools, 'complete': True, 'active': True})
        try:
            await asyncio.wait_for(stop.wait(), 10)
        except asyncio.TimeoutError:
            pass


@contextmanager
def owned_cli_turn():
    """Own the normal CLI privacy holder without clearing inherited protection."""
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    holder = current_sensitive_turn.get()
    if holder is None:
        holder = SensitiveTurn()
    token = current_sensitive_turn.set(holder)
    try:
        yield holder
    finally:
        current_sensitive_turn.reset(token)


async def full_owned_worker(request):
    with owned_cli_turn():
        return await _full_owned_worker(request)


async def _full_owned_worker(request):
    helper = support()
    validate_worker_request(request)
    directory = Path(request['directory'])
    report = inspect_full_pilot(**{name: request[name] for name in
        ('source_ref', 'source_branch', 'image_id', 'image_home', 'profile', 'route')})
    report.update(mode='live', status='unavailable', parent_request_id=request['run_id'],
                  cleanup={'verified': False}, private_transport_cleanup=False)
    if report['selection_contract_sha256'] != request['selection_contract_sha256']:
        raise FullPilotUnavailable('parent_selection_contract_changed')
    if digest(helper._read(Path(os.environ['JARVIS_MODEL_ACCESS_CONFIG']))) != request['policy_sha256']:
        raise FullPilotUnavailable('child_policy_contract_changed')
    report['support_source_sha256'] = _require_committed_support()
    case = helper.load_corpus()
    holdout = helper._holdout_snapshot(request['external_holdout'], request['external_holdout_sha256'], case)
    if holdout is None:
        raise FullPilotUnavailable('independent_holdout_required')
    from jarvis.storage_context import storage_scope, state_to_thread
    from jarvis.config import load_settings
    from jarvis.selfedit.service import SelfEditService
    from jarvis.skills.registry import SkillRegistry
    from jarvis.agents.base import load_sub_agents
    from jarvis.model_routing import resolve_model_route_checked
    from sandbox.control import Controller
    from sandbox.runtime import Runtime
    from sandbox.source import GitSource
    home = Path(request['image_home']).resolve(strict=True)
    settings = json.loads(helper._read(home / 'settings.json'))
    from jarvis.vault import inject_env
    inject_env()  # fresh process only; never print or pass these keys to a guest
    token = os.environ.get('JARVIS_SERVICE_TOKEN', '')
    owner = read_service_principal(request['service_auth_db'], token)
    runtime = registry = allocations = tracker = admin = stores = None
    session_id = str(uuid.uuid4())
    report.update(session_id=session_id, owner_id=owner,
                  heldout_input={'sha256': holdout.sha256, 'prepared_before_model': True,
                                 'outside_developer_source': True, 'model_input_contains_holdout': False})
    try:
        async with storage_scope(db_path=directory / 'pilot.db', costs_db_path=directory / 'costs.db',
                                 model_preferences_enabled=False) as stores:
            seed_private_principal(directory, token, owner)
            controller = Controller(home, settings['tart'], settings['softnet'])
            runtime = Runtime(controller, {'mortimer': request['image_id']})
            runtime.workspaces = directory / 'workspaces'
            runtime.workspaces.mkdir(mode=0o700)
            runtime.source = GitSource(directory)
            source = RealSourcePin(runtime, request['source_branch'], report['source_revision'])
            service = SelfEditService(repo_root=ROOT, github_repo=PROJECT,
                github_token=os.environ.get('JARVIS_GITHUB_TOKEN'), base_ref=request['source_branch'],
                runtime_factory=lambda: runtime)
            allocations = Allocations(runtime, source, request['run_id'], report['source_revision'],
                                      request['image_id'], service._allowed, directory)
            async with private_admin(service, case, request['run_id']) as (client, admin, tracker):
                import yaml
                data = yaml.safe_load(helper._read(ROOT / 'config/mcp_servers.yaml'))
                configured = [entry for entry in data['servers'] if entry['name'] in SERVERS]
                config = directory / 'mcp-developer.json'
                config.write_bytes(canonical({'servers': configured}))
                config.chmod(0o600)
                registry = SkillRegistry(config)
                await registry.start()
                try:
                    discovered = helper.inspect_live_developer_registry(registry)
                    schemas = registry.openai_tools(list(SERVERS))
                    report['full_registry'] = discovered
                    from sandbox.durable import atomic_json
                    registry_evidence = {'schema_version': 1, 'servers': list(SERVERS), 'schemas': schemas,
                                         'declaration_source_sha256': discovered['declaration_source_sha256']}
                    atomic_json(directory / 'full-registry.json', registry_evidence)
                    report['registry_evidence_sha256'] = digest(helper._read(directory / 'full-registry.json'))
                    resolved = resolve_model_route_checked('developer', explicit_profile=request['profile'],
                                                           explicit_route=request['route'])
                    native_identity = None
                    if resolved.route.adapter.endswith('subscription_runtime'):
                        if resolved.route.adapter != 'subscription_runtime':
                            raise FullPilotUnavailable('native_full_developer_unsupported')
                        from jarvis.model_execution import ModelToolReference
                        from jarvis.subscription_tools import _validate_native_receipt
                        refs = tuple(ModelToolReference(item['function']['name'], item['function']['parameters'],
                            item['function']['description']) for item in schemas)
                        native_identity = _validate_native_receipt(resolved.model,
                            discovered['declared_tool_names'], refs)
                        report['native_runtime'] = native_identity
                        report['capability_receipt_sha256'] = digest(helper._read(Path(request['capability_receipt'])))
                    settings_obj = load_settings(env_file=None)
                    if not settings_obj.jarvis_runlog_enabled:
                        raise FullPilotUnavailable('actual_run_logging_required')
                    agent = load_sub_agents(settings_obj, registry)['developer']
                    guard = ModelContract(agent, registry, resolved, schemas, request['effective_policy'],
                                          request['selection_contract_sha256'], request['policy_sha256'], native_identity)
                    model_evidence = {'route': asdict(resolved), 'schemas': schemas, 'runtime': native_identity}
                    atomic_json(directory / 'full-model-contract.json', model_evidence)
                    tools = PilotToolGuard(registry, case, guard.check, report['target_baseline_sha256'])
                    stop = asyncio.Event()
                    names = [item['function']['name'] for item in schemas]
                    heartbeat = asyncio.create_task(inventory_loop(client, session_id, owner, names, stop))
                    async def associated(actual_run):
                        if actual_run != request['run_id']:
                            raise FullPilotUnavailable('actual_run_identity_changed')
                        # Real authenticated runtime evidence comes from this actual live registry.
                        await post_ok(client, '/api/skills/runtime/inventory', {'schema_version': 1,
                            'runtime_id': session_id, 'owner_id': owner, 'tools': names,
                            'complete': True, 'active': True})
                        staged = await post_ok(client, '/api/selfedit/stage', {'goal': case['goal'],
                            'run_id': actual_run, 'target_paths': [case['target_path']]})
                        await post_ok(client, '/api/selfedit/run', {'staging_id': staged['staging_id'], 'author': True})
                        deadline = asyncio.get_running_loop().time() + min(240, agent._timeout_s)
                        while asyncio.get_running_loop().time() < deadline:
                            value = (await client.get('/api/selfedit/status')).json()
                            if value.get('active') and value.get('ready'):
                                if value.get('run_id') != actual_run or value.get('ref') != report['source_revision']:
                                    raise FullPilotUnavailable('actual_workspace_identity_changed')
                                return True
                            if admin._opening_job.get('state') == 'error':
                                raise FullPilotUnavailable('actual_workspace_setup_failed')
                            await asyncio.sleep(.1)
                        raise FullPilotUnavailable('actual_workspace_setup_deadline')
                    try:
                        from jarvis.tenant import user_id_scope
                        task = case['goal'] + ('\nThe approved host preview is already staged and opens the sandbox '
                            'before this run starts. Use selfedit_read and selfedit_write for the named file. '
                            'Stop after writing; the host will run all twelve installed checks. '
                            'Do not call selfedit_finish, publication, planning, git, screen, status or runlog tools.')
                        from jarvis.bot.sensitive_turn import arm_from_text
                        arm_from_text(task, request['run_id'])
                        with user_id_scope(owner):
                            reply = await agent.run(task, run_id=request['run_id'], session_id=session_id,
                                                    on_run_created=associated)
                        guard.check()
                        if heartbeat.done() and heartbeat.exception() is not None:
                            raise FullPilotUnavailable('actual_runtime_inventory_failed')
                        if guard.failed or reply.startswith(('FAILED:', 'REFUSED:')):
                            raise FullPilotUnavailable('actual_developer_run_failed')
                        from jarvis.runlog.store import get_run
                        detail = get_run(request['run_id'])
                        row = detail.get('run') if isinstance(detail, dict) else None
                        if (not isinstance(row, dict) or row.get('agent') != 'developer'
                                or row.get('run_id') != request['run_id'] or row.get('session_id') != session_id
                                or row.get('user_id') != owner or row.get('model') != resolved.model
                                or row.get('status') != 'ok' or detail.get('unresolved_tool_calls')):
                            raise FullPilotUnavailable('actual_finished_developer_record_required')
                        report['actual_run'] = {key: row.get(key) for key in
                                               ('run_id', 'session_id', 'agent', 'user_id', 'model', 'status')}
                        if 'selfedit_read' not in tools.executed or 'selfedit_write' not in tools.executed:
                            raise FullPilotUnavailable('actual_developer_edit_required')
                        report['tool_execution'] = tools.executed
                        report['actual_selection_verified'] = True
                        report['model_contract_sha256'] = digest(canonical({'route': asdict(resolved), 'schemas': schemas,
                                                                          'runtime': native_identity}))
                        session = allocations.session
                        if session is None:
                            raise FullPilotUnavailable('actual_session_required')
                        state = session._read()
                        files = session._files(state)
                        candidate = files.frozen()
                        baseline = {file.path: file for file in files.baseline.files}
                        changed = {file.path for file in candidate.files if baseline.get(file.path) != file}
                        if changed != {case['target_path']} or not state.get('proposals'):
                            raise FullPilotUnavailable('nonempty_exact_target_edit_required')
                        report['target_candidate_sha256'] = digest(next(
                            file.data for file in candidate.files if file.path == case['target_path']))
                        checked = await state_to_thread(service.validate)
                        if checked.get('ok') is not True:
                            raise FullPilotUnavailable('full_twelve_validation_failed')
                        receipt = runtime.verifier.receipt(files, request['image_id'], session.profile)
                        required = [name for name, _ in session.profile.checks]
                        if (len(required) != 12 or [item['name'] for item in receipt['checks']] != required
                                or not receipt['passed']):
                            raise FullPilotUnavailable('full_twelve_validation_required')
                        report['verification'] = {key: receipt[key] for key in ('attempt', 'candidate', 'baseline',
                            'source_commit', 'image', 'profile', 'runner', 'development_task', 'verification_task', 'passed')}
                        report['verification']['checks'] = [{key: check[key] for key in
                            ('name', 'passed', 'returncode', 'log_sha256')} for check in receipt['checks']]
                        quality = await state_to_thread(helper._oracle_checks, runtime, session, receipt, case, holdout=holdout)
                        report['quality'] = quality
                        passed = (not quality[0]['checks'][0]['passed'] and quality[0]['checks'][1]['passed']
                                  and not quality[1]['checks'][0]['passed'] and quality[1]['checks'][1]['passed'])
                        report.update(full_developer_passed=passed, independent_holdout_verified=passed,
                                      status='full_developer_passed' if passed else 'quality_failed')
                    finally:
                        stop.set()
                        await heartbeat
                        await post_ok(client, '/api/skills/runtime/inventory', {'schema_version': 1,
                            'runtime_id': session_id, 'owner_id': owner, 'tools': names,
                            'complete': True, 'active': False})
                finally:
                    await registry.stop()
                    report['registry_cleanup'] = True
            report['private_transport_cleanup'] = True
            # Admin's real asynchronous setup thread must settle before stores are retired.
            if not await tracker.drain():
                raise FullPilotUnavailable('actual_workspace_worker_pending')
            if allocations.session is not None:
                report['cleanup'] = await state_to_thread(helper._cleanup, runtime, allocations.session,
                                                         allocations.identity, allocations=allocations)
            else:
                report['cleanup'] = {'verified': not allocations.tasks, 'owned_tasks': list(allocations.tasks)}
        if not stores.cleanup_verified or report['cleanup'].get('verified') is not True:
            raise FullPilotUnavailable('owned_cleanup_unverified')
    except BaseException as exc:
        report.update(status='unavailable', reason=getattr(exc, 'code', 'full_pilot_boundary_refused'),
                      error_category=type(exc).__name__, full_developer_passed=False,
                      independent_holdout_verified=False)
    finally:
        # A failure does not make an allocated VM or real setup thread cease
        # to exist. Drain the retained target first, then pin real teardown.
        workers_done = tracker is None or await tracker.drain()
        storage_done = stores is None or stores.cleanup_verified
        if tracker is not None:
            report['private_transport_cleanup'] = (
                tracker.transport_cleanup and report.get('registry_cleanup') is True)
        if runtime is not None and allocations is not None and workers_done and storage_done:
            try:
                if allocations.session is not None and report['cleanup'].get('verified') is not True:
                    report['cleanup'] = helper._cleanup(runtime, allocations.session, allocations.identity,
                                                        allocations=allocations)
                elif allocations.session is None:
                    report['cleanup'] = {'verified': not allocations.tasks, 'owned_tasks': list(allocations.tasks)}
            except BaseException as exc:
                report['cleanup'] = {'verified': False, 'error_category': type(exc).__name__}
        elif runtime is None:
            report['cleanup'] = {'verified': workers_done and storage_done, 'owned_tasks': []}
        if (not workers_done or not storage_done or report['cleanup'].get('verified') is not True
                or report['private_transport_cleanup'] is not True):
            report.update(status='cleanup_unverified', full_developer_passed=False,
                          independent_holdout_verified=False)
    # This per-case result never closes the whole MAR-I workload/rollout checklist.
    report.update(developer_accepted=False, mar_i_complete=False)
    return report


def worker_environment(directory, profile, route, capability_receipt, limits):
    helper = support()
    environment = helper._worker_environment(directory, profile, route, capability_receipt, limits)
    environment.update(JARVIS_DB_PATH=str(directory / 'pilot.db'), JARVIS_COSTS_DB=str(directory / 'costs.db'),
        JARVIS_MODEL_PREFERENCES_ENABLED='0', JARVIS_AUTH_ENABLED='true',
        JARVIS_KEY_HEALTH_ENABLED='false', JARVIS_REMINDER_NOTIFICATIONS_ENABLED='false',
        JARVIS_SCREEN_ENABLED='false', JARVIS_ENV_SCOPING_ENABLED='true',
        MORTIMER_SANDBOX_HOME=str(directory))
    return environment


def validate_worker_request(request):
    fields = {'source_ref', 'source_branch', 'image_id', 'image_home', 'profile', 'route',
              'service_auth_db', 'capability_receipt', 'external_holdout', 'external_holdout_sha256',
              'directory', 'run_id', 'selection_contract_sha256', 'policy_sha256'}
    fields.add('effective_policy')
    if type(request) is not dict or set(request) != fields:
        raise FullPilotUnavailable('worker_request_invalid')
    try:
        directory = Path(request['directory'])
        home = Path(request['image_home']).resolve(strict=True)
        if (directory.parent != home / 'pilots' or directory.is_symlink()
                or not re.fullmatch(r'[0-9a-f]{32}', directory.name)
                or str(uuid.UUID(request['run_id'])) != request['run_id']
                or any(not re.fullmatch(r'[0-9a-f]{64}', request[name] or '') for name in
                       ('image_id', 'external_holdout_sha256', 'selection_contract_sha256', 'policy_sha256'))
                or os.environ.get('JARVIS_DB_PATH') != str(directory / 'pilot.db')
                or os.environ.get('JARVIS_COSTS_DB') != str(directory / 'costs.db')
                or os.environ.get('MORTIMER_SANDBOX_HOME') != str(directory)
                or os.environ.get('JARVIS_MODEL_ROUTING_ENABLED') != '1'
                or os.environ.get('JARVIS_AUTH_ENABLED') != 'true'
                or os.environ.get('JARVIS_KEY_HEALTH_ENABLED') != 'false'
                or os.environ.get('JARVIS_REMINDER_NOTIFICATIONS_ENABLED') != 'false'
                or os.environ.get('JARVIS_SCREEN_ENABLED') != 'false'):
                raise ValueError()
        if type(request['effective_policy']) is not dict or type(request['effective_policy'].get('limits')) is not dict:
            raise ValueError()
        if Path.cwd().resolve() != directory.resolve(strict=True):
            raise ValueError()
    except (TypeError, ValueError, OSError):
        raise FullPilotUnavailable('worker_environment_invalid') from None


_BOOLEAN_FIELDS = frozenset({
    'full_developer_passed', 'developer_accepted', 'mar_i_complete', 'production_bot_session',
    'publication_allowed', 'actual_selection_verified', 'private_transport_cleanup', 'registry_cleanup',
    'independent_holdout_verified', 'capability_verified', 'source_scanner_verified', 'image_stopped_verified',
    'verified', 'passed', 'live_schema_verified', 'outside_developer_source', 'prepared_before_model',
    'model_input_contains_holdout', 'response_text_saved', 'provider_error_text_saved',
    'candidate_executed_on_host', 'production_writes', 'settings_changed',
})


def _receipt_booleans(value):
    if type(value) is dict:
        for name, item in value.items():
            if name in _BOOLEAN_FIELDS and type(item) is not bool:
                raise FullPilotUnavailable('worker_receipt_boolean_invalid')
            _receipt_booleans(item)
    elif type(value) is list:
        for item in value:
            _receipt_booleans(item)


def validate_child_control(value, returncode, expected, request):
    """No coercion: distinguish a typed refusal from a complete success claim."""
    _receipt_booleans(value)
    bound = ('operation_surface', 'source_revision', 'source_branch', 'image_id', 'corpus_sha256',
             'oracle_sha256', 'harness_sha256', 'profile', 'target_baseline_sha256',
             'source_dependency_sha256', 'image_record_sha256', 'selection',
             'selection_contract_sha256', 'effective_limits')
    if (type(value) is not dict or any(value.get(key) != expected.get(key) for key in bound)
            or value.get('parent_request_id') != request['run_id'] or value.get('mode') != 'live'
            or type(value.get('full_developer_passed')) is not bool
            or value.get('production_bot_session') is not False
            or value.get('developer_accepted') is not False or value.get('mar_i_complete') is not False
            or 'parent_receipt_verified' in value or type(returncode) is not int):
        raise FullPilotUnavailable('worker_receipt_invalid')
    if value['full_developer_passed'] is True:
        if value.get('status') != 'full_developer_passed' or returncode != 0:
            raise FullPilotUnavailable('worker_receipt_status_invalid')
    elif value.get('status') not in {'unavailable', 'quality_failed', 'cleanup_unverified'} or returncode != 2:
        raise FullPilotUnavailable('worker_receipt_status_invalid')
    return value['full_developer_passed'] is True


def _host_record(home, relative, *, limit=64 * 1024 * 1024):
    """Read only an owned, nonsymlink evidence chain; candidate data stays inert."""
    home = Path(home)
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise FullPilotUnavailable('worker_evidence_path_invalid')
    path = home / relative
    for parent in (home, *(home.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts)))):
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.getuid() or info.st_mode & 0o022):
            raise FullPilotUnavailable('worker_evidence_owner_invalid')
    return support()._read(path, limit=limit)


def _host_json(home, relative):
    value = json.loads(_host_record(home, relative))
    if type(value) is not dict:
        raise FullPilotUnavailable('worker_evidence_invalid')
    return value


def _readonly_rows(path, query, arguments=()):
    with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=.25)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        return [dict(row) for row in connection.execute(query, arguments)]


def validate_success_evidence(value, expected, request, selection):
    """Reconcile success with host-owned artifacts, never summary flags alone."""
    from sandbox.artifacts import Candidate, SandboxError
    from sandbox.profiles import MORTIMER
    from sandbox.verify import runner_fingerprint
    import hmac
    helper = support()
    try:
        _receipt_booleans(value)
        if any(value.get(name) is not True for name in ('actual_selection_verified',
                'independent_holdout_verified', 'private_transport_cleanup', 'registry_cleanup')):
            raise ValueError()
        if (value.get('publication_allowed') is not False or value.get('origin') != 'actual_owned_cli_runtime'
                or value.get('cleanup', {}).get('verified') is not True):
            raise ValueError()
        directory, home = Path(request['directory']), Path(request['image_home'])
        schema_raw = _host_record(directory, 'full-registry.json')
        schema = json.loads(schema_raw)
        declarations = helper.full_registry_contract()
        registry = value['full_registry']
        schemas = schema['schemas']
        names = [item['function']['name'] for item in schemas]
        references = [{'name': item['function']['name'], 'description': item['function']['description'],
                       'parameters': item['function']['parameters']} for item in schemas]
        if (type(schema.get('schema_version')) is not int or schema.get('schema_version') != 1
                or schema.get('servers') != list(SERVERS)
                or type(schemas) is not list or len(schemas) != 40 or len(set(names)) != 40
                or set(names) != set(declarations['declared_tool_names'])
                or schema.get('declaration_source_sha256') != declarations['declaration_source_sha256']
                or registry.get('declaration_source_sha256') != declarations['declaration_source_sha256']
                or registry.get('servers') != list(SERVERS) or type(registry.get('declared_tool_count')) is not int
                or registry.get('declared_tool_count') != 40
                or registry.get('declared_tool_names') != declarations['declared_tool_names']
                or registry.get('live_schema_verified') is not True
                or registry.get('developer_accepted') is not False
                or registry.get('tool_schema_sha256') != digest(canonical(references))
                or value.get('registry_evidence_sha256') != digest(schema_raw)):
            raise ValueError()
        model = _host_json(directory, 'full-model-contract.json')
        if model.get('schemas') != schemas or value.get('model_contract_sha256') != digest(canonical(model)):
            raise ValueError()
        resolved, profile, route, policy = model['route'], selection['model'], selection['route'], selection['policy']
        expected_provider = 'subscription' if route['adapter'] in {
            'subscription_runtime', 'codex_subscription_runtime'} else profile['provider']
        expected_url = {'subscription': 'subscription://claude', 'codex_subscription': 'subscription://codex'}.get(
            route['name'], route['base_url'] or '')
        if (resolved.get('workload') != 'developer' or resolved.get('profile_name') != request['profile']
                or resolved.get('model') != expected['selection']['model']
                or resolved.get('model') != profile['model'] or resolved.get('identity') != profile['identity']
                or resolved.get('provider') != expected_provider or resolved.get('base_url') != expected_url
                or resolved.get('api_key_env') != route['credential_env']
                or canonical(resolved.get('route')) != canonical(route)
                or resolved.get('priority') != policy['priority'] or resolved.get('limits') != policy['limits']):
            raise ValueError()
        if route['adapter'] in {'subscription_runtime', 'codex_subscription_runtime'}:
            from jarvis.subscription_tools import (PROTOCOL, NATIVE_CONTROL_CONTRACT, NATIVE_PROTOCOL_SOURCE,
                NATIVE_ISOLATION_ENV, _claude_tool_argv, _json_digest, _file_digest)
            native_raw = helper._read(Path(request['capability_receipt']))
            native = json.loads(native_raw)
            required_native = ('native_tool_call_observed', 'unknown_tool_rejected',
                'unadvertised_host_tool_rejected', 'unadvertised_host_tool_side_effect_absent', 'builtins_disabled',
                'customization_canaries_absent', 'system_constraints_observed', 'api_credentials_absent',
                'terminal_success_without_error_items')
            if (route['adapter'] != 'subscription_runtime' or type(native.get('schema_version')) is not int
                    or native.get('schema_version') != 1 or native.get('provider') != 'claude'
                    or native.get('model') != resolved['model'] or native.get('protocol') != PROTOCOL
                    or native.get('tool_names') != declarations['declared_tool_names']
                    or native.get('tool_schema_sha256') != _json_digest(references)
                    or any(native.get(name) is not True for name in required_native)
                    or value.get('capability_receipt_sha256') != digest(native_raw)
                    or native.get('executable') != value.get('native_runtime')
                    or model.get('runtime') != value.get('native_runtime')
                    or _file_digest(Path(native['executable']['path'])) != native['executable']['sha256']
                    or native.get('control_protocol_sha256') != _json_digest(NATIVE_CONTROL_CONTRACT)
                    or native.get('protocol_source') != NATIVE_PROTOCOL_SOURCE
                    or native.get('isolation_env_sha256') != _json_digest(NATIVE_ISOLATION_ENV)
                    or native.get('invocation_sha256') != _json_digest(_claude_tool_argv(
                        native['executable']['path'], resolved['model'], '<mcp-config>', '<system-prompt>',
                        declarations['declared_tool_names']))):
                raise ValueError()
        elif model.get('runtime') is not None or 'native_runtime' in value:
            raise ValueError()
        actual = value['actual_run']
        session_id = actual['session_id']
        if (str(uuid.UUID(session_id)) != session_id or actual.get('run_id') != request['run_id']
                or actual.get('agent') != 'developer' or actual.get('status') != 'ok'
                or actual.get('model') != resolved['model'] or value.get('session_id') != session_id
                or value.get('owner_id') != actual.get('user_id')):
            raise ValueError()
        private_db = directory / 'pilot.db'
        _host_record(directory, 'pilot.db')
        rows = _readonly_rows(private_db, 'SELECT run_id,session_id,agent,user_id,model,status FROM agent_runs WHERE run_id=?',
                              (request['run_id'],))
        if rows != [actual]:
            raise ValueError()
        principal = _readonly_rows(private_db,
            'SELECT name,user_id,token_hash FROM client_tokens WHERE name=? AND revoked_at IS NULL', ('service-bot',))
        operator = _readonly_rows(Path(request['service_auth_db']).resolve(strict=True),
            'SELECT name,user_id,token_hash FROM client_tokens WHERE name=? AND revoked_at IS NULL', ('service-bot',))
        if (len(principal) != 1 or len(operator) != 1 or principal[0]['user_id'] != actual['user_id']
                or principal[0]['user_id'] != operator[0]['user_id']
                or not hmac.compare_digest(principal[0]['token_hash'], operator[0]['token_hash'])):
            raise ValueError()
        events = _readonly_rows(private_db, 'SELECT type,tool,tool_call_id FROM agent_events WHERE run_id=? ORDER BY seq',
                                (request['run_id'],))
        # Match get_run's authoritative unresolved-call semantics. A later
        # extra call cannot disappear merely because each required tool also
        # has an older, successful result elsewhere in the same run.
        resolved_calls = {item['tool_call_id'] for item in events
                          if item['type'] == 'tool_result' and item['tool_call_id']}
        if any(item['type'] == 'tool_call' and item['tool_call_id']
               and item['tool_call_id'] not in resolved_calls for item in events):
            raise ValueError()
        for tool in ('selfedit_read', 'selfedit_write'):
            if not all(any(item['type'] == kind and item['tool'] == tool for item in events)
                       for kind in ('tool_call', 'tool_result')):
                raise ValueError()
        tools = value['tool_execution']
        if (type(tools) is not list or not {'selfedit_read', 'selfedit_write'} <= set(tools)
                or any(tool not in ALLOWED_TOOLS for tool in tools)):
            raise ValueError()
        allocations = _host_json(directory, 'full-allocations.json')
        sid = allocations['session_id']
        if not re.fullmatch(r'[0-9a-f]{32}', sid or ''):
            raise ValueError()
        state = _host_json(home, 'sessions/' + sid + '/session.json')
        key = digest((PROJECT.casefold() + '\0selfedit').encode())
        workspace = _host_json(directory, 'workspaces/' + key + '.json')
        verification = value['verification']
        dev, check_task, attempt = (verification[name] for name in ('development_task', 'verification_task', 'attempt'))
        if (not all(re.fullmatch(r'[0-9a-f]{12}', task or '') for task in (dev, check_task))
                or dev == check_task or not re.fullmatch(r'[0-9a-f]{32}', attempt or '')
                or allocations.get('run_id') != request['run_id'] or allocations.get('source_ref') != request['source_ref']
                or allocations.get('image_id') != request['image_id']
                or type(allocations.get('schema_version')) is not int or allocations.get('schema_version') != 1
                or allocations.get('identity') != [state.get(name) for name in helper._SESSION_KEYS]
                or workspace != {'repository': PROJECT, 'kind': 'selfedit', 'profile': MORTIMER.name, 'session': sid}
                or set(allocations['tasks']) != {dev, check_task}
                or set(value['cleanup'].get('owned_tasks', [])) != {dev, check_task}
                or state.get('id') != sid or state.get('task') != dev or state.get('run_id') != request['run_id']
                or state.get('ref') != request['source_ref'] or state.get('image') != request['image_id']
                or state.get('repository') != PROJECT or state.get('kind') != 'selfedit'
                or state.get('phase') != 'reverted' or state.get('publication')):
            raise ValueError()
        for task, purpose, parent in ((dev, 'development', None), (check_task, 'verification', dev)):
            row = _host_json(home, 'tasks/' + task + '/state.json')
            proof = allocations['tasks'][task]
            if (type(proof) is not dict or row.get('id') != task or row.get('vm') != 'mortimer-' + task
                    or row.get('status') != 'deleted' or row.get('purpose') != purpose
                    or row.get('parent_task') != parent or row.get('image') != request['image_id']
                    or row.get('profile') != MORTIMER.name or row.get('source_commit') != request['source_ref']
                    or row.get('profile_sha256') != MORTIMER.fingerprint or row.get('prepared') is not True
                    or row.get('hydrated') is not True or row.get('worker') != 'mortimer-dev'
                    or row.get('network') != 'offline'
                    or row.get('candidate') != verification['baseline' if purpose == 'development' else 'candidate']
                    or helper._canonical(asdict(helper._task_generation(EvidenceLocations(home), task))) != helper._canonical(proof)):
                raise ValueError()
        source = _host_record(home, 'tasks/' + dev + '/input/source.tar')
        task_record = _host_json(home, 'tasks/' + dev + '/state.json')
        if digest(source) != task_record.get('source_sha256'):
            raise ValueError()
        baseline = Candidate.from_snapshot(home / 'tasks' / dev / 'input/source.tar')
        if (type(task_record.get('source_files')) is not int or task_record['source_files'] != len(baseline.files)
                or type(task_record.get('source_bytes')) is not int
                or task_record['source_bytes'] != sum(len(file.data) for file in baseline.files)):
            raise ValueError()
        candidate_id = verification['candidate']
        if not re.fullmatch(r'[0-9a-f]{64}', candidate_id or ''):
            raise ValueError()
        candidate = Candidate.decode(_host_record(home, 'tasks/' + dev + '/candidates/' + candidate_id + '.json'))
        before, after = ({file.path: file for file in data.files} for data in (baseline, candidate))
        changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
        target = expected['target_path']
        if (candidate.fingerprint != candidate_id or changed != {target} or target not in before or target not in after
                or digest(before[target].data) != expected['target_baseline_sha256']
                or digest(after[target].data) != value.get('target_candidate_sha256')
                or MORTIMER.dependency_key(baseline) != expected['source_dependency_sha256']):
            raise ValueError()
        evidence_directory = 'tasks/' + dev + '/verification/' + attempt
        saved = _host_json(home, evidence_directory + '/receipt.json')
        fields = ('attempt', 'candidate', 'baseline', 'source_commit', 'image', 'profile', 'runner',
                  'development_task', 'verification_task', 'passed')
        if (any(saved.get(name) != verification.get(name) for name in fields)
                or saved.get('baseline') != baseline.fingerprint or saved.get('source_commit') != request['source_ref']
                or saved.get('image') != request['image_id'] or saved.get('profile') != MORTIMER.fingerprint
                or saved.get('runner') != runner_fingerprint() or saved.get('passed') is not True
                or saved.get('source_unchanged') is not True or saved.get('status') != 'passed'
                or len(saved.get('checks', [])) != 12
                or [(item['name'], tuple(item['argv'])) for item in saved['checks']] != list(MORTIMER.checks)
                or [{name: item[name] for name in ('name', 'passed', 'returncode', 'log_sha256')}
                    for item in saved['checks']] != verification.get('checks')):
            raise ValueError()
        for check in saved['checks']:
            if (check.get('passed') is not True or type(check.get('returncode')) is not int or check['returncode'] != 0
                    or digest(_host_record(home, evidence_directory + '/' + check['name'] + '.log')) != check['log_sha256']):
                raise ValueError()
        desktop = saved.get('desktop_probe')
        desktop_log = _host_record(home, evidence_directory + '/desktop-probe.log')
        if (type(desktop) is not dict or desktop.get('passed') is not True
                or type(desktop.get('returncode')) is not int or desktop['returncode'] != 0
                or b'desktop=visible' not in desktop_log or digest(desktop_log) != desktop.get('log_sha256')):
            raise ValueError()
        case = helper.load_corpus()
        holdout = helper._holdout_snapshot(request['external_holdout'], request['external_holdout_sha256'], case)
        raw_specs = (helper._canonical(case['oracle']), holdout.raw)
        quality = value['quality']
        if type(quality) is not list or len(quality) != 2:
            raise ValueError()
        for item, kind, raw_spec, outside in zip(quality, ('known', 'external'), raw_specs, (False, True)):
            if (item.get('kind') != kind or item.get('outside_developer_source') is not outside
                    or item.get('spec_sha256') != digest(raw_spec) or len(item.get('checks', [])) != 2):
                raise ValueError()
            for check, phase, passed in zip(item['checks'], ('baseline', 'candidate'), (False, True)):
                relative = 'sessions/' + sid + '/pilot-oracle/pilot-' + kind + '-' + phase + '.log'
                oracle_raw = _host_record(home, relative, limit=64 * 1024)
                _receipt_booleans(json.loads(oracle_raw))
                checked = helper._oracle_result(check, home / relative, raw_spec, phase, case)
                if checked != check or check.get('passed') is not passed:
                    raise ValueError()
        held = value['heldout_input']
        if (held.get('sha256') != request['external_holdout_sha256'] or held.get('prepared_before_model') is not True
                or held.get('outside_developer_source') is not True or held.get('model_input_contains_holdout') is not False):
            raise ValueError()
        return True
    except (KeyError, ValueError, TypeError, AttributeError, OSError, sqlite3.Error,
            SandboxError, helper.DevelopmentPilotUnavailable):
        raise FullPilotUnavailable('worker_success_evidence_invalid') from None


class EvidenceLocations:
    """Read-only location adapter for the existing generation validator; no RPC."""
    def __init__(self, home):
        self.home = home

    def task_dir(self, task):
        if not re.fullmatch(r'[0-9a-f]{12}', task or ''):
            raise FullPilotUnavailable('worker_evidence_path_invalid')
        return self.home / 'tasks' / task


def run_full_pilot(*, mode='dry', source_ref, source_branch, image_id, image_home, profile, route,
                   service_auth_db=None, capability_receipt=None, external_holdout=None,
                   external_holdout_sha256=None, limits=None):
    helper = support()
    report = inspect_full_pilot(source_ref=source_ref, source_branch=source_branch, image_id=image_id,
                               image_home=image_home, profile=profile, route=route)
    if mode == 'dry':
        return report
    if mode != 'live':
        raise FullPilotUnavailable('mode_invalid')
    _require_committed_support()
    from jarvis.model_routing import WorkloadLimits
    if type(limits) is not WorkloadLimits or limits.deadline_seconds is None:
        raise FullPilotUnavailable('explicit_model_deadline_required')
    if service_auth_db is None or external_holdout is None:
        raise FullPilotUnavailable('existing_principal_and_independent_holdout_required')
    home = Path(image_home).resolve(strict=True)
    directory = helper._owned_directory(home, uuid.uuid4().hex)
    run_id = str(uuid.uuid4())
    request = {'source_ref': report['source_revision'], 'source_branch': source_branch,
        'image_id': image_id, 'image_home': str(home), 'profile': profile, 'route': route,
        'service_auth_db': str(Path(service_auth_db).absolute()),
        'capability_receipt': str(Path(capability_receipt).absolute()) if capability_receipt else None,
        'external_holdout': str(Path(external_holdout).absolute()),
        'external_holdout_sha256': external_holdout_sha256,
        'directory': str(directory), 'run_id': run_id,
        'selection_contract_sha256': report['selection_contract_sha256']}
    from sandbox.durable import atomic_json
    path = directory / 'full-worker-request.json'
    environment = worker_environment(directory, profile, route, capability_receipt, limits)
    policy_path = Path(environment['JARVIS_MODEL_ACCESS_CONFIG'])
    contract, concrete_selection = selection_contract(profile, route, policy_path=policy_path)
    report.update(selection_contract_sha256=concrete_selection, effective_limits=contract['policy']['limits'])
    request.update(selection_contract_sha256=concrete_selection, effective_policy=contract['policy'],
                   policy_sha256=digest(helper._read(policy_path)))
    atomic_json(path, request)
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--owned-worker', str(path)],
            env=environment, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=limits.deadline_seconds + 8400, check=False)
        if len(result.stdout) > 512 * 1024:
            raise FullPilotUnavailable('worker_receipt_invalid')
        value = json.loads(result.stdout)
        success = validate_child_control(value, result.returncode, report, request)
        if success:
            validate_success_evidence(value, report, request, contract)
            return {**value, 'parent_receipt_verified': True}
        # A refusal needs no acceptance artifact. Do not propagate arbitrary
        # child summaries, optimistic flags, error strings or content fields.
        return {**report, 'mode': 'live', 'status': value['status'], 'parent_request_id': run_id,
                'reason': 'owned_worker_refused', 'full_developer_passed': False,
                'independent_holdout_verified': False, 'parent_receipt_verified': False,
                'cleanup': {'verified': False}, 'outcome_unknown': value['status'] == 'cleanup_unverified'}
    except (OSError, ValueError, subprocess.SubprocessError, FullPilotUnavailable) as exc:
        return {**report, 'mode': 'live', 'status': 'cleanup_unverified', 'parent_request_id': run_id,
                'reason': getattr(exc, 'code', 'worker_outcome_unknown'), 'full_developer_passed': False,
                'cleanup': {'verified': False}, 'outcome_unknown': True, 'parent_receipt_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owned-worker', help=argparse.SUPPRESS)
    parser.add_argument('--source-ref')
    parser.add_argument('--source-branch')
    parser.add_argument('--image-id')
    parser.add_argument('--image-home')
    parser.add_argument('--profile')
    parser.add_argument('--route')
    parser.add_argument('--service-auth-db')
    parser.add_argument('--capability-receipt')
    parser.add_argument('--external-holdout')
    parser.add_argument('--external-holdout-sha256')
    parser.add_argument('--deadline-seconds', type=float, default=300)
    parser.add_argument('--output')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args(argv)
    helper = support()
    if args.owned_worker:
        request = json.loads(helper._read(Path(args.owned_worker), limit=64 * 1024))
        if Path(request['directory']) != Path(args.owned_worker).parent:
            raise FullPilotUnavailable('worker_storage_binding_invalid')
        report = asyncio.run(full_owned_worker(request))
        print(json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False))
        return 0 if report.get('full_developer_passed') is True else 2
    required = ('source_ref', 'source_branch', 'image_id', 'image_home', 'profile', 'route', 'output')
    if any(getattr(args, name) is None for name in required):
        parser.error('source, remote branch, explicit image, selection and new output path are required')
    from jarvis.model_routing import WorkloadLimits
    with helper._receipt_publication(args.output) as publish:
        report = run_full_pilot(mode='live' if args.live else 'dry',
            **{name: getattr(args, name) for name in required if name != 'output'},
            service_auth_db=args.service_auth_db, capability_receipt=args.capability_receipt,
            external_holdout=args.external_holdout, external_holdout_sha256=args.external_holdout_sha256,
            limits=WorkloadLimits(deadline_seconds=args.deadline_seconds))
        publish(report)
    success = (report.get('full_developer_passed') is True and report.get('status') == 'full_developer_passed'
               and report.get('parent_receipt_verified') is True)
    print(json.dumps({'status': report['status'], 'full_developer_passed': success,
                      'developer_accepted': False, 'mar_i_complete': False, 'output': args.output}))
    return 0 if (not args.live and report['status'] == 'dry_ready_unverified'
                 and report.get('full_developer_passed') is False) or success else 2


if __name__ == '__main__':
    raise SystemExit(main())
