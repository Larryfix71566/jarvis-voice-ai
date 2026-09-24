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

Those two real-config comparisons pin the MIGRATION: they hold while
``config/model_endpoints.yaml`` and ``config/model_profiles.yaml`` are
byte-for-byte what the migration commit wrote (``MIGRATED_SHA256``). The
first routine pool change (split plan §6 step 7 adds a profile) is by
definition no longer the pre-split registry, so from then on they skip,
saying why, and the permanent proofs are the two that do not depend on the
pool's contents: the split script re-run over the frozen pre-split file is
lossless (D6), and the committed files concatenated back into one file
load identically (§9 rollback).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from jarvis.agents import upgrade_agent as ua

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "model_registry"
PRE_SPLIT_YAML = FIXTURES / "upgrade_models.pre_split.yaml"
PRE_SPLIT_REGISTRY = FIXTURES / "registry.pre_split.json"
PRE_SPLIT_AVAILABLE = FIXTURES / "available_models.pre_split.json"

# sha256 of the two split files exactly as the migration wrote them.
MIGRATED_SHA256 = {
    "model_endpoints.yaml": "11ec8ecd439ef594ef6f74de629264350f9bc9b6709b0caa6a2bbcb042a4e7a9",
    "model_profiles.yaml": "fc74fc6813adc8cb9d41f42d7a0b4d1818354c3a5ea81d84dbb372acd946acbf",
}

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


@pytest.fixture
def as_migrated():
    """Skip (never pass vacuously) once the pool has legitimately changed."""
    changed = [name for name, digest in MIGRATED_SHA256.items()
               if hashlib.sha256((ROOT / "config" / name).read_bytes()).hexdigest() != digest]
    if changed:
        pytest.skip(f"{', '.join(changed)} changed since the migration commit, so the "
                    "registry is no longer the pre-split one; D6 is carried by "
                    "test_split_script_is_lossless_on_the_pre_split_registry and "
                    "test_concatenated_rollback_loads_identically")


def _split_script():
    spec = importlib.util.spec_from_file_location(
        "split_model_registry_under_test", ROOT / "scripts" / "split_model_registry.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_available_models_is_byte_identical(snapshot_env, as_migrated):
    """§7: the console contract. Serialised exactly as the snapshot was."""
    rendered = json.dumps(ua.available_models(), indent=2) + "\n"
    assert rendered == PRE_SPLIT_AVAILABLE.read_text(encoding="utf-8")


def test_joined_registry_equals_the_pre_split_registry(snapshot_env, as_migrated):
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


def test_split_script_is_lossless_on_the_pre_split_registry(snapshot_env, tmp_path):
    """D6, permanently: the one-shot script, run over the frozen pre-split
    file, renders a pair whose join equals the pre-split registry exactly —
    every profile, every key, same order, codex-subscription with no
    credential keys."""
    split = _split_script()
    endpoints_text, profiles_text = split.render(PRE_SPLIT_YAML)
    pool = _write_split(tmp_path / "config", endpoints_text, profiles_text)
    joined = ua.load_model_registry(pool)
    expected = _pre_split_registry()
    assert list(joined["profiles"]) == list(expected["profiles"])
    assert joined == expected
    codex = joined["profiles"]["codex-subscription"]
    assert "base_url" not in codex and "api_key_env" not in codex
    assert ua.available_models(pool) == json.loads(
        PRE_SPLIT_AVAILABLE.read_text(encoding="utf-8"))


def test_committed_split_files_are_what_the_script_renders(as_migrated):
    """The committed pair is the script's output, not a hand edit."""
    endpoints_text, profiles_text = _split_script().render(PRE_SPLIT_YAML)
    assert (ROOT / "config" / ua.ENDPOINTS_FILENAME).read_text(encoding="utf-8") == endpoints_text
    assert (ROOT / "config" / ua.PROFILES_FILENAME).read_text(encoding="utf-8") == profiles_text


def test_concatenated_rollback_loads_identically(snapshot_env, tmp_path):
    """§9: "concatenate the two files back into config/upgrade_models.yaml;
    the loader accepts that shape throughout". Done here with the REAL
    committed files, so it keeps holding as the pool changes."""
    config = ROOT / "config"
    combined = tmp_path / ua.LEGACY_REGISTRY_FILENAME
    combined.write_text(
        (config / ua.ENDPOINTS_FILENAME).read_text(encoding="utf-8") + "\n"
        + (config / ua.PROFILES_FILENAME).read_text(encoding="utf-8"),
        encoding="utf-8")
    rolled_back = ua.load_model_registry(config_dir=tmp_path)
    current = ua.load_model_registry()
    assert list(rolled_back["profiles"]) == list(current["profiles"])
    assert rolled_back == current


def test_the_legacy_single_file_is_gone():
    """Step 4 deletes it; its presence beside the split pair is refused."""
    assert not (ROOT / "config" / ua.LEGACY_REGISTRY_FILENAME).exists()


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


# --------------------------------------------------------------------------
# Step 3: every reader goes through the one loader (D2, spec I6 / A2).

_PATH_NAMES = (ua.LEGACY_REGISTRY_FILENAME, ua.PROFILES_FILENAME, ua.ENDPOINTS_FILENAME)
# The loader itself, and the one-shot migration script that writes the files.
_ALLOWED_PARSERS = {
    "jarvis/agents/upgrade_agent.py",
    "scripts/split_model_registry.py",
}


def test_no_module_outside_the_loader_names_a_registry_file_path():
    """§10: "if a reader bypasses the loader, the split makes things worse
    than the status quo by appearing safe". A registry file path as a string
    literal anywhere else is a second reader in the making."""
    import ast

    offenders = []
    for top in ("jarvis", "scripts", "mcp_servers", "sandbox", "services"):
        for py in sorted((ROOT / top).rglob("*.py")):
            rel = py.relative_to(ROOT).as_posix()
            if rel in _ALLOWED_PARSERS or "/node_modules/" in rel:
                continue
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and not any(c.isspace() for c in node.value)
                        and node.value.endswith(_PATH_NAMES)):
                    offenders.append(f"{rel}:{node.lineno} {node.value!r}")
    assert not offenders, offenders


