"""jarvis/memory_extraction_worker.py — Phase 2 standalone per-exchange
memory extraction service (MORTIMER_OPTIMIZATION_PLAN.md Phase 2,
"Extraction Gate", task 1: "Async post-turn extraction worker — new
service (Procfile entry now, launchd later)").

Companion to jarvis/memory_extraction.py, which does the actual candidate
extraction + novelty gate for ONE finished exchange. This module's whole
job is turning the conversations table into a stream of finished exchanges
and feeding them there, as its own long-lived process (own Procfile line,
not an in-process asyncio task started by the bot the way
jarvis/bot/memory_watcher.py's MemorySweepWatcher is) — Larry's explicit
choice (2026-09-02) of a full rearchitecture over a narrower "close the
gaps in the existing watcher" alternative.

THE PAIRING PROBLEM this module exists to solve: conversations rows are
role-tagged (user | assistant | tool) but nothing marks which user row a
given assistant row replies to, or which rows have already been turned
into an exchange. A single global watermark (memory_extraction_cursor,
migration 0016) is enough to say "everything up to here has been looked
at", but NOT enough on its own to say "everything up to here has been
correctly PAIRED" — a user row's assistant reply can land in a LATER poll
(ordinary latency), or never land at all: jarvis/bot/transcript_log.py's
P2/P6 privacy gate deliberately never persists a sensitive assistant
reply, so a dangling user row with no reply ever coming is DESIGNED
behavior of this codebase, not a rare glitch. A cursor that blocks
advancement until a pairing resolves would stall the very first time that
gate fires — and since the cursor is global, it would stall extraction
for every OTHER session too, not just the one with the dangling turn.

The fix (migration 0017, memory_extraction_pending): track the one
open/unresolved user turn per session in its OWN small table, separate
from the cursor. The cursor advances unconditionally, every poll, to the
last row id fetched. Pairing state survives across polls (and worker
restarts) by living in the pending table rather than in this process's
memory. A pending row older than ORPHAN_TIMEOUT_S is dropped, ungracefully
but deliberately: giving up on it matches the pipeline's own privacy
intent (if the reply side was never safe to persist, extracting from the
lone user question isn't obviously safer either), and losing one
extraction opportunity from an unanswered turn is a low-stakes, rare gap
— not the kind of "facts Larry actually stated" loss the plan's exit
criteria cares about, since a turn with no reply is unusual to begin with.

WHY NOT persist a "processed" flag per conversations row instead of a
pending-turn table: the pairing problem is about PENDING work (what's
still open), and a table that tracks only the open items is one row per
session at most (cheap, self-cleaning), versus a flag on every row ever
written (unbounded growth, and no clearer for it — you would still need
to scan for "the most recent user row without a following assistant row"
to recover pairing state after a restart).

CRASH SAFETY / AT-LEAST-ONCE, NOT EXACTLY-ONCE: each tick's cursor advance
and pending-table updates commit on ONE connection at the end of the tick,
but jarvis.memory_extraction.extract_from_exchange opens and commits on
its OWN separate connection per exchange (matching jarvis.memory's own
update_memory_from_session convention). If the process dies between an
exchange's extraction committing and the tick's own cursor-advance commit,
that exchange is re-fetched and re-extracted on the next poll. This is
deliberately accepted rather than engineered away with two-phase commit or
similar: jarvis.memory_extraction's novelty gate already makes a repeat
extraction of the same exchange cheap and safe (an exact-key fact refresh,
a same-tier near-duplicate recurrence bump, or a within-session observation
duplicate bump — never a silent duplicate row), so a rare crash-recovery
re-run costs a little redundant bookkeeping, not corrupted memory.

Summary regeneration is NOT this module's job — see
jarvis/memory_extraction.py's own docstring for why that stays on
jarvis.memory.update_memory_from_session's existing whole-session path.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable

from jarvis.config import Settings, load_settings
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.logging_config import setup_logging
from jarvis.memory_extraction import extract_from_exchange

logger = logging.getLogger(__name__)

# [guessing] Starting values, not load-tested — easy to override without a
# code change (env var) or a deploy (constant) if Larry's actual usage
# pattern wants something different. 20s is a deliberate, large step down
# from MemorySweepWatcher's 300s default: per-exchange extraction is the
# whole point of Phase 2, and a poll that finds nothing new costs one
# cheap SQLite query, not an LLM call — the cost only shows up when there
# is real work to do.
DEFAULT_POLL_INTERVAL_S = 20.0

# [guessing] Long enough to comfortably outlast a slow LLM call or a brief
# network hiccup; short enough that a permanently-orphaned (sensitive-skip)
# pending row does not linger indefinitely. One row per session either way
# — the cost of getting this wrong in either direction is small.
DEFAULT_ORPHAN_TIMEOUT_S = 600.0


def _poll_interval_s() -> float:
    raw = os.environ.get("JARVIS_MEMORY_EXTRACTION_POLL_INTERVAL_S")
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "invalid JARVIS_MEMORY_EXTRACTION_POLL_INTERVAL_S=%r, using default", raw
            )
    return DEFAULT_POLL_INTERVAL_S


def _orphan_timeout_s() -> float:
    raw = os.environ.get("JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S")
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "invalid JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S=%r, using default", raw
            )
    return DEFAULT_ORPHAN_TIMEOUT_S


def _iso_minus(iso_str: str, seconds: float) -> str:
    """`iso_str` (as produced by jarvis.db.now_iso) minus `seconds`,
    formatted the same way -- used to build the orphan-cleanup cutoff."""
    dt = datetime.fromisoformat(iso_str)
    return (dt - timedelta(seconds=seconds)).isoformat()


def _get_cursor(conn) -> int:
    row = conn.execute(
        "SELECT last_processed_conversation_id FROM memory_extraction_cursor WHERE id = 1"
    ).fetchone()
    return row["last_processed_conversation_id"] if row is not None else 0


def _set_cursor(conn, value: int) -> None:
    conn.execute(
        "UPDATE memory_extraction_cursor SET last_processed_conversation_id = ?, "
        "updated_at = ? WHERE id = 1",
        (value, now_iso()),
    )


def _get_pending(conn, session_id: str):
    return conn.execute(
        "SELECT * FROM memory_extraction_pending WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def _set_pending(
    conn, session_id: str, content: str, turn_id: int, first_seen_at: str
) -> None:
    conn.execute(
        "INSERT INTO memory_extraction_pending "
        "(session_id, user_content, user_turn_id, first_seen_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "user_content = excluded.user_content, "
        "user_turn_id = excluded.user_turn_id, "
        "first_seen_at = excluded.first_seen_at",
        (session_id, content, turn_id, first_seen_at),
    )


def _clear_pending(conn, session_id: str) -> None:
    conn.execute(
        "DELETE FROM memory_extraction_pending WHERE session_id = ?", (session_id,)
    )


def _group_by_session(rows: list) -> dict:
    """Preserves fetch order (id ASC) within each session's list — Python
    dicts keep insertion order, so iterating this dict processes sessions
    in the order their first new row appeared, and each session's own rows
    stay in strict chronological order."""
    by_session: dict[str, list] = {}
    for row in rows:
        by_session.setdefault(row["session_id"], []).append(row)
    return by_session


async def tick_once(
    settings: Settings,
    db_path: str | None = None,
    client_factory: Callable[[Settings], Any] | None = None,
) -> dict:
    """One poll cycle. Public for tests; never raises — mirrors
    MemorySweepWatcher.tick_once's discipline so one broken poll can never
    take the whole service down, exactly as one bad exchange inside
    extract_from_exchange itself can never wedge this loop.

    Returns {"rows": n, "exchanges": n, "cursor": new_or_unchanged_cursor}
    (plus "error": True on the rare tick-level failure, distinct from a
    single exchange's own failure — extract_from_exchange already reports
    that internally and never raises here).
    """
    try:
        conn = get_conn(db_path)
        try:
            cursor = _get_cursor(conn)
            rows = conn.execute(
                "SELECT * FROM conversations WHERE id > ? ORDER BY id ASC",
                (cursor,),
            ).fetchall()
            if not rows:
                return {"rows": 0, "exchanges": 0, "cursor": cursor}

            now = now_iso()
            exchange_count = 0

            for session_id, session_rows in _group_by_session(rows).items():
                pending = _get_pending(conn, session_id)
                pending_content = pending["user_content"] if pending else None
                pending_turn_id = pending["user_turn_id"] if pending else None
                pending_first_seen = pending["first_seen_at"] if pending else None

                for row in session_rows:
                    role = row["role"]
                    if role == "user":
                        # A newer user turn supersedes an older unresolved
                        # one (e.g. two user turns before any reply) —
                        # only the most recent utterance is ever the
                        # trigger for the next assistant reply. The
                        # superseded turn is never extracted; a documented,
                        # rare edge case, not a silent bug.
                        pending_content = row["content"]
                        pending_turn_id = row["id"]
                        pending_first_seen = now
                    elif role == "assistant":
                        if pending_content is not None:
                            await extract_from_exchange(
                                settings,
                                session_id,
                                pending_content,
                                row["content"],
                                row["id"],
                                client_factory=client_factory,
                            )
                            exchange_count += 1
                            pending_content = None
                            pending_turn_id = None
                            pending_first_seen = None
                        # else: an assistant row with nothing pending
                        # (proactive message, or its user turn already
                        # timed out of the pending table) — nothing the
                        # user said to extract from; skip.
                    # role == "tool": no pairing effect, passed over.

                if pending_content is not None:
                    _set_pending(
                        conn, session_id, pending_content, pending_turn_id,
                        pending_first_seen or now,
                    )
                else:
                    _clear_pending(conn, session_id)
                # Item 13 (2026-09-17): release the write lock NOW. The
                # INSERT/DELETE above opened an implicit transaction on this
                # connection, and extract_from_exchange writes through a
                # connection of its own -- so without this commit every
                # session after the first blocks on this one, in the same
                # thread, until the busy timeout fails it. Measured on the
                # 2026-09-16 backfill: 28 of 122 exchanges lost, every one
                # inside upsert_fact or add_observation.
                conn.commit()

            new_cursor = rows[-1]["id"]
            _set_cursor(conn, new_cursor)

            cutoff = _iso_minus(now, _orphan_timeout_s())
            conn.execute(
                "DELETE FROM memory_extraction_pending WHERE first_seen_at < ?",
                (cutoff,),
            )

            conn.commit()
            return {"rows": len(rows), "exchanges": exchange_count, "cursor": new_cursor}
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — one bad poll must never crash the worker
        logger.exception("memory_extraction_tick_failed")
        return {"rows": 0, "exchanges": 0, "cursor": None, "error": True}


async def run_forever(
    settings: Settings | None = None,
    db_path: str | None = None,
    poll_interval_s: float | None = None,
    client_factory: Callable[[Settings], Any] | None = None,
) -> None:
    """The service loop. Runs until cancelled (task cancellation in tests)
    or the process is killed (SIGTERM under a process manager — no custom
    signal handling here, matching every other long-lived process in this
    repo; none trap signals themselves)."""
    settings = settings or load_settings()
    interval = poll_interval_s if poll_interval_s is not None else _poll_interval_s()
    logger.info("memory_extraction_worker_started poll_interval_s=%s", interval)
    while True:
        result = await tick_once(settings, db_path=db_path, client_factory=client_factory)
        if result.get("exchanges"):
            logger.info(
                "memory_extraction_tick rows=%s exchanges=%s cursor=%s",
                result.get("rows"), result.get("exchanges"), result.get("cursor"),
            )
        await asyncio.sleep(interval)


def main() -> None:
    setup_logging(os.environ.get("JARVIS_LOG_LEVEL", "INFO"))
    run_migrations()
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("memory_extraction_worker_stopped")


if __name__ == "__main__":
    main()
