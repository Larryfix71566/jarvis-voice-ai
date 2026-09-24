"""Unit tests for jarvis/prompts.py."""

import pytest

from jarvis.prompts import (
    HANDOFF_ADDENDUM,
    SCREEN_VISION_ADDENDUM,
    STATUS_ADDENDUM,
    SUBAGENT_PROMPTS,
    SUPERVISOR_PROMPT,
    UI_CONTROL_ADDENDUM,
    VOICE_ADDENDUM,
    build_supervisor_prompt,
    render_agent_catalog,
    render_voice_catalog,
)


def test_supervisor_prompt_formats_all_placeholders():
    rendered = SUPERVISOR_PROMPT.format(
        jarvis_name="Jarvis",
        user_name="Boss",
        timezone="America/New_York",
        units="imperial",
        agent_catalog="- scheduler (Scheduler): time stuff",
        model_catalog="- claude-opus (say \"Opus\"): anthropic, tier frontier",
        voice_catalog="- rachel: Rachel (calm)",
        memory_context="- user.name: Larry",
    )
    assert "Jarvis" in rendered
    assert "America/New_York" in rendered
    assert "imperial" in rendered
    assert "- scheduler (Scheduler): time stuff" in rendered
    assert "- rachel: Rachel (calm)" in rendered
    assert "- user.name: Larry" in rendered
    assert "{" not in rendered  # no unformatted placeholders remain


def test_supervisor_prompt_carries_units():
    """W3 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — {units} is a
    real placeholder in the template (so a missed call site raises
    KeyError at render time, not silently), and the rendered text tells
    the Supervisor when NOT to re-convert a get_weather figure."""
    assert "{units}" in SUPERVISOR_PROMPT
    with pytest.raises(KeyError):
        SUPERVISOR_PROMPT.format(
            jarvis_name="Jarvis", user_name="Boss", timezone="America/New_York",
            agent_catalog="", model_catalog="", voice_catalog="",
            memory_context="",
        )  # units= omitted on purpose
    rendered = SUPERVISOR_PROMPT.format(
        jarvis_name="Jarvis", user_name="Boss", timezone="America/New_York",
        units="metric", agent_catalog="", model_catalog="",
        voice_catalog="", memory_context="",
    )
    assert "metric" in rendered
    assert "never re-convert" in rendered.lower()


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
    assert set(SUBAGENT_PROMPTS) == {"scheduler", "librarian", "analyst",
                                     "systems", "developer", "app_builder"}
    for name, prompt in SUBAGENT_PROMPTS.items():
        assert "FAILED:" in prompt, name
    assert "{timezone}" not in SUBAGENT_PROMPTS["scheduler"].format(
        timezone="America/New_York"
    )


def test_analyst_prompt_requires_both_weather_tools():
    """W5 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — radar is
    'standard for this display/workflow' per Larry, so the analyst's own
    prompt must require BOTH get_weather and get_weather_radar for a
    local/current weather question, not just get_weather alone. Also
    checks the prompt tells the analyst not to describe the merge
    mechanism (WeatherReportMerger renders them as one card automatically
    — the analyst shouldn't narrate that)."""
    p = SUBAGENT_PROMPTS["analyst"]
    assert "get_weather_radar" in p
    assert "get_weather" in p
    assert "both" in p.lower()


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


def test_rule_12_single_selfedit_slot_and_no_wait_primitive():
    """G9/G10 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): no
    parallel self-edit slot exists and there is no wait/timer capability —
    the Supervisor must say so rather than imply either."""
    assert "Only one self-edit runs at a time" in SUPERVISOR_PROMPT
    assert "There is no wait or timer capability" in SUPERVISOR_PROMPT


def test_developer_prompt_forbids_unwritten_commit_claims():
    """G11: a commit/PR summary must never describe a change the staged
    diff doesn't actually contain — the direct fix for the phantom radar-
    fix commit found in session log review."""
    from jarvis.prompts import DEVELOPER_SECTIONS

    assert (
        "describe ONLY changes actually present in the staged diff"
        in DEVELOPER_SECTIONS["self_development"]
    )


def test_rule_9_forbids_soliciting_approval_before_preview_relayed():
    """G3 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
    confirmation death spiral was partly a Supervisor-side habit of asking
    for approval of an action whose preview the user never actually
    heard. Rule 9 now forbids that, and requires the staging_id (G2's
    stateful handshake) in a self-edit confirmation task."""
    assert "Never solicit the user's approval before a specialist's preview" in SUPERVISOR_PROMPT
    assert "staging_id" in SUPERVISOR_PROMPT


