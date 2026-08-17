"""Workspace seam (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part D,
D1-D4): the small interface jarvis.agents.upgrade_agent.UpgradeAgent's
edit loop is bound to, so the SAME loop (goal -> read/propose/validate/
submit, one repair attempt, council escalation on repeated failure) can
drive either a self-edit session against Mortimer's own repo or an
app-build session against a foreign app repo, without forking the loop.

Two implementations:
- SelfEditWorkspace: jarvis.selfedit.service.SelfEditService, unchanged —
  a subclass with NO overrides, so isinstance checks and type hints can
  say "this is a Workspace" without touching the class every existing
  caller already imports as SelfEditService. UpgradeAgent +
  SelfEditWorkspace must be behavior-identical to UpgradeAgent +
  SelfEditService before this file existed — that is the whole point of
  landing D1 alone before AppBuildAgent exists.
- AppWorkspace (D2-D4): a foreign app repo, cloned via git subprocess
  under data/app_workspaces/<app-name>/ (credentials/repo lookup reused
  from mcp_servers.mcp_apps.github.GitHubClient — the one module that
  already knows how to authenticate to GitHub — but the actual clone/
  pull/commit/push is done with git subprocess, same discipline as
  jarvis.selfedit.service.SelfEditService._git: argument list, never
  shell, fixed timeout, cwd pinned to the workspace root). Validated by
  the app's own mortimer.app.yaml manifest (D3) instead of Mortimer's own
  CI gates. Write boundary (D4) is a plain deny-list, not an allowlist —
  everything in the workspace tree is writable except .git/**, .env(.*),
  **/*.vault, and .github/workflows/** (an app-build agent must not grant
  itself CI powers on the app repo either).
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jarvis.selfedit.service import SelfEditService
from mcp_servers.mcp_apps.github import GitHubClient
from mcp_servers.mcp_apps.logic import validate_app_name, validate_repo_path

APP_WORKSPACES_DIR = Path(__file__).resolve().parents[2] / "data" / "app_workspaces"
APP_MANIFEST_NAME = "mortimer.app.yaml"
APP_CHECK_TIMEOUT_S = 600.0
APP_GIT_TIMEOUT_S = 120
MAX_FILE_BYTES = 200_000

# D4 — deny-listed inside the workspace tree regardless of the app's own
# manifest or file layout. Prefix match on the repo-relative path.
APP_DENY_PREFIXES = (".git/", ".github/workflows/")
APP_DENY_EXACT = (".git",)


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

    def start_session(self, goal: str) -> dict: ...
    def read_file(self, path: str) -> dict: ...
    def propose_edit(self, path: str, new_content: str, rationale: str) -> dict: ...
    def validate(self) -> dict: ...
    def submit(self) -> dict: ...
    def revert(self) -> dict: ...
    def status(self) -> dict: ...
    def describe_boundary(self) -> str: ...


class SelfEditWorkspace(SelfEditService):
    """D1: SelfEditService under the Workspace name. Zero behavior added —
    every method is inherited unchanged."""


class WorkspaceError(Exception):
    """Raised for refused AppWorkspace operations; converted to dicts at
    the public method boundary, same pattern as selfedit.service.SelfEditError."""


def _slugify(text: str, max_len: int = 32) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].strip("-") or "change")


def _check_app_path(path: str) -> str:
    """D4 write boundary: validate_repo_path (mcp_apps.logic — already
    rejects absolute paths, '.'/'..' segments, and any '.git' component)
    plus the two additional deny prefixes this workspace adds on top."""
    rel = validate_repo_path(path)
    if rel in APP_DENY_EXACT or any(rel.startswith(p) for p in APP_DENY_PREFIXES):
        raise WorkspaceError(
            f"path is outside the app-build write boundary: {rel!r} "
            "(.git, .env*, *.vault, and .github/workflows are always denied)"
        )
    name = rel.rsplit("/", 1)[-1]
    if name == ".env" or name.startswith(".env."):
        raise WorkspaceError(f"path is outside the app-build write boundary: {rel!r}")
    if name.endswith(".vault"):
        raise WorkspaceError(f"path is outside the app-build write boundary: {rel!r}")
    return rel


class AppWorkspace:
    """One active app-build session at a time per instance (same
    convention as SelfEditService). D2: clone-on-first-build,
    pull-on-subsequent-build. D3: validate() reads mortimer.app.yaml from
    the workspace root. D4: write boundary is a deny-list, not an
    allowlist — see _check_app_path."""

    def __init__(
        self,
        app_name: str,
        github_client: GitHubClient | None = None,
        base_ref: str = "main",
        workspaces_dir: str | Path | None = None,
        remote_url: str | None = None,
    ):
        self.app_name = validate_app_name(app_name)
        self._client = github_client or GitHubClient()
        self.base_ref = base_ref
        self.repo_root = Path(workspaces_dir or APP_WORKSPACES_DIR) / self.app_name
        # Test seam: a real session always derives the remote from
        # GitHubClient (see _remote_url below); tests inject a local bare
        # repo path here instead of hitting real GitHub.
        self._remote_url_override = remote_url

        self.branch: str | None = None
        self.goal: str | None = None
        self.proposals: list[dict] = []
        self._validated_ok = False

    # ------------------------------------------------------------- git

    def _git(self, *args: str, timeout: int = APP_GIT_TIMEOUT_S) -> tuple[int, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def _git_ok(self, *args: str, timeout: int = APP_GIT_TIMEOUT_S) -> str:
        code, out = self._git(*args, timeout=timeout)
        if code != 0:
            raise WorkspaceError(f"git {' '.join(args[:2])} failed: {out}")
        return out

    def _run(self, argv: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
            return proc.returncode, (proc.stdout + proc.stderr).strip()[-4000:]
        except FileNotFoundError as exc:
            return 127, str(exc)
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout}s"

    def _remote_url(self) -> str:
        if self._remote_url_override is not None:
            return self._remote_url_override
        owner = self._client._owner()
        return f"https://{self._client.token}@github.com/{owner}/{self.app_name}.git"

    # ---------------------------------------------------------- session

    def start_session(self, goal: str) -> dict:
        if not goal or not goal.strip():
            return {"ok": False, "error": "goal is empty"}
        if self.branch is not None:
            return {
                "ok": False,
                "error": f"an app-build session is already active on {self.branch} — "
                         "submit or revert it first",
            }
        try:
            remote_url = self._remote_url()
            if not self.repo_root.exists():
                self.repo_root.parent.mkdir(parents=True, exist_ok=True)
                code, out = self._run(
                    ["git", "clone", remote_url, str(self.repo_root)],
                    cwd=self.repo_root.parent, timeout=APP_GIT_TIMEOUT_S,
                )
                if code != 0:
                    raise WorkspaceError(f"git clone failed: {_redact(out, self._client.token)}")
                # A fresh clone's checked-out branch follows the remote's
                # HEAD symref, which may not be base_ref (e.g. a bare repo
                # created with "master" as its default before base_ref was
                # ever pushed) — explicitly land on base_ref rather than
                # trusting whatever clone happened to check out.
                self._git_ok("checkout", "-B", self.base_ref, f"origin/{self.base_ref}")
            else:
                _c, porcelain = self._git("status", "--porcelain")
                if porcelain.strip():
                    raise WorkspaceError(
                        "app workspace is not clean — a previous session was not "
                        "submitted or reverted cleanly; resolve manually before "
                        "starting a new build"
                    )
                self._git_ok("checkout", self.base_ref)
                code, out = self._git("pull", "--ff-only", "origin", self.base_ref)
                if code != 0:
                    raise WorkspaceError(f"git pull --ff-only failed: {_redact(out, self._client.token)}")
            branch = f"mortimer/app-build/{time.strftime('%Y%m%d')}-{_slugify(goal)}"
            self._git_ok("checkout", "-b", branch)
        except WorkspaceError as exc:
            return {"ok": False, "error": str(exc)}
        self.branch = branch
        self.goal = goal.strip()
        self.proposals = []
        self._validated_ok = False
        return {"ok": True, "branch": branch, "app": self.app_name}

    # ------------------------------------------------------------ edits

    def read_file(self, path: str) -> dict:
        try:
            rel = _check_app_path(path)
        except (WorkspaceError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        full = self.repo_root / rel
        if not full.is_file():
            return {"ok": False, "error": f"no such file: {rel}"}
        if full.stat().st_size > MAX_FILE_BYTES:
            return {"ok": False, "error": f"file too large to read: {rel}"}
        return {"ok": True, "path": rel, "content": full.read_text(encoding="utf-8")}

    def propose_edit(self, path: str, new_content: str, rationale: str) -> dict:
        if self.branch is None:
            return {"ok": False, "error": "no active session — call start_session first"}
        try:
            rel = _check_app_path(path)
        except (WorkspaceError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        if len(new_content.encode("utf-8")) > MAX_FILE_BYTES:
            return {"ok": False, "error": f"edit too large for {rel}"}
        full = self.repo_root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(new_content, encoding="utf-8")
        self._validated_ok = False
        _c, diff = self._git("diff", "--", rel)
        proposal = {"path": rel, "rationale": rationale, "diff": diff}
        self.proposals = [p for p in self.proposals if p["path"] != rel]
        self.proposals.append(proposal)
        return {"ok": True, "path": rel, "diff": diff}

    # ------------------------------------------------------- validation

    def validate(self) -> dict:
        """D3: run the app's own mortimer.app.yaml `build:`/`test:`
        command lists, in order, all must exit 0. No manifest = "no
        checks defined" reported explicitly (an unvalidated PR must never
        be mistaken for a validated one) rather than silently passing."""
        if self.branch is None:
            return {"ok": False, "error": "no active session"}
        checks: list[dict] = []
        manifest_path = self.repo_root / APP_MANIFEST_NAME
        if not manifest_path.is_file():
            checks.append({
                "name": "manifest",
                "ok": True,
                "output": f"no {APP_MANIFEST_NAME} found — NO CHECKS ARE DEFINED for "
                          "this app; this PR is unvalidated.",
            })
        else:
            import yaml

            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            except Exception as exc:  # noqa: BLE001 — a bad manifest is a check failure
                checks.append({"name": "manifest", "ok": False,
                               "output": f"could not parse {APP_MANIFEST_NAME}: {exc}"})
                manifest = {}
            else:
                checks.append({"name": "manifest", "ok": True, "output": "manifest ok"})
            for section in ("build", "test"):
                commands = manifest.get(section) or []
                for cmd in commands:
                    argv = cmd if isinstance(cmd, list) else str(cmd).split()
                    code, out = self._run(argv, cwd=self.repo_root, timeout=APP_CHECK_TIMEOUT_S)
                    checks.append({
                        "name": f"{section}:{' '.join(str(a) for a in argv)}",
                        "ok": code == 0,
                        "output": out or "ok",
                    })
        ok = all(c["ok"] for c in checks)
        self._validated_ok = ok
        return {"ok": ok, "checks": checks}

    # ---------------------------------------------------------- submit

    def submit(self) -> dict:
        if self.branch is None:
            return {"ok": False, "error": "no active session"}
        if not self.proposals:
            return {"ok": False, "error": "no proposed edits in this session"}
        if not self._validated_ok:
            return {
                "ok": False,
                "error": "validation has not passed since the last edit — "
                         "run validate() and fix any failures first",
            }
        try:
            paths = [p["path"] for p in self.proposals]
            self._git_ok("add", "--", *paths)
            msg = f"app-build: {_slugify(self.goal or 'change', 48)}"
            self._git_ok(
                "commit", "-m",
                msg + "\n\n" + (self.goal or "") + "\n\n"
                "Review and merge on GitHub — this PR was opened by the Mortimer "
                "app-build loop. Merge is manual-only; Mortimer cannot merge it.",
            )
            self._git_ok("push", "-u", "origin", self.branch)
            pr = self._open_pr(msg)
        except WorkspaceError as exc:
            return {"ok": False, "error": str(exc)}
        result = {"ok": True, "branch": self.branch, "pr_url": pr.get("html_url")}
        branch = self.branch
        self._git("checkout", self.base_ref)
        self._git("branch", "-D", branch)
        self.branch = None
        self.proposals = []
        self._validated_ok = False
        return result

    def _open_pr(self, title: str) -> dict:
        import json
        import urllib.request

        owner = self._client._owner()
        body_lines = [f"**Goal:** {self.goal}", "", "**Proposed edits:**"]
        for p in self.proposals:
            body_lines.append(f"- `{p['path']}` — {p['rationale']}")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{self.app_name}/pulls",
            data=json.dumps({
                "title": title, "head": self.branch, "base": self.base_ref,
                "body": "\n".join(body_lines),
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._client.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise WorkspaceError(f"failed to open pull request: {exc}") from exc

    # ---------------------------------------------------------- revert

    def revert(self) -> dict:
        if self.branch is None:
            return {"ok": False, "error": "no active session"}
        branch = self.branch
        self._git("checkout", self.base_ref)
        self._git("clean", "-fd")
        self._git("reset", "--hard", f"origin/{self.base_ref}")
        self._git("branch", "-D", branch)
        self.branch = None
        self.goal = None
        self.proposals = []
        self._validated_ok = False
        return {"ok": True}

    def status(self) -> dict:
        return {
            "active": self.branch is not None,
            "app": self.app_name,
            "branch": self.branch,
            "goal": self.goal,
            "proposals": [
                {"path": p["path"], "rationale": p["rationale"], "diff": p["diff"]}
                for p in self.proposals
            ],
            "validated_ok": self._validated_ok,
        }

    def describe_boundary(self) -> str:
        return (
            f"App-build write boundary for {self.app_name!r}: everything in the "
            "app's own repo is writable EXCEPT .git/**, .env and .env.*, any "
            "*.vault file, and .github/workflows/** (an app-build session must "
            "not grant itself CI powers on the app repo)."
        )


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text
