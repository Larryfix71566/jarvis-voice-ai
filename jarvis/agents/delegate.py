"""delegate_task tool factory (plan Phase 3, step 3.2; concurrency: Phase 4).

Returns the locked OpenAI tool schema plus an async handler that routes a
self-contained task to the named sub-agent.

Concurrency (plan Phase 4): pipecat's LLMService dispatches multiple
delegate_task calls emitted in one assistant turn concurrently by default
(run_in_parallel=True, group_parallel_tools=True — confirmed by reading
pipecat/services/llm_service.py; Mortimer's OpenAILLMService construction in
jarvis/bot/pipeline.py does not override either). SubAgent.run() has no
shared mutable per-instance state (jarvis/agents/base.py builds a fresh
`messages` list per call) and the MCP ClientSession multiplexes concurrent
requests by JSON-RPC id, so no new locking was needed for correctness — only
a bound, since pipecat's own parallel dispatch has none. `max_parallel`
gates actual sub-agent execution with a semaphore; delegate_start still
fires immediately so the UI shows "working" the instant the call arrives,
even if execution is briefly queued behind the cap.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Callable

from jarvis import keyhealth
from jarvis.agents.base import EventCallback, SubAgent
from jarvis.bot.sensitive_turn import current_sensitive_turn
from jarvis.model_routing import resolve_policy
from jarvis.procedures import _overlap_score, _tokens, learn_from_run
from jarvis.sensitive import detect_financial

logger = logging.getLogger(__name__)

DEFAULT_MAX_PARALLEL_DELEGATIONS = 3
PROTECTED_TASK_EVENT = "<protected task>"


def _task_for_event(agent_name: str, task: str) -> str:
    """Keep protected delegation prompts out of stdout and UI events.

    The agent still receives the complete task and its RunLogger applies the
    same policy to durable storage. This copy is only the activity/status
    surface, which previously printed the raw task before the run's privacy
    policy was consulted.
    """
    # The live turn/run logger has its own fail-closed sensitive-turn context;
    # this event surface cannot safely depend on that ContextVar because the
    # delegation may be detached from the voice turn. Use the workload policy
    # plus the shared financial detector for this bounded status copy.
    try:
        protected = resolve_policy(agent_name).privacy in {
            "confidential", "local_only"
        }
    except Exception:  # noqa: BLE001 - status emission must never block work
        protected = False
    if not protected:
        try:
            protected = detect_financial(task) is not None
        except Exception:  # noqa: BLE001 - status emission must never block work
            protected = True
    return PROTECTED_TASK_EVENT if protected else task

# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md A2 — the mechanical
# half of the stop rule: the Supervisor prompt asks it not to retry a
# failed delegation with reworded instructions, but a live session
# showed six such retries in a row (one inventing "vault credentials"),
# so a prompt alone cannot be trusted. Reuses the procedures module's
# own symmetric token-overlap scorer — one scoring implementation, not a
# second one invented here.
RETRY_GUARD_WINDOW_S = 120.0
RETRY_GUARD_OVERLAP = 0.5

# 2026-08-25 — a live incident (staging_id 469bff19ef49) showed the guard
# refusing the LEGITIMATE confirm-half of a two-phase flow, not a reworded
# retry: a preview call failed for an expected, benign reason ("nothing to
# preview yet"), and the very next call — actually confirming and starting
# the staged self-edit — necessarily shares most of its wording with that
# preview (same files, same goal, same staging_id), so it scored well
# above RETRY_GUARD_OVERLAP and was refused before ever reaching the agent.
# `_shares_long_identifier` is a narrow, low-false-positive carve-out: a
# shared token that is BOTH long and contains a digit is essentially
# always the same in-flight thing being confirmed (a staging_id, a
# commit-ish hash, a run_id), not a retry.
#
# The digit requirement is load-bearing and was added after the first cut
# of this fix — length alone was measured WRONG, and it broke the guard
# rather than narrowing it: ordinary developer wording shares 8+ char
# English words constantly ("implement", "component", "refactor",
# "configuration", "investigate" all measured as exempting a genuine
# reworded retry), so a length-only rule silently disabled the guard for
# most developer tasks — the exact class of task it exists to protect.
# No English word contains a digit; an identifier essentially always
# does. A uuid4 hex[:12] staging_id lacking any digit is ~1 in 200,000,
# and that case simply falls back to the pre-existing refusal, which is
# the safe direction.
#
# Deliberately NOT exempting short numeric ids (e.g. `action 35`):
# `_tokens()` already drops tokens under 3 chars, and a 2-digit id is
# common enough that guessing it apart from ordinary overlap would be a
# real false-positive risk. A 7-char short git hash is likewise below the
# length floor and is not exempted — conservative on purpose.
RETRY_GUARD_ID_TOKEN_MIN_LEN = 8


def _shares_long_identifier(a: set[str], b: set[str]) -> bool:
    """True if `a` and `b` share a token that looks like an identifier
    (a staging_id, a commit-ish hash) rather than an ordinary word two
    unrelated tasks both happen to use: long enough AND containing a
    digit, since no English word does."""
    return any(
        len(t) >= RETRY_GUARD_ID_TOKEN_MIN_LEN and any(c.isdigit() for c in t)
        for t in (a & b)
    )


# MORTIMER_SELF_SERVICE_ACCESS_IMPLEMENTATION_SPEC.md T1.1 (2026-09-22): the
# guard refused a CORRECTED input — "weather for Alfreda, Georgia" failed,
# and "weather for Alpharetta, Georgia" (Larry's correction) was refused
# twice at overlap 0.75, leaving the analyst unusable for two minutes. A
# single-word substitution is new input, not a reworded retry: a reworded
# retry either keeps every content word (a superset) or rewords several.
# Checked against every existing refusal fixture in test_delegate.py — all
# still refused.
RETRY_GUARD_CONTENT_TOKEN_MIN_LEN = 4
RETRY_GUARD_SUBSTITUTION_ENV = "JARVIS_RETRY_GUARD_SUBSTITUTION_ENABLED"


def _is_input_substitution(failed: set[str], new: set[str]) -> bool:
    """True when the new task drops EXACTLY ONE content token of the failed
    task and adds at least one content token the failed task lacked. A
    content token has len >= RETRY_GUARD_CONTENT_TOKEN_MIN_LEN. A corrected
    input (Alfreda -> Alpharetta) drops one word; a reworded retry either
    keeps every word (a superset) or rewords several (drops two or more)."""
    dropped = {t for t in failed - new if len(t) >= RETRY_GUARD_CONTENT_TOKEN_MIN_LEN}
    added = {t for t in new - failed if len(t) >= RETRY_GUARD_CONTENT_TOKEN_MIN_LEN}
    return len(dropped) == 1 and bool(added)


def _substitution_exemption_enabled() -> bool:
    """Single enforcement point for the T1.1 kill switch (default on)."""
    value = os.environ.get(RETRY_GUARD_SUBSTITUTION_ENV, "")
    return value.strip().lower() not in ("false", "0", "no")

# MORTIMER_HANDOFF_LOOP_PLAN.md H1/H2.
#
# The marker a sub-agent puts in its reply when it needs something only the
# user can get — a command's output, a value it cannot read. It is the
# AGENT's own word, produced by a different model run against a different
# prompt than the Supervisor's, which is what makes it usable as
# authorization: the Supervisor cannot forge permission for its own retry.
HANDOFF_MARKER = "NEEDS-INPUT:"

# T1.2 (2026-09-22) — the marker a sub-agent writes when no tool of its own
# can get what the task needs. It is a capability gap, not a failed approach
# and not a question for the user: it never arms the retry guard, never marks
# the agent as awaiting the user, and the Supervisor is told to name the gap
# (rule 10) instead of handing the user a command.
MISSING_TOOL_MARKER = "MISSING-TOOL:"
MISSING_TOOL_NOTE = (
    "\n\n[The specialist has no tool for this. Say so plainly per rule 10 "
    "and offer to have it added through self-development. Do not show or "
    "speak commands.]"
)

# H1.1 — matches ITERATIONS_EXHAUSTED_MESSAGE's opening. An exhausted
# budget is an unfinished job, not a failed approach, so it must not arm
# the retry guard.
EXHAUSTED_PREFIX = "FAILED: ran out of tool-call rounds"

# H1.4 — after this many handoffs on one investigation, the agent is asked
# to state where it stands before requesting anything more. Deliberately a
# NOTICE and not a cap: a cap is quitting on a timer, which is the thing
# this plan exists to stop.
HANDOFF_DEPTH_NOTICE = 4

# H2.2 — a findings document carried between runs. Bounded for the same
# reason REPO_MAP_MAX_CHARS is: it is prepended to a task the agent must
# still have room to work on.
FINDINGS_MAX_CHARS = 8000

# Procedures-as-hints (MORTIMER_MEMORY_PROCEDURES_PLAN.md D13): a bare
# asyncio.create_task(...) result has no strong reference anywhere else in
# this module, so without holding one here a background learn_from_run
# task could be garbage-collected — and silently cancelled — before it
# finishes. Module-level so it survives across concurrent delegations;
# add_done_callback discards each task's own reference once it completes.
_background_tasks: set[asyncio.Task] = set()

# 2026-09-05 — run_ids whose VOICE TURN is still awaiting a delegation.
# Distinct from _background_tasks above: that set keeps detached work alive,
# this one answers "is the assistant mid-tool-call right now?".
#
# Why it exists: inject_late_result (jarvis/bot/pipeline.py) used to call
# push_context_frame() unconditionally when an orphaned delegation finally
# landed. On 2026-09-05 that re-ran the model 0.8 s after a librarian
# delegate_task was issued and ~4.8 s before its result arrived, so the model
# saw its own "Storing that now" with no result and re-issued the store —
# one user request, two delegations, two notes (#22 and #23). Forcing a turn
# while a tool call is outstanding is the bug; the note can ride along with
# the generation that call's own completion triggers.
_foreground_delegations: set[str] = set()


# Item 11 (2026-09-17) -- how long session teardown waits for detached
# delegation runs before stopping the registry under them. A developer run
# measured 41 s on 2026-09-16; the agents' own iteration budgets bound the
# rest. Past this the registry is stopped anyway and the run's remaining
# tool calls fail -- the pre-fix behaviour, now logged instead of silent.
DETACHED_DRAIN_TIMEOUT_S = 120.0


async def drain_detached(in_flight: set, timeout: float) -> int:
    """Wait, bounded, for the session's detached delegation runs to finish.

    Barge-in survival keeps a sub-agent running after the voice turn that
    started it is cancelled -- and after the whole session ends, since
    nothing cancels the detached task at shutdown either. When the registry
    those runs call tools through is per-session (JARVIS_REGISTRY_SHARED_
    ENABLED=false; process-scoped by default since status spec T3.1),
    stopping it under a live run turns every remaining tool call into
    "Unknown tool ... Available: none" (measured 2026-09-16 11:45:33, a
    developer run eight seconds after the client disconnected). Teardown
    therefore drains first.

    Returns how many runs were still going at the deadline, so the caller
    can log that the teardown is about to fail them.
    """
    pending = {task for task in in_flight if not task.done()}
    if not pending:
        return 0
    logger.info("delegate_drain_started runs=%d timeout_s=%.0f", len(pending), timeout)
    done, still = await asyncio.wait(pending, timeout=timeout)
    if still:
        logger.warning(
            "delegate_drain_timeout runs=%d -- stopping the registry under "
            "them; their remaining tool calls will fail", len(still),
        )
    else:
        logger.info("delegate_drain_complete runs=%d", len(done))
    return len(still)


def foreground_delegation_count() -> int:
    """How many delegations the current voice turn is still awaiting.

    Zero means nothing is in flight and it is safe to force a generation
    (that is the normal case for a reminder or a late result). Non-zero
    means a tool call is outstanding and a pushed context frame would make
    the model answer with a hole where the result belongs.
    """
    return len(_foreground_delegations)


# Status spec T3.2 (L12) — what the outbox keeps for a late result from a
# protected (armed) turn: the fact that it finished, never its content, since
# the notice is spoken in a LATER session whose turn is not protected.
SENSITIVE_LATE_NOTICE = (
    "A background task you asked for finished; ask me for its result."
)


def _to_outbox(source: str, text: str) -> int:
    """T3.2 — queue an undeliverable late result in the notice outbox.

    One seam so tests (tests/conftest.py) can keep the orphaned-delegation
    path off the real database. jarvis.notices.add_notice never raises."""
    from jarvis import notices

    return notices.add_notice("late_result", source, text)


def _live_session_hook():
    """Review finding 5(b) — the process's current live session's hook."""
    from jarvis import notices

    return notices.live_session_hook()


def _late_note(display_name: str, outcome: str) -> str:
    """The context note a live session's model relays."""
    return (
        f"[system] Background update: the {display_name} "
        "task delegated earlier finished after the conversation "
        f"moved on. Result: {outcome}\nRelay this to the user once, "
        "in one or two short sentences, and do not repeat it in "
        "later turns. If it prepared an action that needs their "
        "confirmation, say so."
    )


