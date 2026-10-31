"""Disposable SQLite/fake-anchor contract tests; no real services or keys."""
import os
import hashlib
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from contextlib import contextmanager

from jarvis.bot.phone_admission_store import (
    FakeProtectedAnchor, PhoneAdmissionStore, StoreDenied, StoreUnavailable, SCHEMA_SQL,
    RESTORE_RECEIPT_SQL,
)
from jarvis.auth import ClientIdentity


def identity(owner="alice"):
    return ClientIdentity(name="verified-test", user_id=owner)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "authority.sqlite")
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.anchor = FakeProtectedAnchor()
        self.store = PhoneAdmissionStore(self.db, self.anchor)

    def tearDown(self):
        self.store._drop_admissions()
        self.db.close()
        self.tmp.cleanup()

    def seed(self):
        self.store.add_device(identity=identity(), device_id="d-a", owner_id="alice", public_key=b"public-a",
                              key_algorithm="test-ed25519")
        self.store.add_grant(identity=identity(), grant_id="g-a", device_id="d-a", owner_id="alice",
                             scopes=["read", "voice"])

    def login(self, session="s-a", owner="alice", grant="g-a"):
        return self.store.login(identity=identity(owner), session_id=session, grant_id=grant, owner_id=owner,
                                now=1, expires_at=100)

    def ticket(self, incarnation, ticket="t-a", session="s-a", owner="alice"):
        self.store.issue_ticket(identity=identity(owner), ticket_id=ticket, session_id=session, owner_id=owner,
                                purpose="offer", payload_digest="sha256:offer",
                                now=2, expires_at=20)

    def test_fresh_schema_is_idempotent_and_only_disposable(self):
        self.assertEqual(self.store.status(), {"schema_version": 1,
                         "host_generation": 1, "login_counter": 0})
        again = PhoneAdmissionStore(self.db, self.anchor)
        self.assertEqual(again.status(), self.store.status())
        names = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"phone_remote_meta", "phone_remote_devices",
                         "phone_remote_grants", "phone_remote_sessions"} <= names)
        self.assertNotIn("phone_remote_tickets", names)
        self.assertFalse(any("private" in n for n in names))
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(phone_remote_devices)")}
        self.assertIn("public_key", columns)
        self.assertNotIn("private_key", columns)

    def test_schema_v2_receipt_is_validated_and_preserved_by_normal_authority_operations(self):
        self.seed()
        receipt = ("restore-test", "host-test", 2, "a" * 64, "b" * 64, "c" * 64, 1)
        self.db.execute(RESTORE_RECEIPT_SQL)
        self.db.execute("INSERT INTO phone_remote_restore_receipt VALUES(1,?,?,?,?,?,?,?)", receipt)
        self.db.execute("UPDATE phone_remote_meta SET schema_version=2")
        self.db.commit()
        reopened = PhoneAdmissionStore(self.db, self.anchor)
        self.assertEqual(reopened.status()["schema_version"], 2)
        self.assertEqual(tuple(self.db.execute(
            "SELECT operation_id,host_id,target_generation,manifest_sha256,checkpoint_sha256,"
            "authority_sha256,receipt_version FROM phone_remote_restore_receipt WHERE singleton_id=1"
        ).fetchone()), receipt)

        incarnation = reopened.login(identity=identity(), session_id="s-v2", grant_id="g-a",
            owner_id="alice", now=1, expires_at=100)
        self.assertTrue(incarnation)
        reopened.revoke_session(identity=identity(), session_id="s-v2", owner_id="alice")
        self.assertEqual(tuple(self.db.execute(
            "SELECT operation_id,host_id,target_generation,manifest_sha256,checkpoint_sha256,"
            "authority_sha256,receipt_version FROM phone_remote_restore_receipt WHERE singleton_id=1"
        ).fetchone()), receipt)

    def test_receipt_schema_version_mismatch_fails_closed(self):
        self.seed()
        self.db.execute(RESTORE_RECEIPT_SQL)
        self.db.commit()
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)

    def test_existing_disposable_database_upgrades_idempotently_without_touching_legacy_rows(self):
        self.db.execute("CREATE TABLE legacy_state(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("INSERT INTO legacy_state VALUES(1,'untouched')")
        self.db.commit()
        upgraded = PhoneAdmissionStore(self.db, self.anchor)
        self.assertEqual(upgraded.status()["schema_version"], 1)
        self.assertEqual(self.db.execute("SELECT value FROM legacy_state WHERE id=1").fetchone()[0], "untouched")
        again = PhoneAdmissionStore(self.db, self.anchor)
        self.assertEqual(again.status(), upgraded.status())

    def test_identity_scope_constraints_and_failed_insert_are_atomic(self):
        self.seed()
        before = self.db.execute("SELECT count(*) FROM phone_remote_grants").fetchone()[0]
        for bad in ("owner-b", "alice "):
            with self.subTest(owner=bad), self.assertRaises(StoreDenied):
                self.store.add_grant(identity=identity(), grant_id="g-b", device_id="d-a", owner_id=bad,
                                     scopes=["read"])
        for scopes in (("read",), ["admin"], ["read", "read"], ["read", 4], []):
            with self.subTest(scopes=scopes), self.assertRaises(StoreDenied):
                self.store.add_grant(identity=identity(), grant_id="g-b", device_id="d-a", owner_id="alice",
                                     scopes=scopes)
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_grants").fetchone()[0], before)
        with self.assertRaises(StoreDenied):
            self.store.add_device(identity=identity(), device_id="", owner_id="alice", public_key=b"x", key_algorithm="x")
        with self.assertRaises(StoreDenied):
            self.store.add_device(identity=identity("bob"), device_id="d-b", owner_id="alice",
                                  public_key=b"public", key_algorithm="test")
        with self.assertRaises(StoreDenied):
            self.store.add_device(identity=object(), device_id="d-c", owner_id="alice",
                                  public_key=b"public", key_algorithm="test")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO phone_remote_grants VALUES('bad','missing','alice','[]',1,NULL)")

    def test_login_incarnations_are_distinct_and_owner_binding_is_enforced(self):
        self.seed()
        one = self.login()
        self.store.revoke_session(identity=identity(), session_id="s-a", owner_id="alice")
        two = self.login()
        self.assertNotEqual(one, two)
        self.assertEqual(self.anchor.state.login_counter, 2)
        with self.assertRaises(StoreDenied):
            self.login(session="s-b", owner="bob")
        with self.assertRaises(StoreDenied):
            self.login(session="s-a")
        self.assertEqual(self.store.status()["login_counter"], 2)

    def test_login_challenge_context_is_current_and_rejects_unavailable_selector(self):
        self.seed()
        context = self.store.login_challenge_context(device_id="d-a", grant_id="g-a")
        self.assertEqual((context.owner_id, context.device_id, context.grant_id),
                         ("alice", "d-a", "g-a"))
        self.assertEqual(context.public_key, b"public-a")
        self.assertEqual(context.key_algorithm, "test-ed25519")
        self.assertEqual(context.scopes, frozenset({"read", "voice"}))
        self.assertEqual((context.host_id, context.host_generation), ("host-test", 3))
        for device_id, grant_id in (("missing", "g-a"), ("d-a", "missing")):
            with self.subTest(device_id=device_id, grant_id=grant_id), self.assertRaises(StoreDenied):
                self.store.login_challenge_context(device_id=device_id, grant_id=grant_id)
        self.store.revoke_grant(identity=identity(), grant_id="g-a", owner_id="alice")
        with self.assertRaises(StoreDenied):
            self.store.login_challenge_context(device_id="d-a", grant_id="g-a")

    def test_login_proof_rechecks_owner_key_generation_and_expiry_before_transition(self):
        self.seed()
        context = self.store.login_challenge_context(device_id="d-a", grant_id="g-a")

        def attempt(*, identity_value=identity(), expected_generation=context.host_generation,
                    challenge_expiry=2_000, now_ms=1_999):
            return self.store.login_proof(identity=identity_value, session_id="s-proof",
                device_id=context.device_id, grant_id=context.grant_id, owner_id=context.owner_id,
                expected_host_id=context.host_id, expected_host_generation=expected_generation,
                expected_grant_generation=context.grant_generation,
                expected_key_algorithm=context.key_algorithm,
                expected_key_fingerprint=hashlib.sha256(context.public_key).hexdigest(),
                challenge_expires_at_ms=challenge_expiry, monotonic_deadline_ms=61_000,
                now_ms=now_ms, monotonic_now_ms=1_000, expires_at_ms=43_201_999)

        with self.assertRaises(StoreDenied):
            attempt(now_ms=2_000)
        with self.assertRaises(StoreDenied):
            attempt(identity_value=identity("bob"))
        self.assertEqual(self.anchor.state.login_counter, 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)

        self.store.replace_device_credential(identity=identity(), device_id="d-a", owner_id="alice",
            public_key=b"replacement", key_algorithm="test-ed25519-v2")
        with self.assertRaises(StoreDenied):
            attempt(expected_generation=context.host_generation)
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertEqual(self.anchor.state.login_counter, 0)

        fresh = self.store.login_challenge_context(device_id="d-a", grant_id="g-a")
        incarnation = self.store.login_proof(identity=identity(), session_id="s-proof",
            device_id=fresh.device_id, grant_id=fresh.grant_id, owner_id=fresh.owner_id,
            expected_host_id=fresh.host_id, expected_host_generation=fresh.host_generation,
            expected_grant_generation=fresh.grant_generation,
            expected_key_algorithm=fresh.key_algorithm,
            expected_key_fingerprint=hashlib.sha256(fresh.public_key).hexdigest(),
            challenge_expires_at_ms=2_000, monotonic_deadline_ms=61_000,
            now_ms=1_999, monotonic_now_ms=1_000, expires_at_ms=43_201_999)
        self.assertEqual(incarnation, "host-test:4:1")
        self.assertEqual(self.anchor.state.login_counter, 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_sessions WHERE session_id='s-proof'").fetchone()[0], 1)

    def test_supported_pre_restore_fence_blocks_snapshot_and_identical_tuple_reuse(self):
        """Only the mandatory pre-restore fence is tested; arbitrary rollback is not claimed."""
        self.seed()
        old = self.login()
        self.ticket(old)
        snap = os.path.join(self.tmp.name, "snapshot.sqlite")
        snapdb = sqlite3.connect(snap)
        self.db.backup(snapdb)
        snapdb.close()

        self.store.advance_host_generation()
        new = self.login(session="s-a")
        self.assertNotEqual(old, new)
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="t-a", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=3)
        self.db.close()
        restored = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        snapdb = sqlite3.connect(snap)
        snapdb.backup(restored)
        snapdb.close()
        self.db = restored
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor).status()

    def test_new_process_requires_fresh_login_before_ticket_admission(self):
        self.seed()
        inc = self.login()
        self.ticket(inc)
        with self.assertRaises(StoreDenied):
            restarted = PhoneAdmissionStore(self.db, self.anchor, process_epoch="restart-2")
            restarted.issue_ticket(identity=identity(), ticket_id="before-login", session_id="s-a",
                                   owner_id="alice", purpose="offer", payload_digest="x",
                                   now=2, expires_at=10)
        new_inc = restarted.login(identity=identity(), session_id="s-a", grant_id="g-a",
                                  owner_id="alice", now=3, expires_at=100)
        self.assertNotEqual(inc, new_inc)
        restarted.issue_ticket(identity=identity(), ticket_id="fresh", session_id="s-a",
                               owner_id="alice", purpose="offer", payload_digest="new",
                               now=3, expires_at=33)
        restarted.consume_ticket(identity=identity(), ticket_id="fresh", session_id="s-a",
                                 owner_id="alice", purpose="offer", payload_digest="new", now=4)
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="t-a", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=4)

    def test_issue_and_consume_require_full_current_tuple_and_known_scopes(self):
        self.seed()
        self.login()
        self.ticket("not-used", ticket="tuple")
        # Changing either generation or the owner/device/grant binding after
        # issue invalidates the captured immutable ticket tuple.
        self.db.execute("UPDATE phone_remote_grants SET grant_generation=grant_generation+1 WHERE grant_id='g-a'")
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="tuple", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=3)
        self.db.execute("UPDATE phone_remote_grants SET scopes_json='[\"admin\"]' WHERE grant_id='g-a'")
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="tuple", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=4)

    def test_session_generation_change_invalidates_issued_ticket(self):
        self.seed()
        self.login()
        self.ticket("unused", ticket="session-tuple")
        self.db.execute("UPDATE phone_remote_sessions SET session_generation=session_generation+1 WHERE session_id='s-a'")
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="session-tuple", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=3)

    def test_issue_ticket_maximum_lifetime_is_thirty_seconds(self):
        self.seed()
        self.login()
        self.store.issue_ticket(identity=identity(), ticket_id="at-30", session_id="s-a",
                                owner_id="alice", purpose="offer", payload_digest="x",
                                now=1, expires_at=31)
        with self.assertRaises(StoreDenied):
            self.store.issue_ticket(identity=identity(), ticket_id="at-31", session_id="s-a",
                                    owner_id="alice", purpose="offer", payload_digest="x",
                                    now=1, expires_at=32)

    def test_update_ticket_binds_exact_peer_and_offer_does_not(self):
        self.seed()
        self.login()
        with self.assertRaises(StoreDenied):
            self.store.issue_ticket(identity=identity(), ticket_id="bad-update", session_id="s-a",
                                    owner_id="alice", purpose="update", payload_digest="u",
                                    now=1, expires_at=10)
        self.store.issue_ticket(identity=identity(), ticket_id="update", session_id="s-a",
                                owner_id="alice", purpose="update", payload_digest="u",
                                now=1, expires_at=10, peer_id="peer-a")
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="update", session_id="s-a",
                                      owner_id="alice", purpose="update", payload_digest="u",
                                      now=2, peer_id="peer-b")
        self.store.consume_ticket(identity=identity(), ticket_id="update", session_id="s-a",
                                  owner_id="alice", purpose="update", payload_digest="u",
                                  now=2, peer_id="peer-a")

    def test_restore_fence_advances_and_old_ticket_never_revives(self):
        self.seed()
        incarnation = self.login()
        self.ticket(incarnation)
        before = self.store.status()["host_generation"]
        self.assertEqual(self.store.advance_host_generation(), before + 1)
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="t-a", session_id="s-a", owner_id="alice",
                                      purpose="offer", payload_digest="sha256:offer", now=3)
        new = self.login(session="s-a")
        self.assertNotEqual(incarnation, new)
        # Reusing the old session ID cannot transfer the pre-restore ticket.
        self.assertNotEqual(
            self.store.db.execute("SELECT login_incarnation FROM phone_remote_sessions WHERE session_id='s-a'").fetchone()[0],
            incarnation,
        )
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="t-a", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=3)
        self.store.issue_ticket(identity=identity(), ticket_id="t-new", session_id="s-a", owner_id="alice",
                                purpose="offer", payload_digest="x", now=2, expires_at=20)

    def test_single_use_ticket_exact_binding_expiry_and_parallel_replay(self):
        self.seed()
        inc = self.login()
        self.ticket(inc)
        def consume():
            self.store.consume_ticket(identity=identity(), ticket_id="t-a", session_id="s-a", owner_id="alice",
                                      purpose="offer", payload_digest="sha256:offer", now=3)
        outcomes = []
        def worker():
            try:
                consume(); outcomes.append("ok")
            except StoreDenied:
                outcomes.append("denied")
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("denied"), 7)
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity("bob"), ticket_id="t-a", session_id="s-a", owner_id="bob",
                                      purpose="offer", payload_digest="sha256:offer", now=3)

    def test_ticket_expiry_boundary_is_closed(self):
        self.seed()
        inc = self.login()
        self.ticket(inc, ticket="expires-at-20")
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="expires-at-20",
                                      session_id="s-a", owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=20)

    def test_anchor_absence_mismatch_write_failure_and_store_failure_fail_closed(self):
        self.seed()
        self.anchor.available = False
        with self.assertRaises(StoreUnavailable): self.store.status()
        self.anchor.available = True
        self.anchor.fail_next_write = True
        with self.assertRaises(StoreUnavailable): self.store.advance_host_generation()
        generation = self.store.status()["host_generation"]
        self.assertEqual(self.anchor.state.host_generation, generation)
        state = self.anchor.state
        with self.anchor.exclusive():
            self.anchor.write(type(state)(1, state.host_id, 2, None, "stable", state.login_counter))
        with self.assertRaises(StoreUnavailable): self.store.status()

    def test_missing_metadata_or_nonnull_stable_transition_never_bootstraps(self):
        self.seed()
        self.db.execute("DELETE FROM phone_remote_meta WHERE singleton_id=1")
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)
        self.db.execute("INSERT INTO phone_remote_meta VALUES(1,1,'host-test',1,NULL,'stable')")
        self.db.execute("UPDATE phone_remote_meta SET transition_id='unreconciled' WHERE singleton_id=1")
        with self.assertRaises(StoreUnavailable): self.store.status()

    def test_missing_authority_table_is_not_silently_recreated(self):
        self.seed()
        self.db.execute("DROP TABLE phone_remote_sessions")
        self.db.commit()
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)
        self.assertNotIn("phone_remote_sessions", {
            row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        })

    def test_constraintless_replacement_table_is_rejected_without_repair(self):
        self.seed()
        self.db.execute("PRAGMA foreign_keys=OFF")
        self.db.execute("CREATE TABLE replacement AS SELECT * FROM phone_remote_devices")
        self.db.execute("DROP TABLE phone_remote_devices")
        self.db.execute("ALTER TABLE replacement RENAME TO phone_remote_devices")
        self.db.commit()
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)
        # Rejection must not rewrite the malformed schema or permit duplicate IDs.
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_devices WHERE device_id='d-a'").fetchone()[0], 1)
        with self.assertRaises(StoreUnavailable):
            self.store.add_device(identity=identity(), device_id="d-a", owner_id="alice",
                                  public_key=b"other", key_algorithm="test-ed25519")
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_devices WHERE device_id='d-a'").fetchone()[0], 1)

    def test_authority_requires_foreign_keys_enabled_and_clean(self):
        self.seed()
        self.db.commit()
        self.db.execute("PRAGMA foreign_keys=OFF")
        with self.assertRaises(StoreUnavailable):
            self.store.status()
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA foreign_keys=OFF")
        self.db.execute("INSERT INTO phone_remote_grants VALUES('orphan','missing','alice','[\"read\"]',1,NULL)")
        self.db.commit()
        self.db.execute("PRAGMA foreign_keys=ON")
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)

    def test_unexpected_authority_trigger_is_rejected(self):
        self.seed()
        self.db.execute("CREATE TRIGGER mutate_authority AFTER INSERT ON phone_remote_devices "
                        "BEGIN UPDATE phone_remote_meta SET host_generation=999; END")
        self.db.commit()
        with self.assertRaises(StoreUnavailable):
            self.store.status()

    def test_schema_check_literal_case_is_not_normalized_away(self):
        self.seed()
        create = SCHEMA_SQL["phone_remote_meta"].replace(
            "CREATE TABLE phone_remote_meta", "CREATE TABLE replacement", 1
        ).replace("'stable','pending'", "'stable','PENDING'")
        self.db.execute(create)
        self.db.execute("INSERT INTO replacement SELECT * FROM phone_remote_meta")
        self.db.execute("DROP TABLE phone_remote_meta")
        self.db.execute("ALTER TABLE replacement RENAME TO phone_remote_meta")
        self.db.commit()
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)

    def test_schema_check_does_not_strip_quoted_identifier_semantics(self):
        self.seed()
        self.db.execute("""CREATE TABLE replacement (
            "singleton_id" INTEGER PRIMARY KEY CHECK(singleton_id=1),
            schema_version INTEGER NOT NULL, host_id TEXT NOT NULL,
            host_generation INTEGER NOT NULL, transition_id TEXT,
            transition_state TEXT NOT NULL CHECK(transition_state IN ('stable','pending'))
        )""")
        self.db.execute("INSERT INTO replacement SELECT * FROM phone_remote_meta")
        self.db.execute("DROP TABLE phone_remote_meta")
        self.db.execute("ALTER TABLE replacement RENAME TO phone_remote_meta")
        self.db.commit()
        with self.assertRaises(StoreUnavailable):
            self.store.status()

    def test_changed_live_schema_version_blocks_every_authority_read(self):
        self.seed()
        self.db.execute("UPDATE phone_remote_meta SET schema_version=999 WHERE singleton_id=1")
        self.db.commit()
        with self.assertRaises(StoreUnavailable): self.store.status()
        with self.assertRaises(StoreUnavailable): PhoneAdmissionStore(self.db, self.anchor)

    def test_anchor_counter_rollback_below_live_incarnation_is_denied(self):
        self.seed()
        self.login()
        state = self.anchor.state
        with self.anchor.exclusive():
            self.anchor.write(type(state)(1, state.host_id, state.host_generation,
                                          None, "stable", 0))
        with self.assertRaises(StoreUnavailable): self.store.status()

    def test_counter_rollback_cannot_reuse_revoked_incarnation(self):
        self.seed()
        first = self.login()
        self.store.revoke_session(identity=identity(), session_id="s-a", owner_id="alice")
        generation = self.store.status()["host_generation"]
        state = self.anchor.state
        with self.anchor.exclusive():
            self.anchor.write(type(state)(1, state.host_id, state.host_generation,
                                          None, "stable", 0))
        with self.assertRaises(StoreUnavailable): self.store.status()
        with self.assertRaises(StoreUnavailable): self.login(session="s-a")
        self.assertEqual(first, f"host-test:{generation}:1")
        self.assertEqual(self.anchor.state.login_counter, 0)

    def test_same_generation_different_host_with_active_sessions_is_denied(self):
        self.seed()
        self.login()
        state = self.anchor.state
        with self.anchor.exclusive():
            self.anchor.write(type(state)(1, "HOST-B", state.host_generation,
                                          None, "stable", state.login_counter))
        with self.assertRaises(StoreUnavailable): self.store.status()

    def test_both_equal_generation_host_substitutions_fail_without_mutation(self):
        self.seed()
        self.login()
        self.ticket("unused", ticket="host-ticket")
        # Database/session claims HOST-B while the injected anchor remains HOST-A.
        self.db.execute("UPDATE phone_remote_meta SET host_id='HOST-B' WHERE singleton_id=1")
        self.db.execute("UPDATE phone_remote_sessions SET host_id='HOST-B',login_incarnation='HOST-B:1:1' WHERE session_id='s-a'")
        with self.assertRaises(StoreUnavailable): self.store.status()
        self.assertFalse(self.store._tickets["host-ticket"]["consumed"])

        # Now try the inverse: HOST-B anchor against the untouched HOST-A DB.
        self.db.execute("UPDATE phone_remote_meta SET host_id='host-test' WHERE singleton_id=1")
        self.db.execute("UPDATE phone_remote_sessions SET host_id='host-test',login_incarnation='host-test:1:1' WHERE session_id='s-a'")
        state = self.anchor.state
        with self.anchor.exclusive():
            self.anchor.write(type(state)(1, "HOST-B", state.host_generation,
                                          None, "stable", state.login_counter))
        with self.assertRaises(StoreUnavailable): self.store.status()
        self.assertFalse(self.store._tickets["host-ticket"]["consumed"])

    def test_crashes_at_each_generation_transition_boundary(self):
        for boundary in ("generation_before_anchor_pending", "generation_anchor_pending",
                         "generation_before_db_commit", "generation_db_committed",
                         "generation_before_anchor_finalize", "generation_anchor_finalized"):
            with self.subTest(boundary=boundary):
                db = sqlite3.connect(":memory:", isolation_level=None)
                anchor = FakeProtectedAnchor()
                def fail(name):
                    if name == boundary: raise RuntimeError("simulated crash")
                store = PhoneAdmissionStore(db, anchor, failpoint=fail)
                if boundary == "generation_anchor_pending":
                    # This stage can be exercised without seeded identity data.
                    pass
                with self.assertRaises(RuntimeError): store.advance_host_generation()
                if boundary == "generation_before_anchor_pending":
                    self.assertEqual(PhoneAdmissionStore(db, anchor).status()["host_generation"], 1)
                else:
                    with self.assertRaises(StoreUnavailable):
                        PhoneAdmissionStore(db, anchor).status()
                db.close()

    def test_restore_prepare_preflight_and_crash_boundaries_are_fail_closed(self):
        self.seed()
        self.login()
        initial = self.anchor.state
        with self.assertRaises(StoreDenied):
            self.store.prepare_restore(expected_host_id=initial.host_id,
                                       expected_generation=initial.host_generation + 1)
        self.assertEqual(self.anchor.state, initial)
        self.assertEqual(tuple(self.db.execute(
            "SELECT transition_state,host_generation FROM phone_remote_meta WHERE singleton_id=1"
        ).fetchone()), ("stable", initial.host_generation))
        self.assertEqual(self.db.execute(
            "SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-a'"
        ).fetchone()[0], None)

        cases = {
            "restore_before_anchor_pending": ("stable", "stable", 1),
            "restore_anchor_pending": ("pending", "stable", 1),
            "restore_before_db_commit": ("pending", "stable", 1),
            "restore_db_pending": ("pending", "pending", 0),
        }
        for boundary, (anchor_state, database_state, active) in cases.items():
            with self.subTest(boundary=boundary):
                db = sqlite3.connect(":memory:", isolation_level=None)
                anchor = FakeProtectedAnchor()
                store = PhoneAdmissionStore(db, anchor)
                store.add_device(identity=identity(), device_id="d", owner_id="alice",
                                 public_key=b"public", key_algorithm="test")
                store.add_grant(identity=identity(), grant_id="g", device_id="d", owner_id="alice",
                                scopes=["read", "voice"])
                store.login(identity=identity(), session_id="s", grant_id="g", owner_id="alice",
                            now=1, expires_at=100)
                initial = anchor.state
                def fail(name):
                    if name == boundary:
                        raise RuntimeError("simulated restore prepare interruption")
                store.failpoint = fail
                with self.assertRaises(RuntimeError):
                    store.prepare_restore(expected_host_id=initial.host_id,
                                          expected_generation=initial.host_generation)
                self.assertEqual(anchor.state.transition_state, anchor_state)
                meta = db.execute(
                    "SELECT transition_state,host_generation FROM phone_remote_meta WHERE singleton_id=1"
                ).fetchone()
                self.assertEqual(meta[0], database_state)
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL"
                ).fetchone()[0], active)
                if anchor_state == "stable":
                    self.assertEqual(store.status()["host_generation"], initial.host_generation)
                else:
                    with self.assertRaises(StoreUnavailable):
                        store.status()
                    pending = anchor.state
                    pending_meta = tuple(db.execute(
                        "SELECT transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1"
                    ).fetchone())
                    store.failpoint = None
                    with self.assertRaises(StoreUnavailable):
                        store.prepare_restore(expected_host_id=initial.host_id,
                                              expected_generation=initial.host_generation)
                    self.assertEqual(anchor.state, pending)
                    self.assertEqual(tuple(db.execute(
                        "SELECT transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1"
                    ).fetchone()), pending_meta)
                db.close()

    def test_crashes_at_each_login_transition_boundary(self):
        for boundary in ("login_before_anchor_reservation", "login_anchor_reserved",
                         "login_before_db_commit", "login_db_committed",
                         "login_before_anchor_finalize", "login_anchor_finalized"):
            with self.subTest(boundary=boundary):
                db = sqlite3.connect(":memory:", isolation_level=None)
                anchor = FakeProtectedAnchor()
                def fail(name):
                    if name == boundary: raise RuntimeError("simulated crash")
                store = PhoneAdmissionStore(db, anchor, failpoint=fail)
                store.add_device(identity=identity("a"), device_id="d", owner_id="a", public_key=b"public", key_algorithm="test")
                store.add_grant(identity=identity("a"), grant_id="g", device_id="d", owner_id="a", scopes=["voice"])
                with self.assertRaises(RuntimeError):
                    store.login(identity=identity("a"), session_id="s", grant_id="g", owner_id="a", now=0, expires_at=10)
                if boundary == "login_before_anchor_reservation":
                    self.assertEqual(store.status()["login_counter"], 0)
                    self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
                elif boundary == "login_anchor_finalized":
                    self.assertEqual(store.status()["login_counter"], 1)
                    self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 1)
                else:
                    with self.assertRaises(StoreUnavailable):
                        store.status()
                db.close()

    def test_sqlite_write_failure_after_anchor_reservation_fails_closed(self):
        self.seed()
        def deny_session_insert(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_INSERT and arg1 == "phone_remote_sessions":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.db.set_authorizer(deny_session_insert)
        with self.assertRaises(sqlite3.DatabaseError):
            self.login()
        self.db.set_authorizer(None)
        self.assertEqual(self.db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        with self.assertRaises(StoreUnavailable): self.store.status()

    def test_two_store_instances_serialize_whole_anchor_transition(self):
        self.seed()
        self.login()  # begin at protected counter 1, as in the reviewer interleave
        second_db = sqlite3.connect(self.path, check_same_thread=False)
        second = PhoneAdmissionStore(second_db, self.anchor)
        arrived, release, second_started = threading.Event(), threading.Event(), threading.Event()
        reentry = []
        outcomes = []
        def pause(name):
            if name == "generation_before_anchor_pending":
                try:
                    second.status()  # same-thread reentry must deny, not deadlock
                except StoreUnavailable:
                    reentry.append("denied")
                arrived.set()
                if not release.wait(2):
                    raise RuntimeError("interleave timed out")
        self.store.failpoint = pause
        first_thread = threading.Thread(target=lambda: outcomes.append(self.store.advance_host_generation()))
        def run_second():
            second_started.set()
            outcomes.append(second.advance_host_generation())
            outcomes.append(second.login(identity=identity(), session_id="s-b", grant_id="g-a",
                                         owner_id="alice", now=1, expires_at=100))
        second_thread = threading.Thread(target=run_second)
        first_thread.start(); self.assertTrue(arrived.wait(2)); second_thread.start()
        self.assertTrue(second_started.wait(2)); release.set()
        first_thread.join(2); second_thread.join(2)
        self.assertFalse(first_thread.is_alive()); self.assertFalse(second_thread.is_alive())
        self.assertEqual(reentry, ["denied"])
        self.assertCountEqual([value for value in outcomes if type(value) is int], [4, 5])
        self.assertEqual(second.status()["host_generation"], 5)
        self.assertEqual(second.status()["login_counter"], 2)
        second._drop_admissions()
        second_db.close()

    def test_reentry_is_rejected_even_when_other_store_waiter_is_queued(self):
        class ObservableAnchor(FakeProtectedAnchor):
            def __init__(self):
                super().__init__()
                self.second_requested = threading.Event()
            @contextmanager
            def exclusive(self):
                if threading.current_thread().name == "store-two-waiter":
                    self.second_requested.set()
                with super().exclusive():
                    yield

        db_path = os.path.join(self.tmp.name, "reentry.sqlite")
        db = sqlite3.connect(db_path, check_same_thread=False)
        anchor = ObservableAnchor()
        first_entered = threading.Event()
        second = None
        outcome = []
        first = PhoneAdmissionStore(db, anchor)
        second_db = sqlite3.connect(db_path, check_same_thread=False)
        second = PhoneAdmissionStore(second_db, anchor)
        def failpoint(name):
            if name == "generation_before_anchor_pending":
                first_entered.set()
                if not anchor.second_requested.wait(2):
                    raise RuntimeError("second waiter did not reach authority lock")
                try:
                    second.status()
                except StoreUnavailable:
                    outcome.append("reentry-denied")
        first.failpoint = failpoint
        t1 = threading.Thread(target=first.advance_host_generation, name="store-one-owner", daemon=True)
        t2 = threading.Thread(target=second.status, name="store-two-waiter", daemon=True)
        t1.start(); self.assertTrue(first_entered.wait(2)); t2.start()
        t1.join(2); t2.join(2)
        self.assertFalse(t1.is_alive(), "authority owner deadlocked on the second store's local lock")
        self.assertFalse(t2.is_alive(), "queued store operation did not resume")
        self.assertEqual(outcome, ["reentry-denied"])
        db.close(); second_db.close()

    def test_grant_and_device_revocation_fence_sessions_and_tickets(self):
        self.seed()
        self.store.add_device(identity=identity(), device_id="d-b", owner_id="alice",
                              public_key=b"public-b", key_algorithm="test-ed25519")
        self.store.add_grant(identity=identity(), grant_id="g-b", device_id="d-b",
                             owner_id="alice", scopes=["read", "voice"])
        self.login()
        self.login(session="s-b", grant="g-b")
        self.ticket("unused")
        self.ticket("unused-b", ticket="ticket-b", session="s-b")
        before = self.store.status()["host_generation"]
        self.store.revoke_grant(identity=identity(), grant_id="g-a", owner_id="alice")
        self.assertEqual(self.store.status()["host_generation"], before + 1)
        self.assertIsNotNone(self.store.db.execute(
            "SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-b'").fetchone()[0])
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="t-a", session_id="s-a",
                                      owner_id="alice", purpose="offer",
                                      payload_digest="sha256:offer", now=3)
        with self.assertRaises(StoreDenied): self.login(session="s-b")
        with self.assertRaises(StoreDenied):
            self.store.consume_ticket(identity=identity(), ticket_id="ticket-b", session_id="s-b",
                owner_id="alice", purpose="offer", payload_digest="sha256:offer", now=3)
        with self.assertRaises(StoreDenied): self.login(session="s-a", grant="g-a")

        self.login(session="s-b", grant="g-b")
        self.store.revoke_device(identity=identity(), device_id="d-a", owner_id="alice")
        with self.assertRaises(StoreDenied):
            self.store.issue_ticket(identity=identity(), ticket_id="d-revoked", session_id="s-b",
                                    owner_id="alice", purpose="offer", payload_digest="x",
                                    now=3, expires_at=10)

    def test_session_signout_stays_scoped_and_scope_change_is_global(self):
        self.seed()
        self.store.add_device(identity=identity(), device_id="d-b", owner_id="alice",
                              public_key=b"public-b", key_algorithm="test-ed25519")
        self.store.add_grant(identity=identity(), grant_id="g-b", device_id="d-b",
                             owner_id="alice", scopes=["read", "voice"])
        self.login()
        self.login(session="s-b", grant="g-b")
        self.store.revoke_session(identity=identity(), session_id="s-a", owner_id="alice")
        self.assertIsNone(self.store.db.execute(
            "SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-b'").fetchone()[0])
        before = self.store.status()["host_generation"]
        self.store.update_grant_scopes(identity=identity(), grant_id="g-a", owner_id="alice", scopes=["read"])
        self.assertEqual(self.store.status()["host_generation"], before + 1)
        self.assertIsNotNone(self.store.db.execute(
            "SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-b'").fetchone()[0])
        incarnation = self.login(session="s-a", grant="g-a")
        binding = self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-a",
            device_id="d-a", login_incarnation=incarnation, now=2)
        self.assertEqual(binding.scopes, frozenset({"read"}))
        # The unaffected enrollment may authenticate afresh after the global fence.
        self.login(session="s-b", grant="g-b")

    def test_failed_or_repeated_revoke_does_not_advance_authority(self):
        self.seed()
        before = self.store.status()
        with self.assertRaises(StoreDenied):
            self.store.revoke_grant(identity=identity(), grant_id="missing", owner_id="alice")
        self.assertEqual(self.store.status(), before)
        self.store.revoke_grant(identity=identity(), grant_id="g-a", owner_id="alice")
        after = self.store.status()
        with self.assertRaises(StoreDenied):
            self.store.revoke_grant(identity=identity(), grant_id="g-a", owner_id="alice")
        self.assertEqual(self.store.status(), after)

    def test_scope_noop_still_checks_stable_anchor(self):
        self.seed()
        before = self.store.status()
        self.anchor.available = False
        with self.assertRaises(StoreUnavailable):
            self.store.update_grant_scopes(identity=identity(), grant_id="g-a", owner_id="alice",
                                           scopes=["read", "voice"])
        self.anchor.available = True
        self.assertEqual(self.store.status(), before)
        self.assertEqual(self.db.execute("SELECT scopes_json FROM phone_remote_grants WHERE grant_id='g-a'").fetchone()[0],
                         '["read","voice"]')

    def test_credential_replacement_uses_global_fence_and_validates_before_reservation(self):
        self.seed()
        inc = self.login()
        before = self.store.status()["host_generation"]
        with self.assertRaises(StoreDenied):
            self.store.replace_device_credential(identity=identity("bob"), device_id="d-a",
                owner_id="alice", public_key=b"new", key_algorithm="test-ed25519")
        self.assertEqual(self.store.status()["host_generation"], before)
        self.store.replace_device_credential(identity=identity(), device_id="d-a", owner_id="alice",
            public_key=b"new", key_algorithm="test-ed25519")
        self.assertEqual(self.store.status()["host_generation"], before + 1)
        with self.assertRaises(StoreDenied):
            self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-a",
                device_id="d-a", login_incarnation=inc, now=2)
        stable = self.store.status()
        self.store.replace_device_credential(identity=identity(), device_id="d-a", owner_id="alice",
            public_key=b"new", key_algorithm="test-ed25519")
        self.assertEqual(self.store.status(), stable)

    def test_snapshot_revoke_raw_restore_fails_without_restore_preparation(self):
        self.seed()
        self.login()
        snapshot = os.path.join(self.tmp.name, "pre-revoke.sqlite")
        backup = sqlite3.connect(snapshot)
        self.db.backup(backup)
        backup.close()
        self.store.revoke_grant(identity=identity(), grant_id="g-a", owner_id="alice")
        self.db.close()
        restored = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        backup = sqlite3.connect(snapshot)
        backup.backup(restored)
        backup.close()
        self.db = restored
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)

    def test_scope_reduction_then_old_broader_snapshot_fails_closed(self):
        self.seed()
        snapshot = os.path.join(self.tmp.name, "broader-grant.sqlite")
        old_db = sqlite3.connect(snapshot)
        self.db.backup(old_db)
        old_db.close()
        self.store.update_grant_scopes(identity=identity(), grant_id="g-a", owner_id="alice", scopes=["read"])
        self.db.close()
        restored = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        old_db = sqlite3.connect(snapshot)
        old_db.backup(restored)
        old_db.close()
        self.db = restored
        with self.assertRaises(StoreUnavailable):
            PhoneAdmissionStore(self.db, self.anchor)

    def test_immutable_binding_rejects_every_changed_authority_dimension(self):
        self.seed()
        incarnation = self.login()
        binding = self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-a",
            device_id="d-a", login_incarnation=incarnation, now=2)
        changes = {
            "owner_id": "bob", "device_id": "other-device", "grant_id": "other-grant",
            "session_id": "other-session", "login_incarnation": "host-test:3:999",
            "host_id": "other-host", "host_generation": binding.host_generation + 1,
            "grant_generation": binding.grant_generation + 1,
            "session_generation": binding.session_generation + 1,
            "process_epoch": "other-process", "scopes": frozenset({"read"}),
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.assertFalse(self.store.binding_current(replace(binding, **{field: value}), now=2))

    def test_session_signout_stays_scoped_across_repeated_raw_stale_restores(self):
        self.seed()
        inc_a = self.login(session="s-a")
        inc_b = self.login(session="s-b")
        snapshot = os.path.join(self.tmp.name, "sessions.sqlite")
        snapdb = sqlite3.connect(snapshot)
        self.db.backup(snapdb)
        snapdb.close()
        self.store.revoke_session(identity=identity(), session_id="s-a", owner_id="alice")

        def restore_snapshot():
            snap = sqlite3.connect(snapshot)
            snap.backup(self.db)
            snap.close()

        restore_snapshot()
        with self.assertRaises(StoreDenied):
            self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-a",
                device_id="d-a", login_incarnation=inc_a, now=2)
        self.assertEqual(self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-b",
            device_id="d-a", login_incarnation=inc_b, now=2).session_id, "s-b")
        self.store.revoke_session(identity=identity(), session_id="s-a", owner_id="alice")
        restore_snapshot()
        with self.assertRaises(StoreDenied):
            self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-a",
                device_id="d-a", login_incarnation=inc_a, now=2)
        self.assertEqual(self.store.current_binding(identity=identity(), owner_id="alice", session_id="s-b",
            device_id="d-a", login_incarnation=inc_b, now=2).session_id, "s-b")

    def test_global_transition_crashes_fail_closed_after_pending_reservation(self):
        boundaries = ("grant_revoke_before_anchor_pending", "grant_revoke_anchor_pending",
            "grant_revoke_before_db_commit", "grant_revoke_db_committed",
            "grant_revoke_before_anchor_finalize", "grant_revoke_anchor_finalized")
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                db = sqlite3.connect(":memory:", isolation_level=None)
                anchor = FakeProtectedAnchor()
                store = PhoneAdmissionStore(db, anchor)
                identity_value = identity()
                store.add_device(identity=identity_value, device_id="d", owner_id="alice",
                                 public_key=b"key", key_algorithm="test")
                store.add_grant(identity=identity_value, grant_id="g", device_id="d",
                                 owner_id="alice", scopes=["read", "voice"])
                generation = anchor.state.host_generation
                def fail(name):
                    if name == boundary:
                        raise RuntimeError("synthetic transition crash")
                store.failpoint = fail
                with self.assertRaises(RuntimeError):
                    store.revoke_grant(identity=identity_value, grant_id="g", owner_id="alice")
                if boundary == "grant_revoke_before_anchor_pending":
                    self.assertEqual(store.status()["host_generation"], generation)
                else:
                    with self.assertRaises(StoreUnavailable):
                        store.status()
                db.close()

    def test_session_revocation_is_scoped_to_one_session(self):
        self.seed()
        self.login()
        other = self.login(session="s-b")
        self.store.revoke_session(identity=identity(), session_id="s-a", owner_id="alice")
        self.assertIsNotNone(self.store.db.execute(
            "SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-a'").fetchone()[0])
        self.assertIsNone(self.store.db.execute(
            "SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-b'").fetchone()[0])
        self.assertEqual(other, self.store.db.execute(
            "SELECT login_incarnation FROM phone_remote_sessions WHERE session_id='s-b'").fetchone()[0])
        with self.assertRaises(StoreDenied):
            self.store.issue_ticket(identity=identity(), ticket_id="revoked-session", session_id="s-a",
                                    owner_id="alice", purpose="offer", payload_digest="x",
                                    now=3, expires_at=10)

    def test_malformed_anchor_versions_and_pending_state_block_bootstrap(self):
        states = (
            (2, "host-test", 1, None, "stable", 0),
            (1, "host-test", 0, None, "stable", 0),
            (1, "host-test", 1, "transition", "pending", 0),
            (1, "host-test", 1, None, "stable", True),
        )
        for values in states:
            with self.subTest(anchor=values):
                db = sqlite3.connect(":memory:")
                anchor = FakeProtectedAnchor()
                anchor.state = type(anchor.state)(*values)
                with self.assertRaises(StoreUnavailable): PhoneAdmissionStore(db, anchor)
                db.close()


if __name__ == "__main__":
    unittest.main()