@pytest.fixture
def split_config(tmp_path, monkeypatch):
    """A small split pair under tmp_path/config, selected via the env
    override so every default-path reader sees it."""
    pool = _write_split(tmp_path / "config")
    monkeypatch.setenv(ua.REGISTRY_PATH_ENV, str(pool))
    return pool


def test_model_routing_reads_the_joined_registry(split_config):
    """A2: jarvis.model_routing._load_model_registry is the loader."""
    from jarvis import model_routing

    assert model_routing._load_model_registry() == ua.load_model_registry(split_config)
    assert model_routing._load_model_registry(split_config)["profiles"]["claude-opus"][
        "base_url"] == "https://api.anthropic.com/v1/"


def test_model_catalog_reads_the_joined_registry(split_config):
    from jarvis.model_catalog import load_profiles

    profiles = load_profiles(split_config)
    assert [p["name"] for p in profiles] == ["claude-opus", "codex-subscription"]
    assert profiles[0]["provider"] == "anthropic"  # joined from the endpoint


def test_mcp_child_key_names_come_from_the_joined_registry(split_config):
    """requires_env_dynamic `upgrade_models_api_keys`: after the split the
    key names live in the endpoints file, and a child that is not handed
    them cannot reach its vision model."""
    from jarvis.skills.registry import _resolve_dynamic_env

    names = _resolve_dynamic_env("mcp-screen", [{"source": "upgrade_models_api_keys"}])
    assert names == ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]


def test_real_mcp_child_key_names_are_unchanged(monkeypatch):
    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    from jarvis.skills.registry import _resolve_dynamic_env

    names = _resolve_dynamic_env("mcp-screen", [{"source": "upgrade_models_api_keys"}])
    assert names == ["ANTHROPIC_API_KEY", "MOONSHOT_API_KEY",
                     "OPENAI_API_KEY", "OPENROUTER_API_KEY"]


def test_vault_verify_groups_by_joined_key_and_endpoint(monkeypatch, capsys):
    """§3 item 4: `python -m jarvis.vault verify` groups by (key, endpoint)
    from the JOINED view. Nothing is in the (fake) vault, so nothing is
    probed; each group prints once with the profiles it serves."""
    import argparse

    from jarvis import vault

    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    monkeypatch.setattr(vault, "load_secrets", lambda: {})
    assert vault._cmd_verify(argparse.Namespace()) == 0
    lines = sorted(" ".join(line.split()) for line in capsys.readouterr().out.splitlines()
                   if "not in the vault" in line)
    assert lines == [
        "-- ANTHROPIC_API_KEY not in the vault (claude-opus, claude-fable-5, claude-sonnet-5)",
        "-- MOONSHOT_API_KEY not in the vault (kimi-k3, kimi-k2)",
        "-- OPENAI_API_KEY not in the vault (codex-subscription)",
        "-- OPENROUTER_API_KEY not in the vault (or-gpt-5-mini, or-gemini-flash, "
        "or-deepseek, or-gpt-5.1, or-grok-4.3, or-codex-max, or-grok-4.6, "
        "or-deepseek-v4-pro)",
    ]


