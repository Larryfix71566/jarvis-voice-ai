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

from jarvis.sensitive import detect_financial


class SensitiveTurn:
    """Mutable per-session holder for the current turn's sensitivity.

    Deliberately not a dataclass and not frozen: every suppression site holds
    the SAME instance and must see mutations.
    """

    __slots__ = ("armed", "turn_id", "kind")

    def __init__(self) -> None:
        self.armed: bool = False
        self.turn_id: str | None = None
        self.kind: str | None = None

    def arm(self, kind: str, turn_id: str | None = None) -> None:
        """Mark the current turn sensitive. Idempotent within a turn."""
        self.armed = True
        self.kind = kind
        if self.turn_id is None:
            self.turn_id = turn_id or uuid.uuid4().hex[:8]

    def clear(self) -> None:
        """End of turn. Always safe to call, armed or not."""
        self.armed = False
        self.turn_id = None
        self.kind = None

    def is_armed(self) -> bool:
        return self.armed


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


def current_turn_id() -> str:
    """The armed turn's id, for redacted log lines. '-' when not armed/unset."""
    holder = current_sensitive_turn.get()
    if holder is None or holder.turn_id is None:
        return "-"
    return holder.turn_id


def arm_from_text(text: str, turn_id: str | None = None) -> bool:
    """Run detection on `text` and arm the current turn if it matches.

    Called on BOTH the user text and the assistant reply (review F2). Returns
    True when it armed. Total: a missing holder is a no-op, not a crash — this
    runs inside the voice loop.
    """
    match = detect_financial(text)
    if match is None:
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
    holder.arm(match.kind, turn_id)
    return True


def redacted(text: str) -> str:
    """The line that replaces a transcript print on a sensitive turn.

    Carries the turn id and a length ONLY — never a character of content,
    never the detected kind (the kind is itself a hint about the value).
    (review F20: no `role` parameter — the caller supplies the USER:/MORTIMER:
    prefix itself.)
    """
    return f"<sensitive turn {current_turn_id()}: {len(text)} chars withheld>"
