#!/bin/bash
# DEPLOY-MAIN: deploy GitHub main to production (~/jarvis-voice-ai-clean).
# Run it from any checkout of this repository, production included:
#   bash scripts/deploy_main.sh                        full verification
#   bash scripts/deploy_main.sh --reuse-verification   reuse an earlier passing run on the same commit
#   bash scripts/deploy_main.sh --install-held --approval-receipt FILE [--reuse-verification]
#   bash scripts/deploy_main.sh --restore-local SNAPSHOT costs,vault
#   bash scripts/deploy_main.sh --rollback-held SNAPSHOT
# Held modes require bound review/CI receipts and preserve the direct-call shutdown.
# Rollback never restarts services or restores databases/settings. Admin is excluded.
# Mortimer names it "DEPLOY-MAIN" after every merge. It moved here from the
# git-ignored closure-checks/DEPLOY-MAIN.sh on 2026-09-26 (Larry's decision of
# 2026-09-25) and is human-only (config/self_edit_allowlist.json deny).
# Phases, each gated; nothing in production changes until phase C:
#   A verify  -- build + all three test suites on the exact target, in a throwaway worktree
#   B snapshot-- rollback folder: live DB backups, code tarball, current app bundle, ROLLBACK.sh
#   C install -- production checkout -> target, build the app there (services untouched so far)
#   D switch  -- quit app, restart the 5 services, health checks, open production app, receipt
# Logs, receipts and verification worktrees go under ~/MortimerRollback.
# Runs as you (your git, your gh, your launchd). Prints no secrets.
#
# The whole script is one function, called on the last line. Phase C checks
# production out at the target, which replaces this file when it is run from
# production. Bash reads a script as it goes, so without the function it would
# go on reading the new file at the old offset. A function is parsed in full
# before it runs, and the last line is read before the call starts.
set -uo pipefail

