#!/usr/bin/env python3
"""Print a deterministic digest of Git-visible worktree source files.

Tracked and non-ignored untracked files are included, so staged and unstaged
candidate changes affect the result. Git-ignored build outputs, caches, vaults,
local runtime data, and acceptance receipts stay outside the source fingerprint.
Receipts are excluded because they record the fingerprint and must not create a
self-referential digest cycle.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

_DOMAIN = b"mortimer-worktree-v1\0"
_EXCLUDED_PREFIXES = (b"docs/acceptance/skills-workspace/receipts/",)


def worktree_fingerprint(root: Path) -> str:
    root = root.resolve(strict=True)
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others",
         "--exclude-standard", "-z"],
        check=False, capture_output=True,
    )
    if result.returncode:
        raise ValueError("git_file_inventory_unavailable")

    paths = sorted(
        path for path in set(result.stdout.split(b"\0"))
        if path and not any(path.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)
    )
    digest = hashlib.sha256(_DOMAIN)
    for relative in paths:
        parts = relative.split(b"/")
        if any(part in {b"", b".", b".."} for part in parts):
            raise ValueError("invalid_git_path")
        path = root
        for index, component in enumerate(parts):
            path = path / os.fsdecode(component)
            if index < len(parts) - 1 and path.is_symlink():
                raise ValueError("symlink_parent_in_git_path")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            # A deleted tracked file is represented by its absence. The
            # remaining path/content sequence therefore changes the digest.
            continue

        if stat.S_ISLNK(metadata.st_mode):
            mode = 0o120000
            data = os.fsencode(os.readlink(path))
        elif stat.S_ISREG(metadata.st_mode):
            mode = 0o755 if metadata.st_mode & 0o111 else 0o644
            data = path.read_bytes()
        else:
            raise ValueError("unsupported_git_file_type")

        content_digest = hashlib.sha256(data).digest()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(mode.to_bytes(4, "big"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(content_digest)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1],
        help="repository/worktree root (default: this checkout)",
    )
    args = parser.parse_args(argv)
    try:
        print(worktree_fingerprint(args.root))
    except (OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "worktree_unreadable"
        print(f"candidate fingerprint unavailable: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
