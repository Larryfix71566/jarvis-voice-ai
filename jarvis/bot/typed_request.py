"""Typed-request and approval message types: pure validators and builders.

Implements contract section 2 (``turn/typed``, ``turn/result``) and section 3
(``approval/pending``, ``approval/settled``, ``approval/decide``,
``approval/result``, and the bare-yes rule of 3.10).  This module holds
shapes, enums and validation (C0), and, since C7-py, the pure state and
decisions behind them: ``ApprovalBook`` (the per-connection pending list),
``ReplyCache`` (duplicate replies) and ``TypedRequestSession`` (the two
message handlers and the bare-yes verdict).  Everything the session needs
from the running bot (sending, speaking, starting a turn, the sensitive
flag) is passed in as plain callables; the framework-side wiring lives in
``jarvis/bot/pipeline.py``.

Rules that bind this file: it imports nothing that talks to a registry, a
tool server, a sidecar, the network or a process; no client string is ever
turned into model text here.  Validators raise ``TypedRequestError`` (a
``ValueError``); its ``code`` is the reply code to send, or None when the
message has no trustworthy identity and gets no reply (contract 2.2).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
import unicodedata
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from jarvis.prompts import (
    APPROVAL_WHICH_TEMPLATE,
    APPROVE_TURN_TEMPLATE,
    DECLINE_TURN_TEMPLATE,
)

_logger = logging.getLogger(__name__)

MAX_MESSAGE = 32 * 1024  # same ceiling as console_protocol.MAX_MESSAGE
VERSION = 1

TURN_TYPED = "turn/typed"
TURN_RESULT = "turn/result"
APPROVAL_PENDING = "approval/pending"
APPROVAL_SETTLED = "approval/settled"
APPROVAL_DECIDE = "approval/decide"
APPROVAL_RESULT = "approval/result"

MIN_TEXT = 1
MAX_TEXT = 4000
TURN_SOURCES = frozenset({"composer", "chip"})
TURN_RESULT_CODES = frozenset({"accepted", "duplicate", "invalid_text", "stale_session", "not_ready", "disabled"})
RESULT_STATUSES = frozenset({"accepted", "rejected"})

APPROVAL_STATES = frozenset({"approved", "declined", "resolved", "superseded", "expired"})
APPROVAL_DECISIONS = frozenset({"approve", "decline"})
APPROVAL_RESULT_CODES = frozenset({
    "accepted", "duplicate", "unknown_approval", "expired", "already_settled",
    "protected_turn", "stale_session", "not_ready", "disabled",
})

MAX_SUMMARY = 600
MAX_NAME = 80
MAX_RUN_ID = 120
MAX_REF_VALUE = 120
MAX_OPEN_APPROVALS = 8
APPROVAL_TTL_S = 600
REPLY_CACHE_MAX = 128
REPLY_CACHE_TTL_S = 300

# Contract 3.10 item 1: the whole list; anything else is not a bare yes.
BARE_YES_PHRASES = frozenset({
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
    "approve", "approved", "go ahead", "do it", "yes please",
})

_TURN_TYPED_KEYS = frozenset({"type", "version", "session_id", "generation", "request_id", "text", "source"})
_TURN_RESULT_KEYS = frozenset({"type", "version", "session_id", "generation", "request_id", "status", "code"})
_PENDING_KEYS = frozenset({
    "type", "version", "session_id", "generation", "approval_id", "origin_request_id",
    "run_id", "agent", "tool", "summary", "ts", "expires_at",
})
_SETTLED_KEYS = frozenset({"type", "version", "session_id", "generation", "approval_id", "state"})
_DECIDE_KEYS = frozenset({"type", "version", "session_id", "generation", "request_id", "approval_id", "decision"})
_APPROVAL_RESULT_KEYS = frozenset({
    "type", "version", "session_id", "generation", "request_id", "approval_id", "status", "code",
})


class TypedRequestError(ValueError):
    """A message failed validation.

    ``code`` is the ``turn/result`` code to reply with, or None for "send no
    reply" (malformed or untrusted identity, contract 2.2).
    """

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- helpers

def _uuid(value: Any, field: str) -> str:
    """Parse as a UUID and return the canonical lowercase form.

    Compared as UUIDs, never as strings: Foundation sends uppercase hex.
    """
    if not isinstance(value, str):
        raise TypedRequestError(f"{field} must be a UUID")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise TypedRequestError(f"{field} must be a UUID") from exc


def _exact_keys(message: Any, allowed: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise TypedRequestError(f"{name} must be an object")
    extra = set(message) - allowed
    missing = allowed - set(message)
    if extra:
        raise TypedRequestError(f"unknown {name} field")
    if missing:
        raise TypedRequestError(f"missing {name} field")
    return message


def _require_current(sid: str, gen: str, session_id: str, generation: str) -> None:
    """Raise ``stale_session`` unless the parsed ids are the session's (contract 2.2, 3.6).

    Only called after every identity field of the message has parsed, so the
    caller has ids to answer with.
    """
    if sid != _uuid(session_id, "session_id"):
        raise TypedRequestError("stale session", "stale_session")
    if gen != _uuid(generation, "generation"):
        raise TypedRequestError("stale generation", "stale_session")


def _header(message: dict, type_name: str, session_id: str, generation: str,
            *, defer_session_check: bool = False) -> tuple[str, str]:
    """Check type and version, parse session and generation, then compare them.

    With ``defer_session_check`` the comparison is left to the caller (via
    ``_require_current``) so it can parse its other ids first.
    """
    if message.get("type") != type_name or type(message.get("version")) is not int or message["version"] != VERSION:
        raise TypedRequestError(f"unsupported {type_name}")
    sid = _uuid(message.get("session_id"), "session_id")
    gen = _uuid(message.get("generation"), "generation")
    if not defer_session_check:
        _require_current(sid, gen, session_id, generation)
    return sid, gen


def _bounded_str(value: Any, field: str, lo: int, hi: int) -> str:
    if not isinstance(value, str) or not lo <= len(value) <= hi:
        raise TypedRequestError(f"{field} must be a string of {lo} to {hi}")
    return value


def _finite(value: Any, field: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise TypedRequestError(f"{field} must be a finite number")
    return value


def normalize_text(text: Any) -> str:
    """Trim and validate typed text (contract 2.2 rule 5).

    1 to 4,000 Unicode scalars after trimming (``len`` of a Python ``str``),
    no control characters except newline and tab.  Surrogate code points are
    not scalars and are refused.
    """
    if not isinstance(text, str):
        raise TypedRequestError("text must be a string", "invalid_text")
    trimmed = text.strip()
    if not MIN_TEXT <= len(trimmed) <= MAX_TEXT:
        raise TypedRequestError("text length out of range", "invalid_text")
    for ch in trimmed:
        cat = unicodedata.category(ch)
        if (cat == "Cc" and ch not in "\n\t") or cat == "Cs":
            raise TypedRequestError("text has a disallowed character", "invalid_text")
    return trimmed


def _pair_ok(status: Any, code: Any, codes: frozenset[str], name: str) -> None:
    """``accepted`` pairs only with ``accepted``; every other code is a rejection."""
    if status not in RESULT_STATUSES or code not in codes:
        raise TypedRequestError(f"invalid {name} status or code")
    if (status == "accepted") != (code == "accepted"):
        raise TypedRequestError(f"{name} status does not match code")


# ------------------------------------------------------------ turn/typed

def validate_turn_typed(message: Any, *, session_id: str, generation: str) -> dict[str, Any]:
    """Validate a client ``turn/typed`` message (contract 2.2, seven rules).

    Returns the normalised message (canonical UUIDs, trimmed text).  Rules 1,
    2, 3a and 4 raise with ``code=None`` (no reply).  A session or generation
    mismatch (3b), checked only after the three ids parse, raises
    ``code="stale_session"``.  Rules 5 to 7 raise with ``code="invalid_text"``.
    """
    msg = _exact_keys(message, _TURN_TYPED_KEYS, "turn/typed")  # rule 1
    sid, gen = _header(msg, TURN_TYPED, session_id, generation, defer_session_check=True)  # rules 2, 3a
    request_id = _uuid(msg.get("request_id"), "request_id")  # rule 4
    _require_current(sid, gen, session_id, generation)  # rule 3b: stale only once the ids parse
    text = normalize_text(msg.get("text"))  # rule 5
    if msg.get("source") not in TURN_SOURCES:  # rule 6
        raise TypedRequestError("invalid source", "invalid_text")
    try:  # rule 7
        size = len(json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise TypedRequestError("message not encodable", "invalid_text") from exc
    if size > MAX_MESSAGE:
        raise TypedRequestError("message too large", "invalid_text")
    return {"type": TURN_TYPED, "version": VERSION, "session_id": sid, "generation": gen,
            "request_id": request_id, "text": text, "source": msg["source"]}


def build_turn_result(*, session_id: str, generation: str, request_id: str, code: str) -> dict[str, Any]:
    """Build a ``turn/result`` (contract 2.3).  The text is never echoed."""
    out = {"type": TURN_RESULT, "version": VERSION,
           "session_id": _uuid(session_id, "session_id"), "generation": _uuid(generation, "generation"),
           "request_id": _uuid(request_id, "request_id"),
           "status": "accepted" if code == "accepted" else "rejected", "code": code}
    return validate_turn_result(out, session_id=session_id, generation=generation)


def validate_turn_result(message: Any, *, session_id: str, generation: str) -> dict[str, Any]:
    msg = _exact_keys(message, _TURN_RESULT_KEYS, "turn/result")
    sid, gen = _header(msg, TURN_RESULT, session_id, generation)
    request_id = _uuid(msg.get("request_id"), "request_id")
    _pair_ok(msg.get("status"), msg.get("code"), TURN_RESULT_CODES, "turn/result")
    return {"type": TURN_RESULT, "version": VERSION, "session_id": sid, "generation": gen,
            "request_id": request_id, "status": msg["status"], "code": msg["code"]}


# -------------------------------------------------------- approval/pending

def validate_approval_pending(message: Any, *, session_id: str, generation: str) -> dict[str, Any]:
    """Client-side check of a bot ``approval/pending`` (contract 3.4)."""
    msg = _exact_keys(message, _PENDING_KEYS, "approval/pending")
    sid, gen = _header(msg, APPROVAL_PENDING, session_id, generation)
    approval_id = _uuid(msg.get("approval_id"), "approval_id")
    origin = msg.get("origin_request_id")
    origin = None if origin is None else _uuid(origin, "origin_request_id")
    run_id = msg.get("run_id")
    if run_id is not None:
        _bounded_str(run_id, "run_id", 1, MAX_RUN_ID)
    summary = _bounded_str(msg.get("summary"), "summary", 1, MAX_SUMMARY)
    agent = _bounded_str(msg.get("agent"), "agent", 1, MAX_NAME)
    tool = _bounded_str(msg.get("tool"), "tool", 1, MAX_NAME)
    ts = _finite(msg.get("ts"), "ts")
    expires_at = _finite(msg.get("expires_at"), "expires_at")
    if not expires_at > ts:
        raise TypedRequestError("expires_at must be after ts")
    return {"type": APPROVAL_PENDING, "version": VERSION, "session_id": sid, "generation": gen,
            "approval_id": approval_id, "origin_request_id": origin, "run_id": run_id,
            "agent": agent, "tool": tool, "summary": summary, "ts": ts, "expires_at": expires_at}


def build_approval_pending(*, session_id: str, generation: str, approval_id: str,
                           origin_request_id: str | None, run_id: str | None,
                           agent: str, tool: str, summary: str,
                           ts: float, expires_at: float) -> dict[str, Any]:
    """Build an ``approval/pending``; the summary is cut to 600 chars (3.3)."""
    out = {"type": APPROVAL_PENDING, "version": VERSION, "session_id": session_id,
           "generation": generation, "approval_id": approval_id,
           "origin_request_id": origin_request_id, "run_id": run_id, "agent": agent,
           "tool": tool, "summary": summary[:MAX_SUMMARY] if isinstance(summary, str) else summary,
           "ts": ts, "expires_at": expires_at}
    return validate_approval_pending(out, session_id=session_id, generation=generation)


# -------------------------------------------------------- approval/settled

def validate_approval_settled(message: Any, *, session_id: str, generation: str) -> dict[str, Any]:
    """Check an ``approval/settled`` (contract 3.5)."""
    msg = _exact_keys(message, _SETTLED_KEYS, "approval/settled")
    sid, gen = _header(msg, APPROVAL_SETTLED, session_id, generation)
    approval_id = _uuid(msg.get("approval_id"), "approval_id")
    if msg.get("state") not in APPROVAL_STATES:
        raise TypedRequestError("invalid approval state")
    return {"type": APPROVAL_SETTLED, "version": VERSION, "session_id": sid, "generation": gen,
            "approval_id": approval_id, "state": msg["state"]}


def build_approval_settled(*, session_id: str, generation: str, approval_id: str, state: str) -> dict[str, Any]:
    out = {"type": APPROVAL_SETTLED, "version": VERSION, "session_id": session_id,
           "generation": generation, "approval_id": approval_id, "state": state}
    return validate_approval_settled(out, session_id=session_id, generation=generation)


# --------------------------------------------------------- approval/decide

def validate_approval_decide(message: Any, *, session_id: str, generation: str) -> dict[str, Any]:
    """Validate a client ``approval/decide`` (contract 3.6).

    Exactly seven keys; there is no free-text field.  Every failure raises
    with ``code=None`` (no reply: the message has no trustworthy identity)
    except a session or generation mismatch, which raises
    ``code="stale_session"`` once all four ids have parsed (3.6), so the
    caller has a ``request_id`` and ``approval_id`` to answer with.
    """
    msg = _exact_keys(message, _DECIDE_KEYS, "approval/decide")
    sid, gen = _header(msg, APPROVAL_DECIDE, session_id, generation, defer_session_check=True)
    request_id = _uuid(msg.get("request_id"), "request_id")
    approval_id = _uuid(msg.get("approval_id"), "approval_id")
    _require_current(sid, gen, session_id, generation)
    if msg.get("decision") not in APPROVAL_DECISIONS:
        raise TypedRequestError("invalid decision")
    try:
        size = len(json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise TypedRequestError("message not encodable") from exc
    if size > MAX_MESSAGE:
        raise TypedRequestError("message too large")
    return {"type": APPROVAL_DECIDE, "version": VERSION, "session_id": sid, "generation": gen,
            "request_id": request_id, "approval_id": approval_id, "decision": msg["decision"]}


# --------------------------------------------------------- approval/result

def validate_approval_result(message: Any, *, session_id: str, generation: str) -> dict[str, Any]:
    """Check an ``approval/result`` (contract 3.7)."""
    msg = _exact_keys(message, _APPROVAL_RESULT_KEYS, "approval/result")
    sid, gen = _header(msg, APPROVAL_RESULT, session_id, generation)
    request_id = _uuid(msg.get("request_id"), "request_id")
    approval_id = _uuid(msg.get("approval_id"), "approval_id")
    _pair_ok(msg.get("status"), msg.get("code"), APPROVAL_RESULT_CODES, "approval/result")
    return {"type": APPROVAL_RESULT, "version": VERSION, "session_id": sid, "generation": gen,
            "request_id": request_id, "approval_id": approval_id,
            "status": msg["status"], "code": msg["code"]}


def build_approval_result(*, session_id: str, generation: str, request_id: str,
                          approval_id: str, code: str) -> dict[str, Any]:
    out = {"type": APPROVAL_RESULT, "version": VERSION, "session_id": session_id,
           "generation": generation, "request_id": request_id, "approval_id": approval_id,
           "status": "accepted" if code == "accepted" else "rejected", "code": code}
    return validate_approval_result(out, session_id=session_id, generation=generation)


# ---------------------------------------------------------------- bare yes

def is_bare_yes(text: Any) -> bool:
    """True when ``text`` is exactly one phrase of ``BARE_YES_PHRASES`` (3.10).

    Lowercase, trim, remove trailing punctuation, then compare to the fixed
    list.  "yes, the plan" and "yes and also" are not bare.
    """
    if not isinstance(text, str):
        return False
    s = text.strip().lower()
    while s and (unicodedata.category(s[-1]).startswith("P") or s[-1].isspace()):
        s = s[:-1]
    return s in BARE_YES_PHRASES


# ====================================================================
# C7-py: pending list, duplicate replies, handlers (contract 2.4, 3.3, 3.8)
# ====================================================================

#: Result keys, in order, that name what a preview is waiting on (3.3).
REF_KEYS = ("staging_id", "preview_id", "draft_id", "action_id")
_REF_VALUE_RE = re.compile(r"[A-Za-z0-9_.:-]{1,120}")
_NAME_RE = re.compile(r"[A-Za-z0-9 _.-]{1,80}")
SETTLED_MEMORY = 256
_COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}


def _parse_json_object(raw: Any) -> dict | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def is_preview(result: Any) -> bool:
    """True when a parsed tool result asks for confirmation (3.3).

    Reads both flags, and only the JSON ``true`` (a string "true" is not).
    """
    return isinstance(result, dict) and (
        result.get("pending") is True or result.get("needs_confirmation") is True)


def pick_ref(result: dict) -> dict[str, str] | None:
    """First present of ``REF_KEYS`` whose value is a safe short token (3.3).

    A first-present key with an unusable value ends the search: the entry
    carries no ref rather than a later key's value.
    """
    for key in REF_KEYS:
        if result.get(key) is not None:
            value = result[key]
            if isinstance(value, str) and _REF_VALUE_RE.fullmatch(value):
                return {"kind": key, "value": value}
            return None
    return None


@dataclass
class Approval:
    approval_id: str
    agent: str
    tool: str
    run_id: str | None
    origin_id: str | None
    summary: str
    ref: dict[str, str] | None
    ts: float
    expires_at: float


def approval_turn_text(entry: Approval, decision: str) -> str:
    """The user-turn text for a decision: a pure function of what the bot
    recorded.  No client string is an input."""
    if decision == "approve":
        ref = f" ({entry.ref['kind']} {entry.ref['value']})" if entry.ref else ""
        return APPROVE_TURN_TEMPLATE.format(tool=entry.tool, agent=entry.agent, ref=ref)
    return DECLINE_TURN_TEMPLATE.format(tool=entry.tool, agent=entry.agent)


def _join_items(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class ReplyCache:
    """Bounded duplicate-reply memory: 128 entries for 300 seconds (2.3).

    Stores the reply dict only, never the request text.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 max_entries: int = REPLY_CACHE_MAX, ttl_s: float = REPLY_CACHE_TTL_S) -> None:
        self._clock, self._max, self._ttl = clock, max_entries, ttl_s
        self._items: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    def _prune(self) -> None:
        now = self._clock()
        for key in [k for k, (t, _) in self._items.items() if now - t > self._ttl]:
            del self._items[key]

    def get(self, key: str) -> dict | None:
        self._prune()
        hit = self._items.get(key)
        return dict(hit[1]) if hit else None

    def put(self, key: str, reply: dict) -> None:
        self._prune()
        self._items[key] = (self._clock(), dict(reply))
        self._items.move_to_end(key)
        while len(self._items) > self._max:
            self._items.popitem(last=False)


