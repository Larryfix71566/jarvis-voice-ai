"""WS-42: hand_off, the decision call and its validation. No network, no real
model call: the model client is a stub, the specialists are fakes."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from jarvis.agents import orchestration as O
from jarvis.agents.delegate import build_delegate_tool
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_routing import ModelRouteError
from jarvis.privacy_policy import DataPolicy
from jarvis.subscription import SubscriptionRuntimeError
from jarvis.toolresult import FAILURE_TAG_RE
from jarvis.voice_sources import ClassifiedText, text_policy
from tests.unit.test_delegate import ScriptedAgent, SlowFakeSubAgent
from tests.unit.test_orchestrator import FakeSubAgent

AGENTS = ["scheduler", "librarian", "analyst", "systems", "developer"]
APPROVED = DataPolicy("approved_external", "test")


@pytest.fixture(autouse=True)
def _non_sensitive_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def decision_json(steps=None, ask=None):
    return json.dumps({"steps": steps if steps is not None else [], "ask_user": ask})


def one_step(agent="librarian", task="Save a note: plumber Tuesday.", **extra):
    return {"agent_name": agent, "task": task, **extra}


class StubClient:
    """Chat-completions stand-in. `replies` are consumed one per call; an
    exception instance is raised instead of returned."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


async def decide(client, *, transcript="save a note that the plumber comes Tuesday", note="",
                 tail="", policy=APPROVED, agents=AGENTS, resolve_route=None):
    kwargs = {} if resolve_route is None else {"resolve_route": resolve_route}
    return await O.decide_route(
        system_prompt="SYSTEM", transcript=transcript, note=note, tail=tail,
        data_policy=policy, agent_names=agents, client_factory=lambda _: client, **kwargs)


def validate(raw, **over):
    args = dict(agent_names=AGENTS,
                profile_names={"claude-sonnet-5": "claude-sonnet-5",
                               "claude-fable-5": "claude-fable-5"},
                aliases={"Fable": "claude-fable-5", "Sonnet": "claude-sonnet-5"},
                user_words="use opus for this", seen_text="", model="m")
    args.update(over)
    return O.validate_decision(raw, **args)


# --- flag ------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "Yes"])
def test_flag_truthy_values(value):
    assert O.orchestrator_enabled({"JARVIS_ORCHESTRATOR_ENABLED": value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "on", "2", "enabled", " "])
def test_flag_falsy_values(value):
    assert O.orchestrator_enabled({"JARVIS_ORCHESTRATOR_ENABLED": value}) is False


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("JARVIS_ORCHESTRATOR_ENABLED", raising=False)
    assert O.orchestrator_enabled() is False
    assert O.orchestrator_enabled({}) is False


# --- extraction ------------------------------------------------------------

def test_extract_plain_json():
    assert O.extract_first_json_object('{"steps": [], "ask_user": "x"}') == {"steps": [], "ask_user": "x"}


def test_extract_prose_then_json_takes_the_object():
    text = 'Troubleshooting goes to the developer. {"steps": [], "ask_user": "which?"}'
    assert O.extract_first_json_object(text)["ask_user"] == "which?"


def test_extract_fenced_json():
    assert O.extract_first_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_no_object_is_bad_output_and_retryable():
    with pytest.raises(O.DecisionError) as err:
        O.extract_first_json_object("I would send this to the librarian.")
    assert err.value.reason == "orchestrator_bad_output" and err.value.retryable


def test_only_the_first_object_counts():
    first_invalid = '{"steps": 3} then {"steps": [], "ask_user": "ok?"}'
    raw = O.extract_first_json_object(first_invalid)
    assert raw == {"steps": 3}
    with pytest.raises(O.DecisionError) as err:
        validate(raw)
    assert err.value.reason == "orchestrator_invalid_decision"


# --- validation ------------------------------------------------------------