def test_no_guessing_at_causes():
    """Rule 2 names the exact categories that were invented."""
    from jarvis.prompts import GOLDEN_RULES

    for word in ("access", "permissions", "credentials", "connectivity"):
        assert word in GOLDEN_RULES


class TestAgentDiscipline:
    """The ONE rule block on every sub-agent prompt.

    Consolidated 2026-08-18 from four rules (grounding D6,
    no-invented-remediation D7, verification taxonomy, handoff H2) that
    overlapped heavily — 1,216 chars down to ~546. Larry asked for under
    15%; that was arithmetically unreachable (86 chars for the scheduler)
    because the conversational prompts carry only 382-490 chars of their
    own, so the guardrail below is an ABSOLUTE budget instead. A ratio is
    hostage to how terse the agent-specific text happens to be: the
    developer sat at 23% with the same rules the analyst had at 76%.
    """

    def test_every_subagent_gets_it_exactly_once(self):
        from jarvis.prompts import AGENT_DISCIPLINE, SUBAGENT_PROMPTS

        # 2026-09-06: six since app_builder split out of developer.
        assert len(SUBAGENT_PROMPTS) == 6
        for name, prompt in SUBAGENT_PROMPTS.items():
            assert prompt.count(AGENT_DISCIPLINE) == 1, name

    def test_it_fits_the_absolute_budget(self):
        """D — what matters is how much undifferentiated instruction a
        small model must hold, and that is a character count. If this
        needs raising, CONSOLIDATE first; appending a fifth rule is what
        made the last consolidation necessary."""
        from jarvis.prompts import AGENT_DISCIPLINE, MAX_AGENT_DISCIPLINE_CHARS

        assert len(AGENT_DISCIPLINE) <= MAX_AGENT_DISCIPLINE_CHARS

    def test_it_is_smaller_than_what_it_replaced(self):
        """The four rules totalled 1,216 chars."""
        from jarvis.prompts import AGENT_DISCIPLINE

        assert len(AGENT_DISCIPLINE) < 1216 * 0.6

    def test_no_agent_prompt_is_mostly_boilerplate(self):
        """A per-agent ceiling, so the shared block cannot creep back by
        being appended to rather than consolidated."""
        from jarvis.prompts import SUBAGENT_PROMPTS

        # 2026-09-06: derived, not hardcoded. app_builder was added to the
        # roster and slipped straight past this ceiling because it was not
        # in the tuple — a per-agent budget that a new agent can sidestep
        # by existing is not a budget. developer is the one exemption and
        # it is named, so adding another is a deliberate edit here.
        for name in sorted(set(SUBAGENT_PROMPTS) - {"developer"}):
            assert len(SUBAGENT_PROMPTS[name]) < 1200, name

    # --- every clause earns its place; each maps to an observed failure --

    def test_grounding_survived(self):
        """D6 — a run described a repository it had failed to read."""
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert "never describe what you could not read" in R
        assert "Say when a tool failed" in R

    def test_no_invented_cause_or_fix_survived(self):
        """D7 — a GitHub 401 was reported as "the admin sidecar may be
        offline", sending Larry to debug the wrong component."""
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert "never name a cause a tool did not name" in R
        assert "never invent a fix" in R
        assert "a service to restart" in R      # the concrete D7 shape

    def test_missing_context_survived(self):
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert "Say what you assumed" in R

    def test_magnitude_check_survived(self):
        """The question that cracked the weather bug: 13F does not fit a
        15-minute cache."""
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert "size of the error does not fit your explanation" in R

    def test_missing_tool_replaces_the_command_handoff(self):
        """T1.2 (2026-09-22) — a sub-agent without a tool names the gap
        (MISSING-TOOL:) instead of handing the user a command; NEEDS-INPUT:
        stays for choices only the user can make. delegate.py reads both
        markers from the agent's OWN reply, so this pins the pairs."""
        from jarvis.agents.delegate import HANDOFF_MARKER, MISSING_TOOL_MARKER
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert HANDOFF_MARKER in R
        assert MISSING_TOOL_MARKER in R
        assert 'do not stop at "I cannot"' in R
        assert "never a user command" in R
        assert "exact command" not in R

    def test_search_discipline_survived(self):
        """H2.3 — run b74ed019 had every file it needed by round 8 and
        spent rounds 9-15 searching wider."""
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert "stop gathering and reason" in R

    def test_voice_output_shape_survived(self):
        """Sub-agents speak through TTS under a 60-word contract; an
        appended caveat list is unspeakable."""
        from jarvis.prompts import AGENT_DISCIPLINE as R

        assert "Hedge inline; never append caveats" in R


