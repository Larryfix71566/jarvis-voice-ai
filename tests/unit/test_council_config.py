"""Unit tests for jarvis/council/config.py (MORTIMER_LLM_COUNCIL_PLAN.md D4,
D8.2.1, D9's key-present/fallback rules). No network."""

from __future__ import annotations

import pytest

from jarvis.council.config import (
    NoUsableProfilesError,
    resolve_members,
    should_shadow,
    tier_members,
)

REGISTRY_YAML = """
default: k-mid-1

profiles:
  - name: k-economy-1
    label: economy one
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_ECON_1
    temperature: 0.2
    tier: economy
  - name: k-economy-2
    label: economy two
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_ECON_2
    temperature: 0.2
    tier: economy
  - name: k-mid-1
    label: mid one
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_MID_1
    temperature: 0.2
    tier: mid
  - name: k-frontier-1
    label: frontier one
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_FRONTIER_1
    temperature: 0.2
    tier: frontier
"""


@pytest.fixture()
def registry_path(tmp_path, monkeypatch):
    p = tmp_path / "upgrade_models.yaml"
    p.write_text(REGISTRY_YAML, encoding="utf-8")
    for key in (
        "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1", "TESTKEY_FRONTIER_1",
    ):
        monkeypatch.delenv(key, raising=False)
    return p


def _set_keys(monkeypatch, *names):
    for n in names:
        monkeypatch.setenv(n, "x")


def test_tier_members_defined_tiers():
    assert tier_members(1) == {"proposers": ["economy"], "judges": ["mid"]}
    # Tier 2 judges = frontier, not mid (2026-08-16 deviation from the
    # plan's original D4 table — see jarvis/council/config.py comment):
    # mid appeared in both tier-2 pools, violating D5's disjointness rule.
    assert tier_members(2) == {"proposers": ["frontier", "mid"], "judges": ["frontier"]}


def test_tier_members_raises_on_undefined_tier():
    with pytest.raises(KeyError):
        tier_members(3)


