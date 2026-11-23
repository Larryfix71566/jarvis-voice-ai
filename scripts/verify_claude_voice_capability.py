#!/usr/bin/env python3
"""Write the voice tool capability receipt the subscription route requires.

Larry 2026-11-23 (WS-40): voice runs only on the Claude subscription. The
native tool route (jarvis.subscription_tools) refuses every voice turn until
JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT names a receipt that matches the
installed claude CLI, the voice model and the EXACT voice tool menu.

The menu depends on the live sub-agent roster and the kill switches, so the
bot writes it when it builds a session (logs/voice-tool-menu.json, see
jarvis.bot.subscription_llm). This script reads that file and proves, against
the installed CLI:

* live: one real subscription turn where the model calls ``cost_summary``
  through the native gateway and then answers with a fixed word. The host
  answers the call with a synthetic result; no voice handler runs;
* isolated: the same CLI against a local fake provider with planted
  CLAUDE.md, skills, hooks and settings canaries, which must not reach the
  provider, and a tool menu that must be exactly the voice menu;
* negative: the fake provider asks for the built-in Bash tool, which must be
  refused before any host call, with its side effect absent.

Dry by default: ``--live`` runs the proofs and ``--output`` writes the
receipt. The live turn uses the subscription login of the user running it;
the script never reads or sends an API key. Exit 0 on success, 2 on refusal.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_claude_developer_capability import (  # noqa: E402
    OUTPUT_BYTES, CapabilityUnavailable, canonical, digest, observed_session_type,
    tool_menu_observation, unknown_request, wire_tool_names,
)

DEFAULT_MENU = 'logs/voice-tool-menu.json'
PROBE_TOOL = 'cost_summary'
PROBE_RESULT = json.dumps({'ok': True, 'note': 'synthetic capability-probe result; no handler ran'})
DONE = 'MORTIMER_VOICE_PROTOCOL_OK'
CONSTRAINT = ('This voice protocol diagnostic answered its one tool call with a synthetic host '
              'result. No voice handler ran and nothing was spoken, sent or changed.')
MENU_BYTES = 500_000
WORKLOAD = 'voice_supervisor'


def load_menu(path):
    """The recorded voice menu, as the ModelToolReference tuple voice sends."""
    from jarvis.bot.subscription_llm import VOICE_TOOL_MENU_KIND
    from jarvis.model_execution import ModelToolReference
    source = Path(path)
    try:
        if not source.is_file() or source.stat().st_size > MENU_BYTES:
            raise CapabilityUnavailable('voice_tool_menu_missing')
        record = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CapabilityUnavailable('voice_tool_menu_unreadable') from exc
    tools = record.get('tools') if type(record) is dict else None
    if (record.get('record_kind') != VOICE_TOOL_MENU_KIND or record.get('schema_version') != 1
            or record.get('workload') != WORKLOAD or type(record.get('model')) is not str
            or not record['model'].startswith('claude-') or type(tools) is not list or not tools):
        raise CapabilityUnavailable('voice_tool_menu_invalid')
    refs = []
    for tool in tools:
        if (type(tool) is not dict or set(tool) != {'name', 'description', 'parameters'}
                or type(tool['name']) is not str or not tool['name']
                or type(tool['description']) is not str or type(tool['parameters']) is not dict):
            raise CapabilityUnavailable('voice_tool_menu_invalid')
        refs.append(ModelToolReference(tool['name'], tool['parameters'], tool['description']))
    names = [ref.name for ref in refs]
    if len(set(names)) != len(names):
        raise CapabilityUnavailable('voice_tool_menu_invalid')
    if PROBE_TOOL not in names:
        raise CapabilityUnavailable('voice_probe_tool_missing')
    return record['model'], tuple(refs)


def route_model():
    """The model the bot's voice route resolves to in this environment."""
    from jarvis.config import bridge_settings_to_env
    from jarvis.model_routing import resolve_model_route
    bridge_settings_to_env()
    resolved = resolve_model_route(WORKLOAD)
    route = resolved.route
    if (route.name != 'subscription' or route.adapter != 'subscription_runtime'
            or 'tools' not in route.capabilities or route.credential_env or route.base_url):
        raise CapabilityUnavailable('voice_subscription_route_required')
    return resolved.model


