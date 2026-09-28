"""The creator gets one package and fixture tree, never general self-edit."""
import pytest

from jarvis.selfedit.skill_policy import SkillAuthoringPolicy


def test_policy_is_scoped_to_one_skill_and_its_public_fixtures():
    policy = SkillAuthoringPolicy("weather-brief")
    assert policy.is_allowed("skills/weather-brief/SKILL.md")
    assert policy.is_allowed("skills/weather-brief/references/sources.md")
    assert policy.is_allowed("skills/weather-brief/mortimer.yaml")
    assert policy.is_allowed("tests/fixtures/skills_authoring/weather-brief/cases.json")
    assert not policy.is_allowed("skills/other-skill/SKILL.md")
    assert not policy.is_allowed("config/skills.yaml")
    assert not policy.is_allowed("tests/unit/test_agent_skills.py")
    assert not policy.is_allowed("jarvis/selfedit/skill_policy.py")
    assert not policy.is_allowed("sandbox/runtime.py")


@pytest.mark.parametrize("path", [
    "skills/weather-brief/../other/SKILL.md",
    "skills/weather-brief/.env",
    "skills/weather-brief/private.key",
    "skills/weather-brief/build.py",
    "tests/fixtures/skills_authoring/weather-brief/data.sqlite",
    "skills/weather-brief\\SKILL.md",
])
def test_policy_rejects_traversal_hidden_secret_and_executable_paths(path):
    assert not SkillAuthoringPolicy("weather-brief").is_allowed(path)


@pytest.mark.parametrize("slug", ["", "../other", "Weather", "a/b", "with.dot", "-leading"])
def test_policy_requires_a_canonical_host_approved_slug(slug):
    with pytest.raises(ValueError, match="invalid approved skill slug"):
        SkillAuthoringPolicy(slug)


def test_policy_refuses_creator_self_modification_before_sandbox_creation():
    with pytest.raises(ValueError, match="creator cannot modify its own package"):
        SkillAuthoringPolicy("skill-creator")
