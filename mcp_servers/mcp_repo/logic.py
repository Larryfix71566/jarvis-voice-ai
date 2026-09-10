"""Read-only access to the installed local repository.

Reads retain the existing path and secret guards. Both legacy file-writing
entry points refuse unconditionally; development uses VM self-edit sessions.
"""

from __future__ import annotations

from mcp_servers.development_boundary import sandbox_required

import os
from pathlib import Path


# ⚙ TUNING KNOB — largest file repo_read_file will return (D20).
REPO_READ_MAX_BYTES = 256_000

# ⚙ TUNING KNOB — cap on repo_list_files/repo_search result counts (D20).
REPO_SEARCH_MAX_RESULTS = 50

# Denied by exact path-SEGMENT match, case-insensitive. Segment matching
# (not prefix) is what makes `web/.env` and `a/b/.git/config` denied too.
DENY_SEGMENTS = frozenset({
    ".git", ".env", ".venv", "venv", "node_modules",
    "data", "logs", "__pycache__", ".ssh", ".aws",
})

# Denied by filename glob, case-insensitive, applied to the FINAL segment.
# "*.vault": the credential vault (MORTIMER_CREDENTIAL_VAULT_PLAN.md S8)
# lives in data/ (already a denied segment); the glob covers a vault
# file misplaced anywhere else.
DENY_FILE_GLOBS = (
    "*.key", "*.pem", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    ".env.*", "*.sqlite", "*.sqlite3", "*.db", "*.vault",
)

# Explicit re-allow, checked AFTER the globs. Exactly one entry today.
ALLOW_FILENAMES = frozenset({".env.example"})

class RepoPathError(Exception):
    """Raised for any rejected path. The message is user/agent facing."""


def _repo_root() -> Path:
    # Mirrors mcp_git/logic.py's _repo_root exactly, so both servers agree
    # on what "the repo" means without importing across the mcp_* boundary.
    #
    # F2 hardening (MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md): a value that is
    # empty, whitespace, or contains "${" is treated as unset. The
    # registry's expand_env_vars leaves unknown ${VAR}s as literal text by
    # design, and a config entry referencing an unset variable once handed
    # this function the literal string "${JARVIS_REPO_ROOT}" — a phantom
    # root under which no file exists.
    value = os.environ.get("JARVIS_REPO_ROOT", "")
    if not value.strip() or "${" in value:
        return Path(__file__).resolve().parents[2]
    return Path(value)


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


def repo_write_file(path: str, content: str, rationale: str = "") -> dict:
    """Retired local writer; neither preview nor confirmation can write files."""
    return sandbox_required()


def repo_commit_write(action_id: int) -> dict:
    """Refuse even a pending action created before sandbox isolation shipped."""
    return sandbox_required()
