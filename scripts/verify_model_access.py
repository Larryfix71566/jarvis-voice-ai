#!/usr/bin/env python3
"""Print a secret-free model-route readiness report.

By default this is a local dry run: it reads policy/registry metadata and
checks command presence and environment-variable presence without making model
calls. ``--saygm`` performs only the authenticated SAYGM ``/models`` catalog
request. ``--require-ready`` turns unavailable routes into a non-zero exit.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Make the documented ``python scripts/verify_model_access.py`` invocation
# work from a checkout without requiring callers to set PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis.model_routing import load_access_config, model_profile_for_workload, resolve_policy
from jarvis.saygm import SayGMError, fetch_catalog
from jarvis.status.subscriptions import probe_subscription
from jarvis.subscription import SubscriptionRuntimeError, _run_claude, _run_codex  # noqa: F401 - SubscriptionRuntimeError re-exported for callers/tests
from jarvis.vault import VaultError, inject_env


def _command(name: str) -> dict[str, Any]:
    override = os.environ.get(name)
    defaults = {
        "JARVIS_CLAUDE_SUBSCRIPTION_COMMAND": "claude",
        "JARVIS_CODEX_SUBSCRIPTION_COMMAND": "codex",
    }
    command = override or defaults.get(name, name)
    path = shutil.which(command)
    return {"command": command, "installed": path is not None}


def _script_probe(name: str, runner) -> dict[str, Any]:
    """This report's view of the one subscription probe
    (jarvis.status.subscriptions.probe_subscription, status spec T4.2): the
    same {"ok", "response_present"} / {"ok": False, "category"} JSON as
    before, the script's own 45 s timeout, and no not-installed
    short-circuit — a missing CLI surfaces through the runner's failure,
    exactly as it did before the probe moved."""
    result = probe_subscription(name, force=True, timeout=45.0, runner=runner,
                                check_installed=False)
    if result["category"] is None:
        return {"ok": result["ok"], "response_present": result["response_present"]}
    return {"ok": False, "category": result["category"]}


def build_report(*, check_saygm: bool = False,
                 probe_subscriptions: bool = False) -> dict[str, Any]:
    access = load_access_config()
    routes = access.get("routes") or {}
    report: dict[str, Any] = {
        "policy": str(Path(os.environ.get("JARVIS_MODEL_ACCESS_CONFIG", "config/model_access.yaml"))),
        "routing_enabled": os.environ.get("JARVIS_MODEL_ROUTING_ENABLED", "0") == "1",
        "routes": {},
        "workloads": {},
        "saygm_catalog": None,
        "subscription_probes": None,
    }
    for name, route in routes.items():
        credential = route.get("credential_env")
        row: dict[str, Any] = {
            "adapter": route.get("adapter", name),
            "billing": route.get("billing", name),
            "privacy": route.get("privacy"),
            "capabilities": sorted(str(item) for item in (route.get("capabilities") or [])),
            "credential_env": credential,
            "credential_present": bool(credential and os.environ.get(credential)),
        }
        if name == "subscription":
            row.update(_command("JARVIS_CLAUDE_SUBSCRIPTION_COMMAND"))
            row["api_credentials_stripped_before_launch"] = True
        elif name == "codex_subscription":
            row.update(_command("JARVIS_CODEX_SUBSCRIPTION_COMMAND"))
            row["api_credentials_stripped_before_launch"] = True
        report["routes"][name] = row
    for workload in (access.get("workloads") or {}):
        try:
            policy = resolve_policy(workload, include_preferences=False)
            profile = model_profile_for_workload(workload)
            credential_env = profile.get("api_key_env")
            report["workloads"][workload] = {
                "profile": policy.profile,
                "route": policy.route,
                "privacy": policy.privacy,
                "priority": policy.priority,
                "capabilities": list(policy.required_capabilities),
                "credential_env": credential_env,
                "credential_present": bool(credential_env and os.environ.get(credential_env)),
            }
        except Exception as exc:  # noqa: BLE001 - report every broken policy row
            report["workloads"][workload] = {"error": str(exc)}
    if check_saygm:
        try:
            catalog = fetch_catalog()
            report["saygm_catalog"] = {
                "ok": True,
                "models": len(catalog),
                "confidential_models": [item.model for item in catalog if item.confidential],
            }
        except SayGMError as exc:
            report["saygm_catalog"] = {"ok": False, "error": str(exc)}
    if probe_subscriptions:
        report["subscription_probes"] = {
            "claude": _script_probe("claude", _run_claude),
            "codex": _script_probe("codex", _run_codex),
        }
    return report


def _not_ready(report: dict[str, Any]) -> list[str]:
    missing: list[str] = []

    def add(message: str) -> None:
        if message not in missing:
            missing.append(message)

    used_routes = {
        item.get("route") for item in report.get("workloads", {}).values()
        if isinstance(item, dict) and item.get("route")
    }
    for name, route in report["routes"].items():
        if name not in used_routes and not (name == "saygm" and report.get("saygm_catalog") is not None):
            continue
        if route.get("credential_env") and not route.get("credential_present"):
            add(f"{name}: {route['credential_env']} is not set")
        if name in {"subscription", "codex_subscription"} and not route.get("installed"):
            add(f"{name}: CLI command is not installed")
    for workload, policy in report.get("workloads", {}).items():
        if (isinstance(policy, dict) and policy.get("credential_env")
                and not policy.get("credential_present")):
            add(f"{workload}: {policy['credential_env']} is not set")
    catalog = report.get("saygm_catalog")
    if isinstance(catalog, dict) and not catalog.get("ok"):
        add(f"saygm: {catalog.get('error', 'catalog unavailable')}")
    probes = report.get("subscription_probes")
    if isinstance(probes, dict):
        for name, result in probes.items():
            if not isinstance(result, dict) or result.get("ok"):
                continue
            category = result.get("category", "probe failed")
            add(f"{name} subscription: {category}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--saygm", action="store_true", help="perform the authenticated SAYGM catalog check")
    parser.add_argument("--probe-subscriptions", action="store_true",
                        help="send one fixed synthetic prompt through each subscription adapter")
    parser.add_argument("--require-ready", action="store_true", help="exit 1 when configured route prerequisites are unavailable")
    parser.add_argument("--output", type=Path, help="write the sanitized JSON report")
    args = parser.parse_args()
    # The readiness command is also the documented operator check.  Load the
    # configured project vault before inspecting credential presence so a
    # candidate checkout can validate against the established vault without
    # copying secrets into the checkout.  The report itself remains secret-free.
    try:
        inject_env()
    except VaultError as exc:
        parser.error(f"credential vault unavailable: {exc}")
    report = build_report(check_saygm=args.saygm,
                          probe_subscriptions=args.probe_subscriptions)
    report["ready_issues"] = _not_ready(report)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.require_ready and report["ready_issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