def test_valid_single_step():
    decision = validate({"steps": [one_step()], "ask_user": None})
    assert decision.steps == (O.Step("librarian", "Save a note: plumber Tuesday."),)
    assert decision.ask_user == "" and decision.model == "m"


def test_valid_ask_user():
    decision = validate({"steps": [], "ask_user": " What should I remind you about? "})
    assert decision.steps == () and decision.ask_user == "What should I remind you about?"


@pytest.mark.parametrize("raw", [
    {"steps": [one_step("plumber")], "ask_user": None},                       # unknown agent
    {"steps": [one_step(task=f"t{i}") for i in range(5)], "ask_user": None},
    {"steps": [one_step(task="   ")], "ask_user": None},                      # empty task
    {"steps": [one_step(task="x" * 2001)], "ask_user": None},                 # over cap
    {"steps": [one_step()], "ask_user": None, "extra": 1},                    # extra top key
    {"steps": [one_step(extra="no")], "ask_user": None},                      # extra step key
    {"steps": [one_step()], "ask_user": "or this?"},                          # both
    {"steps": [], "ask_user": None},                                          # neither
    {"steps": [], "ask_user": "  "},                                          # blank question
    {"steps": [], "ask_user": "x" * 301},
    {"steps": [one_step(model_profile="claude-nonesuch")], "ask_user": None},  # unknown profile
    {"steps": [one_step(model_profile="claude-fable-5")], "ask_user": None},   # not named by user
    {"steps": [one_step(continuation="yes")], "ask_user": None},
    {"steps": [one_step(findings_path="/tmp/not-seen.md")], "ask_user": None},
    {"steps": [{"agent_name": "librarian"}], "ask_user": None},
    {"steps": ["librarian"], "ask_user": None},
    {"steps": {}, "ask_user": None},
    {"steps": [one_step()]},
])
def test_invalid_decisions_are_refused_not_retried(raw):
    with pytest.raises(O.DecisionError) as err:
        validate(raw)
    assert err.value.reason == "orchestrator_invalid_decision"
    assert err.value.retryable is False


def test_model_profile_named_by_profile_name_model_id_or_alias():
    raw = {"steps": [one_step(model_profile="claude-fable-5")], "ask_user": None}
    assert validate(raw, user_words="do it with claude-fable-5").steps[0].model_profile == "claude-fable-5"
    assert validate(raw, user_words="ask Fable about it").steps[0].model_profile == "claude-fable-5"
    assert validate(raw, user_words="ask fable").steps[0].model_profile == "claude-fable-5"
    with pytest.raises(O.DecisionError):
        validate(raw, user_words="ask unfabled things")          # whole words only
    with pytest.raises(O.DecisionError):
        validate(raw, user_words="use claude-fable-5-2 please")  # a different profile's name


def test_findings_path_must_appear_verbatim_in_what_was_seen():
    raw = {"steps": [one_step(findings_path="/tmp/findings/run-7.md")], "ask_user": None}
    ok = validate(raw, seen_text="the specialist wrote /tmp/findings/run-7.md for you")
    assert ok.steps[0].findings_path == "/tmp/findings/run-7.md"
    with pytest.raises(O.DecisionError):
        validate(raw, seen_text="the specialist wrote /tmp/findings/run-8.md")


def test_continuation_flag_passes_through_validation():
    step = validate({"steps": [one_step(continuation=True)], "ask_user": None}).steps[0]
    assert step.continuation is True


def test_exact_duplicate_steps_are_collapsed():
    decision = validate({"steps": [one_step(), one_step(), one_step("scheduler", "Remind me.")],
                         "ask_user": None})
    assert [s.agent_name for s in decision.steps] == ["librarian", "scheduler"]


# --- tail ------------------------------------------------------------------

