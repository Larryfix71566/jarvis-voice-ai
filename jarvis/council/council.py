"""D6.1 prompts + council orchestration (D1's council.py): fan-out,
anonymize, score, select, log. The only module in jarvis/council/ that
talks to models or the database — scoring.py and config.py's pure helpers
stay importable without network.

A council may rank, review, and advise; it may NEVER author a merged
artifact (§0.1.1). This module only ever assembles a prose brief — the
winning Proposal's `content` — for the caller to hand to a single model.
It never produces or touches a diff.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from jarvis.agents.upgrade_agent import available_models, load_model_registry
from jarvis.council import config as council_config
from jarvis.council.scoring import council_size_ok, mean_of, parse_scores, select_winner
from jarvis.council.types import Proposal, RoundResult, Score
from jarvis.db import get_conn, now_iso
from jarvis.prompts import PLAN_AUTHOR_PROMPT, PLAN_REVIEW_PROMPT

logger = logging.getLogger(__name__)

# ⚙ TUNING KNOB (D12)
COUNCIL_MEMBER_TIMEOUT_S = 120
COUNCIL_PREVIEW_CHARS = 2000

COUNCIL_LOG_DIR = Path("logs/council")

# D11 — the kill switch's single enforcement point.
KILL_SWITCH_ENV = "JARVIS_COUNCIL_ENABLED"

# ⚙ TUNING KNOB — MORTIMER_LLM_COUNCIL_V2_PLAN.md V7. True runs the
# shadow pass inline (tests; deterministic CLI runs). False (default)
# detaches it onto its own daemon thread so the live result returns
# without waiting on an advisory measurement.
COUNCIL_SHADOW_INLINE = False

# V7 test seam: the most recently started shadow-pass thread (or None if
# no round has run detached yet, or the last one ran inline). Tests
# `join(timeout=...)` this to deterministically wait for the detached
# pass to finish before asserting on its writes — production code never
# reads this.
_last_shadow_thread: threading.Thread | None = None


def _council_enabled() -> bool:
    """Read directly from the environment so convene() has no hard
    dependency on constructing a full Settings object; jarvis/config.py's
    `jarvis_council_enabled` field reads the same variable for the rest
    of the app, so the two can never disagree on the default (true)."""
    value = os.environ.get(KILL_SWITCH_ENV)
    if value is None:
        return True
    return value.strip().lower() not in ("false", "0", "no")


# D6.1 — the two prompts, verbatim. Not left to the implementer.

PROPOSER_PROMPT = """You are one member of a council of AI models advising on \
a software change to the Mortimer codebase.

A previous attempt at this goal FAILED. You are being asked for a corrected \
approach.

Your output is a PLAN IN PROSE, read by another model that will write the \
actual code. Therefore:
- Do NOT output file contents, diffs, or code blocks longer than a few \
illustrative lines.
- DO state: what went wrong, what to do differently, which files to touch, \
and in what order.
- Be concrete and specific. Vague advice ("refactor carefully") is useless \
to the implementer.
- If you believe the goal cannot be achieved within the stated constraints, \
say so plainly and explain why — that is a valid and useful answer.

Keep your response under 400 words."""

JUDGE_PROMPT = """You are evaluating competing proposals for how to fix a \
failed software change.

You did NOT write any of these proposals. Judge them on merit alone.

Score EVERY proposal listed below on a scale of 1.0 to 10.0, using ONE \
decimal place. Use the full range: 1.0 means actively harmful, 5.0 means \
mediocre, 10.0 means excellent. Avoid clustering every proposal around the \
same value — the point of this exercise is to discriminate between them.

Judge on:
- Does it correctly diagnose why the previous attempt failed?
- Would following it actually fix the problem?
- Is it specific enough for another model to implement without guessing?
- Does it stay within the stated constraints?

Your response MUST end with a section in EXACTLY this format:

SCORES:
Proposal A: 7.4 - one-line justification
Proposal B: 8.1 - one-line justification

One line per proposal. Score every proposal shown. Do not add any other \
text after the SCORES section."""

# V14 — the scope-advisor prompt pair, verbatim. Selected instead of the
# pair above when placement == "scope" (E2: a declined, off-allowlist goal).

SCOPE_ADVISOR_PROMPT = """You are one member of a council of AI models \
advising on the Mortimer voice assistant's self-edit system.

The self-edit agent DECLINED the goal below because it requires changes \
outside its allowlist. Your job is to analyse scope, not to write code.

You are given the goal, the agent's stated reason for declining, and the \
allowlist configuration (allow patterns and deny patterns; deny always \
wins).

Your output is a SCOPING ANALYSIS IN PROSE, read by a human deciding what \
to do next. State:
- Which specific parts of the goal fall OUTSIDE the allowlist, and which \
deny/allow patterns they hit.
- Which subset of the goal IS achievable entirely within the allowlist, \
if any. Be honest: "none of it" is a valid and useful answer.
- A suggested rephrasing of the goal narrowed to the achievable subset, \
written so it could be given to the agent as-is.
- What the human would need to develop themselves for the remainder.

Do NOT output file contents, diffs, or code. Keep your response under \
300 words."""

SCOPE_JUDGE_PROMPT = """You are evaluating competing scoping analyses of \
a goal that a self-edit agent declined as outside its allowlist.

You did NOT write any of these analyses. Judge them on merit alone.

Score EVERY proposal listed below on a scale of 1.0 to 10.0, using ONE \
decimal place. Use the full range and avoid clustering scores.

Judge on:
- Does it correctly identify which parts of the goal are inside vs \
outside the allowlist, per the patterns shown?
- Is the proposed achievable subset genuinely achievable within the \
allowlist as written?
- Is the suggested narrowed goal concrete enough to hand to the agent \
without edits?
- Is it honest where the answer is "none of this is achievable"?

Your response MUST end with a section in EXACTLY this format:

SCORES:
Proposal A: 7.4 - one-line justification
Proposal B: 8.1 - one-line justification

One line per proposal. Score every proposal shown. Do not add any other \
text after the SCORES section."""

# MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — the planning pathway's judge
# prompt, used ONLY by draft_candidates below (never by convene()). A
# fresh plan has no prior failed attempt to diagnose, so JUDGE_PROMPT's
# "why did the previous attempt fail" framing does not apply; this is the
# same kind of companion prompt SCOPE_JUDGE_PROMPT already is for the
# scope-advisor placement. Scores here are advisory only — draft_candidates
# never calls select_winner; the user chooses (record_user_choice).
PLAN_JUDGE_PROMPT = """You are evaluating competing implementation-plan documents for the same goal.

You did NOT write any of these plans. Judge them on merit alone. Your scores are advisory — a human will make the final choice, not you.

