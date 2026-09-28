"""Offline contract for the opt-in, fail-closed primary skill selector."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from jarvis.agent_skills import Skill, load_skills
from jarvis.skill_catalog import SkillCatalogEntry, inspect_package
from jarvis.skill_selection import (
    capabilities_for_inventory,
    load_capability_requirements,
    select_primary_skill,
    select_runtime_primary_skill,
)


def skill(
    name: str,
    description: str = "weather forecast lookup",
    body: str = "Reviewed instructions.",
) -> Skill:
    return Skill(name=name, description=description, path=Path(f"/{name}/SKILL.md"),
                 _body=body)


def entry(
    name: str,
    *,
    enabled: bool = True,
    tools: tuple[str, ...] = (),
    capabilities: tuple[str, ...] = (),
    compatible_with: tuple[str, ...] = (),
) -> SkillCatalogEntry:
    return SkillCatalogEntry(
        skill_id=name, display_name=name, description="weather forecast lookup",
        category="research", version="1.0.0", revision="a" * 64,
        installation="installed", enabled=enabled, readiness="ready",
        verification="passed", capabilities=capabilities,
        required_tools=tools, required_credentials=(), reference_paths=(),
        example_ids=(), related_workflow_ids=(),
        compatible_with=compatible_with,
        process_kind="linear", process_nodes=(), source={"kind": "local"},
        blockers=(),
    )


def select(task: str, candidates: list[Skill], entries: list[SkillCatalogEntry], **kwargs):
    return select_primary_skill(
        task, candidates, {item.skill_id: item for item in entries},
        available_tools=kwargs.pop("available_tools", frozenset()),
        available_capabilities=kwargs.pop("available_capabilities", frozenset()),
        readiness=kwargs.pop("readiness", {item.skill_id: "ready" for item in entries}),
        privacy_compatible_skill_ids=kwargs.pop(
            "privacy_compatible_skill_ids", frozenset(item.skill_id for item in entries)
        ),
        **kwargs,
    )


def test_selects_one_primary_and_breaks_score_ties_by_skill_id():
    candidates = [skill("weather-z"), skill("weather-a")]
    result = select("weather forecast", candidates,
                    [entry("weather-z"), entry("weather-a")])
    assert result.selected is not None
    assert result.selected.name == "weather-a"
    assert result.reason == "automatic_match"
    assert [item.reason for item in result.candidates] == ["selected", "eligible"]


def test_duplicate_skill_ids_refuse_independent_of_input_order():
    original = skill("weather", body="first body")
    conflicting = skill("weather", body="conflicting body")
    for candidates in ([original, conflicting], [conflicting, original]):
        result = select("weather forecast", list(candidates), [entry("weather")])
        assert result.selected is None
        assert result.supporting is None
        assert result.reason == "duplicate_skill_id"


def test_explicit_selection_skips_only_lexical_threshold():
    candidate = skill("weather", "weather forecast lookup")
    result = select("unrelated short request", [candidate], [entry("weather")],
                    explicit_skill_id="weather")
    assert result.selected is candidate
    assert result.reason == "explicit_selection"
    assert result.candidates[0].threshold_met is False


def test_explicit_selection_cannot_override_unknown_readiness_or_missing_tools():
    candidate = skill("weather")
    blocked = select("weather forecast", [candidate],
                     [entry("weather", tools=("get_weather",))],
                     explicit_skill_id="weather", readiness={"weather": "unknown"},
                     available_tools=frozenset({"get_weather"}))
    assert blocked.selected is None
    assert blocked.reason == "readiness_unverified"

    unavailable = select("weather forecast", [candidate],
                         [entry("weather", tools=("get_weather",))],
                         explicit_skill_id="weather", available_tools=frozenset())
    assert unavailable.selected is None
    assert unavailable.reason == "required_tool_unavailable_or_unknown"


def test_unknown_capabilities_disabled_package_and_missing_catalog_fail_closed():
    candidate = skill("weather")
    capability = select("weather forecast", [candidate],
                        [entry("weather", capabilities=("forecast",))],
                        available_capabilities=None)
    assert capability.selected is None
    assert capability.candidates[0].reason == "capability_unavailable_or_unknown"

    disabled = select("weather forecast", [candidate], [entry("weather", enabled=False)])
    assert disabled.selected is None
    assert disabled.candidates[0].reason == "skill_disabled"

    invalid_package = entry("weather")
    invalid_package = replace(invalid_package, installation="invalid")
    invalid = select("weather forecast", [candidate], [invalid_package])
    assert invalid.selected is None
    assert invalid.candidates[0].reason == "package_not_validated"

    missing = select("weather forecast", [candidate], [])
    assert missing.selected is None
    assert missing.candidates[0].reason == "catalog_snapshot_missing"

    privacy = select("weather forecast", [candidate], [entry("weather")],
                     privacy_compatible_skill_ids=None)
    assert privacy.selected is None
    assert privacy.candidates[0].reason == "privacy_compatibility_unverified"


def test_prompt_budget_refuses_only_the_selected_skill():
    candidate = skill("weather")
    result = select("weather forecast", [candidate], [entry("weather")],
                    max_injection_chars=1)
    assert result.selected is None
    assert result.reason == "injection_budget_exceeded"
    assert result.candidates[0].reason == "injection_budget_exceeded"


def test_prompt_budget_accepts_exact_primary_boundary_and_refuses_one_char_less():
    candidate = skill("weather", body="Reviewed instructions.")
    exact_limit = len(candidate.as_prompt())

    exact = select("weather forecast", [candidate], [entry("weather")],
                   max_injection_chars=exact_limit)
    short = select("weather forecast", [candidate], [entry("weather")],
                   max_injection_chars=exact_limit - 1)

    assert exact.selected is candidate
    assert exact.reason == "automatic_match"
    assert short.selected is None
    assert short.reason == "injection_budget_exceeded"


def test_selector_never_allows_a_caller_to_raise_the_fixed_prompt_ceiling():
    candidate = skill("weather", body="A" * 20_000)
    result = select("weather forecast", [candidate], [entry("weather")],
                    max_injection_chars=100_000)
    assert result.selected is None
    assert result.reason == "injection_budget_exceeded"


def test_optional_support_requires_mutual_compatibility_and_combined_budget():
    primary = skill("alpha-primary", "alpha beta shared method", "primary body")
    support = skill("beta-support", "alpha beta shared reference", "support body")
    catalog = {
        "alpha-primary": entry("alpha-primary", compatible_with=("beta-support",)),
        "beta-support": entry("beta-support", compatible_with=("alpha-primary",)),
    }
    chosen = select(
        "alpha beta shared", [support, primary], list(catalog.values()),
        threshold=0.2,
    )
    assert chosen.selected is primary
    assert chosen.supporting is support
    assert chosen.support_reason == "mutually_compatible"
    assert [item.reason for item in chosen.candidates] == [
        "selected", "support_selected",
    ]

    one_sided = dict(catalog)
    one_sided["beta-support"] = replace(
        one_sided["beta-support"], compatible_with=(),
    )
    conflict = select(
        "alpha beta shared", [support, primary], list(one_sided.values()),
        threshold=0.2,
    )
    assert conflict.selected is primary
    assert conflict.supporting is None
    assert conflict.support_reason == "mutual_compatibility_not_declared"

    primary_only_budget = len(primary.as_prompt())
    over_budget = select(
        "alpha beta shared", [support, primary], list(catalog.values()),
        threshold=0.2, max_injection_chars=primary_only_budget,
    )
    assert over_budget.selected is primary
    assert over_budget.supporting is None
    assert over_budget.support_reason == "combined_injection_budget_exceeded"


def test_combined_budget_exact_boundary_is_inclusive_and_order_independent():
    primary = skill("alpha-primary", "alpha beta shared method", "primary body")
    support = skill("beta-support", "alpha beta shared reference", "support body")
    catalog = [
        entry("alpha-primary", compatible_with=("beta-support",)),
        entry("beta-support", compatible_with=("alpha-primary",)),
    ]
    exact_limit = len(primary.as_prompt()) + 2 + len(support.as_prompt())

    for candidates in ([primary, support], [support, primary]):
        exact = select("alpha beta shared", list(candidates), catalog,
                       threshold=0.2, max_injection_chars=exact_limit)
        one_short = select("alpha beta shared", list(candidates), catalog,
                           threshold=0.2, max_injection_chars=exact_limit - 1)

        assert exact.selected is primary
        assert exact.supporting is support
        assert exact.support_reason == "mutually_compatible"
        assert one_short.selected is primary
        assert one_short.supporting is None
        assert one_short.support_reason == "combined_injection_budget_exceeded"


def test_reviewed_capability_registry_covers_enabled_skill_metadata():
    requirements = load_capability_requirements()
    skills = load_skills()
    declared = {
        capability
        for skill_item in skills
        for capability in inspect_package(skill_item.path.parent).capabilities
    }
    assert declared <= requirements.keys()
    assert capabilities_for_inventory(
        frozenset({"text", "tools"}), frozenset({"get_weather"}),
        requirements=requirements,
    ) >= {"weather_lookup", "forecast_reporting"}
    assert "weather_lookup" not in capabilities_for_inventory(
        frozenset({"text"}), frozenset(), requirements=requirements,
    )


def test_runtime_selector_requires_both_flags_and_uses_live_inventory(monkeypatch):
    monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
    monkeypatch.setenv("JARVIS_SKILLS_SELECTION_V2", "1")
    monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)

    class Registry:
        def __init__(self, tools):
            self.tools = tools

        def tools_for(self, _server_names):
            return sorted(self.tools)

    requirements = load_capability_requirements()
    tool_inventory = frozenset(
        tool for _routes, tools in requirements.values() for tool in tools
    )
    registry = Registry(tool_inventory)
    route = SimpleNamespace(route=SimpleNamespace(
        capabilities=("text", "tools"), privacy="approved_external",
    ))
    denied = select_runtime_primary_skill(
        "What is the current weather forecast in Camp Croft?",
        registry=registry, server_names=["mcp-web"], resolved_route=route,
        private_route=False, sensitive_task=False,
    )
    assert denied.selected is None
    assert denied.reason == "revision_enforcement_disabled"

    monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
    selected = select_runtime_primary_skill(
        "What is the current weather forecast in Camp Croft?",
        registry=registry, server_names=["mcp-web"], resolved_route=route,
        private_route=False, sensitive_task=False,
    )
    assert selected.selected is not None
    assert selected.selected.name == "current-weather-with-fahrenheit"

    explicitly_selected = select_runtime_primary_skill(
        "Completely unrelated request",
        registry=registry, server_names=["mcp-web"], resolved_route=route,
        private_route=False, sensitive_task=False,
        explicit_skill_id="current-weather-with-fahrenheit",
    )
    assert explicitly_selected.selected is not None
    assert explicitly_selected.selected.name == "current-weather-with-fahrenheit"
    assert explicitly_selected.reason == "explicit_selection"


def test_runtime_package_snapshot_is_ttl_cached_and_pin_changes_invalidate(
    monkeypatch, tmp_path,
):
    import yaml

    import jarvis.agent_skills as agent_skills_module
    import jarvis.skill_selection as selection_module

    monkeypatch.setenv("JARVIS_SKILLS_SELECTION_V2", "1")
    monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
    config_path = tmp_path / "skills.yaml"
    skill_id = "cache-skill"
    revision = "a" * 64
    candidate = skill(skill_id, "cache test reference", "cached body")
    catalog_entry = entry(skill_id)
    config_path.write_text(yaml.safe_dump({
        "schema_version": 2,
        "enabled": [skill_id],
        "revisions": {skill_id: revision},
    }), encoding="utf-8")
    monkeypatch.setattr(agent_skills_module, "SKILLS_CONFIG", config_path)
    monkeypatch.setattr(agent_skills_module, "SKILLS_DIR", tmp_path / "skills")
    load_calls = []
    inspect_calls = []
    refresh_keys = []
    monkeypatch.setattr(
        selection_module, "load_skills",
        lambda **_kwargs: load_calls.append(True) or [candidate],
    )
    monkeypatch.setattr(
        selection_module, "inspect_package",
        lambda *_args, **_kwargs: inspect_calls.append(True) or catalog_entry,
    )
    monkeypatch.setattr(
        selection_module, "_start_runtime_snapshot_refresh",
        lambda key: refresh_keys.append(key),
    )
    now = [100.0]
    monkeypatch.setattr(selection_module.time, "monotonic", lambda: now[0])
    selection_module.clear_runtime_package_snapshot()

    class Registry:
        def tools_for(self, _server_names):
            return []

    route = SimpleNamespace(route=SimpleNamespace(
        capabilities=("text", "tools"), privacy="approved_external",
    ))

    def choose():
        return selection_module.select_runtime_primary_skill(
            "unrelated request", registry=Registry(), server_names=[],
            resolved_route=route, private_route=False, sensitive_task=False,
            explicit_skill_id=skill_id,
        )

    assert choose().selected is candidate
    now[0] += 30
    assert choose().selected is candidate
    assert len(load_calls) == 1
    assert len(inspect_calls) == 1

    now[0] += selection_module.RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS
    assert choose().selected is candidate
    assert len(load_calls) == 1
    assert len(refresh_keys) == 1
    # Expired snapshots remain available during a background refresh. Run the
    # captured worker directly so this test is deterministic and provider-free.
    selection_module._refresh_runtime_package_snapshot(refresh_keys.pop())
    assert len(load_calls) == 2
    assert len(inspect_calls) == 2

    now[0] += selection_module.RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS
    prior_snapshot = selection_module._RUNTIME_PACKAGE_SNAPSHOT
    assert choose().selected is candidate
    assert len(refresh_keys) == 1
    monkeypatch.setattr(
        selection_module, "load_skills",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("fixture refresh failure")),
    )
    selection_module._refresh_runtime_package_snapshot(refresh_keys.pop())
    assert selection_module._RUNTIME_PACKAGE_SNAPSHOT is prior_snapshot
    assert choose().selected is candidate
    assert not refresh_keys
    monkeypatch.setattr(
        selection_module, "load_skills",
        lambda **_kwargs: load_calls.append(True) or [candidate],
    )

    config_path.write_text(yaml.safe_dump({
        "schema_version": 2,
        "enabled": [skill_id],
        "revisions": {skill_id: "b" * 64},
    }), encoding="utf-8")
    now[0] += 1
    changed = choose()
    assert changed.selected is None
    assert changed.reason == "readiness_unverified"
    assert len(load_calls) == 3
    assert len(inspect_calls) == 3
    selection_module.clear_runtime_package_snapshot()


def test_runtime_selector_refuses_sensitive_task_without_private_route(monkeypatch):
    monkeypatch.setenv("JARVIS_SKILLS_SELECTION_V2", "1")
    monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
    route = SimpleNamespace(route=SimpleNamespace(
        capabilities=("text", "tools"), privacy="approved_external",
    ))
    result = select_runtime_primary_skill(
        "Sensitive weather request", registry=object(), server_names=[],
        resolved_route=route, private_route=False, sensitive_task=True,
    )
    assert result.selected is None
    assert result.reason == "privacy_compatibility_unverified"
