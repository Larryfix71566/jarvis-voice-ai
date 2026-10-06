#!/usr/bin/env python3
"""Acquire exact Claude/forty-schema protocol evidence; dry by default.

This is a public capability diagnostic, not an authorized Developer workload.
It cannot enable a route, approve a private source, edit, publish, or certify
workload quality. Live acquisition runs in a fresh, privately stored process.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
import hashlib
import http.server
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import signal
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REFERENCE = 'docs/REPO_MAP.md'
DONE = 'MORTIMER_NATIVE40_PROTOCOL_OK'
CONSTRAINT = ('This public protocol diagnostic read only its approved reference. '
              'No edit, publication, private operation or Developer workload was authorized.')
OUTPUT_BYTES = 1_000_000
WORKER_DRAIN_SECONDS = 12
_WORKER_QUARANTINE = {}
CONFIG_FILES = ('config/model_access.yaml', 'config/model_profiles.yaml',
                'config/model_endpoints.yaml', 'config/agents.yaml', 'config/mcp_servers.yaml')


class CapabilityUnavailable(RuntimeError):
    pass


class WorkerCleanupUnavailable(CapabilityUnavailable):
    def __init__(self, ownership):
        self.ownership = ownership
        super().__init__('worker_cleanup_unverified')


@dataclass
class _WorkerOwnership:
    directory: Path = field(repr=False)
    process: object = field(repr=False)
    readers: tuple = field(default=(), repr=False)
    lifetime: object = field(default=None, repr=False)
    failure: object = field(default=None, repr=False)
    stop_requested: bool = False
    quarantine: bool = False
    cleanup_verified: bool = False
    evidence_published: bool = False

    def stop(self):
        if not self.stop_requested:
            self.stop_requested = True
            if self.process.returncode is None:
                try:
                    self.process.send_signal(signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def metadata(self):
        return {'record_kind': 'native40_worker_quarantine', 'directory': str(self.directory),
            'worker_pid': self.process.pid, 'stop_requested': self.stop_requested,
            'quarantined': self.quarantine, 'process_exited': self.process.returncode is not None,
            'readers_done': all(reader.done() for reader in self.readers),
            'cleanup_verified': self.cleanup_verified, 'scratch_retained': True,
            'reader_loop_required': True, 'evidence_published': self.evidence_published}

    def retain(self):
        # Retain the exact process/readers even if evidence publication itself
        # refuses. These are owners, not success flags inferred from wait().
        self.quarantine = True
        _WORKER_QUARANTINE[str(self.directory)] = self
        try:
            with support()._receipt_publication(self.directory / 'quarantine.json') as publish:
                publish({**self.metadata(), 'evidence_published': True})
            self.evidence_published = True
        except Exception:
            # The exception owner and in-process quarantine still retain the
            # exact child. Failure to publish evidence never authorizes cleanup.
            pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def diagnostic_host_limits(timeout):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 90:
        raise CapabilityUnavailable('invalid_host_deadline')
    return {'deadline_seconds': timeout, 'observed_output_bytes_per_round': OUTPUT_BYTES,
            'native_tool_calls_per_round': 2}


def support():
    from scripts import run_model_use_development_pilot
    return run_model_use_development_pilot


def task_budget_authority(budget):
    """Read stored bounds as authority; a captured handle can only restrict."""
    from jarvis.model_budget import (TaskBudget, ChildTaskBudget, _existing_scope,
        recover_model_task_budget_for_transport, remaining_seconds,
        remaining_child_seconds, validate_model_child_budget)
    if type(budget) is ChildTaskBudget:
        current = validate_model_child_budget(budget)
        return (budget.owner, *budget._ancestors, budget.child,
                current.owner, *current._ancestors, current.child), remaining_child_seconds(current)
    if type(budget) is not TaskBudget:
        raise CapabilityUnavailable('typed_task_budget_required')
    remaining = remaining_seconds(budget)  # authenticates transient seal/tenant/root identity
    if budget.scope_id is not None:
        current = recover_model_task_budget_for_transport(budget.workload,
            budget.parent_request_id, scope_id=budget.scope_id)
        if current.started_at != budget.started_at:
            raise CapabilityUnavailable('budget_scope_mismatch')
    else:
        # An authentic transient handle may precede a later durable restriction
        # of the same root. Its empty captured policy cannot clear that row.
        current = _existing_scope(budget.user_id, budget.workload, budget.parent_request_id)
    return (budget,) if current is None else (budget, current), remaining


def selection(profile, route, model=None, *, input_policy=None, task_budget=None):
    """Keep ordinary route refusal; only its missing tools are under test."""
    from jarvis import model_routing as routing
    from jarvis.privacy_policy import DataPolicy, assert_route_allowed, strictest
    from jarvis.bot.sensitive_turn import current_sensitive_turn
    if route != 'subscription':
        raise CapabilityUnavailable('subscription_route_required')
    policy = routing.resolve_policy('developer', explicit_profile=profile, explicit_route=route,
        include_preferences=False)
    registry = routing._load_model_registry()
    routing._assert_unique_canonical_identities(registry)
    configured = routing._resolve_model_profile(registry, profile, workload='developer')
    routing.assert_model_quality(policy, configured)
    access = routing._route_for_profile(configured, route,
        routing.load_access_config().get('routes') or {})
    if (access.adapter != 'subscription_runtime' or access.billing != 'subscription'
            or access.credential_env or access.base_url or configured.get('provider') != 'anthropic'):
        raise CapabilityUnavailable('native_route_contract_invalid')
    floor = DataPolicy(policy.privacy, 'configured-developer-floor')
    holder = current_sensitive_turn.get()
    if holder is not None and holder.is_armed():
        floor = strictest(floor, DataPolicy('confidential', 'inherited-protected-turn'))
    if input_policy is not None:
        if type(input_policy) is not DataPolicy:
            raise CapabilityUnavailable('typed_input_policy_required')
        floor = strictest(floor, input_policy)
    assert_route_allowed(access, floor)
    missing = set(policy.required_capabilities) - set(access.capabilities)
    if missing - {'tools'}:
        raise CapabilityUnavailable('unsupported_configured_capability')
    ordinary_refusal = None
    try:
        routing._assert_policy_route(policy, access)
    except routing.ModelRouteError:
        if missing != {'tools'}:
            raise
        ordinary_refusal = 'route lacks required capabilities: tools'
    if model is not None and model != configured['model']:
        raise CapabilityUnavailable('requested_model_mismatch')
    limits = policy.limits
    if (limits.max_output_tokens_per_call is not None
            or limits.max_estimated_spend_usd_per_task is not None):
        raise CapabilityUnavailable('native_provider_limits_unsupported')
    if task_budget is not None:
        budgets, _ = task_budget_authority(task_budget)
        if any(budget.limits.max_output_tokens_per_call is not None
                or budget.limits.max_estimated_spend_usd_per_task is not None for budget in budgets):
            raise CapabilityUnavailable('native_provider_limits_unsupported')
    return {'profile': profile, 'model': configured['model'], 'identity': configured['identity'],
        'policy': asdict(policy), 'route': asdict(access), 'ordinary_route_refusal': ordinary_refusal,
        'tools_under_test': True, 'production_route_ready': False, 'input_floor': floor.level,
        'registry': registry, 'access_config': routing.load_access_config()}


@dataclass(frozen=True)
class ReferencePin:
    root: str
    raw: bytes = field(repr=False)
    identities: tuple = field(repr=False)


def pin_reference():
    from mcp_servers.mcp_repo.logic import REPO_READ_MAX_BYTES, resolve_repo_path
    root = ROOT.resolve(strict=True)
    path = resolve_repo_path(root, REFERENCE)
    if path != root / REFERENCE:
        raise CapabilityUnavailable('reference_scope_invalid')
    chain = [root, root / 'docs', path]
    def pins():
        result = []
        for item in chain:
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise CapabilityUnavailable('reference_identity_changed')
            result.append((info.st_dev, info.st_ino, info.st_mode,
                *((info.st_size, info.st_mtime_ns, info.st_ctime_ns) if item == path else ())))
        return tuple(result)
    before = pins()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > REPO_READ_MAX_BYTES
                or (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != before[-1]):
            raise CapabilityUnavailable('reference_identity_changed')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(REPO_READ_MAX_BYTES + 1)
        after = os.fstat(descriptor)
        if (pins() != before or (after.st_dev, after.st_ino, after.st_mode, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns) != before[-1] or not raw):
            raise CapabilityUnavailable('reference_identity_changed')
        raw.decode('utf-8')
        return ReferencePin(str(root), raw, before)
    finally:
        os.close(descriptor)


def check_reference(pin):
    if pin_reference() != pin:
        raise CapabilityUnavailable('reference_identity_changed')


def frozen_contract(profile, route, model=None):
    from jarvis.model_routing import POLICY_PATH_ENV, DEFAULT_POLICY_PATH
    from jarvis.agents.upgrade_agent import registry_source, load_registry_layers
    pin = pin_reference()
    selected_policy = Path(os.environ.get(POLICY_PATH_ENV) or DEFAULT_POLICY_PATH).absolute()
    selected_registry = registry_source().absolute()
    layers = load_registry_layers()
    effective_sources = [selected_policy, selected_registry]
    if layers.get('endpoints_source'):
        effective_sources.append(Path(layers['endpoints_source']).absolute())
    return json.loads(canonical({'selection': selection(profile, route, model),
        'declarations': support().full_registry_contract(),
        'source': {'root': pin.root, 'path': REFERENCE, 'sha256': digest(pin.raw),
                   'identities': pin.identities},
        'config_sha256': {name: digest((ROOT / name).read_bytes()) for name in CONFIG_FILES},
        'effective_config_sha256': {str(path): digest(path.read_bytes()) for path in set(effective_sources)},
        'config_environment': {POLICY_PATH_ENV: str(selected_policy), 'JARVIS_UPGRADE_MODELS': str(selected_registry)},
        'runner_sha256': digest(Path(__file__).read_bytes())}))


def references(schemas):
    from jarvis.model_execution import ModelToolReference
    return tuple(ModelToolReference(item['function']['name'], item['function']['parameters'],
                                    item['function']['description']) for item in schemas)


async def installed_schemas():
    """Independently reconstruct metadata from the actual installed servers.

    list_tools is metadata only: no Registry call, admin HTTP or tool function.
    The worker still requires real six-process discovery; this parent check
    prevents an internally self-consistent changed schema receipt passing.
    """
    import copy
    import yaml
    from jarvis.skills.registry import RUN_ID_INJECTED_TOOLS
    configured = yaml.safe_load((ROOT / 'config/mcp_servers.yaml').read_text())['servers']
    result = []
    for entry in configured:
        if entry['name'] not in support().DEVELOPER_SERVERS: continue
        module = importlib.import_module('mcp_servers.' + entry['name'].replace('-', '_') + '.server')
        for tool in await module.mcp.list_tools():
            parameters = copy.deepcopy(getattr(tool, 'inputSchema', None) or getattr(tool, 'parameters', None)
                                       or {'type': 'object', 'properties': {}})
            if tool.name in RUN_ID_INJECTED_TOOLS:
                (parameters.get('properties') or {}).pop('run_id', None)
                if isinstance(parameters.get('required'), list):
                    parameters['required'] = [name for name in parameters['required'] if name != 'run_id']
            result.append({'type': 'function', 'function': {'name': tool.name,
                'description': tool.description or '', 'parameters': parameters}})
    return json.loads(canonical(result))


class PublicReferenceGuard:
    """No other operation can reach Registry, even when it is advertised."""
    def __init__(self, registry, pin, contract_check):
        self.registry, self.pin, self.check = registry, pin, contract_check
        self.reads = 0
        self.refusals = 0
        self.source_evidence = []

    async def call(self, name, arguments, scope):
        from jarvis.privacy_policy import issue_tool_result, validate_tool_result
        self.check()
        check_reference(self.pin)
        if scope.input_policy.level != 'approved_external':
            raise CapabilityUnavailable('reference_source_protected')
        if name != 'repo_read_file' or arguments != {'path': REFERENCE}:
            self.refusals += 1
            envelope = issue_tool_result(scope, '{"error":"outside_public_capability_probe","ok":false}',
                scope.input_policy, 'host-generated-capability-refusal')
        else:
            envelope = await self.registry.call_classified(name, arguments,
                list(support().DEVELOPER_SERVERS), execution_scope=scope)
            policy, content = validate_tool_result(scope, envelope)
            if policy.level != 'approved_external':
                raise CapabilityUnavailable('reference_source_protected')
            body = json.loads(content)
            normalized = self.pin.raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
            if (body != {'ok': True, 'path': REFERENCE, 'bytes': len(self.pin.raw), 'content': normalized}
                    or len(content.encode()) > OUTPUT_BYTES):
                raise CapabilityUnavailable('reference_result_mismatch')
            self.reads += 1
        self.check()
        check_reference(self.pin)
        policy, content = validate_tool_result(scope, envelope)
        if policy.level != 'approved_external':
            raise CapabilityUnavailable('reference_source_protected')
        self.source_evidence.append({'parent_request_id': scope.parent_request_id,
            'task_id': scope.task_id, 'tool_call_id': scope.tool_call_id, 'tool': name,
            'argument_digest': scope.argument_digest, 'policy': policy.level,
            'content_digest': envelope.content_digest, 'source_scope': envelope.source_scope,
            'content': content})
        return content


def observed_session_type():
    from jarvis.subscription_tools import _ClaudeNativeSession
    class Session(_ClaudeNativeSession):
        def __init__(self, *args, environment=None, contract_check=lambda: None, **kwargs):
            super().__init__(*args, **kwargs)
            self.environment = environment
            self.contract_check = contract_check
            self.observed_models = set()
            self.observed_native_tools = []
            self.native_calls = []
            self.hook_evidence = []
            self.output_bytes = 0
        def _environment(self):
            self.contract_check()  # Last synchronous check before actual CLI construction.
            result = super()._environment()
            return {**result, **(self.environment or {})}
        async def _stdout(self):
            original = self.process.stdout
            owner = self
            class Reader:
                async def readline(self):
                    raw = await original.readline()
                    owner.output_bytes += len(raw)
                    if owner.output_bytes > OUTPUT_BYTES:
                        raise CapabilityUnavailable('native_output_byte_limit')
                    if raw:
                        event = json.loads(raw)
                        message = event.get('message') or {}
                        model = message.get('model') if type(message) is dict else None
                        if type(message) is dict:
                            owner.observed_native_tools.extend(block.get('name') for block in message.get('content', [])
                                if type(block) is dict and block.get('type') == 'tool_use')
                            owner.native_calls.extend({'tool_call_id': block.get('id'), 'name': block.get('name'),
                                'arguments_sha256': digest(canonical(block.get('input')))}
                                for block in message.get('content', []) if type(block) is dict and block.get('type') == 'tool_use')
                        if model:
                            owner.observed_models.add(model)
                            if model != owner.model:
                                raise CapabilityUnavailable('native_model_mismatch')
                    return raw
            self.process.stdout = Reader()
            try:
                await super()._stdout()
            finally:
                self.process.stdout = original
        async def _stderr(self):
            while raw := await self.process.stderr.read(65536):
                self.output_bytes += len(raw)
                if self.output_bytes > OUTPUT_BYTES:
                    self.failure = CapabilityUnavailable('native_output_byte_limit')
                    await self.queue.put(self.failure)
                    return
        async def _post_tool_hook(self, event):
            await super()._post_tool_hook(event)
            request = event['request']
            pending = self.completed[request['tool_use_id']]
            self.hook_evidence.append({'request_id': event['request_id'],
                'parent_request_id': self.parent_id, 'tool_call_id': pending.call_id,
                'tool': pending.name, 'task_id': pending.task_id,
                'arguments_sha256': digest(canonical(pending.arguments)),
                'constraints_sha256': digest(pending.constraints.encode()),
                'hook_done': pending.hook_done})
    return Session


async def unknown_request(session):
    reader, writer = await asyncio.open_unix_connection(str(session.socket_path))
    try:
        packet = {'nonce': session.nonce, 'parent_id': session.parent_id,
            'task_id': session.origin_task_id, 'request_id': uuid.uuid4().hex,
            'name': 'unregistered_capability_probe_tool', 'arguments': {}}
        writer.write(canonical(packet) + b'\n')
        await writer.drain()
        value = json.loads(await reader.readline())
        return value.get('ok') is False
    finally:
        writer.close()
        await writer.wait_closed()


async def protocol_round(identity, model, refs, guard, timeout, *, environment=None, expect_bash=False):
    from jarvis.model_execution import ModelExecutionRequest
    from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope
    from jarvis.subscription import SubscriptionCapabilityError
    parent = str(uuid.uuid4())
    messages = [{'role': 'system', 'content': CONSTRAINT}, {'role': 'user',
        'content': f"Call repo_read_file once with path {REFERENCE!r}, then reply exactly {DONE}. Use no other operation."}]
    def request(index):
        return ModelExecutionRequest('developer', f'native-capability:{parent}:{index}', parent, '',
            tools=refs, data_policy=DataPolicy('approved_external', 'standing-public-reference-probe'),
            timeout_s=timeout)
    first = request(0)
    before_reads = guard.reads
    Session = observed_session_type()
    session = Session(first, SimpleNamespace(model=model), {'messages': messages}, identity['path'],
                      max_tool_calls=2, environment=environment, contract_check=guard.check)
    result = {'native_tool_call_observed': False, 'unknown_tool_rejected': False,
              'system_constraints_observed': False, 'terminal_success_without_error_items': False,
              'unadvertised_host_tool_rejected': False, 'cleanup_verified': False}
    try:
        async with asyncio.timeout(timeout):
            await session.start()
            result['unknown_tool_rejected'] = await unknown_request(session)
            for index in range(3):
                current = request(index)
                try:
                    completion = await session.next_completion(current, {'messages': messages})
                except SubscriptionCapabilityError as exc:
                    if not expect_bash:
                        raise
                    result['unadvertised_host_tool_rejected'] = (
                        str(exc) == 'native runtime requested an unapproved or excessive tool'
                        and session.call_count == 0 and session.observed_native_tools == ['Bash'])
                    break
                message = completion.choices[0].message
                calls = message.tool_calls or []
                if not calls:
                    result['terminal_success_without_error_items'] = (
                        message.content == DONE and not expect_bash and guard.reads == before_reads + 1)
                    break
                assistant = {'role': 'assistant', 'content': message.content or None, 'tool_calls': []}
                replies = []
                for call in calls:
                    arguments = json.loads(call.function.arguments)
                    scope = make_tool_execution_scope(parent, current.task_id, call.id,
                        call.function.name, arguments, first.data_policy)
                    content = await guard.call(call.function.name, arguments, scope)
                    result['native_tool_call_observed'] |= call.function.name == 'repo_read_file'
                    assistant['tool_calls'].append({'id': call.id, 'type': 'function',
                        'function': {'name': call.function.name, 'arguments': call.function.arguments},
                        **call.model_extra})
                    replies.append({'role': 'tool', 'tool_call_id': call.id,
                                    'name': call.function.name, 'content': content})
                messages += [assistant, *replies, {'role': 'system', 'content': CONSTRAINT}]
            result['system_constraints_observed'] = bool(session.completed) and all(
                pending.hook_done and pending.constraints == CONSTRAINT for pending in session.completed.values())
            result['observed_models'] = sorted(session.observed_models)
            result['output_bytes'] = session.output_bytes
            result['hook_evidence'] = list(session.hook_evidence)
            result['native_tool_names'] = list(session.observed_native_tools)
            result['native_calls'] = list(session.native_calls)
            result['parent_request_id'] = parent
            result['origin_task_id'] = first.task_id
            if not expect_bash and session.observed_models != {model}:
                raise CapabilityUnavailable('native_model_unverified')
    finally:
        await session.close()
        result['cleanup_verified'] = (session.closed and not session.directory.exists()
            and (session.process is None or session.process.returncode is not None)
            and all(task.done() for task in session.readers))
    if session.output_bytes > OUTPUT_BYTES or (session.failure is not None and not expect_bash):
        raise CapabilityUnavailable('native_transport_failed')
    return result


@asynccontextmanager
async def loopback_fixture(directory, model, refs, *, bash=False):
    """Actual installed CLI, synthetic HTTP provider; never a paid fallback."""
    marker = 'NATIVE40_CUSTOMIZATION_' + uuid.uuid4().hex
    home = directory / ('negative-home' if bash else 'isolation-home')
    config = home / '.claude'
    config.mkdir(parents=True, mode=0o700)
    for name in ('CLAUDE.md', 'CLAUDE.local.md'):
        (home / name).write_text(marker)
    for name in ('rules/canary.md', 'skills/canary/SKILL.md', 'commands/canary.md', 'agents/canary.md'):
        target = config / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(marker)
    (config / 'settings.json').write_text(json.dumps({'env': {'NATIVE40_CANARY': marker},
        'hooks': {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'printf ' + marker}]}]}}))
    canary = home / 'forbidden-bash-side-effect'
    observations = []
    expected_names = ['mcp__mortimer__' + ref.name for ref in refs]
    class Handler(http.server.BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)
        def log_message(self, *_args):
            pass
        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= OUTPUT_BYTES:
                    self.send_error(413); return
                packet = json.loads(self.rfile.read(size))
                if type(packet) is not dict: raise ValueError()
            except (ValueError, OSError):
                self.send_error(400); return
            if '/messages' not in self.path:
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"input_tokens":8}'); return
            tools = packet.get('tools', [])
            observations.append({'names': [item.get('name') for item in tools],
                'schemas_match': len(tools) == len(refs) and all(
                    item.get('input_schema') == dict(ref.parameters) for item, ref in zip(tools, refs)),
                'model': packet.get('model'), 'canary_absent': marker not in json.dumps(packet),
                'constraint_present': CONSTRAINT in json.dumps(packet),
                'synthetic_auth_only': self.headers.get('x-api-key') == 'native40-synthetic-not-a-key'
                    and self.headers.get('Authorization') is None})
            index = len(observations)
            tool_name = 'Bash' if bash else ('mcp__mortimer__repo_read_file' if index == 1 else 'mcp__mortimer__selfedit_finish')
            arguments = {'command': 'touch ' + str(canary)} if bash else ({'path': REFERENCE} if index == 1 else {})
            use_tool = bash or index < 3
            block = {'type': 'tool_use', 'id': 'toolu_native40_' + str(index), 'name': tool_name, 'input': arguments}
            if not use_tool:
                block = {'type': 'text', 'text': DONE}
            message = {'id': 'msg_native40_' + str(index), 'type': 'message', 'role': 'assistant',
                'model': model, 'content': [block], 'stop_reason': 'tool_use' if use_tool else 'end_turn',
                'stop_sequence': None, 'usage': {'input_tokens': 8, 'output_tokens': 8}}
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream' if packet.get('stream') else 'application/json')
            self.end_headers()
            if not packet.get('stream'):
                self.wfile.write(json.dumps(message).encode()); return
            events = [('message_start', {'type': 'message_start', 'message': {**message, 'content': [],
                'stop_reason': None, 'usage': {'input_tokens': 8, 'output_tokens': 0}}}),
                ('content_block_start', {'type': 'content_block_start', 'index': 0,
                    'content_block': {**block, 'input': {}} if use_tool else {**block, 'text': ''}}),
                ('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                    'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(arguments)} if use_tool
                        else {'type': 'text_delta', 'text': DONE}}),
                ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
                ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': message['stop_reason'],
                    'stop_sequence': None}, 'usage': {'output_tokens': 8}}), ('message_stop', {'type': 'message_stop'})]
            for event, payload in events:
                self.wfile.write(('event: ' + event + '\ndata: ' + json.dumps(payload) + '\n\n').encode())
                self.wfile.flush()
    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.05), name='native40-loopback')
    thread.start()
    value = {'environment': {'HOME': str(home), 'CLAUDE_CONFIG_DIR': str(config),
        'ANTHROPIC_API_KEY': 'native40-synthetic-not-a-key',
        'ANTHROPIC_BASE_URL': 'http://127.0.0.1:' + str(server.server_port),
        'CLAUDE_CODE_MAX_RETRIES': '0', 'API_TIMEOUT_MS': '10000'},
        'observations': observations, 'expected_names': expected_names, 'canary': canary,
        'closed': False}
    try:
        yield value
    finally:
        from jarvis.storage_context import state_to_thread
        await state_to_thread(server.shutdown)
        server.server_close()
        await state_to_thread(thread.join, 3)
        value['closed'] = not thread.is_alive()
        if not value['closed']:
            raise CapabilityUnavailable('loopback_cleanup_unverified')


def verified_loopback(value, model):
    seen = value['observations']
    return bool(seen) and all(item['names'] == value['expected_names'] and item['schemas_match']
        and item['model'] == model and item['canary_absent'] and item['synthetic_auth_only'] for item in seen)


async def acquire(directory, frozen, timeout, started_at):
    from jarvis.storage_context import storage_scope, state_to_thread
    from jarvis.skills.registry import SkillRegistry
    from jarvis.subscription_tools import (claude_tool_runtime_identity, _claude_tool_argv,
        PROTOCOL, NATIVE_CONTROL_CONTRACT, NATIVE_ISOLATION_ENV, NATIVE_PROTOCOL_SOURCE)
    from jarvis.subscription import _json_digest, _subscription_env
    import yaml
    registry = None
    sessions_clean = False
    storage = None
    owners = []
    report = None
    deadline = started_at + timeout
    if frozen.get('host_limits') != diagnostic_host_limits(timeout):
        raise CapabilityUnavailable('frozen_host_limits_changed')
    configured_deadline = frozen['selection']['policy']['limits']['deadline_seconds']
    if configured_deadline is not None:
        deadline = min(deadline, started_at + configured_deadline)
    def remaining():
        value = deadline - time.time()
        if value <= 0: raise CapabilityUnavailable('host_deadline_exhausted')
        return value
    async with storage_scope(db_path=directory / 'probe.db', costs_db_path=directory / 'costs.db',
                             model_preferences_enabled=False) as storage:
        async with asyncio.timeout(remaining()):
            actual = frozen_contract(frozen['selection']['profile'], 'subscription', frozen['selection']['model'])
            expected_static = {key: value for key, value in frozen.items() if key not in ('runtime', 'host_limits')}
            if actual != expected_static:
                raise CapabilityUnavailable('frozen_contract_changed')
            identity = await state_to_thread(claude_tool_runtime_identity)
            if identity != frozen.get('runtime'):
                raise CapabilityUnavailable('native_runtime_changed')
            binary = Path(identity['path'])
            binary_info = binary.lstat()
            binary_pin = (binary_info.st_dev, binary_info.st_ino, binary_info.st_mode,
                binary_info.st_size, binary_info.st_mtime_ns, binary_info.st_ctime_ns)
            pin = pin_reference()
            configured = yaml.safe_load((ROOT / 'config/mcp_servers.yaml').read_text())
            entries = [entry for entry in configured['servers'] if entry['name'] in support().DEVELOPER_SERVERS]
            path = directory / 'mcp-discovery.json'
            path.write_bytes(canonical({'servers': entries})); path.chmod(0o600)
            registry = SkillRegistry(path)
            try:
                await registry.start()
                owners = list(registry._handles.values())
                discovered = support().inspect_live_developer_registry(registry)
                schemas = registry.openai_tools(list(support().DEVELOPER_SERVERS))
                refs = references(schemas)
                names = [ref.name for ref in refs]
                if len(names) != 40 or set(names) != set(discovered['declared_tool_names']):
                    raise CapabilityUnavailable('full_schema_menu_changed')
                def check():
                    remaining()
                    info = binary.lstat()
                    if (frozen_contract(actual['selection']['profile'], 'subscription', actual['selection']['model']) != expected_static
                            or registry.openai_tools(list(support().DEVELOPER_SERVERS)) != schemas
                            or support().inspect_live_developer_registry(registry) != discovered
                            or (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                                info.st_mtime_ns, info.st_ctime_ns) != binary_pin
                            or digest(binary.read_bytes()) != identity['sha256']):
                        raise CapabilityUnavailable('frozen_contract_changed')
                    check_reference(pin)
                guard = PublicReferenceGuard(registry, pin, check)
                live = await protocol_round(identity, actual['selection']['model'], refs, guard, remaining())
                async with loopback_fixture(directory, actual['selection']['model'], refs) as isolated:
                    isolation = await protocol_round(identity, actual['selection']['model'], refs, guard,
                        remaining(), environment=isolated['environment'])
                async with loopback_fixture(directory, actual['selection']['model'], refs, bash=True) as negative:
                    bash = await protocol_round(identity, actual['selection']['model'], refs, guard,
                        remaining(), environment=negative['environment'], expect_bash=True)
                check(); check_reference(pin)
                if await state_to_thread(claude_tool_runtime_identity) != identity:
                    raise CapabilityUnavailable('native_runtime_changed')
                proof = {'native_tool_call_observed': live['native_tool_call_observed'],
                    'unknown_tool_rejected': live['unknown_tool_rejected'],
                    'unadvertised_host_tool_rejected': bash['unadvertised_host_tool_rejected'] and verified_loopback(negative, actual['selection']['model']),
                    'unadvertised_host_tool_side_effect_absent': not negative['canary'].exists(),
                    'customization_canaries_absent': verified_loopback(isolated, actual['selection']['model']),
                    'builtins_disabled': verified_loopback(isolated, actual['selection']['model']) and verified_loopback(negative, actual['selection']['model']),
                    'system_constraints_observed': live['system_constraints_observed'] and isolation['system_constraints_observed']
                        and len(isolated['observations']) == 3 and isolated['observations'][-1]['constraint_present'],
                    'terminal_success_without_error_items': live['terminal_success_without_error_items'] and isolation['terminal_success_without_error_items']}
                sessions_clean = all(part['cleanup_verified'] for part in (live, isolation, bash)) and isolated['closed'] and negative['closed']
                if not all(proof.values()) or not sessions_clean or guard.refusals != 1 or guard.reads != 2:
                    raise CapabilityUnavailable('native_protocol_proof_incomplete')
                report = {'schema_version': 1, 'provider': 'claude', 'model': actual['selection']['model'],
                    'executable': identity, 'protocol': PROTOCOL, 'tool_names': names,
                    'tool_schema_sha256': _json_digest([{'name': ref.name, 'description': ref.description,
                        'parameters': dict(ref.parameters)} for ref in refs]),
                    'invocation_sha256': _json_digest(_claude_tool_argv(identity['path'], actual['selection']['model'],
                        '<mcp-config>', '<system-prompt>', names)),
                    'control_protocol_sha256': _json_digest(NATIVE_CONTROL_CONTRACT),
                    'isolation_env_sha256': _json_digest(NATIVE_ISOLATION_ENV), 'protocol_source': NATIVE_PROTOCOL_SOURCE,
                    'api_credentials_absent': not any('API_KEY' in key or 'BASE_URL' in key for key in _subscription_env()),
                    **proof, 'frozen_contract': frozen, 'servers': list(support().DEVELOPER_SERVERS),
                    'schemas': schemas, 'private_mutation_refused_before_ingress': guard.refusals == 1,
                    'tools_under_test': True, 'production_route_ready': False, 'developer_accepted': False,
                    'workload_quality_accepted': False, 'mar_i_complete': False, 'billing_verified': False,
                    'full_profile_verified': False, 'provider_token_or_spend_bound_verified': False,
                    'host_limits': frozen['host_limits'], 'native_cleanup_verified': sessions_clean,
                    'observations': {'live': live, 'isolation': isolation, 'negative': bash,
                        'isolation_http': isolated['observations'], 'negative_http': negative['observations'],
                        'sources': guard.source_evidence},
                    'record_kind': 'installed_cli_exact_schema_protocol_evidence', 'runtime_receipt': True}
            finally:
                if registry is not None:
                    await registry.stop()
    if (not storage.cleanup_verified or storage.pending_workers or not sessions_clean
            or any(owner.task is not None and not owner.task.done() for owner in owners)):
        raise CapabilityUnavailable('owned_cleanup_unverified')
    report['storage_cleanup_verified'] = report['registry_cleanup_verified'] = True
    return report


def worker_environment(directory, frozen=None):
    from jarvis.subscription import _subscription_env
    environment = _subscription_env(str(directory))
    environment.update({'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1', 'RUN_LIVE': '0',
        'JARVIS_DB_PATH': str(directory / 'probe.db'), 'JARVIS_COSTS_DB': str(directory / 'costs.db'),
        'JARVIS_VAULT_PATH': str(directory / 'no-vault'), 'MORTIMER_HOME': str(directory / 'knowledge'),
        'JARVIS_MODEL_PREFERENCES_ENABLED': '0', 'JARVIS_VAULT_ENABLED': 'false',
        'JARVIS_KEY_HEALTH_ENABLED': 'false', 'JARVIS_SCREEN_ENABLED': 'false',
        'JARVIS_ADMIN_URL': 'http://127.0.0.1:1', 'JARVIS_REPO_ROOT': str(ROOT),
        'JARVIS_TIMEZONE': 'UTC', 'FASTMCP_CHECK_FOR_UPDATES': 'off'})
    environment.update((frozen or {}).get('config_environment') or {})
    return environment


def validate_worker_boundary(request, packet):
    """Validate isolation before any MCP/native/DB module is imported."""
    directory = request.parent
    info = directory.lstat()
    if (directory.parent != Path('/private/tmp') or not directory.name.startswith('mortimer-native40-capability-')
            or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.getuid() or directory.resolve() != directory
            or Path.cwd().resolve() != directory or request.name != 'request.json'):
        raise CapabilityUnavailable('owned_worker_directory_required')
    required = {'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1', 'RUN_LIVE': '0',
        'JARVIS_DB_PATH': str(directory / 'probe.db'), 'JARVIS_COSTS_DB': str(directory / 'costs.db'),
        'JARVIS_VAULT_PATH': str(directory / 'no-vault'), 'MORTIMER_HOME': str(directory / 'knowledge'),
        'JARVIS_MODEL_PREFERENCES_ENABLED': '0', 'JARVIS_VAULT_ENABLED': 'false',
        'JARVIS_KEY_HEALTH_ENABLED': 'false', 'JARVIS_SCREEN_ENABLED': 'false',
        'JARVIS_ADMIN_URL': 'http://127.0.0.1:1', 'JARVIS_REPO_ROOT': str(ROOT),
        'JARVIS_TIMEZONE': 'UTC', 'FASTMCP_CHECK_FOR_UPDATES': 'off'}
    configurations = packet['contract']['config_environment']
    if type(configurations) is not dict or set(configurations) != {'JARVIS_MODEL_ACCESS_CONFIG', 'JARVIS_UPGRADE_MODELS'}:
        raise CapabilityUnavailable('owned_worker_environment_required')
    required.update(configurations)
    standard = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'LC_CTYPE',
                'TMPDIR', 'TMP', 'TEMP', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}
    if (any(os.environ.get(key) != value for key, value in required.items())
            or set(os.environ) - standard - set(required)):
        raise CapabilityUnavailable('owned_worker_environment_required')


async def worker_acquire(directory, packet):
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    signalled = False
    def cancel_once():
        nonlocal signalled
        if not signalled:
            signalled = True
            task.cancel()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, cancel_once)
    try:
        return await acquire(directory, packet['contract'], packet['timeout'], packet['started_at'])
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


async def fresh_capture(frozen, timeout, started_at, *, input_policy=None, task_budget=None):
    from jarvis.subscription import _owned_group_present
    from jarvis.subscription_tools import claude_tool_runtime_identity
    from jarvis.storage_context import storage_scope, state_to_thread
    selection(frozen['selection']['profile'], 'subscription', frozen['selection']['model'],
              input_policy=input_policy, task_budget=task_budget)
    if task_budget is not None:
        _, inherited_remaining = task_budget_authority(task_budget)
        if inherited_remaining is not None:
            timeout = min(timeout, max(0, time.time() + inherited_remaining - started_at))
    configured = frozen['selection']['policy']['limits']['deadline_seconds']
    if configured is not None: timeout = min(timeout, configured)
    if started_at + timeout <= time.time():
        raise CapabilityUnavailable('host_deadline_exhausted')
    directory = Path(tempfile.mkdtemp(prefix='mortimer-native40-capability-', dir='/private/tmp'))
    directory.chmod(0o700)
    async with storage_scope(db_path=directory / 'identity.db', costs_db_path=directory / 'identity-costs.db',
                             model_preferences_enabled=False) as identity_store:
        async with asyncio.timeout(max(.001, started_at + timeout - time.time())):
            identity = await state_to_thread(claude_tool_runtime_identity)
            expected_schemas = await installed_schemas()
    if not identity_store.cleanup_verified:
        raise CapabilityUnavailable('owned_cleanup_unverified')
    selection(frozen['selection']['profile'], 'subscription', frozen['selection']['model'],
              input_policy=input_policy, task_budget=task_budget)
    if frozen_contract(frozen['selection']['profile'], 'subscription', frozen['selection']['model']) != frozen:
        raise CapabilityUnavailable('frozen_contract_changed')
    frozen = {**frozen, 'runtime': identity, 'host_limits': diagnostic_host_limits(timeout)}
    request = directory / 'request.json'
    request.write_bytes(canonical({'contract': frozen, 'timeout': timeout, 'started_at': started_at}))
    request.chmod(0o600)
    process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).resolve()),
        '--live', '--worker', str(request), cwd=str(directory), env=worker_environment(directory, frozen),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
    owner = _WorkerOwnership(directory, process, failure=asyncio.get_running_loop().create_future())
    async def drain(reader):
        count = 0
        try:
            while raw := await reader.read(65536):
                count += len(raw)
                if count > OUTPUT_BYTES and not owner.failure.done():
                    owner.failure.set_result('worker_output_byte_limit')
                    owner.stop()
                # After overflow discard bounded chunks while retaining the
                # pipe owner; blocking a pipe must not prevent child cleanup.
        except Exception:
            if not owner.failure.done(): owner.failure.set_result('worker_transport_failed')
    owner.readers = tuple(asyncio.create_task(drain(reader)) for reader in (process.stdout, process.stderr))
    async def lifetime():
        await asyncio.gather(process.wait(), *owner.readers, return_exceptions=True)
    owner.lifetime = asyncio.create_task(lifetime())
    try:
        async with asyncio.timeout(max(.001, started_at + timeout - time.time())):
            await asyncio.wait((owner.lifetime, owner.failure), return_when=asyncio.FIRST_COMPLETED)
        if owner.failure.done():
            raise CapabilityUnavailable(owner.failure.result())
        if process.returncode != 0:
            raise CapabilityUnavailable('native_capability_worker_refused')
        path = directory / 'result.json'
        if path.is_symlink() or path.stat().st_size > OUTPUT_BYTES:
            raise CapabilityUnavailable('worker_result_invalid')
        value = json.loads(path.read_bytes())
        validate_capture(value, frozen, expected_schemas=expected_schemas)
        selection(frozen['selection']['profile'], 'subscription', frozen['selection']['model'],
                  input_policy=input_policy, task_budget=task_budget)
        if await state_to_thread(_owned_group_present, process.pid):
            raise CapabilityUnavailable('worker_descendants_unverified')
        owner.cleanup_verified = True  # validated child proof plus actual owner drain
        return value
    finally:
        if not owner.lifetime.done():
            owner.stop()
            try:
                # Admission deadline has already failed. Give the signal-aware
                # worker a separate bounded drain for its native/MCP owners.
                await asyncio.wait_for(asyncio.shield(owner.lifetime), timeout=WORKER_DRAIN_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                owner.retain()
                raise WorkerCleanupUnavailable(owner) from None
        if await state_to_thread(_owned_group_present, process.pid):
            owner.retain()
            raise WorkerCleanupUnavailable(owner) from None


def validate_capture(value, frozen, *, expected_schemas):
    """Reject incomplete or changed worker evidence; never infer true flags."""
    from jarvis.subscription_tools import (PROTOCOL, NATIVE_CONTROL_CONTRACT, CLAUDE_NATIVE_VERSIONS,
        NATIVE_ISOLATION_ENV, NATIVE_PROTOCOL_SOURCE, _claude_tool_argv)
    from jarvis.subscription import _json_digest, _file_digest
    fields = ('native_tool_call_observed', 'unknown_tool_rejected', 'unadvertised_host_tool_rejected',
        'unadvertised_host_tool_side_effect_absent', 'customization_canaries_absent', 'builtins_disabled',
        'system_constraints_observed', 'terminal_success_without_error_items', 'api_credentials_absent',
        'private_mutation_refused_before_ingress', 'native_cleanup_verified', 'storage_cleanup_verified',
        'registry_cleanup_verified')
    try:
        if frozen_contract(frozen['selection']['profile'], 'subscription', frozen['selection']['model']) != {
                key: entry for key, entry in frozen.items() if key not in ('runtime', 'host_limits')}:
            raise ValueError()
        expected_limits = diagnostic_host_limits(frozen['host_limits']['deadline_seconds'])
        if (frozen['host_limits'] != expected_limits or value.get('host_limits') != expected_limits
                or any(type(value['host_limits'].get(key)) is not type(expected)
                       for key, expected in expected_limits.items())):
            raise ValueError()
        pin = pin_reference()
        schemas = value['schemas']
        refs = references(schemas)
        names = [ref.name for ref in refs]
        identity = value['executable']
        if (schemas != expected_schemas or value['frozen_contract'] != frozen or value['model'] != frozen['selection']['model']
                or identity != frozen.get('runtime') or identity['version'] not in CLAUDE_NATIVE_VERSIONS
                or type(value.get('schema_version')) is not int or value['schema_version'] != 1
                or value.get('provider') != 'claude' or value.get('runtime_receipt') is not True
                or value.get('tools_under_test') is not True
                or value.get('servers') != list(support().DEVELOPER_SERVERS)
                or value.get('record_kind') != 'installed_cli_exact_schema_protocol_evidence'
                or len(names) != 40 or len(set(names)) != 40
                or set(names) != set(frozen['declarations']['declared_tool_names'])
                or value['tool_names'] != names or value['protocol'] != PROTOCOL
                or any(value.get(field) is not True for field in fields)
                or any(value.get(field) is not False for field in ('production_route_ready', 'developer_accepted',
                    'workload_quality_accepted', 'mar_i_complete', 'billing_verified', 'full_profile_verified',
                    'provider_token_or_spend_bound_verified'))
                or value['tool_schema_sha256'] != _json_digest([{'name': ref.name,
                    'description': ref.description, 'parameters': dict(ref.parameters)} for ref in refs])
                or _file_digest(Path(identity['path'])) != identity['sha256']
                or value['invocation_sha256'] != _json_digest(_claude_tool_argv(identity['path'], value['model'],
                    '<mcp-config>', '<system-prompt>', names))
                or value['control_protocol_sha256'] != _json_digest(NATIVE_CONTROL_CONTRACT)
                or value['isolation_env_sha256'] != _json_digest(NATIVE_ISOLATION_ENV)
                or value['protocol_source'] != NATIVE_PROTOCOL_SOURCE):
            raise ValueError()
        observation = value['observations']
        for phase in ('live', 'isolation', 'negative'):
            output_bytes = observation[phase]['output_bytes']
            if type(output_bytes) is not int or not 0 < output_bytes <= OUTPUT_BYTES:
                raise ValueError()
        sources = observation['sources']
        if type(sources) is not list or len(sources) != 3:
            raise ValueError()
        source_keys = set()
        hook_keys = set()
        for phase in ('live', 'isolation'):
            part = observation[phase]
            if (part['native_tool_call_observed'] is not True or part['unknown_tool_rejected'] is not True
                    or part['system_constraints_observed'] is not True or part['cleanup_verified'] is not True
                    or part['terminal_success_without_error_items'] is not True
                    or part['observed_models'] != [value['model']] or not part['hook_evidence']
                    or any(item['hook_done'] is not True or item['constraints_sha256'] != digest(CONSTRAINT.encode())
                           for item in part['hook_evidence'])):
                raise ValueError()
            parent = part['parent_request_id']
            if str(uuid.UUID(parent)) != parent or part['origin_task_id'] != f'native-capability:{parent}:0':
                raise ValueError()
            expected = ['repo_read_file'] if phase == 'live' else ['repo_read_file', 'selfedit_finish']
            if (part['native_tool_names'] != ['mcp__mortimer__' + tool for tool in expected]
                    or len(part['native_calls']) != len(expected) or len(part['hook_evidence']) != len(expected)):
                raise ValueError()
            for index, (tool, native_call, hook) in enumerate(zip(expected, part['native_calls'], part['hook_evidence'])):
                args = {'path': REFERENCE} if tool == 'repo_read_file' else {}
                args_hash = digest(canonical(args))
                call_id = native_call['tool_call_id']
                request_id = hook['request_id']
                if (type(request_id) is not str
                        or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}', request_id) is None
                        or (parent, request_id) in hook_keys):
                    raise ValueError()
                hook_keys.add((parent, request_id))
                key = (parent, call_id)
                matched = [entry for entry in sources if (entry['parent_request_id'], entry['tool_call_id']) == key]
                if key in source_keys or len(matched) != 1 or not isinstance(call_id, str) or not call_id:
                    raise ValueError()
                source_keys.add(key)
                source = matched[0]
                task = f'native-capability:{parent}:{index}'
                body = {'ok': True, 'path': REFERENCE, 'bytes': len(pin.raw),
                    'content': pin.raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')} if tool == 'repo_read_file' else {
                    'error': 'outside_public_capability_probe', 'ok': False}
                source_scope = ('repository:' + digest(pin.root.encode())) if tool == 'repo_read_file' else 'host-generated-capability-refusal'
                if (native_call != {'tool_call_id': call_id, 'name': 'mcp__mortimer__' + tool, 'arguments_sha256': args_hash}
                        or hook['parent_request_id'] != parent or hook['tool_call_id'] != call_id
                        or hook['task_id'] != task or hook['tool'] != tool or hook['arguments_sha256'] != args_hash
                        or source['task_id'] != task or source['tool'] != tool or source['argument_digest'] != args_hash
                        or source['policy'] != 'approved_external' or source['source_scope'] != source_scope
                        or source['content_digest'] != digest(source['content'].encode()) or json.loads(source['content']) != body):
                    raise ValueError()
        negative = observation['negative']
        if (negative['native_tool_names'] != ['Bash'] or negative['unadvertised_host_tool_rejected'] is not True
                or negative['cleanup_verified'] is not True):
            raise ValueError()
        for phase, count in (('isolation_http', 3), ('negative_http', 1)):
            packets = observation[phase]
            if (len(packets) != count or any(item['names'] != ['mcp__mortimer__' + name for name in names]
                    or item['schemas_match'] is not True or item['model'] != value['model']
                    or item['canary_absent'] is not True or item['synthetic_auth_only'] is not True for item in packets)):
                raise ValueError()
        if observation['isolation_http'][-1]['constraint_present'] is not True:
            raise ValueError()
        if len(source_keys) != 3:
            raise ValueError()
    except (KeyError, ValueError, TypeError, OSError):
        raise CapabilityUnavailable('worker_result_invalid') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='claude-opus')
    parser.add_argument('--route', default='subscription')
    parser.add_argument('--model')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--timeout', type=float, default=45)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    started_at = time.time()
    try:
        if args.worker is not None:
            if not args.live:
                raise CapabilityUnavailable('explicit_live_worker_required')
            info = args.worker.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise CapabilityUnavailable('owned_worker_request_required')
            packet = json.loads(args.worker.read_bytes())
            if (set(packet) != {'contract', 'timeout', 'started_at'}
                    or type(packet['timeout']) not in (int, float)
                    or not math.isfinite(packet['timeout']) or not 0 < packet['timeout'] <= 90
                    or type(packet['started_at']) not in (int, float)
                    or not math.isfinite(packet['started_at']) or packet['started_at'] > started_at):
                raise CapabilityUnavailable('owned_worker_request_required')
            validate_worker_boundary(args.worker, packet)
            value = asyncio.run(worker_acquire(args.worker.parent, packet))
            with support()._receipt_publication(args.worker.parent / 'result.json') as publish:
                publish(value)
            return 0
        if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 90:
            raise CapabilityUnavailable('invalid_host_deadline')
        contract = frozen_contract(args.profile, args.route, args.model)
        value = {'record_kind': 'native40_capability_dry_run', 'mode': 'dry', 'contract': contract,
            'inference_performed': False, 'runtime_receipt': False, 'developer_accepted': False,
            'mar_i_complete': False, 'production_route_ready': False}
        if args.live:
            if args.output is None: raise CapabilityUnavailable('new_receipt_path_required')
            # Reserve/pin the requested destination before any inference, then
            # atomically link without replacing a concurrently created entry.
            with support()._receipt_publication(args.output) as publish:
                value = asyncio.run(fresh_capture(contract, args.timeout, started_at))
                publish(value)
        elif args.output is not None:
            with support()._receipt_publication(args.output) as publish:
                publish(value)
        print(json.dumps({'record_kind': value['record_kind'], 'model': contract['selection']['model'],
            'tools_under_test': True, 'production_route_ready': False, 'developer_accepted': False,
            'mode': 'live' if args.live else 'dry'}, sort_keys=True))
        return 0
    except (Exception, asyncio.CancelledError):
        print('native_capability_refused', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