Score EVERY proposal listed below on a scale of 1.0 to 10.0, using ONE \
decimal place. Use the full range: 1.0 means unusable, 5.0 means mediocre, \
10.0 means excellent. Avoid clustering every proposal around the same \
value — the point of this exercise is to discriminate between them.

Judge on:
- Is every decision actually made, with nothing left for the implementer \
to guess?
- Does it correctly and completely address the stated goal?
- Is the implementation order sound and the file list accurate?
- Is it honest about risks and about anything left out of scope?

Your response MUST end with a section in EXACTLY this format:

SCORES:
Proposal A: 7.4 - one-line justification
Proposal B: 8.1 - one-line justification

One line per proposal. Score every proposal shown. Do not add any other \
text after the SCORES section."""


# --------------------------------------------------------------- transport

async def _call_profile(
    profile: dict[str, Any], system_prompt: str, user_content: str,
    timeout_s: float,
) -> tuple[str, dict[str, int] | None]:
    """One OpenAI-compatible chat completion for one registry profile.
    Raises on any failure (missing key, network error, timeout) — callers
    are responsible for turning that into an explicit abstention/dropped-
    proposal record (§0.1.5), never a silent skip.

    MORTIMER_LLM_COUNCIL_V2_PLAN.md V9 — returns `(content, usage)`.
    `usage` is `{"prompt_tokens": int, "completion_tokens": int}` taken
    from `response.usage` when the provider reports both fields, else
    `None` (some OpenAI-compatible providers omit it entirely — never
    fabricated)."""

    def _sync_call() -> tuple[str, dict[str, int] | None]:
        from openai import OpenAI

        api_key_env = profile.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} is not set")
        client = OpenAI(api_key=api_key, base_url=profile.get("base_url"))
        request: dict[str, Any] = {
            "model": profile["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        temperature = profile.get("temperature")
        if temperature is not None:  # None omits the parameter (D-003)
            request["temperature"] = temperature
        response = client.chat.completions.create(**request)
        content = response.choices[0].message.content or ""
        usage_obj = getattr(response, "usage", None)
        usage: dict[str, int] | None = None
        if usage_obj is not None:
            prompt_tokens = getattr(usage_obj, "prompt_tokens", None)
            completion_tokens = getattr(usage_obj, "completion_tokens", None)
            if prompt_tokens is not None and completion_tokens is not None:
                usage = {
                    "prompt_tokens": int(prompt_tokens),
                    "completion_tokens": int(completion_tokens),
                }
        return content, usage

    return await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=timeout_s)


def _proposer_user_message(goal: str, context: dict[str, Any], placement: str) -> str:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V2 (supersedes v1 D6.1's assembly
    clause) / V14. Branches on `placement` at exactly one point — never
    on which context keys happen to be present (§0.1.4's "never infer
    from prose/payload shape" discipline): `placement == "scope"` uses
    V14's GOAL / DECLINE REASON / ALLOWLIST template; every other
    placement uses V2's GOAL / FAILURE CONTEXT / CHECKS template."""
    if placement == "scope":
        parts = [f"GOAL:\n{goal}"]
        if context.get("reason") is not None:
            parts.append(f"DECLINE REASON:\n{context['reason']}")
        if context.get("allowlist") is not None:
            parts.append(
                f"SELF-EDIT ALLOWLIST (deny always wins):\n{context['allowlist']}"
            )
        return "\n\n".join(str(p) for p in parts)
    parts = [f"GOAL:\n{goal}"]
    if context.get("diff") is not None:
        parts.append(f"FAILURE CONTEXT — the attempt being corrected:\n{context['diff']}")
    if context.get("checks") is not None:
        parts.append(f"VALIDATION CHECKS:\n{context['checks']}")
    if context.get("document") is not None:
        # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R3 — additive branch: a
        # review job's context carries the (already-truncated) document
        # under review. convene() never sets this key, so escalation
        # rounds are untouched.
        parts.append(
            f"DOCUMENT UNDER REVIEW ({context.get('document_path')}):\n"
            f"{context['document']}"
        )
    return "\n\n".join(str(p) for p in parts)


