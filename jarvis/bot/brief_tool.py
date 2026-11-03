"""daily_brief — the Supervisor's direct mail-headlines tool (WS-13 P3m, plan R.0f).

A direct tool like system_status: no specialist, no delegation. The model
only ever receives one fixed sentence, returned before any mail is read
(R.10.3). The reading happens in a separate task that:

* runs under ``contextvars.copy_context()`` with its OWN ``SensitiveTurn``
  and no foreground ``RunLogger`` (R.10.4), so confidential mail never arms
  the session's holder and never lands in a foreground run log;
* calls the P1 mail server once through ``registry.call_classified`` with a
  host-owned confidential scope (R.10.2, R.10.9);
* assembles a typed card with ``jarvis.brief`` and pushes it to the asking
  native session only, after a final connected check (R.10.5);
* logs content-free events only: names, status codes, durations (R.10.3).
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, tzinfo
from typing import Any, Awaitable, Callable, Mapping

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.brief import assemble_mail_brief, build_brief_payload
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.runlog.context import current_run_logger

_logger = logging.getLogger(__name__)

ENV_BRIEF_ENABLED = "JARVIS_BRIEF_ENABLED"

DAILY_BRIEF_SCHEMA = {
    "type": "function",
    "function": {
        "name": "daily_brief",
        "description": (
            "Shows the user's email headlines (Gmail and AT&T, read-only) as a protected card on "
            "screen. Use it for any question about their email, inbox or new mail. It cannot "
            "send, reply to, delete or read the body of a message."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["mail"]},
            },
            "required": ["scope"],
        },
    },
}

ACK_TEXT = "Putting your mail together."
REFUSAL_TEXT = "The brief needs the Mortimer app."
BAD_SCOPE_TEXT = "daily_brief failed: scope must be mail."

#: One mail_headlines call is bounded at 12 s by the server
#: (mcp_mail.logic.MAIL_CALL_DEADLINE_S); leave a little for the transport.
JOB_TIMEOUT_S = 15.0
MAIL_ARGUMENTS = {"window_hours": 24, "account": "all"}
SOURCE_LABEL = "brief-mail"

_FALSE_WORDS = frozenset({"0", "false", "no", "off"})


def brief_enabled(env: Mapping[str, str] | None = None) -> bool:
    """JARVIS_BRIEF_ENABLED, default on. Only the pipeline registration site
    calls this; the menu, the prompt and the handler follow its boolean."""
    env = os.environ if env is None else env
    return (env.get(ENV_BRIEF_ENABLED) or "true").strip().lower() not in _FALSE_WORDS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_daily_brief_tool(
    *,
    registry: Any,
    send_display: Callable[[dict], Awaitable[Any]],
    eligible: Callable[[], bool],
    connected: Callable[[], bool],
    now: Callable[[], datetime] = _utc_now,
    tz: tzinfo = timezone.utc,
) -> tuple[dict, Callable[[dict], Awaitable[str]]]:
    """Return (openai_tool_schema, async_handler) for daily_brief.

    ``eligible()`` is evaluated when the tool is called (native /ws-client
    session with a loopback peer); ``connected()`` is evaluated again just
    before the card is sent. ``send_display(payload)`` delivers to the asking
    session and nobody else."""
    tasks: set[asyncio.Task] = set()

    async def job() -> None:
        started = time.monotonic()
        _logger.info("brief_job_start scope=mail")
        content: dict | None = None
        error: str | None = None
        try:
            request_id = f"brief-{uuid.uuid4().hex}"
            scope = make_tool_execution_scope(
                request_id, request_id, request_id, "mail_headlines", dict(MAIL_ARGUMENTS),
                DataPolicy("confidential", SOURCE_LABEL))
            envelope = await asyncio.wait_for(
                registry.call_classified("mail_headlines", dict(MAIL_ARGUMENTS),
                                         execution_scope=scope),
                timeout=JOB_TIMEOUT_S)
            _policy, text = validate_tool_result(scope, envelope)
            parsed = json.loads(text)
            content = parsed if isinstance(parsed, dict) else None
            if content is None:
                error = "unusable"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — every failure becomes an honest card
            error = "timeout" if isinstance(exc, asyncio.TimeoutError) else "failed"
            # Only the exception type: its text could carry source bytes.
            _logger.warning("brief_job_source_error type=%s", type(exc).__name__)
        try:
            moment = now()
            assembled = assemble_mail_brief(content, error=error, now=moment, tz=tz)
            payload = build_brief_payload(assembled, result_id=str(uuid.uuid4()), ts=time.time())
        except Exception as exc:  # noqa: BLE001
            _logger.warning("brief_job_assemble_error type=%s", type(exc).__name__)
            return
        statuses = ",".join(f"{a['key']}={a['status']}" for a in assembled["accounts"])
        elapsed_ms = int((time.monotonic() - started) * 1000)
        try:
            still_connected = bool(connected())
        except Exception:  # noqa: BLE001
            still_connected = False
        if not still_connected:
            _logger.info("brief_job_dropped reason=not_connected outcome=%s duration_ms=%d",
                         assembled["outcome"], elapsed_ms)
            return
        try:
            await send_display(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.warning("brief_job_send_failed type=%s duration_ms=%d",
                            type(exc).__name__, elapsed_ms)
            return
        _logger.info("brief_job_done outcome=%s statuses=%s duration_ms=%d",
                     assembled["outcome"], statuses, elapsed_ms)

    async def handler(arguments: dict) -> str:
        args = arguments if isinstance(arguments, dict) else {}
        if args.get("scope") != "mail":
            return BAD_SCOPE_TEXT
        try:
            allowed = bool(eligible())
        except Exception:  # noqa: BLE001 — unknown means not eligible
            allowed = False
        if not allowed:
            _logger.info("brief_refused reason=not_eligible")
            return REFUSAL_TEXT
        ctx = contextvars.copy_context()
        # The job's own holder and no foreground run log (R.10.4).
        ctx.run(current_sensitive_turn.set, SensitiveTurn())
        ctx.run(current_run_logger.set, None)
        task = asyncio.get_running_loop().create_task(job(), context=ctx)
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return ACK_TEXT

    return DAILY_BRIEF_SCHEMA, handler