class TestHandoffAddendum:
    """The Supervisor's half of the handoff loop (H3/H6), shipped only
    when its tools are registered."""

    def test_the_addendum_forbids_shell_comments(self):
        """zsh does not treat # as a comment interactively — it cost two
        broken command handoffs on 2026-08-18."""
        from jarvis.prompts import HANDOFF_ADDENDUM

        assert "zsh" in HANDOFF_ADDENDUM

    def test_the_addendum_explains_continuation(self):
        from jarvis.prompts import HANDOFF_ADDENDUM

        assert "continuation" in HANDOFF_ADDENDUM
        assert "not a retry" in HANDOFF_ADDENDUM

    def test_addendum_forbids_commands_by_default(self):
        """T1.3 (Larry, 2026-09-22): assume the user is not technical."""
        from jarvis.prompts import HANDOFF_ADDENDUM

        assert "assume he does not use a terminal" in HANDOFF_ADDENDUM
        assert "only when he explicitly asks" in HANDOFF_ADDENDUM
        assert "MISSING-TOOL" in HANDOFF_ADDENDUM


class TestDeveloperSections:
    """MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md Part A.

    Measured before the split: the developer's own prompt was 4,034 chars,
    of which app_development (1,188) and self_development (1,566) — 68% —
    were injected on EVERY run including "read this YAML file".

    The property that matters most here is not the saving; it is that no
    task can lose a confirmation protocol. Two of these tests exist purely
    to pin failure modes, not features.
    """

    def _own(self, task):
        from jarvis.prompts import developer_prompt_for
        return developer_prompt_for(task)

    def test_full_prompt_is_core_plus_every_section(self):
        """The reassembly identity — no text was lost in the split."""
        from jarvis.prompts import (
            DEVELOPER_CORE, DEVELOPER_SECTIONS, developer_prompt_for)
        full = developer_prompt_for("")
        assert DEVELOPER_CORE in full
        for text in DEVELOPER_SECTIONS.values():
            assert text in full

    def test_no_section_text_was_reworded(self):
        """This change alters WHEN text is injected, never what it says. A
        rewording here would let a behavioural regression hide behind an
        editorial one."""
        from jarvis.prompts import DEVELOPER_SECTIONS
        for name, text in DEVELOPER_SECTIONS.items():
            assert "two-phase" in text or "plan_start" in text, name
            assert text.strip() == text

    def test_self_development_offers_plan_on_core_refusal(self):
        """Status spec T4.8: a core-tier refusal becomes an offer to write
        the plan, then a restart with its plan_path — not a dead end."""
        from jarvis.prompts import DEVELOPER_SECTIONS
        text = DEVELOPER_SECTIONS["self_development"]
        sentence = ("If selfedit_start refuses because a core file needs a plan, offer to "
                    "write one with plan_start for the same goal, and after the user adopts "
                    "it, start again with that plan_path.")
        assert text.endswith(sentence)
        assert text.count(sentence) == 1

    def test_an_offline_sidecar_is_reported_without_a_command(self):
        """Review finding 8 (L1): the user never gets a terminal command —
        the section used to say to suggest ./scripts/mortimer.sh."""
        from jarvis.prompts import DEVELOPER_SECTIONS
        text = DEVELOPER_SECTIONS["self_development"]
        assert "scripts/" not in text and ".sh" not in text
        assert "the admin sidecar is not running" in text
        assert "never give the user a command" in text

    def test_a_self_edit_task_gets_the_self_development_section(self):
        from jarvis.prompts import select_developer_sections as sel
        assert "self_development" in sel("implement the drawer plan in mortimer")

    def test_an_app_task_gets_the_app_section(self):
        from jarvis.prompts import select_developer_sections as sel
        assert "app_development" in sel("create a new app for tracking runs")

    def test_a_plain_repo_read_gets_neither_protocol(self):
        """The actual saving, and the case that motivated Part A. The pin
        is against the 4,034-char full prompt; it was 1000 when core had
        no runlog or confirmation-shortcut sentences (2026-08-20/21 —
        each one earned its place by a live failure) and moves to 1100
        with them. If core needs to grow again, trim it first."""
        from jarvis.prompts import select_developer_sections as sel
        assert sel("read config/agents.yaml and tell me the timeout") == []
        # 2026-09-04 — MORTIMER_GRAPH_LAYER_PLAN.md step 9: the graph_view
        # sentence in DEVELOPER_CORE (1,098 -> ~1,220). Next growth trims first.
        assert len(self._own("show me the git log")) < 1250

    def test_a_read_that_could_write_keeps_the_protocol(self):
        """THE hazard of the core-only path. "read the file and fix the bug"
        looks like a read; it is a self-edit. Every mutation verb lives in
        self_development's vocabulary precisely so this cannot slip
        through."""
        from jarvis.prompts import select_developer_sections as sel
        for task in ("read the file and fix the bug in it",
                     "look at prompts.py and update the wording",
                     "check the config then add a new field"):
            assert "self_development" in sel(task), task

    def test_an_unrecognized_task_gets_every_section(self):
        """Fail-open. A task the selector does not understand must never be
        the one that loses a gate."""
        from jarvis.prompts import DEVELOPER_SECTIONS
        from jarvis.prompts import select_developer_sections as sel
        assert set(sel("zzz qqq wibble")) == set(DEVELOPER_SECTIONS)

    def test_a_task_that_is_both_gets_both_sections(self):
        """No MAX_INJECTED here — sections do not compete."""
        from jarvis.prompts import select_developer_sections as sel
        picked = sel("write an implementation plan then implement it in mortimer")
        assert "planning" in picked and "self_development" in picked

    def test_the_kill_switch_restores_the_full_prompt(self, monkeypatch):
        from jarvis.prompts import (
            DEVELOPER_SECTIONS_ENABLED_ENV, developer_prompt_for)
        monkeypatch.setenv(DEVELOPER_SECTIONS_ENABLED_ENV, "false")
        assert developer_prompt_for("show me the git log") == developer_prompt_for("")

    def test_selection_is_pure(self):
        """No DB, no network, no model — it runs in a unit test with no
        fixtures at all, which is the assertion."""
        from jarvis.prompts import select_developer_sections as sel
        assert sel("read a file") == sel("read a file")

    def test_core_names_the_runlog_tools(self):
        """2026-08-20, from a live miss: the developer has mcp-runlog wired
        in agents.yaml but its prompt never named the tools, so an
        investigation delegation could land on an agent that didn't know it
        could read run history. The route from ear to evidence is
        prompt-text at both layers (Supervisor rule 8, and here) — losing
        this sentence severs the second hop."""
        from jarvis.prompts import DEVELOPER_CORE
        assert "runlog_list" in DEVELOPER_CORE
        assert "runlog_detail" in DEVELOPER_CORE

    def test_an_investigation_task_is_a_read(self):
        """Run-log investigation is read-only work and takes the core-only
        path — the runlog sentence lives in CORE, so it is always present,
        and no confirmation protocol is needed to read history."""
        from jarvis.prompts import select_developer_sections as sel
        assert sel(
            "investigate why the analyst run found nothing when it searched"
        ) == []

    def test_investigate_and_fix_keeps_the_protocol(self):
        """Same hazard shape as test_a_read_that_could_write: an
        investigation that could end in a write must still carry the
        self-development gate."""
        from jarvis.prompts import select_developer_sections as sel
        assert "self_development" in sel(
            "investigate why the run failed and fix the bug behind it")


