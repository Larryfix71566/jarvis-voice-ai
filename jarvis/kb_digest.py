"""jarvis/kb_digest.py — session-end digester for the knowledge-base
(mcp_kb / mortimer-vault) layer.

W1 (2026-08-31). Mirrors jarvis/memory.py's failure discipline exactly:
this module must NEVER raise into the voice pipeline. Any failure — LLM
error, vault unreachable, malformed response — logs and returns False,
leaving the pipeline unaffected. Call site: jarvis/bot/pipeline.py
teardown, immediately after update_memory_from_session (see that file for
the exact splice).

This is a SEPARATE layer from jarvis.memory: memory.py folds a session
into short keyed facts injected every turn; this module folds a session
into a long-form curated document, searched on demand via kb_search, never
auto-injected into the base prompt. Reuses jarvis.memory.scan_memory_content
(D8 discipline: never reveal the rejection reason to a caller) rather than
maintaining a second content filter.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from jarvis.config import Settings
from jarvis.db import get_conn
from jarvis.memory import MAX_ROW_CHARS, MAX_TRANSCRIPT_ROWS, scan_memory_content
from jarvis.memory_model import make_background_async_client
from jarvis.model_execution import (
    ModelContextMessage,
    ModelExecutionRequest,
    execute_chat,
)
from jarvis.privacy_policy import DataPolicy
from jarvis.usage_ledger import (
    provider_from_base_url,
    record_completion,
    record_execution_result,
)
from mcp_servers.mcp_kb import logic as kb

logger = logging.getLogger(__name__)

DIGEST_SYSTEM_PROMPT = (
    "You write the session digest for a personal AI assistant's knowledge "
    "base. Given one session transcript, write a self-contained markdown "
    "digest of what was worked on, decided, and left open. Plain prose, no "
    "headers needed. Include concrete names (projects, files, decisions). "
    "Omit small talk. Maximum 3500 characters. If the session was trivial, "
    "respond with exactly: SKIP"
)

# Buffer under the vault's hard DIGEST_MAX_CHARS (4000) — the splitter must
# never let a write reach the vault's own rejection threshold.
DIGEST_SPLIT_THRESHOLD = 3800
DIGEST_EXTRACTION_TIMEOUT_S = 30.0


def _session_transcript(conn, session_id: str) -> list[Any]:
    """(recent rows for the session). Mirrors jarvis.memory._session_transcript's
    query shape exactly (that function returns (rows, summary); this module
    only needs rows, so it is not imported/reused directly to avoid coupling
    to memory.py's private helper — same query, independent copy)."""
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, MAX_TRANSCRIPT_ROWS),
    ).fetchall()
    rows.reverse()
    return rows


def _split_into_parts(text: str, limit: int) -> list[str]:
    """Split text on paragraph boundaries into chunks each <= limit chars.
    Pure and total: always returns at least one part (even if the whole
    text is a single paragraph longer than limit, in which case that one
    paragraph is hard-cut at limit — better than an oversized part reaching
    the vault, which is the failure this function exists to prevent)."""
    paragraphs = text.split("\n\n")
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            if len(para) <= limit:
                current = para
            else:
                # single paragraph exceeds the limit on its own — hard cut
                for i in range(0, len(para), limit):
                    parts.append(para[i : i + limit])
                current = ""
    if current:
        parts.append(current)
    return parts or [text[:limit]]


