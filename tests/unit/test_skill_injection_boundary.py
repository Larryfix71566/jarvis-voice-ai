"""Last-boundary regressions for digest-pinned skill prompt injection."""

from types import SimpleNamespace

import pytest

from jarvis.agent_skills import parse_skill
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from tests.unit.test_subagent import make_agent


@pytest.fixture(autouse=True)
def _initialized_non_sensitive_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_source", ["registry", "package"])
async def test_pinned_skill_is_not_injected_if_registry_pin_changes_after_selection(
    monkeypatch, tmp_path, changed_source,
):
    import jarvis.agents.base as base_module
    import jarvis.skill_catalog as catalog_module

    package = tmp_path / "skills" / "demo-pinned-skill"
    package.mkdir(parents=True)
    skill_path = package / "SKILL.md"
    skill_path.write_text(
        "---\nname: demo-pinned-skill\ndescription: Detect a pin update\n---\n"
        "DO_NOT_INJECT_AFTER_PIN_CHANGE\n",
        encoding="utf-8",
    )
    selected_skill, problems = parse_skill(skill_path)
    assert selected_skill is not None and not problems

    pin = "a" * 64
    pin_reads = iter((
        {"demo-pinned-skill": pin},
        {"demo-pinned-skill": "b" * 64 if changed_source == "registry" else pin},
    ))
    package_reads = 0

    def inspect(_directory, **_kwargs):
        nonlocal package_reads
        package_reads += 1
        revision = "b" * 64 if changed_source == "package" and package_reads > 2 else pin
        return SimpleNamespace(
            enabled=True, revision=revision, reference_paths=(), process_nodes=(),
        )

    monkeypatch.setattr(base_module, "match_skill", lambda _task: selected_skill)
    monkeypatch.setattr(base_module, "skills_workspace_enabled", lambda: True)
    monkeypatch.setattr(base_module, "skill_revision_pins", lambda: next(pin_reads))
    monkeypatch.setattr(catalog_module, "inspect_package", inspect)

    agent, completions = make_agent([("text", "completed")])

    assert await agent.run("use demo-pinned-skill") == "completed"
    injected = "\n".join(
        str(message) for message in completions.requests[0]["messages"]
    )
    assert "DO_NOT_INJECT_AFTER_PIN_CHANGE" not in injected
    assert package_reads == 3
    assert next(pin_reads, None) is None
