"""Independent inert source admission/actor counterexamples, preserved unchanged."""
import json
import uuid
from types import SimpleNamespace

from jarvis import development_sources as sources
from jarvis.bot.sensitive_turn import SensitiveTurn,current_sensitive_turn
from jarvis.privacy_policy import DataPolicy,make_tool_execution_scope,validate_tool_result
from jarvis.runlog.context import run_logger_scope
from jarvis.runlog.store import RunLogger,get_run
from jarvis.db import get_conn
from jarvis.tenant import user_id_scope
from tests.unit.test_development_sources import workspace
from tests.unit.test_workspace_source_bridge import bridge
from sandbox.durable import atomic_json


async def test_strengthened_floor_between_prepare_and_write_carries_to_next_turn(bridge, monkeypatch, tmp_path):
    canary='PRIVATE_LATE_ACQUIRED_LOCAL_ONLY_CANARY_e632'
    original=bridge.child.call_tool
    async def strengthen(name, arguments, *, meta=None):
        if name=='selfedit_write' and meta['mortimer_development_source']['phase']=='execute':
            sources.retain_workspace_floor(get_run(bridge.parent)['run'],
                DataPolicy('local_only','actual-host-acquired-private-source'))
        return await original(name, arguments, meta=meta)
    monkeypatch.setattr(bridge.child,'call_tool',strengthen)
    policy,result,_=await bridge.call('selfedit_write',{'path':'jarvis/app.py','content':canary,'rationale':'synthetic'})
    assert result['ok'] and policy.level=='local_only'
    journal=json.loads((bridge.w.controller.task_dir(bridge.w.task)/'files.json').read_text())
    print('WRITTEN_JOURNAL_FLOOR',journal['source_floor'])
    parent=str(uuid.uuid4())
    with user_id_scope(bridge.owner):
        logger=RunLogger(parent,'developer','Developer','public later read',session_id=bridge.session_id,root=tmp_path)
        logger.start()
    arguments={'path':'jarvis/app.py'}
    scope=make_tool_execution_scope(parent,'new-task','new-call','selfedit_read',arguments,DataPolicy('approved_external','later-public-input'))
    fresh=current_sensitive_turn.set(SensitiveTurn())
    try:
        with run_logger_scope(logger):
            envelope=await bridge.registry.call_classified('selfedit_read',arguments,execution_scope=scope)
    finally:
        current_sensitive_turn.reset(fresh)
    next_policy,content=validate_tool_result(scope,envelope)
    print('NEXT_TURN_POLICY',next_policy.level,content)
    assert json.loads(content)['content']==canary
    assert next_policy.level=='local_only'


def test_actual_app_worker_preserves_stable_host_parent(bridge,monkeypatch):
    from jarvis.agents import upgrade_agent as ua
    from jarvis.agents.workspace import AppWorkspace
    from jarvis.model_routing import AccessRoute,ResolvedModelRoute
    monkeypatch.setenv('JARVIS_MODEL_ROUTING_ENABLED','1')
    monkeypatch.setenv('ANTHROPIC_API_KEY','synthetic-unused-key')
    monkeypatch.setenv('JARVIS_MODEL_PREFERENCES_ENABLED','0')
    selected=ResolvedModelRoute('app_builder','claude-opus','fixture-model','openai','',
        AccessRoute('direct_api','openai_compatible','provider_api',None,'approved_external',capabilities=('text','tools')),
        None,'openai/fixture-model','interactive')
    monkeypatch.setattr(ua,'resolve_model_route_checked',lambda *args,**kwargs:selected)
    workspace=AppWorkspace('public-fixture',github_client=SimpleNamespace(token='synthetic-unused'))
    monkeypatch.setattr(bridge.admin,'AppWorkspace',lambda app:workspace)
    original=bridge.admin._make_appbuild_agent
    seen=[]
    def make(workspace,profile):
        agent=original(workspace,profile)
        def stop_before_workspace_or_model(*args,**kwargs):
            seen.append((agent._execution_parent_id,agent._run_snapshot.budget.parent_request_id))
            return {'ok':False,'summary':'synthetic stop before VM/model'}
        monkeypatch.setattr(agent,'_run_with_execution_loop',stop_before_workspace_or_model)
        return agent
    monkeypatch.setattr(bridge.admin,'_make_appbuild_agent',make)
    with user_id_scope(bridge.owner):
        bridge.admin._run_appbuild_agent('public-fixture','public goal','claude-opus',run_id=bridge.parent,
            data_policy=DataPolicy('approved_external','synthetic-input'))
    print('ACTUAL_APP_WORKER_PARENT',seen,'EXPECTED',bridge.parent)
    assert seen==[(bridge.parent,bridge.parent)]


