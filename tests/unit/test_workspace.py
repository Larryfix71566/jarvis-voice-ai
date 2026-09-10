"""Application workspace policy and VM adapter regressions."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from jarvis.agents.workspace import AppWorkspace, SelfEditWorkspace, Workspace, WorkspaceError, _check_app_path
from jarvis.selfedit.service import SelfEditService
from tests.sandbox_fakes import FakeRuntime

@pytest.fixture
def workspace(tmp_path):
    (tmp_path/'src').mkdir()
    (tmp_path/'src/app.js').write_text('original\n')
    runtime=FakeRuntime(tmp_path)
    client=SimpleNamespace(token='host-test-token',_owner=lambda:'test')
    workspace=AppWorkspace('example-app',github_client=client,workspaces_dir=tmp_path,
                           runtime_factory=lambda:runtime)
    workspace.test_runtime=runtime
    return workspace

def test_self_edit_workspace_is_a_subclass_of_self_edit_service():
    assert issubclass(SelfEditWorkspace,SelfEditService)

def test_self_edit_workspace_satisfies_workspace_protocol(tmp_path):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/self_edit_allowlist.json').write_text(json.dumps({'allow':['docs/**'],'deny':[]}))
    runtime=FakeRuntime(tmp_path)
    service=SelfEditWorkspace(repo_root=tmp_path,runtime_factory=lambda:runtime)
    assert isinstance(service,Workspace)

@pytest.mark.parametrize('path',['.git/config','.env','.env.local','data/private.vault','.github/workflows/run.yml','../outside','/tmp/outside'])
def test_check_app_path_denies(path):
    with pytest.raises((ValueError,WorkspaceError)): _check_app_path(path)

@pytest.mark.parametrize('path',['src/App.tsx','README.md','a/b/c.py'])
def test_check_app_path_allows(path):
    assert _check_app_path(path)==path

def test_app_development_uses_shared_vm_session_and_host_profile(workspace):
    with patch('subprocess.run',side_effect=AssertionError('unexpected host candidate command')):
        assert workspace.start_session('Improve app')['ok']
        assert workspace.read_file('src/app.js')['content']=='original\n'
        assert workspace.propose_edit('src/app.js','new\n','reason')['ok']
        assert workspace.validate()['ok']
        assert workspace.submit()['pr_url'].endswith('/42')
    assert workspace.test_runtime.events[0][1:]==('test/example-app','app-build','main','web-app')
    assert not workspace.status()['active']
    assert not workspace.repo_root.exists()
    assert not hasattr(workspace,'_run') and not hasattr(workspace,'_git')

def test_local_checkout_test_seam_is_rejected(workspace):
    with pytest.raises(WorkspaceError): AppWorkspace('example',remote_url='/some/host/checkout')

def test_candidate_manifest_cannot_replace_host_validation_profile(workspace):
    workspace.start_session('Goal')
    workspace.propose_edit('mortimer.app.yaml','checks: [echo pass]\n','untrusted manifest')
    assert workspace.test_runtime.events[0][-1]=='web-app'
    workspace.test_runtime.validation_ok=False
    assert not workspace.validate()['ok']
    assert not workspace.submit()['ok']

def test_app_policy_cancel_and_reopen(workspace):
    workspace.start_session('Goal')
    assert not workspace.propose_edit('.github/workflows/run.yml','bad','denied')['ok']
    assert workspace.cancel()['ok']
    assert not workspace.status()['active']
    assert workspace.start_session('Next goal')['ok']
    assert workspace.revert()['ok']