class ApprovalBook:
    """The per-connection pending list (contract 3.3).  In memory only.

    It never sends, speaks or calls anything itself: every ``approval/pending``
    and ``approval/settled`` goes to the injected synchronous ``emit``.  It
    records an entry only from a tool result that parses as a JSON object
    with a top-level ``pending is True`` or ``needs_confirmation is True``,
    and never on a sensitive turn.
    """

    def __init__(self, *, session_id: str, generation: str,
                 emit: Callable[[dict], None],
                 clock: Callable[[], float] = time.time,
                 schedule: Callable[[float, Callable[[], None]], Any] | None = None,
                 new_id: Callable[[], str] | None = None) -> None:
        self._sid, self._gen, self._emit = session_id, generation, emit
        self._clock, self._schedule = clock, schedule
        self._new_id = new_id or (lambda: str(uuid.uuid4()))
        self._open: OrderedDict[str, Approval] = OrderedDict()
        self._settled: OrderedDict[str, str] = OrderedDict()
        self._timers: list[Any] = []

    # ------------------------------------------------------------ internals
    def _settle(self, entry: Approval, state: str) -> None:
        self._open.pop(entry.approval_id, None)
        self._settled[entry.approval_id] = state
        while len(self._settled) > SETTLED_MEMORY:
            self._settled.popitem(last=False)
        try:
            self._emit(build_approval_settled(session_id=self._sid, generation=self._gen,
                                              approval_id=entry.approval_id, state=state))
        except Exception:  # noqa: BLE001 - a broken channel never blocks the list
            _logger.info("approval_settled_not_emitted state=%s", state)

    def _expire_due(self) -> list[str]:
        now = self._clock()
        due = [e for e in self._open.values() if e.expires_at <= now]
        for entry in due:
            self._settle(entry, "expired")
        return [e.approval_id for e in due]

    @staticmethod
    def _names(event: dict) -> tuple[str, str]:
        return (str(event.get("display_name") or event.get("agent") or ""),
                str(event.get("tool") or ""))

    # ------------------------------------------------------------- recording
    def observe(self, event: Any, *, origin_id: str | None, sensitive: bool) -> None:
        """Feed one ``agent_tool_result`` event (3.3)."""
        self._expire_due()
        if not isinstance(event, dict) or event.get("type") != "agent_tool_result":
            return
        raw = event.get("result")
        if not isinstance(raw, str) or not raw.strip():
            return  # a protected route carries no result: nothing to record
        agent, tool = self._names(event)
        parsed = _parse_json_object(raw)
        if not is_preview(parsed):
            if event.get("ok", True):
                # The tool ran (the user said yes by voice): settle its preview.
                for entry in [e for e in self._open.values()
                              if (e.agent, e.tool) == (agent, tool)]:
                    self._settle(entry, "resolved")
            return
        if sensitive:
            return
        if not _NAME_RE.fullmatch(agent) or not _NAME_RE.fullmatch(tool):
            _logger.info("approval_not_recorded reason=name")
            return
        summary = parsed.get("summary")
        summary = summary.strip() if isinstance(summary, str) else ""
        if not summary:
            summary = f"{agent} is waiting for your approval to run {tool}."
        run_id = event.get("run_id")
        run_id = run_id if isinstance(run_id, str) and 1 <= len(run_id) <= MAX_RUN_ID else None
        try:
            origin = _uuid(origin_id, "origin") if origin_id is not None else None
        except TypedRequestError:
            origin = None
        now = self._clock()
        entry = Approval(self._new_id(), agent, tool, run_id, origin, summary[:MAX_SUMMARY],
                         pick_ref(parsed), now, now + APPROVAL_TTL_S)
        try:
            pending = build_approval_pending(
                session_id=self._sid, generation=self._gen, approval_id=entry.approval_id,
                origin_request_id=origin, run_id=run_id, agent=agent, tool=tool,
                summary=entry.summary, ts=entry.ts, expires_at=entry.expires_at)
        except TypedRequestError:
            _logger.info("approval_not_recorded reason=shape")
            return
        for old in [e for e in self._open.values() if (e.agent, e.tool) == (agent, tool)]:
            self._settle(old, "superseded")
        while len(self._open) >= MAX_OPEN_APPROVALS:
            self._settle(next(iter(self._open.values())), "superseded")
        self._open[entry.approval_id] = entry
        try:
            self._emit(pending)
        except Exception:  # noqa: BLE001
            _logger.info("approval_pending_not_emitted")
        if self._schedule is not None:
            self._timers.append(self._schedule(APPROVAL_TTL_S + 1, self.expire))

    def expire(self) -> None:
        """Settle every entry past its time as ``expired`` (timer entry point)."""
        self._expire_due()

    def close(self) -> None:
        for timer in self._timers:
            cancel = getattr(timer, "cancel", None)
            if callable(cancel):
                cancel()
        self._timers.clear()

    # --------------------------------------------------------------- reading
    def open_items(self) -> list[Approval]:
        self._expire_due()
        return list(self._open.values())

    def decide(self, approval_id: str, decision: str) -> tuple[str, Approval | None]:
        """Apply a decision.  Returns ``(code, entry)``; ``entry`` only on
        ``accepted``.  Each id settles once; unknown, expired and settled ids
        change nothing."""
        expired_now = self._expire_due()
        if approval_id in expired_now:
            return "expired", None
        entry = self._open.get(approval_id)
        if entry is None:
            state = self._settled.get(approval_id)
            if state is None:
                return "unknown_approval", None
            return ("expired" if state == "expired" else "already_settled"), None
        self._settle(entry, "approved" if decision == "approve" else "declined")
        return "accepted", entry

    def yes_verdict(self, text: Any, *, sensitive: bool, offer_pending: bool,
                    source: str) -> str | None:
        """Contract 3.10.  None means "pass the turn on unchanged"; a string
        is the fixed question to speak instead (two or more open).  Nothing
        is approved or settled either way."""
        if sensitive or offer_pending or not is_bare_yes(text):
            return None
        items = self.open_items()
        if len(items) < 2:
            return None
        _logger.info("approval_yes_ambiguous open=%d source=%s", len(items), source)
        spoken = [f"{e.tool.replace('_', ' ')} from {e.agent}" for e in items]
        return APPROVAL_WHICH_TEMPLATE.format(
            count=_COUNT_WORDS.get(len(items), str(len(items))), items=_join_items(spoken))


