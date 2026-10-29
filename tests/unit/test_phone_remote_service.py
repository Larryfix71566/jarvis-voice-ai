import hashlib
import json
import sqlite3
import threading
import unittest
import gc

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore
from jarvis.bot.phone_remote_protocol import PROTOCOL
from jarvis.bot.phone_remote_service import (FakeContextVerifier, FakeMediaAdapter,
    FakeBoundedSink, FakeClockGate, FakeOwnerAvailabilityGate, FakeReadinessGate, PhoneRemoteService,
    TrustedRequestContext)


class BlockingMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def prepare(self, sdp, peer_id=None, resource=None):
        self.calls += 1
        result = super().prepare(sdp, peer_id, resource)
        self.started.set()
        if not self.release.wait(2):
            raise RuntimeError("test barrier timed out")
        return result


class FailingMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def prepare(self, _sdp, peer_id=None, resource=None):
        self.calls += 1
        raise RuntimeError("synthetic media failure with content canary")


class BlockingCommitMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.commit_called = threading.Event()
        self.release = threading.Event()

    def commit(self, _prepared):
        self.commit_called.set()
        if not self.release.wait(2):
            raise RuntimeError("unexpected adapter commit call blocked")
        return True

class CountingMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def prepare(self, sdp, peer_id=None, resource=None):
        self.calls += 1
        return super().prepare(sdp, peer_id, resource)


class InvalidResponseMedia(FakeMediaAdapter):
    def prepare(self, _sdp, peer_id=None, resource=None):
        prepared = super().prepare(_sdp, peer_id, resource)
        return self._replace_prepared(prepared, answer={"private": "unexpected nested content"})


class AliasInvalidMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.alias = None

    def prepare(self, sdp, peer_id=None, resource=None):
        prepared = super().prepare(sdp, peer_id, resource)
        if self.alias is not None:
            return self._replace_prepared(prepared, peer_id=self.alias,
                                          answer={"private": "unexpected nested content"})
        return prepared


class AliasMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.alias = None

    def prepare(self, sdp, peer_id=None, resource=None):
        prepared = super().prepare(sdp, peer_id, resource)
        return (self._replace_prepared(prepared, peer_id=self.alias)
                if self.alias is not None else prepared)


class GhostMedia(FakeMediaAdapter):
    def prepare(self, sdp, peer_id=None, resource=None):
        if peer_id is None:
            return self._make_prepared("ghost-peer", "answer", updating=True, resource=None)
        return super().prepare(sdp, peer_id, resource)


class HashToken:
    def __init__(self):
        self.calls = 0

    def __hash__(self):
        self.calls += 1
        return 123


class HashTokenMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.token = HashToken()

    def prepare(self, sdp, peer_id=None, resource=None):
        return PreparedMedia(self._capability, self.token, "hash-peer", "answer", False, object())


class PeerId(str):
    def __new__(cls, value):
        instance = super().__new__(cls, value)
        instance.calls = 0
        return instance

    def __hash__(self):
        self.calls += 1
        return 456


class HashPeerMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.peer = PeerId("bad-peer")

    def prepare(self, sdp, peer_id=None, resource=None):
        return PreparedMedia(self._capability, b"x" * 16, self.peer, "answer", False, object())


class BarrierOffersMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.barrier = threading.Barrier(2)

    def prepare(self, sdp, peer_id=None, resource=None):
        result = super().prepare(sdp, peer_id, resource)
        if peer_id is None:
            self.barrier.wait(2)
        return result


class UpdateBlockingMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.block_updates = False
        self.started = threading.Event()
        self.release = threading.Event()

    def prepare(self, sdp, peer_id=None, resource=None):
        result = super().prepare(sdp, peer_id, resource)
        if peer_id is not None and self.block_updates:
            self.started.set()
            if not self.release.wait(2):
                raise RuntimeError("update test barrier timed out")
        return result