def _judge_user_message(
    goal: str, context: dict[str, Any], proposals: list[Proposal], placement: str,
) -> str:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V2 (supersedes v1 D6.1's assembly
    clause) / V14: same placement-branching rule as
    `_proposer_user_message`, then each proposal as 'Proposal <label>:
    <content>', in label order. No proposer profile name ever appears
    here in either branch."""
    if placement == "scope":
        parts = [f"GOAL:\n{goal}"]
        if context.get("reason") is not None:
            parts.append(f"DECLINE REASON:\n{context['reason']}")
        if context.get("allowlist") is not None:
            parts.append(
                f"SELF-EDIT ALLOWLIST (deny always wins):\n{context['allowlist']}"
            )
        for p in proposals:
            parts.append(f"{p.label}:\n{p.content}")
        return "\n\n".join(parts)
    parts = [f"GOAL:\n{goal}"]
    if context.get("diff") is not None:
        parts.append(f"FAILURE CONTEXT — the attempt being corrected:\n{context['diff']}")
    if context.get("checks") is not None:
        parts.append(f"VALIDATION CHECKS:\n{context['checks']}")
    if context.get("document") is not None:
        # R3 — same additive branch as _proposer_user_message, so a
        # council-mode review's judges see the document too.
        parts.append(
            f"DOCUMENT UNDER REVIEW ({context.get('document_path')}):\n"
            f"{context['document']}"
        )
    for p in proposals:
        parts.append(f"{p.label}:\n{p.content}")
    return "\n\n".join(parts)


def _empty_usage_totals() -> dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "reported_calls": 0}


def _add_usage(totals: dict[str, int], usage: dict[str, int] | None) -> None:
    if usage is None:
        return
    totals["prompt_tokens"] += usage.get("prompt_tokens", 0)
    totals["completion_tokens"] += usage.get("completion_tokens", 0)
    totals["reported_calls"] += 1


async def _gather_proposals(
    names: list[str], profiles_by_name: dict[str, dict[str, Any]],
    user_content: str, system_prompt: str = PROPOSER_PROMPT,
    usage_by_name: dict[str, dict[str, int] | None] | None = None,
    *, timeout_s: float = COUNCIL_MEMBER_TIMEOUT_S,
) -> tuple[list[Proposal], dict[str, int]]:
    """Fan out `system_prompt` (V14: PROPOSER_PROMPT or, for a scope
    round, SCOPE_ADVISOR_PROMPT — `_convene_inner` selects the pair once
    at the top and passes it down here rather than letting this function
    import a constant, so there is exactly one selection site) to each
    proposer, in order. A proposer that errors or times out simply
    produces no Proposal — logged, and reflected in a shrunk
    proposer_count, never hidden.

    MORTIMER_LLM_COUNCIL_V2_PLAN.md V4: labels are NOT assigned here.
    Returned proposals carry `label=""`; `_convene_inner` is the single
    site that assigns real labels, after a deterministic per-round
    shuffle (so registry order — knowable to anyone who reads
    config/upgrade_models.yaml — never leaks into label order) and after
    any V1 carried proposal has been appended.

    V9 — the return type's second element is
    `{"prompt_tokens": int, "completion_tokens": int, "reported_calls":
    int}`, summed over only the calls whose response carried usage
    (§3's fixed multi-consumer contract). `usage_by_name`, if given, is
    populated in place with each proposer's raw per-call usage (or
    None) — an internal-only extension used by `_convene_inner` to
    attach per-proposal `"usage"` to the JSONL payload (V9's "each
    proposal record gains a usage field"), which the fixed 2-element
    return contract has no room for; callers that don't need it (e.g.
    `__main__.py`'s replay path has no proposer pass) simply omit it."""

    async def _one(name: str) -> tuple[str, str | None, dict[str, int] | None]:
        try:
            content, usage = await _call_profile(
                profiles_by_name[name], system_prompt, user_content,
                timeout_s,
            )
            return name, content, usage
        except Exception as exc:  # noqa: BLE001 — never raise into convene()
            logger.warning("council_proposer_failed profile=%s error=%s", name, exc)
            return name, None, None

    results = await asyncio.gather(*(_one(n) for n in names))
    proposals = [
        Proposal(label="", profile=name, content=content)
        for name, content, _usage in results
        if content is not None
    ]
    totals = _empty_usage_totals()
    for name, content, usage in results:
        if usage_by_name is not None:
            usage_by_name[name] = usage
        if content is None:
            continue
        _add_usage(totals, usage)
    return proposals, totals


def _shuffle_and_label(
    round_id: str, proposals: list[Proposal], carried_ids: frozenset[int] = frozenset(),
) -> tuple[list[Proposal], set[str]]:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V4 — the ONLY place labels are
    assigned. Deterministic per round (seeded from `round_id`, same
    derivation family as `should_shadow`): a replay of the same round
    reconstructs the same labels, but a judge cannot infer proposer
    identity from label order the way it could when labels tracked
    registry order 1:1. Uses a private `random.Random` instance, never
    the global `random` module, so nothing else in the process is
    affected and tests need no monkeypatching.

    `carried_ids` (V1) is the set of `id()` values of pre-shuffle
    Proposal objects that came from a carry-forward, not fan-out;
    `Proposal` carries no `carried` field of its own (unchanged by the
    v2 signature ledger), so identity is tracked out-of-band and
    returned as the set of final labels that are carried — the only
    consumer is `_write_payload`'s JSONL `"carried"` field."""
    rng = random.Random(
        int.from_bytes(hashlib.sha256(round_id.encode("utf-8")).digest()[:8], "big")
    )
    shuffled = list(proposals)
    rng.shuffle(shuffled)
    labeled: list[Proposal] = []
    carried_labels: set[str] = set()
    for i, p in enumerate(shuffled):
        label = f"Proposal {chr(ord('A') + i)}"
        if id(p) in carried_ids:
            carried_labels.add(label)
        labeled.append(Proposal(label=label, profile=p.profile, content=p.content))
    return labeled, carried_labels


async def _gather_scores(
    judge_names: list[str], profiles_by_name: dict[str, dict[str, Any]],
    judge_user_content: str, labels: list[str], *, shadow: bool,
    system_prompt: str = JUDGE_PROMPT,
    usage_by_name: dict[str, dict[str, int] | None] | None = None,
    timeout_s: float = COUNCIL_MEMBER_TIMEOUT_S,
) -> tuple[list[Score], dict[str, int]]:
    """Fan out `system_prompt` (V14: JUDGE_PROMPT or, for a scope round,
    SCOPE_JUDGE_PROMPT — selected once by the caller, same rule as
    `_gather_proposals`) to each judge. A judge that errors or times out
    is an EXPLICIT abstention on every label (§0.1.5) — never silently
    dropped, unlike a failed proposer (which has no scoring concept to
    abstain on).

    V9 — same usage contract and `usage_by_name` out-parameter as
    `_gather_proposals` (see its docstring); a failed judge call
    contributes no usage (None). The caller decides whether this pass's
    totals count toward the round row (`_convene_inner` sums only the
    live pass, per V9; V7's `_shadow_pass` persists the shadow pass's
    usage separately, via its own additive UPDATE)."""

    async def _one(name: str) -> tuple[list[Score], dict[str, int] | None]:
        try:
            raw, usage = await _call_profile(
                profiles_by_name[name], system_prompt, judge_user_content,
                timeout_s,
            )
            return parse_scores(name, raw, labels), usage
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "council_judge_failed profile=%s shadow=%s error=%s",
                name, shadow, exc,
            )
            return [
                Score(judge_profile=name, proposal_label=lbl, value=None,
                     abstain_reason=f"judge call failed: {exc}")
                for lbl in labels
            ], None

    results = await asyncio.gather(*(_one(n) for n in judge_names))
    out: list[Score] = []
    totals = _empty_usage_totals()
    for name, (scores, usage) in zip(judge_names, results):
        out.extend(scores)
        if usage_by_name is not None:
            usage_by_name[name] = usage
        _add_usage(totals, usage)
    return out, totals


# ------------------------------------------------------------------ convene

async def convene(
    *, workflow: str, placement: str, trigger: str, goal: str, tier: int,
    context: dict, run_id: str | None = None,
) -> RoundResult | None:
    """Run one council round. Returns None on ANY structural failure
    (kill switch off, no usable profiles, an unexpected exception) — D13.
    Returns a RoundResult with `winner=None` when the round ran to
    completion but selected nobody (council_too_small after fan-out, or
    no proposal received a valid score) — callers must check BOTH
    `result is None` and `result.winner is None` (D2.1's `_maybe_escalate`
    does exactly this). `context` carries placement-specific input (for
    E1: keys 'diff' and 'checks'). Writes the D8 rows and JSONL itself.
    Never raises."""
    if not _council_enabled():
        return None
    try:
        return await _convene_inner(
            workflow=workflow, placement=placement, trigger=trigger,
            goal=goal, tier=tier, context=context, run_id=run_id,
        )
    except Exception:  # noqa: BLE001 — D13, never raise into the agent loop
        logger.warning("council_convene_failed", exc_info=True)
        return None


