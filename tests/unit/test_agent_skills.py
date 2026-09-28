"""Unit tests for jarvis/agent_skills.py (K3).

Parsing, validation and matching are pure when the directory and the
config path are supplied — that is the test seam.
"""

from __future__ import annotations

import pytest

from jarvis.agent_skills import (
    DESCRIPTION_MAX_CHARS,
    NAME_MAX_CHARS,
    Skill,
    discover,
    enabled_names,
    format_inventory,
    load_skills,
    match_skill,
    parse_skill,
    skill_from_procedure,
    skills_enabled,
    validate_frontmatter,
    write_skill,
)

FRONT = """---
name: {name}
description: {desc}
---

# Body

Some instructions.
"""


def make_skill(root, name="a-skill", desc="Do the thing when asked to do the thing.",
               body_extra="", scripts=False):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        FRONT.format(name=name, desc=desc) + body_extra, encoding="utf-8")
    if scripts:
        (folder / "scripts").mkdir()
        (folder / "scripts" / "run.sh").write_text("echo hi", encoding="utf-8")
    return folder / "SKILL.md"


def config_with(root, names):
    path = root / "skills.yaml"
    body = "enabled:\n" + "".join(f"  - {n}\n" for n in names) if names else "enabled: []\n"
    path.write_text(body, encoding="utf-8")
    return path


def sk(name="a-skill", desc="do the thing", body="B", **kw) -> Skill:
    return Skill(name=name, description=desc, path=kw.pop("path", None) or __import__(
        "pathlib").Path("x"), _body=body, **kw)


class TestValidation:
    """The standard's own limits, enforced so an imported skill fails
    loudly at load rather than silently misbehaving in a prompt."""

    def test_valid_frontmatter_has_no_problems(self):
        assert validate_frontmatter({"name": "a-b", "description": "x"}) == []

    def test_name_and_description_are_required(self):
        problems = validate_frontmatter({})
        assert any("name" in p for p in problems)
        assert any("description" in p for p in problems)

    def test_name_charset_is_enforced(self):
        assert validate_frontmatter({"name": "Bad Name", "description": "x"})
        assert validate_frontmatter({"name": "trailing-", "description": "x"})
        assert validate_frontmatter({"name": "under_score", "description": "x"})

    def test_reserved_vendor_words_are_refused(self):
        """The standard reserves these; a skill named after a vendor
        would also be a lie about its provenance."""
        for name in ("claude-helper", "anthropic-tools"):
            assert validate_frontmatter({"name": name, "description": "x"})

    def test_length_limits(self):
        assert validate_frontmatter(
            {"name": "a" * (NAME_MAX_CHARS + 1), "description": "x"})
        assert validate_frontmatter(
            {"name": "a", "description": "x" * (DESCRIPTION_MAX_CHARS + 1)})

    def test_all_problems_are_returned_not_just_the_first(self):
        """Someone fixing an imported skill should see the whole list."""
        problems = validate_frontmatter({"name": "Bad Name", "description": ""})
        assert len(problems) >= 2

    def test_non_mapping_frontmatter(self):
        assert validate_frontmatter(["not", "a", "mapping"])