class FakeOutputPolicy:
    def __init__(self, barrier=None):
        self.barrier = barrier

    def prepare(self, value):
        if self.barrier:
            self.barrier[0].set()
            if not self.barrier[1].wait(2):
                raise RuntimeError("output preparation timeout")
        if (type(value) is not dict or value.get("classification") != "approved_shared"
                or value.get("destination_granted") is not True
                or type(value.get("content")) is not str):
            return None
        return value["content"].encode("utf-8")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.anchor = FakeProtectedAnchor()
        self.store = PhoneAdmissionStore(self.db, self.anchor)
        self.identity = ClientIdentity(name="fake", user_id="alice")
        self.store.add_device(identity=self.identity, device_id="dev", owner_id="alice",
                              public_key=b"public", key_algorithm="test")
        self.store.add_grant(identity=self.identity, grant_id="grant", device_id="dev",
                             owner_id="alice", scopes=["read", "voice"])
        self.incarnation = self.store.login(identity=self.identity, session_id="session",
            grant_id="grant", owner_id="alice", now=1, expires_at=100)
        self.clock = FakeClockGate(2)
        self.media = FakeMediaAdapter()
        self.service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                                          clock=self.clock)
        self.context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation)

    def tearDown(self):
        self.store._drop_admissions()
        self.db.close()

    @staticmethod
    def request(operation, payload, request_id="req"):
        return json.dumps({"kind": PROTOCOL, "protocol_version": 1, "request_id": request_id,
                           "operation": operation, "payload": payload}, separators=(",", ":"))

    def test_feature_off_precedes_context_and_adapter(self):
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                                     enabled=False, clock=FakeClockGate(2))
        result = service.handle(self.request("session.status", {}), object())
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "feature_off"))
        self.assertEqual(service._active_resources, {})

    def test_constructor_rejects_unserialized_runtime_callbacks(self):
        with self.assertRaises(TypeError):
            PhoneRemoteService(self.store, FakeContextVerifier(), self.media, clock=lambda: 2)
        with self.assertRaises(TypeError):
            PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                owner_available=lambda _owner: True)
        with self.assertRaises(TypeError):
            PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                voice_ready=lambda: True)
        with self.assertRaises(TypeError):
            PhoneRemoteService(self.store, object(), self.media)

    def test_readiness_is_content_free_and_voice_offers_store_terminal_receipt(self):
        readiness = FakeReadinessGate(False)
        unavailable = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, voice_ready=readiness)
        status = unavailable.handle(self.request("session.status", {}, "voice-status"), self.context)
        self.assertEqual((status["status"], status["reason"], status["payload"]),
                         ("unavailable", "voice_not_ready", {}))
        self.assertEqual(unavailable.handle(self.request("session.status", {}, "voice-status"), self.context), status)
        sdp = "readiness-offer"
        ticket = "readiness-ticket"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        raw = self.request("voice.offer", {"sdp": sdp}, "readiness-effect")
        first = unavailable.handle(raw, context)
        self.assertEqual(first, unavailable.handle(raw, context))
        self.assertEqual((first["status"], first["reason"], first["payload"]),
                         ("unavailable", "voice_not_ready", {}))
        self.assertEqual(unavailable._active_resources, {})

    def test_offer_consumes_server_ticket_once_and_exact_retry_replays_receipt(self):
        sdp = "synthetic offer canary"
        ticket = "server-only-ticket"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        raw = self.request("voice.offer", {"sdp": sdp})
        receipt = self.service.handle(raw, context)
        self.assertEqual((receipt["status"], receipt["reason"]), ("ok", "none"))
        self.assertEqual(set(receipt["payload"]), {"peer_id", "sdp"})
        self.assertEqual(self.service.handle(raw, context), receipt)
        self.assertNotIn(sdp, repr(self.service._active_resources))

    def test_request_id_digest_conflict_and_capacity_are_closed(self):
        sdp, ticket = "offer", "ticket"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        first = self.service.handle(self.request("voice.offer", {"sdp": sdp}), context)
        conflict = self.service.handle(self.request("voice.offer", {"sdp": "changed"}), context)
        self.assertEqual((conflict["status"], conflict["reason"]), ("denied", "request_conflict"))
        bounded = PhoneRemoteService(self.store, FakeContextVerifier(), self.media, clock=FakeClockGate(2),
                                     ledger_per_binding=1, ledger_total=1)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(bounded.handle(self.request("session.status", {}, request_id="one"), self.context)["status"], "ok")
        capacity = bounded.handle(self.request("session.status", {}, request_id="other"), self.context)
        self.assertEqual((capacity["status"], capacity["reason"]), ("denied", "request_capacity"))
        self.store.revoke_session(identity=self.identity, session_id="session", owner_id="alice")
        renewed = self.store.login(identity=self.identity, session_id="session", grant_id="grant",
            owner_id="alice", now=2, expires_at=100)
        renewed_context = TrustedRequestContext(self.identity, "alice", "session", "dev", renewed)
        self.assertEqual(bounded.handle(self.request("session.status", {}, request_id="renewed"), renewed_context)["status"], "ok")
        self.assertEqual(len(bounded._ledger), 1)  # old incarnation retired only after store proof

    def test_raw_rollbackable_row_absence_does_not_retire_ledger_receipt(self):
        media = CountingMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        before = sqlite3.connect(":memory:")
        self.db.backup(before)
        inc_a = self.store.login(identity=self.identity, session_id="session-a", grant_id="grant",
            owner_id="alice", now=2, expires_at=100)
        context_a = TrustedRequestContext(self.identity, "alice", "session-a", "dev", inc_a)
        binding_a = self.store.current_binding(identity=self.identity, owner_id="alice",
            session_id="session-a", device_id="dev", login_incarnation=inc_a, now=2)
        after = sqlite3.connect(":memory:")
        self.db.backup(after)
        sdp, request_id = "rollback offer", "rollback-replay"
        request = self.request("voice.offer", {"sdp": sdp}, request_id)
        self.store.issue_ticket(identity=self.identity, ticket_id="first-rollback-ticket",
            session_id="session-a", owner_id="alice", purpose="offer",
            payload_digest=hashlib.sha256(sdp.encode()).hexdigest(), now=2, expires_at=20)
        first_context = TrustedRequestContext(self.identity, "alice", "session-a", "dev", inc_a,
            "first-rollback-ticket")
        first = service.handle(request, first_context)
        peer = first["payload"]["peer_id"]
        self.assertEqual(service.handle(self.request("voice.end", {"peer_id": peer}, "rollback-end"),
            context_a)["status"], "ok")
        before.backup(self.db)
        status_b = service.handle(self.request("session.status", {}, "trigger-prune"), self.context)
        self.assertEqual(status_b["status"], "ok")
        key = (service._binding_key(binding_a), request_id)
        self.assertIn(key, service._ledger)
        after.backup(self.db)
        self.store.issue_ticket(identity=self.identity, ticket_id="second-rollback-ticket",
            session_id="session-a", owner_id="alice", purpose="offer",
            payload_digest=hashlib.sha256(sdp.encode()).hexdigest(), now=2, expires_at=20)
        replay = service.handle(request, TrustedRequestContext(self.identity, "alice", "session-a",
            "dev", inc_a, "second-rollback-ticket"))
        self.assertEqual((replay["status"], replay["reason"]), ("denied", "not_authorized"))
        self.assertEqual(media.calls, 1)
        self.assertNotIn(peer, service._peers)

    def test_invalid_fake_media_success_dto_is_rejected_before_publication(self):
        media = InvalidResponseMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="invalid-dto-ticket", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"offer").hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation,
            "invalid-dto-ticket")
        result = service.handle(self.request("voice.offer", {"sdp": "offer"}, "invalid-dto"), context)
        self.assertEqual((result["status"], result["reason"], result["payload"]),
                         ("unavailable", "voice_not_ready", {}))
        self.assertEqual(service._peers, {})
        self.assertEqual(service._active_resources, {})

    def test_invalid_adapter_alias_abort_cannot_close_existing_peer(self):
        media = AliasInvalidMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        first, _, _ = self._offer(service=service, media=media, ticket="alias-existing",
                                  request_id="alias-existing")
        peer_id = first["payload"]["peer_id"]
        media.alias = peer_id
        sdp = "bad alias"
        self.store.issue_ticket(identity=self.identity, ticket_id="alias-invalid-ticket",
            session_id="session", owner_id="alice", purpose="offer",
            payload_digest=hashlib.sha256(sdp.encode()).hexdigest(), now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation,
                                        "alias-invalid-ticket")
        result = service.handle(self.request("voice.offer", {"sdp": sdp}, "alias-invalid-request"), context)
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "voice_not_ready"))
        self.assertIn(peer_id, service._peers)
        self.assertIn(peer_id, service._active_resources)
        self.assertEqual(service._pending_media, {})

    def test_revocation_fences_peer_and_fake_clock_closes_it(self):
        sdp, ticket = "offer", "ticket"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        receipt = self.service.handle(self.request("voice.offer", {"sdp": sdp}), context)
        peer = receipt["payload"]["peer_id"]
        self.store.revoke_grant(identity=self.identity, grant_id="grant", owner_id="alice")
        self.assertFalse(self.store.binding_current(self.service._peers[peer]["binding"], now=3))
        self.clock.set_time(6.9)  # four-point-nine fake seconds after revoke
        self.assertEqual(self.service.tick(), 1)
        self.assertNotIn(peer, self.service._active_resources)

    def _offer(self, sdp="offer", request_id="offer-req", service=None, media=None, ticket="offer-ticket"):
        media = media or self.media
        service = service or self.service
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        raw = self.request("voice.offer", {"sdp": sdp}, request_id)
        return service.handle(raw, context), context, raw

    def test_every_enabled_operation_uses_the_same_binding_ledger(self):
        status = self.request("session.status", {}, "replay")
        first = self.service.handle(status, self.context)
        self.assertEqual(self.service.handle(status, self.context), first)
        conflict = self.request("call.state", {}, "replay")
        denied = self.service.handle(conflict, self.context)
        self.assertEqual((denied["status"], denied["reason"]), ("denied", "request_conflict"))
        deferred = self.request("results.snapshot", {}, "later")
        receipt = self.service.handle(deferred, self.context)
        self.assertEqual((receipt["status"], receipt["reason"]), ("unavailable", "operation_unavailable"))
        self.assertEqual(self.service.handle(deferred, self.context), receipt)

    def test_voice_end_uses_replay_ledger_and_keeps_idempotent_receipt(self):
        offer, _, _ = self._offer(ticket="end-ticket")
        peer_id = offer["payload"]["peer_id"]
        end = self.request("voice.end", {"peer_id": peer_id}, "end-once")
        first = self.service.handle(end, self.context)
        self.assertEqual((first["status"], first["payload"]),
                         ("ok", {"peer_id": peer_id, "ended": True}))
        self.assertEqual(self.service.handle(end, self.context), first)
        conflict = self.request("voice.end", {"peer_id": "other-peer"}, "end-once")
        result = self.service.handle(conflict, self.context)
        self.assertEqual((result["status"], result["reason"]), ("denied", "request_conflict"))

    def test_concurrent_exact_retry_has_one_media_effect(self):
        media = BlockingMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="race-ticket", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"race").hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, "race-ticket")
        raw = self.request("voice.offer", {"sdp": "race"}, "same-race")
        result = []
        thread = threading.Thread(target=lambda: result.append(service.handle(raw, context)))
        thread.start()
        self.assertTrue(media.started.wait(2))
        retry = service.handle(raw, context)
        self.assertEqual((retry["status"], retry["reason"]), ("denied", "request_conflict"))
        media.release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(media.calls, 1)
        self.assertEqual(result[0]["status"], "ok")

    def test_concurrent_offers_linearize_to_one_owner_lease(self):
        media = BarrierOffersMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        contexts, raws = [], []
        for i, sdp in enumerate(("offer-a", "offer-b")):
            ticket = f"barrier-offer-{i}"
            self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
                owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
                now=2, expires_at=20)
            contexts.append(TrustedRequestContext(self.identity, "alice", "session", "dev",
                self.incarnation, ticket))
            raws.append(self.request("voice.offer", {"sdp": sdp}, f"barrier-request-{i}"))
        results = []
        threads = [threading.Thread(target=lambda i=i: results.append(service.handle(raws[i], contexts[i])))
                   for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(result["status"] for result in results), ["ok", "unavailable"])
        self.assertEqual(len(service._peers), 1)
        peer_id = next(iter(service._peers))
        self.assertEqual(service._owner_lease["alice"], peer_id)
        self.assertEqual(set(service._active_resources), {peer_id})
        self.assertEqual(service._pending_media, {})

    def test_update_prepared_before_voice_end_cannot_resurrect_ended_peer(self):
        media = UpdateBlockingMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="race-update-offer", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"offer").hexdigest(),
            now=2, expires_at=20)
        offer_context = TrustedRequestContext(self.identity, "alice", "session", "dev",
            self.incarnation, "race-update-offer")
        offered = service.handle(self.request("voice.offer", {"sdp": "offer"}, "race-update-offer"), offer_context)
        peer_id = offered["payload"]["peer_id"]
        sdp, ticket = "update", "blocked-update-ticket"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="update", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20, peer_id=peer_id)
        update_context = TrustedRequestContext(self.identity, "alice", "session", "dev",
            self.incarnation, ticket)
        media.block_updates = True
        result = []
        thread = threading.Thread(target=lambda: result.append(service.handle(
            self.request("voice.update", {"peer_id": peer_id, "sdp": sdp}, "blocked-update"), update_context)))
        thread.start()
        self.assertTrue(media.started.wait(2))
        ended = service.handle(self.request("voice.end", {"peer_id": peer_id}, "end-during-update"), self.context)
        self.assertEqual(ended["status"], "ok")
        media.release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]["status"], "denied")
        self.assertNotIn(peer_id, service._peers)
        self.assertNotIn(peer_id, service._owner_lease.values())
        self.assertNotIn(peer_id, self.service._active_resources)

    def test_media_failure_receipt_is_terminal_and_never_retries_media(self):
        media = FailingMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="fail-ticket", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"fail").hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, "fail-ticket")
        raw = self.request("voice.offer", {"sdp": "fail"}, "terminal-failure")
        first = service.handle(raw, context)
        second = service.handle(raw, context)
        self.assertEqual(first, second)
        self.assertEqual((first["status"], first["reason"]), ("unavailable", "voice_not_ready"))
        self.assertEqual(media.calls, 1)
        self.assertNotIn("content canary", repr(first))

    def test_revoke_after_media_prepare_before_commit_cleans_up(self):
        media = BlockingMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="race-revoke", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"race").hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, "race-revoke")
        raw = self.request("voice.offer", {"sdp": "race"}, "revoke-before-commit")
        result = []
        thread = threading.Thread(target=lambda: result.append(service.handle(raw, context)))
        thread.start()
        self.assertTrue(media.started.wait(2))
        self.store.revoke_grant(identity=self.identity, grant_id="grant", owner_id="alice")
        media.release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]["status"], "denied")
        self.assertEqual(service._peers, {})
        self.assertEqual(service._active_resources, {})

    def test_output_is_bounded_private_and_revocation_cancels_before_dequeue(self):
        sink = FakeBoundedSink(capacity=1)
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, output_sink=sink, output_policy=FakeOutputPolicy())
        receipt, _, _ = self._offer(service=service, ticket="output-ticket")
        peer = receipt["payload"]["peer_id"]
        canary = "private-output-canary"
        output = {"classification": "approved_shared", "destination_granted": True, "content": canary}
        self.assertTrue(service.emit_output(peer, output))
        self.assertFalse(service.emit_output(peer, output))  # bounded, no blocking
        self.store.revoke_grant(identity=self.identity, grant_id="grant", owner_id="alice")
        self.assertFalse(service.emit_output(peer, output))  # immediate authority check
        refused = service.handle(self.request("voice.end", {"peer_id": peer}, "post-revoke-command"), self.context)
        self.assertEqual((refused["status"], refused["reason"]), ("denied", "not_authorized"))
        self.assertEqual(service.notify_revocation(), 1)
        self.assertEqual(len(sink), 0)
        self.assertIsNone(service.drain_output())
        self.assertNotIn(canary, repr(service._ledger))

    def test_output_policy_denies_unknown_or_protected_content_without_canary_leak(self):
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, output_sink=FakeBoundedSink(), output_policy=FakeOutputPolicy())
        receipt, _, _ = self._offer(service=service, ticket="deny-output-ticket")
        peer = receipt["payload"]["peer_id"]
        canary = "protected-output-canary"
        self.assertFalse(service.emit_output(peer, {"classification": "legacy_protected",
            "destination_granted": False, "content": canary}))
        self.assertFalse(service.emit_output(peer, {"classification": "unknown",
            "destination_granted": True, "content": canary}))
        self.assertEqual(len(service.output_sink), 0)
        self.assertNotIn(canary, repr(service._ledger))

    def test_live_feature_off_and_owner_unavailability_fence_output_and_close_leases(self):
        for mode in ("feature_off", "owner_busy"):
            with self.subTest(mode=mode):
                available = FakeOwnerAvailabilityGate()
                service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                    clock=self.clock, owner_available=available,
                    output_sink=FakeBoundedSink(), output_policy=FakeOutputPolicy())
                offer, _, _ = self._offer(service=service, ticket=f"{mode}-ticket")
                peer = offer["payload"]["peer_id"]
                output = {"classification": "approved_shared", "destination_granted": True,
                          "content": "queued before gate"}
                self.assertTrue(service.emit_output(peer, output))
                if mode == "feature_off":
                    service.enabled = False
                    self.assertFalse(service.emit_output(peer, output))
                    self.assertIsNone(service.drain_output())
                else:
                    available.set_available(False)
                    self.assertIsNone(service.drain_output())
                self.assertNotIn(peer, service._peers)
                self.assertNotIn(peer, self.service._active_resources)
                self.assertEqual(len(service.output_sink), 0)

    def test_availability_change_before_peer_and_output_commit_wins(self):
        # The test gate pauses before taking its lock. set_available therefore
        # linearizes before the commit snapshot; no arbitrary callback runs under lock.
        for operation in ("offer", "enqueue", "drain"):
            with self.subTest(operation=operation):
                gate = FakeOwnerAvailabilityGate()
                sink = FakeBoundedSink()
                service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                    clock=self.clock, owner_available=gate,
                    output_sink=sink, output_policy=FakeOutputPolicy())
                if operation == "offer":
                    self.store.issue_ticket(identity=self.identity, ticket_id=f"gate-{operation}",
                        session_id="session", owner_id="alice", purpose="offer",
                        payload_digest=hashlib.sha256(b"offer").hexdigest(), now=2, expires_at=20)
                    context = TrustedRequestContext(self.identity, "alice", "session", "dev",
                        self.incarnation, f"gate-{operation}")
                    raw = self.request("voice.offer", {"sdp": "offer"}, f"gate-{operation}")
                    action = lambda: service.handle(raw, context)
                else:
                    offered, _, _ = self._offer(service=service, ticket=f"gate-base-{operation}")
                    peer = offered["payload"]["peer_id"]
                    output = {"classification": "approved_shared", "destination_granted": True,
                              "content": "gate canary"}
                    if operation == "enqueue":
                        action = lambda: service.emit_output(peer, output)
                    else:
                        self.assertTrue(service.emit_output(peer, output))
                        action = service.drain_output
                arrived, release = threading.Event(), threading.Event()
                gate.pause_before_commit(f"gate-{operation}", arrived, release)
                result = []
                thread = threading.Thread(name=f"gate-{operation}", target=lambda: result.append(action()))
                thread.start()
                self.assertTrue(arrived.wait(2))
                gate.set_available(False)
                release.set()
                thread.join(3)
                self.assertFalse(thread.is_alive())
                if operation == "offer":
                    self.assertEqual((result[0]["status"], result[0]["reason"]),
                                     ("unavailable", "owner_busy"))
                elif operation == "enqueue":
                    self.assertEqual(result, [False])
                else:
                    self.assertEqual(result, [None])
                self.assertEqual(len(sink), 0)
                self.assertEqual(service._peers, {})
                self.assertEqual(self.service._active_resources, {})

    def test_delayed_duplicate_end_cannot_remove_newer_owner_lease(self):
        offered, _, _ = self._offer(ticket="end-race-offer")
        old_peer = offered["payload"]["peer_id"]
        arrived, release = threading.Event(), threading.Event()
        self.service.owner_available.pause_before_commit("delayed-end", arrived, release)
        delayed = []
        thread = threading.Thread(name="delayed-end", target=lambda: delayed.append(
            self.service.handle(self.request("voice.end", {"peer_id": old_peer}, "delayed-end"), self.context)))
        thread.start()
        self.assertTrue(arrived.wait(2))
        self.assertEqual(self.service.handle(self.request("voice.end", {"peer_id": old_peer}, "first-end"),
                                             self.context)["status"], "ok")
        newer, _, _ = self._offer(ticket="end-race-new", request_id="end-race-new")
        new_peer = newer["payload"]["peer_id"]
        self.assertEqual(self.service._owner_lease.get("alice"), new_peer)
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(delayed[0]["status"], "ok")
        self.assertIn(new_peer, self.service._peers)
        self.assertEqual(self.service._owner_lease.get("alice"), new_peer)
        third, _, _ = self._offer(ticket="end-race-third", request_id="end-race-third")
        self.assertEqual((third["status"], third["reason"]), ("unavailable", "owner_busy"))

    def test_delayed_end_closes_same_binding_peer_after_update_wins(self):
        offered, _, _ = self._offer(ticket="end-update-offer", request_id="end-update-offer")
        peer_id = offered["payload"]["peer_id"]
        arrived, release = threading.Event(), threading.Event()
        self.service.owner_available.pause_before_commit("end-update-delayed", arrived, release)
        ended = []
        thread = threading.Thread(name="end-update-delayed", target=lambda: ended.append(
            self.service.handle(self.request("voice.end", {"peer_id": peer_id}, "end-update-delayed"),
                                self.context)))
        thread.start()
        self.assertTrue(arrived.wait(2))
        update_sdp = "update before end"
        self.store.issue_ticket(identity=self.identity, ticket_id="end-update-ticket", session_id="session",
            owner_id="alice", purpose="update", payload_digest=hashlib.sha256(update_sdp.encode()).hexdigest(),
            now=2, expires_at=20, peer_id=peer_id)
        update_context = TrustedRequestContext(self.identity, "alice", "session", "dev",
            self.incarnation, "end-update-ticket")
        updated = self.service.handle(self.request("voice.update",
            {"peer_id": peer_id, "sdp": update_sdp}, "update-before-end"), update_context)
        self.assertEqual(updated["status"], "ok")
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual((ended[0]["status"], ended[0]["payload"]["ended"]), ("ok", True))
        self.assertNotIn(peer_id, self.service._peers)
        self.assertNotIn(peer_id, self.service._owner_lease.values())
        self.assertNotIn(peer_id, self.service._active_resources)

    def test_delayed_end_does_not_close_new_same_binding_resource_with_reused_id(self):
        media = AliasMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        first, _, _ = self._offer(service=service, media=media, ticket="reuse-first",
                                  request_id="reuse-first")
        peer_id = first["payload"]["peer_id"]
        arrived, release = threading.Event(), threading.Event()
        service.owner_available.pause_before_commit("reuse-delayed-end", arrived, release)
        delayed = []
        thread = threading.Thread(name="reuse-delayed-end", target=lambda: delayed.append(
            service.handle(self.request("voice.end", {"peer_id": peer_id}, "reuse-delayed-end"),
                           self.context)))
        thread.start()
        self.assertTrue(arrived.wait(2))
        self.assertEqual(service.handle(self.request("voice.end", {"peer_id": peer_id}, "reuse-first-end"),
                                        self.context)["status"], "ok")
        media.alias = peer_id
        second, _, _ = self._offer(service=service, media=media, ticket="reuse-second",
                                   request_id="reuse-second")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["payload"]["peer_id"], peer_id)
        second_resource = service._peers[peer_id]["resource"]
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual((delayed[0]["status"], delayed[0]["reason"]), ("denied", "not_authorized"))
        self.assertIs(service._peers[peer_id]["resource"], second_resource)
        self.assertEqual(service._owner_lease.get("alice"), peer_id)
        self.assertIs(service._active_resources[peer_id], second_resource)

    def test_cached_voice_readiness_change_revoke_linearizes_before_receipt(self):
        readiness = FakeReadinessGate()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, voice_ready=readiness)
        offer, context, raw = self._offer(service=service, ticket="readiness-revoke-ticket",
            request_id="readiness-revoke")
        self.assertEqual(offer["status"], "ok")
        arrived, release = threading.Event(), threading.Event()
        readiness.pause_before_commit("cached-readiness", arrived, release)
        responses = []
        thread = threading.Thread(name="cached-readiness", target=lambda: responses.append(
            service.handle(raw, context)))
        thread.start()
        self.assertTrue(arrived.wait(2))
        self.store.revoke_grant(identity=self.identity, grant_id="grant", owner_id="alice")
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual((responses[0]["status"], responses[0]["reason"]),
                         ("denied", "not_authorized"))
        self.assertNotEqual(responses[0], offer)

    def test_injected_adapter_commit_callback_never_runs_under_locks(self):
        media = BlockingCommitMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="no-adapter-commit", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"offer").hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation,
                                        "no-adapter-commit")
        result = []
        thread = threading.Thread(target=lambda: result.append(service.handle(
            self.request("voice.offer", {"sdp": "offer"}, "no-adapter-commit"), context)))
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive(), "service must not invoke injectable commit callback")
        self.assertEqual(result[0]["status"], "ok")
        self.assertFalse(media.commit_called.is_set())
        completed = threading.Event()
        revoke = threading.Thread(target=lambda: (self.store.revoke_grant(identity=self.identity,
            grant_id="grant", owner_id="alice"), completed.set()))
        revoke.start()
        revoke.join(2)
        self.assertFalse(revoke.is_alive())
        self.assertTrue(completed.is_set())
        self.assertEqual(service.tick(), 1)
        self.assertEqual(service._peers, {})

    def test_exact_retries_revalidate_readiness_and_live_lease(self):
        voice_ready = FakeReadinessGate()
        gate = FakeOwnerAvailabilityGate()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, owner_available=gate, voice_ready=voice_ready)
        status_raw = self.request("session.status", {}, "cached-status")
        first_status = service.handle(status_raw, self.context)
        self.assertEqual(first_status["status"], "ok")
        gate.set_available(False)
        owner_refusal = service.handle(status_raw, self.context)
        self.assertEqual((owner_refusal["status"], owner_refusal["reason"]),
                         ("unavailable", "owner_busy"))
        gate.set_available(True)
        voice_ready.set_ready(False)
        self.assertEqual((service.handle(status_raw, self.context)["status"],
                          service.handle(status_raw, self.context)["reason"]),
                         ("unavailable", "voice_not_ready"))
        voice_ready.set_ready(True)
        offer, context, raw = self._offer(service=service, ticket="cached-offer",
                                          request_id="cached-voice")
        peer = offer["payload"]["peer_id"]
        voice_ready.set_ready(False)
        stale_readiness = service.handle(raw, context)
        self.assertEqual((stale_readiness["status"], stale_readiness["reason"]),
                         ("unavailable", "voice_not_ready"))
        voice_ready.set_ready(True)
        self.assertEqual(service.handle(self.request("voice.end", {"peer_id": peer}, "cached-end"),
                                        context)["status"], "ok")
        stale = service.handle(raw, context)
        self.assertEqual((stale["status"], stale["reason"]), ("denied", "not_authorized"))
        self.assertNotIn(peer, service._peers)

    def test_clock_expiry_is_rechecked_at_every_commit_and_delivery(self):
        for mode in ("status", "offer", "enqueue", "drain", "cached"):
            with self.subTest(mode=mode):
                clock = FakeClockGate(2)
                sink = FakeBoundedSink()
                service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                    clock=clock, output_sink=sink, output_policy=FakeOutputPolicy())
                if mode == "status":
                    action = lambda: service.handle(self.request("session.status", {}, "expiry-status"),
                                                     self.context)
                elif mode == "offer":
                    self.store.issue_ticket(identity=self.identity, ticket_id="expiry-offer-ticket",
                        session_id="session", owner_id="alice", purpose="offer",
                        payload_digest=hashlib.sha256(b"offer").hexdigest(), now=2, expires_at=20)
                    context = TrustedRequestContext(self.identity, "alice", "session", "dev",
                        self.incarnation, "expiry-offer-ticket")
                    action = lambda: service.handle(self.request("voice.offer", {"sdp": "offer"},
                        "expiry-offer"), context)
                else:
                    first, context, raw = self._offer(service=service, ticket=f"expiry-base-{mode}",
                        request_id=f"expiry-base-{mode}")
                    peer = first["payload"]["peer_id"]
                    output = {"classification": "approved_shared", "destination_granted": True,
                              "content": "must not cross expiry"}
                    if mode == "enqueue":
                        action = lambda: service.emit_output(peer, output)
                    elif mode == "drain":
                        self.assertTrue(service.emit_output(peer, output))
                        action = service.drain_output
                    else:
                        action = lambda: service.handle(raw, context)
                arrived, release = threading.Event(), threading.Event()
                clock.pause_before_commit(f"expiry-{mode}", arrived, release)
                result = []
                thread = threading.Thread(name=f"expiry-{mode}", target=lambda: result.append(action()))
                thread.start()
                self.assertTrue(arrived.wait(2))
                clock.set_time(100)  # session expires while final commit waits outside clock lock
                release.set()
                thread.join(3)
                self.assertFalse(thread.is_alive())
                if mode in {"status", "offer", "cached"}:
                    self.assertEqual((result[0]["status"], result[0]["reason"]),
                                     ("denied", "not_authorized"))
                elif mode == "enqueue":
                    self.assertEqual(result, [False])
                    self.assertEqual(len(sink), 0)
                else:
                    self.assertEqual(result, [None])
                    self.assertEqual(len(sink), 0)
                service.tick()
                clock.set_time(2)

    def test_malformed_attempt_token_and_peer_keys_never_hash_in_commit(self):
        for media in (HashTokenMedia(), HashPeerMedia()):
            with self.subTest(media=type(media).__name__):
                service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
                self.store.issue_ticket(identity=self.identity, ticket_id=f"bad-{type(media).__name__}",
                    session_id="session", owner_id="alice", purpose="offer",
                    payload_digest=hashlib.sha256(b"offer").hexdigest(), now=2, expires_at=20)
                context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation,
                    f"bad-{type(media).__name__}")
                result = service.handle(self.request("voice.offer", {"sdp": "offer"},
                    f"bad-{type(media).__name__}"), context)
                self.assertEqual((result["status"], result["reason"]),
                                 ("unavailable", "voice_not_ready"))
                self.assertEqual(service._pending_media, {})
                self.assertEqual(service._active_resources, {})
                if isinstance(media, HashTokenMedia):
                    self.assertEqual(media.token.calls, 0)
                else:
                    self.assertEqual(media.peer.calls, 0)

    def test_offer_rejects_update_mode_and_missing_resource_preparations(self):
        media = GhostMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=self.clock)
        self.store.issue_ticket(identity=self.identity, ticket_id="ghost-ticket", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(b"offer").hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation,
                                        "ghost-ticket")
        result = service.handle(self.request("voice.offer", {"sdp": "offer"}, "ghost-request"), context)
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "voice_not_ready"))
        self.assertEqual(service._peers, {})
        self.assertEqual(service._active_resources, {})
        self.assertEqual(service._pending_media, {})

    def test_shared_store_facades_share_owner_lease_and_weak_lifetime_cleanup(self):
        second = PhoneRemoteService(self.store, FakeContextVerifier(), self.media, clock=self.clock,
            owner_available=self.service.owner_available, voice_ready=self.service.voice_ready)
        first, _, _ = self._offer(service=self.service, ticket="shared-first", request_id="shared-first")
        self.assertEqual(first["status"], "ok")
        blocked, _, _ = self._offer(service=second, ticket="shared-blocked", request_id="shared-blocked")
        self.assertEqual((blocked["status"], blocked["reason"]), ("unavailable", "owner_busy"))
        peer = first["payload"]["peer_id"]
        self.assertEqual(self.service.handle(self.request("voice.end", {"peer_id": peer}, "shared-end"),
                                             self.context)["status"], "ok")
        after_end, _, _ = self._offer(service=second, ticket="shared-after-end", request_id="shared-after-end")
        self.assertEqual(after_end["status"], "ok")
        second_peer = after_end["payload"]["peer_id"]
        second.handle(self.request("voice.end", {"peer_id": second_peer}, "shared-end-second"), self.context)
        transient = PhoneRemoteService(self.store, FakeContextVerifier(), self.media, clock=self.clock,
            owner_available=self.service.owner_available, voice_ready=self.service.voice_ready)
        orphaned, _, _ = self._offer(service=transient, ticket="weak-owner", request_id="weak-owner")
        self.assertEqual(orphaned["status"], "ok")
        del transient
        gc.collect()
        replacement, _, _ = self._offer(service=second, ticket="weak-replacement", request_id="weak-replacement")
        self.assertEqual(replacement["status"], "ok")

    def test_owner_lease_is_not_preempted_and_update_requires_live_peer(self):
        first, _, _ = self._offer(service=self.service, ticket="lease-first")
        peer = first["payload"]["peer_id"]
        second_sdp = "second offer"
        self.store.issue_ticket(identity=self.identity, ticket_id="lease-second", session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(second_sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        second_context = TrustedRequestContext(self.identity, "alice", "session", "dev",
            self.incarnation, "lease-second")
        second = self.service.handle(self.request("voice.offer", {"sdp": second_sdp}, "second-offer"), second_context)
        self.assertEqual((second["status"], second["reason"]), ("unavailable", "owner_busy"))
        self.assertIn(peer, self.service._peers)
        update_sdp = "update"
        self.store.issue_ticket(identity=self.identity, ticket_id="bad-update", session_id="session",
            owner_id="alice", purpose="update", payload_digest=hashlib.sha256(update_sdp.encode()).hexdigest(),
            now=2, expires_at=20, peer_id="stale-peer")
        update_context = TrustedRequestContext(self.identity, "alice", "session", "dev",
            self.incarnation, "bad-update")
        update = self.service.handle(self.request("voice.update",
            {"peer_id": "stale-peer", "sdp": update_sdp}, "stale-update"), update_context)
        self.assertEqual((update["status"], update["reason"]), ("denied", "not_authorized"))
        self.assertIn(peer, self.service._peers)

    def test_update_ticket_is_purpose_bound_to_the_full_live_peer(self):
        offer, _, _ = self._offer(ticket="update-offer")
        peer = offer["payload"]["peer_id"]
        sdp = "updated offer"
        ticket = "valid-update"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="update", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20, peer_id=peer)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        result = self.service.handle(self.request("voice.update", {"peer_id": peer, "sdp": sdp}, "update-ok"), context)
        self.assertEqual((result["status"], result["reason"]), ("ok", "none"))
        self.assertEqual(result["payload"]["peer_id"], peer)
        self.assertEqual(set(result["payload"]), {"peer_id", "sdp"})

    def test_authenticated_binding_rejects_other_owner_or_device(self):
        wrong_owner = TrustedRequestContext(ClientIdentity(name="fake", user_id="bob"),
            "bob", "session", "dev", self.incarnation)
        result = self.service.handle(self.request("session.status", {}), wrong_owner)
        self.assertEqual((result["status"], result["reason"]), ("denied", "not_authorized"))
        wrong_device = TrustedRequestContext(self.identity, "alice", "session", "other-device", self.incarnation)
        result = self.service.handle(self.request("session.status", {}, "wrong-device"), wrong_device)
        self.assertEqual((result["status"], result["reason"]), ("denied", "not_authorized"))

    def test_same_owner_different_device_and_grant_cannot_control_existing_peer(self):
        self.store.add_device(identity=self.identity, device_id="dev-b", owner_id="alice",
                              public_key=b"public-b", key_algorithm="test")
        self.store.add_grant(identity=self.identity, grant_id="grant-b", device_id="dev-b",
                             owner_id="alice", scopes=["read", "voice"])
        self.incarnation = self.store.login(identity=self.identity, session_id="session", grant_id="grant",
            owner_id="alice", now=2, expires_at=100)
        self.context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation)
        offer, _, _ = self._offer(ticket="owner-a-ticket")
        peer = offer["payload"]["peer_id"]
        inc_b = self.store.login(identity=self.identity, session_id="session-b", grant_id="grant-b",
            owner_id="alice", now=2, expires_at=100)
        context_b = TrustedRequestContext(self.identity, "alice", "session-b", "dev-b", inc_b)
        result = self.service.handle(self.request("voice.end", {"peer_id": peer}, "cross-grant-end"), context_b)
        self.assertEqual((result["status"], result["reason"]), ("denied", "not_authorized"))
        self.assertIn(peer, self.service._peers)

    def test_session_signout_immediately_denies_peer_commands_and_output_but_not_other_session(self):
        sink = FakeBoundedSink()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, output_sink=sink, output_policy=FakeOutputPolicy())
        offer, _, _ = self._offer(service=service, ticket="scoped-signout-ticket")
        peer = offer["payload"]["peer_id"]
        self.assertTrue(service.emit_output(peer, {"classification": "approved_shared",
            "destination_granted": True, "content": "queued"}))
        self.store.login(identity=self.identity, session_id="session-b", grant_id="grant",
            owner_id="alice", now=2, expires_at=100)
        global_before = self.store.status()["host_generation"]
        self.store.revoke_session(identity=self.identity, session_id="session", owner_id="alice")
        self.assertEqual(self.store.status()["host_generation"], global_before)
        self.assertFalse(service.emit_output(peer, {"classification": "approved_shared",
            "destination_granted": True, "content": "after revoke"}))
        denied = service.handle(self.request("voice.end", {"peer_id": peer}, "signed-out-command"), self.context)
        self.assertEqual((denied["status"], denied["reason"]), ("denied", "not_authorized"))
        self.assertEqual(service.notify_revocation(), 1)
        self.assertEqual(len(sink), 0)
        row = self.db.execute("SELECT login_incarnation FROM phone_remote_sessions WHERE session_id='session-b'").fetchone()
        fresh = TrustedRequestContext(self.identity, "alice", "session-b", "dev", row[0])
        self.assertEqual(service.handle(self.request("session.status", {}, "session-b-status"), fresh)["status"], "ok")

    def test_revoke_during_output_preparation_prevents_commit(self):
        started, release = threading.Event(), threading.Event()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=self.clock, output_sink=FakeBoundedSink(),
            output_policy=FakeOutputPolicy((started, release)))
        receipt, _, _ = self._offer(service=service, ticket="output-race-ticket")
        peer = receipt["payload"]["peer_id"]
        result = []
        content = {"classification": "approved_shared", "destination_granted": True, "content": "canary"}
        thread = threading.Thread(target=lambda: result.append(service.emit_output(peer, content)))
        thread.start()
        self.assertTrue(started.wait(2))
        self.store.revoke_grant(identity=self.identity, grant_id="grant", owner_id="alice")
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [False])
        self.assertEqual(len(service.output_sink), 0)


if __name__ == "__main__":
    unittest.main()
