"""Host-owned source provenance for the existing VM development services.

Access permission, a provider result's labels, and the selected route are not
source approvals. Only installed adapters and their exact immutable snapshot
and admitted write bytes can classify project source. Unknown workspaces and
foreign baselines remain confidential. No operation runs on the host here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import uuid

from jarvis.model_routing import ModelRouteError, resolve_policy
from jarvis.privacy_policy import (DataPolicy, ToolExecutionScope, issue_tool_result,
                                  make_tool_execution_scope, strictest,
                                  unclassified_tool_result)
from sandbox.artifacts import source_path_allowed
from sandbox.files import capture_sources
from sandbox.runtime import Runtime
from sandbox.session import Session, pin_source_identity
from sandbox.workspace import SandboxWorkspace, TERMINAL, pin_source_session

_key = secrets.token_bytes(32)
_levels = {'approved_external': 1, 'confidential': 2, 'local_only': 3}
_hex = re.compile(r'[0-9a-f]{40,64}\Z')
_project = 'larryfix71566/jarvis-voice-ai'
# Reuse the project's standing cloud-development approval for code/config,
# rather than exporting arbitrary documents, private reports, or runtime data.
_code_roots = {'jarvis', 'sandbox', 'mcp_servers', 'macos', 'web', 'scripts',
               'tests', 'config', 'skills', '.github'}
_code_files = {'pyproject.toml', 'requirements.txt', 'requirements-lock.txt',
               'package.json', 'package-lock.json', 'uv.lock'}
_reference_files = {'README.md', 'AGENTS.md', 'CLAUDE.md', 'docs/ARCHITECTURE.md',
                    'docs/REPO_MAP.md', 'docs/README.md'}
_phases = {'creating', 'starting', 'editing', 'validating', 'validated',
           'validation_failed', 'publishing', 'publication_pending', *TERMINAL}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _floor(workload):
    # Configuration is host-owned. A selected route never supplies this floor.
    return DataPolicy(resolve_policy(workload, include_preferences=False).privacy,
                      'development-workload-floor')


def _secure(path: Path, home: Path, *, directory=False):
    """Reject redirectable host records; mutable records are rechecked each call."""
    relative = path.relative_to(home)
    for current in [home, *(home.joinpath(*relative.parts[:i])
                            for i in range(1, len(relative.parts) + 1))]:
        info = current.lstat()
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o022):
            raise ModelRouteError('development_source_record_invalid')
    info = path.lstat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ModelRouteError('development_source_record_invalid')
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ModelRouteError('development_source_record_invalid')
    return (info.st_dev, info.st_ino)


@dataclass(frozen=True)
class DevelopmentSourceContext:
    """Local capability; exported metadata alone can never reproduce it."""
    input_floor: DataPolicy = field(repr=False)
    _service: object = field(repr=False)
    _session: object = field(repr=False)
    _metadata: tuple = field(repr=False)
    _identity: tuple = field(repr=False)
    _pins: tuple = field(repr=False)
    _seal: str = field(default='', repr=False)

    def as_metadata(self):
        _verify_context(self, self._service)
        return dict(self._metadata)


def _seal(context):
    material = (id(context._service), id(context._session), context._metadata,
                context._identity, context._pins, context.input_floor.level,
                context.input_floor.source)
    return hmac.new(_key, json.dumps(material, sort_keys=True,
                                    separators=(',', ':')).encode(), hashlib.sha256).hexdigest()


def _make_context(service, session, metadata, identity, pins, floor):
    context = DevelopmentSourceContext(floor, service, session,
        tuple(sorted(metadata.items())), tuple(identity), tuple(pins))
    object.__setattr__(context, '_seal', _seal(context))
    return context


def _verify_context(context, service):
    if (type(context) is not DevelopmentSourceContext or context._service is not service
            or type(context.input_floor) is not DataPolicy or type(context._seal) is not str
            or not hmac.compare_digest(context._seal, _seal(context))):
        raise ModelRouteError('development_source_context_invalid')


def _host_session(service):
    # Duck-typed protocol implementations are usable in legacy mode, but they
    # cannot assert an installed sandbox source or session authority.
    from jarvis.selfedit.service import SelfEditService
    from jarvis.agents.workspace import AppWorkspace
    from jarvis.skill_authoring import SkillAuthoringService

    if not isinstance(service, (SelfEditService, AppWorkspace, SkillAuthoringService)):
        raise ModelRouteError('development_session_unverified')
    runtime = service._runtime()
    if type(runtime) is not Runtime:
        raise ModelRouteError('development_session_unverified')
    _secure(runtime.workspaces / (runtime._key(service._repository(), service._kind) + '.json'),
            runtime.controller.home)
    session = service._session()
    if type(session) is not Session or session.controller is not runtime.controller:
        raise ModelRouteError('development_session_unverified')
    return session


def _snapshot(service, session, expected_job, *, terminal=False):
    home = session.controller.home
    _secure(session.directory, home, directory=True)
    _secure(session.directory / 'session.json', home)
    state = session._read()
    cancelled = (session.directory / 'cancelled.json').exists()
    if (state.get('id') != session.id or state.get('run_id') != expected_job
            or state.get('kind') != service._kind
            or state.get('repository', '').casefold() != service._repository().casefold()
            or not isinstance(state.get('ref'), str) or not _hex.fullmatch(state['ref'])
            or state.get('phase') not in _phases
            or (not terminal and state.get('phase') in TERMINAL)
            or (not terminal and cancelled)):
        raise ModelRouteError('development_session_owner_mismatch')
    if cancelled:
        state['phase'] = 'cancelled'
    task = session.controller.task_dir(state['task'])
    source = task / 'input' / 'source.tar'
    source_pin = _secure(source, home)
    _secure(task / 'state.json', home)
    record = session.controller.read(state['task'])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if record.get('source_commit') != state['ref'] or record.get('source_sha256') != digest:
        raise ModelRouteError('development_source_snapshot_changed')
    files = session._files(state)
    journal = task / 'files.json'
    if journal.exists():
        _secure(journal, home)
    for lock_path in (session.directory / 'session.lock', task / 'files.lock'):
        if lock_path.exists():
            _secure(lock_path, home)
    identity = (session.id, state['task'], state['run_id'], state['ref'],
                state['repository'].casefold(), state['kind'], digest,
                files.baseline.fingerprint)
    pins = (_secure(session.directory, home, directory=True), source_pin)
    return state, identity, pins


def _owner_context(service, parent_request_id, *, terminal=False):
    try:
        session = _host_session(service)
        state, identity, pins = _snapshot(service, session, parent_request_id, terminal=terminal)
        return _make_context(service, session, {'developer_run_id': parent_request_id,
            'sandbox_session_id': session.id, 'sandbox_task_id': state['task'],
            'sandbox_job_id': parent_request_id, 'source_commit': state['ref']}, identity, pins,
            _floor('app_builder' if service._kind == 'app-build' else 'developer'))
    except ModelRouteError:
        raise
    except Exception:
        raise ModelRouteError('development_session_unverified') from None


def assert_workspace_session_owner(service, parent_request_id):
    return _owner_context(service, parent_request_id)


def _live(service, parent, context, *, terminal=False):
    if context is None:
        context = _owner_context(service, parent, terminal=terminal)
    _verify_context(context, service)
    if dict(context._metadata).get('developer_run_id') != parent:
        raise ModelRouteError('development_session_owner_mismatch')
    try:
        session = _host_session(service)
        if session.id != context._session.id or session.directory != context._session.directory:
            raise ModelRouteError('development_session_changed')
        state, identity, pins = _snapshot(service, session,
            dict(context._metadata)['sandbox_job_id'], terminal=terminal)
    except ModelRouteError:
        raise
    except Exception:
        raise ModelRouteError('development_session_unverified') from None
    if identity != context._identity or pins != context._pins:
        raise ModelRouteError('development_session_changed')
    return context, state


def creator_context(service, state, run):
    """Mint from an authenticated admin's durable creator/run association.

    Metadata-only test/foreign services get no sandbox source authority. The
    seven bindings still authenticate unknown results under confidential policy.
    """
    try:
        if (type(state) is not dict or type(run) is not dict
                or run.get('agent') != 'developer' or run.get('status') != 'running'
                or state.get('operation') != 'draft' or state.get('cancel_requested')
                or state.get('developer_run_id') != run.get('run_id')
                or state.get('bot_session_id') != run.get('session_id')
                or (state.get('user_id') is not None and state['user_id'] != run.get('user_id'))):
            raise ValueError()
        metadata = {'owner_id': run['user_id'], 'bot_session_id': run['session_id'],
            'request_id': state['request_id'], 'developer_run_id': run['run_id'],
            'creator_revision': state['creator_revision'], 'skill_id': state['skill_id'],
            'sandbox_job_id': state['sandbox_job_id']}
        for name in ('bot_session_id', 'request_id', 'developer_run_id', 'sandbox_job_id'):
            if str(uuid.UUID(metadata[name])) != metadata[name]:
                raise ValueError()
        if (not isinstance(metadata['owner_id'], str) or not metadata['owner_id']
                or len(metadata['owner_id']) > 64
                or not re.fullmatch(r'[0-9a-f]{64}', metadata['creator_revision'])
                or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', metadata['skill_id'])):
            raise ValueError()
        floor = _floor('developer')
        from jarvis.runlog.store import SENSITIVE_SENTINEL
        if any(run.get(key) == SENSITIVE_SENTINEL for key in ('task', 'task_preview', 'reply_preview')):
            floor = strictest(floor, DataPolicy('confidential', 'protected-developer-run'))
        try:
            session = _host_session(service)
        except ModelRouteError:
            if isinstance(service, SandboxWorkspace):
                # A broken installed source proof is a refusal; it must not
                # be converted into a duck service and invoked anyway.
                raise
            # No approved content can be issued from this context.
            return _make_context(service, None, metadata, (), (), floor)
        if (service._kind != 'skill-authoring-' + metadata['skill_id']
                or service.expected_job_id != metadata['sandbox_job_id']):
            raise ValueError()
        live, identity, pins = _snapshot(service, session, metadata['sandbox_job_id'])
        for key, value in {'sandbox_session_id': session.id, 'sandbox_task_id': live['task'],
                           'source_commit': live['ref']}.items():
            if state.get(key) is not None and state[key] != value:
                raise ValueError()
            metadata[key] = value
        return _make_context(service, session, metadata, identity, pins, floor)
    except Exception:
        raise ModelRouteError('creator_source_context_invalid') from None


def workspace_status_for_owner(service, parent_request_id, *, context=None):
    context, state = _live(service, parent_request_id, context, terminal=True)
    return {'active': state['phase'] not in TERMINAL, 'phase': state['phase'],
            'session_id': context._session.id, 'sandbox_task': state['task'],
            'proposal_count': len(state.get('proposals', [])),
            'validated_ok': state['phase'] in {'validated', 'publishing', 'publication_pending'}}


def cancel_workspace_session_for_owner(service, parent_request_id, *, context=None):
    context, _ = _live(service, parent_request_id, context)
    # Cancel the pinned object. Never re-resolve service.cancel() after proof.
    with pin_source_identity(context._session, context._identity):
        return context._session.cancel()


def _project_code(context, path):
    return (context._identity[4] == _project and source_path_allowed(path)
            and (path.split('/')[0] in _code_roots or path in _code_files
                 or path in _reference_files))


def _proposal_plan(service, context, state, arguments):
    """Rebuild the installed proposal transform from the pinned inert base."""
    from jarvis.selfedit import proposals
    from jarvis.selfedit.allowlist import CORE, ROUTINE
    from jarvis.selfedit.service import SelfEditService

    if (not isinstance(service, SelfEditService) or type(arguments.get('path')) is not str
            or type(arguments.get('new_content')) is not str
            or type(arguments.get('rationale', '')) is not str
            or set(arguments) - {'path', 'new_content', 'rationale', 'visual_intent', 'proposal'}):
        return None
    target = arguments['path'].strip()
    if (not source_path_allowed(target) or proposals.is_proposal_path(target)
            or not (service.is_human_only(target) or (
                arguments.get('proposal') is True and target.startswith('tests/')
                and service._tier(target) in {CORE, ROUTINE}))):
        return None
    files = context._session._files(state)
    if files.baseline.fingerprint != context._identity[7]:
        raise ModelRouteError('development_source_snapshot_changed')
    baseline = next((file for file in files.baseline.files if file.path == target), None)
    patch_path = proposals.proposal_path(target)
    patch_base = next((file for file in files.baseline.files if file.path == patch_path), None)
    try:
        text = proposals.render(target, baseline.data.decode('utf-8') if baseline else None,
                                arguments['new_content'], arguments.get('rationale', ''),
                                baseline.mode if baseline else 0o644)
    except (UnicodeError, ValueError):
        return None
    return target, baseline, patch_path, patch_base, text


def _proposal_source(context, plan, arguments, observations, result, after):
    """Approve only the exact saved patch and the host's unchanged approval notice."""
    from jarvis.selfedit import proposals

    target, baseline, patch_path, patch_base, text = plan
    expected_result = {
        'ok': True, 'path': target, 'proposal': True, 'proposal_file': patch_path,
        'diff': text[text.index('diff --git'):],
        'summary': f'{target} was NOT changed. The change is saved as a proposal ({patch_path}) for Larry to approve and apply himself.',
    }
    expected_bases = [file for file in (baseline, patch_base) if file is not None]
    if result != expected_result or len(observations) != len(expected_bases) + 1:
        return None
    levels = []
    for task, digest, file, origin, level in observations:
        if task != context._identity[1] or digest != context._identity[7] or level not in _levels:
            return None
        levels.append(DataPolicy(level, 'verified-proposal-observation'))
    for observation, origin in zip(observations, expected_bases):
        if observation[2] != origin or observation[3] != origin:
            return None
    written = observations[-1][2]
    if (written.path != patch_path or written.data != text.encode('utf-8')
            or written.mode != (patch_base.mode if patch_base else 0o644)
            or observations[-1][3] != patch_base):
        return None
    previous = patch_base.data.decode('utf-8', errors='replace') if patch_base else ''
    saved = {
        'path': patch_path,
        'rationale': proposals.rationale_for(target, arguments.get('rationale', ''), proposals.content_digest(text)),
        'diff': ''.join(difflib.unified_diff(previous.splitlines(keepends=True), text.splitlines(keepends=True),
                                         fromfile='a/' + patch_path, tofile='b/' + patch_path)),
        'visual_intent': '',
    }
    records = after.get('proposals', [])
    if (type(records) is not list or any(type(item) is not dict for item in records)
            or [item for item in records if item.get('path') == patch_path] != [saved]):
        return None
    if ((baseline is not None and not _project_code(context, target))
            or (patch_base is not None and not _project_code(context, patch_path))):
        levels.append(DataPolicy('confidential', 'private-proposal-baseline'))
    policy = strictest(context.input_floor, *levels)
    references = (target, patch_path, hashlib.sha256(written.data).hexdigest())
    if baseline is not None:
        references += (hashlib.sha256(baseline.data).hexdigest(),)
    return policy, references