main() {
  HELD=0; REUSE=0; HELD_OP=""; APPROVAL=""; SNAPSHOT=""; LOCAL_SERVICES=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --install-held) [ -z "$HELD_OP" ] && [ "$HELD" = 0 ] || return 2; HELD=1; shift;;
      --reuse-verification) [ "$REUSE" = 0 ] || return 2; REUSE=1; shift;;
      --approval-receipt) [ $# -ge 2 ] && [ -z "$APPROVAL" ] || return 2; APPROVAL=$2; shift 2;;
      --rollback-held) [ $# -eq 2 ] && [ "$HELD" = 0 ] && [ "$REUSE" = 0 ] && [ -z "$APPROVAL" ] || return 2; HELD_OP=rollback; SNAPSHOT=$2; shift 2;;
      --restore-local) [ $# -eq 3 ] && [ "$HELD" = 0 ] && [ "$REUSE" = 0 ] && [ -z "$APPROVAL" ] || return 2; HELD_OP=restore; SNAPSHOT=$2; LOCAL_SERVICES=$3; shift 3;;
      *) echo "unknown deployment argument" >&2; return 2;;
    esac
  done
  [ "$HELD" = 1 ] || [ -z "$APPROVAL" ] || return 2
  [ "$HELD" = 0 ] || [ -n "$APPROVAL" ] || return 2
  held_python() {
    /usr/bin/python3 -I -S - "$@" <<'PY_HELD'
# BEGIN HELD PYTHON
from __future__ import annotations
import hashlib, json, os, pathlib, plistlib, re, shutil, signal, stat, subprocess, sys, tarfile, tempfile, time, urllib.request, uuid

MODE = 'direct_apis_disabled'
LABELS = {x: 'com.mortimer.' + x for x in ('vault','bot','extractor','admin','costs')}
LABELS['status-daily'] = 'com.mortimer.status-daily'
CLEANUP = 'com.mortimer.sandbox-prune'
LOCAL = {'costs':(8487,'/openapi.json'), 'vault':(8484,'/health')}
CHECKS = {'allowlist','policy-tests','controller-tests','knowledge-base','validate'}

class HeldError(RuntimeError): pass

def require(ok, message):
    if not ok: raise HeldError(message)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def private_json(path, data):
    p=pathlib.Path(path); require(not p.is_symlink(), 'unsafe receipt path')
    fd,name=tempfile.mkstemp(prefix='.held-',dir=p.parent)
    try:
        with os.fdopen(fd,'w') as out:json.dump(data,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(name,p);p.chmod(0o600)
    finally:
        if os.path.exists(name):os.unlink(name)

def read_json(path):
    p=pathlib.Path(path);s=p.lstat()
    require(stat.S_ISREG(s.st_mode) and not p.is_symlink() and s.st_uid==os.getuid()
            and not s.st_mode&0o022 and s.st_nlink==1 and s.st_size<2_000_000,'unsafe receipt')
    return json.loads(p.read_text())

def revision(value):
    require(isinstance(value,str) and re.fullmatch('[0-9a-f]{40}',value),'exact revision required')
    return value

def tree_digest(path):
    p=pathlib.Path(path);require(p.is_dir() and not p.is_symlink(),'app snapshot missing')
    values=[]
    for base,dirs,files in os.walk(p,followlinks=False):
        for name in sorted(dirs+files):
            f=pathlib.Path(base)/name;r=str(f.relative_to(p));mode=stat.S_IMODE(f.lstat().st_mode)
            if f.is_symlink(): values.append([r,mode,'link',os.readlink(f)])
            elif f.is_file():values.append([r,mode,digest(f)])
            else:values.append([r,mode,'directory'])
    return hashlib.sha256(json.dumps(sorted(values),separators=(',',':')).encode()).hexdigest()

class System:
    def run(self,argv,check=True):
        try:r=subprocess.run([str(x) for x in argv],capture_output=True,text=True,timeout=40)
        except Exception:raise HeldError('operator command unavailable') from None
        if check:require(r.returncode==0,'operator command failed')
        return r
    def request(self,port,path):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
        with opener.open('http://127.0.0.1:'+str(port)+path,timeout=3) as response:
            require(response.getcode()==200,'local health refused')
    def alive(self,pid):
        try:os.kill(pid,0);return True
        except ProcessLookupError:return False
        except PermissionError:return True
    def sleep(self):time.sleep(.2)

class Held:
    def __init__(self,c,source,system=None):
        self.c=pathlib.Path(c).resolve();self.source=pathlib.Path(source).resolve();self.sys=system or System()
        self.home=pathlib.Path.home().resolve();self.root=self.home/'MortimerRollback';self.domain='gui/'+str(os.getuid())
        require(self.c==self.home/'jarvis-voice-ai-clean','unexpected production root')
    def run(self,*args,check=True):return self.sys.run(args,check)
    def disabled(self):
        text=self.run('launchctl','print-disabled',self.domain).stdout
        return dict(re.findall(r'"([^"]+)"\s*=>\s*(disabled|enabled|true|false)',text))
    def job(self,label):
        r=self.run('launchctl','print',self.domain+'/'+label,check=False)
        if r.returncode==0:
            m=re.search(r'^\s*pid = (\d+)\s*$',r.stdout,re.M)
            return {'loaded':True,'pid':int(m.group(1)) if m else None}
        require('Could not find service' in r.stderr and label in r.stderr,'cannot prove service absence')
        return {'loaded':False,'pid':None}
    def hold(self,subset=None):
        flags=self.disabled()
        names=list(LABELS) if subset is None else list(subset)
        for label in [LABELS[n] for n in names]+[CLEANUP]:
            require(flags.get(label) in {'disabled','true'},'disabled override missing')
            require(not self.job(label)['loaded'],'service not held')
    def policy_files(self):
        env=self.c/'.env';st=env.lstat()
        require(stat.S_ISREG(st.st_mode) and not env.is_symlink() and st.st_uid==os.getuid() and not st.st_mode&0o022,'unsafe settings file')
        text=env.read_text()
        lines=[x for x in text.splitlines() if re.match(r'^\s*(?:export\s+)?JARVIS_LLM_ACCESS_MODE\s*=',x)]
        pattern=r'''^\s*(?:export\s+)?JARVIS_LLM_ACCESS_MODE\s*=\s*(?:direct_apis_disabled|'direct_apis_disabled'|"direct_apis_disabled")\s*(?:#.*)?$'''
        require(len(lines)==1 and re.fullmatch(pattern,lines[0]),'disk shutdown policy missing or ambiguous')
        require(os.environ.get('JARVIS_LLM_ACCESS_MODE',MODE)==MODE,'ambient policy conflicts')
        files={'.env':digest(env)}
        for label in LABELS.values():
            p=self.home/'Library/LaunchAgents'/(label+'.plist');s=p.lstat()
            require(not p.is_symlink() and stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid()
                    and not s.st_mode&0o022,'unsafe launch envelope')
            data=plistlib.loads(p.read_bytes())
            require(data.get('Label')==label and data.get('EnvironmentVariables',{}).get('JARVIS_LLM_ACCESS_MODE')==MODE,
                    'launch envelope shutdown policy missing')
            files[label]=digest(p)
        return files
    def legacy_allowed(self):
        mode=os.environ.get('JARVIS_LLM_ACCESS_MODE')
        if (self.c/'.env').exists():
            matches=re.findall(r'^\s*(?:export\s+)?JARVIS_LLM_ACCESS_MODE\s*=\s*([^\n]+)',(self.c/'.env').read_text(),re.M)
            if matches: require(len(matches)==1 and re.fullmatch(r'''(?:legacy|'legacy'|"legacy")\s*(?:#.*)?''',matches[0].strip()),'held policy requires held deployment')
        require(mode in (None,'legacy'),'held policy requires held deployment')
        flags=self.disabled()
        require(not any(flags.get(x) in {'disabled','true'} for x in LABELS.values()),'disabled services require held deployment')
        for label in LABELS.values():
            p=self.home/'Library/LaunchAgents'/(label+'.plist')
            if p.exists():
                require(not p.is_symlink(),'unsafe launch envelope')
                info=plistlib.loads(p.read_bytes());mode=info.get('EnvironmentVariables',{}).get('JARVIS_LLM_ACCESS_MODE')
                require(mode in (None,'legacy'),'launch policy requires held deployment')
                require(info.get('Disabled') is not True or flags.get(label) in {'enabled','false'},'disabled launch envelope requires held deployment')
    def program(self,repo,rev):
        rows=[]
        for line in self.run('git','-C',repo,'ls-tree','-r',revision(rev)).stdout.splitlines():
            info,path=line.split('\t',1)
            require(path!='.env' and not (path.startswith('.env.') and path!='.env.example'),'private settings in code tree')
            if path=='ROADMAP.md' or path.startswith(('docs/plans/','docs/acceptance/','docs/roadmap-log/')):continue
            rows.append([path,info])
        require(rows,'empty program manifest')
        return hashlib.sha256(json.dumps(sorted(rows),separators=(',',':')).encode()).hexdigest()
    def approval(self,repo,target,path):
        a=read_json(path);require(a.get('version')==1 and a.get('target')==target,'approval target mismatch')
        program=self.program(repo,target)
        for kind in ('review','ci'):
            p=a.get(kind+'_receipt');require(isinstance(p,str),'missing gate receipt')
            receipt=read_json(p);require(digest(p)==a.get(kind+'_sha256'),'gate receipt hash mismatch');rev=revision(receipt.get('source'))
            require(self.program(repo,rev)==program and receipt.get('program_sha256')==program,'gate program mismatch')
            if kind=='review':require(receipt.get('verdict')=='no_blocking_findings','required review not passed')
            else:require(receipt.get('checks')==dict.fromkeys(CHECKS,'SUCCESS'),'required exact-program CI not passed')
        expected=self.run('git','-C',repo,'show',target+':scripts/deploy_main.sh').stdout.encode()
        require(hashlib.sha256(expected).hexdigest()==digest(self.source),'run exact target canonical script')
        return {'target':target,'program_sha256':program,'approval_sha256':digest(path)}
    def preflight(self,repo,target,path):
        gate=self.approval(repo,revision(target),path);self.hold();self.policy_files();return gate
    def rb_path(self,path):
        p=pathlib.Path(path);require(p.is_dir() and not p.is_symlink(),'snapshot missing')
        p=p.resolve();require(p.parent==self.root and p.stat().st_uid==os.getuid() and not p.stat().st_mode&0o077,'unsafe snapshot directory')
        return p
    def snapshot(self,rb,repo,target,approval):
        rb=self.rb_path(rb);gate=self.preflight(repo,target,approval);self.archive_safe(rb/'code.tgz')
        require(self.run('git','-C',self.c,'ls-files','--error-unmatch','.env',check=False).returncode==1,'private settings must not be tracked')
        frozen=rb/'deploy-main-held.sh';shutil.copyfile(self.source,frozen);frozen.chmod(0o700)
        meta={**gate,'version':1,'production':str(self.c),'prior':revision(self.run('git','-C',self.c,'rev-parse','HEAD').stdout.strip()),
              'policy_files':self.policy_files(),'runner_sha256':digest(frozen),'archive_sha256':digest(rb/'code.tgz'),
              'app_sha256':tree_digest(rb/'MortimerHost.app')}
        private_json(rb/'held-policy.json',meta)
        launcher='#!/bin/bash\nset -euo pipefail\nexec /bin/bash '+__import__('shlex').quote(str(frozen))+' --rollback-held '+__import__('shlex').quote(str(rb))+'\n'
        (rb/'ROLLBACK.sh').write_text(launcher);(rb/'ROLLBACK.sh').chmod(0o700)
    def envelope(self,rb):
        rb=self.rb_path(rb);a=read_json(rb/'held-policy.json');require(a.get('version')==1 and a.get('production')==str(self.c),'snapshot binding mismatch')
        require(digest(self.source)==a.get('runner_sha256'),'frozen operator source changed')
        revision(a.get('prior'));revision(a.get('target'));return rb,a
    def floor(self,a):require(self.policy_files()==a.get('policy_files'),'shutdown policy/envelopes drifted')
    def stop_app(self):
        r=self.run('pgrep','-x','MortimerHost',check=False);require(r.returncode in (0,1),'app inventory unavailable')
        pids=[int(x) for x in r.stdout.split()]
        for pid in pids:
            exe=self.run('ps','-p',str(pid),'-o','comm=').stdout.strip()
            require(exe==str(self.c/'macos/MortimerHost/.build/MortimerHost.app/Contents/MacOS/MortimerHost'),'unrelated app instance; stop before install')
        if pids:self.run('osascript','-e','tell application id "com.mortimer.host" to quit')
        for _ in range(100):
            if not any(self.sys.alive(p) for p in pids):return
            self.sys.sleep()
        raise HeldError('production app did not quit; no install/rollback')
    def quarantine(self):
        owned=set();table={}
        for line in self.run('ps','-axo','pid=,ppid=').stdout.splitlines():
            fields=line.split()
            if len(fields)==2 and all(x.isdigit() for x in fields):table[int(fields[0])]=int(fields[1])
        for label in LABELS.values():
            j=self.job(label)
            if j['pid']:owned.add(j['pid'])
        for _ in range(len(table)+1):
            more={pid for pid,parent in table.items() if parent in owned};old=len(owned);owned.update(more)
            if len(owned)==old:break
        for label in LABELS.values():
            self.run('launchctl','disable',self.domain+'/'+label)
            self.run('launchctl','bootout',self.domain+'/'+label,check=False)
        self.hold()
        for _ in range(100):
            if not any(self.sys.alive(p) for p in owned):return
            self.sys.sleep()
        raise HeldError('owned process remains; no code rollback')
    def installed(self,rb):
        rb,a=self.envelope(rb);self.hold();self.floor(a)
        require(self.run('git','-C',self.c,'rev-parse','HEAD').stdout.strip()==a['target'],'installed source mismatch')
        self.run('git','-C',self.c,'diff','--quiet',a['target'],'--','.',':(exclude)docs/acceptance/adaptive-interface/P2-latency.json')
        untracked=self.run('git','-C',self.c,'ls-files','--others','--exclude-standard').stdout.splitlines()
        require(not any(p.startswith(('jarvis/','macos/','scripts/','sandbox/','config/','services/','mcp_servers/','web/')) for p in untracked),'untracked runtime source')
        info=plistlib.loads((self.c/'macos/MortimerHost/.build/MortimerHost.app/Contents/Info.plist').read_bytes())
        require(info.get('MortimerSourceRevision')==a['target'],'bundle source mismatch')
        a['installed_program_sha256']=self.program(self.c,a['target'])
        require(a['installed_program_sha256']==a['program_sha256'],'installed program mismatch')
        installed={'status':'installed-held','target':a['target'],'policy_sha256':digest(rb/'held-policy.json'),'bundle_sha256':tree_digest(self.c/'macos/MortimerHost/.build/MortimerHost.app')}
        if (rb/'installed-held.json').exists():require(read_json(rb/'installed-held.json')==installed,'installed bundle/receipt drifted')
        else:private_json(rb/'installed-held.json',installed)
    def prelaunch_source(self,name):
        # Hash-stable configuration is not proof of the right executable.
        # Validate the actual source command before any enable/bootstrap.
        import shlex
        p=self.home/'Library/LaunchAgents'/(LABELS[name]+'.plist')
        data=plistlib.loads(p.read_bytes())
        command={'costs':'exec ./scripts/run_costs.sh','vault':'exec ./scripts/run_kb.sh'}[name]
        expected=['/bin/bash','-c','cd '+shlex.quote(str(self.c))+' && '+command]
        require(data.get('ProgramArguments')==expected and not data.get('Program')
                and data.get('WorkingDirectory')==str(self.c),'noncanonical local launch source')
        env=data.get('EnvironmentVariables',{})
        hooks={'BASH_ENV','ENV','PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','LD_PRELOAD',
               'DYLD_INSERT_LIBRARIES','DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH'}
        require(not any(env.get(k) for k in hooks),'unsupported local loader override')
        if name=='vault':require(env.get('MORTIMER_VAULT_DIR',str(self.c/'services/mortimer-vault'))==str(self.c/'services/mortimer-vault'),'foreign KB source')
        executable=self.c/('.venv/bin/python' if name=='costs' else 'services/mortimer-vault/.venv/bin/mortimer-vault')
        require(executable.is_file() and os.access(executable,os.X_OK),'recognized local runtime missing; no PATH fallback')
    def restore(self,rb,names):
        rb,a=self.envelope(rb);require(set(names)<=set(LOCAL) and names and len(names)==len(set(names)),'only explicit costs/vault permitted')
        require((rb/'installed-held.json').is_file(),'held installation receipt missing')
        self.installed(rb);self.hold();self.floor(a)
        try:
            for name in names:
                self.floor(a);self.prelaunch_source(name);label=LABELS[name];self.run('launchctl','enable',self.domain+'/'+label)
                self.run('launchctl','bootstrap',self.domain,self.home/'Library/LaunchAgents'/(label+'.plist'))
                for _ in range(100):
                    job=self.job(label)
                    if job['pid']:break
                    self.sys.sleep()
                require(job['pid'],'new service PID unavailable')
                env=self.run('ps','eww','-p',str(job['pid']),'-o','command=').stdout
                require(re.findall(r'(?:^|\s)JARVIS_LLM_ACCESS_MODE=([^\s]+)',env)==[MODE],'effective service policy unavailable')
                cwd=self.run('lsof','-a','-p',str(job['pid']),'-d','cwd','-Fn').stdout
                paths=[x[1:] for x in cwd.splitlines() if x.startswith('n')]
                require(len(paths)==1 and pathlib.Path(paths[0]).resolve().is_relative_to(self.c),'service source cwd mismatch')
                self.sys.request(*LOCAL[name]);self.floor(a)
            self.hold(set(LABELS)-set(names))
            private_json(rb/'local-restoration.json',{'status':'local-only-restored','services':names,'target':a['target']})
        except Exception:
            self.quarantine();raise HeldError('local restoration failed; services quarantined') from None
    def archive_safe(self,path):
        with tarfile.open(path,'r:gz') as tar:
            for item in tar:
                bits=pathlib.PurePosixPath(item.name).parts
                require(not item.name.startswith('/') and '..' not in bits,'unsafe code archive path')
                require(not any(x in {'.git','.venv','data','logs'} or x=='.env' or x.startswith('.env.') or x.endswith(('.db','.db-wal','.db-shm','.sqlite','.sqlite3')) for x in bits),'archive contains protected settings/data')
                require(not item.issym() and not item.islnk() and (item.isfile() or item.isdir()),'unsafe code archive mode')
    def rollback(self,rb):
        rb,a=self.envelope(rb);self.quarantine();self.stop_app();self.floor(a)
        require(digest(rb/'code.tgz')==a['archive_sha256'] and tree_digest(rb/'MortimerHost.app')==a['app_sha256'],'rollback archive/app changed')
        self.archive_safe(rb/'code.tgz')
        self.run('git','-C',self.c,'checkout','-q','-f','--detach',a['prior'])
        self.run('tar','-C',self.c,'-xzf',rb/'code.tgz')
        app=self.c/'macos/MortimerHost/.build/MortimerHost.app';require(not app.is_symlink() and app.parent.resolve().is_relative_to(self.c),'unsafe app target')
        if app.exists():shutil.rmtree(app)
        self.run('ditto',rb/'MortimerHost.app',app)
        self.hold();self.floor(a)
        require(self.run('git','-C',self.c,'rev-parse','HEAD').stdout.strip()==a['prior'] and tree_digest(app)==a['app_sha256'],'rollback identity mismatch')
        private_json(rb/'rollback-held.json',{'status':'rollback-held','prior':a['prior'],'services_restarted':False,'databases_restored':False,'settings_restored':False})
    def lock(self):
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True);p=self.root/'.held-deploy.lock'
        p.mkdir(mode=0o700);token=uuid.uuid4().hex;private_json(p/'owner.json',{'token':token,'pid':os.getppid()});return token
    def unlock(self,token):
        p=self.root/'.held-deploy.lock';require(read_json(p/'owner.json').get('token')==token,'foreign deployment lease')
        (p/'owner.json').unlink();p.rmdir()

def held_main(args):
    op,c,source,*rest=args;h=Held(c,source)
    if op=='legacy':h.legacy_allowed()
    elif op=='preflight':h.preflight(*rest)
    elif op=='snapshot':h.snapshot(*rest)
    elif op=='hold':h.hold()
    elif op=='floor':_,a=h.envelope(rest[0]);h.floor(a)
    elif op=='quarantine':h.quarantine()
    elif op=='stop-app':h.stop_app()
    elif op=='installed':h.installed(*rest)
    elif op=='restore':h.restore(rest[0],rest[1].split(','))
    elif op=='rollback':h.rollback(*rest)
    elif op=='lock':print(h.lock())
    elif op=='unlock':h.unlock(rest[0])
    else:raise HeldError('unsupported held operation')

if __name__=='__main__':
    try:held_main(sys.argv[1:])
    except Exception as exc:
        print('HELD operation refused: '+(str(exc) if isinstance(exc,HeldError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
# END HELD PYTHON
PY_HELD
  }
  SOURCE_PATH="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
  # A compiler or XCTest error, not a source excerpt that happens to contain
  # "error: " (LAUNCHER-RULES rule 9): ": error: " or "error: " at line start,
  # with or without colour codes.
  ERR_RE='(^|: )(.\[[0-9;]*m)*error: '
  HERE="$(cd "$(dirname "$0")/.." && pwd)"   # the checkout this script is in: production or any clone
  C="$HOME/jarvis-voice-ai-clean"
  PY="$C/.venv/bin/python"
  if [ -n "$HELD_OP" ]; then
    HELD_LOCK_TOKEN=$(held_python lock "$C" "$SOURCE_PATH") || return 1
    trap 'held_python unlock "$C" "$SOURCE_PATH" "$HELD_LOCK_TOKEN" >/dev/null 2>&1' EXIT
    if [ "$HELD_OP" = restore ]; then
      held_python restore "$C" "$SOURCE_PATH" "$SNAPSHOT" "$LOCAL_SERVICES"
    else
      held_python rollback "$C" "$SOURCE_PATH" "$SNAPSHOT"
    fi
    return $?
  fi
  TS=$(date +%Y%m%d-%H%M%S)
  # Logs and verification worktrees live beside the rollback snapshots, outside
  # every checkout, so the script behaves the same wherever it is run from.
  RBROOT="$HOME/MortimerRollback"; LOGD="$RBROOT/logs"
  LOG="$LOGD/deploy-main-$TS.log"; mkdir -p "$LOGD" || { echo "cannot create $LOGD"; exit 1; }
  exec > >(tee -a "$LOG") 2>&1
  die() { echo; echo "STOPPED: $*"; echo "full log: $LOG"; exit 1; }
  say() { echo; echo "=== $* ==="; }
  UIDN=$(id -u)
  SERVICES="vault bot extractor admin costs"

  say "0. target"
  git -C "$HERE" fetch -q origin || die "fetch failed"
  TARGET=$(git -C "$HERE" rev-parse origin/main); SHORT=${TARGET:0:7}
  git -C "$HERE" log -1 --format='origin/main: %h %ad %s' --date=format:'%m-%d %H:%M' "$TARGET"
  git -C "$HERE" merge-base --is-ancestor 88b206f "$TARGET" || die "origin/main does not contain #80 (88b206f)"
  [ -x "$PY" ] || die "production venv python missing: $PY"
  if [ "$HELD" = 1 ]; then
    HELD_LOCK_TOKEN=$(held_python lock "$C" "$SOURCE_PATH") || die "another held deployment owns the lease"
    trap 'held_python unlock "$C" "$SOURCE_PATH" "$HELD_LOCK_TOKEN" >/dev/null 2>&1' EXIT
    held_python preflight "$C" "$SOURCE_PATH" "$HERE" "$TARGET" "$APPROVAL" || die "held preflight refused"
  else
    held_python legacy "$C" "$SOURCE_PATH" || die "shutdown or disabled services require --install-held"
  fi
  # A zero-byte index.lock left by a crashed/sandboxed git blocks every checkout
  # (23 Sep: production had one dated 11 Sep). Remove it only when it is empty,
  # older than 10 minutes, and no git process is running; otherwise stop.
  LOCK="$C/.git/index.lock"
  if [ -e "$LOCK" ]; then
    if [ ! -s "$LOCK" ] && [ -n "$(find "$LOCK" -mmin +10 2>/dev/null)" ] && ! pgrep -x git >/dev/null; then
      echo "removing stale production lock: $(ls -l "$LOCK" | awk '{print $6,$7,$8}') (0 bytes, no git running)"
      rm -f "$LOCK" || die "could not remove $LOCK"
    else
      die "$LOCK exists and is not clearly stale (non-empty, recent, or git is running) -- check it by hand"
    fi
  fi
  echo "production before: $(git -C "$C" log -1 --format='%h' ) (+ $(git -C "$C" status --porcelain | wc -l | tr -d ' ') uncommitted entries)"
  # Production must hold no work that is not on main where the app build or the
  # services read. 24 Sep: Codex had 9 tracked edits and a half-applied
  # orb-crystal change in production. Phase C's `checkout -f` discarded the
  # tracked edits, the build then compiled the untracked CrystalGlassRig.swift
  # against the reverted JarvisConfig.swift and failed. Had it compiled, the
  # deploy would have shipped unreviewed Swift and dropped Codex's edits.
  # Untracked docs/, data/, logs/, tests/ and _to_delete/ are left alone.
  # P2-latency.json is the app's own latency report, rewritten on every run.
  DIRTY_TRACKED=$(git -C "$C" status --porcelain --untracked-files=no \
    | grep -v -x ' M docs/acceptance/adaptive-interface/P2-latency.json')
  UNTRACKED_CODE=$(git -C "$C" status --porcelain --untracked-files=all | sed -n 's/^?? //p' \
    | grep -E '^(macos/|jarvis/|mcp_servers/|services/|skills/|sandbox/|scripts/|config/|web/|requirements)')
  if [ -n "$DIRTY_TRACKED$UNTRACKED_CODE" ]; then
    echo "production holds work that is not on main:"
    { [ -n "$DIRTY_TRACKED" ] && echo "$DIRTY_TRACKED"; [ -n "$UNTRACKED_CODE" ] && sed 's/^/?? /' <<< "$UNTRACKED_CODE"; } | head -40 | sed 's/^/  /'
    die "move that work out of ~/jarvis-voice-ai-clean (commit it on a branch in its own worktree) before deploying -- nothing changed"
  fi

  # ---------------------------------------------------------------- A. verify
  # --reuse-verification: skip re-running the suites when an earlier run of THIS
  # script already passed all three on the SAME commit. The evidence is that
  # run's own log, named and quoted below, not a claim.
  if [ "$REUSE" = 1 ]; then
    PREV=$(grep -l "origin/main: $SHORT" "$LOGD"/deploy-main-*.log 2>/dev/null | while read f; do
             grep -qE "Executed [0-9]+ tests, with 0 failures" "$f" \
             && grep -qE "Executed [0-9]+ tests, with [0-9]+ tests skipped and 0 failures" "$f" \
             && grep -qE "^[0-9]+ passed, [0-9]+ skipped" "$f" && ! grep -qE "^[0-9]+ failed|STOPPED: .*(suite|pytest)" "$f" && echo "$f"; done | tail -1)
    [ -n "$PREV" ] || die "--reuse-verification: no earlier log shows all three suites passing on $SHORT"
    say "A. verification reused from $(basename "$PREV")"
    grep -E "^origin/main:|Executed [0-9]+ tests|^[0-9]+ passed" "$PREV" | sed 's/^[[:space:]]*/  /'
  else
  say "A. verify $SHORT in a throwaway worktree (no production change)"
  V="$(cd "$RBROOT" && pwd -P)/deploy-verify-$SHORT"      # absolute, no '..' (the first run compared the unnormalized path)
  if [ -e "$V" ]; then
    git -C "$HERE" worktree list --porcelain | grep -qx "worktree $V" || die "$V exists and is not a worktree of this repo -- move it aside"
    # Reuse it only if it is exactly the target and clean; its build is the one the
    # 23 Sep A/B and bisect runs passed on. Anything else is rebuilt from scratch.
    if [ "$(git -C "$V" rev-parse HEAD)" = "$TARGET" ] && [ -z "$(git -C "$V" status --porcelain)" ]; then
      echo "reusing verification worktree at $SHORT (clean)"
    else
      git -C "$HERE" worktree remove --force "$V" && echo "removed stale verification worktree"
    fi
  fi
  [ -d "$V" ] || git -C "$HERE" worktree add -q --detach "$V" "$TARGET" || die "worktree add failed"
  cd "$V"
  IMP=$(cd "$V" && "$PY" -c 'import jarvis,os;print(os.path.realpath(os.path.dirname(jarvis.__file__)))')
  case "$IMP" in "$V"/*) echo "python imports jarvis from the worktree: ok ($IMP)";; *) die "python imported jarvis from $IMP, not $V";; esac

  swift_gate() {  # $1 package dir, $2 label -- capture once, judge the suite's own final tally
    local out final status=0
    # Write diagnostics as they arrive: a stalled/killed XCTest must not keep
    # its only evidence in a command-substitution buffer. A prior passing
    # subsuite tally never authorizes a failed or interrupted Swift process.
    (cd "$V/$1" && swift test) > "$LOGD/deploy-$2-$TS.txt" 2>&1 || status=$?
    out=$(cat "$LOGD/deploy-$2-$TS.txt") || die "$2 log unavailable"
    [ "$status" -eq 0 ] || die "$2 suite failed (exit $status; see deploy-$2-$TS.txt)"
    # No `echo | grep -q` under pipefail: grep -q exits at its first match and the
    # writer can die of SIGPIPE, turning a match into a non-zero pipeline (23 Sep:
    # a 250-test pass was stopped twice). Here-strings and [[ =~ ]] have no writer.
    final=$(grep -E 'Executed [0-9]+ tests?,' <<< "$out" | tail -1); echo "$final"
    if grep -qE "$ERR_RE" <<< "$out" || [[ "$final" =~ (with|and)\ [1-9][0-9]*\ failures? ]]; then
      grep -E "^Test Case .* failed|$ERR_RE" <<< "$out" | head -15; die "$2 suite failed"
    fi
    [[ "$final" =~ with\ ([0-9]+\ tests?\ skipped\ and\ )?0\ failures ]] || die "$2 suite produced no passing tally: $final"
  }
  echo "JarvisKit:";    swift_gate macos/JarvisKit jarviskit
  echo "MortimerHost:"; swift_gate macos/MortimerHost mortimerhost
  # tests/conftest.py isolates the vault so tests never see real credentials; a
  # credential exported in this shell walks straight past that (23 Sep: an
  # exported JARVIS_GITHUB_TOKEN made check_env probe GitHub, and an exported
  # model key let the real council convene inside test_upgrade_agent). Run the
  # suite with a minimal allowlisted environment instead. Pipecat's runner
  # imports python-dotenv with override=True during test collection; without
  # PYTHON_DOTENV_DISABLED it can reload production .env from this venv's
  # parent directory and undo env -i before tests even begin.
  # Names only are shown.
  echo "credential-shaped variables in this shell (names only; NOT passed to pytest):"
  echo "  $(env | grep -oE '^[A-Za-z0-9_]*(API_KEY|TOKEN|SECRET|PASSWORD|_KEY)[A-Za-z0-9_]*=' | tr -d = | sort | tr '\n' ' ')"
  echo "JARVIS_* variables in this shell (names only; NOT passed): $(env | grep -oE '^JARVIS_[A-Z0-9_]*=' | tr -d = | sort | tr '\n' ' ')"
  CLEAN_ENV=(env -i HOME="$HOME" PATH="$PATH" USER="${USER:-larryfix}" LOGNAME="${LOGNAME:-${USER:-larryfix}}"
             SHELL="${SHELL:-/bin/zsh}" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" TERM="${TERM:-xterm-256color}"
             PYTHON_DOTENV_DISABLED=1)
  echo "Python (clean environment, no .env sourced):"
  OUT=$(cd "$V" && "${CLEAN_ENV[@]}" "$PY" -m pytest -q -p no:cacheprovider 2>&1); RC=$?
  echo "$OUT" > "$LOGD/deploy-pytest-$TS.txt"; echo "$OUT" | tail -1
  [ $RC -eq 0 ] || { echo "$OUT" | grep -E "^FAILED|^ERROR" | head -15; die "pytest failed (exit $RC)"; }
  cd "$HERE"; git -C "$HERE" worktree remove --force "$V" && echo "verification worktree removed"
  fi

  # -------------------------------------------------------------- B. snapshot
  RB="$HOME/MortimerRollback/release-$SHORT-$TS"
  say "B. rollback snapshot -> $RB"
  mkdir -p "$RB" && chmod 700 "$RB" || die "cannot create $RB"
  PRIOR=$(git -C "$C" rev-parse HEAD)
  git -C "$C" status --porcelain > "$RB/prior-status.txt"
  git -C "$C" diff > "$RB/prior-tracked-changes.patch"
  "$PY" - "$C/data" "$RB" "$HELD" <<'PYB' || die "database backup failed"
import sqlite3, sys, hashlib, json, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); held = sys.argv[3] == "1"
meta = {}
for name in ("jarvis.db", "costs.db"):
    s = src / name
    if not s.exists(): continue
    d = dst / name
    with sqlite3.connect(s) as a, sqlite3.connect(d) as b: a.backup(b)   # consistent online snapshot
    meta[name] = {"sha256": hashlib.sha256(d.read_bytes()).hexdigest(), "bytes": d.stat().st_size}
with sqlite3.connect(dst / "jarvis.db") as c:
    meta["conversations"] = c.execute("select count(*), max(id) from conversations").fetchone()
    meta["memories"] = c.execute("select count(*) from memories").fetchone()[0]
    meta["memories_columns"] = len(c.execute("pragma table_info(memories)").fetchall())
    meta["extraction_cursor"] = c.execute("select * from memory_extraction_cursor").fetchall()
(dst / "db-backup.json").write_text(json.dumps(meta, indent=1)); (dst / "db-backup.json").chmod(0o600)
print("consistent database snapshots saved" if held else json.dumps(meta))
PYB
  if [ "$HELD" = 1 ]; then
    tar -C "$C" --exclude './.env' --exclude './.env.*' --exclude '*/.env' --exclude '*/.env.*' \
      --exclude '*/.venv' --exclude '*/data' --exclude '*/logs' --exclude '*.db' --exclude '*.db-wal' \
      --exclude '*.db-shm' --exclude '*.sqlite' --exclude '*.sqlite3' --exclude ./.git --exclude ./.venv --exclude ./data --exclude ./logs \
      --exclude './macos/*/.build' --exclude '*/node_modules' --exclude '*/__pycache__' \
      -czf "$RB/code.tgz" .
  else
    tar -C "$C" --exclude ./.git --exclude ./.venv --exclude ./data --exclude ./logs \
      --exclude './macos/*/.build' --exclude '*/node_modules' --exclude '*/__pycache__' \
      -czf "$RB/code.tgz" .
  fi || die "code tarball failed"
  [ -d "$C/macos/MortimerHost/.build/MortimerHost.app" ] && ditto "$C/macos/MortimerHost/.build/MortimerHost.app" "$RB/MortimerHost.app"
  echo "code.tgz $(du -h "$RB/code.tgz" | cut -f1), prior HEAD ${PRIOR:0:7}, app bundle copied: $([ -d "$RB/MortimerHost.app" ] && echo yes || echo no)"
  if [ "$HELD" = 0 ]; then
  cat > "$RB/ROLLBACK.sh" <<RBEOF
#!/bin/bash
# Restore production to its state before the $SHORT deploy of $TS.
# Code + app only by default. The database is NOT restored unless you pass --restore-db,
# because that discards every conversation and memory written since the deploy.
set -uo pipefail
C="$C"; RB="$RB"
osascript -e 'tell application id "com.mortimer.host" to quit' 2>/dev/null; sleep 3; pkill -x MortimerHost 2>/dev/null
git -C "\$C" checkout -q -f --detach $PRIOR || { echo "checkout of prior HEAD failed"; exit 1; }
tar -C "\$C" -xzf "\$RB/code.tgz" || { echo "code restore failed"; exit 1; }
rm -rf "\$C/macos/MortimerHost/.build/MortimerHost.app"; ditto "\$RB/MortimerHost.app" "\$C/macos/MortimerHost/.build/MortimerHost.app"
if [ "\${1:-}" = "--restore-db" ]; then
  for s in $SERVICES; do launchctl bootout gui/$UIDN/com.mortimer.\$s 2>/dev/null; done
  cp "\$RB/jarvis.db" "\$C/data/jarvis.db"; rm -f "\$C/data/jarvis.db-wal" "\$C/data/jarvis.db-shm"
  for s in $SERVICES; do launchctl bootstrap gui/$UIDN ~/Library/LaunchAgents/com.mortimer.\$s.plist; done
else
  for s in $SERVICES; do launchctl kickstart -k gui/$UIDN/com.mortimer.\$s; done
fi
sleep 8; open "\$C/macos/MortimerHost/.build/MortimerHost.app"; echo "rolled back to ${PRIOR:0:7} + prior local changes"
RBEOF
  chmod +x "$RB/ROLLBACK.sh"; echo "rollback script: $RB/ROLLBACK.sh"
  fi

  if [ "$HELD" = 1 ]; then
    held_python snapshot "$C" "$SOURCE_PATH" "$RB" "$HERE" "$TARGET" "$APPROVAL" || die "held rollback snapshot refused"
    held_python hold "$C" "$SOURCE_PATH" || die "hold changed before installation"
    held_python floor "$C" "$SOURCE_PATH" "$RB" || die "held policy changed before installation"
    held_python stop-app "$C" "$SOURCE_PATH" || die "app still active; no installation"
  fi

  # --------------------------------------------------------------- C. install
  say "C. install $SHORT into production (services still on the old code in memory)"
  restore_code() {
    if [ "$HELD" = 1 ]; then
      held_python rollback "$C" "$SOURCE_PATH" "$RB" || die "held rollback failed; do not use legacy restart"
      return
    fi
    git -C "$C" checkout -q -f --detach "$PRIOR" && echo "git HEAD back on ${PRIOR:0:7}" || echo "WARNING: git checkout of ${PRIOR:0:7} failed -- files restored from the tarball only"
    tar -C "$C" -xzf "$RB/code.tgz" && echo "working files restored from $RB/code.tgz" || echo "WARNING: tarball restore reported errors -- see $RB"; }
  git -C "$C" fetch -q origin || die "production fetch failed"
  git -C "$C" checkout -q -f --detach "$TARGET" || { restore_code; die "production checkout failed"; }
  echo "production now: $(git -C "$C" log -1 --format='%h %s')"
  echo "left untracked (not on main, kept):"; git -C "$C" status --porcelain | sed 's/^/  /'
  echo "building app..."
  BUILD=$(cd "$C" && MORTIMER_BUNDLE_LAUNCH=0 MORTIMER_SOURCE_REVISION="$TARGET" bash macos/MortimerHost/scripts/bundle.sh debug 2>&1); BRC=$?
  echo "$BUILD" > "$LOGD/deploy-bundle-$TS.txt"; echo "$BUILD" | tail -3
  APPP="$C/macos/MortimerHost/.build/MortimerHost.app"
  REV=$(/usr/libexec/PlistBuddy -c 'Print :MortimerSourceRevision' "$APPP/Contents/Info.plist" 2>/dev/null)
  [ $BRC -eq 0 ] && [ "$REV" = "$TARGET" ] || {
    if [ "$HELD" = 1 ]; then restore_code; else restore_code; rm -rf "$APPP"; ditto "$RB/MortimerHost.app" "$APPP"; fi
    die "app build failed or bundle revision '$REV' != $TARGET -- production code and app restored; services were never restarted"; }
  echo "bundle revision: $REV"

  if [ "$HELD" = 1 ]; then
    held_python installed "$C" "$SOURCE_PATH" "$RB" || { held_python quarantine "$C" "$SOURCE_PATH" || die "held quarantine failed; no automatic rollback"; die "installed-held proof failed; services quarantined"; }
    say "DONE -- installed-held; no service or app activation. Use only the frozen held rollback."
    return 0
  fi

  # ---------------------------------------------------------------- D. switch
  say "D. switch over"
  osascript -e 'tell application id "com.mortimer.host" to quit' 2>/dev/null; sleep 4
  pkill -x MortimerHost 2>/dev/null && sleep 2
  pgrep -x MortimerHost >/dev/null && die "an app instance is still running -- quit it and re-run from phase D by hand (see log)"
  for s in $SERVICES; do launchctl kickstart -k gui/$UIDN/com.mortimer.$s && echo "restarted $s"; done
  hcode() { curl -s -o /dev/null -m 3 -w '%{http_code}' "$1"; }
  ok=0
  for i in $(seq 1 30); do
    a=$(cd "$C" && "$PY" scripts/service_health.py admin)
    v=$(hcode http://127.0.0.1:8484/health)
    b=$(cd "$C" && "$PY" scripts/service_health.py bot)
    if [ "$a" = 200 ] && [ "$v" = 200 ] && { [ "$b" = 307 ] || [ "$b" = 200 ]; }; then ok=1; break; fi; sleep 2
  done
  echo "health: admin=$a vault=$v bot=$b"
  [ $ok = 1 ] || { for s in bot admin vault; do echo "--- $s log tail"; tail -5 "$C/logs/$s.launchd.log"; done;
    die "services did not come healthy in 60 s. Code is deployed. To roll back code+app: $RB/ROLLBACK.sh"; }
  open "$APPP"; sleep 6

  "$PY" - "$C" "$RB" "$TARGET" "$LOGD" <<'PYD' || die "receipt failed"
import json, subprocess, sys, sqlite3, datetime, pathlib
C, RB, T, LOGS = sys.argv[1:5]; uid = subprocess.check_output(["id", "-u"], text=True).strip()
def pid(label):
    out = subprocess.run(["launchctl", "print", f"gui/{uid}/com.mortimer.{label}"], capture_output=True, text=True).stdout
    return next((int(l.split("=")[1]) for l in out.splitlines() if l.strip().startswith("pid =")), None)
def cwd(p):
    if not p: return None
    out = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", str(p), "-Fn"], capture_output=True, text=True).stdout
    return next((l[1:] for l in out.splitlines() if l.startswith("n")), None)
procs = {}
for s in ("vault", "bot", "extractor", "admin", "costs"):
    p = pid(s); procs[s] = {"pid": p, "working_directory": cwd(p)}
app = subprocess.run(["pgrep", "-x", "MortimerHost"], capture_output=True, text=True).stdout.split()
exe = subprocess.run(["ps", "-o", "command=", "-p", app[0]], capture_output=True, text=True).stdout.strip() if app else None
procs["app"] = {"pid": int(app[0]) if app else None, "executable": exe}
with sqlite3.connect(f"file:{C}/data/jarvis.db?mode=ro", uri=True) as c:
    db = {"path": f"{C}/data/jarvis.db", "conversations": c.execute("select count(*),max(id) from conversations").fetchone(),
          "memories": c.execute("select count(*) from memories").fetchone()[0],
          "memories_columns": len(c.execute("pragma table_info(memories)").fetchall()),
          "extraction_cursor": c.execute("select * from memory_extraction_cursor").fetchall()}
# scripts/run_kb.sh cds into services/mortimer-vault by design (line 18), so a
# service is "in production" when its cwd is the checkout or a folder inside it.
inside = lambda d: bool(d) and (d == C or d.startswith(C + "/"))
problems = [f"{s} cwd is {v['working_directory']}" for s, v in procs.items() if s != "app" and not inside(v["working_directory"])]
if not exe or not exe.startswith(f"{C}/macos/MortimerHost/.build/MortimerHost.app/"): problems.append(f"app executable is {exe}")
r = {"status": "deployed" if not problems else "deployed-with-problems", "problems": problems,
     "deployed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
     "main_revision": T, "production_head": subprocess.check_output(["git", "-C", C, "rev-parse", "HEAD"], text=True).strip(),
     "bundle_source_revision": subprocess.check_output(["/usr/libexec/PlistBuddy", "-c", "Print :MortimerSourceRevision",
                                f"{C}/macos/MortimerHost/.build/MortimerHost.app/Contents/Info.plist"], text=True).strip(),
     "processes": procs, "database": db, "rollback": {"directory": RB, "script": f"{RB}/ROLLBACK.sh",
     "db_backup": json.loads(pathlib.Path(RB, "db-backup.json").read_text())}}
out = json.dumps(r, indent=1); pathlib.Path(RB, "deployment-receipt.json").write_text(out)
pathlib.Path(LOGS, f"deployment-receipt-{T[:7]}.json").write_text(out); print(out)
sys.exit(1 if problems else 0)
PYD
  say "DONE -- $SHORT deployed. Receipt in $RB and $LOGD. Rollback: $RB/ROLLBACK.sh"
}

main "$@"; exit $?
