"""Policy/API regressions for self-edit's VM adapter; VM mechanics have their own suite."""
import json
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from jarvis.selfedit import proposals
from jarvis.selfedit.service import SelfEditService, BASE_REF_ENV, is_swift_path, swift_packages_for
from tests.sandbox_fakes import FakeRuntime

ALLOWLIST = {'allow':['docs/**','web/src/**','macos/**','config/agents.yaml','mcp_servers/**','tests/**'],
    'core':['jarvis/**'], 'deny':['jarvis/wakeword.py','jarvis/selfedit/**','.github/**','sandbox/**','**/.env*']}

@pytest.fixture
def service(tmp_path):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/self_edit_allowlist.json').write_text(json.dumps(ALLOWLIST))
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/README.md').write_text('original\n')
    runtime=FakeRuntime(tmp_path)
    service=SelfEditService(repo_root=tmp_path,github_token='host-test-token',runtime_factory=lambda:runtime)
    service.test_runtime=runtime
    return service

def test_complete_adapter_flow_never_checks_out_or_executes_candidate_on_host(service):
    with patch('subprocess.run',side_effect=AssertionError('unexpected host execution')):
        start=service.start_session('Update docs','run-123')
        assert start['ok'] and start['sandbox_task']
        assert service.read_file('docs/README.md')['content']=='original\n'
        assert service.propose_edit('docs/README.md','updated\n','clarify')['ok']
        assert service.validate()['ok']
        assert service.submit()['pr_url'].endswith('/42')
    assert (service.repo_root/'docs/README.md').read_text()=='original\n'
    assert service.work_root is None
    assert not service.status()['active']
    assert not hasattr(service,'_git') and not hasattr(service,'_run')

def test_reopened_service_resumes_same_session(service):
    service.start_session('Update docs')
    branch=service.branch
    reopened=SelfEditService(repo_root=service.repo_root,runtime_factory=lambda:service.test_runtime)
    assert reopened.branch==branch
    assert reopened.propose_edit('docs/README.md','new\n','reason')['ok']
    assert service.proposals[0]['path']=='docs/README.md'

def test_policy_and_frozen_web_are_enforced_on_actual_edits(service):
    service.start_session('Update docs')
    for path in ['../outside','.env','web/src/App.tsx','docs/proposals/x.patch']:
        assert not service.propose_edit(path,'change','denied')['ok'],path
    assert 'secrets' in service.propose_edit('.env','K=1\n','why')['error']
    assert service.propose_edit('docs/new.md','new\n','allowed')['ok']
    assert [p['path'] for p in service.proposals]==['docs/new.md']

HUMAN_ONLY=['jarvis/wakeword.py','sandbox/control.py','.github/workflows/evil.yml']

def test_a_human_only_write_becomes_a_proposal_and_the_file_is_never_written(service):
    """W8 (Larry 2026-09-25, option A): Mortimer never writes a human-only
    file. The change is saved as a patch against the session's base."""
    service.test_runtime.baseline['jarvis/wakeword.py']='MODEL = "a"\n'
    service.start_session('Tighten the wake word and CI')
    for path in HUMAN_ONLY:
        res=service.propose_edit(path,'MODEL = "b"\n','why '+path)
        assert res['ok'] and res['proposal'] and res['path']==path, res
        assert res['proposal_file']==proposals.proposal_path(path)
        assert 'NOT changed' in res['summary'] and res['diff'].startswith('diff --git')
    session=service.test_runtime.current
    assert [p['path'] for p in session.state['proposals']]==[proposals.proposal_path(p) for p in HUMAN_ONLY]
    assert session.files['jarvis/wakeword.py']=='MODEL = "a"\n'
    assert 'sandbox/control.py' not in session.files and '.github/workflows/evil.yml' not in session.files
    changed=proposals.parse(session.files[proposals.proposal_path('jarvis/wakeword.py')])
    assert changed['target']=='jarvis/wakeword.py' and changed['base']==proposals.git_blob_sha(b'MODEL = "a"\n')
    assert changed['result']==proposals.git_blob_sha(b'MODEL = "b"\n')
    created=proposals.parse(session.files[proposals.proposal_path('.github/workflows/evil.yml')])
    assert created['base']==proposals.NEW_FILE
    assert service.human_only_targets()==HUMAN_ONLY
    again=service.propose_edit('jarvis/wakeword.py','MODEL = "c"\n','second thought')
    assert again['ok'] and len(service.proposals)==3, 'a second write replaces that proposal'
    assert not service.propose_edit('jarvis/wakeword.py','MODEL = "a"\n','no-op')['ok']

