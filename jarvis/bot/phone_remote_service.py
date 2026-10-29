"""Store-backed, in-process synthetic facade; no listener or real media."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from jarvis.bot.phone_admission_store import PhoneAdmissionStore, StoreDenied, StoreUnavailable
from jarvis.bot.phone_remote_protocol import (ProtocolError, parse_request, response,
    validate_response, validate_success_payload)


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
    """Nonblocking synthetic media backend with attempt-owned abort handles."""
    def __init__(self):
        self.peers = {}
        self._capability = object()
        self._prepared = {}

    def prepare(self, sdp, peer_id=None):
        peer = peer_id or uuid.uuid4().hex
        if peer_id is not None and peer_id not in self.peers:
            raise RuntimeError("peer unavailable")
        answer = "v=0\r\no=fake 1 1 IN IP4 127.0.0.1\r\ns=fake\r\nt=0 0\r\n"
        return self._make_prepared(peer, answer, updating=peer_id is not None)

    def _make_prepared(self, peer_id, answer, *, updating=False):
        resource = self.peers.get(peer_id) if updating else object()
        handle = PreparedMedia(self._capability, object(), peer_id, answer, updating, resource)
        self._prepared[handle.token] = handle
        return handle

    def _replace_prepared(self, prepared, *, peer_id=None, answer=None):
        """Fake-adapter test seam for malformed or aliased adapter replies."""
        if self._prepared.get(prepared.token) is not prepared:
            raise ValueError("preparation is not owned")
        replacement = PreparedMedia(self._capability, prepared.token,
            prepared.peer_id if peer_id is None else peer_id,
            prepared.answer if answer is None else answer, prepared.updating, prepared.resource)
        self._prepared[prepared.token] = replacement
        return replacement

    def abort(self, prepared):
        """Discard only this adapter's still-pending attempt; never close by ID."""
        if (type(prepared) is PreparedMedia and prepared._capability is self._capability
                and self._prepared.get(prepared.token) is prepared):
            self._prepared.pop(prepared.token, None)
            return True
        return False

    def close_resource(self, peer_id, resource):
        """Cleanup by exact prepared resource token, never by peer ID alone."""
        if self.peers.get(peer_id) is resource:
            self.peers.pop(peer_id, None)


@dataclass(frozen=True)
class PreparedMedia:
    _capability: object
    token: object
    peer_id: object
    answer: object
    updating: bool
    resource: object


class FakeOwnerAvailabilityGate:
    """Test-only gate. All transitions use set_available; commit_guard linearizes them."""
    def __init__(self, available=True):
        if type(available) is not bool:
            raise TypeError("availability must be bool")
        self._available = bool(available)
        self._lock = threading.RLock()
        self._version = 0
        self._pause_thread = None
        self._pause_arrived = None
        self._pause_release = None

    def set_available(self, available):
        if type(available) is not bool:
            raise TypeError("availability must be bool")
        with self._lock:
            self._available = available
            self._version += 1

    def snapshot(self, _owner_id):
        with self._lock:
            return self._available, self._version

    def pause_before_commit(self, thread_name, arrived, release):
        """Deterministic race-test seam; pause before locking or reading the gate."""
        self._pause_thread, self._pause_arrived, self._pause_release = thread_name, arrived, release

    @contextmanager
    def commit_guard(self, _owner_id):
        if threading.current_thread().name == self._pause_thread:
            self._pause_arrived.set()
            if not self._pause_release.wait(2):
                raise RuntimeError("availability gate barrier timed out")
        with self._lock:
            yield self._available, self._version


class FakeReadinessGate:
    """Test-only versioned voice readiness gate; mutable state is commit-guarded."""
    def __init__(self, ready=True):
        if type(ready) is not bool:
            raise TypeError("readiness must be bool")
        self._ready = ready
        self._lock = threading.RLock()
        self._version = 0
        self._pause_thread = None
        self._pause_arrived = None
        self._pause_release = None

    def set_ready(self, ready):
        if type(ready) is not bool:
            raise TypeError("readiness must be bool")
        with self._lock:
            self._ready = ready
            self._version += 1

    def snapshot(self):
        with self._lock:
            return self._ready, self._version

    def pause_before_commit(self, thread_name, arrived, release):
        self._pause_thread, self._pause_arrived, self._pause_release = thread_name, arrived, release

    @contextmanager
    def commit_guard(self):
        if threading.current_thread().name == self._pause_thread:
            self._pause_arrived.set()
            if not self._pause_release.wait(2):
                raise RuntimeError("readiness gate barrier timed out")
        with self._lock:
            yield self._ready, self._version


