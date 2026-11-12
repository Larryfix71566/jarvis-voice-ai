"""Admin sidecar routes: model routes and self-service status (/api/model-routes*, /api/status/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    ModelRouteConfirmIn,
    ModelRouteStageIn,
    SubscriptionProbeBody,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.get("/api/model-routes")
def model_routes() -> dict:
    """Return route/workload policy metadata without credential material."""
    try:
        access = srv.load_access_config()
        registry = srv.load_model_registry()
        workloads = access.get("workloads") or {}
        configured_routes = access.get("routes") or {}
        profile_pool = dict(registry.get("profiles") or {})
        restricted_profiles = {}
        # Preserve Haiku's voice-only exception without adding an economy
        # profile to the general registry or hiding its current selection.
        if "voice_supervisor" in workloads:
            voice_name = workloads["voice_supervisor"].get("profile")
            if voice_name and voice_name not in profile_pool:
                profile_pool[voice_name] = srv.model_profile_for_workload("voice_supervisor")
                restricted_profiles[voice_name] = ["voice_supervisor"]
        profiles = []
        choices = {name: {} for name in workloads}
        for name, profile in sorted(profile_pool.items()):
            routes = srv.available_routes(profile, route_catalog=configured_routes)
            supported_workloads = restricted_profiles.get(name, sorted(workloads))
            profiles.append({
                "name": name,
                "identity": profile.get("identity", ""),
                "provider": profile.get("provider", ""),
                "model": profile.get("model", ""),
                "tier": profile.get("tier"),
                "routes": routes,
                "supported_workloads": supported_workloads,
                "api_key_env": profile.get("api_key_env"),
                "key_present": bool(profile.get("api_key_env")
                                     and srv.os.environ.get(profile["api_key_env"])),
            })
            for workload in supported_workloads:
                choices[workload][name] = {
                    route: srv.describe_route_choice(
                        workload, name, route, access_config=access,
                        registry=registry,
                    )
                    for route in routes
                }
        route_catalog = {}
        for name, route in configured_routes.items():
            route_catalog[name] = {
                "adapter": route.get("adapter", name),
                "billing": route.get("billing", name),
                "privacy": route.get("privacy", "approved_external"),
                "capabilities": list(route.get("capabilities") or []),
                "credential_env": route.get("credential_env"),
                "key_present": bool(route.get("credential_env")
                                     and srv.os.environ.get(route["credential_env"])),
            }
        # Direct API is synthesized per profile by the resolver, not a global
        # YAML route. Its credentials/capabilities are in choices above.
        route_catalog.setdefault("direct_api", {
            "adapter": "profile_api", "billing": "provider_api",
            "privacy": "approved_external", "capabilities": [],
            "per_profile": True,
        })
        return {"ok": True, "routes": route_catalog,
                "workloads": workloads, "choices": choices,
                "profiles": profiles, "preferences": srv.list_preferences(),
                "routing_enabled": srv.os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1",
                "routing_process": "admin",
                "harness_brief": srv.status_harness_models(),
                "harness_switching_supported": False}
    except Exception as exc:  # noqa: BLE001 - read-only status boundary
        srv.logger.warning("model_routes_status_failed error_type=%s",
                       type(exc).__name__)
        return {"ok": False, "error": "model route status unavailable"}


@app.post("/api/model-routes/stage")
def model_routes_stage(body: ModelRouteStageIn) -> dict:
    """Draft a route choice; confirmation is a separate request by design."""
    try:
        return {"ok": True, **srv.stage_preference(
            body.workload, body.profile, body.route, body.privacy)}
    except srv.ModelPreferenceError as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/model-routes/confirm")
def model_routes_confirm(body: ModelRouteConfirmIn) -> dict:
    try:
        return {"ok": True, **srv.confirm_preference(body.draft_id)}
    except srv.ModelPreferenceError as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/status/harness-models/refresh")
def refresh_harness_models() -> dict:
    """Explicit public-doc refresh. No account API, inference, secrets or model writes."""
    from jarvis.status.harness import refresh_report
    from jarvis.status.daily import STATUS_DIR
    return srv._status_call("harness-models-refresh", lambda: refresh_report(STATUS_DIR))


@app.get("/api/status/harness-models")
def status_harness_models() -> dict:
    """Read cached daily evidence only; never refresh, probe or change a model."""
    from jarvis.status.harness import read_report
    from jarvis.status.daily import STATUS_DIR
    return srv._status_call("harness-models", lambda: read_report(STATUS_DIR))


@app.get("/api/status/models")
def status_models() -> dict:
    from jarvis.status import models as _m

    return srv._status_call("models", lambda: _m.model_access_status())


@app.get("/api/status/services")
def status_services() -> dict:
    from jarvis.status import services as _s

    return srv._status_call("services", lambda: _s.service_health())


@app.get("/api/status/overview")
def status_overview() -> dict:
    from jarvis.status import overview as _o

    return srv._status_call("overview", lambda: _o.system_overview())


@app.get("/api/status/build")
def status_build() -> dict:
    from jarvis.status import build as _b

    return srv._status_call("build", lambda: _b.app_build_status(srv.REPO_ROOT))


@app.get("/api/status/location")
def status_location() -> dict:
    from jarvis.status import location as _l

    return srv._status_call("location", lambda: _l.current_location())


@app.get("/api/status/logs")
def status_logs(source: str = "", query: str = "", since_minutes: int = 60,
                limit: int = 50) -> dict:
    from jarvis.status import logs as _g

    return srv._status_call("logs", lambda: _g.log_search(
        source, query, since_minutes=since_minutes, limit=limit))


@app.get("/api/status/catalog")
def status_catalog(provider: str = "all", force: bool = False) -> dict:
    """What each configured provider offers right now (status spec T4.1):
    live `/models` reads with the vault's keys, cached an hour unless
    `force`. Leaves the machine, so the voice tool refuses it on a
    protected turn (I3)."""
    from jarvis.status import catalog as _c

    return srv._status_call("catalog", lambda: _c.catalog_status(provider, force=force))


@app.post("/api/status/subscription/probe")
def status_subscription_probe(body: SubscriptionProbeBody) -> dict:
    """Try one exact model on the Claude or Codex subscription CLI (status
    spec T4.2). The one status route that spends anything — a little
    subscription quota — so it is rate-limited per (which, model) for 10
    minutes unless `force` (I2)."""
    from jarvis.status import subscriptions as _su

    return srv._status_call("subscription", lambda: _su.subscription_status(
        body.which, body.model, force=body.force))


@app.get("/api/status/github")
def status_github(kind: str = "prs", state: str = "open", limit: int = 10,
                  number: int | None = None) -> dict:
    """Pull requests and their checks on Mortimer's own repository (status
    spec T4.3). GET-only reads through mcp_apps' GitHubClient; the token
    stays in this process."""
    from jarvis.status import github as _gh

    return srv._status_call("github", lambda: _gh.github_status(
        kind, state=state, limit=limit, number=number))