class TestParsing:
    def test_parses_a_well_formed_skill(self, tmp_path):
        path = make_skill(tmp_path)
        skill, problems = parse_skill(path)
        assert problems == []
        assert skill.name == "a-skill"
        assert "Some instructions." in skill.body()

    def test_missing_frontmatter_is_a_problem_not_a_crash(self, tmp_path):
        p = tmp_path / "x" / "SKILL.md"
        p.parent.mkdir()
        p.write_text("# just markdown\n", encoding="utf-8")
        skill, problems = parse_skill(p)
        assert skill is None
        assert any("frontmatter" in prob for prob in problems)

    @pytest.mark.parametrize("newline", ["\n", "\r\n"])
    def test_body_keeps_markdown_rules_and_diff_headers(self, tmp_path, newline):
        path = tmp_path / "rule-skill" / "SKILL.md"
        path.parent.mkdir()
        body = (
            "# Instructions" + newline + newline
            + "Keep this section." + newline + newline
            + "---" + newline + "This section follows a Markdown rule." + newline + newline
            + "--- a/example.md" + newline + "This section follows a diff header." + newline
        )
        path.write_text(
            "---" + newline + "name: rule-skill" + newline
            + "description: Demonstrate complete body parsing." + newline
            + "---" + newline + body,
            encoding="utf-8",
            newline="",
        )
        skill, problems = parse_skill(path)
        assert skill is not None, problems
        assert skill.body() == body.strip()

    @pytest.mark.parametrize("text", ["", "---", " ---\nname: x\n---\nbody\n"])
    def test_frontmatter_requires_exact_open_and_close_delimiter_lines(self, text):
        from jarvis.agent_skills import _split_frontmatter

        front, body = _split_frontmatter(text)
        assert front == ""
        assert body == text

    def test_body_is_not_silently_truncated_after_later_separator(self, tmp_path):
        path = tmp_path / "long-skill" / "SKILL.md"
        path.parent.mkdir()
        body = "# Start\n\n" + "x" * 25_000 + "\n\n---\n\n# Required ending\n"
        path.write_text(
            "---\nname: long-skill\ndescription: Complete body\n---\n" + body,
            encoding="utf-8",
        )
        skill, _ = parse_skill(path)
        assert skill is not None
        assert skill.body() == body.strip()

    def test_broken_yaml_is_a_problem_not_a_crash(self, tmp_path):
        p = tmp_path / "x" / "SKILL.md"
        p.parent.mkdir()
        p.write_text("---\nname: [unclosed\n---\nbody\n", encoding="utf-8")
        skill, problems = parse_skill(p)
        assert skill is None
        assert problems

    def test_scripts_are_detected(self, tmp_path):
        path = make_skill(tmp_path, scripts=True)
        skill, _ = parse_skill(path)
        assert skill.has_scripts is True

    def test_oversized_body_warns_but_still_loads(self, tmp_path):
        path = make_skill(tmp_path, body_extra="x" * 25_000)
        skill, problems = parse_skill(path)
        assert skill is not None
        assert any("progressive disclosure" in p for p in problems)


