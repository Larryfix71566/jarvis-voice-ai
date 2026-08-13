"""Run-id correlation for concurrent sub-agent delegations (plan D3).

The ContextVar holds the *live RunLogger instance*, not a bare run_id
string. This is deliberate (plan §3 D3, revision 2): SkillRegistry.call()
needs a way to record an mcp_call event on the same run buffer that
SubAgent is writing tool_call/tool_result events to, so that MCP-layer
failures land in the same JSONL payload as everything else instead of
being dropped or split across two write paths. A ContextVar holding only
the id string would give SkillRegistry no route back to that buffer.

contextvars propagate correctly across asyncio task boundaries, so
concurrent delegations (jarvis/agents/delegate.py's semaphore-gated
parallel dispatch) each see their own RunLogger with no additional
plumbing.

This module must not import jarvis.runlog.store at runtime — store.py has
no need of this module, and importing it here would risk a cycle via
jarvis/runlog/__init__.py. The RunLogger type is therefore only known at
type-check time.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from jarvis.runlog.store import RunLogger

current_run_logger: "ContextVar[RunLogger | None]" = ContextVar(
    "current_run_logger", default=None
)


def get_run_logger() -> "RunLogger | None":
    """The RunLogger for the currently-executing sub-agent run, if any."""
    return current_run_logger.get()


def get_run_id() -> str | None:
    """Convenience: the current run's id, or None outside any run."""
    logger = current_run_logger.get()
    return logger.run_id if logger is not None else None


@contextmanager
def run_logger_scope(logger: "RunLogger | None") -> Iterator[None]:
    """Set current_run_logger for the duration of the block, then restore.

    Passing None is legal and means "explicitly no run" (used by tests and
    by any caller that wants to suppress MCP-layer correlation).
    """
    token = current_run_logger.set(logger)
    try:
        yield
    finally:
        current_run_logger.reset(token)