def runtime_identity():
    """The installed claude CLI, refused with a readable reason when unpinned."""
    from jarvis.subscription import SubscriptionCapabilityError
    from jarvis.subscription_tools import CLAUDE_NATIVE_VERSIONS, claude_tool_runtime_identity
    try:
        return claude_tool_runtime_identity()
    except SubscriptionCapabilityError as exc:
        pinned = ' or '.join(sorted(version.split()[0] for version in CLAUDE_NATIVE_VERSIONS))
        if 'version' in str(exc):
            raise CapabilityUnavailable(f'claude_cli_version_unverified (needs {pinned})') from exc
        raise CapabilityUnavailable('claude_cli_unavailable') from exc


def _request(parent, index, refs, timeout):
    from jarvis.model_execution import ModelExecutionRequest
    from jarvis.privacy_policy import DataPolicy
    return ModelExecutionRequest(WORKLOAD, f'voice-capability:{parent}:{index}', parent, '',
        tools=refs, data_policy=DataPolicy('approved_external', 'voice-capability-probe'),
        timeout_s=timeout)


async def protocol_round(identity, model, refs, timeout, *, environment=None, expect_bash=False):
    """One native session: the probe tool once, then the fixed reply."""
    from jarvis.subscription import SubscriptionCapabilityError
    parent = str(uuid.uuid4())
    messages = [{'role': 'system', 'content': CONSTRAINT}, {'role': 'user', 'content':
        f'Call {PROBE_TOOL} once with no arguments, then reply exactly {DONE}. '
        'Use no other operation.'}]
    first = _request(parent, 0, refs, timeout)
    Session = observed_session_type()
    session = Session(first, SimpleNamespace(model=model), {'messages': messages}, identity['path'],
                      max_tool_calls=2, environment=environment)
    host_calls = 0
    result = {'native_tool_call_observed': False, 'unknown_tool_rejected': False,
              'system_constraints_observed': False, 'terminal_success_without_error_items': False,
              'unadvertised_host_tool_rejected': False, 'cleanup_verified': False}
    try:
        async with asyncio.timeout(timeout):
            await session.start()
            result['unknown_tool_rejected'] = await unknown_request(session)
            for index in range(3):
                current = _request(parent, index, refs, timeout)
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
                        (message.content or '').strip() == DONE and not expect_bash and host_calls == 1)
                    break
                assistant = {'role': 'assistant', 'content': message.content or None, 'tool_calls': []}
                replies = []
                for call in calls:
                    arguments = json.loads(call.function.arguments or '{}')
                    if call.function.name != PROBE_TOOL or type(arguments) is not dict or host_calls:
                        raise CapabilityUnavailable('voice_probe_called_another_operation')
                    host_calls += 1
                    result['native_tool_call_observed'] = True
                    assistant['tool_calls'].append({'id': call.id, 'type': 'function',
                        'function': {'name': call.function.name, 'arguments': call.function.arguments},
                        **(call.model_extra or {})})
                    replies.append({'role': 'tool', 'tool_call_id': call.id,
                                    'name': call.function.name, 'content': PROBE_RESULT})
                messages += [assistant, *replies, {'role': 'system', 'content': CONSTRAINT}]
            result['system_constraints_observed'] = bool(session.completed) and all(
                pending.hook_done and pending.constraints == CONSTRAINT
                for pending in session.completed.values())
            result['observed_models'] = sorted(session.observed_models)
            result['output_bytes'] = session.output_bytes
            result['hook_evidence'] = list(session.hook_evidence)
            result['native_tool_names'] = list(session.observed_native_tools)
            result['native_calls'] = list(session.native_calls)
            result['native_host_ingress_count'] = session.call_count
            result['host_probe_calls'] = host_calls
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