class TestRegistrationGate:
    """Larry, 2026-08-18: 'skills should only be added one at a time so
    the risk can be reviewed individually.' Presence on disk must not be
    enough — that is the property these tests pin."""

    def test_a_skill_on_disk_is_inert_until_registered(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        make_skill(tmp_path / "skills")
        cfg = config_with(tmp_path, [])
        assert discover(tmp_path / "skills")          # it IS on disk
        assert load_skills(tmp_path / "skills", cfg) == []   # and does nothing

    def test_registering_by_name_enables_exactly_that_one(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        root = tmp_path / "skills"
        make_skill(root, name="wanted")
        make_skill(root, name="unwanted")
        cfg = config_with(tmp_path, ["wanted"])
        assert [s.name for s in load_skills(root, cfg)] == ["wanted"]

    def test_a_missing_config_enables_nothing(self, tmp_path, monkeypatch):
        """The safe direction: no config means no skills, never all."""
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        root = tmp_path / "skills"
        make_skill(root)
        assert load_skills(root, tmp_path / "absent.yaml") == []

    def test_an_unreadable_config_enables_nothing_without_logging_path_or_text(
        self, tmp_path, caplog
    ):
        bad = tmp_path / "SKILLS_PATH_CANARY" / "skills.yaml"
        bad.parent.mkdir()
        bad.write_text("CONFIG_CONTENT_CANARY: {[not yaml", encoding="utf-8")
        assert enabled_names(bad) == []
        assert "skills_config_unreadable error_type=" in caplog.text
        assert "SKILLS_PATH_CANARY" not in caplog.text
        assert "CONFIG_CONTENT_CANARY" not in caplog.text

    def test_one_invalid_skill_does_not_disable_the_rest(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        root = tmp_path / "skills"
        make_skill(root, name="good")
        (root / "broken").mkdir()
        (root / "broken" / "SKILL.md").write_text("no frontmatter", encoding="utf-8")
        cfg = config_with(tmp_path, ["good", "broken"])
        assert [s.name for s in load_skills(root, cfg)] == ["good"]

    def test_invalid_skill_log_omits_path_and_frontmatter(self, tmp_path, monkeypatch, caplog):
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        root = tmp_path / "SKILLS_PATH_CANARY"
        (root / "broken").mkdir(parents=True)
        (root / "broken" / "SKILL.md").write_text(
            "---\nname: SKILL_CONTENT_CANARY\ndescription: X\n---\n"
        )
        cfg = config_with(tmp_path, ["broken"])
        assert load_skills(root, cfg) == []
        assert "skill_invalid problem_count=1" in caplog.text
        assert "SKILLS_PATH_CANARY" not in caplog.text
        assert "SKILL_CONTENT_CANARY" not in caplog.text

    def test_kill_switch(self, tmp_path, monkeypatch):
        root = tmp_path / "skills"
        make_skill(root)
        cfg = config_with(tmp_path, ["a-skill"])
        monkeypatch.setenv("JARVIS_AGENT_SKILLS_ENABLED", "false")
        assert skills_enabled() is False
        assert load_skills(root, cfg) == []

    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        assert skills_enabled() is True

    def test_digest_pinned_v2_loader_accepts_exact_revision_and_refuses_drift(
        self, tmp_path, monkeypatch,
    ):
        from jarvis.skill_catalog import inspect_package

        root = tmp_path / "skills"
        skill_path = make_skill(root, name="pinned-skill")
        revision = inspect_package(skill_path.parent).revision
        cfg = tmp_path / "skills.yaml"
        cfg.write_text(
            "schema_version: 2\n"
            "enabled: [pinned-skill]\n"
            f"revisions: {{pinned-skill: {revision}}}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)

        assert [skill.name for skill in load_skills(root, cfg)] == ["pinned-skill"]
        skill_path.write_text(skill_path.read_text() + "Drifted instructions.\n", encoding="utf-8")
        assert load_skills(root, cfg) == []

    @pytest.mark.parametrize("registry", [
        "schema_version: 2\nenabled: [pinned-skill]\nrevisions: {}\n",
        "schema_version: 2\nenabled: [pinned-skill]\nrevisions: {pinned-skill: bad}\n",
        "schema_version: 2\nenabled: [pinned-skill, pinned-skill]\nrevisions: {}\n",
        "schema_version: 3\nenabled: [pinned-skill]\nrevisions: {}\n",
    ])
    def test_digest_registry_rejects_missing_duplicate_or_malformed_pins(
        self, tmp_path, monkeypatch, registry,
    ):
        root = tmp_path / "skills"
        make_skill(root, name="pinned-skill")
        cfg = tmp_path / "skills.yaml"
        cfg.write_text(registry, encoding="utf-8")
        monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
        assert load_skills(root, cfg) == []

    def test_workspace_mode_refuses_legacy_registry_but_legacy_mode_still_loads(
        self, tmp_path, monkeypatch,
    ):
        root = tmp_path / "skills"
        make_skill(root, name="pinned-skill")
        cfg = config_with(tmp_path, ["pinned-skill"])
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)
        assert [skill.name for skill in load_skills(root, cfg)] == ["pinned-skill"]
        monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
        assert load_skills(root, cfg) == []

    def test_repository_v2_pins_match_every_enabled_package(self, monkeypatch):
        monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        loaded = load_skills()
        assert {skill.name for skill in loaded} == {
            "current-weather-with-fahrenheit",
            "git-history-and-status-review",
            "layered-geolocation",
            "mcp-server-authoring",
            "technical-plan-document",
        }

    def test_inventory_reports_digest_pin_state_and_enforcement_mode(self, monkeypatch):
        monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)
        text = format_inventory()
        assert "registry: schema v2; digest enforcement OFF (legacy loader)" in text
        assert text.count("digest pin: matches") == 5

    def test_inventory_surfaces_a_package_pin_mismatch(self, tmp_path):
        from jarvis.skill_catalog import inspect_package

        root = tmp_path / "skills"
        skill_path = make_skill(root, name="pinned-skill")
        revision = inspect_package(skill_path.parent).revision
        skill_path.write_text(skill_path.read_text() + "changed\n", encoding="utf-8")
        cfg = tmp_path / "skills.yaml"
        cfg.write_text(
            "schema_version: 2\nenabled: [pinned-skill]\n"
            f"revisions: {{pinned-skill: {revision}}}\n",
            encoding="utf-8",
        )
        assert "digest pin: MISMATCH" in format_inventory(root, cfg)

    def test_inventory_does_not_call_unregistered_v2_candidate_a_pin_mismatch(self, tmp_path):
        root = tmp_path / "skills"
        make_skill(root, name="draft-skill")
        cfg = tmp_path / "skills.yaml"
        cfg.write_text("schema_version: 2\nenabled: []\nrevisions: {}\n", encoding="utf-8")
        text = format_inventory(root, cfg)
        assert "[inert   ] draft-skill" in text
        assert "digest pin: not configured (inert)" in text
        assert "digest pin: MISMATCH" not in text


class TestMatching:
    def test_matches_on_shared_language(self):
        s = sk(desc="retrieve current weather with fahrenheit temperatures")
        assert match_skill("what is the current weather in fahrenheit", [s]) is s

    def test_unrelated_task_does_not_match(self):
        s = sk(desc="retrieve current weather with fahrenheit temperatures")
        assert match_skill("rename a git branch on the remote", [s]) is None

    def test_strongest_match_wins(self):
        """MAX_INJECTED is 1: two competing how-tos in one prompt is how
        a small model stalls."""
        weak = sk(name="weak", desc="weather")
        strong = sk(name="strong", desc="current weather fahrenheit humidity wind")
        got = match_skill("current weather fahrenheit humidity wind", [weak, strong])
        assert got.name == "strong"

    def test_one_coincidental_word_is_not_a_match(self):
        """Measured 2026-08-18: "what's the plan for today" tokenizes to
        {plan, today} and scored 0.500 against technical-plan-document on
        the word "plan" alone — above the 0.30 threshold. _overlap_score
        divides by the SMALLER set, so a short task is cheap to satisfy.
        MIN_SHARED_TOKENS targets that directly."""
        s = sk(name="technical-plan-document",
               desc="write an implementation plan or technical specification "
                    "document with sections and acceptance criteria")
        assert match_skill("what is the plan for today", [s]) is None
        # …while the real request, sharing several tokens, still matches.
        assert match_skill(
            "write an implementation plan for the new feature", [s]) is s

    def test_min_shared_tokens_agrees_with_consolidate(self):
        """One idea applied twice, not two ideas that can drift apart."""
        from jarvis.agent_skills import MIN_SHARED_TOKENS
        from jarvis.consolidate import MIN_SHARED_TOKENS as CONSOLIDATE_MIN

        assert MIN_SHARED_TOKENS == CONSOLIDATE_MIN == 2

    def test_empty_task_matches_nothing(self):
        assert match_skill("", [sk()]) is None

    def test_no_skills_is_not_an_error(self):
        assert match_skill("anything", []) is None

    def test_matching_never_reads_the_body(self, tmp_path):
        """Progressive disclosure is the point: tier one is name +
        description only. If matching touched the body, importing a
        hundred skills would cost a hundred file reads per delegation."""
        path = make_skill(tmp_path / "skills", desc="totally unrelated topic",
                          body_extra="\ngit commit push branch repository status\n")
        skill, _ = parse_skill(path)
        skill._body = None  # force a read if anything asks for it
        assert match_skill("git commit push branch repository status", [skill]) is None


class TestPromptRendering:
    def test_reads_as_reference_not_as_an_order(self):
        """A skill says how a thing is done; a workflow says it must be.
        Losing that distinction makes every imported skill binding."""
        text = sk().as_prompt()
        assert "Reference" in text
        assert "ignore it if it does not" in text

    def test_bundled_scripts_are_declared_unavailable(self):
        text = sk(has_scripts=True).as_prompt()
        assert "does not run" in text
        assert "unavailable" in text


class TestNoExecutionPath:
    """The security property, pinned. Importing a community skill and
    running its code is arbitrary code execution from the internet on
    Larry's machine; this module contributes text and nothing else."""

    def test_module_imports_nothing_that_executes(self):
        import jarvis.agent_skills as mod

        source = open(mod.__file__, encoding="utf-8").read()
        for forbidden in ("subprocess", "os.system", "eval(", "exec(",
                          "importlib", "__import__("):
            assert forbidden not in source, f"agent_skills grew {forbidden}"

    def test_skill_has_no_run_method(self):
        for forbidden in ("run", "execute", "invoke", "call"):
            assert not hasattr(sk(), forbidden), f"Skill grew a .{forbidden}()"

    def test_a_bundled_script_is_never_read_or_run(self, tmp_path, monkeypatch, caplog):
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        root = tmp_path / "skills"
        make_skill(root, scripts=True)
        cfg = config_with(tmp_path, ["a-skill"])
        loaded = load_skills(root, cfg)
        assert loaded and loaded[0].has_scripts is True
        assert "skill_bundles_scripts" in caplog.text
        assert "a-skill" not in caplog.text
        assert str(root) not in caplog.text
        # The prompt carries the warning; the script content never appears.
        assert "echo hi" not in loaded[0].as_prompt()


class TestAuthoring:
    def test_write_and_reload_round_trips(self, tmp_path):
        write_skill("my-skill", "does a thing", "# Body\n\ntext", directory=tmp_path)
        skill, problems = parse_skill(tmp_path / "my-skill" / "SKILL.md")
        assert problems == []
        assert skill.name == "my-skill"
        assert "text" in skill.body()

    def test_refuses_to_overwrite(self, tmp_path):
        write_skill("my-skill", "d", "b", directory=tmp_path)
        with pytest.raises(FileExistsError):
            write_skill("my-skill", "d", "b", directory=tmp_path)

    def test_refuses_an_invalid_name(self, tmp_path):
        with pytest.raises(ValueError):
            write_skill("Bad Name", "d", "b", directory=tmp_path)

    def test_writing_a_skill_does_not_enable_it(self, tmp_path, monkeypatch):
        """Writing the file and trusting it are two decisions, and the
        second one is Larry's."""
        monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)
        write_skill("my-skill", "does a thing", "body", directory=tmp_path / "skills")
        cfg = config_with(tmp_path, [])
        assert load_skills(tmp_path / "skills", cfg) == []


class TestPromotionFromProcedure:
    ROW = {
        "id": 16,
        "agent": "analyst",
        "label": "Current weather data retrieval with formatting",
        "description": "Query weather API and format temperatures in Fahrenheit.",
        "status": "active",
        "success_count": 5,
        "failure_count": 0,
    }

    def test_promotion_produces_a_valid_skill(self, tmp_path):
        path = skill_from_procedure(self.ROW, directory=tmp_path)
        skill, problems = parse_skill(path)
        assert problems == []
        assert skill.name == "current-weather-data-retrieval-with-formatting"

    def test_provenance_is_recorded(self, tmp_path):
        """A skill carries no counters, so where it came from and what
        evidence it had at promotion is the only trace left."""
        path = skill_from_procedure(self.ROW, directory=tmp_path)
        text = path.read_text(encoding="utf-8")
        assert "procedure:16" in text
        assert "5 success" in text

    def test_the_procedure_row_is_untouched(self, tmp_path):
        """Promotion is a copy, not a move: the procedure keeps its
        counters and keeps being matched."""
        row = dict(self.ROW)
        skill_from_procedure(row, directory=tmp_path)
        assert row == self.ROW

    def test_an_overlong_description_is_truncated_not_rejected(self, tmp_path):
        row = dict(self.ROW, description="x" * (DESCRIPTION_MAX_CHARS + 500))
        path = skill_from_procedure(row, directory=tmp_path)
        skill, problems = parse_skill(path)
        assert problems == []
        assert len(skill.description) <= DESCRIPTION_MAX_CHARS


class TestExplain:
    """Part A — the enable gate (D2a). Without it, 'does this match the
    right tasks' is only answerable by restarting the bot."""

    def test_shows_the_score_and_the_winner(self, tmp_path):
        from jarvis.agent_skills import explain

        root = tmp_path / "skills"
        make_skill(root, name="weather-skill",
                   desc="current weather fahrenheit temperature conditions")
        cfg = config_with(tmp_path, ["weather-skill"])
        text = explain("what is the current weather in fahrenheit", root, cfg)
        assert "weather-skill" in text
        assert "PASS" in text
        assert "Would inject: weather-skill" in text

    def test_an_inert_skill_is_never_reported_as_injected(self, tmp_path):
        """The most misleading possible output would be showing a match
        for a skill that cannot fire."""
        from jarvis.agent_skills import explain

        root = tmp_path / "skills"
        make_skill(root, name="weather-skill",
                   desc="current weather fahrenheit temperature conditions")
        cfg = config_with(tmp_path, [])
        text = explain("what is the current weather in fahrenheit", root, cfg)
        assert "Would inject" not in text
        assert "are inert" in text

    def test_reports_competing_skills_above_threshold(self, tmp_path):
        """MAX_INJECTED is 1, so a second skill above threshold is a
        silent loser. Overlap has to be visible to be fixed (B5)."""
        from jarvis.agent_skills import explain

        root = tmp_path / "skills"
        make_skill(root, name="skill-one",
                   desc="current weather fahrenheit temperature conditions wind")
        make_skill(root, name="skill-two",
                   desc="current weather fahrenheit temperature conditions")
        cfg = config_with(tmp_path, ["skill-one", "skill-two"])
        text = explain("current weather fahrenheit temperature conditions", root, cfg)
        assert "NOT injected" in text
        assert "merge or sharpen" in text

    def test_empty_task_is_not_an_error(self, tmp_path):
        from jarvis.agent_skills import explain

        root = tmp_path / "skills"
        make_skill(root)
        text = explain("", root, config_with(tmp_path, ["a-skill"]))
        assert "nothing can match" in text

    def test_needs_no_database(self, tmp_path, monkeypatch):
        """Skills are files, not rows — this must work on a fresh
        checkout where data/jarvis.db does not exist."""
        from jarvis.agent_skills import explain

        monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "nonexistent.db"))
        root = tmp_path / "skills"
        make_skill(root)
        assert "threshold" in explain("do the thing", root,
                                      config_with(tmp_path, []))


class TestShippedSkills:
    """The four skills promoted from active procedures on 2026-08-18."""

    def test_every_shipped_skill_is_valid(self):
        found = discover()
        assert found, "skills/ should contain the promoted skills"
        for path, skill, problems in found:
            assert skill is not None, f"{path}: {problems}"
            assert not problems, f"{path}: {problems}"

    def test_none_of_them_bundle_scripts(self):
        for _, skill, _ in discover():
            assert skill.has_scripts is False

    def test_shipped_skills_start_inert(self):
        """Every name in config/skills.yaml must correspond to a real
        skill — and the promoted ones ship unregistered, awaiting the
        individual review Larry asked for."""
        on_disk = {s.name for _, s, _ in discover() if s}
        for name in enabled_names():
            assert name in on_disk, f"{name} is enabled but not on disk"
