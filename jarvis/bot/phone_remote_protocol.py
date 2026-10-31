"""Closed JSON protocol for the offline Mortimer phone facade."""
from __future__ import annotations

import json
import math
import re
import uuid

from jarvis.bot.phone_remote_result_commands import ACTIONS as CARD_ACTIONS, OPERATIONS as CARD_OPERATIONS

PROTOCOL = "mortimer.phone-remote.v1"
OPERATIONS = {"session.status", "voice.offer", "voice.update", "voice.end",
              "results.snapshot", "results.resume", "call.state", "call.answer", "call.decline"}
OPERATIONS |= CARD_OPERATIONS
_UNAVAILABLE = {"call.state", "call.answer", "call.decline"}
_PAYLOAD_KEYS = {"session.status": set(), "voice.offer": {"sdp"},
                 "voice.update": {"peer_id", "sdp"}, "voice.end": {"peer_id"},
                 "results.snapshot": set(), "results.resume": {"cursor"},
                 **{op: set() for op in _UNAVAILABLE}}
_PAYLOAD_KEYS.update({"results.view": {"generation", "collection_epoch"},
    **{op: {"generation", "collection_epoch", "view_id", "view_revision", "result_id", "result_revision"}
       for op in CARD_ACTIONS}})
_STATUSES = {"ok", "denied", "unavailable", "incompatible"}
_REASONS = {"none", "feature_off", "malformed_request", "unsupported_protocol",
            "not_authorized", "authority_unavailable", "voice_not_ready", "owner_busy",
            "operation_unavailable", "request_conflict", "request_capacity"}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CURSOR = re.compile(r"^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$")
_I63 = (1 << 63) - 1
_SAFE_MS = (1 << 53) - 1
_MAX_RESULTS_RESPONSE_BYTES = 512 * 1024


class ProtocolError(ValueError):
    def __init__(self, reason="malformed_request", request_id=None, status="denied"):
        super().__init__(reason)
        self.reason, self.request_id, self.status = reason, request_id, status


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def _constant(_):
    raise ValueError("non-finite number")


def _walk(value, depth=0):
    if depth > 64:
        raise ValueError("too deep")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite number")
    if type(value) is str:
        value.encode("utf-8", "strict")
    if type(value) is dict:
        for k, v in value.items():
            if type(k) is not str:
                raise ValueError("bad key")
            k.encode("utf-8", "strict")
            _walk(v, depth + 1)
    elif type(value) is list:
        for v in value:
            _walk(v, depth + 1)


def parse_request(raw):
    if type(raw) is bytes:
        if len(raw) > 1_048_576:
            raise ProtocolError()
        try:
            raw = raw.decode("utf-8", "strict")
        except UnicodeError:
            raise ProtocolError() from None
    if type(raw) is not str:
        raise ProtocolError()
    try:
        if len(raw.encode("utf-8", "strict")) > 1_048_576:
            raise ProtocolError()
    except UnicodeError:
        raise ProtocolError() from None
    try:
        obj = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        _walk(obj)
    except (ValueError, TypeError, RecursionError):
        raise ProtocolError() from None
    if type(obj) is not dict:
        raise ProtocolError()
    rid = obj.get("request_id")
    trusted_rid = rid if type(rid) is str and rid and len(rid.encode("utf-8")) <= 128 else None
    if set(obj) != {"kind", "protocol_version", "request_id", "operation", "payload"}:
        raise ProtocolError(request_id=trusted_rid)
    if obj["kind"] != PROTOCOL or type(obj["protocol_version"]) is not int:
        raise ProtocolError(request_id=trusted_rid)
    if obj["protocol_version"] != 1:
        raise ProtocolError("unsupported_protocol", trusted_rid, "incompatible")
    if trusted_rid is None or type(obj["operation"]) is not str:
        raise ProtocolError(request_id=None)
    operation = obj["operation"]
    if operation not in OPERATIONS:
        raise ProtocolError(request_id=trusted_rid)
    payload = obj["payload"]
    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS[operation]:
        raise ProtocolError(request_id=trusted_rid)
    for key in ("sdp", "peer_id"):
        if key in payload and (type(payload[key]) is not str or not payload[key]):
            raise ProtocolError(request_id=trusted_rid)
    if operation == "results.resume" and (
            type(payload["cursor"]) is not str or not _CURSOR.fullmatch(payload["cursor"])):
        raise ProtocolError(request_id=trusted_rid)
    if operation in CARD_OPERATIONS:
        uuid_fields = ("generation", "collection_epoch") + (("view_id", "result_id") if operation in CARD_ACTIONS else ())
        if any(not _valid_uuid(payload[key]) for key in uuid_fields):
            raise ProtocolError(request_id=trusted_rid)
        if operation in CARD_ACTIONS and (type(payload["view_revision"]) is not int
                or not 0 <= payload["view_revision"] <= _I63
                or type(payload["result_revision"]) is not int or not 1 <= payload["result_revision"] <= _I63):
            raise ProtocolError(request_id=trusted_rid)
    return obj