# ------------------------------------------------ S11: attribution rules
# MORTIMER_SESSION_MISSES_PLAN.md S11. Both are prompt-only and Haiku-
# fragile by nature (the plan says so); these pin the TEXT so a later
# prompt edit cannot silently drop them, which is the only guarantee a
# prompt rule can carry.


def test_golden_rule_4_forbids_naming_a_specialist():
    """2026-09-03 13:46:22: "The analyst's result didn't include it" — two
    turns after the prompt told it delegation IS its own work."""
    from jarvis.prompts import GOLDEN_RULES

    assert "Never name a specialist to the user" in GOLDEN_RULES
    # It must ride in the Supervisor's prompt, not just the constant.
    assert "Never name a specialist to the user" in SUPERVISOR_PROMPT


def test_supervisor_prompt_re_delegates_for_a_missing_detail():
    """Same turn: it reported the humidity missing instead of asking for
    it. Rule 1's "say exactly that" is scoped to after a fresh attempt."""
    assert "delegate again for that detail before saying it was missing" in SUPERVISOR_PROMPT


def test_the_new_rules_survive_formatting():
    rendered = SUPERVISOR_PROMPT.format(
        jarvis_name="Jarvis", user_name="Boss", timezone="America/New_York",
        units="imperial", agent_catalog="- analyst (Analyst): research",
        model_catalog='- claude-opus (say "Opus"): anthropic, tier frontier',
        voice_catalog="- rachel: Rachel", memory_context="- user.name: Larry",
    )
    assert "Never name a specialist to the user" in rendered
    assert "delegate again for that detail before saying it was missing" in rendered
    assert "{" not in rendered


