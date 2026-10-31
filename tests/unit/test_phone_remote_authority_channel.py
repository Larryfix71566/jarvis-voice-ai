"""Actual-process conformance for the private native-owner/store channel."""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import sqlite3
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
import errno
import uuid

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import (
    AnchorState, FakeProtectedAnchor, PhoneAdmissionStore, StoreDenied, StoreUnavailable,
)
from jarvis.bot.phone_remote_authority_channel import (
    ChannelProtocolError, MAX_FRAME_BYTES, NativeProtectedAnchor,
    decode_frame_payload, encode_frame_payload, open_store, run_store_operation,
)


def _identity():
    return ClientIdentity(name="authority-channel-test", user_id="alice")


def _record_scenario_result(value: str) -> None:
    path = os.environ.get("PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT")
    if path:
        with open(path, "w", encoding="ascii") as handle:
            handle.write(value)


def _child(database: str, scenario: str) -> int:
    """Fixed test child entrypoint used by the Swift process owner only."""
    from jarvis.bot.phone_remote_authority_channel import (
        NativeProtectedAnchor, open_store, run_store_operation,
    )
    if scenario == "hold":
        anchor = NativeProtectedAnchor.from_inherited_environment()
        os.fstat(4)
        if any(_is_open(fd) for fd in (0, 1, 2)):
            return 71
        if any(_is_open(fd) for fd in range(5, 64)):
            return 72
        anchor.wait_for_shutdown()
        return 0
    if scenario in {"duplicate-frame", "float-sequence", "sequence-replay",
                    "sequence-skip", "sequence-overflow"}:
        anchor = NativeProtectedAnchor.from_inherited_environment()
        owner, child = anchor._owner_incarnation, anchor._child_incarnation
        corr = str(uuid.uuid4())
        if scenario == "duplicate-frame":
            body = ("{\"protocol\":\"mortimer.phone-authority-channel.v1\",\"version\":1,"
                    f"\"kind\":\"child.grant.acquire\",\"owner_incarnation\":\"{owner}\","
                    f"\"child_incarnation\":\"{child}\",\"sequence\":2,\"sequence\":2,"
                    f"\"correlation_id\":\"{corr}\",\"payload\":{{\"operation\":\"store.read\"}}}}")
        else:
            bad_sequence = {"float-sequence": 2.0, "sequence-replay": 1,
                "sequence-skip": 3, "sequence-overflow": 1 << 64}[scenario]
            body = json.dumps({"protocol": "mortimer.phone-authority-channel.v1", "version": 1,
                "kind": "child.grant.acquire", "owner_incarnation": owner,
                "child_incarnation": child, "sequence": bad_sequence, "correlation_id": corr,
                "payload": {"operation": "store.read"}})
        encoded = body.encode("utf-8")
        anchor._socket.sendall(struct.pack(">I", len(encoded)) + encoded)
        anchor._socket.settimeout(2)
        try:
            outcome = "data" if anchor._socket.recv(1) else "eof"
        except TimeoutError:
            outcome = "timeout"
        _record_scenario_result(outcome)
        anchor.close()
        return 0
    if scenario not in {"basic", "denied", "denied-mutation", "repeat-revoke",
                        "release-without-read", "abort-eof", "malformed-final-null",
                        "unicode-host-transition", "scoped-signout-control",
                        "duplicate-readback", "second-grant"}:
        return 64
    def failpoint(name: str) -> None:
        if os.environ.get("PHONE_REMOTE_AUTHORITY_FAILPOINT") != name:
            return
        if os.environ.get("PHONE_REMOTE_AUTHORITY_CRASH_AT") == name:
            os._exit(77)
        entered = os.environ.get("PHONE_REMOTE_AUTHORITY_ENTERED_FILE")
        release = os.environ.get("PHONE_REMOTE_AUTHORITY_RELEASE_FILE")
        if entered and release:
            with open(entered, "w", encoding="ascii") as handle:
                handle.write("entered")
            while not os.path.exists(release):
                time.sleep(0.005)
            return
        raise RuntimeError("injected transition interruption")
    channel_fd = int(os.environ["PHONE_REMOTE_AUTHORITY_CHANNEL_FD"])
    lock_fd = int(os.environ["PHONE_REMOTE_AUTHORITY_LOCK_FD"])
    os.fstat(channel_fd); os.fstat(lock_fd)
    if any(_is_open(fd) for fd in (0, 1, 2)):
        return 73
    # Only the designated channel and singleton descriptors may survive exec.
    inherited = [fd for fd in range(5, 64) if _is_open(fd)]
    if inherited:
        return 65
    db = sqlite3.connect(database, isolation_level=None, timeout=0.25)
    anchor = NativeProtectedAnchor.from_inherited_environment()
    try:
        store = open_store(PhoneAdmissionStore, db, anchor=anchor, failpoint=failpoint)
        initial_generation = db.execute("SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
        if scenario == "release-without-read":
            try:
                with anchor._operation_context("store.read"):
                    with anchor.exclusive():
                        pass
            except StoreUnavailable:
                _record_scenario_result("release-rejected")
                return 0
            return 80
        if scenario == "duplicate-readback":
            try:
                with anchor._operation_context("authority.mutate"):
                    with anchor.exclusive():
                        current = anchor.read()
                        anchor.write(AnchorState(current.anchor_version, current.host_id,
                            current.host_generation + 1, "duplicate-readback", "pending", current.login_counter))
            except StoreUnavailable:
                _record_scenario_result("duplicate-readback-rejected")
                return 0
            return 87
        if scenario == "abort-eof":
            with anchor._operation_context("store.read"):
                acquired = anchor._request("child.grant.acquire", {"operation": "store.read"}, "owner.grant.acquired")
                anchor._grant_id = acquired["grant_id"]
                anchor._grant_operation = "store.read"
                anchor._grant_owner_thread = threading.get_ident()
                anchor._scope_local.grant_count = 1
                anchor._request("child.grant.abort", {"grant_id": anchor._grant_id}, "owner.grant.aborted")
                anchor._socket.settimeout(2)
                try:
                    outcome = "data" if anchor._socket.recv(1) else "eof"
                except TimeoutError:
                    outcome = "timeout"
                _record_scenario_result(outcome)
            return 0
        status = run_store_operation("store.read", store.status, anchor=anchor)
        if status != {"schema_version": 1, "host_generation": initial_generation, "login_counter": 0}:
            return 66
        if scenario in {"malformed-final-null", "unicode-host-transition"}:
            try:
                with anchor._operation_context("authority.mutate"):
                    with anchor.exclusive():
                        current = anchor.read()
                        pending = AnchorState(current.anchor_version, current.host_id,
                            current.host_generation + 1, "probe-transition", "pending", current.login_counter)
                        anchor.write(pending)
                        anchor.read()
                        state = {"anchor_version": current.anchor_version,
                            "host_id": (unicodedata.normalize("NFC", current.host_id)
                                        if scenario == "unicode-host-transition" else current.host_id),
                            "host_generation": pending.host_generation,
                            "transition_id": False if scenario == "malformed-final-null" else None,
                            "transition_state": "stable", "login_counter": current.login_counter}
                        anchor._request("child.anchor.advance", {"grant_id": anchor._grant_id,
                            "step": "global_stable", "state": state}, "owner.anchor.verified")
            except StoreUnavailable:
                _record_scenario_result(scenario + "-rejected")
                return 0
            return 82
        if scenario == "denied":
            try:
                run_store_operation("session.login", store.login, anchor=anchor,
                    identity=ClientIdentity(name="verified-test", user_id="mallory"),
                    session_id="s-denied", grant_id="g-channel", owner_id="mallory",
                    now=1, expires_at=100)
            except StoreDenied:
                _record_scenario_result("login-denied")
                return 68
            return 84
        if scenario == "denied-mutation":
            try:
                run_store_operation("authority.mutate", store.revoke_grant, anchor=anchor,
                    identity=_identity(), grant_id="missing", owner_id="alice")
            except StoreDenied:
                _record_scenario_result("mutation-preflight-denied")
                return 69
            return 85
        if scenario == "repeat-revoke":
            run_store_operation("authority.mutate", store.revoke_grant, anchor=anchor,
                identity=_identity(), grant_id="g-channel", owner_id="alice")
            try:
                run_store_operation("authority.mutate", store.revoke_grant, anchor=anchor,
                    identity=_identity(), grant_id="g-channel", owner_id="alice")
            except StoreDenied:
                _record_scenario_result("repeated-revoke-completed")
                return 70
            return 86
        if scenario == "scoped-signout-control":
            for session_id in ("s-control-a", "s-control-b"):
                run_store_operation("session.login", store.login, anchor=anchor,
                    identity=_identity(), session_id=session_id, grant_id="g-channel",
                    owner_id="alice", now=1, expires_at=100)
            run_store_operation("session.signout", store.revoke_session, anchor=anchor,
                identity=_identity(), session_id="s-control-a", owner_id="alice")
            run_store_operation("ticket.issue", store.issue_ticket, anchor=anchor,
                identity=_identity(), ticket_id="t-control-b", session_id="s-control-b",
                owner_id="alice", purpose="offer", payload_digest="sha256:control-b",
                now=2, expires_at=20)
            binding = run_store_operation("ticket.consume", store.consume_ticket, anchor=anchor,
                identity=_identity(), ticket_id="t-control-b", session_id="s-control-b",
                owner_id="alice", purpose="offer", payload_digest="sha256:control-b", now=3)
            final = run_store_operation("store.read", store.status, anchor=anchor)
            _record_scenario_result("unrelated-ticket-consumed" if binding.session_id == "s-control-b" else "wrong-session")
            anchor.wait_for_shutdown()
            return 0 if final["host_generation"] == initial_generation and final["login_counter"] == 2 else 83
        if scenario == "second-grant":
            try:
                with anchor._operation_context("store.read"):
                    with anchor.exclusive():
                        anchor.read()
                        anchor._request("child.grant.acquire", {"operation": "store.read"},
                                        "owner.grant.acquired")
            except StoreUnavailable:
                _record_scenario_result("second-grant-denied")
                return 0
            return 88
        run_store_operation("session.login", store.login, anchor=anchor,
            identity=_identity(), session_id="s-channel", grant_id="g-channel",
            owner_id="alice", now=1, expires_at=100)
        run_store_operation("ticket.issue", store.issue_ticket, anchor=anchor,
            identity=_identity(), ticket_id="t-channel", session_id="s-channel",
            owner_id="alice", purpose="offer", payload_digest="sha256:offer",
            now=2, expires_at=20)
        run_store_operation("ticket.consume", store.consume_ticket, anchor=anchor,
            identity=_identity(), ticket_id="t-channel", session_id="s-channel",
            owner_id="alice", purpose="offer", payload_digest="sha256:offer", now=3)
        run_store_operation("session.signout", store.revoke_session, anchor=anchor,
            identity=_identity(), session_id="s-channel", owner_id="alice")
        run_store_operation("authority.mutate", store.advance_host_generation, anchor=anchor)
        final = run_store_operation("store.read", store.status, anchor=anchor)
        if final != {"schema_version": 1, "host_generation": initial_generation + 1, "login_counter": 1}:
            return 67
        anchor.wait_for_shutdown()
        return 0
    finally:
        db.close()


def _is_open(fd: int) -> bool:
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


if __name__ == "__main__" and len(sys.argv) >= 2 and sys.argv[1] == "--authority-child":
    try:
        child_code = _child(sys.argv[2], sys.argv[3])
    except BaseException:
        child_code = 1
    raise SystemExit(child_code)


class FrameTests(unittest.TestCase):
    def test_strict_frame_json_boundary(self):
        valid = {"version": 1, "payload": {"x": 1}}
        self.assertEqual(decode_frame_payload(encode_frame_payload(valid)), valid)
        for bad in (b"", b"[]", b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"{" + b" " * MAX_FRAME_BYTES):
            with self.subTest(bad=bad[:20]), self.assertRaises(ChannelProtocolError):
                decode_frame_payload(bad)
        with self.assertRaises(ChannelProtocolError):
            encode_frame_payload({"x": float("inf")})
        with self.assertRaises(ChannelProtocolError):
            encode_frame_payload({1: "non-string key"})
        nested = value = {}
        for _ in range(66):
            nested["x"] = {}
            nested = nested["x"]
        with self.assertRaises(ChannelProtocolError):
            encode_frame_payload(value)

    def test_store_operation_method_mismatch_is_rejected_before_call(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        store = PhoneAdmissionStore(db, FakeProtectedAnchor())
        channel = object.__new__(NativeProtectedAnchor)
        store.anchor = channel
        with self.assertRaises(StoreUnavailable):
            run_store_operation("store.read", store.login, anchor=channel,
                identity=_identity(), session_id="s", grant_id="g", owner_id="alice",
                now=1, expires_at=2)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()

    def test_store_open_refuses_empty_schema_before_any_bootstrap(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        channel = object.__new__(NativeProtectedAnchor)
        with self.assertRaises(StoreUnavailable):
            open_store(PhoneAdmissionStore, db, anchor=channel)
        self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0], 0)
        db.close()


class NativeFrameValidationTests(unittest.TestCase):
    @staticmethod
    def _frame(kind, sequence, owner, child, correlation, payload, version=1):
        return {"protocol": "mortimer.phone-authority-channel.v1", "version": version,
                "kind": kind, "owner_incarnation": owner, "child_incarnation": child,
                "sequence": sequence, "correlation_id": correlation, "payload": payload}

    @staticmethod
    def _packet(frame):
        body = json.dumps(frame, separators=(",", ":")).encode("utf-8")
        return struct.pack(">I", len(body)) + body

    def test_native_client_rejects_duplicate_and_noninteger_handshake_fields(self):
        owner, child, corr = (str(uuid.uuid4()) for _ in range(3))
        base = self._frame("owner.hello", 1, owner, child, corr, {"max_frame_bytes": MAX_FRAME_BYTES})
        bad_packets = [self._packet({**base, "version": True}),
                       self._packet({**base, "sequence": 1.0}),
                       self._packet({**base, "payload": {"max_frame_bytes": float(MAX_FRAME_BYTES)}}),
                       self._packet({**base, "owner_incarnation": owner.upper()})]
        raw = json.dumps(base, separators=(",", ":")).replace('"version":1', '"version":1,"version":1').encode()
        bad_packets.append(struct.pack(">I", len(raw)) + raw)
        for packet in bad_packets:
            with self.subTest(packet=packet[:50]):
                parent, child_socket = socket.socketpair()
                parent.sendall(packet); parent.close()
                with self.assertRaises(ChannelProtocolError):
                    NativeProtectedAnchor(child_socket)

    def test_native_client_rejects_wrong_reply_correlation_and_incarnation(self):
        for mismatch in ("correlation", "incarnation"):
            parent, child_socket = socket.socketpair()
            owner, child, hello_corr = (str(uuid.uuid4()) for _ in range(3))
            ready = threading.Event()
            def fake_owner():
                try:
                    parent.sendall(self._packet(self._frame("owner.hello", 1, owner, child,
                        hello_corr, {"max_frame_bytes": MAX_FRAME_BYTES})))
                    self._read_frame(parent)  # child.ready
                    request = self._read_frame(parent)
                    response_child = str(uuid.uuid4()) if mismatch == "incarnation" else child
                    response_corr = str(uuid.uuid4()) if mismatch == "correlation" else request["correlation_id"]
                    response = self._frame("owner.grant.acquired", 2, owner, response_child,
                        response_corr, {"grant_id": str(uuid.uuid4()), "operation": "store.read"})
                    parent.sendall(self._packet(response))
                finally:
                    ready.set(); parent.close()
            thread = threading.Thread(target=fake_owner, daemon=True); thread.start()
            anchor = NativeProtectedAnchor(child_socket)
            with self.subTest(mismatch=mismatch), self.assertRaises(StoreUnavailable):
                with anchor._operation_context("store.read"):
                    with anchor.exclusive():
                        pass
            anchor.close(); thread.join(timeout=2)
            self.assertTrue(ready.is_set())

    def test_native_client_binds_anchor_reads_and_writes_to_grant_thread(self):
        parent, child_socket = socket.socketpair()
        owner, child, hello_corr, grant = (str(uuid.uuid4()) for _ in range(4))
        state = {"anchor_version": 1, "host_id": "host", "host_generation": 1,
            "transition_id": None, "transition_state": "stable", "login_counter": 0}
        def fake_owner():
            try:
                parent.sendall(self._packet(self._frame("owner.hello", 1, owner, child,
                    hello_corr, {"max_frame_bytes": MAX_FRAME_BYTES})))
                self._read_frame(parent)  # child.ready
                acquire = self._read_frame(parent)
                parent.sendall(self._packet(self._frame("owner.grant.acquired", 2, owner, child,
                    acquire["correlation_id"], {"grant_id": grant, "operation": "store.read"})))
                read = self._read_frame(parent)
                parent.sendall(self._packet(self._frame("owner.anchor.state", 3, owner, child,
                    read["correlation_id"], {"grant_id": grant, "state": state})))
                release = self._read_frame(parent)
                parent.sendall(self._packet(self._frame("owner.grant.released", 4, owner, child,
                    release["correlation_id"], {"grant_id": grant})))
            finally:
                parent.close()
        worker = threading.Thread(target=fake_owner, daemon=True)
        worker.start()
        anchor = NativeProtectedAnchor(child_socket)
        rejected = []
        with anchor._operation_context("store.read"):
            with anchor.exclusive():
                def foreign_access():
                    for action in (anchor.read,
                                   lambda: anchor.write(AnchorState(1, "host", 1, None, "stable", 0)),
                                   lambda: anchor._request("child.anchor.read", {"grant_id": grant}, "owner.anchor.state")):
                        try:
                            action()
                            rejected.append(False)
                        except StoreUnavailable:
                            rejected.append(True)
                thread = threading.Thread(target=foreign_access)
                thread.start(); thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(anchor.read().host_id, "host")
        anchor.close()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(rejected, [True, True, True])

    @classmethod
    def _read_frame(cls, sock):
        header = sock.recv(4)
        if len(header) != 4: raise AssertionError("missing child frame")
        size = struct.unpack(">I", header)[0]
        body = bytearray()
        while len(body) < size: body.extend(sock.recv(size - len(body)))
        return json.loads(body)


@unittest.skipUnless(os.environ.get("PHONE_REMOTE_AUTHORITY_OWNER_BIN"), "requires built native owner executable")
class ProcessBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="phone-authority-process-")
        self.root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        self.db_path = os.path.join(self.tmp.name, "authority.sqlite")
        self.lock_path = os.path.join(self.tmp.name, "owner.lock")
        self.anchor_path = os.path.join(self.tmp.name, "anchor.json")
        open(self.lock_path, "xb").close()  # Explicit disposable, preprovisioned inode.
        os.chmod(self.lock_path, 0o600)
        db = sqlite3.connect(self.db_path, isolation_level=None)
        self.anchor = FakeProtectedAnchor("host-test")
        store = PhoneAdmissionStore(db, self.anchor)
        store.add_device(identity=_identity(), device_id="d-channel", owner_id="alice",
                         public_key=b"public-test", key_algorithm="test-ed25519")
        store.add_grant(identity=_identity(), grant_id="g-channel", device_id="d-channel",
                        owner_id="alice", scopes=["read", "voice"])
        self.initial_generation = db.execute("SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
        db.close()
        with open(self.anchor_path, "w", encoding="utf-8") as handle:
            json.dump({"anchor_version": 1, "host_id": "host-test",
                       "host_generation": self.initial_generation, "transition_id": None,
                       "transition_state": "stable", "login_counter": 0}, handle)
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = self.root + os.pathsep + self.env.get("PYTHONPATH", "")
        self.env["PHONE_REMOTE_AUTHORITY_PYTHON"] = sys.executable
        self.env["PHONE_REMOTE_AUTHORITY_TEST_ROOT"] = self.root

    def tearDown(self):
        self.tmp.cleanup()

    def owner_command(self, scenario: str, count: int, hold_ms: int = 0):
        return [os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"], "--test-owner",
                self.lock_path, sys.executable, self.db_path, self.root,
                scenario, str(count), str(hold_ms), str(self.initial_generation), "0", self.anchor_path]

    def test_owner_rejects_untyped_initial_anchor_and_unsafe_lock_before_spawn(self):
        ready = os.path.join(self.tmp.name, "ready")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_READY_FILE=ready)
        with open(self.anchor_path, encoding="utf-8") as handle:
            initial = json.load(handle)
        initial["transition_id"] = False
        with open(self.anchor_path, "w", encoding="utf-8") as handle:
            json.dump(initial, handle)
        malformed = subprocess.run(self.owner_command("hold", 0), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(malformed.returncode, 0)
        self.assertFalse(os.path.exists(ready), "invalid initial anchor must be rejected before child launch")
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["transition_id"], False)

        with open(self.anchor_path, "w", encoding="utf-8") as handle:
            canonical = {"anchor_version": 1, "host_id": "host-test", "host_generation": self.initial_generation,
                         "transition_id": None, "transition_state": "stable", "login_counter": 0}
            json.dump(canonical, handle)
        duplicate_json = json.dumps(canonical).replace(
            f'"host_generation": {self.initial_generation}',
            f'"host_generation": {self.initial_generation}, "host_generation": 0')
        pathlib.Path(self.anchor_path).write_text(duplicate_json, encoding="utf-8")
        duplicate = subprocess.run(self.owner_command("hold", 0), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertFalse(os.path.exists(ready), "duplicate anchor keys must be rejected before child launch")

        with open(self.anchor_path, "w", encoding="utf-8") as handle:
            json.dump(canonical, handle)
        os.chmod(self.lock_path, 0o666)
        unsafe = subprocess.run(self.owner_command("hold", 0), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertFalse(os.path.exists(ready), "unsafe lock must be rejected before child launch")
        os.chmod(self.lock_path, 0o600)

        os.chmod(self.tmp.name, 0o777)
        try:
            unsafe_directory = subprocess.run(self.owner_command("hold", 0), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertNotEqual(unsafe_directory.returncode, 0)
            self.assertFalse(os.path.exists(ready), "unsafe lock directory must be rejected before child launch")
        finally:
            os.chmod(self.tmp.name, 0o700)

    def test_owner_rejects_malformed_final_anchor_values_at_transition(self):
        for scenario in ("malformed-final-null", "unicode-host-transition"):
            with self.subTest(scenario=scenario):
                case = ProcessBoundaryTests(); case.setUp()
                try:
                    if scenario == "unicode-host-transition":
                        decomposed = "e\u0301-host"
                        db = sqlite3.connect(case.db_path, isolation_level=None)
                        db.execute("UPDATE phone_remote_meta SET host_id=? WHERE singleton_id=1", (decomposed,))
                        db.close()
                        with open(case.anchor_path, "w", encoding="utf-8") as handle:
                            json.dump({"anchor_version": 1, "host_id": decomposed,
                                "host_generation": case.initial_generation, "transition_id": None,
                                "transition_state": "stable", "login_counter": 0}, handle)
                    marker = os.path.join(case.tmp.name, "scenario-result")
                    env = dict(case.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
                    result = subprocess.run(case.owner_command(scenario, 3), env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), scenario + "-rejected")
                    with open(case.anchor_path, encoding="utf-8") as handle:
                        state = json.load(handle)
                    self.assertEqual(state["transition_state"], "pending")
                    if scenario == "unicode-host-transition":
                        self.assertEqual(state["host_id"], "e\u0301-host")
                finally:
                    case.tearDown()

    def test_duplicate_anchor_field_is_rejected_during_readback(self):
        marker = os.path.join(self.tmp.name, "scenario-result")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker,
                   PHONE_REMOTE_AUTHORITY_TEST_DUPLICATE_READBACK="host_generation")
        result = subprocess.run(self.owner_command("duplicate-readback", 2), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        text = pathlib.Path(self.anchor_path).read_text(encoding="utf-8")
        self.assertEqual(text.count('"host_generation"'), 2)
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), "duplicate-readback-rejected",
                         "child must not receive a successful write acknowledgment")

    def test_terminal_abort_closes_channel_before_reap_and_releases_lock(self):
        started = time.monotonic()
        result = subprocess.run(self.owner_command("abort-eof", 2), env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 32, result.stderr.decode("utf-8", "replace"))
        self.assertLess(time.monotonic() - started, 5)
        descriptor = os.open(self.lock_path, os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(descriptor)

    def test_store_read_grant_requires_verified_anchor_read(self):
        marker = os.path.join(self.tmp.name, "scenario-result")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
        result = subprocess.run(self.owner_command("release-without-read", 2), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), "release-rejected")

    def test_denials_and_repeated_revoke_reach_the_intended_store_operation(self):
        for scenario, count, expected in (("denied", 3, "login-denied"),
                                          ("denied-mutation", 3, "mutation-preflight-denied"),
                                          ("repeat-revoke", 4, "repeated-revoke-completed")):
            with self.subTest(scenario=scenario):
                case = ProcessBoundaryTests(); case.setUp()
                try:
                    marker = os.path.join(case.tmp.name, "scenario-result")
                    env = dict(case.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
                    result = subprocess.run(case.owner_command(scenario, count), env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), expected)
                    db = sqlite3.connect(case.db_path)
                    if scenario == "denied":
                        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
                        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                                         (case.initial_generation, "stable"))
                    elif scenario == "denied-mutation":
                        self.assertEqual(db.execute("SELECT grant_generation,revoked_at FROM phone_remote_grants WHERE grant_id='g-channel'").fetchone(), (1, None))
                        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                                         (case.initial_generation, "stable"))
                    else:
                        self.assertEqual(db.execute("SELECT grant_generation,revoked_at FROM phone_remote_grants WHERE grant_id='g-channel'").fetchone(), (2, 0.0))
                        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                                         (case.initial_generation + 1, "stable"))
                    db.close()
                finally:
                    case.tearDown()

    def test_scoped_signout_preserves_an_unrelated_session_through_process_channel(self):
        marker = os.path.join(self.tmp.name, "scoped-signout-result")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
        result = subprocess.run(self.owner_command("scoped-signout-control", 8), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), "unrelated-ticket-consumed")
        db = sqlite3.connect(self.db_path)
        rows = dict(db.execute("SELECT session_id,revoked_at FROM phone_remote_sessions"))
        self.assertEqual(rows, {"s-control-a": 0.0, "s-control-b": None})
        self.assertEqual(db.execute("SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0],
                         self.initial_generation)
        db.close()

    def test_second_grant_is_denied_while_the_first_is_active(self):
        marker = os.path.join(self.tmp.name, "scenario-result")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
        result = subprocess.run(self.owner_command("second-grant", 3), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 30)
        self.assertIn(b"owner_busy", result.stderr)
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), "second-grant-denied")

    def test_terminal_abort_child_observes_eof_after_ack(self):
        marker = os.path.join(self.tmp.name, "scenario-result")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
        result = subprocess.run(self.owner_command("abort-eof", 2), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 32, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), "eof")

    def test_failed_abort_ack_is_neutral_unavailable(self):
        parent, child_socket = socket.socketpair()
        owner, child, hello_corr = (str(uuid.uuid4()) for _ in range(3))
        def packet(kind, sequence, correlation, payload):
            frame = {"protocol": "mortimer.phone-authority-channel.v1", "version": 1,
                "kind": kind, "owner_incarnation": owner, "child_incarnation": child,
                "sequence": sequence, "correlation_id": correlation, "payload": payload}
            body = json.dumps(frame, separators=(",", ":")).encode()
            return struct.pack(">I", len(body)) + body
        def receive_frame(sock):
            header = bytearray()
            while len(header) < 4: header.extend(sock.recv(4 - len(header)))
            size = struct.unpack(">I", header)[0]
            body = bytearray()
            while len(body) < size: body.extend(sock.recv(size - len(body)))
            return json.loads(body)
        def fake_owner():
            try:
                parent.sendall(packet("owner.hello", 1, hello_corr, {"max_frame_bytes": MAX_FRAME_BYTES}))
                receive_frame(parent)  # child.ready
                acquire = receive_frame(parent)
                parent.sendall(packet("owner.grant.acquired", 2, acquire["correlation_id"],
                    {"grant_id": str(uuid.uuid4()), "operation": "store.read"}))
                receive_frame(parent)  # child.grant.abort; deliberately withhold the acknowledgment
            finally:
                parent.close()
        worker = threading.Thread(target=fake_owner, daemon=True)
        worker.start()
        anchor = NativeProtectedAnchor(child_socket)
        with self.assertRaisesRegex(StoreUnavailable, "outcome is unknown"):
            with anchor._operation_context("store.read"):
                with anchor.exclusive():
                    raise StoreDenied("original denial must not escape a failed abort")
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_existing_store_runs_across_real_owner_and_child_processes(self):
        result = subprocess.run(self.owner_command("basic", 8), env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        db = sqlite3.connect(self.db_path)
        row = db.execute("SELECT host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()
        session = db.execute("SELECT login_incarnation,revoked_at,session_generation FROM phone_remote_sessions WHERE session_id='s-channel'").fetchone()
        db.close()
        self.assertEqual(row, (self.initial_generation + 1, None, "stable"))
        self.assertEqual(session, (f"host-test:{self.initial_generation}:1", 0, 2))
        # Reopening with the resulting synthetic protected state demonstrates
        # stable pair reconciliation; it is not rollback or Keychain evidence.
        final_anchor = FakeProtectedAnchor("host-test")
        final_anchor.state = AnchorState(1, "host-test", self.initial_generation + 1, None, "stable", 1)
        verify_db = sqlite3.connect(self.db_path, isolation_level=None)
        verify = PhoneAdmissionStore(verify_db, final_anchor)
        self.assertEqual(verify.status()["host_generation"], self.initial_generation + 1)
        verify_db.close()

    def test_second_owner_cannot_take_preprovisioned_inode_while_child_holds_it(self):
        ready = os.path.join(self.tmp.name, "owner-ready")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_READY_FILE=ready)
        first = subprocess.Popen(self.owner_command("hold", 0, 800), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not os.path.exists(ready) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(os.path.exists(ready), "owner/child did not handshake")
            descriptor = os.open(self.lock_path, os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
            self.assertEqual(first.wait(timeout=10), 0)
        finally:
            if first.poll() is None:
                first.kill(); first.wait(timeout=5)
            if first.stdout: first.stdout.close()
            if first.stderr: first.stderr.close()

    def test_login_failure_after_sqlite_commit_leaves_pending_anchor_and_fails_closed(self):
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_FAILPOINT="login_db_committed")
        result = subprocess.run(self.owner_command("basic", 8), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual(anchor["transition_state"], "pending")
        self.assertEqual(anchor["login_counter"], 1)
        db = sqlite3.connect(self.db_path)
        session = db.execute("SELECT login_incarnation,revoked_at FROM phone_remote_sessions WHERE session_id='s-channel'").fetchone()
        db.close()
        self.assertEqual(session, (f"host-test:{self.initial_generation}:1", None))
        unavailable = FakeProtectedAnchor("host-test")
        unavailable.state = AnchorState(1, "host-test", self.initial_generation, "login:interrupted", "pending", 1)
        check_db = sqlite3.connect(self.db_path, isolation_level=None)
        try:
            with self.assertRaises(Exception):
                PhoneAdmissionStore(check_db, unavailable)
        finally:
            check_db.close()

    def test_every_store_transition_failpoint_retains_expected_fail_closed_pair(self):
        cases = {
            "login_before_anchor_reservation": ("stable", 0, 0, "stable", 0, False),
            "login_anchor_reserved": ("pending", 1, 0, "stable", 0, False),
            "login_before_db_commit": ("pending", 1, 0, "stable", 0, False),
            "login_db_committed": ("pending", 1, 0, "stable", 0, True),
            "login_before_anchor_finalize": ("pending", 1, 0, "stable", 0, True),
            "login_anchor_finalized": ("stable", 1, 0, "stable", 0, True),
            "generation_before_anchor_pending": ("stable", 1, 0, "stable", 0, True),
            "generation_anchor_pending": ("pending", 1, 1, "stable", 0, True),
            "generation_before_db_commit": ("pending", 1, 1, "stable", 0, True),
            "generation_db_committed": ("pending", 1, 1, "pending", 1, True),
            "generation_before_anchor_finalize": ("pending", 1, 1, "pending", 1, True),
            "generation_anchor_finalized": ("stable", 1, 1, "pending", 1, True),
        }
        for failpoint, (anchor_phase, anchor_counter, anchor_generation_delta,
                        db_phase, generation_delta, has_session) in cases.items():
            with self.subTest(failpoint=failpoint):
                case = ProcessBoundaryTests()
                case.setUp()
                try:
                    env = dict(case.env, PHONE_REMOTE_AUTHORITY_FAILPOINT=failpoint)
                    result = subprocess.run(case.owner_command("basic", 8), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    with open(case.anchor_path, encoding="utf-8") as handle:
                        anchor = json.load(handle)
                    expected_counter = anchor_counter
                    self.assertEqual((anchor["transition_state"], anchor["host_generation"], anchor["login_counter"]),
                                     (anchor_phase, case.initial_generation + anchor_generation_delta, expected_counter))
                    db = sqlite3.connect(case.db_path)
                    meta = db.execute("SELECT host_generation,transition_state,transition_id FROM phone_remote_meta WHERE singleton_id=1").fetchone()
                    session_count = db.execute("SELECT count(*) FROM phone_remote_sessions WHERE session_id='s-channel'").fetchone()[0]
                    db.close()
                    self.assertEqual(meta[0], case.initial_generation + generation_delta)
                    self.assertEqual(meta[1], db_phase)
                    self.assertEqual(bool(meta[2]), db_phase == "pending")
                    self.assertEqual(session_count == 1, has_session)
                finally:
                    case.tearDown()

    def test_login_after_anchor_finalization_without_release_is_not_admitted_on_restart(self):
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_FAILPOINT="login_anchor_finalized")
        result = subprocess.run(self.owner_command("basic", 8), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor_data = json.load(handle)
        self.assertEqual((anchor_data["transition_state"], anchor_data["login_counter"]), ("stable", 1))
        anchor = FakeProtectedAnchor("host-test")
        anchor.state = AnchorState(1, "host-test", self.initial_generation, None, "stable", 1)
        db = sqlite3.connect(self.db_path, isolation_level=None)
        store = PhoneAdmissionStore(db, anchor)
        self.assertEqual(store.status()["login_counter"], 1)
        with self.assertRaises(StoreDenied):
            store.issue_ticket(identity=_identity(), ticket_id="t-restart", session_id="s-channel",
                owner_id="alice", purpose="offer", payload_digest="sha256:offer",
                now=2, expires_at=20)
        db.close()

    def test_failed_login_authorization_does_not_mutate_anchor_or_database(self):
        result = subprocess.run(self.owner_command("denied", 2), env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual((anchor["transition_state"], anchor["host_generation"], anchor["login_counter"]),
                         ("stable", self.initial_generation, 0))
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()

    def test_spoofed_method_attributes_are_rejected_before_execution(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        store = PhoneAdmissionStore(db, FakeProtectedAnchor())
        channel = object.__new__(NativeProtectedAnchor)
        store.anchor = channel
        calls = []
        class Impostor:
            __name__ = "status"
            __self__ = store
            __func__ = PhoneAdmissionStore.status
            def __call__(self):
                calls.append("executed")
        with self.assertRaises(StoreUnavailable):
            run_store_operation("store.read", Impostor(), anchor=channel)
        self.assertEqual(calls, [])
        db.close()

    def test_operation_context_rejects_concurrent_use(self):
        channel = object.__new__(NativeProtectedAnchor)
        channel._scope_lock = threading.Lock()
        channel._scope_local = threading.local()
        entered = threading.Event()
        release = threading.Event()
        def hold_context():
            with channel._operation_context("store.read"):
                channel._scope_local.grant_count = 1
                entered.set()
                release.wait(2)
        worker = threading.Thread(target=hold_context)
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(StoreUnavailable):
                with channel._operation_context("store.read"):
                    pass
        finally:
            release.set(); worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_failed_global_preflight_does_not_advance_anchor(self):
        result = subprocess.run(self.owner_command("denied-mutation", 1), env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual((anchor["transition_state"], anchor["host_generation"]),
                         ("stable", self.initial_generation))
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_grants WHERE revoked_at IS NOT NULL").fetchone()[0], 0)
        db.close()

    def test_repeated_global_revoke_changes_generation_only_once(self):
        result = subprocess.run(self.owner_command("repeat-revoke", 3), env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual((anchor["transition_state"], anchor["host_generation"]),
                         ("stable", self.initial_generation + 1))
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT grant_generation,revoked_at FROM phone_remote_grants WHERE grant_id='g-channel'").fetchone(), (2, 0.0))
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(), (self.initial_generation + 1, "stable"))
        db.close()

    def test_global_mutation_failure_after_database_commit_preserves_pending_fence(self):
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_FAILPOINT="generation_db_committed")
        result = subprocess.run(self.owner_command("basic", 8), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual(anchor["transition_state"], "pending")
        self.assertEqual(anchor["host_generation"], self.initial_generation + 1)
        db = sqlite3.connect(self.db_path)
        meta = db.execute("SELECT host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()
        session = db.execute("SELECT revoked_at FROM phone_remote_sessions WHERE session_id='s-channel'").fetchone()
        db.close()
        self.assertEqual(meta[0], self.initial_generation + 1)
        self.assertTrue(meta[1])
        self.assertEqual(meta[2], "pending")
        self.assertEqual(session, (0,))

    def test_global_failure_after_anchor_finalization_leaves_database_pending(self):
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_FAILPOINT="generation_anchor_finalized")
        result = subprocess.run(self.owner_command("basic", 8), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual((anchor["transition_state"], anchor["host_generation"], anchor["transition_id"]),
                         ("stable", self.initial_generation + 1, None))
        db = sqlite3.connect(self.db_path)
        meta = db.execute("SELECT host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()
        db.close()
        self.assertEqual(meta[0], self.initial_generation + 1)
        self.assertTrue(meta[1])
        self.assertEqual(meta[2], "pending")

    def test_child_crash_after_anchor_reservation_is_observed_and_keeps_pending_state(self):
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_FAILPOINT="login_anchor_reserved",
                   PHONE_REMOTE_AUTHORITY_CRASH_AT="login_anchor_reserved")
        result = subprocess.run(self.owner_command("basic", 8), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        with open(self.anchor_path, encoding="utf-8") as handle:
            anchor = json.load(handle)
        self.assertEqual((anchor["transition_state"], anchor["login_counter"]), ("pending", 1))
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0], "stable")
        db.close()

    def test_native_owner_rejects_duplicate_and_invalid_sequence_frames(self):
        for scenario in ("duplicate-frame", "float-sequence", "sequence-replay",
                         "sequence-skip", "sequence-overflow"):
            with self.subTest(scenario=scenario):
                marker = os.path.join(self.tmp.name, "malformed-frame-result")
                env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
                result = subprocess.run(self.owner_command(scenario, 1), env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"), "eof",
                                 "the native owner must reject the malformed request and close the channel")
                with open(self.anchor_path, encoding="utf-8") as handle:
                    anchor = json.load(handle)
                self.assertEqual(anchor["transition_state"], "stable")
                db = sqlite3.connect(self.db_path)
                self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
                db.close()

    def test_lost_global_release_ack_is_uncertain_and_does_not_replay_mutation(self):
        entered = os.path.join(self.tmp.name, "release-entered")
        release = os.path.join(self.tmp.name, "release-release")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE="authority.mutate",
                   PHONE_REMOTE_AUTHORITY_ENTERED_FILE=entered,
                   PHONE_REMOTE_AUTHORITY_RELEASE_FILE=release)
        owner = subprocess.Popen(self.owner_command("basic", 8), env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 15
            while not os.path.exists(entered) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(os.path.exists(entered), "owner did not reach the pre-ack barrier")
            owner.kill(); owner.wait(timeout=5)
            descriptor = os.open(self.lock_path, os.O_RDWR)
            try:
                deadline = time.monotonic() + 10
                acquired = False
                while time.monotonic() < deadline:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                        break
                    except BlockingIOError:
                        time.sleep(0.01)
                self.assertTrue(acquired, "child did not terminate after the owner died before release acknowledgment")
            finally:
                os.close(descriptor)
            # The SQLite mutation and final stable metadata commit preceded the
            # withheld acknowledgment; the child must fail instead of replaying.
            db = sqlite3.connect(self.db_path)
            meta = db.execute("SELECT host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()
            session = db.execute("SELECT revoked_at,session_generation FROM phone_remote_sessions WHERE session_id='s-channel'").fetchone()
            db.close()
            self.assertEqual(meta, (self.initial_generation + 1, None, "stable"))
            self.assertEqual(session, (0, 2))
        finally:
            if owner.poll() is None:
                owner.kill(); owner.wait(timeout=5)
            if not os.path.exists(release):
                open(release, "w", encoding="ascii").close()

    def test_owner_death_during_login_transaction_keeps_child_lock_until_uncertain_completion(self):
        entered = os.path.join(self.tmp.name, "entered")
        release = os.path.join(self.tmp.name, "release")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_FAILPOINT="login_before_db_commit",
                   PHONE_REMOTE_AUTHORITY_ENTERED_FILE=entered,
                   PHONE_REMOTE_AUTHORITY_RELEASE_FILE=release)
        owner = subprocess.Popen(self.owner_command("basic", 8), env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        descriptor = os.open(self.lock_path, os.O_RDWR)
        try:
            deadline = time.monotonic() + 15
            while not os.path.exists(entered) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(os.path.exists(entered), "child did not reach the deterministic in-transaction barrier")
            owner.kill(); owner.wait(timeout=5)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            open(release, "w", encoding="ascii").close()
            deadline = time.monotonic() + 10
            acquired = False
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    time.sleep(0.01)
            self.assertTrue(acquired, "child did not release inherited lock after observing owner death")
        finally:
            if owner.poll() is None:
                owner.kill(); owner.wait(timeout=5)
            if os.path.exists(entered) and not os.path.exists(release):
                open(release, "w", encoding="ascii").close()
            os.close(descriptor)
        with open(self.anchor_path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["transition_state"], "pending")
        db = sqlite3.connect(self.db_path)
        session = db.execute("SELECT login_incarnation,revoked_at FROM phone_remote_sessions WHERE session_id='s-channel'").fetchone()
        db.close()
        self.assertEqual(session, (f"host-test:{self.initial_generation}:1", None))