def test_a_human_only_file_reads_read_only_from_the_base(service):
    service.test_runtime.baseline['jarvis/wakeword.py']='MODEL = "a"\n'
    service.start_session('Look at the wake word')
    read=service.read_file('jarvis/wakeword.py')
    assert read['ok'] and read['human_only'] and read['content']=='MODEL = "a"\n'
    assert 'proposal' in read['note']
    assert not service.read_file('sandbox/control.py')['ok']   # not in the base
    assert not service.read_file('.env')['ok']                  # secrets are never shown

def test_a_test_that_needs_the_proposal_joins_it_and_never_both(service):
    service.test_runtime.baseline['jarvis/wakeword.py']='MODEL = "a"\n'
    service.start_session('Wake word with a test')
    assert service.propose_edit('jarvis/wakeword.py','MODEL = "b"\n','new model')['ok']
    joined=service.propose_edit('tests/unit/test_wake.py','def test_b(): pass\n','covers it',proposal=True)
    assert joined['ok'] and joined['proposal'], joined
    assert 'tests/unit/test_wake.py' not in service.test_runtime.current.files
    both=service.propose_edit('tests/unit/test_wake.py','x\n','direct too')
    assert not both['ok'] and 'proposal=true' in both['error']
    assert not service.propose_edit('docs/new.md','x\n','why',proposal=True)['ok']
    assert service.propose_edit('tests/unit/test_other.py','x\n','direct')['ok']
    after=service.propose_edit('tests/unit/test_other.py','y\n','now proposed',proposal=True)
    assert not after['ok'] and 'already written directly' in after['error']

def test_a_proposal_pr_says_approve_then_apply_and_never_merge(service):
    service.test_runtime.baseline['jarvis/wakeword.py']='MODEL = "a"\n'
    service.start_session('Wake word model')
    service.propose_edit('jarvis/wakeword.py','MODEL = "b"\n','new model')
    service.propose_edit('macos/MortimerHost/Sources/MortimerHost/View.swift','new\n','view')
    service.validate()
    result=service.submit()
    assert result['ok'] and result['human_only']==['jarvis/wakeword.py']
    digest=service.proposal_set_digest(service.test_runtime.current.state['proposals'])
    command=proposals.apply_command(service.repo_root,42,digest)
    assert result['apply_command']==command
    assert result['notice'].startswith(proposals.MARKER)
    assert command in result['notice'] and 'approve?' in result['notice'] and 'Do not merge' in result['notice']
    assert 'pushes nothing until he types y' in result['notice']
    assert 'Review and merge' not in result['notice']
    body=service.test_runtime.events[-1][2]
    assert proposals.MARKER+' — do not merge this pull request as it is' in body
    assert proposals.APPLY_SCRIPT in body and 'jarvis/wakeword.py' in body and 'until he types y' in body

def test_an_ordinary_pr_says_deploy_with_deploy_main_and_names_no_build_script(service):
    service.start_session('Native view')
    service.propose_edit('macos/MortimerHost/Sources/MortimerHost/View.swift','new\n','view')
    service.validate()
    result=service.submit()
    assert 'human_only' not in result
    assert 'DEPLOY-MAIN' in result['notice'] and 'bundle' not in result['notice']
    assert proposals.MARKER not in service.test_runtime.events[-1][2]

def test_edits_and_failed_checks_invalidate_submission(service):
    service.start_session('Update docs')
    service.propose_edit('docs/README.md','new\n','reason')
    assert not service.submit()['ok']
    service.test_runtime.validation_ok=False
    assert not service.validate()['ok']
    assert not service.submit()['ok']
    service.test_runtime.validation_ok=True
    assert service.validate()['ok']
    service.propose_edit('docs/README.md','changed again\n','reason')
    assert not service.status()['validated_ok']
    assert not service.submit()['ok']

def test_cancel_and_revert_are_vm_operations(service):
    service.start_session('Goal')
    assert service.cancel()['ok']
    assert not service.status()['active']
    assert service.start_session('Another goal')['ok']
    assert service.revert()['ok']
    assert (service.repo_root/'docs/README.md').exists()

def test_configured_base_ref_is_passed_to_the_source_and_pr_session(service,monkeypatch):
    monkeypatch.setenv(BASE_REF_ENV,'origin/feat/test')
    from_env=SelfEditService(repo_root=service.repo_root,runtime_factory=lambda:service.test_runtime)
    assert from_env.pr_base=='feat/test'
    assert from_env.start_session('Goal')['ok']
    assert service.test_runtime.events[-1][3]=='feat/test'
    explicit=SelfEditService(repo_root=service.repo_root,base_ref='origin/main')
    assert explicit.pr_base=='main'

def test_pr_preserves_core_capability_native_and_visual_review_information(service):
    service.start_session('Improve native behavior')
    for path in ['jarvis/bot/display.py','config/agents.yaml','macos/MortimerHost/Sources/MortimerHost/View.swift']:
        service.propose_edit(path,'new\n','reason','Show progress clearly')
    service.validate(); assert service.submit()['ok']
    body=service.test_runtime.events[-1][2]
    for marker in ['CORE CHANGE','CAPABILITY CHANGE','SWIFT CHANGE','VISUAL CHANGE','Show progress clearly','independent-vm']:
        assert marker in body