# --- build_supervisor_prompt (2026-09-05, EVAL_CONFIG_PARITY item A) ----
#
# The assembly used to exist twice: jarvis/bot/pipeline.py concatenated
# four addenda onto SUPERVISOR_PROMPT, and jarvis/agents/supervisor.py
# formatted it bare. They had drifted, and the routing eval — which drives
# Orchestrator — was scoring a prompt with none of the addenda production
# ships. These tests exist to prove the extraction changed NOTHING, which
# is the only reason it is safe to land before the behavioural work.

_FMT = dict(
    jarvis_name="Mortimer",
    user_name="Larry",
    timezone="America/New_York",
    units="imperial",
    agent_catalog="- scheduler (Scheduler): time stuff",
    model_catalog='- claude-opus (say "Opus"): anthropic, tier frontier',
    voice_catalog="- rachel: Rachel",
    memory_context="(none yet)",
)


def test_a_bare_call_is_the_prompt_supervisor_py_has_always_built():
    # Pins jarvis/agents/supervisor.py:92 as a no-op.
    assert build_supervisor_prompt(**_FMT) == SUPERVISOR_PROMPT.format(**_FMT)


def test_the_default_production_call_matches_the_expression_it_replaced():
    # Pins jarvis/bot/pipeline.py as a no-op. The right-hand side is the
    # old expression transcribed literally, addendum order and single "\n"
    # separator included; if either drifts this fails.
    expected = (
        SUPERVISOR_PROMPT.format(**_FMT)
        + "\n"
        + VOICE_ADDENDUM
        + ("\n" + UI_CONTROL_ADDENDUM)
        + ("\n" + SCREEN_VISION_ADDENDUM)
        + ("\n" + HANDOFF_ADDENDUM)
    )
    assert build_supervisor_prompt(
        **_FMT, voice=True, ui_control=True, screen=True, clipboard=True
    ) == expected


@pytest.mark.parametrize(
    "flag,addendum",
    [
        ("voice", VOICE_ADDENDUM),
        ("ui_control", UI_CONTROL_ADDENDUM),
        ("screen", SCREEN_VISION_ADDENDUM),
        ("clipboard", HANDOFF_ADDENDUM),
        ("status", STATUS_ADDENDUM),
    ],
)
def test_each_flag_appends_exactly_its_own_addendum(flag, addendum):
    base = build_supervisor_prompt(**_FMT)
    got = build_supervisor_prompt(**_FMT, **{flag: True})
    assert got == base + "\n" + addendum


def test_a_disabled_addendum_leaves_no_trace_in_the_prompt():
    # U5/U6: a prompt describing an unregistered tool invites hallucinated
    # calls, so "off" must mean absent, not merely unmentioned elsewhere.
    off = build_supervisor_prompt(**_FMT, voice=True)
    assert UI_CONTROL_ADDENDUM not in off
    assert SCREEN_VISION_ADDENDUM not in off
    assert HANDOFF_ADDENDUM not in off


def test_status_addendum_follows_ui_control():
    full = build_supervisor_prompt(
        **_FMT, voice=True, ui_control=True, screen=True, clipboard=True, status=True
    )
    assert full.index(UI_CONTROL_ADDENDUM) < full.index(STATUS_ADDENDUM) < full.index(
        SCREEN_VISION_ADDENDUM)
    assert STATUS_ADDENDUM not in build_supervisor_prompt(
        **_FMT, voice=True, ui_control=True, screen=True, clipboard=True)


