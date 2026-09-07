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
# 2026-09-06: hyphens allowed. The class was [a-z_]+, so a hyphenated
# agent name would never match a frontend key and this guard would
# report the agent missing even once its satellite existed — a check
# that cannot be satisfied is worse than no check. app_builder uses an
# underscore, but the guard should not depend on that.
_TS_KEY_RE = re.compile(r"""key:\s*["']([a-z_-]+)["']""")


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


def test_exactly_six_agents_today():
    """Not a permanent invariant — documents the roster size at the time
    this test was written so a future change to the roster is a visible,
    deliberate edit to this test rather than a silent pass either way.

    2026-09-06: five became six. `app_builder` split out of `developer`,
    which carried six MCP servers and ~31 tools against 2-4 for every
    other specialist and was the only category ever to miss in the routing
    eval. This canary did its job — it failed on the roster change before
    anything else did, which is the whole point of writing it down.
    """
    assert _backend_agent_keys() == {
        "scheduler", "librarian", "analyst", "systems", "developer",
        "app_builder",
    }


# --- the LIVE interface, added 2026-09-06 ------------------------------
#
# This module guarded web/src/agentLayout.ts and nothing else, while the
# console moved to Swift and the web client was deprecated. So the guard
# written to stop "Developer silently never appeared as a satellite" was
# watching the surface that no longer ships, and the surface that does
# ship had no guard at all. Splitting app_builder out of developer is the
# first roster change since; it would have gone missing from the Swift orb
# field exactly the way Developer once did from the web one.

ORB_FIELD_SWIFT = (
    REPO_ROOT / "macos" / "MortimerHost" / "Sources" / "MortimerHost"
    / "Console" / "OrbFieldView.swift"
)

_SWIFT_KEY_RE = re.compile(r'AgentLayoutEntry\(key:\s*"([a-z_-]+)"')


def _swift_agent_keys() -> set[str]:
    keys = set(_SWIFT_KEY_RE.findall(
        ORB_FIELD_SWIFT.read_text(encoding="utf-8")))
    assert keys, (
        "no AgentLayoutEntry(key: \"...\") entries found in "
        "OrbFieldView.swift — the regex may need updating if the file's "
        "structure changed"
    )
    return keys


def test_the_swift_orb_field_has_every_backend_agent():
    missing = _backend_agent_keys() - _swift_agent_keys()
    assert not missing, (
        f"agent(s) {sorted(missing)} exist in config/agents.yaml but are "
        f"missing from OrbFieldView.swift's AGENT_LAYOUT — they will not "
        f"appear as satellites in the console that actually ships."
    )


def test_the_swift_orb_field_invents_no_agents():
    extra = _swift_agent_keys() - _backend_agent_keys()
    assert not extra, (
        f"OrbFieldView.swift positions {sorted(extra)}, which no longer "
        f"exist in config/agents.yaml — a satellite that can never light up."
    )


def test_both_front_ends_agree_with_each_other():
    # Two hand-tuned copies of the same geometry; they drift or they don't.
    assert _swift_agent_keys() == _frontend_agent_keys()