def response(request_id, status, reason, payload=None):
    if type(status) is not str or type(reason) is not str or status not in _STATUSES or reason not in _REASONS:
        raise ValueError("invalid internal response")
    if payload is None:
        payload = {}
    if type(request_id) is not str or not request_id:
        request_id = uuid.uuid4().hex
    try:
        if len(request_id.encode("utf-8", "strict")) > 128:
            request_id = uuid.uuid4().hex
    except UnicodeError:
        request_id = uuid.uuid4().hex
    result = {"request_id": request_id, "status": status, "reason": reason, "payload": payload}
    validate_response(result)
    return result


def validate_success_payload(operation, payload):
    """Validate the exact success DTO for one closed operation."""
    if type(payload) is not dict:
        return False
    if operation in CARD_OPERATIONS:
        return _valid_card_view(payload)
    if operation == "session.status":
        return set(payload) == {"readiness"} and payload["readiness"] == "ready"
    if operation in {"voice.offer", "voice.update"}:
        if set(payload) != {"peer_id", "sdp"}:
            return False
        return all(_valid_text(payload[key]) for key in ("peer_id", "sdp"))
    if operation == "voice.end":
        return (set(payload) == {"peer_id", "ended"} and _valid_text(payload["peer_id"])
                and payload["ended"] is True)
    if operation == "results.snapshot":
        return _valid_snapshot(payload)
    if operation == "results.resume":
        return _valid_resume(payload)
    return False


def _valid_card_view(payload):
    if set(payload) != {"generation", "collection_epoch", "view_id", "view_revision",
                        "selected_result_id", "allowed_operations", "cards"}:
        return False
    if (any(not _valid_uuid(payload[k]) for k in ("generation", "collection_epoch", "view_id"))
            or type(payload["view_revision"]) is not int or not 0 <= payload["view_revision"] <= _I63):
        return False
    allowed, cards = payload["allowed_operations"], payload["cards"]
    if (type(allowed) is not list or any(type(op) is not str or op not in CARD_ACTIONS for op in allowed)
            or allowed != sorted(set(allowed)) or type(cards) is not list or len(cards) > 25):
        return False
    for card in cards:
        if (type(card) is not dict or set(card) != {"result_id", "result_revision", "open", "pinned"}
                or not _valid_uuid(card["result_id"]) or type(card["result_revision"]) is not int
                or not 1 <= card["result_revision"] <= _I63 or type(card["open"]) is not bool
                or type(card["pinned"]) is not bool or (card["pinned"] and not card["open"])):
            return False
    ids = [c["result_id"] for c in cards]
    if ids != sorted(set(ids)) or sum(c["pinned"] for c in cards) > 20:
        return False
    selected = payload["selected_result_id"]
    return selected is None or (_valid_uuid(selected) and any(c["result_id"] == selected and c["open"] for c in cards))


def _valid_text(value):
    if type(value) is not str or not value:
        return False
    try:
        value.encode("utf-8", "strict")
    except UnicodeError:
        return False
    return True


def _valid_uuid(value):
    return type(value) is str and bool(_UUID.fullmatch(value))


def _valid_result_item(item):
    if type(item) is not dict or set(item) != {
            "result_id", "revision", "source", "classification", "title", "body", "received_at_ms"}:
        return False
    result_id, revision, source = item["result_id"], item["revision"], item["source"]
    if (not _valid_uuid(result_id) or type(revision) is not int or not 1 <= revision <= _I63
            or type(source) is not dict or set(source) != {"kind", "id", "revision"}
            or source["kind"] != "synthetic.workspace_result.v1" or source["id"] != result_id
            or type(source["revision"]) is not int or source["revision"] != revision
            or type(item["classification"]) is not str or item["classification"] != "ordinary"):
        return False
    title, body, received = item["title"], item["body"], item["received_at_ms"]
    return ( _valid_text(title) and len(title.encode("utf-8")) <= 512 and "\x00" not in title
            and _valid_text(body) and len(body.encode("utf-8")) <= 8192 and "\x00" not in body
            and type(received) is int and 0 <= received <= _SAFE_MS)


