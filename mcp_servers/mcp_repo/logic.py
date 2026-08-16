"""mcp-repo: LOCAL working-tree access as pure logic
(MORTIMER_AGENT_TRUST_PLAN.md D10-D12).

Transport-free (invariant 9, matching mcp_git/mcp_apps): no MCP imports
here; server.py is the thin wrapper.

This is deliberately a SEPARATE server from mcp_apps (D10) — mcp_apps
reads/writes GitHub; this module reads/writes the local filesystem on this
machine. Blurring the two is exactly what caused the Supervisor to route a
"create a file in the repo" request to app_write_file, which PUTs to
GitHub (plan §1.3). Every tool description in server.py begins "Local
working tree on this machine:" for the same reason (D14).

resolve_repo_path is D11's shared validator, implemented exactly as
specified in the plan — do not reorder its checks (see its docstring).
Writes (D12) reuse the SAME draft -> confirm pattern and the SAME
`actions` table mcp_git's prepare_commit/commit already use
(mcp_servers/mcp_git/logic.py), with their own TTL and their own
write-only deny list.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.db import get_conn, now_iso, run_migrations

# ⚙ TUNING KNOB — largest file repo_read_file will return (D20).
REPO_READ_MAX_BYTES = 256_000

# ⚙ TUNING KNOB — cap on repo_list_files/repo_search result counts (D20).
REPO_SEARCH_MAX_RESULTS = 50

# ⚙ TUNING KNOB — how long a repo_write_file preview's action_id stays
# valid before repo_commit_write must be called again (D20/D12 rule 3).
REPO_WRITE_ACTION_TTL_S = 300

# Denied by exact path-SEGMENT match, case-insensitive. Segment matching
# (not prefix) is what makes `web/.env` and `a/b/.git/config` denied too.
DENY_SEGMENTS = frozenset({
    ".git", ".env", ".venv", "venv", "node_modules",
    "data", "logs", "__pycache__", ".ssh", ".aws",
})

# Denied by filename glob, case-insensitive, applied to the FINAL segment.
DENY_FILE_GLOBS = (
    "*.key", "*.pem", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    ".env.*", "*.sqlite", "*.sqlite3", "*.db",
)

# Explicit re-allow, checked AFTER the globs. Exactly one entry today.
ALLOW_FILENAMES = frozenset({".env.example"})

# --- write-only deny list (D12) — applied IN ADDITION to the read-deny
# list above, because these are readable but must never be agent-writable.
# Mirrors the self-edit machinery's own rule that the agent may not
# repoint its own brain, CI, or dependency pins.
DENY_WRITE_PATHS = frozenset({
    "config/agents.yaml",
    "config/mcp_servers.yaml",
    "config/self_edit_allowlist.json",
    "config/upgrade_models.yaml",
    "claude.md",  # compared lowercase; see _check_write_allowed
})
DENY_WRITE_SEGMENTS = frozenset({".github", "scripts"})
DENY_WRITE_GLOBS = (
    "requirements*.txt", "*.lock", "package-lock.json",
    "pyproject.toml", "dockerfile*",
)


class RepoPathError(Exception):
    """Raised for any rejected path. The message is user/agent facing."""


def _repo_root() -> Path:
    # Mirrors mcp_git/logic.py's _repo_root exactly, so both servers agree
    # on what "the repo" means without importing across the mcp_* boundary.
    return Path(
        os.environ.get(
            "JARVIS_REPO_ROOT",
            Path(__file__).resolve().parents[2],
        )
    )


def resolve_repo_path(repo_root: Path, path: str) -> Path:
    """Validate `path` and return the resolved absolute path inside the repo.

    Raises RepoPathError on any rejection. Never returns a path outside
    repo_root, and never returns a path touching a denied segment or file.

    D11: implemented EXACTLY as specified in
    MORTIMER_AGENT_TRUST_PLAN.md — do not reorder these checks. Resolution
    must happen before containment, and containment before the deny list,
    or a symlink can carry a path out of the repo while still presenting
    innocent-looking segments.
    """
    # 1. Reject absolute paths and empty input outright. An absolute path is
    #    never valid here even if it happens to point inside the repo —
    #    accepting it widens the surface for no benefit.
    if not path or not path.strip():
        raise RepoPathError("path is required")
    candidate = Path(path)
    if candidate.is_absolute():
        raise RepoPathError(f"path must be relative to the repo root: {path!r}")

    # 2. Reject NUL and any segment that is exactly '..'. Redundant with the
    #    containment check below, but it produces a clearer message and does
    #    not rely on resolution semantics.
    if "\x00" in path:
        raise RepoPathError("path contains a NUL byte")
    if any(part == ".." for part in candidate.parts):
        raise RepoPathError(f"path may not contain '..': {path!r}")

    # 3. Resolve BOTH sides with strict=False, then compare. resolve()
    #    collapses '..' and follows symlinks, so this is the check that
    #    actually defeats a symlink pointing out of the repo.
    root = repo_root.resolve(strict=False)
    resolved = (root / candidate).resolve(strict=False)

    # 4. Containment. Use is_relative_to (Python >= 3.9) rather than string
    #    prefix comparison — a str.startswith check would accept a sibling
    #    directory such as '/repo-evil' for root '/repo'.
    if resolved != root and not resolved.is_relative_to(root):
        raise RepoPathError(f"path escapes the repository root: {path!r}")

    # 5. Deny list, applied to the RESOLVED path's segments relative to root,
    #    so a symlink that resolves into .git is caught here even though the
    #    written path never mentioned it.
    rel = resolved.relative_to(root) if resolved != root else Path(".")
    for part in rel.parts:
        if part.lower() in DENY_SEGMENTS:
            raise RepoPathError(f"'{part}' is not readable through this tool")

    # 6. Filename globs, then the explicit re-allow.
    name = resolved.name
    if name not in ALLOW_FILENAMES:
        lowered = name.lower()
        for pattern in DENY_FILE_GLOBS:
            if Path(lowered).match(pattern):
                raise RepoPathError(
                    f"'{name}' matches a denied filename pattern ({pattern})"
                )
    return resolved


def _check_write_allowed(resolved: Path, root: Path) -> None:
    """D12's write-only deny list. Compared against the path relative to
    the repo root, POSIX-style, case-insensitive, as the plan specifies."""
    rel_posix = resolved.relative_to(root).as_posix().lower()
    if rel_posix in DENY_WRITE_PATHS:
        raise RepoPathError(
            f"{rel_posix} is not writable through this tool "
            "(protected configuration)"
        )
    parts = Path(rel_posix).parts
    for part in parts:
        if part in DENY_WRITE_SEGMENTS:
            raise RepoPathError(
                f"{rel_posix} is not writable through this tool "
                "(protected configuration)"
            )
    name = Path(rel_posix).name
    for pattern in DENY_WRITE_GLOBS:
        if Path(name).match(pattern):
            raise RepoPathError(
                f"{rel_posix} is not writable through this tool "
                "(protected configuration)"
            )


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


# ---------------------------------------------------------------- reads


def repo_read_file(path: str) -> dict:
    """Read one file's contents from the local working tree."""
    root = _repo_root()
    try:
        resolved = resolve_repo_path(root, path)
    except RepoPathError as exc:
        return _err(str(exc))
    if not resolved.exists():
        return _err(f"{path} does not exist")
    if not resolved.is_file():
        return _err(f"{path} is not a file")

    # Size enforcement AFTER resolve_repo_path, BEFORE reading (D11) — a
    # stat() call, not read-then-measure, so an oversized file is never
    # actually loaded into memory.
    size = resolved.stat().st_size
    if size > REPO_READ_MAX_BYTES:
        return _err(f"{path} is {size} bytes, over the "
                    f"{REPO_READ_MAX_BYTES} byte limit — read a smaller "
                    "file or a specific section; it was NOT truncated")
    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _err(f"{path} is not valid UTF-8 text (binary file?)")
    rel = resolved.relative_to(root.resolve(strict=False)).as_posix()
    return {"ok": True, "path": rel, "bytes": size, "content": content}


