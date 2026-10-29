import hashlib
import json
import sqlite3
import threading
import unittest

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore
from jarvis.bot.phone_remote_protocol import PROTOCOL
from jarvis.bot.phone_remote_service import (FakeContextVerifier, FakeMediaAdapter,
    FakeBoundedSink, PhoneRemoteService, TrustedRequestContext)


class BlockingMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def prepare(self, sdp, peer_id=None):
        self.calls += 1
        result = super().prepare(sdp, peer_id)
        self.started.set()
        if not self.release.wait(2):
            raise RuntimeError("test barrier timed out")
        return result


class FailingMedia:
    def __init__(self):
        self.calls = 0

    def prepare(self, _sdp, peer_id=None):
        self.calls += 1
        raise RuntimeError("synthetic media failure with content canary")

    def close(self, _peer_id):
        pass


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
        self.now = [2]
        self.media = FakeMediaAdapter()
        self.service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
                                          clock=lambda: self.now[0])
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
                                     enabled=False, clock=lambda: 2)
        result = service.handle(self.request("session.status", {}), object())
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "feature_off"))
        self.assertEqual(self.media.peers, {})

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
        self.assertNotIn(sdp, repr(self.media.peers))

    def test_request_id_digest_conflict_and_capacity_are_closed(self):
        sdp, ticket = "offer", "ticket"
        self.store.issue_ticket(identity=self.identity, ticket_id=ticket, session_id="session",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, ticket)
        first = self.service.handle(self.request("voice.offer", {"sdp": sdp}), context)
        conflict = self.service.handle(self.request("voice.offer", {"sdp": "changed"}), context)
        self.assertEqual((conflict["status"], conflict["reason"]), ("denied", "request_conflict"))
        bounded = PhoneRemoteService(self.store, FakeContextVerifier(), self.media, clock=lambda: 2,
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
        self.now[0] = 6.9  # four-point-nine fake seconds after revoke
        self.assertEqual(self.service.tick(), 1)
        self.assertNotIn(peer, self.media.peers)

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
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=lambda: self.now[0])
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

    def test_media_failure_receipt_is_terminal_and_never_retries_media(self):
        media = FailingMedia()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=lambda: self.now[0])
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
        service = PhoneRemoteService(self.store, FakeContextVerifier(), media, clock=lambda: self.now[0])
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
        self.assertEqual(media.peers, {})

    def test_output_is_bounded_private_and_revocation_cancels_before_dequeue(self):
        sink = FakeBoundedSink(capacity=1)
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=lambda: self.now[0], output_sink=sink, output_policy=FakeOutputPolicy())
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
            clock=lambda: self.now[0], output_sink=FakeBoundedSink(), output_policy=FakeOutputPolicy())
        receipt, _, _ = self._offer(service=service, ticket="deny-output-ticket")
        peer = receipt["payload"]["peer_id"]
        canary = "protected-output-canary"
        self.assertFalse(service.emit_output(peer, {"classification": "legacy_protected",
            "destination_granted": False, "content": canary}))
        self.assertFalse(service.emit_output(peer, {"classification": "unknown",
            "destination_granted": True, "content": canary}))
        self.assertEqual(len(service.output_sink), 0)
        self.assertNotIn(canary, repr(service._ledger))

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

    def test_revoke_during_output_preparation_prevents_commit(self):
        started, release = threading.Event(), threading.Event()
        service = PhoneRemoteService(self.store, FakeContextVerifier(), self.media,
            clock=lambda: self.now[0], output_sink=FakeBoundedSink(),
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
