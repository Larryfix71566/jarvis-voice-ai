"""GitHub API client for mcp-apps — ALL network access lives here.

logic.py never imports this module; server.py builds one client and passes
it in. Reads/writes go through the REST contents API (no shell, no git
binary, no clone). There is deliberately no delete method: agents never
delete repositories or files.

Auth: GITHUB_TOKEN (repo-capable PAT). Owner: GITHUB_OWNER (used only for
repo lookups; repo creation uses the authenticated user).
"""

from __future__ import annotations

import base64
import os

import httpx

API_BASE = "https://api.github.com"
TIMEOUT = 30.0


class GitHubError(RuntimeError):
    """API call failed; message is safe to show the user (no token)."""


class GitHubClient:
    def __init__(self, token: str | None = None, owner: str | None = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.owner = owner if owner is not None else os.environ.get("GITHUB_OWNER", "")
        if not self.token:
            raise GitHubError("no GITHUB_TOKEN configured")

    # ------------------------------------------------------------ helpers

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            resp = httpx.request(
                method, url, headers=self._headers(), timeout=TIMEOUT, **kwargs
            )
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub request failed: {type(exc).__name__}") from exc
        return resp

    @staticmethod
    def _raise_for_status(resp: httpx.Response, what: str) -> None:
        if resp.status_code >= 400:
            # MORTIMER_AGENT_TRUST_PLAN.md D8: 401/403 get a specific,
            # correctly-attributed message. This is the ONE string a
            # sub-agent is permitted to repeat verbatim (plan D7 — no
            # invented remediation) — a prior incident had the agent report
            # a GitHub 401 as "admin sidecar may be offline", which sent
            # the user to debug an unrelated, healthy component. The
            # explicit "unrelated to the admin sidecar" clause exists
            # because that is the exact wrong conclusion already reached
            # twice in the logged history (see the plan's Appendix A.5).
            if resp.status_code in (401, 403):
                raise GitHubError(
                    f"GitHub authentication failed (HTTP {resp.status_code}). "
                    "The GITHUB_TOKEN in .env is missing, expired, or "
                    "revoked. This is unrelated to the admin sidecar."
                )
            detail = ""
            try:
                detail = resp.json().get("message", "")
            except Exception:  # noqa: BLE001 — best-effort detail only
                pass
            raise GitHubError(f"{what} failed (HTTP {resp.status_code}): {detail}")

    # --------------------------------------------------------------- repos

    def authenticated_user(self) -> str:
        resp = self._request("GET", f"{API_BASE}/user")
        self._raise_for_status(resp, "lookup of authenticated user")
        return resp.json()["login"]

    def repo_exists(self, name: str) -> bool:
        owner = self._owner()
        resp = self._request("GET", f"{API_BASE}/repos/{owner}/{name}")
        if resp.status_code == 404:
            return False
        self._raise_for_status(resp, f"check for repo {name}")
        return True

    def create_repo(self, name: str, description: str = "", private: bool = True) -> dict:
        resp = self._request(
            "POST", f"{API_BASE}/user/repos",
            json={"name": name, "description": description, "private": private},
        )
        self._raise_for_status(resp, f"creation of repo {name}")
        return resp.json()

    # --------------------------------------------------------------- files

    def _owner(self) -> str:
        return self.owner or self.authenticated_user()

    def get_file(self, repo: str, path: str, branch: str) -> dict | None:
        """Return {'content': str, 'sha': str} or None if the file is absent."""
        resp = self._request(
            "GET",
            f"{API_BASE}/repos/{self._owner()}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp, f"read of {path} in {repo}")
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return {"content": content, "sha": data["sha"]}

    def put_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict:
        body: dict = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha is not None:
            body["sha"] = sha
        resp = self._request(
            "PUT",
            f"{API_BASE}/repos/{self._owner()}/{repo}/contents/{path}",
            json=body,
        )
        self._raise_for_status(resp, f"write of {path} in {repo}")
        return resp.json()

    # --------------------------------------------- reads (status spec T4.3)
    # Read-only: both methods issue GET only. Used by jarvis/status/github.py
    # (the admin sidecar's /api/status/github), never by mcp-apps' tools.

    def list_pulls(self, repo: str, state: str = "open", limit: int = 10) -> list[dict]:
        """Pull requests in `repo`, newest activity first as GitHub orders them."""
        limit = max(1, min(int(limit), 100))
        resp = self._request(
            "GET", f"{API_BASE}/repos/{self._owner()}/{repo}/pulls",
            params={"state": state, "per_page": limit},
        )
        self._raise_for_status(resp, f"list of pull requests in {repo}")
        out = []
        for pr in resp.json()[:limit]:
            out.append({
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "draft": bool(pr.get("draft")),
                "head": (pr.get("head") or {}).get("ref"),
                "base": (pr.get("base") or {}).get("ref"),
                "updated_at": pr.get("updated_at"),
                "html_url": pr.get("html_url"),
            })
        return out

    def pull_checks(self, repo: str, number: int) -> dict:
        """Check runs on pull request `number`'s head commit."""
        owner = self._owner()
        resp = self._request("GET", f"{API_BASE}/repos/{owner}/{repo}/pulls/{int(number)}")
        self._raise_for_status(resp, f"read of pull request #{int(number)} in {repo}")
        sha = ((resp.json().get("head") or {}).get("sha")) or ""
        if not sha:
            raise GitHubError(f"pull request #{int(number)} in {repo} has no head commit")
        resp = self._request(
            "GET", f"{API_BASE}/repos/{owner}/{repo}/commits/{sha}/check-runs",
            params={"per_page": 100},
        )
        self._raise_for_status(resp, f"check runs for {sha[:7]} in {repo}")
        runs = resp.json().get("check_runs") or []
        return {
            "sha": sha,
            "checks": [{"name": r.get("name"), "status": r.get("status"),
                        "conclusion": r.get("conclusion")} for r in runs],
        }
