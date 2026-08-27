"""C6 / contract K4 — untrusted input never shares an agent with an outbound
channel (MORTIMER_PLATFORM_ROADMAP.md C6; MORTIMER_SECURITY_HARDENING_PLAN.md
§7.4).

This test passes trivially today: no agent in config/agents.yaml holds an
untrusted-input server, because mcp-mail does not exist yet. That is the
point. It fails the day someone wires mail to the developer — which is a PR
review comment nobody will remember to make, and a test that will not forget.

MAIL_CALENDAR_BRIEF (T5) adds mcp-mail and the sixth agent; it does not need
to touch this file, because UNTRUSTED_INPUT already names mcp-mail.

OUTBOUND includes mcp-screen and mcp-calendar per CROSS_PLAN_RESOLUTION.md §B:
screen capture and a CalDAV write channel can both act on / exfiltrate through
the outside world, so an agent that reads untrusted email must hold neither.
mcp-calendar does not exist yet (T5, CalDAV Branch B); naming it here is
deliberate — the constraint is in place before the server is.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_YAML = REPO_ROOT / "config" / "agents.yaml"
ALLOWLIST_JSON = REPO_ROOT / "config" / "self_edit_allowlist.json"

#: Contract K4 (CROSS_PLAN_RESOLUTION.md §B). Servers that can reach the
#: outside world, write code, capture the screen, or write a shared calendar.
OUTBOUND = {"mcp-web", "mcp-git", "mcp-apps", "mcp-repo", "mcp-selfedit",
            "mcp-screen", "mcp-calendar"}

#: Contract K4. Servers whose CONTENT is authored by someone who is not
#: Larry, and is therefore a prompt-injection vector.
UNTRUSTED_INPUT = {"mcp-mail"}


def _agents() -> list[dict]:
    data = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8")) or {}
    agents = data.get("sub_agents") or []
    assert agents, f"{AGENTS_YAML} declares no sub_agents"
    return agents


def test_no_agent_mixes_untrusted_input_with_an_outbound_channel():
    violations = []
    for agent in _agents():
        servers = set(agent.get("mcp_servers") or [])
        untrusted = servers & UNTRUSTED_INPUT
        outbound = servers & OUTBOUND
        if untrusted and outbound:
            violations.append(
                f"{agent.get('name')!r} holds untrusted input "
                f"{sorted(untrusted)} AND outbound {sorted(outbound)}"
            )
    assert not violations, (
        "roadmap C6 violated in config/agents.yaml — an agent that reads "
        "content Larry did not write must not also hold a channel that can "
        "act on the outside world:\n  " + "\n  ".join(violations)
    )


def test_the_sets_have_not_been_quietly_emptied():
    """A passing test with an empty set proves nothing. K4 fixes both sets;
    growing UNTRUSTED_INPUT is expected, shrinking either is not."""
    assert OUTBOUND == {"mcp-web", "mcp-git", "mcp-apps", "mcp-repo",
                        "mcp-selfedit", "mcp-screen", "mcp-calendar"}
    assert "mcp-mail" in UNTRUSTED_INPUT


def test_every_named_server_is_real_or_planned():
    """Catches a typo that would make the intersection silently empty.
    mcp-mail (T5) and mcp-calendar (T5 CalDAV) are named before they exist."""
    declared = {p.parent.name.replace("_", "-")
                for p in (REPO_ROOT / "mcp_servers").glob("*/skill.yaml")}
    unknown = (OUTBOUND | UNTRUSTED_INPUT) - declared - {"mcp-mail", "mcp-calendar"}
    assert not unknown, f"K4 names servers that do not exist: {sorted(unknown)}"


def test_report_self_edit_exposure(capsys):
    """INFORMATIONAL, asserts nothing (plan D-H9 / §5 Step 9).

    Reports which mechanisms of this plan the self-edit loop can still
    rewrite. Larry's §8 V7 commit empties this list. It does not assert,
    because the plan must be mergeable before that commit — asserting here
    would make the suite red for a change the implementing model is
    forbidden (C8) to make.
    """
    import json

    from jarvis.selfedit.allowlist import Allowlist

    allowlist = Allowlist.load(ALLOWLIST_JSON)
    # D-H9 / resolution §A — the three paths W0 denies. config/agents.yaml and
    # mcp_servers/*/skill.yaml are DELIBERATELY not here: they stay editable,
    # guarded by tests/unit/test_requires_env_snapshot.py instead.
    guarded = [
        "jarvis/skills/registry.py",
        "tests/unit/test_agent_isolation.py",
        "tests/unit/test_requires_env_snapshot.py",
    ]
    exposed = [p for p in guarded if allowlist.is_allowed(p)]
    print("\nT4a self-edit exposure (D-H9): "
          + (", ".join(exposed) if exposed else "none — V7 commit is in"))
