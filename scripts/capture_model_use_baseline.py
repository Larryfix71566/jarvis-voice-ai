#!/usr/bin/env python3
"""Capture content-free WS-05 baseline facts without opening a source DB for writing.

The live costs ledger is copied with its WAL to a temporary directory. Queries
run only against that copy after an unchanged source-stat window. No application
writer, migration, vault, provider client, conversation table or prompt log is
loaded. Deployment/configuration facts remain distinct from effective routing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import subprocess
import tempfile

VERSION = "model-use-baseline-v1"
ROUTES = {"direct_api", "subscription", "codex_subscription", "saygm", "local"}
BILLING = {"provider_api", "subscription", "saygm_credit", "local", "none"}
RUNGS = {"supervisor", "scheduler", "librarian", "analyst", "systems", "developer",
         "app_builder", "memory_merge", "memory_classify", "memory_extraction",
         "memory_settle", "kb_digest", "procedures_describe", "planning", "council",
         "selfedit_executor", "appbuild_executor", "skill_eval", "research", "tts", "stt"}


class BaselineUnavailable(RuntimeError):
    pass


def utc(value: str | None = None) -> str:
    date = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(timezone.utc)
    if date.tzinfo is None:
        raise BaselineUnavailable("timestamp_timezone_required")
    return date.astimezone(timezone.utc).isoformat()


def _signature(source: Path) -> dict[str, tuple[int, int, int]]:
    result = {}
    for suffix in ("", "-wal"):
        path = Path(str(source) + suffix)
        if path.is_symlink():
            raise BaselineUnavailable("ledger_symlink_refused")
        if path.exists():
            stat = path.stat()
            result[suffix] = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
    return result


def _tag(value, allowed: set[str]) -> str:
    return value if value in allowed else "unknown" if value is None else "unrecognized"


def summarize_ledger(conn: sqlite3.Connection, *, since: str | None = None) -> dict:
    """Select allowlisted metadata only; NULL/missing measurements stay unknown."""
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_calls)")}
    if not {"ts", "rung"}.issubset(columns):
        raise BaselineUnavailable("ledger_schema_unavailable")
    where, args = (" WHERE ts >= ?", (utc(since),)) if since else ("", ())
    n, first, last = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM llm_calls" + where, args).fetchone()
    coverage = {}
    for name in ("route_name", "billing_source", "duration_ms", "usage_known", "cache_breakdown_known"):
        if name not in columns:
            coverage[name] = {"column_present": False, "known_rows": None}
            continue
        condition = f"{name} IS NOT NULL"
        if name in {"route_name", "billing_source"}:
            condition += f" AND {name} != ''"
        if name in {"usage_known", "cache_breakdown_known"}:
            condition = f"{name} = 1"
        known = conn.execute("SELECT COUNT(*) FROM llm_calls" + where +
                             (" AND " if where else " WHERE ") + condition, args).fetchone()[0]
        coverage[name] = {"column_present": True, "known_rows": known}
    rungs = {}
    for rung, count in conn.execute("SELECT rung, COUNT(*) FROM llm_calls" + where + " GROUP BY rung", args):
        name = _tag(rung, RUNGS)
        rungs[name] = rungs.get(name, 0) + count
    groups = []
    if {"route_name", "billing_source", "duration_ms"}.issubset(columns):
        for route, billing, count, durations, avg, low, high in conn.execute(
                "SELECT route_name, billing_source, COUNT(*), COUNT(duration_ms), "
                "AVG(duration_ms), MIN(duration_ms), MAX(duration_ms) FROM llm_calls" +
                where + " GROUP BY route_name, billing_source", args):
            groups.append({"route": _tag(route, ROUTES), "billing_source": _tag(billing, BILLING),
                           "calls": count, "duration_rows": durations,
                           "mean_duration_ms": avg, "min_duration_ms": low, "max_duration_ms": high})
    totals = {}
    for name in ("input_tokens", "output_tokens"):
        totals[name] = conn.execute(f"SELECT SUM({name}) FROM llm_calls" + where, args).fetchone()[0] if name in columns else None
    if {"reported_cost", "computed_cost"}.issubset(columns):
        cost, priced = conn.execute("SELECT SUM(COALESCE(reported_cost, computed_cost)), "
                                    "COUNT(COALESCE(reported_cost, computed_cost)) FROM llm_calls" + where, args).fetchone()
        totals.update(estimated_cost_usd=cost, priced_rows=priced)
    else:
        totals.update(estimated_cost_usd=None, priced_rows=None)
    conn.rollback()
    return {"window_start_utc": utc(since) if since else None, "calls": n,
            "llm_calls": n - rungs.get("stt", 0) - rungs.get("tts", 0),
            "first_row_utc": first, "last_row_utc": last, "rungs": rungs,
            "metadata_coverage": coverage, "route_billing_duration_groups": groups,
            "totals": totals, "quality_scores_available": False,
            "cost_is_provider_bill_verification": False}


def capture_ledger(source: Path, *, since: str | None = None, attempts: int = 4) -> dict:
    if not source.is_file():
        raise BaselineUnavailable("ledger_missing")
    if not 1 <= attempts <= 4:
        raise BaselineUnavailable("invalid_snapshot_attempts")
    with tempfile.TemporaryDirectory(prefix="ws05-ledger-") as scratch:
        target = Path(scratch) / "costs.db"
        for attempt in range(attempts):
            before = _signature(source)
            try:
                for suffix in ("", "-wal"):
                    path, dest = Path(str(source) + suffix), Path(str(target) + suffix)
                    if path.exists():
                        shutil.copyfile(path, dest)
                    elif dest.exists():
                        dest.unlink()
            except FileNotFoundError:
                continue  # checkpoint/replacement during the copy; never query it
            after = _signature(source)
            if before != after:
                continue
            with sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True) as conn:
                report = summarize_ledger(conn, since=since)
            report["snapshot"] = {"method": "temporary_db_plus_wal_copy",
                                  "source_stat_window_unchanged": True,
                                  "source_wal_present": "-wal" in after,
                                  "attempts": attempt + 1,
                                  "transactional_source_snapshot_claimed": False}
            return report
    raise BaselineUnavailable("source_changed_during_snapshot")


def _revision(root: Path) -> str | None:
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=10)
    candidate = result.stdout.strip()
    return candidate if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", candidate) else None


def capture_baseline(root: Path, *, deployment_receipt: Path | None = None,
                     bundle_plist: Path | None = None) -> dict:
    if not root.is_dir():
        raise BaselineUnavailable("source_checkout_missing")
    deployment = json.loads(deployment_receipt.read_bytes()) if deployment_receipt else {}
    since = deployment.get("deployed_at")
    revision = _revision(root)
    bundle_revision = None
    if bundle_plist:
        bundle = plistlib.loads(bundle_plist.read_bytes())
        value = bundle.get("MortimerSourceRevision") or bundle.get("JarvisSourceRevision")
        bundle_revision = value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{7,40}", value) else None
    ledger = capture_ledger(root / "data" / "costs.db", since=since)
    return {"version": VERSION, "workstream": "WS-05", "milestone": "MAR-A",
            "captured_at_utc": utc(), "source_revision": revision,
            "deployment": {"status": "deployed" if deployment.get("status") == "deployed" else "unknown",
                           "deployed_at_utc": utc(since) if since else None,
                           "receipt_revision_matches_checkout": deployment.get("production_head") == revision if deployment else None},
            "bundle_revision": bundle_revision,
            "bundle_matches_checkout": revision.startswith(bundle_revision) if revision and bundle_revision else None,
            "ledger": ledger, "effective_process_routing_independently_verified": False,
            "handling": {"production_writes": False, "provider_calls": 0,
                         "prompt_or_response_content_read": False, "credential_values_loaded": False},
            "mar_a_complete": False,
            "open_gates": ["effective_process_routing", "representative_workload_quality_latency",
                           "production_route_billing_duration_attribution", "sufficient_workload_samples"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="read-only installed checkout")
    parser.add_argument("--deployment-receipt", type=Path)
    parser.add_argument("--bundle-plist", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.output and args.output.resolve().is_relative_to(args.root.resolve()):
        parser.error("output must be outside the read-only source checkout")
    try:
        report = capture_baseline(args.root, deployment_receipt=args.deployment_receipt,
                                  bundle_plist=args.bundle_plist)
    except Exception as exc:
        # Even malformed metadata/filesystem exceptions can contain private paths.
        report = {"version": VERSION, "ok": False, "error_category": type(exc).__name__}
        print(json.dumps(report, sort_keys=True))
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