def test_resolve_members_tier1_proposers_are_economy(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1")
    names = resolve_members(1, "proposers", registry_path=registry_path)
    assert set(names) == {"k-economy-1", "k-economy-2"}


def test_resolve_members_tier1_judges_are_mid(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1")
    names = resolve_members(1, "judges", registry_path=registry_path)
    assert names == ["k-mid-1"]


def test_resolve_members_tier2_proposers_are_frontier_plus_mid(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_MID_1", "TESTKEY_FRONTIER_1")
    names = resolve_members(2, "proposers", registry_path=registry_path)
    assert set(names) == {"k-frontier-1", "k-mid-1"}


def test_resolve_members_tier2_judges_are_frontier(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_MID_1", "TESTKEY_FRONTIER_1")
    names = resolve_members(2, "judges", registry_path=registry_path)
    assert names == ["k-frontier-1"]


def test_resolve_members_exclude_enforces_disjointness(registry_path, monkeypatch):
    # Only one frontier profile exists, and it's also the only tier-2
    # proposer with a key besides mid. Excluding it (as council.py would,
    # having already used it as a proposer) must fall back up the ladder
    # rather than letting it also judge.
    _set_keys(monkeypatch, "TESTKEY_MID_1", "TESTKEY_FRONTIER_1")
    proposer_names = resolve_members(2, "proposers", registry_path=registry_path)
    assert "k-frontier-1" in proposer_names
    # frontier is the top of _TIER_ORDER, so once its one profile is
    # excluded there is nowhere higher to fall back to in this fixture —
    # NoUsableProfilesError is correct (council.py treats this as a
    # convene() failure, D13), not a silent empty judge pool.
    with pytest.raises(NoUsableProfilesError):
        resolve_members(
            2, "judges", registry_path=registry_path, exclude=set(proposer_names),
        )


def test_resolve_members_missing_key_excluded(registry_path, monkeypatch):
    # Only one economy key present -> the other economy profile is dropped,
    # never silently kept.
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_MID_1")
    names = resolve_members(1, "proposers", registry_path=registry_path)
    assert names == ["k-economy-1"]


def test_resolve_members_degenerate_tier_falls_back_up(registry_path, monkeypatch):
    # No economy keys at all -> tier 1 proposers falls back to mid.
    _set_keys(monkeypatch, "TESTKEY_MID_1")
    names = resolve_members(1, "proposers", registry_path=registry_path)
    assert names == ["k-mid-1"]


def test_resolve_members_no_usable_profile_raises(registry_path, monkeypatch):
    # No keys present anywhere -> nothing usable at any tier.
    with pytest.raises(NoUsableProfilesError):
        resolve_members(1, "proposers", registry_path=registry_path)


def test_resolve_members_ui_selection_narrows(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1")
    names = resolve_members(
        1, "proposers", registry_path=registry_path,
        selected={"economy": ["k-economy-2"]},
    )
    assert names == ["k-economy-2"]


def test_resolve_members_empty_ui_selection_falls_back_to_full_tier(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1")
    names = resolve_members(
        1, "proposers", registry_path=registry_path,
        selected={"economy": []},
    )
    assert set(names) == {"k-economy-1", "k-economy-2"}


# --------------------------------------------------- V8: judge backfill

TWO_MID_REGISTRY_YAML = REGISTRY_YAML + """  - name: k-mid-2
    label: mid two
    provider: openai
    model: m
    base_url: https://api.openai.com/v1
    api_key_env: TESTKEY_MID_2
    temperature: 0.2
    tier: mid
"""


@pytest.fixture()
def two_mid_registry_path(tmp_path, monkeypatch):
    p = tmp_path / "upgrade_models_two_mid.yaml"
    p.write_text(TWO_MID_REGISTRY_YAML, encoding="utf-8")
    for key in (
        "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1", "TESTKEY_MID_2",
        "TESTKEY_FRONTIER_1",
    ):
        monkeypatch.delenv(key, raising=False)
    return p


def test_v8_backfill_fires_when_mid_yields_one_judge(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1",
              "TESTKEY_FRONTIER_1")
    names = resolve_members(1, "judges", registry_path=registry_path)
    assert names == ["k-mid-1", "k-frontier-1"]  # mid first, backfill after


def test_v8_no_backfill_when_mid_alone_meets_target(
    two_mid_registry_path, monkeypatch,
):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1",
              "TESTKEY_MID_2", "TESTKEY_FRONTIER_1")
    names = resolve_members(1, "judges", registry_path=two_mid_registry_path)
    assert set(names) == {"k-mid-1", "k-mid-2"}
    assert "k-frontier-1" not in names  # frontier never consulted — target already met


def test_v8_backfill_candidate_in_exclude_is_skipped(registry_path, monkeypatch):
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1",
              "TESTKEY_FRONTIER_1")
    names = resolve_members(
        1, "judges", registry_path=registry_path, exclude={"k-frontier-1"},
    )
    assert names == ["k-mid-1"]  # backfill candidate excluded, target not reached


def test_v8_backfill_exhausted_below_target_still_convenes(registry_path, monkeypatch):
    # No frontier key present -> backfill finds nothing, but the round is
    # not blocked: the hard floor (COUNCIL_MIN_JUDGES) is 1, well below
    # COUNCIL_JUDGE_TARGET's 2.
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_ECON_2", "TESTKEY_MID_1")
    names = resolve_members(1, "judges", registry_path=registry_path)
    assert names == ["k-mid-1"]


def test_v8_proposer_resolution_untouched_by_backfill(registry_path, monkeypatch):
    # Proposers never backfill even if the pool is thin.
    _set_keys(monkeypatch, "TESTKEY_ECON_1", "TESTKEY_MID_1", "TESTKEY_FRONTIER_1")
    names = resolve_members(1, "proposers", registry_path=registry_path)
    assert names == ["k-economy-1"]  # not topped up from mid/frontier


def test_should_shadow_deterministic_same_round_id():
    r = "some-round-id-123"
    assert should_shadow(r, 1) == should_shadow(r, 1)


def test_should_shadow_never_for_undefined_tier():
    assert should_shadow("any-round", 2) is False  # tier 2 absent from COUNCIL_SHADOW_TIERS


def test_should_shadow_rate_zero_never_shadows(monkeypatch):
    import jarvis.council.config as cfg
    monkeypatch.setattr(cfg, "COUNCIL_SHADOW_RATE", 0.0)
    for i in range(20):
        assert cfg.should_shadow(f"round-{i}", 1) is False


def test_should_shadow_rate_one_always_shadows(monkeypatch):
    import jarvis.council.config as cfg
    monkeypatch.setattr(cfg, "COUNCIL_SHADOW_RATE", 1.0)
    for i in range(20):
        assert cfg.should_shadow(f"round-{i}", 1) is True