class TypedRequestSession:
    """The two message handlers, with everything impure injected.

    ``send`` delivers a reply message; ``start_turn(text, tag)`` makes the
    text the user's next turn and returns whether it did; ``speak`` says a
    fixed sentence with no model call.  The handlers never call a tool.
    """

    def __init__(self, *, session_id: str, generation: str,
                 send: Callable[[dict], Awaitable[None]],
                 start_turn: Callable[[str, str], Awaitable[bool]],
                 speak: Callable[[str], Awaitable[None]],
                 is_alive: Callable[[], bool],
                 is_sensitive: Callable[[], bool],
                 book: ApprovalBook | None = None,
                 typed_enabled: bool = True,
                 offer_pending: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._sid, self._gen = session_id, generation
        self._send, self._start_turn, self._speak = send, start_turn, speak
        self._alive, self._sensitive = is_alive, is_sensitive
        self._book, self._typed_enabled, self._offer_pending = book, typed_enabled, offer_pending
        self._turn_replies = ReplyCache(clock)
        self._decide_replies = ReplyCache(clock)
        self._inflight: set[str] = set()
        self._lock = asyncio.Lock()  # one delivery at a time, in arrival order

    # --------------------------------------------------------------- typed
    async def handle_turn(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("type") != TURN_TYPED:
            return
        kw = {"session_id": self._sid, "generation": self._gen}
        try:
            msg = validate_turn_typed(message, **kw)
            rid, text, code = msg["request_id"], msg["text"], None
        except TypedRequestError as exc:
            if exc.code is None:
                _logger.info("typed_request_dropped reason=identity")
                return
            rid, text, code = _uuid(message.get("request_id"), "request_id"), "", exc.code
        cached = self._turn_replies.get(rid)
        if cached is not None:
            await self._send(cached)
            return
        if rid in self._inflight:
            return  # the first reply is still coming
        self._inflight.add(rid)
        try:
            if code is None:
                code = await self._turn_code(rid, text)
            reply = build_turn_result(code=code, request_id=rid, **kw)
            self._turn_replies.put(rid, reply)
            await self._send(reply)
        finally:
            self._inflight.discard(rid)

    async def _turn_code(self, rid: str, text: str) -> str:
        if not self._typed_enabled:
            return "disabled"
        if not self._alive():
            return "not_ready"
        if text.lower().startswith("[system]"):
            return "invalid_text"  # typed text must not pass as a system note
        if self._book is not None:
            # A new typed turn starts unflagged and a bare yes cannot arm it,
            # so the previous turn's flag is not consulted here.
            question = self._book.yes_verdict(text, sensitive=False,
                                              offer_pending=bool(self._offer_pending()),
                                              source="typed")
            if question is not None:
                try:
                    await self._speak(question)
                except Exception:  # noqa: BLE001
                    _logger.info("approval_question_not_spoken")
                return "accepted"
        return await self._deliver(text, f"typed:{rid}")

    async def _deliver(self, text: str, tag: str) -> str:
        async with self._lock:
            try:
                ok = await self._start_turn(text, tag)
            except Exception:  # noqa: BLE001 - a failed start is never a crash
                _logger.warning("typed_turn_start_failed")
                ok = False
        return "accepted" if ok else "not_ready"

    # ----------------------------------------------------------- approvals
    async def handle_decide(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("type") != APPROVAL_DECIDE:
            return
        kw = {"session_id": self._sid, "generation": self._gen}
        try:
            msg = validate_approval_decide(message, **kw)
        except TypedRequestError:
            _logger.info("approval_decide_dropped reason=identity")
            return
        rid, aid = msg["request_id"], msg["approval_id"]
        cached = self._decide_replies.get(rid)
        if cached is not None:
            await self._send(cached)
            return
        if rid in self._inflight:
            return
        self._inflight.add(rid)
        try:
            if self._book is None:
                code, entry = "disabled", None
            elif not self._alive():
                return  # the list died with the session; let the socket close
            elif self._sensitive():
                code, entry = "protected_turn", None
            else:
                code, entry = self._book.decide(aid, msg["decision"])
            reply = build_approval_result(code=code, request_id=rid, approval_id=aid, **kw)
            self._decide_replies.put(rid, reply)
            await self._send(reply)
            if entry is not None:
                outcome = await self._deliver(
                    approval_turn_text(entry, msg["decision"]), f"approval:{aid}")
                if outcome != "accepted":
                    # Stays settled (one tap counts once); the user can ask again.
                    _logger.info("approval_turn_not_delivered decision=%s", msg["decision"])
        finally:
            self._inflight.discard(rid)