async def test_strengthened_floor_after_prepare_is_in_worker_goal_and_plan_policies(bridge,monkeypatch):
    root=bridge.w.service.repo_root
    (root/'docs').mkdir()
    (root/'docs/REPO_MAP.md').write_text('public standing project plan')
    monkeypatch.setenv('JARVIS_REPO_ROOT',str(root))
    launched=[]
    class Thread:
        def __init__(self,*,target,args,daemon,kwargs=None):
            launched.append((args,kwargs or {}))
        def start(self):
            pass
    monkeypatch.setattr(bridge.admin.threading,'Thread',Thread)
    monkeypatch.setattr(bridge.admin,'_make_agent',lambda *args:SimpleNamespace(model_label=lambda:'public-fixture'))
    original=bridge.child.call_tool
    async def strengthen(name,arguments,*,meta=None):
        if name=='selfedit_start' and meta['mortimer_development_source']['phase']=='execute':
            sources.retain_workspace_floor(get_run(bridge.parent)['run'],DataPolicy('local_only','actual-host-acquisition'))
        return await original(name,arguments,meta=meta)
    monkeypatch.setattr(bridge.child,'call_tool',strengthen)
    policy,result,_=await bridge.call('selfedit_start',{'goal':'PRIVATE_LOCAL_ONLY_GOAL_e632','confirm':True,'plan_path':'docs/REPO_MAP.md'})
    assert result['ok'] and policy.level=='local_only' and len(launched)==1
    args,kwargs=launched[0]
    assert args[2]=='public standing project plan'
    print('WORKER_DATA_FLOOR',kwargs['data_policy'].level,'PLAN_FLOOR',kwargs['plan_policy'].level)
    assert kwargs['data_policy'].level=='local_only'


async def test_finish_cannot_validate_changed_retained_actor_after_proof(bridge,monkeypatch):
    _,written,_=await bridge.call('selfedit_write',{'path':'jarvis/app.py','content':'public edit','rationale':'public'})
    assert written['ok']
    monkeypatch.setattr(bridge.admin,'authoring_enabled',lambda:True)
    foreign=str(uuid.uuid4())
    original=bridge.admin.selfedit_finish
    def swap_actor():
        state=bridge.w.service._session()._read()
        atomic_json(bridge.w.directory/'session.json',{**state,'run_id':foreign})
        return original()
    monkeypatch.setattr(bridge.admin,'selfedit_finish',swap_actor)
    validated=[]
    def validate():
        validated.append(bridge.w.service._session()._read()['run_id'])
        return {'ok':False,'checks':[]}
    monkeypatch.setattr(bridge.w.service,'validate',validate)
    class Thread:
        def __init__(self,*,target,daemon,**kwargs):
            self.target=target
        def start(self):
            self.target()
    monkeypatch.setattr(bridge.admin.threading,'Thread',Thread)
    _,result,_=await bridge.call('selfedit_finish',{})
    print('FINISH_RESULT',result,'VALIDATED_ACTORS',validated)
    assert not result['ok']
    assert validated==[]


async def test_fresh_start_cannot_discard_foreign_retained_job(bridge,monkeypatch):
    stopped,destroyed=[],[]
    monkeypatch.setattr(bridge.w.controller,'stop',lambda task:stopped.append(task))
    monkeypatch.setattr(bridge.w.controller,'destroy',lambda task:destroyed.append(task))
    with get_conn() as conn:
        conn.execute('UPDATE agent_runs SET user_id=?,session_id=? WHERE run_id=?',
            ('foreign-owner',str(uuid.uuid4()),bridge.w.parent))
        conn.commit()
    class Agent:
        def model_label(self):
            return 'public-fixture'
        def run(self,*args,**kwargs):
            return {'ok':False,'summary':'synthetic stopped worker'}
    monkeypatch.setattr(bridge.admin,'_make_agent',lambda *args:Agent())
    class Thread:
        def __init__(self,*,target,args=(),daemon,kwargs=None):
            self.target,self.args,self.kwargs=target,args,kwargs or {}
        def start(self):
            self.target(*self.args,**self.kwargs)
    monkeypatch.setattr(bridge.admin.threading,'Thread',Thread)
    _,result,_=await bridge.call('selfedit_start',{'goal':'fresh public goal','confirm':True})
    print('FRESH_START_RESULT',result,'STOPPED_TASKS',stopped,'DESTROYED_TASKS',destroyed)
    assert stopped==[] and destroyed==[]


async def test_strengthened_floor_inside_actual_write_invoke_survives_next_turn(bridge,monkeypatch,tmp_path):
    canary='PRIVATE_INSIDE_WRITE_LOCAL_ONLY_CANARY_c044'
    original=bridge.w.service.propose_edit
    def strengthen(*args,**kwargs):
        sources.retain_workspace_floor(get_run(bridge.parent)['run'],DataPolicy('local_only','actual-host-acquisition-inside-invoke'))
        return original(*args,**kwargs)
    monkeypatch.setattr(bridge.w.service,'propose_edit',strengthen)
    policy,result,_=await bridge.call('selfedit_write',{'path':'jarvis/app.py','content':canary,'rationale':'synthetic'})
    assert result['ok'] and policy.level=='local_only'
    journal=json.loads((bridge.w.controller.task_dir(bridge.w.task)/'files.json').read_text())
    print('INSIDE_WRITTEN_FILE_FLOOR',journal['source_floor'],'RETAINED_JOB_FLOOR',sources.workspace_floor(get_run(bridge.w.parent)['run']).level)
    parent=str(uuid.uuid4())
    with user_id_scope(bridge.owner):
        logger=RunLogger(parent,'developer','Developer','public later read',session_id=bridge.session_id,root=tmp_path)
        logger.start()
    arguments={'path':'jarvis/app.py'}
    scope=make_tool_execution_scope(parent,'new-task','new-call','selfedit_read',arguments,DataPolicy('approved_external','later-public-input'))
    fresh=current_sensitive_turn.set(SensitiveTurn())
    try:
        with run_logger_scope(logger):
            envelope=await bridge.registry.call_classified('selfedit_read',arguments,execution_scope=scope)
    finally:
        current_sensitive_turn.reset(fresh)
    next_policy,content=validate_tool_result(scope,envelope)
    print('INSIDE_NEXT_TURN_POLICY',next_policy.level,content)
    assert json.loads(content)['content']==canary
    assert next_policy.level=='local_only'
