"""mcp-git: repo operations as pure logic (upgrade plan §10 U1.5).

Transport-free (invariant 9): no MCP imports here; server.py is the thin
wrapper. Git is invoked via subprocess with an argument list (never shell),
a fixed timeout, and cwd pinned to the repo root.

Draft → confirm → commit (plan §5.2): writes are two-phase. prepare_*
stages/validates and records a pending row in the `actions` table;
the matching execute function requires the action_id and refuses anything
not pending. Drafts expire after DRAFT_TTL_SECONDS.

Allowlist only (plan §9.3): there is no force-push, no branch deletion,
and no way to commit anything but the staged tree. Push is plain `git push`
of the current branch to its configured upstream.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.db import get_conn, now_iso, run_migrations

DRAFT_TTL_SECONDS = 900  # 15 minutes


def _repo_root() -> Path:
    return Path(
        os.environ.get(
            "JARVIS_REPO_ROOT",
            Path(__file__).resolve().parents[2],
        )
    )


def _db() -> sqlite3.Connection:
    conn = get_conn()
    run_migrations(conn)
    return conn


def _git(*args: str) -> tuple[int, str]:
    """Run a git command in the repo. Returns (returncode, combined output)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- reads


def git_status() -> dict:
    code, branch = _git("branch", "--show-current")
    code, porcelain = _git("status", "--porcelain")
    _c, ahead_raw = _git("rev-list", "--count", "@{u}..HEAD")
    _c2, behind_raw = _git("rev-list", "--count", "HEAD..@{u}")
    changed = [l for l in porcelain.splitlines() if l.strip()]
    return {
        "branch": branch,
        "clean": not changed,
        "changed_files": [l[3:] for l in changed],
        "ahead": int(ahead_raw) if ahead_raw.isdigit() else 0,
        "behind": int(behind_raw) if behind_raw.isdigit() else 0,
    }


def git_log(n: int = 5) -> dict:
    n = max(1, min(int(n), 20))
    code, out = _git("log", f"-{n}", "--pretty=format:%h %ad %s", "--date=relative")
    return {"commits": out.splitlines() if out else []}


def git_diff_summary() -> dict:
    _c, stat = _git("diff", "--stat", "HEAD")
    lines = [l for l in stat.splitlines() if l.strip()]
    return {"stat": lines, "summary_line": lines[-1] if lines else "no changes"}


# ------------------------------------------------------- drafts (writes)


def _insert_action(tool: str, payload: dict, summary: str) -> int:
    conn = _db()
    with conn:
        cur = conn.execute(
            "INSERT INTO actions (tool, action_class, draft_payload, summary, status, created_at)"
            " VALUES (?, 'privileged', ?, ?, 'pending', ?)",
            (tool, json.dumps(payload), summary, now_iso()),
        )
    return int(cur.lastrowid)


def _load_pending(action_id: int, tool: str) -> dict | None:
    conn = _db()
    row = conn.execute(
        "SELECT * FROM actions WHERE id = ? AND tool = ?", (action_id, tool)
    ).fetchone()
    if row is None or row["status"] != "pending":
        return None
    created = datetime.fromisoformat(row["created_at"])
    if _now_utc() - created > timedelta(seconds=DRAFT_TTL_SECONDS):
        with conn:
            conn.execute(
                "UPDATE actions SET status = 'expired', resolved_at = ? WHERE id = ?",
                (now_iso(), action_id),
            )
        return None
    return dict(row)


def _resolve(action_id: int, status: str, result: str) -> None:
    conn = _db()
    with conn:
        conn.execute(
            "UPDATE actions SET status = ?, resolved_at = ?, result = ? WHERE id = ?",
            (status, now_iso(), result, action_id),
        )


def prepare_commit(message: str) -> dict:
    """Stage all current changes and draft a commit. Does not commit."""
    if not message or not message.strip():
        return {"ok": False, "error": "commit message is empty"}
    st = git_status()
    if st["clean"]:
        return {"ok": False, "error": "working tree is clean — nothing to commit"}
    code, out = _git("add", "-A")
    if code != 0:
        return {"ok": False, "error": f"git add failed: {out}"}
    files = st["changed_files"]
    summary = (
        f"Commit {len(files)} file(s) on branch '{st['branch']}' "
        f"with message: \"{message}\". Files: {', '.join(files[:10])}"
        + (" …" if len(files) > 10 else "")
    )
    action_id = _insert_action(
        "git_commit", {"message": message, "files": files, "branch": st["branch"]}, summary
    )
    return {"ok": True, "action_id": action_id, "summary": summary}


def commit(action_id: int) -> dict:
    """Execute a previously prepared commit draft."""
    row = _load_pending(action_id, "git_commit")
    if row is None:
        return {"ok": False, "error": "no pending commit with that id (missing, used, or expired)"}
    payload = json.loads(row["draft_payload"])
    code, out = _git("commit", "-m", payload["message"])
    if code != 0:
        _resolve(action_id, "failed", out)
        return {"ok": False, "error": out}
    _resolve(action_id, "committed", out)
    return {"ok": True, "result": out}


def prepare_push() -> dict:
    """Draft a push of the current branch to its upstream. Does not push."""
    st = git_status()
    if st["ahead"] == 0:
        return {"ok": False, "error": f"branch '{st['branch']}' has no unpushed commits"}
    summary = f"Push {st['ahead']} commit(s) on branch '{st['branch']}' to origin."
    action_id = _insert_action("git_push", {"branch": st["branch"], "ahead": st["ahead"]}, summary)
    return {"ok": True, "action_id": action_id, "summary": summary}


def push(action_id: int) -> dict:
    """Execute a previously prepared push draft."""
    row = _load_pending(action_id, "git_push")
    if row is None:
        return {"ok": False, "error": "no pending push with that id (missing, used, or expired)"}
    code, out = _git("push")
    if code != 0:
        _resolve(action_id, "failed", out)
        return {"ok": False, "error": out}
    _resolve(action_id, "committed", out)
    return {"ok": True, "result": out}


def list_actions(status: str = "all", limit: int = 10) -> dict:
    """Recent audit rows from the actions table."""
    limit = max(1, min(int(limit), 50))
    conn = _db()
    if status == "all":
        rows = conn.execute(
            "SELECT id, tool, summary, status, created_at, resolved_at FROM actions"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, tool, summary, status, created_at, resolved_at FROM actions"
            " WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    return {"actions": [dict(r) for r in rows]}
