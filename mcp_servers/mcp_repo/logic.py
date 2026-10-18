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
    result = {"ok": True, "path": rel, "bytes": size, "content": content}
    if rel == "ROADMAP.md":
        try:
            # Hash the actual file bytes, including CRLF, rather than universal
            # newline normalization. Ordinary document reads stay unchanged.
            raw = resolved.read_bytes()
            if len(raw) > REPO_READ_MAX_BYTES:
                raise RepoPathError("Roadmap grew beyond the read limit; not truncated")
            result["content"] = raw.decode("utf-8")
            result["bytes"] = len(raw)
            result["roadmap"] = _roadmap_snapshot(root, result["content"])
        except (OSError, UnicodeError, RepoPathError) as exc:
            return _err(str(exc))
    return result


# A derived presentation of the canonical source, never another status store.
ROADMAP_SNAPSHOT_MAX_BYTES = 512 * 1024
# One canonical roadmap ref plus each log must fit the existing 256-ref
# source envelope. Refuse excess history explicitly; never weaken that bound.
ROADMAP_LOG_MAX_FILES = 255
ROADMAP_LOG_TOTAL_MAX_BYTES = 4 * 1024 * 1024
_ROADMAP_STATES = frozenset({"proposed", "claimed", "in-progress", "review", "landed", "accepted", "blocked", "parked"})


def _roadmap_cards(content: str) -> tuple[list[dict], list[str]]:
    """Parse fenced Markdown conservatively; retain unknown prose verbatim."""
    import re
    cards, issues = [], []
    current, depth, fence = None, 0, None
    seen: set[str] = set()
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else (marker if fence is None else fence)
        if fence is not None or stripped.startswith(("```", "~~~")):
            if current is not None:
                current[1].append(line)
            continue
        opening = re.search(r'<details\b[^>]*\bid=["\'](ws-\d+)["\'][^>]*>', line, re.I)
        if opening:
            if current is not None:
                issues.append(f"{current[0]}: nested workstream section is unsupported")
            else:
                current = [opening[1].upper(), []]
                depth = 0
        if current is None:
            continue
        current[1].append(line)
        depth += len(re.findall(r'<details\b[^>]*>', line, re.I))
        depth -= len(re.findall(r'</details\s*>', line, re.I))
        if depth > 0:
            continue
        identity, lines = current
        current = None
        if identity in seen:
            issues.append(f"{identity}: duplicate section; not combined")
            continue
        seen.add(identity)
        details = "\n".join(lines)
        summary = re.search(r'<summary>(.*?)</summary>', details, re.S)
        title = re.sub(r'<[^>]+>', '', summary[1]).strip() if summary else identity
        fields: dict[str, str] = {}
        checklist = []
        section = ""
        for source_line in lines:
            field = re.match(r'^- \*\*([^*]+):\*\*\s*(.*)$', source_line)
            if field:
                label, value = field.groups()
                if label in fields:
                    issues.append(f"{identity}: duplicate {label} field; see source details")
                else:
                    fields[label] = value.strip()
                section = label
            elif source_line.startswith("#"):
                section = source_line.lstrip("# ")
            item = re.match(r'^\s*- \[([ xX])\]\s+(.*)$', source_line)
            if item:
                checklist.append({"text": item[2], "checked": item[1].lower() == "x", "section": section})
        status = fields.get("Status", "")
        token = re.match(r'^([a-z-]+)(?=\s|:|$)', status.casefold())
        lifecycle = token[1] if token and token[1] in _ROADMAP_STATES else "unclassified"
        if not summary or not status or "Owner" not in fields:
            issues.append(f"{identity}: missing summary, Status or Owner; see source details")
        if lifecycle == "unclassified":
            issues.append(f"{identity}: unclassified lifecycle; original status preserved")
        cards.append({"id": identity, "title": title, "status": status, "lifecycle": lifecycle,
                      "owner": fields.get("Owner", ""), "fields": fields,
                      "details": details, "checklist": checklist})
    if current is not None:
        issues.append(f"{current[0]}: unclosed workstream section; source is malformed")
    if not cards:
        issues.append("No complete workstream sections found")
    # Stable sort; landed remains open until explicitly accepted.
    return sorted(cards, key=lambda c: c["lifecycle"] == "accepted"), issues


