"""The model floor — Larry, 2026-09-01 (MORTIMER_OPTIMIZATION_PLAN.md,
Phase 0b item 5).

"The only agent that can use Haiku is the voice agent; all other agents
should not go below the Sonnet or equivalent level."

This is policy, bound in CONFIG rather than stored as a memory fact or a
workflow, because a fact only persuades a model — it cannot bind which
model a delegation actually runs on (the `jarvis_units` lesson). These
tests are the mechanical backstop: they read the real
`config/agents.yaml` and the model registry (joined by `load_model_registry`
from `config/model_profiles.yaml` + `config/model_endpoints.yaml`), so a future edit
that quietly puts a specialist back on the voice model fails CI rather
than surfacing as a slowly-worsening answer quality nobody can explain.

The Supervisor is exempt by construction — it is `settings.openai_model`,
not an entry in agents.yaml. Background maintenance has its own registry
profiles as well; it may use a different provider or model, but it must not
inherit the Supervisor route.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENTS_PATH = ROOT / "config" / "agents.yaml"

# Anything matching this is BELOW the floor. Case-insensitive on purpose:
# "claude-haiku-4-5", "Claude Haiku", "haiku-next" must all trip it.
BELOW_FLOOR = re.compile(r"haiku", re.IGNORECASE)


@pytest.fixture(scope="module")
def profiles_by_name() -> dict[str, dict]:
    # The JOINED view, through the one loader — the floor is about which
    # model and endpoint an agent reaches, and after the registry split the
    # endpoint half lives in config/model_endpoints.yaml.
    from jarvis.agents.upgrade_agent import REGISTRY_PATH_ENV, load_model_registry
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv(REGISTRY_PATH_ENV, raising=False)
        reg = load_model_registry(config_dir=ROOT / "config")
    return {p["name"]: p for p in reg["profiles"].values() if isinstance(p, dict)}


@pytest.fixture(scope="module")
def sub_agents() -> list[dict]:
    cfg = yaml.safe_load(AGENTS_PATH.read_text(encoding="utf-8")) or {}
    agents = [a for a in cfg.get("sub_agents") or [] if isinstance(a, dict)]
    assert agents, "agents.yaml has no sub_agents — the floor has nothing to guard"
    return agents


class TestEveryAgentIsPinnedAboveTheFloor:
    def test_every_agent_declares_a_model_profile(self, sub_agents):
        """An agent with no `model_profile` runs on the voice model, which
        is Haiku. Under the floor that is not a default — it is a bug."""
        missing = [a["name"] for a in sub_agents if not a.get("model_profile")]
        assert not missing, (
            f"agents on the voice model (no model_profile): {missing} — "
            "the floor requires every sub-agent to name a Sonnet-or-better profile"
        )

    def test_every_named_profile_exists(self, sub_agents, profiles_by_name):
        unknown = [
            (a["name"], a["model_profile"])
            for a in sub_agents
            if a.get("model_profile") and a["model_profile"] not in profiles_by_name
        ]
        assert not unknown, f"agents naming a profile the registry lacks: {unknown}"

    def test_no_agent_resolves_to_a_model_below_the_floor(self, sub_agents, profiles_by_name):
        """Checks the RESOLVED wire model, not the profile name — a profile
        called `claude-sonnet-5` whose `model:` was repointed at haiku
        would otherwise pass."""
        below = []
        for a in sub_agents:
            prof = profiles_by_name.get(a.get("model_profile") or "")
            if not prof:
                continue  # covered by the tests above
            for field in ("model", "identity"):
                value = str(prof.get(field, ""))
                if BELOW_FLOOR.search(value):
                    below.append((a["name"], a["model_profile"], field, value))
        assert not below, f"agents resolving below the floor: {below}"

    def test_every_agent_refuses_rather_than_falling_back(self, sub_agents):
        """`on_profile_fallback: warn` falls back to the voice model when the
        profile cannot resolve (unknown name, missing key). Under the floor
        that fallback IS the forbidden outcome, so every agent must refuse
        loudly instead — the Agents-tab chip turns red, the Supervisor
        relays the stated reason, nothing runs on Haiku by accident."""
        soft = [
            (a["name"], a.get("on_profile_fallback", "warn"))
            for a in sub_agents
            if a.get("on_profile_fallback") != "refuse"
        ]
        assert not soft, (
            f"agents that would silently fall back to the voice model: {soft} — "
            "set on_profile_fallback: refuse"
        )


class TestTheFloorProfileItself:
    def test_the_floor_profile_is_direct_anthropic_sonnet(self, profiles_by_name):
        """`claude-sonnet-5` is the floor profile AND the Phase 3 executor
        tier. It replaced the OpenRouter route (same identity, same tier)
        because the registry rule is: never keep a proxy route for a model
        reachable directly."""
        prof = profiles_by_name.get("claude-sonnet-5")
        assert prof is not None, "claude-sonnet-5 profile missing from the registry"
        assert prof.get("identity") == "anthropic/claude-sonnet-5"
        assert "anthropic.com" in str(prof.get("base_url", ""))
        assert prof.get("tier") == "mid"
        assert "or-sonnet-5" not in profiles_by_name, (
            "or-sonnet-5 must not coexist with claude-sonnet-5 (shared identity)"
        )


def test_registry_has_no_haiku_profile_for_non_supervisor_routes(profiles_by_name):
    """Haiku is a voice Supervisor route, never a registry background route."""
    below = [
        (name, field, value)
        for name, profile in profiles_by_name.items()
        for field in ("model", "identity")
        for value in [str(profile.get(field, ""))]
        if BELOW_FLOOR.search(value)
    ]
    assert not below, f"registry profiles must not resolve to Haiku: {below}"
