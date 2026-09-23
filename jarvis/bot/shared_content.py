"""Safe staging and transfer contract for text/image sharing.

Normalization is local and bounded. Nothing is uploaded, persisted, or sent
to a provider until the user explicitly approves the staged item.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import base64
import re
import uuid
import inspect
import asyncio
from typing import Awaitable, Callable

MAX_TEXT_CHARS = 12_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENTS = 4
MAX_QUESTION_CHARS = 2_000
MAX_CHUNK_BYTES = 16 * 1024
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_CONSENT_SPACE = re.compile(r"[^a-z0-9]+")

SHARED_CONTENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "shared_content",
        "description": "Ask Mortimer to analyze explicitly staged text or images after user approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "attachment_ids": {"type": "array", "items": {"type": "string"},
                                    "minItems": 1, "maxItems": MAX_ATTACHMENTS},
                "question": {"type": "string", "maxLength": MAX_QUESTION_CHARS},
            },
            "required": ["attachment_ids", "question"],
        },
    },
}


@dataclass(frozen=True)
class SharedContent:
    content_id: str
    kind: str
    mime_type: str
    text: str | None
    data: bytes | None
    digest: str
    ephemeral: bool = True


def parse_voice_consent(text: str) -> bool | None:
    """Return the decision for the one exact spoken approval phrase.

    Punctuation and whitespace are presentation noise; no other utterance is
    accepted. ``None`` means the speech must remain an ordinary user turn.
    """
    normalized = _CONSENT_SPACE.sub(" ", str(text).casefold()).strip()
    if normalized == "send these items":
        return True
    if normalized == "cancel these items":
        return False
    return None


def normalize_shared_content(*, kind: str, text: str | None = None,
                             data: bytes | None = None,
                             mime_type: str | None = None) -> SharedContent:
    if kind == "text":
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text content is required")
        clean = _CONTROL.sub("", text).strip()
        if len(clean) > MAX_TEXT_CHARS:
            raise ValueError("text content exceeds quota")
        payload = clean.encode("utf-8")
        return SharedContent(str(uuid.uuid4()), "text", "text/plain", clean, None,
                             sha256(payload).hexdigest())
    if kind == "image":
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise ValueError("image bytes are required")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image content exceeds quota")
        mime = mime_type or "image/png"
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("unsupported image type")
        raw = bytes(data)
        return SharedContent(str(uuid.uuid4()), "image", mime, None, raw,
                             sha256(raw).hexdigest())
    raise ValueError("unsupported content kind")


def normalize_message(message: dict) -> SharedContent:
    """Decode a transport message without accepting arbitrary file paths."""
    if set(message) - {"kind", "text", "data_base64", "mime_type"}:
        raise ValueError("unknown shared-content field")
    if message.get("kind") == "image":
        try:
            raw = base64.b64decode(message.get("data_base64", ""), validate=True)
        except Exception as exc:
            raise ValueError("invalid image encoding") from exc
        return normalize_shared_content(kind="image", data=raw,
                                       mime_type=message.get("mime_type"))
    return normalize_shared_content(kind="text", text=message.get("text"))


def validate_input_message(message: dict) -> dict:
    """Validate one locked ``input/*`` envelope before any transfer state.

    This is intentionally transport agnostic. It rejects unknown fields,
    malformed UUIDs, oversized questions/chunks, and path-like payloads so a
    WebSocket and WebRTC adapter can share the same boundary.
    """
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise ValueError("input message type is required")
    kind = message["type"]
    common = {"version", "session_id", "generation", "request_id"}
    schemas = {
        "input/offer": {"type", "batch_id", "attachment_ids", "question", "profile"},
        "input/analyze": {"type", "batch_id", "attachment_ids", "question"},
        "input/manifest": {"type", "batch_id", "approval_id", "attachments", "items", "question"},
        "input/chunk": {"type", "transfer_id", "attachment_id", "sequence", "base64"},
        "input/commit": {"type", "transfer_id", "attachment_id", "total_chunks", "total_bytes", "sha256"},
        "input/cancel": {"type", "batch_id", "transfer_id"},
    }
    if kind not in schemas or set(message) - (schemas[kind] | common):
        raise ValueError("unknown or malformed input message")

    if "version" in message and message["version"] != 1:
        raise ValueError("unsupported input message version")

    envelope: dict[str, str | int] = {"type": kind, "version": 1}

    def uuid_field(name: str, *, required: bool = True) -> str | None:
        value = message.get(name)
        if value is None and not required:
            return None
        try:
            parsed = uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"invalid {name}") from exc
        return str(parsed)

    for name in ("session_id", "generation", "request_id"):
        if name in message:
            envelope[name] = uuid_field(name)  # type: ignore[assignment]

    if kind in {"input/offer", "input/analyze"}:
        batch_id = uuid_field("batch_id")
        ids = message.get("attachment_ids")
        question = message.get("question")
        if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_ATTACHMENTS:
            raise ValueError("attachment_ids must contain one to four items")
        # Validate list UUIDs without accepting duplicate IDs.
        normalized_ids = []
        for item in ids:
            try:
                normalized_ids.append(str(uuid.UUID(str(item))))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("invalid attachment id") from exc
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("duplicate attachment ids")
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
            raise ValueError("question is required and bounded")
        result = dict(envelope)
        result.update(batch_id=batch_id, attachment_ids=normalized_ids,
                      question=question.strip())
        if kind == "input/offer":
            profile = message.get("profile", {})
            if not isinstance(profile, dict) or set(profile) - {"id", "label"}:
                raise ValueError("invalid input profile")
            result["profile"] = {"id": str(profile.get("id", ""))[:120],
                                  "label": str(profile.get("label", ""))[:120]}
        return result
    if kind == "input/chunk":
        transfer_id = uuid_field("transfer_id")
        attachment_id = uuid_field("attachment_id")
        sequence = message.get("sequence")
        encoded = message.get("base64")
        if not isinstance(sequence, int) or sequence < 0 or not isinstance(encoded, str):
            raise ValueError("invalid chunk")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("invalid chunk encoding") from exc
        if not raw or len(raw) > MAX_CHUNK_BYTES:
            raise ValueError("chunk exceeds quota")
        result = dict(envelope)
        result.update(transfer_id=transfer_id, attachment_id=attachment_id,
                      sequence=sequence, base64=encoded)
        return result
    if kind == "input/commit":
        transfer_id = uuid_field("transfer_id")
        attachment_id = uuid_field("attachment_id")
        if (not isinstance(message.get("total_chunks"), int) or message["total_chunks"] < 1
                or not isinstance(message.get("total_bytes"), int) or message["total_bytes"] < 1
                or not isinstance(message.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", message["sha256"])):
            raise ValueError("invalid commit metadata")
        result = dict(envelope)
        result.update(transfer_id=transfer_id, attachment_id=attachment_id,
                      total_chunks=message["total_chunks"],
                      total_bytes=message["total_bytes"], sha256=message["sha256"])
        return result
    if kind == "input/manifest":
        uuid_field("batch_id"); uuid_field("approval_id")
        attachments = message.get("attachments", message.get("items"))
        if not isinstance(attachments, list) or not 1 <= len(attachments) <= MAX_ATTACHMENTS:
            raise ValueError("invalid attachment manifest")
        normalized_attachments = []
        allowed_attachment_fields = {"content_id", "kind", "mime_type", "digest", "total_bytes"}
        seen_ids: set[str] = set()
        for item in attachments:
            if not isinstance(item, dict) or set(item) != allowed_attachment_fields:
                raise ValueError("invalid attachment metadata")
            try:
                content_id = str(uuid.UUID(str(item["content_id"])))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("invalid content id") from exc
            if content_id in seen_ids:
                raise ValueError("duplicate attachment id")
            seen_ids.add(content_id)
            if item["kind"] not in {"text", "image"} or not isinstance(item["mime_type"], str):
                raise ValueError("invalid attachment kind")
            allowed_mimes = {"text/plain", "image/png", "image/jpeg", "image/webp"}
            if item["mime_type"] not in allowed_mimes:
                raise ValueError("unsupported attachment type")
            if (not isinstance(item["total_bytes"], int) or isinstance(item["total_bytes"], bool)
                    or item["total_bytes"] < 1 or item["total_bytes"] > MAX_IMAGE_BYTES):
                raise ValueError("invalid attachment size")
            if not isinstance(item["digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["digest"]):
                raise ValueError("invalid attachment digest")
            normalized_attachments.append({"content_id": content_id, "kind": item["kind"],
                                           "mime_type": item["mime_type"], "digest": item["digest"],
                                           "total_bytes": item["total_bytes"]})
        result = dict(envelope)
        result.update(batch_id=uuid_field("batch_id"), approval_id=uuid_field("approval_id"),
                      attachments=normalized_attachments)
        if "question" in message:
            question = message["question"]
            if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
                raise ValueError("invalid analysis question")
            result["question"] = question.strip()
        return result
    result = dict(envelope)
    result.update(batch_id=uuid_field("batch_id", required=False),
                  transfer_id=uuid_field("transfer_id", required=False))
    return result


def approve_transfer(content: SharedContent, *, approved: bool,
                     provider: str | None = None) -> dict:
    if not approved:
        return {"status": "cancelled", "content_id": content.content_id}
    if not provider:
        raise ValueError("provider disclosure is required")
    return {"status": "approved", "content_id": content.content_id,
            "kind": content.kind, "mime_type": content.mime_type,
            "provider": provider, "digest": content.digest,
            "ephemeral": content.ephemeral}


def build_shared_content_tool(send: Callable[[dict], Awaitable[None] | None], *,
                              session_id: str, generation: str,
                              profile: dict[str, str] | None = None,
                              on_offer: Callable[[dict], None] | None = None):
    """Build the voice entry point; it requests approval and never uploads."""
    async def handler(arguments: dict) -> str:
        ids = arguments.get("attachment_ids")
        question = arguments.get("question")
        if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_ATTACHMENTS:
            return "Choose one to four staged items first."
        try:
            ids = [str(uuid.UUID(str(item))) for item in ids]
        except (ValueError, TypeError, AttributeError):
            return "Those staged items are no longer available."
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
            return "The analysis question is missing or too long."
        batch_id = str(uuid.uuid4())
        message = {"type": "input/offer", "version": 1,
                   "session_id": session_id, "generation": generation,
                   "request_id": str(uuid.uuid4()), "batch_id": batch_id,
                   "attachment_ids": ids, "question": question.strip(),
                   "profile": profile or {"id": "", "label": ""}}
        sent = send(message)
        if inspect.isawaitable(sent):
            await sent
        if on_offer is not None:
            on_offer(message)
        return "I displayed the provider and approval notice for those staged items."
    return SHARED_CONTENT_SCHEMA, handler


class SharedContentService:
    """One-shot, tool-free analyzer with request-id replay protection."""

    def __init__(self, *, model: Callable[[list[SharedContent], str], str] | None = None,
                 profile: str = "configured-vision"):
        self._model = model
        self.profile = profile[:120]
        self._items: dict[str, SharedContent] = {}
        self._cache: dict[str, dict] = {}
        self._active: set[str] = set()
        self._cancelled: set[str] = set()

    def stage(self, content: SharedContent) -> None:
        self._items[content.content_id] = content

    def cancel(self, request_id: str) -> None:
        """Cancel an in-flight request; a late provider result is discarded."""
        if request_id:
            self._cancelled.add(request_id)

    async def analyze(self, request_id: str, batch_id: str,
                      attachment_ids: list[str], question: str,
                      approval_id: str | None = None) -> dict:
        if request_id in self._cache:
            return self._cache[request_id]
        if not approval_id or not question.strip() or len(question) > MAX_QUESTION_CHARS or not attachment_ids:
            return {"ok": False, "request_id": request_id, "error_code": "not_approved"}
        if request_id in self._active:
            return {"ok": False, "request_id": request_id, "error_code": "in_progress"}
        try:
            items = [self._items[item_id] for item_id in attachment_ids]
        except KeyError:
            return {"ok": False, "request_id": request_id, "error_code": "decode_failed"}
        self._active.add(request_id)
        try:
            if self._model is None:
                payload = {"ok": False, "request_id": request_id,
                           "error_code": "provider_unavailable"}
                self._cache[request_id] = payload
                return payload
            result = self._model(items, question[:MAX_QUESTION_CHARS])
            if inspect.isawaitable(result):
                result = await result
            if request_id in self._cancelled:
                payload = {"ok": False, "request_id": request_id, "error_code": "cancelled"}
            else:
                answer = str(result)[:12_000]
                payload = {"ok": True, "request_id": request_id, "batch_id": batch_id,
                           "answer": answer, "model": self.profile, "ephemeral": True}
        except asyncio.CancelledError:
            raise
        except Exception:
            payload = {"ok": False, "request_id": request_id, "error_code": "analysis_failed"}
        finally:
            self._active.discard(request_id)
            self._items.clear()
            self._cancelled.discard(request_id)
        self._cache[request_id] = payload
        return payload
