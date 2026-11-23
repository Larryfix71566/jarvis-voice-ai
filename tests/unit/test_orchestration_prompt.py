"""WS-42: the voice prompt split (flag off byte-identical, flag on swapped)."""

import hashlib

import pytest

from jarvis import prompts as P
from jarvis.bot.tool_schemas import supervisor_tool_schemas
from jarvis.agents.delegate import build_delegate_tool
from tests.unit.test_orchestrator import FakeSubAgent

# sha256 of SUPERVISOR_PROMPT on origin/next a469553 (13,892 characters).
GOLDEN_SHA256 = "38f69d871852dc3a1ce3a104c2568d3f050657a8678b87899b60b7f7c82a9b34"
GOLDEN_MENU_ALL_FLAGS = [
    "delegate_task", "set_voice", "remember", "cost_summary", "system_status",
    "ui_control", "view_screen", "list_screens", "show_commands", "clear_clipboard",
    "read_clipboard", "console_action", "shared_content", "progress_updates",
    "follow_up", "local_weather", "daily_brief",
]

_KW = dict(jarvis_name="Mortimer", user_name="Larry", timezone="America/New_York",
           units="imperial", agent_catalog="- librarian (Librarian): notes",
           model_catalog="- claude-sonnet-5: tier mid", voice_catalog="- v: Voice",
           memory_context="(none)")


def test_flag_off_template_is_byte_identical():
    assert len(P.SUPERVISOR_PROMPT) == 13892
    assert hashlib.sha256(P.SUPERVISOR_PROMPT.encode()).hexdigest() == GOLDEN_SHA256


def test_flag_off_tool_menu_is_unchanged():
    schema, _ = build_delegate_tool({"librarian": FakeSubAgent("librarian")})
    names = [s["function"]["name"] for s in supervisor_tool_schemas(
        schema, ui_control=True, screen=True, clipboard=True, command_console=True,
        shared_content=True, status=True, progress=True, follow_up=True,
        weather=True, brief=True)]
    assert names == GOLDEN_MENU_ALL_FLAGS


def test_default_call_ignores_the_orchestrator_argument():
    assert P.build_supervisor_prompt(**_KW) == P.build_supervisor_prompt(**_KW, orchestrator=False)
    assert "delegate_task" in P.build_supervisor_prompt(**_KW)
    assert "hand_off" not in P.build_supervisor_prompt(**_KW)


def test_handoff_template_has_no_delegate_task_and_keeps_all_13_rules():
    template = P.SUPERVISOR_PROMPT_HANDOFF
    assert "delegate_task" not in template
    assert "hand_off" in template
    rules = template.partition("\nRules:\n")[2]
    for n in range(1, 14):
        assert f"\n{n}. " in "\n" + rules, n
    assert template.count("{agent_catalog}") == 1
    assert template.count("{model_catalog}") == 1
    prompt = P.build_supervisor_prompt(**_KW, orchestrator=True)
    assert "Mortimer" in prompt and "- librarian (Librarian): notes" in prompt


def test_handoff_template_keeps_non_routing_rule_8_sentences():
    rule8 = P._rule(8, P.SUPERVISOR_PROMPT_HANDOFF)
    assert P._R8_KEEP_A in rule8
    assert P._R8_KEEP_C in rule8
    assert P._R8_ANSWERING in rule8
    assert P._R8_KEEP_B[len("never "):] in rule8
    # The routing half moved out.
    assert "Anything about the Jarvis repository" not in rule8
    assert "pass the matching profile name" not in rule8
    # Rules 3 and 9 and 13 stay in the voice prompt verbatim.
    for n in (1, 3, 5, 6, 7, 9, 10, 12, 13):
        assert P._rule(n, P.SUPERVISOR_PROMPT_HANDOFF) == (
            P._rule(n) if n != 1 else P._rule(1).replace("delegate_task", "hand_off"))


def test_rule_8_slices_cover_the_original_exactly():
    assert P._RULE8 == (P._R8_KEEP_A + " " + P._R8_ROUTE + " — " + P._R8_KEEP_B
                        + " " + P._R8_KEEP_C)


def test_orchestrator_prompt_carries_moved_rules_verbatim():
    text = P.ORCHESTRATOR_PROMPT
    assert P._rule(2) in text
    assert P._R3_FIRST_TWO in text
    assert P._rule(4) in text
    assert P._R8_ROUTE in text
    assert P._rule(9) in text
    assert P._R11_RETRY in text
    assert P._rule(13) in text
    # Rule 3's failure-reporting tail and rule 11's reporting half stay with the voice model.
    assert "If a specialist returns FAILED, say so plainly" not in text
    assert "report the sub-agent's stated reason" not in text


def test_orchestrator_prompt_has_catalogs_and_contract():
    prompt = P.build_orchestrator_prompt(
        jarvis_name="Mortimer", timezone="America/New_York",
        agent_catalog="- librarian (Librarian): notes {curly}", model_catalog="- claude-sonnet-5: tier mid")
    assert "- librarian (Librarian): notes {curly}" in prompt
    assert "- claude-sonnet-5: tier mid" in prompt
    assert "America/New_York" in prompt and "Mortimer" in prompt
    for token in ("{jarvis_name}", "{timezone}", "{agent_catalog}", "{model_catalog}"):
        assert token not in prompt
    assert '"steps"' in prompt and '"ask_user"' in prompt
    assert "0 to 4 steps" in prompt
    assert "continuation" in prompt and "findings_path" in prompt and "model_profile" in prompt
    assert "cannot see each other's results" in prompt


@pytest.mark.parametrize("flag", [False, True])
def test_personality_formal_still_applies_to_handoff_template(flag):
    formal = P.build_supervisor_prompt(**_KW, personality="formal", orchestrator=flag)
    assert P.PERSONA_FORMAL in formal
    assert "Tone: the user has asked you to be sarcastic" not in formal
    playful = P.build_supervisor_prompt(**_KW, orchestrator=flag)
    assert P.PERSONA_PLAYFUL in playful