def test_appearance_never_uses_a_host_screenshot(service):
    view=Mock()
    result=service.verify_appearance(branch_override=True,view=view)
    assert not result['ok']
    view.assert_not_called()

def test_swift_dependency_closure_is_preserved():
    assert is_swift_path('macos/JarvisKit/Sources/Client.swift')
    assert swift_packages_for(['macos/JarvisKit/Sources/Client.swift'])==['JarvisKit','MortimerHost']
class TestWebFreezeMessageNamesTheSwiftPath:
    """SE7 — the freeze message used to end the conversation ("which is a
    human PR"). It is now a redirect: the same request, aimed at the file
    self-edit can actually change."""

    def test_the_freeze_message_points_at_target_paths(self, service: SelfEditService):
        res = service.preflight("restyle web/src/App.tsx", has_plan=False)
        assert res["ok"] is False
        assert "macos/MortimerHost" in res["error"]
        assert "target_paths" in res["error"]
        assert "human PR" not in res["error"]

class TestPreflight:
    """The preview refuses what the planner would only discover after
    confirm + staging + a run (2026-08-30: three such runs)."""

    def test_a_human_only_goal_passes_and_names_the_file(self, service: SelfEditService) -> None:
        # W8 (2026-09-25): until then a Tier-0 goal was refused here. Its
        # change now becomes a proposal, and the preview names the file.
        res = service.preflight("rewrite jarvis/wakeword.py to use a new model", has_plan=True)
        assert res["ok"] is True, res
        assert res["human_only"] == ["jarvis/wakeword.py"]

    def test_a_secrets_goal_is_refused_naming_the_file(self, service: SelfEditService) -> None:
        res = service.preflight("rotate the key", has_plan=False, target_paths=[".env"])
        assert res["ok"] is False
        assert ".env" in res["error"] and "secrets" in res["error"]
        assert res["human_only"] == []

    def test_core_goal_without_plan_is_refused(self, service: SelfEditService) -> None:
        res = service.preflight("merge results in jarvis/bot/display.py", has_plan=False)
        assert res["ok"] is False
        assert "plan" in res["error"]
        assert res["tiers"]["core"] == ["jarvis/bot/display.py"]

    def test_core_goal_with_plan_passes(self, service: SelfEditService) -> None:
        res = service.preflight("merge results in jarvis/bot/display.py", has_plan=True)
        assert res["ok"] is True
        assert res["tiers"]["core"] == ["jarvis/bot/display.py"]

    def test_routine_goal_passes_without_plan(self, service: SelfEditService) -> None:
        res = service.preflight("tidy docs/README.md spacing", has_plan=False)  # GC4: web/ frozen
        assert res["ok"] is True and res["tiers"]["core"] == []

    def test_goal_naming_no_files_passes_through(self, service: SelfEditService) -> None:
        # Extraction is best-effort; the planner's own allowlist check still
        # governs every write.
        res = service.preflight("make the drawer feel more like glass", has_plan=False)
        assert res["ok"] is True and res["paths"] == []

class TestPreflightTargetPaths:
    """2026-09-07 (review F5): preflight classifies the files the edit will
    CHANGE when the caller names them, and consults the prose only as the
    fallback. The fixture's tiers: docs/** routine, jarvis/** core,
    jarvis/wakeword.py Tier 0."""

    def test_target_paths_override_a_core_path_the_prose_mentions(self, service) -> None:
        res = service.preflight(
            "add a line about jarvis/bot/display.py to docs/README.md",
            has_plan=False, target_paths=["docs/README.md"],
        )
        assert res["ok"] is True, res
        assert res["paths"] == ["docs/README.md"]
        assert res["tiers"]["core"] == []

    def test_without_target_paths_the_same_goal_is_refused_as_core(self, service) -> None:
        res = service.preflight(
            "add a line about jarvis/bot/display.py to docs/README.md", has_plan=False,
        )
        assert res["ok"] is False
        assert "jarvis/bot/display.py" in res["error"]

    def test_target_paths_catch_a_tier0_target_the_prose_hides(self, service) -> None:
        res = service.preflight(
            "make the wake word detector feel snappier", has_plan=False,
            target_paths=["jarvis/wakeword.py"],
        )
        assert res["ok"] is True, res
        assert res["human_only"] == ["jarvis/wakeword.py"]

    def test_blank_target_paths_fall_back_to_the_prose(self, service) -> None:
        res = service.preflight("tidy docs/README.md spacing", has_plan=False,
                                target_paths=["", "  "])
        assert res["ok"] is True and res["paths"] == ["docs/README.md"]