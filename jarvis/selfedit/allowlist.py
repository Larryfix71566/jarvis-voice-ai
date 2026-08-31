"""Path allowlist matching for the self-development loop (plan section 4).

Stdlib-only on purpose: scripts/check_allowlist.py imports this module in CI
before any project dependencies are installed, and jarvis/selfedit/service.py
uses the same matcher so the backend and the gate can never drift apart.

Semantics:
- Patterns match against the full repo-relative POSIX path.
- ``*`` matches within a single path segment; ``**`` matches across segments.
- A pattern without a slash (e.g. ``*.md``) matches root-level files only.
- Deny wins: a path matching any deny pattern is rejected even if an allow
  or core pattern also matches.

Three tiers (MORTIMER_SELFEDIT_TIERS_PLAN.md, Larry 2026-08-31: "if we
continue to deny everything we want to do self-edit wise then a self-edit is
not useful"):

- ``deny`` — Tier 0, human-only. The precise definition: files whose
  corruption the loop CANNOT recover from because they ARE the loop — the
  self-edit service, the sidecar that runs it, the allowlist, the validation
  gates (CI), the model registry it plans with, the vault/.env, dependency
  manifests. A broken Tier-0 file cannot be repaired by the next self-edit.
- ``core`` — Tier B, allowed with ceremony. The product core (jarvis/bot,
  jarvis/agents, …). A bad change here breaks voice — but it lives on a
  sandbox branch in an isolated worktree that Mortimer can never merge, so
  it is recoverable by construction (discard the PR). The ceremony is: a
  plan_path is REQUIRED at preview (refused before staging otherwise), a
  fifth validation gate imports the pipeline/agent modules, and the PR body
  carries a CORE CHANGE block. The human merge is the last gate, as always.
- ``allow`` — Tier A, routine. web/src, docs, tests, prompts, skills, MCP
  servers, configs. Unchanged behaviour.

Precedence for a path matching several lists: deny > allow (routine) >
core. `jarvis/prompts.py` is on both allow and core; it stays routine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DENIED = "denied"
CORE = "core"
ROUTINE = "routine"
UNLISTED = "unlisted"


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


# A repo path as it appears in prose: at least one slash or a known source
# suffix, path-safe characters only. Used by the preview pre-flight to find
# the files a goal NAMES ("Touch jarvis/bot/display.py and web/src/…") so a
# Tier-0 or plan-less Tier-B goal is refused before staging — never after
# the planner has burned iterations discovering the same thing.
_PATH_IN_TEXT = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]*[\w]|[\w-]+\.(?:py|tsx|ts|jsx|js|css|yaml|yml|json|md|swift|sh|toml))(?![\w])"
)


def extract_paths(text: str) -> list[str]:
    """Best-effort: repo-relative paths named in free text, de-duplicated,
    order preserved. Trailing punctuation and a leading './' are stripped;
    URLs and version-ish tokens ('1.4', '0.0.108') are ignored."""
    seen: list[str] = []
    for m in _PATH_IN_TEXT.finditer(text or ""):
        cand = m.group(1).strip().rstrip(".,;:)")
        if cand.startswith("./"):
            cand = cand[2:]
        if "://" in cand or cand.startswith("http"):
            continue
        # a bare "x.y" with no letters after the dot is a version, not a path
        if "/" not in cand and not re.search(r"\.[A-Za-z]", cand):
            continue
        if re.fullmatch(r"[\d.]+", cand):
            continue
        if cand and cand not in seen:
            seen.append(cand)
    return seen


class Allowlist:
    """Compiled allow/core/deny rules loaded from config/self_edit_allowlist.json."""

    def __init__(self, allow: list[str], deny: list[str], core: list[str] | None = None):
        if not allow:
            raise ValueError("allowlist must contain at least one allow pattern")
        self.allow_patterns = list(allow)
        self.deny_patterns = list(deny)
        self.core_patterns = list(core or [])
        self._allow = [_glob_to_regex(p) for p in allow]
        self._deny = [_glob_to_regex(p) for p in deny]
        self._core = [_glob_to_regex(p) for p in self.core_patterns]

    @classmethod
    def load(cls, path: str | Path) -> "Allowlist":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            allow=list(data["allow"]),
            deny=list(data.get("deny", [])),
            core=list(data.get("core", [])),
        )

    @staticmethod
    def _normalize(path: str) -> str:
        # Repo-relative POSIX path; reject absolute paths and traversal.
        p = path.replace("\\", "/").lstrip("/")
        parts = [seg for seg in p.split("/") if seg not in ("", ".")]
        if any(seg == ".." for seg in parts):
            raise ValueError(f"path traversal is not allowed: {path!r}")
        return "/".join(parts)

    def tier(self, path: str) -> str:
        """DENIED / ROUTINE / CORE / UNLISTED for one path (deny wins;
        routine outranks core)."""
        p = self._normalize(path)
        if any(rx.match(p) for rx in self._deny):
            return DENIED
        if any(rx.match(p) for rx in self._allow):
            return ROUTINE
        if any(rx.match(p) for rx in self._core):
            return CORE
        return UNLISTED

    def is_allowed(self, path: str) -> bool:
        return self.tier(path) in (ROUTINE, CORE)

    def is_core(self, path: str) -> bool:
        return self.tier(path) == CORE

    def filter_violations(self, paths: list[str]) -> list[str]:
        """Return the subset of paths that are NOT allowed."""
        return [p for p in paths if not self.is_allowed(p)]

    def core_paths(self, paths: list[str]) -> list[str]:
        """The subset that is Tier B (core) — the ceremony trigger."""
        return [p for p in paths if self.is_core(p)]

    def classify(self, paths: list[str]) -> dict[str, list[str]]:
        """Group paths by tier: {"denied": [...], "core": [...],
        "routine": [...], "unlisted": [...]}."""
        out: dict[str, list[str]] = {DENIED: [], CORE: [], ROUTINE: [], UNLISTED: []}
        for p in paths:
            try:
                out[self.tier(p)].append(p)
            except ValueError:
                out[DENIED].append(p)
        return out
