import json
from types import SimpleNamespace

import pytest

from jarvis.skill_authoring import SkillAuthoringService
from tests.sandbox_fakes import FakeRuntime


def test_creator_tool_refuses_replaced_job_at_session_resolution(tmp_path):
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
        expected_job_id="job-original",
    )
    assert service.start_session("Original draft", run_id="job-original")["ok"]
    assert service.propose_edit("skills/weather-brief/SKILL.md", "original", "draft")["ok"]
    # A status check could have happened before another request replaced the
    # slug's active session. The actual read/write/validate lookup must fence it.
    assert service.cancel()["ok"]
    replacement = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert replacement.start_session("Replacement draft", run_id="job-new")["ok"]
    assert service.propose_edit("skills/weather-brief/SKILL.md", "wrong draft", "stale")["ok"] is False
    assert service.read_file("skills/weather-brief/SKILL.md")["ok"] is False
    assert service.validate()["ok"] is False
    assert "skills/weather-brief/SKILL.md" not in service._runtime().active(
        "owner/repo", "skill-authoring-weather-brief", service.policy.is_allowed,
    ).files


def _draft_valid_weather_skill(service):
    # FakeRuntime snapshots its fixture root at construction time. Keep the
    # protected registry in that baseline just as the real candidate has it.
    runtime = service._runtime()
    runtime.baseline.setdefault(
        "config/skills.yaml", "schema_version: 2\nenabled: []\nrevisions: {}\n",
    )
    skill = "---\nname: weather-brief\ndescription: Local weather summaries.\n---\n\n# Weather brief\n\nSummarize a requested forecast.\n"
    manifest = """schema_version: 1
skill_id: weather-brief
display_name: Weather Brief
category: weather
version: 0.1.0
source: {kind: authored}
capabilities: []
required_tools: []
required_credentials: []
reference_paths: []
example_ids: [positive-weather, negative-weather]
related_workflow_ids: []
compatible_with: []
process:
  kind: linear
  nodes:
    - step_id: summarize
      title: Summarize forecast
      description: Present the requested forecast.
      inputs: [location]
      outputs: [summary]
      tools: []
      success_criteria: [summary is clear]
      edges: []
"""
    matcher_cases = '{"schema_version":1,"cases":[{"id":"positive-weather","request":"Give me a weather brief","expect_selected":true},{"id":"negative-weather","request":"Tell me a joke","expect_selected":false}]}'
    assert service.start_session("Improve weather-brief")['ok']
    assert service.propose_edit("skills/weather-brief/SKILL.md", skill, "create skill")['ok']
    assert service.propose_edit("skills/weather-brief/mortimer.yaml", manifest, "describe process")['ok']
    assert service.propose_edit(
        "tests/fixtures/skills_authoring/weather-brief/matcher-cases.json",
        matcher_cases, "add positive and negative trigger examples",
    )['ok']
    return service.validate()


class Runtime:
    def __init__(self):
        self.args = None

    def start(self, *args):
        self.args = args
        return SimpleNamespace(
            id="session-1",
            status=lambda: {
                "branch": "mortimer/skill-authoring-weather-brief/20260926-draft",
                "task": "task-1", "ref": "a" * 40,
            },
        )


def test_creator_binds_slug_policy_to_existing_sandbox_runtime():
    runtime = Runtime()
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    started = service.start_session("Draft a weather briefing skill")
    assert started["ok"] is True
    repository, kind, base, token, profile, allowed, goal, run_id = runtime.args
    assert (repository, kind, base, token, profile, goal) == (
        "owner/repo", "skill-authoring-weather-brief", "main", "host-token",
        "mortimer", "Draft a weather briefing skill",
    )
    assert allowed("skills/weather-brief/SKILL.md")
    assert allowed("tests/fixtures/skills_authoring/weather-brief/cases.json")
    assert not allowed("skills/other-skill/SKILL.md")
    assert not allowed("config/skills.yaml")
    assert not allowed("sandbox/runtime.py")
    assert run_id is None