async def _convene_inner(
    *, workflow: str, placement: str, trigger: str, goal: str, tier: int,
    context: dict, run_id: str | None,
) -> RoundResult:
    round_id = uuid.uuid4().hex
    started_at = now_iso()
    started_monotonic = time.monotonic()

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V14 — the ONE prompt-pair selection
    # site. Every gather call in this round (proposer fan-out, live
    # judges, and the shadow pass) is handed one of these two pairs;
    # nothing downstream re-derives it from context shape.
    if placement == "scope":
        proposer_system_prompt, judge_system_prompt = (
            SCOPE_ADVISOR_PROMPT, SCOPE_JUDGE_PROMPT,
        )
    else:
        proposer_system_prompt, judge_system_prompt = PROPOSER_PROMPT, JUDGE_PROMPT

    registry = load_model_registry()
    profiles_by_name: dict[str, dict[str, Any]] = registry.get("profiles", {})
    registry_order = list(profiles_by_name.keys())

    def _sort_by_registry(names: list[str]) -> list[str]:
        return sorted(
            names,
            key=lambda n: registry_order.index(n) if n in registry_order else len(registry_order),
        )

    # D9/D10 wire-format completion: a manual convene from the console
    # (jarvis/admin/server.py's POST /api/council/convene) may narrow
    # membership per tier name. Carried in `context` rather than as a new
    # parameter, since D1.1 fixes convene()'s signature and `context` is
    # already documented as carrying placement-specific input. Absent for
    # every automatic (E1/E2/E3) escalation — those always use full tier
    # membership, unaffected by this.
    selected = context.get("members") if isinstance(context, dict) else None

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — read the carry early: judge
    # resolution happens BEFORE proposal fan-out, and the carried
    # profile must be excluded from the judge pool exactly like a
    # fan-out proposer.
    carry = context.get("carry_forward") if isinstance(context, dict) else None
    carry_profile = {str(carry["profile"])} if carry and carry.get("profile") else set()

    try:
        proposer_names = _sort_by_registry(
            # seed=round_id — TIER_PARTITION rotates which frontier profiles
            # are reserved as judges. BOTH calls must pass the SAME seed or
            # the two roles disagree about the split and it stops being one.
            council_config.resolve_members(
                tier, "proposers", selected=selected, seed=round_id)
        )
    except council_config.NoUsableProfilesError as exc:
        return _finalize_too_small(
            round_id=round_id, run_id=run_id, workflow=workflow,
            placement=placement, trigger=trigger, tier=tier, goal=goal,
            proposer_count=0, judge_count=0,
            reason=f"no usable proposers: {exc}", started_at=started_at,
        )

    try:
        judge_names = _sort_by_registry(
            council_config.resolve_members(
                tier, "judges", selected=selected,
                exclude=set(proposer_names) | carry_profile,
                seed=round_id,
            )
        )
    except council_config.NoUsableProfilesError as exc:
        return _finalize_too_small(
            round_id=round_id, run_id=run_id, workflow=workflow,
            placement=placement, trigger=trigger, tier=tier, goal=goal,
            proposer_count=len(proposer_names), judge_count=0,
            reason=f"no usable judges: {exc}", started_at=started_at,
        )

    if not council_size_ok(
        len(proposer_names), len(judge_names),
        min_proposers=council_config.COUNCIL_MIN_PROPOSERS,
        min_judges=council_config.COUNCIL_MIN_JUDGES,
    ):
        return _finalize_too_small(
            round_id=round_id, run_id=run_id, workflow=workflow,
            placement=placement, trigger=trigger, tier=tier, goal=goal,
            proposer_count=len(proposer_names), judge_count=len(judge_names),
            reason=(
                f"council_too_small: {len(proposer_names)} proposers, "
                f"{len(judge_names)} judges (need >= "
                f"{council_config.COUNCIL_MIN_PROPOSERS}/"
                f"{council_config.COUNCIL_MIN_JUDGES})"
            ),
            started_at=started_at,
        )

    proposer_user_content = _proposer_user_message(goal, context, placement)
    proposer_usage_by_name: dict[str, dict[str, int] | None] = {}
    proposals, proposer_usage = await _gather_proposals(
        proposer_names, profiles_by_name, proposer_user_content,
        proposer_system_prompt, usage_by_name=proposer_usage_by_name,
    )

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — the carried proposal is a real
    # candidate: it counts toward proposer_count and the post-fan-out
    # size check below. If the carried profile also proposed fresh this
    # round, both proposals are kept (judges score proposals, not
    # models — select_winner's D5 backstop only excludes that profile's
    # scores, never its proposals).
    carried_ids: frozenset[int] = frozenset()
    if carry and carry.get("content"):
        carried_proposal = Proposal(
            label="",  # real label assigned by the V4 shuffle below
            profile=str(carry.get("profile") or "unknown"),
            content=str(carry["content"]),
        )
        proposals.append(carried_proposal)
        carried_ids = frozenset({id(carried_proposal)})

    if not council_size_ok(
        len(proposals), len(judge_names),
        min_proposers=council_config.COUNCIL_MIN_PROPOSERS,
        min_judges=council_config.COUNCIL_MIN_JUDGES,
    ):
        return _finalize_too_small(
            round_id=round_id, run_id=run_id, workflow=workflow,
            placement=placement, trigger=trigger, tier=tier, goal=goal,
            proposer_count=len(proposals), judge_count=len(judge_names),
            reason=(
                f"council_too_small after fan-out: only {len(proposals)} of "
                f"{len(proposer_names)} proposers responded"
            ),
            started_at=started_at,
        )

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V4 — the single labeling site. Runs
    # after the post-fan-out council_size_ok check (which only consumes
    # counts, never labels/content) and after V1's carried proposal has
    # been appended, so the carried proposal never needs its own
    # labeling logic.
    proposals, carried_labels = _shuffle_and_label(round_id, proposals, carried_ids)

    labels = [p.label for p in proposals]
    judge_user_content = _judge_user_message(goal, context, proposals, placement)
    judge_usage_by_name: dict[str, dict[str, int] | None] = {}
    live_scores, live_usage = await _gather_scores(
        judge_names, profiles_by_name, judge_user_content, labels, shadow=False,
        system_prompt=judge_system_prompt, usage_by_name=judge_usage_by_name,
    )

    # V9 — the round row's token totals sum only the proposer + live-
    # judge passes (never replay, never shadow — the shadow pass's own
    # usage is not yet persisted; V7 adds that via its own UPDATE). NULL
    # when nothing reported usage at all, never zero.
    reported_calls = proposer_usage["reported_calls"] + live_usage["reported_calls"]
    if reported_calls > 0:
        round_prompt_tokens = proposer_usage["prompt_tokens"] + live_usage["prompt_tokens"]
        round_completion_tokens = (
            proposer_usage["completion_tokens"] + live_usage["completion_tokens"]
        )
    else:
        round_prompt_tokens = None
        round_completion_tokens = None

    winner, reason = select_winner(proposals, live_scores, registry_order)
    winner_mean = None if winner is None else mean_of(winner.label, live_scores)
    abstentions = sum(1 for s in live_scores if s.value is None)

    ended_at = now_iso()
    latency_ms = int((time.monotonic() - started_monotonic) * 1000)
    status = "ok" if winner is not None else "failed"

    # V7 — live scores only (see RoundResult.scores' docstring); the
    # shadow pass, decided and launched below, never merges into this.
    result = RoundResult(
        round_id=round_id, winner=winner, winner_mean=winner_mean,
        select_reason=reason, proposals=proposals,
        scores=live_scores,
        abstentions=abstentions, tier=tier,
    )

    profile_tiers = {name: prof.get("tier") for name, prof in profiles_by_name.items()}
    _write_round_row(
        round_id=round_id, run_id=run_id, workflow=workflow, placement=placement,
        trigger=trigger, tier=tier, goal=goal,
        proposer_count=len(proposals), judge_count=len(judge_names),
        abstentions=abstentions, winner=winner, winner_mean=winner_mean,
        select_reason=reason, status=status, started_at=started_at,
        ended_at=ended_at, latency_ms=latency_ms,
        prompt_tokens=round_prompt_tokens, completion_tokens=round_completion_tokens,
        registry_order=registry_order,
        # K6 — asked vs answered. len(proposer_names) is who was invited;
        # len(proposals) is who came back. _gather_proposals drops a failed
        # member with only a log line, so without this pair a round gutted
        # by a dead credential is indistinguishable from a small one.
        proposers_attempted=len(proposer_names),
        judges_attempted=len(judge_names),
    )
    label_to_profile = {p.label: p.profile for p in proposals}
    _write_score_rows(
        round_id, live_scores, profile_tiers, label_to_profile, shadow=False,
    )
    proposal_usage_by_profile = dict(proposer_usage_by_name)
    payload_path = _payload_path(round_id, started_at)
    _write_payload(
        round_id=round_id, workflow=workflow, placement=placement,
        trigger=trigger, tier=tier, goal=goal, context=context,
        proposals=proposals, live_scores=live_scores,
        result=result, started_at=started_at, ended_at=ended_at,
        carried_labels=carried_labels,
        proposal_usage_by_profile=proposal_usage_by_profile,
        score_usage_by_profile=judge_usage_by_name,
        registry_order=registry_order,
    )

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V7 — shadow judging, off the live
    # path. Advisory-only, sampled deterministically, NEVER consulted by
    # select_winner above (which already ran and was written, on
    # live_scores alone). The *decision* (should_shadow, tier-name
    # resolution, exclusion set) stays inline and cheap; only the
    # execution (network calls + writes) is deferred/detached.
    shadow_tier_name = council_config.shadow_tier_name(tier)
    if shadow_tier_name and council_config.should_shadow(round_id, tier):
        try:
            shadow_judge_names = council_config.resolve_tier_name_members(
                shadow_tier_name,
                exclude=set(proposer_names) | set(judge_names),
            )
        except Exception:  # noqa: BLE001 — D8.2.1, never degrades the round
            logger.warning("council_shadow_failed round_id=%s", round_id, exc_info=True)
            shadow_judge_names = []
        if shadow_judge_names:
            if COUNCIL_SHADOW_INLINE:
                await _shadow_pass(
                    round_id, shadow_judge_names, profiles_by_name,
                    judge_user_content, labels, profile_tiers, label_to_profile,
                    payload_path, judge_system_prompt=judge_system_prompt,
                )
            else:
                global _last_shadow_thread
                thread = threading.Thread(
                    target=lambda: asyncio.run(_shadow_pass(
                        round_id, shadow_judge_names, profiles_by_name,
                        judge_user_content, labels, profile_tiers,
                        label_to_profile, payload_path,
                        judge_system_prompt=judge_system_prompt,
                    )),
                    daemon=True,
                )
                thread.start()
                _last_shadow_thread = thread

    return result


