"""Disposable trusted-image IPv6 canary; no candidate code or host shares.
Control NAT is used only to prove this synthetic path works before/after the
actual isolation modes. Never use this driver for development or verification.
"""
import fcntl, hashlib, json, os, re, secrets, socket, subprocess, sys, time
from pathlib import Path
ROOT=Path('/Users/larryfix/Documents/Codex/2026-09-09/can/work/codex-isolated-20260924')
OUT=Path('/private/tmp/mortimer-ipv6-verified-20260928')
SANDBOX_HOME=Path('/Users/larryfix/Documents/Codex/MortimerSandbox')
sys.path.insert(0,str(ROOT))
from sandbox.control import provisioning_network_blocks
settings=json.loads((SANDBOX_HOME/'settings.json').read_text())
image=json.loads((SANDBOX_HOME/'images'/settings['images']['mortimer']/'image.json').read_text())
env={'PATH':str(Path(settings['softnet']).parent)+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','TART_HOME':str(SANDBOX_HOME/'tart'),'LANG':'en_US.UTF-8'}
vm='mortimer-ipv6-canary-'+secrets.token_hex(6)
report={'schema_version':1,'vm':vm,'image':settings['images']['mortimer'],'no_host_shares':True,'no_candidate_import':True,'softnet_sha256':hashlib.sha256(Path(settings['softnet']).read_bytes()).hexdigest(),'phases':[],'passed':False}
def save(): (OUT/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
def tart(*args,timeout=30,check=True):
 return subprocess.run([settings['tart'],*args],env=env,capture_output=True,text=True,timeout=timeout,check=check)
def assert_idle():
 running=[x for x in json.loads(tart('list','--format','json').stdout) if x.get('State',x.get('state'))=='running']
 if running: raise RuntimeError('Existing VM is running; do not interrupt it')
def bridge(gateway):
 text=subprocess.check_output(['/sbin/ifconfig'],text=True)
 for block in re.split(r'(?=^\S[^\n]*: flags=)',text,flags=re.M):
  if not re.match(r'bridge\d+:',block) or 'member: vmenet' not in block or ('inet '+gateway+' ') not in block: continue
  match=re.search(r'inet6 (fe80::[^\s%]+)%([^\s]+)',block)
  if match: return match.group(1),match.group(2)
 raise RuntimeError('No active VM bridge IPv6 link-local address')
GUEST='''import json,socket,subprocess,sys
host,port,token=sys.argv[1],int(sys.argv[2]),sys.argv[3].encode()
family=socket.AF_INET6 if sys.argv[4]=='6' else socket.AF_INET
r=subprocess.run(['/sbin/route','-n','get','default'],capture_output=True,text=True)
interface=next((s.split(':',1)[1].strip() for s in r.stdout.splitlines() if s.strip().startswith('interface:')),None)
if not interface: raise RuntimeError('No guest interface')
route=subprocess.run(['/sbin/route','-n','get','-inet6',host+'%'+interface],capture_output=True,text=True)
info={'interface':interface,'ipv6_target_route_observed':route.returncode==0 and 'interface:' in route.stdout,'sent':False,'reply':False}
with socket.socket(family,socket.SOCK_DGRAM) as sock:
 sock.settimeout(4)
 try:
  target=(host,port,0,socket.if_nametoindex(interface)) if family==socket.AF_INET6 else (host,port)
  sock.sendto(token,target);info['sent']=True
  info['source_address']=sock.getsockname()[0]
  data,_=sock.recvfrom(256);info['reply']=data==token
 except OSError as exc: info['socket_errno']=exc.errno
info['guest_interface_ipv6_present']='inet6 ' in subprocess.check_output(['/sbin/ifconfig',interface],text=True)
print(json.dumps(info))
'''
if '--preflight' in sys.argv:
 print(json.dumps({'image':image['vm'],'mode_order':['control-before','provisioning','offline','control-after'],'existing_helper_sha256':report['softnet_sha256']}));raise SystemExit(0)
with (SANDBOX_HOME/'start.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 assert_idle();tart('clone',image['vm'],vm,timeout=600);tart('set',vm,'--cpu','4','--memory','8192')
 try:
  for mode in ('control-before','provisioning','offline','control-after'):
   assert_idle()
   args=['run','--no-clipboard','--no-audio','--no-graphics']
   if mode in ('provisioning','offline'):
    args+=['--net-softnet','--net-softnet-block='+(provisioning_network_blocks() if mode=='provisioning' else '0.0.0.0/0')]
   args+=[vm]
   with (OUT/(mode+'.log')).open('wb') as log:
    process=subprocess.Popen([settings['tart'],*args],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
     deadline=time.monotonic()+180
     while True:
      if process.poll() is not None: raise RuntimeError('VM exited before guest readiness')
      try:
       if tart('exec',vm,'/usr/bin/true',timeout=10,check=False).returncode==0: break
      except subprocess.TimeoutExpired: pass
      if time.monotonic()>deadline: raise RuntimeError('Guest readiness timed out')
      time.sleep(1)
     default=tart('exec',vm,'/sbin/route','-n','get','default').stdout
     gateway=next(line.split(':',1)[1].strip() for line in default.splitlines() if line.strip().startswith('gateway:'))
     address,interface=bridge(gateway)
     for version,host in ((4,gateway),(6,address)):
      family=socket.AF_INET6 if version==6 else socket.AF_INET
      token=secrets.token_hex(24).encode()
      with socket.socket(family,socket.SOCK_DGRAM) as listener:
       endpoint=(host,0,0,socket.if_nametoindex(interface)) if version==6 else (host,0)
       listener.bind(endpoint);listener.settimeout(8)
       port=listener.getsockname()[1]
       child=subprocess.Popen([settings['tart'],'exec',vm,'/usr/bin/python3','-c',GUEST,host,str(port),token.decode(),str(version)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
       received=False
       try:
        data,peer=listener.recvfrom(256)
        if data==token: received=True;listener.sendto(data,peer)
       except socket.timeout: pass
       stdout,stderr=child.communicate(timeout=20)
       if child.returncode: raise RuntimeError('Guest canary failed')
       observation=json.loads(stdout)
      observation.update(mode=mode,ip_version=version,host_received_canary=received,host_bridge=interface,bridge_matched_guest_gateway=True)
      report['phases'].append(observation);save();print(json.dumps(observation),flush=True)
      if mode.startswith('control') and not (received and observation['reply']):
       raise RuntimeError('Positive control failed; containment remains unproven')
    finally:
     tart('stop',vm,timeout=30,check=False)
     try: process.wait(timeout=30)
     except subprocess.TimeoutExpired: raise RuntimeError('VM process did not stop')
  report['diagnostic_only']=False
  report['passed']=len(report['phases'])==8 and all(p['sent'] and (p['ip_version']==4 or p['ipv6_target_route_observed']) and ((p['host_received_canary'] and p['reply']) if p['mode'].startswith('control') else (not p['host_received_canary'] and not p['reply'])) for p in report['phases'])
  save()
 finally:
  stopped=all(x.get('State',x.get('state'))=='stopped' for x in json.loads(tart('list','--format','json').stdout) if x.get('Name',x.get('name'))==vm)
  if stopped: tart('delete',vm);report['disposable_vm_deleted']=True
  save()
