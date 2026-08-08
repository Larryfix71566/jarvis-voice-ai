"""Path allowlist matching for the self-development loop (plan section 4).

Stdlib-only on purpose: scripts/check_allowlist.py imports this module in CI
before any project dependencies are installed, and jarvis/selfedit/service.py
uses the same matcher so the backend and the gate can never drift apart.

Semantics:
- Patterns match against the full repo-relative POSIX path.
- ``*`` matches within a single path segment; ``**`` matches across segments.
- A pattern without a slash (e.g. ``*.md``) matches root-level files only.
- Deny wins: a path matching any deny pattern is rejected even if an allow
  pattern also matches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate an allowlist glob into a full-match regex."""
    i = 0
    out = []
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                # '**' crosses directory boundaries; also swallow a trailing '/'
                i += 2
                if i < n and pattern[i] == "/":
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class Allowlist:
    """Compiled allow/deny rules loaded from config/self_edit_allowlist.json."""

    def __init__(self, allow: list[str], deny: list[str]):
        if not allow:
            raise ValueError("allowlist must contain at least one allow pattern")
        self.allow_patterns = list(allow)
        self.deny_patterns = list(deny)
        self._allow = [_glob_to_regex(p) for p in allow]
        self._deny = [_glob_to_regex(p) for p in deny]

    @classmethod
    def load(cls, path: str | Path) -> "Allowlist":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(allow=list(data["allow"]), deny=list(data.get("deny", [])))

    @staticmethod
    def _normalize(path: str) -> str:
        # Repo-relative POSIX path; reject absolute paths and traversal.
        p = path.replace("\\", "/").lstrip("/")
        parts = [seg for seg in p.split("/") if seg not in ("", ".")]
        if any(seg == ".." for seg in parts):
            raise ValueError(f"path traversal is not allowed: {path!r}")
        return "/".join(parts)

    def is_allowed(self, path: str) -> bool:
        p = self._normalize(path)
        if any(rx.match(p) for rx in self._deny):
            return False
        return any(rx.match(p) for rx in self._allow)

    def filter_violations(self, paths: list[str]) -> list[str]:
        """Return the subset of paths that are NOT allowed."""
        return [p for p in paths if not self.is_allowed(p)]
