"""LateResultNeutralizer — MORTIMER_SESSION_MISSES_PLAN.md S6-S8.

A delegation orphaned by barge-in delivers its result as a user-role
context note that ends "Relay this to the user …" (jarvis/agents/
delegate.py `_deliver`). Delivered once, that imperative then sits in
context for the rest of the session, and on 2026-09-03 Haiku obeyed it a
second time on the very next user turn — repeating a result the user had
just heard (192 output tokens, 244 spoken characters) and, because
pipecat holds function-call results until the bot stops speaking, holding
the NEW answer behind 17 s of redundant speech (user_end->llm_done 23542
ms for a 7.6 s analyst run).

This observer rewrites the note IN PLACE — the same dict object the
aggregator holds; pipecat's LLMContext.add_messages extends its list
with the caller's objects (llm_context.py:394) and get_messages reads
that list at request time (:240) — to a non-imperative record once the
relay turn has ended. State machine:

  IDLE --arm(note)--> ARMED --LLMFullResponseStartFrame--> RELAYING
  RELAYING --LLMFullResponseEndFrame | InterruptionFrame--> neutralize, IDLE

A stale LLMFullResponseEndFrame seen while ARMED (the response that was
already in flight when the note landed) is ignored: neutralizing then
would hide a result the model has not relayed yet — a silent LOSS, which
is worse than the repeat this fixes. An interruption during the relay
counts as done: the user chose to move on, and the content stays in
context as a record for "what did you find?".

Fixed in code rather than prompt because two prompt-only rules failed on
this same model in this same session (markdown to TTS, specialist
attribution) — the repo's own lesson (jarvis_units, the model floor): a
rule that must hold is bound in code, not persuaded into a model.

Same BaseObserver/on_push_frame pattern as jarvis/bot/interruption.py and
jarvis/bot/usage_watcher.py. Kill switch: Settings.
jarvis_late_result_neutralize_enabled (JARVIS_LATE_RESULT_NEUTRALIZE_
ENABLED), default True; False restores the exact pre-plan behaviour.
"""

from __future__ import annotations

import logging

from pipecat.frames.frames import (
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

logger = logging.getLogger(__name__)

#: What the note becomes once relayed. Non-imperative on purpose: a
#: record the model can consult if asked, never an instruction to speak.
LATE_RESULT_RELAYED_NOTE = (
    "[system] (A background result was delivered here and has already been "
    "relayed, or the user moved on. Do not repeat it unless asked.)"
)


class LateResultNeutralizer(BaseObserver):
    def __init__(self, *, enabled: bool = True) -> None:
        super().__init__()
        self._enabled = enabled
        self._pending: list[dict] = []
        self._relaying = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def arm(self, message: dict) -> None:
        """Register a just-injected late-result note — the SAME dict object
        that is handed to add_messages, so the in-place rewrite below is
        what the next get_messages() returns."""
        if not self._enabled:
            return
        self._pending.append(message)
        self._relaying = False

    async def on_push_frame(self, data: FramePushed) -> None:
        if not self._enabled or not self._pending:
            return
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        frame = data.frame
        if isinstance(frame, LLMFullResponseStartFrame):
            self._relaying = True
            return
        if isinstance(frame, (LLMFullResponseEndFrame, InterruptionFrame)) and self._relaying:
            for message in self._pending:
                message["content"] = LATE_RESULT_RELAYED_NOTE
            logger.info(
                "late_result_neutralized count=%d via=%s",
                len(self._pending), type(frame).__name__,
            )
            self._pending.clear()
            self._relaying = False
