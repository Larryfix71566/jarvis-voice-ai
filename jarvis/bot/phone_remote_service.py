"""Store-backed, in-process synthetic facade; no listener or real media."""
from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import sqlite3
import threading
import time
import uuid
import weakref
from contextlib import contextmanager
from dataclasses import dataclass

from jarvis.bot.phone_admission_store import (FakeProtectedAnchor, PhoneAdmissionStore, StoreDenied, StoreUnavailable)
from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV2, run_store_operation
from jarvis.bot.phone_remote_protocol import (ProtocolError, parse_request, response,
    validate_response, validate_success_payload)

_AUTHORITY_REGISTRY_LOCK = threading.RLock()
_RUNTIMES_BY_ANCHOR = weakref.WeakKeyDictionary()
_AUTHORITY_CHILD_CAPABILITY = object()


class _AuthorityRuntime:
    """Strong-lived process coordinator for one injected protected authority."""
    def __init__(self, owner_available, clock, voice_ready, ledger_per_binding, ledger_total):
        self.lock = threading.RLock()
        self.owner_available = owner_available
        self.clock = clock
        self.voice_ready = voice_ready
        self.ledger_per_binding = ledger_per_binding
        self.ledger_total = ledger_total
        self.ledger = {}
        self.peers = {}
        self.owner_lease = {}
        self.active_resources = {}
        self.pending_media = {}
        self.sinks = weakref.WeakSet()


def _authority_runtime(anchor, owner_available, clock, voice_ready,
                       default_owner, default_clock, default_ready,
                       ledger_per_binding, ledger_total):
    with _AUTHORITY_REGISTRY_LOCK:
        runtime = _RUNTIMES_BY_ANCHOR.get(anchor)
        if runtime is None:
            runtime = _AuthorityRuntime(default_owner, default_clock, default_ready,
                                        ledger_per_binding, ledger_total)
            _RUNTIMES_BY_ANCHOR[anchor] = runtime
        else:
            for supplied, current, label in (
                    (owner_available, runtime.owner_available, "owner availability"),
                    (clock, runtime.clock, "clock"),
                    (voice_ready, runtime.voice_ready, "voice readiness")):
                if supplied is not None and supplied is not current:
                    raise TypeError(f"shared authority requires the same {label} gate")
            runtime.ledger_per_binding = min(runtime.ledger_per_binding, ledger_per_binding)
            runtime.ledger_total = min(runtime.ledger_total, ledger_total)
        return runtime


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
    """Synthetic preparer; the service alone owns active and pending registries."""
    def __init__(self):
        self._capability = object()

    def prepare(self, sdp, peer_id=None, resource=None):
        peer = peer_id or uuid.uuid4().hex
        if peer_id is not None and resource is None:
            raise RuntimeError("peer unavailable")
        answer = "v=0\r\no=fake 1 1 IN IP4 127.0.0.1\r\ns=fake\r\nt=0 0\r\n"
        return self._make_prepared(peer, answer, updating=peer_id is not None, resource=resource)

    def _make_prepared(self, peer_id, answer, *, updating=False, resource=None):
        resource = resource if updating else object()
        return PreparedMedia(self._capability, uuid.uuid4().bytes, peer_id, answer, updating, resource)

    def _replace_prepared(self, prepared, *, peer_id=None, answer=None):
        """Fake-adapter test seam for malformed or aliased adapter replies."""
        replacement = PreparedMedia(self._capability, prepared.token,
            prepared.peer_id if peer_id is None else peer_id,
            prepared.answer if answer is None else answer, prepared.updating, prepared.resource)
        return replacement


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


