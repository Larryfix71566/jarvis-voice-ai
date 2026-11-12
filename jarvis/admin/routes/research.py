"""Admin sidecar routes: site research job (/api/research/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    ResearchSaveIn,
    ResearchStartIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


# ------------------------------------------------------------- research
# MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1/R6/R10. Same background-
# thread-plus-polling shape as self-edit/plan/council/app-build above.


@app.post("/api/research/start")
def research_start(body: ResearchStartIn) -> dict:
    advisory_started_at = srv.time.time()
    if not srv._research_enabled():
        return {"ok": False, "error": srv.RESEARCH_DISABLED_MESSAGE}
    run_id = (body.run_id or "").strip()
    if not run_id:
        return {"ok": False, "error": "a stable run_id is required for a research start"}
    if len(run_id) > 256:
        return {"ok": False, "error": "run identity is invalid; no research job was started"}
    urls = [u.strip() for u in (body.urls or []) if u.strip()]
    cfg = srv.research_crawl.load_research_config()
    max_sites = int(cfg.get("max_sites", 2))
    if len(urls) < 2:
        return {"ok": False, "error": "two URLs are required to compare"}
    if len(urls) > max_sites:
        return {"ok": False, "error": f"at most {max_sites} sites can be compared at once"}
    if not srv.os.environ.get(srv.research_crawl.TAVILY_API_KEY_ENV):
        return {"ok": False, "error": "TAVILY_API_KEY is not configured"}
    with srv._research_lock:
        try:
            prior = srv.get_execution_action(srv._RESEARCH_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            srv.logger.warning("research_start_claim_read_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not verify whether this research already started; no retry was launched",
                "outcome": "unknown", "action_run_id": run_id,
            }
        if prior is not None:
            return srv._research_duplicate(run_id, prior, srv._research_job)
        if srv._research_job["state"] == "running":
            return {
                "ok": False,
                "error": "a comparison is already in progress — ask for status instead",
                "job": dict(srv._research_job),
            }
        try:
            claimed = srv.claim_execution_action(srv._RESEARCH_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            srv.logger.warning("research_start_claim_write_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not safely record research start; no crawl was launched",
                "outcome": "unknown", "action_run_id": run_id,
            }
        if not claimed:
            try:
                prior = srv.get_execution_action(srv._RESEARCH_START_ACTION_SCOPE, run_id)
            except Exception:
                prior = None
            return srv._research_duplicate(
                run_id, prior or {"status": "unknown"}, srv._research_job,
            )
        srv._research_job.update(
            state="running", urls=urls, focus=(body.focus or "").strip() or None,
            sites=None, comparison=None, model=None, credits_used=None, error=None,
            started_at=srv.time.time(), finished_at=None, saved_path=None, save_error=None,
            run_id=run_id,
        )
        srv._activate_advisory(srv._research_job)
    srv._update_research_start_claim(run_id, "running")
    srv.logger.info("research_state_transition state=running site_count=%d", len(urls))
    try:
        srv._start_advisory_thread(
            srv._run_research_job, args=(urls, body.focus or "", run_id),
            started_at=advisory_started_at,
        )
    except Exception as exc:
        srv.logger.warning("research_job_dispatch_failed error_type=%s", type(exc).__name__)
        with srv._research_lock:
            srv._research_job.update(state="error", error="research job could not be started",
                                 finished_at=srv.time.time())
        srv._update_research_start_claim(run_id, "failed")
        return {"ok": False, "error": "research job could not be started",
                "action_run_id": run_id}
    return {"ok": True, "started": True, "action_run_id": run_id}


@app.get("/api/research/job")
def research_job_status(run_id: str | None = None) -> dict:
    requested_run_id = (run_id or "").strip()
    with srv._research_lock:
        srv._advisory_context_for_job('research', srv._research_job)
        job = dict(srv._research_job)
    if requested_run_id and job.get("run_id") != requested_run_id:
        try:
            prior = srv.get_execution_action(srv._RESEARCH_START_ACTION_SCOPE, requested_run_id)
        except Exception as exc:
            srv.logger.warning("research_status_claim_read_failed error_type=%s", type(exc).__name__)
            return {"ok": False, "error": "research status is temporarily unavailable"}
        if prior is None:
            return {"ok": False, "error": "no research action found for that execution ID"}
        state = prior.get("status", "unknown")
        if state in {"claimed", "running", "awaiting_choice"}:
            state = "unknown"
        state = {"completed": "done", "failed": "error"}.get(state, state)
        job = {"state": state, "run_id": requested_run_id,
               "finished_at": None, "error": None}
    return {"ok": True, "job": job}


@app.post("/api/research/save")
def research_save(body: ResearchSaveIn) -> dict:
    """Save through the guarded sandbox editor. Attribution names model, URLs, page
    counts, and credits — a comparison without its sources and cost is a
    claim with no provenance (R6/R8)."""
    with srv._research_lock:
        source = srv._advisory_context_for_job('research', srv._research_job)
        if srv._research_job["state"] != "done":
            return {"ok": False, "error": "no finished comparison to save"}
        job = dict(srv._research_job)
    comparison = job.get("comparison") or ""
    if not comparison:
        return {"ok": False, "error": "the comparison is empty"}

    urls = job.get("urls") or []
    slug = srv.re.sub(r"[^a-z0-9]+", "-", "-vs-".join(urls).lower()).strip("-")[:60] or "comparison"
    path = (body.path or "").strip() or f"docs/research/{slug}.md"

    registry = srv.load_model_registry()
    profiles = registry.get("profiles", {})
    model_name = job.get("model") or "unknown"
    provider_model = (profiles.get(model_name) or {}).get("model", model_name)
    sites = job.get("sites") or []
    pages_note = ", ".join(
        f"{s.get('url')}: {s.get('page_count')} pages" if s.get("ok")
        else f"{s.get('url')}: failed ({s.get('error_kind', 'unknown')})"
        for s in sites
    )
    footer = (
        f"\n\n---\n*Comparison by {model_name} ({provider_model}) — {srv.now_iso()[:10]}. "
        f"Sites: {', '.join(urls)}. Pages: {pages_note}. "
        f"Credits used: {job.get('credits_used', 0)}.*"
    )
    token = srv._advisory_transport_context.set(source)
    try:
        result = srv._save_document_to_sandbox(
            path, comparison + footer,
            rationale=f"Site comparison: {', '.join(urls)}",
        )
    finally:
        srv._advisory_transport_context.reset(token)
    if result.get("ok"):
        with srv._research_lock:
            srv._advisory_context_for_job('research', srv._research_job)
            srv._research_job.update(saved_path=result.get("path"), save_error=None)
            if source is not None:
                from jarvis.advisory_sources import record_advisory_job
                record_advisory_job(source, srv._research_job)
    else:
        with srv._research_lock:
            srv._advisory_context_for_job('research', srv._research_job)
            srv._research_job.update(save_error=result.get("error"))
            if source is not None:
                from jarvis.advisory_sources import record_advisory_job
                record_advisory_job(source, srv._research_job)
    return dict(result)


@app.post("/api/research/cancel")
def research_cancel() -> dict:
    if srv._research_busy() and srv._advisory_transport_context.get() is None:
        return {"ok": False, "error": "a comparison is in progress — ask for status instead"}
    with srv._research_lock:
        source = srv._advisory_transport_context.get()
        guard = srv._advisory_job_guards.get('research')
        if source is not None and (srv._research_job.get('run_id') != source.as_metadata()['action_run_id']
                or (guard is not None and guard['source'] is not None and guard['source']._action is not source._action)):
            return {'ok': True, 'already_idle': True}
        srv._advisory_context_for_job('research', srv._research_job)
        guard = srv._advisory_job_guards.pop('research', None)
        if guard is not None:
            guard['event'].set()
        if srv._research_job["state"] == "idle":
            return {"ok": True, "already_idle": True}
        srv._research_job.update(
            state="idle", urls=None, focus=None, sites=None, comparison=None,
            model=None, credits_used=None, error=None, started_at=None,
            finished_at=None, saved_path=None, save_error=None,
            run_id=guard['run_id'] if guard is not None and guard['source'] is not None else None,
        )
        if guard is not None and guard['source'] is not None:
            from jarvis.advisory_sources import record_advisory_job
            record_advisory_job(guard['source'], srv._research_job, allow_cancelled=True)
    return {"ok": True}