def _load_check_env(monkeypatch, repo_root: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_env_under_test_split", ROOT / "scripts" / "check_env.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)
    return module


def test_check_env_reads_the_split_pair(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    monkeypatch.delenv("JARVIS_VISION_PROFILE", raising=False)
    monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _write_split(tmp_path / "config")
    check_env = _load_check_env(monkeypatch, tmp_path)
    check_env.check_model_registry()
    check_env.check_screen_vision()
    out = capsys.readouterr().out
    assert "Model profile claude-opus (registry default) — ANTHROPIC_API_KEY present" in out
    assert "Model profile codex-subscription — OPENAI_API_KEY missing" in out
    assert "Screen vision — will use profile claude-opus" in out


def test_check_env_reports_an_unsafe_registry_instead_of_crashing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    config = tmp_path / "config"
    _write_split(config)
    (config / ua.ENDPOINTS_FILENAME).unlink()
    check_env = _load_check_env(monkeypatch, tmp_path)
    check_env.check_model_registry()
    out = capsys.readouterr().out
    assert "[WARN] Model registry — could not parse the model registry" in out
    assert "does not exist" in out


# --------------------------------------------------------------------------
# Step 5: the credential boundary is structural (D3) and the planner is
# pinned in the denied file (D4).

def _profile_with(extra: str) -> str:
    """PROFILES_YAML with `extra` (4-space-indented YAML) added to claude-opus."""
    return PROFILES_YAML.replace("    vision: true\n", "    vision: true\n" + extra, 1)


class TestCredentialBoundary:
    @pytest.fixture(autouse=True)
    def _no_env_override(self, monkeypatch):
        monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)

    @pytest.mark.parametrize("extra", [
        "    base_url: https://attacker.example/v1\n",
        "    api_key_env: ANTHROPIC_API_KEY\n",
        "    provider: openrouter\n",
        "    api_key: not-a-real-key\n",
        "    credential_env: ANTHROPIC_API_KEY\n",
        "    routes:\n      direct_api:\n        credential_env: ANTHROPIC_API_KEY\n",
        "    headers: {X-Forward: yes}\n",
        "    extra:\n      proxy: https://attacker.example/v1\n",
    ])
    def test_a_profile_declaring_endpoint_vocabulary_is_a_load_error(self, tmp_path, extra):
        """D3: the routine file cannot express "send this key elsewhere"."""
        pool = _write_split(tmp_path / "config", profiles=_profile_with(extra))
        with pytest.raises(ua.ModelRegistryError, match="claude-opus"):
            ua.load_model_registry(pool)

    def test_the_legacy_shape_in_the_pool_is_refused_for_its_vocabulary(self, tmp_path):
        pool = _write_split(tmp_path / "config", profiles=LEGACY_YAML)
        with pytest.raises(ua.ModelRegistryError, match=r"base_url.*\(D3\)"):
            ua.load_model_registry(pool)

    def test_the_real_pool_uses_only_profile_vocabulary(self):
        layers = ua.load_registry_layers()
        assert layers["shape"] == "split"
        assert layers["source"] == ROOT / "config" / ua.PROFILES_FILENAME
        for prof in layers["profiles"]:
            assert not set(prof) & ua.PROFILE_FORBIDDEN_KEYS, prof["name"]


PINNED_ENDPOINTS = ENDPOINTS_YAML + """
supervisor:
  identity: anthropic/claude-opus-5
  endpoint: anthropic
"""