def _roadmap_logs(root: Path) -> tuple[list[dict], list[str]]:
    import datetime
    import hashlib
    import re
    import yaml
    records, issues = [], []
    try:
        directory = resolve_repo_path(root, "docs/roadmap-log")
        if not directory.is_dir():
            return [], ["Dated roadmap log directory is missing"]
        files = sorted(directory.glob("*.md"))
        if len(files) > ROADMAP_LOG_MAX_FILES:
            raise RepoPathError("Roadmap logs exceed the file limit; snapshot was not truncated")
        total = 0
        for file in files:
            # Validate every child, including symlinks, through the same guards.
            relative = file.relative_to(root.resolve()).as_posix()
            try:
                resolved = resolve_repo_path(root, relative)
                size = resolved.stat().st_size
                total += size
                if total > ROADMAP_LOG_TOTAL_MAX_BYTES:
                    raise RepoPathError("Roadmap logs exceed the total byte limit; snapshot was not truncated")
                if size > REPO_READ_MAX_BYTES:
                    issues.append(f"{relative}: exceeds guarded per-file read limit")
                    continue
                raw = resolved.read_bytes()
                if len(raw) > REPO_READ_MAX_BYTES:
                    raise RepoPathError("Roadmap log grew beyond the read limit")
                text = raw.decode("utf-8")
                match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
                metadata = yaml.safe_load(match[1]) if match else None
                if not isinstance(metadata, dict):
                    raise ValueError("missing front matter")
                date_value = metadata.get("date")
                if isinstance(date_value, datetime.date) and not isinstance(date_value, datetime.datetime):
                    day = date_value.isoformat()
                elif isinstance(date_value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_value):
                    day = datetime.date.fromisoformat(date_value).isoformat()
                else:
                    raise ValueError("invalid date")
                rows = metadata.get("rows")
                if not isinstance(rows, list) or not rows or any(
                    not isinstance(row, str) or not re.fullmatch(r'WS-\d+', row) for row in rows
                ):
                    raise ValueError("invalid rows")
                heading = next((line.lstrip("# ").strip() for line in text[match.end():].splitlines()
                                if line.startswith("# ")), file.stem)
                records.append({"path": relative, "date": day, "rows": rows,
                                "sha256": hashlib.sha256(raw).hexdigest(), "title": heading})
            except (OSError, UnicodeError, ValueError, yaml.YAMLError):
                issues.append(f"{relative}: unreadable or malformed date/rows metadata")
            except RepoPathError as exc:
                # A refused symlink is reported; an aggregate bound refuses the
                # snapshot rather than returning a plausible partial history.
                if "limit" in str(exc):
                    raise
                issues.append(f"{relative}: path refused by repository guards")
    except OSError:
        issues.append("Dated roadmap log directory could not be read")
    return records, issues


def _roadmap_snapshot(root: Path, content: str) -> dict:
    import datetime
    import hashlib
    import json
    import subprocess
    cards, issues = _roadmap_cards(content)
    logs, log_issues = _roadmap_logs(root.resolve())
    revision, dirty = None, None
    # Local read only. Disable executable fsmonitor hooks; never fetch or pull.
    def git(*args):
        return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                              capture_output=True, text=True, check=True, timeout=3).stdout.strip()
    try:
        revision = git("rev-parse", "--verify", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=all", "--", "ROADMAP.md", "docs/roadmap-log"))
    except (OSError, subprocess.SubprocessError):
        issues.append("Local Git provenance unavailable; no main/installed-revision claim")
    snapshot = {"schema": "mortimer.roadmap.v1", "provenance": {
        "path": "ROADMAP.md", "revision": revision, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "read_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dirty": dirty, "source_kind": "local_checkout"},
        "cards": cards, "logs": logs, "issues": issues + log_issues}
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > ROADMAP_SNAPSHOT_MAX_BYTES:
        raise RepoPathError("Roadmap snapshot exceeds 512 KiB; no workstreams were silently truncated")
    return snapshot

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
        try:
            requested = candidate.relative_to(root).as_posix()
            resolved = resolve_repo_path(root, requested)
            if not resolved.is_relative_to(base) or not resolved.is_file():
                continue
            rel = resolved.relative_to(root)
        except (RepoPathError, ValueError, OSError):
            continue
        if pattern and not candidate.match(pattern):
            continue
        if len(results) >= REPO_SEARCH_MAX_RESULTS:
            truncated = True
            break
        if rel.as_posix() not in results:
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
        try:
            requested = candidate.relative_to(root).as_posix()
            resolved = resolve_repo_path(root, requested)
            if not resolved.is_relative_to(base) or not resolved.is_file():
                continue
            rel = resolved.relative_to(root)
        except (RepoPathError, ValueError, OSError):
            continue
        try:
            if resolved.stat().st_size > REPO_READ_MAX_BYTES:
                continue
            text = resolved.read_text(encoding="utf-8")
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