def test_creator_submission_keeps_enablement_separate_from_review(tmp_path):
    runtime = Runtime()
    runtime.active = lambda *args: SimpleNamespace(directory=tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    title, body = service._submission({
        "goal": "Draft a weather skill", "proposals": [],
    })
    assert title.startswith("skill: weather-brief")
    assert "changes the package only" in body
    assert "does not change" in body
    assert "merge, release, and activation" in body


def test_creator_uses_existing_session_file_validation_and_draft_publication_flow(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "skills.yaml").write_text(
        "schema_version: 2\nenabled: []\nrevisions: {}\n", encoding="utf-8",
    )
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert service.start_session("Improve weather-brief")['ok']
    assert runtime.events[0][1:3] == ("owner/repo", "skill-authoring-weather-brief")
    assert not service.propose_edit("config/skills.yaml", "enabled: [weather-brief]", "enable skill")['ok']
    skill = "---\nname: weather-brief\ndescription: Local weather summaries.\n---\n\n# Weather brief\n\nSummarize a requested forecast.\n"
    manifest = """schema_version: 1
skill_id: weather-brief
display_name: Weather Brief
category: weather
version: 0.1.0
source: {kind: authored}
capabilities: []
required_tools: []
required_credentials: []
reference_paths: []
example_ids: [positive-weather, negative-weather]
related_workflow_ids: []
compatible_with: []
process:
  kind: linear
  nodes:
    - step_id: summarize
      title: Summarize forecast
      description: Present the requested forecast.
      inputs: [location]
      outputs: [summary]
      tools: []
      success_criteria: [summary is clear]
      edges: []
"""
    assert service.propose_edit("skills/weather-brief/SKILL.md", skill, "create skill")['ok']
    assert service.propose_edit("skills/weather-brief/mortimer.yaml", manifest, "describe process")['ok']
    matcher_cases = '{"schema_version":1,"cases":[{"id":"positive-weather","request":"Give me a weather brief","expect_selected":true},{"id":"negative-weather","request":"Tell me a joke","expect_selected":false}]}'
    assert service.propose_edit(
        "tests/fixtures/skills_authoring/weather-brief/matcher-cases.json",
        matcher_cases, "add positive and negative trigger examples",
    )['ok']
    validation = service.validate()
    assert validation['ok']
    assert validation['skill_validation']['passed']
    assert validation['skill_validation']['provider_calls'] == 0
    submitted = service.submit()
    assert submitted['ok']
    title, body = runtime.events[-1][1:]
    assert title.startswith("skill: weather-brief")
    assert "changes the package only" in body and "does not change" in body
    assert not (tmp_path / "skills/weather-brief/SKILL.md").exists()


@pytest.mark.parametrize("corrupt_receipt", [None, [], {"passed": True}, "truncated"])
def test_creator_refuses_malformed_or_incomplete_offline_receipts(tmp_path, corrupt_receipt):
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert _draft_valid_weather_skill(service)["ok"]
    receipt_path = runtime.current.directory / "skill-authoring-validation.json"
    receipt_path.write_text(json.dumps(corrupt_receipt), encoding="utf-8")

    assert "package_revision" not in service.status()
    result = service.submit()

    assert result == {
        "ok": False,
        "error": "a matching offline skill validation and sandbox receipt are required",
    }
    assert runtime.current.state["phase"] == "validated"
    assert not any(event[0] == "submit" for event in runtime.events)


@pytest.mark.parametrize(("field", "value"), [
    ("slug", "another-skill"),
    ("package_revision", "not-a-sha256"),
    ("provider_calls", 1),
    ("candidate_digest", "0" * 64),
    ("checks", [{"name": "package_schema", "passed": True, "detail": "passed"}]),
    ("checks", [{"name": "package_schema", "passed": False, "detail": "failed"}]),
])
def test_creator_refuses_receipt_with_wrong_identity_or_failed_evidence(tmp_path, field, value):
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert _draft_valid_weather_skill(service)["ok"]
    receipt_path = runtime.current.directory / "skill-authoring-validation.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert "package_revision" not in service.status()
    result = service.submit()

    assert result["ok"] is False
    assert "matching offline skill validation" in result["error"]
    assert not any(event[0] == "submit" for event in runtime.events)


def test_creator_refuses_submission_after_candidate_changes_post_validation(tmp_path):
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert _draft_valid_weather_skill(service)["ok"]
    assert service.propose_edit(
        "skills/weather-brief/SKILL.md",
        "---\nname: weather-brief\ndescription: Changed after validation.\n---\n\n# Weather\nChanged.\n",
        "change after validation",
    )["ok"]

    result = service.submit()

    assert result["ok"] is False
    assert "matching offline skill validation" in result["error"]
    assert runtime.current.state["phase"] == "editing"
    assert not any(event[0] == "submit" for event in runtime.events)


def test_creator_retries_interrupted_publication_for_same_frozen_candidate(tmp_path):
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert _draft_valid_weather_skill(service)["ok"]
    assert service.status()["package_revision"]

    # Recovery after a crash between publication intent and saved result sets
    # this phase. Retry remains safe only because the publisher is idempotent
    # and submit preflight binds the receipt to the still-frozen candidate.
    runtime.current.state["phase"] = "publication_pending"
    result = service.submit()

    assert result["ok"] is True
    assert runtime.current.state["phase"] == "published"
    assert len([event for event in runtime.events if event[0] == "submit"]) == 1


def test_failed_fresh_host_validation_invalidates_prior_receipt(tmp_path, monkeypatch):
    runtime = FakeRuntime(tmp_path)
    service = SkillAuthoringService(
        "weather-brief", repository=lambda: "owner/repo", token=lambda: "host-token",
        base_branch=lambda: "main", runtime_factory=lambda: runtime,
    )
    assert _draft_valid_weather_skill(service)["ok"]
    receipt_path = runtime.current.directory / "skill-authoring-validation.json"
    assert receipt_path.exists()

    class FailedReceipt:
        passed = False

        @staticmethod
        def as_dict():
            return {"passed": False, "candidate_digest": ""}

    monkeypatch.setattr("jarvis.skill_authoring.validate_skill_candidate", lambda *args, **kwargs: FailedReceipt())

    failed = service.validate()
    submitted = service.submit()

    assert failed["ok"] is False
    assert not receipt_path.exists()
    assert submitted["ok"] is False
    assert not any(event[0] == "submit" for event in runtime.events)


@pytest.mark.parametrize("slug", ["../other", "Weather", "two/segments"])
def test_creator_service_refuses_untrusted_slug(slug):
    with pytest.raises(ValueError, match="invalid approved skill slug"):
        SkillAuthoringService(
            slug, repository=lambda: "owner/repo", token=lambda: "host-token",
            base_branch=lambda: "main",
        )


def test_creator_service_refuses_its_own_slug_before_runtime_access():
    class MustNotStartRuntime:
        def __call__(self):
            pytest.fail("self-modification must be refused before sandbox setup")

    with pytest.raises(ValueError, match="creator cannot modify its own package"):
        SkillAuthoringService(
            "skill-creator", repository=lambda: "owner/repo", token=lambda: "host-token",
            base_branch=lambda: "main", runtime_factory=MustNotStartRuntime(),
        )
