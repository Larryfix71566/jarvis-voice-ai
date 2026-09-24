"""Model registry split (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md).

The split moves the registry from one denied file into a denied endpoint
map and a routine profile pool, joined by ONE loader
(``jarvis.agents.upgrade_agent.load_model_registry``). D7 says nothing
observable changes, so the first two tests here were written against the
PRE-split file, before any code moved, and must keep passing afterwards:

- ``available_models()`` — what the console's model picker renders — is
  byte-identical (§7, §3 item 1);
- the joined registry equals the pre-split registry profile-for-profile,
  key-for-key, in the same order (D6).

The frozen inputs live in ``tests/unit/fixtures/model_registry/``:
``upgrade_models.pre_split.yaml`` is the last single-file registry verbatim,
``registry.pre_split.json`` and ``available_models.pre_split.json`` are what
the pre-split code returned for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.agents import upgrade_agent as ua

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "model_registry"
PRE_SPLIT_YAML = FIXTURES / "upgrade_models.pre_split.yaml"
PRE_SPLIT_REGISTRY = FIXTURES / "registry.pre_split.json"
PRE_SPLIT_AVAILABLE = FIXTURES / "available_models.pre_split.json"

# The key-presence pattern the snapshot was taken with. `key_present` is
# part of the console contract, so it is pinned too, not stripped.
_PRESENT = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")
_ABSENT = ("MOONSHOT_API_KEY", "OPENAI_API_KEY")


@pytest.fixture
def snapshot_env(monkeypatch):
    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    for name in _PRESENT:
        monkeypatch.setenv(name, "x")
    for name in _ABSENT:
        monkeypatch.delenv(name, raising=False)


def _pre_split_registry() -> dict:
    return json.loads(PRE_SPLIT_REGISTRY.read_text(encoding="utf-8"))


def test_available_models_is_byte_identical(snapshot_env):
    """§7: the console contract. Serialised exactly as the snapshot was."""
    rendered = json.dumps(ua.available_models(), indent=2) + "\n"
    assert rendered == PRE_SPLIT_AVAILABLE.read_text(encoding="utf-8")


def test_joined_registry_equals_the_pre_split_registry(snapshot_env):
    """D6, on the real config: profile-for-profile, key-for-key, same order.

    Includes ``codex-subscription``, which must come back with NO
    ``base_url`` and NO ``api_key_env`` key (A1) — not keys set to None.
    """
    expected = _pre_split_registry()
    joined = ua.load_model_registry()
    assert joined["default"] == expected["default"]
    assert list(joined["profiles"]) == list(expected["profiles"])
    for name, profile in expected["profiles"].items():
        assert joined["profiles"][name] == profile, name
    codex = joined["profiles"]["codex-subscription"]
    assert "base_url" not in codex and "api_key_env" not in codex
    assert joined == expected


def test_the_frozen_pre_split_file_still_loads_to_the_snapshot(snapshot_env):
    """Legacy single-file acceptance (§3 item 2, §9 rollback): the last
    single-file registry, loaded through the same loader, is still exactly
    what it was."""
    assert ua.load_model_registry(PRE_SPLIT_YAML) == _pre_split_registry()


# --------------------------------------------------------------------------
# Step 2: the loader joins endpoints into profiles and accepts both shapes.

ENDPOINTS_YAML = """
endpoints:
  anthropic:
    provider: anthropic
    base_url: https://api.anthropic.com/v1/
    api_key_env: ANTHROPIC_API_KEY
  codex-subscription: {provider: openai, kind: subscription, route: codex_subscription}
"""

PROFILES_YAML = """
default: claude-opus
profiles:
  - name: claude-opus
    label: Opus
    endpoint: anthropic
    model: claude-opus-5
    identity: anthropic/claude-opus-5
    temperature: null
    tier: frontier
    vision: true
  - name: codex-subscription
    label: Codex
    endpoint: codex-subscription
    model: gpt-6-astra
    identity: openai/gpt-6-astra
    tier: frontier
"""

LEGACY_YAML = """
default: claude-opus
profiles:
  - name: claude-opus
    label: Opus
    provider: anthropic
    model: claude-opus-5
    identity: anthropic/claude-opus-5
    base_url: https://api.anthropic.com/v1/
    api_key_env: ANTHROPIC_API_KEY
    temperature: null
    tier: frontier
    vision: true
  - name: codex-subscription
    label: Codex
    provider: openai
    model: gpt-6-astra
    identity: openai/gpt-6-astra
    tier: frontier
