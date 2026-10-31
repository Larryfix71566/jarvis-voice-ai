"""Owner-controlled, disposable proof-to-connection composition. Never mounted.

Opaque capabilities stay in the inherited-channel child. This is not production
controller authentication, enrollment, a bearer token API, or a network server.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import binascii
import json
import threading
import time
from dataclasses import dataclass, field

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import StoreDenied, StoreUnavailable
from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV4, run_store_operation
from jarvis.bot.phone_remote_login import (
    LoginClockGate, LoginFailure, PhoneRemoteLogin, _VerifiedLoginAdmission,
    _decode_challenge_id, MAX_SAFE_INTEGER,
)
from jarvis.bot.phone_remote_protocol import encode_response, parse_request, ProtocolError, response

CONNECTION_PROTOCOL = "mortimer.phone-connection.v1"
HANDSHAKE_OPERATIONS = frozenset({"auth.challenge", "auth.prove"})
MAX_FRAME_BYTES = 8192
MAX_CONNECTIONS = 64
HANDSHAKE_TTL_MS = 60_000
_CONNECTION_CONSTRUCTION = object()
_PREAUTH = frozenset({"opened", "challenging", "challenged", "proving", "binding_pending"})


@dataclass(frozen=True)
class ConnectionFailure:
    reason: str = "not_authorized"


class _ConnectionCancelled(StoreDenied):
    """Known local refusal before an authority acquisition was sent."""


class HandshakeError(ValueError):
    def __init__(self, request_id=None):
        self.request_id = request_id
        super().__init__("invalid handshake")


def _text(value, limit=128, *, stripped=False):
    try:
        return (type(value) is str and 0 < len(value.encode("utf-8", "strict")) <= limit
                and (not stripped or value == value.strip()))
    except UnicodeError:
        return False


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("invalid number")


def _depth(value, n=0):
    if n > 4:
        raise ValueError("depth")
    if type(value) is dict:
        for v in value.values():
            _depth(v, n + 1)
    elif type(value) is list:
        for v in value:
            _depth(v, n + 1)


def parse_handshake(raw):
    rid = None
    try:
        if type(raw) is str:
            raw = raw.encode("utf-8", "strict")
        if type(raw) is not bytes or not raw or len(raw) > MAX_FRAME_BYTES or raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("frame")
        obj = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
                         parse_constant=_constant)
        _depth(obj)
        if type(obj) is not dict:
            raise ValueError("envelope")
        if _text(obj.get("request_id")):
            rid = obj["request_id"]
        if (obj.keys() != {"protocol", "request_id", "operation", "payload"}
                or obj["protocol"] != CONNECTION_PROTOCOL or rid is None
                or type(obj["operation"]) is not str or obj["operation"] not in HANDSHAKE_OPERATIONS
                or type(obj["payload"]) is not dict):
            raise ValueError("envelope")
        p = obj["payload"]
        if obj["operation"] == "auth.challenge":
            if p.keys() != {"device_id", "grant_id"} or not all(_text(v, stripped=True) for v in p.values()):
                raise ValueError("selectors")
        else:
            if p.keys() != {"challenge_id", "proof"} or _decode_challenge_id(p["challenge_id"]) is None:
                raise ValueError("proof")
            decode_proof(p["proof"])
        return obj
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise HandshakeError(rid) from None


def is_handshake_attempt(raw):
    """Classify reserved top-level names without accepting a handshake payload.

    Keep duplicate top-level pairs: an invalid duplicate cannot hide an earlier
    reserved protocol/operation. This predicate grants no parsing authority.
    """
    class ObjectPairs(list):
        pass
    try:
        if type(raw) is str:
            raw = raw.encode("utf-8", "strict")
        if type(raw) is not bytes or not raw or len(raw) > 1_048_576:
            return False
        obj = json.loads(raw.decode("utf-8-sig", "strict"), object_pairs_hook=ObjectPairs)
        if type(obj) is not ObjectPairs:
            return False
        return any((key == "protocol" and value == CONNECTION_PROTOCOL)
            or (key == "operation" and type(value) is str and value.startswith("auth."))
            for key, value in obj)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return False


def decode_proof(value):
    if type(value) is not str or not 1 <= len(value) <= 5462:
        raise ValueError("proof")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("proof") from None
    if not 1 <= len(raw) <= 4096 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise ValueError("proof")
    return raw


def handshake_response(request_id, *, payload=None, reason=None):
    if request_id is not None and not _text(request_id):
        raise ValueError("request id")
    if reason is None:
        if request_id is None or type(payload) is not dict:
            raise ValueError("success")
        if payload.keys() == {"authenticated", "expires_at_ms"}:
            if payload["authenticated"] is not True or type(payload["expires_at_ms"]) is not int or not 1 <= payload["expires_at_ms"] <= MAX_SAFE_INTEGER:
                raise ValueError("authentication result")
        elif payload.keys() == {"protocol", "purpose", "challenge_id", "challenge_nonce", "service_id", "host_id", "enrolled_key_id", "authority_generation", "expires_at_ms"}:
            from jarvis.bot.phone_remote_auth_proof import PROTOCOL, PURPOSE, MAX_AUTHORITY_GENERATION
            if (payload["protocol"] != PROTOCOL or payload["purpose"] != PURPOSE
                    or _decode_challenge_id(payload["challenge_id"]) is None
                    or type(payload["authority_generation"]) is not int
                    or not 1 <= payload["authority_generation"] <= MAX_AUTHORITY_GENERATION
                    or type(payload["expires_at_ms"]) is not int
                    or not 1 <= payload["expires_at_ms"] <= MAX_SAFE_INTEGER):
                raise ValueError("challenge result")
            for name in ("service_id", "host_id", "enrolled_key_id"):
                value = payload[name]
                if not _text(value) or not value.isascii() or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-" for c in value):
                    raise ValueError("challenge identity")
            nonce = payload["challenge_nonce"]
            if type(nonce) is not str or len(nonce) != 43:
                raise ValueError("challenge nonce")
            decoded = base64.b64decode(nonce + "=", altchars=b"-_", validate=True)
            if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode() != nonce:
                raise ValueError("challenge nonce")
        else:
            raise ValueError("result schema")
        status, code = "ok", "none"
    else:
        if reason not in {"invalid_request", "not_authorized", "capacity", "authority_unavailable"}:
            raise ValueError("reason")
        status = "denied" if reason in {"invalid_request", "not_authorized"} else "unavailable"
        code, payload = reason, {}
    return json.dumps(dict(protocol=CONNECTION_PROTOCOL, request_id=request_id,
        status=status, reason=code, payload=payload), separators=(",", ":"), allow_nan=False)


def _failure(value):
    if type(value) is LoginFailure:
        return ConnectionFailure("capacity" if value.code == "capacity" else
            "authority_unavailable" if value.code in {"busy", "unavailable"} else "not_authorized")
    return value


class ConnectionClock:
    """Paired fixture clock. Services read the coherent image under F, never L."""
    def __init__(self, *, wall_ms=1_800_000_000_000, monotonic_ms=1000):
        from jarvis.bot.phone_remote_service import FakeClockGate
        self.login = LoginClockGate(wall_ms=wall_ms, monotonic_ms=monotonic_ms)
        self.service = FakeClockGate(wall_ms / 1000)
        self._login_gate, self._service_gate = self.login, self.service
        self._failed = False
        self.login._connection_clock = self.service._connection_clock = self
        self._image = (wall_ms, monotonic_ms, self.service._version)
        self.set_time(wall_ms=wall_ms, monotonic_ms=monotonic_ms)

    def set_time(self, *, wall_ms, monotonic_ms):
        if any(type(v) is not int or not 0 <= v <= MAX_SAFE_INTEGER for v in (wall_ms, monotonic_ms)):
            raise TypeError("invalid paired clock")
        # Never called by a service commit or an injected callback.
        if self._service_gate._lock._is_owned():
            raise StoreUnavailable("clock update from a service guard")
        with self._login_gate._lock, self._service_gate._lock:
            self.image_locked()
            if monotonic_ms < self._image[1]:
                raise ValueError("monotonic clock rollback")
            self.login._wall_ms, self.login._monotonic_ms = wall_ms, monotonic_ms
            self.service._now = wall_ms / 1000
            self.service._version += 1
            self._image = (wall_ms, monotonic_ms, self.service._version)

    def image_locked(self):
        if not self._service_gate._lock._is_owned():
            raise StoreUnavailable("proof clock guard absent")
        wall, mono, version = self._image
        if (self._failed or self.login is not self._login_gate or self.service is not self._service_gate
                or self.login._connection_clock is not self or self.service._connection_clock is not self
                or self.service._version != version or self.service._now != wall / 1000
                or (self.login._wall_ms, self.login._monotonic_ms) != (wall, mono)):
            self._failed = True
            raise StoreUnavailable("proof clock image inconsistent")
        return wall, mono

    def check_login_entry(self, gate):
        # Reject an accidental service F→login L call before touching L.
        # Reentrant use that already owns L retains the original L→F order.
        if self._service_gate._lock._is_owned() and not gate._lock._is_owned():
            self._failed = True
            raise StoreUnavailable("paired clock lock order violation")

    @contextmanager
    def login_guard(self, gate):
        if gate is not self._login_gate or not gate._lock._is_owned():
            raise StoreUnavailable("paired login clock identity unavailable")
        with self._service_gate._lock:
            yield self.image_locked()

    def reject_login_write(self, gate):
        with self._service_gate._lock:
            self._failed = True
        raise StoreUnavailable("paired login clock requires controller update")

    def reject_service_write(self, gate):
        # Called under F; never take L from this path.
        self._failed = True
        raise StoreUnavailable("paired service clock requires controller update")

    def snapshot(self):
        with self._service_gate._lock:
            return self.image_locked()


class ConnectionLease:
    __slots__ = ()
    def __repr__(self):
        return "ConnectionLease(<redacted>)"


class ConnectionReply:
    __slots__ = ("_encoded", "_success")
    def __init__(self, encoded, success):
        self._encoded, self._success = encoded, success
    def __repr__(self):
        return "ConnectionReply(<redacted>)"


@dataclass(eq=False, repr=False)
class _Record:
    lease: ConnectionLease
    token: object
    handshake_deadline: int
    real_deadline: float
    epoch: object = field(default_factory=object)
    state: str = "opened"
    challenge_id: str | None = None
    admission: object = None
    binding: object = None
    context: object = None
    expires_at_ms: int = 0
    monotonic_deadline_ms: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    in_flight: int = 0
    pending_sends: int = 0
    reply: object = None


@dataclass(frozen=True, repr=False)
class _Permit:
    record: _Record
    completion: object
    context: object
    binding: object
    wall_deadline: int
    mono_deadline: int


class ProofContextVerifier:
    def __init__(self, registry, capability):
        if capability is not _CONNECTION_CONSTRUCTION or type(registry) is not ConnectionRegistry:
            raise TypeError("unsupported proof verifier")
        self.registry = registry

    def verify(self, context):
        r = self.registry
        permit = r.permit
        if (permit is None or permit.completion is not r.host._current
                or threading.current_thread() is not r.host._thread
                or context is not permit.context):
            return False
        with r.lock:
            return (r.records.get(permit.record.lease) is permit.record
                    and (permit.record.state == "active" or permit.completion.authorized))

    def binding_matches(self, binding):
        return self.registry.permit is not None and binding == self.registry.permit.binding

    def lifetime_locked(self):
        p = self.registry.permit
        if p is None or p.completion is not self.registry.host._current:
            raise StoreUnavailable("proof request permit absent")
        wall, mono = self.registry.clock.image_locked()
        return wall < p.wall_deadline and mono < p.mono_deadline


class ConnectionRegistry:
    def __init__(self, host, clock, capability):
        if capability is not _CONNECTION_CONSTRUCTION or type(clock) is not ConnectionClock:
            raise TypeError("unsupported connection registry")
        self.host, self.clock = host, clock
        self.lock = threading.RLock()
        self.records = {}
        self._retired = []
        self._sends_drained = threading.Event()
        self._sends_drained.set()
        self.service = self.store = self.login = None
        self.permit = None
        self.verifier = ProofContextVerifier(self, capability)

    def attach(self, service, store, login):
        if (self.service is not None or type(store.anchor) is not NativeProtectedAnchorV4
                or store.anchor is not self.host._anchor or type(login) is not PhoneRemoteLogin
                or login._store is not store or login._anchor is not store.anchor
                or service.verifier is not self.verifier or service.clock is not self.clock.service):
            raise TypeError("connection ownership mismatch")
        self.service, self.store, self.login = service, store, login

    def _get(self, lease, token):
        record = self.records.get(lease) if type(lease) is ConnectionLease else None
        return record if record is not None and type(token) is object and record.token is token else None

    def _retire_locked(self, record):
        record.state = "retiring"
        record.epoch = None
        record.cancel.set()
        record.reply = None
        if record.in_flight == 0 and record.pending_sends == 0:
            record.state = "closed"
            self.records.pop(record.lease, None)
            if record.admission is not None or record.challenge_id is not None:
                self._retired.append((record.admission, record.challenge_id))
                record.admission = record.challenge_id = None

    def _cleanup(self, *, blocking=True):
        # Only the owner worker may wait for the login lock. Local close
        # opportunistically retires idle seals without blocking the event loop.
        with self.lock:
            retired, self._retired = self._retired, []
        if not retired:
            return
        # Local close must never block the event-loop behind proof execution.
        # Capture C then release it; take L alone, or defer to the owned worker.
        if not self.login._retire_connection_seals(retired, blocking=blocking):
            with self.lock:
                self._retired[:0] = retired

    def open(self, token):
        if type(token) is not object:
            return ConnectionFailure()
        wall, mono = self.clock.snapshot()
        with self.host._lock, self.lock:
            for old in tuple(self.records.values()):
                expired = (old.state == "active" and
                    (wall >= old.expires_at_ms or mono >= old.monotonic_deadline_ms))
                expired = expired or (old.state in _PREAUTH and
                    (mono >= old.handshake_deadline or time.monotonic() >= old.real_deadline))
                if expired:
                    self._retire_locked(old)
            if self.host._closed or self.host._fenced or self.host._quiescing or not self.host._proof_enabled:
                return ConnectionFailure("authority_unavailable")
            if len(self.records) >= MAX_CONNECTIONS:
                return ConnectionFailure("capacity")
            if any(r.token is token for r in self.records.values()):
                return ConnectionFailure()
            lease = ConnectionLease()
            self.records[lease] = _Record(lease, token, mono + HANDSHAKE_TTL_MS,
                                          time.monotonic() + HANDSHAKE_TTL_MS / 1000)
            return lease

    def timer(self, lease, token):
        with self.lock:
            r = self._get(lease, token)
            return (r.epoch, r.real_deadline) if r is not None else (None, 0)

    def expire_handshake(self, lease, token, epoch):
        with self.lock:
            r = self._get(lease, token)
            if r is not None and epoch is not None and r.epoch is epoch and r.state in _PREAUTH:
                self._retire_locked(r)
                return True
            return False

    def close(self, lease, token):
        with self.lock:
            r = self._get(lease, token)
            if r is not None:
                self._retire_locked(r)
        self._cleanup(blocking=False)

    def close_all(self):
        with self.lock:
            for r in tuple(self.records.values()):
                self._retire_locked(r)

    def begin_send(self, lease, token):
        # Serialize with terminal host admission before retaining a send. The
        # worker publishes _closed before _drained, then cleans the registry;
        # that cleanup gap must not admit new application sends.
        with self.host._lock, self.lock:
            if self.host._closed or self.host._fenced or not self.host._proof_enabled:
                return False
            r = self._get(lease, token)
            if r is None or r.state in {"retiring", "closed"} or r.cancel.is_set():
                return False
            if r.pending_sends:
                raise StoreUnavailable("overlapping connection send")
            r.pending_sends = 1
            self._sends_drained.clear()
            return r.cancel

    def end_send(self, lease, token):
        with self.lock:
            r = self._get(lease, token)
            if r is None or r.pending_sends != 1:
                raise StoreUnavailable("connection send ownership unavailable")
            r.pending_sends = 0
            if not any(record.pending_sends for record in self.records.values()):
                self._sends_drained.set()
            if r.state in {"retiring", "closed"}:
                self._retire_locked(r)
        self._cleanup(blocking=False)

    def cancel_event(self, lease, token):
        with self.lock:
            r = self._get(lease, token)
            return r.cancel if r is not None and r.state not in {"retiring", "closed"} else None

    def _preauth_current(self, r):
        _, mono = self.clock.snapshot()
        return mono < r.handshake_deadline and time.monotonic() < r.real_deadline and not r.cancel.is_set()

    def _seal(self, r, encoded, success):
        reply = ConnectionReply(encoded, success)
        with self.lock:
            if self.records.get(r.lease) is not r or r.state != "active" or r.cancel.is_set():
                return ConnectionFailure()
            r.reply = (reply, encoded, success)
        return reply

    def claim(self, lease, token, reply):
        with self.clock.service._lock:
            wall, mono = self.clock.image_locked()
            with self.host._lock, self.lock:
                r = self._get(lease, token)
                if (r is None or r.state != "active" or type(reply) is not ConnectionReply
                        or r.reply is None or r.reply[0] is not reply
                        or r.reply[1:] != (reply._encoded, reply._success)):
                    return ConnectionFailure()
                r.reply = None
                if self.host._fenced or self.host._closed or not self.host._proof_enabled:
                    self._retire_locked(r)
                    return ConnectionFailure("authority_unavailable")
                if r.cancel.is_set() or wall >= r.expires_at_ms or mono >= r.monotonic_deadline_ms:
                    self._retire_locked(r)
                    return ConnectionFailure()
                return reply._encoded

    def invoke(self, method, lease, token, *args):
        self._cleanup()
        with self.lock:
            r = self._get(lease, token)
            if r is None or r.state in {"retiring", "closed"} or r.cancel.is_set():
                return ConnectionFailure()
            completion = self.host._current
            if completion is None or getattr(completion, "connection_record", None) is not None:
                self._retire_locked(r)
                raise StoreUnavailable("reentrant connection dispatch")
            completion.connection_record = r
            r.in_flight += 1
        try:
            if method != "handle_connection" and not self._preauth_current(r):
                self.close(lease, token)
                return ConnectionFailure("authority_unavailable")
            result = getattr(self, "_" + method)(r, *args)
            if type(result) is ConnectionFailure:
                self.close(lease, token)
            return result
        finally:
            self.permit = None

    def finish_owned(self, completion):
        # Run after host terminal/result bookkeeping, before worker_finished.
        # A caller's earlier cancellation cannot release this registry capacity.
        with self.lock:
            r = getattr(completion, "connection_record", None)
            if r is not None:
                completion.connection_record = None
                r.in_flight -= 1
                if r.state in {"retiring", "closed"}:
                    self._retire_locked(r)
        self._cleanup()

    def _connection_challenge(self, r, device_id, grant_id):
        with self.lock:
            if r.state != "opened":
                return ConnectionFailure("invalid_request")
            r.state = "challenging"
        if not all(_text(x, stripped=True) for x in (device_id, grant_id)):
            return ConnectionFailure("invalid_request")
        result = _failure(self.login.issue_challenge(device_id=device_id, grant_id=grant_id))
        if type(result) is ConnectionFailure:
            return result
        current = self._preauth_current(r)
        with self.lock:
            r.challenge_id = result.challenge_id
            if not current or r.cancel.is_set() or r.state != "challenging":
                return ConnectionFailure()
            r.state = "challenged"
        return result

    def _connection_prove(self, r, challenge_id, proof_bytes):
        with self.lock:
            if r.state != "challenged" or challenge_id != r.challenge_id:
                return ConnectionFailure()
            r.state = "proving"
        admission = _failure(self.login._complete_for_connection(
            challenge_id=challenge_id, proof_bytes=proof_bytes))
        if type(admission) is ConnectionFailure:
            return admission
        if type(admission) is not _VerifiedLoginAdmission:
            raise StoreUnavailable("proof admission malformed")
        with self.lock:
            r.admission = admission
            if r.cancel.is_set() or r.state != "proving":
                return ConnectionFailure()
            r.state = "binding_pending"
        return True

    def _activate_connection(self, r, request_id):
        from jarvis.bot.phone_remote_service import TrustedRequestContext
        with self.lock:
            admission = r.admission
            if r.state != "binding_pending" or not _text(request_id):
                return ConnectionFailure()
        if not self.login._consume_admission(admission):
            return ConnectionFailure()
        identity = ClientIdentity(name="phone-auth-proof", user_id=admission.owner_id)
        with self.service.owner_available.commit_guard(admission.owner_id) as (ready, _):
            with self.clock.service.commit_guard():
                wall, mono = self.clock.image_locked()
                if wall >= admission.expires_at_ms or mono >= admission.monotonic_deadline_ms:
                    return ConnectionFailure()
                try:
                    binding = run_store_operation("service.authorize", self.store.current_binding,
                        identity=identity, owner_id=admission.owner_id,
                        device_id=admission.device_id, session_id=admission.session_id,
                        login_incarnation=admission.login_incarnation, now=wall / 1000,
                        anchor=self.store.anchor)
                except StoreDenied:
                    return ConnectionFailure()
                if any(getattr(binding, k) != getattr(admission, k) for k in (
                        "owner_id", "device_id", "grant_id", "session_id", "login_incarnation",
                        "host_id", "host_generation", "grant_generation", "scopes")):
                    return ConnectionFailure()
                with self.host._lock, self.lock:
                    if (not ready or self.host._closed or self.host._fenced or self.host._quiescing
                            or not self.host._proof_enabled or r.cancel.is_set()
                            or r.state != "binding_pending" or mono >= r.handshake_deadline
                            or time.monotonic() >= r.real_deadline):
                        return ConnectionFailure()
                    r.binding = binding
                    r.context = TrustedRequestContext(identity, binding.owner_id, binding.session_id,
                        binding.device_id, binding.login_incarnation)
                    r.expires_at_ms = admission.expires_at_ms
                    r.monotonic_deadline_ms = admission.monotonic_deadline_ms
                    r.state, r.epoch, r.admission = "active", None, None
        return self._seal(r, handshake_response(request_id, payload={"authenticated": True,
            "expires_at_ms": r.expires_at_ms}), True)

    def _handle_connection(self, r, raw):
        with self.lock:
            if r.state != "active":
                return ConnectionFailure()
            self.permit = _Permit(r, self.host._current, r.context, r.binding,
                                  r.expires_at_ms, r.monotonic_deadline_ms)
        try:
            request = parse_request(raw)
        except ProtocolError as exc:
            return self._seal(r, encode_response(response(exc.request_id, exc.status, exc.reason)), False)
        if request["operation"] in {"voice.offer", "voice.update"}:
            result = response(request["request_id"], "denied", "not_authorized")
        else:
            result = self.service.handle(raw, r.context)
            if result.get("reason") == "not_authorized":
                return ConnectionFailure()
        encoded = encode_response(result, operation=request["operation"])
        return self._seal(r, encoded, result["status"] == "ok")


def create_offline_connection_host(database_path, *, enabled=False, clock=None,
                                   results=None, actions=(), **fixture_options):
    """Explicit synthetic composition; no credentials, socket listener or real data."""
    from jarvis.bot.phone_remote_service import _AuthorityChildServiceHost, FakeContextVerifier, FakeMediaAdapter
    if type(enabled) is not bool or (clock is not None and type(clock) is not ConnectionClock):
        raise TypeError("unsupported connection fixture")
    if any(k not in {"owner_available", "voice_ready", "store_failpoint", "login_service_id"} for k in fixture_options):
        raise TypeError("unsupported connection options")
    return _AuthorityChildServiceHost(database_path, verifier=FakeContextVerifier(),
        media=FakeMediaAdapter(), enabled=enabled, results=results,
        _connection_capability=_CONNECTION_CONSTRUCTION,
        _connection_clock=clock or ConnectionClock(), _connection_actions=actions,
        **fixture_options)
