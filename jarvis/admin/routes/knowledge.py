"""Admin sidecar routes: memory, knowledge, workflows, run log and graphs (/api/memory*, /api/knowledge, /api/workflows, /api/runs*, /api/graph/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    MemoryReviewResolveIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


# --------------------------------------------------------------- memory
# Plan Phase 5e: visibility/correction surface. Thin pass-throughs over
# jarvis.memory — matching the git panel's convention above (logic lives in
# the shared module; the sidecar only adapts it to HTTP). run_migrations()
# is idempotent and mirrors mcp_git.logic._db()'s own pattern of ensuring
# the schema exists before every call, since this endpoint can be hit
# before any voice session has run migrations itself.

# MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A3 — thin wrappers over
# jarvis.memory_sweep, same convention as the memory endpoints above:
# the sidecar owns nothing new, it just exposes the review queue the
# startup sweep (A1/A2/A4/A5) populates.

# ----------------------------------------------------------------- runs
# Run-logging plan §5.11: thin pass-throughs over jarvis.runlog, same
# convention as memory/git above. Query normalization (since -> ISO, the
# D9 orphan-status rule) lives in jarvis.runlog.store and must not be
# reimplemented here — both endpoints call parse_since() before calling
# list_runs()/get_run() so the CLI and the console panel can never
# disagree about what "2d" means.


@app.get("/api/memory")
def memory_overview() -> dict:
    srv.run_migrations()
    return {
        "ok": True,
        "facts": srv.memory_module.list_facts(),
        "summary": srv.memory_module.get_summary_text(),
        "observations": srv.memory_module.list_observation_groups(),
        "usage": srv.memory_module.memory_usage(),
    }


@app.get("/api/knowledge")
def knowledge_overview() -> dict:
    """K5 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — the four layers, with
    counts, in one read-only call. The body lives in
    jarvis/status/overview.py (status spec T2.3) so this endpoint and
    system_overview() share one implementation (R8); response unchanged."""
    from jarvis.status.overview import knowledge_overview as _knowledge

    return _knowledge()


@app.get("/api/workflows")
def workflows_detail() -> dict:
    """MORTIMER_WORKFLOW_VIEWER_PLAN.md piece 1 — every workflow in full for
    the read-only viewer. Body in jarvis/status/overview.py, beside the
    knowledge overview."""
    from jarvis.status.overview import workflows_detail as _workflows
    return _workflows()


@app.delete("/api/memory/fact/{key}")
def memory_delete_fact(key: str) -> dict:
    srv.run_migrations()
    with srv.get_conn() as conn:
        deleted = srv.memory_module.delete_fact(conn, key)
    if not deleted:
        return {"ok": False, "error": f"No fact with key '{key}'."}
    return {"ok": True, "key": key}


@app.get("/api/memory/reviews")
def memory_reviews_list() -> dict:
    srv.run_migrations()
    from jarvis import memory_sweep

    try:
        return {"ok": True, "reviews": memory_sweep.list_open_reviews()}
    except Exception as exc:  # noqa: BLE001 — a panel must never break the sidecar
        srv.logger.warning("memory_reviews_list_failed error_type=%s",
                       type(exc).__name__)
        return {"ok": False, "error": "could not read the review queue"}


@app.post("/api/memory/reviews/{review_id}/resolve")
def memory_reviews_resolve(review_id: int, body: MemoryReviewResolveIn) -> dict:
    srv.run_migrations()
    from jarvis import memory_sweep

    try:
        with srv.get_conn() as conn:
            result = memory_sweep.resolve_review(
                conn, review_id, body.action, body.rewrite_content,
            )
            conn.commit()
        return {"ok": True, **result}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — a panel must never break the sidecar
        srv.logger.warning("memory_reviews_resolve_failed error_type=%s",
                       type(exc).__name__)
        return {"ok": False, "error": "could not resolve that review"}


@app.get("/api/runs")
def runs_list(
    agent: str = "", status: str = "", since: str = "", limit: int = 50,
) -> dict:
    srv.run_migrations()
    clamped_limit = max(1, min(200, limit))
    return {
        "ok": True,
        "runs": srv.list_runs(
            agent=agent or None,
            status=status or None,
            since=srv.parse_since(since or None),
            limit=clamped_limit,
        ),
    }


@app.get("/api/runs/{run_id}")
def runs_detail(run_id: str) -> dict:
    srv.run_migrations()
    detail = srv.get_run(run_id)
    if detail is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, **detail}


# ---- MORTIMER_GRAPH_LAYER_PLAN.md GL11 — read-only graph views. Every edge is
# derived in jarvis/graphs; these endpoints only call build() and render.
@app.get("/api/graph/{name}")
def graph_json(name: str, focus: str = "", depth: int | None = None,
               edge_types: str = "", since: str = "") -> dict:
    srv.run_migrations()
    with srv.closing(srv.get_conn()) as conn:
        return srv.graphs.build(name, conn, focus=focus, depth=depth,
                            edge_types=edge_types, since=since or None)


@app.get("/api/graph/{name}/image.{fmt}")
def graph_image(name: str, fmt: str, focus: str = "", depth: int | None = None,
                edge_types: str = "", since: str = "", w: int = 0, h: int = 0):
    if fmt not in ("png", "svg"):
        return srv.Response(status_code=404)
    width = srv.gcfg.GRAPH_IMAGE_W if w <= 0 else max(srv.gcfg.GRAPH_IMAGE_MIN_PX, min(srv.gcfg.GRAPH_IMAGE_MAX_PX, w))
    height = srv.gcfg.GRAPH_IMAGE_H if h <= 0 else max(srv.gcfg.GRAPH_IMAGE_MIN_PX, min(srv.gcfg.GRAPH_IMAGE_MAX_PX, h))
    srv.run_migrations()
    with srv.closing(srv.get_conn()) as conn:
        result = srv.graphs.build(name, conn, focus=focus, depth=depth, edge_types=edge_types,
                              since=since or None)
    media = "image/png" if fmt == "png" else "image/svg+xml"
    if not result.get("ok"):
        # GL11: never a 4xx for a graph error — an <img>/AsyncImage shows nothing for one.
        body = (srv.render.error_image_png(result["error"], width, height) if fmt == "png"
                else srv.render.error_image_svg(result["error"], width, height))
        return srv.Response(content=body, media_type=media)
    graph = srv.graphs.from_json(result)
    pos = srv.render.layout(graph, result["focus"], width, height)
    body = (srv.render.to_png(graph, pos, width, height, focus=result["focus"]) if fmt == "png"
            else srv.render.to_svg(graph, pos, width, height, focus=result["focus"]))
    return srv.Response(content=body, media_type=media)
