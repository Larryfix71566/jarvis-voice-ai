"""Offline roadmap read/refresh contracts; no model, network or mailbox calls."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from jarvis.bot.console_protocol import validate_request, ALLOWED_ACTIONS
from jarvis.bot.console_actions import build_console_action_tool
from jarvis.bot.display import build_display_payload
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result, issue_tool_result
from tests.unit.test_console_voice_bridge import bridge, SESSION, GENERATION


@pytest.fixture(autouse=True)
def enabled_console(monkeypatch):
    # Exercise the enabled feature independently of production defaults or
    # another test's environment bridging. A separate test pins the off gate.
    monkeypatch.setenv('JARVIS_COMMAND_CONSOLE_ENABLED', 'true')


def request(**args):
    return dict(type='console/request', version=1, session_id=SESSION, generation=GENERATION,
                request_id=str(uuid.uuid4()), revision=0, action='roadmap_control',
                target=str(uuid.uuid4()), args={'operation': 'replace', **args})


@pytest.mark.parametrize('args', [
    {'owners': ['codex', 'claude'], 'topics': ['interface'], 'states': ['open']},
    {'operation': 'refine', 'owners': []}, {'operation': 'clear'}, {'operation': 'refresh'},
    {'operation': 'focus', 'workstreams': ['WS-17']},
    {'checklist': 'larry', 'blockers': True, 'period': 'this_week'},
])
def test_typed_roadmap_wire_accepts_supported_controls(args):
    assert validate_request(request(**args))['args'] == request(**args)['args']
    assert len(ALLOWED_ACTIONS) <= 100


@pytest.mark.parametrize('args', [
    {'operation': []}, {'checklist': {}}, {'period': []}, {'blockers': 1},
    {'owners': ['unknown']}, {'authors': ['unknown']}, {'states': ['merged']},
    {'topics': [' ']}, {'topics': ['x'] * 5}, {'topics': [True]},
    {'workstreams': ['../ROADMAP.md']}, {'workstreams': ['WS-١٧']}, {'operation': 'refresh', 'owners': []},
    {'operation': 'focus', 'workstreams': []}, {'operation': 'focus', 'workstreams': ['WS-1', 'WS-2']},
    {'operation': 'clear', 'path': '.env'}, {'states': None},
])
def test_invalid_filters_refuse_without_type_errors(args):
    with pytest.raises(ValueError):
        validate_request(request(**args))


def read_helper(*, sensitive=False):
    # Compile the actual helper, avoiding pipeline startup (STT/TTS/model clients).
    path = Path(__file__).resolve().parents[2] / 'jarvis/bot/pipeline.py'
    module = ast.parse(path.read_text())
    node = next(n for n in module.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_read_console_roadmap')
    ns = dict(Any=object, asyncio=asyncio, json=json, DataPolicy=DataPolicy,
              make_tool_execution_scope=make_tool_execution_scope, validate_tool_result=validate_tool_result,
              get_run_id=lambda: None, _voice_is_sensitive=lambda: sensitive,
              build_display_payload=build_display_payload)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
    return ns['_read_console_roadmap']


def body():
    return {'path': 'ROADMAP.md', 'content': 'long source', 'roadmap': {'cards': [
        {'id': 'WS-01', 'details': 'x' * 31000}, {'id': 'WS-17', 'details': 'final card'}]}}


class Registry:
    def __init__(self, *, privacy='approved_external', invalid=False):
        self.privacy, self.invalid, self.calls = privacy, invalid, []

    async def call_classified(self, tool, arguments, *, execution_scope):
        self.calls.append((tool, arguments, execution_scope))
        assert tool == 'repo_read_file' and arguments == {'path': 'ROADMAP.md'}
        if self.invalid:
            return body()  # Raw MCP JSON must not acquire host authority.
        return issue_tool_result(execution_scope, json.dumps(body()), DataPolicy(self.privacy, 'test-source'), 'repo', ('ROADMAP.md',))


def runtime(registry):
    return SimpleNamespace(registry=registry, settings=SimpleNamespace(jarvis_timezone='America/New_York'))


async def test_refresh_reads_only_fixed_source_with_bound_policy_and_full_final_card():
    registry = Registry()
    result = await read_helper()(runtime(registry), request(operation='refresh'))
    assert len(registry.calls) == 1
    assert result['roadmap']['cards'][-1]['id'] == 'WS-17'
    assert len(result['roadmap']['cards'][0]['details']) > 30000
    assert result['roadmap_timezone'] == 'America/New_York'
    assert result['data_policy'] == 'approved_external'
    assert result['title'] == 'Project roadmap'


@pytest.mark.parametrize('sensitive,privacy,invalid', [(True, 'approved_external', False), (False, 'confidential', False), (False, 'approved_external', True)])
async def test_refresh_never_exports_sensitive_or_unsealed_source(sensitive, privacy, invalid):
    with pytest.raises(ValueError):
        await read_helper(sensitive=sensitive)(runtime(Registry(privacy=privacy, invalid=invalid)), request(operation='refresh'))


async def test_actual_console_refresh_deduplicates_and_rejects_stale_without_read():
    *_, ns = bridge(with_sender=True)
    calls, sent = [], []
    async def read(rt, req):
        calls.append(req)
        return {'roadmap': {'cards': []}}
    async def send(transport, response):
        sent.append(dict(response))
    ns.update(_read_console_roadmap=read, send_app_message=send)
    req = request(operation='refresh')
    await ns['handle_console'](req)
    await ns['handle_console'](req)
    assert len(calls) == 1
    assert sent[0] == sent[1]
    assert sent[0]['code'] == 'roadmap_snapshot'
    stale = request(operation='refresh'); stale['generation'] = str(uuid.uuid4())
    await ns['handle_console'](stale)
    assert len(calls) == 1 and sent[-1]['code'] == 'stale_session'


async def test_actual_console_failed_refresh_keeps_payload_out_of_error():
    *_, ns = bridge(with_sender=True)
    sent = []
    async def fail(*args):
        raise RuntimeError('PRIVATE-EXCEPTION-CANARY')
    async def send(transport, response):
        sent.append(response)
    ns.update(_read_console_roadmap=fail, send_app_message=send)
    await ns['handle_console'](request(operation='refresh'))
    assert sent[0]['status'] == 'error'
    assert 'data' not in sent[0]
    assert 'PRIVATE' not in repr(sent)


async def test_voice_waits_for_native_applied_summary_not_predicted_success():
    reqs = []
    async def send(req): reqs.append(req)
    async def settled(_): return {'status': 'ok', 'summary': 'Roadmap: 2 of 22 workstreams. owners: codex'}
    _, handler = build_console_action_tool(send, session_id=SESSION, generation=GENERATION, await_result=settled)
    summary = await handler({'action': 'roadmap_control', 'target': str(uuid.uuid4()), 'args': {'operation': 'refine', 'owners': ['codex']}})
    assert summary == 'Roadmap: 2 of 22 workstreams. owners: codex'
    assert reqs[0]['args']['operation'] == 'refine'


async def test_console_kill_switch_prevents_roadmap_read(monkeypatch):
    monkeypatch.setenv('JARVIS_COMMAND_CONSOLE_ENABLED', 'false')
    *_, ns = bridge(with_sender=True)
    async def forbidden(*args):
        pytest.fail('disabled console performed work')
    ns.update(_read_console_roadmap=forbidden, send_app_message=forbidden)
    await ns['handle_console'](request(operation='refresh'))