def _finalize_too_small(
    *, round_id: str, run_id: str | None, workflow: str, placement: str,
    trigger: str, tier: int, goal: str, proposer_count: int,
    judge_count: int, reason: str, started_at: str,
) -> RoundResult:
    """A round that never got far enough to fan out to any model. Cheap
    to log (no LLM cost incurred), and D8's status enum has `too_small`
    specifically for this case."""
    logger.info("council_too_small round_id=%s reason=%s", round_id, reason)
    ended_at = now_iso()
    _write_round_row(
        round_id=round_id, run_id=run_id, workflow=workflow, placement=placement,
        trigger=trigger, tier=tier, goal=goal, proposer_count=proposer_count,
        judge_count=judge_count, abstentions=0, winner=None, winner_mean=None,
        select_reason=reason, status="too_small", started_at=started_at,
        ended_at=ended_at, latency_ms=0,
    )
    return RoundResult(
        round_id=round_id, winner=None, winner_mean=None, select_reason=reason,
        proposals=[], scores=[], abstentions=0, tier=tier,
    )


# ------------------------------------------------------- planning pathway
# MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — additive: convene()/select_winner
# above are UNCHANGED by everything below (self-edit escalation behavior
# cannot change). draft_candidates never calls select_winner; the round
# stays workflow="planning" and awaits a human's record_user_choice call.

async def draft_candidates(
    goal: str, *, members: dict[str, list[str]] | None = None, judge: bool = True,
    context: dict | None = None,
) -> RoundResult | None:
    """Fan out PLAN_AUTHOR_PROMPT to every usable proposer (or the subset
    named in `members["proposers"]`) and, when `judge` is True, score the
    results ADVISORILY with the same judge machinery convene() uses (V4
    label shuffle, V6 parsing) — narrowed to `members["judges"]` if given.
    Returns None on any structural failure (kill switch off, unexpected
    exception), matching convene()'s D13 contract. Returns a RoundResult
    with `winner=None` always — this function never selects a winner; a
    human does, via record_user_choice. Never raises.

    MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R3 — `context` is optional and
    additive (default None -> {}, so every existing caller is unchanged).
    When `context["document"]` is present this is a REVIEW job: proposers
    and judges use PLAN_REVIEW_PROMPT/PLAN_JUDGE_PROMPT instead of
    PLAN_AUTHOR_PROMPT, the document is injected via the shared
    `_proposer_user_message`/`_judge_user_message` assembly, and the
    round is written with `placement="review"` instead of `"doc"`."""
    if not _council_enabled():
        return None
    try:
        return await _draft_candidates_inner(
            goal, members=members, judge=judge, context=context or {},
        )
    except Exception:  # noqa: BLE001 — D13, never raise into the caller
        logger.warning("council_draft_candidates_failed", exc_info=True)
        return None


