"""mcp-kb logic — curated-documents knowledge base, backed by the
mortimer-vault HTTP service (services/mortimer-vault, run via scripts/run_kb.sh).

W1 (2026-08-31): completes the Hermes three-layer memory architecture.
jarvis.memory is the FACTS layer — short, keyed, auto-injected into every
Supervisor turn. This module is the DURABLE CURATED DOCUMENTS layer —
long-form markdown, searched on demand, never auto-injected. The two are
complementary, not competing: this module never touches the `memories`
table, and jarvis.memory is never called from here except for its content
scanner (reused, not duplicated — see kb_write below).

Naming: tools are kb_* (not memory_* or notes_*) because both of those
prefixes are already taken by mcp_servers/mcp_memory and mcp_servers/
mcp_notes respectively. Do not rename.

Thin by construction, same discipline as mcp_memory/logic.py: every
function returns a JSON-serializable dict, NEVER raises. Vault-unreachable
and vault-rejected-the-request are both just {"ok": False, "error": ...} —
the voice pipeline must never see an exception from this module.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from jarvis.memory import scan_memory_content

logger = logging.getLogger(__name__)

DEFAULT_KB_BASE_URL = "http://127.0.0.1:8484"
REQUEST_TIMEOUT_S = 10.0

# Throttle "vault unreachable" warnings to at most once per 60s per
# process, rather than once per failed call — a stopped vault service
# would otherwise flood the log on every tool call.
_LAST_UNREACHABLE_WARNING = 0.0
_UNREACHABLE_WARNING_INTERVAL_S = 60.0


def _base_url() -> str:
    return os.environ.get("KB_BASE_URL", DEFAULT_KB_BASE_URL)


def _warn_unreachable(exc: Exception) -> None:
    global _LAST_UNREACHABLE_WARNING
    now = time.monotonic()
    if now - _LAST_UNREACHABLE_WARNING >= _UNREACHABLE_WARNING_INTERVAL_S:
        logger.warning("kb_vault_unreachable base_url=%s error=%s", _base_url(), exc)
        _LAST_UNREACHABLE_WARNING = now


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST to the vault service. Never raises — returns {"ok": False, ...}
    on any connection, timeout, or non-2xx failure."""
    url = f"{_base_url()}{path}"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
            response = client.post(url, json=body)
    except httpx.RequestError as exc:
        _warn_unreachable(exc)
        return {"ok": False, "error": "knowledge base is unreachable"}

    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": f"knowledge base returned non-JSON (status {response.status_code})"}

    if response.status_code >= 400:
        # Vault structured errors: {"error": "CODE", "message": "...", "id"?: "..."}
        code = payload.get("error", "UNKNOWN")
        message = payload.get("message", "")
        return {"ok": False, "error": f"{code}: {message}" if message else code}

    return {"ok": True, **payload}


def _without_none(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


def kb_search(
    query: str,
    k: int | None = None,
    type: str | None = None,
    tags: list[str] | None = None,
    confidence_min: str | None = None,
) -> dict[str, Any]:
    """Search the knowledge base."""
    body = _without_none(query=query, k=k, type=type, tags=tags, confidence_min=confidence_min)
    return _post("/search", body)


def kb_read(id: str) -> dict[str, Any]:
    """Read one knowledge-base document in full by id."""
    return _post("/read", {"id": id})


def kb_write(
    type: str,
    body: str,
    tags: list[str],
    confidence: str,
    source_sessions: list[str],
    id: str | None = None,
    expected_hash: str | None = None,
    previous_excerpt: str | None = None,
) -> dict[str, Any]:
    """Create or update a knowledge-base document.

    D8 discipline (mirrors jarvis/bot/remember_tool.py): the content scan
    rejection reason is logged at WARNING but NEVER returned to the
    caller — returning it would teach the model how to rephrase around
    the filter. The caller only ever sees the generic "content rejected".
    """
    reason = scan_memory_content(body)
    if reason is not None:
        logger.warning("kb_write_rejected reason=%s id=%s", reason, id)
        return {"ok": False, "error": "content rejected"}

    payload = _without_none(
        type=type,
        body=body,
        tags=tags,
        confidence=confidence,
        source_sessions=source_sessions,
        id=id,
        expected_hash=expected_hash,
        previous_excerpt=previous_excerpt,
    )
    return _post("/write", payload)


def kb_neighbors(id: str) -> dict[str, Any]:
    """List documents linked to or from the given document id."""
    return _post("/neighbors", {"id": id})


def kb_delete(id: str) -> dict[str, Any]:
    """Delete a capture-type document. Other document types cannot be deleted."""
    return _post("/delete", {"id": id})


def kb_flush() -> dict[str, Any]:
    """Flush buffered access-time bookkeeping into a single commit."""
    return _post("/flush_access", {})

