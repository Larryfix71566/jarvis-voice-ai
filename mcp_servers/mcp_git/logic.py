"""mcp-git: repo operations as pure logic (upgrade plan §10 U1.5).

Transport-free (invariant 9): no MCP imports here; server.py is the thin
wrapper. Git is invoked via subprocess with an argument list (never shell),
a fixed timeout, and cwd pinned to the repo root.

Draft → confirm → commit (plan §5.2): writes are two-phase. prepare_*
stages/validates and records a pending row in the `actions` table;
the matching execute function requires the action_id and refuses anything
not pending. Drafts expire after DRAFT_TTL_SECONDS.

Allowlist only (plan §9.3): there is no force-push, no branch deletion,
and no way to commit anything but the files a draft named (SE1, 2026-09-07:
prepare_commit stages ONLY its `paths`; commit refuses an index that drifted). Push is plain `git push`
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


def _clean_paths(paths: list[str] | None) -> list[str]:
    out: list[str] = []
    for p in paths or []:
        if not isinstance(p, str):
            continue
        p = p.strip()
        # git_status()'s porcelain-v1 list quotes a path with a space; an
        # agent that reads a name there and passes it straight back must
        # not be refused for the quotes git itself added.
        if len(p) >= 2 and p[0] == '"' and p[-1] == '"':
            p = p[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if p.startswith("./"):
            p = p[2:]
        if p and p not in out:
            out.append(p)
    return out


def prepare_commit(message: str, paths: list[str]) -> dict:
    """Stage ONLY `paths` and draft a commit. Does not commit.

    2026-09-07 (MORTIMER_SELFEDIT_AUTHORING_PLAN.md SE1): this used to run
    `git add -A` and drafted whatever was dirty — actions #22 and #26
    committed 61 and 62 files to main by voice under one-line messages
    (#3: 69 files, #11: 27 files, same way). A commit tool that stages the
    whole tree is a defect; the developer names what it wrote. Every named
    path must be exactly one changed FILE as `git status` reports it — a
    directory (or ".") is refused, because staging a directory is `git add
    -A` by another name — and nothing else may already be in the index,
    because `git commit` commits the whole index, not the named files."""
    if not message or not message.strip():
        return {"ok": False, "error": "commit message is empty"}
    wanted = _clean_paths(paths)
    if not wanted:
        return {
            "ok": False,
            "error": "prepare_commit needs the list of files to commit — "
                     "name the files you changed",
        }
    st = git_status()
    if st["clean"]:
        return {"ok": False, "error": "working tree is clean — nothing to commit"}
    code, changed, err = _changed_files(wanted)
    if code != 0:
        return {"ok": False, "error": f"git status failed: {err}"}
    missing = [p for p in wanted if p not in changed]
    if missing:
        under = [p for p in changed if p not in wanted]
        hint = (f" — under those paths git reports: {', '.join(under)}"
                if under else "")
        return {
            "ok": False,
            "error": "not changed in the working tree (name each changed "
                     f"file, not a directory): {', '.join(missing)}{hint}",
        }
    code, out = _git("add", "--", *wanted)
    if code != 0:
        return {"ok": False, "error": f"git add failed: {out}"}
    code, staged, err = _staged_files()
    if code != 0:
        return {"ok": False, "error": f"git diff --cached failed: {err}"}
    unnamed = [p for p in staged if p not in wanted]
    if unnamed:
        return {
            "ok": False,
            "error": "the index already holds files you did not name: "
                     f"{', '.join(unnamed)} — unstage them "
                     f"(git restore --staged {' '.join(unnamed)}) or name them",
        }
    summary = (
        f"Commit {len(wanted)} file(s) on branch '{st['branch']}' "
        f"with message: \"{message}\". Files: {', '.join(wanted)}"
    )
    action_id = _insert_action(
        "git_commit", {"message": message, "files": wanted, "branch": st["branch"]}, summary
    )
    return {"ok": True, "action_id": action_id, "summary": summary}


def commit(action_id: int) -> dict:
    """Execute a previously prepared commit draft."""
    row = _load_pending(action_id, "git_commit")
    if row is None:
        return {"ok": False, "error": "no pending commit with that id (missing, used, or expired)"}
    payload = json.loads(row["draft_payload"])
    # SE1: the index must still be exactly the drafted set — `git commit`
    # commits the index, so anything staged since the draft would ride
    # along under this message without the user having heard it.
    drafted = list(payload.get("files") or [])
    code, staged, err = _staged_files()
    if code != 0:
        _resolve(action_id, "failed", err)
        return {"ok": False, "error": f"git diff --cached failed: {err}"}
    extra = [p for p in staged if p not in drafted]
    gone = [p for p in drafted if p not in staged]
    if extra or gone:
        parts = []
        if extra:
            parts.append(f"staged but not drafted: {', '.join(extra)}")
        if gone:
            parts.append(f"drafted but no longer staged: {', '.join(gone)}")
        msg = ("staged set drifted since the draft: " + "; ".join(parts)
               + " — prepare the commit again")
        _resolve(action_id, "failed", msg)
        return {"ok": False, "error": msg}
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
    # Push the branch the draft was prepared for, by explicit refspec, and
    # set its upstream. A bare `git push` depends on push.default and on
    # the branch's configured upstream — a branch cut from main inherits
    # `origin/main` as upstream, so pushing it bare fails with "the upstream
    # branch of your current branch does not match the name of your
    # current branch" (2026-08-23 and 2026-08-30, both live). The draft
    # recorded which branch it meant; refuse if HEAD has moved since, so a
    # confirm never pushes a branch the user did not preview.
    branch = (json.loads(row["draft_payload"]) or {}).get("branch") or ""
    current = git_status()["branch"]
    if branch and current != branch:
        msg = (f"HEAD moved since the draft: it was prepared for branch "
               f"'{branch}' but '{current}' is checked out now — prepare the push again")
        _resolve(action_id, "failed", msg)
        return {"ok": False, "error": msg}
    target = branch or current
    code, out = _git("push", "-u", "origin", f"{target}:refs/heads/{target}")
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