"""


def _write_split(directory: Path, endpoints: str = ENDPOINTS_YAML,
                 profiles: str = PROFILES_YAML) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ua.ENDPOINTS_FILENAME).write_text(endpoints, encoding="utf-8")
    pool = directory / ua.PROFILES_FILENAME
    pool.write_text(profiles, encoding="utf-8")
    return pool


class TestLoaderShapes:
    @pytest.fixture(autouse=True)
    def _no_env_override(self, monkeypatch):
        monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)

    def test_split_pair_joins_to_the_legacy_shape(self, tmp_path):
        pool = _write_split(tmp_path / "config")
        legacy = tmp_path / "legacy.yaml"
        legacy.write_text(LEGACY_YAML, encoding="utf-8")
        assert ua.load_model_registry(pool) == ua.load_model_registry(legacy)

    def test_join_drops_the_endpoint_key(self, tmp_path):
        joined = ua.load_model_registry(_write_split(tmp_path / "config"))
        assert all("endpoint" not in p for p in joined["profiles"].values())

    def test_credential_less_endpoint_adds_no_credential_keys(self, tmp_path):
        """A1: codex-subscription gets `provider` and nothing else."""
        codex = ua.load_model_registry(
            _write_split(tmp_path / "config"))["profiles"]["codex-subscription"]
        assert codex["provider"] == "openai"
        assert "base_url" not in codex and "api_key_env" not in codex
        assert "kind" not in codex and "route" not in codex

    def test_default_resolution_reads_the_split_pair(self, tmp_path):
        _write_split(tmp_path / "config")
        reg = ua.load_model_registry(config_dir=tmp_path / "config")
        assert list(reg["profiles"]) == ["claude-opus", "codex-subscription"]
        assert reg["profiles"]["claude-opus"]["base_url"] == "https://api.anthropic.com/v1/"

    def test_env_override_still_wins(self, tmp_path, monkeypatch):
        _write_split(tmp_path / "config")
        legacy = tmp_path / "other.yaml"
        legacy.write_text("default: x\nprofiles:\n  - name: x\n", encoding="utf-8")
        monkeypatch.setenv(ua.REGISTRY_PATH_ENV, str(legacy))
        assert list(ua.load_model_registry(config_dir=tmp_path / "config")["profiles"]) == ["x"]

    def test_legacy_file_is_used_when_no_split_file_exists(self, tmp_path):
        (tmp_path / ua.LEGACY_REGISTRY_FILENAME).write_text(LEGACY_YAML, encoding="utf-8")
        reg = ua.load_model_registry(config_dir=tmp_path)
        assert reg["profiles"]["claude-opus"]["api_key_env"] == "ANTHROPIC_API_KEY"

    def test_nothing_at_all_is_the_empty_registry(self, tmp_path):
        assert ua.load_model_registry(config_dir=tmp_path) == {"default": None, "profiles": {}}

    def test_combined_single_file_is_the_rollback_shape(self, tmp_path):
        """§9: concatenating the two files back into one still loads."""
        combined = tmp_path / ua.LEGACY_REGISTRY_FILENAME
        combined.write_text(ENDPOINTS_YAML + PROFILES_YAML, encoding="utf-8")
        split = ua.load_model_registry(_write_split(tmp_path / "config"))
        assert ua.load_model_registry(config_dir=tmp_path) == split

    def test_missing_endpoints_file_fails_loudly(self, tmp_path):
        """§3 item 3: never keyless profiles."""
        config = tmp_path / "config"
        _write_split(config)
        (config / ua.ENDPOINTS_FILENAME).unlink()
        with pytest.raises(ua.ModelRegistryError, match="does not exist"):
            ua.load_model_registry(config_dir=config)
        with pytest.raises(ua.ModelRegistryError, match="does not exist"):
            ua.load_model_registry(config / ua.PROFILES_FILENAME)

    def test_missing_profiles_file_fails_loudly(self, tmp_path):
        config = tmp_path / "config"
        _write_split(config)
        (config / ua.PROFILES_FILENAME).unlink()
        with pytest.raises(ua.ModelRegistryError, match="is missing"):
            ua.load_model_registry(config_dir=config)

    def test_split_and_legacy_side_by_side_is_ambiguous(self, tmp_path):
        config = tmp_path / "config"
        _write_split(config)
        (config / ua.LEGACY_REGISTRY_FILENAME).write_text(LEGACY_YAML, encoding="utf-8")
        with pytest.raises(ua.ModelRegistryError, match="will not guess"):
            ua.load_model_registry(config_dir=config)

    def test_unknown_endpoint_id_is_a_load_error(self, tmp_path):
        pool = _write_split(tmp_path / "config",
                            profiles=PROFILES_YAML.replace("endpoint: anthropic",
                                                           "endpoint: anthropc"))
        with pytest.raises(ua.ModelRegistryError, match="unknown endpoint 'anthropc'"):
            ua.load_model_registry(pool)

    def test_the_pool_never_loads_in_the_legacy_shape(self, tmp_path):
        """A profiles file rewritten into the old single-file shape must not
        quietly become a credential-bearing legacy registry."""
        pool = _write_split(tmp_path / "config", profiles=LEGACY_YAML)
        with pytest.raises(ua.ModelRegistryError):
            ua.load_model_registry(pool)

    def test_the_pool_may_not_carry_its_own_endpoints(self, tmp_path):
        pool = _write_split(tmp_path / "config",
                            profiles=ENDPOINTS_YAML + PROFILES_YAML)
        with pytest.raises(ua.ModelRegistryError, match="may not declare"):
            ua.load_model_registry(pool)

    def test_duplicate_profile_names_are_a_load_error(self, tmp_path):
        dup = PROFILES_YAML + """  - name: claude-opus
    endpoint: anthropic
    model: claude-opus-5
    identity: anthropic/claude-opus-5-dup
"""
        with pytest.raises(ua.ModelRegistryError, match="declared twice"):
            ua.load_model_registry(_write_split(tmp_path / "config", profiles=dup))

    def test_endpoint_needs_a_credential_unless_it_is_a_subscription(self, tmp_path):
        bad = ENDPOINTS_YAML.replace("    api_key_env: ANTHROPIC_API_KEY\n", "")
        with pytest.raises(ua.ModelRegistryError, match="needs base_url and api_key_env"):
            ua.load_model_registry(_write_split(tmp_path / "config", endpoints=bad))
        sub = ENDPOINTS_YAML.replace("route: codex_subscription",
                                     "route: codex_subscription, base_url: https://x.test/v1")
        with pytest.raises(ua.ModelRegistryError, match="kind: subscription"):
            ua.load_model_registry(_write_split(tmp_path / "config", endpoints=sub))