def test_render_tail_labels_clips_and_orders():
    messages = [
        {"role": "system", "content": "SYSTEM PROMPT"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "a" * 900},
        {"role": "tool", "tool_call_id": "t1", "content": "r" * 5000},
        {"role": "user", "content": "[system] late result arrived"},
        {"role": "user", "content": [{"type": "text", "text": "not a string"}]},
        {"role": "user", "content": "last words"},
    ]
    lines = O.render_tail(messages).splitlines()
    assert lines[0] == "USER: first"
    assert lines[1] == "ASSISTANT: " + "a" * O.TAIL_MSG_CHARS
    assert lines[2] == "RESULT: " + "r" * O.TAIL_TOOL_CHARS
    assert lines[3] == "NOTE: [system] late result arrived"
    assert lines[4] == "USER: last words"
    assert "SYSTEM PROMPT" not in "\n".join(lines)


def test_render_tail_keeps_only_the_last_eight_and_drops_oldest_over_budget():
    many = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    assert O.render_tail(many).splitlines() == [f"USER: m{i}" for i in range(12, 20)]
    big = [{"role": "tool", "content": "x" * 4000} for _ in range(8)]
    rendered = O.render_tail(big)
    assert len(rendered) <= O.TAIL_TOTAL_CHARS
    assert len(rendered.splitlines()) == 2


def test_render_tail_survives_junk():
    assert O.render_tail(None) == ""
    assert O.render_tail([None, 3, {"role": "user"}]) == ""


# --- decide_route ----------------------------------------------------------

async def test_decide_route_sends_a_text_only_request_with_the_voice_policy(monkeypatch):
    seen = {}
    real = O.execute_chat

    async def spy(request, resolved, **kwargs):
        seen["request"], seen["resolved"] = request, resolved
        return await real(request, resolved, **kwargs)

    monkeypatch.setattr(O, "execute_chat", spy)
    client = StubClient(decision_json([one_step()]))
    decision = await decide(client, note="n", tail="USER: earlier")
    request = seen["request"]
    assert request.workload == "orchestration"
    assert request.data_policy == APPROVED
    assert request.tools == () and request.temperature is None
    assert request.timeout_s == O.DECISION_TIMEOUT_S
    assert request.task_id.startswith("hand-off:")
    assert request.context[0].role == "system" and request.context[0].content == "SYSTEM"
    assert "save a note that the plumber comes Tuesday" in request.instructions
    assert seen["resolved"].model == "claude-fable-5-2"
    assert decision.model == "claude-fable-5-2"
    sent = client.calls[0]
    assert "tools" not in sent and "max_tokens" not in sent and "temperature" not in sent


@pytest.mark.usefixtures("subscription_without_carry")
async def test_confidential_context_is_refused_before_any_client_call():
    client = StubClient(decision_json([one_step()]))
    with pytest.raises(O.DecisionError) as err:
        await decide(client, policy=DataPolicy("confidential", "x"))
    assert err.value.reason == "orchestrator_route_refused" and not err.value.retryable
    assert client.calls == []


async def test_bad_output_then_success_is_one_retry_by_the_handler():
    client = StubClient("I would use the librarian.", decision_json([one_step()]))
    attempts = []

    async def decider(**kw):
        attempts.append(1)
        return await decide(client, transcript=kw["transcript"])

    _, handler = O.build_hand_off_tool(
        _echo_handler, agent_names=AGENTS, system_prompt="S", user_text=lambda: "save a note", decide=decider)
    out = await handler({})
    assert len(attempts) == 2 and not out.startswith("FAILED")


async def test_unavailable_retries_once_then_fails_tagged():
    client = StubClient(TimeoutError())
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert len(client.calls) == 2
    assert out.startswith("FAILED: routing did not finish in time. No work was started.")
    assert _tag(out) == ("transient", "orchestrator_unavailable")


async def test_provider_failure_retries_once():
    client = StubClient(SubscriptionRuntimeError("x", category="provider_failure"))
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert len(client.calls) == 2
    assert out.startswith("FAILED: the routing model did not answer. No work was started.")
    assert _tag(out) == ("transient", "orchestrator_unavailable")