def _stream_events(message, block, use_tool, arguments):
    yield 'message_start', {'type': 'message_start', 'message': {**message, 'content': [],
        'stop_reason': None, 'usage': {'input_tokens': 8, 'output_tokens': 0}}}
    yield 'content_block_start', {'type': 'content_block_start', 'index': 0,
        'content_block': {**block, 'input': {}} if use_tool else {**block, 'text': ''}}
    yield 'content_block_delta', {'type': 'content_block_delta', 'index': 0,
        'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(arguments)} if use_tool
        else {'type': 'text_delta', 'text': DONE}}
    yield 'content_block_stop', {'type': 'content_block_stop', 'index': 0}
    yield 'message_delta', {'type': 'message_delta', 'delta': {'stop_reason': message['stop_reason'],
        'stop_sequence': None}, 'usage': {'output_tokens': 8}}
    yield 'message_stop', {'type': 'message_stop'}


@asynccontextmanager
async def loopback_fixture(directory, model, refs, *, bash=False):
    """The installed CLI against a local fake provider; never a paid endpoint."""
    marker = 'VOICE40_CUSTOMIZATION_' + uuid.uuid4().hex
    home = Path(directory) / ('negative-home' if bash else 'isolation-home')
    config = home / '.claude'
    config.mkdir(parents=True, mode=0o700)
    for name in ('CLAUDE.md', 'CLAUDE.local.md'):
        (home / name).write_text(marker)
    for name in ('rules/canary.md', 'skills/canary/SKILL.md', 'commands/canary.md', 'agents/canary.md'):
        target = config / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(marker)
    (config / 'settings.json').write_text(json.dumps({'env': {'VOICE40_CANARY': marker},
        'hooks': {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'printf ' + marker}]}]}}))
    canary = home / 'forbidden-bash-side-effect'
    observations = []

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
                    self.send_error(413)
                    return
                packet = json.loads(self.rfile.read(size))
                if type(packet) is not dict:
                    raise ValueError()
            except (ValueError, OSError):
                self.send_error(400)
                return
            if '/messages' not in self.path:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"input_tokens":8}')
                return
            observations.append({**tool_menu_observation(packet.get('tools', []), refs),
                'model': packet.get('model'), 'canary_absent': marker not in json.dumps(packet),
                'constraint_present': CONSTRAINT in json.dumps(packet),
                'synthetic_auth_only': self.headers.get('x-api-key') == 'voice40-synthetic-not-a-key'
                    and self.headers.get('Authorization') is None})
            index = len(observations)
            if index > 2:
                self.send_error(409)
                return
            use_tool = index == 1
            tool_name = 'Bash' if bash else 'mcp__mortimer__' + PROBE_TOOL
            arguments = {'command': 'touch ' + str(canary)} if bash else {}
            block = ({'type': 'tool_use', 'id': 'toolu_voice40_' + str(index), 'name': tool_name,
                      'input': arguments} if use_tool else {'type': 'text', 'text': DONE})
            message = {'id': 'msg_voice40_' + str(index), 'type': 'message', 'role': 'assistant',
                'model': model, 'content': [block], 'stop_reason': 'tool_use' if use_tool else 'end_turn',
                'stop_sequence': None, 'usage': {'input_tokens': 8, 'output_tokens': 8}}
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream' if packet.get('stream') else 'application/json')
            self.end_headers()
            if not packet.get('stream'):
                self.wfile.write(json.dumps(message).encode())
                return
            for event, payload in _stream_events(message, block, use_tool, arguments):
                self.wfile.write(('event: ' + event + '\ndata: ' + json.dumps(payload) + '\n\n').encode())
                self.wfile.flush()

    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.05),
                              name='voice40-loopback', daemon=True)
    thread.start()
    value = {'environment': {'HOME': str(home), 'CLAUDE_CONFIG_DIR': str(config),
        'ANTHROPIC_API_KEY': 'voice40-synthetic-not-a-key',
        'ANTHROPIC_BASE_URL': 'http://127.0.0.1:' + str(server.server_port),
        'CLAUDE_CODE_MAX_RETRIES': '0', 'API_TIMEOUT_MS': '10000'},
        'observations': observations, 'expected_names': wire_tool_names(refs),
        'expected_message_counts': (1, 2) if bash else (2,), 'canary': canary, 'closed': False}
    try:
        yield value
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        await asyncio.to_thread(thread.join, 3)
        value['closed'] = not thread.is_alive()
        if not value['closed']:
            raise CapabilityUnavailable('loopback_cleanup_unverified')


