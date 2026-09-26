"""In-memory test doubles for the VM workspace seam; never a production fallback."""
import difflib
import uuid
from pathlib import Path
from sandbox.artifacts import SandboxError, source_path_allowed

class FakeRuntime:
    def __init__(self, root):
        root = Path(root)
        self.baseline = {}
        for p in root.rglob('*'):
            if p.is_file() and '.git' not in p.relative_to(root).parts and source_path_allowed(str(p.relative_to(root))):
                try: self.baseline[str(p.relative_to(root))] = p.read_text()
                except UnicodeError: pass
        self.current = None
        self.validation_ok = True
        self.pr_url = 'https://github.com/test/repo/pull/42'
        self.events = []

    def select_application(self, repository): self.selected_repository = repository
    def active(self, repository, kind, allowed): return self.current
    def publisher(self, token): return object()
    def start(self, repository, kind, base_branch, token, profile, allowed, goal, run_id=None):
        if self.current and self.current.state['phase'] not in {'published','reverted','cancelled','setup_failed'}:
            raise SandboxError('A session is already active')
        if not goal.strip(): raise SandboxError('Goal is empty')
        self.events.append(('start', repository, kind, base_branch, profile))
        self.current = FakeSession(self, allowed, goal, run_id)
        return self.current

class FakeSession:
    def __init__(self, runtime, allowed, goal, run_id):
        self.runtime, self.allowed = runtime, allowed
        self.id = uuid.uuid4().hex
        self.files = dict(runtime.baseline)
        self.state = {'id':self.id, 'task':self.id[:12], 'phase':'editing', 'goal':goal, 'run_id':run_id,
            'ready':True, 'vm_status':'running', 'ref':'a'*40, 'branch':'mortimer/selfedit/'+self.id, 'proposals':[], 'checks':[]}

    def resume(self):
        if self.state['phase'] in {'published', 'reverted', 'cancelled', 'setup_failed'}:
            raise SandboxError('This session has ended')
        self.state.update(ready=True, vm_status='running')
        return {'ok': True, 'ready': True}
    def status(self): return dict(self.state)
    def _path(self, path):
        if not source_path_allowed(path) or not self.allowed(path): raise SandboxError('Path is outside the workspace policy')
        if self.state['phase'] in {'reverted','cancelled'}: raise SandboxError('Session is not available')
    def read_file(self, path):
        self._path(path)
        if path not in self.files: raise SandboxError('No such file')
        return {'ok':True,'path':path,'content':self.files[path]}
    def baseline_text(self, path):
        # Mirrors sandbox.session.Session.baseline_text: the base snapshot,
        # no workspace policy, secrets and runtime data refused.
        if not source_path_allowed(path): raise SandboxError('Path is outside the source snapshot')
        if self.state['phase'] in {'reverted','cancelled'}: raise SandboxError('This session has ended')
        if path not in self.runtime.baseline: return {'ok':True,'path':path,'exists':False,'content':''}
        return {'ok':True,'path':path,'exists':True,'content':self.runtime.baseline[path],'mode':0o644}
    def propose_edit(self, path, content, rationale, visual_intent=''):
        self._path(path)
        old=self.runtime.baseline.get(path,'')
        diff=''.join(difflib.unified_diff(old.splitlines(keepends=True),content.splitlines(keepends=True),fromfile='a/'+path,tofile='b/'+path))
        self.files[path]=content
        self.state['proposals']=[p for p in self.state['proposals'] if p['path']!=path]+[{'path':path,'diff':diff,'rationale':rationale,'visual_intent':visual_intent}]
        self.state.update(phase='editing',checks=[])
        return {'ok':True,'path':path,'diff':diff}
    def validate(self):
        passed=self.runtime.validation_ok
        checks=[{'name':'independent-vm','ok':passed,'seconds':1}]
        self.state.update(phase='validated' if passed else 'validation_failed',checks=checks,candidate='b'*64)
        return {'ok':passed,'checks':checks}
    def submit(self, publisher, title, body):
        if self.state['phase']!='validated': raise SandboxError('Validation has not passed since the last edit')
        self.runtime.events.append(('submit',title,body))
        self.state['phase']='published'
        return {'ok':True,'number':42,'url':self.runtime.pr_url}
    def revert(self):
        self.state['phase']='reverted'
        return {'ok':True}
    def cancel(self):
        self.state['phase']='cancelled'
        return {'ok':True,'cancelled':True}
