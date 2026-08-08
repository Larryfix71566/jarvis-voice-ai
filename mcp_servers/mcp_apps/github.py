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
