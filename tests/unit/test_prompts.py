"""Unit tests for jarvis/prompts.py."""

import pytest

from jarvis.prompts import (
    SUBAGENT_PROMPTS,
    SUPERVISOR_PROMPT,
    VOICE_ADDENDUM,
    render_agent_catalog,
    render_voice_catalog,
)


def test_supervisor_prompt_formats_all_placeholders():
    rendered = SUPERVISOR_PROMPT.format(
        jarvis_name="Jarvis",
        user_name="Boss",
        timezone="America/New_York",
        agent_catalog="- scheduler (Scheduler): time stuff",
        voice_catalog="- rachel: Rachel (calm)",
        memory_context="- user.name: Larry",
    )
    assert "Jarvis" in rendered
    assert "America/New_York" in rendered
    assert "- scheduler (Scheduler): time stuff" in rendered
    assert "- rachel: Rachel (calm)" in rendered
    assert "- user.name: Larry" in rendered
    assert "{" not in rendered  # no unformatted placeholders remain


def test_supervisor_prompt_memory_section_present():
    assert "{memory_context}" in SUPERVISOR_PROMPT
    assert "Long-term memory" in SUPERVISOR_PROMPT


def test_supervisor_prompt_locked_rules_present():
    for fragment in ("delegate_task", "set_voice", "acknowledgment", "40 words"):
        assert fragment in SUPERVISOR_PROMPT


def test_supervisor_prompt_identity_and_no_hedging_rules():
    # Delegating IS doing: the specialists' abilities are Mortimer's own.
    assert "their abilities are your abilities" in SUPERVISOR_PROMPT
    assert "IS you doing the task" in SUPERVISOR_PROMPT
    # Rule 10: no capability commentary or hedging, ever.
    assert "Never comment on what you can or cannot do" in SUPERVISOR_PROMPT


def test_voice_addendum_is_plain_prose_rule():
    assert "plain prose" in VOICE_ADDENDUM
    assert "no markdown" in VOICE_ADDENDUM


def test_subagent_prompts_roster_and_contracts():
    assert set(SUBAGENT_PROMPTS) == {"scheduler", "librarian", "analyst", "systems", "developer"}
    for name, prompt in SUBAGENT_PROMPTS.items():
        assert "FAILED:" in prompt, name
    assert "{timezone}" not in SUBAGENT_PROMPTS["scheduler"].format(
        timezone="America/New_York"
    )


def test_render_agent_catalog():
    agents = [{"name": "scheduler", "display_name": "Scheduler",
               "description": "Time and reminders."}]
    assert render_agent_catalog(agents) == "- scheduler (Scheduler): Time and reminders."


def test_render_voice_catalog():
    voices = [{"id": "rachel", "label": "Rachel (calm)"}]
    assert render_voice_catalog(voices) == "- rachel: Rachel (calm)"


# --- Golden Rules (Larry 2026-08-18) -------------------------------------


def test_golden_rules_come_first_in_the_supervisor_prompt():
    """Primacy is the point: they sit ahead of the specialists list and the
    numbered rules so they aren't buried in a long prompt on a small
    dispatcher model."""
    from jarvis.prompts import GOLDEN_RULES

    assert SUPERVISOR_PROMPT.startswith(GOLDEN_RULES)
    assert SUPERVISOR_PROMPT.index("Golden Rules") < SUPERVISOR_PROMPT.index("Rules:")


def test_golden_rule_1_authorizes_saying_i_dont_know():
    """The 2026-08-18 fabrication happened because no rule sanctioned
    ignorance, so the model supplied a plausible cause instead."""
    from jarvis.prompts import GOLDEN_RULES

    assert "I don't know why" in GOLDEN_RULES


def test_rule_3_no_longer_mandates_suggesting_a_fix():
    """Rule 3 used to end 'and suggest the fix' — an instruction to
    speculate when the specialist named none. That phrasing was the
    proximate cause of "the codebase access is blocked"."""
    assert "and suggest the fix." not in SUPERVISOR_PROMPT
    assert "Suggest a fix ONLY if" in SUPERVISOR_PROMPT


def test_rule_11_authorizes_reporting_an_absent_reason():
    assert "didn't finish and didn't say why" in SUPERVISOR_PROMPT


def test_no_guessing_at_causes():
    """Rule 2 names the exact categories that were invented."""
    from jarvis.prompts import GOLDEN_RULES

    for word in ("access", "permissions", "credentials", "connectivity"):
        assert word in GOLDEN_RULES


