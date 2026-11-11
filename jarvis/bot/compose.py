"""Answer composer: one composed answer per request (contract 1.5 to 1.10).

Pure and synchronous: no pipecat, network, database or timers.  One
``AnswerComposer`` lives per connection.  The pipeline's display emit sites
call ``compose`` at the moment they emit; ``delegate_start`` and
``delegate_done`` call ``delegation_started`` and ``delegation_finished``,
and ``take_completion`` yields the ``complete: true`` re-send.

Invariants (each pinned by ``tests/unit/test_compose.py``):
- a sensitive turn, a protected or confidential payload, ``read_clipboard``,
  a tool without a template, or any build or size failure sends the legacy
  payload unchanged, with no ``layout`` and no ``answer_id``;
- a real result is never suppressed;
- nothing here reads the environment except ``composed_answers_enabled``.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from jarvis.bot import compose_templates as templates
from jarvis.bot.compose_schema import (
    TRUNCATION_BLOCK_ID,
    compact_size,
    sanitize_layout_urls,
    truncate_layout,
    validate_envelope,
)
from jarvis.bot.sensitive_turn import is_sensitive

_logger = logging.getLogger(__name__)

MAX_ANSWERS = 8
MAX_RESULTS_PER_ANSWER = 7  # 7 x 3 blocks + header + sources = 23 <= 24
MAX_TRACKED_REQUESTS = 64
COMPOSED_TOOL = "composed_answer"
NOT_COMPOSED_TOOLS = frozenset({"read_clipboard", "protected_result"})
APPROVED_POLICY = "approved_external"
_ENABLED_VALUES = ("true", "1", "yes", "on")


def composed_answers_enabled(env: Any = None) -> bool:
    """Kill switch, default OFF until the app understands ``answer_id`` (C4)."""
    source = os.environ if env is None else env
    return str(source.get("JARVIS_COMPOSED_ANSWERS_ENABLED", "")).strip().lower() in _ENABLED_VALUES


class _Answer:
    __slots__ = ("answer_id", "last_complete", "parts", "revision")

    def __init__(self, answer_id: str) -> None:
        self.answer_id = answer_id
        self.revision = 0
        self.parts: list[dict] = []
        self.last_complete: bool | None = None


class AnswerComposer:
    def __init__(self, *, is_sensitive: Callable[[], bool] = is_sensitive,
                 now: Callable[[], float] = time.time,
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())) -> None:
        self._is_sensitive = is_sensitive
        self._now = now
        self._new_id = new_id
        self._answers: OrderedDict[str, _Answer] = OrderedDict()
        self._inflight: OrderedDict[str, set[str]] = OrderedDict()

    # ------------------------------------------------------------ state

    def delegation_started(self, request_id: str | None, run_id: str) -> None:
        if not request_id:
            return
        self._inflight.setdefault(request_id, set()).add(run_id)
        while len(self._inflight) > MAX_TRACKED_REQUESTS:
            self._inflight.popitem(last=False)

    def delegation_finished(self, request_id: str | None, run_id: str) -> None:
        if not request_id:
            return
        runs = self._inflight.get(request_id)
        if runs is None:
            return
        runs.discard(run_id)
        if not runs:
            del self._inflight[request_id]

    def _open(self, request_id: str) -> bool:
        return bool(self._inflight.get(request_id))

    # ---------------------------------------------------------- building

    def _build(self, answer_id: str, parts: list[dict], revision: int, complete: bool) -> dict | None:
        """Return the composed payload, or None to fall back (never raises)."""
        tool = "-"
        try:
            tool = str(parts[-1]["payload"].get("tool"))
            layout = templates.build_layout(parts, revision=revision, complete=complete)
            layout = sanitize_layout_urls(layout)
            payload = templates.legacy_fields(parts, layout["title"], now=self._now())
            payload["answer_id"] = answer_id
            truncated = truncate_layout(layout, envelope_bytes=compact_size(payload))
            if truncated is None:
                _logger.warning("compose_fallback tool=%s reason=size_or_invalid", tool)
                return None
            kept, before = len(truncated["blocks"]), len(layout["blocks"])
            if kept != before:
                _logger.warning("compose_truncated answer=%s kept=%d dropped=%d",
                                answer_id, kept, max(0, before - kept))
            if not any(b.get("type") != "header" and b.get("id") != TRUNCATION_BLOCK_ID
                       for b in truncated["blocks"]):
                _logger.warning("compose_fallback tool=%s reason=no_content", tool)
                return None
            payload["layout"] = truncated
            problems = validate_envelope(payload)
            if problems:
                _logger.warning("compose_fallback tool=%s reason=invalid problems=%d", tool, len(problems))
                return None
            return payload
        except Exception as exc:  # noqa: BLE001 - a composer bug must never hide a result
            _logger.warning("compose_fallback tool=%s reason=error error_type=%s",
                            tool, type(exc).__name__[:64])
            return None

    def _completion(self, ans: _Answer) -> dict | None:
        """The ``complete: true`` re-send of ``ans`` (revision + 1), recorded."""
        if not ans.parts or ans.last_complete is not False:
            return None
        payload = self._build(ans.answer_id, ans.parts, ans.revision + 1, True)
        if payload is None:
            return None
        ans.revision += 1
        ans.last_complete = True
        return payload

    def _passes_through(self, payload: dict) -> bool:
        if self._is_sensitive():
            return True
        policy = payload.get("data_policy")
        if policy is not None and policy != APPROVED_POLICY:
            return True
        tool = payload.get("tool")
        if tool in NOT_COMPOSED_TOOLS or "content" in payload:
            return True
        if tool not in templates.TEMPLATES:
            return True
        return "answer_id" in payload or "layout" in payload

    # ----------------------------------------------------------- compose

    def compose(self, payload: dict, *, request_id: str | None) -> list[dict]:
        """Payloads to send, in order; the last one is the main payload."""
        if not isinstance(payload, dict):
            return [payload]
        hints = payload.pop("layout_hints", None)
        if self._passes_through(payload):
            return [payload]
        part = templates.part_for(payload, hints)
        if part is None:
            return [payload]

        if not request_id:  # stand-alone answer, never stored (rule 5)
            built = self._build(self._new_id(), [part], 1, True)
            return [built] if built is not None else [payload]

        prefix: list[dict] = []
        ans = self._answers.get(request_id)
        if ans is not None and len(ans.parts) >= MAX_RESULTS_PER_ANSWER:
            done = self._completion(ans)
            if done is not None:
                prefix.append(done)
            del self._answers[request_id]
            ans = None
        is_new = ans is None
        if is_new:
            ans = _Answer(self._new_id())
        complete = not self._open(request_id)
        built = self._build(ans.answer_id, [*ans.parts, part], ans.revision + 1, complete)
        if built is None:
            return [*prefix, payload]
        ans.parts.append(part)
        ans.revision += 1
        ans.last_complete = complete
        if is_new:
            while len(self._answers) >= MAX_ANSWERS:
                _, oldest = self._answers.popitem(last=False)
                done = self._completion(oldest)
                if done is not None:
                    prefix.append(done)
            self._answers[request_id] = ans
        else:
            self._answers.move_to_end(request_id)
        return [*prefix, built]

    def take_completion(self, request_id: str | None) -> dict | None:
        """A ``complete: true`` re-send once nothing is in flight, else None."""
        if not request_id:
            return None
        ans = self._answers.get(request_id)
        if ans is None:
            return None
        if self._is_sensitive():
            del self._answers[request_id]
            return None
        if self._open(request_id):
            return None
        return self._completion(ans)