def repo_list_files(subdir: str = "", pattern: str = "") -> dict:
    """List files under `subdir` (repo root if empty), optionally filtered
    by a glob `pattern` matched against the filename. Denied directories
    are skipped entirely rather than reported as empty."""
    root = _repo_root().resolve(strict=False)
    try:
        base = resolve_repo_path(root, subdir) if subdir else root
    except RepoPathError as exc:
        return _err(str(exc))
    if not base.exists() or not base.is_dir():
        return _err(f"{subdir or '.'} is not a directory")

    results: list[str] = []
    truncated = False
    for candidate in sorted(base.rglob("*")):
        if not candidate.is_file():
            continue
        try:
            rel = candidate.relative_to(root)
        except ValueError:
            continue  # symlink resolved outside root — skip, don't error
        if any(part.lower() in DENY_SEGMENTS for part in rel.parts):
            continue
        if pattern and not candidate.match(pattern):
            continue
        if len(results) >= REPO_SEARCH_MAX_RESULTS:
            truncated = True
            break
        results.append(rel.as_posix())
    return {"ok": True, "files": results, "truncated": truncated}


def repo_search(query: str, subdir: str = "") -> dict:
    """Substring search across text files under `subdir`. Best-effort: a
    file that fails to decode as UTF-8 is silently skipped, not errored."""
    if not query or not query.strip():
        return _err("query is required")
    root = _repo_root().resolve(strict=False)
    try:
        base = resolve_repo_path(root, subdir) if subdir else root
    except RepoPathError as exc:
        return _err(str(exc))
    if not base.exists() or not base.is_dir():
        return _err(f"{subdir or '.'} is not a directory")

    matches: list[dict] = []
    truncated = False
    for candidate in sorted(base.rglob("*")):
        if len(matches) >= REPO_SEARCH_MAX_RESULTS:
            truncated = True
            break
        if not candidate.is_file():
            continue
        try:
            rel = candidate.relative_to(root)
        except ValueError:
            continue
        if any(part.lower() in DENY_SEGMENTS for part in rel.parts):
            continue
        try:
            if candidate.stat().st_size > REPO_READ_MAX_BYTES:
                continue
            text = candidate.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if query in line:
                matches.append({
                    "path": rel.as_posix(), "line": line_no,
                    "text": line.strip()[:200],
                })
                if len(matches) >= REPO_SEARCH_MAX_RESULTS:
                    break
    return {"ok": True, "matches": matches, "truncated": truncated}