class TestSupervisorPin:
    @pytest.fixture(autouse=True)
    def _no_env_override(self, monkeypatch):
        monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
        monkeypatch.delenv(ua.PROFILE_ENV, raising=False)

    def test_a_default_matching_the_pin_loads(self, tmp_path):
        pool = _write_split(tmp_path / "config", endpoints=PINNED_ENDPOINTS)
        assert ua.load_model_registry(pool)["default"] == "claude-opus"

    def test_re_pointing_the_default_is_a_load_error(self, tmp_path):
        """D4: a routine edit of `default` cannot move the planner."""
        pool = _write_split(
            tmp_path / "config", endpoints=PINNED_ENDPOINTS,
            profiles=PROFILES_YAML.replace("default: claude-opus",
                                           "default: codex-subscription"))
        with pytest.raises(ua.ModelRegistryError, match="supervisor pin"):
            ua.load_model_registry(pool)

    def test_re_identifying_the_pinned_profile_is_a_load_error(self, tmp_path):
        pool = _write_split(
            tmp_path / "config", endpoints=PINNED_ENDPOINTS,
            profiles=PROFILES_YAML.replace("identity: anthropic/claude-opus-5",
                                           "identity: anthropic/claude-haiku-4-5"))
        with pytest.raises(ua.ModelRegistryError, match="supervisor pin"):
            ua.load_model_registry(pool)

    def test_moving_the_pinned_profile_to_another_endpoint_is_a_load_error(self, tmp_path):
        endpoints = PINNED_ENDPOINTS.replace(
            "  codex-subscription:",
            "  other:\n    provider: anthropic\n    base_url: https://api.anthropic.com/v1/\n"
            "    api_key_env: OTHER_KEY\n  codex-subscription:")
        pool = _write_split(
            tmp_path / "config", endpoints=endpoints,
            profiles=PROFILES_YAML.replace("endpoint: anthropic", "endpoint: other"))
        with pytest.raises(ua.ModelRegistryError, match="supervisor pin"):
            ua.load_model_registry(pool)

    def test_the_real_pin_matches_the_resolved_planner_profile(self):
        """D4 on the real config: the planner that resolve_profile() picks
        with no per-session or env choice is the pinned identity, reached
        through the pinned endpoint's host and key."""
        layers = ua.load_registry_layers()
        pin = layers["supervisor"]
        assert pin, "config/model_endpoints.yaml must pin the supervisor"
        planner = ua.resolve_profile(ua.load_model_registry())
        endpoint = layers["endpoints"][pin["endpoint"]]
        assert planner["identity"] == pin["identity"]
        assert planner["base_url"] == endpoint["base_url"]
        assert planner["api_key_env"] == endpoint["api_key_env"]
        assert planner["provider"] == endpoint["provider"]


# --------------------------------------------------------------------------
# Step 8: the generated upstream catalogue baseline (§4a).

def _real_layers(monkeypatch) -> dict:
    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    return ua.load_registry_layers()


class TestGeneratedCatalogue:
    def test_one_catalogue_per_endpoint_and_no_strays(self, monkeypatch):
        layers = _real_layers(monkeypatch)
        assert set(ua.load_upstream_catalogs()) == set(layers["endpoints"])

    def test_every_entry_carries_the_full_schema(self):
        for endpoint, catalog in ua.load_upstream_catalogs().items():
            assert catalog["provider"]
            for entry in catalog["models"]:
                assert tuple(entry) == ua.CATALOG_ENTRY_KEYS, (endpoint, entry)
                assert "/" in entry["identity"]
                if entry["source"] == "seeded":
                    assert entry["fetched_at"] is None

    def test_seeded_baseline_is_what_the_split_script_renders(self):
        """Step 8: seeded from the split script, all 14 pre-split models,
        fetched_at null and source "seeded". Skips once a sync has written
        real entries (the baseline is then a diff, as intended)."""
        catalogs = ua.load_upstream_catalogs()
        if any(e["source"] != "seeded" for c in catalogs.values() for e in c["models"]):
            pytest.skip("a sync has replaced the seeded baseline")
        rendered = _split_script().render_catalogs(PRE_SPLIT_YAML)
        assert set(rendered) == set(catalogs)
        for endpoint, text in rendered.items():
            assert ua.catalog_path(endpoint).read_text(encoding="utf-8") == text
        identities = sorted(e["identity"] for c in catalogs.values() for e in c["models"])
        expected = sorted(p["identity"] for p in _pre_split_registry()["profiles"].values())
        assert identities == expected and len(identities) == 14

    def test_the_pinned_planner_model_string_matches_the_catalogue(self, monkeypatch):
        """D4, the half the load-time pin cannot see: rewriting the pinned
        profile's `model` string (keeping its identity) would quietly
        re-point the planner. The catalogue — generated, never hand-edited —
        says which model string that identity is on that endpoint."""
        monkeypatch.delenv(ua.PROFILE_ENV, raising=False)
        pin = _real_layers(monkeypatch)["supervisor"]
        entry = next(e for e in ua.load_upstream_catalogs()[pin["endpoint"]]["models"]
                     if e["identity"] == pin["identity"])
        planner = ua.resolve_profile(ua.load_model_registry())
        assert planner["model"] == entry["model"]

    def test_no_profile_uses_a_retired_model(self, monkeypatch):
        """§4a.3: a warning in check_env while retirement is ahead, a failing
        invariant in CI once the model is actually gone."""
        import datetime

        today = datetime.date.today().isoformat()
        catalogs = ua.load_upstream_catalogs()
        retired = []
        for prof in _real_layers(monkeypatch)["profiles"]:
            for entry in catalogs.get(prof["endpoint"], {}).get("models", []):
                when = ua.catalog_retirement(entry)
                if entry["identity"] == prof["identity"] and when and when <= today:
                    retired.append(f"{prof['name']} ({entry['identity']}, {when})")
        assert not retired, retired

    @pytest.mark.parametrize("dep, expected", [
        (None, None), ("2026-10-30", "2026-10-30"),
        ({"retires_at": "2026-10-30T00:00:00Z"}, "2026-10-30"), ({}, None),
    ])
    def test_catalog_retirement_reader(self, dep, expected):
        assert ua.catalog_retirement({"deprecation": dep}) == expected


