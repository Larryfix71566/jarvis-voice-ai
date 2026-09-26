"""Voice workflows — MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 1 (D1-D9).

Authored workflows in config/workflows/ whose `agents:` list names
`supervisor` reach the VOICE agent at three moments, all rendering the
same guidance text (Workflow.as_prompt):

  user    a regex in `triggers.user` matches Larry's turn (pre-generation)
  result  a delegate_task result carries a kind in `triggers.result`
          (failed / needs_input / missing_tool / limitation)
  reply   the reply guard (jarvis/bot/voice_guidance.py) stopped a
          sentence of kind `triggers.reply` (refusal / handoff)

Everything here is pure and never raises into a voice turn. The regexes
are pinned by tests/fixtures/voice_failures.yaml: an edit that changes
what they match on the logged corpus fails tests/unit/test_voice_workflows.py.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jarvis.workflows import Workflow, load_workflows

logger = logging.getLogger(__name__)

SUPERVISOR = "supervisor"

# D6 — the reply guard's detectors. Pinned by the fixture; see §6 before
# editing. A sentence is a violation when REFUSE_RE or HANDOFF_RE matches
# and ALLOWED_RE does not (the sanctioned missing-tool sentence from
# SUPERVISOR_PROMPT rule 10).
REFUSE_RE = re.compile(r"""\b(?:I (?:can(?:no|')t|cannot|am unable to|'m unable to|am not able to|'m not able to|don't have (?:a tool|a way|access|the ability|any way)|do not have (?:a tool|a way|access)|have no (?:tool|way))|(?:that's|that is|it's) (?:outside|beyond) (?:what I|my)|isn't something I (?:can|have))""", re.I)
HANDOFF_RE = re.compile(r"""\b(?:you(?:'ll| will)? need to (?:run|open|check|edit|drag|kill|create|copy|tell|do|scroll|merge|pull|share)|you'd need to|run (?:this|that|the) (?:curl )?command|run the curl|copy (?:its|the) output|copy it(?:,| and)|say \"?read my clipboard|in your terminal|manually)|\brun `""", re.I)
ALLOWED_RE = re.compile(r"""isn't something I have a tool for yet""", re.I)
LIMITATION_RE = re.compile(r"""(?:\bMISSING[- ]TOOL:|\bI (?:have no|don't have (?:a|any)|do not have (?:a|any))\b[^.\n]{0,40}?\b(?:tool|way|access)\b|\bno tool (?:that|to|for)\b|\bisn't available to me\b|\bI cannot (?:query|run|execute|reach|access)\b|\bcan't execute\b)""", re.I)
CAPABILITY_QUESTION_RE = re.compile(
    r"\b(?:capabilit\w*|what can you do|what are you able to do)\b", re.I)
# D-L5 (Larry, 2026-09-25): when Larry explicitly asks to be given a command,
# Mortimer may show it (never a destructive one). Real asks from the log:
# "Give me the command to do that." (764), "Give me the commands again."
# (831), "Give me the commands without quotes." (833). Pushback such as
# "Are you unable to run that command yourself?" (2865) is NOT an ask.
EXPLICIT_COMMAND_ASK_RE = re.compile(
    r"\b(?:give|show|send|tell|write|get)\s+me\s+(?:the\s+|a\s+|an\s+|that\s+|those\s+|these\s+)?"
    r"(?:exact\s+|full\s+|actual\s+)?(?:(?:curl|shell|terminal|git)\s+)?(?:commands?|script)\b"
    r"|\bwhat(?:'s|\s+is|\s+are|\s+was|\s+were)\s+the\s+(?:exact\s+|full\s+)?"
    r"(?:(?:curl|shell|terminal|git)\s+)?commands?\b"
    r"|\b(?:i'll|i\s+will|let\s+me|i\s+can|i'd\s+rather|i\s+want\s+to)\s+run\s+"
    r"(?:it|that|this|them|the\s+commands?)\s+myself\b",
    re.I)
EXPLICIT_ASK_NEGATION_RE = re.compile(
    r"\b(?:don't|do\s+not|never|no\s+need\s+to|stop)\s+(?:\w+\s+){0,2}?"
    r"(?:give|show|send|tell|write|get)\s+me\b",
    re.I)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
SENTENCE_END_RE = re.compile(r"[.!?]\s")

RESULT_KINDS = ("failed", "needs_input", "missing_tool", "limitation")
REPLY_KINDS = ("refusal", "handoff")
NEEDS_INPUT_MARKER = "NEEDS-INPUT:"   # == jarvis.agents.delegate.HANDOFF_MARKER
MISSING_TOOL_MARKER = "MISSING-TOOL:"  # == jarvis.agents.delegate.MISSING_TOOL_MARKER
# Either spelling counts: Phase 1 prompts first taught "MISSING TOOL:"; #86
# (T1.2) settled on "MISSING-TOOL:", which is what delegate.py reads.
MISSING_TOOL_RE = re.compile(r"\bMISSING[- ]TOOL:")

GUIDANCE_PREFIX = "[system] "
TOMBSTONE = "[system] (Guidance for an earlier request was here; it no longer applies.)"
KIND_PHRASE = {
    "refusal": "told Larry you can't do something",
    "handoff": "asked Larry to do a step himself",
}
CORRECTION_TEMPLATE = (
    "[system] Your last reply was cut off before this sentence was spoken, "
    "because it {phrase}: \"{sentence}\". Answer the same request again. "
    "If any specialist in your list covers it, delegate it now with "
    "delegate_task and deliver the result. If a specialist has already "
    "reported MISSING-TOOL for it, say in one sentence that it isn't "
    "something you have a tool for yet and offer to have it added. Do not "
    "ask Larry to run a command, copy output, or edit a file."
)
GAP_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "capability_gaps.jsonl"
GAP_LOG_ENV = "JARVIS_CAPABILITY_GAP_LOG"   # evals point this at a temp file
NEEDS_INPUT_WINDOW_S = 600.0
DEFAULT_PRIORITY = 100
GUARD_MODES = ("off", "log", "correct")

_pattern_cache: dict[tuple[str, str], re.Pattern | None] = {}


def normalize_guard_mode(value: Any) -> str:
    """D16 — unknown values fall back to 'log', never to 'off' or 'correct'."""
    mode = str(value or "").strip().lower()
    return mode if mode in GUARD_MODES else "log"


def split_sentences(text: str | None) -> list[str]:
    return [s for s in SENTENCE_SPLIT_RE.split((text or "").strip()) if s]


def sentence_violation(sentence: str | None) -> str | None:
    """'refusal', 'handoff', or None. Refusal is checked first."""
    if not sentence or ALLOWED_RE.search(sentence):
        return None
    if REFUSE_RE.search(sentence):
        return "refusal"
    if HANDOFF_RE.search(sentence):
        return "handoff"
    return None


def reply_violations(text: str | None) -> list[tuple[str, str]]:
    """Every (sentence, kind) violation in a finished reply, in order."""
    out = []
    for s in split_sentences(text):
        kind = sentence_violation(s)
        if kind:
            out.append((s, kind))
    return out


def result_kinds(result: Any) -> list[str]:
    """Kinds of a delegate_task result, in RESULT_KINDS order."""
    if not isinstance(result, str):
        return []
    kinds = []
    if result.lstrip().startswith("FAILED"):
        kinds.append("failed")
    if NEEDS_INPUT_MARKER in result:
        kinds.append("needs_input")
    if MISSING_TOOL_RE.search(result):
        kinds.append("missing_tool")
    if LIMITATION_RE.search(result):
        kinds.append("limitation")
    return kinds


def is_capability_question(user_text: str | None) -> bool:
    return bool(CAPABILITY_QUESTION_RE.search(user_text or ""))


def is_explicit_command_ask(user_text: str | None) -> bool:
    """D-L5 — Larry explicitly asked to be given a command."""
    text = user_text or ""
    return bool(EXPLICIT_COMMAND_ASK_RE.search(text)) and not EXPLICIT_ASK_NEGATION_RE.search(text)


def voice_workflows(workflows: list[Workflow] | None = None) -> list[Workflow]:
    candidates = load_workflows() if workflows is None else workflows
    return [wf for wf in candidates if SUPERVISOR in wf.agents]


def _user_patterns(wf: Workflow) -> list[re.Pattern]:
    out = []
    for raw in (wf.triggers or {}).get("user", []):
        key = (wf.source or wf.name, raw)
        if key not in _pattern_cache:
            try:
                _pattern_cache[key] = re.compile(raw, re.I)
            except re.error:
                logger.warning("voice_workflow_bad_regex name=%s pattern=%r", wf.name, raw)
                _pattern_cache[key] = None
        pat = _pattern_cache[key]
        if pat is not None:
            out.append(pat)
    return out


def match_voice_workflow(
    *,
    user_text: str | None = None,
    result_kinds: list[str] | None = None,
    reply_kinds: list[str] | None = None,
    workflows: list[Workflow] | None = None,
) -> Workflow | None:
    """The one voice workflow for this hook, or None. Pass exactly one of
    user_text / result_kinds / reply_kinds. Lowest priority wins; ties go
    to the alphabetically first name."""
    given = [x is not None for x in (user_text, result_kinds, reply_kinds)]
    if sum(given) != 1:
        raise ValueError("pass exactly one of user_text, result_kinds, reply_kinds")
    best: Workflow | None = None
    for wf in voice_workflows(workflows):
        trig = wf.triggers or {}
        if user_text is not None:
            hit = any(p.search(user_text) for p in _user_patterns(wf))
        elif result_kinds is not None:
            hit = bool(set(trig.get("result", [])) & set(result_kinds))
        else:
            hit = bool(set(trig.get("reply", [])) & set(reply_kinds))
        if not hit:
            continue
        if best is None or (wf.priority, wf.name) < (best.priority, best.name):
            best = wf
    return best


def render_guidance(wf: Workflow) -> str:
    return GUIDANCE_PREFIX + wf.as_prompt()


def correction_note(kind: str, sentence: str, wf: Workflow | None) -> str:
    text = CORRECTION_TEMPLATE.format(
        phrase=KIND_PHRASE.get(kind, KIND_PHRASE["refusal"]),
        sentence=" ".join(sentence.split())[:300],
    )
    if wf is not None:
        text += "\n" + wf.as_prompt()
    return text


def log_capability_gap(
    *, source: str, kind: str, text: str, session_id: str | None = None,
    agent: str | None = None, user_text: str | None = None,
    workflow: str | None = None, sensitive: bool = False,
    path: Path | None = None,
) -> None:
    """D8 — one JSON line per gap. Never raises."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": session_id,
            "source": source,
            "kind": kind,
            "agent": agent,
            "user_text": "[sensitive]" if sensitive else (user_text or "")[:300],
            "text": "[sensitive]" if sensitive else (text or "")[:400],
            "workflow": workflow,
        }
        target = path or Path(os.environ.get(GAP_LOG_ENV) or GAP_LOG_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        logger.exception("capability_gap_log_failed")


def wrap_delegate_handler(
    handler: Callable[[dict], Any],
    *,
    gate: dict | None = None,
    session_id: str | None = None,
    enabled: Callable[[], bool] = lambda: True,
    is_sensitive: Callable[[], bool] = lambda: False,
    gap_log_path: Path | None = None,
) -> Callable[[dict], Any]:
    """D9 — the `result` hook. Wraps delegate_task's handler: records the
    NEEDS-INPUT time for the show_commands gate, logs capability gaps, and
    appends the matched voice workflow's guidance to the result text."""

    async def wrapped(arguments: dict) -> Any:
        result = await handler(arguments)
        try:
            kinds = result_kinds(result)
            if not kinds:
                return result
            if gate is not None and "needs_input" in kinds:
                gate["needs_input_at"] = time.monotonic()
            for gap_kind in ("missing_tool", "limitation"):
                if gap_kind in kinds:
                    log_capability_gap(
                        source="result", kind=gap_kind, text=result,
                        session_id=session_id,
                        agent=str((arguments or {}).get("agent_name") or "") or None,
                        sensitive=is_sensitive(), path=gap_log_path,
                    )
                    break
            if not enabled():
                return result
            wf = match_voice_workflow(result_kinds=kinds)
            if wf is None:
                return result
            logger.info("voice_workflow_injected hook=result name=%s kinds=%s",
                        wf.name, ",".join(kinds))
            return result + "\n\n" + render_guidance(wf)
        except Exception:  # noqa: BLE001 — guidance is never load-bearing
            logger.exception("voice_workflow_result_hook_failed")
            return result

    return wrapped
