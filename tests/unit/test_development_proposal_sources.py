"""Authenticated human-only patch data; no target write, VM, or publication."""
import hashlib
import json

import pytest

from jarvis.selfedit import proposals
from jarvis.selfedit.allowlist import Allowlist
from sandbox.artifacts import Candidate
from sandbox.durable import atomic_json
from tests.unit.test_development_sources import workspace, dispatch

CANARY = 'SYNTHETIC_PRIVATE_PROPOSAL_BASELINE_61924'


def args(path='config/protected.json'):
    return {'path': path, 'new_content': '{"public": true}\n', 'rationale': 'public fixture'}


def test_exact_human_only_proposal_remains_usable_without_changing_target(workspace):
    before = workspace.guest['config/protected.json']
    policy, result, envelope = dispatch(workspace, 'edit_propose', args())
    patch_path = proposals.proposal_path('config/protected.json')
    expected = proposals.render('config/protected.json', '{}', args()['new_content'], 'public fixture')
    assert policy.level == 'approved_external'
    assert result['proposal'] is True and result['proposal_file'] == patch_path
    assert 'was NOT changed' in result['summary'] and 'Larry to approve' in result['summary']
    assert result['diff'] == expected[expected.index('diff --git'):]
    assert workspace.guest[patch_path] == expected.encode()
    assert workspace.guest['config/protected.json'] == before
    writes = [Candidate.decode(json.dumps(call['candidate']).encode())
              for call in workspace.calls if call['operation'] == 'write']
    assert len(writes) == 1 and [file.path for file in writes[0].files] == [patch_path]
    assert 'config/protected.json' in envelope.canonical_refs and patch_path in envelope.canonical_refs
    assert hashlib.sha256(expected.encode()).hexdigest() in envelope.canonical_refs
    assert dispatch(workspace, args={'path': patch_path})[0].level == 'approved_external'


@pytest.mark.parametrize('level', ['confidential', 'local_only'])
def test_proposal_and_its_later_read_retain_caller_floor(workspace, level):
    policy, result, _ = dispatch(workspace, 'edit_propose', args(), level=level)
    assert policy.level == level
    assert dispatch(workspace, args={'path': result['proposal_file']})[0].level == level
    journal = json.loads((workspace.controller.task_dir(workspace.task) / 'files.json').read_text())
    assert journal['source_floor'] == level


def test_private_target_baseline_is_protected_before_patch_write_and_later_read(workspace, monkeypatch):
    workspace.service.allowlist = Allowlist(['**'], ['config/protected.json', 'docs/private-report.txt'], [])
    original = workspace.controller.rpc
    floors_at_write = []

    def rpc(task, call):
        if call['operation'] == 'write':
            journal = json.loads((workspace.controller.task_dir(workspace.task) / 'files.json').read_text())
            floors_at_write.append(journal['source_floor'])
        return original(task, call)

    monkeypatch.setattr(workspace.controller, 'rpc', rpc)
    policy, result, _ = dispatch(workspace, 'edit_propose', args('docs/private-report.txt'))
    assert policy.level == 'confidential'
    assert floors_at_write == ['confidential']
    assert workspace.guest['docs/private-report.txt'].startswith(b'SYNTHETIC_PRIVATE_SOURCE')
    assert dispatch(workspace, args={'path': result['proposal_file']})[0].level == 'confidential'


@pytest.mark.parametrize('tamper', ['diff', 'summary', 'path', 'proposal-file', 'extra-policy', 'record', 'bytes'])
def test_proposal_tampering_cannot_authenticate_returned_data(workspace, monkeypatch, tamper):
    original = workspace.service.propose_edit

    def altered(*values, **kwargs):
        result = original(*values, **kwargs)
        if tamper == 'diff':
            result['diff'] += CANARY
        elif tamper == 'summary':
            result['summary'] = 'Target applied: ' + CANARY
        elif tamper == 'path':
            result['path'] = 'jarvis/unrelated.py'
        elif tamper == 'proposal-file':
            result['proposal_file'] = 'docs/proposals/unrelated.patch'
        elif tamper == 'extra-policy':
            result['privacy'] = 'approved_external'
            result['extra'] = CANARY
        elif tamper == 'record':
            state = workspace.service._session()._read()
            state['proposals'][0]['rationale'] += CANARY
            atomic_json(workspace.directory / 'session.json', state)
        else:
            # Execute an unrelated admitted write after the genuine proposal;
            # the additional actual File observation prevents classification.
            workspace.service._session().propose_edit(result['proposal_file'], CANARY, 'unrelated')
        return result

    monkeypatch.setattr(workspace.service, 'propose_edit', altered)
    assert dispatch(workspace, 'edit_propose', args())[0].level == 'confidential'
    assert workspace.guest['config/protected.json'] == b'{}'
    if tamper == 'bytes':
        assert dispatch(workspace, args={'path': proposals.proposal_path('config/protected.json')})[0].level == 'confidential'