def loopback_failures(value, model):
    """What the fake provider saw that breaks isolation; empty means verified."""
    seen = value['observations']
    failures = []
    if len(seen) not in value['expected_message_counts']:
        failures.append(f'provider_requests={len(seen)}')
    for index, item in enumerate(seen, 1):
        if item['names'] != value['expected_names']:
            failures.append(f'request{index}:tool_names')
        if item['schemas_match'] is not True:
            failures.append(f'request{index}:tool_schemas')
        if item['model'] != model:
            failures.append(f'request{index}:model')
        if not item['canary_absent']:
            failures.append(f'request{index}:customization_canary_present')
        if not item['synthetic_auth_only']:
            failures.append(f'request{index}:credentials')
    return failures


def build_receipt(identity, model, refs, live, isolation, negative, isolated, refused):
    from jarvis.subscription import _json_digest, _subscription_env
    from jarvis.subscription_tools import (
        NATIVE_CONTROL_CONTRACT, NATIVE_ISOLATION_ENV, NATIVE_PROTOCOL_SOURCE, PROTOCOL,
        _claude_tool_argv,
    )
    names = [ref.name for ref in refs]
    isolated_ok = not loopback_failures(isolated, model)
    negative_ok = not loopback_failures(refused, model)
    proof = {
        'native_tool_call_observed': live['native_tool_call_observed'],
        'unknown_tool_rejected': live['unknown_tool_rejected'] and isolation['unknown_tool_rejected'],
        'unadvertised_host_tool_rejected': (negative['unadvertised_host_tool_rejected']
            and negative['native_tool_names'] == ['Bash'] and len(negative['native_calls']) == 1
            and negative['native_host_ingress_count'] == 0 and negative_ok),
        'unadvertised_host_tool_side_effect_absent': not refused['canary'].exists(),
        'customization_canaries_absent': isolated_ok,
        'builtins_disabled': isolated_ok and negative_ok,
        'system_constraints_observed': (live['system_constraints_observed']
            and isolation['system_constraints_observed'] and len(isolated['observations']) == 2
            and isolated['observations'][-1]['constraint_present']),
        'terminal_success_without_error_items': (live['terminal_success_without_error_items']
            and isolation['terminal_success_without_error_items']),
    }
    cleanup = (all(part['cleanup_verified'] for part in (live, isolation, negative))
               and isolated['closed'] and refused['closed'])
    return {'schema_version': 1, 'provider': 'claude', 'model': model, 'executable': identity,
        'protocol': PROTOCOL, 'tool_names': names,
        'tool_schema_sha256': _json_digest([{'name': ref.name, 'description': ref.description,
            'parameters': dict(ref.parameters)} for ref in refs]),
        'invocation_sha256': _json_digest(_claude_tool_argv(identity['path'], model,
            '<mcp-config>', '<system-prompt>', names)),
        'control_protocol_sha256': _json_digest(NATIVE_CONTROL_CONTRACT),
        'isolation_env_sha256': _json_digest(NATIVE_ISOLATION_ENV),
        'protocol_source': NATIVE_PROTOCOL_SOURCE,
        'api_credentials_absent': not any('API_KEY' in key or 'BASE_URL' in key
                                          for key in _subscription_env()),
        **proof, 'native_cleanup_verified': cleanup, 'workload': WORKLOAD,
        'probe_tool': PROBE_TOOL, 'runner_sha256': digest(Path(__file__).read_bytes()),
        'observations': {'live': live, 'isolation': isolation, 'negative': negative,
            'isolation_http': isolated['observations'], 'negative_http': refused['observations'],
            'isolation_failures': loopback_failures(isolated, model),
            'negative_failures': loopback_failures(refused, model)},
        'record_kind': 'voice_native_tool_capability_receipt', 'runtime_receipt': True}


