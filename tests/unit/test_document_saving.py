"""Generated documents use the VM editor, never the installed repository."""
import json
import time
import pytest
from fastapi.testclient import TestClient
from jarvis.admin import server as srv
from jarvis.selfedit.service import SelfEditService
from tests.sandbox_fakes import FakeRuntime


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    policy = tmp_path / 'allow.json'
    policy.write_text(json.dumps({'allow':['docs/**'], 'deny':['docs/plans/protected.md']}))
    runtime = FakeRuntime(tmp_path)
    service = SelfEditService(repo_root=tmp_path, allowlist_path=policy,
                              runtime_factory=lambda: runtime)
    monkeypatch.setattr(srv, '_selfedit_service', service)
    monkeypatch.setattr(srv, 'authoring_enabled', lambda: True)
    for name, state in [('_run_job','idle'), ('_finish_job','idle'), ('_opening_job','idle')]:
        monkeypatch.setattr(srv, name, {'state':state})
    service.start_session('Save generated documents')
    return service, runtime, tmp_path


@pytest.mark.parametrize('kind', ['plan','review','research'])
def test_generated_document_enters_session_and_invalidates_validation(workspace, monkeypatch, kind):
    service, runtime, root = workspace
    service.validate()
    if kind == 'research':
        monkeypatch.setattr(srv, '_research_job', {'state':'done', 'comparison':'# Findings',
            'urls':['https://a.example','https://b.example'], 'sites':[], 'credits_used':0})
        endpoint, directory = '/api/research/save', 'research'
    else:
        monkeypatch.setattr(srv, '_plan_job', {'state':'done', 'mode':'single', 'goal':'Document',
            'plan':'# Plan', 'author':'unknown', 'review_path':'docs/plans/source.md' if kind == 'review' else None})
        endpoint, directory = '/api/plan/adopt', 'reviews' if kind == 'review' else 'plans'
    path = f'docs/{directory}/saved.md'
    result = TestClient(srv.app).post(endpoint, json={'path':path}).json()
    assert result['ok'] and result['saved_to_sandbox']
    assert result['verified'] is False and result['published'] is False
    assert 'action_id' not in result
    assert path in runtime.current.files
    assert not (root / path).exists()
    assert not service.status()['validated_ok']
    assert not service.submit()['ok'], 'Saving must require fresh validation.'
    assert service.validate()['ok']
    assert service.submit()['ok'], 'The existing verified draft workflow remains usable.'


@pytest.mark.parametrize('path', ['jarvis/config.py','docs/plans/../escape.md',
    '/docs/plans/x.md','docs/plans/x.py','docs//x.md','docs/plans/protected.md'])
def test_document_paths_and_installed_policy_are_enforced(workspace, path):
    service, runtime, _ = workspace
    assert not srv._save_document_to_sandbox(path, 'unapproved')['ok']
    assert not service.proposals


def test_cold_save_returns_retry_without_queuing_document(workspace):
    service, runtime, _ = workspace
    runtime.current.state.update(ready=False, vm_status='stopped')
    path = 'docs/plans/cold.md'
    first = srv._save_document_to_sandbox(path, '# Document')
    assert not first['ok'] and first['retryable']
    assert path not in runtime.current.files
    deadline = time.monotonic()+3
    while srv._opening_job['state'] == 'starting' and time.monotonic()<deadline:
        time.sleep(.01)
    assert srv._save_document_to_sandbox(path, '# Document')['saved_to_sandbox']


def test_busy_save_preserves_existing_files(workspace, monkeypatch):
    _, runtime, _ = workspace
    monkeypatch.setattr(srv, '_finish_job', {'state':'validating'})
    assert not srv._save_document_to_sandbox('docs/plans/x.md', 'x')['ok']
    assert 'docs/plans/x.md' not in runtime.current.files


def test_disabled_authoring_never_saves(workspace, monkeypatch):
    service, _, _ = workspace
    monkeypatch.setattr(srv, 'authoring_enabled', lambda: False)
    assert not srv._save_document_to_sandbox('docs/plans/x.md', 'x')['ok']
    assert not service.proposals
