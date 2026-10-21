"""Replayable offline2.1.291 native-contract fixture.

Run with the repository dependency environment and PYTHON_DOTENV_DISABLED=1;
redirect stdout to a private local receipt. Only an installed CLI is inspected;
this never installs software, changes a gate or creates workload acceptance.
All model endpoints/auth/home and callback data are synthetic/local.
"""
from pathlib import Path
import asyncio, importlib.util, sys, os, json, hashlib, subprocess, tempfile, datetime, shutil
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('native_contract_fixture',ROOT/'scripts/verify_claude_developer_capability.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
from jarvis import subscription_tools as st
from jarvis.model_execution import ModelToolReference
from jarvis.subscription import SubscriptionCapabilityError, _subscription_env
MODEL='claude-haiku-4-5'
m.REFERENCE='synthetic-native-fixture.txt'
m.CONSTRAINT='This offline synthetic protocol fixture uses stub callbacks only. No real read, edit, private operation or model inference is authorized.'
known_versions_before=st.CLAUDE_NATIVE_VERSIONS
selected=shutil.which('claude');assert selected;binary=Path(selected).resolve()
with tempfile.TemporaryDirectory(prefix='mortimer-candidate-version-',dir='/tmp') as d:
 p=subprocess.run([str(binary),'--version'],cwd=d,env=_subscription_env(d),capture_output=True,text=True,timeout=5)
assert p.returncode==0 and p.stdout.strip()=='2.1.291 (Claude Code)'
identity={'path':str(binary),'version':p.stdout.strip(),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
try:st.claude_tool_runtime_identity();production_refusal=False
except SubscriptionCapabilityError:production_refusal=True
# Inspection is diagnostic whether the version is already known or still a candidate.
# Never mutate CLAUDE_NATIVE_VERSIONS or generate a production capability receipt.
refs=(ModelToolReference('repo_read_file',{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False},'Read the synthetic protocol fixture only'),ModelToolReference('selfedit_finish',{'type':'object','properties':{},'additionalProperties':False},'Synthetic completion acknowledgement; no real edit'))
class Guard:
 def __init__(self):self.reads=0;self.calls=[]
 def check(self):assert hashlib.sha256(binary.read_bytes()).hexdigest()==identity['sha256']
 async def call(self,name,arguments,scope):
  self.check();assert name in {'repo_read_file','selfedit_finish'};self.calls.append(name)
  if name=='repo_read_file':assert arguments=={'path':m.REFERENCE};self.reads+=1;return json.dumps({'synthetic':True,'content':'MORTIMER_PROTOCOL_FIXTURE_ONLY'})
  assert arguments=={};return json.dumps({'synthetic':True,'status':'finished'})
async def main():
 report={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate_identity':identity,'model':MODEL,'protocol':st.PROTOCOL,'native_control_sha256':st._json_digest(st.NATIVE_CONTROL_CONTRACT),'production_admission_unchanged':True,'inference_requests':0,'synthetic_only':True,'rounds':{}}
 with tempfile.TemporaryDirectory(prefix='mortimer-291-offline-',dir='/tmp') as d:
  directory=Path(d)
  for name,negative in [('positive',False),('unadvertised_builtin',True)]:
   guard=Guard()
   async with m.loopback_fixture(directory,MODEL,refs,bash=negative) as fixture:
    value=await m.protocol_round(identity,MODEL,refs,guard,45,environment=fixture['environment'],expect_bash=negative)
    validated=m.verified_loopback(fixture,MODEL)
    canary_absent=not fixture['canary'].exists()
   report['rounds'][name]={'result':value,'loopback_verified':validated,'canary_absent':canary_absent,'fixture_closed':fixture['closed'],'synthetic_calls':guard.calls,'observations':fixture['observations']}
   assert validated and canary_absent and fixture['closed'] and value['cleanup_verified']
   assert all(x['constraint_present'] for x in fixture['observations'])
   if negative:assert value['unadvertised_host_tool_rejected'] and value['native_host_ingress_count']==0 and not guard.calls
   else:assert value['native_tool_call_observed'] and value['terminal_success_without_error_items'] and value['system_constraints_observed'] and value['unknown_tool_rejected']
 report['result']='PASS'
 assert st.CLAUDE_NATIVE_VERSIONS==known_versions_before
 report['known_versions_before']=sorted(known_versions_before)
 report['candidate_initially_refused']=production_refusal
 report['limits']=['Offline native protocol only; no live inference, quality, latency or voice acceptance.', 'Exact workload/model/schema/binary receipts, source privacy and activation gates remain mandatory.']
 print(json.dumps(report,indent=2))

asyncio.run(main())
