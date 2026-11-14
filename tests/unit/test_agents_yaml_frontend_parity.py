"""Guard against config/agents.yaml and the native orb field's agent list
drifting apart (star-layout plan §7).

The bug that motivated it: config/agents.yaml listed all five sub-agents,
but the web console's OrbField kept its own four-agent list, so Developer
never appeared as a satellite. The web console was deleted in release
closure C1b (2026-11); the same guard now watches the Swift orb field,
which is what ships. Regex over the Swift source, no Swift toolchain.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_YAML = REPO_ROOT / "config" / "agents.yaml"


def _backend_agent_keys() -> set[str]:
    data = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8"))
    return {entry["name"] for entry in data["sub_agents"]}


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
