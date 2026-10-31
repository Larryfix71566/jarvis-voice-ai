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
    ChannelProtocolError, MAX_FRAME_BYTES, NativeProtectedAnchor, NativeProtectedAnchorV2,
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
    malformed_case = scenario.removeprefix("v2-")
    malformed_cases = {"duplicate-frame", "float-sequence", "sequence-replay",
                        "sequence-skip", "sequence-overflow"}
    if malformed_case in malformed_cases:
        from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV2
        v2 = scenario.startswith("v2-")
        anchor = (NativeProtectedAnchorV2 if v2 else NativeProtectedAnchor).from_inherited_environment()
        owner, child = anchor._owner_incarnation, anchor._child_incarnation
        corr = str(uuid.uuid4())
        protocol = "mortimer.phone-authority-channel.v2" if v2 else "mortimer.phone-authority-channel.v1"
        version = 2 if v2 else 1
        if malformed_case == "duplicate-frame":
            body = ("{\"protocol\":\"" + protocol + "\",\"version\":" + str(version) + ","
                    f"\"kind\":\"child.grant.acquire\",\"owner_incarnation\":\"{owner}\","
                    f"\"child_incarnation\":\"{child}\",\"sequence\":2,\"sequence\":2,"
                    f"\"correlation_id\":\"{corr}\",\"payload\":{{\"operation\":\"store.read\"}}}}")
        else:
            bad_sequence = {"float-sequence": 2.0, "sequence-replay": 1,
                "sequence-skip": 3, "sequence-overflow": 1 << 64}[malformed_case]
            body = json.dumps({"protocol": protocol, "version": version,
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
    if scenario not in {"basic", "denied", "denied-mutation", "repeat-revoke", "v2-auth-denial", "v2-service-signout", "v2-lost-authorize-ack", "v2-lost-output-drain", "v2-lost-offer-commit-ack", "v2-lost-update-commit-ack", "v2-output-preflight-lost-ack", "v2-feature-output-gates", "v2-global-revoke-restore", "v2-same-child-restore", "v2-grant-revoke-cleanup", "v2-eof-during-preparation",
                        "v2-duplicate-frame", "v2-float-sequence", "v2-sequence-replay", "v2-sequence-skip", "v2-sequence-overflow",
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
    if scenario in {"v2-service-signout", "v2-lost-authorize-ack", "v2-lost-output-drain",
                     "v2-lost-offer-commit-ack", "v2-lost-update-commit-ack", "v2-feature-output-gates",
                     "v2-output-preflight-lost-ack", "v2-global-revoke-restore", "v2-same-child-restore",
                     "v2-grant-revoke-cleanup", "v2-eof-during-preparation"}:
        from jarvis.bot.phone_remote_service import (
            _AuthorityChildServiceHost, FakeContextVerifier, FakeMediaAdapter,
            TrustedRequestContext,
        )
        class BarrierMedia(FakeMediaAdapter):
            def __init__(self):
                super().__init__(); self.started = threading.Event(); self.release = threading.Event(); self.calls = 0
            def prepare(self, sdp, peer_id=None, resource=None):
                self.calls += 1
                self.started.set()
                if not self.release.wait(5):
                    raise RuntimeError("media barrier timed out")
                return super().prepare(sdp, peer_id, resource)
        class FileBarrierMedia(FakeMediaAdapter):
            def prepare(self, sdp, peer_id=None, resource=None):
                entered = os.environ["PHONE_REMOTE_AUTHORITY_MEDIA_ENTERED_FILE"]
                release = os.environ["PHONE_REMOTE_AUTHORITY_MEDIA_RELEASE_FILE"]
                pathlib.Path(entered).write_text("preparing", encoding="ascii")
                deadline = time.monotonic() + 15
                while not pathlib.Path(release).exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
                if not pathlib.Path(release).exists():
                    raise RuntimeError("media preparation barrier timed out")
                return super().prepare(sdp, peer_id, resource)
        identity = _identity()
        media = (FileBarrierMedia() if scenario == "v2-eof-during-preparation" else
                 FakeMediaAdapter() if scenario in {"v2-lost-output-drain", "v2-lost-offer-commit-ack",
                     "v2-lost-update-commit-ack", "v2-output-preflight-lost-ack", "v2-feature-output-gates",
                     "v2-global-revoke-restore", "v2-same-child-restore", "v2-grant-revoke-cleanup"} else BarrierMedia())
        class CanaryOutputPolicy:
            def prepare(self, _content): return b"private-output-canary"
        from jarvis.bot.phone_remote_service import FakeClockGate, FakeOwnerAvailabilityGate
        clock = FakeClockGate(now=2)
        owner_gate = FakeOwnerAvailabilityGate()
        host = _AuthorityChildServiceHost(database, verifier=FakeContextVerifier(),
            media=media, clock=clock, owner_available=owner_gate,
            output_policy=CanaryOutputPolicy() if scenario in {"v2-lost-output-drain",
                "v2-output-preflight-lost-ack", "v2-feature-output-gates", "v2-global-revoke-restore", "v2-same-child-restore",
                "v2-grant-revoke-cleanup"} else None)
        stage = "login-and-signout"
        try:
            inc_a = host.login(identity=identity, session_id="s-a", grant_id="g-channel",
                              owner_id="alice", now=1, expires_at=100)
            inc_b = host.login(identity=identity, session_id="s-b", grant_id="g-channel",
                              owner_id="alice", now=1, expires_at=100)
            if scenario not in {"v2-same-child-restore", "v2-grant-revoke-cleanup"}:
                host.signout(identity=identity, session_id="s-a", owner_id="alice")
            ctx_a = TrustedRequestContext(identity, "alice", "s-a", "d-channel", inc_a)
            preissue_sdp = "v=0\\r\\no=preissue\\r\\ns=preissue\\r\\nt=0 0\\r\\n"
            preissue_ticket = scenario == "v2-lost-authorize-ack"
            if preissue_ticket:
                preissue_digest = __import__("hashlib").sha256(preissue_sdp.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-b-preissued", session_id="s-b",
                    owner_id="alice", purpose="offer", payload_digest=preissue_digest,
                    now=2, expires_at=20)
            stale = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                "request_id": "a-stale", "operation": "session.status", "payload": {}})
            denied = host.handle(stale, ctx_a)
            if scenario == "v2-lost-authorize-ack":
                try:
                    offer = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                        "request_id": "b-preissued", "operation": "voice.offer",
                        "payload": {"sdp": preissue_sdp}})
                    host.handle(offer, TrustedRequestContext(identity, "alice", "s-b", "d-channel",
                        inc_b, "t-b-preissued"))
                    issue = "unexpected-success"
                except StoreUnavailable:
                    issue = "fenced"
                _record_scenario_result("lost-ack-a=" + denied["status"] + ";b=" + issue
                    + ";preissued=" + str(preissue_ticket) + ";media=" + str(media.calls))
                return 0
            sdp = "v=0\\r\\no=test\\r\\ns=test\\r\\nt=0 0\\r\\n"
            if scenario in {"v2-lost-offer-commit-ack", "v2-eof-during-preparation"}:
                digest = __import__("hashlib").sha256(sdp.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-b-offer", session_id="s-b",
                    owner_id="alice", purpose="offer", payload_digest=digest, now=2, expires_at=20)
                context = TrustedRequestContext(identity, "alice", "s-b", "d-channel", inc_b, "t-b-offer")
                request_wire = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "b-offer", "operation": "voice.offer", "payload": {"sdp": sdp}})
                if scenario == "v2-eof-during-preparation":
                    result = host.handle(request_wire, context)
                    _record_scenario_result("eof-preparation=" + result["status"] + ";after=" +
                        ("fenced" if host._closed else "live"))
                    return 0
                result = host.handle(request_wire, context)
                if result.get("status") != "unavailable" or result.get("reason") != "authority_unavailable":
                    _record_scenario_result("offer-ack-unexpected:" + json.dumps(result, sort_keys=True))
                    return 95
                try:
                    host.handle(stale, ctx_a)
                    after = "unexpected-live"
                except StoreUnavailable:
                    after = "fenced"
                _record_scenario_result("lost-offer=" + result["status"] + ";after=" + after)
                return 0
            if scenario == "v2-lost-update-commit-ack":
                import hashlib
                offer_digest = hashlib.sha256(sdp.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-update-base", session_id="s-b",
                    owner_id="alice", purpose="offer", payload_digest=offer_digest, now=2, expires_at=20)
                offer_context = TrustedRequestContext(identity, "alice", "s-b", "d-channel",
                    inc_b, "t-update-base")
                offer_wire = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "b-base-offer", "operation": "voice.offer", "payload": {"sdp": sdp}})
                accepted = host.handle(offer_wire, offer_context)
                peer_id = accepted.get("payload", {}).get("peer_id")
                if accepted.get("status") != "ok" or not peer_id:
                    _record_scenario_result("base-offer-failed:" + json.dumps(accepted, sort_keys=True))
                    return 96
                update_sdp = "v=0\\r\\no=lost-update\\r\\ns=lost-update\\r\\nt=0 0\\r\\n"
                update_digest = hashlib.sha256(update_sdp.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-update-lost", session_id="s-b",
                    owner_id="alice", purpose="update", payload_digest=update_digest,
                    peer_id=peer_id, now=3, expires_at=20)
                update_context = TrustedRequestContext(identity, "alice", "s-b", "d-channel",
                    inc_b, "t-update-lost")
                update_wire = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "b-lost-update", "operation": "voice.update",
                    "payload": {"peer_id": peer_id, "sdp": update_sdp}})
                result = host.handle(update_wire, update_context)
                try:
                    host.handle(stale, ctx_a)
                    after = "unexpected-live"
                except StoreUnavailable:
                    after = "fenced"
                _record_scenario_result("lost-update=" + result["status"] + ";after=" + after)
                return 0
            if scenario == "v2-output-preflight-lost-ack":
                import hashlib
                output_sdp = "v=0\\r\\no=output-preflight\\r\\ns=output-preflight\\r\\nt=0 0\\r\\n"
                digest = hashlib.sha256(output_sdp.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-output-preflight", session_id="s-b",
                    owner_id="alice", purpose="offer", payload_digest=digest, now=2, expires_at=20)
                request_context = TrustedRequestContext(identity, "alice", "s-b", "d-channel",
                    inc_b, "t-output-preflight")
                request_wire = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "output-preflight-offer", "operation": "voice.offer",
                    "payload": {"sdp": output_sdp}})
                accepted = host.handle(request_wire, request_context)
                if accepted.get("status") != "ok":
                    _record_scenario_result("output-preflight-offer-failed:" + json.dumps(accepted, sort_keys=True))
                    return 97
                enqueued = host.emit_output(accepted["payload"]["peer_id"], {"source": "synthetic-test"})
                fenced_immediately = host._fenced and host._closed
                try:
                    after_response = host.handle(stale, ctx_a)
                    after = ("unavailable:" + str(after_response.get("reason"))
                        if after_response.get("status") == "unavailable" else "unexpected-live")
                except StoreUnavailable:
                    after = "fenced"
                _record_scenario_result("output-preflight=" + str(enqueued)
                    + ";fenced=" + str(host._fenced) + ";closed=" + str(host._closed)
                    + ";immediate=" + str(fenced_immediately) + ";after=" + after)
                return 0
            if scenario == "v2-same-child-restore":
                stage = "same-child-restore-setup"
                sync = pathlib.Path(os.environ["PHONE_REMOTE_AUTHORITY_TEST_SYNC_DIR"])
                sync.mkdir(mode=0o700, parents=True, exist_ok=True)
                sdp_a = "v=0\\r\\no=restore-a\\r\\ns=restore-a\\r\\nt=0 0\\r\\n"
                digest_a = __import__("hashlib").sha256(sdp_a.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-restore-a", session_id="s-a",
                    owner_id="alice", purpose="offer", payload_digest=digest_a, now=2, expires_at=20)
                stage = "same-child-restore-offer"
                ctx_a = TrustedRequestContext(identity, "alice", "s-a", "d-channel", inc_a, "t-restore-a")
                wire_a = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "restore-a-offer", "operation": "voice.offer", "payload": {"sdp": sdp_a}})
                accepted_a = host.handle(wire_a, ctx_a)
                stage = "same-child-restore-queue"
                peer_a = accepted_a.get("payload", {}).get("peer_id")
                queued_a = bool(peer_a and host.emit_output(peer_a, {"source": "restore-canary"}))
                pathlib.Path(sync / "snapshot-ready").write_text("ready", encoding="ascii")
                def wait_signal(name):
                    deadline = time.monotonic() + 20
                    while not (sync / name).exists() and time.monotonic() < deadline:
                        time.sleep(0.005)
                    if not (sync / name).exists():
                        raise RuntimeError("parent restore synchronization timed out")
                wait_signal("snapshot-captured")
                stage = "same-child-restore-signout"
                host.signout(identity=identity, session_id="s-a", owner_id="alice")
                pathlib.Path(sync / "a-signed-out").write_text("signed-out", encoding="ascii")
                def check_after_restore(label):
                    nonlocal stage
                    stage = label + "-check"
                    wait_signal(label + "-ready")
                    stale_retry = host.handle(wire_a, ctx_a)
                    stale_output = host.emit_output(peer_a, {"source": "restore-canary"}) if peer_a else False
                    stale_drain = host.drain_output()
                    return (stale_retry.get("status") == "denied" and not stale_output
                            and stale_drain is None)
                first_denied = check_after_restore("restore-one")
                pathlib.Path(sync / "restore-one-checked").write_text("checked", encoding="ascii")
                second_denied = check_after_restore("restore-two")
                pathlib.Path(sync / "restore-two-checked").write_text("checked", encoding="ascii")
                sdp_b = "v=0\\r\\no=restore-b\\r\\ns=restore-b\\r\\nt=0 0\\r\\n"
                stage = "same-child-b-ticket"
                digest_b = __import__("hashlib").sha256(sdp_b.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-restore-b", session_id="s-b",
                    owner_id="alice", purpose="offer", payload_digest=digest_b, now=3, expires_at=20)
                stage = "same-child-b-offer"
                ctx_b = TrustedRequestContext(identity, "alice", "s-b", "d-channel", inc_b, "t-restore-b")
                wire_b = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "restore-b-offer", "operation": "voice.offer", "payload": {"sdp": sdp_b}})
                accepted_b = host.handle(wire_b, ctx_b)
                _record_scenario_result("a-queued=" + str(queued_a) + ";a-denied="
                    + str(first_denied and second_denied) + ";b=" + accepted_b.get("status", "missing"))
                host.shutdown()
                return 0
            if scenario == "v2-grant-revoke-cleanup":
                sdp_grant = "v=0\\r\\no=grant-revoke\\r\\ns=grant-revoke\\r\\nt=0 0\\r\\n"
                digest_grant = __import__("hashlib").sha256(sdp_grant.encode()).hexdigest()
                host.issue_ticket(identity=identity, ticket_id="t-grant-revoke", session_id="s-b",
                    owner_id="alice", purpose="offer", payload_digest=digest_grant, now=2, expires_at=20)
                ctx_b = TrustedRequestContext(identity, "alice", "s-b", "d-channel", inc_b, "t-grant-revoke")
                wire = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "grant-revoke-offer", "operation": "voice.offer",
                    "payload": {"sdp": sdp_grant}})
                offer_result = host.handle(wire, ctx_b)
                peer = offer_result.get("payload", {}).get("peer_id")
                queued = bool(peer and host.emit_output(peer, {"source": "grant-revoke-canary"}))
                host.mutate_authority("revoke_grant", identity=identity, grant_id="g-channel", owner_id="alice")
                after_status = host.handle(json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "grant-revoke-status", "operation": "session.status", "payload": {}}),
                    TrustedRequestContext(identity, "alice", "s-b", "d-channel", inc_b))
                clean = host.drain_output() is None and not host.emit_output(peer, {"source": "test"})
                try:
                    host.login(identity=identity, session_id="s-fresh-grant", grant_id="g-channel",
                        owner_id="alice", now=3, expires_at=100)
                    fresh = "unexpected-login"
                except (StoreDenied, StoreUnavailable):
                    fresh = "denied"
                _record_scenario_result("offer=" + offer_result.get("status", "missing")
                    + ";queued=" + str(queued) + ";old=" + after_status.get("status", "missing")
                    + ";clean=" + str(clean) + ";fresh=" + fresh)
                if not host._closed:
                    host.shutdown()
                return 0
            if scenario in {"v2-feature-output-gates", "v2-global-revoke-restore"}:
                import hashlib
                def make_offer(session_id, incarnation, ticket_id, request_id, sdp_value):
                    digest = hashlib.sha256(sdp_value.encode()).hexdigest()
                    host.issue_ticket(identity=identity, ticket_id=ticket_id, session_id=session_id,
                        owner_id="alice", purpose="offer", payload_digest=digest, now=2, expires_at=20)
                    request_context = TrustedRequestContext(identity, "alice", session_id,
                        "d-channel", incarnation, ticket_id)
                    wire = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                        "request_id": request_id, "operation": "voice.offer", "payload": {"sdp": sdp_value}})
                    return host.handle(wire, request_context), request_context, wire
                def queue_synthetic(peer):
                    return bool(host.emit_output(peer, {"source": "synthetic-process-test"}))
                if scenario == "v2-feature-output-gates":
                    stage = "feature-off"
                    first, _, first_wire = make_offer("s-b", inc_b, "t-feature", "feature-offer", sdp)
                    stage = "feature-output-queue"
                    first_peer = first.get("payload", {}).get("peer_id")
                    queued_feature = bool(first_peer and queue_synthetic(first_peer))
                    stage = "feature-disable"
                    host.set_enabled(False)
                    stage = "feature-retry"
                    retry = host.handle(first_wire, TrustedRequestContext(identity, "alice", "s-b",
                        "d-channel", inc_b, "t-feature"))
                    stage = "feature-cleanup-check"
                    retry_denied = retry.get("status") == "unavailable" and retry.get("reason") == "feature_off"
                    stage = "feature-drain"
                    drained = host.drain_output() is None
                    stage = "feature-peer-check"
                    peer_denied = not host.emit_output(first_peer, {"source": "test"})
                    feature_clean = retry_denied and drained and peer_denied
                    host.set_enabled(True)
                    stage = "availability-off"
                    inc_c = host.login(identity=identity, session_id="s-c", grant_id="g-channel",
                        owner_id="alice", now=3, expires_at=100)
                    second, _, _ = make_offer("s-c", inc_c, "t-availability", "availability-offer",
                        "v=0\\r\\no=availability\\r\\ns=availability\\r\\nt=0 0\\r\\n")
                    second_peer = second.get("payload", {}).get("peer_id")
                    queued_availability = bool(second_peer and queue_synthetic(second_peer))
                    owner_gate.set_available(False)
                    availability_clean = (host.drain_output() is None
                        and not host.emit_output(second_peer, {"source": "test"}))
                    owner_gate.set_available(True)
                    stage = "expiry"
                    inc_d = host.login(identity=identity, session_id="s-d", grant_id="g-channel",
                        owner_id="alice", now=4, expires_at=100)
                    third, _, _ = make_offer("s-d", inc_d, "t-expiry", "expiry-offer",
                        "v=0\\r\\no=expiry\\r\\ns=expiry\\r\\nt=0 0\\r\\n")
                    third_peer = third.get("payload", {}).get("peer_id")
                    queued_expiry = bool(third_peer and queue_synthetic(third_peer))
                    clock.set_time(101)
                    expiry_clean = (host.drain_output() is None
                        and not host.emit_output(third_peer, {"source": "test"}))
                    _record_scenario_result("feature=" + str(queued_feature and feature_clean)
                        + ";availability=" + str(queued_availability and availability_clean)
                        + ";expiry=" + str(queued_expiry and expiry_clean))
                    host.shutdown()
                    return 0
                # Queue a peer and protected output, globally advance the
                # anchor generation, then prove cleanup and fresh login.
                stage = "global-revoke"
                first, _, _ = make_offer("s-b", inc_b, "t-global-old", "global-old", sdp)
                peer = first.get("payload", {}).get("peer_id")
                queued = bool(peer and queue_synthetic(peer))
                host.mutate_authority("advance_host_generation")
                denied_old = host.handle(stale, ctx_a).get("status")
                output_empty = host.drain_output() is None
                old_peer_rejected = not host.emit_output(peer, {"source": "test"})
                fresh_inc = host.login(identity=identity, session_id="s-fresh", grant_id="g-channel",
                    owner_id="alice", now=3, expires_at=100)
                fresh, _, _ = make_offer("s-fresh", fresh_inc, "t-global-fresh", "global-fresh",
                    "v=0\\r\\no=fresh\\r\\ns=fresh\\r\\nt=0 0\\r\\n")
                _record_scenario_result("old=" + str(denied_old) + ";queued=" + str(queued)
                    + ";clean=" + str(output_empty and old_peer_rejected)
                    + ";fresh=" + str(fresh.get("status")))
                host.shutdown()
                return 0
            ticket_id = "t-b-offer"
            digest = __import__("hashlib").sha256(sdp.encode()).hexdigest()
            host.issue_ticket(identity=identity, ticket_id=ticket_id, session_id="s-b",
                      owner_id="alice", purpose="offer", payload_digest=digest, now=2, expires_at=20)
            ctx_b = TrustedRequestContext(identity, "alice", "s-b", "d-channel", inc_b, ticket_id)
            offer = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                "request_id": "b-offer", "operation": "voice.offer", "payload": {"sdp": sdp}})
            from jarvis.bot.phone_remote_asgi import PhoneRemoteASGI
            import asyncio
            async def run_request(raw):
                sent = []
                events = iter([{"type": "websocket.connect"},
                               {"type": "websocket.receive", "text": raw, "bytes": None},
                               {"type": "websocket.disconnect", "code": 1000}])
                async def receive():
                    return next(events)
                async def send(message):
                    sent.append(message)
                await app({"type": "websocket", "path": "/ws/phone-remote"}, receive, send)
                return sent
            def provider(_scope, request):
                request_ticket = ("t-b-offer" if request is not None and request["operation"] == "voice.offer"
                                  else "t-b-update" if request is not None and request["operation"] == "voice.update"
                                  else None)
                return TrustedRequestContext(identity, "alice", "s-b", "d-channel", inc_b,
                                             request_ticket)
            app = PhoneRemoteASGI(host, provider, enabled=True)
            if scenario == "v2-lost-output-drain":
                sent = asyncio.run(run_request(offer))
                accepted = json.loads(sent[1]["text"])
                if accepted.get("status") != "ok" or not host.emit_output(accepted["payload"]["peer_id"],
                        {"source": "synthetic-test"}):
                    return 94
                try:
                    host.drain_output()
                    drain = "unexpected-bytes"
                except StoreUnavailable:
                    drain = "unavailable"
                try:
                    host.handle(stale, ctx_a)
                    after = "unexpected-live"
                except StoreUnavailable:
                    after = "fenced"
                _record_scenario_result("output-drain=" + drain + ";after=" + after)
                return 0
            async def overlapping_requests():
                first_task = asyncio.create_task(run_request(offer))
                started = await asyncio.to_thread(media.started.wait, 3)
                if not started:
                    media.release.set()
                    raise RuntimeError("media preparation did not reach its barrier")
                # Cancel only after child-worker media preparation started.
                # ASGI must drain the dispatched synchronous service call.
                first_task.cancel()
                second_offer = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "b-busy", "operation": "voice.offer", "payload": {"sdp": sdp}})
                second = await run_request(second_offer)
                media.release.set()
                try:
                    await first_task
                    cancelled = False
                except asyncio.CancelledError:
                    cancelled = True
                first = await run_request(offer)  # exact retry must retrieve the one committed receipt
                return first, second, cancelled
            sent, busy_sent, drained_cancel = asyncio.run(overlapping_requests())
            if len(sent) < 2 or "text" not in sent[1]:
                _record_scenario_result("asgi-no-reply:" + json.dumps(sent, sort_keys=True))
                host.shutdown()
                return 91
            if len(busy_sent) < 2 or "text" not in busy_sent[1]:
                _record_scenario_result("asgi-busy-no-reply:" + json.dumps(busy_sent, sort_keys=True))
                host.shutdown()
                return 92
            accepted = json.loads(sent[1]["text"])
            busy = json.loads(busy_sent[1]["text"])
            if (denied.get("status") != "denied" or accepted.get("status") != "ok"
                    or busy.get("status") != "unavailable" or not drained_cancel):
                _record_scenario_result(json.dumps({"a": denied, "b": accepted, "busy": busy}, sort_keys=True))
                return 90
            peer_id = accepted["payload"]["peer_id"]
            update_sdp = "v=0\\r\\no=update\\r\\ns=update\\r\\nt=0 0\\r\\n"
            update_digest = __import__("hashlib").sha256(update_sdp.encode()).hexdigest()
            host.issue_ticket(identity=identity, ticket_id="t-b-update", session_id="s-b",
                owner_id="alice", purpose="update", payload_digest=update_digest,
                peer_id=peer_id, now=3, expires_at=20)
            update = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                "request_id": "b-update", "operation": "voice.update",
                "payload": {"peer_id": peer_id, "sdp": update_sdp}})
            update_sent = asyncio.run(run_request(update))
            retry_sent = asyncio.run(run_request(update))
            update_reply = json.loads(update_sent[1]["text"])
            retry_reply = json.loads(retry_sent[1]["text"])
            if update_reply != retry_reply or update_reply["status"] != "ok" or media.calls != 2:
                _record_scenario_result("update-retry-invalid:" + json.dumps({
                    "update": update_reply, "retry": retry_reply, "media_calls": media.calls}, sort_keys=True))
                return 93
            _record_scenario_result("a-denied-b-offer-ok-busy-rejected-cancel-drained-update-replayed:" + peer_id)
            host.shutdown()
            return 0
        except BaseException as exc:
            _record_scenario_result("child-error@" + stage + ":" + type(exc).__name__ + ":" + str(exc))
            raise
        finally:
            if not host._closed:
                # Test failures still close the inherited channel so the owner
                # can reap the child rather than hanging on a live descriptor.
                host._thread.join(timeout=2)
    db = sqlite3.connect(database, isolation_level=None, timeout=0.25)
    from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV2
    anchor_type = NativeProtectedAnchorV2 if os.environ.get("PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION") == "2" else NativeProtectedAnchor
    anchor = anchor_type.from_inherited_environment()
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
        if scenario == "v2-auth-denial":
            try:
                run_store_operation("service.authorize", store.current_binding, anchor=anchor,
                    identity=_identity(), owner_id="alice", session_id="missing",
                    device_id="d-channel", login_incarnation="missing-incarnation", now=1)
            except StoreDenied:
                _record_scenario_result("authorization-denied-released")
            else:
                return 89
            anchor.wait_for_shutdown()
            return 0
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

    @staticmethod
    def _v2_frame(kind, sequence, owner, child, correlation, payload):
        return {"protocol": "mortimer.phone-authority-channel.v2", "version": 2,
                "kind": kind, "owner_incarnation": owner, "child_incarnation": child,
                "sequence": sequence, "correlation_id": correlation, "payload": payload}

    def test_v2_rejects_malformed_handshake_fields(self):
        owner, child, corr = (str(uuid.uuid4()) for _ in range(3))
        base = self._v2_frame("owner.hello", 1, owner, child, corr,
                              {"max_frame_bytes": MAX_FRAME_BYTES})
        raw_duplicate = json.dumps(base, separators=(",", ":")).replace(
            '"version":2', '"version":2,"version":2').encode()
        packets = [self._packet({**base, "version": 2.0}),
                   self._packet({**base, "payload": {"max_frame_bytes": float(MAX_FRAME_BYTES)}}),
                   struct.pack(">I", len(raw_duplicate)) + raw_duplicate]
        for packet in packets:
            parent, child_socket = socket.socketpair()
            parent.sendall(packet); parent.close()
            with self.subTest(packet=packet[:64]), self.assertRaises(ChannelProtocolError):
                NativeProtectedAnchorV2(child_socket)

    def test_v2_binding_current_accepts_only_exact_pregrant_false(self):
        parent, child_socket = socket.socketpair()
        owner, child, correlation = (str(uuid.uuid4()) for _ in range(3))
        observed = []
        def fake_owner():
            try:
                parent.sendall(self._packet(self._v2_frame("owner.hello", 1,
                    owner, child, correlation, {"max_frame_bytes": MAX_FRAME_BYTES})))
                self._read_frame(parent)  # child.ready
                parent.settimeout(0.15)
                try:
                    observed.append("unexpected-grant" if parent.recv(1) else "no-grant")
                except TimeoutError:
                    observed.append("no-grant")
            finally:
                parent.close()
        worker = threading.Thread(target=fake_owner, daemon=True)
        worker.start()
        anchor = NativeProtectedAnchorV2(child_socket)
        db = sqlite3.connect(":memory:", isolation_level=None)
        store = PhoneAdmissionStore(db, FakeProtectedAnchor())
        store.anchor = anchor
        result = run_store_operation("service.authorize", store.binding_current,
                                     object(), now=2, anchor=anchor)
        self.assertIs(result, False)
        anchor.close(); worker.join(timeout=2); db.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(observed, ["no-grant"])

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

    def test_v2_readonly_authorization_denial_releases_grant_without_fencing(self):
        marker = os.path.join(self.tmp.name, "v2-authorization-result")
        env = dict(self.env, PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=marker)
        result = subprocess.run(self.owner_command("v2-auth-denial", 3), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(pathlib.Path(marker).read_text(encoding="ascii"),
                         "authorization-denied-released")
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.initial_generation, "stable"))
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
        scenarios = tuple(name for base in ("duplicate-frame", "float-sequence", "sequence-replay",
                         "sequence-skip", "sequence-overflow") for name in (base, "v2-" + base))
        for scenario in scenarios:
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