# ------------------------------------------------------- writes (D12)


def _db() -> sqlite3.Connection:
    conn = get_conn()
    run_migrations(conn)
    return conn


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _insert_write_action(payload: dict, summary: str) -> int:
    conn = _db()
    with conn:
        cur = conn.execute(
            "INSERT INTO actions (tool, action_class, draft_payload, "
            "summary, status, created_at) VALUES "
            "('repo_write', 'privileged', ?, ?, 'pending', ?)",
            (json.dumps(payload), summary, now_iso()),
        )
    return int(cur.lastrowid)


class _ActionExpired(Exception):
    """Internal signal from _load_pending_write — distinct from 'unknown'
    so repo_commit_write can return D12's two different error messages."""


def _load_pending_write(action_id: int) -> dict | None:
    """Return the pending action row, or None if unknown/already used.
    Raises _ActionExpired (after marking the row expired) if it was
    pending but past REPO_WRITE_ACTION_TTL_S — kept distinct from the
    None case so the caller can report "expired" vs "already used or
    unknown" (D12 rules 2 and 3 specify different messages)."""
    conn = _db()
    row = conn.execute(
        "SELECT * FROM actions WHERE id = ? AND tool = 'repo_write'",
        (action_id,),
    ).fetchone()
    if row is None or row["status"] != "pending":
        return None
    created = datetime.fromisoformat(row["created_at"])
    if _now_utc() - created > timedelta(seconds=REPO_WRITE_ACTION_TTL_S):
        with conn:
            conn.execute(
                "UPDATE actions SET status = 'expired', resolved_at = ? "
                "WHERE id = ?",
                (now_iso(), action_id),
            )
        raise _ActionExpired()
    return dict(row)