class FakeClockGate:
    """Serialized synthetic clock; time changes cannot race authority commits."""
    def __init__(self, now=None):
        value = time.monotonic() if now is None else now
        if type(value) not in (int, float) or not math.isfinite(value):
            raise TypeError("clock value must be finite")
        self._now = float(value)
        self._lock = threading.RLock()
        self._version = 0
        self._pause_thread = None
        self._pause_arrived = None
        self._pause_release = None

    def set_time(self, now):
        if type(now) not in (int, float) or not math.isfinite(now):
            raise TypeError("clock value must be finite")
        with self._lock:
            self._now = float(now)
            self._version += 1

    def snapshot(self):
        with self._lock:
            return self._now, self._version

    def pause_before_commit(self, thread_name, arrived, release):
        self._pause_thread, self._pause_arrived, self._pause_release = thread_name, arrived, release

    @contextmanager
    def commit_guard(self):
        if threading.current_thread().name == self._pause_thread:
            self._pause_arrived.set()
            if not self._pause_release.wait(2):
                raise RuntimeError("clock gate barrier timed out")
        with self._lock:
            yield self._now, self._version


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
                 owner_available=None, clock=None,
                 ledger_per_binding=256, ledger_total=4096, output_sink=None,
                 output_policy=None, voice_ready=None, _authority_child_capability=None):
        if type(store) is not PhoneAdmissionStore:
            raise TypeError("service requires the concrete disposable admission store")
        if type(verifier) is not FakeContextVerifier:
            raise TypeError("context verification must use the explicit fake verifier")
        if not isinstance(media, FakeMediaAdapter) or not callable(getattr(media, "prepare", None)):
            raise TypeError("media must be a synthetic FakeMediaAdapter preparer")
        if type(getattr(media, "_capability", None)) is not object:
            raise TypeError("media preparation capability is invalid")
        child_authority = (type(store.anchor) is NativeProtectedAnchorV2
                           and _authority_child_capability is _AUTHORITY_CHILD_CAPABILITY)
        if type(store.anchor) is not FakeProtectedAnchor and not child_authority:
            raise TypeError("service authority must use the exact fake protected anchor")
        if type(enabled) is not bool:
            raise TypeError("feature state must be bool")
        if type(ledger_per_binding) is not int or ledger_per_binding < 1 or type(ledger_total) is not int or ledger_total < 1:
            raise TypeError("ledger limits must be positive integers")
        if output_sink is not None and type(output_sink) is not FakeBoundedSink:
            raise TypeError("only the bounded synthetic sink is supported")
        if clock is not None and type(clock) is not FakeClockGate:
            raise TypeError("clock must use FakeClockGate")
        if owner_available is not None and type(owner_available) is not FakeOwnerAvailabilityGate:
            raise TypeError("owner availability must use FakeOwnerAvailabilityGate")
        if voice_ready is not None and type(voice_ready) is not FakeReadinessGate:
            raise TypeError("voice readiness must use FakeReadinessGate")
        self.store, self.verifier, self.media = store, verifier, media
        self.enabled = enabled
        requested_clock = clock if clock is not None else FakeClockGate()
        requested_owner = owner_available if owner_available is not None else FakeOwnerAvailabilityGate()
        requested_ready = voice_ready if voice_ready is not None else FakeReadinessGate()
        self._runtime = _authority_runtime(store.anchor, owner_available, clock, voice_ready,
                                           requested_owner, requested_clock, requested_ready,
                                           ledger_per_binding, ledger_total)
        # First service seeds the gates; subsequent wrappers must supply the same
        # explicit objects or omit them and inherit this authority's gates.
        if self._runtime.clock is not requested_clock and clock is not None:
            raise TypeError("shared authority requires the same clock gate")
        if self._runtime.owner_available is not requested_owner and owner_available is not None:
            raise TypeError("shared authority requires the same owner availability gate")
        if self._runtime.voice_ready is not requested_ready and voice_ready is not None:
            raise TypeError("shared authority requires the same voice readiness gate")
        self.clock = self._runtime.clock
        self.owner_available = self._runtime.owner_available
        self.voice_ready = self._runtime.voice_ready
        self._service_token = object()
        self._media_capability = media._capability
        self.ledger_per_binding, self.ledger_total = (self._runtime.ledger_per_binding,
                                                      self._runtime.ledger_total)
        self.output_sink = output_sink if output_sink is not None else FakeBoundedSink()
        self.output_policy = output_policy
        self._lock = self._runtime.lock
        self._ledger = self._runtime.ledger
        self._peers = self._runtime.peers
        self._owner_lease = self._runtime.owner_lease
        self._lease_registry = self._runtime.owner_lease  # compatibility inspection alias
        self._active_resources = self._runtime.active_resources
        self._pending_media = self._runtime.pending_media
        with self._lock:
            self._runtime.sinks.add(self.output_sink)
        self._authority_child = child_authority
        self._authority_failed = False

    @classmethod
    def _from_authority_child(cls, store, verifier, media, **kwargs):
        """Private constructor available only to the inherited-channel child."""
        return cls(store, verifier, media,
                   _authority_child_capability=_AUTHORITY_CHILD_CAPABILITY, **kwargs)

    @contextmanager
    def _service_commit(self):
        if self._authority_child:
            with self.store.anchor.service_commit():
                with self.store.serialized_authority():
                    yield
        else:
            with self.store.serialized_authority():
                yield

    def _binding_current(self, binding, *, now):
        if self._authority_child:
            return run_store_operation("service.authorize", self.store.binding_current,
                binding, now=now, anchor=self.store.anchor)
        return self.store.binding_current(binding, now=now)

    def _current_binding(self, **kwargs):
        if self._authority_child:
            return run_store_operation("service.authorize", self.store.current_binding,
                anchor=self.store.anchor, **kwargs)
        return self.store.current_binding(**kwargs)

    def _consume_ticket(self, **kwargs):
        if self._authority_child:
            return run_store_operation("ticket.consume", self.store.consume_ticket,
                anchor=self.store.anchor, **kwargs)
        return self.store.consume_ticket(**kwargs)

    def _fence_authority(self):
        if not self._authority_child:
            return
        with self._lock:
            self._authority_failed = True
            self._peers.clear()
            self._owner_lease.clear()
            self._active_resources.clear()
            self._pending_media.clear()
            for entry in self._ledger.values():
                if entry.get("state") == "in_flight":
                    entry.update(state="uncertain", receipt=None)
            for sink in tuple(self._runtime.sinks):
                sink.clear()

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

    def _now(self):
        return self.clock.snapshot()[0]

    def _prepared_is_valid(self, prepared, *, updating, peer_id=None, resource=None):
        if (type(prepared) is not PreparedMedia
                or prepared._capability is not self._media_capability
                or type(prepared.token) is not bytes or len(prepared.token) != 16
                or type(prepared.peer_id) is not str or not prepared.peer_id
                or type(prepared.updating) is not bool or prepared.updating is not updating
                or type(prepared.resource) is not object):
            return False
        try:
            if len(prepared.peer_id.encode("utf-8", "strict")) > 128:
                return False
        except UnicodeError:
            return False
        if updating and (prepared.peer_id != peer_id or prepared.resource is not resource):
            return False
        return validate_success_payload("voice.update" if updating else "voice.offer",
            {"peer_id": prepared.peer_id, "sdp": prepared.answer})

    def _discard_prepared_locked(self, prepared):
        if (type(prepared) is PreparedMedia and type(prepared.token) is bytes
                and self._pending_media.get(prepared.token) is prepared):
            self._pending_media.pop(prepared.token, None)

    def _lease_owner_locked(self, owner_id):
        return self._owner_lease.get(owner_id)

    def _lease_is_mine_locked(self, owner_id, peer_id, resource=None):
        entry = self._lease_owner_locked(owner_id)
        return (entry is not None and entry[0] == peer_id
                and (resource is None or entry[1] is resource))

    def _record_lease_locked(self, owner_id, peer_id, resource):
        self._owner_lease[owner_id] = (peer_id, resource)

    def _clear_lease_locked(self, owner_id, peer_id, resource):
        entry = self._owner_lease.get(owner_id)
        if entry is not None and entry[0] == peer_id and entry[1] is resource:
            self._owner_lease.pop(owner_id, None)

    def _cancel_peer_outputs_locked(self, peer_id):
        for sink in tuple(self._runtime.sinks):
            sink.cancel_peer(peer_id)

    def _activate_prepared_locked(self, prepared):
        """Activate an owned fake resource with plain local dict mutations only.

        Caller holds owner/readiness, store-authority and service locks. No
        adapter method or other injected code runs in this critical section.
        """
        if (type(prepared) is not PreparedMedia or type(prepared.token) is not bytes
                or self._pending_media.get(prepared.token) is not prepared):
            return False
        if prepared.updating:
            valid = self._active_resources.get(prepared.peer_id) is prepared.resource
        else:
            valid = (prepared.peer_id not in self._active_resources
                     and not any(resource is prepared.resource
                                 for resource in self._active_resources.values()))
            if valid:
                self._active_resources[prepared.peer_id] = prepared.resource
        if valid:
            self._pending_media.pop(prepared.token, None)
        return valid

    def _finish(self, key, receipt):
        with self._lock:
            entry = self._ledger[key]
            if entry.get("state") == "uncertain" or self._authority_failed:
                entry.update(state="uncertain", receipt=None)
            else:
                entry.update(state="done", receipt=receipt)
        return receipt

    def _reserve_request(self, binding, request):
        key = (self._binding_key(binding), request["request_id"])
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        with self._lock:
            old = self._ledger.get(key)
            if old is None:
                active = sum(1 for candidate in self._ledger if candidate[0] == key[0])
                if active >= self._runtime.ledger_per_binding or len(self._ledger) >= self._runtime.ledger_total:
                    return key, None, response(request["request_id"], "denied", "request_capacity"), None
                self._ledger[key] = {"binding": binding, "operation": request["operation"],
                    "version": request["protocol_version"], "digest": digest,
                    "state": "in_flight", "receipt": None, "resource_incarnation": None}
                return key, digest, None, None
        if old["operation"] != request["operation"] or old["version"] != request["protocol_version"] or old["digest"] != digest:
            return key, None, response(request["request_id"], "denied", "request_conflict"), None
        if old["state"] == "in_flight":
            return key, None, response(request["request_id"], "denied", "request_conflict"), None
        try:
            current = self._binding_current(binding, now=self._now())
        except StoreUnavailable:
            return key, None, response(request["request_id"], "unavailable", "authority_unavailable"), None
        if not current:
            return key, None, response(request["request_id"], "denied", "not_authorized"), None
        return key, None, old["receipt"], old.get("resource_incarnation")

    def _revalidate_cached_receipt(self, request, context, binding, receipt, resource_incarnation):
        operation = request["operation"]
        needs_ready = operation in {"session.status", "voice.offer", "voice.update"}
        # Readiness preparation is outside authority locks. The final state is
        # re-read under its versioned gate after all potentially blocking work.
        self.voice_ready.snapshot() if needs_ready else None
        try:
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                if needs_ready:
                    with self.voice_ready.commit_guard() as (voice_ready, _):
                        with self.clock.commit_guard() as (commit_now, _):
                            with self._service_commit():
                                result = self._cached_receipt_commit(request, context, binding, receipt,
                                    commit_now, owner_ready, voice_ready, resource_incarnation)
                else:
                    with self.clock.commit_guard() as (commit_now, _):
                        with self._service_commit():
                            result = self._cached_receipt_commit(request, context, binding, receipt,
                                commit_now, owner_ready, True, resource_incarnation)
            if self._authority_child and not self.enabled:
                # The receipt check is serialized with authority first; after
                # releasing the commit contexts, explicit tick performs the
                # normal peer/lease/output teardown.
                self.tick()
            return result
        except StoreUnavailable:
            self._fence_authority()
            return response(request["request_id"], "unavailable", "authority_unavailable")
        except StoreDenied:
            if self._authority_child:
                self._fence_authority()
                return response(request["request_id"], "unavailable", "authority_unavailable")
            return response(request["request_id"], "denied", "not_authorized")

    def _cached_receipt_commit(self, request, context, binding, receipt, now, owner_ready, voice_ready, resource_incarnation):
        operation = request["operation"]
        if self._authority_failed:
            return response(request["request_id"], "unavailable", "authority_unavailable")
        if not self.store.binding_current_serialized(binding, now=now):
            return response(request["request_id"], "denied", "not_authorized")
        if not self.enabled:
            return response(request["request_id"], "unavailable", "feature_off")
        if not owner_ready:
            return response(request["request_id"], "unavailable", "owner_busy")
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
                        or peer.get("incarnation") is not resource_incarnation
                        or self._owner_lease.get(binding.owner_id, (None,))[0] != peer_id
                        or not self._lease_is_mine_locked(binding.owner_id, peer_id, peer["resource"])):
                    return response(request["request_id"], "denied", "not_authorized")
        return receipt

    def _serve(self, request, context, binding):
        op, rid, payload = request["operation"], request["request_id"], request["payload"]
        if (not self.enabled and (not self._authority_child
                or op in {"voice.offer", "voice.update", "voice.end"})):
            self.tick()
            return response(rid, "unavailable", "feature_off")
        if (op in {"voice.offer", "voice.update"}
                and not self._owner_ready(context.owner_id)):
            self.tick()
            return response(rid, "unavailable", "owner_busy")
        if op in {"results.snapshot", "results.resume", "call.state", "call.answer", "call.decline"}:
            return response(rid, "unavailable", "operation_unavailable")
        # A server handle carries the ticket and the exact login incarnation.
        # Ticket binding is checked and consumed by the store before media prep.
        if op == "session.status":
            if "read" not in binding.scopes and not self._authority_child:
                return response(rid, "denied", "not_authorized")
            self.voice_ready.snapshot()  # preparation outside the final authority commit
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                with self.voice_ready.commit_guard() as (voice_ready, _):
                    with self.clock.commit_guard() as (now, _):
                        with self._service_commit():
                            if not self.store.binding_current_serialized(binding, now=now):
                                commit_result = response(request["request_id"], "denied", "not_authorized")
                            elif "read" not in binding.scopes:
                                commit_result = response(request["request_id"], "denied", "not_authorized")
                            else:
                                commit_result = None
                            if commit_result is not None:
                                return commit_result
                            if not self.enabled:
                                return response(rid, "unavailable", "feature_off")
                            if not owner_ready:
                                return response(rid, "unavailable", "owner_busy")
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
            ended = None
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                with self.clock.commit_guard() as (now, _):
                    with self._service_commit():
                        current_is_valid = self.store.binding_current_serialized(binding, now=now)
                        if not self.enabled:
                            return response(rid, "unavailable", "feature_off")
                        if not owner_ready:
                            return response(rid, "unavailable", "owner_busy")
                        if not current_is_valid:
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
                                if self._owner_lease.get(binding.owner_id, (None,))[0] == peer_id:
                                    self._owner_lease.pop(binding.owner_id, None)
                                self._clear_lease_locked(binding.owner_id, peer_id, current["resource"])
                                self._active_resources.pop(peer_id, None)
                                self._cancel_peer_outputs_locked(peer_id)
            return response(rid, "ok", "none", {"peer_id": peer_id, "ended": True})
        if op not in {"voice.offer", "voice.update"}:
            return response(rid, "unavailable", "operation_unavailable")
        if "voice" not in binding.scopes:
            return response(rid, "denied", "not_authorized")
        if not context.ticket_id:
            return response(rid, "denied", "not_authorized")
        prior_peer = None
        prior_version = None
        prior_resource = None
        if op == "voice.update":
            with self._lock:
                prior_peer = self._peers.get(payload["peer_id"])
                if (prior_peer is None or prior_peer["binding"] != binding
                        or self._owner_lease.get(binding.owner_id, (None,))[0] != payload["peer_id"]
                        or not self._lease_is_mine_locked(binding.owner_id, payload["peer_id"],
                                                          prior_peer["resource"])):
                    return response(rid, "denied", "not_authorized")
                prior_version = prior_peer["version"]
                prior_resource = prior_peer["resource"]
        try:
            ticket_now = self._now()
            consumed = self._consume_ticket(identity=context.identity,
                ticket_id=context.ticket_id, session_id=context.session_id,
                owner_id=context.owner_id, purpose="update" if op == "voice.update" else "offer",
                payload_digest=hashlib.sha256(payload["sdp"].encode()).hexdigest(),
                now=ticket_now, peer_id=payload.get("peer_id"))
        except StoreDenied:
            if self._authority_child:
                self._fence_authority()
                return response(rid, "unavailable", "authority_unavailable")
            return response(rid, "denied", "not_authorized")
        except StoreUnavailable:
            self._fence_authority()
            return response(rid, "unavailable", "authority_unavailable")
        if consumed != binding:
            return response(rid, "denied", "not_authorized")
        prepare_now = self._now()
        if not self._binding_current(binding, now=prepare_now):
            return response(rid, "denied", "not_authorized")
        if not self.voice_ready.snapshot()[0]:
            return response(rid, "unavailable", "voice_not_ready")
        try:
            # This is deliberately outside the authority guard.
            prepared = self.media.prepare(payload["sdp"],
                payload.get("peer_id") if op == "voice.update" else None,
                resource=prior_resource if op == "voice.update" else None)
        except Exception:
            return response(rid, "unavailable", "voice_not_ready")
        if not self._prepared_is_valid(prepared, updating=op == "voice.update",
                peer_id=payload.get("peer_id"), resource=prior_resource):
            return response(rid, "unavailable", "voice_not_ready")
        peer_id = prepared.peer_id
        response_payload = {"peer_id": peer_id, "sdp": prepared.answer}
        with self._lock:
            if prepared.token in self._pending_media:
                return response(rid, "unavailable", "voice_not_ready")
            self._pending_media[prepared.token] = prepared
        commit_error = None
        published = False
        try:
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready_at_commit, _gate_version):
                with self.voice_ready.commit_guard() as (voice_ready_at_commit, _ready_version):
                    with self.clock.commit_guard() as (commit_now, _clock_version):
                        with self._service_commit():
                            current_is_valid = self.store.binding_current_serialized(binding, now=commit_now)
                            if not current_is_valid:
                                commit_error = response(rid, "denied", "not_authorized")
                            elif not self.enabled:
                                commit_error = response(rid, "unavailable", "feature_off")
                            elif not owner_ready_at_commit:
                                commit_error = response(rid, "unavailable", "owner_busy")
                            elif not voice_ready_at_commit:
                                commit_error = response(rid, "unavailable", "voice_not_ready")
                            elif commit_error is None:
                                with self._lock:
                                    if op == "voice.offer":
                                        lease = self._lease_owner_locked(binding.owner_id)
                                        if lease is not None:
                                            commit_error = response(rid, "unavailable", "owner_busy")
                                        elif peer_id in self._peers:
                                            commit_error = response(rid, "unavailable", "voice_not_ready")
                                        elif not self._activate_prepared_locked(prepared):
                                            commit_error = response(rid, "unavailable", "voice_not_ready")
                                        else:
                                            incarnation = object()
                                            self._peers[peer_id] = {"binding": binding, "context": context,
                                                "version": 1, "resource": prepared.resource,
                                                "incarnation": incarnation, "service_token": self._service_token}
                                            self._ledger[(self._binding_key(binding), rid)]["resource_incarnation"] = incarnation
                                            self._record_lease_locked(binding.owner_id, peer_id, prepared.resource)
                                            published = True
                                    else:
                                        current_peer = self._peers.get(peer_id)
                                        if (current_peer is not prior_peer or current_peer is None
                                                or current_peer["version"] != prior_version
                                                or current_peer["binding"] != binding
                                                or self._owner_lease.get(binding.owner_id, (None,))[0] != peer_id
                                                or not self._lease_is_mine_locked(binding.owner_id, peer_id,
                                                                                  prior_resource)):
                                            commit_error = response(rid, "denied", "not_authorized")
                                        elif not self._activate_prepared_locked(prepared):
                                            commit_error = response(rid, "unavailable", "voice_not_ready")
                                        else:
                                            incarnation = object()
                                            self._peers[peer_id] = {"binding": binding, "context": context,
                                                "version": prior_version + 1, "resource": prepared.resource,
                                                "incarnation": incarnation, "service_token": self._service_token}
                                            self._ledger[(self._binding_key(binding), rid)]["resource_incarnation"] = incarnation
                                            published = True
        except StoreDenied:
            if self._authority_child:
                self._fence_authority()
                published = False
                commit_error = response(rid, "unavailable", "authority_unavailable")
            else:
                commit_error = response(rid, "denied", "not_authorized")
        except StoreUnavailable:
            published = False
            self._fence_authority()
            commit_error = response(rid, "unavailable", "authority_unavailable")
        except Exception:
            published = False
            self._fence_authority()
            commit_error = response(rid, "unavailable", "authority_unavailable")
        if not published:
            with self._lock:
                self._discard_prepared_locked(prepared)
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
            if peer is None or self._owner_lease.get(peer["binding"].owner_id, (None,))[0] != peer_id:
                return False
            binding = peer["binding"]
            origin_incarnation = peer["incarnation"]
            owner_id = peer["context"].owner_id
        if not self._owner_ready(owner_id):
            self.tick()
            return False
        try:
            prepare_now = self._now()
            if "read" not in binding.scopes or not self._binding_current(binding, now=prepare_now):
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
        with self.owner_available.commit_guard(owner_id) as (owner_ready_at_commit, _gate_version):
            owner_was_unavailable = not owner_ready_at_commit
            with self.clock.commit_guard() as (commit_now, _clock_version):
                with self._service_commit():
                    authority_valid = self.store.binding_current_serialized(binding, now=commit_now)
                    if (authority_valid and self.enabled and owner_ready_at_commit):
                        with self._lock:
                            current = self._peers.get(peer_id)
                            if (current is not None and current["binding"] == binding
                                    and current.get("incarnation") is origin_incarnation
                                    and self._owner_lease.get(binding.owner_id, (None,))[0] == peer_id
                                    and self._lease_is_mine_locked(binding.owner_id, peer_id,
                                                                   current["resource"])):
                                committed = self.output_sink.enqueue_nonblocking({
                                    "peer_id": peer_id, "binding": binding, "payload": prepared,
                                    "incarnation": origin_incarnation})
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
        with self.owner_available.commit_guard(owner_id) as (owner_ready_at_commit, _gate_version):
            with self.clock.commit_guard() as (commit_now, _clock_version):
                with self._service_commit():
                    authority_valid = self.store.binding_current_serialized(queued["binding"], now=commit_now)
                    if not owner_ready_at_commit:
                        invalidated = True
                        item = None
                    else:
                        item = self.output_sink.dequeue(expected=queued)
                        if item is None:
                            return None
                    if invalidated or (not self.enabled or not authority_valid):
                        if not self.enabled:
                            self.output_sink.clear()
                        payload = None
                    else:
                        with self._lock:
                            peer = self._peers.get(item["peer_id"])
                            valid_peer = (peer is not None and peer["binding"] == item["binding"]
                                and peer.get("incarnation") is item["incarnation"]
                                and self._owner_lease.get(item["binding"].owner_id, (None,))[0] == item["peer_id"]
                                and self._lease_is_mine_locked(item["binding"].owner_id, item["peer_id"],
                                                               peer["resource"]))
                        payload = item["payload"] if valid_peer else None
        if invalidated:
            self.tick()
        return payload

    def tick(self):
        """Explicit synthetic poll; caller must invoke at least once per five seconds."""
        if self._authority_failed:
            return 0
        with self._lock:
            peers = list(self._peers.items())
        if not self.enabled and not peers:
            self.output_sink.clear()
            return 0
        closed = 0
        for peer_id, item in peers:
            if not self.enabled and item.get("service_token") is not self._service_token:
                continue
            binding = item["binding"]
            removed = None
            with self.owner_available.commit_guard(item["context"].owner_id) as (owner_ready, _gate_version):
                with self.clock.commit_guard() as (now, _clock_version):
                    with self._service_commit():
                        try:
                            current = self.store.binding_current_serialized(binding, now=now)
                        except StoreUnavailable:
                            current = False
                        if not self.enabled or not owner_ready:
                            current = False
                        with self._lock:
                            current_peer = self._peers.get(peer_id)
                            should_remove = not current
                            if current_peer is not item:
                                # Another tick/end/reconnect may have replaced this
                                # peer ID while this poll waited for its gate. Never
                                # apply the captured binding's result to a new record.
                                if current_peer is None:
                                    should_remove = False
                                elif not self.enabled:
                                    should_remove = current_peer.get("service_token") is self._service_token
                                elif not owner_ready:
                                    should_remove = True
                                else:
                                    try:
                                        should_remove = not self.store.binding_current_serialized(
                                            current_peer["binding"], now=now)
                                    except StoreUnavailable:
                                        should_remove = True
                            if should_remove and current_peer is not None:
                                removed = self._peers.pop(peer_id, None)
                                if removed and self._owner_lease.get(removed["binding"].owner_id, (None,))[0] == peer_id:
                                    self._owner_lease.pop(removed["binding"].owner_id, None)
                                if removed:
                                    self._clear_lease_locked(removed["binding"].owner_id, peer_id,
                                                             removed["resource"])
                                    self._active_resources.pop(peer_id, None)
                                    self._cancel_peer_outputs_locked(peer_id)
            item = removed
            if item:
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
        if self._authority_failed:
            return response(request["request_id"], "unavailable", "authority_unavailable")
        if not self.enabled and not self._authority_child:
            self.tick()
            return response(request["request_id"], "unavailable", "feature_off")
        if not self._valid_context(context):
            return response(request["request_id"], "denied", "not_authorized")
        try:
            current_now = self._now()
            binding = self._current_binding(identity=context.identity,
                owner_id=context.owner_id, session_id=context.session_id,
                device_id=context.device_id, login_incarnation=context.login_incarnation,
                now=current_now)
        except StoreUnavailable:
            self._fence_authority()
            return response(request["request_id"], "unavailable", "authority_unavailable")
        except StoreDenied:
            return response(request["request_id"], "denied", "not_authorized")
        try:
            key, _, early, cached_incarnation = self._reserve_request(binding, request)
        except StoreUnavailable:
            self._fence_authority()
            return response(request["request_id"], "unavailable", "authority_unavailable")
        if early is not None:
            with self._lock:
                entry = self._ledger.get(key)
                cached = entry is not None and entry["state"] == "done" and entry["receipt"] is early
            if cached:
                return self._revalidate_cached_receipt(request, context, binding, early, cached_incarnation)
            return early
        try:
            result = self._serve(request, context, binding)
        except StoreUnavailable:
            self._fence_authority()
            result = response(request["request_id"], "unavailable", "authority_unavailable")
        except Exception:
            # Never leak exception messages or adapter/authority internals.
            self._fence_authority()
            result = response(request["request_id"], "unavailable", "authority_unavailable")
        try:
            validate_response(result, operation=request["operation"], require_operation=True)
        except (TypeError, ValueError):
            result = response(request["request_id"], "unavailable", "authority_unavailable")
        return self._finish(key, result)


