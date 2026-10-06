"""Host-only planning/research provenance and retained action ownership.

Wire metadata contains locators, never spending limits or source approval.
The installed admin keeps the actual cancellation event, budget and exact
published job bytes. A restart cannot promote an unverified legacy job.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import uuid
from dataclasses import dataclass, field

from jarvis.development_attestation import _advisory_context
from jarvis.development_sources import workspace_floor, retain_workspace_floor
from jarvis.model_budget import recover_model_task_budget_for_transport, resolve_model_child_budget
from jarvis.model_routing import ModelRouteError, resolve_policy
from jarvis.privacy_policy import DataPolicy, ToolExecutionScope, issue_tool_result, strictest
from jarvis.runlog.store import SENSITIVE_SENTINEL, get_run

ADVISORY_SOURCE_TOOLS = frozenset({'plan_start', 'plan_status', 'plan_choose', 'plan_adopt',
    'research_compare_start', 'research_status', 'research_save'})
_key = secrets.token_bytes(32)
_lock = threading.RLock()
_active = {}
_issued = {}


def _fail():
    raise ModelRouteError('advisory_source_binding_changed')


def kind_for_tool(name):
    if name not in ADVISORY_SOURCE_TOOLS:
        _fail()
    return 'planning' if name.startswith('plan_') else 'research'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _join(*values):
    # The restriction is monotonic; diagnostic tags must not accumulate
    # exponentially each time the retained action is inspected.
    return DataPolicy(strictest(*values).level, 'advisory-source-floor')


def _run(run, kind, *, running=True):
    role = 'developer' if kind == 'planning' else 'analyst'
    actual = get_run(run['run_id'])['run']
    if (actual.get('agent') != role or actual.get('user_id') != run['user_id']
            or actual.get('session_id') != run['session_id']
            or (running and actual.get('status') != 'running')):
        _fail()
    for key in ('run_id', 'session_id'):
        if str(uuid.UUID(actual[key])) != actual[key]:
            _fail()
    return actual


def _floor(run, workload):
    result = _join(workspace_floor(run),
        DataPolicy(resolve_policy(workload, include_preferences=False).privacy, 'advisory-workload-floor'))
    if any(run.get(key) == SENSITIVE_SENTINEL for key in ('task', 'reply_preview')):
        result = _join(result, DataPolicy('confidential', 'protected-advisory-run'))
    return result


@dataclass
class _Action:
    metadata: dict = field(repr=False)
    owner: object = field(repr=False)
    floor: DataPolicy = field(repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    slot: object = field(default=None, repr=False)
    content_digest: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class AdvisorySourceContext:
    input_floor: DataPolicy = field(repr=False)
    _metadata: tuple = field(repr=False)
    _action: _Action = field(repr=False)
    _seal: str = field(default='', repr=False)

    def as_metadata(self):
        _verify(self)
        return dict(self._metadata)

    @property
    def parent_budget(self):
        _verify(self)
        return self._action.owner

    @property
    def cancel_event(self):
        _verify(self)
        return self._action.cancel_event


def _seal(context):
    return hmac.new(_key, json.dumps((context._metadata, id(context._action),
        context.input_floor.level, context.input_floor.source), separators=(',', ':')).encode(),
        hashlib.sha256).hexdigest()


def _verify(context):
    if (type(context) is not AdvisorySourceContext
            or _issued.get(context._action.metadata['action_generation']) is not context._action
            or not hmac.compare_digest(context._seal, _seal(context))):
        _fail()
    _advisory_context(dict(context._metadata))


def _context(action, run, floor):
    metadata = {**action.metadata, 'caller_run_id': run['run_id'], 'caller_agent': run['agent']}
    _advisory_context(metadata)
    context = AdvisorySourceContext(floor, tuple(sorted(metadata.items())), action)
    object.__setattr__(context, '_seal', _seal(context))
    return context


def prepare_advisory_source(scope, run, *, owner_scope_id, child_scope_id):
    """Recover the original durable budget; no creation or JSON ceilings."""
    if type(scope) is not ToolExecutionScope or scope.parent_request_id != run['run_id']:
        _fail()
    kind = kind_for_tool(scope.tool_name)
    run = _run(run, kind)
    workload = 'planning' if kind == 'planning' else 'council'
    owner = recover_model_task_budget_for_transport(run['agent'], run['run_id'], scope_id=owner_scope_id)
    binding = resolve_model_child_budget(workload, run['run_id'],
        resolve_policy(workload, include_preferences=False).limits)
    if (owner.scope_id != owner_scope_id or binding.owner.scope_id != owner_scope_id
            or binding.child.scope_id != child_scope_id or owner.workload != run['agent']
            or binding.child.workload != workload or binding.parent_request_id != run['run_id']):
        _fail()
    floor = _join(scope.input_policy, _floor(run, workload))
    retain_workspace_floor(run, floor)
    with _lock:
        previous = _active.get(kind)
        if previous is not None and previous.metadata['action_run_id'] == run['run_id']:
            if (previous.metadata['owner_id'] != run['user_id']
                    or previous.metadata['bot_session_id'] != run['session_id']
                    or previous.metadata['owner_scope_id'] != owner_scope_id
                    or previous.metadata['child_scope_id'] != child_scope_id):
                _fail()
            return _context(previous, run, _join(previous.floor, floor))
    metadata = {'owner_id': run['user_id'], 'bot_session_id': run['session_id'],
        'origin_run_id': run['run_id'], 'advisory_kind': kind, 'action_run_id': run['run_id'],
        'action_generation': uuid.uuid4().hex, 'owner_scope_id': owner_scope_id, 'child_scope_id': child_scope_id}
    action = _Action(metadata, owner, floor)
    with _lock:
        _issued[metadata['action_generation']] = action
    return _context(action, run, floor)


def retained_advisory_source(scope, run, slot):
    kind = kind_for_tool(scope.tool_name)
    run = _run(run, kind)
    with _lock:
        action = _active.get(kind)
        if (action is None or action.slot is not slot or action.metadata['action_run_id'] != slot.get('run_id')
                or action.metadata['owner_id'] != run['user_id']
                or action.metadata['bot_session_id'] != run['session_id']
                or action.content_digest != _digest(slot)):
            _fail()
        workload = 'planning' if kind == 'planning' else 'council'
        floor = _join(scope.input_policy, action.floor, _floor(run, workload))
        return _context(action, run, floor)


def refresh_advisory_source(context, run):
    _verify(context)
    metadata = context.as_metadata()
    run = _run(run, metadata['advisory_kind'])
    if (run['run_id'] != metadata['caller_run_id'] or run['user_id'] != metadata['owner_id']
            or run['session_id'] != metadata['bot_session_id']):
        _fail()
    live = _floor(run, 'planning' if metadata['advisory_kind'] == 'planning' else 'council')
    with _lock:
        floor = _join(context.input_floor, context._action.floor, live)
        context._action.floor = floor
    retain_workspace_floor(run, floor)
    return _context(context._action, run, floor)


def activate_advisory_source(context, slot):
    _verify(context)
    with _lock:
        if context.cancel_event.is_set() or slot.get('run_id') != context._action.metadata['action_run_id']:
            _fail()
        context._action.slot = slot
        context._action.content_digest = _digest(slot)
        _active[context._action.metadata['advisory_kind']] = context._action


def check_advisory_source(context, slot, *, allow_cancelled=False):
    _verify(context)
    action = context._action
    with _lock:
        if (action.slot is not slot or _active.get(action.metadata['advisory_kind']) is not action
                or slot.get('run_id') != action.metadata['action_run_id']
                or (not allow_cancelled and action.cancel_event.is_set())):
            _fail()
    origin = _run({'run_id': action.metadata['origin_run_id'], 'user_id': action.metadata['owner_id'],
        'session_id': action.metadata['bot_session_id']}, action.metadata['advisory_kind'], running=False)
    live = _floor(origin, 'planning' if action.metadata['advisory_kind'] == 'planning' else 'council')
    with _lock:
        floor = _join(action.floor, context.input_floor, live)
        action.floor = floor
    retain_workspace_floor(origin, floor)
    return floor


def verify_advisory_job(context, slot):
    floor = check_advisory_source(context, slot, allow_cancelled=True)
    with _lock:
        if context._action.content_digest != _digest(slot):
            _fail()
    return floor


def manual_advisory_source(kind, slot, owner_id):
    """Existing authenticated admin actions retain the same host capability."""
    with _lock:
        action = _active.get(kind)
        if action is None or action.slot is not slot or slot.get('run_id') != action.metadata['action_run_id']:
            return None
        if action.metadata['owner_id'] != owner_id or action.content_digest != _digest(slot):
            _fail()
    origin = _run({'run_id': action.metadata['origin_run_id'], 'user_id': action.metadata['owner_id'],
        'session_id': action.metadata['bot_session_id']}, kind, running=False)
    return _context(action, origin, _join(action.floor, _floor(origin,
        'planning' if kind == 'planning' else 'council')))


def record_advisory_job(context, slot, *, policy=None, allow_cancelled=False):
    floor = check_advisory_source(context, slot, allow_cancelled=allow_cancelled)
    if policy is not None:
        if type(policy) is not DataPolicy:
            _fail()
        floor = _join(floor, policy)
    with _lock:
        context._action.floor = _join(context._action.floor, floor)
        context._action.content_digest = _digest(slot)
    return floor


def cancel_advisory_source(context):
    _verify(context)
    # Signal the exact retained event even when a newer action owns the slot.
    context._action.cancel_event.set()


def save_advisory_document(context, service, path, content, rationale, invoke):
    """Transfer exact owned derivative bytes to an already-authorized workspace.

