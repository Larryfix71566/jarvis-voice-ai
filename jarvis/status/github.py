"""GitHub pull request and check reads (spec T4.3).

Read-only: this calls only `GitHubClient.list_pulls`/`pull_checks`
(`mcp_servers/mcp_apps/github.py`, the one module that talks to GitHub),
both GET. The repository is `JARVIS_GITHUB_REPO` — the same variable and
default as `jarvis/selfedit/service.py` — and the token is the self-edit
token when present, else `GITHUB_TOKEN`. Runs in the admin sidecar, which
holds the vault's keys; the token value never appears in a result (R7).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from jarvis.status.logs import redact

DEFAULT_REPO = "Larryfix71566/jarvis-voice-ai"
KINDS = ("prs", "checks")
STATES = ("open", "closed", "all")
MAX_LIMIT = 50


def _repo() -> tuple[str, str]:
    full = (os.environ.get("JARVIS_GITHUB_REPO") or DEFAULT_REPO).strip()
    owner, _, repo = full.partition("/")
    if not owner or not repo:
        raise ValueError(f"JARVIS_GITHUB_REPO must be owner/repo, got {full!r}")
    return owner, repo


def _token() -> str:
    return (os.environ.get("JARVIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def _client(token: str, owner: str) -> Any:
    from mcp_servers.mcp_apps.github import GitHubClient

    return GitHubClient(token=token, owner=owner)


def _scrub(text: str, token: str) -> str:
    out = str(text)
    if token:
        out = out.replace(token, "<redacted>")
    return redact(out)[:300]


def github_status(kind: str = "prs", *, state: str = "open", limit: int = 10,
                  number: int | None = None, client: Any = None) -> dict[str, Any]:
    """`kind="prs"`: pull requests in `state`; `kind="checks"`: the check
    runs on PR `number`'s head commit. Errors are results, never raised."""
    if kind not in KINDS:
        return {"ok": False, "error": "kind must be 'prs' or 'checks'"}
    if kind == "prs" and state not in STATES:
        return {"ok": False, "error": "state must be 'open', 'closed' or 'all'"}
    if kind == "checks" and (number is None or int(number) <= 0):
        return {"ok": False, "error": "checks needs a pull request number"}
    owner, repo = _repo()
    token = _token()
    if client is None:
        if not token:
            return {"ok": False,
                    "error": "no GitHub token configured (JARVIS_GITHUB_TOKEN or GITHUB_TOKEN)"}
        client = _client(token, owner)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {"ok": True, "generated_at": now, "source": f"github:{owner}/{repo}@{now}",
            "repo": f"{owner}/{repo}", "kind": kind}
    try:
        if kind == "prs":
            n = max(1, min(int(limit), MAX_LIMIT))
            return {**base, "state": state, "pulls": client.list_pulls(repo, state, n)}
        return {**base, "number": int(number), **client.pull_checks(repo, int(number))}
    except Exception as exc:  # noqa: BLE001 — GitHubError and transport alike
        return {"ok": False, "error": _scrub(str(exc), token)}
