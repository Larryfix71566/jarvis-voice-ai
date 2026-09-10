"""Self-edit policy and API backed by persistent isolated VM sessions."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from jarvis.selfedit.allowlist import Allowlist, extract_paths
from sandbox.artifacts import SandboxError
from sandbox.workspace import SandboxWorkspace
SWIFT_PACKAGES: dict[str, tuple[str, ...]] = {'JarvisKit': ('JarvisKit', 'MortimerHost'), 'MortimerHost': ('MortimerHost',)}
DEFAULT_BASE_REF = 'origin/main'
BASE_REF_ENV = 'JARVIS_SELFEDIT_BASE_REF'
MAX_FILE_BYTES = 200000

def _repo_root() -> Path:
    return Path(os.environ.get('JARVIS_REPO_ROOT', Path(__file__).resolve().parents[2]))

def _slugify(text: str, max_len: int=32) -> str:
    slug = re.sub('[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug[:max_len].strip('-') or 'change'
VISUAL_PATH_PREFIXES = ('web/src/', 'web/public/', 'macos/MortimerHost/Sources/MortimerHost/')

def is_visual_path(path: str) -> bool:
    return str(path).replace('\\', '/').startswith(VISUAL_PATH_PREFIXES)
SWIFT_PATH_PREFIXES = ('macos/JarvisKit/Sources/', 'macos/MortimerHost/Sources/')

def is_swift_path(path: str) -> bool:
    return str(path).replace('\\', '/').startswith(SWIFT_PATH_PREFIXES)

def swift_packages_for(changed: list[str]) -> list[str]:
    """Ordered, de-duplicated packages to build for these changed paths —
    JarvisKit before MortimerHost, because MortimerHost consumes it.

    A path outside macos/, or under a macos/ directory that is not a
    package (macos/README.md), contributes nothing."""
    out: list[str] = []
    for p in changed:
        parts = str(p).replace('\\', '/').split('/')
        if len(parts) >= 2 and parts[0] == 'macos' and (parts[1] in SWIFT_PACKAGES):
            for pkg in SWIFT_PACKAGES[parts[1]]:
                if pkg not in out:
                    out.append(pkg)
    order = list(SWIFT_PACKAGES)
    return sorted(out, key=order.index)

def is_swift_only(changed: list[str]) -> bool:
    """True when EVERY changed path is under macos/ — the diff contains no
    Python for pytest to exercise. Named for the common case; a macos-only
    diff of docs qualifies too (and gets no Swift gate either, since
    swift_packages_for ignores non-package paths)."""
    return bool(changed) and all((str(p).replace('\\', '/').startswith('macos/') for p in changed))
CAPABILITY_PATHS = ('config/agents.yaml', 'config/mcp_servers.yaml')
CAPABILITY_PATH_PREFIXES = ('mcp_servers/',)

def is_capability_path(path: str) -> bool:
    p = str(path).replace('\\', '/')
    return p in CAPABILITY_PATHS or p.startswith(CAPABILITY_PATH_PREFIXES)

class SelfEditError(SandboxError):
    """A refused self-edit operation."""

class SelfEditService(SandboxWorkspace):
    """One persistent VM session per self-edit repository, shared across restarts."""

    def __init__(self, repo_root=None, allowlist_path=None, github_token=None, github_repo=None, base_ref=None, *, runtime_factory=None):
        self.repo_root = Path(repo_root) if repo_root else _repo_root()
        self.allowlist = Allowlist.load(allowlist_path or self.repo_root / 'config/self_edit_allowlist.json')
        self.base_ref = base_ref or os.environ.get(BASE_REF_ENV) or DEFAULT_BASE_REF
        self._github_token = github_token
        self._github_repo = github_repo or os.environ.get('JARVIS_GITHUB_REPO', 'Larryfix71566/jarvis-voice-ai')
        super().__init__(repository=lambda : self._github_repo, token=lambda : self._github_token or os.environ.get('JARVIS_GITHUB_TOKEN', ''), kind='selfedit', profile='mortimer', base_branch=lambda : self.pr_base, allowed=self._allowed_path, runtime_factory=runtime_factory)

    @property
    def pr_base(self):
        return self.base_ref[len('origin/'):] if self.base_ref.startswith('origin/') else self.base_ref

    def _allowed_path(self, path):
        return self.allowlist.is_allowed(path) and path != 'web' and (not path.startswith('web/'))

    def propose_edit(self, path, new_content, rationale, visual_intent=''):
        if not isinstance(new_content, str) or len(new_content.encode()) > MAX_FILE_BYTES:
            return {'ok': False, 'error': 'Edit exceeds the self-edit text limit.'}
        return super().propose_edit(path, new_content, rationale, visual_intent)

    def submit(self):
        paths = [proposal['path'] for proposal in self.proposals]
        result = super().submit()
        if not result.get('ok'):
            return result
        notices = []
        core = [path for path in paths if self.allowlist.is_core(path)]
        swift = [path for path in paths if is_swift_path(path)]
        capability = [path for path in paths if is_capability_path(path)]
        if swift:
            result.update(swift_change=True, swift_paths=swift)
            notices.append('SWIFT CHANGE: deployment must rebuild the native app.')
        if capability:
            result['capability_change'] = True
            notices.append('CAPABILITY CHANGE: review changes to standing agent tool permissions.')
        if core:
            result.update(core_change=True, core_paths=core)
            notices.append('CORE CHANGE: review the voice and agent behavior before merging.')
        notices.append('Review and merge on GitHub; deployment is a separate operation.')
        result['notice'] = ' '.join(notices)
        return result

    def _submission(self, state):
        (title, body) = super()._submission(state)
        paths = [p['path'] for p in state['proposals']]
        body += '\n\nSource revision: ' + state['ref']
        body += '\nCandidate: ' + state.get('candidate', '')
        body += '\n\nRequired VM checks:\n' + '\n'.join(('- ' + c['name'] + ': ' + ('passed' if c['ok'] else 'failed') for c in state.get('checks', [])))
        if any((self.allowlist.is_core(p) for p in paths)):
            body += '\n\nCORE CHANGE: review the voice and agent behavior exercised by this change.'
        if any((is_capability_path(p) for p in paths)):
            body += '\n\nCAPABILITY CHANGE: review changes to standing agent tool permissions.'
        if any((is_swift_path(p) for p in paths)):
            body += '\n\nSWIFT CHANGE: deployment must rebuild the native application.'
        if any((is_visual_path(p) for p in paths)):
            intents = [p.get('visual_intent', '') for p in state['proposals'] if is_visual_path(p['path'])]
            body += '\n\nVISUAL CHANGE: ' + ('; '.join(filter(None, intents)) or 'No appearance goal was recorded.')
        return (title, body)

    def verify_appearance(self, *, branch_override=False, display=1, view=None):
        return {'ok': False, 'error': 'Guest appearance verification requires this session’s sandbox preview.'}

    def describe_boundary(self):
        return json.dumps({'allow': self.allowlist.allow_patterns, 'core': self.allowlist.core_patterns, 'deny': self.allowlist.deny_patterns, 'frozen': ['web/**'], 'execution': 'disposable offline VM; independently verified draft pull requests'}, indent=2)

    def preflight(self, goal: str, has_plan: bool, target_paths: list[str] | None=None) -> dict:
        """Tier pre-flight for a goal BEFORE it is staged
        (MORTIMER_SELFEDIT_TIERS_PLAN.md). Classifies the repo paths the
        edit will TOUCH — `target_paths` when the caller supplies them,
        otherwise the paths the goal text names; refuses a Tier-0 (denied)
        path outright and a Tier-B (core) path with no plan. Best-effort on
        extraction — a goal that names no files passes through (the
        planner's own allowlist check still governs every write). The
        point is to fail at the preview, in one sentence, instead of after
        confirm + staging + a planner run that discovers the same wall
        (2026-08-30: three runs).

        `target_paths` (2026-09-07 review, F5): prose cannot tell "edit
        jarvis/model_catalog.py" from "add a line ABOUT
        jarvis/model_catalog.py" — four previews were refused that day as
        Tier B for a docs-only edit that merely mentioned a core file, and
        a goal that named no path at all ("the macOS host console view
        script") walked a Tier-0 target straight past this gate. When the
        developer states the files the edit will change, those are what
        is classified and the prose is not consulted."""
        targets = [t.strip() for t in target_paths or [] if t and t.strip()]
        paths = targets or extract_paths(goal)
        tiers = self.allowlist.classify(paths)
        result: dict = {'ok': True, 'paths': paths, 'tiers': tiers}
        if any((p == 'web' or p.startswith('web/') for p in paths)):
            result.update(ok=False, error='web/ is frozen (2026-09-04): interface work goes to macos/MortimerHost, which self-edit can change — name the Swift file in target_paths.')
            return result
        if tiers['denied']:
            result.update(ok=False, error="these files are human-only (Tier 0 — the self-edit loop's own machinery, secrets, dependencies or CI) and cannot be self-edited: " + ', '.join(tiers['denied']) + '. Ask Larry to make that change directly, or re-scope the goal to the other files.')
            return result
        if tiers['core'] and (not has_plan):
            result.update(ok=False, error='this goal touches the voice/agent core (Tier B: ' + ', '.join(tiers['core']) + '). Core edits need a plan document — draft one with plan_start (or point at an existing docs/plans/ file) and pass it as plan_path.')
        return result
