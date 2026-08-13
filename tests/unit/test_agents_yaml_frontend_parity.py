"""Guard against config/agents.yaml and web/src/agentLayout.ts drifting
apart (star-layout plan §7).

This is the direct regression test for the bug that motivated the star
layout work: config/agents.yaml has always listed all five sub-agents
correctly, and the backend has always emitted delegate_start/delegate_done
events for all five — but web/src/components/OrbField.tsx kept its own,
separately-hardcoded four-agent list, so Developer silently never appeared
as a satellite even though everything else about it worked. The fix moved
satellite positions into web/src/agentLayout.ts as the single shared
source for OrbField and AgentStatusPanel (plan D2/D3), but a hardcoded
frontend list can still drift from config/agents.yaml again the next time
an agent is added — this test fails loudly if that happens.

Regex over the TS source, not a JS/Node runtime dependency, per plan §7:
"do not add a JS runtime dependency to the Python suite."
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_YAML = REPO_ROOT / "config" / "agents.yaml"
AGENT_LAYOUT_TS = REPO_ROOT / "web" / "src" / "agentLayout.ts"

# Matches `key: "developer",` (and similarly quoted single/double) inside
# an AgentLayoutEntry object literal.
_TS_KEY_RE = re.compile(r"""key:\s*["']([a-z_]+)["']""")


def _backend_agent_keys() -> set[str]:
    data = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8"))
    return {entry["name"] for entry in data["sub_agents"]}


def _frontend_agent_keys() -> set[str]:
    text = AGENT_LAYOUT_TS.read_text(encoding="utf-8")
    keys = set(_TS_KEY_RE.findall(text))
    assert keys, (
        "no `key: \"...\"` entries found in agentLayout.ts — the regex "
        "may need updating if the file's structure changed"
    )
    return keys


def test_frontend_layout_has_every_backend_agent():
    backend = _backend_agent_keys()
    frontend = _frontend_agent_keys()
    missing_from_frontend = backend - frontend
    assert not missing_from_frontend, (
        f"agent(s) {sorted(missing_from_frontend)} exist in "
        f"config/agents.yaml but are missing from "
        f"web/src/agentLayout.ts's AGENT_LAYOUT — they will not appear "
        f"as satellites or get positioned status cards. This is exactly "
        f"the bug the star-layout plan fixed for 'developer'; add the "
        f"missing agent(s) to AGENT_LAYOUT."
    )


def test_frontend_layout_has_no_extra_agents():
    backend = _backend_agent_keys()
    frontend = _frontend_agent_keys()
    extra_in_frontend = frontend - backend
    assert not extra_in_frontend, (
        f"agent(s) {sorted(extra_in_frontend)} exist in "
        f"web/src/agentLayout.ts but not in config/agents.yaml — remove "
        f"the stale entry/entries from AGENT_LAYOUT."
    )


def test_exactly_five_agents_today():
    """Not a permanent invariant — documents the roster size at the time
    this test was written so a future change to the roster is a visible,
    deliberate edit to this test rather than a silent pass either way."""
    assert _backend_agent_keys() == {
        "scheduler", "librarian", "analyst", "systems", "developer",
    }
