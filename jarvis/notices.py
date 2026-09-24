"""Notice outbox (status spec T3.2, L12).

Barge-in survival lets a delegation finish after its voice turn — and after
its whole session — ended. Before this module such a result went to a dead
pipeline, or was logged `delegate_late_result_undeliverable` and lost
(fact 3.5). It now lands here, persistently, and is spoken ONCE, after the
greeting, at the next connect (`jarvis/bot/pipeline.py`'s
on_client_connected). The daily status job (P4) writes here too.

Kill switch `JARVIS_NOTICES_ENABLED` (default on), checked only inside
`add_notice` and `take_pending`: off, nothing is written and nothing is read.
Neither function ever raises — a notice must never break a delegation or a
greeting.
"""

from __future__ import annotations

import logging
import os

from jarvis.db import get_conn, now_iso

logger = logging.getLogger(__name__)

MAX_NOTICE_CHARS = 600
MAX_DELIVERED_PER_CONNECT = 5
NOTICES_ENABLED_ENV = "JARVIS_NOTICES_ENABLED"
KINDS = ("late_result", "daily_status")


def _enabled() -> bool:
    value = os.environ.get(NOTICES_ENABLED_ENV, "")
    return value.strip().lower() not in ("false", "0", "no", "off")


def add_notice(kind: str, source: str, text: str) -> int:
    """Queue one notice; returns its id, or -1 when disabled or on error."""
    if not _enabled():
        return -1
    if kind not in KINDS:
        logger.warning("notice_rejected kind=%s source=%s", kind, source)
        return -1
    try:
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO notices (created_at, kind, source, text) "
                "VALUES (?, ?, ?, ?)",
                (now_iso(), kind, str(source), str(text)[:MAX_NOTICE_CHARS]),
            )
            conn.commit()
            notice_id = int(cur.lastrowid)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — must never break the caller
        logger.warning("notice_add_failed kind=%s source=%s error=%s",
                       kind, source, exc)
        return -1
    logger.info("notice_added id=%d kind=%s source=%s", notice_id, kind, source)
    return notice_id


def take_pending(limit: int = MAX_DELIVERED_PER_CONNECT) -> list[dict]:
    """Oldest undelivered notices, marked delivered in the same transaction."""
    if not _enabled():
        return []
    try:
        conn = get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id, created_at, kind, source, text FROM notices "
                "WHERE delivered_at IS NULL ORDER BY created_at, id LIMIT ?",
                (int(limit),),
            ).fetchall()
            items = [dict(row) for row in rows]
            if items:
                conn.executemany(
                    "UPDATE notices SET delivered_at = ? WHERE id = ?",
                    [(now_iso(), item["id"]) for item in items],
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — must never break the greeting
        logger.warning("notice_take_failed error=%s", exc)
        return []
    if items:
        logger.info("notices_delivered count=%d ids=%s",
                    len(items), [item["id"] for item in items])
    return items


def render_for_greeting(items: list[dict]) -> str:
    """The greeting suffix for `items`; "" when there are none."""
    if not items:
        return ""
    texts = [str(item.get("text", "")) for item in items]
    return (" While they were away: " + " / ".join(texts)
            + " Mention these in one or two short sentences after greeting.")