class TestVerificationTaxonomy:
    """MORTIMER_SKILL_LIBRARY_PLAN.md Part B — the discernment taxonomy
    lives in the prompt layer, NOT in a skill, because MAX_INJECTED = 1
    means a general skill loses to every specific one."""

    def test_every_subagent_gets_it(self):
        """No matching involved: it reaches all five agents, always."""
        from jarvis.prompts import SUBAGENT_PROMPTS, VERIFICATION_TAXONOMY_RULE

        assert len(SUBAGENT_PROMPTS) == 5
        for name, prompt in SUBAGENT_PROMPTS.items():
            assert VERIFICATION_TAXONOMY_RULE in prompt, name

    def test_it_appears_exactly_once_per_prompt(self):
        """Appended in one place (the dict comprehension), never baked
        into a literal — same discipline as D6/D7."""
        from jarvis.prompts import SUBAGENT_PROMPTS, VERIFICATION_TAXONOMY_RULE

        for name, prompt in SUBAGENT_PROMPTS.items():
            assert prompt.count(VERIFICATION_TAXONOMY_RULE) == 1, name

    def test_names_all_three_claim_categories(self):
        from jarvis.prompts import VERIFICATION_TAXONOMY_RULE as rule

        assert "did a tool return it in this run" in rule       # facts/figures
        assert "cause for a failure" in rule                     # reasoning
        assert "say what you assumed" in rule                    # missing context

    def test_forbids_the_appended_caveat_list(self):
        """B2 — discernment-nudge's output format must NOT port. Sub-agents
        have a 60-word plain-text contract and speak through TTS."""
        from jarvis.prompts import VERIFICATION_TAXONOMY_RULE as rule

        assert "never append caveats" in rule.lower()

    def test_stays_short(self):
        """B3 — this is injected into EVERY sub-agent run, so length costs
        more here than in a skill that fires on match."""
        from jarvis.prompts import VERIFICATION_TAXONOMY_RULE

        assert len(VERIFICATION_TAXONOMY_RULE) < 400

    def test_conversational_agents_stay_lean(self):
        """The four non-developer prompts must not drift toward the
        developer's size.

        **The ceiling moved from 1600 to 1800 on 2026-08-18** when
        HANDOFF_RULE was added, and the reason is worth recording rather
        than quietly raising: measured at that point, the four shared
        discipline rules (grounding, no-invented-remediation,
        verification taxonomy, handoff) total ~1,226 chars against ~490
        of scheduler-specific instruction — **71% of a conversational
        agent's prompt is now shared rules**, a 2.5:1 ratio.

        That is not obviously wrong; the discipline is the valuable part
        and these agents are simple. But it is the same dilution shape
        the meta-prompts review measured on the developer from the other
        direction, and the four rules overlap substantially — all are
        variations on "do not state what you did not observe". If this
        ceiling needs raising again, CONSOLIDATE them first, the way
        GOLDEN_RULES consolidated rules 3/11 rather than adding to them.
        """
        from jarvis.prompts import SUBAGENT_PROMPTS

        for name in ("scheduler", "librarian", "analyst", "systems"):
            assert len(SUBAGENT_PROMPTS[name]) < 1800, name


class TestHandoffRule:
    """MORTIMER_HANDOFF_LOOP_PLAN.md H2 — Larry: "quitting is not
    acceptable". The run log showed Mortimer did not quit; it stopped at
    "I cannot" instead of converting the blocker into a handoff."""

    def test_every_subagent_gets_it(self):
        from jarvis.prompts import HANDOFF_RULE, SUBAGENT_PROMPTS

        for name, prompt in SUBAGENT_PROMPTS.items():
            assert HANDOFF_RULE in prompt, name

    def test_it_names_the_marker_delegate_py_keys_off(self):
        """The marker is the mechanical half: delegate.py reads it from
        the agent's OWN reply to authorise a continuation, so a Supervisor
        cannot forge permission for its own retry."""
        from jarvis.agents.delegate import HANDOFF_MARKER
        from jarvis.prompts import HANDOFF_RULE

        assert HANDOFF_MARKER in HANDOFF_RULE

    def test_it_asks_for_the_command_not_just_the_complaint(self):
        from jarvis.prompts import HANDOFF_RULE

        assert "exact command" in HANDOFF_RULE

    def test_search_discipline_is_stated(self):
        """Rounds 9-15 of b74ed019 were a widening search after the answer
        was already in hand."""
        from jarvis.prompts import HANDOFF_RULE

        assert "more searching is not more progress" in HANDOFF_RULE

    def test_the_magnitude_check_is_in_the_taxonomy(self):
        """The question that actually cracked the weather bug: 13F does
        not fit a 15-minute cache, so staleness was the wrong hypothesis."""
        from jarvis.prompts import VERIFICATION_TAXONOMY_RULE as rule

        assert "MAGNITUDE" in rule

    def test_the_addendum_forbids_shell_comments(self):
        """zsh does not treat # as a comment interactively — it cost two
        broken command handoffs on 2026-08-18."""
        from jarvis.prompts import HANDOFF_ADDENDUM

        assert "zsh" in HANDOFF_ADDENDUM

    def test_the_addendum_explains_continuation(self):
        from jarvis.prompts import HANDOFF_ADDENDUM

        assert "continuation" in HANDOFF_ADDENDUM
        assert "not a retry" in HANDOFF_ADDENDUM