async def _draft_candidates_inner(
    goal: str, *, members: dict[str, list[str]] | None, judge: bool,
    context: dict,
) -> RoundResult:
    round_id = uuid.uuid4().hex
    started_at = now_iso()
    started_monotonic = time.monotonic()

    is_review = context.get("document") is not None
    placement = "review" if is_review else "doc"
    proposer_system_prompt = PLAN_REVIEW_PROMPT if is_review else PLAN_AUTHOR_PROMPT

    registry = load_model_registry()
    profiles_by_name: dict[str, dict[str, Any]] = registry.get("profiles", {})
    registry_order = list(profiles_by_name.keys())

    def _sort_by_registry(names: list[str]) -> list[str]:
        return sorted(
            names,
            key=lambda n: registry_order.index(n) if n in registry_order else len(registry_order),
        )

    # V2-P7: proposer set = the FULL registry's key-present profiles by
    # default, NOT tier-1 only (unlike convene(), which always resolves
    # through the escalation tier ladder) — the user is paying deliberate
    # attention here, per Larry's 2026-08-17 clarification.
    proposer_names = [m["name"] for m in available_models() if m["key_present"]]
    picked_proposers = (members or {}).get("proposers") or []
    if picked_proposers:
        proposer_names = [n for n in proposer_names if n in picked_proposers]
    proposer_names = _sort_by_registry(proposer_names)

    if not proposer_names:
        return _finalize_too_small(
            round_id=round_id, run_id=None, workflow="planning", placement=placement,
            trigger="user", tier=0, goal=goal, proposer_count=0, judge_count=0,
            reason="no usable proposers for planning", started_at=started_at,
        )

    proposer_user_content = _proposer_user_message(goal, context, "doc")
    proposer_usage_by_name: dict[str, dict[str, int] | None] = {}
    proposals, proposer_usage = await _gather_proposals(
        proposer_names, profiles_by_name, proposer_user_content,
        proposer_system_prompt, usage_by_name=proposer_usage_by_name,
        timeout_s=council_config.PLANNING_MEMBER_TIMEOUT_S,
    )

    if not proposals:
        return _finalize_too_small(
            round_id=round_id, run_id=None, workflow="planning", placement=placement,
            trigger="user", tier=0, goal=goal, proposer_count=len(proposer_names),
            judge_count=0,
            reason=(
                f"no proposer responded: 0 of {len(proposer_names)} produced a plan"
            ),
            started_at=started_at,
        )

    # V4 — the single labeling site, same as convene()'s (no carry-forward
    # concept in the planning pathway).
    proposals, _carried_labels = _shuffle_and_label(round_id, proposals)
    labels = [p.label for p in proposals]

    judge_names: list[str] = []
    live_scores: list[Score] = []
    judge_usage_by_name: dict[str, dict[str, int] | None] = {}
    live_usage = _empty_usage_totals()
    if judge:
        judge_names = [
            m["name"] for m in available_models()
            if m["key_present"] and m["name"] not in {p.profile for p in proposals}
        ]
        picked_judges = (members or {}).get("judges") or []
        if picked_judges:
            judge_names = [n for n in judge_names if n in picked_judges]
        judge_names = _sort_by_registry(judge_names)
        if judge_names:
            judge_user_content = _judge_user_message(goal, context, proposals, "doc")
            live_scores, live_usage = await _gather_scores(
                judge_names, profiles_by_name, judge_user_content, labels,
                shadow=False, system_prompt=PLAN_JUDGE_PROMPT,
                usage_by_name=judge_usage_by_name,
                timeout_s=council_config.PLANNING_MEMBER_TIMEOUT_S,
            )

    reported_calls = proposer_usage["reported_calls"] + live_usage["reported_calls"]
    if reported_calls > 0:
        round_prompt_tokens = proposer_usage["prompt_tokens"] + live_usage["prompt_tokens"]
        round_completion_tokens = (
            proposer_usage["completion_tokens"] + live_usage["completion_tokens"]
        )
    else:
        round_prompt_tokens = None
        round_completion_tokens = None

    ended_at = now_iso()
    latency_ms = int((time.monotonic() - started_monotonic) * 1000)
    abstentions = sum(1 for s in live_scores if s.value is None)

    # No select_winner call — P7's whole point: the council never picks
    # the winner in this pathway, a human does (record_user_choice).
    result = RoundResult(
        round_id=round_id, winner=None, winner_mean=None,
        select_reason=f"awaiting user choice among {len(proposals)} candidate(s)",
        proposals=proposals, scores=live_scores,
        abstentions=abstentions, tier=0,
    )

    profile_tiers = {name: prof.get("tier") for name, prof in profiles_by_name.items()}
    _write_round_row(
        round_id=round_id, run_id=None, workflow="planning", placement=placement,
        trigger="user", tier=0, goal=goal,
        proposer_count=len(proposals), judge_count=len(judge_names),
        abstentions=abstentions, winner=None, winner_mean=None,
        select_reason=result.select_reason, status="awaiting_user",
        started_at=started_at, ended_at=ended_at, latency_ms=latency_ms,
        prompt_tokens=round_prompt_tokens, completion_tokens=round_completion_tokens,
        registry_order=registry_order,
        proposers_attempted=len(proposer_names),
        judges_attempted=len(judge_names),
    )
    label_to_profile = {p.label: p.profile for p in proposals}
    _write_score_rows(round_id, live_scores, profile_tiers, label_to_profile, shadow=False)
    _write_payload(
        round_id=round_id, workflow="planning", placement=placement, trigger="user",
        tier=0, goal=goal, context=context, proposals=proposals, live_scores=live_scores,
        result=result, started_at=started_at, ended_at=ended_at,
        proposal_usage_by_profile=dict(proposer_usage_by_name),
        score_usage_by_profile=judge_usage_by_name,
        registry_order=registry_order, status="awaiting_user",
    )

    return result


def _profile_for_label_from_payload(round_id: str, started_at: str, label: str) -> str | None:
    """Reads the round's JSONL payload back to resolve a label to the
    profile that proposed it. council_scores only carries a label ->
    profile mapping when judging actually ran (judge=True and at least
    one usable judge); the payload's `proposal` records are the one place
    this mapping ALWAYS exists, judged or not — the same reason
    __main__.py's --replay reads the payload rather than council_scores
    for proposal content."""
    path = _payload_path(round_id, started_at)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") == "proposal" and record.get("label") == label:
            return record.get("profile")
    return None


