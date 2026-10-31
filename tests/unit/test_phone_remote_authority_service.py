"""Actual-process acceptance for the v2 authority/service composition."""
from __future__ import annotations

import json
import fcntl
import os
import pathlib
import queue
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore, StoreDenied, StoreUnavailable
from jarvis.bot.phone_remote_service import _AuthorityChildServiceHost


@unittest.skipUnless(os.environ.get("PHONE_REMOTE_AUTHORITY_OWNER_BIN"),
                     "requires the built offline native owner executable")
class PhoneRemoteAuthorityServiceProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="phone-authority-service-")
        self.root = pathlib.Path(__file__).resolve().parents[2]
        self.database = os.path.join(self.tmp.name, "authority.sqlite")
        self.lock = os.path.join(self.tmp.name, "owner.lock")
        self.anchor_path = os.path.join(self.tmp.name, "anchor.json")
        pathlib.Path(self.lock).touch(mode=0o600)
        os.chmod(self.tmp.name, 0o700)
        db = sqlite3.connect(self.database, isolation_level=None)
        anchor = FakeProtectedAnchor("host-test")
        store = PhoneAdmissionStore(db, anchor)
        identity = ClientIdentity(name="authority-service-test", user_id="alice")
        store.add_device(identity=identity, device_id="d-channel", owner_id="alice",
                         public_key=b"test-only", key_algorithm="test-ed25519")
        store.add_grant(identity=identity, grant_id="g-channel", device_id="d-channel",
                        owner_id="alice", scopes=["read", "voice"])
        generation = db.execute("SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
        db.close()
        pathlib.Path(self.anchor_path).write_text(json.dumps({"anchor_version": 1,
            "host_id": "host-test", "host_generation": generation, "transition_id": None,
            "transition_state": "stable", "login_counter": 0}), encoding="utf-8")
        self.generation = generation

    def tearDown(self):
        self.tmp.cleanup()

    def _start_owner(self, scenario, *, grants=64, env_updates=None):
        owner = os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"]
        python = os.environ.get("PHONE_REMOTE_AUTHORITY_PYTHON", os.sys.executable)
        marker = os.path.join(self.tmp.name, scenario + ".result")
        env = os.environ.copy()
        env.update({"PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION": "2",
                    "PHONE_REMOTE_AUTHORITY_CHANNEL_FD": "3",
                    "PHONE_REMOTE_AUTHORITY_LOCK_FD": "4",
                    "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT": marker,
                    "PYTHONPATH": str(self.root) + os.pathsep + env.get("PYTHONPATH", "")})
        if env_updates:
            env.update(env_updates)
        command = [owner, "--test-owner", self.lock, python, self.database,
                   str(self.root), scenario, str(grants), "0", str(self.generation), "0", self.anchor_path]
        return marker, subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _wait_for_file(self, path, process, timeout=10):
        deadline = time.monotonic() + timeout
        while not pathlib.Path(path).exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.01)
        if not pathlib.Path(path).exists():
            detail = ""
            if process.poll() is not None:
                out, err = process.communicate()
                marker = pathlib.Path(self.tmp.name) / (str(process.args[6]) + ".result") if isinstance(process.args, list) and len(process.args) > 6 else None
                marker_text = marker.read_text(encoding="utf-8", errors="replace") if marker and marker.exists() else None
                detail = f"; exit={process.returncode}; marker={marker_text!r}; stdout={out!r}; stderr={err!r}"
            self.fail(f"barrier was not reached: {path}{detail}")

    def _wait_for_marker(self, path, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if pathlib.Path(path).stat().st_size > 0:
                    return
            except FileNotFoundError:
                pass
            time.sleep(0.01)
        self.fail(f"child result marker was not fully written: {path}")

    def test_same_child_signout_denial_and_fresh_unrelated_offer_through_asgi_executor(self):
        owner = os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"]
        python = os.environ.get("PHONE_REMOTE_AUTHORITY_PYTHON", os.sys.executable)
        marker = os.path.join(self.tmp.name, "result")
        env = os.environ.copy()
        env.update({"PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION": "2",
                    "PHONE_REMOTE_AUTHORITY_CHANNEL_FD": "3",
                    "PHONE_REMOTE_AUTHORITY_LOCK_FD": "4",
                    "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT": marker,
                    "PYTHONPATH": str(self.root) + os.pathsep + env.get("PYTHONPATH", "")})
        command = [owner, "--test-owner", self.lock, python, self.database,
                   str(self.root), "v2-service-signout", "21", "0",
                   str(self.generation), "0", self.anchor_path]
        result = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30)
        marker_text = pathlib.Path(marker).read_text(encoding="utf-8") if pathlib.Path(marker).exists() else "<no child result>"
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace") + " | " + marker_text)
        self.assertTrue(pathlib.Path(marker).read_text(encoding="ascii").startswith(
            "a-denied-b-offer-ok-busy-rejected-cancel-drained-update-replayed:"))
        db = sqlite3.connect(self.database)
        rows = dict(db.execute("SELECT session_id,revoked_at FROM phone_remote_sessions"))
        self.assertEqual(rows["s-a"], 0.0)
        self.assertIsNone(rows["s-b"])
        self.assertEqual(db.execute("SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0],
                         self.generation)
        db.close()

    def test_lost_readonly_denial_release_ack_fences_child_before_preissued_ticket_effect(self):
        owner = os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"]
        python = os.environ.get("PHONE_REMOTE_AUTHORITY_PYTHON", os.sys.executable)
        marker = os.path.join(self.tmp.name, "lost-ack-result")
        entered = os.path.join(self.tmp.name, "release-entered")
        release = os.path.join(self.tmp.name, "release-ack")
        env = os.environ.copy()
        env.update({"PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION": "2",
                    "PHONE_REMOTE_AUTHORITY_CHANNEL_FD": "3",
                    "PHONE_REMOTE_AUTHORITY_LOCK_FD": "4",
                    "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT": marker,
                    "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "service.authorize",
                    "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
                    "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release,
                    "PYTHONPATH": str(self.root) + os.pathsep + env.get("PYTHONPATH", "")})
        command = [owner, "--test-owner", self.lock, python, self.database,
                   str(self.root), "v2-lost-authorize-ack", "64", "0",
                   str(self.generation), "0", self.anchor_path]
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not pathlib.Path(entered).exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                time.sleep(0.01)
            self.assertTrue(pathlib.Path(entered).exists(), "owner did not reach the release-ack barrier")
            process.terminate()  # EOF makes the outstanding release result uncertain.
            process.communicate(timeout=10)
            deadline = time.monotonic() + 10
            self._wait_for_marker(marker)
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "lost-ack-a=unavailable;b=fenced;preissued=True;media=0")
            probe = os.open(self.lock, os.O_RDWR)
            try:
                deadline = time.monotonic() + 5
                acquired = False
                while time.monotonic() < deadline:
                    try:
                        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                        break
                    except BlockingIOError:
                        time.sleep(0.01)
                self.assertTrue(acquired, "child must release its inherited singleton on exit")
            finally:
                os.close(probe)
            db = sqlite3.connect(self.database)
            self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0], 1)
            db.close()
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_lost_output_dequeue_ack_returns_no_bytes_and_fences_child(self):
        owner = os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"]
        python = os.environ.get("PHONE_REMOTE_AUTHORITY_PYTHON", os.sys.executable)
        marker = os.path.join(self.tmp.name, "lost-output-result")
        entered = os.path.join(self.tmp.name, "output-release-entered")
        release = os.path.join(self.tmp.name, "output-release-ack")
        env = os.environ.copy()
        env.update({"PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION": "2",
                    "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT": marker,
                    "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "service.commit",
                    "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "13",
                    "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
                    "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release,
                    "PYTHONPATH": str(self.root) + os.pathsep + env.get("PYTHONPATH", "")})
        command = [owner, "--test-owner", self.lock, python, self.database,
                   str(self.root), "v2-lost-output-drain", "64", "0",
                   str(self.generation), "0", self.anchor_path]
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not pathlib.Path(entered).exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                time.sleep(0.01)
            self.assertTrue(pathlib.Path(entered).exists(), "output commit did not reach its release-ack barrier")
            process.terminate()
            process.communicate(timeout=10)
            deadline = time.monotonic() + 10
            self._wait_for_marker(marker)
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "output-drain=unavailable;after=fenced")
            db = sqlite3.connect(self.database)
            self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0], 1)
            db.close()
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_offer_commit_lost_ack_never_returns_success(self):
        entered = os.path.join(self.tmp.name, "offer-commit-entered")
        release = os.path.join(self.tmp.name, "offer-commit-release")
        marker, process = self._start_owner("v2-lost-offer-commit-ack", env_updates={
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "service.commit",
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "10",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        try:
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            deadline = time.monotonic() + 10
            self._wait_for_marker(marker)
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "lost-offer=unavailable;after=fenced")
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_peer_update_commit_lost_ack_fences_without_returning_answer(self):
        entered = os.path.join(self.tmp.name, "update-commit-entered")
        release = os.path.join(self.tmp.name, "update-commit-release")
        marker, process = self._start_owner("v2-lost-update-commit-ack", env_updates={
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "service.commit",
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "15",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        try:
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            self._wait_for_marker(marker)
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "lost-update=unavailable;after=fenced")
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_eof_observed_after_blocked_media_prep_prevents_offer_publication(self):
        entered = os.path.join(self.tmp.name, "media-prep-entered")
        release = os.path.join(self.tmp.name, "media-prep-release")
        marker, process = self._start_owner("v2-eof-during-preparation", env_updates={
            "PHONE_REMOTE_AUTHORITY_MEDIA_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_MEDIA_RELEASE_FILE": release})
        try:
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            pathlib.Path(release).write_text("continue", encoding="ascii")
            deadline = time.monotonic() + 10
            self._wait_for_marker(marker)
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "eof-preparation=unavailable;after=fenced")
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_feature_availability_and_expiry_deny_queued_output_and_retire_peers(self):
        marker, process = self._start_owner("v2-feature-output-gates", grants=35)
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, err.decode("utf-8", "replace") + out.decode("utf-8", "replace"))
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                         "feature=True;availability=True;expiry=True")

    def test_global_generation_fences_peer_queue_allows_fresh_login_and_rejects_repeated_raw_restore(self):
        snapshot = self.database + ".stale-snapshot"
        source = sqlite3.connect(self.database)
        destination = sqlite3.connect(snapshot)
        source.backup(destination)
        destination.close(); source.close()
        marker, process = self._start_owner("v2-global-revoke-restore", grants=21)
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, err.decode("utf-8", "replace") + out.decode("utf-8", "replace"))
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                         "old=denied;queued=True;clean=True;fresh=ok")
        with open(self.anchor_path, encoding="utf-8") as handle:
            current_anchor = json.load(handle)
        self.assertEqual(current_anchor["host_generation"], self.generation + 1)
        for attempt in range(2):
            shutil.copyfile(snapshot, self.database)
            for suffix in ("-wal", "-shm"):
                try:
                    os.unlink(self.database + suffix)
                except FileNotFoundError:
                    pass
            owner = os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"]
            python = os.environ.get("PHONE_REMOTE_AUTHORITY_PYTHON", os.sys.executable)
            command = [owner, "--test-owner", self.lock, python, self.database,
                       str(self.root), "basic", "1", "0", str(current_anchor["host_generation"]),
                       str(current_anchor["login_counter"]), self.anchor_path]
            environment = os.environ.copy()
            environment.update({"PYTHONPATH": str(self.root) + os.pathsep + environment.get("PYTHONPATH", "")})
            restored = subprocess.run(command, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            self.assertNotEqual(restored.returncode, 0, f"raw restore attempt {attempt + 1} was admitted")
            with open(self.anchor_path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), current_anchor)

    def test_output_preflight_lost_ack_is_terminal_even_when_service_returns_false(self):
        entered = os.path.join(self.tmp.name, "output-preflight-entered")
        release = os.path.join(self.tmp.name, "output-preflight-release")
        marker, process = self._start_owner("v2-output-preflight-lost-ack", env_updates={
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "service.authorize",
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "11",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        try:
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            self._wait_for_marker(marker)
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "output-preflight=False;fenced=True;closed=True;immediate=True;after=fenced")
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_scoped_signout_and_repeated_raw_restore_stay_fenced_in_same_child(self):
        sync_dir = pathlib.Path(self.tmp.name) / "restore-sync"
        sync_dir.mkdir(mode=0o700)
        snapshot = str(pathlib.Path(self.tmp.name) / "pre-signout.sqlite")
        marker, process = self._start_owner("v2-same-child-restore", grants=21,
            env_updates={"PHONE_REMOTE_AUTHORITY_TEST_SYNC_DIR": str(sync_dir)})
        try:
            self._wait_for_file(str(sync_dir / "snapshot-ready"), process)
            anchor_before = pathlib.Path(self.anchor_path).read_bytes()
            source = sqlite3.connect(self.database)
            destination = sqlite3.connect(snapshot)
            source.backup(destination)
            destination.close(); source.close()
            (sync_dir / "snapshot-captured").write_text("captured", encoding="ascii")
            self._wait_for_file(str(sync_dir / "a-signed-out"), process)

            def restore_raw_snapshot():
                restored = sqlite3.connect(self.database)
                saved = sqlite3.connect(snapshot)
                saved.backup(restored)
                restored.close(); saved.close()
                check = sqlite3.connect(self.database)
                a_revoked, b_revoked = check.execute("""SELECT
                    (SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-a'),
                    (SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-b')""").fetchone()
                check.close()
                self.assertIsNone(a_revoked, "restore must actually reinstate A's stale row")
                self.assertIsNone(b_revoked, "unaffected B control must remain present")
                self.assertEqual(pathlib.Path(self.anchor_path).read_bytes(), anchor_before,
                                 "scoped signout and raw DB restore must not alter protected authority")

            for attempt in ("restore-one", "restore-two"):
                restore_raw_snapshot()
                (sync_dir / (attempt + "-ready")).write_text("ready", encoding="ascii")
                self._wait_for_file(str(sync_dir / (attempt + "-checked")), process)
            out, err = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0,
                err.decode("utf-8", "replace") + out.decode("utf-8", "replace")
                + "; marker=" + pathlib.Path(marker).read_text(encoding="utf-8", errors="replace"))
            self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                             "a-queued=True;a-denied=True;b=ok")
            self.assertEqual(pathlib.Path(self.anchor_path).read_bytes(), anchor_before)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_grant_revocation_cleans_peer_output_and_blocks_relogin(self):
        marker, process = self._start_owner("v2-grant-revoke-cleanup", grants=64)
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 32, err.decode("utf-8", "replace") + out.decode("utf-8", "replace"))
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                         "offer=ok;queued=True;old=denied;clean=True;fresh=denied")
        with open(self.anchor_path, encoding="utf-8") as handle:
            authority = json.load(handle)
        self.assertEqual(authority["host_generation"], self.generation + 1)
        db = sqlite3.connect(self.database)
        grant_generation, revoked_at = db.execute(
            "SELECT grant_generation,revoked_at FROM phone_remote_grants WHERE grant_id='g-channel'").fetchone()
        db.close()
        self.assertEqual(grant_generation, 2)
        self.assertIsNotNone(revoked_at)


