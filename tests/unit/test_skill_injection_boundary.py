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


@pytest.mark.parametrize("v2,explicit", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("change", ["control", "scripts"])
async def test_compatibility_drift_refuses_at_final_injection_boundary(
    monkeypatch, tmp_path, caplog, v2, explicit, change,
):
    import jarvis.agents.base as base_module
    import jarvis.skill_catalog as catalog_module
    import jarvis.skill_selection as selection_module

    package = tmp_path / "sample-skill"
    package.mkdir()
    path = package / "SKILL.md"
    original = "---\nname: sample-skill\ndescription: Safe skill text\n---\nPRIVATE_BODY_CANARY\n"
    path.write_text(original)
    selected, problems = parse_skill(path)
    assert selected is not None and not problems
    count = 0
    def inspect(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            # Isolate the last parser guard even if catalog evidence is stale.
            if change == "control":
                path.write_text(original.replace("description:", "allowed-tools: PRIVATE_TOOL_CANARY\ndescription:"))
            else:
                (package / "ScRiPtS").mkdir()
        return SimpleNamespace(enabled=True, revision="a" * 64, reference_paths=(), process_nodes=())

    monkeypatch.setattr(catalog_module, "inspect_package", inspect)
    monkeypatch.setattr(base_module, "match_skill", lambda _task: selected)
    monkeypatch.setattr(base_module, "skill_selection_v2_enabled", lambda: v2)
    monkeypatch.setattr(base_module, "skills_workspace_enabled", lambda: True)
    monkeypatch.setattr(base_module, "skill_revision_pins", lambda: {"sample-skill": "a" * 64})
    monkeypatch.setattr(selection_module, "select_runtime_primary_skill", lambda *a, **kw: SimpleNamespace(
        selected=selected, supporting=None, reason="explicit_selection" if explicit else "automatic_match", candidates=(),
    ))
    agent, completions = make_agent([("text", "completed")])
    result = await agent.run("safe task", explicit_skill_id="sample-skill" if explicit else None)
    if explicit:
        assert result.startswith("REFUSED:")
        assert not completions.requests
    else:
        assert result == "completed"
        assert "PRIVATE_BODY_CANARY" not in str(completions.requests)
    assert count == 3
    assert "PRIVATE_TOOL_CANARY" not in caplog.text
    assert str(tmp_path) not in caplog.text
