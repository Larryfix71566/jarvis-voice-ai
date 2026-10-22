"""Read-only harness recommendations: public documents + local metadata, no inference.

This module has no subscription CLI, credential, configuration-write, review or
model-execution capability. Public model mentions are never account eligibility.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import sqlite3
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SOURCES = (
    "https://code.claude.com/docs/en/model-config",
    "https://learn.chatgpt.com/docs/models.md",
    "https://learn.chatgpt.com/docs/app-server.md",
)
MAX_BYTES = 512 * 1024
MAX_CANDIDATES = 32
MODEL_ID = re.compile(r"(?<![\w-])(?:claude-(?:opus|sonnet|haiku|fable)-\d+(?:-\d+){1,3}|gpt-\d+(?:\.\d+)?-(?:sol|astra))(?![\w-])")
REPORT_NAME = "harness-model-brief.json"


def fetch_document(url: str) -> str:
    """Fixed official HTTPS pages only; no redirects, cookies, auth or proxy env."""
    if url not in SOURCES:
        raise ValueError("unapproved public documentation source")
    target = urlsplit(url)
    connection = http.client.HTTPSConnection(target.hostname, timeout=5,
                                             context=ssl.create_default_context())
    try:
        connection.request("GET", target.path, headers={
            "User-Agent": "Mortimer-model-brief/1", "Accept": "text/plain,text/html"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("official documentation unavailable")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("official documentation exceeds size limit")
        return body.decode("utf-8", errors="strict")
    finally:
        connection.close()


def configured_selection() -> dict:
    """Routed metadata only. Legacy voice uses Settings, so this is not its baseline."""
    from jarvis.db import _default_db_path
    from jarvis.model_preferences import _proposal, _digest
    from jarvis.model_routing import resolve_policy
    path = _default_db_path().resolve()
    if not path.is_file():
        raise ValueError("saved preference store unavailable")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        p = resolve_policy("voice_supervisor", include_preferences=False)
        proposal = _proposal(db, {"workload": p.workload, "profile": p.profile,
                                  "route": p.route, "privacy": p.privacy})
    selected = proposal["current"]
    return {"model": selected["model"], "profile": selected["profile"],
            "route": selected["route"], "privacy": selected["privacy"],
            "digest": _digest(proposal), "evidence": "routed_selection_only",
            "applies_to_voice_runtime": False}


def _selection(read):
    try:
        value = read()
        if (not isinstance(value, dict) or not isinstance(value.get("model"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", value.get("digest", ""))):
            return None
        return value
    except Exception:
        return None


def _sources(raw: list) -> list[dict]:
    """Revalidate cached data; documents grant no execution or account authority."""
    raw = raw if isinstance(raw, list) else []
    result = []
    for url in SOURCES:
        item = next((x for x in raw if isinstance(x, dict) and x.get("url") == url), {})
        ids = item.get("models")
        ids = sorted({v for v in ids if isinstance(v, str) and MODEL_ID.fullmatch(v)})[:MAX_CANDIDATES] if isinstance(ids, list) else []
        stamp = item.get("retrieved_at")
        digest = item.get("sha256")
        valid = isinstance(stamp, str) and isinstance(digest, str) and bool(re.fullmatch(r"[0-9a-f]{64}", digest))
        result.append({"url": url, "retrieved_at": stamp if valid else None,
                       "sha256": digest if valid else None,
                       "models": ids if valid else [],
                       "status": "documented_mentions" if valid and ids else "unavailable_or_unparsed"})
    return result


def _report(sources, selection, now):
    sources = _sources(sources)
    ids = sorted({m for source in sources for m in source["models"]})[:MAX_CANDIDATES]
    return {"schema_version": 2, "generated_at": now.astimezone(timezone.utc).isoformat(),
            "mode": "read_only", "configured_selection": selection,
            "baseline": None, "active_model": None, "runtime_adoption": "unverified",
            "sources": sources, "candidates": [{"model": m, "status": "documented_candidate",
                "account_eligibility": "unverified", "adapter_readiness": "unverified",
                "comparative_quality": "unmeasured", "expected_latency": "unknown"} for m in ids],
            "recommendation": "retain_pending_evidence", "switching_supported": False,
            "inference_calls": 0, "automatic_change": False,
            "gaps": ["Routed selection is not the voice baseline; legacy voice may use separate Settings.",
                     "Active controller, account eligibility, adapter acceptance and comparable results are unverified.",
                     "Harness switching is blocked pending a durable approval contract across all writers and runtime."],
            "summary": f"Harness model brief: {len(ids)} model IDs appear in cached official documentation. "
                "They are unverified candidates, not proven improvements. The active controller is unknown; "
                "retain pending evidence. Harness switching is unavailable. No model was changed."}


def _raw(status_dir):
    path = status_dir / REPORT_NAME
    try:
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            return None
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) and value.get("schema_version") == 2 else None
    except (OSError, ValueError, RecursionError):
        return None


def collect(*, fetch=fetch_document, selection=configured_selection, now=None) -> dict:
    """Explicit public-document refresh only; never called by the scheduled hook."""
    now = now or datetime.now(timezone.utc)
    sources = []
    for url in SOURCES:
        item = {"url": url}
        try:
            content = fetch(url)
            if not isinstance(content, str) or len(content.encode()) > MAX_BYTES:
                raise ValueError("invalid documentation")
            item.update(retrieved_at=now.astimezone(timezone.utc).isoformat(),
                        sha256=hashlib.sha256(content.encode()).hexdigest(),
                        models=sorted(set(MODEL_ID.findall(content)))[:MAX_CANDIDATES])
        except Exception:
            pass
        sources.append(item)
    return _report(sources, _selection(selection), now)


def read_report(status_dir: Path, *, selection=configured_selection, now=None) -> dict:
    """Recheck current selection and source age; never repeat a stale current claim."""
    raw = _raw(status_dir)
    if raw is None:
        return {"ok": False, "error": "Harness evidence unavailable; no model availability is inferred."}
    now = now or datetime.now(timezone.utc)
    current = _selection(selection)
    report = _report(raw.get("sources") or [], current, now)
    freshness = "recent"
    for source in report["sources"]:
        if source["status"] != "documented_mentions":
            freshness = "incomplete"
        try:
            age = (now - datetime.fromisoformat(source["retrieved_at"])).total_seconds()
            if age < 0 or age > 26 * 3600: freshness = "stale"
        except (TypeError, ValueError):
            freshness = "incomplete"
    cached = raw.get("configured_selection")
    cached = cached if isinstance(cached, dict) else {}
    if current is None:
        freshness = "selection_unavailable"
    elif current["digest"] != cached.get("digest"):
        freshness = "selection_changed"
    report["evidence_generated_at"] = raw.get("generated_at")
    if freshness != "recent":
        report["summary"] = (f"Harness evidence is {freshness.replace('_', ' ')}. "
                             "Documented IDs below are historical evidence, not current availability or an upgrade recommendation. "
                             "The active controller is unverified; switching is blocked.")
    return {"ok": True, "report": report, "freshness": freshness, "cached_only": True}


def refresh_report(status_dir: Path, *, fetch=fetch_document, selection=configured_selection, now=None):
    from jarvis.status.daily import write_atomic
    report = collect(fetch=fetch, selection=selection, now=now)
    # Explicit caller receives the report; no greeting notice is needed here.
    report["notice_pending"] = False
    write_atomic(status_dir / REPORT_NAME, report)
    return read_report(status_dir, selection=selection, now=now)


def run_passive(*, status_dir: Path, now=None, selection=configured_selection, notice=None):
    """Scheduled addition: local cached evidence only, no network or inference."""
    from jarvis.status.daily import write_atomic
    now = now or datetime.now(timezone.utc)
    prior = _raw(status_dir)
    current = _selection(selection)
    report = _report((prior or {}).get("sources") or [], current, now)
    def meaning(value):
        return {key: value.get(key) for key in ("configured_selection", "sources", "recommendation")}
    changed = prior is None or meaning(prior) != meaning(report)
    report["notice_pending"] = changed or bool((prior or {}).get("notice_pending"))
    write_atomic(status_dir / REPORT_NAME, report)
    visible = read_report(status_dir, selection=lambda: current, now=now)
    if report["notice_pending"]:
        if notice is None:
            from jarvis.notices import add_notice
            notice = add_notice
        try:
            notice_id = notice("daily_status", "harness-models", visible["report"]["summary"][:600])
            report["notice_pending"] = not (type(notice_id) is int and notice_id >= 0)
        except Exception:
            report["notice_pending"] = True
        write_atomic(status_dir / REPORT_NAME, report)
    return visible
