"""mcp-memory logic — voice control of the memory review queue.

Larry 2026-08-21: "Mortimer should have access to control anything in the
interface like the memory panel." The Memory panel's review queue
(MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A3) was console-only: voice
could ANNOUNCE open reviews and OPEN the panel (ui_control), but resolving
one required a click. These two tools close that gap, wired to the
LIBRARIAN — memory is its domain, and resolution is a data action, not a
view action, so it belongs to a specialist rather than to ui_control.

Thin by construction: both tools call jarvis.memory_sweep's OWN
list_open_reviews/resolve_review — the same functions the admin sidecar's
endpoints wrap — so voice, console, and any future surface can never
disagree about what resolving a review does. No second implementation.
"""

from __future__ import annotations

from typing import Any

from jarvis.db import get_conn, run_migrations
from jarvis.memory_sweep import list_open_reviews, resolve_review

# Actions a review supports, by kind — mirrored from resolve_review's
# docstring so the tool can validate before touching the DB and return a
# spoken-friendly error instead of a traceback.
ACTIONS_BY_KIND = {
    "cluster": ("keep_a", "keep_b", "rewrite", "dismiss"),
    "contradiction": ("keep_a", "keep_b", "rewrite", "dismiss"),
    "audience": ("convert_workflow", "archive_implemented",
                 "keep_interaction", "dismiss"),
}


def review_list(limit: int = 10) -> dict[str, Any]:
    """Open memory reviews, newest first, bounded."""
    try:
        run_migrations()
        reviews = list_open_reviews()
    except Exception as exc:  # noqa: BLE001 — a tool returns, never raises
        return {"ok": False, "error": f"could not read the review queue: {exc}"}
    limit = max(1, min(int(limit), 50))
    out = []
    for r in reviews[:limit]:
        out.append({
            "id": r["id"],
            "kind": r["kind"],
            "keys": r["keys"],
            "detail": r["detail"],
            "actions": list(ACTIONS_BY_KIND.get(r["kind"], ("dismiss",))),
        })
    return {"ok": True, "total_open": len(reviews), "reviews": out}


def review_resolve(
    review_id: int, action: str, rewrite_content: str | None = None,
) -> dict[str, Any]:
    """Resolve one review by id with the given action."""
    action = (action or "").strip()
    try:
        run_migrations()
        conn = get_conn()
        try:
            result = resolve_review(conn, int(review_id), action,
                                    rewrite_content)
            conn.commit()
        finally:
            conn.close()
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — a tool returns, never raises
        return {"ok": False, "error": f"could not resolve review: {exc}"}
    return {"ok": True, "review_id": int(review_id), **result}