class _AuthorityChildServiceHost:
    """Single-thread owner for the disposable v2 channel/store/service composition."""
    _METHODS = frozenset({"handle", "tick", "emit_output", "drain_output", "read_status",
                         "login", "issue_ticket", "signout", "mutate_authority",
                         "notify_revocation", "set_enabled", "shutdown"})

    def __init__(self, database_path, *, verifier, media, enabled=True,
                 owner_available=None, clock=None, voice_ready=None, output_sink=None,
                 output_policy=None):
        if type(database_path) is not str or not database_path or database_path == ":memory:":
            raise TypeError("child authority requires a preprovisioned file database")
        if type(verifier) is not FakeContextVerifier or not isinstance(media, FakeMediaAdapter):
            raise TypeError("child composition requires explicit synthetic dependencies")
        self._database_path = database_path
        self._deps = (verifier, media, enabled, owner_available, clock, voice_ready,
                      output_sink, output_policy)
        self._queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._busy = False
        self._fenced = False
        self._ready = threading.Event()
        self._startup_error = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="phone-authority-child", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise StoreUnavailable("authority child unavailable") from self._startup_error

    def _run(self):
        db = None
        anchor = None
        service = None
        try:
            db = sqlite3.connect(self._database_path, isolation_level=None, timeout=0.25)
            anchor = NativeProtectedAnchorV2.from_inherited_environment()
            from jarvis.bot.phone_remote_authority_channel import open_store
            store = open_store(PhoneAdmissionStore, db, anchor=anchor)
            verifier, media, enabled, owner_available, clock, voice_ready, output_sink, output_policy = self._deps
            service = PhoneRemoteService._from_authority_child(
                store, verifier, media, enabled=enabled, owner_available=owner_available,
                clock=clock, voice_ready=voice_ready, output_sink=output_sink,
                output_policy=output_policy)
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            if anchor is not None:
                anchor.close()
            if db is not None:
                db.close()
            return
        self._ready.set()
        while True:
            item = self._queue.get()
            if item is None:
                break
            method, args, kwargs, done = item
            try:
                result = self._invoke_owned(service, store, anchor, method, args, kwargs)
            except BaseException as exc:
                # Read-only authorization denials are converted to responses
                # inside PhoneRemoteService.handle after a verified release.
                # Any exception escaping an owned call is therefore terminal;
                # in particular, mutation/abort StoreDenied must not leave a
                # child alive merely because it shares the same exception type.
                service._fence_authority()
                result = exc
            # Several content-free service paths intentionally turn transport
            # failures into False/None. Observe a closed authority channel here
            # before completing any call, so those paths cannot leave the
            # process coordinator accepting more work.
            if anchor.is_closed and method != "shutdown":
                service._fence_authority()
            done.result_box.append(result)
            if service._authority_failed or method == "shutdown":
                with self._lock:
                    self._closed = True
                    if service._authority_failed:
                        self._fenced = True
            done.event.set()
            self._queue.task_done()
            if method == "shutdown" or service._authority_failed:
                break
        anchor.close()
        db.close()

    @staticmethod
    def _invoke_owned(service, store, anchor, method, args, kwargs):
        if method == "handle":
            return service.handle(*args, **kwargs)
        if method in {"tick", "emit_output", "drain_output"}:
            result = getattr(service, method)(*args, **kwargs)
            return result
        if method == "notify_revocation":
            return service.notify_revocation()
        if method == "set_enabled":
            enabled = args[0] if len(args) == 1 else None
            if type(enabled) is not bool:
                raise StoreUnavailable("invalid feature state")
            service.enabled = enabled
            if not enabled:
                return service.tick()
            return None
        if method == "read_status":
            return run_store_operation("store.read", store.status, anchor=anchor)
        if method == "login":
            return run_store_operation("session.login", store.login, *args, anchor=anchor, **kwargs)
        if method == "issue_ticket":
            return run_store_operation("ticket.issue", store.issue_ticket, *args, anchor=anchor, **kwargs)
        if method == "signout":
            result = run_store_operation("session.signout", store.revoke_session, *args, anchor=anchor, **kwargs)
            service.notify_revocation()
            return result
        if method == "mutate_authority":
            mutation = args[0] if args else None
            if type(mutation) is not str or mutation not in {"advance_host_generation", "revoke_grant",
                    "update_grant_scopes", "revoke_device", "replace_device_credential"}:
                raise StoreUnavailable("unsupported authority mutation")
            result = run_store_operation("authority.mutate", getattr(store, mutation),
                                         *args[1:], anchor=anchor, **kwargs)
            service.notify_revocation()
            return result
        if method == "shutdown":
            anchor.wait_for_shutdown()
            return None
        raise StoreUnavailable("unsupported child operation")

    def _submit(self, method, *args, **kwargs):
        if type(method) is not str or method not in self._METHODS:
            raise StoreUnavailable("authority child unavailable")
        with self._lock:
            if self._closed:
                raise StoreUnavailable("authority child unavailable")
            if self._busy:
                return self._busy_result(method, args)
            self._busy = True
            event = threading.Event()
            result_box = []
            # A local immutable envelope; no callback is ever run by the caller.
            self._queue.put_nowait((method, args, kwargs, _OwnedCompletion(event, result_box)))
        event.wait()
        with self._lock:
            self._busy = False
        result = result_box[0]
        if isinstance(result, StoreDenied):
            raise result
        if isinstance(result, BaseException):
            raise StoreUnavailable("authority child unavailable") from result
        if method == "shutdown":
            self._closed = True
        return result

    def handle(self, raw, context):
        return self._submit("handle", raw, context)

    def tick(self):
        return self._submit("tick")

    def emit_output(self, peer_id, server_output):
        return self._submit("emit_output", peer_id, server_output)

    def drain_output(self):
        return self._submit("drain_output")

    def read_status(self):
        return self._submit("read_status")

    def login(self, **kwargs):
        return self._submit("login", **kwargs)

    def issue_ticket(self, **kwargs):
        return self._submit("issue_ticket", **kwargs)

    def signout(self, **kwargs):
        return self._submit("signout", **kwargs)

    def mutate_authority(self, mutation, *args, **kwargs):
        return self._submit("mutate_authority", mutation, *args, **kwargs)

    def notify_revocation(self):
        return self._submit("notify_revocation")

    def set_enabled(self, enabled):
        return self._submit("set_enabled", enabled)

    def shutdown(self):
        return self._submit("shutdown")

    @staticmethod
    def _busy_result(method, args):
        if method == "handle":
            from jarvis.bot.phone_remote_protocol import ProtocolError, parse_request, response
            try:
                request = parse_request(args[0])
                return response(request["request_id"], "unavailable", "authority_unavailable")
            except ProtocolError as exc:
                return response(exc.request_id, exc.status, exc.reason)
        if method in {"emit_output"}:
            return False
        if method in {"drain_output"}:
            return None
        if method in {"tick", "notify_revocation"}:
            return 0
        raise StoreUnavailable("authority child is busy")


class _OwnedCompletion:
    def __init__(self, event, result_box):
        self.event = event
        self.result_box = result_box