def _edit_observation(context, arguments, observations):
    if len(observations) not in {1, 2}:
        return None
    task, digest, file, baseline, level = observations[-1]
    if (task != context._identity[1] or digest != context._identity[7]
            or file.path != arguments.get('path') or level not in _levels):
        return None
    if baseline is None:
        if len(observations) != 1:
            return None
    elif (len(observations) != 2
          or observations[0][0:2] != (task, digest)
          or observations[0][2] != baseline or observations[0][3] != baseline
          or observations[0][4] not in _levels):
        return None
    return task, digest, file, baseline, level


def _protect_unbound_proposal_bytes(context, plan, observations, state):
    """An observed write outside the authenticated render cannot approve later reads."""
    _, _, path, base, text = plan
    if not any(file.path == path and (file.data != text.encode('utf-8')
               or file.mode != (base.mode if base else 0o644))
               for _, _, file, _, _ in observations):
        return
    with pin_source_session(context._service, context._session, context._identity):
        files = context._session._files(state)
        with files._locked():
            journal = files._journal()
            level = journal.get('source_floor', 'confidential')
            if level not in _levels:
                level = 'confidential'
            journal['source_floor'] = max((level, 'confidential'), key=_levels.get)
            files._save(journal)


def _invoke(service, name, args):
    if name == 'file_read':
        return service.read_file(args['path'])
    if name == 'edit_propose':
        return service.propose_edit(args['path'], args['new_content'], args.get('rationale', ''),
                                    args.get('visual_intent', ''))
    if name == 'session_validate':
        return service.validate()
    if name == 'session_submit':
        return service.submit()
    if name == 'session_decline':
        return {'ok': False, 'declined': True, 'reason': args['reason']}
    return {'ok': False, 'error': 'development_tool_unavailable'}