def test_status_addendum_is_the_spec_text():
    assert STATUS_ADDENDUM == (
        "Your own status: for questions about your models, what a provider or "
        "subscription offers, your services, configuration, the Mac app build, or "
        "where the user is, call system_status yourself — never delegate these and "
        "never hand the user a command. The model registry lists what is configured, "
        "not what an account offers: answer whether a model is available only from a "
        "catalog or subscription result, and say which source and when."
    )


def test_addenda_keep_the_order_pipeline_py_used():
    full = build_supervisor_prompt(
        **_FMT, voice=True, ui_control=True, screen=True, clipboard=True
    )
    positions = [
        full.index(VOICE_ADDENDUM),
        full.index(UI_CONTROL_ADDENDUM),
        full.index(SCREEN_VISION_ADDENDUM),
        full.index(HANDOFF_ADDENDUM),
    ]
    assert positions == sorted(positions)


# --- 2026-09-05: two clauses added from observed eval failures ---------
#
# Both come from misses that reproduced across two live parity runs, not
# from reading the prompt. They are pinned because a later edit that
# quietly drops either one would restore a behaviour we have watched fail.


def test_a_specialists_records_are_not_self_knowledge():
    from jarvis.prompts import GOLDEN_RULES
    # Case 25, twice: "the registry is empty at the moment" with no tool
    # call at all. Golden Rule 1 covered unobserved FACTS but the model did
    # not read a specialist's data as one.
    assert "A specialist's records are not things you know" in GOLDEN_RULES
    assert "reporting any of it without asking" in GOLDEN_RULES
    # The boundary against the memory block, which says the opposite about
    # memories ("things you already know").
    assert "a specialist's data never is" in GOLDEN_RULES


def test_the_golden_rules_still_permit_not_knowing():
    from jarvis.prompts import GOLDEN_RULES
    # The clause above adds an obligation to ask; it must not crowd out the
    # answer that made Golden Rule 1 work.
    assert "I don't know why" in GOLDEN_RULES


def test_a_specialist_that_can_resolve_the_gap_gets_the_delegation():
    # Cases 56 and 66, twice: a clarifying question instead of delegating,
    # which is Rule 4 doing what it says. Rule 9 and HANDOFF_ADDENDUM exist
    # so the SPECIALIST asks and the orchestrator relays; Rule 4 was
    # pre-empting that path at the door.
    assert "But ask ONLY when the missing detail exists nowhere except" in \
        SUPERVISOR_PROMPT
    assert "the run log that records every delegation" in SUPERVISOR_PROMPT
    assert "withholding the delegation is what breaks that path" in \
        SUPERVISOR_PROMPT


def test_rule_4_still_asks_when_only_the_user_has_the_answer():
    # Cases 36 and 37 ("remind me about the thing", "save a note") expect NO
    # delegation and pass. The new clause must not turn them into
    # delegations to a specialist that cannot act.
    assert 'A vague request like "remind me about the thing" is missing its ' \
        'content — ask, do not delegate.' in SUPERVISOR_PROMPT