The target retains its real Developer job identity. The advisory caller stays
Developer or Analyst; no invented actor or response label adopts that target.
"""
    from jarvis.development_sources import _host_session, assert_workspace_session_owner, dispatch_workspace_tool
    from jarvis.privacy_policy import make_tool_execution_scope, validate_tool_result
    floor = verify_advisory_job(context, context._action.slot)
    session = _host_session(service)
    state = session._read()
    target = get_run(state['run_id'])['run']
    metadata = context.as_metadata()
    if (target.get('agent') != 'developer' or target.get('user_id') != metadata['owner_id']
            or target.get('session_id') != metadata['bot_session_id'] or service._kind != 'selfedit'):
        _fail()
    target_context = assert_workspace_session_owner(service, target['run_id'])
    floor = _join(floor, workspace_floor(target))
    retain_workspace_floor(target, floor)
    arguments = {'path': path, 'new_content': content, 'rationale': rationale, 'visual_intent': '', 'proposal': False}
    scope = make_tool_execution_scope(target['run_id'], 'advisory-save-' + metadata['action_generation'],
        'transfer-' + uuid.uuid4().hex, 'edit_propose', arguments, floor)
    try:
        envelope = dispatch_workspace_tool(service, 'edit_propose', arguments,
            execution_scope=scope, context=target_context, invoke=invoke)
        policy, value = validate_tool_result(scope, envelope)
        floor = _join(floor, policy)
        return json.loads(value)
    finally:
        floor = _join(floor, verify_advisory_job(context, context._action.slot))
        retain_workspace_floor(target, floor)
        with _lock:
            context._action.floor = _join(context._action.floor, floor)


def issue_advisory_result(scope, context, value, *, pending=False):
    _verify(context)
    metadata = context.as_metadata()
    if scope.parent_request_id != metadata['caller_run_id'] or kind_for_tool(scope.tool_name) != metadata['advisory_kind']:
        _fail()
    floor = _join(context.input_floor, context._action.floor)
    if not pending:
        floor = _join(floor, check_advisory_source(context, context._action.slot, allow_cancelled=True))
        if context._action.content_digest != _digest(context._action.slot):
            _fail()
    return issue_tool_result(scope, json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False), floor, 'advisory:' + metadata['action_generation'],
        (() if pending else (context._action.content_digest,)))
