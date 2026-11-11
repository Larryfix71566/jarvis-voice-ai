"""Typed-request and approval message types: pure validators and builders.

Implements contract section 2 (``turn/typed``, ``turn/result``) and section 3
(``approval/pending``, ``approval/settled``, ``approval/decide``,
``approval/result``, and the bare-yes rule of 3.10).  This module holds
shapes, enums and validation only.  Handlers, the pending list, the
duplicate-reply cache and speech live in a later item.

Rules that bind this file: it imports nothing that talks to a registry, a
tool server, a sidecar, the network or a process; no client string is ever
turned into model text here.  Validators raise ``TypedRequestError`` (a
``ValueError``); its ``code`` is the reply code to send, or None when the
message has no trustworthy identity and gets no reply (contract 2.2).
"""
from __future__ import annotations

import json
import math
import unicodedata
import uuid
from typing import Any

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
    "protected_turn", "stale_session", "disabled",
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


def _header(message: dict, type_name: str, session_id: str, generation: str) -> tuple[str, str]:
    if message.get("type") != type_name or type(message.get("version")) is not int or message["version"] != VERSION:
        raise TypedRequestError(f"unsupported {type_name}")
    sid = _uuid(message.get("session_id"), "session_id")
    gen = _uuid(message.get("generation"), "generation")
    if sid != _uuid(session_id, "session_id"):
        raise TypedRequestError("stale session")
    if gen != _uuid(generation, "generation"):
        raise TypedRequestError("stale generation")
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

    Returns the normalised message (canonical UUIDs, trimmed text).  Rules 1
    to 4 raise with ``code=None`` (no reply); rules 5 to 7 raise with
    ``code="invalid_text"``.
    """
    msg = _exact_keys(message, _TURN_TYPED_KEYS, "turn/typed")  # rule 1
    sid, gen = _header(msg, TURN_TYPED, session_id, generation)  # rules 2, 3
    request_id = _uuid(msg.get("request_id"), "request_id")  # rule 4
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
    with ``code=None``: the message carries no text the bot may answer to.
    """
    msg = _exact_keys(message, _DECIDE_KEYS, "approval/decide")
    sid, gen = _header(msg, APPROVAL_DECIDE, session_id, generation)
    request_id = _uuid(msg.get("request_id"), "request_id")
    approval_id = _uuid(msg.get("approval_id"), "approval_id")
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
