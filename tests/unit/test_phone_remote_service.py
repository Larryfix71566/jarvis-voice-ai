import hashlib
import json
import sqlite3
import unittest

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore
from jarvis.bot.phone_remote_protocol import PROTOCOL
from jarvis.bot.phone_remote_service import (FakeContextVerifier, FakeMediaAdapter,
    PhoneRemoteService, TrustedRequestContext)


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
                                     ledger_per_binding=0)
        self.assertEqual(first["status"], "ok")
        next_ticket = "second-ticket"
        next_context = TrustedRequestContext(self.identity, "alice", "session", "dev", self.incarnation, next_ticket)
        capacity = bounded.handle(self.request("voice.offer", {"sdp": "next"}, request_id="other"), next_context)
        self.assertEqual((capacity["status"], capacity["reason"]), ("denied", "request_capacity"))

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
        self.assertEqual(self.service.tick(), 0)  # under five seconds from last check
        self.now[0] = 7
        self.assertEqual(self.service.tick(), 1)
        self.assertNotIn(peer, self.media.peers)


if __name__ == "__main__":
    unittest.main()
