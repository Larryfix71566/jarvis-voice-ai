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