def test_only_prompts_py_formats_the_template_directly():
    """The assembler is the single entry point, by construction.

    2026-09-05: adding {model_catalog} broke scripts/context_growth_probe.py
    and revealed scripts/voice_model_bench.py had been calling .format()
    without `units` — a KeyError on every run, in a script nothing
    exercised. Four independent argument lists for one template is how a
    placeholder becomes a latent break. Anything that needs the prompt goes
    through build_supervisor_prompt; only prompts.py itself and this test
    module touch the raw template.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    offenders = []
    for folder in ("jarvis", "scripts"):
        for path in (root / folder).rglob("*.py"):
            if path.name == "prompts.py" and path.parent.name == "jarvis":
                continue
            if "SUPERVISOR_PROMPT.format" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], (
        "these format the template directly instead of calling "
        f"build_supervisor_prompt: {offenders}"
    )


# --- the three remaining self-contradictions, resolved 2026-09-06 --------
#
# Found by reading the prompt, not by a run — but contradiction 1 then
# fired live TWICE in the parity runs: cases 25 and 30 both named the
# developer specialist to the user, which rule 4 and Golden Rule 4 forbid
# and rule 10's own worked example licensed.


def test_rule_10s_example_no_longer_names_a_specialist():
    # Rule 4 and Golden Rule 4 are absolute ("Never name a specialist to
    # the user"). Rule 10's example used to be a verbatim violation of
    # them, which left the model to pick one at random — and it picked
    # wrong in both runs.
    assert "the librarian doesn't have a tool for that yet" not in \
        SUPERVISOR_PROMPT
    assert "offer to have the developer add it" not in SUPERVISOR_PROMPT
    assert "that isn't something I have a tool for yet" in SUPERVISOR_PROMPT


def test_the_missing_tool_case_is_still_reported_plainly():
    # Removing the specialist's name must not remove the disclosure. A
    # named gap gets fixed; a worked-around gap stays broken forever.
    assert "MISSING TOOL" in SUPERVISOR_PROMPT
    assert "offer to have it added through self-development" in SUPERVISOR_PROMPT


def test_rule_10_assumes_no_terminal():
    # T1.3 — holds even when the clipboard switch removes HANDOFF_ADDENDUM.
    assert "Assume the user does not use a terminal" in SUPERVISOR_PROMPT


def test_rule_13_cites_golden_rule_1_not_the_numbered_rule_1():
    # There are two "Rule 1"s: the numbered one is the acknowledgment
    # sentence, and "say exactly that" is in the GOLDEN rules. Rule 3 gets
    # this right; rule 13 did not.
    assert 'Golden Rule 1\'s "say exactly that"' in SUPERVISOR_PROMPT
    assert 'Rule 1\'s "say exactly that"' not in \
        SUPERVISOR_PROMPT.replace('Golden Rule 1\'s "say exactly that"', "")


def test_rule_11_is_scoped_so_it_does_not_forbid_what_rule_13_requires():
    # Rule 11 means a FAILED delegation; rule 13 means a successful one
    # missing a detail. Neither said so, which left them contradicting.
    assert "a reworded version of a task that FAILED" in SUPERVISOR_PROMPT
    assert "rule 13 is the other case" in SUPERVISOR_PROMPT
    # Rule 13's own instruction has to survive the scoping.
    assert "delegate again for that detail before saying it was missing" in \
        SUPERVISOR_PROMPT


def test_the_staging_id_example_matches_what_the_server_generates():
    """Observed live 2026-09-07, and it is why §8.6 never closed.

    admin/server.py:820 generates `uuid.uuid4().hex[:12]` — a bare
    twelve-character hex string. Rule 9's worked example used to read
    "Confirmation: start self-edit staging stg-abc", and the model
    pattern-matched that `stg-` prefix onto a real id: a preview naming
    0d049db0947d became a confirmation naming stg-0d049db0947d, which the
    server answered with "no staged edit with id 'stg-0d049db0947d' — it
    may have expired". It then re-staged and looped, every cycle producing
    a fresh bare id the confirmation corrupted again.

    Same shape as the or-sonnet-5 defect: a worked example that does not
    match what the system produces, turning into an unresolvable
    identifier and a refusal.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    server = (root / "jarvis" / "admin" / "server.py").read_text(encoding="utf-8")
    assert "uuid.uuid4().hex[:12]" in server, (
        "staging_id generation moved — rule 9's example describes its shape "
        "and must be rechecked against it"
    )

    # No prefix may appear anywhere in the prompt.
    assert "stg-" not in SUPERVISOR_PROMPT
    assert "bare twelve-character hex string with NO prefix" in SUPERVISOR_PROMPT

    # The example id itself must be a plausible product of that generator,
    # or it teaches the wrong shape all over again.
    m = re.search(r"a preview naming ([0-9a-f]+) becomes", SUPERVISOR_PROMPT)
    assert m, "rule 9's staging_id example is missing or reworded"
    assert len(m.group(1)) == 12, m.group(1)


def test_selfedit_previews_then_starts_without_an_extra_spoken_confirmation():
    from jarvis.prompts import DEVELOPER_SECTIONS
    text = DEVELOPER_SECTIONS["self_development"]
    assert "speak the returned preview summary" in text
    assert "same turn with confirm set to true" in text
    assert "exact staging_id" in text
    assert "user approves or rejects the result in the pull request" in text
    assert "Merging is never yours" in text
    assert "only after explicit confirmation in a new turn" not in text
    # Larry's self-edit decision does not silently change new-app creation.
    assert "only after the user explicitly confirms in a new turn" in DEVELOPER_SECTIONS["app_development"]