def dispatch_workspace_tool(service, name, arguments, *, execution_scope, context=None, invoke=None):
    """Execute once, classify before return, and reject changed session bindings."""
    if type(execution_scope) is not ToolExecutionScope:
        raise ModelRouteError('development_tool_binding_invalid')
    expected = make_tool_execution_scope(execution_scope.parent_request_id,
        execution_scope.task_id, execution_scope.tool_call_id, name, arguments,
        execution_scope.input_policy)
    if (type(execution_scope) is not ToolExecutionScope or expected.tool_name != execution_scope.tool_name
            or expected.argument_digest != execution_scope.argument_digest):
        raise ModelRouteError('development_tool_binding_invalid')
    if context is not None:
        _verify_context(context, service)
    if context is not None and context._session is None:
        if dict(context._metadata).get('developer_run_id') != execution_scope.parent_request_id:
            raise ModelRouteError('development_tool_binding_invalid')
        result = invoke() if invoke else _invoke(service, name, arguments)
        unknown = unclassified_tool_result(execution_scope, result)
        return issue_tool_result(execution_scope, unknown.content,
            strictest(context.input_floor, unknown.policy), unknown.source_scope)
    context, before = _live(service, execution_scope.parent_request_id, context)
    baseline_level = 'approved_external' if context._identity[4] == _project else 'confidential'
    proposal = _proposal_plan(service, context, before, arguments) if name == 'edit_propose' else None
    input_floor = strictest(context.input_floor, execution_scope.input_policy)
    if proposal is not None:
        target, baseline, patch_path, patch_base, _ = proposal
        if ((baseline is not None and not _project_code(context, target))
                or (patch_base is not None and not _project_code(context, patch_path))):
            # The new patch contains source-derived bytes. Persist this floor
            # before any guest write, so a later patch read cannot downgrade a
            # private baseline even if its target is never itself changed.
            input_floor = strictest(input_floor, DataPolicy('confidential', 'private-proposal-baseline'))
    with pin_source_session(service, context._session, context._identity), capture_sources(
            input_floor.level, baseline_level,
            baseline_policy=lambda path: baseline_level if _project_code(context, path) else 'confidential') as capture:
        result = invoke() if invoke else _invoke(service, name, arguments)
    _, after = _live(service, execution_scope.parent_request_id, context, terminal=name == 'session_submit')
    source = DataPolicy('confidential', 'unclassified-development-source')
    refs = (context._identity[6], context._identity[7])
    if name == 'session_validate' and type(result) is dict and type(result.get('ok')) is bool:
        # Names come from the installed host check profile. Neither guest log
        # text nor arbitrary package-validator diagnostics grant approval.
        names = {check[0] for check in context._session.profile.checks}
        checks = []
        for check in result.get('checks', []):
            if type(check) is dict and check.get('name') in names:
                checks.append({'name': check['name'], 'ok': check.get('ok') is True,
                               'output': 'See the saved sandbox check log.'})
        result = {'ok': result['ok'], 'checks': checks}
        source = context.input_floor
    elif type(result) is dict and result.get('ok') is not True:
        # Installed failures expose a fixed control category, never source text.
        if name == 'session_decline' and result.get('declined') is True:
            result = {'ok': False, 'declined': True, 'reason': arguments['reason']}
        else:
            result = {'ok': False, 'error': 'development_operation_failed'}
        source = context.input_floor
    elif proposal is not None and type(result) is dict and result.get('proposal') is True:
        verified = _proposal_source(context, proposal, arguments, capture.observations, result, after)
        if verified is not None:
            source, proposal_refs = verified
            refs += proposal_refs
        else:
            _protect_unbound_proposal_bytes(context, proposal, capture.observations, after)
    elif name in {'file_read', 'edit_propose'} and type(result) is dict:
        observation = (capture.observations[0] if name == 'file_read' and len(capture.observations) == 1
                       else _edit_observation(context, arguments, capture.observations)
                       if name == 'edit_propose' else None)
        if observation is None:
            content = json.dumps(result, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
            return issue_tool_result(execution_scope, content, strictest(context.input_floor, source),
                                     'development:' + context._identity[0], refs)
        task, baseline_digest, file, baseline, level = observation
        if (task == context._identity[1] and baseline_digest == context._identity[7]
                and file.path == arguments.get('path') and result.get('path') == file.path):
            if baseline is not None and not _project_code(context, file.path):
                level = strictest(DataPolicy(level, 'admitted-write'), DataPolicy()).level
            if name == 'file_read':
                exact = (result.get('content') == file.data.decode('utf-8')
                         and not set(result) - {'ok', 'path', 'content', 'human_only', 'note'})
                if exact:
                    # Human-only guidance is rebuilt locally; returned extras
                    # cannot smuggle unrelated data under a file's approval.
                    human_only = result.get('human_only') is True
                    result = {'ok': True, 'path': file.path, 'content': result['content']}
                    if human_only:
                        result['human_only'] = True
                        result['note'] = 'Human-only source: read-only; changes require the existing proposal approval.'
            else:
                previous = baseline.data.decode('utf-8', errors='replace') if baseline else ''
                diff = ''.join(difflib.unified_diff(previous.splitlines(keepends=True),
                    arguments['new_content'].splitlines(keepends=True),
                    fromfile='a/' + file.path, tofile='b/' + file.path))
                exact = (file.data == arguments['new_content'].encode()
                         and set(result) == {'ok', 'path', 'diff'} and result['diff'] == diff)
            if exact:
                source = DataPolicy(level, 'verified-development-bytes')
                refs += (file.path, hashlib.sha256(file.data).hexdigest())
    elif name == 'session_submit' and type(result) is dict and result.get('ok') is True:
        publication = after.get('publication')
        if type(publication) is dict:
            number = publication.get('number')
            url = f"https://github.com/{after['repository']}/pull/{number}"
            if (after['phase'] == 'published' and type(number) is int and number > 0
                    and publication.get('ok') is True and publication.get('url') == url
                    and result.get('number') == number and result.get('url') == url
                    and result.get('pr_number') == number and result.get('pr_url') == url
                    and re.fullmatch(r'[0-9a-f]{40,64}', publication.get('commit', ''))
                    and re.fullmatch(r'[0-9a-f]{64}', publication.get('candidate', ''))):
                result = {'ok': True, 'pr_number': number, 'pr_url': url,
                          'number': number, 'url': url, 'commit': publication['commit'],
                          'candidate': publication['candidate']}
                source = context.input_floor
    content = json.dumps(result, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    return issue_tool_result(execution_scope, content, strictest(context.input_floor, source),
                             'development:' + context._identity[0], refs)