class SubmissionAdmissionRaceTests(unittest.TestCase):
    """Binary-independent local admission race; always run by pytest."""

    def test_submission_racing_terminal_close_is_rejected_without_stranding_a_queue_item(self):
        arrived = threading.Event()
        resume = threading.Event()
        class BarrierLock:
            def __init__(self):
                self.inner = threading.Lock()
                self.pause_once = True
            def __enter__(self):
                if threading.current_thread().name == "submitter" and self.pause_once:
                    self.pause_once = False
                    arrived.set()
                    if not resume.wait(2):
                        raise RuntimeError("submission barrier timed out")
                self.inner.acquire()
                return self
            def __exit__(self, *_):
                self.inner.release()
        host = object.__new__(_AuthorityChildServiceHost)
        host._closed = False
        host._fenced = False
        host._busy = False
        host._lock = BarrierLock()
        host._queue = queue.Queue(maxsize=1)
        result = []
        def submit():
            try:
                result.append(host.read_status())
            except StoreUnavailable:
                result.append("closed")
        caller = threading.Thread(target=submit, name="submitter")
        caller.start()
        self.assertTrue(arrived.wait(2))
        with host._lock:
            host._closed = True
            host._fenced = True
        resume.set()
        caller.join(timeout=2)
        self.assertFalse(caller.is_alive(), "a post-close item must not be enqueued without a worker")
        self.assertEqual(result, ["closed"])
        self.assertTrue(host._queue.empty())
