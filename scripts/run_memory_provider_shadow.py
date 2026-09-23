#!/usr/bin/env python3
"""Run the opt-in B6 provider shadow corpus without touching the live DB.

The API key is loaded through the project credential path (Mac vault first,
then the process environment or local `.env`) and is never written to the
receipt. The command sends only the checked-in synthetic fixture, compares the
provider result with the deterministic baseline, and writes a bounded JSON
receipt for review. It does not enable production memory automation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "memory_automation_cases.json"
sys.path.insert(0, str(ROOT))

from jarvis.agents.upgrade_agent import load_model_registry  # noqa: E402
from jarvis.llm_client import make_sync_client  # noqa: E402
from jarvis.memory_automation import heuristic_classifier  # noqa: E402
from jarvis.memory_automation_eval import ProviderClassifier, measure_shadow  # noqa: E402
from jarvis.vault import VaultError, inject_env  # noqa: E402


def _safe_base_url(value: str | None) -> str | None:
    """Keep provider identity while removing URL credentials and queries."""
    if not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.hostname:
        return "<configured>"
    host = parts.hostname
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _load_dotenv_fallback() -> None:
    """Load local non-shell configuration after vault injection.

    The application treats a missing vault as a supported pre-migration
    fallback to ``.env``. Preserve that behavior for this standalone runner,
    while keeping a non-empty shell or vault value authoritative.
    """
    for name, value in dotenv_values(ROOT / ".env").items():
        if value is not None and os.environ.get(name, "") == "":
            os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True,
                        help="explicit memory-evaluation profile from the model registry")
    parser.add_argument("--registry", type=Path, default=ROOT / "config/upgrade_models.yaml")
    parser.add_argument("--vault-path", type=Path,
                        help="existing credential vault; never copied or modified")
    parser.add_argument("--dry-run", action="store_true",
                        help="show selected route without loading secrets or calling a provider")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "acceptance" / "memory-automation" / "provider-shadow-receipt.json")
    args = parser.parse_args()

    registry = load_model_registry(args.registry)
    route = registry["profiles"].get(args.profile)
    if not route:
        parser.error(f"unknown profile {args.profile!r}; choose an explicit registered profile")
    for field in ("model", "base_url", "api_key_env", "provider"):
        if not route.get(field):
            parser.error(f"profile is missing {field}")
    model, base_url = route["model"], route["base_url"]
    route_receipt = {
        "profile": args.profile, "model": model,
        "provider": route["provider"], "base_url": _safe_base_url(base_url),
        "api_key_env": route["api_key_env"],
    }
    if args.dry_run:
        print(json.dumps({**route_receipt, "provider_called": False}, sort_keys=True))
        return 0
    if args.vault_path:
        if not args.vault_path.is_file():
            parser.error("specified vault file does not exist")
        os.environ["JARVIS_VAULT_PATH"] = str(args.vault_path.resolve())
    try:
        inject_env()
    except VaultError as exc:
        parser.error(f"credential vault unavailable: {exc}")
    _load_dotenv_fallback()
    api_key = os.environ.get(route["api_key_env"], "")
    if not api_key:
        parser.error(f"profile credential {route['api_key_env']} is unavailable; check --vault-path")

    cases = json.loads(FIXTURE.read_text())
    client = make_sync_client(api_key=api_key, base_url=base_url, model=model,
                              provider=route["provider"], timeout=60, max_retries=0)
    provider = ProviderClassifier(client, model=model, temperature=route.get("temperature"))
    measurement = measure_shadow(
        cases["cases"], baseline_classifier=heuristic_classifier,
        candidate_classifier=provider,
    )
    receipt = {
        "version": "memory-automation-provider-shadow-v1",
        "fixture_version": cases["version"],
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **route_receipt,
        "measurement": measurement.to_dict(),
        "provider_usage": provider.usage(),
        "live_database_touched": False,
        "production_automation_enabled": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "passed": measurement.candidate.passed,
        "no_regression": measurement.no_regression,
        "provider_usage": provider.usage(),
    }, sort_keys=True))
    return 0 if measurement.candidate.passed and measurement.no_regression else 1


if __name__ == "__main__":
    raise SystemExit(main())
