"""Voice-workflow processors — MORTIMER_VOICE_WORKFLOWS_PLAN.md D5/D6.

Two FrameProcessors around the Supervisor LLM, sharing one VoiceTurnState:

    aggregators.user() -> VoiceWorkflowInjector -> llm -> ReplyGuard -> transcript -> tts

VoiceWorkflowInjector (the `user` hook) sees every LLMContextFrame. When
the context's last message is a NEW real user turn it (1) tombstones the
previous turn's guidance and correction notes in place, (2) records the
turn text for the guard, (3) resets the guard's one-correction budget and
(4) appends the matched voice workflow's guidance as a user-role
"[system]" note. Turn tracking runs even when injection is disabled,
because the guard depends on it.

ReplyGuard (the backstop) re-chunks the LLM's text into sentences, checks
each with jarvis.voice_workflows.sentence_violation before it can reach
TTS, and in "correct" mode drops the first violating sentence and the rest
of that response, then asks for ONE regeneration with a correction note.
A second violation in the same user turn is spoken and logged as a
capability gap: the guard never loops and never silences Mortimer twice.

Same "[system]" note channel and in-place rewrite as late_result.py; same
push_frame test seam as speaker_gate.py.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Coroutine

from pipecat.frames.frames import (
    Frame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.voice_workflows import (
    SENTENCE_END_RE,
    TOMBSTONE,
    correction_note,
    is_capability_question,
    is_explicit_command_ask,
    log_capability_gap,
    match_voice_workflow,
    normalize_guard_mode,
    render_guidance,
    sentence_violation,
)

__all__ = [
    "ReplyGuard", "VoiceTurnState", "VoiceWorkflowInjector",
    "is_real_user_message", "normalize_guard_mode",
]

logger = logging.getLogger(__name__)

class VoiceTurnState:
    """Per-session state shared by the injector, the guard and pipeline.py."""

    __slots__ = ("user_text", "corrected", "notes", "last_user_message")

    def __init__(self) -> None:
        self.user_text: str = ""
        self.corrected: bool = False
        self.notes: list[dict] = []
        self.last_user_message: dict | None = None

    def start_turn(self, message: dict) -> None:
        for note in self.notes:
            note["content"] = TOMBSTONE
        self.notes.clear()
        self.last_user_message = message
        self.user_text = str(message.get("content") or "")
        self.corrected = False


def is_real_user_message(message: Any) -> bool:
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    content = message.get("content")
    return (isinstance(content, str) and bool(content.strip())
            and not content.lstrip().startswith("[system]"))


class VoiceWorkflowInjector(FrameProcessor):
    def __init__(self, state: VoiceTurnState, *, inject_enabled: bool = True,
                 gate: dict | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._state = state
        self._inject_enabled = inject_enabled
        # D-L5 — runtime.handoff_gate: an explicit ask for a command opens
        # show_commands for NEEDS_INPUT_WINDOW_S (jarvis/bot/handoff_tools.py).
        self._gate = gate

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                self._on_context(frame.context)
            except Exception:  # noqa: BLE001 — never break a voice turn
                logger.exception("voice_workflow_injector_failed")
        await self.push_frame(frame, direction)

    def _on_context(self, context: Any) -> None:
        messages = context.get_messages()
        if not messages:
            return
        last = messages[-1]
        if not is_real_user_message(last) or last is self._state.last_user_message:
            return
        self._state.start_turn(last)
        if self._gate is not None and is_explicit_command_ask(self._state.user_text):
            self._gate["explicit_ask_at"] = time.monotonic()
            logger.info("voice_explicit_command_ask")
        if not self._inject_enabled:
            return
        wf = match_voice_workflow(user_text=self._state.user_text)
        if wf is None:
            return
        note = {"role": "user", "content": render_guidance(wf)}
        context.add_message(note)
        self._state.notes.append(note)
        logger.info("voice_workflow_injected hook=user name=%s", wf.name)


class ReplyGuard(FrameProcessor):
    def __init__(
        self,
        state: VoiceTurnState,
        *,
        mode: str,
        on_correct: Callable[[str], Awaitable[None]],
        session_id: str | None = None,
        is_sensitive: Callable[[], bool] = lambda: False,
        schedule: Callable[[Coroutine], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._state = state
        self._mode = normalize_guard_mode(mode)
        self._on_correct = on_correct
        self._session_id = session_id
        self._is_sensitive = is_sensitive
        self._schedule = schedule
        self._reset_response()

    @property
    def mode(self) -> str:
        return self._mode

    def _reset_response(self) -> None:
        self._in_response = False
        self._function_called = False
        self._buffer = ""
        self._template: LLMTextFrame | None = None
        self._suppressed: tuple[str, str] | None = None   # (kind, sentence)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._mode == "off" or direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMFullResponseStartFrame):
            self._reset_response()
            self._in_response = True
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, InterruptionFrame):
            self._reset_response()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, FunctionCallsStartedFrame):
            self._function_called = True
            if self._suppressed is None:
                await self._drain(direction, final=True, check=False)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMTextFrame) and self._in_response and not self._function_called:
            if self._suppressed is not None:
                return                      # drop the rest of this response
            self._template = frame
            self._buffer += frame.text
            await self._drain(direction, final=False, check=True)
            return
        if isinstance(frame, LLMFullResponseEndFrame) and self._in_response:
            if self._suppressed is None:
                await self._drain(direction, final=True, check=not self._function_called)
            suppressed = self._suppressed
            function_called = self._function_called
            self._reset_response()
            await self.push_frame(frame, direction)
            if suppressed is not None:
                kind, sentence = suppressed
                if function_called:
                    logger.info("reply_guard action=suppressed_then_delegated kind=%s", kind)
                else:
                    self._request_correction(kind, sentence)
            return
        await self.push_frame(frame, direction)

    async def _drain(self, direction: FrameDirection, *, final: bool, check: bool) -> None:
        while self._buffer:
            match = SENTENCE_END_RE.search(self._buffer)
            if match is None:
                if not final:
                    return
                sentence, self._buffer = self._buffer, ""
            else:
                sentence = self._buffer[:match.end()]
                self._buffer = self._buffer[match.end():]
            if check and self._should_suppress(sentence):
                self._buffer = ""
                return
            await self.push_frame(self._text_frame(sentence), direction)

    def _text_frame(self, text: str) -> LLMTextFrame:
        out = LLMTextFrame(text=text)
        if self._template is not None:
            out.skip_tts = self._template.skip_tts
            out.append_to_context = self._template.append_to_context
        return out

    def _should_suppress(self, sentence: str) -> bool:
        kind = sentence_violation(sentence)
        if kind is None:
            return False
        if is_capability_question(self._state.user_text):
            logger.info("reply_guard action=exempt kind=%s", kind)
            return False
        if kind == "handoff" and is_explicit_command_ask(self._state.user_text):
            logger.info("reply_guard action=exempt_explicit_ask kind=%s", kind)
            return False
        if self._mode == "log":
            logger.info("reply_guard action=logged kind=%s", kind)
            return False
        if self._state.corrected:
            logger.info("reply_guard action=allowed_after_retry kind=%s", kind)
            log_capability_gap(
                source="reply_guard", kind=kind, text=sentence,
                user_text=self._state.user_text, session_id=self._session_id,
                sensitive=self._is_sensitive(),
            )
            return False
        self._suppressed = (kind, sentence)
        logger.info("reply_guard action=suppressed kind=%s", kind)
        return True

    def _request_correction(self, kind: str, sentence: str) -> None:
        self._state.corrected = True
        wf = match_voice_workflow(reply_kinds=[kind])
        note = correction_note(kind, sentence, wf)
        coro = self._on_correct(note)
        if self._schedule is not None:
            self._schedule(coro)
        else:
            self.create_task(coro, "reply_guard_correction")