async def test_unreadable_answer_retries_once_then_fails_tagged():
    client = StubClient("no json here")
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert len(client.calls) == 2
    assert out.startswith("FAILED: the routing model's answer could not be read. No work was started.")
    assert _tag(out) == ("transient", "orchestrator_bad_output")


async def test_invalid_decision_is_not_retried():
    client = StubClient(decision_json([one_step("plumber")]))
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert len(client.calls) == 1
    assert out.startswith("FAILED: the routing decision was not valid, so it was not used. No work was started.")
    assert _tag(out) == ("approach", "orchestrator_invalid_decision")


@pytest.mark.parametrize("category", ["allowance", "credit"])
async def test_quota_is_not_retried(category):
    client = StubClient(SubscriptionRuntimeError("x", category=category))
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert len(client.calls) == 1
    assert out.startswith("FAILED: the subscription usage limit was reached. No work was started.")
    assert _tag(out) == ("policy", "orchestrator_quota")


async def test_route_error_is_not_retried():
    client = StubClient(decision_json([one_step()]))

    def refuse(_workload):
        raise ModelRouteError("route refused")

    attempts = []

    async def decider(**kw):
        attempts.append(1)
        return await decide(client, resolve_route=refuse)

    _, handler = O.build_hand_off_tool(
        _echo_handler, agent_names=AGENTS, system_prompt="S", user_text=lambda: "hi", decide=decider)
    out = await handler({})
    assert attempts == [1] and client.calls == []
    assert out.startswith("FAILED: routing is not allowed or not available for this turn. No work was started.")
    assert _tag(out) == ("policy", "orchestrator_route_refused")


@pytest.mark.parametrize("category", ["authentication", "capability", "runtime_unavailable", "policy", "cleanup"])
async def test_other_runtime_categories_are_a_tagged_runtime_error(category):
    client = StubClient(SubscriptionRuntimeError("provider text must not leak", category=category))
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert len(client.calls) == 1
    assert f"({category})" in out and "provider text" not in out
    assert _tag(out) == ("approach", "orchestrator_runtime_error")


async def test_unexpected_exception_is_a_runtime_error_with_only_its_type_name():
    client = StubClient(KeyError("secret user words"))
    _, handler = _tool_with_client(client)
    out = await handler({})
    assert "KeyError" in out and "secret user words" not in out
    assert _tag(out) == ("approach", "orchestrator_runtime_error")


# --- the handler -----------------------------------------------------------

class Recorder:
    def __init__(self, results=None, delay=0.0):
        self.calls = []
        self.results = results or {}
        self.delay = delay
        self.active = 0
        self.peak = 0

    async def __call__(self, arguments):
        self.calls.append(dict(arguments))
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self.results.get(arguments["agent_name"], f"done by {arguments['agent_name']}")
        finally:
            self.active -= 1


async def _echo_handler(arguments):
    return f"done by {arguments['agent_name']}"


def fixed(decision):
    async def decider(**kwargs):
        decider.kwargs = kwargs
        return decision
    return decider


def _tool(step_handler, decision, *, user_text="remind me about the car", **extra):
    decider = fixed(decision)
    schema, handler = O.build_hand_off_tool(
        step_handler, agent_names=AGENTS, system_prompt="S", user_text=lambda: user_text,
        decide=decider, **extra)
    return schema, handler, decider


def _tool_with_client(client):
    async def decider(**kw):
        return await decide(client, transcript=kw["transcript"])

    return O.build_hand_off_tool(
        _echo_handler, agent_names=AGENTS, system_prompt="S",
        user_text=lambda: "save a note that the plumber comes Tuesday", decide=decider)


def _tag(text):
    match = FAILURE_TAG_RE.search(text)
    return (match.group(1), match.group(2)) if match else None


