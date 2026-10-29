"""Store-backed, in-process synthetic facade; no listener or real media."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass

from jarvis.bot.phone_admission_store import PhoneAdmissionStore, SessionBinding, StoreDenied, StoreUnavailable
from jarvis.bot.phone_remote_protocol import OPERATIONS, ProtocolError, parse_request, response


@dataclass(frozen=True)
class TrustedRequestContext:
    """Server-injected values; none are populated from the JSON request."""
    identity: object
    owner_id: str
    session_id: str
    device_id: str
    login_incarnation: str
    ticket_id: str | None = None


class FakeContextVerifier:
    """Explicit test verifier. Production verification is intentionally absent."""
    def verify(self, context):
        return type(context) is TrustedRequestContext and bool(
            getattr(context.identity, "user_id", None) == context.owner_id
            and context.session_id and context.device_id and context.login_incarnation)


class FakeMediaAdapter:
    def __init__(self):
        self.peers = {}

    def prepare(self, sdp, peer_id=None):
        peer = peer_id or uuid.uuid4().hex
        if peer_id is not None and peer_id not in self.peers:
            raise RuntimeError("peer unavailable")
        answer = "v=0\r\no=fake 1 1 IN IP4 127.0.0.1\r\ns=fake\r\nt=0 0\r\n"
        # Keep media content out of the fake adapter's persistent state.
        self.peers[peer] = True
        return peer, answer

    def close(self, peer_id):
        self.peers.pop(peer_id, None)


class PhoneRemoteService:
    def __init__(self, store: PhoneAdmissionStore, verifier, media, *, enabled=True,
                 owner_available=lambda _owner: True, clock=time.monotonic,
                 ledger_per_binding=256, ledger_total=4096):
        self.store, self.verifier, self.media = store, verifier, media
        self.enabled, self.owner_available, self.clock = enabled, owner_available, clock
        self.ledger_per_binding, self.ledger_total = ledger_per_binding, ledger_total
        self._lock = threading.RLock()
        self._ledger = {}
        self._peers = {}
        self._owner_lease = {}
        self._peer_last_check = {}

    @staticmethod
    def _binding_key(binding):
        return (binding.owner_id, binding.device_id, binding.grant_id, binding.session_id,
                binding.login_incarnation, binding.host_id, binding.host_generation,
                binding.grant_generation, binding.session_generation, binding.process_epoch,
                tuple(sorted(binding.scopes)))

    def _valid_context(self, context):
        return type(context) is TrustedRequestContext and self.verifier.verify(context)

    def _finish(self, key, receipt):
        with self._lock:
            self._ledger[key].update(state="done", receipt=receipt)
        return receipt

    def _serve(self, request, context):
        op, rid, payload = request["operation"], request["request_id"], request["payload"]
        if not self.enabled:
            return response(rid, "unavailable", "feature_off")
        if op in {"results.snapshot", "results.resume", "call.state", "call.answer", "call.decline"}:
            return response(rid, "unavailable", "operation_unavailable")
        if not self._valid_context(context):
            return response(rid, "denied", "not_authorized")
        if not self.owner_available(context.owner_id):
            return response(rid, "unavailable", "owner_busy")
        # A server handle carries the ticket and the exact login incarnation.
        # Ticket binding is checked and consumed by the store before media prep.
        if op == "session.status":
            try:
                binding = self.store.current_binding(identity=context.identity,
                    owner_id=context.owner_id, session_id=context.session_id,
                    device_id=context.device_id, login_incarnation=context.login_incarnation,
                    now=self.clock())
                if "read" not in binding.scopes:
                    return response(rid, "denied", "not_authorized")
            except StoreUnavailable:
                return response(rid, "unavailable", "authority_unavailable")
            except StoreDenied:
                return response(rid, "denied", "not_authorized")
            return response(rid, "ok", "none", {"readiness": "ready"})
        if op == "voice.end":
            peer_id = payload["peer_id"]
            try:
                current = self.store.current_binding(identity=context.identity,
                    owner_id=context.owner_id, session_id=context.session_id,
                    device_id=context.device_id, login_incarnation=context.login_incarnation,
                    now=self.clock())
            except StoreUnavailable:
                return response(rid, "unavailable", "authority_unavailable")
            except StoreDenied:
                return response(rid, "denied", "not_authorized")
            with self._lock:
                item = self._peers.get(peer_id)
                if item is None:
                    return response(rid, "ok", "none", {"peer_id": peer_id, "ended": True})
                binding = item["binding"]
                if binding != current:
                    return response(rid, "denied", "not_authorized")
            if not self.store.binding_current(binding, now=self.clock()):
                return response(rid, "denied", "not_authorized")
            if (binding.owner_id, binding.device_id, binding.login_incarnation) != (
                    context.owner_id, context.device_id, context.login_incarnation):
                return response(rid, "denied", "not_authorized")
            with self.store.serialized_authority():
                if not self.store.binding_current_serialized(binding, now=self.clock()):
                    return response(rid, "denied", "not_authorized")
                with self._lock:
                    item = self._peers.pop(peer_id, None)
                    self._owner_lease.pop(binding.owner_id, None)
                    self._peer_last_check.pop(peer_id, None)
            if item:
                self.media.close(peer_id)
            return response(rid, "ok", "none", {"peer_id": peer_id, "ended": True})
        if op not in {"voice.offer", "voice.update"}:
            return response(rid, "unavailable", "operation_unavailable")
        if not context.ticket_id:
            return response(rid, "denied", "not_authorized")
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        try:
            binding = self.store.current_binding(identity=context.identity,
                owner_id=context.owner_id, session_id=context.session_id,
                device_id=context.device_id, login_incarnation=context.login_incarnation,
                now=self.clock())
        except (StoreDenied, StoreUnavailable):
            return response(rid, "unavailable", "authority_unavailable")
        key = (self._binding_key(binding), rid)
        with self._lock:
            old = self._ledger.get(key)
            if old is None:
                active = sum(1 for k in self._ledger if k[0] == key[0])
                if active >= self.ledger_per_binding or len(self._ledger) >= self.ledger_total:
                    return response(rid, "denied", "request_capacity")
                self._ledger[key] = {"digest": digest, "state": "in_flight", "receipt": None}
        if old is not None:
            if old["digest"] != digest or old["state"] == "in_flight":
                return response(rid, "denied", "request_conflict")
            return old["receipt"] if self.store.binding_current(binding, now=self.clock()) else response(rid, "denied", "not_authorized")
        if op == "voice.update":
            with self._lock:
                existing = self._peers.get(payload["peer_id"])
                if existing is None or existing["binding"] != binding:
                    receipt = response(rid, "denied", "not_authorized")
                    return self._finish(key, receipt)
        try:
            consumed = self.store.consume_ticket(identity=context.identity,
                ticket_id=context.ticket_id, session_id=context.session_id,
                owner_id=context.owner_id, purpose="update" if op == "voice.update" else "offer",
                payload_digest=hashlib.sha256(payload["sdp"].encode()).hexdigest(),
                now=self.clock(), peer_id=payload.get("peer_id"))
            if consumed != binding:
                raise StoreDenied("binding changed")
        except (StoreDenied, StoreUnavailable):
            receipt = response(rid, "denied", "not_authorized")
            return self._finish(key, receipt)
        if not self.store.binding_current(binding, now=self.clock()):
            receipt = response(rid, "denied", "not_authorized")
            return self._finish(key, receipt)
        with self._lock:
            lease = self._owner_lease.get(binding.owner_id)
            if op == "voice.offer" and lease and lease in self._peers:
                receipt = response(rid, "unavailable", "owner_busy")
                return self._finish(key, receipt)
        try:
            # This is deliberately outside the authority guard.
            peer_id, answer = self.media.prepare(payload["sdp"],
                payload.get("peer_id") if op == "voice.update" else None)
        except Exception:
            receipt = response(rid, "unavailable", "voice_not_ready")
            return self._finish(key, receipt)
        try:
            with self.store.serialized_authority():
                if not self.store.binding_current_serialized(binding, now=self.clock()):
                    raise StoreDenied("authority changed")
                with self._lock:
                    self._peers[peer_id] = {"binding": binding, "context": context}
                    self._owner_lease[binding.owner_id] = peer_id
                    self._peer_last_check[peer_id] = self.clock()
        except (StoreDenied, StoreUnavailable):
            self.media.close(peer_id)
            receipt = response(rid, "denied", "not_authorized")
            return self._finish(key, receipt)
        receipt = response(rid, "ok", "none", {"peer_id": peer_id, "sdp": answer})
        return self._finish(key, receipt)

    def tick(self):
        """Fake-clock sweep: close stale peers within the five-second bound."""
        now = self.clock()
        with self._lock:
            peers = list(self._peers.items())
        stale = []
        for peer_id, item in peers:
            last = self._peer_last_check.get(peer_id, now)
            if now - last < 5.0:
                continue
            binding = item["binding"]
            if not self.store.binding_current(binding, now=now):
                stale.append(peer_id)
            else:
                self._peer_last_check[peer_id] = now
        for peer_id in stale:
            with self._lock:
                item = self._peers.pop(peer_id, None)
                self._peer_last_check.pop(peer_id, None)
                if item:
                    self._owner_lease.pop(item["binding"].owner_id, None)
            if item:
                self.media.close(peer_id)
        return len(stale)

    def notify_revocation(self):
        """Explicit in-process notification hook; callbacks occur outside store locks."""
        with self._lock:
            peers = list(self._peers.items())
        for peer_id, item in peers:
            if not self.store.binding_current(item["binding"], now=self.clock()):
                with self._lock:
                    self._peers.pop(peer_id, None)
                    self._peer_last_check.pop(peer_id, None)
                    self._owner_lease.pop(item["binding"].owner_id, None)
                self.media.close(peer_id)

    def handle(self, raw, context):
        try:
            request = parse_request(raw)
        except ProtocolError as error:
            return response(error.request_id, error.status, error.reason)
        try:
            return self._serve(request, context)
        except Exception:
            # Never leak exception messages or adapter/authority internals.
            return response(request["request_id"], "unavailable", "authority_unavailable")
