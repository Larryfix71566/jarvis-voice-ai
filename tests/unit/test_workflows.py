"""Unit tests for jarvis/workflows.py (K4).

Matching is pure when `workflows` is passed explicitly — no file I/O, no
model, no network.
"""

from __future__ import annotations

import pytest

from jarvis.workflows import (
    MATCH_THRESHOLD,
    Workflow,
    load_workflows,
    match_workflow,
    parse_workflow,
    workflows_enabled,
)


def wf(name="w", when="commit and push the branch", **kw) -> Workflow:
    return Workflow(name=name, when=when, **kw)


class TestParsing:
    def test_requires_name_and_when(self):
        assert parse_workflow({"name": "a"}) is None
        assert parse_workflow({"when": "b"}) is None
        assert parse_workflow({}) is None
        assert parse_workflow("not a dict") is None

    def test_scalar_fields_are_coerced_to_lists(self):
        w = parse_workflow({"name": "a", "when": "b", "steps": "one step"})
        assert w.steps == ["one step"]

    def test_agents_are_lowercased(self):
        w = parse_workflow({"name": "a", "when": "b", "agents": ["Developer"]})
        assert w.agents == ["developer"]


class TestMatching:
    def test_matches_on_shared_task_language(self):
        w = wf(when="review the plan before committing to the repository")
        got = match_workflow("developer",
                             "review the plan before committing changes", [w])
        assert got is w

    def test_unrelated_task_does_not_match(self):
        w = wf(when="review the plan before committing")
        assert match_workflow("developer", "what is the weather tomorrow", [w]) is None

    def test_agent_list_restricts(self):
        w = wf(when="commit and push the branch", agents=["developer"])
        assert match_workflow("scheduler", "commit and push the branch", [w]) is None
        assert match_workflow("developer", "commit and push the branch", [w]) is w

    def test_empty_agent_list_means_every_agent(self):
        w = wf(when="commit and push the branch")
        assert match_workflow("scheduler", "commit and push the branch", [w]) is w

    def test_strongest_match_wins(self):
        """MAX_INJECTED is 1 by design — two competing policies in one
        prompt is how an agent gets stuck choosing between them."""
        weak = wf(name="weak", when="commit changes")
        strong = wf(name="strong", when="commit and push the branch to origin")
        got = match_workflow("developer", "commit and push the branch to origin",
                             [weak, strong])
        assert got.name == "strong"

    def test_empty_task_matches_nothing(self):
        assert match_workflow("developer", "", [wf()]) is None

    def test_no_workflows_is_not_an_error(self):
        assert match_workflow("developer", "anything", []) is None

    def test_threshold_is_higher_than_a_hint_would_need(self):
        """A false procedure match costs little; a false workflow match
        tells an agent to follow a policy that does not apply."""
        assert MATCH_THRESHOLD >= 0.3


class TestPromptRendering:
    def test_states_it_as_a_standing_instruction_not_a_fact(self):
        w = wf(steps=["Research alternatives first"])
        text = w.as_prompt()
        assert "standing instruction" in text
        assert "Research alternatives first" in text

    def test_done_when_is_rendered_when_present(self):
        w = wf(steps=["do the thing"], done_when=["tests are green"])
        text = w.as_prompt()
        assert "It is not done until:" in text
        assert "tests are green" in text

    def test_done_when_section_is_omitted_when_empty(self):
        assert "It is not done until" not in wf(steps=["x"]).as_prompt()

    def test_tells_the_agent_to_say_so_rather_than_fake_compliance(self):
        """Golden Rule 1 applies here too: an agent that cannot follow the
        instruction must say so, not report success."""
        assert "rather than reporting success" in wf(steps=["x"]).as_prompt()


class TestKillSwitchAndLoading:
    def test_kill_switch_disables_loading(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JARVIS_WORKFLOWS_ENABLED", "false")
        assert workflows_enabled() is False
        assert load_workflows(tmp_path) == []

    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("JARVIS_WORKFLOWS_ENABLED", raising=False)
        assert workflows_enabled() is True

    def test_missing_directory_is_not_an_error(self, tmp_path):
        assert load_workflows(tmp_path / "nope") == []

    def test_one_bad_file_does_not_disable_the_rest(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_WORKFLOWS_ENABLED", raising=False)
        (tmp_path / "good.yaml").write_text(
            "name: good\nwhen: commit and push\n", encoding="utf-8")
        (tmp_path / "broken.yaml").write_text("{[not yaml", encoding="utf-8")
        (tmp_path / "incomplete.yaml").write_text("when: no name\n", encoding="utf-8")
        loaded = load_workflows(tmp_path)
        assert [w.name for w in loaded] == ["good"]

    def test_source_is_recorded_for_traceability(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_WORKFLOWS_ENABLED", raising=False)
        (tmp_path / "a.yaml").write_text("name: a\nwhen: b\n", encoding="utf-8")
        assert load_workflows(tmp_path)[0].source == "a.yaml"


class TestNotAnExecutor:
    def test_workflow_has_no_run_method(self):
        """Guidance, not a state machine. If this test ever fails,
        someone has started building an executor — which the plan puts
        explicitly out of scope."""
        w = wf(steps=["a", "b"], done_when=["c"])
        for forbidden in ("run", "execute", "apply", "step", "advance"):
            assert not hasattr(w, forbidden), f"Workflow grew a .{forbidden}()"
