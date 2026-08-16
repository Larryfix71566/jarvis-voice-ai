"""Retention pruning for the LLM Council (MORTIMER_LLM_COUNCIL_V2_PLAN.md
V11). Structural copy of jarvis/runlog/prune.py — same pattern, different
tables/directory.

Runs once at bot startup (jarvis/bot/pipeline.py, beside the existing
runlog prune call), same try/except-log shape. Best-effort: the caller
wraps this in try/except and logs one INFO line with the counts; prune()
itself does not raise.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.council.council import COUNCIL_LOG_DIR
from jarvis.db import get_conn

logger = logging.getLogger(__name__)


def prune(
    retention_days: int,
    db_path: str | Path | None = None,
    root: Path | None = None,
) -> dict:
    """Delete council_rounds/council_scores rows and logs/council/<date>/
    directories older than `retention_days` (by `council_rounds.started_at`).
    Returns {"rounds_deleted": n, "dirs_deleted": n}. `retention_days <= 0`
    disables pruning and returns zeros immediately."""
    if retention_days <= 0:
        return {"rounds_deleted": 0, "dirs_deleted": 0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    rounds_deleted = 0
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "SELECT round_id FROM council_rounds WHERE started_at < ?", (cutoff,)
        )
        expired_ids = [row[0] for row in cur.fetchall()]
        if expired_ids:
            placeholders = ",".join("?" for _ in expired_ids)
            # Child before parent, same order as runlog's
            # agent_events-before-agent_runs.
            conn.execute(
                f"DELETE FROM council_scores WHERE round_id IN ({placeholders})",
                expired_ids,
            )
            conn.execute(
                f"DELETE FROM council_rounds WHERE round_id IN ({placeholders})",
                expired_ids,
            )
            conn.commit()
            rounds_deleted = len(expired_ids)
    finally:
        conn.close()

    dirs_deleted = 0
    base = (root if root is not None else Path(".")) / COUNCIL_LOG_DIR
    if base.exists():
        cutoff_date = cutoff[:10]
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            # Directory names are YYYY-MM-DD (council.py's _payload_path);
            # string comparison is correct for that format.
            if entry.name < cutoff_date:
                shutil.rmtree(entry, ignore_errors=True)
                dirs_deleted += 1

    return {"rounds_deleted": rounds_deleted, "dirs_deleted": dirs_deleted}
