"""Sub-agent run logging (MORTIMER_RUN_LOGGING_PLAN.md).

Durable, queryable records of every sub-agent delegation: one agent_runs
row plus N agent_events rows in SQLite (bounded previews, migration 0006
in jarvis/db.py), plus one JSONL file per run under
logs/agents/<date>/<run_id>.jsonl holding the untruncated payloads. See
jarvis/runlog/store.py for the implementation and
MORTIMER_RUN_LOGGING_PLAN.md §3 for the design decisions (D1-D20) that
shape it.
"""

from jarvis.runlog.context import get_run_id, get_run_logger, run_logger_scope
from jarvis.runlog.prune import prune
from jarvis.runlog.store import RunLogger, get_run, list_runs, parse_since

__all__ = [
    "RunLogger",
    "get_run",
    "list_runs",
    "parse_since",
    "get_run_id",
    "get_run_logger",
    "run_logger_scope",
    "prune",
]