def test_schema_shape_matches_the_delegate_tool():
    schema, _ = O.build_hand_off_tool(_echo_handler, agent_names=AGENTS, system_prompt="S",
                                      user_text=lambda: "")
    delegate_schema, _ = build_delegate_tool({"librarian": FakeSubAgent("librarian")})
    assert set(schema) == set(delegate_schema) == {"type", "function"}
    function = schema["function"]
    assert function["name"] == "hand_off"
    assert set(function) == set(delegate_schema["function"])
    assert function["parameters"]["required"] == []
    assert list(function["parameters"]["properties"]) == ["note"]
    assert function["parameters"]["properties"]["note"]["type"] == "string"


async def test_single_step_result_comes_first_then_provenance():
    recorder = Recorder()
    _, handler, _ = _tool(recorder, O.Decision((O.Step("librarian", "Save it."),), "", "claude-fable-5-2"))
    out = await handler({"note": "plumber"})
    assert out == "done by librarian\n[routed by claude-fable-5-2: librarian]"


async def test_two_steps_run_concurrently_and_combine():
    recorder = Recorder(delay=0.05)
    decision = O.Decision((O.Step("librarian", "Save."), O.Step("scheduler", "Remind.")), "", "m")
    _, handler, _ = _tool(recorder, decision)
    started = time.perf_counter()
    out = await handler({})
    assert time.perf_counter() - started < 0.09
    assert recorder.peak == 2
    assert out == ("[librarian]\ndone by librarian\n\n[scheduler]\ndone by scheduler\n\n"
                   "[routed by m: librarian, scheduler]")


async def test_step_arguments_pass_through_exactly():
    recorder = Recorder()
    decision = O.Decision((
        O.Step("developer", "Plan it.", model_profile="claude-fable-5", continuation=True,
               findings_path="/tmp/f.md"),
        O.Step("librarian", "Save."),
    ), "", "m")
    _, handler, _ = _tool(recorder, decision)
    await handler({})
    assert recorder.calls == [
        {"agent_name": "developer", "task": "Plan it.", "model_profile": "claude-fable-5",
         "continuation": True, "findings_path": "/tmp/f.md"},
        {"agent_name": "librarian", "task": "Save."},
    ]


async def test_the_decider_gets_exact_words_note_tail_and_policy():
    recorder = Recorder()
    decision = O.Decision((O.Step("librarian", "Save."),), "", "m")
    messages = [{"role": "user", "content": "earlier ask"}, {"role": "assistant", "content": "ok"}]
    policy = DataPolicy("approved_external", "complete-voice-context")
    _, handler, decider = _tool(recorder, decision, user_text="  the exact words  ",
                                conversation=lambda: messages, context_policy=lambda: policy,
                                session_id="s1")
    await handler({"note": "line one\nline two " + "x" * 400})
    kwargs = decider.kwargs
    assert kwargs["transcript"] == "the exact words"
    assert kwargs["note"].startswith("line one line two x") and len(kwargs["note"]) == O.NOTE_MAX_CHARS
    assert kwargs["tail"] == "USER: earlier ask\nASSISTANT: ok"
    assert kwargs["data_policy"] == policy and kwargs["session_id"] == "s1"
    assert kwargs["agent_names"] == AGENTS and kwargs["system_prompt"] == "S"


async def test_a_missing_or_failing_context_policy_falls_back_to_confidential():
    decision = O.Decision((O.Step("librarian", "Save."),), "", "m")

    def boom():
        raise RuntimeError("no context")

    for provider in (None, boom):
        _, handler, decider = _tool(Recorder(), decision, context_policy=provider,
                                    conversation=boom)
        await handler({})
        assert decider.kwargs["data_policy"].level == "confidential"
        assert decider.kwargs["tail"] == ""


