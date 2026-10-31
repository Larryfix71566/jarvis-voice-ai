"""Closed journal codec/writer tests; all files live in temporary directories."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import uuid
import sqlite3
from unittest import mock
from pathlib import Path

from jarvis.bot.phone_remote_recovery import (
    FileRecord, RECEIPT_DDL, RecoveryJournal, RecoveryUnavailable, apply_pending_database,
    authority_projection_sha256, commit_reconciled_database, create_checkpoint,
    decode_journal,
    decode_manifest, encode_journal, encode_manifest, validate_journal,
    validate_receipt_tombstone, normalize_live_database, validate_source_catalog,
    reconcile_staged_database, stage_pending_database, inspect_database_state,
    validate_pending_anchor_v2,
    RecoveryProtocolSession,
)
from jarvis.bot.phone_admission_store import AnchorState, FakeProtectedAnchor, PhoneAdmissionStore, SCHEMA_SQL


def initial_journal(operation_id: str | None = None):
    operation_id = operation_id or str(uuid.uuid4())
    absent = {"present": False, "size_bytes": 0, "sha256": None}
    present = {"present": True, "size_bytes": 3, "sha256": hashlib.sha256(b"db\n").hexdigest()}
    cleanup = {name: {"state": "absent", "sha256": None} for name in
               ("checkpoint", "staged_database", "old_database", "old_wal", "old_shm")}
    cleanup["checkpoint"] = {"state": "pending", "sha256": hashlib.sha256(b"cp").hexdigest()}
    return {
        "journal_version": 1, "operation_id": operation_id,
        "manifest_sha256": "a" * 64, "phase": "checkpoint_bound", "rename_step": None,
        "files": {"database": present, "wal": absent, "shm": absent},
        "staged_database_sha256": None, "installed_database_sha256": None,
        "final_database_sha256": None, "cleanup_artifacts": cleanup,
    }


def _receipt(db: sqlite3.Connection):
    row = db.execute("SELECT operation_id,host_id,target_generation,manifest_sha256,"
        "checkpoint_sha256,authority_sha256,receipt_version FROM phone_remote_restore_receipt "
        "WHERE singleton_id=1").fetchone()
    return None if row is None else tuple(row)


def _meta_for_test(db: sqlite3.Connection):
    return db.execute("SELECT schema_version,host_id,host_generation,transition_id,transition_state "
                      "FROM phone_remote_meta WHERE singleton_id=1").fetchone()


class RecoveryJournalCodecTests(unittest.TestCase):
    @staticmethod
    def record(path: Path) -> FileRecord:
        if not path.exists():
            return FileRecord(False, 0, None)
        data = path.read_bytes()
        return FileRecord(True, len(data), hashlib.sha256(data).hexdigest())

    @staticmethod
    def create_install_fixture(root: Path, *, sidecars: bool = True):
        data = root / "data"
        recovery_parent = data / ".phone-restore"
        operation_id = str(uuid.uuid4())
        recovery_root = recovery_parent / operation_id
        for directory in (data, recovery_parent, recovery_root):
            directory.mkdir(mode=0o700)
        live = data / "jarvis.db"
        live.write_bytes(b"live-database")
        live.chmod(0o600)
        wal = data / "jarvis.db-wal"
        shm = data / "jarvis.db-shm"
        if sidecars:
            wal.write_bytes(b"wal-data"); wal.chmod(0o600)
            shm.write_bytes(b"shm-data"); shm.chmod(0o600)
        staged = recovery_root / "staged.db"
        staged.write_bytes(b"staged-database")
        staged.chmod(0o600)
        checkpoint = recovery_root / "checkpoint.db"
        checkpoint.write_bytes(b"checkpoint-database")
        checkpoint.chmod(0o600)
        writer = RecoveryJournal(recovery_root, operation_id=operation_id,
                                 manifest_sha256="a" * 64)
        state = writer.create(files={"database": RecoveryJournalCodecTests.record(live),
            "wal": RecoveryJournalCodecTests.record(wal),
            "shm": RecoveryJournalCodecTests.record(shm)},
            checkpoint_sha256=RecoveryJournalCodecTests.record(checkpoint).sha256)
        writer.mark_staged(staged)
        writer.mark_quiesced()
        writer.begin_installation()
        return writer, live, wal, shm, staged

    @staticmethod
    def create_application_db(*, with_phone: bool) -> sqlite3.Connection:
        from jarvis.db import run_migrations
        from jarvis.usage_ledger import _MODEL_BUDGET_SCHEMA, _SCHEMA

        db = sqlite3.connect(":memory:", isolation_level=None)
        db.row_factory = sqlite3.Row
        run_migrations(db)
        db.executescript(_SCHEMA)
        db.executescript(_MODEL_BUDGET_SCHEMA)
        if with_phone:
            PhoneAdmissionStore(db, FakeProtectedAnchor("host-test"))
        return db

    def test_pinned_catalog_accepts_application_without_or_with_exact_phone_schema(self):
        db = self.create_application_db(with_phone=False)
        try:
            self.assertRegex(validate_source_catalog(db), r"^[0-9a-f]{64}$")
        finally:
            db.close()

    def test_pinned_phone_catalog_includes_exact_implicit_unique_indexes(self):
        db = self.create_application_db(with_phone=True)
        try:
            db.execute(RECEIPT_DDL)
            db.execute("UPDATE phone_remote_meta SET schema_version=2")
            expected = {
                ("index", "sqlite_autoindex_phone_remote_devices_1", "phone_remote_devices", None),
                ("index", "sqlite_autoindex_phone_remote_devices_2", "phone_remote_devices", None),
                ("index", "sqlite_autoindex_phone_remote_grants_1", "phone_remote_grants", None),
                ("index", "sqlite_autoindex_phone_remote_grants_2", "phone_remote_grants", None),
                ("index", "sqlite_autoindex_phone_remote_sessions_1", "phone_remote_sessions", None),
                ("index", "sqlite_autoindex_phone_remote_sessions_2", "phone_remote_sessions", None),
            }
            rows = {tuple(row) for row in db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name LIKE 'sqlite_autoindex_phone_remote_%'")}
            observed = {row for row in rows if row[1].startswith("sqlite_autoindex_phone_remote_")}
            self.assertEqual(observed, expected)
            self.assertRegex(validate_source_catalog(db), r"^[0-9a-f]{64}$")
        finally:
            db.close()

        db = self.create_application_db(with_phone=True)
        try:
            digest_v1 = validate_source_catalog(db)
            db.execute(RECEIPT_DDL)
            db.execute("UPDATE phone_remote_meta SET schema_version=2")
            digest_v2 = validate_source_catalog(db)
            self.assertNotEqual(digest_v1, digest_v2)
        finally:
            db.close()

    def test_catalog_rejects_unknown_objects_migration_drift_and_unpinned_ddl(self):
        db = self.create_application_db(with_phone=True)
        try:
            db.execute("CREATE TABLE unexpected_restore_table(value TEXT)")
            with self.assertRaises(RecoveryUnavailable):
                validate_source_catalog(db)
            db.execute("DROP TABLE unexpected_restore_table")
            db.execute("CREATE INDEX unexpected_restore_index ON notes(title)")
            with self.assertRaises(RecoveryUnavailable):
                validate_source_catalog(db)
            db.execute("DROP INDEX unexpected_restore_index")
            db.execute("DELETE FROM migrations WHERE id=(SELECT id FROM migrations ORDER BY rowid DESC LIMIT 1)")
            with self.assertRaises(RecoveryUnavailable):
                validate_source_catalog(db)
        finally:
            db.close()

    def test_staging_uses_source_application_and_checkpoint_authority_only(self):
        source = self.create_application_db(with_phone=False)
        checkpoint = self.create_application_db(with_phone=True)
        staged = sqlite3.connect(":memory:", isolation_level=None)
        anchor = FakeProtectedAnchor("host-test")
        store = PhoneAdmissionStore(checkpoint, anchor)
        from jarvis.auth import ClientIdentity
        identity = ClientIdentity(name="test", user_id="alice")
        store.add_device(identity=identity, device_id="device-current", owner_id="alice",
                         public_key=b"checkpoint-key", key_algorithm="test-p256")
        store.add_grant(identity=identity, grant_id="grant-current", device_id="device-current",
                        owner_id="alice", scopes=["read", "voice"])
        store.login(identity=identity, session_id="session-current", grant_id="grant-current",
                    owner_id="alice", now=1, expires_at=100)
        source.execute("INSERT INTO notes(title,body,tags,created_at,updated_at,user_id) "
                       "VALUES('source-note','restored body','','t0','t1','alice')")
        source.commit()
        digest = authority_projection_sha256(checkpoint)
        fingerprint = reconcile_staged_database(source, checkpoint, staged, host_id="host-test",
            base_generation=anchor.state.host_generation, authority_sha256=digest)
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual(staged.execute("SELECT title,body FROM notes").fetchone(),
                         ("source-note", "restored body"))
        self.assertEqual(staged.execute("SELECT device_id,public_key FROM phone_remote_devices").fetchone(),
                         ("device-current", b"checkpoint-key"))
        self.assertEqual(staged.execute("SELECT grant_id,scopes_json FROM phone_remote_grants").fetchone(),
                         ("grant-current", '["read","voice"]'))
        self.assertEqual(staged.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertIsNone(staged.execute("SELECT name FROM sqlite_master WHERE name='phone_remote_restore_receipt'").fetchone())
        self.assertEqual(staged.execute("SELECT schema_version,host_id,host_generation,transition_state "
                                        "FROM phone_remote_meta").fetchone(),
                         (1, "host-test", anchor.state.host_generation, "stable"))
        source.close(); checkpoint.close(); staged.close()

    def test_staging_rejects_checkpoint_authority_or_identity_mismatch(self):
        source = self.create_application_db(with_phone=False)
        checkpoint = self.create_application_db(with_phone=True)
        staged = sqlite3.connect(":memory:", isolation_level=None)
        digest = authority_projection_sha256(checkpoint)
        with self.assertRaises(RecoveryUnavailable):
            reconcile_staged_database(source, checkpoint, staged, host_id="other-host",
                base_generation=1, authority_sha256=digest)
        self.assertEqual(staged.execute("SELECT count(*) FROM sqlite_master").fetchone()[0], 0)
        source.close(); checkpoint.close(); staged.close()

    def test_staged_database_pending_and_receipt_commit_replay_without_duplicate_effects(self):
        source = self.create_application_db(with_phone=False)
        checkpoint = self.create_application_db(with_phone=True)
        staged = sqlite3.connect(":memory:", isolation_level=None)
        anchor = FakeProtectedAnchor("host-test")
        store = PhoneAdmissionStore(checkpoint, anchor)
        from jarvis.auth import ClientIdentity
        identity = ClientIdentity(name="test", user_id="alice")
        store.add_device(identity=identity, device_id="d", owner_id="alice", public_key=b"k",
                         key_algorithm="test-p256")
        store.add_grant(identity=identity, grant_id="g", device_id="d", owner_id="alice",
                        scopes=["read"])
        store.login(identity=identity, session_id="old-session", grant_id="g", owner_id="alice",
                    now=1, expires_at=100)
        authority_hash = authority_projection_sha256(checkpoint)
        base_generation = anchor.state.host_generation
        reconcile_staged_database(source, checkpoint, staged, host_id="host-test",
            base_generation=base_generation, authority_sha256=authority_hash)
        operation_id = str(uuid.uuid4())
        manifest_hash, checkpoint_hash = "a" * 64, "b" * 64
        kwargs = dict(operation_id=operation_id, host_id="host-test",
            base_generation=base_generation, target_generation=base_generation + 1,
            manifest_sha256=manifest_hash, checkpoint_sha256=checkpoint_hash,
            authority_sha256=authority_hash)
        self.assertEqual(apply_pending_database(staged, **kwargs), "pending")
        pending_bytes = staged.serialize()
        self.assertEqual(apply_pending_database(staged, **kwargs), "pending")
        self.assertEqual(staged.serialize(), pending_bytes)
        self.assertEqual(staged.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        receipt = commit_reconciled_database(staged, operation_id=operation_id, host_id="host-test",
            target_generation=base_generation + 1, manifest_sha256=manifest_hash,
            checkpoint_sha256=checkpoint_hash, authority_sha256=authority_hash)
        stable_bytes = staged.serialize()
        self.assertEqual(commit_reconciled_database(staged, operation_id=operation_id,
            host_id="host-test", target_generation=base_generation + 1,
            manifest_sha256=manifest_hash, checkpoint_sha256=checkpoint_hash,
            authority_sha256=authority_hash), receipt)
        self.assertEqual(staged.serialize(), stable_bytes)
        new_anchor = FakeProtectedAnchor("host-test")
        new_anchor.state = AnchorState(1, "host-test", base_generation + 1, None, "stable",
                                       anchor.state.login_counter)
        reopened = PhoneAdmissionStore(staged, new_anchor)
        self.assertEqual(reopened.status()["schema_version"], 2)
        reopened.login(identity=identity, session_id="new-session", grant_id="g", owner_id="alice",
                       now=2, expires_at=100)
        self.assertEqual(tuple(staged.execute("SELECT operation_id,manifest_sha256,checkpoint_sha256 "
            "FROM phone_remote_restore_receipt WHERE singleton_id=1").fetchone()),
            (operation_id, manifest_hash, checkpoint_hash))
        source.close(); checkpoint.close(); staged.close()

    def test_resume_inspection_distinguishes_exact_base_pending_and_committed(self):
        db = self.create_application_db(with_phone=True)
        anchor = FakeProtectedAnchor("host-test")
        store = PhoneAdmissionStore(db, anchor)
        authority_hash = authority_projection_sha256(db)
        operation_id = str(uuid.uuid4())
        manifest_hash, checkpoint_hash, base_hash = "a" * 64, "b" * 64, "c" * 64
        identity = dict(operation_id=operation_id, host_id="host-test", base_generation=1,
            target_generation=2, manifest_sha256=manifest_hash,
            checkpoint_sha256=checkpoint_hash, authority_sha256=authority_hash,
            base_database_sha256=base_hash, expected_previous_receipt=None)
        self.assertEqual(inspect_database_state(db, actual_database_sha256=base_hash, **identity), "base")
        with self.assertRaises(RecoveryUnavailable):
            inspect_database_state(db, actual_database_sha256="d" * 64, **identity)

        self.assertEqual(apply_pending_database(db, operation_id=operation_id,
            host_id="host-test", base_generation=1, target_generation=2,
            manifest_sha256=manifest_hash, checkpoint_sha256=checkpoint_hash,
            authority_sha256=authority_hash), "pending")
        self.assertEqual(inspect_database_state(db, actual_database_sha256="d" * 64, **identity), "pending")
        commit_reconciled_database(db, operation_id=operation_id, host_id="host-test",
            target_generation=2, manifest_sha256=manifest_hash,
            checkpoint_sha256=checkpoint_hash, authority_sha256=authority_hash)
        # Ordinary app writes change the current byte identity; the stable
        # receipt is the commit evidence and historical database hash is not
        # used to reject the committed state.
        db.execute("INSERT INTO notes(title, body, created_at, updated_at) VALUES('ordinary', 'write', 'now', 'now')")
        db.commit()
        self.assertEqual(inspect_database_state(db, actual_database_sha256="e" * 64, **identity), "committed")
        with self.assertRaises(RecoveryUnavailable):
            inspect_database_state(db, **{**identity, "host_id": "other"},
                                   actual_database_sha256="e" * 64)
        db.close()

    def test_schema_v2_prior_receipt_survives_staging_and_pending_until_new_completion(self):
        source = self.create_application_db(with_phone=False)
        checkpoint = self.create_application_db(with_phone=True)
        staged = sqlite3.connect(":memory:", isolation_level=None)
        previous = (str(uuid.uuid4()), "host-test", 2, "1" * 64, "2" * 64, "3" * 64, 1)
        checkpoint.execute(RECEIPT_DDL)
        checkpoint.execute("UPDATE phone_remote_meta SET schema_version=2")
        checkpoint.execute("INSERT INTO phone_remote_restore_receipt VALUES(1,?,?,?,?,?,?,?)", previous)
        checkpoint.commit()
        authority_hash = authority_projection_sha256(checkpoint)
        new_manifest, new_checkpoint = "4" * 64, "5" * 64
        operation_id = str(uuid.uuid4())
        stage_pending_database(source, checkpoint, staged,
            operation_id=operation_id, host_id="host-test", base_generation=1,
            target_generation=2, manifest_sha256=new_manifest,
            checkpoint_sha256=new_checkpoint, authority_sha256=authority_hash,
            expected_previous_receipt=previous)
        self.assertEqual(_receipt(staged), previous)

        pending = dict(operation_id=operation_id, host_id="host-test", base_generation=1,
            target_generation=2, manifest_sha256=new_manifest,
            checkpoint_sha256=new_checkpoint, authority_sha256=authority_hash,
            expected_previous_receipt=previous)
        wrong_previous = (*previous[:3], "9" * 64, *previous[4:])
        pending_bytes = staged.serialize()
        with self.assertRaises(RecoveryUnavailable):
            apply_pending_database(staged, **{**pending, "expected_previous_receipt": wrong_previous})
        self.assertEqual(staged.serialize(), pending_bytes)
        self.assertEqual(_meta_for_test(staged)["transition_state"], "pending")
        self.assertEqual(_receipt(staged), previous)
        self.assertEqual(apply_pending_database(staged, **pending), "pending")
        self.assertEqual(_receipt(staged), previous,
                         "pending metadata must retain the previous completed receipt")
        commit_reconciled_database(staged, operation_id=operation_id, host_id="host-test",
            target_generation=2, manifest_sha256=new_manifest,
            checkpoint_sha256=new_checkpoint, authority_sha256=authority_hash,
            expected_previous_receipt=previous)
        self.assertNotEqual(_receipt(staged), previous)
        self.assertEqual(_receipt(staged), (operation_id, "host-test", 2,
            new_manifest, new_checkpoint, authority_hash, 1))
        source.close(); checkpoint.close(); staged.close()

    @staticmethod
    def create_store_db(path: Path) -> None:
        db = sqlite3.connect(path)
        try:
            from jarvis.db import run_migrations
            from jarvis.usage_ledger import _MODEL_BUDGET_SCHEMA, _SCHEMA
            run_migrations(db)
            db.executescript(_SCHEMA)
            db.executescript(_MODEL_BUDGET_SCHEMA)
            for ddl in SCHEMA_SQL.values():
                db.execute(ddl)
            db.execute("INSERT INTO phone_remote_meta VALUES(1,1,'host-test',4,NULL,'stable')")
            db.commit()
        finally:
            db.close()
        path.chmod(0o600)

    def test_live_database_normalization_and_checkpoint_use_distinct_hash_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = root / "live.db"
            checkpoint = root / "checkpoint.db"
            self.create_store_db(live)
            normalized = normalize_live_database(live)
            self.assertTrue(normalized.present)
            self.assertGreater(normalized.size_bytes, 0)
            self.assertFalse(Path(f"{live}-wal").exists())
            self.assertFalse(Path(f"{live}-shm").exists())
            record = create_checkpoint(live, checkpoint,
                                      expected_live_sha256=normalized.sha256)
            self.assertTrue(record.present)
            self.assertIsNotNone(record.sha256)
            self.assertIsNotNone(normalized.sha256)
            self.assertEqual(normalize_live_database(live).sha256, normalized.sha256)

    def test_normalization_fails_closed_for_active_writer_and_checkpoint_digest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = root / "live.db"
            self.create_store_db(live)
            writer = sqlite3.connect(live, isolation_level=None)
            writer.execute("BEGIN EXCLUSIVE")
            try:
                with self.assertRaises(RecoveryUnavailable):
                    normalize_live_database(live)
            finally:
                writer.execute("ROLLBACK")
                writer.close()
            normalized = normalize_live_database(live)
            with self.assertRaises(RecoveryUnavailable):
                create_checkpoint(live, root / "wrong.db", expected_live_sha256="0" * 64)
            self.assertFalse((root / "wrong.db").exists())
            record = create_checkpoint(live, root / "checkpoint.db",
                                       expected_live_sha256=normalized.sha256)
            self.assertTrue(record.present)

    def test_round_trip_closed_shape_and_exact_int_types(self):
        value = initial_journal()
        self.assertEqual(decode_journal(encode_journal(value)), value)
        malformed = dict(value, journal_version=True)
        with self.assertRaises(RecoveryUnavailable):
            validate_journal(malformed)

    def test_duplicate_keys_unknown_keys_and_noncanonical_identity_reject(self):
        value = encode_journal(initial_journal())
        with self.assertRaises(RecoveryUnavailable):
            decode_journal(value[:-1] + b',"phase":"complete"}')
        with self.assertRaises(RecoveryUnavailable):
            decode_journal(value.replace(b'"journal_version":1', b'"journal_version":1,"journal_version":1'))
        bad = initial_journal()
        bad["operation_id"] = bad["operation_id"].upper()
        with self.assertRaises(RecoveryUnavailable):
            validate_journal(bad)
        bad["operation_id"] = "not-a-uuid"
        with self.assertRaises(RecoveryUnavailable):
            validate_journal(bad)

    def test_present_empty_journal_file_and_unsafe_root_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)
            writer.path.write_bytes(b"")
            writer.path.chmod(0o600)
            with self.assertRaises(RecoveryUnavailable):
                writer.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            with self.assertRaises(RecoveryUnavailable):
                RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)

    def test_journal_phase_cannot_skip_durable_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)
            initial = initial_journal(writer.operation_id)
            writer._write_new(initial)
            jumped = dict(initial, phase="quiesced")
            with self.assertRaises(RecoveryUnavailable):
                writer.advance(jumped)

    def test_phase_cannot_move_back_and_final_digest_is_gated(self):
        value = initial_journal()
        value["phase"] = "staged"
        value["staged_database_sha256"] = "e" * 64
        value["cleanup_artifacts"]["staged_database"] = {"state": "pending", "sha256": "e" * 64}
        value["final_database_sha256"] = "b" * 64
        with self.assertRaises(RecoveryUnavailable):
            validate_journal(value)
        value["phase"] = "database_finalized"
        value["installed_database_sha256"] = "e" * 64
        value["rename_step"] = {"name": "staged_database", "action": "install",
                                "expected_sha256": "e" * 64, "state": "done"}
        value["cleanup_artifacts"]["staged_database"] = {"state": "done", "sha256": "e" * 64}
        value["cleanup_artifacts"]["old_database"] = {"state": "pending", "sha256": "d" * 64}
        validate_journal(value)

    def test_fixed_journal_reclaims_only_validated_temp_and_fsyncs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            op = str(uuid.uuid4())
            writer = RecoveryJournal(root, operation_id=op, manifest_sha256="a" * 64)
            files = {
                "database": FileRecord(True, 3, hashlib.sha256(b"db\n").hexdigest()),
                "wal": FileRecord(False, 0, None),
                "shm": FileRecord(False, 0, None),
            }
            # Checkpoint digest is retained in the cleanup catalog.
            first = initial_journal(op)
            writer._write_new(first)
            loaded = writer.load()
            self.assertEqual(loaded, first)
            writer.temp_path.write_bytes(b"interrupted")
            writer.temp_path.chmod(0o600)
            self.assertEqual(writer.load(), first)
            self.assertFalse(writer.temp_path.exists())

    def test_journal_write_interruption_boundaries_reconcile_from_canonical_file(self):
        """A temp is never authoritative; rename outcome is read from journal.json."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)
            initial = initial_journal(writer.operation_id)
            writer._write_new(initial)
            staged = dict(initial, phase="staged", staged_database_sha256="e" * 64)
            staged["cleanup_artifacts"] = dict(initial["cleanup_artifacts"],
                staged_database={"state": "pending", "sha256": "e" * 64})

            real_write = os.write
            remaining = {"bytes": 17}
            def partial_then_fail(fd, data):
                if remaining["bytes"]:
                    count = min(remaining["bytes"], len(data))
                    remaining["bytes"] -= count
                    return real_write(fd, data[:count])
                raise OSError("simulated partial journal write")
            with mock.patch("jarvis.bot.phone_remote_recovery.os.write", side_effect=partial_then_fail):
                with self.assertRaises(RecoveryUnavailable):
                    writer.advance(staged)
            self.assertTrue(writer.temp_path.exists())
            self.assertEqual(writer.load(), initial)
            self.assertFalse(writer.temp_path.exists())

            real_replace = os.replace
            def rename_then_lose_ack(source, target):
                real_replace(source, target)
                raise OSError("simulated rename acknowledgment loss")
            with mock.patch("jarvis.bot.phone_remote_recovery.os.replace", side_effect=rename_then_lose_ack):
                with self.assertRaises(RecoveryUnavailable):
                    writer.advance(staged)
            self.assertFalse(writer.temp_path.exists())
            self.assertEqual(writer.load(), staged)

            quiesced = dict(staged, phase="quiesced")
            with mock.patch.object(writer, "_fsync_root", side_effect=RecoveryUnavailable("simulated directory sync loss")):
                with self.assertRaises(RecoveryUnavailable):
                    writer.advance(quiesced)
            self.assertEqual(writer.load(), quiesced,
                             "after replace, recovery must inspect the canonical journal")

    def test_journal_transition_cannot_rewrite_file_or_cleanup_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)
            initial = initial_journal(writer.operation_id)
            writer._write_new(initial)

            changed_files = dict(initial)
            changed_files["files"] = dict(initial["files"], database={
                "present": True, "size_bytes": 3, "sha256": "f" * 64})
            with self.assertRaises(RecoveryUnavailable):
                writer.advance(changed_files)

            changed_checkpoint = dict(initial)
            changed_checkpoint["cleanup_artifacts"] = dict(initial["cleanup_artifacts"],
                checkpoint={"state": "pending", "sha256": "f" * 64})
            with self.assertRaises(RecoveryUnavailable):
                writer.advance(changed_checkpoint)
            self.assertEqual(writer.load(), initial)

    def test_unvalidated_orphan_temp_and_symlink_journal_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)
            writer.temp_path.write_bytes(b"orphan")
            with self.assertRaises(RecoveryUnavailable):
                writer.load()

    def test_fixed_file_moves_are_ordered_journaled_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            writer, live, wal, shm, staged = self.create_install_fixture(Path(directory))
            wal_hash = self.record(wal).sha256
            shm_hash = self.record(shm).sha256
            db_hash = self.record(live).sha256
            stage_hash = self.record(staged).sha256
            for name, digest in (("wal", wal_hash), ("shm", shm_hash), ("database", db_hash)):
                writer.move_database_file(live, name=name, action="move_to_quarantine",
                                          expected_sha256=digest)
                # Acknowledged operations are idempotent while they remain the
                # journal's latest durable step.
                before = writer.path.read_bytes()
                writer.move_database_file(live, name=name, action="move_to_quarantine",
                                          expected_sha256=digest)
                self.assertEqual(writer.path.read_bytes(), before)
            writer.move_database_file(live, name="staged_database", action="install",
                                      expected_sha256=stage_hash)
            writer.mark_installed()
            state = writer.load()
            self.assertEqual(state["rename_step"], {"name": "staged_database",
                "action": "install", "expected_sha256": stage_hash, "state": "done"})
            self.assertEqual(self.record(live).sha256, stage_hash)
            self.assertFalse(wal.exists()); self.assertFalse(shm.exists()); self.assertFalse(staged.exists())
            self.assertEqual(self.record(writer.root / "old.wal").sha256, wal_hash)
            self.assertEqual(self.record(writer.root / "old.shm").sha256, shm_hash)
            self.assertEqual(self.record(writer.root / "old.db").sha256, db_hash)

    def test_cleanup_is_ordered_durable_and_resumes_after_lost_unlink_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            writer, live, wal, shm, staged = self.create_install_fixture(Path(directory))
            for name in ("wal", "shm", "database"):
                writer.move_database_file(live, name=name, action="move_to_quarantine",
                    expected_sha256=self.record({"wal": wal, "shm": shm, "database": live}[name]).sha256)
            writer.move_database_file(live, name="staged_database", action="install",
                expected_sha256=self.record(staged).sha256)
            writer.mark_installed()
            writer.mark_database_committed()
            final_digest = self.record(live).sha256
            writer.mark_database_finalized(final_digest)
            writer.mark_anchor_committed()
            writer.begin_cleanup()

            self.assertEqual(writer.load()["cleanup_artifacts"]["staged_database"]["state"], "done")
            real_unlink = os.unlink

            def unlink_then_lose_ack(path, *args, **kwargs):
                result = real_unlink(path, *args, **kwargs)
                if Path(path).name == "checkpoint.db":
                    raise OSError("simulated unlink acknowledgment loss")
                return result

            with mock.patch("jarvis.bot.phone_remote_recovery.os.unlink", side_effect=unlink_then_lose_ack):
                with self.assertRaises(RecoveryUnavailable):
                    writer.cleanup_artifact("checkpoint")
            self.assertEqual(writer.load()["cleanup_artifacts"]["checkpoint"]["state"], "intent")
            writer.cleanup_artifact("checkpoint")
            for name in ("old_database", "old_wal", "old_shm"):
                writer.cleanup_artifact(name)
            state = writer.complete_cleanup()
            self.assertEqual(state["phase"], "complete")
            self.assertFalse((writer.root / "checkpoint.db").exists())
            self.assertFalse((writer.root / "staged.db").exists())
            self.assertFalse((writer.root / "old.db").exists())
            self.assertFalse((writer.root / "old.wal").exists())
            self.assertFalse((writer.root / "old.shm").exists())

    def test_interrupted_rename_resumes_from_intent_and_verified_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            writer, live, wal, shm, _ = self.create_install_fixture(Path(directory))
            wal_hash = self.record(wal).sha256
            shm_hash = self.record(shm).sha256
            digest = self.record(live).sha256
            writer.move_database_file(live, name="wal", action="move_to_quarantine",
                                      expected_sha256=wal_hash)
            writer.move_database_file(live, name="shm", action="move_to_quarantine",
                                      expected_sha256=shm_hash)
            real_rename = os.rename

            def rename_then_lose_ack(source, target):
                real_rename(source, target)
                raise OSError("simulated lost rename acknowledgment")

            with mock.patch("jarvis.bot.phone_remote_recovery.os.rename", side_effect=rename_then_lose_ack):
                with self.assertRaises(RecoveryUnavailable):
                    writer.move_database_file(live, name="database", action="move_to_quarantine",
                                              expected_sha256=digest)
            # Placement alone does not acknowledge the rename; retry must
            # verify the target and complete the durable journal receipt.
            state = writer.load()
            self.assertEqual(state["rename_step"]["state"], "intent")
            self.assertEqual(state["rename_step"]["name"], "database")
            writer.move_database_file(live, name="database", action="move_to_quarantine",
                                      expected_sha256=digest)
            self.assertFalse(live.exists())
            self.assertEqual(self.record(writer.root / "old.db").sha256, digest)

    def test_fixed_file_move_rejects_ambiguous_placement_and_wrong_order(self):
        with tempfile.TemporaryDirectory() as directory:
            writer, live, wal, _, _ = self.create_install_fixture(Path(directory))
            with self.assertRaises(RecoveryUnavailable):
                writer.move_database_file(live, name="database", action="move_to_quarantine",
                                          expected_sha256=self.record(live).sha256)
            self.assertTrue(live.exists()); self.assertTrue(wal.exists())

    def test_manifest_is_canonical_bounded_and_exactly_typed(self):
        value = {
            "manifest_version": 1, "operation_id": str(uuid.uuid4()),
            "host_id": "host-test", "base_generation": 8, "target_generation": 9,
            "source_id": "00000000-0000-4000-8000-000000000001", "source_schema_version": 1,
            "source_size_bytes": 4, "source_sha256": "a" * 64,
            "checkpoint_size_bytes": 4, "checkpoint_sha256": "b" * 64,
            "authority_sha256": "c" * 64, "base_database_sha256": "d" * 64,
        }
        data = encode_manifest(value)
        self.assertEqual(decode_manifest(data), value)
        with self.assertRaises(RecoveryUnavailable):
            decode_manifest(data.replace(b'"base_generation":8', b'"base_generation":8.0'))
        with self.assertRaises(RecoveryUnavailable):
            decode_manifest(data.replace(b'"host_id":"host-test"', b'"host_id":"host-test","extra":1'))
        with self.assertRaises(RecoveryUnavailable):
            encode_manifest({**value, "source_id": "caller-path-or-arbitrary-label"})
        value["target_generation"] = 10
        with self.assertRaises(RecoveryUnavailable):
            encode_manifest(value)

    def test_manifest_is_written_once_after_checkpoint_and_verified_on_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            live = root / "live.db"
            self.create_store_db(live)
            normalized = normalize_live_database(live)
            checkpoint_path = root / "checkpoint.db"
            checkpoint = create_checkpoint(live, checkpoint_path,
                                           expected_live_sha256=normalized.sha256)
            db = sqlite3.connect(live)
            try:
                meta = db.execute("SELECT host_id,host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()
                authority = authority_projection_sha256(db)
            finally:
                db.close()
            operation_id = str(uuid.uuid4())
            value = {"manifest_version": 1, "operation_id": operation_id,
                "host_id": meta[0], "base_generation": meta[1],
                "target_generation": meta[1] + 1, "source_id": "00000000-0000-4000-8000-000000000001",
                "source_schema_version": 1, "source_size_bytes": normalized.size_bytes,
                "source_sha256": normalized.sha256,
                "checkpoint_size_bytes": checkpoint.size_bytes,
                "checkpoint_sha256": checkpoint.sha256, "authority_sha256": authority,
                "base_database_sha256": normalized.sha256}
            encoded = encode_manifest(value)
            digest = hashlib.sha256(encoded).hexdigest()
            writer = RecoveryJournal(root, operation_id=operation_id, manifest_sha256=digest)
            self.assertEqual(writer.bind_manifest(encoded), value)
            self.assertEqual(writer.load_manifest(), value)
            self.assertEqual(writer.bind_manifest(encoded), value)
            changed = encoded.replace(b"00000000-0000-4000-8000-000000000001", b"00000000-0000-4000-8000-000000000002")
            with self.assertRaises(RecoveryUnavailable):
                writer.bind_manifest(changed)

    def test_file_staging_builds_pending_schema_v2_and_records_exact_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data_dir = base / "data"
            restore_parent = data_dir / ".phone-restore"
            data_dir.mkdir(mode=0o700); restore_parent.mkdir(mode=0o700)
            operation_id = str(uuid.uuid4())
            root = restore_parent / operation_id
            root.mkdir(mode=0o700)
            live = data_dir / "jarvis.db"
            self.create_store_db(live)
            normalized = normalize_live_database(live)
            checkpoint_record = create_checkpoint(live, root / "checkpoint.db",
                expected_live_sha256=normalized.sha256)
            checkpoint = sqlite3.connect(root / "checkpoint.db", isolation_level=None)
            source = self.create_application_db(with_phone=False)
            source_bytes = source.serialize()
            operation_meta = checkpoint.execute("SELECT host_id,host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()
            authority_hash = authority_projection_sha256(checkpoint)
            manifest = {"manifest_version": 1, "operation_id": operation_id,
                "host_id": operation_meta[0], "base_generation": operation_meta[1],
                "target_generation": operation_meta[1] + 1, "source_id": "00000000-0000-4000-8000-000000000001",
                "source_schema_version": 1, "source_size_bytes": len(source_bytes),
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "checkpoint_size_bytes": checkpoint_record.size_bytes,
                "checkpoint_sha256": checkpoint_record.sha256,
                "authority_sha256": authority_hash,
                "base_database_sha256": normalized.sha256}
            manifest_bytes = encode_manifest(manifest)
            manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            writer = RecoveryJournal(root, operation_id=operation_id,
                                     manifest_sha256=manifest_hash)
            files = {"database": self.record(live),
                "wal": FileRecord(False, 0, None), "shm": FileRecord(False, 0, None)}
            writer.create(files=files, checkpoint_sha256=checkpoint_record.sha256)
            writer.bind_manifest(manifest_bytes)
            with mock.patch.object(writer, "mark_staged",
                                   side_effect=RecoveryUnavailable("simulated lost stage journal acknowledgment")):
                with self.assertRaises(RecoveryUnavailable):
                    writer.stage_database(source, checkpoint)
            self.assertEqual(writer.load()["phase"], "checkpoint_bound")
            self.assertTrue((root / "staged.db").is_file())
            # Restart verifies the fixed file's complete source rows, authority,
            # pending metadata, receipt and integrity before binding its digest.
            staged_record = writer.stage_database(source, checkpoint)
            self.assertEqual(writer.load()["phase"], "staged")
            self.assertEqual(writer.load()["staged_database_sha256"], staged_record.sha256)
            self.assertEqual(writer.load()["cleanup_artifacts"]["staged_database"],
                             {"state": "pending", "sha256": staged_record.sha256})
            staged = sqlite3.connect(root / "staged.db")
            meta = staged.execute("SELECT schema_version,host_generation,transition_id,transition_state "
                                  "FROM phone_remote_meta WHERE singleton_id=1").fetchone()
            self.assertEqual(tuple(meta), (2, manifest["target_generation"], operation_id, "pending"))
            self.assertEqual(_receipt(staged), None)
            self.assertEqual(staged.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
            self.assertFalse(Path(f"{root / 'staged.db'}-wal").exists())
            staged.close(); source.close(); checkpoint.close()

    def test_disposable_full_database_transaction_journals_install_receipt_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data_dir = base / "data"
            restore_parent = data_dir / ".phone-restore"
            data_dir.mkdir(mode=0o700); restore_parent.mkdir(mode=0o700)
            operation_id = str(uuid.uuid4())
            root = restore_parent / operation_id
            root.mkdir(mode=0o700)
            live = data_dir / "jarvis.db"
            self.create_store_db(live)
            base_record = normalize_live_database(live)
            checkpoint_record = create_checkpoint(live, root / "checkpoint.db",
                expected_live_sha256=base_record.sha256)
            checkpoint = sqlite3.connect(root / "checkpoint.db", isolation_level=None)
            source = self.create_application_db(with_phone=False)
            source_bytes = source.serialize()
            meta = checkpoint.execute("SELECT host_id,host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()
            authority_hash = authority_projection_sha256(checkpoint)
            manifest = {"manifest_version": 1, "operation_id": operation_id,
                "host_id": meta[0], "base_generation": meta[1], "target_generation": meta[1] + 1,
                "source_id": "00000000-0000-4000-8000-000000000001", "source_schema_version": 1,
                "source_size_bytes": len(source_bytes),
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "checkpoint_size_bytes": checkpoint_record.size_bytes,
                "checkpoint_sha256": checkpoint_record.sha256,
                "authority_sha256": authority_hash, "base_database_sha256": base_record.sha256}
            manifest_bytes = encode_manifest(manifest)
            manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
            writer = RecoveryJournal(root, operation_id=operation_id,
                                     manifest_sha256=manifest_digest)
            writer.create(files={"database": self.record(live),
                "wal": FileRecord(False, 0, None), "shm": FileRecord(False, 0, None)},
                checkpoint_sha256=checkpoint_record.sha256)
            writer.bind_manifest(manifest_bytes)
            staged_record = writer.stage_database(source, checkpoint)
            writer.mark_quiesced()
            writer.begin_installation()
            for name in ("wal", "shm"):
                writer.move_database_file(live, name=name, action="move_to_quarantine",
                                          expected_sha256=None)
            old_digest = self.record(live).sha256
            writer.move_database_file(live, name="database", action="move_to_quarantine",
                                      expected_sha256=old_digest)
            writer.move_database_file(live, name="staged_database", action="install",
                                      expected_sha256=staged_record.sha256)
            writer.mark_installed()
            checkpoint.close(); source.close()

            installed = sqlite3.connect(live, isolation_level=None)
            receipt = commit_reconciled_database(installed, operation_id=operation_id,
                host_id=manifest["host_id"], target_generation=manifest["target_generation"],
                manifest_sha256=manifest_digest, checkpoint_sha256=manifest["checkpoint_sha256"],
                authority_sha256=authority_hash)
            installed.close()
            writer.mark_database_committed()
            final_record = normalize_live_database(live)
            writer.mark_database_finalized(final_record.sha256)
            tombstone = {"operation_id": operation_id, "target_generation": manifest["target_generation"],
                "manifest_sha256": manifest_digest, "checkpoint_sha256": manifest["checkpoint_sha256"],
                "database_sha256": final_record.sha256}
            check = sqlite3.connect(live, isolation_level=None)
            self.assertEqual(validate_receipt_tombstone(check, tombstone=tombstone,
                host_id=manifest["host_id"], retained_manifest_bytes=manifest_bytes), receipt)
            check.close()
            writer.mark_anchor_committed()
            writer.begin_cleanup()
            for name in ("checkpoint", "staged_database", "old_database", "old_wal", "old_shm"):
                writer.cleanup_artifact(name)
            self.assertEqual(writer.complete_cleanup()["phase"], "complete")
            self.assertTrue(writer.manifest_path.is_file(), "completion manifest remains as receipt evidence")
            self.assertEqual(writer.load_manifest(), manifest)
            self.assertEqual(self.record(live).sha256, final_record.sha256)

    def test_recovery_protocol_prepare_and_resume_sequences_are_closed(self):
        operation_id = str(uuid.uuid4())
        common = {"operation_id": operation_id, "manifest_sha256": "a" * 64}
        calls = []
        def preflight(payload):
            calls.append(("preflight", payload))
            return {**common, "status": "ok", "checkpoint_sha256": "b" * 64,
                "authority_sha256": "c" * 64, "base_database_sha256": "d" * 64,
                "checkpoint_size_bytes": 100}
        def pending(payload):
            calls.append(("pending", payload))
            return {"operation_id": operation_id, "status": "ok", "host_id": "host-test",
                "target_generation": 9, "transition_state": "pending"}
        prepare = RecoveryProtocolSession(mode="prepare", operation_id=operation_id,
            host_id="host-test", target_generation=9, manifest_sha256="a" * 64,
            executors={"preflight": preflight, "commit_pending": pending})
        self.assertEqual(prepare.ready_payload["mode"], "prepare")
        with self.assertRaises(RecoveryUnavailable):
            prepare.handle("owner.restore.commit_pending", {**common,
                "checkpoint_sha256": "b" * 64, "authority_sha256": "c" * 64,
                "target_generation": 9})
        with self.assertRaises(RecoveryUnavailable):
            prepare.handle("owner.restore.preflight", common)
        prepare = RecoveryProtocolSession(mode="prepare", operation_id=operation_id,
            host_id="host-test", target_generation=9, manifest_sha256="a" * 64,
            executors={"preflight": preflight, "commit_pending": pending})
        request = {"operation_id": operation_id, "manifest_sha256": "a" * 64}
        self.assertEqual(prepare.handle("owner.restore.preflight", request)[0],
                         "child.restore.preflight_result")
        self.assertEqual(prepare.handle("owner.restore.commit_pending", {**common,
            "checkpoint_sha256": "b" * 64, "authority_sha256": "c" * 64,
            "target_generation": 9})[0], "child.restore.pending_result")
        self.assertEqual(prepare.handle("owner.shutdown", {"operation_id": operation_id,
            "reason": "prepare_complete"}), ("child.shutdown_ack", {"operation_id": operation_id}))
        self.assertEqual([item[0] for item in calls], ["preflight", "pending"])

        resume = RecoveryProtocolSession(mode="prepare_resume", operation_id=operation_id,
            checkpoint_sha256="b" * 64, authority_sha256="c" * 64,
            host_id="host-test", target_generation=9, manifest_sha256="a" * 64,
            executors={"resume_preflight": lambda payload: {"operation_id": operation_id,
                "status": "ok", "database_state": "pending",
                "base_database_sha256": "d" * 64}, "commit_pending": pending})
        self.assertEqual(resume.handle("owner.restore.resume_preflight", {**request,
            "base_database_sha256": "d" * 64})[0], "child.restore.resume_preflight_result")
        with self.assertRaises(RecoveryUnavailable):
            resume.handle("owner.restore.commit_pending", {**common,
                "checkpoint_sha256": "b" * 64, "authority_sha256": "c" * 64,
                "target_generation": 9})
        with self.assertRaises(RecoveryUnavailable):
            resume.handle("owner.shutdown", {"operation_id": operation_id,
                "reason": "prepare_resume_complete"})

    def test_recovery_protocol_inspect_stage_install_commit_and_blocked_exit(self):
        operation_id = str(uuid.uuid4())
        manifest = "a" * 64
        events = []
        def record(name, result):
            def execute(payload):
                events.append((name, dict(payload)))
                return result
            return execute
        protocol = RecoveryProtocolSession(mode="recover", operation_id=operation_id,
            host_id="host-test", target_generation=9, manifest_sha256=manifest,
            executors={
                "inspect": record("inspect", {"operation_id": operation_id, "status": "ok",
                    "phase": "checkpoint_bound", "database_state": "pending",
                    "checkpoint_sha256": "b" * 64, "authority_sha256": "c" * 64,
                    "base_database_sha256": "d" * 64, "staged_database_sha256": None,
                    "installed_database_sha256": None}),
                "stage": record("stage", {"operation_id": operation_id, "status": "ok",
                    "staged_database_sha256": "e" * 64, "staged_size_bytes": 400,
                    "store_schema_version": 2}),
                "install": record("install", {"operation_id": operation_id, "status": "ok",
                    "installed_database_sha256": "e" * 64, "phase": "installed"}),
                "commit_database": record("commit_database", {"operation_id": operation_id,
                    "status": "ok", "receipt_version": 1, "database_sha256": "f" * 64,
                    "phase": "database_committed"}),
            })
        self.assertEqual(protocol.handle("owner.restore.inspect", {
            "operation_id": operation_id, "manifest_sha256": manifest})[0],
            "child.restore.inspect_result")
        self.assertEqual(protocol.handle("owner.restore.stage", {
            "operation_id": operation_id, "manifest_sha256": manifest,
            "checkpoint_sha256": "b" * 64})[0], "child.restore.stage_result")
        self.assertEqual(protocol.handle("owner.restore.install", {
            "operation_id": operation_id, "manifest_sha256": manifest,
            "checkpoint_sha256": "b" * 64,
            "staged_database_sha256": "e" * 64})[0], "child.restore.install_result")
        self.assertEqual(protocol.handle("owner.restore.commit_database", {
            "operation_id": operation_id, "manifest_sha256": manifest,
            "checkpoint_sha256": "b" * 64, "installed_database_sha256": "e" * 64,
            "target_generation": 9})[0], "child.restore.database_committed")
        self.assertEqual(protocol.handle("owner.shutdown", {"operation_id": operation_id,
            "reason": "recovery_complete"})[0], "child.shutdown_ack")
        self.assertEqual([event[0] for event in events], ["inspect", "stage", "install", "commit_database"])
        with self.assertRaises(RecoveryUnavailable):
            protocol.handle("owner.restore.inspect", {"operation_id": operation_id,
                "manifest_sha256": manifest})

        denied = RecoveryProtocolSession(mode="prepare", operation_id=operation_id,
            host_id="host-test", target_generation=9, manifest_sha256=manifest,
            executors={"preflight": lambda payload: {"operation_id": operation_id,
                "status": "blocked", "code": "source_unavailable"},
                "commit_pending": lambda payload: self.fail("blocked preflight must not commit")})
        self.assertEqual(denied.handle("owner.restore.preflight", {
            "operation_id": operation_id, "manifest_sha256": manifest})[1]["code"],
            "source_unavailable")
        self.assertEqual(denied.handle("owner.shutdown", {"operation_id": operation_id,
            "reason": "preflight_denied"})[0], "child.shutdown_ack")

    def test_recovery_transactions_rollback_ddl_and_each_statement_in_both_modes(self):
        for isolation in (None, "IMMEDIATE"):
            for failing_table in ("phone_remote_meta", "phone_remote_sessions"):
                with self.subTest(isolation=isolation, failing_table=failing_table):
                    db = sqlite3.connect(":memory:", isolation_level=isolation)
                    for ddl in SCHEMA_SQL.values():
                        db.execute(ddl)
                    db.execute("INSERT INTO phone_remote_meta VALUES(1,1,'host-test',4,NULL,'stable')")
                    db.commit()
                    identity = dict(operation_id=str(uuid.uuid4()), host_id="host-test",
                        target_generation=5, manifest_sha256="a" * 64,
                        checkpoint_sha256="b" * 64, authority_sha256=authority_projection_sha256(db))
                    before = list(db.iterdump())
                    db.set_authorizer(lambda action, table, *rest:
                        sqlite3.SQLITE_DENY if action in {sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE} and table == failing_table
                        else sqlite3.SQLITE_OK)
                    with self.assertRaises(RecoveryUnavailable):
                        apply_pending_database(db, base_generation=4, **identity)
                    db.set_authorizer(None)
                    self.assertFalse(db.in_transaction)
                    self.assertEqual(list(db.iterdump()), before)
                    apply_pending_database(db, base_generation=4, **identity)
                    before = list(db.iterdump())
                    db.set_authorizer(lambda action, table, *rest:
                        sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT
                            and table == "phone_remote_restore_receipt" else sqlite3.SQLITE_OK)
                    with self.assertRaises(RecoveryUnavailable):
                        commit_reconciled_database(db, **identity)
                    db.set_authorizer(None)
                    self.assertFalse(db.in_transaction)
                    self.assertEqual(list(db.iterdump()), before)
                    db.close()

    def test_recovery_inspection_can_repeat_and_continue_each_committed_crash_phase(self):
        for phase, state, next_step in (("quiesced", "pending", "install"),
                ("installing", "pending", "install"), ("installed", "committed", "commit_database"),
                ("database_committed", "committed", "commit_database"),
                ("database_finalized", "committed", "commit_database")):
            with self.subTest(phase=phase):
                op = str(uuid.uuid4())
                common = {"operation_id": op, "manifest_sha256": "a" * 64}
                observed = {"operation_id": op, "status": "ok", "phase": phase,
                    "database_state": state, "checkpoint_sha256": "b" * 64,
                    "authority_sha256": "c" * 64, "base_database_sha256": "d" * 64,
                    "staged_database_sha256": "e" * 64,
                    "installed_database_sha256": "e" * 64 if state == "committed" else None}
                effects = []
                def resume(payload):
                    effects.append(next_step)
                    if next_step == "install":
                        return {"operation_id": op, "status": "ok", "phase": "installed",
                                "installed_database_sha256": "e" * 64}
                    return {"operation_id": op, "status": "ok", "phase": "database_committed",
                            "receipt_version": 1, "database_sha256": "f" * 64}
                protocol = RecoveryProtocolSession(mode="recover", operation_id=op,
                    host_id="host-test", target_generation=2, manifest_sha256="a" * 64,
                    executors={"inspect": lambda p: dict(observed), "stage": lambda p: self.fail("restage"),
                               "install": resume, "commit_database": resume})
                for _ in range(2):
                    self.assertEqual(protocol.handle("owner.restore.inspect", common)[1], observed)
                payload = {**common, "checkpoint_sha256": "b" * 64}
                if next_step == "install": payload["staged_database_sha256"] = "e" * 64
                else: payload.update(installed_database_sha256="e" * 64, target_generation=2)
                protocol.handle("owner.restore." + next_step, payload)
                self.assertEqual(effects, [next_step])

    def test_recovery_callback_failure_and_reentrancy_are_terminal(self):
        for reentrant in (False, True):
            events = []
            op = str(uuid.uuid4())
            common = {"operation_id": op, "manifest_sha256": "a" * 64}
            request = {**common, "checkpoint_sha256": "b" * 64,
                       "authority_sha256": "c" * 64, "target_generation": 2}
            def mutate(payload):
                events.append("effect")
                if reentrant:
                    with self.assertRaises(RecoveryUnavailable):
                        session.handle("owner.restore.commit_pending", request)
                    return {"operation_id": op, "status": "ok", "host_id": "host-test",
                            "target_generation": 2, "transition_state": "pending"}
                raise OSError("uncertain after effect")
            session = RecoveryProtocolSession(mode="prepare", operation_id=op, host_id="host-test",
                target_generation=2, manifest_sha256="a" * 64, executors={
                    "preflight": lambda p: {**common, "status": "ok", "checkpoint_sha256": "b" * 64,
                        "authority_sha256": "c" * 64, "base_database_sha256": "d" * 64,
                        "checkpoint_size_bytes": 100}, "commit_pending": mutate})
            session.handle("owner.restore.preflight", common)
            with self.assertRaises((OSError, RecoveryUnavailable)):
                session.handle("owner.restore.commit_pending", request)
            with self.assertRaises(RecoveryUnavailable):
                session.handle("owner.restore.commit_pending", request)
            self.assertEqual(events, ["effect"])

    def test_pending_request_cannot_replace_verified_hashes_or_integer_types(self):
        for field, value in (("checkpoint_sha256", "e" * 64), ("authority_sha256", "f" * 64),
                             ("target_generation", 2.0), ("target_generation", True)):
            op = str(uuid.uuid4())
            common = {"operation_id": op, "manifest_sha256": "a" * 64}
            session = RecoveryProtocolSession(mode="prepare", operation_id=op, host_id="host-test",
                target_generation=2, manifest_sha256="a" * 64, executors={
                    "preflight": lambda p: {**common, "status": "ok", "checkpoint_sha256": "b" * 64,
                        "authority_sha256": "c" * 64, "base_database_sha256": "d" * 64,
                        "checkpoint_size_bytes": 100},
                    "commit_pending": lambda p: self.fail("unbound mutation executed")})
            session.handle("owner.restore.preflight", common)
            request = {**common, "checkpoint_sha256": "b" * 64, "authority_sha256": "c" * 64,
                       "target_generation": 2, field: value}
            with self.assertRaises(RecoveryUnavailable):
                session.handle("owner.restore.commit_pending", request)

    def test_authority_projection_is_order_stable_and_rejects_noncanonical_scopes(self):
        db = sqlite3.connect(":memory:")
        try:
            for ddl in SCHEMA_SQL.values():
                db.execute(ddl)
            db.execute("INSERT INTO phone_remote_meta VALUES(1,1,'host-test',1,NULL,'stable')")
            db.execute("INSERT INTO phone_remote_devices VALUES('d','alice',?,'p256',NULL)", (b"key",))
            db.execute("INSERT INTO phone_remote_grants VALUES('g','d','alice','[\"voice\",\"read\"]',1,NULL)")
            first = authority_projection_sha256(db)
            db.execute("UPDATE phone_remote_grants SET scopes_json='[\"read\",\"voice\"]'")
            self.assertEqual(authority_projection_sha256(db), first)
            db.execute("UPDATE phone_remote_grants SET scopes_json='[\"read\",\"read\"]'")
            with self.assertRaises(RecoveryUnavailable):
                authority_projection_sha256(db)
        finally:
            db.close()

    def test_pending_transition_is_idempotent_and_completion_receipt_is_mapped(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            for ddl in SCHEMA_SQL.values():
                db.execute(ddl)
            db.execute("INSERT INTO phone_remote_meta VALUES(1,1,'host-test',4,NULL,'stable')")
            operation_id = str(uuid.uuid4())
            authority_hash = authority_projection_sha256(db)
            manifest = {
                "manifest_version": 1, "operation_id": operation_id, "host_id": "host-test",
                "base_generation": 4, "target_generation": 5, "source_id": "00000000-0000-4000-8000-000000000001",
                "source_schema_version": 1, "source_size_bytes": 1, "source_sha256": "1" * 64,
                "checkpoint_size_bytes": 1, "checkpoint_sha256": "2" * 64,
                "authority_sha256": authority_hash, "base_database_sha256": "3" * 64,
            }
            manifest_bytes = encode_manifest(manifest)
            manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            pending_anchor = {
                "anchor_version": 2, "host_id": "host-test", "host_generation": 5,
                "transition_id": operation_id, "transition_state": "pending",
                "login_counter": 7,
                "pending_restore": {"operation_id": operation_id, "target_generation": 5,
                    "manifest_sha256": manifest_hash, "checkpoint_sha256": "2" * 64},
                "last_completed_restore": None,
            }
            self.assertEqual(validate_pending_anchor_v2(pending_anchor,
                manifest_bytes=manifest_bytes, checkpoint_sha256="2" * 64), manifest)
            for invalid_generation in (6, 5.0, True, "5"):
                malformed_anchor = dict(pending_anchor,
                    pending_restore=dict(pending_anchor["pending_restore"], target_generation=invalid_generation))
                with self.subTest(nested_generation=invalid_generation), self.assertRaises(RecoveryUnavailable):
                    validate_pending_anchor_v2(malformed_anchor,
                        manifest_bytes=manifest_bytes, checkpoint_sha256="2" * 64)
            kwargs = dict(operation_id=operation_id, host_id="host-test", base_generation=4,
                          target_generation=5, manifest_sha256=manifest_hash,
                          checkpoint_sha256="2" * 64, authority_sha256=authority_hash)
            self.assertEqual(apply_pending_database(db, **kwargs), "pending")
            self.assertEqual(apply_pending_database(db, **kwargs), "pending")
            receipt = commit_reconciled_database(db, operation_id=operation_id, host_id="host-test",
                target_generation=5, manifest_sha256=manifest_hash, checkpoint_sha256="2" * 64,
                authority_sha256=authority_hash)
            tombstone = {"operation_id": operation_id, "target_generation": 5,
                         "manifest_sha256": manifest_hash, "checkpoint_sha256": "2" * 64,
                         "database_sha256": "4" * 64}
            self.assertEqual(validate_receipt_tombstone(db, tombstone=tombstone, host_id="host-test",
                                                       retained_manifest_bytes=manifest_bytes), receipt)
            self.assertEqual(commit_reconciled_database(db, operation_id=operation_id,
                host_id="host-test", target_generation=5, manifest_sha256=manifest_hash,
                checkpoint_sha256="2" * 64, authority_sha256=authority_hash), receipt)
            db.execute("UPDATE phone_remote_meta SET host_generation=6")
            # Ordinary mutations change current DB state; the historical DB hash
            # remains intentionally excluded from receipt comparison.
            self.assertEqual(validate_receipt_tombstone(db, tombstone=tombstone, host_id="host-test",
                                                        retained_manifest_bytes=manifest_bytes), receipt)
        finally:
            db.close()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RecoveryJournal(root, operation_id=str(uuid.uuid4()), manifest_sha256="a" * 64)
            target = root / "target"
            target.write_bytes(encode_journal(initial_journal(writer.operation_id)))
            writer.path.symlink_to(target)
            with self.assertRaises((RecoveryUnavailable, OSError)):
                writer.load()


@unittest.skipUnless(os.environ.get("PHONE_REMOTE_AUTHORITY_OWNER_BIN"), "requires offline native owner")
class RecoveryActualProcessTests(unittest.TestCase):
    def fixture(self, root):
        for name, with_phone in (("jarvis.db", True), ("source.db", True)):
            db = RecoveryJournalCodecTests.create_application_db(with_phone=with_phone)
            db.execute("INSERT INTO notes(title,body,created_at,updated_at) VALUES(?,?,?,?)",
                       ("synthetic", "current" if name == "jarvis.db" else "restored", "0", "0"))
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import serialization
            key = ec.derive_private_key(1, ec.SECP256R1()).public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            device = "current-device" if name == "jarvis.db" else "stale-device"
            db.execute("INSERT INTO phone_remote_devices VALUES(?,?,?,?,NULL)",
                       (device, "alice", key, "p256-sha256-sec1-v1"))
            db.execute("INSERT INTO phone_remote_grants VALUES(?,?,?,?,?,NULL)",
                       ("current-grant", device, "alice", '["read","voice"]', 1))
            db.commit()
            target = sqlite3.connect(str(root / name))
            db.backup(target); target.close(); db.close()
            (root / name).chmod(0o600)
        (root / "owner.lock").touch(mode=0o600)
        (root / "anchor.json").write_text(json.dumps(dict(anchor_version=1, host_id="host-test",
            host_generation=1, transition_id=None, transition_state="stable", login_counter=7)))
        (root / "anchor.json").chmod(0o600)

    def launch(self, root, failpoint=None, *, begin=False):
        import subprocess, sys
        env = os.environ.copy()
        env["PHONE_REMOTE_AUTHORITY_READY_FILE"] = str(root / "ready")
        env["PHONE_REMOTE_AUTHORITY_RECOVERY_BEGIN"] = "1" if begin else "0"
        if failpoint:
            env["PHONE_REMOTE_AUTHORITY_FAILPOINT"] = failpoint
        else:
            env.pop("PHONE_REMOTE_AUTHORITY_FAILPOINT", None)
        return subprocess.Popen([env["PHONE_REMOTE_AUTHORITY_OWNER_BIN"], "--test-owner",
            str(root / "owner.lock"), sys.executable, str(root / "jarvis.db"), str(Path.cwd()),
            "v4-recovery", "0", "0", "1", "7", str(root / "anchor.json")], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def complete(self, root, *, begin=False, generation=2, counter=7, failpoint=None):
        process = self.launch(root, failpoint, begin=begin)
        try:
            out, err = process.communicate(timeout=15)
        except BaseException:
            process.kill(); process.communicate(); raise
        self.assertEqual(process.returncode, 0, err.decode() +
            ((root / "child-failure").read_text() if (root / "child-failure").exists() else ""))
        anchor = json.loads((root / "anchor.json").read_bytes())
        self.assertEqual((anchor["anchor_version"], anchor["host_generation"], anchor["login_counter"]), (2, generation, counter))
        self.assertIsNone(anchor["pending_restore"])
        receipt = json.loads((root / "ready").read_bytes())
        self.assertEqual(receipt["first"]["child_incarnation"], receipt["repeated"]["child_incarnation"])
        self.assertNotEqual(receipt["first"]["request_correlation"], receipt["repeated"]["request_correlation"])
        db = sqlite3.connect(str(root / "jarvis.db"))
        try:
            self.assertEqual(db.execute("SELECT body FROM notes").fetchall(), [("restored",)])
            self.assertEqual(db.execute("SELECT device_id FROM phone_remote_devices").fetchall(), [("current-device",)])
            self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone(), (0,))
        finally:
            db.close()
        op_root = root / ".phone-restore" / anchor["last_completed_restore"]["operation_id"]
        self.assertEqual(decode_journal((op_root / "journal.json").read_bytes())["phase"], "complete")
        self.assertEqual({path.name for path in op_root.iterdir()}, {"journal.json", "manifest.json"})
        return anchor

    def test_native_owner_recovers_and_completed_restart_preserves_database_and_tombstone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            first = self.complete(root)
            witnesses = json.loads((root / "ready").read_bytes())["prepared"]
            self.assertEqual(len(witnesses), 2)
            self.assertEqual(witnesses[0]["status"], "pending")
            self.assertEqual(witnesses[0]["owner_incarnation"], witnesses[1]["owner_incarnation"])
            self.assertNotEqual(witnesses[0]["request_correlation"], witnesses[1]["request_correlation"])
            before = (root / "jarvis.db").read_bytes()
            (root / "source.db").unlink()  # completion does not reopen the old source
            (root / "ready").unlink()
            second = self.complete(root)
            self.assertEqual(len(list(root.glob("quiesce-*.request"))), 1)
            self.assertEqual(first, second)
            self.assertEqual(before, (root / "jarvis.db").read_bytes())

    def test_lost_acknowledgments_resume_actual_durable_phases(self):
        import time
        for point in ("pending-anchor", "commit_pending", "stage", "install", "commit_database"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                process = self.launch(root, "r324-after-" + point)
                try:
                    deadline = time.monotonic() + 10
                    while not (root / "interrupted").exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue((root / "interrupted").exists())
                    self.assertFalse((root / "ready").exists())
                    anchor = json.loads((root / "anchor.json").read_bytes())
                    self.assertEqual(anchor["transition_state"], "pending")
                finally:
                    if process.poll() is None: process.terminate()
                    process.communicate(timeout=5)
                # A new native owner reacquires the same inode, re-reads state,
                # and starts distinct prepare_resume/recover incarnations.
                self.complete(root)

    def test_legacy_pending_is_held_without_source_child_or_implicit_upgrade(self):
        import time
        for transition, code in ((str(uuid.uuid4()), "legacy_pending_unbound"),
                                 ("login:" + "a" * 32, "transaction_mismatch")):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                anchor = json.loads((root / "anchor.json").read_bytes())
                anchor.update(transition_state="pending", transition_id=transition)
                (root / "anchor.json").write_text(json.dumps(anchor))
                with sqlite3.connect(root / "jarvis.db") as db:
                    db.execute("UPDATE phone_remote_meta SET transition_state='pending',transition_id=?", (transition,))
                (root / "source.db").unlink()
                before = (root / "jarvis.db").read_bytes()
                process = self.launch(root)
                try:
                    deadline = time.monotonic() + 3
                    while not (root / "blocked").exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
                    self.assertIsNone(process.poll())
                    self.assertEqual(json.loads((root / "blocked").read_bytes()), {"status": "blocked", "code": code})
                    self.assertEqual(before, (root / "jarvis.db").read_bytes())
                    self.assertEqual(list(root.glob("quiesce-*.pid")), [])
                    self.assertFalse((root / ".phone-restore").exists())
                finally:
                    if process.poll() is None: process.terminate()
                    process.communicate(timeout=5)

    def test_surviving_v4_child_excludes_replacement_after_owner_death(self):
        import time, signal, fcntl
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            owner = self.launch(root, "r324-drain-stall-ignore-term")
            child_pid = None
            replacement = None
            try:
                deadline = time.monotonic() + 5
                while not list(root.glob("quiesce-*.activity")) and owner.poll() is None and time.monotonic() < deadline: time.sleep(.005)
                self.assertTrue(list(root.glob("quiesce-*.activity")))
                pid_file = next(root.glob("quiesce-*.pid"))
                child_pid = json.loads(pid_file.read_bytes())["pid"]
                owner.kill(); owner.communicate(timeout=5)
                os.kill(child_pid, 0)  # exact child still owns inherited descriptor 4
                with (root / "owner.lock").open("rb") as lock:
                    with self.assertRaises(BlockingIOError): fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                before = ((root / "jarvis.db").read_bytes(), (root / "anchor.json").read_bytes())
                replacement = self.launch(root)
                replacement.communicate(timeout=3)
                self.assertNotEqual(replacement.returncode, 0)
                os.kill(child_pid, 0)  # replacement did not signal/adopt it
                self.assertEqual(len(list(root.glob("quiesce-*.pid"))), 1)
                self.assertEqual(before, ((root / "jarvis.db").read_bytes(), (root / "anchor.json").read_bytes()))
                self.assertFalse((root / ".phone-restore").exists())
            finally:
                if owner.poll() is None: owner.kill(); owner.communicate(timeout=5)
                if replacement is not None and replacement.poll() is None: replacement.kill(); replacement.communicate(timeout=5)
                if child_pid is not None:
                    # Test teardown targets only its own recorded orphan. The
                    # replacement owner never signals or adopts another owner’s child.
                    try: os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    until = time.monotonic() + 3
                    with (root / "owner.lock").open("rb") as lock:
                        while True:
                            try:
                                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                break
                            except BlockingIOError:
                                if time.monotonic() >= until: raise
                                time.sleep(.005)

    def test_native_cleanup_reclaims_partial_private_temp_before_next_update(self):
        for data in (b"", b'{"partial":', b'{"complete":"orphan"}'):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                self.interrupt_stable(root, "r324-after-stable-anchor")
                anchor = json.loads((root / "anchor.json").read_bytes())
                operation_root = root / ".phone-restore" / anchor["last_completed_restore"]["operation_id"]
                temp = operation_root / "journal.next.tmp"
                fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as stream: stream.write(data)
                self.complete(root)
                self.assertFalse(temp.exists())

    def test_same_owner_continuation_rejects_other_operation_then_finishes_without_new_incarnation(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            process = self.launch(root, "r324-after-commit_database")
            try:
                deadline = time.monotonic() + 10
                while not (root / "blocked").exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
                self.assertTrue((root / "blocked").exists())
                anchor = json.loads((root / "anchor.json").read_bytes())
                op = anchor["pending_restore"]["operation_id"]
                before = (root / "jarvis.db").read_bytes()
                def request(operation):
                    correlation = str(uuid.uuid4())
                    temp = root / "continue.tmp"
                    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, "w") as stream:
                        stream.write(json.dumps({"operation_id": operation, "request_correlation": correlation},
                            sort_keys=True, separators=(",", ":")))
                    os.replace(temp, root / "continue.request")
                    response = root / ("continue-" + correlation + ".response")
                    until = time.monotonic() + 5
                    while not response.exists() and process.poll() is None and time.monotonic() < until: time.sleep(.01)
                    return json.loads(response.read_bytes())
                denied = request(str(uuid.uuid4()))
                self.assertEqual((denied["status"], denied["code"]), ("blocked", "operation_mismatch"))
                self.assertEqual(before, (root / "jarvis.db").read_bytes())
                pending = request(op)
                self.assertEqual(pending["status"], "pending")
                _, err = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, err.decode())
                completed = json.loads((root / "ready").read_bytes())["first"]
                self.assertEqual(completed["operation_id"], op)
                self.assertEqual(completed["owner_incarnation"], pending["owner_incarnation"])
                self.assertEqual(before, (root / "jarvis.db").read_bytes())
            finally:
                if process.poll() is None: process.terminate(); process.communicate(timeout=5)

    def test_normal_readiness_checks_each_receipt_field_and_retained_manifest(self):
        from jarvis.bot.phone_remote_recovery import normal_service_receipt
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            protected = self.complete(root)
            with sqlite3.connect(root / "jarvis.db") as db:
                self.assertEqual(normal_service_receipt(db, protected)["store_schema_version"], 2)
                db.execute("PRAGMA ignore_check_constraints=ON")
                for field, value in (("operation_id", str(uuid.uuid4())), ("host_id", "different-host"),
                        ("target_generation", 3), ("manifest_sha256", "a" * 64),
                        ("checkpoint_sha256", "b" * 64), ("authority_sha256", "c" * 64),
                        ("receipt_version", 2)):
                    with self.subTest(field=field):
                        db.execute("BEGIN")
                        db.execute("UPDATE phone_remote_restore_receipt SET " + field + "=?", (value,))
                        with self.assertRaises(RecoveryUnavailable): normal_service_receipt(db, protected)
                        db.rollback()
                manifest_path = root / ".phone-restore" / protected["last_completed_restore"]["operation_id"] / "manifest.json"
                original = manifest_path.read_bytes()
                manifest = decode_manifest(original); manifest["authority_sha256"] = "d" * 64
                manifest_path.write_bytes(encode_manifest(manifest))
                with self.assertRaises(RecoveryUnavailable): normal_service_receipt(db, protected)
                manifest_path.write_bytes(original)
                self.assertEqual(normal_service_receipt(db, protected)["last_completed_restore"], protected["last_completed_restore"])

    def test_preflight_denial_reactivates_exact_normalized_base_without_pending_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            anchor = (root / "anchor.json").read_bytes()
            process = self.launch(root, "r324-preflight-denied")
            try:
                _, err = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, err.decode())
                self.assertEqual(json.loads((root / "ready").read_bytes()), {"status": "blocked", "code": "schema_unsupported"})
                self.assertEqual(anchor, (root / "anchor.json").read_bytes())
                operations = list((root / ".phone-restore").iterdir())
                self.assertEqual(len(operations), 1)
                manifest = decode_manifest((operations[0] / "manifest.json").read_bytes())
                self.assertEqual(hashlib.sha256((root / "jarvis.db").read_bytes()).hexdigest(), manifest["base_database_sha256"])
                with sqlite3.connect(root / "jarvis.db") as db:
                    self.assertEqual(_meta_for_test(db), (1, "host-test", 1, None, "stable"))
                    self.assertEqual(db.execute("SELECT body FROM notes").fetchall(), [("current",)])
                self.assertEqual(decode_journal((operations[0] / "journal.json").read_bytes())["phase"], "checkpoint_bound")
            finally:
                if process.poll() is None: process.kill(); process.communicate()

    def test_source_catalog_denial_precedes_quiescence_and_changes_no_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            with sqlite3.connect(root / "source.db") as db: db.execute("CREATE TABLE unlisted(value TEXT)")
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            process = self.launch(root)
            try:
                process.communicate(timeout=10)
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(before, {path.name: path.read_bytes() for path in root.iterdir()})
            finally:
                if process.poll() is None: process.kill(); process.communicate()

    def test_normal_v4_proof_and_revocation_preserve_tombstone_and_historical_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            first = self.complete(root)
            before = (root / "jarvis.db").read_bytes()
            (root / "ready").unlink()
            process = self.launch(root, "r324-normal-proof")
            try:
                _, err = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, err.decode())
                updated = json.loads((root / "anchor.json").read_bytes())
                self.assertEqual(first["last_completed_restore"], updated["last_completed_restore"])
                self.assertEqual((updated["host_generation"], updated["login_counter"]), (3, 8))
                self.assertNotEqual(before, (root / "jarvis.db").read_bytes())
                self.assertEqual(len(list(root.glob("quiesce-*.proof"))), 1)
                with sqlite3.connect(root / "jarvis.db") as db:
                    from jarvis.bot.phone_remote_recovery import normal_service_receipt
                    ready = normal_service_receipt(db, updated)
                    self.assertEqual(ready["last_completed_restore"], first["last_completed_restore"])
                # Completion retry validates receipt fields, never historical
                # database bytes, after ordinary login/signout/security changes.
                (root / "ready").unlink()
                retry = self.launch(root)
                try:
                    _, err = retry.communicate(timeout=15)
                    self.assertEqual(retry.returncode, 0, err.decode())
                finally:
                    if retry.poll() is None: retry.kill(); retry.communicate()
                self.assertEqual(len(list(root.glob("quiesce-*.request"))), 1)
            finally:
                if process.poll() is None: process.kill(); process.communicate()

    def test_activation_acknowledgment_losses_withhold_completion_and_hold_exact_pair(self):
        import time
        for point in ("lost-open-ack", "lost-activate"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                self.complete(root); (root / "ready").unlink()
                before = ((root / "jarvis.db").read_bytes(), (root / "anchor.json").read_bytes())
                process = self.launch(root, "r324-normal-" + point)
                try:
                    deadline = time.monotonic() + 5
                    while not (root / "blocked").exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
                    self.assertTrue((root / "blocked").exists())
                    self.assertIsNone(process.poll())
                    self.assertFalse((root / "ready").exists())
                    self.assertEqual(before, ((root / "jarvis.db").read_bytes(), (root / "anchor.json").read_bytes()))
                    self.assertEqual(len(list(root.glob("quiesce-*.request"))), 1)
                finally:
                    if process.poll() is None: process.terminate()
                    process.communicate(timeout=5)
                self.complete(root)

    def test_actual_authorized_continuation_finishes_before_shutdown_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            self.complete(root, failpoint="r324-drain-success", counter=8)
            outcomes = list(root.glob("quiesce-*.outcome"))
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(json.loads(outcomes[0].read_bytes()), {"terminal": True, "status": "ok"})

    def test_actual_drain_failure_reaps_only_owned_child_and_retains_lock_without_recovery(self):
        import time, fcntl
        for point in ("stall", "stall-ignore-term", "lost-commit", "lost-release", "lost-shutdown"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                process = self.launch(root, "r324-drain-" + point)
                started = time.monotonic()
                try:
                    deadline = started + 10
                    while not (root / "blocked").exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.005)
                    self.assertTrue((root / "blocked").exists(),
                        (root / "child-failure").read_text() if (root / "child-failure").exists() else point)
                    self.assertIsNone(process.poll())
                    self.assertFalse((root / "child-failure").exists(),
                        (root / "child-failure").read_text() if (root / "child-failure").exists() else "")
                    self.assertFalse((root / "ready").exists())
                    self.assertFalse((root / ".phone-restore").exists())
                    anchor = json.loads((root / "anchor.json").read_bytes())
                    self.assertEqual((anchor["transition_state"], anchor["host_generation"], anchor["login_counter"]),
                                     ("stable", 1, 8))  # completed proof login is not rolled back
                    with sqlite3.connect(root / "jarvis.db") as db:
                        self.assertEqual(db.execute("SELECT body FROM notes").fetchall(), [("current",)])
                        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone(), (1,))
                    with (root / "owner.lock").open("rb") as lock:
                        with self.assertRaises(BlockingIOError): fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    elapsed = time.monotonic() - started
                    self.assertLess(elapsed, 8.5)
                    reaped = [json.loads(path.read_bytes()) for path in root.glob("reaped-*.json")]
                    self.assertEqual(len(reaped), 1)
                    self.assertTrue(reaped[0]["confirmed"])
                    self.assertLess(reaped[0]["term_wait_ms"], 350)
                    self.assertLess(reaped[0]["kill_wait_ms"], 2100)
                    if point == "stall-ignore-term": self.assertEqual(reaped[0]["signal"], "KILL")
                    if not point.startswith("stall"): self.assertLess(elapsed, 3)
                finally:
                    if process.poll() is None: process.terminate()
                    process.communicate(timeout=5)

    def test_actual_child_crash_matrix_at_durable_journal_and_rename_boundaries(self):
        import time
        points = ["before-staged", "after-quiesced", "after-installing",
                  "before-database_committed", "after-database_committed",
                  "before-database_finalized", "after-database_finalized"]
        for name in ("wal", "shm", "database", "staged_database"):
            points += ["intent-" + name, "done-" + name]
        points += ["renamed-database", "renamed-staged_database"]
        for point in points:
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                process = self.launch(root, "r324-journal-" + point)
                try:
                    deadline = time.monotonic() + 10
                    while not (root / "interrupted").exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue((root / "interrupted").exists(), point)
                    self.assertFalse((root / "ready").exists())
                    self.assertIsNone(process.poll(), "pending owner must retain singleton")
                finally:
                    if process.poll() is None: process.terminate()
                    process.communicate(timeout=5)
                self.complete(root)

    def test_second_recovery_has_fresh_identity_and_preserves_previous_retry_until_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            first = self.complete(root)
            (root / "ready").unlink()
            second = self.complete(root, begin=True, generation=3)
            self.assertNotEqual(first["last_completed_restore"]["operation_id"],
                                second["last_completed_restore"]["operation_id"])
            old_root = root / ".phone-restore" / first["last_completed_restore"]["operation_id"]
            self.assertEqual(decode_journal((old_root / "journal.json").read_bytes())["phase"], "complete")
            (root / "ready").unlink()
            self.assertEqual(second, self.complete(root, generation=3))

    def test_stable_anchor_interruption_resumes_cleanup_before_service_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            self.interrupt_stable(root, "r324-after-stable-anchor")
            self.complete(root)

    def interrupt_stable(self, root, point):
        import time, fcntl
        process = self.launch(root, point)
        try:
            deadline = time.monotonic() + 10
            while not (root / "blocked").exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((root / "interrupted").exists())
            self.assertTrue((root / "blocked").exists())
            self.assertIsNone(process.poll())
            self.assertFalse((root / "ready").exists())
            self.assertEqual(json.loads((root / "anchor.json").read_bytes())["transition_state"], "stable")
            with (root / "owner.lock").open("rb") as lock:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if process.poll() is None: process.terminate()
            process.communicate(timeout=5)

    def test_cleanup_interruptions_hold_lock_and_resume_without_replacement(self):
        for point in ("after-anchor_committed", "after-cleaning", "unlinked-checkpoint",
                      "unlinked-old_database", "after-complete"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.fixture(root)
                self.interrupt_stable(root, "r324-cleanup-" + point)
                database = (root / "jarvis.db").read_bytes()
                protected = (root / "anchor.json").read_bytes()
                self.complete(root)
                self.assertEqual(database, (root / "jarvis.db").read_bytes())
                self.assertEqual(protected, (root / "anchor.json").read_bytes())


def _recovery_child_entrypoint(database):
    import socket
    from jarvis.bot.phone_remote_authority_channel import (
        NativeProtectedAnchorV4, RecoveryChildChannel, open_store)
    from jarvis.bot.phone_remote_recovery import RecoveryDiskExecutor
    config = json.loads(os.environ["PHONE_REMOTE_AUTHORITY_RECOVERY_CONFIG"])
    assert os.environ["PHONE_REMOTE_AUTHORITY_LOCK_FD"] == "4"
    os.fstat(4)  # inherited lock descriptor remains open through process exit
    if config["mode"] == "normal":
        import threading, time
        from jarvis.bot.phone_admission_store import StoreUnavailable
        from jarvis.bot.phone_remote_service import (
            _AuthorityChildServiceHost, FakeContextVerifier, FakeMediaAdapter,
            FakeReadinessGate, TrustedRequestContext)
        from jarvis.bot.phone_remote_login import LoginSession
        path = Path(config["quiescence_path"])
        point = os.environ.get("PHONE_REMOTE_AUTHORITY_FAILPOINT")
        if point == "r324-drain-stall-ignore-term":
            import signal
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        def record(suffix, value):
            target = Path(str(path) + suffix)
            tmp = target.with_suffix(target.suffix + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
                handle.flush(); os.fsync(handle.fileno())
            os.replace(tmp, target)
        gate = FakeReadinessGate()
        arrived, release = threading.Event(), threading.Event()
        host = _AuthorityChildServiceHost(database, verifier=FakeContextVerifier(),
            media=FakeMediaAdapter(), voice_ready=gate)
        anchor = host._anchor
        outcome = []
        if config["exercise_drain"] or config["exercise_proof"]:
            from cryptography.hazmat.primitives.asymmetric import ec
            from jarvis.auth import ClientIdentity
            from tests.unit.test_phone_remote_login import sign_challenge_proof
            challenge = host.issue_login_challenge(device_id="current-device", grant_id="current-grant")
            login = host.complete_phone_login(challenge_id=challenge.challenge_id,
                proof_bytes=sign_challenge_proof(challenge, ec.derive_private_key(1, ec.SECP256R1())))
            if type(login) is not LoginSession: raise AssertionError("proof login failed")
            with sqlite3.connect(database) as db:
                incarnation = db.execute("SELECT login_incarnation FROM phone_remote_sessions WHERE session_id=?", (login.session_id,)).fetchone()[0]
            context = TrustedRequestContext(ClientIdentity(name="phone-auth-proof", user_id="alice"),
                "alice", login.session_id, "current-device", incarnation)
            class StalledDependency:
                def wait(self, timeout): return release.wait(8)
            if config["exercise_drain"]:
                gate.pause_before_commit("phone-authority-child", arrived,
                                         StalledDependency() if point and point.startswith("r324-drain-stall") else release)
            def request():
                outcome.append(host.handle(json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "frozen-status", "operation": "session.status", "payload": {}}), context))
            caller = threading.Thread(target=request)
            caller.start()
            if config["exercise_drain"]:
                if not arrived.wait(5): raise AssertionError("authorized operation never reached continuation")
            else:
                caller.join(5)
                if caller.is_alive() or outcome[0]["status"] != "ok": raise AssertionError("v2 protected proof service failed")
                host.signout(identity=context.identity, session_id=login.session_id, owner_id="alice")
                host.mutate_authority("revoke_grant", identity=context.identity, grant_id="current-grant", owner_id="alice")
                record(".proof", {"proof": True, "status": "ok", "signout": True, "revocation": True})
            record(".activity", {"authorized": True})
        deadline = time.monotonic() + 10
        request_path = Path(str(path) + ".request")
        while not request_path.exists() and time.monotonic() < deadline: time.sleep(.001)
        # Native writeNew is synchronous, but file creation precedes its write.
        while True:
            try:
                request = json.loads(request_path.read_bytes()); break
            except (ValueError, FileNotFoundError):
                if time.monotonic() >= deadline: raise
                time.sleep(.001)
        result = []
        def drain():
            try: result.append(host.quiesce(request["operation_id"], _owner_deadline=float(request["deadline"])))
            except BaseException as exc: result.append(exc)
        waiter = threading.Thread(target=drain)
        waiter.start()
        while not host._quiescing and waiter.is_alive(): time.sleep(.001)
        if config["exercise_drain"]:
            try: host.read_status()
            except StoreUnavailable: pass
            else: raise AssertionError("new request entered the frozen set")
            if not point or not point.startswith("r324-drain-stall"): release.set()
        waiter.join(6)
        if waiter.is_alive() or not result or isinstance(result[0], BaseException):
            record(".failed", {"settled": True})
            anchor.close()
            if point == "r324-drain-stall-ignore-term":
                while True: time.sleep(1)  # owned fixture forces bounded KILL/reap
            return
        if config["exercise_drain"]:
            caller.join(1)
            if caller.is_alive() or not outcome or outcome[0]["status"] != "ok":
                raise AssertionError("frozen continuation failed before drain")
            record(".outcome", {"terminal": True, "status": outcome[0]["status"]})
        record(".terminal", {"operation_id": request["operation_id"], "terminal": True})
        if point == "r324-drain-lost-shutdown":
            frame = anchor._receive()
            if frame["kind"] != "owner.shutdown": raise AssertionError("shutdown not requested")
            os._exit(77)
        host.shutdown()
        return
    manifest = config["manifest"]
    digest = hashlib.sha256(encode_manifest(manifest)).hexdigest()
    root = Path(database).parent / ".phone-restore" / manifest["operation_id"]
    journal = RecoveryJournal(root, operation_id=manifest["operation_id"], manifest_sha256=digest)
    executor = RecoveryDiskExecutor(Path(database), journal,
        5 if config["source_available"] else -1, config["protected_anchor"])
    session = executor.session(config["mode"])
    point = os.environ.get("PHONE_REMOTE_AUTHORITY_FAILPOINT", "").removeprefix("r324-journal-")
    def interrupted():
        Path(database).with_name("interrupted").write_text(point)
        os._exit(77)
    original_write = journal._write_new
    def write(value):
        phase = value["phase"]
        if point == "before-" + phase: interrupted()
        original_write(value)
        if point == "after-" + phase: interrupted()
        step = value["rename_step"]
        if step is not None and point == step["state"] + "-" + step["name"]:
            interrupted()
    journal._write_new = write
    original_replace = os.rename
    def replace(source, target, *args, **kwargs):
        original_replace(source, target, *args, **kwargs)
        name = "database" if Path(source) == Path(database) else "staged_database" if Path(source).name == "staged.db" else None
        if name is not None and point == "renamed-" + name: interrupted()
    os.rename = replace
    for name, callback in tuple(session.executors.items()):
        def injected(payload, name=name, callback=callback):
            if name == "preflight" and os.environ.get("PHONE_REMOTE_AUTHORITY_FAILPOINT") == "r324-preflight-denied":
                return {"operation_id": manifest["operation_id"], "status": "blocked", "code": "schema_unsupported"}
            result = callback(payload)
            if (os.environ.get("PHONE_REMOTE_AUTHORITY_FAILPOINT") == "r324-after-" + name
                    and not Path(database).with_name("interrupted").exists()):
                Path(database).with_name("interrupted").write_text(name)
                os._exit(77)
            return result
        session.executors[name] = injected
    RecoveryChildChannel(socket.socket(fileno=3), session=session).serve()


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--recovery-child":
        try:
            _recovery_child_entrypoint(sys.argv[2])
        except BaseException:
            # Child stdio is intentionally closed by the real native owner.
            # Diagnostics contain only disposable synthetic fixture data.
            Path(sys.argv[2]).with_name("child-failure").write_text(__import__("traceback").format_exc())
            sys.exit(78)
    else:
        unittest.main()
