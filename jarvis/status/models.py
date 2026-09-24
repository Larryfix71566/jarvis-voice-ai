"""`model_access_status()` — configured models with key health (spec T2.2).

Source is always the registry: this says what is CONFIGURED, never what an
account offers (I5). Key health is the cached verdict of the process this
runs in (the admin sidecar probes at start, see jarvis/admin/server.py).
No network, no key values (R7).
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping

from jarvis import keyhealth
from jarvis.status.providers import coverage_gaps, discover_providers

SUBSCRIPTION_HEALTH = "n/a (subscription)"


def model_access_status(*, registry: dict | None = None, access: dict | None = None,
                        env: Mapping[str, str] = os.environ) -> dict[str, Any]:
    from jarvis.model_routing import ModelRouteError, available_routes, load_access_config

    if registry is None:
        from jarvis.agents.upgrade_agent import load_model_registry

        registry = load_model_registry()
    if access is None:
        try:
            access = load_access_config()
        except ModelRouteError:
            access = {}

    profiles_raw = registry.get("profiles") or {}
    profiles: list[dict[str, Any]] = []
    for name, p in sorted(profiles_raw.items()):
        if not isinstance(p, dict):
            continue
        key_env = p.get("api_key_env")
        profiles.append({
            "name": name,
            "provider": p.get("provider"),
            "model": p.get("model"),
            "identity": p.get("identity"),
            "tier": p.get("tier"),
            "routes": available_routes(p),
            "key_env": key_env,
            "key_present": bool(key_env and str(env.get(key_env) or "").strip()),
            "key_health": keyhealth.verdict(key_env) if key_env else SUBSCRIPTION_HEALTH,
            "key_health_detail": keyhealth.detail(key_env) if key_env else "",
        })

    workloads = {
        str(name): {"profile": w.get("profile"), "route": w.get("route", "direct_api")}
        for name, w in sorted(((access or {}).get("workloads") or {}).items())
        if isinstance(w, dict)
    }
    refs = discover_providers(registry=registry, access=access, env=env)
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "registry",
        "default": registry.get("default"),
        "profiles": profiles,
        "workloads": workloads,
        "providers": [asdict(ref) for ref in refs],
        "coverage_gaps": coverage_gaps(refs),
    }