async def test_ask_user_starts_no_work():
    recorder = Recorder()
    _, handler, _ = _tool(recorder, O.Decision((), "What should I remind you about?", "m"))
    out = await handler({})
    assert out.startswith("ASK_USER: What should I remind you about?\nNo work was started.")
    assert out.endswith("[routed by m: ask_user]")
    assert recorder.calls == []


async def test_decision_failure_starts_no_work_and_carries_the_tag():
    recorder = Recorder()

    async def failing(**kwargs):
        raise O.DecisionError("orchestrator_invalid_decision", detail="unknown_agent")

    _, handler = O.build_hand_off_tool(recorder, agent_names=AGENTS, system_prompt="S",
                                       user_text=lambda: "hi", decide=failing)
    out = await handler({})
    assert out.startswith("FAILED:") and "No work was started." in out
    assert _tag(out) == ("approach", "orchestrator_invalid_decision")
    assert recorder.calls == []


async def test_all_failed_combined_starts_with_failed():
    recorder = Recorder({"librarian": "FAILED: no disk", "scheduler": "FAILED: no clock"})
    decision = O.Decision((O.Step("librarian", "a"), O.Step("scheduler", "b")), "", "m")
    _, handler, _ = _tool(recorder, decision)
    out = await handler({})
    assert out.startswith("FAILED: every part of this request failed.")
    assert "[librarian]\nFAILED: no disk" in out


async def test_one_failure_among_several_is_not_a_blanket_failure():
    recorder = Recorder({"librarian": "FAILED: no disk"})
    decision = O.Decision((O.Step("librarian", "a"), O.Step("scheduler", "b")), "", "m")
    _, handler, _ = _tool(recorder, decision)
    assert not (await handler({})).startswith("FAILED")


async def test_single_failed_step_keeps_startswith_failed():
    recorder = Recorder({"librarian": "FAILED: no disk\n[failure class: approach; reason: tool_exception]"})
    _, handler, _ = _tool(recorder, O.Decision((O.Step("librarian", "a"),), "", "m"))
    out = await handler({})
    assert out.startswith("FAILED: no disk") and _tag(out) == ("approach", "tool_exception")


async def test_classified_results_keep_the_strictest_policy():
    private = ClassifiedText("secret", DataPolicy("confidential", "mail"))
    plain = ClassifiedText("fine", DataPolicy("approved_external", "web"))
    recorder = Recorder({"librarian": private, "scheduler": plain})
    decision = O.Decision((O.Step("librarian", "a"), O.Step("scheduler", "b")), "", "m")
    _, handler, _ = _tool(recorder, decision)
    out = await handler({})
    assert type(out) is ClassifiedText
    assert text_policy(out).level == "confidential"
    single = O.combine_results(O.Decision((O.Step("librarian", "a"),), "", "m"), [private])
    assert type(single) is ClassifiedText and text_policy(single).level == "confidential"
    assert type(O.combine_results(O.Decision((O.Step("librarian", "a"),), "", "m"), ["plain"])) is str


async def test_empty_transcript_and_note_is_refused():
    recorder = Recorder()
    _, handler, decider = _tool(recorder, O.Decision((O.Step("librarian", "a"),), "", "m"), user_text="  ")
    out = await handler({"note": "   "})
    assert out == ("REFUSED: hand_off had nothing to route (no user words, no note). "
                   "No work was started.")
    assert recorder.calls == [] and not hasattr(decider, "kwargs")


async def test_a_note_alone_is_enough_to_route():
    recorder = Recorder()
    _, handler, _ = _tool(recorder, O.Decision((O.Step("librarian", "a"),), "", "m"), user_text="")
    assert (await handler({"note": "save a note"})).startswith("done by librarian")


