"""Retention pruning for the run log (plan D10).

Runs once at bot startup (jarvis/bot/pipeline.py's run_session, before the
pipeline is built) — startup is the only moment guaranteed to happen
regularly, sit outside the latency-critical voice path, and require no
scheduler. Best-effort: the caller wraps this in try/except and logs one
INFO line with the counts (plan §5.8); prune() itself does not raise.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.db import get_conn
from jarvis.runlog.store import RUNLOG_DIR

logger = logging.getLogger(__name__)


def prune(
    retention_days: int,
    db_path: str | Path | None = None,
    root: Path | None = None,
) -> dict:
    """Delete agent_runs/agent_events rows and logs/agents/<date>/
    directories older than `retention_days`. Returns
    {"runs_deleted": n, "dirs_deleted": n}. `retention_days <= 0` disables
    pruning and returns zeros immediately."""
    if retention_days <= 0:
        return {"runs_deleted": 0, "dirs_deleted": 0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    runs_deleted = 0
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "SELECT run_id FROM agent_runs WHERE started_at < ?", (cutoff,)
        )
        expired_ids = [row[0] for row in cur.fetchall()]
        if expired_ids:
            placeholders = ",".join("?" for _ in expired_ids)
            conn.execute(
                f"DELETE FROM agent_events WHERE run_id IN ({placeholders})",
                expired_ids,
            )
            conn.execute(
                f"DELETE FROM agent_runs WHERE run_id IN ({placeholders})",
                expired_ids,
            )
            conn.commit()
            runs_deleted = len(expired_ids)
    finally:
        conn.close()

    dirs_deleted = 0
    base = (root if root is not None else Path(".")) / RUNLOG_DIR
    if base.exists():
        cutoff_date = cutoff[:10]
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            # Directory names are YYYY-MM-DD (plan §5.3 start()); string
            # comparison is correct for that format.
            if entry.name < cutoff_date:
                shutil.rmtree(entry, ignore_errors=True)
                dirs_deleted += 1

    return {"runs_deleted": runs_deleted, "dirs_deleted": dirs_deleted}
