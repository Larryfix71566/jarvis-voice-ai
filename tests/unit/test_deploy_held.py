"""Actual protected deployer payload, synthetic HOME/processes only; no live ops."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import types

import pytest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/deploy_main.sh'
TARGET='2'*40
PRIOR='1'*40

@pytest.fixture
def held(tmp_path,monkeypatch):
    monkeypatch.setenv('HOME',str(tmp_path));monkeypatch.delenv('JARVIS_LLM_ACCESS_MODE',raising=False)
    code=SCRIPT.read_text().split('# BEGIN HELD PYTHON\n',1)[1].split('# END HELD PYTHON',1)[0]
    m=types.ModuleType('held_deploy_fixture');exec(compile(code,'canonical-held-payload','exec'),m.__dict__)
    c=tmp_path/'jarvis-voice-ai-clean';c.mkdir();(c/'.env').write_text('JARVIS_LLM_ACCESS_MODE=direct_apis_disabled\nKEY=synthetic-only\n')
    source=tmp_path/'source/scripts/deploy_main.sh';source.parent.mkdir(parents=True);source.write_bytes(SCRIPT.read_bytes())
    agents=tmp_path/'Library/LaunchAgents';agents.mkdir(parents=True)
    for label in m.LABELS.values():
        (agents/(label+'.plist')).write_bytes(plistlib.dumps({'Label':label,'EnvironmentVariables':{'JARVIS_LLM_ACCESS_MODE':m.MODE}}))
    app=c/'macos/MortimerHost/.build/MortimerHost.app';(app/'Contents/MacOS').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'MortimerSourceRevision':PRIOR}))
    (app/'Contents/MacOS/MortimerHost').write_text('synthetic-prior-app')
    root=tmp_path/'MortimerRollback';root.mkdir();rb=root/'synthetic-snapshot';rb.mkdir(mode=0o700)
    old=tmp_path/'old.txt';old.write_text('synthetic-prior-code')
    with tarfile.open(rb/'code.tgz','w:gz') as out:out.add(old,arcname='./old.txt')
    shutil.copytree(app,rb/'MortimerHost.app')
    class Fake(m.System):
        def __init__(self):
            self.flags=dict.fromkeys([*m.LABELS.values(),m.CLEANUP],'disabled');self.jobs={};self.calls=[]
            self.head=PRIOR;self.dirty=False;self.untracked='';self.tracked_env=False;self.private_tree=False;self.fail_bootout=None;self.bad_absence=False
            self.fail_health=False;self.env_mode=m.MODE;self.cwd=c;self.survivors=set();self.app_exe=None
        def run(self,argv,check=True):
            a=[str(x) for x in argv];self.calls.append(a);rc=0;out='';err=''
            if a[0]=='launchctl':
                if a[1]=='print-disabled':out='\n'.join('"'+k+'" => '+v for k,v in self.flags.items())
                elif a[1]=='print':
                    label=a[2].rsplit('/',1)[-1]
                    if label in self.jobs:out='pid = '+str(self.jobs[label])+'\nSECRET=synthetic-only\n'
                    else:rc=113;err=('Permission denied' if self.bad_absence else 'Could not find service "'+label+'"')
                elif a[1] in ('disable','enable'):self.flags[a[2].rsplit('/',1)[-1]]='disabled' if a[1]=='disable' else 'enabled'
                elif a[1]=='bootout':
                    label=a[2].rsplit('/',1)[-1]
                    if self.fail_bootout==label:rc=1;err='denied'
                    else:self.jobs.pop(label,None)
                elif a[1]=='bootstrap':
                    label=Path(a[3]).stem;self.jobs[label]=90000001+len(self.jobs)
                else:pytest.fail('unexpected launchctl operation')
            elif a[0]=='git':
                if 'ls-tree' in a:
                    marker='a'*40 if a[-1]==TARGET else 'b'*40
                    out='100644 blob '+marker+'\tscripts/deploy_main.sh\n'
                    if self.private_tree:out+='100644 blob '+marker+'\t.env\n'
                elif 'show' in a:out=source.read_text()
                elif 'rev-parse' in a:out=self.head+'\n'
                elif 'diff' in a:rc=int(self.dirty)
                elif 'ls-files' in a:
                    if '--error-unmatch' in a:rc=0 if self.tracked_env else 1
                    else:out=self.untracked
                elif 'checkout' in a:self.head=a[-1];(c/'prior-checkout.txt').write_text('synthetic prior source')
                else:pytest.fail('unexpected git operation')
            elif a[0]=='ps':
                if '-axo' in a:out='\n'.join(str(p)+' 1' for p in self.jobs.values())
                elif 'eww' in a:out='python JARVIS_LLM_ACCESS_MODE='+self.env_mode+' SECRET=synthetic-only'
                elif self.app_exe is not None:out=self.app_exe
                else:pytest.fail('unexpected ps operation')
            elif a[0]=='lsof':out='p90000001\nn'+str(self.cwd)+'\n'
            elif a[0]=='pgrep':rc=1 if self.app_exe is None else 0;out='' if rc else '90000099\n'
            elif a[0]=='osascript':pytest.fail('no app may be quit in this fixture')
            elif a[0]=='tar':
                with tarfile.open(a[-1],'r:gz') as archive:archive.extractall(c,filter='data')
            elif a[0]=='ditto':shutil.copytree(a[1],a[2],dirs_exist_ok=True)
            else:pytest.fail('unexpected operator command: '+a[0])
            r=subprocess.CompletedProcess(a,rc,out,err)
            if check and rc:raise m.HeldError('synthetic command refused')
            return r
        def alive(self,pid):return pid in self.survivors
        def sleep(self):pass
        def request(self,port,path):
            self.calls.append(['health',str(port),path])
            if self.fail_health:raise m.HeldError('synthetic health failure')
    sys=Fake();h=m.Held(c,source,sys)
    program=h.program(source.parent.parent,TARGET)
    review=tmp_path/'review.json';ci=tmp_path/'ci.json';approval=tmp_path/'approval.json'
    m.private_json(review,{'source':TARGET,'program_sha256':program,'verdict':'no_blocking_findings'})
    m.private_json(ci,{'source':TARGET,'program_sha256':program,'checks':dict.fromkeys(m.CHECKS,'SUCCESS')})
    m.private_json(approval,{'version':1,'target':TARGET,'review_receipt':str(review),'review_sha256':m.digest(review),'ci_receipt':str(ci),'ci_sha256':m.digest(ci)})
    x=types.SimpleNamespace(m=m,h=h,sys=sys,c=c,source=source,rb=rb,app=app,approval=approval,review=review,ci=ci,program=program,home=tmp_path)
    def snapshot():h.snapshot(rb,source.parent.parent,TARGET,approval)
    def installed():
        snapshot();sys.head=TARGET;(app/'Contents/Info.plist').write_bytes(plistlib.dumps({'MortimerSourceRevision':TARGET}));h.installed(rb)
    x.snapshot=snapshot;x.installed=installed
    return x


def test_approval_requires_exact_program_review_and_all_five_ci(held):
    x=held;x.h.preflight(x.source.parent.parent,TARGET,x.approval)
    a=x.m.read_json(x.approval);a['review_sha256']='0'*64;x.m.private_json(x.approval,a)
    with pytest.raises(x.m.HeldError):x.h.preflight(x.source.parent.parent,TARGET,x.approval)

@pytest.mark.parametrize('field,value',[('source',PRIOR),('program_sha256','0'*64),('verdict','pending')])
def test_review_binding_cannot_be_reused_or_invented(held,field,value):
    x=held;r=x.m.read_json(x.review);r[field]=value;x.m.private_json(x.review,r)
    a=x.m.read_json(x.approval);a['review_sha256']=x.m.digest(x.review);x.m.private_json(x.approval,a)
    with pytest.raises(x.m.HeldError):x.h.preflight(x.source.parent.parent,TARGET,x.approval)

@pytest.mark.parametrize('alter',['pending','omitted','extra'])
def test_ci_not_just_a_green_boolean(held,alter):
    x=held;r=x.m.read_json(x.ci)
    if alter=='pending':r['checks']['validate']='IN_PROGRESS'
    elif alter=='omitted':del r['checks']['validate']
    else:r['checks']['invented']='SUCCESS'
    x.m.private_json(x.ci,r);a=x.m.read_json(x.approval);a['ci_sha256']=x.m.digest(x.ci);x.m.private_json(x.approval,a)
    with pytest.raises(x.m.HeldError):x.h.preflight(x.source.parent.parent,TARGET,x.approval)

@pytest.mark.parametrize('mode',['legacy','subscription_only','unknown','$(legacy)'])
def test_wrong_disk_policy_refuses_before_install(held,mode):
    x=held;(x.c/'.env').write_text('JARVIS_LLM_ACCESS_MODE='+mode+'\n')
    with pytest.raises(x.m.HeldError):x.h.preflight(x.source.parent.parent,TARGET,x.approval)
    assert not any('checkout' in a for a in x.sys.calls)


def test_duplicate_mode_and_wrong_launch_envelope_refuse(held):
    x=held;(x.c/'.env').write_text('JARVIS_LLM_ACCESS_MODE=direct_apis_disabled\nJARVIS_LLM_ACCESS_MODE=legacy\n')
    with pytest.raises(x.m.HeldError):x.h.policy_files()
    (x.c/'.env').write_text('JARVIS_LLM_ACCESS_MODE=direct_apis_disabled\n')
    p=x.home/'Library/LaunchAgents/com.mortimer.costs.plist';p.write_bytes(plistlib.dumps({'Label':'com.mortimer.costs'}))
    with pytest.raises(x.m.HeldError):x.h.policy_files()


def test_unknown_disabled_state_and_permission_denial_are_not_absence(held):
    x=held;x.sys.bad_absence=True
    with pytest.raises(x.m.HeldError):x.h.hold()
    x.sys.bad_absence=False;del x.sys.flags[x.m.CLEANUP]
    with pytest.raises(x.m.HeldError):x.h.hold()


def test_legacy_default_cannot_undo_shutdown_or_disabled_override(held):
    x=held
    with pytest.raises(x.m.HeldError):x.h.legacy_allowed()
    (x.c/'.env').write_text('JARVIS_LLM_ACCESS_MODE=legacy\n')
    with pytest.raises(x.m.HeldError):x.h.legacy_allowed()
    x.sys.flags=dict.fromkeys(x.sys.flags,'enabled')
    for label in x.m.LABELS.values():
        p=x.home/'Library/LaunchAgents'/(label+'.plist');p.write_bytes(plistlib.dumps({'Label':label}))
    x.h.legacy_allowed()


def test_snapshot_frozen_rollback_has_no_legacy_restart(held):
    x=held;x.snapshot();launcher=(x.rb/'ROLLBACK.sh').read_text()
    assert '--rollback-held' in launcher and 'kickstart' not in launcher and 'open ' not in launcher
    assert (x.rb/'deploy-main-held.sh').read_bytes()==x.source.read_bytes()
    assert x.m.read_json(x.rb/'held-policy.json')['runner_sha256']==x.m.digest(x.source)

@pytest.mark.parametrize('member',['./.env','./data/private.db','./nested/.env.local','../escape','/absolute'])
def test_unsafe_snapshot_archive_refuses_before_install_or_launcher(held,member):
    x=held;data=x.home/'payload';data.write_text('synthetic')
    with tarfile.open(x.rb/'code.tgz','w:gz') as out:
        item=tarfile.TarInfo(member);item.size=9;out.addfile(item,io.BytesIO(b'synthetic'))
    with tarfile.open(x.rb/'code.tgz') as check:assert check.getmembers()[0].name==member
    with pytest.raises(x.m.HeldError):x.snapshot()
    assert not (x.rb/'ROLLBACK.sh').exists()


def test_base_restore_only_costs_and_kb_and_keeps_inference_and_cleanup_held(held):
    x=held;x.installed();x.h.restore(x.rb,['costs','vault'])
    assert set(x.sys.jobs)=={x.m.LABELS[n] for n in x.m.LOCAL}
    assert all(x.sys.flags[label]=='disabled' for n,label in x.m.LABELS.items() if n not in x.m.LOCAL)
    assert x.sys.flags[x.m.CLEANUP]=='disabled'
    assert not any(x.m.CLEANUP in ' '.join(a) for a in x.sys.calls if a[0]=='launchctl' and a[1] not in ('print','print-disabled'))

@pytest.mark.parametrize('names',[['admin'],['bot'],['extractor'],['status-daily'],['costs','costs'],[''],['unknown']])
def test_restore_rejects_other_or_ambiguous_targets(held,names):
    x=held;x.installed();before=len(x.sys.calls)
    with pytest.raises(x.m.HeldError):x.h.restore(x.rb,names)
    assert not any(a[0]=='launchctl' and a[1] in ('enable','bootstrap') for a in x.sys.calls[before:])

@pytest.mark.parametrize('failure',['health','environment','cwd'])
def test_failed_local_restore_quarantines_without_reverting_guarded_code(held,failure):
    x=held;x.installed()
    if failure=='health':x.sys.fail_health=True
    elif failure=='environment':x.sys.env_mode='legacy'
    else:x.sys.cwd=x.home/'outside-production'
    with pytest.raises(x.m.HeldError):x.h.restore(x.rb,['costs','vault'])
    assert not x.sys.jobs and x.sys.head==TARGET
    assert all(x.sys.flags[l]=='disabled' for l in x.m.LABELS.values())
    assert not (x.rb/'local-restoration.json').exists()


def test_rollback_restores_code_app_but_not_settings_databases_or_service_state(held):
    x=held;x.installed();x.h.restore(x.rb,['costs','vault'])
    (x.c/'data').mkdir();db=x.c/'data/jarvis.db';db.write_text('synthetic-new-data-do-not-restore')
    settings=(x.c/'.env').read_bytes();plists=x.h.policy_files();x.sys.calls.clear();x.h.rollback(x.rb)
    assert x.sys.head==PRIOR and not x.sys.jobs
    assert (x.app/'Contents/MacOS/MortimerHost').read_text()=='synthetic-prior-app'
    assert db.read_text()=='synthetic-new-data-do-not-restore' and (x.c/'.env').read_bytes()==settings
    assert x.h.policy_files()==plists
    assert not any(a[0]=='launchctl' and a[1] in ('enable','bootstrap','kickstart') for a in x.sys.calls)
    restore_at=next(i for i,a in enumerate(x.sys.calls) if a[0]=='git' and 'checkout' in a)
    assert sum(a[0]=='launchctl' and a[1]=='disable' for a in x.sys.calls[:restore_at])==6
    assert x.m.read_json(x.rb/'rollback-held.json')['settings_restored'] is False


def test_quarantine_failure_never_restores_old_code(held):
    x=held;x.installed();label=x.m.LABELS['bot'];x.sys.jobs[label]=90000111;x.sys.flags[label]='enabled';x.sys.fail_bootout=label
    with pytest.raises(x.m.HeldError):x.h.rollback(x.rb)
    assert x.sys.head==TARGET and not any('checkout' in a for a in x.sys.calls)


def test_orphan_liveness_blocks_code_rollback(held):
    x=held;x.installed();label=x.m.LABELS['costs'];x.sys.jobs[label]=90000111;x.sys.survivors.add(90000111)
    with pytest.raises(x.m.HeldError):x.h.rollback(x.rb)
    assert x.sys.head==TARGET


def test_policy_drift_or_archive_tamper_never_reopens_service(held):
    x=held;x.installed();(x.c/'.env').write_text('JARVIS_LLM_ACCESS_MODE=legacy\n')
    with pytest.raises(x.m.HeldError):x.h.rollback(x.rb)
    assert x.sys.head==TARGET and not x.sys.jobs


def test_runtime_dirt_and_wrong_bundle_source_refuse_installed_receipt(held):
    x=held;x.snapshot();x.sys.head=TARGET;x.sys.dirty=True
    with pytest.raises(x.m.HeldError):x.h.installed(x.rb)
    x.sys.dirty=False
    with pytest.raises(x.m.HeldError):x.h.installed(x.rb)
    assert not (x.rb/'installed-held.json').exists()


def test_foreign_lock_never_reclaimed_or_unlocked(held):
    x=held;token=x.h.lock()
    with pytest.raises(FileExistsError):x.h.lock()
    with pytest.raises(x.m.HeldError):x.h.unlock('foreign')
    assert (x.home/'MortimerRollback/.held-deploy.lock').is_dir()
    x.h.unlock(token);assert not (x.home/'MortimerRollback/.held-deploy.lock').exists()


def test_unrelated_app_never_quit(held):
    x=held;x.sys.app_exe=str(x.home/'unrelated/MortimerHost')
    with pytest.raises(x.m.HeldError):x.h.stop_app()
    assert not any(a[0]=='osascript' for a in x.sys.calls)

@pytest.mark.parametrize('args',[['--install-held'],['--approval-receipt','missing'],['--restore-local','missing'],['--unknown']])
def test_shell_invalid_flags_stop_before_any_operator_command(tmp_path,args):
    home=tmp_path/'empty-home';home.mkdir()
    result=subprocess.run(['bash',str(SCRIPT),*args],env={'HOME':str(home),'PATH':'/usr/bin:/bin'},capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and list(home.iterdir())==[]


def test_generated_frozen_rollback_executes_with_only_fake_services_and_temp_files(held):
    x=held;x.installed();(x.c/'data').mkdir();db=x.c/'data/jarvis.db';db.write_text('synthetic-new-data')
    binpath=x.home/'fake-bin';binpath.mkdir();head=x.home/'fake-head';head.write_text(TARGET);audit=x.home/'fake-commands'
    driver=binpath/'operator'
    driver.write_text('''#!/usr/bin/python3
import json,os,pathlib,shutil,sys
name=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:]
with open(os.environ['FAKE_AUDIT'],'a') as out:out.write(name+' '+' '.join(a)+'\\n')
if name=='launchctl':
 if a[0]=='print-disabled':
  for s in ['vault','bot','extractor','admin','costs','status-daily','sandbox-prune']:print('"com.mortimer.'+s+'" => disabled')
 elif a[0]=='print':
  print('Could not find service "'+a[1].rsplit('/',1)[-1]+'"',file=sys.stderr);sys.exit(113)
 elif a[0] not in ['disable','bootout']:sys.exit(99)
elif name=='pgrep':sys.exit(1)
elif name=='ps':pass
elif name=='git':
 if 'checkout' in a:pathlib.Path(os.environ['FAKE_HEAD']).write_text(a[-1])
 elif 'rev-parse' in a:print(pathlib.Path(os.environ['FAKE_HEAD']).read_text())
 else:sys.exit(98)
elif name=='ditto':shutil.copytree(a[0],a[1],dirs_exist_ok=True)
else:sys.exit(97)
''');driver.chmod(0o700)
    for name in ('launchctl','pgrep','ps','git','ditto'):(binpath/name).symlink_to(driver.name)
    settings=(x.c/'.env').read_bytes()
    r=subprocess.run(['bash',str(x.rb/'ROLLBACK.sh')],env={'HOME':str(x.home),'PATH':str(binpath)+':/usr/bin:/bin',
          'FAKE_AUDIT':str(audit),'FAKE_HEAD':str(head),'LANG':'C'},capture_output=True,text=True,timeout=15)
    assert r.returncode==0,r.stderr
    assert head.read_text()==PRIOR and db.read_text()=='synthetic-new-data' and (x.c/'.env').read_bytes()==settings
    assert x.m.read_json(x.rb/'rollback-held.json')['services_restarted'] is False
    calls=audit.read_text();assert 'bootstrap' not in calls and 'kickstart' not in calls and 'launchctl enable' not in calls
    assert 'synthetic-only' not in r.stdout+r.stderr
    assert calls.index('launchctl disable')<calls.index('git -C')
    assert not (x.home/'MortimerRollback/.held-deploy.lock').exists()


def test_install_missing_bound_approval_stops_before_source_or_service_mutation(tmp_path):
    c=tmp_path/'jarvis-voice-ai-clean';(c/'.venv/bin').mkdir(parents=True)
    (c/'.venv/bin/python').symlink_to(shutil.which('python3'))
    marker=c/'untouched';marker.write_text('synthetic-before')
    binpath=tmp_path/'bin';binpath.mkdir();audit=tmp_path/'git-calls'
    git=binpath/'git';git.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_AUDIT"
case " $* " in
 *" rev-parse "*) echo 2222222222222222222222222222222222222222;;
 *" merge-base "*) exit 0;;
esac
exit 0
''');git.chmod(0o700)
    r=subprocess.run(['bash',str(SCRIPT),'--install-held','--approval-receipt',str(tmp_path/'absent.json')],
       env={'HOME':str(tmp_path),'PATH':str(binpath)+':/usr/bin:/bin','FAKE_AUDIT':str(audit),'LANG':'C'},
       capture_output=True,text=True,timeout=15)
    assert r.returncode!=0 and 'held preflight refused' in r.stdout
    assert marker.read_text()=='synthetic-before'
    assert 'checkout' not in audit.read_text() and not list((tmp_path/'MortimerRollback').glob('release-*'))
    assert not (tmp_path/'MortimerRollback/.held-deploy.lock').exists()


def test_restore_does_not_reset_existing_bundle_identity_receipt(held):
    x=held;x.installed();(x.app/'Contents/MacOS/MortimerHost').write_text('synthetic-app-drift')
    before=(x.rb/'installed-held.json').read_bytes()
    with pytest.raises(x.m.HeldError):x.h.restore(x.rb,['costs'])
    assert (x.rb/'installed-held.json').read_bytes()==before
    assert not x.sys.jobs


def test_restore_requires_prior_canonical_installed_receipt(held):
    x=held;x.installed();(x.rb/'installed-held.json').unlink()
    with pytest.raises(x.m.HeldError):x.h.restore(x.rb,['costs'])
    assert not x.sys.jobs


def test_code_checkout_cannot_restore_a_tracked_private_env(held):
    x=held;x.sys.tracked_env=True
    with pytest.raises(x.m.HeldError):x.snapshot()
    assert not (x.rb/'held-policy.json').exists()
    x.sys.tracked_env=False;x.sys.private_tree=True
    with pytest.raises(x.m.HeldError):x.h.program(x.source.parent.parent,TARGET)


def test_default_legacy_cannot_bypass_per_service_guard_envelope(held):
    x=held;(x.c/'.env').write_text('JARVIS_LLM_ACCESS_MODE=legacy # synthetic baseline\n')
    x.sys.flags=dict.fromkeys(x.sys.flags,'enabled')
    with pytest.raises(x.m.HeldError):x.h.legacy_allowed()
