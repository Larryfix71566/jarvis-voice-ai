"""Stage/confirm/edit/finish integration through the VM workspace boundary.

FastAPI routes and SelfEditService are real. The injected runtime represents
VM transport and independent verification; it never executes candidate code
on the test host. Real VM, verifier, and GitHub publication acceptance is
recorded separately in sandbox/acceptance/2026-09-10-session.json.
"""
from __future__ import annotations
import json
import time
import pytest
from fastapi.testclient import TestClient
import jarvis.admin.server as srv
from jarvis.admin.server import app
from jarvis.selfedit.service import SelfEditService
from tests.sandbox_fakes import FakeRuntime

@pytest.fixture(autouse=True)
def reset_jobs():
    with srv._run_lock:
        srv._run_job.update(state='idle', cancel_requested=False, goal=None, profile=None, summary=None,
            started_at=None, finished_at=None, submitted=False, pr_url=None)
    with srv._finish_lock:
        srv._finish_job.update(state='idle', cancel_requested=False, checks=None, pr_url=None, notice=None,
            run_id=None, started_at=None, finished_at=None)
    with srv._staging_lock:
        srv._selfedit_stagings.clear()
    yield
    with srv._staging_lock:
        srv._selfedit_stagings.clear()

@pytest.fixture
def service(tmp_path, monkeypatch):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/README.md').write_text('# docs\n\nOne line.\n')
    policy = tmp_path / 'allow.json'
    policy.write_text(json.dumps({'allow':['docs/**', 'tests/**'], 'core':['jarvis/**'],
                                  'deny':['jarvis/vault.py', '.github/**']}))
    runtime = FakeRuntime(tmp_path)
    runtime.pr_url = 'https://github.com/test/repo/pull/42'
    service = SelfEditService(repo_root=tmp_path, allowlist_path=policy,
        github_repo='test/repo', github_token='test-only-token', base_ref='main',
        runtime_factory=lambda: runtime)
    service.test_runtime = runtime
    monkeypatch.setattr(srv, '_selfedit_service', service)
    return service

def open_session(client, path='docs/README.md'):
    staged = client.post('/api/selfedit/stage', json={
        'goal':'Update '+path, 'target_paths':[path], 'run_id':'run-e2e'}).json()
    assert staged['ok'], staged
    opened = client.post('/api/selfedit/run', json={
        'staging_id':staged['staging_id'], 'author':True}).json()
    assert opened['ok'] and not opened['started'], opened
    assert opened['session']['worktree'] is None
    assert opened['session']['sandbox_task']
    assert opened['session']['session_id']
    assert opened['session']['branch'].startswith('mortimer/selfedit/')
    return opened

def finish(client, expected):
    started = client.post('/api/selfedit/finish', json={}).json()
    assert started['ok'] and started['started'], started
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        result = client.get('/api/selfedit/run').json()['finish']
        if result['state'] in {'done','failed','error'}:
            assert result['state']==expected, result
            return result
        time.sleep(.02)
    pytest.fail('Finish job did not settle')

def test_a_voice_self_edit_reaches_a_pull_request(service):
    client = TestClient(app)
    open_session(client)
    read = client.get('/api/selfedit/file',params={'path':'docs/README.md'}).json()
    assert read['ok'] and 'One line.' in read['content']
    wrote = client.post('/api/selfedit/write',json={'path':'docs/README.md',
        'content':read['content']+'\nReviewed.\n','rationale':'record review'}).json()
    assert wrote['ok'] and '+Reviewed.' in wrote['diff']
    # The actual host fixture remains unchanged after the API edit.
    assert (service.repo_root/'docs/README.md').read_text()==read['content']
    result = finish(client,'done')
    assert result['pr_url']==service.test_runtime.pr_url
    assert result['run_id']=='run-e2e'
    assert all(c['ok'] for c in result['checks'])
    submissions = [e for e in service.test_runtime.events if e[0]=='submit']
    assert len(submissions)==1
    assert 'docs/README.md' in submissions[0][2]
    assert not client.get('/api/selfedit/run').json()['status']['active']

def test_a_failed_check_blocks_publication_and_allows_repair(service):
    client = TestClient(app)
    path='tests/unit/test_added.py'
    open_session(client,path)
    assert client.post('/api/selfedit/write',json={'path':path,
        'content':'def test_added():\n    assert False\n','rationale':'initial test'}).json()['ok']
    service.test_runtime.validation_ok=False
    result=finish(client,'failed')
    assert result['pr_url'] is None
    assert not any(e[0]=='submit' for e in service.test_runtime.events)
    state=client.get('/api/selfedit/run').json()['status']
    assert state['active'] and not state['validated_ok']
    assert [p['path'] for p in state['proposals']]==[path]
    assert client.post('/api/selfedit/write',json={'path':path,
        'content':'def test_added():\n    assert True\n','rationale':'repair test'}).json()['ok']
    service.test_runtime.validation_ok=True
    assert finish(client,'done')['pr_url']==service.test_runtime.pr_url
    assert not (service.repo_root/path).exists()

def test_denied_path_never_reaches_the_workspace(service):
    client=TestClient(app)
    open_session(client)
    result=client.post('/api/selfedit/write',json={'path':'jarvis/vault.py',
        'content':'KEY = 1\n','rationale':'denied'}).json()
    assert not result['ok'] and 'workspace policy' in result['error']
    assert 'jarvis/vault.py' not in service.test_runtime.current.files
