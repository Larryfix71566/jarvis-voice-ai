"""Strict private IPC adapter for the offline native authority owner claim.

This is a cooperative same-user process channel, not a network listener or a
sandbox. Production packaging, signing, Keychain access and startup are out of
scope. Tests launch the Swift owner and this module as separate processes.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import socket
import sqlite3
import stat
import struct
import threading
import types
import uuid
from typing import Any, Callable

from jarvis.bot.phone_admission_store import (
    AUTHORITY_TABLES,
    AnchorState,
    PhoneAdmissionStore,
    StoreDenied,
    StoreUnavailable,
)


PROTOCOL = "mortimer.phone-authority-channel.v1"
VERSION = 1
PROTOCOL_V2 = "mortimer.phone-authority-channel.v2"
VERSION_V2 = 2
MAX_FRAME_BYTES = 65_536
MAX_SEQUENCE = (1 << 64) - 1
FRAME_FIELDS = frozenset({
    "protocol", "version", "kind", "owner_incarnation", "child_incarnation",
    "sequence", "correlation_id", "payload",
})
OPERATIONS = frozenset({
    "store.open", "store.read", "session.login", "session.signout",
    "authority.mutate", "ticket.issue", "ticket.consume",
})
ERROR_CODES = frozenset({
    "owner_busy", "authority_unavailable", "anchor_missing", "anchor_locked",
    "anchor_denied", "anchor_corrupt", "stale_incarnation", "sequence_invalid",
    "correlation_invalid", "grant_invalid", "phase_invalid", "malformed_frame",
    "unsupported_version", "child_exited",
})
_UINT32_MAX = (1 << 32) - 1


class ChannelProtocolError(StoreUnavailable):
    """The private channel violated its closed framing contract."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _validate_json_value(value: object, depth: int = 0) -> None:
    if depth > 64:
        raise ChannelProtocolError("JSON nesting limit exceeded")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ChannelProtocolError("non-finite JSON number")
        return
    if type(value) is list:
        for item in value:
            _validate_json_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ChannelProtocolError("JSON object keys must be strings")
            _validate_json_value(item, depth + 1)
        return
    raise ChannelProtocolError("unsupported JSON value")


