"""Read-only Git inspection and historical action audit.

The legacy staging, commit and push entry points return an unconditional
sandbox-required response. Publication is owned by the verified VM session.
"""

from __future__ import annotations

from mcp_servers.development_boundary import sandbox_required

import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jarvis.db import get_conn, run_migrations

# ⚙ TUNING KNOB — age past which a held index.lock is called out as
# unusually old in the D15 message below (MORTIMER_AGENT_TRUST_PLAN.md
# D20). scripts/check_env.py duplicates this value locally (by value, not
# import — see its own comment) for its independent stale-lock WARN.
GIT_LOCK_STALE_AFTER_S = 300


def _repo_root() -> Path:
    # Mirrored by mcp_repo/logic.py's _repo_root — keep in sync.
    # F2 hardening (MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md): empty,
    # whitespace, or "${"-containing values are treated as unset —
    # expand_env_vars leaves unknown ${VAR}s literal by design, and a
    # config entry referencing an unset variable would otherwise hand
    # this function a phantom root.
    value = os.environ.get("JARVIS_REPO_ROOT", "")
    if not value.strip() or "${" in value:
        return Path(__file__).resolve().parents[2]
    return Path(value)


def _db() -> sqlite3.Connection:
    conn = get_conn()
    run_migrations(conn)
    return conn


def _format_age(age_s: float) -> str:
    age_s = max(0, int(age_s))
    days, rem = divmod(age_s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes}m"
    if minutes:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"


def _lock_error_message(raw_output: str) -> str | None:
    """D15: if `raw_output` is git's held/stale index.lock error, return the
    precise message naming the lock path, its creation time, and its age,
    with the exact manual-removal command — instead of the raw git stderr,
    which is what got paraphrased into "restart the admin sidecar" in the
    incident this decision exists to prevent (plan §1.4). Returns None for
    any other git error, in which case the caller keeps using raw_output
    unchanged.

    Deliberately does NOT delete the lock file itself, at any age — see the
    plan's explicit "Do not implement auto-deletion" rule.
    """
    if "index.lock" not in raw_output or "File exists" not in raw_output:
        return None
    lock_path = _repo_root() / ".git" / "index.lock"
    if not lock_path.exists():
        return None
    mtime = lock_path.stat().st_mtime
    created = datetime.fromtimestamp(mtime, tz=timezone.utc)
    age_s = _now_utc().timestamp() - mtime
    age = _format_age(age_s)
    stale_note = (
        " — older than expected for an active git operation"
        if age_s > GIT_LOCK_STALE_AFTER_S else ""
    )
    return (
        f"git index is locked by {lock_path} (created {created.isoformat()}, "
        f"{age} ago{stale_note}).\n"
        "If no git process is running, remove it with:\n"
        f"    rm {lock_path}"
    )


def _git_raw(*args: str) -> tuple[int, str, str]:
    """Run a git command in the repo. Returns (returncode, stdout, stderr)
    untouched — for callers that parse NUL-separated output and must not
    see stderr mixed into it."""
    proc = subprocess.run(
        ["git", *args],
        cwd=_repo_root(),
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _git(*args: str) -> tuple[int, str]:
    """Run a git command in the repo. Returns (returncode, combined output).
    On failure, a held/stale index.lock error is rewritten via
    _lock_error_message (D15); any other failure passes through unchanged."""
    code, stdout, stderr = _git_raw(*args)
    out = (stdout + stderr).strip()
    if code != 0:
        lock_msg = _lock_error_message(out)
        if lock_msg is not None:
            return code, lock_msg
    return code, out


def _nul_paths(stdout: str) -> list[str]:
    """Paths from `-z` (NUL-separated) git output — never quoted, so a path
    with a space is the same string the caller passed."""
    return [t for t in stdout.split("\0") if t]


def _changed_files(paths: list[str]) -> tuple[int, list[str], str]:
    """Every changed FILE under `paths` as git reports it — tracked
    modifications, deletions, and untracked files. `--untracked-files=all`
    so a new directory lists its files instead of collapsing to `dir/`;
    `-z` so names are raw (porcelain v1 quotes a path with a space). A
    rename/copy entry carries its original path as a following token,
    which is skipped. Returns (returncode, files, error_text)."""
    code, stdout, stderr = _git_raw(
        "status", "--porcelain", "-z", "--untracked-files=all", "--", *paths
    )
    if code != 0:
        err = (stdout + stderr).strip()
        return code, [], _lock_error_message(err) or err
    files: list[str] = []
    tokens = stdout.split("\0")
    i = 0
    while i < len(tokens):
        entry = tokens[i]
        i += 1
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        files.append(path)
        if xy[0] in "RC":
            i += 1  # the original path of a rename/copy
    return 0, files, ""


def _staged_files() -> tuple[int, list[str], str]:
    """Files in the index that differ from HEAD — what `git commit` would
    commit right now."""
    code, stdout, stderr = _git_raw("diff", "--cached", "--name-only", "-z")
    if code != 0:
        err = (stdout + stderr).strip()
        return code, [], _lock_error_message(err) or err
    return 0, _nul_paths(stdout), ""


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


def changed_files() -> dict:
    """Every changed FILE in the working tree, one entry per file — the
    shape prepare_commit accepts.

    git_status()'s `changed_files` is porcelain v1: it QUOTES a path
    containing a space and collapses an untracked directory to `dir/`.
    Both forms are rejected by prepare_commit (which needs real, per-file
    names), so callers that need a list to hand to it use this."""
    code, files, err = _changed_files(["."])
    if code != 0:
        return {"ok": False, "error": err, "files": []}
    return {"ok": True, "files": files}


def git_log(n: int = 5) -> dict:
    n = max(1, min(int(n), 20))
    code, out = _git("log", f"-{n}", "--pretty=format:%h %ad %s", "--date=relative")
    return {"commits": out.splitlines() if out else []}


def git_diff_summary() -> dict:
    _c, stat = _git("diff", "--stat", "HEAD")
    lines = [l for l in stat.splitlines() if l.strip()]
    return {"stat": lines, "summary_line": lines[-1] if lines else "no changes"}


# ------------------------------------------------------- drafts (writes)


def prepare_commit(message: str, paths: list[str]) -> dict:
    """Retired: do not stage host files or create a legacy commit draft."""
    return sandbox_required()


def commit(action_id: int) -> dict:
    """Retired: old action IDs cannot bypass sandbox verification."""
    return sandbox_required()


def prepare_push() -> dict:
    """Retired: publication belongs to the verified sandbox session."""
    return sandbox_required()


def push(action_id: int) -> dict:
    """Retired: never push a host checkout, including a confirmed old draft."""
    return sandbox_required()


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
