"""Closed JSON protocol for the offline Mortimer phone facade."""
from __future__ import annotations

import json
import math
import uuid

PROTOCOL = "mortimer.phone-remote.v1"
OPERATIONS = {"session.status", "voice.offer", "voice.update", "voice.end",
              "results.snapshot", "results.resume", "call.state", "call.answer", "call.decline"}
_UNAVAILABLE = {"results.snapshot", "results.resume", "call.state", "call.answer", "call.decline"}
_PAYLOAD_KEYS = {"session.status": set(), "voice.offer": {"sdp"},
                 "voice.update": {"peer_id", "sdp"}, "voice.end": {"peer_id"},
                 **{op: set() for op in _UNAVAILABLE}}
_STATUSES = {"ok", "denied", "unavailable", "incompatible"}
_REASONS = {"none", "feature_off", "malformed_request", "unsupported_protocol",
            "not_authorized", "authority_unavailable", "voice_not_ready", "owner_busy",
            "operation_unavailable", "request_conflict", "request_capacity"}


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
    return obj


def response(request_id, status, reason, payload=None):
    if status not in _STATUSES or reason not in _REASONS:
        raise ValueError("invalid internal response")
    if payload is None:
        payload = {}
    return {"request_id": request_id if type(request_id) is str and request_id else uuid.uuid4().hex,
            "status": status, "reason": reason, "payload": payload}


def encode_response(value):
    if type(value) is not dict or set(value) != {"request_id", "status", "reason", "payload"}:
        raise ValueError("invalid response")
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