def _valid_snapshot(payload):
    if set(payload) != {"generation", "collection_epoch", "content_watermark", "cursor", "items"}:
        return False
    if (not _valid_uuid(payload["generation"]) or not _valid_uuid(payload["collection_epoch"])
            or type(payload["content_watermark"]) is not int
            or not 0 <= payload["content_watermark"] <= _I63
            or type(payload["cursor"]) is not str or not _CURSOR.fullmatch(payload["cursor"])
            or type(payload["items"]) is not list or len(payload["items"]) > 25):
        return False
    ids = []
    for item in payload["items"]:
        if not _valid_result_item(item):
            return False
        ids.append(item["result_id"])
    return ids == sorted(set(ids), key=lambda value: value.encode("ascii"))


def _valid_resume(payload):
    common = {"generation", "collection_epoch", "reset_required"}
    if type(payload.get("reset_required")) is not bool:
        return False
    if payload["reset_required"]:
        return (set(payload) == common and _valid_uuid(payload["generation"])
                and _valid_uuid(payload["collection_epoch"]))
    if set(payload) != common | {"content_watermark", "has_more", "cursor", "events"}:
        return False
    if (not _valid_uuid(payload["generation"]) or not _valid_uuid(payload["collection_epoch"])
            or type(payload["content_watermark"]) is not int
            or not 0 <= payload["content_watermark"] <= _I63
            or type(payload["has_more"]) is not bool or type(payload["cursor"]) is not str
            or not _CURSOR.fullmatch(payload["cursor"])
            or type(payload["events"]) is not list or len(payload["events"]) > 25):
        return False
    previous = None
    for event in payload["events"]:
        if (type(event) is not dict or set(event) != {"sequence", "kind", "item"}
                or type(event["sequence"]) is not int or not 1 <= event["sequence"] <= _I63
                or (previous is not None and event["sequence"] != previous + 1)
                or event["sequence"] > payload["content_watermark"]
                or event["kind"] != "upsert" or not _valid_result_item(event["item"])):
            return False
        previous = event["sequence"]
    return True


def validate_response(value, *, operation=None, require_operation=False):
    """Reject unknown response fields, status/reason pairs and unsafe DTOs."""
    if type(value) is not dict or set(value) != {"request_id", "status", "reason", "payload"}:
        raise ValueError("invalid response envelope")
    rid = value["request_id"]
    if type(rid) is not str or not rid:
        raise ValueError("invalid response request ID")
    try:
        if len(rid.encode("utf-8", "strict")) > 128:
            raise ValueError("invalid response request ID")
    except UnicodeError:
        raise ValueError("invalid response request ID") from None
    status, reason, payload = value["status"], value["reason"], value["payload"]
    if (type(status) is not str or type(reason) is not str or status not in _STATUSES
            or reason not in _REASONS or type(payload) is not dict):
        raise ValueError("invalid response values")
    if status == "ok":
        if reason != "none":
            raise ValueError("invalid success reason")
        if require_operation and operation is None:
            raise ValueError("success response needs its operation schema")
        if operation is not None and not validate_success_payload(operation, payload):
            raise ValueError("invalid operation success payload")
    else:
        allowed = {
            "denied": {"malformed_request", "not_authorized", "request_conflict", "request_capacity"},
            "unavailable": {"feature_off", "authority_unavailable", "voice_not_ready", "owner_busy", "operation_unavailable"},
            "incompatible": {"unsupported_protocol"},
        }
        if (reason not in allowed[status] or payload != {}
                or (operation in CARD_OPERATIONS and reason == "voice_not_ready")):
            raise ValueError("invalid error response")
    return True


def encode_response(value, *, operation=None):
    validate_response(value, operation=operation, require_operation=value.get("status") == "ok" if type(value) is dict else True)
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if operation in {"results.snapshot", "results.resume"} and len(encoded.encode("utf-8", "strict")) > _MAX_RESULTS_RESPONSE_BYTES:
        raise ValueError("results response exceeds byte limit")
    if operation in CARD_OPERATIONS and len(encoded.encode("utf-8", "strict")) > 16 * 1024:
        raise ValueError("card view exceeds byte limit")
    return encoded
