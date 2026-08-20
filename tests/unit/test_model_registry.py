"""config/upgrade_models.yaml invariants.

Larry 2026-08-19, when OpenRouter joined the registry. A proxy makes it
possible — and easy — to register a model you can already reach directly,
under a different profile name and a different model string. That is not a
tidiness problem: the council's founding rule is that a model never scores
its own proposal, and `resolve_members`' `exclude` enforces it on PROFILE
NAMES. Two profiles wrapping one model would let that model judge itself
while the guarantee still read as enforced in the code.

`identity` is the canonical vendor/model string, distinct from `name` (this
profile) and `model` (what this endpoint wants). These tests are the
backstop that makes the rule mechanical rather than a comment nobody reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "upgrade_models.yaml"
AGENTS_PATH = Path(__file__).resolve().parents[2] / "config" / "agents.yaml"
COUNCIL_TIERS = {"economy", "mid", "frontier"}


@pytest.fixture(scope="module")
def registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}


@pytest.fixture(scope="module")
def profiles(registry) -> list[dict]:
    return [p for p in (registry.get("profiles") or []) if isinstance(p, dict)]


class TestIdentity:
    def test_every_profile_declares_an_identity(self, profiles):
        missing = [p.get("name") for p in profiles if not p.get("identity")]
        assert not missing, f"profiles without `identity`: {missing}"

    def test_no_two_profiles_share_an_identity(self, profiles):
        """THE test this file exists for. A duplicate means one model can
        propose and judge in the same council round."""
        seen: dict[str, str] = {}
        clashes = []
        for p in profiles:
            ident = str(p["identity"])
            if ident in seen:
                clashes.append(f"{ident}: {seen[ident]} and {p['name']}")
            seen[ident] = str(p["name"])
        assert not clashes, (
            "two profiles resolve to the SAME underlying model, which breaks "
            "the council's proposer/judge disjointness (resolve_members "
            "excludes by profile name, not by model): " + "; ".join(clashes)
        )

    def test_identity_is_vendor_qualified(self, profiles):
        """A bare model string cannot be compared across providers — the
        whole point is that `gpt-5.1` direct and `openai/gpt-5.1` via a
        proxy must collide, and they only do if both are written the
        vendor-qualified way."""
        bare = [p["name"] for p in profiles if "/" not in str(p.get("identity", ""))]
        assert not bare, f"identity must be vendor/model: {bare}"


class TestTiers:
    def test_every_council_tier_has_at_least_two_profiles(self, profiles):
        """A tier of one makes select_winner's min/variance tiebreaks inert
        and turns a 'council' into one model's output with ceremony. This
        was true of `mid` before OpenRouter, and invisible."""
        counts = {t: 0 for t in COUNCIL_TIERS}
        for p in profiles:
            if p.get("tier") in counts:
                counts[p["tier"]] += 1
        thin = {t: n for t, n in counts.items() if n < 2}
        assert not thin, f"tiers with fewer than two profiles: {thin}"

    def test_no_single_key_owns_an_entire_tier(self, profiles):
        """Frontier used to be two profiles behind one ANTHROPIC_API_KEY, so
        a single revocation took tier-2 proposers AND judges to zero at the
        same moment. A tier must survive losing any one credential."""
        by_tier: dict[str, set] = {}
        for p in profiles:
            if p.get("tier") in COUNCIL_TIERS:
                by_tier.setdefault(p["tier"], set()).add(
                    str(p.get("api_key_env", "OPENAI_API_KEY")))
        single = {t: keys for t, keys in by_tier.items() if len(keys) < 2}
        assert not single, (
            f"tiers depending on a single credential: {single}")


class TestAgentAssignments:
    def test_every_model_profile_named_by_an_agent_exists(self, profiles):
        """A typo here does not raise — SubAgent falls back to the voice
        model with a logged warning, which is a dispatcher silently doing
        specialist work."""
        names = {str(p["name"]) for p in profiles}
        agents = yaml.safe_load(AGENTS_PATH.read_text(encoding="utf-8")) or {}
        for agent in agents.get("sub_agents") or []:
            if not isinstance(agent, dict):
                continue
            wanted = agent.get("model_profile")
            if wanted:
                assert str(wanted) in names, (
                    f"{agent.get('name')} names model_profile {wanted!r}, "
                    f"which is not in the registry")

    def test_the_registry_default_exists(self, registry, profiles):
        names = {str(p["name"]) for p in profiles}
        assert str(registry.get("default")) in names


class TestTierTwoConvenes:
    """Larry 2026-08-19, option (b). Tier 2 listed "frontier" for BOTH roles
    while proposers also took "mid", so proposers swallowed every profile in
    the registry and per-member disjointness left the judge pool empty.
    _fallback_up could not rescue it (frontier is the top of the ladder), so
    resolve_members raised and convene() quietly downgraded a second
    escalation to "council too small" — declining to convene the exact
    council that tier exists for.

    Latent from the start: the pre-OpenRouter registry (2 frontier, 1 mid)
    produced the identical zero. It survived because tier 2 needs two
    validation failures plus a failed repair to fire at all, which is also
    why a unit test rather than live use has to be the thing that catches it.
    """

    @pytest.fixture(autouse=True)
    def _keys(self, monkeypatch):
        for env in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
                    "MOONSHOT_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.setenv(env, "test-key")

    @pytest.mark.parametrize("tier", [1, 2])
    def test_both_roles_resolve_and_never_overlap(self, tier):
        from jarvis.council import config as cc
        proposers = cc.resolve_members(tier, "proposers", seed="round-x")
        judges = cc.resolve_members(
            tier, "judges", exclude=set(proposers), seed="round-x")
        assert proposers, f"tier {tier} resolved no proposers"
        assert judges, f"tier {tier} resolved no judges"
        assert not (set(proposers) & set(judges)), (
            f"tier {tier} has a model both proposing and judging")

    def test_tier_two_reaches_the_judge_target(self):
        """The first cut of the partition passed the caller's `exclude` into
        the basis, so the judges call reserved from an already-halved pool
        and produced ONE judge. One judge makes an abstention fatal and
        leaves select_winner's min/variance tiebreaks inert."""
        from jarvis.council import config as cc
        proposers = cc.resolve_members(2, "proposers", seed="round-x")
        judges = cc.resolve_members(
            2, "judges", exclude=set(proposers), seed="round-x")
        assert len(judges) >= cc.COUNCIL_JUDGE_TARGET

    def test_tier_two_still_has_frontier_proposers(self):
        """Reserving judges must never consume the whole frontier tier —
        tier 2's purpose is frontier PROPOSALS, and a partition that fixed
        the crash by leaving nothing to propose would defeat it."""
        from jarvis.council import config as cc
        frontier = {p["name"] for p in cc._profiles_for_tier_name("frontier")}
        proposers = set(cc.resolve_members(2, "proposers", seed="round-x"))
        assert frontier & proposers

    def test_the_partition_is_deterministic_for_one_round(self):
        from jarvis.council import config as cc
        first = cc.resolve_members(2, "judges", seed="round-x")
        second = cc.resolve_members(2, "judges", seed="round-x")
        assert first == second

    def test_the_partition_rotates_across_rounds(self):
        """A fixed split would make the same two models the permanent
        arbiters of every tier-2 winner."""
        from jarvis.council import config as cc
        seen = {tuple(cc.resolve_members(2, "judges", seed=f"round-{i}"))
                for i in range(40)}
        assert len(seen) > 1