async def test_nothing_the_user_said_is_logged(caplog):
    caplog.set_level("DEBUG")
    recorder = Recorder()
    decision = O.Decision((O.Step("librarian", "TASKSECRET"),), "", "m")
    _, handler, _ = _tool(recorder, decision, user_text="TRANSCRIPTSECRET",
                          conversation=lambda: [{"role": "user", "content": "TAILSECRET"}])
    await handler({"note": "NOTESECRET"})
    logged = caplog.text
    for secret in ("TASKSECRET", "TRANSCRIPTSECRET", "TAILSECRET", "NOTESECRET"):
        assert secret not in logged
    assert "hand_off_decision" in logged


# --- guards run unmodified through hand_off --------------------------------

def _real_tool(agents, decision, **delegate_kwargs):
    _, delegate = build_delegate_tool(agents, **delegate_kwargs)
    _, handler, _ = _tool(delegate, decision)
    return handler


async def test_unknown_model_profile_is_refused_by_the_existing_handler():
    agent = FakeSubAgent("developer", override_refused="profile 'nope' cannot be resolved")
    handler = _real_tool({"developer": agent}, O.Decision(
        (O.Step("developer", "Plan it.", model_profile="nope"),), "", "m"))
    out = await handler({})
    assert out.startswith("REFUSED: profile 'nope' cannot be resolved")
    assert agent.tasks == []


async def test_retry_guard_still_refuses_through_hand_off():
    agent = ScriptedAgent("developer", ["FAILED: could not read the log", "second"])
    task = "investigate why the weather chip went stale yesterday evening"
    handler = _real_tool({"developer": agent}, O.Decision((O.Step("developer", task),), "", "m"))
    first = await handler({})
    assert first.startswith("FAILED: could not read the log")
    second = await handler({})
    assert second.startswith("REFUSED: this delegation was blocked by a safety guard")
    assert agent.tasks == [task]


async def test_unearned_continuation_is_ignored_by_the_existing_handler():
    """The step claims a continuation, but the agent never asked the user for
    anything, so the handler does not reset its retry guard."""
    agent = ScriptedAgent("developer", ["FAILED: could not read the log", "second"])
    task = "investigate why the weather chip went stale yesterday evening"
    handler = _real_tool({"developer": agent}, O.Decision(
        (O.Step("developer", task, continuation=True),), "", "m"))
    assert (await handler({})).startswith("FAILED")
    assert (await handler({})).startswith("REFUSED: this delegation was blocked by a safety guard")
    assert agent.tasks == [task]


async def test_unknown_agent_from_a_bypassing_decision_is_still_refused_by_delegate():
    agent = FakeSubAgent("librarian")
    handler = _real_tool({"librarian": agent}, O.Decision((O.Step("ghost", "x"),), "", "m"))
    assert "Unknown agent 'ghost'" in await handler({})


# --- barge-in --------------------------------------------------------------

async def test_cancel_during_the_decision_starts_nothing():
    recorder = Recorder()
    entered = asyncio.Event()

    async def slow_decider(**kwargs):
        entered.set()
        await asyncio.sleep(10)

    _, handler = O.build_hand_off_tool(recorder, agent_names=AGENTS, system_prompt="S",
                                       user_text=lambda: "hi", decide=slow_decider)
    turn = asyncio.create_task(handler({}))
    await entered.wait()
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    assert recorder.calls == []


async def test_cancel_during_the_steps_orphans_each_and_late_delivers():
    one = SlowFakeSubAgent("librarian", delay=0.05, result="saved late")
    two = SlowFakeSubAgent("scheduler", delay=0.05, result="set late")
    delivered = []

    async def deliver(text):
        delivered.append(text)

    handler = _real_tool({"librarian": one, "scheduler": two}, O.Decision(
        (O.Step("librarian", "Save."), O.Step("scheduler", "Remind.")), "", "m"),
        late_delivery={"fn": deliver})
    turn = asyncio.create_task(handler({}))
    await asyncio.sleep(0.01)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    await asyncio.sleep(0.15)
    assert one.finished_at is not None and two.finished_at is not None
    assert len(delivered) == 2
    assert any("saved late" in d for d in delivered) and any("set late" in d for d in delivered)
