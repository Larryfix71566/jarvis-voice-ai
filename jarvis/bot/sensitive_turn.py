"""Per-turn sensitive flag (T4a, contract K3).

The ContextVar is the SINGLE access path (plan D-H4, review F15). run_session
(and the CLI's main) call current_sensitive_turn.set(...) BEFORE the observer,
processor and any turn exist, so every task created afterwards — including the
Pipecat observer's and processor's tasks — inherits the reference and sees its
mutations. The earlier claim that the transcript sites run on tasks "not
children of the turn" was false: they run on tasks created after set().

Runtime.sensitive_turn is the object's LIFETIME OWNER, not a second access path:
a default_factory dataclass field, so one SensitiveTurn is constructed with the
Runtime, published on the ContextVar, and dies with the session. The object is
mutable and shared precisely so a reference copied into a child context stays
live — arm() on the main task is visible to a reader in a child task with no
synchronisation.

The run-log is the ONE exception: it runs in a detached task that outlives the
turn (jarvis/agents/delegate.py), so it reads a boolean SNAPSHOT taken when the
RunLogger is constructed (plan D-H7), never the live flag.

This module stores nothing and persists nothing. The flag dies with the
session; a sensitive turn deliberately does not survive a restart, because
T4a has nowhere to survive to (roadmap C3).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from jarvis.sensitive import (
    asks_for_credential, detect_credential, detect_financial,
    detect_spoken_credential, leaves_credential_pending,
)

# Larry, 2026-11-24: "the only text that should be banned from outside the
# machine would include account or password info". These arm kinds hold
# account or credential details; every other sensitive kind (a balance, a
# confidential tool source, imported content) may go to the Claude
# subscription, which carries every privacy level.
ACCOUNT_INFO_KINDS = frozenset({"card", "account", "routing", "iban", "credential"})


class SensitiveTurn:
    """Mutable per-session holder for the current turn's sensitivity.

    Deliberately not a dataclass and not frozen: every suppression site holds
    the SAME instance and must see mutations.
    """

    __slots__ = ("armed", "turn_id", "kind", "temporary_content_mode", "account_info",
                 "credential_prompted")

    def __init__(self) -> None:
        self.armed: bool = False
        self.turn_id: str | None = None
        self.kind: str | None = None
        # Unlike the per-turn financial flag, this latch survives turn
        # boundaries for the lifetime of the bot session. Imported content
        # has already crossed the provider boundary; clearing it between
        # turns would allow the next memory sweep to persist the context.
        self.temporary_content_mode: bool = False
        # Sticky for the turn: a later, milder arm() must not hide it.
        self.account_info: bool = False
        # Set when a turn asks for (or leaves hanging) a credential, so the NEXT
        # user turn is read as the value. Outlives clear() by one user turn.
        self.credential_prompted: bool = False

    def take_credential_prompt(self) -> bool:
        value, self.credential_prompted = self.credential_prompted, False
        return value

    def arm(self, kind: str, turn_id: str | None = None) -> None:
        """Mark the current turn sensitive. Idempotent within a turn."""
        self.armed = True
        self.kind = kind
        if kind in ACCOUNT_INFO_KINDS:
            self.account_info = True
        if self.turn_id is None:
            self.turn_id = turn_id or uuid.uuid4().hex[:8]

    def clear(self) -> None:
        """End the current turn without resetting temporary-content mode."""
        self.armed = False
        self.turn_id = None
        self.kind = None
        self.account_info = False

    def arm_temporary_content(self) -> None:
        """Pause memory persistence for the rest of this bot session."""
        self.temporary_content_mode = True

    def is_armed(self) -> bool:
        return self.armed or self.temporary_content_mode


current_sensitive_turn: ContextVar[SensitiveTurn | None] = ContextVar(
    "current_sensitive_turn", default=None
)


def is_sensitive() -> bool:
    """True when the current turn is flagged sensitive.

    FAIL-CLOSED, and this is the ONE place that choice is made (review F1/F6):
    an UNSET ContextVar returns True — "treat as sensitive → suppress". The
    ContextVar is always set at every live read site (run_session and the CLI's
    main wire it before any turn), so the None branch is reached only on a
    genuine wiring regression — and then the failure is LOUD (transcripts stop
    appearing, caught immediately by V4) instead of a silent leak. An ordinary
    turn logs normally: its holder is set and is_armed() is False.
    """
    holder = current_sensitive_turn.get()
    if holder is None:
        return True  # fail-closed
    return holder.is_armed()


def holds_account_info() -> bool:
    """True when the current turn carries account or credential details.

    Those never leave the Mac, on any external route. Fail-closed like
    is_sensitive(): an unset ContextVar counts as holding them.
    """
    holder = current_sensitive_turn.get()
    if holder is None:
        return True
    return bool(holder.account_info)


def current_turn_id() -> str:
    """The armed turn's id, for redacted log lines. '-' when not armed/unset."""
    holder = current_sensitive_turn.get()
    if holder is None or holder.turn_id is None:
        return "-"
    return holder.turn_id


def arm_from_text(text: str, turn_id: str | None = None, *, credentials: bool = False,
                  credential_pending: bool = False) -> bool:
    """Run detection on `text` and arm the current turn if it matches.

    Called on BOTH the user text and the assistant reply (review F2). Returns
    True when it armed. Total: a missing holder is a no-op, not a crash — this
    runs inside the voice loop.
    """
    match = detect_financial(text)
    kind = match.kind if match is not None else None
    # Credentials are checked on what the user says or types (credentials=
    # True), not on tool output, where source files carry fake keys.
    if kind is None and credentials and detect_credential(text):
        kind = "credential"
    if kind is None and credentials and detect_spoken_credential(
            text, pending=credential_pending):
        kind = "credential"
    if kind is None:
        return False
    holder = current_sensitive_turn.get()
    if holder is None:
        return False
    if turn_id is None:
        # Correlate the redacted log line with the run, when inside one
        # (review F17). Lazy import: jarvis.runlog must not be imported at this
        # module's top (it would pull jarvis.agents, a heavier graph); this is
        # the only place we need it.
        try:
            from jarvis.runlog import get_run_id
            turn_id = get_run_id() or None
        except Exception:  # noqa: BLE001
            turn_id = None
    holder.arm(kind, turn_id)
    return True


def redacted(text: str) -> str:
    """The line that replaces a transcript print on a sensitive turn.

    Carries the turn id and a length ONLY — never a character of content,
    never the detected kind (the kind is itself a hint about the value).
    (review F20: no `role` parameter — the caller supplies the USER:/MORTIMER:
    prefix itself.)
    """
    return f"<sensitive turn {current_turn_id()}: {len(text)} chars withheld>"


def arm_user_turn(text: str, turn_id: str | None = None) -> bool:
    """Arm for a CLOSED user turn (spoken or typed). Consumes a pending
    credential prompt, and sets one when the turn leaves a value unsaid."""
    try:
        holder = current_sensitive_turn.get()
        pending = holder.take_credential_prompt() if holder is not None else False
        result = arm_from_text(text, turn_id, credentials=True, credential_pending=pending)
        if holder is not None and leaves_credential_pending(text):
            holder.credential_prompted = True
        return result
    except Exception:  # noqa: BLE001 — runs inside the voice loop
        return False


def note_assistant_reply(text: str) -> None:
    """Remember that Mortimer asked for a credential, so the next user turn
    is read as the value."""
    try:
        holder = current_sensitive_turn.get()
        if holder is not None and asks_for_credential(text):
            holder.credential_prompted = True
    except Exception:  # noqa: BLE001
        pass
