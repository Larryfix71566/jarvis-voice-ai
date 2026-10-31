"""One combined scoped-signout/raw-restore service-boundary invariant."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore
from jarvis.bot.phone_remote_protocol import PROTOCOL
from jarvis.bot.phone_remote_service import (
    FakeBoundedSink,
    FakeClockGate,
    FakeContextVerifier,
    FakeMediaAdapter,
    PhoneRemoteService,
    TrustedRequestContext,
)


class _CanaryOutputPolicy:
    def prepare(self, value):
        if (type(value) is not dict or value.get("classification") != "approved_shared"
                or value.get("destination_granted") is not True
                or type(value.get("content")) is not str):
            return None
        return value["content"].encode("utf-8")


class ScopedSignoutRestoreBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.anchor = FakeProtectedAnchor("boundary-restore-host")
        self.store = PhoneAdmissionStore(self.db, self.anchor)
        self.identity = ClientIdentity(name="fake", user_id="alice")
        self.store.add_device(identity=self.identity, device_id="device", owner_id="alice",
                              public_key=b"synthetic-public-key", key_algorithm="test")
        self.store.add_grant(identity=self.identity, grant_id="grant", device_id="device",
                             owner_id="alice", scopes=["read", "voice"])
        self.incarnation_a = self.store.login(identity=self.identity, session_id="session-a",
            grant_id="grant", owner_id="alice", now=1, expires_at=100)
        self.incarnation_b = self.store.login(identity=self.identity, session_id="session-b",
            grant_id="grant", owner_id="alice", now=1, expires_at=100)
        self.context_a = TrustedRequestContext(self.identity, "alice", "session-a", "device", self.incarnation_a)
        self.context_b = TrustedRequestContext(self.identity, "alice", "session-b", "device", self.incarnation_b)
        self.sink = FakeBoundedSink(capacity=2)
        self.service = PhoneRemoteService(
            self.store, FakeContextVerifier(), FakeMediaAdapter(), clock=FakeClockGate(2),
            output_sink=self.sink, output_policy=_CanaryOutputPolicy())
        self.temp = tempfile.TemporaryDirectory(prefix="phone-boundary-restore-")

    def tearDown(self):
        self.store._drop_admissions()
        self.db.close()
        self.temp.cleanup()

    @staticmethod
    def _request(operation, payload, request_id):
        return json.dumps({"kind": PROTOCOL, "protocol_version": 1, "request_id": request_id,
                           "operation": operation, "payload": payload}, separators=(",", ":"))

    def test_cached_receipt_and_queued_output_stay_fenced_after_repeated_raw_restore(self):
        sdp = "synthetic-offer-canary"
        self.store.issue_ticket(identity=self.identity, ticket_id="ticket-a", session_id="session-a",
            owner_id="alice", purpose="offer", payload_digest=hashlib.sha256(sdp.encode()).hexdigest(),
            now=2, expires_at=20)
        context_a = TrustedRequestContext(self.identity, "alice", "session-a", "device",
            self.incarnation_a, "ticket-a")
        offer_request = self._request("voice.offer", {"sdp": sdp}, "cached-offer-a")
        first_receipt = self.service.handle(offer_request, context_a)
        self.assertEqual((first_receipt["status"], first_receipt["reason"]), ("ok", "none"))
        peer_id = first_receipt["payload"]["peer_id"]
        # Establish that the successful receipt is cached before signout.
        self.assertEqual(self.service.handle(offer_request, context_a), first_receipt)

        canaries = ("queued-output-canary-one", "queued-output-canary-two")
        for canary in canaries:
            self.assertTrue(self.service.emit_output(peer_id, {
                "classification": "approved_shared", "destination_granted": True, "content": canary,
            }))
        self.assertEqual(len(self.sink), 2)

        snapshot_path = Path(self.temp.name) / "before-session-a-signout.sqlite"
        snapshot = sqlite3.connect(snapshot_path)
        self.db.backup(snapshot)
        snapshot.close()
        self.store.revoke_session(identity=self.identity, session_id="session-a", owner_id="alice")

        for attempt in range(2):
            stale_snapshot = sqlite3.connect(snapshot_path)
            stale_snapshot.backup(self.db)  # Raw SQLite restore; no preparation hook.
            stale_snapshot.close()

            replay = self.service.handle(offer_request, context_a)
            self.assertEqual((replay["status"], replay["reason"], replay["payload"]),
                             ("denied", "not_authorized", {}))

            unaffected = self.service.handle(
                self._request("session.status", {}, f"session-b-status-{attempt}"), self.context_b)
            self.assertEqual((unaffected["status"], unaffected["reason"], unaffected["payload"]),
                             ("ok", "none", {"readiness": "ready"}))

            # The queued canary is discarded at the dequeue boundary, never emitted.
            self.assertIsNone(self.service.drain_output())
            self.assertEqual(len(self.sink), 1 - attempt)

        self.assertEqual(self.service.tick(), 1)
        self.assertIsNone(self.service.drain_output())
        self.assertEqual(len(self.sink), 0)


if __name__ == "__main__":
    unittest.main()