def _catalogue(endpoint: str, provider: str, *entries: dict) -> str:
    models = []
    for extra in entries:
        entry = dict.fromkeys(ua.CATALOG_ENTRY_KEYS)
        entry.update(extra)
        models.append(entry)
    return json.dumps({"schema": 1, "endpoint": endpoint, "provider": provider,
                       "models": models})


class TestCheckEnvCatalogueReport:
    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
        _write_split(tmp_path / "config")
        (tmp_path / "config" / "generated").mkdir()
        return tmp_path

    def _write(self, repo: Path, endpoint: str, text: str) -> None:
        ua.catalog_path(endpoint, config_dir=repo / "config").write_text(text, encoding="utf-8")

    def _run(self, monkeypatch, repo, capsys) -> str:
        check_env = _load_check_env(monkeypatch, repo)
        check_env.check_model_catalog()
        assert check_env.failures == []  # WARN-only, never a preflight failure
        return capsys.readouterr().out

    def test_seeded_and_missing_catalogues_are_visible(self, repo, monkeypatch, capsys):
        self._write(repo, "anthropic", _catalogue(
            "anthropic", "anthropic",
            {"identity": "anthropic/claude-opus-5", "model": "claude-opus-5", "source": "seeded"}))
        out = self._run(monkeypatch, repo, capsys)
        assert ("[WARN] Model catalogue anthropic — 1 models, 1 never fetched "
                "(seeded baseline)") in out
        assert "[WARN] Model catalogue codex-subscription — no config/generated catalogue" in out

    def test_a_fresh_catalogue_passes_and_a_stale_one_warns(self, repo, monkeypatch, capsys):
        import datetime

        fresh = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write(repo, "anthropic", _catalogue(
            "anthropic", "anthropic",
            {"identity": "anthropic/claude-opus-5", "model": "claude-opus-5",
             "fetched_at": fresh, "source": "api"}))
        self._write(repo, "codex-subscription", _catalogue(
            "codex-subscription", "openai",
            {"identity": "openai/gpt-6-astra", "model": "gpt-6-astra",
             "fetched_at": "2026-01-02T00:00:00Z", "source": "api"}))
        out = self._run(monkeypatch, repo, capsys)
        assert "[PASS] Model catalogue anthropic — 1 models, oldest entry fetched" in out
        assert "[WARN] Model catalogue codex-subscription — 1 models, oldest entry " \
               "fetched 2026-01-02" in out and "STALE" in out

    def test_profile_drift_and_retirement_warn(self, repo, monkeypatch, capsys):
        self._write(repo, "anthropic", _catalogue(
            "anthropic", "anthropic",
            {"identity": "anthropic/claude-opus-5", "model": "claude-opus-5-renamed",
             "deprecation": {"retires_at": "2000-01-01"}, "source": "seeded"}))
        self._write(repo, "codex-subscription", _catalogue("codex-subscription", "openai"))
        out = self._run(monkeypatch, repo, capsys)
        assert "profile claude-opus — model 'claude-opus-5' differs from the catalogue's " \
               "'claude-opus-5-renamed'" in out
        assert "anthropic/claude-opus-5 RETIRED on 2000-01-01" in out
        assert "profile codex-subscription — openai/gpt-6-astra is not in the " \
               "codex-subscription catalogue" in out

    def test_legacy_registry_reports_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / ua.LEGACY_REGISTRY_FILENAME).write_text(LEGACY_YAML,
                                                                       encoding="utf-8")
        assert self._run(monkeypatch, tmp_path, capsys) == ""
