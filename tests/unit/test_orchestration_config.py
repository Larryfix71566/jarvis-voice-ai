"""WS-42: the `orchestration` workload and the claude-fable-5-2 profile."""

import json
from pathlib import Path

import yaml

from jarvis.model_routing import resolve_model_route
from jarvis.toolresult import REASON_CLASSES

ROOT = Path(__file__).resolve().parents[2]


def test_orchestration_resolves_to_fable_5_2_text_only_on_the_subscription():
    resolved = resolve_model_route("orchestration")
    assert resolved.model == "claude-fable-5-2"
    assert resolved.identity == "anthropic/claude-fable-5-2"
    assert resolved.route.name == "subscription"
    assert resolved.route.capabilities == ("text",)
    assert resolved.priority == "interactive"


def test_orchestration_has_no_fallback_routes_and_a_subscription_default():
    access = yaml.safe_load((ROOT / "config/model_access.yaml").read_text())
    workload = access["workloads"]["orchestration"]
    assert workload["fallback_routes"] == []
    assert workload["capabilities"] == ["text"]
    assert workload["route"] == "subscription"
    assert access["subscription_defaults"]["orchestration"] == {"route": "subscription"}


def test_profile_mirrors_claude_fable_5():
    profiles = {p["name"]: p for p in
                yaml.safe_load((ROOT / "config/model_profiles.yaml").read_text())["profiles"]}
    new, old = profiles["claude-fable-5-2"], profiles["claude-fable-5"]
    assert new["identity"] == "anthropic/claude-fable-5-2"
    assert new["model"] == "claude-fable-5-2"
    for field in ("endpoint", "temperature", "tier", "vision", "streaming"):
        assert new.get(field) == old.get(field), field


def test_generated_catalog_lists_the_identity_as_seeded():
    data = json.loads((ROOT / "config/generated/model_catalog.claude-subscription.json").read_text())
    entry = next(m for m in data["models"] if m["identity"] == "anthropic/claude-fable-5-2")
    assert entry["model"] == "claude-fable-5-2"
    assert entry["source"] == "seeded"
    assert all(entry[k] is None for k in (
        "context_window", "input_price_per_mtok", "output_price_per_mtok",
        "input_modalities", "deprecation", "fetched_at"))


def test_spoken_fable_alias_stays_on_fable_5():
    aliases = yaml.safe_load((ROOT / "config/model_aliases.yaml").read_text())["aliases"]
    assert aliases["Fable"] == "claude-fable-5"


def test_orchestrator_reasons_have_the_planned_classes():
    assert {k: v for k, v in REASON_CLASSES.items() if k.startswith("orchestrator_")} == {
        "orchestrator_unavailable": "transient",
        "orchestrator_bad_output": "transient",
        "orchestrator_invalid_decision": "approach",
        "orchestrator_runtime_error": "approach",
        "orchestrator_route_refused": "policy",
        "orchestrator_quota": "policy",
    }