def _outbox_text(display_name: str, outcome: str) -> str:
    """Review finding 5(c): what the outbox keeps — the result, not the
    relay instructions, so the 600-char notice budget holds the result."""
    return f"The {display_name} task finished: {outcome}"


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _read_findings(path: str, max_chars: int = FINDINGS_MAX_CHARS) -> str | None:
    """H2.2 — read a findings document, or None if it cannot be read.

    Goes through mcp_repo's own reader so path confinement and the secret
    deny-list apply identically here; a findings path is agent-supplied and
    must not become a way to read `.env`. Never raises.
    """
    try:
        from mcp_servers.mcp_repo import logic as repo_logic

        result = repo_logic.repo_read_file(path)
    except Exception:  # noqa: BLE001 — a bad path must not break a run
        logger.exception("delegate_findings_read_failed path=%s", path)
        return None
    if not isinstance(result, dict) or result.get("error"):
        logger.info("delegate_findings_unreadable path=%s reason=%s",
                    path, (result or {}).get("error") if isinstance(result, dict) else "?")
        return None
    content = str(result.get("content") or "").strip()
    if not content:
        return None
    return content[:max_chars]


def build_delegate_tool(
    sub_agents: dict[str, SubAgent],
    on_event: EventCallback | None = None,
    max_parallel: int = DEFAULT_MAX_PARALLEL_DELEGATIONS,
    *,
    session_id: str | None = None,
    late_delivery: dict | None = None,
    in_flight: set | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for delegate_task.

    Barge-in survival (Larry 2026-08-21: "me continuing to talk should not
    kill existing work" — observed live that morning: 5 of 9 developer runs
    were killed mid-flight by pipecat's function-call cancellation on user
    interruption, one AFTER its repo write had already executed, leaving
    zombie 'running' rows and no spoken result, which invited the re-ask
    that killed the next run too). The sub-agent run therefore executes in
    a DETACHED task the voice turn's cancellation cannot reach; the handler
    awaits it through asyncio.shield. On the normal path nothing changes.
    When the awaiting turn IS cancelled, the work continues, every piece of
    bookkeeping (run log terminal status, retry guard, handoff record,
    delegate_done event, learn_from_run) still happens inside the detached
    task, and the finished result is delivered to the conversation through
    `late_delivery["fn"]` — the inject_context hook run_session installs —
    so Mortimer reports it when it lands instead of losing it.
    """
    names = list(sub_agents)
    available = ", ".join(names)
    schema = {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": (
                "Delegate a specialist task to a sub-agent. The task must be "
                "fully self-contained; sub-agents cannot see this conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "enum": names},
                    "task": {
                        "type": "string",
                        "description": (
                            "Complete, self-contained instruction including "
                            "all facts needed."
                        ),
                    },
                    "continuation": {
                        "type": "boolean",
                        "description": (
                            "True ONLY when you are handing back results the "
                            "user just produced for this agent (command "
                            "output, a pasted value) after it asked for them. "
                            "Include the results in the task text. This is "
                            "refused if the agent's previous run did not "
                            "actually ask you for anything."
                        ),
                    },
                    "findings_path": {
                        "type": "string",
                        "description": (
                            "Repository path the agent's previous run wrote "
                            "its findings to, so it resumes instead of "
                            "starting over. Use the path that run returned."
                        ),
                    },
                    "model_profile": {
                        "type": "string",
                        "description": (
                            "Set ONLY when the user EXPLICITLY named a "
                            "specific model for this task (e.g. 'use "
                            "Fable', 'have the developer check with Opus', "
                            "'use Kimi for this'). Use the exact profile "
                            "name from the model list in your system "
                            "prompt — 2026-09-05: this description used to "
                            "restate that mapping and had drifted from the "
                            "registry, naming two profiles that do not "
                            "exist. One rendered list, no second copy. "
                            "Omit this field entirely otherwise — never "
                            "guess or default to a model the user did not "
                            "name. If the profile can't be resolved (wrong "
                            "name, missing credential), the run refuses "
                            "rather than silently using a different model — "
                            "report that refusal plainly, do not retry on "
                            "the default."
                        ),
                    },
                },
                "required": ["agent_name", "task"],
            },
        },
    }

    semaphore = asyncio.Semaphore(max(1, max_parallel))
    # A2 — per-session, per-agent: (task_tokens, failed_at_monotonic).
    # Session-scoped closure state, same lifetime as the semaphore above.
    last_failure: dict[str, tuple[set[str], float]] = {}
    # H1.2 — per-agent: did that agent's last run actually ASK the user for
    # something? A continuation is only legitimate after a real handoff, and
    # this is the record of one. Set from the run's own reply, never from the
    # Supervisor's claim.
    awaiting_user: dict[str, bool] = {}
    # H1.4 — handoffs taken in this session, for the honesty checkpoint. Not
    # a cap: Larry's rule is that quitting is unacceptable, and a limit is
    # quitting on a timer.
    handoff_depth: dict[str, int] = {}

    async def handler(arguments: dict) -> str:
        agent_name = str(arguments.get("agent_name", ""))
        task = str(arguments.get("task", ""))
        claims_continuation = bool(arguments.get("continuation"))
        findings_path = str(arguments.get("findings_path") or "").strip()
        model_profile = str(arguments.get("model_profile") or "").strip()
        # T3.2 — captured at delegation start: a late result from a protected
        # turn goes to the outbox redacted (SENSITIVE_LATE_NOTICE).
        holder = current_sensitive_turn.get()
        armed = bool(holder and holder.is_armed())
        agent = sub_agents.get(agent_name)
        if agent is None:
            # No agent, nothing ran — this path does not create a run
            # (run-logging plan §5.5).
            return f"Unknown agent '{agent_name}'. Available: {available}."

        # F6/F7 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md, 2026-08-22) —
        # a named per-run model request. Resolved HERE, before
        # delegate_start, so the Agents-tab chip shows the requested model
        # from the moment the card appears rather than the agent's
        # configured default; an unresolvable request refuses immediately
        # with no run row at all (F7's "before any run row or model
        # call"). agent.run() below resolves the SAME profile again
        # (resolve_model_profile is deterministic and does no I/O at
        # construction — see its docstring) — one source of truth, called
        # twice, not two.
        override_model = ""
        if model_profile:
            _preview_client, override_model, override_refused = (
                agent.resolve_model_profile(model_profile)
            )
            if override_refused:
                logger.info(
                    "delegate_override_refused agent=%s profile=%s",
                    agent_name, model_profile,
                )
                return f"REFUSED: {override_refused}"

        # H1.2 — the reset is EARNED, not claimed. A continuation is valid
        # only if this agent's previous run actually offered a handoff; that
        # is recorded from the reply itself (`awaiting_user`), so a
        # Supervisor that simply sets the flag gets nothing. Without this
        # condition, an unlimited handoff reset plus a self-declared marker
        # would be infinite guard-free retries — exactly what the guard
        # below exists to prevent, unbounded.
        continuation = claims_continuation and awaiting_user.get(agent_name, False)
        if claims_continuation and not continuation:
            logger.info(
                "delegate_continuation_unearned agent=%s — no handoff was "
                "recorded for this agent's previous run", agent_name,
            )

        prior = last_failure.get(agent_name)
        if prior is not None and not continuation:
            prior_tokens, failed_at = prior
            if time.monotonic() - failed_at < RETRY_GUARD_WINDOW_S:
                task_tokens = _tokens(task)
                overlap = _overlap_score(prior_tokens, task_tokens)
                if overlap >= RETRY_GUARD_OVERLAP and _shares_long_identifier(
                    prior_tokens, task_tokens,
                ):
                    logger.info(
                        "delegate_retry_guard_exempted_shared_id agent=%s "
                        "overlap=%.2f", agent_name, overlap,
                    )
                elif (overlap >= RETRY_GUARD_OVERLAP
                        and _substitution_exemption_enabled()
                        and _is_input_substitution(prior_tokens, task_tokens)):
                    logger.info(
                        "delegate_retry_guard_exempted_substitution agent=%s "
                        "overlap=%.2f", agent_name, overlap,
                    )
                elif overlap >= RETRY_GUARD_OVERLAP:
                    logger.info(
                        "delegate_retry_guard_refused agent=%s overlap=%.2f",
                        agent_name, overlap,
                    )
                    return (
                        f"REFUSED: this delegation was blocked by a safety "
                        f"guard because it overlaps too closely with the "
                        f"{agent_name} agent's immediately prior FAILED "
                        "task — the guard's only job is to stop a reworded "
                        "retry of a failed approach. This message says "
                        "NOTHING about any ID's validity or expiry, and "
                        "carries no other cause — relay this reason to the "
                        "user in your own words, but do not attribute the "
                        "refusal to an expired, invalid, or unrecognized "
                        "ID, or any other cause not stated here. Never "
                        "tell the user to wait; waiting changes nothing. "
                        "Change the approach or the input, or ask the user "
                        "what to change. If you "
                        "obtain NEW information the agent asked for (the "
                        "output of a command it gave the user), include it "
                        "in the task and set continuation to true; that is "
                        "not a retry."
                    )
        if continuation:
            handoff_depth[agent_name] = handoff_depth.get(agent_name, 0) + 1
            logger.info(
                "delegate_continuation agent=%s depth=%d findings_path=%s",
                agent_name, handoff_depth[agent_name], findings_path or "-",
            )

        # H2.2 — carry the prior run's findings forward. Read here, once,
        # synchronously, and REFUSE on a read failure rather than running a
        # continuation that silently starts from nothing: the same
        # read-and-refuse shape plan_path/review_path already use. Without
        # this a reset hands back 15 rounds that get spent re-deriving what
        # the last run already knew — in b74ed019 that was rounds 1-8.
        if findings_path:
            findings = _read_findings(findings_path)
            if findings is None:
                return (
                    f"REFUSED: could not read findings at {findings_path!r}. "
                    "Do not continue without them — re-state what is known "
                    "in the task itself, or omit findings_path."
                )
            task = (
                "Findings established by your previous run on this problem "
                f"(from {findings_path}) — continue from here rather than "
                f"starting over:\n\n{findings}\n\n---\n\n{task}"
            )
        # run_id generated here, one per delegation (run-logging plan D1):
        # this is the unit a human reviews, and generating it before the
        # semaphore below means a queued-but-not-yet-running delegation
        # still has an identity in the UI and the run log.
        run_id = str(uuid.uuid4())
        if on_event is not None:
            on_event({"type": "delegate_start", "agent": agent_name,
                      "display_name": agent.display_name,
                      "task": _task_for_event(agent_name, task),
                      "run_id": run_id,
                      # Larry 2026-08-19 — the Agents tab card header shows
                      # which LLM is doing the work. Read from the agent
                      # itself (the RESOLVED model, not config/agents.yaml's
                      # configured name), so a silent profile fallback is
                      # visible on screen rather than only in a log line.
                      # F8, 2026-08-22 — a named override (resolved above)
                      # takes precedence: it is what will ACTUALLY run, and
                      # is never a "fallback" (it was explicitly requested).
                      "model": override_model if model_profile else agent.model,
                      "model_fallback": False if model_profile else agent.model_is_fallback,
                      # K4 — the credential behind this model was
                      # actively refused or could not be billed. Distinct
                      # from a fallback: the profile resolved fine, so
                      # nothing upstream noticed anything wrong. Tied to
                      # the agent's CONFIGURED credential regardless of an
                      # override — keyhealth has no per-override signal
                      # yet, and an override that failed its own key check
                      # already refused above without reaching here.
                      "model_unusable": agent.model_unusable,
                      "model_unusable_detail": agent.model_unusable_detail})
        async def _execute() -> str:
            # Cap actual concurrent execution — pipecat's own parallel
            # tool-call dispatch has no limit. A failure inside agent.run()
            # (SubAgent.run() never raises; failures come back as
            # "FAILED: ..." strings) does not affect the semaphore or any
            # sibling delegation.
            async with semaphore:
                result = await agent.run(
                    task, on_event=on_event, run_id=run_id,
                    session_id=session_id,
                    model_profile_override=model_profile or None,
                )
            # F9 — the honesty backstop. "Checking with Fable now" was a
            # promise the Supervisor had no mechanism to keep (measured
            # live, 2026-08-22: the developer ran on its DEFAULT model
            # while the Supervisor announced Fable). This line is
            # APPENDED BY CODE, not authored by any model, so when the
            # Supervisor quotes it back it is grounded by construction —
            # it reports what the tool result names, not what it intended.
            if model_profile:
                result += f"\n[ran on {override_model}]"
            # D13: spawned unconditionally — D20 makes
            # jarvis_procedures_enabled a single-enforcement-point flag,
            # checked once inside learn_from_run itself (which loads its own
            # settings). A disabled flag still spawns a task, which returns
            # immediately as a no-op; this keeps delegate.py from reaching
            # into SubAgent's private _settings attribute to check the flag
            # redundantly.
            _spawn_background(learn_from_run(run_id, agent_name))
            failed = result.startswith("FAILED:")
            # Status spec T3.3 — a run that did not fail proves the agent's
            # own credential works right now, so a stale rejected/unfunded
            # verdict recovers without waiting for the refresh loop. Not for
            # a per-run override: that ran on a different credential. Not
            # for REFUSED:, which made no model call at all. getattr keeps
            # test fakes without the property working.
            if not failed and not model_profile and not result.startswith("REFUSED:"):
                key_env = getattr(agent, "api_key_env", "")
                if key_env:
                    keyhealth.note_success(key_env)
            # H1.1 — an exhausted iteration budget is NOT a failed approach,
            # it is an unfinished job; ITERATIONS_EXHAUSTED_MESSAGE says so
            # in those words. Arming the guard on it would refuse the one
            # thing that should happen next: continuing where it stopped.
            exhausted = result.startswith(EXHAUSTED_PREFIX)
            # H1.2 — did the agent itself ask the user for something? Read
            # from the agent's OWN reply, which the Supervisor does not
            # author, so a Supervisor cannot forge the authorization for its
            # own retry.
            awaiting_user[agent_name] = HANDOFF_MARKER in result or exhausted
            # T1.2 — a missing tool is a capability gap: it overrides the
            # failed handling below whether or not the reply starts FAILED:.
            missing_tool = MISSING_TOOL_MARKER in result
            if missing_tool:
                awaiting_user[agent_name] = False
                result += MISSING_TOOL_NOTE
            # A2 — a failure arms the guard for this agent; a success clears
            # it (the agent is demonstrably working again).
            if failed and not exhausted and not missing_tool:
                last_failure[agent_name] = (_tokens(task), time.monotonic())
            else:
                last_failure.pop(agent_name, None)
            if not failed and HANDOFF_MARKER not in result:
                # Resolved: the chain is over, so the depth counter starts
                # fresh for whatever Larry asks next.
                handoff_depth.pop(agent_name, None)
            # H1.4 — an honesty checkpoint, never a brake. Appended so the
            # Supervisor relays it; the run itself is unaffected.
            depth = handoff_depth.get(agent_name, 0)
            if depth >= HANDOFF_DEPTH_NOTICE and HANDOFF_MARKER in result:
                result += (
                    f"\n\n[This is handoff {depth} on this investigation. "
                    "Before asking for anything else, tell the user what you "
                    "have established, what you still do not know, and what "
                    "the next command would settle.]"
                )
            if on_event is not None:
                on_event({"type": "delegate_done", "agent": agent_name,
                          "display_name": agent.display_name,
                          "ok": not failed,
                          "run_id": run_id,
                          # Failure reasons surface in the UI status card;
                          # successful output is spoken/displayed elsewhere.
                          # Protected workloads keep the failure detail in
                          # the specialist result/run log, never this UI
                          # activity event.
                          "detail": (_task_for_event(agent_name, result[:300])
                                     if failed else "")})
            return result

        # Barge-in survival: the WORK runs in a detached task; only the
        # AWAIT below belongs to the voice turn. When the user speaks over
        # a delegation, pipecat cancels the function call — the shield lets
        # that cancellation land here without touching _execute, which
        # keeps running to completion (run log terminal status, guards,
        # delegate_done, all of it). The finished result is then handed to
        # late_delivery so the next thing Mortimer says can include it.
        run_task = asyncio.create_task(_execute())
        _background_tasks.add(run_task)
        run_task.add_done_callback(_background_tasks.discard)
        # Item 11: the session that owns this registry drains this set
        # before stopping it. Per-session on purpose -- _background_tasks is
        # module-level, shared across sessions, and also holds learn_from_run
        # and late-delivery tasks that teardown has no reason to wait on.
        if in_flight is not None:
            in_flight.add(run_task)
            run_task.add_done_callback(in_flight.discard)
        # The voice turn is now awaiting this call; see
        # foreground_delegation_count(). The finally below clears it on every
        # exit path INCLUDING the barge-in cancellation, because once the
        # await is cancelled the turn is no longer waiting on it.
        _foreground_delegations.add(run_id)
        try:
            return await asyncio.shield(run_task)
        except asyncio.CancelledError:
            if run_task.cancelled():
                # The work itself was cancelled (session shutdown), not
                # just this await — nothing survives to deliver.
                raise
            logger.info(
                "delegate_orphaned_by_interruption agent=%s run_id=%s — "
                "work continues; result will be delivered when it lands",
                agent_name, run_id,
            )

            def _outbox(outcome: str, reason: str) -> None:
                # T3.2 (L12): a result nobody can hear now is kept and
                # spoken after the greeting at the next connect.
                logger.warning(
                    "delegate_late_result_undeliverable agent=%s "
                    "run_id=%s reason=%s", agent_name, run_id, reason)
                notice_id = _to_outbox(
                    agent.display_name,
                    SENSITIVE_LATE_NOTICE if armed
                    else _outbox_text(agent.display_name, outcome))
                logger.info("delegate_late_result_outboxed agent=%s run_id=%s "
                            "notice_id=%s redacted=%s",
                            agent_name, run_id, notice_id, armed)

            async def _offer(fn: Callable, note: str) -> bool:
                try:
                    return await fn(note) is not False
                except Exception:  # noqa: BLE001 — never lose the result
                    logger.exception("delegate_late_delivery_failed agent=%s "
                                     "run_id=%s", agent_name, run_id)
                    return False

            async def _deliver_or_outbox(fn: Callable | None, note: str,
                                         outcome: str) -> None:
                # The hook returns False when its session has ended
                # (runtime.alive). Review finding 5(b): the session connected
                # NOW is tried next; only then does the result go to the
                # outbox.
                if fn is not None and await _offer(fn, note):
                    return
                live = _live_session_hook()
                if live is not None and live is not fn:
                    # Another, unprotected session: an armed turn's result
                    # is redacted there exactly as in the outbox.
                    elsewhere = (_late_note(agent.display_name, SENSITIVE_LATE_NOTICE)
                                 if armed else note)
                    if await _offer(live, elsewhere):
                        logger.info("delegate_late_result_redirected agent=%s "
                                    "run_id=%s redacted=%s",
                                    agent_name, run_id, armed)
                        return
                _outbox(outcome, "no_hook" if fn is None else "session_ended")

            def _deliver(task: asyncio.Task) -> None:
                if task.cancelled():
                    return
                exc = task.exception()
                outcome = f"FAILED: {exc}" if exc else task.result()
                note = _late_note(agent.display_name, outcome)
                fn = (late_delivery or {}).get("fn")
                _spawn_background(_deliver_or_outbox(fn, note, outcome))

            if run_task.done():
                _deliver(run_task)
            else:
                run_task.add_done_callback(_deliver)
            raise
        finally:
            _foreground_delegations.discard(run_id)

    return schema, handler
