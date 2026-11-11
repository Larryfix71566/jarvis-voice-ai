"""Complete local roadmap observations through the real agent/display path."""
import copy
import json
from pathlib import Path

import pytest

from jarvis.agents.base import _tool_result_observation, TOOL_RESULT_EVENT_MAX
from jarvis.bot.display import build_display_payload
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from mcp_servers.mcp_repo import logic
from tests.unit.test_agent_events import flush, sent
from tests.unit.test_registry_source_policy import registry_for, Session, response
from tests.unit.test_subagent import make_agent
from tests.unit.test_subagent_tool_policy import routed


@pytest.fixture(autouse=True)
def ordinary_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    text = '''<details id="ws-01"><summary>First</summary>
- **Owner:** codex
- **Status:** claimed
''' + 'Large fixture ' * 4000 + '''
</details>
<details id="ws-17"><summary>Final card</summary>
- **Owner:** codex
- **Status:** landed
- [ ] Larry: final acceptance
</details>
'''
    (tmp_path / 'ROADMAP.md').write_text(text)
    return logic.repo_read_file('ROADMAP.md')


def full(result):
    """The full v1 snapshot derived from a compact read result's single text copy."""
    return logic.expand_roadmap_snapshot(result['content'], result['roadmap'])


def display(result):
    return build_display_payload('developer', 'Developer', 'repo_read_file',
                                 {'path': 'ROADMAP.md'}, result)


@pytest.mark.parametrize('classified', [False, True])
async def test_actual_agent_event_displays_final_card_and_preserves_history(source, tmp_path, classified, sent):
    from jarvis.bot.pipeline import make_agent_event_handler

    registry = registry_for('repo_read_file', 'mcp-repo', Session(response(source)), pinned=True, root=tmp_path)
    script = [('tool', 'repo_read_file', {'path': 'ROADMAP.md'}), ('text', 'completed')]
    if classified:
        agent, provider = routed(registry)
        provider._script = script
    else:
        agent, provider = make_agent(script, registry=registry)
    agent.mcp_servers = ['mcp-repo']
    events = []
    handler = make_agent_event_handler(object())
    def observe(event):
        events.append(event)
        handler(event)
    assert await agent.run('Read the synthetic roadmap', observe) == 'completed'
    await flush()
    event = next(e for e in events if e['type'] == 'agent_tool_result')
    assert len(event['result']) > TOOL_RESULT_EVENT_MAX
    delivered = next(m['display'] for m in sent if m['type'] == 'display')
    assert delivered['roadmap'] == full(source)
    assert delivered['roadmap']['schema'] == 'mortimer.roadmap.v1'
    assert delivered['roadmap']['cards'][-1]['id'] == 'WS-17'
    assert 'data_policy' not in delivered  # Projection creates no source grant.
    history = next(m['content'] for m in provider.requests[-1]['messages'] if m['role'] == 'tool')
    assert json.loads(history) == source  # No truncation or projection for model history.


@pytest.mark.parametrize('variant', ['missing', 'array', 'bad-log', 'bad-date', 'nonfinite', 'oversize', 'bad-utf8', 'content-altered', 'no-content', 'full-schema'])
def test_malformed_or_oversize_snapshot_has_explicit_content_free_failure(source, variant):
    data = copy.deepcopy(source)
    snapshot = data['roadmap']
    if variant == 'missing': del data['roadmap']
    elif variant == 'array': data['roadmap'] = []
    elif variant == 'bad-log': snapshot['logs'] = [{'path': 'ROADMAP.md', 'date': 'x', 'sha256': 'y', 'title': 't', 'rows': []}]
    elif variant == 'bad-date': snapshot['provenance']['read_at'] = 'not a timestamp'
    elif variant == 'nonfinite': snapshot['unexpected'] = float('nan')
    elif variant == 'oversize': snapshot['issues'] = ['x' * (1024 * 1024)]
    elif variant == 'bad-utf8': snapshot['issues'] = ['\ud800']
    elif variant == 'content-altered': data['content'] += ' altered after sealing'
    elif variant == 'no-content': del data['content']
    elif variant == 'full-schema': snapshot['schema'] = 'mortimer.roadmap.v1'
    observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, json.dumps(data))
    assert json.loads(observed)['error'] == 'roadmap_display_unavailable'
    payload = display(observed)
    assert payload['title'] == 'Roadmap unavailable'
    assert 'roadmap' not in payload
    assert 'Large fixture' not in json.dumps(payload)


def test_failed_source_and_invalid_json_are_not_silently_dropped():
    for raw in ['{incomplete', '{"ok":false,"error":"synthetic private error"}']:
        observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, raw)
        assert display(observed)['title'] == 'Roadmap unavailable'
        assert 'synthetic private error' not in observed