class FakeBoundedSink:
    """Nonblocking synthetic output queue with cancel-before-dequeue semantics."""
    def __init__(self, capacity=64):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._lock = threading.Lock()
        self._queue = []

    def enqueue_nonblocking(self, item):
        with self._lock:
            if len(self._queue) >= self.capacity:
                return False
            self._queue.append(item)
            return True

    def cancel_peer(self, peer_id):
        with self._lock:
            self._queue = [item for item in self._queue if item["peer_id"] != peer_id]

    def clear(self):
        with self._lock:
            self._queue.clear()

    def peek(self):
        with self._lock:
            return self._queue[0] if self._queue else None

    def dequeue(self, expected=None):
        with self._lock:
            if not self._queue or (expected is not None and self._queue[0] is not expected):
                return None
            return self._queue.pop(0)

    def __len__(self):
        with self._lock:
            return len(self._queue)


class PhoneRemoteService:
    def __init__(self, store: PhoneAdmissionStore, verifier, media, *, enabled=True,
                 owner_available=None, clock=time.monotonic,
                 ledger_per_binding=256, ledger_total=4096, output_sink=None,
                 output_policy=None, voice_ready=None):
        self.store, self.verifier, self.media = store, verifier, media
        self.enabled = enabled
        self.owner_available = owner_available if owner_available is not None else FakeOwnerAvailabilityGate()
        if type(self.owner_available) is not FakeOwnerAvailabilityGate:
            raise TypeError("owner availability must use FakeOwnerAvailabilityGate")
        if (type(getattr(media, "peers", None)) is not dict
                or type(getattr(media, "_prepared", None)) is not dict):
            raise TypeError("media adapter must provide synthetic in-memory resource maps")
        self._media_peers = media.peers
        self._media_prepared = media._prepared
        self._media_capability = media._capability
        self.clock = clock
        self.ledger_per_binding, self.ledger_total = ledger_per_binding, ledger_total
        if output_sink is not None and type(output_sink) is not FakeBoundedSink:
            raise TypeError("only the bounded synthetic sink is supported")
        self.output_sink = output_sink if output_sink is not None else FakeBoundedSink()
        self.output_policy = output_policy
        self.voice_ready = voice_ready if voice_ready is not None else FakeReadinessGate()
        if type(self.voice_ready) is not FakeReadinessGate:
            raise TypeError("voice readiness must use FakeReadinessGate")
        self._lock = threading.RLock()
        self._ledger = {}
        self._peers = {}
        self._owner_lease = {}

    @staticmethod
    def _binding_key(binding):
        return (binding.owner_id, binding.device_id, binding.grant_id, binding.session_id,
                binding.login_incarnation, binding.host_id, binding.host_generation,
                binding.grant_generation, binding.session_generation, binding.process_epoch,
                tuple(sorted(binding.scopes)))

    def _valid_context(self, context):
        return type(context) is TrustedRequestContext and self.verifier.verify(context)

    def _owner_ready(self, owner_id):
        try:
            return self.owner_available.snapshot(owner_id)[0] is True
        except Exception:
            return False

    def _activate_prepared_locked(self, prepared):
        """Activate an owned fake resource with plain local dict mutations only.

        Caller holds owner/readiness, store-authority and service locks. No
        adapter method or other injected code runs in this critical section.
        """
        if (type(prepared) is not PreparedMedia
                or prepared._capability is not self._media_capability
                or self._media_prepared.get(prepared.token) is not prepared):
            return False
        if prepared.updating:
            valid = self._media_peers.get(prepared.peer_id) is prepared.resource
        else:
            valid = prepared.peer_id not in self._media_peers
            if valid:
                self._media_peers[prepared.peer_id] = prepared.resource
        if valid:
            self._media_prepared.pop(prepared.token, None)
        return valid

    def _finish(self, key, receipt):
        with self._lock:
            self._ledger[key].update(state="done", receipt=receipt)
        return receipt

    def _reserve_request(self, binding, request):
        key = (self._binding_key(binding), request["request_id"])
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        with self._lock:
            old = self._ledger.get(key)
            if old is None:
                active = sum(1 for candidate in self._ledger if candidate[0] == key[0])
                if active >= self.ledger_per_binding or len(self._ledger) >= self.ledger_total:
                    return key, None, response(request["request_id"], "denied", "request_capacity")
                self._ledger[key] = {"binding": binding, "operation": request["operation"],
                    "version": request["protocol_version"], "digest": digest,
                    "state": "in_flight", "receipt": None}
                return key, digest, None
        if old["operation"] != request["operation"] or old["version"] != request["protocol_version"] or old["digest"] != digest:
            return key, None, response(request["request_id"], "denied", "request_conflict")
        if old["state"] == "in_flight":
            return key, None, response(request["request_id"], "denied", "request_conflict")
        try:
            current = self.store.binding_current(binding, now=self.clock())
        except StoreUnavailable:
            return key, None, response(request["request_id"], "unavailable", "authority_unavailable")
        if not current:
            return key, None, response(request["request_id"], "denied", "not_authorized")
        return key, None, old["receipt"]

    def _revalidate_cached_receipt(self, request, context, binding, receipt):
        operation = request["operation"]
        needs_ready = operation in {"session.status", "voice.offer", "voice.update"}
        # Readiness preparation is outside authority locks. The final state is
        # re-read under its versioned gate after all potentially blocking work.
        self.voice_ready.snapshot() if needs_ready else None
        now = self.clock()
        try:
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                if needs_ready:
                    with self.voice_ready.commit_guard() as (voice_ready, _):
                        with self.store.serialized_authority():
                            return self._cached_receipt_commit(request, binding, receipt, now,
                                owner_ready, voice_ready)
                with self.store.serialized_authority():
                    return self._cached_receipt_commit(request, binding, receipt, now,
                        owner_ready, True)
        except StoreUnavailable:
            return response(request["request_id"], "unavailable", "authority_unavailable")

    def _cached_receipt_commit(self, request, binding, receipt, now, owner_ready, voice_ready):
        operation = request["operation"]
        if not self.enabled:
            return response(request["request_id"], "unavailable", "feature_off")
        if not owner_ready:
            return response(request["request_id"], "unavailable", "owner_busy")
        if not self.store.binding_current_serialized(binding, now=now):
            return response(request["request_id"], "denied", "not_authorized")
        if operation in {"session.status", "voice.offer", "voice.update"}:
            required_scope = "read" if operation == "session.status" else "voice"
            if required_scope not in binding.scopes:
                return response(request["request_id"], "denied", "not_authorized")
            if not voice_ready:
                return response(request["request_id"], "unavailable", "voice_not_ready")
        if receipt["status"] == "ok" and operation in {"voice.offer", "voice.update"}:
            peer_id = receipt["payload"].get("peer_id")
            with self._lock:
                peer = self._peers.get(peer_id)
                if (peer is None or peer["binding"] != binding
                        or self._owner_lease.get(binding.owner_id) != peer_id):
                    return response(request["request_id"], "denied", "not_authorized")
        return receipt

    def _prune_terminal_ledger(self):
        with self._lock:
            entries = [(key, value["binding"]) for key, value in self._ledger.items()
                       if value["state"] == "done"]
        terminal = []
        for key, binding in entries:
            try:
                now = self.clock()
                if self.store.binding_terminal(binding, now=now):
                    terminal.append(key)
            except StoreUnavailable:
                pass
        if terminal:
            with self._lock:
                for key in terminal:
                    self._ledger.pop(key, None)

    def _serve(self, request, context, binding):
        op, rid, payload = request["operation"], request["request_id"], request["payload"]
        if not self.enabled:
            self.tick()
            return response(rid, "unavailable", "feature_off")
        if not self._owner_ready(context.owner_id):
            self.tick()
            return response(rid, "unavailable", "owner_busy")
        if op in {"results.snapshot", "results.resume", "call.state", "call.answer", "call.decline"}:
            return response(rid, "unavailable", "operation_unavailable")
        # A server handle carries the ticket and the exact login incarnation.
        # Ticket binding is checked and consumed by the store before media prep.
        if op == "session.status":
            if "read" not in binding.scopes:
                return response(rid, "denied", "not_authorized")
            self.voice_ready.snapshot()  # preparation outside the final authority commit
            now = self.clock()
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                with self.voice_ready.commit_guard() as (voice_ready, _):
                    with self.store.serialized_authority():
                        if not self.enabled:
                            return response(rid, "unavailable", "feature_off")
                        if not owner_ready:
                            return response(rid, "unavailable", "owner_busy")
                        if not self.store.binding_current_serialized(binding, now=now):
                            return response(rid, "denied", "not_authorized")
                        if not voice_ready:
                            return response(rid, "unavailable", "voice_not_ready")
                        return response(rid, "ok", "none", {"readiness": "ready"})
        if op == "voice.end":
            peer_id = payload["peer_id"]
            authenticated_binding = binding
            with self._lock:
                item = self._peers.get(peer_id)
                if item is not None and item["binding"] != authenticated_binding:
                    return response(rid, "denied", "not_authorized")
                if item is not None:
                    binding = item["binding"]
            if (binding.owner_id, binding.device_id, binding.login_incarnation) != (
                    context.owner_id, context.device_id, context.login_incarnation):
                return response(rid, "denied", "not_authorized")
            now = self.clock()
            ended = None
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                with self.store.serialized_authority():
                    if not self.enabled:
                        return response(rid, "unavailable", "feature_off")
                    if not owner_ready:
                        return response(rid, "unavailable", "owner_busy")
                    if not self.store.binding_current_serialized(binding, now=now):
                        return response(rid, "denied", "not_authorized")
                    with self._lock:
                        current = self._peers.get(peer_id)
                        if current is not None and current["binding"] != binding:
                            return response(rid, "denied", "not_authorized")
                        if (current is not None and item is not None
                                and current["resource"] is not item["resource"]):
                            return response(rid, "denied", "not_authorized")
                        if current is not None:
                            self._peers.pop(peer_id, None)
                            ended = current
                            if self._owner_lease.get(binding.owner_id) == peer_id:
                                self._owner_lease.pop(binding.owner_id, None)
                            self.output_sink.cancel_peer(peer_id)
                            if self._media_peers.get(peer_id) is current["resource"]:
                                self._media_peers.pop(peer_id, None)
            if ended is not None:
                # External cleanup is deliberately after authority/service locks.
                self.media.close_resource(peer_id, ended["resource"])
            return response(rid, "ok", "none", {"peer_id": peer_id, "ended": True})
        if op not in {"voice.offer", "voice.update"}:
            return response(rid, "unavailable", "operation_unavailable")
        if "voice" not in binding.scopes:
            return response(rid, "denied", "not_authorized")
        if not context.ticket_id:
            return response(rid, "denied", "not_authorized")
        prior_peer = None
        prior_version = None
        if op == "voice.update":
            with self._lock:
                prior_peer = self._peers.get(payload["peer_id"])
                if (prior_peer is None or prior_peer["binding"] != binding
                        or self._owner_lease.get(binding.owner_id) != payload["peer_id"]):
                    return response(rid, "denied", "not_authorized")
                prior_version = prior_peer["version"]
        try:
            ticket_now = self.clock()
            consumed = self.store.consume_ticket(identity=context.identity,
                ticket_id=context.ticket_id, session_id=context.session_id,
                owner_id=context.owner_id, purpose="update" if op == "voice.update" else "offer",
                payload_digest=hashlib.sha256(payload["sdp"].encode()).hexdigest(),
                now=ticket_now, peer_id=payload.get("peer_id"))
            if consumed != binding:
                raise StoreDenied("binding changed")
        except StoreDenied:
            return response(rid, "denied", "not_authorized")
        except StoreUnavailable:
            return response(rid, "unavailable", "authority_unavailable")
        prepare_now = self.clock()
        if not self.store.binding_current(binding, now=prepare_now):
            return response(rid, "denied", "not_authorized")
        if not self.voice_ready.snapshot()[0]:
            return response(rid, "unavailable", "voice_not_ready")
        try:
            # This is deliberately outside the authority guard.
            prepared = self.media.prepare(payload["sdp"],
                payload.get("peer_id") if op == "voice.update" else None)
        except Exception:
            return response(rid, "unavailable", "voice_not_ready")
        if type(prepared) is not PreparedMedia:
            return response(rid, "unavailable", "voice_not_ready")
        peer_id = prepared.peer_id
        response_payload = {"peer_id": peer_id, "sdp": prepared.answer}
        if (not validate_success_payload(op, response_payload)
                or (op == "voice.update" and peer_id != payload["peer_id"])):
            self.media.abort(prepared)
            return response(rid, "unavailable", "voice_not_ready")
        commit_error = None
        published = False
        commit_now = self.clock()
        try:
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready_at_commit, _gate_version):
                with self.voice_ready.commit_guard() as (voice_ready_at_commit, _ready_version):
                    with self.store.serialized_authority():
                        if not self.enabled:
                            commit_error = response(rid, "unavailable", "feature_off")
                        elif not owner_ready_at_commit:
                            commit_error = response(rid, "unavailable", "owner_busy")
                        elif not voice_ready_at_commit:
                            commit_error = response(rid, "unavailable", "voice_not_ready")
                        elif not self.store.binding_current_serialized(binding, now=commit_now):
                            commit_error = response(rid, "denied", "not_authorized")
                        else:
                            with self._lock:
                                if op == "voice.offer":
                                    lease = self._owner_lease.get(binding.owner_id)
                                    if lease is not None and lease in self._peers:
                                        commit_error = response(rid, "unavailable", "owner_busy")
                                    elif peer_id in self._peers:
                                        commit_error = response(rid, "unavailable", "voice_not_ready")
                                    elif not self._activate_prepared_locked(prepared):
                                        commit_error = response(rid, "unavailable", "voice_not_ready")
                                    else:
                                        self._peers[peer_id] = {"binding": binding, "context": context,
                                            "version": 1, "resource": prepared.resource}
                                        self._owner_lease[binding.owner_id] = peer_id
                                        published = True
                                else:
                                    current_peer = self._peers.get(peer_id)
                                    if (current_peer is not prior_peer or current_peer is None
                                            or current_peer["version"] != prior_version
                                            or current_peer["binding"] != binding
                                            or self._owner_lease.get(binding.owner_id) != peer_id):
                                        commit_error = response(rid, "denied", "not_authorized")
                                    elif not self._activate_prepared_locked(prepared):
                                        commit_error = response(rid, "unavailable", "voice_not_ready")
                                    else:
                                        self._peers[peer_id] = {"binding": binding, "context": context,
                                            "version": prior_version + 1, "resource": prepared.resource}
                                        published = True
        except StoreDenied:
            commit_error = response(rid, "denied", "not_authorized")
        except StoreUnavailable:
            commit_error = response(rid, "unavailable", "authority_unavailable")
        except Exception:
            commit_error = response(rid, "unavailable", "authority_unavailable")
        if not published:
            self.media.abort(prepared)
            if not self.enabled or not self._owner_ready(context.owner_id):
                self.tick()
            return commit_error or response(rid, "denied", "not_authorized")
        receipt = response(rid, "ok", "none", response_payload)
        return receipt

    def emit_output(self, peer_id, server_output):
        """Prepare trusted server content, then linearly enqueue under the revoke guard.

        ``server_output`` is internal data from the later source-classifier seam;
        this facade never accepts it from phone JSON. The injected policy must
        deny unknown/legacy/protected content and require a destination grant.
        """
        if not self.enabled:
            self.tick()
            return False
        if self.output_policy is None:
            return False
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer is None or self._owner_lease.get(peer["binding"].owner_id) != peer_id:
                return False
            binding = peer["binding"]
            owner_id = peer["context"].owner_id
        if not self._owner_ready(owner_id):
            self.tick()
            return False
        try:
            prepare_now = self.clock()
            if "read" not in binding.scopes or not self.store.binding_current(binding, now=prepare_now):
                return False
        except StoreUnavailable:
            return False
        try:
            prepared = self.output_policy.prepare(server_output)
        except Exception:
            return False
        if type(prepared) is not bytes:
            return False
        committed = False
        owner_was_unavailable = False
        commit_now = self.clock()
        with self.owner_available.commit_guard(owner_id) as (owner_ready_at_commit, _gate_version):
            owner_was_unavailable = not owner_ready_at_commit
            with self.store.serialized_authority():
                if (self.enabled and owner_ready_at_commit
                        and self.store.binding_current_serialized(binding, now=commit_now)):
                    with self._lock:
                        current = self._peers.get(peer_id)
                        if current is not None and current["binding"] == binding and self._owner_lease.get(binding.owner_id) == peer_id:
                            committed = self.output_sink.enqueue_nonblocking({
                                "peer_id": peer_id, "binding": binding, "payload": prepared})
        if not self.enabled or owner_was_unavailable:
            self.tick()
        return committed

    def drain_output(self):
        """Dequeue one synthetic item only while its current binding is valid."""
        if not self.enabled:
            self.tick()
            return None
        queued = self.output_sink.peek()
        if queued is None:
            return None
        if not self._owner_ready(queued["binding"].owner_id):
            self.tick()
            return None
        invalidated = False
        owner_id = queued["binding"].owner_id
        commit_now = self.clock()
        with self.owner_available.commit_guard(owner_id) as (owner_ready_at_commit, _gate_version):
            with self.store.serialized_authority():
                if not owner_ready_at_commit:
                    invalidated = True
                    item = None
                else:
                    item = self.output_sink.dequeue(expected=queued)
                    if item is None:
                        return None
                if invalidated or (not self.enabled
                        or not self.store.binding_current_serialized(item["binding"], now=commit_now)):
                    if not self.enabled:
                        self.output_sink.clear()
                    payload = None
                else:
                    with self._lock:
                        peer = self._peers.get(item["peer_id"])
                        valid_peer = (peer is not None and peer["binding"] == item["binding"]
                                      and self._owner_lease.get(item["binding"].owner_id) == item["peer_id"])
                    payload = item["payload"] if valid_peer else None
        if invalidated:
            self.tick()
        return payload

    def tick(self):
        """Explicit synthetic poll; caller must invoke at least once per five seconds."""
        with self._lock:
            peers = list(self._peers.items())
        if not self.enabled and not peers:
            self.output_sink.clear()
            return 0
        closed = 0
        for peer_id, item in peers:
            binding = item["binding"]
            removed = None
            now = self.clock()
            with self.owner_available.commit_guard(item["context"].owner_id) as (owner_ready, _gate_version):
                with self.store.serialized_authority():
                    if not self.enabled or not owner_ready:
                        current = False
                    else:
                        try:
                            current = self.store.binding_current_serialized(binding, now=now)
                        except StoreUnavailable:
                            current = False
                    if not current:
                        with self._lock:
                            removed = self._peers.pop(peer_id, None)
                            if removed and self._owner_lease.get(removed["binding"].owner_id) == peer_id:
                                self._owner_lease.pop(removed["binding"].owner_id, None)
                            if removed:
                                self.output_sink.cancel_peer(peer_id)
                                if self._media_peers.get(peer_id) is removed["resource"]:
                                    self._media_peers.pop(peer_id, None)
            item = removed
            if item:
                self.media.close_resource(peer_id, item["resource"])
                closed += 1
        if not self.enabled:
            self.output_sink.clear()
        return closed

    def notify_revocation(self):
        """Explicit in-process notification hook; callbacks occur outside store locks."""
        return self.tick()

    def handle(self, raw, context):
        try:
            request = parse_request(raw)
        except ProtocolError as error:
            return response(error.request_id, error.status, error.reason)
        if not self.enabled:
            self.tick()
            return response(request["request_id"], "unavailable", "feature_off")
        if not self._valid_context(context):
            return response(request["request_id"], "denied", "not_authorized")
        try:
            current_now = self.clock()
            binding = self.store.current_binding(identity=context.identity,
                owner_id=context.owner_id, session_id=context.session_id,
                device_id=context.device_id, login_incarnation=context.login_incarnation,
                now=current_now)
        except StoreUnavailable:
            return response(request["request_id"], "unavailable", "authority_unavailable")
        except StoreDenied:
            return response(request["request_id"], "denied", "not_authorized")
        self._prune_terminal_ledger()
        try:
            key, _, early = self._reserve_request(binding, request)
        except StoreUnavailable:
            return response(request["request_id"], "unavailable", "authority_unavailable")
        if early is not None:
            with self._lock:
                entry = self._ledger.get(key)
                cached = entry is not None and entry["state"] == "done" and entry["receipt"] is early
            if cached:
                return self._revalidate_cached_receipt(request, context, binding, early)
            return early
        try:
            result = self._serve(request, context, binding)
        except StoreUnavailable:
            result = response(request["request_id"], "unavailable", "authority_unavailable")
        except Exception:
            # Never leak exception messages or adapter/authority internals.
            result = response(request["request_id"], "unavailable", "authority_unavailable")
        try:
            validate_response(result, operation=request["operation"], require_operation=True)
        except (TypeError, ValueError):
            result = response(request["request_id"], "unavailable", "authority_unavailable")
        return self._finish(key, result)
