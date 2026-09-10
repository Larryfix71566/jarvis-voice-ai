"""Self-edit and application workspaces share persistent isolated VM sessions."""
from __future__ import annotations
from pathlib import Path
from typing import Protocol, runtime_checkable
from jarvis.selfedit.service import SelfEditService
from mcp_servers.mcp_apps.github import GitHubClient, GitHubError
from mcp_servers.mcp_apps.logic import validate_app_name, validate_repo_path
from sandbox.artifacts import SandboxError
from sandbox.workspace import SandboxWorkspace
APP_WORKSPACES_DIR = Path(__file__).resolve().parents[2] / 'data/app_workspaces'
APP_MANIFEST_NAME = 'mortimer.app.yaml'
APP_DENY_PREFIXES = ('.git/', '.github/workflows/')
APP_DENY_EXACT = ('.git',)

@runtime_checkable
class Workspace(Protocol):
    """Duck-typed interface UpgradeAgent.run()'s edit loop calls through.
    Every method returns a plain dict with at least an "ok" key; refusals
    are data ({"ok": False, "error": ...}), never an exception — same
    convention SelfEditService already uses. Not enforced at runtime
    (@runtime_checkable only checks method/attribute PRESENCE, not
    signatures) — this exists for readability and type-checking, not as
    a gate."""
    branch: str | None
    repo_root: Path
    proposals: list[dict]

    def start_session(self, goal: str, run_id: str | None=None) -> dict:
        ...

    def read_file(self, path: str) -> dict:
        ...

    def propose_edit(self, path: str, new_content: str, rationale: str) -> dict:
        ...

    def validate(self) -> dict:
        ...

    def submit(self) -> dict:
        ...

    def revert(self) -> dict:
        ...

    def status(self) -> dict:
        ...

    def describe_boundary(self) -> str:
        ...

class SelfEditWorkspace(SelfEditService):
    """D1: SelfEditService under the Workspace name. Zero behavior added —
    every method is inherited unchanged."""

class WorkspaceError(Exception):
    """Raised for refused AppWorkspace operations; converted to dicts at
    the public method boundary, same pattern as selfedit.service.SelfEditError."""

def _check_app_path(path: str) -> str:
    """D4 write boundary: validate_repo_path (mcp_apps.logic — already
    rejects absolute paths, '.'/'..' segments, and any '.git' component)
    plus the two additional deny prefixes this workspace adds on top."""
    rel = validate_repo_path(path)
    if rel in APP_DENY_EXACT or any((rel.startswith(p) for p in APP_DENY_PREFIXES)):
        raise WorkspaceError(f'path is outside the app-build write boundary: {rel!r} (.git, .env*, *.vault, and .github/workflows are always denied)')
    name = rel.rsplit('/', 1)[-1]
    if name == '.env' or name.startswith('.env.'):
        raise WorkspaceError(f'path is outside the app-build write boundary: {rel!r}')
    if name.endswith('.vault'):
        raise WorkspaceError(f'path is outside the app-build write boundary: {rel!r}')
    return rel

class AppWorkspace(SandboxWorkspace):
    """A foreign application repository developed exclusively inside a VM."""

    def __init__(self, app_name, github_client=None, base_ref='main', workspaces_dir=None, remote_url=None, *, runtime_factory=None, sandbox_profile='web-app'):
        if remote_url is not None:
            raise WorkspaceError('Host checkout URLs are no longer supported; inject a sandbox runtime for tests.')
        self.app_name = validate_app_name(app_name)
        self._client = github_client
        self._app_repo_name = None
        self.base_ref = base_ref
        self.repo_root = Path(workspaces_dir or APP_WORKSPACES_DIR) / self.app_name
        super().__init__(repository=self._repository_name, token=lambda : self._get_client().token, kind='app-build', profile=sandbox_profile, base_branch=lambda : self.base_ref, allowed=self._allowed_path, runtime_factory=runtime_factory)

    def _get_client(self):
        if self._client is None:
            try:
                self._client = GitHubClient()
            except GitHubError as exc:
                raise SandboxError(str(exc)) from None
        return self._client

    def _repository_name(self):
        if self._app_repo_name is None:
            try:
                self._app_repo_name = self._get_client()._owner() + '/' + self.app_name
            except GitHubError as exc:
                raise SandboxError(str(exc)) from None
        return self._app_repo_name

    @staticmethod
    def _allowed_path(path):
        try:
            return _check_app_path(path) == path
        except (WorkspaceError, ValueError):
            return False

    def status(self):
        return {**super().status(), 'app': self.app_name}

    def describe_boundary(self):
        return 'App development runs in a disposable offline VM. The installed host profile chooses required checks. Private files, Git metadata and GitHub workflow changes are excluded; reviewed candidates become draft pull requests.'