@pytest.mark.parametrize('tool,args', [
    ('repo_read_file', {'path': 'plain.md'}),
    ('repo_read_file', {'path': './ROADMAP.md'}),
    ('repo_read_file', {'path': 'ROADMAP.md', 'extra': True}),
    ('web_search', {'path': 'ROADMAP.md'}),
])
def test_all_other_observations_keep_the_existing_cap(source, tool, args):
    raw = json.dumps(source)
    assert _tool_result_observation(tool, args, raw) == raw[:TOOL_RESULT_EVENT_MAX]


async def test_tampered_classified_snapshot_cannot_publish_or_continue(source, tmp_path, sent):
    source['roadmap']['cards'] = [{'id': 'WS-17', 'details': 'FORGED_CARD_CANARY'}]
    registry = registry_for('repo_read_file', 'mcp-repo', Session(response(source)), pinned=True, root=tmp_path)
    agent, provider = routed(registry)
    agent.mcp_servers = ['mcp-repo']
    provider._script = [('tool', 'repo_read_file', {'path': 'ROADMAP.md'}), ('text', 'must not run')]
    events = []
    assert (await agent.run('Read fixture', events.append)).startswith('FAILED:')
    assert len(provider.requests) == 1
    assert 'FORGED_CARD_CANARY' not in json.dumps(events)
    assert all('result' not in e for e in events if e['type'] == 'agent_tool_result')


def test_sensitive_observation_retains_cap_and_emit_redacts(source):
    current_sensitive_turn.get().arm('manual', 'private-run')
    raw = json.dumps(source)
    observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, raw)
    assert observed == raw[:TOOL_RESULT_EVENT_MAX]
    agent, _ = make_agent([('text', 'unused')])
    events = []
    agent._emit(events.append, {'type': 'agent_tool_result', 'tool': 'repo_read_file',
                               'arguments': {'path': 'ROADMAP.md'}, 'result': observed})
    assert events == [{'type': 'agent_tool_result', 'tool': 'repo_read_file'}]


def test_current_repository_complete_snapshot_survives_projection(monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(Path(__file__).resolve().parents[2]))
    source = logic.repo_read_file('ROADMAP.md')
    assert source['ok']
    observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, json.dumps(source))
    assert display(observed)['roadmap'] == full(source)
    assert display(observed)['roadmap']['cards']
    assert len(observed.encode('utf-8')) <= 1200 * 1024


def test_snapshot_above_old_size_limit_survives_event_projection(source):
    source['roadmap']['issues'] = ['x' * 550000]
    observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, json.dumps(source))
    assert display(observed)['roadmap'] == full(source)
    assert len(observed.encode()) <= 1200 * 1024


async def test_current_repository_classified_source_reaches_complete_display(monkeypatch):
    from jarvis.privacy_policy import validate_tool_result
    from tests.unit.test_registry_source_policy import execution
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(root))
    source = logic.repo_read_file('ROADMAP.md')
    assert source['ok'], source.get('error')
    arguments = {'path': 'ROADMAP.md'}
    registry = registry_for('repo_read_file', 'mcp-repo', Session(response(source)), pinned=True, root=root)
    scope = execution('repo_read_file', arguments)
    envelope = await registry.call_classified('repo_read_file', arguments, execution_scope=scope)
    policy, content = validate_tool_result(scope, envelope)
    assert policy.level == 'approved_external'
    assert len(envelope.canonical_refs) <= 256
    observed = _tool_result_observation('repo_read_file', arguments, content)
    assert display(observed)['roadmap'] == full(source)


def test_compact_read_result_projects_full_cards_and_drops_content(source):
    assert 'cards' not in source['roadmap']
    observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, json.dumps(source))
    projected = json.loads(observed)
    assert projected['content'] == 'Read-only roadmap snapshot.'
    assert projected['roadmap'] == full(source)
    assert [c['id'] for c in projected['roadmap']['cards']] == ['WS-01', 'WS-17']
    assert 'Large fixture' not in projected['content']


def test_altered_content_after_sealing_yields_roadmap_display_unavailable(source):
    source['content'] = source['content'].replace('landed', 'accepted')
    observed = _tool_result_observation('repo_read_file', {'path': 'ROADMAP.md'}, json.dumps(source))
    assert json.loads(observed) == {'ok': False, 'error': 'roadmap_display_unavailable', 'path': 'ROADMAP.md'}


def test_display_payload_expands_compact_and_keeps_full_snapshot(source):
    expanded = full(source)
    assert display(json.dumps(source))['roadmap'] == expanded
    already_full = {**source, 'roadmap': expanded}
    assert display(json.dumps(already_full))['roadmap'] == expanded
    tampered = {**source, 'content': source['content'] + 'x'}
    payload = display(json.dumps(tampered))
    assert 'roadmap' not in payload
    oversize = copy.deepcopy(source)
    oversize['roadmap']['issues'] = ['x' * (1024 * 1024)]
    assert 'roadmap' not in display(json.dumps(oversize))
