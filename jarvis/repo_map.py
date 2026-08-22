"""Shared docs/REPO_MAP.md loader (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md G5).

`SubAgent.__init__` (jarvis/agents/base.py, `inject_repo_map: true` in
config/agents.yaml) has read this file into its system prompt since the
Model Discipline plan — but `UpgradeAgent` (jarvis/agents/upgrade_agent.py),
the loop that actually authors most edits, never read it at all, so the
developer's own self-edit sessions rediscovered the codebase from scratch
every run. This module is the ONE read/cap/skip implementation both loops
now call — never a second copy of the same 8000-char-cap, missing-file-
skips-silently logic.
"""

from __future__ import annotations

from pathlib import Path

# One shared cap — was previously duplicated as SubAgent.REPO_MAP_MAX_CHARS.
REPO_MAP_MAX_CHARS = 8000


def load_repo_map_suffix(max_chars: int = REPO_MAP_MAX_CHARS) -> str:
    """Return a system-prompt suffix carrying docs/REPO_MAP.md, or "".

    Missing file = skip silently (a fresh checkout must not crash either
    loop). Reads once per call — callers are construction-time call sites
    (one read per boot/session, not per run/iteration). Path is resolved
    from this module's OWN `__file__` at call time (not a module-level
    constant) so tests can monkeypatch `jarvis.repo_map.__file__` to point
    at a fixture repo root, the same pattern SubAgent's own repo-map tests
    already used before this logic was extracted here.
    """
    map_path = Path(__file__).resolve().parents[1] / "docs" / "REPO_MAP.md"
    try:
        content = map_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    if len(content) > max_chars:
        content = content[:max_chars]
    return (
        "\n\nRepository map (maintained, may lag reality — "
        "verify with tools before writing):\n" + content
    )