def test_custom_unclassified_result_and_missing_observations_remain_protected(workspace):
    fake = {'ok': True, 'proposal': True, 'path': 'config/protected.json',
            'proposal_file': proposals.proposal_path('config/protected.json'),
            'diff': CANARY, 'summary': 'applied', 'privacy': 'approved_external'}
    policy, result, _ = dispatch(workspace, 'edit_propose', args(), invoke=lambda: fake)
    assert policy.level == 'confidential' and result['diff'] == CANARY
    assert workspace.calls == []


def test_source_exclusions_still_refuse_without_guest_or_proposal(workspace):
    policy, result, _ = dispatch(workspace, 'edit_propose', args('.env'))
    assert result == {'ok': False, 'error': 'development_operation_failed'}
    assert workspace.calls == [] and '.env' not in workspace.guest


def test_new_human_only_target_uses_verified_absence_and_never_writes_target(workspace):
    workspace.service.allowlist = Allowlist(['**'], ['config/protected.json', 'config/new-protected.json'], [])
    policy, result, _ = dispatch(workspace, 'edit_propose', args('config/new-protected.json'))
    assert policy.level == 'approved_external'
    assert result['proposal'] is True
    assert 'config/new-protected.json' not in workspace.guest
    assert workspace.guest[result['proposal_file']] == proposals.render(
        'config/new-protected.json', None, args()['new_content'], 'public fixture',
    ).encode()


def test_repeated_proposal_replaces_only_patch_and_preserves_target(workspace):
    first = dispatch(workspace, 'edit_propose', args())[1]
    changed = {**args(), 'new_content': '{"public": "second"}\n', 'rationale': 'second fixture'}
    policy, second, _ = dispatch(workspace, 'edit_propose', changed)
    assert policy.level == 'approved_external'
    assert first['proposal_file'] == second['proposal_file']
    assert workspace.guest['config/protected.json'] == b'{}'
    assert len(workspace.service.proposals) == 1


def test_private_read_copied_during_proposal_admits_only_private_derivatives(workspace, monkeypatch):
    original = workspace.controller.rpc
    floors = []

    def rpc(task, call):
        if call['operation'] == 'write':
            journal = json.loads((workspace.controller.task_dir(workspace.task) / 'files.json').read_text())
            floors.append(journal['source_floor'])
        return original(task, call)

    monkeypatch.setattr(workspace.controller, 'rpc', rpc)

    def derive():
        private = workspace.service.read_file('docs/private-report.txt')['content']
        workspace.service.propose_edit('jarvis/copied.py', private, 'copy fixture')
        return workspace.service.propose_edit(**{
            'path': args()['path'], 'new_content': args()['new_content'], 'rationale': args()['rationale'],
        })

    assert dispatch(workspace, 'edit_propose', args(), invoke=derive)[0].level == 'confidential'
    assert floors == ['confidential', 'confidential']
    assert dispatch(workspace, args={'path': 'jarvis/copied.py'})[0].level == 'confidential'
    assert dispatch(workspace, args={'path': proposals.proposal_path('config/protected.json')})[0].level == 'confidential'


def test_direct_private_baseline_diff_is_private_before_actual_write(workspace, monkeypatch):
    original = workspace.controller.rpc
    floors = []

    def rpc(task, call):
        if call['operation'] == 'write':
            floors.append(json.loads((workspace.controller.task_dir(workspace.task) / 'files.json').read_text())['source_floor'])
        return original(task, call)

    monkeypatch.setattr(workspace.controller, 'rpc', rpc)
    policy, result, _ = dispatch(workspace, 'edit_propose', args('docs/private-report.txt'))
    assert policy.level == 'confidential' and 'SYNTHETIC_PRIVATE_SOURCE' in result['diff']
    assert floors == ['confidential']
    assert dispatch(workspace, args={'path': 'docs/private-report.txt'})[0].level == 'confidential'
