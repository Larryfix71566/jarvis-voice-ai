"""Store-backed, in-process synthetic facade; no listener or real media."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import queue
import sqlite3
import threading
import time
import types
import uuid
import weakref
from contextlib import contextmanager
from dataclasses import dataclass

from jarvis.bot.phone_admission_store import (FakeProtectedAnchor, PhoneAdmissionStore, StoreDenied, StoreUnavailable)
from jarvis.bot.phone_remote_authority_channel import (
    NativeProtectedAnchorV2, NativeProtectedAnchorV3, NativeProtectedAnchorV4, run_store_operation,
)
from jarvis.bot.phone_remote_login import LoginClockGate, LoginFailure, PhoneRemoteLogin
from jarvis.bot.phone_remote_connection import (
    _ConnectionCancelled,
    _CONNECTION_CONSTRUCTION, ConnectionClock, ConnectionRegistry, ConnectionFailure,
    ProofContextVerifier,
)
from jarvis.bot.phone_remote_protocol import (ProtocolError, parse_request, response,
    validate_response, validate_success_payload)
from jarvis.bot.phone_remote_results import PhoneRemoteResults
from jarvis.bot.phone_remote_result_commands import (PhoneResultCommandRegistry, CommandDenied,
    OPERATIONS as CARD_OPERATIONS)

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
        self.result_commands = PhoneResultCommandRegistry(self.lock)
        self.card_authority_failed = False
        self.card_commit_active = False
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
        self._connection_clock = None
        self._pause_thread = None
        self._pause_arrived = None
        self._pause_release = None

    def set_time(self, now):
        if type(now) not in (int, float) or not math.isfinite(now):
            raise TypeError("clock value must be finite")
        with self._lock:
            if self._connection_clock is not None:
                self._connection_clock.reject_service_write(self)
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
                 output_policy=None, voice_ready=None, _login_coordinator=None,
                 results=None, _authority_child_capability=None, _connection_registry=None):
        if type(store) is not PhoneAdmissionStore:
            raise TypeError("service requires the concrete disposable admission store")
        proof_mode = (type(_connection_registry) is ConnectionRegistry
                      and type(verifier) is ProofContextVerifier
                      and verifier is _connection_registry.verifier
                      and _authority_child_capability is _AUTHORITY_CHILD_CAPABILITY
                      and type(store.anchor) is NativeProtectedAnchorV4
                      and store.anchor is _connection_registry.host._anchor
                      and clock is _connection_registry.clock.service
                      and _login_coordinator is not None)
        if type(verifier) is not FakeContextVerifier and not proof_mode:
            raise TypeError("context verification requires an exact owned verifier")
        if _connection_registry is not None and not proof_mode:
            raise TypeError("invalid connection composition")
        if not isinstance(media, FakeMediaAdapter) or not callable(getattr(media, "prepare", None)):
            raise TypeError("media must be a synthetic FakeMediaAdapter preparer")
        if type(getattr(media, "_capability", None)) is not object:
            raise TypeError("media preparation capability is invalid")
        child_authority = (type(store.anchor) in {NativeProtectedAnchorV2, NativeProtectedAnchorV3, NativeProtectedAnchorV4}
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
        if results is not None and type(results) is not PhoneRemoteResults:
            raise TypeError("results must be an explicit synthetic projector")
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
        self.results = results
        self._lock = self._runtime.lock
        self._ledger = self._runtime.ledger
        self.result_commands = self._runtime.result_commands
        if results is not None:
            self.result_commands.attach(results)
        self._peers = self._runtime.peers
        self._owner_lease = self._runtime.owner_lease
        self._lease_registry = self._runtime.owner_lease  # compatibility inspection alias
        self._active_resources = self._runtime.active_resources
        self._pending_media = self._runtime.pending_media
        with self._lock:
            self._runtime.sinks.add(self.output_sink)
        self._authority_child = child_authority
        self._authority_failed = False
        if _login_coordinator is not None and (
                not child_authority or type(_login_coordinator) is not PhoneRemoteLogin
                or _login_coordinator._store is not store or _login_coordinator._anchor is not store.anchor):
            raise TypeError("login coordinator must belong to this authority child")
        self._login_coordinator = _login_coordinator

    @classmethod
    def _from_authority_child(cls, store, verifier, media, **kwargs):
        """Private constructor available only to the inherited-channel child."""
        return cls(store, verifier, media,
                   _authority_child_capability=_AUTHORITY_CHILD_CAPABILITY, **kwargs)

    def issue_login_challenge(self, *, device_id, grant_id):
        if not self._authority_child or self._login_coordinator is None:
            raise StoreUnavailable("proof login is unavailable")
        return self._login_coordinator.issue_challenge(device_id=device_id, grant_id=grant_id)

    def complete_phone_login(self, *, challenge_id, proof_bytes):
        if not self._authority_child or self._login_coordinator is None:
            raise StoreUnavailable("proof login is unavailable")
        return self._login_coordinator.complete_login(challenge_id=challenge_id, proof_bytes=proof_bytes)

    @contextmanager
    def _service_commit(self):
        if self._authority_child:
            with self.store.anchor.service_commit():
                with self.store.serialized_authority():
                    yield
        else:
            with self.store.serialized_authority():
                yield

    def _proof_lifetime_current(self):
        # Owner-local polls have no phone permit. handle() rejects a proof
        # context without its exact current worker permit before any grant.
        if type(self.verifier) is not ProofContextVerifier or self.verifier.registry.permit is None:
            return True
        return self.verifier.lifetime_locked()

    def _binding_current(self, binding, *, now):
        if type(self.verifier) is ProofContextVerifier and self.verifier.registry.permit is not None:
            with self.clock.commit_guard() as (current_now, _):
                if not self._proof_lifetime_current():
                    return False
                result = run_store_operation("service.authorize", self.store.binding_current,
                    binding, now=current_now, anchor=self.store.anchor)
                return result and self._proof_lifetime_current()
        if self._authority_child:
            return run_store_operation("service.authorize", self.store.binding_current,
                binding, now=now, anchor=self.store.anchor)
        return self.store.binding_current(binding, now=now)

    def _current_binding(self, **kwargs):
        if type(self.verifier) is ProofContextVerifier:
            with self.clock.commit_guard() as (now, _):
                if not self._proof_lifetime_current():
                    raise StoreDenied("connection expired")
                result = run_store_operation("service.authorize", self.store.current_binding,
                    anchor=self.store.anchor, **{**kwargs, "now": now})
                if not self._proof_lifetime_current() or not self.verifier.binding_matches(result):
                    raise StoreDenied("connection binding unavailable")
                return result
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
                if entry.get("state") in {"in_flight", "prepared", "applying", "applied-awaiting-ack"}:
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
        if type(self.verifier) is ProofContextVerifier:
            with self.clock.commit_guard():
                if receipt["status"] == "ok" and not self._proof_lifetime_current():
                    denied = response(key[1], "unavailable", "authority_unavailable")
                    with self._lock:
                        entry = self._ledger[key]
                        if entry["state"] != "done":
                            entry.update(state="withheld", receipt=denied)
                    return denied
                return self._finish_receipt(key, receipt)
        return self._finish_receipt(key, receipt)

    def _finish_receipt(self, key, receipt):
        with self._lock:
            entry = self._ledger[key]
            if entry.get("state") == "withheld":
                return copy.deepcopy(entry["receipt"])
            if entry["operation"] in CARD_OPERATIONS and entry.get("state") == "done":
                return copy.deepcopy(entry["receipt"])
            if entry.get("state") == "uncertain" or self._authority_failed:
                entry.update(state="uncertain", receipt=None)
            else:
                entry.update(state="done", receipt=copy.deepcopy(receipt) if entry["operation"] in CARD_OPERATIONS else receipt)
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
        if old["state"] in {"in_flight", "prepared", "applying", "applied-awaiting-ack"}:
            return key, None, response(request["request_id"], "denied", "request_conflict"), None
        try:
            current = self._binding_current(binding, now=self._now())
        except StoreUnavailable:
            return key, None, response(request["request_id"], "unavailable", "authority_unavailable"), None
        if not current:
            return key, None, response(request["request_id"], "denied", "not_authorized"), None
        return key, None, old["receipt"], old.get("resource_incarnation")

    def _revalidate_cached_receipt(self, request, context, binding, receipt, resource_incarnation):
        if request["operation"] in CARD_OPERATIONS:
            return self._serve_card_request(request, context, binding, cached=receipt)
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
        if not self.store.binding_current_serialized(binding, now=now) or not self._proof_lifetime_current():
            return response(request["request_id"], "denied", "not_authorized")
        if not self.enabled:
            return response(request["request_id"], "unavailable", "feature_off")
        if not owner_ready:
            return response(request["request_id"], "unavailable", "owner_busy")
        if operation in {"session.status", "voice.offer", "voice.update",
                         "results.snapshot", "results.resume"}:
            required_scope = "read" if operation in {"session.status", "results.snapshot", "results.resume"} else "voice"
            if required_scope not in binding.scopes:
                return response(request["request_id"], "denied", "not_authorized")
            if operation in {"session.status", "voice.offer", "voice.update"} and not voice_ready:
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
        if (receipt["status"] == "ok" and operation in {"results.snapshot", "results.resume"}
                and (self.results is None
                     or not self.results.cached_content_authorized(binding, receipt))):
            return response(request["request_id"], "unavailable", "authority_unavailable")
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
        if op in CARD_OPERATIONS:
            return self._serve_card_request(request, context, binding)
        if op in {"results.snapshot", "results.resume"}:
            return self._serve_results(request, context, binding)
        if op in {"call.state", "call.answer", "call.decline"}:
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
                            if not self.store.binding_current_serialized(binding, now=now) or not self._proof_lifetime_current():
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
                        current_is_valid = self.store.binding_current_serialized(binding, now=now) and self._proof_lifetime_current()
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

    @contextmanager
    def _card_commit_lock(self):
        with self._lock:
            if self._runtime.card_commit_active:
                self._runtime.card_authority_failed = True
                raise RuntimeError("reentrant card commit")
            self._runtime.card_commit_active = True
            try:
                yield
            finally:
                self._runtime.card_commit_active = False

    def _serve_card_request(self, request, context, binding, *, cached=None):
        rid = request["request_id"]
        if self._runtime.card_authority_failed:
            return self._results_error(rid, "authority_unavailable")
        if self.results is None:
            return self._results_error(rid, "operation_unavailable")
        key = (self._binding_key(binding), rid)
        prepared = None
        try:
            if cached is None:
                prepared = self.result_commands.prepare(self.results, binding)
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                with self.clock.commit_guard() as (now, _):
                    with self._card_commit_lock():
                        entry = self._ledger[key]
                        commit_denial = None
                        with self._service_commit():
                            try:
                                if self._authority_failed:
                                    raise CommandDenied("authority_unavailable")
                                if not self.store.binding_current_serialized(binding, now=now) or not self._proof_lifetime_current():
                                    self.result_commands.retire_binding(binding)
                                    raise CommandDenied("not_authorized")
                                if not self.enabled:
                                    raise CommandDenied("feature_off")
                                if not owner_ready:
                                    raise CommandDenied("owner_busy")
                                if cached is None:
                                    entry["state"] = "applying"
                                    try:
                                        payload, witness = self.result_commands.apply(
                                            self.results, binding, request, prepared)
                                    except CommandDenied:
                                        entry["state"] = "prepared"  # definitely before effect
                                        raise
                                    if self._runtime.card_authority_failed:
                                        raise RuntimeError("card authority became uncertain")
                                    candidate = response(rid, "ok", "none", payload)
                                    entry.update(state="applied-awaiting-ack", card_witness=witness)
                                else:
                                    candidate = cached
                                    if cached["status"] == "ok":
                                        self.result_commands.publication(self.results, binding, request,
                                            candidate, entry["card_witness"], historical=True)
                            except CommandDenied as error:
                                commit_denial = error
                        if self._runtime.card_authority_failed or self._authority_failed:
                            raise RuntimeError("terminal card authority after acknowledgement")
                        if commit_denial is not None:
                            raise commit_denial
                        if not self._proof_lifetime_current():
                            denied = self._results_error(rid, "authority_unavailable")
                            if cached is None:
                                entry.update(state="withheld", receipt=denied)
                            return denied
                        # ACK precedes first publication. R excludes capability
                        # changes; P/S compare source changes during ACK wait.
                        with self.results._lock, self.results._source._lock:
                            if candidate["status"] == "ok":
                                try:
                                    self.result_commands.publication(self.results, binding, request,
                                        candidate, entry["card_witness"], historical=cached is not None)
                                except CommandDenied as error:
                                    if self._runtime.card_authority_failed or self._authority_failed:
                                        raise RuntimeError("terminal card authority overrides publication denial") from error
                                    denied = self._results_error(rid, error.reason)
                                    if cached is None:
                                        entry.update(state="withheld", receipt=denied)
                                    return denied
                            if self._runtime.card_authority_failed or self._authority_failed:
                                raise RuntimeError("terminal card authority at publication")
                            if cached is None:
                                entry.update(state="done", receipt=copy.deepcopy(candidate))
                            return copy.deepcopy(candidate)
        except CommandDenied as error:
            if self._runtime.card_authority_failed or self._authority_failed:
                return self._uncertain_card_request(key, rid)
            return self._results_error(rid, error.reason)
        except Exception:
            return self._uncertain_card_request(key, rid)

    def _uncertain_card_request(self, key, rid):
        with self._lock:
            self._ledger[key].update(state="uncertain", receipt=None)
            self._runtime.card_authority_failed = True
        self._fence_authority()
        return self._results_error(rid, "authority_unavailable")

    @staticmethod
    def _results_error(rid, reason):
        if reason in {"malformed_request", "not_authorized", "request_capacity", "request_conflict"}:
            return response(rid, "denied", reason)
        if reason == "feature_off":
            return response(rid, "unavailable", reason)
        if reason == "owner_busy":
            return response(rid, "unavailable", reason)
        if reason == "operation_unavailable":
            return response(rid, "unavailable", reason)
        if reason == "authority_unavailable":
            return response(rid, "unavailable", reason)
        return response(rid, "unavailable", "authority_unavailable")

    def _serve_results(self, request, context, binding):
        """Run result preparation outside guards and finalize after v3 release ack."""
        rid, operation = request["request_id"], request["operation"]
        if not self.enabled:
            return response(rid, "unavailable", "feature_off")
        if "read" not in binding.scopes:
            return response(rid, "denied", "not_authorized")
        if self.results is None:
            return response(rid, "unavailable", "operation_unavailable")
        if operation == "results.snapshot":
            source_status, candidate = self.results.prepare_snapshot(binding, self.results.generation)
        else:
            source_status, candidate = self.results.prepare_resume(
                binding, self.results.generation, request["payload"]["cursor"])
        if source_status == "ok" and candidate is None:
            source_status = "authority_unavailable"
        owner_unavailable = False
        result_status, payload = "authority_unavailable", None
        try:
            with self.owner_available.commit_guard(context.owner_id) as (owner_ready, _):
                owner_unavailable = not owner_ready
                with self.clock.commit_guard() as (now, _):
                    # Keep the in-process commit lock across authority release
                    # and projector finalization. The channel release ACK is
                    # received before cursors/receipts become visible, while
                    # the owner worker cannot process another authority change
                    # until this serialized call returns.
                    self._lock.acquire()
                    try:
                        with self._service_commit():
                            if self._authority_failed:
                                gate_error = "authority_unavailable"
                            elif not self.store.binding_current_serialized(binding, now=now) or not self._proof_lifetime_current():
                                gate_error = "not_authorized"
                            elif not self.enabled:
                                gate_error = "feature_off"
                            elif not owner_ready:
                                gate_error = "owner_busy"
                            else:
                                gate_error = None
                        if gate_error is None and not self._proof_lifetime_current():
                            gate_error = "not_authorized"
                        if gate_error is None and source_status == "ok":
                            if operation == "results.snapshot":
                                result_status, payload = self.results.snapshot(
                                    binding, self.results.generation, candidate=candidate,
                                    request_id=rid)
                            else:
                                result_status, payload = self.results.resume(
                                    binding, self.results.generation,
                                    request["payload"]["cursor"], candidate=candidate,
                                    request_id=rid)
                    finally:
                        self._lock.release()
            if gate_error is not None:
                return self._results_error(rid, gate_error)
        except StoreDenied:
            if self._authority_child:
                self._fence_authority()
                return self._results_error(rid, "authority_unavailable")
            return self._results_error(rid, "not_authorized")
        except StoreUnavailable:
            self._fence_authority()
            return self._results_error(rid, "authority_unavailable")
        if owner_unavailable:
            return self._results_error(rid, "owner_busy")
        if source_status != "ok":
            if source_status == "not_authorized":
                return self._results_error(rid, "not_authorized")
            if source_status == "malformed_request":
                return self._results_error(rid, "malformed_request")
            if source_status == "request_capacity":
                return self._results_error(rid, "request_capacity")
            return self._results_error(rid, "authority_unavailable")
        if result_status == "reset":
            return response(rid, "ok", "none", payload)
        if result_status != "ok":
            return self._results_error(rid, result_status)
        return response(rid, "ok", "none", payload)

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
        for binding in self.result_commands.bindings():
            with self.owner_available.commit_guard(binding.owner_id):
                with self.clock.commit_guard() as (now, _):
                    with self._lock, self._service_commit():
                        if not self.store.binding_current_serialized(binding, now=now) or not self._proof_lifetime_current():
                            self.result_commands.retire_binding(binding)
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
        if request["operation"] in CARD_OPERATIONS:
            with self._lock:
                if self._runtime.card_commit_active:
                    self._runtime.card_authority_failed = True
                    return response(request["request_id"], "unavailable", "authority_unavailable")
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
            self.result_commands.retire_context(context)
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
            return copy.deepcopy(early) if request["operation"] in CARD_OPERATIONS else early
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
    """Single-thread owner for the disposable versioned authority composition."""
    _METHODS = frozenset({"handle", "tick", "emit_output", "drain_output", "read_status",
                         "login", "issue_ticket", "signout", "mutate_authority",
                         "issue_login_challenge", "complete_phone_login",
                         "notify_revocation", "set_enabled", "shutdown", "prepare_restore",
                         "connection_challenge", "connection_prove", "activate_connection", "handle_connection"})

    def __init__(self, database_path, *, verifier, media, enabled=True,
                 owner_available=None, clock=None, voice_ready=None, output_sink=None,
                 output_policy=None, login_clock=None, login_service_id="svc.test",
                 store_failpoint=None, results=None, _connection_capability=None,
                 _connection_clock=None, _connection_actions=()):
        if type(database_path) is not str or not database_path or database_path == ":memory:":
            raise TypeError("child authority requires a preprovisioned file database")
        if type(verifier) is not FakeContextVerifier or not isinstance(media, FakeMediaAdapter):
            raise TypeError("child composition requires explicit synthetic dependencies")
        if login_clock is not None and type(login_clock) is not LoginClockGate:
            raise TypeError("login clock must be the concrete offline gate")
        if type(login_service_id) is not str or not login_service_id.strip():
            raise TypeError("login service identity must be configured")
        if store_failpoint is not None and type(store_failpoint) is not types.FunctionType:
            raise TypeError("test store failpoint must be a plain function")
        if results is not None and type(results) is not PhoneRemoteResults:
            raise TypeError("results must use the explicit synthetic projector")
        if _connection_capability is not None and (
                _connection_capability is not _CONNECTION_CONSTRUCTION
                or type(_connection_clock) is not ConnectionClock
                or type(enabled) is not bool or type(_connection_actions) is not tuple):
            raise TypeError("unsupported connection construction")
        if _connection_capability is None and (_connection_clock is not None or _connection_actions):
            raise TypeError("unowned connection dependencies")
        self._proof_enabled = enabled
        self._connections = (ConnectionRegistry(self, _connection_clock, _CONNECTION_CONSTRUCTION)
                             if _connection_capability is _CONNECTION_CONSTRUCTION else None)
        self._connection_actions = _connection_actions
        if getattr(self, "_connections", None) is not None:
            clock, login_clock = _connection_clock.service, _connection_clock.login
        self._database_path = database_path
        self._deps = (verifier, media, enabled, owner_available, clock, voice_ready,
                      output_sink, output_policy, login_clock, login_service_id, store_failpoint, results)
        self._queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._busy = False
        self._fenced = False
        self._quiescing = False
        self._quiescence_deadline = None
        self._quiescence_id = None
        self._current = None
        self._anchor = None
        self._drained = threading.Event()
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
            protocol_version = os.environ.get("PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION", "2")
            anchor_type = {"2": NativeProtectedAnchorV2, "3": NativeProtectedAnchorV3,
                           "4": NativeProtectedAnchorV4}.get(protocol_version)
            if anchor_type is None:
                raise StoreUnavailable("unsupported authority child protocol")
            anchor = anchor_type.from_inherited_environment()
            self._anchor = anchor
            if type(anchor) is NativeProtectedAnchorV4:
                anchor._admission_observer = self._observe_authority
            from jarvis.bot.phone_remote_authority_channel import open_store
            (verifier, media, enabled, owner_available, clock, voice_ready, output_sink,
             output_policy, login_clock, login_service_id, store_failpoint, results) = self._deps
            store = open_store(PhoneAdmissionStore, db, anchor=anchor,
                               **({"failpoint": store_failpoint} if store_failpoint is not None else {}))
            login_coordinator = None
            if type(anchor) in {NativeProtectedAnchorV3, NativeProtectedAnchorV4}:
                login_coordinator = PhoneRemoteLogin(store, anchor,
                    clock=login_clock or LoginClockGate(wall_ms=1_800_000_000_000,
                                                       monotonic_ms=1_000),
                    service_id=login_service_id)
            if getattr(self, "_connections", None) is not None:
                if type(anchor) is not NativeProtectedAnchorV4:
                    raise StoreUnavailable("proof connections require v4")
                verifier = self._connections.verifier
            service = PhoneRemoteService._from_authority_child(
                store, verifier, media, enabled=enabled, owner_available=owner_available,
                clock=clock, voice_ready=voice_ready, output_sink=output_sink,
                output_policy=output_policy, results=results, _login_coordinator=login_coordinator,
                _connection_registry=self._connections)
            if getattr(self, "_connections", None) is not None:
                self._connections.attach(service, store, login_coordinator)
                if results is not None and self._connection_actions:
                    service.result_commands.register(results, self._connection_actions)
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            if anchor is not None:
                anchor.close()
            if db is not None:
                db.close()
            return
        self._ready.set()
        self._serve_owned(service, store, anchor, db)

    def _serve_owned(self, service, store, anchor, db):
        """Serialized dispatch after startup; also exercises the local drain seam."""
        while True:
            item = self._queue.get()
            if item is None:
                break
            method, args, kwargs, done = item
            with self._lock:
                if self._quiescing and method != "__quiesce__":
                    done.settle(StoreUnavailable("quiescing"))
                    done.worker_finished.set()
                    self._busy = False
                    self._queue.task_done()
                    continue
                if method != "__quiesce__" and done.cancellation_requested() and not done.authorized:
                    done.settle(StoreUnavailable("cancelled"))
                    done.worker_finished.set()
                    self._busy = False
                    self._queue.task_done()
                    continue
                self._current = done
            if method == "__quiesce__":
                # The serialized worker owns resources and closes them only
                # after the frozen operation and output bookkeeping terminate.
                failure = None
                try:
                    service._fence_authority()
                    db.close()
                except BaseException as exc:
                    failure = exc
                with self._lock:
                    self._closed = True
                    self._fenced = self._fenced or failure is not None
                    self._current = None
                    self._busy = False
                self._drained.set()
                done.settle(failure)
                done.worker_finished.set()
                if getattr(self, "_connections", None) is not None:
                    self._connections.close_all()
                self._queue.task_done()
                return  # channel stays owned until terminal shutdown/reap
            try:
                result = self._invoke_owned(service, store, anchor, method, args, kwargs)
            except _ConnectionCancelled as exc:
                if done.authorized or anchor.is_closed:
                    service._fence_authority()
                result = exc
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
            with self._lock:
                if service._authority_failed or method == "shutdown":
                    # Publish terminal admission before waking the caller.
                    # Otherwise its next submission can become stranded after
                    # this worker exits.
                    self._closed = True
                    if service._authority_failed:
                        self._fenced = True
                        if self._quiescing:
                            self._drained.set()
                self._current = None
                self._busy = False
                if done.cancellation_requested() and not isinstance(result, BaseException):
                    result = StoreUnavailable("cancelled; effects may have completed" if done.authorized else "cancelled")
                done.settle(result)
            if (method == "shutdown" or service._authority_failed) and getattr(self, "_connections", None) is not None:
                self._connections.close_all()
            if getattr(self, "_connections", None) is not None:
                self._connections.finish_owned(done)
            done.worker_finished.set()
            self._queue.task_done()
            if method == "shutdown" or service._authority_failed:
                break
        anchor.close()
        db.close()

    @staticmethod
    def _invoke_owned(service, store, anchor, method, args, kwargs):
        if method in {"connection_challenge", "connection_prove", "activate_connection", "handle_connection"}:
            if type(service.verifier) is not ProofContextVerifier or kwargs:
                return ConnectionFailure()
            return service.verifier.registry.invoke(method, *args)
        if (type(anchor) is NativeProtectedAnchorV4 and
                (method in {"tick", "notify_revocation"}
                 or (method == "set_enabled" and args == (False,)))):
            # One authorization belongs to this entire owned poll. A revoked
            # binding may return False: the verified release still authorizes
            # cleanup, while each commit rechecks eligibility before mutation.
            # Authorize once so a frozen poll can finish multiple cleanups
            # during drain without admitting a new logical operation.
            with service._lock:
                bindings = service.result_commands.bindings()
                if not bindings:
                    bindings = tuple(peer["binding"] for peer in service._peers.values())
            if bindings:
                service._binding_current(bindings[0], now=service._now())
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
            if type(getattr(service, "verifier", None)) is ProofContextVerifier:
                registry = service.verifier.registry
                with registry.host._lock:
                    registry.host._proof_enabled = enabled
                if not enabled:
                    registry.close_all()
            if not enabled:
                return service.tick()
            return None
        if method == "read_status":
            return run_store_operation("store.read", store.status, anchor=anchor)
        if method == "login":
            return run_store_operation("session.login", store.login, *args, anchor=anchor, **kwargs)
        if method == "issue_login_challenge":
            return service.issue_login_challenge(*args, **kwargs)
        if method == "complete_phone_login":
            return service.complete_phone_login(*args, **kwargs)
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
        if method == "prepare_restore":
            if type(anchor) is not NativeProtectedAnchorV3:
                raise StoreUnavailable("restore preparation is unavailable")
            try:
                run_store_operation("restore.prepare", store.prepare_restore,
                                    *args, anchor=anchor, **kwargs)
                service._fence_authority()
                if os.environ.get("PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE") == "service-fenced":
                    os._exit(79)
                with anchor.restore_finish_context():
                    receipt = anchor.finish_restore_prepare()
                    anchor.wait_for_shutdown()
                    return receipt
            except StoreDenied as exc:
                # The channel permits this only after a verified stable read
                # and an acknowledged pre-write release. Preserve the child
                # for unrelated authority work on this known denial.
                if anchor.is_closed:
                    raise StoreUnavailable("authority operation outcome is unknown") from exc
                return exc
        raise StoreUnavailable("unsupported child operation")

    def _submit(self, method, *args, _cancel_event=None, _wait_worker=False, **kwargs):
        if _cancel_event is not None and type(_cancel_event) is not threading.Event:
            raise TypeError("local cancellation requires a threading event")
        if type(method) is not str or method not in self._METHODS:
            raise StoreUnavailable("authority child unavailable")
        with self._lock:
            if self._closed or getattr(self, "_quiescing", False):
                raise StoreUnavailable("quiescing" if getattr(self, "_quiescing", False) else "authority child unavailable")
            if _cancel_event is not None and _cancel_event.is_set():
                raise StoreUnavailable("cancelled")
            if self._busy:
                return self._busy_result(method, args)
            self._busy = True
            event = threading.Event()
            result_box = []
            # A local immutable envelope; no callback is ever run by the caller.
            completion = _OwnedCompletion(event, result_box, cancel_event=_cancel_event)
            self._queue.put_nowait((method, args, kwargs, completion))
        while not event.wait(0.02 if _cancel_event is not None else None):
            if _cancel_event.is_set():
                with self._lock:
                    completion.cancelled = True
                    try:
                        queued = self._queue.get_nowait()
                    except queue.Empty:
                        queued = None
                    if queued is not None:
                        if queued[3] is not completion:
                            self._queue.task_done()
                            self._queue.put_nowait(queued)
                        else:
                            self._queue.task_done()
                            self._busy = False
                            completion.worker_finished.set()
                    completion.settle(StoreUnavailable("cancelled; effects may have completed"))
        if _wait_worker:
            completion.worker_finished.wait()
        result = result_box[0]
        if isinstance(result, StoreDenied):
            raise result
        if isinstance(result, BaseException):
            raise StoreUnavailable("authority child unavailable") from result
        if method == "shutdown":
            self._closed = True
        return result

    def _observe_authority(self, phase, operation):
        # Called by the one worker at authority boundaries. The frozen receipt
        # belongs to exactly this queued logical operation, never to a caller.
        with self._lock:
            current = self._current
            if self._closed or self._fenced:
                raise StoreUnavailable("authority child unavailable")
            if self._quiescing and time.monotonic() >= self._quiescence_deadline:
                raise StoreUnavailable("authority drain deadline expired")
            if current is None:  # startup store.open
                if operation != "store.open":
                    raise StoreUnavailable("authority operation has no owner")
                return
            if (self._quiescing or current.cancellation_requested()) and not current.authorized:
                if getattr(self, "_connections", None) is not None and phase == "acquire":
                    raise _ConnectionCancelled("local request retired before authority")
                raise StoreUnavailable("quiescing" if self._quiescing else "cancelled")
            if self._quiescing and phase == "acquire" and operation != "service.commit":
                raise StoreUnavailable("only frozen service continuation may drain")
            if operation == "service.commit" and not current.authorized:
                raise StoreUnavailable("service continuation has no authorization")
            if phase == "released" and operation == "service.authorize":
                current.authorized = True
            if phase == "acquire" and operation not in {"service.authorize", "service.commit"}:
                # Direct trusted store calls are serialized operations, not
                # service continuations, and retain ownership once dispatched.
                current.authorized = True

    def quiesce(self, operation_id, *, _owner_deadline=None):
        """Injected local-owner barrier; no phone/HTTP dispatch path calls it.

        One monotonic deadline covers queued removal, the frozen operation,
        resource close, and terminal bookkeeping. Reentry never extends it.
        The native owner separately bounds and reaps its owned child on failure.
        """
        try:
            valid_operation = type(operation_id) is str and str(uuid.UUID(operation_id)) == operation_id
        except ValueError:
            valid_operation = False
        if not valid_operation:
            raise StoreUnavailable("invalid quiescence operation")
        with self._lock:
            if self._quiescing:
                if self._quiescence_id != operation_id:
                    raise StoreUnavailable("authority child is busy")
            else:
                if self._closed or type(self._anchor) is not NativeProtectedAnchorV4:
                    raise StoreUnavailable("authority child unavailable")
                now = time.monotonic()
                if _owner_deadline is not None and (type(_owner_deadline) is not float
                        or not math.isfinite(_owner_deadline) or _owner_deadline > now + 5):
                    raise StoreUnavailable("invalid owner drain deadline")
                self._quiescing = True
                self._quiescence_id = operation_id
                self._quiescence_deadline = now + 5 if _owner_deadline is None else _owner_deadline
                try:
                    queued = self._queue.get_nowait()
                except queue.Empty:
                    queued = None
                if queued is not None:
                    queued[3].settle(StoreUnavailable("quiescing"))
                    queued[3].worker_finished.set()
                    self._queue.task_done()
                completion = _OwnedCompletion(threading.Event(), [])
                self._queue.put_nowait(("__quiesce__", (), {}, completion))
            deadline = self._quiescence_deadline
        remaining = max(0, deadline - time.monotonic())
        drained = remaining > 0 and self._drained.wait(remaining)
        if drained and getattr(self, "_connections", None) is not None:
            # Registry retirement cancels owned ASGI sends. Their actual join
            # shares the original deadline; caller settlement is insufficient.
            drained = self._connections._sends_drained.wait(max(0, deadline - time.monotonic()))
        if (not drained or self._fenced
                or self._anchor.is_closed or time.monotonic() >= deadline):
            with self._lock:
                self._closed = self._fenced = True
                if self._current is not None:
                    self._current.settle(StoreUnavailable("authority_unavailable: completion uncertain"))
            self._anchor.close()
            raise StoreUnavailable("authority_unavailable: completion uncertain")
        return {"operation_id": operation_id, "drained": True}

    def open_connection(self, transport_token):
        return self._connections.open(transport_token) if self._connections is not None else ConnectionFailure()

    def close_connection(self, lease, transport_token):
        if getattr(self, "_connections", None) is not None:
            self._connections.close(lease, transport_token)

    def _connection_call(self, method, lease, token, *args):
        if self._connections is None:
            return ConnectionFailure()
        cancel = self._connections.cancel_event(lease, token)
        if cancel is None:
            return ConnectionFailure()
        try:
            return self._submit(method, lease, token, *args,
                                _cancel_event=cancel, _wait_worker=True)
        except StoreUnavailable:
            return ConnectionFailure("authority_unavailable")

    def connection_challenge(self, lease, token, device_id, grant_id):
        return self._connection_call("connection_challenge", lease, token, device_id, grant_id)

    def connection_prove(self, lease, token, challenge_id, proof_bytes):
        return self._connection_call("connection_prove", lease, token, challenge_id, proof_bytes)

    def activate_connection(self, lease, token, request_id):
        return self._connection_call("activate_connection", lease, token, request_id)

    def handle_connection(self, lease, token, raw):
        return self._connection_call("handle_connection", lease, token, raw)

    def claim_connection_reply(self, lease, token, reply):
        if self._connections is None:
            return ConnectionFailure()
        try:
            return self._connections.claim(lease, token, reply)
        except StoreUnavailable:
            with self._lock:
                self._fenced = self._closed = True
            self._connections.close_all()
            self._anchor.close()
            return ConnectionFailure("authority_unavailable")

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

    def issue_login_challenge(self, **kwargs):
        try:
            return self._submit("issue_login_challenge", **kwargs)
        except StoreUnavailable:
            return LoginFailure("unavailable")

    def complete_phone_login(self, **kwargs):
        try:
            return self._submit("complete_phone_login", **kwargs)
        except StoreUnavailable:
            return LoginFailure("unavailable")

    def issue_ticket(self, **kwargs):
        return self._submit("issue_ticket", **kwargs)

    def signout(self, **kwargs):
        return self._submit("signout", **kwargs)

    def mutate_authority(self, mutation, *args, **kwargs):
        return self._submit("mutate_authority", mutation, *args, **kwargs)

    def prepare_restore(self, **kwargs):
        return self._submit("prepare_restore", **kwargs)

    def notify_revocation(self):
        return self._submit("notify_revocation")

    def set_enabled(self, enabled):
        return self._submit("set_enabled", enabled)

    def shutdown(self):
        if type(self._anchor) is not NativeProtectedAnchorV4:
            return self._submit("shutdown")
        # The caller is the injected local controller. The worker retains sole
        # ownership of its SQLite/service resources until the drain completes.
        anchor = self._anchor
        try:
            frame = anchor._receive()
            payload = frame["payload"]
            if (frame["kind"] != "owner.shutdown" or type(payload) is not dict
                    or payload.keys() != {"operation_id", "reason"}
                    or payload["reason"] != "restore_quiesce"):
                raise StoreUnavailable("invalid shutdown request")
            receipt = self.quiesce(payload["operation_id"])
            anchor._send("child.shutdown_ack", receipt,
                         correlation_id=frame["correlation_id"])
        finally:
            anchor.close()

    @staticmethod
    def _busy_result(method, args):
        if method in {"connection_challenge", "connection_prove", "activate_connection", "handle_connection"}:
            return ConnectionFailure("authority_unavailable")
        if method in {"issue_login_challenge", "complete_phone_login"}:
            return LoginFailure("busy")
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
    def __init__(self, event, result_box, *, cancel_event=None):
        self.event = event
        self.worker_finished = threading.Event()
        self.result_box = result_box
        self.authorized = False
        self.cancelled = False
        self._cancel_event = cancel_event
        self._completion_lock = threading.Lock()

    def cancellation_requested(self):
        # The worker observes the same signal as the waiting caller. Polling
        # latency must never decide whether queued work becomes authorized.
        if self._cancel_event is not None and self._cancel_event.is_set():
            self.cancelled = True
        return self.cancelled

    def settle(self, result):
        with self._completion_lock:
            if self.event.is_set():
                return
            self.result_box.append(result)
            self.event.set()
