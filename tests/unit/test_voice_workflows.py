"""MORTIMER_VOICE_WORKFLOWS_PLAN.md §7 T1 — detectors and matcher pinned
against the logged corpus (tests/fixtures/voice_failures.yaml)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from jarvis import voice_workflows as vw
from jarvis import workflows as wfmod

REPO = Path(__file__).resolve().parents[2]
FIXTURE = yaml.safe_load((REPO / "tests" / "fixtures" / "voice_failures.yaml").read_text(encoding="utf-8"))
WF_DIR = REPO / "config" / "workflows"


@pytest.fixture(scope="module")
def voice_wfs():
    return vw.voice_workflows(wfmod.load_workflows(WF_DIR))


class TestRegexesArePinned:
    def test_code_regexes_equal_fixture(self):
        assert vw.REFUSE_RE.pattern == FIXTURE["guard_regex"]["refuse"]
        assert vw.HANDOFF_RE.pattern == FIXTURE["guard_regex"]["handoff"]
        assert vw.ALLOWED_RE.pattern == FIXTURE["guard_regex"]["allowed"]
        assert vw.LIMITATION_RE.pattern == FIXTURE["limitation_regex"]

    def test_yaml_user_triggers_equal_fixture(self, voice_wfs):
        by_name = {wf.name: wf for wf in voice_wfs}
        for name, pin in FIXTURE["user_triggers"].items():
            assert by_name[name].priority == pin["priority"], name
            assert by_name[name].triggers["user"] == [pin["pattern"]], name


class TestReplyGuardDetector:
    @pytest.mark.parametrize("case", FIXTURE["failure_cases"], ids=lambda c: str(c["id"]))
    def test_failure_cases(self, case):
        fired = bool(vw.reply_violations(case["reply"]))
        assert fired == (case["guard"] == "fire")

    @pytest.mark.parametrize("case", FIXTURE["accepted_false_positives"], ids=lambda c: str(c["id"]))
    def test_accepted_false_positives_still_fire(self, case):
        # Pinned so the accepted false-positive count cannot grow silently.
        assert bool(vw.reply_violations(case["reply"])) == (case["guard"] == "fire")

    @pytest.mark.parametrize("case", FIXTURE["negative_sample"], ids=lambda c: str(c["id"]))
    def test_negative_sample_does_not_fire(self, case):
        assert case["guard"] == "no_fire"
        assert vw.reply_violations(case["reply"]) == []

    def test_sanctioned_missing_tool_sentence_is_allowed(self):
        assert vw.sentence_violation(
            "That isn't something I have a tool for yet. Want me to have it added?") is None

    def test_refusal_is_checked_before_handoff(self):
        assert vw.sentence_violation("I can't do that, you'll need to run it.") == "refusal"

    def test_destructive_advice_is_a_handoff(self):
        # Turn 737 (2026-08-18): the unsafe-advice case D10 names.
        assert vw.sentence_violation("Try this: run `git reset --hard HEAD`.") == "handoff"


class TestResultKinds:
    @pytest.mark.parametrize("case", FIXTURE["result_cases"], ids=lambda c: c["run_id"])
    def test_result_cases(self, case):
        assert vw.result_kinds(case["result"]) == case["kinds"]

    def test_missing_tool_marker(self):
        assert vw.result_kinds("MISSING-TOOL: an HTTP fetch tool") == ["missing_tool", "limitation"]

    def test_missing_tool_marker_old_spelling(self):
        assert vw.result_kinds("MISSING TOOL: an HTTP fetch tool") == ["missing_tool", "limitation"]

    def test_missing_tool_marker_matches_delegate(self):
        # One marker for both readers: delegate.py (#86 T1.2) and the result hook.
        from jarvis.agents.delegate import MISSING_TOOL_MARKER
        assert vw.MISSING_TOOL_MARKER == MISSING_TOOL_MARKER
        assert vw.MISSING_TOOL_RE.search(MISSING_TOOL_MARKER)

    def test_non_string_result(self):
        assert vw.result_kinds(None) == []


class TestExplicitCommandAsk:
    """D-L5 (Larry, 2026-09-25): an explicit ask for a command lets
    Mortimer show one. Pinned to Larry's own words from the log."""

    @pytest.mark.parametrize("text", [
        "Give me the command to do that.",                                  # 764
        "So that's one... Give me the commands again.",                     # 831
        "They're closer creating an error for the commands. Give me the commands without quotes.",  # 833
        "What's the exact command?",
        "Show me the git command.",
        "Just give me the curl command.",
        "I'll run it myself.",
    ])
    def test_asks(self, text):
        assert vw.is_explicit_command_ask(text) is True

    @pytest.mark.parametrize("text", [
        "Are you unable to run that command yourself?",                     # 2865
        "So you don't have access to the terminal?",                        # 828
        "No. You do that for me.",                                          # 3478
        "Don't give me commands, do it yourself.",
        "Do not give me the command, just fix it.",
        "I don't want to run the command.",
        "Run the command yourself.",
        "I ran the command.",
        "Can you give me a rundown of the games?",
        "",
        None,
    ])
    def test_not_asks(self, text):
        assert vw.is_explicit_command_ask(text) is False

    def test_no_logged_failure_is_an_ask(self):
        # Every one of the 93 logged failures is a turn where Larry did NOT
        # want a command; none may open the gate.
        assert [c["id"] for c in FIXTURE["failure_cases"]
                if vw.is_explicit_command_ask(c["user"])] == []