def decode_frame_payload(payload: bytes) -> dict[str, Any]:
    """Decode one bounded JSON object, rejecting duplicate and non-finite data."""
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_FRAME_BYTES:
        raise ChannelProtocolError("invalid frame length")
    try:
        value = json.loads(
            payload.decode("utf-8", "strict"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError) as exc:
        raise ChannelProtocolError("invalid frame JSON") from exc
    if type(value) is not dict:
        raise ChannelProtocolError("frame must be an object")
    _validate_json_value(value)
    return value


def encode_frame_payload(value: dict[str, Any]) -> bytes:
    if type(value) is not dict:
        raise ChannelProtocolError("frame must be an object")
    _validate_json_value(value)
    try:
        payload = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8", "strict")
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise ChannelProtocolError("invalid frame value") from exc
    if not 1 <= len(payload) <= MAX_FRAME_BYTES:
        raise ChannelProtocolError("invalid frame length")
    return payload


def _exact_int(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _canonical_uuid(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _state_to_wire(state: AnchorState) -> dict[str, object]:
    return {
        "anchor_version": state.anchor_version,
        "host_id": state.host_id,
        "host_generation": state.host_generation,
        "transition_id": state.transition_id,
        "transition_state": state.transition_state,
        "login_counter": state.login_counter,
    }


def _state_from_wire(value: object, *, allow_pending: bool = True) -> AnchorState:
    fields = {
        "anchor_version", "host_id", "host_generation", "transition_id",
        "transition_state", "login_counter",
    }
    if type(value) is not dict or value.keys() != fields:
        raise ChannelProtocolError("invalid anchor state")
    if (not _exact_int(value["anchor_version"], 1, _UINT32_MAX)
            or type(value["host_id"]) is not str or not value["host_id"].strip()
            or not _exact_int(value["host_generation"], 0, MAX_SEQUENCE)
            or not _exact_int(value["login_counter"], 0, MAX_SEQUENCE)
            or value["transition_state"] not in ("stable", "pending")
            or (value["transition_state"] == "pending" and not allow_pending)
            or (value["transition_id"] is not None
                and (type(value["transition_id"]) is not str or not value["transition_id"]))
            or (value["transition_state"] == "stable" and value["transition_id"] is not None)
            or (value["transition_state"] == "pending" and value["transition_id"] is None)):
        raise ChannelProtocolError("invalid anchor state")
    return AnchorState(
        anchor_version=value["anchor_version"],
        host_id=value["host_id"],
        host_generation=value["host_generation"],
        transition_id=value["transition_id"],
        transition_state=value["transition_state"],
        login_counter=value["login_counter"],
    )


class NativeProtectedAnchor:
    """Implements the store's injected ProtectedAnchor over inherited FD 3."""

    protocol = PROTOCOL
    version = VERSION
    operations = OPERATIONS
    service_authority = False

    def __init__(self, channel: socket.socket) -> None:
        if type(channel) is not socket.socket:
            raise TypeError("a connected socket is required")
        self._socket = channel
        self._send_sequence = 1
        self._receive_sequence = 0
        self._owner_incarnation: str | None = None
        self._child_incarnation: str | None = None
        self._scope_lock = threading.Lock()
        self._scope_local = threading.local()
        self._grant_id: str | None = None
        self._grant_operation: str | None = None
        self._grant_owner_thread: int | None = None
        self._grant_read_verified = False
        self._anchor_state: AnchorState | None = None
        self._closed = False
        try:
            hello = self._receive()
        except BaseException:
            self.close()
            raise
        if hello["kind"] != "owner.hello" or hello["sequence"] != 1:
            self.close()
            raise ChannelProtocolError("owner handshake required")
        if (type(hello["payload"]) is not dict
                or hello["payload"].keys() != {"max_frame_bytes"}
                or not _exact_int(hello["payload"]["max_frame_bytes"], MAX_FRAME_BYTES, MAX_FRAME_BYTES)):
            self.close()
            raise ChannelProtocolError("unsupported owner handshake")
        self._receive_sequence = 1
        self._owner_incarnation = hello["owner_incarnation"]
        self._child_incarnation = hello["child_incarnation"]
        self._correlation_id = hello["correlation_id"]
        self._send("child.ready", {}, correlation_id=self._correlation_id)

    @classmethod
    def from_inherited_environment(cls) -> "NativeProtectedAnchor":
        raw_fd = os.environ.get("PHONE_REMOTE_AUTHORITY_CHANNEL_FD")
        lock_fd = os.environ.get("PHONE_REMOTE_AUTHORITY_LOCK_FD")
        if raw_fd != "3" or lock_fd != "4":
            raise StoreUnavailable("authority channel is unavailable")
        try:
            if not stat.S_ISREG(os.fstat(4).st_mode):
                raise StoreUnavailable("authority channel is unavailable")
            channel = socket.socket(fileno=3)
        except OSError as exc:
            raise StoreUnavailable("authority channel is unavailable") from exc
        return cls(channel)

    def _read_exact(self, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise ChannelProtocolError("truncated or closed channel")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _receive(self) -> dict[str, Any]:
        if self._closed:
            raise ChannelProtocolError("closed channel")
        try:
            size = struct.unpack(">I", self._read_exact(4))[0]
            if not 1 <= size <= MAX_FRAME_BYTES:
                raise ChannelProtocolError("invalid frame length")
            frame = decode_frame_payload(self._read_exact(size))
            if frame.keys() != FRAME_FIELDS:
                raise ChannelProtocolError("invalid frame envelope")
            if frame["protocol"] != self.protocol or not _exact_int(frame["version"], self.version, self.version):
                raise ChannelProtocolError("unsupported protocol")
            if (type(frame["kind"]) is not str or not frame["kind"]
                    or not _canonical_uuid(frame["owner_incarnation"])
                    or not _canonical_uuid(frame["child_incarnation"])
                    or not _exact_int(frame["sequence"], 1, MAX_SEQUENCE)
                    or not _canonical_uuid(frame["correlation_id"])
                    or type(frame["payload"]) is not dict):
                raise ChannelProtocolError("invalid frame fields")
            if frame["sequence"] != self._receive_sequence + 1:
                raise ChannelProtocolError("invalid frame sequence")
            if self._receive_sequence == 0:
                if self._owner_incarnation is not None or self._child_incarnation is not None:
                    raise ChannelProtocolError("invalid initial state")
            elif (frame["owner_incarnation"] != self._owner_incarnation
                  or frame["child_incarnation"] != self._child_incarnation):
                raise ChannelProtocolError("stale channel incarnation")
            self._receive_sequence = frame["sequence"]
            return frame
        except ChannelProtocolError:
            self.close()
            raise
        except (OSError, struct.error) as exc:
            self.close()
            raise ChannelProtocolError("channel read failed") from exc

    def _send(self, kind: str, payload: dict[str, Any], *, correlation_id: str | None = None) -> None:
        if self._closed or self._send_sequence > MAX_SEQUENCE:
            self.close()
            raise ChannelProtocolError("closed or exhausted channel")
        correlation_id = correlation_id or str(uuid.uuid4())
        if not _canonical_uuid(correlation_id):
            self.close()
            raise ChannelProtocolError("invalid correlation id")
        frame = {
            "protocol": self.protocol,
            "version": self.version,
            "kind": kind,
            "owner_incarnation": self._owner_incarnation,
            "child_incarnation": self._child_incarnation,
            "sequence": self._send_sequence,
            "correlation_id": correlation_id,
            "payload": payload,
        }
        encoded = encode_frame_payload(frame)
        try:
            self._socket.sendall(struct.pack(">I", len(encoded)) + encoded)
        except OSError as exc:
            self.close()
            raise ChannelProtocolError("channel write failed") from exc
        self._send_sequence += 1
        self._last_correlation_id = correlation_id

    def _request(self, kind: str, payload: dict[str, Any], expected: str) -> dict[str, Any]:
        if kind == "child.grant.acquire":
            operation = payload.get("operation") if type(payload) is dict else None
            if self._require_operation_context() != operation:
                raise StoreUnavailable("store operation context does not match authority grant")
        elif kind in {"child.anchor.read", "child.anchor.advance", "child.grant.release", "child.grant.abort"}:
            self._require_grant()
        correlation_id = str(uuid.uuid4())
        self._send(kind, payload, correlation_id=correlation_id)
        response = self._receive()
        if response["correlation_id"] != correlation_id:
            self.close()
            raise ChannelProtocolError("response correlation mismatch")
        if response["kind"] == "owner.error":
            code = response["payload"].get("code")
            if (response["payload"].keys() != {"code"}
                    or type(code) is not str or code not in ERROR_CODES):
                self.close()
                raise ChannelProtocolError("invalid owner error")
            self.close()
            raise StoreUnavailable("authority owner unavailable")
        if response["kind"] != expected:
            self.close()
            raise ChannelProtocolError("unexpected owner response")
        return response["payload"]

    @contextlib.contextmanager
    def _operation_context(self, operation: str, *, method: str | None = None):
        if operation not in self.operations:
            raise StoreUnavailable("unsupported store operation")
        if not self._scope_lock.acquire(blocking=False):
            raise StoreUnavailable("concurrent or nested store operation")
        if getattr(self._scope_local, "operation", None) is not None:
            self._scope_lock.release()
            raise StoreUnavailable("nested store operation")
        self._scope_local.operation = operation
        self._scope_local.method = method
        self._scope_local.thread_id = threading.get_ident()
        self._scope_local.grant_count = 0
        self._scope_local.allow_zero_grant_false = False
        try:
            yield
            valid_zero_grant_false = (
                self.service_authority
                and operation == "service.authorize"
                and method == "binding_current"
                and self._scope_local.allow_zero_grant_false is True
                and self._scope_local.grant_count == 0
            )
            if self._scope_local.grant_count != 1 and not valid_zero_grant_false:
                raise StoreUnavailable("store method did not use exactly one authority grant")
        finally:
            self._scope_local.operation = None
            self._scope_local.method = None
            self._scope_local.thread_id = None
            self._scope_local.allow_zero_grant_false = False
            self._scope_lock.release()

    @contextlib.contextmanager
    def exclusive(self):
        operation = getattr(self._scope_local, "operation", None)
        if (operation not in self.operations or self._grant_id is not None
                or getattr(self._scope_local, "grant_count", 0) != 0):
            raise StoreUnavailable("explicit store operation context required")
        payload = self._request("child.grant.acquire", {"operation": operation}, "owner.grant.acquired")
        grant_id = payload.get("grant_id")
        if (not _canonical_uuid(grant_id) or payload.get("operation") != operation
                or payload.keys() != {"grant_id", "operation"}):
            self.close()
            raise ChannelProtocolError("invalid grant response")
        self._grant_id = grant_id
        self._grant_operation = operation
        self._grant_owner_thread = threading.get_ident()
        self._grant_read_verified = False
        self._scope_local.grant_count += 1
        self._anchor_state = None
        try:
            yield
        except StoreDenied:
            if (not self.service_authority
                    or getattr(self._scope_local, "operation", None) != "service.authorize"
                    or getattr(self._scope_local, "method", None) not in {"current_binding", "binding_current"}
                    or not self._grant_read_verified or self._closed):
                if not self._abort_grant():
                    raise StoreUnavailable("authority operation outcome is unknown")
                raise
            grant_id = self._grant_id
            try:
                payload = self._request("child.grant.release", {"grant_id": grant_id}, "owner.grant.released")
                if payload != {"grant_id": grant_id}:
                    raise ChannelProtocolError("invalid release acknowledgment")
                self._grant_id = self._grant_operation = None
                self._grant_owner_thread = None
                self._grant_read_verified = False
                self._anchor_state = None
            except BaseException as exc:
                self.close()
                raise StoreUnavailable("authority operation outcome is unknown") from exc
            raise
        except BaseException as original:
            if not self._abort_grant():
                raise StoreUnavailable("authority operation outcome is unknown") from original
            raise
        else:
            if not self._grant_read_verified:
                if not self._abort_grant():
                    raise StoreUnavailable("authority operation outcome is unknown")
                raise StoreUnavailable("store operation did not read protected state")
            try:
                payload = self._request("child.grant.release", {"grant_id": grant_id}, "owner.grant.released")
                if payload != {"grant_id": grant_id}:
                    raise ChannelProtocolError("invalid release acknowledgment")
                self._grant_id = None
                self._grant_operation = None
                self._grant_owner_thread = None
                self._grant_read_verified = False
                self._anchor_state = None
            except BaseException:
                self.close()
                raise

    def _abort_grant(self) -> bool:
        grant_id = self._grant_id
        acknowledged = False
        try:
            if grant_id is not None and not self._closed:
                payload = self._request("child.grant.abort", {"grant_id": grant_id}, "owner.grant.aborted")
                if payload != {"grant_id": grant_id, "disposition": "unknown"}:
                    raise ChannelProtocolError("invalid abort acknowledgment")
                acknowledged = True
        except BaseException:
            # Without a valid abort acknowledgment the operation result is
            # uncertain, so callers must receive only the neutral failure.
            pass
        finally:
            self._grant_id = None
            self._grant_operation = None
            self._grant_owner_thread = None
            self._grant_read_verified = False
            self._anchor_state = None
            self.close()
        return acknowledged

    def read(self) -> AnchorState:
        grant_id = self._require_grant()
        payload = self._request("child.anchor.read", {"grant_id": grant_id}, "owner.anchor.state")
        if payload.keys() != {"grant_id", "state"} or payload["grant_id"] != grant_id:
            self.close()
            raise ChannelProtocolError("invalid anchor read response")
        state = _state_from_wire(payload["state"])
        if self._anchor_state is None:
            if (state.anchor_version != 1 or state.host_generation <= 0
                    or not state.host_id.strip() or state.transition_state != "stable"
                    or state.transition_id is not None):
                self.close()
                raise StoreUnavailable("initial anchor state is not stable")
        elif state != self._anchor_state:
            self.close()
            raise StoreUnavailable("anchor changed outside the active transition")
        self._anchor_state = state
        self._grant_read_verified = True
        return state

    def write(self, state: AnchorState) -> None:
        grant_id = self._require_grant()
        if type(state) is not AnchorState or self._anchor_state is None:
            raise StoreUnavailable("anchor write requires a verified prior read")
        current = self._anchor_state
        if current.transition_state == "stable":
            if (state.transition_state != "pending" or not state.transition_id
                    or state.anchor_version != current.anchor_version
                    or state.host_id != current.host_id):
                raise StoreUnavailable("invalid pending anchor transition")
            if self._grant_operation == "authority.mutate":
                valid = (state.host_generation == current.host_generation + 1
                         and state.login_counter == current.login_counter)
                step = "global_pending"
            elif self._grant_operation == "session.login":
                valid = (state.host_generation == current.host_generation
                         and state.login_counter == current.login_counter + 1)
                step = "login_pending"
            else:
                valid = False
                step = ""
            if not valid:
                raise StoreUnavailable("anchor transition does not match the granted operation")
        elif current.transition_state == "pending":
            valid = (
                self._grant_operation in {"authority.mutate", "session.login"}
                and state.anchor_version == current.anchor_version
                and state.host_id == current.host_id
                and state.host_generation == current.host_generation
                and state.login_counter == current.login_counter
                and current.transition_id is not None
                and state.transition_state == "stable"
                and state.transition_id is None
            )
            if not valid:
                raise StoreUnavailable("invalid stable anchor finalization")
            step = "global_stable" if self._grant_operation == "authority.mutate" else "login_stable"
        else:
            raise StoreUnavailable("unknown anchor transition state")
        payload = self._request("child.anchor.advance", {
            "grant_id": grant_id, "step": step, "state": _state_to_wire(state),
        }, "owner.anchor.verified")
        if (payload.keys() != {"grant_id", "state"} or payload["grant_id"] != grant_id
                or _state_from_wire(payload["state"]) != state):
            self.close()
            raise ChannelProtocolError("anchor write did not verify")
        self._anchor_state = state

    def _require_grant(self) -> str:
        grant_id = self._grant_id
        thread_id = threading.get_ident()
        if (grant_id is None or self._closed
                or self._grant_owner_thread != thread_id
                or getattr(self._scope_local, "thread_id", None) != thread_id
                or getattr(self._scope_local, "operation", None) != self._grant_operation
                or getattr(self._scope_local, "grant_count", 0) != 1):
            raise StoreUnavailable("active authority grant required")
        return grant_id

    def _require_operation_context(self) -> str:
        operation = getattr(self._scope_local, "operation", None)
        thread_id = threading.get_ident()
        if (operation not in self.operations
                or getattr(self._scope_local, "thread_id", None) != thread_id
                or not self._scope_lock.locked()):
            raise StoreUnavailable("active store operation context required")
        return operation

    def wait_for_shutdown(self) -> None:
        if self._grant_id is not None:
            raise StoreUnavailable("cannot shut down with an active grant")
        frame = self._receive()
        if (frame["kind"] != "owner.shutdown"
                or frame["payload"] != {"reason": "requested"}):
            self.close()
            raise ChannelProtocolError("invalid shutdown request")
        self._send("child.shutdown_ack", {}, correlation_id=frame["correlation_id"])
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._socket.close()
        except OSError:
            pass

    @property
    def is_closed(self) -> bool:
        """Expose terminal channel state to the owning process coordinator."""
        return self._closed


class NativeProtectedAnchorV2(NativeProtectedAnchor):
    """Strict v2 authority channel used by the offline service composition."""
    protocol = PROTOCOL_V2
    version = VERSION_V2
    operations = OPERATIONS | frozenset({"service.authorize", "service.commit"})
    service_authority = True

    @contextlib.contextmanager
    def service_commit(self):
        with self._operation_context("service.commit", method="serialized_authority"):
            yield

    @contextlib.contextmanager
    def service_authorize(self, method: str):
        if method not in {"current_binding", "binding_current"}:
            raise StoreUnavailable("service authorization method is not allowlisted")
        with self._operation_context("service.authorize", method=method):
            yield


_METHOD_OPERATIONS = {
    "store.read": frozenset({"status"}),
    "session.login": frozenset({"login"}),
    "session.signout": frozenset({"revoke_session"}),
    "authority.mutate": frozenset({
        "advance_host_generation", "revoke_grant", "update_grant_scopes",
        "revoke_device", "replace_device_credential",
    }),
    "ticket.issue": frozenset({"issue_ticket"}),
    "ticket.consume": frozenset({"consume_ticket"}),
}


def open_store(factory: Callable[..., PhoneAdmissionStore], *args: Any,
               anchor: NativeProtectedAnchor, **kwargs: Any) -> PhoneAdmissionStore:
    """Construct exactly the existing store inside the `store.open` grant."""
    if (factory is not PhoneAdmissionStore or type(anchor) not in {NativeProtectedAnchor, NativeProtectedAnchorV2}
            or len(args) != 1 or type(args[0]) is not sqlite3.Connection
            or set(kwargs) - {"failpoint", "process_epoch"} or args[0].in_transaction):
        raise StoreUnavailable("unsupported store construction")
    connection = args[0]
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if not AUTHORITY_TABLES.issubset(tables):
        raise StoreUnavailable("preprovisioned authority schema required")
    if connection.execute("SELECT singleton_id FROM phone_remote_meta WHERE singleton_id=1").fetchone() is None:
        raise StoreUnavailable("preprovisioned authority metadata required")
    with anchor._operation_context("store.open"):
        store = factory(*args, anchor=anchor, **kwargs)
    return store


def run_store_operation(operation: str, method: Callable[..., Any], *args: Any,
                        anchor: NativeProtectedAnchor, **kwargs: Any) -> Any:
    """Run one allowlisted bound store method under its explicit operation grant."""
    if type(method) is not types.MethodType:
        raise StoreUnavailable("store method does not match operation")
    method_name = method.__name__
    method_owner = method.__self__
    method_function = method.__func__
    class_function = getattr(PhoneAdmissionStore, method_name, None)
    v2 = type(anchor) is NativeProtectedAnchorV2
    method_map = dict(_METHOD_OPERATIONS)
    if v2:
        method_map["service.authorize"] = frozenset({"current_binding", "binding_current"})
        method_map["service.commit"] = frozenset()
    if (operation not in method_map
            or method_name not in method_map[operation]
            or type(method_owner) is not PhoneAdmissionStore
            or method_function is not class_function
            or type(anchor) not in {NativeProtectedAnchor, NativeProtectedAnchorV2}
            or method_owner.anchor is not anchor):
        raise StoreUnavailable("store method does not match operation")
    with anchor._operation_context(operation, method=method_name if v2 else None):
        result = method(*args, **kwargs)
        if (v2 and operation == "service.authorize" and method_name == "binding_current"
                and result is False):
            # This exact store method can reject malformed immutable bindings
            # before opening its authority guard. No other zero-grant result is
            # accepted by the v2 operation context.
            anchor._scope_local.allow_zero_grant_false = True
    return result