def record_user_choice(round_id: str, label: str) -> None:
    """P7 — the human's choice among draft_candidates' parallel plans.
    This is the ONLY function that sets winner_* on a workflow="planning"
    round — the council's founding rule (rank, review, advise; NEVER
    select) survives because this is a human decision recorded, not a
    scoring outcome computed. Best-effort, like every other D8 writer
    here: a failure must never raise into the sidecar's request handler."""
    try:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM council_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if row is None or row["workflow"] != "planning":
                logger.warning(
                    "council_record_user_choice_bad_round round_id=%s", round_id,
                )
                return
            profile = _profile_for_label_from_payload(round_id, row["started_at"], label)
            if profile is None:
                logger.warning(
                    "council_record_user_choice_unknown_label round_id=%s label=%s",
                    round_id, label,
                )
                return
            conn.execute(
                "UPDATE council_rounds SET winner_label = ?, winner_profile = ?, "
                "select_reason = 'user choice', status = 'ok' WHERE round_id = ?",
                (label, profile, round_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning(
            "council_record_user_choice_failed round_id=%s", round_id, exc_info=True,
        )


# --------------------------------------------------------------------- D8

def _truncate(value: str | None, limit: int = COUNCIL_PREVIEW_CHARS) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[:limit]


def _write_round_row(
    *, round_id: str, run_id: str | None, workflow: str, placement: str,
    trigger: str, tier: int, goal: str, proposer_count: int, judge_count: int,
    abstentions: int, winner: Proposal | None, winner_mean: float | None,
    select_reason: str, status: str, started_at: str, ended_at: str | None,
    latency_ms: int | None,
    prompt_tokens: int | None = None, completion_tokens: int | None = None,
    registry_order: list[str] | None = None,
    proposers_attempted: int | None = None,
    judges_attempted: int | None = None,
) -> None:
    """V9 — `prompt_tokens`/`completion_tokens` are NULL (unknown) unless
    at least one member call in this round reported usage; never 0 —
    same discipline as `tools_ok`/`tools_failed` (MIGRATION_0008).

    V13 — `registry_order` (profile names in registry order at convene()
    time) is stored as a JSON array, NULL when not given (pre-v2 rows,
    or `_finalize_too_small`'s too-small-to-ever-resolve-a-registry
    case), so `agreement.py`/`--replay` can reproduce D7's rule-4
    tiebreak exactly instead of approximating it from row order.

    K6 — `proposers_attempted`/`judges_attempted` are how many members were
    ASKED; proposer_count/judge_count are how many answered. A member whose
    call fails is logged and dropped (`council_proposer_failed`), so without
    the pair a round that lost half its proposers to a dead credential looks
    identical to one that never had them. NULL when the caller does not know
    (pre-migration rows, `_finalize_too_small`'s never-resolved cases) —
    never 0, which would assert a fact instead of admitting a gap."""
    try:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO council_rounds (round_id, run_id, workflow, "
                "placement, trigger, tier, goal, proposer_count, judge_count, "
                "abstentions, winner_profile, winner_label, winner_mean, "
                "select_reason, status, started_at, ended_at, latency_ms, "
                "prompt_tokens, completion_tokens, registry_order, "
                "proposers_attempted, judges_attempted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    round_id, run_id, workflow, placement, trigger, tier,
                    _truncate(goal), proposer_count, judge_count, abstentions,
                    winner.profile if winner else None,
                    winner.label if winner else None,
                    winner_mean, _truncate(select_reason), status, started_at,
                    ended_at, latency_ms, prompt_tokens, completion_tokens,
                    json.dumps(registry_order) if registry_order is not None else None,
                    proposers_attempted, judges_attempted,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — a logging failure must not sink the round
        logger.warning("council_write_round_row_failed round_id=%s", round_id, exc_info=True)


def _write_score_rows(
    round_id: str, scores: list[Score], profile_tiers: dict[str, str | None],
    label_to_profile: dict[str, str], *, shadow: bool,
) -> None:
    """`label_to_profile` unmasks each score's anonymised `proposal_label`
    back to the profile that actually wrote it (D8's `proposal_profile`
    column, "unmasked at write time, post-selection") — the judge never
    saw this mapping; it is applied only here, after scoring is done."""
    if not scores:
        return
    try:
        conn = get_conn()
        try:
            created_at = now_iso()
            conn.executemany(
                "INSERT INTO council_scores (round_id, judge_profile, "
                "judge_tier, shadow, proposal_label, proposal_profile, "
                "score, abstain_reason, justification, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        round_id, s.judge_profile,
                        profile_tiers.get(s.judge_profile) or "unknown",
                        1 if shadow else 0, s.proposal_label,
                        label_to_profile.get(s.proposal_label, "unknown"),
                        s.value, s.abstain_reason,
                        _truncate(s.justification), created_at,
                    )
                    for s in scores
                ],
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning("council_write_score_rows_failed round_id=%s", round_id, exc_info=True)


def record_retry_validated(round_id: str, validated: bool) -> None:
    """D8.1 — write back whether the single post-council retry passed
    validation. This is the only way to answer "is the council earning
    its cost" from data instead of assertion. Best-effort: a write
    failure here must never raise into the agent loop."""
    try:
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE council_rounds SET retry_validated = ? WHERE round_id = ?",
                (1 if validated else 0, round_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning(
            "council_record_retry_validated_failed round_id=%s", round_id,
            exc_info=True,
        )


# ---------------------------------------------------------- read helpers
# D10: shared by the admin sidecar (jarvis/admin/server.py) and any future
# CLI/test caller, mirroring jarvis/runlog/store.py's convention of one
# shared implementation so two readers can never disagree.

def get_round(round_id: str) -> dict | None:
    """Full detail for one round: the council_rounds row plus its
    council_scores rows (live and shadow), newest score first."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (round_id,)
        ).fetchone()
        if row is None:
            return None
        scores = conn.execute(
            "SELECT * FROM council_scores WHERE round_id = ? ORDER BY id DESC",
            (round_id,),
        ).fetchall()
        return {"round": dict(row), "scores": [dict(s) for s in scores]}
    finally:
        conn.close()


def list_rounds(
    workflow: str | None = None, status: str | None = None,
    since: str | None = None, limit: int = 50,
) -> list[dict]:
    """Recent rounds, newest first. `since` must already be normalized
    (jarvis.runlog.store.parse_since) — this function does not parse it,
    same convention as jarvis.runlog.store.list_runs."""
    conn = get_conn()
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if workflow:
            clauses.append("workflow = ?")
            params.append(workflow)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since:
            clauses.append("started_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM council_rounds {where} ORDER BY started_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _payload_path(round_id: str, started_at: str) -> Path:
    """The one place a round's JSONL path is computed from (round_id,
    started_at) — shared by `_write_payload` (initial write) and V7's
    `_shadow_pass` (later append), so they can never disagree about
    where a round's payload lives."""
    date = started_at[:10]
    return COUNCIL_LOG_DIR / date / f"{round_id}.jsonl"


def _write_payload(
    *, round_id: str, workflow: str, placement: str, trigger: str, tier: int,
    goal: str, context: dict, proposals: list[Proposal],
    live_scores: list[Score],
    result: RoundResult, started_at: str, ended_at: str,
    carried_labels: set[str] = frozenset(),
    proposal_usage_by_profile: dict[str, dict[str, int] | None] | None = None,
    score_usage_by_profile: dict[str, dict[str, int] | None] | None = None,
    registry_order: list[str] | None = None,
    status: str | None = None,
) -> None:
    """Full, untruncated record for one round: mirrors logs/agents/'s
    two-tier pattern (jarvis/runlog/store.py). Read by
    jarvis/council/__main__.py's --replay (D8.2.2), which needs the full
    proposal texts to re-score with a different judge lineup.

    `carried_labels` (V1) marks which final `proposal` records came from
    a tier carry-forward rather than this round's fan-out. V9's
    `proposal_usage_by_profile`/`score_usage_by_profile` (keyed by the
    profile that made the call — the carried proposal and any profile
    absent from the map get `"usage": null`, exactly like a call whose
    provider omitted usage) attach each record's own token usage; both
    default to None so callers with nothing to report (there are none in
    council.py itself, but keeps the function usable standalone) still
    write valid `null` usage fields rather than raising.

    V7 — `shadow_scores` is GONE from this signature. This writes the
    live round only (round_start...round_end); the shadow pass, if any,
    appends its own `score` records to the same file afterward via
    `_shadow_pass`, on its own schedule. Record order in the JSONL is
    not semantic — every reader filters by `type`, not position — so a
    shadow record landing after `round_end` is correct, not a
    compromise."""
    try:
        path = _payload_path(round_id, started_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = [
            {
                "type": "round_start", "round_id": round_id, "workflow": workflow,
                "placement": placement, "trigger": trigger, "tier": tier,
                "goal": goal, "context": context, "started_at": started_at,
                "registry_order": registry_order,
            },
        ]
        for p in proposals:
            records.append({
                "type": "proposal", "label": p.label, "profile": p.profile,
                "content": p.content, "carried": p.label in carried_labels,
                "usage": (proposal_usage_by_profile or {}).get(p.profile),
            })
        for s in live_scores:
            records.append({
                "type": "score", "judge_profile": s.judge_profile,
                "proposal_label": s.proposal_label, "value": s.value,
                "justification": s.justification,
                "abstain_reason": s.abstain_reason, "shadow": False,
                "usage": (score_usage_by_profile or {}).get(s.judge_profile),
            })
        # MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — `status` override: a
        # planning round with judge=True can have live scores and yet no
        # winner (draft_candidates never calls select_winner), which the
        # old "ok" if result.winner else "failed" derivation would
        # mislabel as failed. Existing convene() callers pass nothing and
        # get the exact old behavior.
        records.append({
            "type": "round_end",
            "status": status if status is not None
                      else ("ok" if result.winner else "failed"),
            "winner_label": result.winner.label if result.winner else None,
            "winner_profile": result.winner.profile if result.winner else None,
            "winner_mean": result.winner_mean,
            "select_reason": result.select_reason, "ended_at": ended_at,
        })
        with path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, default=str))
                f.write("\n")
    except Exception:  # noqa: BLE001
        logger.warning("council_write_payload_failed round_id=%s", round_id, exc_info=True)


async def _shadow_pass(
    round_id: str, shadow_judge_names: list[str],
    profiles_by_name: dict[str, dict[str, Any]], judge_user_content: str,
    labels: list[str], profile_tiers: dict[str, str | None],
    label_to_profile: dict[str, str], payload_path: Path,
    *, judge_system_prompt: str = JUDGE_PROMPT,
) -> None:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V7 — the shadow pass's entire
    execution, extracted so it can run inline (tests, `COUNCIL_SHADOW_
    INLINE=True`) or detached on its own thread+event loop (default).
    Gathers shadow scores, writes them (`shadow=True`), appends its own
    JSONL score records (open mode "a"), and — V9 — folds its usage into
    the round row via a best-effort additive UPDATE (the round row may
    already show NULL from the live pass if nothing there reported
    usage; COALESCE treats that as 0 for the addition). Never raises —
    a shadow-pass failure is logged and simply means no shadow rows/
    usage for this round, exactly as when it ran inline.

    `judge_system_prompt` (V14, keyword-only with a default so the
    fixed positional shape this function had at V7 is unchanged):
    JUDGE_PROMPT for an ordinary round, or SCOPE_JUDGE_PROMPT when the
    round being shadowed has `placement == 'scope'` — the caller
    (`_convene_inner`) is the single selection site and passes the same
    value it used for the live judge pass, so a shadow judge is never
    scored against the wrong rubric."""
    shadow_usage_by_name: dict[str, dict[str, int] | None] = {}
    try:
        shadow_scores, shadow_usage = await _gather_scores(
            shadow_judge_names, profiles_by_name, judge_user_content, labels,
            shadow=True, system_prompt=judge_system_prompt,
            usage_by_name=shadow_usage_by_name,
        )
    except Exception:  # noqa: BLE001 — D8.2.1, never degrades the round
        logger.warning("council_shadow_failed round_id=%s", round_id, exc_info=True)
        return

    if shadow_scores:
        _write_score_rows(
            round_id, shadow_scores, profile_tiers, label_to_profile, shadow=True,
        )

    try:
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        with payload_path.open("a", encoding="utf-8") as f:
            for s in shadow_scores:
                record = {
                    "type": "score", "judge_profile": s.judge_profile,
                    "proposal_label": s.proposal_label, "value": s.value,
                    "justification": s.justification,
                    "abstain_reason": s.abstain_reason, "shadow": True,
                    "usage": shadow_usage_by_name.get(s.judge_profile),
                }
                f.write(json.dumps(record, default=str))
                f.write("\n")
    except Exception:  # noqa: BLE001
        logger.warning(
            "council_shadow_write_payload_failed round_id=%s", round_id, exc_info=True,
        )

    if shadow_usage.get("reported_calls", 0) > 0:
        try:
            conn = get_conn()
            try:
                conn.execute(
                    "UPDATE council_rounds SET "
                    "prompt_tokens = COALESCE(prompt_tokens, 0) + ?, "
                    "completion_tokens = COALESCE(completion_tokens, 0) + ? "
                    "WHERE round_id = ?",
                    (
                        shadow_usage["prompt_tokens"], shadow_usage["completion_tokens"],
                        round_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            logger.warning(
                "council_shadow_usage_update_failed round_id=%s", round_id, exc_info=True,
            )