class TestVoiceMatcher:
    @pytest.mark.parametrize("case", FIXTURE["failure_cases"], ids=lambda c: str(c["id"]))
    def test_user_hook_matches_pinned_workflow(self, case, voice_wfs):
        wf = vw.match_voice_workflow(user_text=case["user"], workflows=voice_wfs)
        assert (wf.name if wf else None) == case["user_trigger"]

    @pytest.mark.parametrize("kinds,expected", [
        (["failed"], "voice-explain-failure"),
        (["needs_input"], "voice-do-it-dont-hand-off"),
        (["missing_tool"], "voice-check-before-cant"),
        (["limitation"], "voice-check-before-cant"),
        (["needs_input", "limitation"], "voice-do-it-dont-hand-off"),
        (["failed", "needs_input"], "voice-do-it-dont-hand-off"),
        ([], None),
    ])
    def test_result_hook_priority(self, kinds, expected, voice_wfs):
        wf = vw.match_voice_workflow(result_kinds=kinds, workflows=voice_wfs)
        assert (wf.name if wf else None) == expected

    @pytest.mark.parametrize("kind,expected", [
        ("refusal", "voice-check-before-cant"),
        ("handoff", "voice-do-it-dont-hand-off"),
    ])
    def test_reply_hook(self, kind, expected, voice_wfs):
        assert vw.match_voice_workflow(reply_kinds=[kind], workflows=voice_wfs).name == expected

    def test_exactly_one_hook_argument(self, voice_wfs):
        with pytest.raises(ValueError):
            vw.match_voice_workflow(user_text="x", result_kinds=["failed"], workflows=voice_wfs)
        with pytest.raises(ValueError):
            vw.match_voice_workflow(workflows=voice_wfs)

    def test_voice_workflows_never_reach_specialists(self, voice_wfs):
        for agent in ("scheduler", "librarian", "analyst", "systems", "developer", "app_builder"):
            for case in FIXTURE["failure_cases"]:
                assert wfmod.match_workflow(agent, case["user"], workflows=voice_wfs) is None

    def test_bad_regex_is_skipped_not_raised(self):
        bad = wfmod.Workflow(name="x", when="x", agents=["supervisor"],
                             triggers={"user": ["(unclosed"]}, source="bad.yaml")
        assert vw.match_voice_workflow(user_text="anything", workflows=[bad]) is None


class TestGuidanceAndGapLog:
    def test_guidance_is_a_system_note(self, voice_wfs):
        text = vw.render_guidance(voice_wfs[0])
        assert text.startswith("[system] Larry's standing instruction")

    def test_correction_note_names_the_sentence_and_appends_workflow(self, voice_wfs):
        wf = vw.match_voice_workflow(reply_kinds=["handoff"], workflows=voice_wfs)
        note = vw.correction_note("handoff", "Run that command locally.", wf)
        assert note.startswith("[system] Your last reply was cut off")
        assert "\"Run that command locally.\"" in note
        assert "voice-do-it-dont-hand-off" in note

    def test_gap_log_writes_one_json_line(self, tmp_path):
        path = tmp_path / "gaps.jsonl"
        vw.log_capability_gap(source="result", kind="limitation", text="I have no HTTP tool",
                              session_id="s1", agent="developer", path=path)
        record = json.loads(path.read_text().strip())
        assert record["kind"] == "limitation" and record["agent"] == "developer"

    def test_gap_log_redacts_sensitive(self, tmp_path):
        path = tmp_path / "gaps.jsonl"
        vw.log_capability_gap(source="reply_guard", kind="refusal", text="secret",
                              user_text="secret", sensitive=True, path=path)
        record = json.loads(path.read_text().strip())
        assert record["text"] == "[sensitive]" and record["user_text"] == "[sensitive]"

    def test_gap_log_never_raises(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        vw.log_capability_gap(source="result", kind="limitation", text="t",
                              path=blocker / "sub" / "gaps.jsonl")


class TestResultWrapper:
    def _run(self, handler, **kw):
        return asyncio.run(vw.wrap_delegate_handler(handler, **kw)({"agent_name": "developer", "task": "t"}))

    def test_clean_result_is_unchanged(self, tmp_path):
        async def h(_):
            return "Current time in America/New_York: 9:03 PM."
        assert self._run(h, gap_log_path=tmp_path / "g.jsonl") == "Current time in America/New_York: 9:03 PM."

    def test_needs_input_stamps_gate_and_appends_guidance(self, tmp_path, monkeypatch, voice_wfs):
        monkeypatch.setattr(vw, "load_workflows", lambda: voice_wfs)
        gate: dict = {}

        async def h(_):
            return "NEEDS-INPUT: I have no network tool. Run: curl -s https://example"
        out = self._run(h, gate=gate, gap_log_path=tmp_path / "g.jsonl")
        assert "needs_input_at" in gate
        assert out.startswith("NEEDS-INPUT:")
        assert "voice-do-it-dont-hand-off" in out
        assert (tmp_path / "g.jsonl").exists()

    def test_disabled_still_stamps_gate_but_adds_nothing(self, tmp_path):
        gate: dict = {}

        async def h(_):
            return "NEEDS-INPUT: sign in on GitHub"
        out = self._run(h, gate=gate, enabled=lambda: False, gap_log_path=tmp_path / "g.jsonl")
        assert out == "NEEDS-INPUT: sign in on GitHub" and "needs_input_at" in gate

    def test_handler_exception_propagates_unchanged(self):
        async def h(_):
            raise RuntimeError("boom")
        with pytest.raises(RuntimeError):
            self._run(h)
