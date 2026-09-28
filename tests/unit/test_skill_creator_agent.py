from types import SimpleNamespace

import pytest

from jarvis import skill_creator_agent
from jarvis.agents.upgrade_agent import TOOL_SPECS


def test_creator_loads_the_exact_reviewed_package_and_declared_references():
    prompt, revision = skill_creator_agent.skill_creator_system_prompt([{
        "skill_id": "existing-skill", "display_name": "Existing skill",
        "description": "Public catalog description", "category": "general",
        "related_workflow_ids": "weekly-review",
    }])
    assert revision == skill_creator_agent.CREATOR_PACKAGE_REVISION
    assert "offline" in prompt
    assert "references/authoring-quality.md" in prompt
    assert "references/mortimer-boundaries.md" in prompt
    assert "Do not call or claim publication" in prompt
    assert '"skill_id":"existing-skill"' in prompt
    assert "related workflow IDs" in prompt


def test_builder_uses_only_creator_read_edit_validate_and_decline_tools():
    captured = {}

    class FakeAgent:
        def __init__(self, service, **kwargs):
            captured.update(service=service, **kwargs)

    service = object()
    agent, revision = skill_creator_agent.build_skill_creator_agent(
        service, run_id="request-1", agent_factory=FakeAgent,
    )
    names = {item["function"]["name"] for item in captured["tool_specs"]}
    assert names == {"file_read", "edit_propose", "session_validate", "session_decline"}
    assert "session_submit" not in names
    assert captured["service"] is service
    assert captured["run_id"] == "request-1"
    assert captured["council_workflow"] == "skill_authoring"
    assert revision == skill_creator_agent.CREATOR_PACKAGE_REVISION


def test_builder_refuses_modified_creator_package(monkeypatch):
    monkeypatch.setattr(skill_creator_agent, "CREATOR_PACKAGE_REVISION", "0" * 64)
    with pytest.raises(skill_creator_agent.CreatorUnavailable):
        skill_creator_agent.skill_creator_system_prompt()


def test_builder_supplies_matched_workflow_and_only_safe_learned_procedure_fields(monkeypatch):
    from jarvis import procedures, workflows

    class Workflow:
        name = "plan-before-implementation"
        when = "Implement a repository change"
        steps = ["Inspect current code"]
        done_when = ["Run the relevant tests"]

    monkeypatch.setattr(workflows, "match_workflow", lambda _agent, _task: Workflow())
    monkeypatch.setattr(procedures, "match_procedure", lambda *_args, **_kwargs: {
        "label": "Review before editing", "description": "Read current code first.",
        "task_tokens": "private-task-tokens", "source_run_ids": "private-run-id",
    })
    captured = {}

    class FakeAgent:
        def __init__(self, _service, **kwargs): captured.update(kwargs)

    skill_creator_agent.build_skill_creator_agent(
        object(), run_id="request-1", task_brief="Implement a repository change",
        agent_factory=FakeAgent,
    )
    assert '"name":"plan-before-implementation"' in captured["system_prompt"]
    assert '"label":"Review before editing"' in captured["system_prompt"]
    assert "private-task-tokens" not in captured["system_prompt"]
    assert "private-run-id" not in captured["system_prompt"]


def test_upgrade_agent_copies_custom_tool_authority():
    from jarvis.agents.upgrade_agent import UpgradeAgent

    specs = [TOOL_SPECS[0]]
    agent = UpgradeAgent(
        SimpleNamespace(status=lambda: {}, branch=None, proposals=[]),
        config_path="config/upgrade_agent.yaml",
        registry_path="config/upgrade_models.yaml",
        profile="codex-subscription",
        client_factory=lambda: object(),
        tool_specs=specs,
    )
    specs.clear()
    assert agent._tool_specs == [TOOL_SPECS[0]]