def _resolve_write_action(action_id: int, status: str, result: str) -> None:
    conn = _db()
    with conn:
        conn.execute(
            "UPDATE actions SET status = ?, resolved_at = ?, result = ? "
            "WHERE id = ?",
            (status, now_iso(), result, action_id),
        )


def repo_write_file(path: str, content: str, rationale: str = "") -> dict:
    """Call 1 (D12): preview a local file write. Writes NOTHING — full
    validation happens here so an invalid write can never reach call 2."""
    root = _repo_root().resolve(strict=False)
    try:
        resolved = resolve_repo_path(root, path)
        _check_write_allowed(resolved, root)
    except RepoPathError as exc:
        return _err(str(exc))

    action = "overwrite" if resolved.exists() else "create"
    byte_len = len(content.encode("utf-8"))
    rel = resolved.relative_to(root).as_posix()
    action_id = _insert_write_action(
        {"path": rel, "content": content, "action": action, "bytes": byte_len,
         "rationale": rationale},
        f"{action} {rel} ({byte_len} bytes)",
    )
    return {
        "ok": True, "pending": True, "action_id": action_id, "path": rel,
        "action": action, "bytes": byte_len,
        "summary": f"Will {action} {rel} ({byte_len} bytes). Call "
                   f"repo_commit_write with action_id={action_id} to apply.",
    }


def repo_commit_write(action_id: int) -> dict:
    """Call 2 (D12): apply a previously previewed write."""
    try:
        row = _load_pending_write(action_id)
    except _ActionExpired:
        return _err(f"action {action_id} expired; call repo_write_file again")
    if row is None:
        return _err(f"action {action_id} already used or unknown")
    payload = json.loads(row["draft_payload"])
    rel_path = payload["path"]

    # Rule 4 — re-validate immediately before writing, from scratch. Do
    # NOT trust the stored resolved path: this is what closes the window
    # in which a symlink is created between call 1 and call 2.
    root = _repo_root().resolve(strict=False)
    try:
        resolved = resolve_repo_path(root, rel_path)
        _check_write_allowed(resolved, root)
    except RepoPathError as exc:
        _resolve_write_action(action_id, "failed", str(exc))
        return _err(str(exc))

    # Rule 6 — parent directories created only inside the repo root, and
    # only after the parent path itself passes resolve_repo_path. If
    # resolved's own segments already passed the deny-list check above,
    # every parent segment was checked too (resolve_repo_path validates
    # the FULL relative path) — this call is the literal, defensive
    # re-statement of that guarantee rather than a trust shortcut.
    parent_rel = resolved.parent.relative_to(root).as_posix()
    if parent_rel and parent_rel != ".":
        try:
            resolve_repo_path(root, parent_rel)
        except RepoPathError as exc:
            _resolve_write_action(action_id, "failed", str(exc))
            return _err(str(exc))
    resolved.parent.mkdir(parents=True, exist_ok=True)

    # Rule 5 — atomic write: temp file in the same directory, then
    # os.replace(). A half-written file is worse than no write.
    content = payload["content"]
    tmp_path = resolved.parent / f".{resolved.name}.tmp{os.getpid()}"
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, resolved)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        _resolve_write_action(action_id, "failed", str(exc))
        return _err(f"write failed: {exc}")

    byte_len = len(content.encode("utf-8"))
    summary = f"Wrote {rel_path} ({byte_len} bytes)."
    _resolve_write_action(action_id, "committed", summary)
    return {
        "ok": True, "path": rel_path, "action": payload["action"],
        "bytes": byte_len, "summary": summary,
    }