async def write_session_digest(
    settings: Settings,
    session_id: str,
    client_factory: Callable[[Settings], Any] | None = None,
) -> bool:
    """Fold one finished session into a curated knowledge-base digest.

    Never raises. Returns True only when a digest document was actually
    written to the knowledge base.
    """
    try:
        with get_conn() as conn:
            rows = _session_transcript(conn, session_id)
        if not any(r["role"] == "user" for r in rows):
            return False

        transcript = "\n".join(
            f"{r['role'].upper()}: {r['content'][:MAX_ROW_CHARS]}" for r in rows
        )
        if client_factory is not None:
            # Test seam only; production uses JARVIS_BACKGROUND_PROFILE.
            client = client_factory(settings)
            model = settings.openai_model
            resolved = None
        else:
            client, route = make_background_async_client(settings)
            model = route.model
            resolved = route.resolved
        if resolved is not None:
            execution = await execute_chat(
                ModelExecutionRequest(
                    workload=resolved.workload,
                    task_id=f"kb-digest:{session_id}",
                    parent_request_id=session_id,
                    instructions=f"Session transcript:\n{transcript}",
                    context=(ModelContextMessage(
                        "system", DIGEST_SYSTEM_PROMPT,
                        DataPolicy("confidential", "digest-system-prompt"),
                    ),),
                    data_policy=DataPolicy("confidential", "session-transcript"),
                    timeout_s=DIGEST_EXTRACTION_TIMEOUT_S,
                ),
                resolved,
                # The already resolved route/client are one immutable
                # selection. Do not resolve preferences a second time.
                client_factory=lambda _: client,
            )
            record_execution_result("kb_digest", execution, session_id=session_id)
            digest = execution.text.strip()
        else:
            # Compatibility path for deployments that have not enabled model
            # routing yet, plus the injected test seam. It retains its exact
            # direct-client request shape until that feature gate is enabled.
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Session transcript:\n{transcript}"},
                ],
            )
            try:
                record_completion(
                    rung="kb_digest",
                    provider=provider_from_base_url(str(client.base_url)),
                    model=model,
                    response=response,
                    session_id=session_id,
                )
            except Exception:
                pass
            digest = (response.choices[0].message.content or "").strip()

        wrote = False
        skip = False
        if digest == "SKIP":
            skip = True
        elif not digest:
            logger.warning("kb_digest_empty_response")
            skip = True
        else:
            reason = scan_memory_content(digest)
            if reason is not None:
                logger.warning("kb_digest_rejected")
                skip = True

        if skip:
            pass
        elif len(digest) > DIGEST_SPLIT_THRESHOLD:
            parts = _split_into_parts(digest, DIGEST_SPLIT_THRESHOLD)
            part_ids: list[str] = []
            for part_body in parts:
                result = kb.kb_write(
                    type="session-digest",
                    body=part_body,
                    tags=["digest-part"],
                    confidence="medium",
                    source_sessions=[session_id],
                )
                if result.get("ok"):
                    part_ids.append(result["id"])
                else:
                    logger.warning(
                        "kb_digest_part_write_failed",
                    )

            if part_ids:
                links = "\n".join(f"Continued in [[{pid}]]." for pid in part_ids)
                head = parts[0][: DIGEST_SPLIT_THRESHOLD - len(links) - 2]
                primary_body = f"{head}\n\n{links}"
                primary_result = kb.kb_write(
                    type="session-digest",
                    body=primary_body,
                    tags=["digest"],
                    confidence="medium",
                    source_sessions=[session_id],
                )
                wrote = bool(primary_result.get("ok"))
                if not wrote:
                    logger.warning(
                        "kb_digest_primary_write_failed",
                    )
        else:
            result = kb.kb_write(
                type="session-digest",
                body=digest,
                tags=["digest"],
                confidence="medium",
                source_sessions=[session_id],
            )
            wrote = bool(result.get("ok"))
            if not wrote:
                logger.warning(
                    "kb_digest_write_failed",
                )

        flush_result = kb.kb_flush()
        if not flush_result.get("ok"):
            logger.warning(
                "kb_flush_failed",
            )

        return wrote
    except Exception as exc:  # noqa: BLE001 — digest must never break the pipeline
        logger.warning("kb_digest_failed error_type=%s",
                       type(exc).__name__[:64])
        try:
            kb.kb_flush()
        except Exception:  # noqa: BLE001
            pass
        return False