async def acquire(model, refs, timeout):
    identity = await asyncio.to_thread(runtime_identity)
    live = await protocol_round(identity, model, refs, timeout)
    with tempfile.TemporaryDirectory(prefix='mortimer-voice40-', dir='/tmp') as directory:
        async with loopback_fixture(directory, model, refs) as isolated:
            isolation = await protocol_round(identity, model, refs, timeout,
                                             environment=isolated['environment'])
        async with loopback_fixture(directory, model, refs, bash=True) as refused:
            negative = await protocol_round(identity, model, refs, timeout,
                                            environment=refused['environment'], expect_bash=True)
        if await asyncio.to_thread(runtime_identity) != identity:
            raise CapabilityUnavailable('native_runtime_changed')
        receipt = build_receipt(identity, model, refs, live, isolation, negative, isolated, refused)
    return receipt


REQUIRED_TRUE = ('native_tool_call_observed', 'unknown_tool_rejected', 'unadvertised_host_tool_rejected',
    'unadvertised_host_tool_side_effect_absent', 'builtins_disabled', 'customization_canaries_absent',
    'system_constraints_observed', 'api_credentials_absent', 'terminal_success_without_error_items',
    'native_cleanup_verified')


def failed_checks(receipt):
    return [name for name in REQUIRED_TRUE if receipt.get(name) is not True]


def publish(path, receipt):
    """Write owner-only, then confirm the route's own validator accepts it."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.voice-receipt-', dir=str(target.parent))
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(canonical(receipt))
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target.resolve()


def validate_published(path, model, refs):
    from jarvis.subscription_tools import (
        TOOL_CAPABILITY_RECEIPT_ENV, TOOLS_ENABLED_ENV, _validate_native_receipt,
    )
    saved = {name: os.environ.get(name) for name in (TOOLS_ENABLED_ENV, TOOL_CAPABILITY_RECEIPT_ENV)}
    os.environ[TOOLS_ENABLED_ENV] = '1'
    os.environ[TOOL_CAPABILITY_RECEIPT_ENV] = str(path)
    try:
        _validate_native_receipt(model, [ref.name for ref in refs], refs)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--menu', type=Path, default=Path(DEFAULT_MENU),
                        help=f'voice tool menu the bot recorded (default {DEFAULT_MENU})')
    parser.add_argument('--live', action='store_true', help='run the proofs (one subscription turn)')
    parser.add_argument('--timeout', type=float, default=90, help='seconds per proof round')
    parser.add_argument('--output', type=Path, help='where to write the receipt (with --live)')
    args = parser.parse_args(argv)
    try:
        if not 5 <= args.timeout <= 300:
            raise CapabilityUnavailable('invalid_timeout')
        model, refs = load_menu(args.menu)
        routed = route_model()
        if routed != model:
            raise CapabilityUnavailable(f'menu_model_{model}_differs_from_voice_route_{routed}')
        summary = {'mode': 'live' if args.live else 'dry', 'model': model, 'tools': len(refs),
                   'menu_sha256': digest(canonical([[ref.name, ref.description, dict(ref.parameters)]
                                                    for ref in refs]))}
        if not args.live:
            summary['claude_cli'] = runtime_identity()['version']
            summary['next'] = 'rerun with --live --output PATH to write the receipt'
            print(json.dumps(summary, sort_keys=True))
            return 0
        if args.output is None:
            raise CapabilityUnavailable('output_path_required')
        receipt = asyncio.run(acquire(model, refs, args.timeout))
        failures = failed_checks(receipt)
        if failures:
            summary.update(failed=failures,
                           isolation=receipt['observations']['isolation_failures'],
                           negative=receipt['observations']['negative_failures'])
            print(json.dumps(summary, sort_keys=True))
            raise CapabilityUnavailable('voice_protocol_proof_incomplete')
        path = publish(args.output, receipt)
        validate_published(path, model, refs)
        summary.update(receipt=str(path), accepted_by_route=True)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (Exception, asyncio.CancelledError) as exc:
        reason = str(exc) if isinstance(exc, CapabilityUnavailable) else type(exc).__name__
        print(f'voice_capability_refused: {reason}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
