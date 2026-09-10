"""Application-facing workspace operations backed exclusively by VM sessions."""
from __future__ import annotations
import logging
from sandbox.artifacts import SandboxError
from sandbox.runtime import Runtime

log = logging.getLogger(__name__)
TERMINAL = {'published', 'reverted', 'cancelled', 'setup_failed'}

class SandboxWorkspace:
    def __init__(self, *, repository, token, kind, profile, base_branch, allowed, runtime_factory=None):
        self._repository, self._token = repository, token
        self._kind, self._profile = kind, profile
        self._base_branch, self._allowed = base_branch, allowed
        self._runtime_factory = runtime_factory or Runtime.configured
        self._installed_runtime = None

    def _runtime(self):
        if self._installed_runtime is None:
            self._installed_runtime = self._runtime_factory()
        return self._installed_runtime

    def _session(self):
        session = self._runtime().active(self._repository(), self._kind, self._allowed)
        if session is None:
            raise SandboxError('No sandbox session is active; start a development session first.')
        return session

    @staticmethod
    def _error(exc):
        if isinstance(exc, SandboxError): return {'ok': False, 'error': str(exc)}
        log.warning('sandbox_workspace_failure type=%s', type(exc).__name__)
        return {'ok': False, 'error': 'The sandbox operation failed. Its saved session can be inspected and retried.'}

    def _invoke(self, name, *args, **kwargs):
        try: return getattr(self._session(), name)(*args, **kwargs)
        except (SandboxError, OSError, ValueError, KeyError) as exc: return self._error(exc)

    def start_session(self, goal: str, run_id: str | None = None) -> dict:
        try:
            session = self._runtime().start(self._repository(), self._kind, self._base_branch(), self._token(),
                self._profile, self._allowed, goal, run_id)
            state = session.status()
            return {'ok': True, 'branch': state['branch'], 'sandbox_task': state['task'],
                    'session_id': session.id, 'source_commit': state['ref'], 'worktree': None}
        except (SandboxError, OSError, ValueError, KeyError) as exc: return self._error(exc)

    def resume(self, expected_session_id=None) -> dict:
        try:
            session = self._session()
            if expected_session_id is not None and session.id != expected_session_id:
                raise SandboxError('The workspace session changed; inspect its status before retrying.')
            return session.resume()
        except (SandboxError, OSError, ValueError, KeyError) as exc:
            return self._error(exc)

    def read_file(self, path: str) -> dict: return self._invoke('read_file', path)
    def propose_edit(self, path: str, new_content: str, rationale: str, visual_intent: str = '') -> dict:
        return self._invoke('propose_edit', path, new_content, rationale, visual_intent)
    def validate(self) -> dict: return self._invoke('validate')
    def revert(self) -> dict: return self._invoke('revert')
    def cancel(self) -> dict: return self._invoke('cancel')

    def _submission(self, state):
        title = ('self-edit: ' if self._kind == 'selfedit' else 'app-build: ') + state['goal'].splitlines()[0]
        body = 'Goal: ' + state['goal'] + '\n\n'
        body += '\n'.join('- ' + p['path'] + ': ' + p['rationale'] for p in state['proposals'])
        body += '\n\nThe frozen candidate passed the required checks in an independent offline VM. '
        body += 'This draft is for review; merging and deployment require their own decisions.'
        return title[:120], body

    def submit(self) -> dict:
        try:
            session = self._session()
            title, body = self._submission(session.status())
            result = session.submit(self._runtime().publisher(self._token()), title, body)
            return {**result, 'pr_url': result.get('url'), 'pr_number': result.get('number')}
        except (SandboxError, OSError, ValueError, KeyError) as exc: return self._error(exc)

    def status(self) -> dict:
        try:
            session = self._runtime().active(self._repository(), self._kind, self._allowed)
            if session is None:
                return {'active': False, 'branch': None, 'proposals': [], 'validated_ok': False, 'worktree': None}
            state = session.status()
            active = state['phase'] not in TERMINAL
            checked = bool(state.get('checks')) and all(check.get('ok') is True for check in state['checks'])
            return {**state, 'active': active, 'branch': state['branch'] if active else None,
                'session_branch': state['branch'], 'worktree': None, 'rollback_tag': None,
                'validated_ok': checked and state['phase'] in {'validated', 'publishing', 'publication_pending'}}
        except (SandboxError, OSError, ValueError, KeyError) as exc:
            return {'active': False, 'branch': None, 'proposals': [], 'validated_ok': False, 'worktree': None,
                    'error': self._error(exc)['error']}

    @property
    def branch(self): return self.status().get('branch')
    @property
    def proposals(self): return self.status().get('proposals', [])
    @property
    def goal(self): return self.status().get('goal')
    @property
    def run_id(self): return self.status().get('run_id')
    @property
    def _last_checks(self): return self.status().get('checks', [])
    @property
    def _validated_ok(self): return self.status().get('validated_ok', False)
    @property
    def work_root(self): return None
    @property
    def rollback_tag(self): return None
    def describe_boundary(self) -> str:
        return 'Development files and commands run in a disposable offline VM. Publication uses a separately verified candidate.'
