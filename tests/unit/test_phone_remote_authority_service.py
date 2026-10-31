"""Actual-process acceptance for the v2 authority/service composition."""
from __future__ import annotations

import json
import fcntl
import hashlib
import os
import pathlib
import queue
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import unittest
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import AnchorState, FakeProtectedAnchor, PhoneAdmissionStore, StoreDenied, StoreUnavailable
from jarvis.bot.phone_remote_service import (
    _AuthorityChildServiceHost, FakeContextVerifier, FakeMediaAdapter, TrustedRequestContext,
)
from tests.unit.test_phone_remote_login import sign_challenge_proof


def _authority_child_restore_entrypoint(database, scenario):
    """Test-only child entrypoint for the adopted v3 pending-restore exercise."""
    if scenario not in {"v3-restore-prepare", "v3-restore-denied", "v3-restore-busy",
                        "v3-restore-phase-invalid", "v3-restore-results-snapshot",
                        "v3-restore-results-lost-ack",
                        "v3-restore-r321-malformed-dispatch",
                        "v3-restore-r321-malformed-dispatch-mutant"}:
        return 64
    if os.environ.get("PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE") in {
            "child-alive-after-close", "shutdown-no-ack"}:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def record(value):
        path = os.environ.get("PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT")
        if path:
            pathlib.Path(path).write_text(json.dumps(value, sort_keys=True,
                separators=(",", ":")), encoding="utf-8")

    if scenario == "v3-restore-phase-invalid":
        from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV3
        anchor = NativeProtectedAnchorV3.from_inherited_environment()
        try:
            try:
                with anchor._operation_context("restore.prepare", method="prepare_restore"):
                    with anchor.exclusive():
                        anchor._request("child.restore.fenced", {
                            "grant_id": anchor._grant_id,
                        }, "owner.restore.prepared")
            except StoreUnavailable:
                record({"rejected": True})
                return 0
            raise AssertionError("out-of-order restore phase was accepted")
        finally:
            anchor.close()

    def failpoint(name):
        if os.environ.get("PHONE_REMOTE_AUTHORITY_FAILPOINT") != name:
            return
        if os.environ.get("PHONE_REMOTE_AUTHORITY_CRASH_AT") == name:
            os._exit(77)
        entered = os.environ.get("PHONE_REMOTE_AUTHORITY_ENTERED_FILE")
        release = os.environ.get("PHONE_REMOTE_AUTHORITY_RELEASE_FILE")
        if entered and release:
            pathlib.Path(entered).write_text("entered", encoding="ascii")
            deadline = time.monotonic() + 15
            while not pathlib.Path(release).exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            if not pathlib.Path(release).exists():
                raise RuntimeError("restore phase barrier timed out")
            return
        raise RuntimeError("injected restore transition interruption")

    r321 = scenario.startswith("v3-restore-r321-malformed-dispatch")
    r321_mutant = scenario.endswith("-mutant")
    r321_capture = [False]
    r321_counts = {"requests": 0, "grants": 0, "submitted": 0, "dequeued": 0,
                   "dispatched": 0, "completed": 0, "verify": 0, "media": 0,
                   "output": 0}
    r321_records = []
    r321_original_request = None
    r321_original_invoke = None
    r321_service_module = None
    r321_original_parse = None
    if r321:
        import dataclasses
        import jarvis.bot.phone_admission_store as admission_store_module
        import jarvis.bot.phone_remote_service as remote_service_module
        from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV3
        from jarvis.bot.phone_remote_protocol import ProtocolError

        r321_service_module = remote_service_module
        r321_original_request = NativeProtectedAnchorV3._request

        def counted_authority_request(anchor, kind, payload, expected):
            r321_counts["requests"] += 1
            if kind == "child.grant.acquire":
                r321_counts["grants"] += 1
            return r321_original_request(anchor, kind, payload, expected)

        NativeProtectedAnchorV3._request = counted_authority_request
        r321_original_invoke = _AuthorityChildServiceHost._invoke_owned

        def freeze(value):
            if value is None or type(value) in {bool, int, float, str, bytes}:
                return value
            if dataclasses.is_dataclass(value):
                return (type(value).__qualname__, tuple(
                    (field.name, freeze(getattr(value, field.name)))
                    for field in dataclasses.fields(value)))
            if type(value) is dict:
                pairs = [(freeze(key), freeze(item)) for key, item in value.items()]
                return tuple(sorted(pairs, key=repr))
            if type(value) in {list, tuple}:
                return tuple(freeze(item) for item in value)
            if type(value) in {set, frozenset}:
                return tuple(sorted((freeze(item) for item in value), key=repr))
            return (type(value).__qualname__, id(value))

        def state_snapshot(service, store, anchor, host):
            table_names = tuple(sorted(row[0] for row in store.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'phone_remote_%'")))
            table_rows = []
            for table_name in table_names:
                rows = store.db.execute(f'SELECT * FROM "{table_name}" ORDER BY rowid').fetchall()
                table_rows.append((table_name, tuple(tuple(row) for row in rows)))
            anchor_path = pathlib.Path(database).with_name("anchor.json")
            if not anchor_path.is_file():
                raise AssertionError("disposable owner anchor fixture is missing")
            with service.output_sink._lock:
                output_queue = freeze(service.output_sink._queue)
            with service._login_coordinator._lock:
                login_records = freeze(service._login_coordinator._records)
            return (
                ("sqlite", tuple(table_rows)),
                ("tickets", freeze(store._tickets)),
                ("process_admissions", freeze(admission_store_module._PROCESS_ADMISSIONS)),
                ("anchor_bytes", anchor_path.read_bytes()),
                ("anchor_runtime", freeze((anchor._anchor_state, anchor._grant_id,
                    anchor._grant_operation, anchor._grant_read_verified,
                    getattr(anchor._scope_local, "operation", None),
                    getattr(anchor._scope_local, "grant_count", 0), anchor._closed,
                    anchor._owner_incarnation, anchor._child_incarnation))),
                ("host", freeze((host._closed, host._fenced, host._thread.is_alive()))),
                ("service", freeze((service._authority_failed, service._peers,
                    service._owner_lease, service._active_resources,
                    service._pending_media, service._ledger,
                    tuple(sorted(id(sink) for sink in service._runtime.sinks)),
                    id(service._service_token), id(service._media_capability)))),
                ("results_absent", service.results is None),
                ("output_queue", output_queue),
                ("canaries", tuple((name, r321_counts[name])
                    for name in ("verify", "media", "output"))),
                ("service_clock", service.clock.snapshot()),
                ("login", (login_records, service._login_coordinator._clock.snapshot(),
                    service._login_coordinator.child_incarnation)),
            )

        def observed_invoke(service, store, anchor, method, args, kwargs):
            if method != "handle" or not r321_capture[0]:
                return r321_original_invoke(service, store, anchor, method, args, kwargs)
            r321_counts["dispatched"] += 1
            before = state_snapshot(service, store, anchor, host_holder[0])
            requests_before, grants_before = r321_counts["requests"], r321_counts["grants"]
            sequence_before = (anchor._send_sequence, anchor._receive_sequence)
            result = r321_original_invoke(service, store, anchor, method, args, kwargs)
            after = state_snapshot(service, store, anchor, host_holder[0])
            sequence_after = (anchor._send_sequence, anchor._receive_sequence)
            with service._lock:
                final_peers = len(service._peers)
                final_leases = len(service._owner_lease)
            with service.output_sink._lock:
                final_queue = len(service.output_sink._queue)
            command_effects = []
            if final_peers or final_leases or r321_counts["media"]:
                command_effects.append("service-command")
            emission_effects = []
            if final_queue or r321_counts["output"]:
                emission_effects.append("output-emission")
            r321_records.append({
                "state_equal": before == after,
                "before_digest": hashlib.sha256(repr(before).encode("utf-8")).hexdigest(),
                "after_digest": hashlib.sha256(repr(after).encode("utf-8")).hexdigest(),
                "owner_calls_delta": r321_counts["requests"] - requests_before,
                "grant_delta": r321_counts["grants"] - grants_before,
                "sequence_equal": sequence_before == sequence_after,
                "final_projection": {"commands": command_effects,
                    "emissions": emission_effects,
                    "active_peers": final_peers, "owner_leases": final_leases,
                    "queued_output": final_queue, "media_prepares": r321_counts["media"],
                    "output_prepares": r321_counts["output"]},
                "response": result,
            })
            return result

        _AuthorityChildServiceHost._invoke_owned = staticmethod(observed_invoke)
        r321_original_parse = remote_service_module.parse_request

        class R321OutputCanary:
            def prepare(self, _content):
                r321_counts["output"] += 1
                return b"synthetic-output-canary"

        verifier = FakeContextVerifier()
        original_verify = verifier.verify

        def counted_verify(context):
            r321_counts["verify"] += 1
            return original_verify(context)

        verifier.verify = counted_verify
        media = FakeMediaAdapter()
        original_prepare = media.prepare

        def counted_prepare(*args, **kwargs):
            r321_counts["media"] += 1
            return original_prepare(*args, **kwargs)

        media.prepare = counted_prepare
        from jarvis.bot.phone_remote_service import FakeBoundedSink
        r321_host_options = {"output_sink": FakeBoundedSink(),
                             "output_policy": R321OutputCanary()}
    else:
        verifier = FakeContextVerifier()
        media = FakeMediaAdapter()
        r321_host_options = {}

    results = None
    if scenario in {"v3-restore-results-snapshot", "v3-restore-results-lost-ack"}:
        from jarvis.bot.phone_remote_results import (
            PhoneRemoteResults, PhoneResultCollectionGrantV1,
            SyntheticResultRecord, SyntheticResultsSource,
        )
        initial_rows = [SyntheticResultRecord(str(uuid.UUID(int=8101)), 1, "visible", "initial",
                          1_800_000_000_000),
                        SyntheticResultRecord(str(uuid.UUID(int=8102)), 1, "secret-title",
                          "SECRET-RESULT-CANARY", 1_800_000_000_000, "protected")]
        collection_grant = PhoneResultCollectionGrantV1("alice", "d-channel", "g-channel",
            str(uuid.UUID(int=8199)), tuple(row.result_id for row in initial_rows))
        results = PhoneRemoteResults(collection_grant, SyntheticResultsSource(initial_rows))
    grant_count = [0]
    original_anchor_request = None
    if scenario in {"v3-restore-results-snapshot", "v3-restore-results-lost-ack"}:
        from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV3
        original_anchor_request = NativeProtectedAnchorV3._request
        def counted_anchor_request(anchor, kind, payload, expected):
            if kind == "child.grant.acquire":
                grant_count[0] += 1
            return original_anchor_request(anchor, kind, payload, expected)
        NativeProtectedAnchorV3._request = counted_anchor_request
    host = _AuthorityChildServiceHost(database, verifier=verifier, media=media,
        login_service_id="svc.restore-test", store_failpoint=failpoint, results=results,
        **r321_host_options)
    try:
        if r321:
            host_holder = [host]
            original_put = host._queue.put_nowait
            original_get = host._queue.get

            def counted_put(item):
                if r321_capture[0] and item is not None and item[0] == "handle":
                    r321_counts["submitted"] += 1
                return original_put(item)

            def counted_get(*args, **kwargs):
                item = original_get(*args, **kwargs)
                if r321_capture[0] and item is not None and item[0] == "handle":
                    r321_counts["dequeued"] += 1
                return item

            host._queue.put_nowait = counted_put
            host._queue.get = counted_get
            identity = ClientIdentity(name="r321-malformed-dispatch-test", user_id="alice")
            message_dir = pathlib.Path(os.environ["PHONE_REMOTE_AUTHORITY_LOGIN_MESSAGE_DIR"])
            fixture_path = pathlib.Path(__file__).resolve().parents[2] / "tests/fixtures/phone_admission_contract/v1.json"
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            cases = [case for case in fixture["cases"]
                     if case["id"].startswith("malformed-event-type-")]
            if len(cases) != 6 or any(case["steps"][0].get("unchanged") is not True
                                      or case["final"] != {"commands": [], "emissions": []}
                                      for case in cases):
                raise AssertionError("frozen malformed-event fixture rows changed")

            challenge = host.issue_login_challenge(device_id="d-channel", grant_id="g-channel")
            if not hasattr(challenge, "challenge_id"):
                raise AssertionError("synthetic proof challenge was not issued")
            fields = {name: getattr(challenge, name) for name in (
                "protocol", "purpose", "challenge_id", "challenge_nonce", "service_id",
                "host_id", "enrolled_key_id", "authority_generation", "expires_at_ms")}
            challenge_path = message_dir / "challenge-a.json"
            challenge_path.write_text(json.dumps(fields, sort_keys=True,
                separators=(",", ":")), encoding="ascii")
            proof_path = message_dir / "proof-a.json"
            deadline = time.monotonic() + 20
            while not proof_path.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            if not proof_path.exists():
                raise RuntimeError("synthetic proof was not supplied")
            login = host.complete_phone_login(challenge_id=challenge.challenge_id,
                                               proof_bytes=proof_path.read_bytes())
            if not hasattr(login, "session_id"):
                raise AssertionError("synthetic proof login did not create a session")
            anchor_state = json.loads(pathlib.Path(database).with_name("anchor.json").read_text(
                encoding="utf-8"))
            incarnation = (f"host-test:{anchor_state['host_generation']}:{anchor_state['login_counter']}")
            context = TrustedRequestContext(identity, "alice", login.session_id,
                                              "d-channel", incarnation)
            control_raw = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                "request_id": "r321-positive-status", "operation": "session.status", "payload": {}},
                separators=(",", ":"), allow_nan=False).encode("utf-8")
            control = host.handle(control_raw, context)
            if control != {"request_id": "r321-positive-status", "status": "ok", "reason": "none",
                           "payload": {"readiness": "ready"}}:
                raise AssertionError("proof-login/status positive control failed")

            if r321_mutant:
                def coercing_parse(raw):
                    try:
                        return r321_original_parse(raw)
                    except ProtocolError:
                        try:
                            obj = json.loads(raw)
                        except (TypeError, ValueError):
                            raise
                        if (type(obj) is dict and obj.get("kind") == "mortimer.phone-remote.v1"
                                and obj.get("protocol_version") == 1
                                and any(obj.get("operation") == row["steps"][0]["event"]["type"]
                                        for row in cases)):
                            obj["operation"] = "session.status"
                            return r321_original_parse(json.dumps(obj, separators=(",", ":"),
                                                       allow_nan=False))
                        raise
                r321_service_module.parse_request = coercing_parse

            if r321_counts["grants"] != 5:
                raise AssertionError(f"proof-login/status setup used {r321_counts['grants']} grants, expected 5")
            r321_capture[0] = True
            responses = []
            request_sequences = []
            for case in cases:
                event_type = case["steps"][0]["event"]["type"]
                request_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                    "mortimer-r321-malformed-event-type:" + case["id"]))
                raw = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": request_id, "operation": event_type, "payload": {}},
                    separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
                response = host.handle(raw, context)
                r321_counts["completed"] += 1
                record_for_case = r321_records[-1]
                if r321_mutant:
                    if (response.get("status") != "ok" or response.get("reason") != "none"
                            or response.get("payload") != {"readiness": "ready"}
                            or record_for_case["owner_calls_delta"] <= 0
                            or record_for_case["grant_delta"] != 2):
                        raise AssertionError("parser mutant did not exercise real status dispatch")
                else:
                    if (response.get("status") != "denied" or response.get("reason") != "malformed_request"
                            or response.get("payload") != {} or not record_for_case["state_equal"]
                            or record_for_case["owner_calls_delta"] != 0
                            or record_for_case["grant_delta"] != 0
                            or not record_for_case["sequence_equal"]):
                        raise AssertionError("malformed operation changed authority state or response relation")
                    if type(event_type) is str:
                        if response["request_id"] != request_id:
                            raise AssertionError("string operation response ID did not echo request ID")
                    elif not re.fullmatch(r"[0-9a-f]{32}", response["request_id"]):
                        raise AssertionError("non-string operation response ID was not service-generated UUID")
                responses.append({"case_id": case["id"], "response": response})
                request_sequences.append({"case_id": case["id"],
                    "owner_calls_delta": record_for_case["owner_calls_delta"],
                    "grant_delta": record_for_case["grant_delta"],
                    "state_equal": record_for_case["state_equal"],
                    "before_digest": record_for_case["before_digest"],
                    "after_digest": record_for_case["after_digest"]})
            r321_capture[0] = False
            expected_grants = 17 if r321_mutant else 5
            if r321_counts["grants"] != expected_grants:
                raise AssertionError("observed owner grant count did not match the adopted budget")
            if not r321_mutant and not all(item["state_equal"] for item in r321_records):
                raise AssertionError("one or more unchanged:true projections diverged")
            final_projection = r321_records[-1]["final_projection"]
            if not r321_mutant and final_projection != {"commands": [], "emissions": [],
                    "active_peers": 0, "owner_leases": 0, "queued_output": 0,
                    "media_prepares": 0, "output_prepares": 0}:
                raise AssertionError("the mapped complete final-state projection changed")
            if r321_counts["submitted"] != 6 or r321_counts["dequeued"] != 6 \
                    or r321_counts["dispatched"] != 6 or r321_counts["completed"] != 6:
                raise AssertionError("worker submission/dequeue/dispatch/completion counts diverged")
            record({"mode": "mutant" if r321_mutant else "normal", "control": control,
                "responses": responses, "observations": request_sequences,
                "owner_calls": r321_counts["requests"], "owner_grants": r321_counts["grants"],
                "worker_counts": {name: r321_counts[name] for name in
                    ("submitted", "dequeued", "dispatched", "completed")},
                "canaries": {name: r321_counts[name] for name in ("verify", "media", "output")},
                "final_model": final_projection})
            host.shutdown()
            return 0
        if scenario in {"v3-restore-results-snapshot", "v3-restore-results-lost-ack"}:
            # The test owner is configured to stop after 65 grants. Count the
            # child's actual wire acquisitions and consume the remaining
            # read-only grants before requesting the normal shutdown handshake.
            # The initial store.open grant completed during host construction.
            # store.open is included by counting before the host is created.
            stage = "login-a"
            identity = ClientIdentity(name="results-process-test", user_id="alice")
            message_dir = pathlib.Path(os.environ["PHONE_REMOTE_AUTHORITY_LOGIN_MESSAGE_DIR"])

            def step(value):
                with (message_dir / "progress.log").open("a", encoding="ascii") as handle:
                    handle.write(value + "\n")
                    handle.flush()

            def complete_login(label):
                step(label + ":challenge-request")
                challenge = host.issue_login_challenge(device_id="d-channel", grant_id="g-channel")
                step(label + ":challenge-issued")
                fields = {name: getattr(challenge, name) for name in (
                    "protocol", "purpose", "challenge_id", "challenge_nonce", "service_id",
                    "host_id", "enrolled_key_id", "authority_generation", "expires_at_ms")}
                (message_dir / f"challenge-{label}.json").write_text(
                    json.dumps(fields, sort_keys=True, separators=(",", ":")), encoding="ascii")
                proof_path = message_dir / f"proof-{label}.json"
                deadline = time.monotonic() + 15
                while not proof_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
                if not proof_path.exists():
                    raise RuntimeError("synthetic proof was not supplied")
                step(label + ":proof-present")
                login = host.complete_phone_login(challenge_id=challenge.challenge_id,
                                                   proof_bytes=proof_path.read_bytes())
                step(label + ":proof-completed-" + type(login).__name__)
                if not hasattr(login, "session_id"):
                    raise RuntimeError("synthetic proof login failed")
                status = host.read_status()
                step(label + ":status-read")
                return login.session_id, f"host-test:{status['host_generation']}:{status['login_counter']}"

            session_a, incarnation_a = complete_login("a")
            if scenario == "v3-restore-results-lost-ack":
                lost_raw = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": "lost-results-snapshot", "operation": "results.snapshot", "payload": {}},
                    separators=(",", ":"))
                lost = host.handle(lost_raw, TrustedRequestContext(identity, "alice", session_a,
                    "d-channel", incarnation_a))
                record({"response": lost, "cursor_count": len(results._cursors),
                    "sequence": results._sequence, "journal_count": len(results._journal),
                    "host_fenced": host._fenced})
                return 0
            stage = "login-b"
            session_b, incarnation_b = complete_login("b")
            result_id, protected_id = str(uuid.UUID(int=8101)), str(uuid.UUID(int=8102))
            rows = [SyntheticResultRecord(result_id, 1, "visible", "initial", 1_800_000_000_000),
                    SyntheticResultRecord(protected_id, 1, "secret-title", "SECRET-RESULT-CANARY",
                        1_800_000_000_000, "protected")]

            def context(session_id, login_incarnation):
                return TrustedRequestContext(identity, "alice", session_id, "d-channel", login_incarnation)

            def request(rid, operation, payload):
                raw = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                    "request_id": rid, "operation": operation, "payload": payload},
                    separators=(",", ":"), ensure_ascii=False)
                return host.handle(raw, context(session_a, incarnation_a))

            stage = "snapshot-a"
            step("snapshot-a:start")
            snapshot_a = request("a-snapshot", "results.snapshot", {})
            step("snapshot-a:done-" + snapshot_a.get("status", "none"))
            cursor_a = snapshot_a["payload"]["cursor"]
            for revision in range(2, 31):
                rows[0] = SyntheticResultRecord(result_id, revision, "visible",
                    f"revision-{revision}", 1_800_000_000_000)
                results._source.replace(rows)
            stage = "pages-a"
            first = request("a-page-1", "results.resume", {"cursor": cursor_a})
            step("page-a:done-" + first.get("status", "none"))
            first_replay = request("a-page-1", "results.resume", {"cursor": cursor_a})
            second = request("a-page-2", "results.resume", {"cursor": first["payload"]["cursor"]})
            stable_historical_receipt = first_replay == first

            stage = "signout-a"
            host.signout(identity=identity, session_id=session_a, owner_id="alice")
            signed_out_replay = request("a-snapshot", "results.snapshot", {})
            context_b = context(session_b, incarnation_b)
            b_raw = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                "request_id": "b-snapshot", "operation": "results.snapshot", "payload": {}},
                separators=(",", ":"))
            stage = "snapshot-b"
            snapshot_b = host.handle(b_raw, context_b)
            stage = "replace-grant"
            results.replace_grant(PhoneResultCollectionGrantV1("alice", "d-channel", "g-channel",
                str(uuid.UUID(int=8200)), tuple(row.result_id for row in initial_rows), version=2))
            stage = "cached-after-grant"
            cached_b_after_grant = host.handle(b_raw, context_b)
            step("cached-grant:done-" + cached_b_after_grant.get("status", "none"))
            b_fresh_raw = json.dumps({"kind": "mortimer.phone-remote.v1", "protocol_version": 1,
                "request_id": "b-snapshot-after-grant", "operation": "results.snapshot", "payload": {}},
                separators=(",", ":"))
            stage = "fresh-after-grant"
            snapshot_b_after_grant = host.handle(b_fresh_raw, context_b)
            step("snapshot-grant:done-" + snapshot_b_after_grant.get("status", "none"))
            rows[0] = SyntheticResultRecord(result_id, 31, "restricted", "SECRET-RECLASSIFIED-CANARY",
                1_800_000_000_000, "protected")
            results._source.replace(rows)
            rows[0] = SyntheticResultRecord(result_id, 32, "visible-again", "VISIBLE-AGAIN-CANARY",
                1_800_000_000_001)
            results._source.replace(rows)
            stage = "cached-after-classification"
            cached_b = host.handle(b_fresh_raw, context_b)
            step("cached-visibility:done-" + cached_b.get("status", "none"))
            after_visibility_raw = json.dumps({"kind": "mortimer.phone-remote.v1",
                "protocol_version": 1, "request_id": "b-after-visibility",
                "operation": "results.snapshot", "payload": {}}, separators=(",", ":"))
            after_visibility = host.handle(after_visibility_raw, context_b)
            rows[0] = SyntheticResultRecord(result_id, 33, "restricted", "NEVER-RETURN-REMOVED",
                1_800_000_000_002, "protected")
            results._source.replace(rows)
            rows[0] = SyntheticResultRecord(result_id, 34, "visible-again", "REINSERTED-CANARY",
                1_800_000_000_003)
            results._source.replace(rows)
            cached_after_reinsert = host.handle(after_visibility_raw, context_b)
            stage = "cursor-after-classification"
            b_old_cursor = host.handle(json.dumps({"kind": "mortimer.phone-remote.v1",
                "protocol_version": 1, "request_id": "b-reset", "operation": "results.resume",
                "payload": {"cursor": snapshot_b_after_grant["payload"]["cursor"]}}, separators=(",", ":")), context_b)
            step("cursor-reset-done-" + b_old_cursor.get("status", "none"))

            stage = "global-mutate"
            host.mutate_authority("advance_host_generation")
            step("global-mutate-done")
            stale_b = host.handle(json.dumps({"kind": "mortimer.phone-remote.v1",
                "protocol_version": 1, "request_id": "b-old", "operation": "results.snapshot",
                "payload": {}}, separators=(",", ":")), context_b)
            step("stale-b-done-" + stale_b.get("status", "none"))
            stage = "login-c"
            session_c, incarnation_c = complete_login("c")
            step("login-c-done")
            snapshot_c = host.handle(b_raw.replace("b-snapshot", "c-snapshot"),
                context(session_c, incarnation_c))
            step("snapshot-c-done-" + snapshot_c.get("status", "none"))
            while grant_count[0] < 65:
                host.read_status()
            if grant_count[0] != 65:
                raise AssertionError("test owner grant budget was exhausted unexpectedly")
            record({"snapshot_a": snapshot_a, "first": first, "first_replay": first_replay,
                "second": second, "stable_historical_receipt": stable_historical_receipt,
                "signed_out_replay": signed_out_replay, "snapshot_b": snapshot_b,
                "cached_b_after_grant_replacement": cached_b_after_grant,
                "snapshot_b_after_grant_replacement": snapshot_b_after_grant,
                "cached_b_after_classification": cached_b, "b_old_cursor_after_classification": b_old_cursor,
                "snapshot_after_visibility": after_visibility,
                "cached_after_remove_reinsert": cached_after_reinsert,
                "stale_b_after_global_generation": stale_b, "snapshot_c_after_fresh_login": snapshot_c})
            step("shutdown-start")
            host.shutdown()
            step("shutdown-done")
            return 0
        with sqlite3.connect(database) as db:
            generation = db.execute(
                "SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
        if scenario == "v3-restore-denied":
            try:
                host.prepare_restore(expected_host_id="host-test", expected_generation=generation + 1)
                raise AssertionError("mismatched restore target was accepted")
            except StoreDenied:
                status = host.read_status()
                record({"denied": True, "status": status})
            host.shutdown()
            return 0
        if scenario == "v3-restore-busy":
            result, failure = [], []
            def prepare():
                try:
                    result.append(host.prepare_restore(expected_host_id="host-test",
                                                       expected_generation=generation))
                except BaseException as exc:
                    failure.append(exc)
            worker = threading.Thread(target=prepare, name="restore-prepare-test")
            worker.start()
            entered = pathlib.Path(os.environ["PHONE_REMOTE_AUTHORITY_ENTERED_FILE"])
            release = pathlib.Path(os.environ["PHONE_REMOTE_AUTHORITY_RELEASE_FILE"])
            deadline = time.monotonic() + 10
            while not entered.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            if not entered.exists():
                raise RuntimeError("restore prepare did not reach its pending barrier")
            try:
                host.read_status()
                busy_rejected = False
            except StoreUnavailable:
                busy_rejected = True
            release.write_text("continue", encoding="ascii")
            worker.join(timeout=10)
            if worker.is_alive() or failure or not busy_rejected:
                raise RuntimeError("local busy rejection disturbed the pending operation")
            record({"busy_rejected": True, "receipt": result[0]})
            return 0
        receipt = host.prepare_restore(expected_host_id="host-test", expected_generation=generation)
        record({"receipt": receipt})
        return 0
    except BaseException as exc:
        chain, current = [], exc
        while current is not None and len(chain) < 5:
            chain.append(type(current).__name__ + ":" + str(current))
            current = current.__cause__
        record({"error": chain, "stage": locals().get("stage", "before-scenario")})
        raise
    finally:
        host._thread.join(timeout=2)


def _card_mail_write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def _card_mail_read(path, *, process=None, timeout=15):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('bounded card fixture mailbox timed out')
        time.sleep(.005)
    data = path.read_bytes()
    if len(data) > 1_048_576:
        raise RuntimeError('oversized card fixture message')
    return data


def _authority_child_card_entrypoint(database):
    """Private v4 test route. No request bytes can select fixture controls."""
    from dataclasses import asdict
    from jarvis.bot.phone_remote_result_commands import ACTIONS
    from jarvis.bot.phone_remote_results import (PhoneRemoteResults,
        PhoneResultCollectionGrantV1, SyntheticResultRecord, SyntheticResultsSource)
    from jarvis.bot.phone_remote_protocol import encode_response, parse_request, ProtocolError
    if os.environ.get('PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION') != '4':
        raise AssertionError('card child must use real v4 authority')
    mailbox = pathlib.Path(os.environ['PHONE_REMOTE_AUTHORITY_LOGIN_MESSAGE_DIR'])
    rows = [SyntheticResultRecord(str(uuid.UUID(int=n)), 1, 'Synthetic card '+str(n),
        'Offline fixture body', 1_800_000_000_000) for n in (1, 2)]
    source = SyntheticResultsSource(rows)
    projector = PhoneRemoteResults(PhoneResultCollectionGrantV1('alice', 'd-channel',
        'g-channel', str(uuid.UUID(int=99)), tuple(str(uuid.UUID(int=n)) for n in (1,2,3))), source)
    original = _AuthorityChildServiceHost._invoke_owned
    captured = []
    def invoke(service, store, anchor, method, args, kwargs):
        if not captured:
            service.result_commands.register(projector, tuple(sorted(ACTIONS)))
            captured.append(service)
        return original(service, store, anchor, method, args, kwargs)
    _AuthorityChildServiceHost._invoke_owned = staticmethod(invoke)
    host = _AuthorityChildServiceHost(database, verifier=FakeContextVerifier(),
        media=FakeMediaAdapter(), results=projector)
    try:
        challenge = host.issue_login_challenge(device_id='d-channel', grant_id='g-channel')
        _card_mail_write(mailbox/'challenge.json', json.dumps(asdict(challenge)).encode())
        proof = _card_mail_read(mailbox/'proof.json')
        login = host.complete_phone_login(challenge_id=challenge.challenge_id, proof_bytes=proof)
        if not hasattr(login, 'session_id'):
            raise AssertionError('card proof login failed')
        state = json.loads(pathlib.Path(database).with_name('anchor.json').read_bytes())
        context = TrustedRequestContext(ClientIdentity(name='card-fixture', user_id='alice'),
            'alice', login.session_id, 'd-channel',
            f"host-test:{state['host_generation']}:{state['login_counter']}")
        _card_mail_write(mailbox/'ready', b'ready')
        for sequence in range(1, 27):
            request = _card_mail_read(mailbox/f'{sequence}.request')
            if request == b'fixture-stop':
                break
            # Fixture controls have their own private file, never the wire request.
            control_path = mailbox/f'{sequence}.control'
            if control_path.exists():
                control = control_path.read_text()
                if control == 'edit-other':
                    source.replace([rows[0], SyntheticResultRecord(rows[1].result_id, 2,
                        'Updated fixture', 'Offline update', 1_800_000_000_001)])
                elif control == 'protect-other':
                    source.replace([rows[0], SyntheticResultRecord(rows[1].result_id, 2,
                        'PROTECTED-CANARY', 'PROTECTED-CANARY', 1, 'protected')])
                elif control in {'tick', 'notify', 'feature-off', 'feature-on'}:
                    try:
                        if control == 'tick':host.tick()
                        elif control == 'notify':host.notify_revocation()
                        else:host.set_enabled(control == 'feature-on')
                    except StoreUnavailable:
                        pass  # The response/observation must expose any unexpected fence.
                elif control == 'poll-queued-cancel':
                    cancel=threading.Event();original_put=host._queue.put_nowait
                    original_request=host._anchor._request;grants=[]
                    def counted(kind,payload,expected):
                        if kind=='child.grant.acquire':grants.append(payload['operation'])
                        return original_request(kind,payload,expected)
                    def queued(item):
                        wait=item[3].event.wait
                        def before_poll(timeout=None):
                            if not wait(2):raise AssertionError('poll worker did not settle')
                            return True
                        item[3].event.wait=before_poll
                        original_put(item);cancel.set()
                    host._queue.put_nowait=queued;host._anchor._request=counted
                    try:
                        try:host._submit('tick',_cancel_event=cancel)
                        except StoreUnavailable:pass
                        else:raise AssertionError('queued poll cancellation succeeded')
                        if grants or host._fenced:raise AssertionError('cancelled poll touched native authority')
                    finally:
                        host._queue.put_nowait=original_put;host._anchor._request=original_request
                elif control == 'poll-drain':
                    arrived=threading.Event();release=threading.Event();quiescing=threading.Event()
                    original_observer=host._anchor._admission_observer;outcome=[];drained=[]
                    def observed(phase,operation):
                        original_observer(phase,operation)
                        if phase=='released' and operation=='service.authorize':
                            arrived.set()
                            if not release.wait(2):raise AssertionError('poll authorization barrier timed out')
                    host._anchor._admission_observer=observed
                    caller=threading.Thread(target=lambda: outcome.append(host.tick()));caller.start()
                    if not arrived.wait(2):raise AssertionError('poll was not authorized')
                    original_drained=host._drained
                    class DrainEvent:
                        def wait(self,timeout=None):quiescing.set();return original_drained.wait(timeout)
                        def set(self):original_drained.set()
                    host._drained=DrainEvent();operation=str(uuid.uuid4())
                    drain=threading.Thread(target=lambda:drained.append(host.quiesce(operation)));drain.start()
                    if not quiescing.wait(2):raise AssertionError('poll drain did not enter')
                    release.set();caller.join(2);drain.join(2)
                    if caller.is_alive() or drain.is_alive() or outcome!=[0] or drained!=[{'operation_id':operation,'drained':True}]:
                        raise AssertionError('authorized poll did not drain exactly once')
                    _card_mail_write(mailbox/'poll-drained',json.dumps(drained).encode())
                elif control in {'publication-change', 'publication-reentry-change', 'publication-reentry-history'}:
                    service=captured[0];registry=service.result_commands
                    original_publication=registry.publication;publication_calls=[]
                    historical_control=control=='publication-reentry-history'
                    terminal_control=control!='publication-change'
                    nested=json.loads(request);nested['request_id']='nested-publication-denial'
                    def changed_publication(*args,**kwargs):
                        publication_calls.append(None)
                        if len(publication_calls)==(2 if historical_control else 1):
                            if terminal_control:service.handle(json.dumps(nested),context)
                            source.replace([rows[0],SyntheticResultRecord(rows[1].result_id,2,
                                'Changed fixture','Changed body',1,
                                'protected' if historical_control else 'ordinary')])
                        return original_publication(*args,**kwargs)
                    registry.publication=changed_publication
                elif control == 'ack-reentry':
                    from contextlib import contextmanager
                    service=captured[0];original_commit=service._service_commit
                    nested=json.loads(request);nested['request_id']='nested-at-ack'
                    @contextmanager
                    def reentered_commit():
                        with original_commit():yield
                        service.handle(json.dumps(nested),context)
                    service._service_commit=reentered_commit
                elif control == 'lose-ack':
                    original_request = host._anchor._request
                    def lost_ack(kind, payload, expected):
                        anchor = host._anchor
                        if kind == 'child.grant.release' and anchor._grant_operation == 'service.commit':
                            anchor._send(kind, payload, correlation_id=str(uuid.uuid4()))
                            anchor.close()
                            raise StoreUnavailable('injected lost release acknowledgement')
                        return original_request(kind, payload, expected)
                    host._anchor._request = lost_ack
                elif control == 'revoke-capability':
                    registry=captured[0].result_commands
                    registry.revoke(projector, registry._slot(projector).capability)
                else:
                    raise AssertionError('unknown trusted fixture control')
            try:
                response = host.handle(request, context)
            except StoreUnavailable:
                response = dict(request_id=parse_request(request)['request_id'],status='unavailable',
                    reason='authority_unavailable',payload={})
            service=captured[0]
            with service._lock:
                observation=dict(views=[value.payload for value in service.result_commands._views.values()],
                    states=[entry['state'] for entry in service._ledger.values()],
                    fenced=host._fenced, peers=len(service._peers), leases=len(service._owner_lease))
            _card_mail_write(mailbox/f'{sequence}.observation',json.dumps(observation).encode())
            try: operation = parse_request(request)['operation']
            except ProtocolError: operation = None
            _card_mail_write(mailbox/f'{sequence}.response', encode_response(response, operation=operation).encode('utf-8'))
        return 0
    finally:
        host._queue.put_nowait(None)
        host._thread.join(timeout=5)
        if host._thread.is_alive():
            host._anchor.close()
            raise RuntimeError('owned card worker did not terminate')
        _AuthorityChildServiceHost._invoke_owned = staticmethod(original)
        _card_mail_write(mailbox/'closed', b'closed')


class _CardProcessBridge:
    """Owned disposable native process; trusted test configuration, bounded wire I/O."""
    def __init__(self, *, scopes=('read', 'action')):
        self.temporary = tempfile.TemporaryDirectory(prefix='phone-card-process-')
        self.directory = pathlib.Path(self.temporary.name)
        os.chmod(self.directory, 0o700)
        self.sequence = 0
        self.process = None
        try:
            private = ec.generate_private_key(ec.SECP256R1())
            public = private.public_key().public_bytes(serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint)
            database = self.directory/'authority.sqlite'
            db=sqlite3.connect(database, isolation_level=None)
            anchor=FakeProtectedAnchor('host-test')
            store=PhoneAdmissionStore(db, anchor)
            identity=ClientIdentity(name='card-fixture', user_id='alice')
            store.add_device(identity=identity,device_id='d-channel',owner_id='alice',
                public_key=public,key_algorithm='p256-sha256-sec1-v1')
            store.add_grant(identity=identity,grant_id='g-channel',device_id='d-channel',
                owner_id='alice',scopes=list(scopes))
            state=anchor.state
            db.close()
            anchor_path=self.directory/'anchor.json'
            anchor_path.write_text(json.dumps(dict(anchor_version=1,host_id='host-test',
                host_generation=state.host_generation,transition_id=None,
                transition_state='stable',login_counter=0)))
            lock=self.directory/'owner.lock';lock.touch(mode=0o600)
            root=pathlib.Path(__file__).resolve().parents[2]
            env=os.environ.copy()
            env.update(PYTHONPATH=str(root),PHONE_REMOTE_AUTHORITY_CHANNEL_FD='3',
                PHONE_REMOTE_AUTHORITY_LOCK_FD='4',
                PHONE_REMOTE_AUTHORITY_LOGIN_MESSAGE_DIR=str(self.directory),
                PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT=str(self.directory/'result'))
            command=[os.environ['PHONE_REMOTE_AUTHORITY_OWNER_BIN'],'--test-owner',str(lock),
                os.environ.get('PHONE_REMOTE_AUTHORITY_PYTHON',sys.executable),str(database),
                str(root),'v4-card-bridge','65','0',str(state.host_generation),'0',str(anchor_path)]
            self.process=subprocess.Popen(command,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            challenge=SimpleNamespace(**json.loads(_card_mail_read(self.directory/'challenge.json',process=self.process)))
            _card_mail_write(self.directory/'proof.json',sign_challenge_proof(challenge,private))
            _card_mail_read(self.directory/'ready',process=self.process)
        except BaseException:
            self.close()
            raise

    def exchange(self, request, *, control=None):
        if type(request) is not bytes or not 0<len(request)<=1_048_576 or self.sequence>=25:
            raise ValueError('bounded fixture request limit')
        self.sequence+=1
        if control is not None:
            _card_mail_write(self.directory/f'{self.sequence}.control',control.encode())
        _card_mail_write(self.directory/f'{self.sequence}.request',request)
        return _card_mail_read(self.directory/f'{self.sequence}.response',process=self.process)

    def close(self):
        teardown_failure = None
        try:
            if self.process is not None:
                # The owner retains/reaps its child after channel loss. Request
                # child teardown before waiting for that owner to exit.
                _card_mail_write(self.directory/f'{self.sequence+1}.request', b'fixture-stop')
                if (self.directory/'ready').exists():
                    try:
                        _card_mail_read(self.directory/'closed', timeout=5)
                    except RuntimeError as error:
                        teardown_failure = error
                if self.process.poll() is None:
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                            self.process.wait(timeout=2)
            if teardown_failure is not None:
                raise teardown_failure
        finally:
            self.temporary.cleanup()


def _card_stdio_bridge():
    import struct
    def read_exact(size):
        value=b''
        while len(value)<size:
            chunk=sys.stdin.buffer.read(size-len(value))
            if not chunk:raise EOFError
            value+=chunk
        return value
    bridge=_CardProcessBridge()
    try:
        while True:
            try: size=struct.unpack('>I',read_exact(4))[0]
            except EOFError:return 0
            if not 0<size<=1_048_576:return 64
            result=bridge.exchange(read_exact(size))
            sys.stdout.buffer.write(struct.pack('>I',len(result))+result)
            sys.stdout.buffer.flush()
    finally:bridge.close()


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if arguments == ["--phone-card-bridge"]:
        sys.exit(_card_stdio_bridge())
    if len(arguments) == 3 and arguments[0] == "--authority-child":
        sys.exit(_authority_child_restore_entrypoint(arguments[1], arguments[2]))
    sys.exit(64)


@unittest.skipUnless(os.environ.get("PHONE_REMOTE_AUTHORITY_OWNER_BIN"),
                     "requires the built offline native owner executable")
class PhoneRemoteAuthorityServiceProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="phone-authority-service-")
        self._owned_processes = []
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
        for process in self._owned_processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
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
        anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        command = [owner, "--test-owner", self.lock, python, self.database,
                   str(self.root), scenario, str(grants), "0", str(anchor["host_generation"]),
                   str(anchor["login_counter"]), self.anchor_path]
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._owned_processes.append(process)
        return marker, process

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

    def _prepare_login_key(self):
        private = ec.generate_private_key(ec.SECP256R1())
        public = private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        db = sqlite3.connect(self.database, isolation_level=None)
        db.execute("UPDATE phone_remote_devices SET public_key=?,key_algorithm=? WHERE device_id=?",
                   (public, "p256-sha256-sec1-v1", "d-channel"))
        db.close()
        return private

    def _prepare_two_login_devices(self):
        private_a = self._prepare_login_key()
        private_b = ec.generate_private_key(ec.SECP256R1())
        public_b = private_b.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        anchor_data = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        db = sqlite3.connect(self.database, isolation_level=None)
        anchor = FakeProtectedAnchor(anchor_data["host_id"])
        anchor.state = AnchorState(anchor_data["anchor_version"], anchor_data["host_id"],
            anchor_data["host_generation"], anchor_data["transition_id"],
            anchor_data["transition_state"], anchor_data["login_counter"])
        store = PhoneAdmissionStore(db, anchor)
        identity = ClientIdentity(name="authority-login-test", user_id="alice")
        store.add_device(identity=identity, device_id="d-login-b", owner_id="alice",
                         public_key=public_b, key_algorithm="p256-sha256-sec1-v1")
        store.add_grant(identity=identity, grant_id="g-login-b", device_id="d-login-b",
                        owner_id="alice", scopes=["read", "voice"])
        self.generation = db.execute(
            "SELECT host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
        db.close()
        pathlib.Path(self.anchor_path).write_text(json.dumps({"anchor_version": 1,
            "host_id": anchor.state.host_id, "host_generation": anchor.state.host_generation,
            "transition_id": anchor.state.transition_id, "transition_state": anchor.state.transition_state,
            "login_counter": anchor.state.login_counter}), encoding="utf-8")
        return private_a, private_b

    def _prepare_capacity_login_devices(self, count=16):
        anchor_data = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        db = sqlite3.connect(self.database, isolation_level=None)
        anchor = FakeProtectedAnchor(anchor_data["host_id"])
        anchor.state = AnchorState(anchor_data["anchor_version"], anchor_data["host_id"],
            anchor_data["host_generation"], anchor_data["transition_id"],
            anchor_data["transition_state"], anchor_data["login_counter"])
        store = PhoneAdmissionStore(db, anchor)
        identity = ClientIdentity(name="authority-login-test", user_id="alice")
        for index in range(count):
            device_id = "d-capacity-" + str(index)
            grant_id = "g-capacity-" + str(index)
            private = ec.generate_private_key(ec.SECP256R1())
            public = private.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            store.add_device(identity=identity, device_id=device_id, owner_id="alice",
                public_key=public, key_algorithm="p256-sha256-sec1-v1")
            store.add_grant(identity=identity, grant_id=grant_id, device_id=device_id,
                owner_id="alice", scopes=["read", "voice"])
        overflow_private = ec.generate_private_key(ec.SECP256R1())
        overflow_public = overflow_private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        store.add_device(identity=identity, device_id="d-capacity-overflow", owner_id="alice",
            public_key=overflow_public, key_algorithm="p256-sha256-sec1-v1")
        store.add_grant(identity=identity, grant_id="g-capacity-overflow", device_id="d-capacity-overflow",
            owner_id="alice", scopes=["read", "voice"])
        self.generation = store.status()["host_generation"]
        state = anchor.state
        db.close()
        pathlib.Path(self.anchor_path).write_text(json.dumps({"anchor_version": state.anchor_version,
            "host_id": state.host_id, "host_generation": state.host_generation,
            "transition_id": state.transition_id, "transition_state": state.transition_state,
            "login_counter": state.login_counter}), encoding="utf-8")

    def _prepare_restore_session(self):
        data = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        anchor = FakeProtectedAnchor(data["host_id"])
        anchor.state = AnchorState(data["anchor_version"], data["host_id"],
            data["host_generation"], data["transition_id"], data["transition_state"],
            data["login_counter"])
        db = sqlite3.connect(self.database, isolation_level=None)
        store = PhoneAdmissionStore(db, anchor)
        identity = ClientIdentity(name="restore-prepare-test", user_id="alice")
        incarnation = store.login(identity=identity, session_id="s-restore", grant_id="g-channel",
                                  owner_id="alice", now=1, expires_at=100)
        self.assertEqual(incarnation, f"host-test:{self.generation}:1")
        state = anchor.state
        db.close()
        pathlib.Path(self.anchor_path).write_text(json.dumps({"anchor_version": state.anchor_version,
            "host_id": state.host_id, "host_generation": state.host_generation,
            "transition_id": state.transition_id, "transition_state": state.transition_state,
            "login_counter": state.login_counter}), encoding="utf-8")

    def test_v3_restore_prepare_pending_fences_and_keeps_owner_lock(self):
        self._prepare_restore_session()
        hold = os.path.join(self.tmp.name, "restore-owner-held")
        wire = os.path.join(self.tmp.name, "restore-wire.jsonl")
        marker, process = self._start_owner("v3-restore-prepare", grants=64,
            env_updates={"PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE": hold,
                         "PHONE_REMOTE_AUTHORITY_RESTORE_WIRE_FILE": wire})
        try:
            self._wait_for_marker(marker, timeout=15)
            self._wait_for_marker(hold, timeout=15)
            receipt = json.loads(pathlib.Path(marker).read_text(encoding="utf-8"))["receipt"]
            self.assertEqual(receipt["transition_state"], "pending")
            self.assertEqual(receipt["host_generation"], self.generation + 1)
            self.assertEqual(str(uuid.UUID(receipt["transition_id"])), receipt["transition_id"])
            anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
            self.assertEqual((anchor["transition_state"], anchor["host_generation"],
                              anchor["transition_id"]),
                             ("pending", self.generation + 1, receipt["transition_id"]))
            db = sqlite3.connect(self.database)
            meta = db.execute("SELECT host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()
            session = db.execute("SELECT revoked_at,session_generation FROM phone_remote_sessions WHERE session_id='s-restore'").fetchone()
            db.close()
            self.assertEqual(meta, (self.generation + 1, receipt["transition_id"], "pending"))
            self.assertEqual(session, (0, 2))
            contender = os.open(self.lock, os.O_RDWR)
            try:
                try:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.fail("restore owner released the singleton lock while pending")
                except BlockingIOError:
                    pass
            finally:
                os.close(contender)
            frames = [json.loads(line) for line in pathlib.Path(wire).read_text(encoding="utf-8").splitlines()]
            kinds = [(frame["direction"], frame["kind"]) for frame in frames]
            self.assertEqual(kinds, [
                ("child", "child.grant.acquire"), ("owner", "owner.grant.acquired"),
                ("child", "child.anchor.read"), ("owner", "owner.anchor.state"),
                ("child", "child.anchor.advance"), ("owner", "owner.anchor.verified"),
                ("child", "child.anchor.read"), ("owner", "owner.anchor.state"),
                ("child", "child.restore.database_pending"),
                ("child", "child.restore.fenced"), ("owner", "owner.restore.prepared"),
                ("owner", "owner.shutdown"), ("child", "child.shutdown_ack"),
            ])
            acquire, acquired = frames[0], frames[1]
            self.assertEqual(acquire["payload"], {"operation": "restore.prepare"})
            self.assertEqual(acquire["correlation_id"], acquired["correlation_id"])
            self.assertEqual(frames[2]["correlation_id"], frames[3]["correlation_id"])
            advance = frames[4]["payload"]["state"]
            operation_id = advance["transition_id"]
            self.assertEqual(str(uuid.UUID(operation_id)), operation_id)
            self.assertEqual(frames[4]["correlation_id"], frames[5]["correlation_id"])
            self.assertEqual(frames[8]["payload"], {"grant_id": acquired["payload"]["grant_id"],
                                                     "operation_id": operation_id})
            self.assertNotEqual(frames[8]["correlation_id"], frames[4]["correlation_id"])
            self.assertEqual(frames[9]["payload"], {"grant_id": acquired["payload"]["grant_id"],
                                                     "operation_id": operation_id})
            self.assertNotEqual(frames[9]["correlation_id"], frames[8]["correlation_id"])
            prepared = frames[10]
            self.assertEqual(prepared["correlation_id"], frames[9]["correlation_id"])
            self.assertEqual(prepared["payload"], {"grant_id": acquired["payload"]["grant_id"],
                "operation_id": operation_id, "host_generation": self.generation + 1,
                "transition_state": "pending"})
            shutdown = frames[11]
            self.assertNotEqual(shutdown["correlation_id"], prepared["correlation_id"])
            self.assertNotEqual(shutdown["correlation_id"], frames[9]["correlation_id"])
            self.assertEqual(str(uuid.UUID(shutdown["correlation_id"])), shutdown["correlation_id"])
            self.assertEqual(frames[12]["correlation_id"], shutdown["correlation_id"])
            child_request_ids = [frames[index]["correlation_id"] for index in (0, 2, 4, 6, 8, 9)]
            self.assertEqual(len(child_request_ids), len(set(child_request_ids)))
            self.assertNotIn(shutdown["correlation_id"], child_request_ids)
            for direction in ("owner", "child"):
                sequence = [frame["sequence"] for frame in frames if frame["direction"] == direction]
                self.assertEqual(sequence, sorted(set(sequence)), direction)
            self.assertNotIn(("child", "child.grant.release"), kinds)
            self.assertNotIn(("child", "child.restore.grant.retire"), kinds)
            self.assertNotIn(("owner", "owner.restore.database_pending"), kinds)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

        owner = os.environ["PHONE_REMOTE_AUTHORITY_OWNER_BIN"]
        python = os.environ.get("PHONE_REMOTE_AUTHORITY_PYTHON", os.sys.executable)
        rejected = subprocess.run([owner, "--test-owner", self.lock, python, self.database,
            str(self.root), "v3-hold", "0", "0", str(self.generation + 1), "1", self.anchor_path],
            cwd=self.root, capture_output=True, timeout=10)
        self.assertNotEqual(rejected.returncode, 0)

    def test_v3_restore_preflight_denial_preserves_stable_authority(self):
        marker, process = self._start_owner("v3-restore-denied", grants=3)
        try:
            self._wait_for_marker(marker, timeout=15)
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0)
            result = json.loads(pathlib.Path(marker).read_text(encoding="utf-8"))
            self.assertTrue(result["denied"])
            self.assertEqual(result["status"]["host_generation"], self.generation)
            anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
            self.assertEqual((anchor["transition_state"], anchor["host_generation"]),
                             ("stable", self.generation))
            db = sqlite3.connect(self.database)
            self.assertEqual(db.execute("SELECT transition_state,host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                             ("stable", self.generation))
            db.close()
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_v3_restore_local_busy_rejects_without_disturbing_pending_operation(self):
        self._prepare_restore_session()
        entered = os.path.join(self.tmp.name, "restore-entered")
        release = os.path.join(self.tmp.name, "restore-release")
        hold = os.path.join(self.tmp.name, "restore-owner-held")
        marker, process = self._start_owner("v3-restore-busy", grants=64, env_updates={
            "PHONE_REMOTE_AUTHORITY_FAILPOINT": "restore_anchor_pending",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release,
            "PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE": hold})
        try:
            self._wait_for_marker(marker, timeout=15)
            self._wait_for_marker(hold, timeout=15)
            result = json.loads(pathlib.Path(marker).read_text(encoding="utf-8"))
            self.assertTrue(result["busy_rejected"])
            self.assertEqual(result["receipt"]["transition_state"], "pending")
            self.assertIsNone(process.poll(), "prepared owner must continue holding the lock")
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_v3_restore_bad_prepared_ack_never_returns_a_receipt(self):
        self._prepare_restore_session()
        hold = os.path.join(self.tmp.name, "restore-owner-held")
        marker, process = self._start_owner("v3-restore-prepare", grants=64,
            env_updates={"PHONE_REMOTE_AUTHORITY_TEST_BAD_RESTORE_PREPARED_ACK": "1",
                         "PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE": hold})
        try:
            self._wait_for_marker(marker)
            self._wait_for_marker(hold)
            self.assertIsNone(process.poll(), "failed prepared delivery must retain the owner lock")
            outcome = json.loads(pathlib.Path(marker).read_text(encoding="utf-8"))
            self.assertIn("error", outcome)
            self.assertNotIn("receipt", outcome)
            anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
            self.assertEqual(anchor["transition_state"], "pending")
            db = sqlite3.connect(self.database)
            self.assertEqual(db.execute("SELECT transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0],
                             "pending")
            db.close()
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_v3_restore_out_of_order_phase_is_terminal_without_mutation(self):
        marker, process = self._start_owner("v3-restore-phase-invalid", grants=64)
        try:
            process.communicate(timeout=10)
            self.assertNotEqual(process.returncode, 0)
            self._wait_for_marker(marker)
            self.assertEqual(json.loads(pathlib.Path(marker).read_text(encoding="utf-8")),
                             {"rejected": True})
            anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
            self.assertEqual((anchor["transition_state"], anchor["host_generation"]),
                             ("stable", self.generation))
            db = sqlite3.connect(self.database)
            self.assertEqual(db.execute("SELECT transition_state,host_generation FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                             ("stable", self.generation))
            db.close()
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)

    def test_v3_restore_prepare_crash_phases_remain_unfinalized(self):
        cases = {
            "restore_before_anchor_pending": ("stable", "stable", False),
            "restore_anchor_pending": ("pending", "stable", True),
            "restore_before_db_commit": ("pending", "stable", True),
            "restore_db_pending": ("pending", "pending", True),
        }
        for failpoint, (anchor_phase, expected_db_phase, must_hold) in cases.items():
            case = PhoneRemoteAuthorityServiceProcessTests()
            case.setUp()
            try:
                case._prepare_restore_session()
                hold = os.path.join(case.tmp.name, "restore-owner-held")
                marker, process = case._start_owner("v3-restore-prepare", grants=64,
                    env_updates={"PHONE_REMOTE_AUTHORITY_FAILPOINT": failpoint,
                                 "PHONE_REMOTE_AUTHORITY_CRASH_AT": failpoint,
                                 "PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE": hold})
                try:
                    if must_hold:
                        case._wait_for_marker(hold, timeout=15)
                        self.assertIsNone(process.poll(), failpoint + ": owner must retain lock")
                        contender = os.open(case.lock, os.O_RDWR)
                        try:
                            with self.assertRaises(BlockingIOError, msg=failpoint):
                                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        finally:
                            os.close(contender)
                    else:
                        process.communicate(timeout=15)
                        self.assertNotEqual(process.returncode, 0, failpoint)
                        self.assertFalse(pathlib.Path(hold).exists(), failpoint)
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
                anchor = json.loads(pathlib.Path(case.anchor_path).read_text(encoding="utf-8"))
                db = sqlite3.connect(case.database)
                db_phase = db.execute("SELECT transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
                active = db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0]
                db.close()
                self.assertEqual((anchor["transition_state"], db_phase),
                                 (anchor_phase, expected_db_phase), failpoint)
                self.assertEqual(active, 0 if db_phase == "pending" else 1, failpoint)
                self.assertFalse(pathlib.Path(marker).exists(), failpoint)
            finally:
                case.tearDown()

    def test_v3_restore_uncertain_phases_retain_owner_lock_after_child_reap(self):
        cases = {
            "anchor-write-uncertain": ("pending", "stable", 1),
            "anchor-readback-uncertain": ("pending", "stable", 1),
            "database-pending-received": ("pending", "pending", 0),
            "service-fenced": ("pending", "pending", 0),
            "grant-retirement": ("pending", "pending", 0),
            "prepared-delivery": ("pending", "pending", 0),
            "shutdown-ack": ("pending", "pending", 0),
            "child-exit-after-shutdown-ack": ("pending", "pending", 0),
        }
        for phase, (anchor_phase, db_phase_expected, active_expected) in cases.items():
            case = PhoneRemoteAuthorityServiceProcessTests()
            case.setUp()
            try:
                case._prepare_restore_session()
                hold = os.path.join(case.tmp.name, "restore-owner-held")
                marker, process = case._start_owner("v3-restore-prepare", grants=64,
                    env_updates={"PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE": hold,
                                 "PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE": phase})
                try:
                    case._wait_for_marker(hold, timeout=15)
                    self.assertIsNone(process.poll(), phase + ": owner must retain lock")
                    contender = os.open(case.lock, os.O_RDWR)
                    try:
                        with self.assertRaises(BlockingIOError, msg=phase):
                            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        os.close(contender)
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
                anchor = json.loads(pathlib.Path(case.anchor_path).read_text(encoding="utf-8"))
                db = sqlite3.connect(case.database)
                db_phase = db.execute("SELECT transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
                active = db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0]
                db.close()
                self.assertEqual(anchor["transition_state"], anchor_phase, phase)
                self.assertEqual(db_phase, db_phase_expected, phase)
                self.assertEqual(active, active_expected, phase)
                if pathlib.Path(marker).exists():
                    outcome = json.loads(pathlib.Path(marker).read_text(encoding="utf-8"))
                    self.assertNotIn("receipt", outcome, phase)
            finally:
                case.tearDown()

    def test_v3_restore_shutdown_timeout_kills_and_reaps_owned_child_while_holding_lock(self):
        for phase in ("child-alive-after-close", "shutdown-no-ack"):
            case = PhoneRemoteAuthorityServiceProcessTests()
            case.setUp()
            try:
                case._prepare_restore_session()
                hold = os.path.join(case.tmp.name, "restore-owner-held")
                reaping = os.path.join(case.tmp.name, "restore-owner-reaping")
                reaped = os.path.join(case.tmp.name, "restore-owner-reaped")
                marker, process = case._start_owner("v3-restore-prepare", grants=64,
                    env_updates={"PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE": hold,
                        "PHONE_REMOTE_AUTHORITY_RESTORE_REAP_WAIT_FILE": reaping,
                        "PHONE_REMOTE_AUTHORITY_RESTORE_REAP_FILE": reaped,
                        "PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE": phase,
                        "PHONE_REMOTE_AUTHORITY_TEST_RESTORE_SHUTDOWN_TIMEOUT_MS": "150",
                        "PHONE_REMOTE_AUTHORITY_TEST_RESTORE_REAP_GRACE_MS": "100"})
                try:
                    case._wait_for_marker(reaping, timeout=15)
                    self.assertIsNone(process.poll(), phase + ": owner must remain alive while reaping")
                    contender = os.open(case.lock, os.O_RDWR)
                    try:
                        with self.assertRaises(BlockingIOError, msg=phase + ": lock during reap"):
                            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        os.close(contender)
                    case._wait_for_marker(reaped, timeout=10)
                    self.assertIn("reaped;signal=KILL;", pathlib.Path(reaped).read_text(encoding="ascii"))
                    case._wait_for_marker(hold, timeout=10)
                    self.assertIsNone(process.poll(), phase + ": owner must retain lock after reap")
                    anchor = json.loads(pathlib.Path(case.anchor_path).read_text(encoding="utf-8"))
                    db = sqlite3.connect(case.database)
                    state = db.execute("SELECT transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
                    db.close()
                    self.assertEqual(anchor["transition_state"], "pending", phase)
                    self.assertEqual(state, "pending", phase)
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
            finally:
                case.tearDown()

    def _start_login_owner(self, scenario, *, grants=64, extra_env=None, message_dir=None):
        # The owner may write its first challenge before Popen returns. Give
        # independent runs a fresh directory; the restart-replay test may
        # explicitly reuse one to present the prior child's proof.
        if message_dir is None:
            message_dir = pathlib.Path(tempfile.mkdtemp(
                prefix="login-messages-", dir=self.tmp.name))
            if any(message_dir.iterdir()):
                raise AssertionError("new login message directory was not empty before spawn")
        else:
            message_dir = pathlib.Path(message_dir)
            if not message_dir.is_dir():
                raise AssertionError("explicit login message directory is missing")
        env = {"PHONE_REMOTE_AUTHORITY_LOGIN_MESSAGE_DIR": str(message_dir)}
        if extra_env:
            env.update(extra_env)
        if getattr(self, "_v4_regression", False):
            scenario = scenario.replace("v3-login-", "v4-login-", 1)
        marker, process = self._start_owner(scenario, grants=grants, env_updates=env)
        return message_dir, marker, process

    def _wait_login_challenge(self, message_dir, label, process):
        path = message_dir / ("challenge-" + label + ".json")
        self._wait_for_file(str(path), process)
        return SimpleNamespace(**json.loads(path.read_text(encoding="ascii")))

    @staticmethod
    def _write_login_proof(message_dir, label, challenge, private_key):
        proof = sign_challenge_proof(challenge, private_key)
        destination = message_dir / ("proof-" + label + ".json")
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(proof)
        temporary.replace(destination)

    def _finish_login_owner(self, marker, process):
        try:
            result = process.communicate(timeout=25)
        except subprocess.TimeoutExpired:
            self.fail("login owner did not finish before the bounded test timeout")
        self.assertEqual(process.returncode, 0,
                         result[1].decode("utf-8", "replace") + " | " +
                         (pathlib.Path(marker).read_text(encoding="utf-8")
                          if pathlib.Path(marker).exists() else "<no result>"))
        self._wait_for_marker(marker)
        return json.loads(pathlib.Path(marker).read_text(encoding="ascii"))

    def test_v4_actual_process_proof_login_and_service_regressions(self):
        for name in (
            "test_actual_process_login_proof_creates_one_server_owned_session_and_replay_is_denied",
            "test_proof_login_session_is_usable_by_v3_authority_service",
            "test_proof_attempt_limit_retires_challenge_without_session_mutation",
            "test_expiry_between_signature_verification_and_preflight_is_nonmutating_then_b_logs_in",
        ):
            with self.subTest(case=name):
                case = type(self)(name)
                case.setUp()
                try:
                    case._v4_regression = True
                    getattr(case, name)()
                finally:
                    case.tearDown()

    def test_actual_process_login_proof_creates_one_server_owned_session_and_replay_is_denied(self):
        private = self._prepare_login_key()
        message_dir, marker, process = self._start_login_owner("v3-login-replay", grants=3)
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge, private)
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["login"].keys(), {"session_id", "expires_at_ms"})
        self.assertEqual(len(result["login"]["session_id"]), 32)
        self.assertEqual(result["replay"], {"failure": "challenge_unavailable"})
        db = sqlite3.connect(self.database)
        rows = db.execute("SELECT session_id,owner_id,grant_id,login_incarnation,expires_at FROM phone_remote_sessions").fetchall()
        self.assertEqual(len(rows), 1)
        session_id, owner_id, grant_id, incarnation, expires_at = rows[0]
        self.assertEqual(session_id, result["login"]["session_id"])
        self.assertEqual((owner_id, grant_id), ("alice", "g-channel"))
        self.assertTrue(incarnation.startswith("host-test:"))
        self.assertEqual(expires_at, result["login"]["expires_at_ms"] / 1000.0)
        db.close()

    def test_proof_login_session_is_usable_by_v3_authority_service(self):
        private = self._prepare_login_key()
        # Store construction, challenge, login, then service.status authorize
        # and commit grants.
        message_dir, marker, process = self._start_login_owner("v3-login-service-status", grants=5)
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge, private)
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["login"].keys(), {"session_id", "expires_at_ms"})
        self.assertEqual(result["status"], {"request_id": "proof-login-status", "status": "ok",
            "reason": "none", "payload": {"readiness": "ready"}})

    def test_malformed_event_type_refinement_preserves_all_six_no_effect_markers(self):
        private = self._prepare_login_key()
        fixture_path = self.root / "tests/fixtures/phone_admission_contract/v1.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases = [case for case in fixture["cases"]
                 if case["id"].startswith("malformed-event-type-")]
        self.assertEqual(len(cases), 6)
        self.assertTrue(all(case["steps"][0].get("unchanged") is True for case in cases))
        for mutant in (False, True):
            scenario = "v3-restore-r321-malformed-dispatch" + ("-mutant" if mutant else "")
            message_dir, marker, process = self._start_login_owner(
                scenario, grants=17 if mutant else 5)
            try:
                challenge = self._wait_login_challenge(message_dir, "a", process)
                self._write_login_proof(message_dir, "a", challenge, private)
                result = self._finish_login_owner(marker, process)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            self.assertEqual(result["control"], {"request_id": "r321-positive-status",
                "status": "ok", "reason": "none", "payload": {"readiness": "ready"}})
            self.assertEqual(result["owner_grants"], 17 if mutant else 5)
            self.assertEqual(result["worker_counts"], {"submitted": 6, "dequeued": 6,
                "dispatched": 6, "completed": 6})
            self.assertEqual(result["canaries"], {"verify": 7 if mutant else 1,
                "media": 0, "output": 0})
            self.assertEqual([item["case_id"] for item in result["responses"]],
                             [case["id"] for case in cases])
            self.assertEqual([item["case_id"] for item in result["observations"]],
                             [case["id"] for case in cases])
            self.assertEqual(result["final_model"], {"commands": [], "emissions": [],
                "active_peers": 0, "owner_leases": 0, "queued_output": 0,
                "media_prepares": 0, "output_prepares": 0})
            for case, response_item, observation in zip(
                    cases, result["responses"], result["observations"]):
                event_type = case["steps"][0]["event"]["type"]
                request_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                    "mortimer-r321-malformed-event-type:" + case["id"]))
                response = response_item["response"]
                if mutant:
                    self.assertEqual((response["status"], response["reason"], response["payload"]),
                                     ("ok", "none", {"readiness": "ready"}))
                    self.assertGreater(observation["owner_calls_delta"], 0)
                    self.assertEqual(observation["grant_delta"], 2)
                else:
                    self.assertEqual((response["status"], response["reason"], response["payload"]),
                                     ("denied", "malformed_request", {}))
                    self.assertTrue(observation["state_equal"], case["id"])
                    self.assertEqual(observation["before_digest"], observation["after_digest"])
                    self.assertEqual(observation["owner_calls_delta"], 0)
                    self.assertEqual(observation["grant_delta"], 0)
                    if type(event_type) is str:
                        self.assertEqual(response["request_id"], request_id)
                    else:
                        self.assertRegex(response["request_id"], r"^[0-9a-f]{32}$")

    def test_concurrent_cancelled_login_keeps_child_owned_work_and_returns_typed_busy(self):
        private = self._prepare_login_key()
        entered = os.path.join(self.tmp.name, "login-verify-entered")
        release = os.path.join(self.tmp.name, "login-verify-release")
        time_file = os.path.join(self.tmp.name, "login-time.json")
        message_dir, marker, process = self._start_login_owner("v3-login-busy", grants=3, extra_env={
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_RELEASE_FILE": release,
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_TIME_FILE": time_file})
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge, private)
            result = self._finish_login_owner(marker, process)
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["busy"], {"failure": "busy"})
        self.assertEqual(result["busy_challenge"], {"failure": "busy"})
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["duplicate"], {"failure": "busy"})
        self.assertEqual(result["login"]["expires_at_ms"], 1_800_043_200_000)
        self.assertEqual(len(result["login"]["session_id"]), 32)
        self.assertEqual(result["replay"], {"failure": "challenge_unavailable"})
        self.assertTrue(pathlib.Path(entered).exists())
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0], 1)
        db.close()

    def test_proof_login_loss_of_success_release_ack_never_returns_success(self):
        private = self._prepare_login_key()
        entered = os.path.join(self.tmp.name, "login-success-ack-entered")
        release = os.path.join(self.tmp.name, "login-success-ack-release")
        message_dir, marker, process = self._start_login_owner("v3-login-replay", grants=3, extra_env={
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "session.login",
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "3",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge, private)
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            self._wait_for_marker(marker)
            result = json.loads(pathlib.Path(marker).read_text(encoding="ascii"))
            self.assertEqual(result, {"login": {"failure": "unavailable"},
                "replay": {"failure": "unavailable"}})
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0], 1)
        db.close()

    def test_challenge_denial_lost_release_ack_fences_following_login(self):
        entered = os.path.join(self.tmp.name, "challenge-denial-ack-entered")
        release = os.path.join(self.tmp.name, "challenge-denial-ack-release")
        _, marker, process = self._start_login_owner("v3-login-challenge-denial-ack-lost", grants=3, extra_env={
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "session.challenge",
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "2",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        try:
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            self._wait_for_marker(marker)
            self.assertEqual(json.loads(pathlib.Path(marker).read_text(encoding="ascii")),
                {"a": {"failure": "unavailable"}, "b": {"failure": "unavailable"}})
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()

    def test_proof_login_crash_matrix_uses_real_v3_channel_and_session_transition(self):
        cases = {
            "login_before_anchor_reservation": ("stable", 0, "stable", False),
            "login_anchor_reserved": ("pending", 1, "stable", False),
            "login_before_db_commit": ("pending", 1, "stable", False),
            "login_db_committed": ("pending", 1, "stable", True),
            "login_before_anchor_finalize": ("pending", 1, "stable", True),
            "login_anchor_finalized": ("stable", 1, "stable", True),
        }
        for failpoint, (anchor_phase, counter, db_phase, has_session) in cases.items():
            case = PhoneRemoteAuthorityServiceProcessTests()
            case.setUp()
            try:
                private = case._prepare_login_key()
                message_dir, _, process = case._start_login_owner("v3-login-crash", grants=3,
                    extra_env={"PHONE_REMOTE_AUTHORITY_FAILPOINT": failpoint,
                               "PHONE_REMOTE_AUTHORITY_CRASH_AT": failpoint})
                try:
                    challenge = case._wait_login_challenge(message_dir, "a", process)
                    case._write_login_proof(message_dir, "a", challenge, private)
                    process.communicate(timeout=25)
                    self.assertNotEqual(process.returncode, 0, failpoint)
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
                anchor = json.loads(pathlib.Path(case.anchor_path).read_text(encoding="utf-8"))
                self.assertEqual((anchor["transition_state"], anchor["login_counter"]),
                    (anchor_phase, counter), failpoint)
                db = sqlite3.connect(case.database)
                meta = db.execute("SELECT transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone()[0]
                session_count = db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0]
                db.close()
                self.assertEqual(meta, db_phase, failpoint)
                self.assertEqual(session_count == 1, has_session, failpoint)
            finally:
                case.tearDown()

    def test_unknown_selector_denial_is_acknowledged_and_unrelated_login_succeeds_same_child(self):
        private = self._prepare_login_key()
        message_dir, marker, process = self._start_login_owner("v3-login-unknown-b", grants=4)
        try:
            challenge = self._wait_login_challenge(message_dir, "b", process)
            self._write_login_proof(message_dir, "b", challenge, private)
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["a"], {"failure": "not_authorized"})
        self.assertEqual(result["b"].keys(), {"session_id", "expires_at_ms"})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.generation, "stable"))
        db.close()
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["login_counter"], 1)

    def test_revoked_challenge_is_denied_and_unaffected_device_logs_in_same_child(self):
        private_a, private_b = self._prepare_two_login_devices()
        message_dir, marker, process = self._start_login_owner("v3-login-revoke-then-b", grants=6)
        try:
            challenge_a = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge_a, private_a)
            challenge_b = self._wait_login_challenge(message_dir, "b", process)
            self._write_login_proof(message_dir, "b", challenge_b, private_b)
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["a"], {"failure": "not_authorized"})
        self.assertEqual(result["b"].keys(), {"session_id", "expires_at_ms"})
        db = sqlite3.connect(self.database)
        sessions = db.execute("""SELECT s.owner_id,g.device_id,s.grant_id
            FROM phone_remote_sessions s JOIN phone_remote_grants g ON g.grant_id=s.grant_id
            WHERE s.revoked_at IS NULL""").fetchall()
        self.assertEqual(sessions, [("alice", "d-login-b", "g-login-b")])
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.generation + 1, "stable"))
        db.close()
        anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        self.assertEqual(anchor["host_generation"], self.generation + 1)
        self.assertEqual(anchor["login_counter"], 1)

    def test_challenge_capacity_is_bounded_without_eviction(self):
        self._prepare_login_key()
        message_dir, marker, process = self._start_login_owner("v3-login-capacity", grants=5)
        try:
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result, {"issued": 4, "overflow": {"failure": "capacity"}})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.generation, "stable"))
        db.close()
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["login_counter"], 0)

    def test_total_challenge_capacity_is_bounded_across_devices(self):
        self._prepare_capacity_login_devices(16)
        _, marker, process = self._start_login_owner("v3-login-total-capacity", grants=65)
        try:
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result, {"issued": 64, "overflow": {"failure": "capacity"}})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["login_counter"], 0)

    def test_retired_proof_tombstone_retains_total_capacity_until_expiry(self):
        self._prepare_login_key()
        self._prepare_capacity_login_devices(15)
        _, marker, process = self._start_login_owner("v3-login-retired-tombstone", grants=65)
        try:
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result, {"bad": [{"failure": "proof_rejected"}] * 3,
            "filled": 63, "overflow": {"failure": "capacity"}})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["login_counter"], 0)

    def test_challenge_registry_is_not_revived_by_child_restart(self):
        private = self._prepare_login_key()
        message_dir, marker, process = self._start_login_owner("v3-login-issue-only", grants=2)
        try:
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result, {"challenge": {"issued": True}})
        challenge = self._wait_login_challenge(message_dir, "a", process)
        self._write_login_proof(message_dir, "a", challenge, private)
        _, marker, restarted = self._start_login_owner("v3-login-restart-reject", grants=2,
                                                       message_dir=message_dir)
        try:
            result = self._finish_login_owner(marker, restarted)
        finally:
            if restarted.poll() is None:
                restarted.kill(); restarted.wait(timeout=5)
        self.assertEqual(result, {"login": {"failure": "challenge_unavailable"}})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()

    def test_consumed_challenge_stays_retired_after_repeated_raw_database_restore(self):
        private = self._prepare_login_key()
        entered = os.path.join(self.tmp.name, "login-success-release-entered")
        release = os.path.join(self.tmp.name, "login-success-release")
        message_dir, marker, process = self._start_login_owner("v3-login-replay-restore", grants=3, extra_env={
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "session.login",
            "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE": "3",
            "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
            "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        snapshot = self.database + ".challenge-snapshot"
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            source = sqlite3.connect(self.database)
            destination = sqlite3.connect(snapshot)
            source.backup(destination)
            destination.close(); source.close()
            self._write_login_proof(message_dir, "a", challenge, private)
            self._wait_for_file(entered, process)
            for _ in range(2):
                saved = sqlite3.connect(snapshot)
                restored = sqlite3.connect(self.database)
                saved.backup(restored)
                restored.close(); saved.close()
            pathlib.Path(release).write_text("continue", encoding="ascii")
            result = self._finish_login_owner(marker, process)
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["login"].keys(), {"session_id", "expires_at_ms"})
        self.assertEqual(result["replay"], {"failure": "challenge_unavailable"})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        db.close()
        anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        self.assertEqual(anchor["login_counter"], 1)

    def test_unknown_selector_denials_do_not_consume_challenge_capacity(self):
        self._prepare_login_key()
        _, marker, process = self._start_login_owner("v3-login-unknown-capacity", grants=8)
        try:
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result, {"unknown_denied": 6, "issued": True})

    def test_proof_attempt_limit_retires_challenge_without_session_mutation(self):
        private = self._prepare_login_key()
        message_dir, marker, process = self._start_login_owner("v3-login-attempt-limit", grants=2)
        try:
            challenge = self._wait_login_challenge(message_dir, "login", process)
            self._write_login_proof(message_dir, "login", challenge, private)
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["bad"], [{"failure": "proof_rejected"}] * 3)
        self.assertEqual(result["after_limit"], {"failure": "challenge_unavailable"})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.generation, "stable"))
        db.close()
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["login_counter"], 0)

    def test_expiry_between_signature_verification_and_preflight_is_nonmutating_then_b_logs_in(self):
        private = self._prepare_login_key()
        root = pathlib.Path(self.tmp.name)
        entered, release, time_file = (root / "verify-entered", root / "verify-release", root / "clock.json")
        message_dir, marker, process = self._start_login_owner("v3-login-expiry-then-b", grants=5, extra_env={
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_ENTERED_FILE": str(entered),
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_RELEASE_FILE": str(release),
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_TIME_FILE": str(time_file)})
        try:
            challenge_a = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge_a, private)
            self._wait_for_file(str(entered), process)
            time_file.write_text(json.dumps({"wall_ms": challenge_a.expires_at_ms + 1,
                                             "monotonic_ms": 61_001}), encoding="ascii")
            release.touch()
            challenge_b = self._wait_login_challenge(message_dir, "b", process)
            self._write_login_proof(message_dir, "b", challenge_b, private)
            result = self._finish_login_owner(marker, process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result["bad_proof"], {"failure": "proof_rejected"})
        self.assertEqual(result["expired"], {"failure": "challenge_unavailable"})
        self.assertEqual(result["b"].keys(), {"session_id", "expires_at_ms"})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions WHERE revoked_at IS NULL").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.generation, "stable"))
        db.close()
        self.assertEqual(json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))["login_counter"], 1)

    def test_lost_expiry_denial_ack_fences_child_and_never_mints_session(self):
        private = self._prepare_login_key()
        root = pathlib.Path(self.tmp.name)
        verify_entered, verify_release, time_file = (root / "verify-entered", root / "verify-release", root / "clock.json")
        reject_entered, reject_release = root / "reject-entered", root / "reject-release"
        message_dir, marker, process = self._start_login_owner("v3-login-expiry-ack-lost", grants=3, extra_env={
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_ENTERED_FILE": str(verify_entered),
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_RELEASE_FILE": str(verify_release),
            "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_TIME_FILE": str(time_file),
            "PHONE_REMOTE_AUTHORITY_PAUSE_REJECT_ACK": "1",
            "PHONE_REMOTE_AUTHORITY_REJECT_ENTERED_FILE": str(reject_entered),
            "PHONE_REMOTE_AUTHORITY_REJECT_RELEASE_FILE": str(reject_release)})
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge, private)
            self._wait_for_file(str(verify_entered), process)
            time_file.write_text(json.dumps({"wall_ms": challenge.expires_at_ms + 1,
                                             "monotonic_ms": 61_001}), encoding="ascii")
            verify_release.touch()
            self._wait_for_file(str(reject_entered), process)
            process.terminate()  # Lost owner acknowledgment makes the preflight outcome uncertain.
            process.communicate(timeout=10)
            self._wait_for_marker(marker)
            result = json.loads(pathlib.Path(marker).read_text(encoding="ascii"))
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result, {"after": "fenced", "login": {"failure": "unavailable"}})
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT host_generation,transition_state FROM phone_remote_meta WHERE singleton_id=1").fetchone(),
                         (self.generation, "stable"))
        db.close()
        anchor = json.loads(pathlib.Path(self.anchor_path).read_text(encoding="utf-8"))
        self.assertEqual((anchor["login_counter"], anchor["transition_state"]), (0, "stable"))

    def test_v3_results_flow_uses_process_store_and_revalidates_signout_and_visibility(self):
        private = self._prepare_login_key()
        message_dir, marker, process = self._start_login_owner("v3-restore-results-snapshot", grants=65)
        try:
            challenge_a = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge_a, private)
            challenge_b = self._wait_login_challenge(message_dir, "b", process)
            self._write_login_proof(message_dir, "b", challenge_b, private)
            challenge_c = self._wait_login_challenge(message_dir, "c", process)
            self._write_login_proof(message_dir, "c", challenge_c, private)
            output, error = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            output, error = process.communicate(timeout=5)
            progress = pathlib.Path(marker).read_text(encoding="utf-8", errors="replace") if pathlib.Path(marker).exists() else "<missing>"
            steps = pathlib.Path(message_dir / "progress.log").read_text(encoding="ascii") if (message_dir / "progress.log").exists() else "<no steps>"
            self.fail(f"results child did not finish: {error.decode('utf-8', 'replace')}; progress={progress}; steps={steps}")
        marker_text = pathlib.Path(marker).read_text(encoding="utf-8") if pathlib.Path(marker).exists() else "<no result>"
        self.assertEqual(process.returncode, 0, error.decode("utf-8", "replace") + " | " + marker_text)
        result = json.loads(marker_text)
        self.assertEqual(result["snapshot_a"]["status"], "ok")
        self.assertEqual(len(result["snapshot_a"]["payload"]["items"]), 1)
        self.assertNotIn("SECRET-RESULT-CANARY", marker_text)
        self.assertEqual(len(result["first"]["payload"]["events"]), 25)
        self.assertTrue(result["first"]["payload"]["has_more"])
        self.assertEqual(len(result["second"]["payload"]["events"]), 4)
        self.assertFalse(result["second"]["payload"]["has_more"])
        self.assertTrue(result["stable_historical_receipt"])
        self.assertEqual(result["signed_out_replay"]["status"], "denied")
        self.assertEqual(result["signed_out_replay"]["reason"], "not_authorized")
        self.assertEqual(result["snapshot_b"]["status"], "ok")
        self.assertEqual(result["cached_b_after_grant_replacement"], {
            "request_id": "b-snapshot", "status": "unavailable",
            "reason": "authority_unavailable", "payload": {}})
        self.assertEqual(result["snapshot_b_after_grant_replacement"]["status"], "ok")
        self.assertEqual(result["cached_b_after_classification"], {
            "request_id": "b-snapshot-after-grant", "status": "unavailable",
            "reason": "authority_unavailable", "payload": {}})
        self.assertEqual(result["b_old_cursor_after_classification"]["payload"]["reset_required"], True)
        self.assertEqual(result["snapshot_after_visibility"]["status"], "ok")
        self.assertEqual(result["cached_after_remove_reinsert"], {
            "request_id": "b-after-visibility", "status": "unavailable",
            "reason": "authority_unavailable", "payload": {}})
        self.assertEqual(result["stale_b_after_global_generation"]["status"], "denied")
        self.assertEqual(result["snapshot_c_after_fresh_login"]["status"], "ok")

    def test_v3_results_lost_release_ack_withholds_bytes_and_does_not_advance_cursor(self):
        private = self._prepare_login_key()
        entered = os.path.join(self.tmp.name, "results-release-entered")
        release = os.path.join(self.tmp.name, "results-release-ack")
        message_dir, marker, process = self._start_login_owner("v3-restore-results-lost-ack", grants=16,
            extra_env={"PHONE_REMOTE_AUTHORITY_RESULTS_LOST_ACK": "1",
                "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE": "service.commit",
                "PHONE_REMOTE_AUTHORITY_ENTERED_FILE": entered,
                "PHONE_REMOTE_AUTHORITY_RELEASE_FILE": release})
        try:
            challenge = self._wait_login_challenge(message_dir, "a", process)
            self._write_login_proof(message_dir, "a", challenge, private)
            self._wait_for_file(entered, process)
            process.terminate()
            process.communicate(timeout=10)
            self._wait_for_marker(marker)
            result = json.loads(pathlib.Path(marker).read_text(encoding="ascii"))
        finally:
            pathlib.Path(release).touch()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        self.assertEqual(result.get("response"), {"request_id": "lost-results-snapshot",
            "status": "unavailable", "reason": "authority_unavailable", "payload": {}}, result)
        self.assertEqual((result["cursor_count"], result["sequence"], result["journal_count"]), (0, 0, 0))
        self.assertTrue(result["host_fenced"])

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


class V4ProofDependencyTests(unittest.TestCase):
    """Exact dependency gates run independently of the native test executable."""

    def test_exact_v4_login_binding_and_proofless_login_rejection(self):
        from jarvis.bot.phone_remote_authority_channel import (
            NativeProtectedAnchor, NativeProtectedAnchorV3, NativeProtectedAnchorV4,
            run_store_operation,
        )
        from jarvis.bot.phone_remote_login import PhoneRemoteLogin, LoginClockGate
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        store = PhoneAdmissionStore(db, FakeProtectedAnchor("host-test"))
        clock = LoginClockGate(wall_ms=1000, monotonic_ms=1000)
        class V4Subclass(NativeProtectedAnchorV4):
            pass
        for anchor_type in (NativeProtectedAnchorV3, NativeProtectedAnchorV4):
            anchor = object.__new__(anchor_type)
            anchor._child_incarnation = str(uuid.uuid4())
            store.anchor = anchor
            login = PhoneRemoteLogin(store, anchor, clock=clock, service_id="svc.test")
            self.assertIs(login._anchor, anchor)
            before = db.total_changes
            # Rejected by the allowlist before entering any channel context.
            with self.assertRaisesRegex(StoreUnavailable, "store method does not match"):
                run_store_operation("session.login", store.login, anchor=anchor)
            self.assertEqual(db.total_changes, before)
        for anchor in (object.__new__(V4Subclass), object.__new__(NativeProtectedAnchor),
                       SimpleNamespace(_child_incarnation=str(uuid.uuid4()))):
            store.anchor = anchor
            with self.assertRaises(TypeError):
                PhoneRemoteLogin(store, anchor, clock=clock, service_id="svc.test")
        anchor = object.__new__(NativeProtectedAnchorV4)
        store.anchor = object.__new__(NativeProtectedAnchorV4)
        with self.assertRaises(TypeError):
            PhoneRemoteLogin(store, anchor, clock=clock, service_id="svc.test")


class V4DrainBoundaryTests(unittest.TestCase):
    """Deterministic local admission tests; process coverage is separate."""

    def fixture(self):
        from jarvis.bot.phone_remote_authority_channel import NativeProtectedAnchorV4
        import socket
        host = object.__new__(_AuthorityChildServiceHost)
        host._closed = host._fenced = host._busy = host._quiescing = False
        host._quiescence_deadline = host._quiescence_id = host._current = None
        host._lock = threading.Lock()
        host._queue = queue.Queue(maxsize=1)
        host._drained = threading.Event()
        anchor = object.__new__(NativeProtectedAnchorV4)
        anchor._closed = False
        anchor._socket, other = socket.socketpair()
        self.addCleanup(other.close)
        self.addCleanup(anchor._socket.close)
        host._anchor = anchor
        return host

    @staticmethod
    def settle_call(function, result):
        try:
            result.append(function())
        except BaseException as exc:
            result.append(exc)

    def queued(self, host, cancellation=None):
        result = []
        thread = threading.Thread(target=self.settle_call,
            args=(lambda: host._submit("read_status", _cancel_event=cancellation), result))
        thread.start()
        self.addCleanup(lambda: thread.join(2))
        deadline = time.monotonic() + 2
        while host._queue.empty() and time.monotonic() < deadline:
            time.sleep(.001)
        self.assertFalse(host._queue.empty())
        return thread, result

    def test_fast_worker_observes_cancellation_without_waiting_for_caller_poll(self):
        from unittest.mock import Mock
        for when in ("before-submit", "queued", "before-authorization", "after-authorization", "never"):
            with self.subTest(when=when):
                host = self.fixture()
                cancel = threading.Event()
                frames, effects, enqueued = [], [], []
                class FastWorkerQueue(queue.Queue):
                    def put_nowait(self, item):
                        if item is not None:
                            enqueued.append(item)
                            original_wait = item[3].event.wait
                            def completion_before_poll(timeout=None):
                                # The submitting thread cannot execute its
                                # cancellation poll until the worker settles.
                                if not original_wait(2):
                                    raise AssertionError("worker did not settle before caller polling")
                                return True
                            item[3].event.wait = completion_before_poll
                            super().put_nowait(item)
                            if when == "queued": cancel.set()
                        else:
                            super().put_nowait(item)
                host._queue = FastWorkerQueue(maxsize=1)
                service = Mock(_authority_failed=False)
                # This boundary-only fixture has no registered views or peers;
                # its tick below supplies the explicit authority observations.
                service.result_commands.bindings.return_value = ()
                service._peers = {}
                def fence(): service._authority_failed = True
                service._fence_authority.side_effect = fence
                def tick():
                    if when == "before-authorization": cancel.set()
                    host._observe_authority("acquire", "service.authorize")
                    frames.append("authorize")
                    host._observe_authority("released", "service.authorize")
                    owned = host._current
                    if when == "after-authorization": cancel.set()
                    host._observe_authority("acquire", "service.commit")
                    self.assertIs(host._current, owned)
                    self.assertTrue(owned.authorized)
                    self.assertTrue(host._busy)
                    effects.append("committed")
                    host._observe_authority("released", "service.commit")
                    frames.append("commit")
                    return "success"
                service.tick.side_effect = tick
                worker = threading.Thread(target=host._serve_owned,
                    args=(service, None, host._anchor, Mock()))
                worker.start()
                try:
                    if when == "before-submit": cancel.set()
                    if when == "never":
                        self.assertEqual(host._submit("tick", _cancel_event=cancel), "success")
                    else:
                        with self.assertRaises(StoreUnavailable): host._submit("tick", _cancel_event=cancel)
                    if when in {"before-submit", "queued", "before-authorization"}:
                        self.assertEqual(frames, [])
                        self.assertEqual(effects, [])
                    else:
                        self.assertEqual(frames, ["authorize", "commit"])
                        self.assertEqual(effects, ["committed"])
                    if when == "before-submit": self.assertEqual(enqueued, [])
                    if when in {"before-submit", "queued"}: service.tick.assert_not_called()
                    self.assertFalse(host._busy)
                    self.assertIsNone(host._current)
                    self.assertTrue(host._queue.empty())
                    self.assertEqual(host._queue.unfinished_tasks, 0)
                finally:
                    # An authorization-boundary failure already terminated the
                    # worker; other cases stop through its local queue sentinel.
                    if not host._closed: host._queue.put_nowait(None)
                    worker.join(2)
                    self.assertFalse(worker.is_alive())

    def test_queued_cancellation_removes_work_without_authority_frames(self):
        host = self.fixture()
        cancel = threading.Event()
        caller, result = self.queued(host, cancel)
        cancel.set(); caller.join(2)
        self.assertFalse(caller.is_alive())
        self.assertIsInstance(result[0], StoreUnavailable)
        self.assertTrue(host._queue.empty())
        self.assertEqual(host._queue.unfinished_tasks, 0)
        self.assertFalse(host._busy)
        self.assertFalse(host._anchor.is_closed)

    def test_quiesce_removes_queued_work_before_resource_close(self):
        from unittest.mock import Mock
        host = self.fixture()
        caller, result = self.queued(host)
        op = str(uuid.uuid4())
        drained = []
        drain = threading.Thread(target=self.settle_call, args=(lambda: host.quiesce(op), drained))
        drain.start()
        caller.join(2)
        self.assertIsInstance(result[0], StoreUnavailable)
        self.assertTrue(host._quiescing)
        with self.assertRaises(StoreUnavailable): host.read_status()
        service = Mock(_authority_failed=False)
        db = Mock()
        host._serve_owned(service, None, host._anchor, db)
        drain.join(2)
        self.assertEqual(drained, [{"operation_id": op, "drained": True}])
        service._fence_authority.assert_called_once_with()
        db.close.assert_called_once_with()
        self.assertEqual(host._queue.unfinished_tasks, 0)
        # No channel method or normal service method exists on these fixtures;
        # reaching an authority exchange would fail instead of passing silently.

    def test_cancelled_authorized_operation_retains_owner_until_commit_terminal(self):
        from jarvis.bot.phone_remote_service import _OwnedCompletion
        from unittest.mock import Mock
        host = self.fixture()
        cancel = threading.Event()
        caller, result = self.queued(host, cancel)
        item = host._queue.get_nowait()
        host._queue.task_done()
        host._current = item[3]
        host._observe_authority("released", "service.authorize")
        cancel.set(); caller.join(2)
        self.assertIsInstance(result[0], StoreUnavailable)
        self.assertIs(host._current, item[3])
        self.assertTrue(host._busy)
        op = str(uuid.uuid4()); drained = []
        drain = threading.Thread(target=self.settle_call, args=(lambda: host.quiesce(op), drained))
        drain.start()
        deadline = time.monotonic() + 2
        while not host._quiescing and time.monotonic() < deadline: time.sleep(.001)
        host._observe_authority("acquire", "service.commit")
        host._observe_authority("released", "service.commit")
        with self.assertRaises(StoreUnavailable): host._observe_authority("acquire", "service.authorize")
        with self.assertRaises(StoreUnavailable): host.read_status()
        self.assertEqual(drained, [])
        host._current = None  # this owned operation's terminal bookkeeping
        host._serve_owned(Mock(_authority_failed=False), None, host._anchor, Mock())
        drain.join(2)
        self.assertEqual(drained, [{"operation_id": op, "drained": True}])
        self.assertEqual(len(result), 1)  # no success replaces cancelled outcome

    def test_fixed_deadline_settles_uncertain_caller_and_blocks_later_grants(self):
        from jarvis.bot.phone_remote_service import _OwnedCompletion
        from unittest.mock import patch
        host = self.fixture()
        current = _OwnedCompletion(threading.Event(), [])
        current.authorized = True
        host._current = current
        class ClockEvent:
            def __init__(self): self.waits = []
            def wait(self, seconds): self.waits.append(seconds); return False
        host._drained = ClockEvent()
        op = str(uuid.uuid4())
        with patch("jarvis.bot.phone_remote_service.time.monotonic", side_effect=[10, 12, 15]):
            with self.assertRaises(StoreUnavailable): host.quiesce(op)
            with self.assertRaises(StoreUnavailable): host.quiesce(op)
        self.assertEqual(host._quiescence_deadline, 15)
        self.assertEqual(host._drained.waits, [3])
        self.assertTrue(current.event.is_set())
        self.assertIsInstance(current.result_box[0], StoreUnavailable)
        self.assertTrue(host._anchor.is_closed)
        with self.assertRaises(StoreUnavailable): host._observe_authority("acquire", "service.commit")
        with self.assertRaises(StoreUnavailable): host.read_status()
        with self.assertRaises(StoreUnavailable): host.quiesce(str(uuid.uuid4()))

    def test_resource_close_failure_cannot_report_drained(self):
        from unittest.mock import Mock
        host = self.fixture(); op = str(uuid.uuid4()); result = []
        drain = threading.Thread(target=self.settle_call, args=(lambda: host.quiesce(op), result))
        drain.start()
        deadline = time.monotonic() + 2
        while host._queue.empty() and time.monotonic() < deadline: time.sleep(.001)
        db = Mock(); db.close.side_effect = OSError("synthetic close failure")
        host._serve_owned(Mock(_authority_failed=False), None, host._anchor, db)
        drain.join(2)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], StoreUnavailable)
        self.assertTrue(host._fenced)

@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'), 'requires offline native owner')
class PhoneCardAuthorityProcessTests(unittest.TestCase):
    def bridge(self, **kwargs):
        bridge=_CardProcessBridge(**kwargs);self.addCleanup(bridge.close);return bridge

    def call(self, bridge, operation, payload, request_id=None, **kwargs):
        request=dict(kind='mortimer.phone-remote.v1',protocol_version=1,
            request_id=request_id or str(uuid.uuid4()),operation=operation,payload=payload)
        return json.loads(bridge.exchange(json.dumps(request).encode(),**kwargs))

    def view(self, bridge):
        snapshot=self.call(bridge,'results.snapshot',{})
        self.assertEqual(snapshot['status'],'ok')
        view=self.call(bridge,'results.view',{k:snapshot['payload'][k] for k in ('generation','collection_epoch')})
        self.assertEqual(view['status'],'ok');return view['payload']

    @staticmethod
    def target(view):
        return {**{k:view[k] for k in ('generation','collection_epoch','view_id','view_revision')},
            'result_id':view['cards'][0]['result_id'],'result_revision':view['cards'][0]['result_revision']}

    def test_v4_actions_repeated_receipts_and_other_card_view_first(self):
        bridge=self.bridge();view=self.view(bridge);target=self.target(view)
        first=self.call(bridge,'results.pin',target,'repeat')
        self.assertEqual(first['status'],'ok');self.assertTrue(first['payload']['cards'][0]['pinned'])
        replay=self.call(bridge,'results.pin',target,'repeat',control='edit-other')
        self.assertEqual(replay,first)
        conflict=self.call(bridge,'results.close',self.target(first['payload']))
        self.assertEqual(conflict['reason'],'request_conflict')
        view=self.view(bridge)
        for operation in ('results.select','results.unpin','results.close','results.reopen'):
            response=self.call(bridge,operation,self.target(view));self.assertEqual(response['status'],'ok');view=response['payload']
        self.assertTrue(view['cards'][0]['open']);self.assertEqual(view['selected_result_id'],view['cards'][0]['result_id'])
        self.assertEqual(self.call(bridge,'results.pin',target,'repeat'),first)
        denied=self.call(bridge,'results.pin',target,'repeat',control='revoke-capability')
        self.assertEqual(denied['reason'],'not_authorized');self.assertEqual(denied['payload'],{})

    def test_v4_readonly_protected_receipts_and_forged_fields(self):
        bridge=self.bridge(scopes=('read',));view=self.view(bridge)
        denied=self.call(bridge,'results.pin',self.target(view));self.assertEqual(denied['reason'],'not_authorized')
        forged=self.call(bridge,'results.pin',{**self.target(view),'owner_id':'other'})
        self.assertEqual(forged['reason'],'malformed_request')
        other=self.bridge();view=self.view(other);target=self.target(view)
        receipt=self.call(other,'results.select',target,'private')
        self.assertEqual(receipt['status'],'ok')
        hidden=self.call(other,'results.select',target,'private',control='protect-other')
        self.assertEqual(hidden['reason'],'authority_unavailable');self.assertEqual(hidden['payload'],{})
        self.assertNotIn('PROTECTED-CANARY',json.dumps(hidden))
        self.assertEqual(len(self.view(other)['cards']),1)

    def test_v4_lost_commit_release_ack_retains_effect_but_never_promotes_retry(self):
        bridge=self.bridge();view=self.view(bridge);target=self.target(view)
        first=self.call(bridge,'results.pin',target,'uncertain',control='lose-ack')
        self.assertEqual(first['reason'],'authority_unavailable');self.assertEqual(first['payload'],{})
        observed=json.loads((bridge.directory/f'{bridge.sequence}.observation').read_bytes())
        self.assertTrue(observed['fenced']);self.assertIn('uncertain',observed['states'])
        self.assertTrue(observed['views'][0]['cards'][0]['pinned'])
        self.assertEqual(observed['views'][0]['view_revision'],1)
        self.assertEqual((observed['peers'],observed['leases']),(0,0))
        self.assertEqual(self.call(bridge,'results.pin',target,'uncertain'),first)
        later=json.loads((bridge.directory/f'{bridge.sequence}.observation').read_bytes())
        self.assertEqual(later,observed)

class PhoneCardOwnedWorkerTests(unittest.TestCase):
    """Actual card transition through the owned worker; local injected authority observations."""
    def test_card_fast_worker_cancellation_at_each_admission_boundary(self):
        from unittest.mock import Mock, patch
        from contextlib import contextmanager
        from tests.unit.test_phone_remote_result_commands import CardFixture, wire
        for when in ('before-submit','queued','before-authorization','after-authorization','never'):
            with self.subTest(when=when):
                fixture=CardFixture();self.addCleanup(fixture.close);fixture.sync()
                host=V4DrainBoundaryTests.fixture(self);cancel=threading.Event();frames=[];effects=[]
                class FastQueue(queue.Queue):
                    def put_nowait(inner,item):
                        if item is not None:
                            wait=item[3].event.wait
                            def before_poll(timeout=None):
                                if not wait(2):raise AssertionError('card worker did not settle')
                                return True
                            item[3].event.wait=before_poll
                            super().put_nowait(item)
                            if when=='queued':cancel.set()
                        else:super().put_nowait(item)
                host._queue=FastQueue(maxsize=1)
                binding=fixture.service._current_binding;commit=fixture.service._service_commit;apply=fixture.registry.apply
                def authorize(**kwargs):
                    if when=='before-authorization':cancel.set()
                    host._observe_authority('acquire','service.authorize');frames.append('authorize')
                    value=binding(**kwargs);host._observe_authority('released','service.authorize')
                    if when=='after-authorization':cancel.set()
                    return value
                @contextmanager
                def committed():
                    host._observe_authority('acquire','service.commit')
                    with commit():yield
                    host._observe_authority('released','service.commit');frames.append('commit')
                def applied(*args):
                    value=apply(*args);effects.append('pin');return value
                with patch.object(fixture.service,'_current_binding',authorize),patch.object(fixture.service,'_service_commit',committed),patch.object(fixture.registry,'apply',applied):
                    worker=threading.Thread(target=host._serve_owned,args=(fixture.service,fixture.store,host._anchor,Mock()))
                    worker.start()
                    try:
                        if when=='before-submit':cancel.set()
                        raw=wire('results.pin',fixture.target(),'cancel-card')
                        if when=='never':self.assertEqual(host._submit('handle',raw,fixture.context,_cancel_event=cancel)['status'],'ok')
                        else:
                            with self.assertRaises(StoreUnavailable):host._submit('handle',raw,fixture.context,_cancel_event=cancel)
                        expected=when in ('after-authorization','never')
                        self.assertEqual(effects,['pin'] if expected else [])
                        self.assertEqual(frames,['authorize','commit'] if expected else [])
                        saved=next(iter(fixture.registry._views.values())).payload
                        self.assertEqual(saved['cards'][0]['pinned'],expected)
                        self.assertEqual(saved['view_revision'],1 if expected else 0)
                        self.assertFalse(host._busy);self.assertIsNone(host._current)
                    finally:
                        if not host._closed:host._queue.put_nowait(None)
                        worker.join(2);self.assertFalse(worker.is_alive())

    def test_quiesce_waits_for_authorized_card_effect_and_terminal_receipt(self):
        from unittest.mock import Mock, patch
        from contextlib import contextmanager
        from tests.unit.test_phone_remote_result_commands import CardFixture, wire
        fixture=CardFixture();self.addCleanup(fixture.close);fixture.sync()
        host=V4DrainBoundaryTests.fixture(self)
        arrived=threading.Event();release=threading.Event();quiescing=threading.Event()
        original=fixture.service._current_binding;apply=fixture.registry.apply
        def authorized(**kwargs):
            host._observe_authority('acquire','service.authorize')
            value=original(**kwargs);host._observe_authority('released','service.authorize');return value
        def blocked(*args):
            arrived.set()
            if not release.wait(2):raise AssertionError('card effect barrier timed out')
            return apply(*args)
        result=[];drained=[]
        with patch.object(fixture.service,'_current_binding',authorized),patch.object(fixture.registry,'apply',blocked):
            worker=threading.Thread(target=host._serve_owned,args=(fixture.service,fixture.store,host._anchor,Mock()));worker.start()
            caller=threading.Thread(target=V4DrainBoundaryTests.settle_call,args=(lambda:host.handle(wire('results.pin',fixture.target(),'drained'),fixture.context),result));caller.start()
            self.assertTrue(arrived.wait(2))
            operation=str(uuid.uuid4())
            original_event=host._drained
            class DrainEvent:
                def wait(inner,timeout=None):quiescing.set();return original_event.wait(timeout)
                def set(inner):original_event.set()
            host._drained=DrainEvent()
            drain=threading.Thread(target=V4DrainBoundaryTests.settle_call,args=(lambda:host.quiesce(operation),drained));drain.start()
            self.assertTrue(quiescing.wait(2));self.assertEqual(drained,[])
            with self.assertRaises(StoreUnavailable):host.handle(wire('results.close',fixture.target(),'new'),fixture.context)
            release.set();caller.join(2);drain.join(2);worker.join(2)
            self.assertFalse(worker.is_alive());self.assertEqual(drained,[{'operation_id':operation,'drained':True}])
            self.assertEqual(result[0]['status'],'ok')
            saved=next(iter(fixture.registry._views.values())).payload
            self.assertTrue(saved['cards'][0]['pinned']);self.assertTrue(saved['cards'][0]['open'])
            entry=next(e for (binding,rid),e in fixture.service._ledger.items() if rid=='drained')
            self.assertEqual(entry['state'],'done')


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'), 'requires offline native owner')
class PhoneCardReviewProcessTests(unittest.TestCase):
    bridge=PhoneCardAuthorityProcessTests.bridge
    call=PhoneCardAuthorityProcessTests.call
    view=PhoneCardAuthorityProcessTests.view
    target=staticmethod(PhoneCardAuthorityProcessTests.target)

    def test_review_periodic_poll_notify_and_feature_toggle_keep_native_authority_healthy(self):
        bridge=self.bridge();view=self.view(bridge)
        for control in ('tick','notify','feature-off','feature-on'):
            response=self.call(bridge,'results.pin',self.target(view),control=control)
            observed=json.loads((bridge.directory/f'{bridge.sequence}.observation').read_bytes())
            self.assertFalse(observed['fenced'],control)
            self.assertEqual(response['reason'],'feature_off' if control=='feature-off' else 'none')
            if response['status']=='ok':view=response['payload']
        self.assertEqual(self.call(bridge,'results.unpin',self.target(view))['status'],'ok')

    def test_review_native_ack_reentry_fences_before_first_or_historical_publication(self):
        for historical in (False,True):
            with self.subTest(historical=historical):
                bridge=self.bridge();view=self.view(bridge);target=self.target(view)
                if historical:self.assertEqual(self.call(bridge,'results.pin',target,'outer')['status'],'ok')
                result=self.call(bridge,'results.pin',target,'outer',control='ack-reentry')
                self.assertEqual(result['reason'],'authority_unavailable');self.assertEqual(result['payload'],{})
                observed=json.loads((bridge.directory/f'{bridge.sequence}.observation').read_bytes())
                self.assertTrue(observed['fenced']);self.assertIn('uncertain',observed['states'])
                self.assertTrue(observed['views'][0]['cards'][0]['pinned'])
                self.assertEqual(self.call(bridge,'results.pin',target,'outer'),result)

    def test_review_native_poll_queued_cancellation_and_authorized_drain(self):
        bridge=self.bridge();view=self.view(bridge)
        pinned=self.call(bridge,'results.pin',self.target(view),control='poll-queued-cancel')
        self.assertEqual(pinned['status'],'ok')
        result=self.call(bridge,'results.unpin',self.target(pinned['payload']),control='poll-drain')
        self.assertEqual(result['reason'],'authority_unavailable')
        observed=json.loads((bridge.directory/f'{bridge.sequence}.observation').read_bytes())
        self.assertTrue(observed['views'][0]['cards'][0]['pinned'])
        self.assertTrue(json.loads((bridge.directory/'poll-drained').read_bytes())[0]['drained'])

    def test_review_native_combined_publication_denial_fences_only_terminal_failure(self):
        for control in ('publication-change','publication-reentry-change','publication-reentry-history'):
            with self.subTest(control=control):
                bridge=self.bridge();view=self.view(bridge);target=self.target(view)
                terminal=control!='publication-change'
                if control.endswith('history'):
                    self.assertEqual(self.call(bridge,'results.pin',target,'combined')['status'],'ok')
                result=self.call(bridge,'results.pin',target,'combined',control=control)
                self.assertEqual(result['reason'],'authority_unavailable');self.assertEqual(result['payload'],{})
                observed=json.loads((bridge.directory/f'{bridge.sequence}.observation').read_bytes())
                self.assertEqual(observed['fenced'],terminal)
                self.assertEqual(observed['states'][-1],'uncertain' if terminal else 'withheld')
                status=self.call(bridge,'session.status',{})
                self.assertEqual(status['status'],'unavailable' if terminal else 'ok')
                self.assertEqual(self.call(bridge,'results.pin',target,'combined'),result)


def _connection_fixture_host(database, device="d-channel", grant="g-channel"):
    from jarvis.bot.phone_remote_connection import create_offline_connection_host, ConnectionClock
    from jarvis.bot.phone_remote_results import (PhoneRemoteResults, PhoneResultCollectionGrantV1,
        SyntheticResultRecord, SyntheticResultsSource)
    from jarvis.bot.phone_remote_result_commands import ACTIONS
    source=SyntheticResultsSource([SyntheticResultRecord(str(uuid.UUID(int=1)),1,
        'Connection synthetic card','Disposable body',1_800_000_000_000)])
    results=PhoneRemoteResults(PhoneResultCollectionGrantV1('alice',device,grant,
        str(uuid.UUID(int=99)),(str(uuid.UUID(int=1)),)),source)
    clock=ConnectionClock()
    host=create_offline_connection_host(str(database),enabled=True,clock=clock,
        results=results,actions=tuple(sorted(ACTIONS)))
    return host,clock,source


def _proof_connection_child_case(database, case):
    """Invoked by a fixed same-PID fixture launcher, never a phone request."""
    import asyncio
    from tests.unit.test_phone_remote_connection import InMemoryProofClient, wire
    from jarvis.bot.phone_remote_connection import ConnectionFailure, ConnectionReply
    root=pathlib.Path(database).parent
    private=serialization.load_pem_private_key((root/'fixture-key.pem').read_bytes(),None)
    host,clock,source=_connection_fixture_host(database)
    report={"case":case,"pid":os.getpid()}
    if case=='fixture-stall':threading.Event().wait(10)
    async def run():
        if case.startswith('review-'):
            await _connection_review_case(case,host,clock,private,report)
            report['remaining_records']=len(host._connections.records)
            assert not host._connections.records
            return
        if case.startswith(('handshake-', 'gap-')):
            await _connection_handshake_case(case, host, clock, private, report)
            report['remaining_records']=len(host._connections.records)
            assert not host._connections.records
            return
        a=InMemoryProofClient(host)
        await a.login(private)
        assert len(host._connections.records)==1
        record=next(iter(host._connections.records.values()))
        report['binding']={k:getattr(record.binding,k) for k in ('owner_id','device_id','grant_id','login_incarnation','process_epoch')}
        status=await a.exchange(wire());assert status['status']=='ok',status
        if case=='happy':
            # A stale callback queued before activation cannot close the active lease.
            assert not host._connections.expire_handshake(record.lease,record.token,object())
            clock.set_time(wall_ms=1_800_000_070_000,monotonic_ms=71000)
            assert (await a.exchange(wire(rid='after-60s')))['status']=='ok'
            snapshot=await a.exchange(wire('results.snapshot',{},'snapshot'));assert snapshot['status']=='ok',snapshot
            view=await a.exchange(wire('results.view',{k:snapshot['payload'][k] for k in ('generation','collection_epoch')},'view'))
            assert view['status']=='ok',view
            original=None
            for index,op in enumerate(('results.pin','results.unpin','results.select','results.close','results.reopen')):
                target=PhoneCardAuthorityProcessTests.target(view['payload'])
                request=wire(op,target,'action-'+str(index))
                result=await a.exchange(request);assert result['status']=='ok',(op,result)
                if index==0:
                    original=result
                    assert await a.exchange(request)==original
                view=result
            forged=await a.exchange(wire('results.pin',{**target,'owner_id':'mallory'},'forged'))
            assert forged['reason']=='malformed_request'
            denied=await a.exchange(wire('voice.offer',{'sdp':'v=0'},'no-ticket'))
            assert denied['status']!='ok'
            report['actions']=5;report['after_60s']=True
        elif case in {'expired','revoked','feature-off','isolation'}:
            b=InMemoryProofClient(host);await b.login(private)
            if case=='expired':
                clock.set_time(wall_ms=1,monotonic_ms=record.monotonic_deadline_ms)
            elif case=='feature-off':await asyncio.to_thread(host.set_enabled,False)
            else:
                await asyncio.to_thread(host.signout,identity=record.context.identity,
                    session_id=record.binding.session_id,owner_id=record.binding.owner_id)
            denied=await a.exchange(wire(rid='after-change'))
            assert denied.get('status')!='ok',denied
            if case in {'revoked','isolation'}:
                survivor=await b.exchange(wire(rid='survivor'));assert survivor['status']=='ok',survivor
                assert not host._fenced
                report['survivor']=True
            await b.close()
        elif case.startswith(('race-', 'transport-', 'receipt-', 'binding-')):
            await _connection_live_race(case, a, record, host, clock, source, private, report)
        elif case=='forged-context':
            from dataclasses import replace
            copied=replace(record.context)
            denied=await asyncio.to_thread(host.handle,wire(rid='forged-context'),copied)
            assert denied['reason']=='not_authorized' and not host._fenced,denied
            report['foreign_handle']=host.claim_connection_reply(record.lease,object(),ConnectionReply('bad',True)).reason
            assert (await a.exchange(wire(rid='still-valid')))['status']=='ok'
        else:
            raise AssertionError('unknown connection case')
        await a.close()
        report['remaining_records']=len(host._connections.records)
        assert not host._connections.records
    try:
        asyncio.run(run())
        report['ok']=True
    finally:
        host._queue.put_nowait(None);host._thread.join(5)
        assert not host._thread.is_alive(),'owned worker did not exit'
    return report


def _connection_launcher(root):
    """Static controlled executable, preserving native-owned PID and FDs."""
    launcher=root/'connection-python'
    source=(f'#!{sys.executable}\n'
        'import os,sys,json,pathlib,traceback\n'
        'from tests.unit import test_phone_remote_authority_service as driver\n'
        f'root=pathlib.Path({str(root)!r})\n'
        'try:\n'
        ' args=sys.argv[1:]\n'
        ' os.fstat(3);os.fstat(4)\n'
        ' if "PHONE_REMOTE_AUTHORITY_RECOVERY_CONFIG" in os.environ:\n'
        '  assert args==["-m","tests.unit.test_phone_remote_recovery","--recovery-child",str(root/"jarvis.db")]\n'
        '  config=json.loads(os.environ["PHONE_REMOTE_AUTHORITY_RECOVERY_CONFIG"])\n'
        '  if config.get("source_available") is True:os.fstat(5)\n'
        '  if config.get("mode")=="normal" and config.get("exercise_drain") is True:\n'
        '   driver._connection_recovery_normal(str(root/"jarvis.db"),config,json.loads((root/"connection-case.json").read_text())["case"])\n'
        '  else:\n'
        '   from tests.unit.test_phone_remote_recovery import _recovery_child_entrypoint\n'
        '   _recovery_child_entrypoint(str(root/"jarvis.db"))\n'
        ' else:\n'
        '  assert args==["-m","tests.unit.test_phone_remote_authority_channel","--authority-child",str(root/"authority.sqlite"),"v4-connection"]\n'
        '  (root/"connection-child-pid.json").write_text(json.dumps({"pid":os.getpid(),"parent":os.getppid()}))\n'
        '  result=driver._proof_connection_child_case(str(root/"authority.sqlite"),json.loads((root/"connection-case.json").read_text())["case"])\n'
        '  (root/"connection-result.json").write_text(json.dumps(result))\n'
        'except BaseException:\n'
        ' (root/"connection-failure").write_text(traceback.format_exc());sys.exit(78)\n')
    launcher.write_text(source);launcher.chmod(0o700)
    return launcher,hashlib.sha256(source.encode()).hexdigest()


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ProofConnectionProcessTests(unittest.TestCase):
    def run_case(self,case,*,_timeout=15):
        with tempfile.TemporaryDirectory(prefix='proof-connection-') as directory:
            root=pathlib.Path(directory);root.chmod(0o700)
            private=ec.generate_private_key(ec.SECP256R1())
            public=private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
            key=root/'fixture-key.pem';key.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));key.chmod(0o600)
            db=sqlite3.connect(root/'authority.sqlite',isolation_level=None)
            anchor=FakeProtectedAnchor('host-test');store=PhoneAdmissionStore(db,anchor)
            identity=ClientIdentity(name='connection-fixture',user_id='alice')
            store.add_device(identity=identity,device_id='d-channel',owner_id='alice',public_key=public,key_algorithm='p256-sha256-sec1-v1')
            store.add_grant(identity=identity,grant_id='g-channel',device_id='d-channel',owner_id='alice',scopes=['read','action'])
            state=anchor.state;db.close()
            anchor_path=root/'anchor.json';anchor_path.write_text(json.dumps(dict(anchor_version=1,host_id='host-test',
                host_generation=state.host_generation,transition_id=None,transition_state='stable',login_counter=0)));anchor_path.chmod(0o600)
            lock=root/'owner.lock';lock.touch(mode=0o600)
            (root/'connection-case.json').write_text(json.dumps({'case':case}))
            launcher,script_hash=_connection_launcher(root)
            process=subprocess.Popen([os.environ['PHONE_REMOTE_AUTHORITY_OWNER_BIN'],'--test-owner',str(lock),str(launcher),
                str(root/'authority.sqlite'),str(pathlib.Path.cwd()),'v4-connection','65','0',str(state.host_generation),'0',str(anchor_path)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                out,err=process.communicate(timeout=_timeout)
                self.assertFalse((root/'connection-failure').exists(),
                    (root/'connection-failure').read_text() if (root/'connection-failure').exists() else '')
                self.assertTrue((root/'connection-result.json').exists(),(process.returncode,err.decode()))
                result=json.loads((root/'connection-result.json').read_text());self.assertTrue(result['ok'])
                self.assertEqual(result['remaining_records'],0)
                with self.assertRaises(ProcessLookupError):os.kill(result['pid'],0)
                self.assertEqual(hashlib.sha256(launcher.read_bytes()).hexdigest(),script_hash)
                return result
            finally:
                # Normal test-owner has no recovery reap promise. On a failed
                # test, stop its exact recorded child first so the owner can
                # reap it; never leave a deadlocked grandchild holding fd4.
                pid_file=root/'connection-child-pid.json'
                child=json.loads(pid_file.read_text()) if pid_file.exists() else None
                if child is not None:
                    self.assertEqual(child['parent'],process.pid)
                    try:os.kill(child['pid'],15)
                    except ProcessLookupError:pass
                try:process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    if child is not None:
                        try:os.kill(child['pid'],9)
                        except ProcessLookupError:pass
                    process.terminate();process.communicate(timeout=3)
                if child is not None:
                    import time
                    until=time.monotonic()+2
                    while True:
                        try:os.kill(child['pid'],0)
                        except ProcessLookupError:break
                        self.assertLess(time.monotonic(),until,'owned fixture child survived teardown')
                        time.sleep(.005)

    def test_timeout_teardown_reaps_only_its_recorded_native_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):self.run_case('fixture-stall',_timeout=1)

    def test_actual_proof_asgi_five_actions_history_and_post_handshake_lifetime(self):
        self.assertEqual(self.run_case('happy')['actions'],5)

    def test_actual_proof_context_expiry_revocation_feature_and_isolation(self):
        for case in ('expired','revoked','feature-off','isolation','forged-context'):
            with self.subTest(case=case):self.run_case(case)


def _connection_recovery_normal(database, config, case):
    """The actual native-owned normal PID; only fixed disposable test controls."""
    import asyncio, time, signal
    from tests.unit.test_phone_remote_connection import InMemoryProofClient, wire
    from jarvis.bot.phone_admission_store import StoreUnavailable
    assert config['mode']=='normal' and config['exercise_drain'] is True
    assert case in {'timely','queued','activation','stall','stall-ignore-term','lost-commit','lost-release','lost-shutdown','child-failure'}
    os.fstat(3);os.fstat(4)
    root=pathlib.Path(database).parent;path=pathlib.Path(config['quiescence_path'])
    private=serialization.load_pem_private_key((root/'fixture-key.pem').read_bytes(),None)
    if case=='stall-ignore-term':signal.signal(signal.SIGTERM,signal.SIG_IGN)
    def record(suffix,value):
        target=pathlib.Path(str(path)+suffix);tmp=pathlib.Path(str(target)+'.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            f.write(json.dumps(value,sort_keys=True,separators=(',',':')));f.flush();os.fsync(f.fileno())
        os.replace(tmp,target)
    record('.route',dict(route='proof-asgi-card',pid=os.getpid(),case=case,fd3=True,fd4=True))
    host,clock,source=_connection_fixture_host(database,'current-device','current-grant')
    arrived,release=threading.Event(),threading.Event()
    outcome=[];clients=[]
    original_activate=host.activate_connection
    if case=='activation':
        def activation(*args):
            arrived.set();assert release.wait(7)
            return original_activate(*args)
        host.activate_connection=activation
    class Stall:
        def wait(self,timeout):return release.wait(8)
    async def scenario():
        client=InMemoryProofClient(host);clients.append(client)
        if case=='activation':
            await client.start();proof=await client.prove(await client.challenge('current-device','current-grant'),private)
            assert proof.get('status')!='ok';await client.close();return
        await client.login(private,'current-device','current-grant')
        assert (await client.exchange(wire()))['status']=='ok'
        snap=await client.exchange(wire('results.snapshot',{},'snapshot'))
        view=await client.exchange(wire('results.view',{k:snap['payload'][k] for k in ('generation','collection_epoch')},'view'))
        assert view['status']=='ok'
        target=PhoneCardAuthorityProcessTests.target(view['payload'])
        if case=='queued':
            # Pause dequeue, after enqueue, without acquiring native authority.
            original_get=host._queue.get
            def paused_get(*args,**kwargs):
                item=original_get(*args,**kwargs)
                if item is not None and item[0]=='handle_connection':
                    arrived.set();assert release.wait(7)
                return item
            # Worker is already waiting in original_get: interrupt its wait with
            # one local no-effect method, so its next dequeue uses this wrapper.
            host._queue.get=paused_get
            await asyncio.to_thread(host.set_enabled,True)
        else:
            host._connections.service.owner_available.pause_before_commit('phone-authority-child',arrived,
                Stall() if case.startswith('stall') else release)
        answer=await client.exchange(wire('results.pin',target,'drain-pin'))
        outcome.append(answer)
        await client.close()
    errors=[]
    def run():
        try:asyncio.run(scenario())
        except BaseException as e:errors.append(repr(e))
    caller=threading.Thread(target=run);caller.start()
    assert arrived.wait(5),'new path did not reach controlled boundary'
    with host._lock:
        authorized=host._current is not None and host._current.authorized
    assert authorized == (case not in {'queued','activation'}),(case,authorized)
    record('.activity',dict(authorized=authorized,phase=case,pid=os.getpid()))
    deadline=time.monotonic()+7;request_path=pathlib.Path(str(path)+'.request')
    while True:
        try:request=json.loads(request_path.read_bytes());break
        except (FileNotFoundError,ValueError):
            assert time.monotonic()<deadline;time.sleep(.001)
    result=[]
    def drain():
        try:result.append(host.quiesce(request['operation_id'],_owner_deadline=float(request['deadline'])))
        except BaseException as e:result.append(e)
    waiter=threading.Thread(target=drain);waiter.start()
    while not host._quiescing and waiter.is_alive():time.sleep(.001)
    initial_deadline=host._quiescence_deadline
    # The second caller must observe the same frozen deadline.
    repeated=[]
    def repeat():
        try:repeated.append(host.quiesce(request['operation_id'],_owner_deadline=float(request['deadline'])+10))
        except BaseException as e:repeated.append(e)
    second=threading.Thread(target=repeat);second.start()
    assert host._quiescence_deadline==initial_deadline
    if case=='child-failure':os._exit(77)
    if not case.startswith('stall'):release.set()
    waiter.join(6);second.join(1)
    if waiter.is_alive() or not result or isinstance(result[0],BaseException):
        record('.failed',dict(settled=True,pid=os.getpid(),errors=errors))
        host._anchor.close()
        if case=='stall-ignore-term':
            while True:time.sleep(1)
        return
    caller.join(1)
    assert not caller.is_alive() and not errors,errors
    assert repeated and not isinstance(repeated[0],BaseException),repeated
    views=tuple(host._connections.service.result_commands._views.values())
    pinned=bool(views and views[0].payload['cards'][0]['pinned'])
    assert pinned == (case not in {'queued','activation'}),(case,pinned,outcome)
    record('.outcome',dict(terminal=True,pinned=pinned,pid=os.getpid(),deadline_unchanged=host._quiescence_deadline==initial_deadline))
    record('.terminal',dict(operation_id=request['operation_id'],terminal=True))
    if case=='lost-shutdown':
        assert host._anchor._receive()['kind']=='owner.shutdown';os._exit(77)
    record('.shutdown-start',dict(closed=host._closed,fenced=host._fenced,anchor_closed=host._anchor.is_closed))
    host.shutdown()
    record('.shutdown-done',dict(done=True))


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ProofConnectionRecoveryProcessTests(unittest.TestCase):
    def run_recovery(self,case):
        import time,fcntl
        from tests.unit.test_phone_remote_recovery import RecoveryActualProcessTests
        with tempfile.TemporaryDirectory(prefix='proof-recovery-') as directory:
            root=pathlib.Path(directory);root.chmod(0o700)
            RecoveryActualProcessTests().fixture(root)
            private=ec.generate_private_key(ec.SECP256R1())
            key=root/'fixture-key.pem';key.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));key.chmod(0o600)
            public=private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
            with sqlite3.connect(root/'jarvis.db') as db:
                db.execute('UPDATE phone_remote_devices SET public_key=?',(public,))
                db.execute('UPDATE phone_remote_grants SET scopes_json=?',('["action","read","voice"]',))
            (root/'connection-case.json').write_text(json.dumps({'case':case}))
            launcher,script_hash=_connection_launcher(root)
            env=os.environ.copy();env.update(PHONE_REMOTE_AUTHORITY_READY_FILE=str(root/'ready'),
                PHONE_REMOTE_AUTHORITY_RECOVERY_BEGIN='0',PHONE_REMOTE_AUTHORITY_FAILPOINT='r324-drain-'+case)
            process=subprocess.Popen([env['PHONE_REMOTE_AUTHORITY_OWNER_BIN'],'--test-owner',str(root/'owner.lock'),str(launcher),
                str(root/'jarvis.db'),str(pathlib.Path.cwd()),'v4-recovery','0','0','1','7',str(root/'anchor.json')],env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            success=case in {'timely','queued','activation'}
            started=time.monotonic()
            try:
                until=started+12
                while not (root/('ready' if success else 'blocked')).exists() and process.poll() is None and time.monotonic()<until:time.sleep(.005)
                self.assertFalse((root/'connection-failure').exists(),(root/'connection-failure').read_text() if (root/'connection-failure').exists() else '')
                self.assertTrue((root/('ready' if success else 'blocked')).exists(),(case,process.poll(),[(p.name,p.read_text()) for p in root.iterdir() if p.name=='blocked' or p.name.startswith('reaped-') or p.suffix in {'.failed','.outcome','.shutdown-start','.shutdown-done'}]))
                routes=[json.loads(p.read_bytes()) for p in root.glob('quiesce-*.route')]
                self.assertEqual(len(routes),1);route=routes[0]
                self.assertEqual(route['route'],'proof-asgi-card')
                pids=[json.loads(p.read_bytes())['pid'] for p in root.glob('quiesce-*.pid')]
                self.assertIn(route['pid'],pids)
                reaped=[json.loads(p.read_bytes()) for p in root.glob('reaped-*.json')]
                self.assertTrue(any(r['pid']==route['pid'] and r['confirmed'] for r in reaped),reaped)
                with self.assertRaises(ProcessLookupError):os.kill(route['pid'],0)
                self.assertEqual(hashlib.sha256(launcher.read_bytes()).hexdigest(),script_hash)
                if success:
                    _,err=process.communicate(timeout=5);self.assertEqual(process.returncode,0,err.decode())
                    result=json.loads(next(root.glob('quiesce-*.outcome')).read_bytes())
                    self.assertEqual(result['pinned'],case=='timely');self.assertTrue(result['deadline_unchanged'])
                else:
                    self.assertIsNone(process.poll());self.assertFalse((root/'ready').exists());self.assertFalse((root/'.phone-restore').exists())
                    with sqlite3.connect(root/'jarvis.db') as db:self.assertEqual(db.execute('SELECT body FROM notes').fetchall(),[('current',)])
                    with (root/'owner.lock').open('rb') as lock:
                        with self.assertRaises(BlockingIOError):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    if case!='lost-shutdown':self.assertFalse(list(root.glob('quiesce-*.terminal')))
                    self.assertLess(time.monotonic()-started,9)
            finally:
                if process.poll() is None:process.terminate();process.communicate(timeout=5)

    def test_new_proof_path_timely_card_and_rejected_unfrozen_work(self):
        for case in ('timely','queued','activation'):
            with self.subTest(case=case):self.run_recovery(case)

    def test_new_proof_path_uncertain_drain_never_restores_and_reaps_exact_pid(self):
        for case in ('stall','stall-ignore-term','lost-commit','lost-release','lost-shutdown','child-failure'):
            with self.subTest(case=case):self.run_recovery(case)


async def _connection_live_race(case, a, record, host, clock, source, private, report):
    import asyncio,time
    from tests.unit.test_phone_remote_connection import InMemoryProofClient,wire
    from jarvis.bot.phone_remote_connection import ConnectionFailure,ConnectionReply
    service=host._connections.service
    snap=await a.exchange(wire('results.snapshot',{},'snapshot'))
    view=await a.exchange(wire('results.view',{k:snap['payload'][k] for k in ('generation','collection_epoch')},'view'))
    assert view['status']=='ok',view
    target=PhoneCardAuthorityProcessTests.target(view['payload']);request=wire('results.pin',target,'race-pin')
    if case.startswith('race-expiry-'):
        # B's later independent admission remains live when A expires.
        clock.set_time(wall_ms=1_800_000_000_001,monotonic_ms=1001)
        b=InMemoryProofClient(host);await b.login(private)
        arrived,release=threading.Event(),threading.Event()
        service.owner_available.pause_before_commit('phone-authority-child',arrived,release)
        task=asyncio.create_task(a.exchange(request));assert await asyncio.to_thread(arrived.wait,2)
        assert host._current.authorized
        before=case.endswith('before')
        clock.set_time(wall_ms=1,monotonic_ms=record.monotonic_deadline_ms-(1 if before else 0))
        release.set();answer=await task
        assert (answer.get('status')=='ok')==before,answer
        views=tuple(service.result_commands._views.values())
        assert bool(views and views[0].payload['cards'][0]['pinned'])==before
        assert not host._fenced
        assert (await b.exchange(wire(rid='surviving-clock')))['status']=='ok'
        await b.close()
    elif case=='race-after-ack-updater':
        from contextlib import contextmanager
        original=service._service_commit
        started,finished=threading.Event(),threading.Event();workers=[]
        @contextmanager
        def commit():
            with original():yield
            def update():
                started.set();clock.set_time(wall_ms=1,monotonic_ms=record.monotonic_deadline_ms);finished.set()
            worker=threading.Thread(target=update);workers.append(worker);worker.start()
            assert started.wait(1) and not finished.wait(.02),'F guard did not exclude paired updater'
        service._service_commit=commit
        original_seal=host._connections._seal
        def seal(*args):
            assert finished.wait(2)
            return original_seal(*args)
        host._connections._seal=seal
        denied=await a.exchange(request);assert denied.get('status')!='ok'
        for worker in workers:worker.join(1);assert not worker.is_alive()
        entry=next(e for (binding,rid),e in service._ledger.items() if rid=='race-pin')
        assert entry['state']=='done' and not host._fenced
        assert next(iter(service.result_commands._views.values())).payload['cards'][0]['pinned']
    elif case in {'race-egress','race-history'}:
        if case=='race-history':assert (await a.exchange(request))['status']=='ok'
        reply=await asyncio.to_thread(host.handle_connection,record.lease,record.token,request)
        assert type(reply) is ConnectionReply
        entry=next(e for (binding,rid),e in service._ledger.items() if rid=='race-pin')
        assert entry['state']=='done'
        clock.set_time(wall_ms=1,monotonic_ms=record.monotonic_deadline_ms)
        denied=host.claim_connection_reply(record.lease,record.token,reply)
        assert type(denied) is ConnectionFailure and entry['state']=='done' and not host._fenced
        assert next(iter(service.result_commands._views.values())).payload['cards'][0]['pinned']
    elif case in {'transport-authorized-cancel','transport-queued-cancel','transport-pregrant-cancel'}:
        arrived,release=threading.Event(),threading.Event()
        original_send=host._anchor._send;frames=[]
        def send_frame(kind,payload,**kwargs):
            if kind=='child.grant.acquire':frames.append(payload['operation'])
            return original_send(kind,payload,**kwargs)
        host._anchor._send=send_frame
        if case=='transport-authorized-cancel':
            service.owner_available.pause_before_commit('phone-authority-child',arrived,release)
        elif case=='transport-pregrant-cancel':
            original_observer=host._anchor._admission_observer
            def observer(phase,operation):
                if phase=='acquire' and operation=='service.authorize':
                    arrived.set();assert release.wait(2)
                return original_observer(phase,operation)
            host._anchor._admission_observer=observer
        else:
            original_get=host._queue.get
            def paused_get(*args,**kwargs):
                item=original_get(*args,**kwargs)
                if item is not None and item[0]=='handle_connection':arrived.set();assert release.wait(2)
                return item
            host._queue.get=paused_get
            await asyncio.to_thread(host.set_enabled,True)
        await a.incoming.put({'type':'websocket.receive','text':request})
        assert await asyncio.to_thread(arrived.wait,2)
        completion=host._current
        await a.incoming.put({'type':'websocket.disconnect','code':1000})
        for _ in range(100):
            if record.cancel.is_set():break
            await asyncio.sleep(.001)
        assert record.cancel.is_set()
        a.task.cancel();a.task.cancel()
        await asyncio.sleep(.03)
        assert not a.task.done(),'adapter released owned dispatch while worker still executing'
        release.set()
        try:await a.task
        except asyncio.CancelledError:pass
        a.task=None
        assert not host._fenced,frames
        assert frames==(['service.authorize','service.commit'] if case=='transport-authorized-cancel' else []),frames
        if completion is not None:assert completion.worker_finished.is_set()
        views=tuple(service.result_commands._views.values())
        assert bool(views and views[0].payload['cards'][0]['pinned'])==(case=='transport-authorized-cancel')
        assert not any(e.get('text','').find('race-pin')>=0 for e in a.transcript)
        b=InMemoryProofClient(host);await b.login(private)
        assert (await b.exchange(wire(rid='after-cancel')))['status']=='ok';await b.close()
    elif case.startswith('binding-'):
        from dataclasses import replace
        field=case.removeprefix('binding-')
        old=getattr(record.binding,field)
        value=old+1 if type(old) is int else frozenset({'read'}) if field=='scopes' else 'different'
        record.binding=replace(record.binding,**{field:value})
        denied=await a.exchange(request);assert denied.get('status')!='ok'
        assert not any(e.get('operation')=='results.pin' for e in service._ledger.values())
        assert not host._fenced
        b=InMemoryProofClient(host);await b.login(private)
        assert (await b.exchange(wire(rid='surviving-binding')))['status']=='ok';await b.close()
    elif case in {'receipt-protected','receipt-capability-revoke'}:
        from jarvis.bot.phone_remote_results import SyntheticResultRecord
        if case=='receipt-protected':
            source.replace([SyntheticResultRecord(str(uuid.UUID(int=1)),2,'Protected fixture','Hidden',1,'protected')])
        else:
            slot=service.result_commands._slot(service.results)
            service.result_commands.revoke(service.results,slot.capability)
        denied=await a.exchange(request);assert denied.get('status')!='ok'
        assert not host._fenced
        assert not any(v.payload['cards'][0]['pinned'] for v in service.result_commands._views.values())
    elif case in {'receipt-source-change','receipt-terminal-reentry'}:
        from jarvis.bot.phone_remote_results import SyntheticResultRecord
        original=service.result_commands.publication
        def publication(*args,**kwargs):
            if case=='receipt-terminal-reentry':service.handle(wire('results.pin',target,'nested'),record.context)
            source.replace([SyntheticResultRecord(str(uuid.UUID(int=1)),2,'Changed fixture','Changed body',1)])
            return original(*args,**kwargs)
        service.result_commands.publication=publication
        denied=await a.exchange(request);assert denied.get('status')!='ok'
        assert host._fenced==(case=='receipt-terminal-reentry')
        entry=next(e for (binding,rid),e in service._ledger.items() if rid=='race-pin')
        assert entry['state']==('uncertain' if host._fenced else 'withheld')
        if not host._fenced:
            assert (await a.exchange(wire(rid='after-withhold')))['status']=='ok'
            assert await a.exchange(request)==denied
    elif case=='receipt-reused-session':
        from unittest.mock import patch
        await asyncio.to_thread(host.signout,identity=record.context.identity,session_id=record.binding.session_id,owner_id='alice')
        b=InMemoryProofClient(host)
        with patch('jarvis.bot.phone_remote_login.secrets.token_hex',return_value=record.binding.session_id):await b.login(private)
        newer=next(r for r in host._connections.records.values() if r is not record)
        assert newer.binding.session_id==record.binding.session_id and newer.binding.login_incarnation!=record.binding.login_incarnation
        snap=await b.exchange(wire('results.snapshot',{},'b-snapshot'))
        view=await b.exchange(wire('results.view',{k:snap['payload'][k] for k in ('generation','collection_epoch')},'b-view'))
        pinned=await b.exchange(wire('results.pin',PhoneCardAuthorityProcessTests.target(view['payload']),'b-pin'));assert pinned['status']=='ok'
        assert (await a.exchange(request)).get('status')!='ok'
        assert (await b.exchange(wire('results.pin',PhoneCardAuthorityProcessTests.target(view['payload']),'b-pin')))==pinned
        await b.close()
    elif case in {'transport-overflow','transport-send-loss'}:
        if case=='transport-overflow':
            arrived,release=threading.Event(),threading.Event()
            service.owner_available.pause_before_commit('phone-authority-child',arrived,release)
            await a.incoming.put({'type':'websocket.receive','text':request})
            assert await asyncio.to_thread(arrived.wait,2)
            await a.incoming.put({'type':'websocket.receive','text':wire(rid='queued-one')})
            await a.incoming.put({'type':'websocket.receive','text':wire(rid='overflow-two')})
            for _ in range(100):
                if record.cancel.is_set():break
                await asyncio.sleep(.001)
            assert record.cancel.is_set();release.set();await a.task
            assert not any('race-pin' in e.get('text','') for e in a.transcript)
        else:
            a.send_failure_request='race-pin'
            await a.incoming.put({'type':'websocket.receive','text':request})
            await asyncio.wait_for(a.task,3)
            assert record.cancel.is_set()
            entry=next(e for (binding,rid),e in service._ledger.items() if rid=='race-pin')
            assert entry['state']=='done'
        b=InMemoryProofClient(host);await b.login(private)
        assert (await b.exchange(wire(rid='after-transport')))['status']=='ok';await b.close()
    elif case=='receipt-conflict-reconnect':
        first=await a.exchange(request);assert first['status']=='ok'
        assert await a.exchange(request)==first
        conflict=await a.exchange(wire('results.unpin',target,'race-pin'));assert conflict['reason']=='request_conflict'
        b=InMemoryProofClient(host);await b.login(private)
        snap=await b.exchange(wire('results.snapshot',{},'new-snapshot'))
        view=await b.exchange(wire('results.view',{k:snap['payload'][k] for k in ('generation','collection_epoch')},'new-view'))
        assert not view['payload']['cards'][0]['pinned'];await b.close()
    else:raise AssertionError(case)
    report['race']=case


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ProofConnectionRaceProcessTests(unittest.TestCase):
    run_case=ProofConnectionProcessTests.run_case
    def test_atomic_monotonic_commit_egress_history_and_positive_boundary(self):
        for case in ('race-expiry-at','race-expiry-before','race-egress','race-history','race-after-ack-updater'):
            with self.subTest(case=case):self.run_case(case)

    def test_owned_cancellation_pregrant_queued_authorized_and_receipt_isolation(self):
        for case in ('transport-queued-cancel','transport-pregrant-cancel','transport-authorized-cancel','receipt-conflict-reconnect'):
            with self.subTest(case=case):self.run_case(case)


async def _connection_handshake_case(case,host,clock,private,report):
    import asyncio,base64,dataclasses
    from types import SimpleNamespace
    from tests.unit.test_phone_remote_connection import InMemoryProofClient,wire,handshake
    from tests.unit.test_phone_remote_login import sign_challenge_proof
    a,b=InMemoryProofClient(host),InMemoryProofClient(host)
    c=None
    await b.login(private)  # unrelated active transport is the positive control
    await a.start()
    record=next(r for r in host._connections.records.values() if r.state=='opened')
    epoch=record.epoch
    if case=='handshake-prove-first':
        denied=await a.exchange(handshake('auth.prove',dict(challenge_id='AAAAAAAAAAAAAAAAAAAAAA',proof='eA'),'bad'))
    elif case=='handshake-unknown-selector':
        denied=await a.exchange(handshake('auth.challenge',dict(device_id='missing',grant_id='missing')))
    else:
        challenge=await a.challenge()
        if case=='handshake-repeat-challenge':
            denied=await a.exchange(handshake('auth.challenge',dict(device_id='d-channel',grant_id='g-channel'),'again'))
        else:
            changed=SimpleNamespace(**vars(challenge))
            if case.startswith('handshake-wrong-'):
                field=case.removeprefix('handshake-wrong-')
                setattr(changed,field,getattr(changed,field)+1 if type(getattr(changed,field)) is int else 'wrong')
            if case=='handshake-cross-proof':
                c=InMemoryProofClient(host);await c.start();changed=await c.challenge()
            proof=sign_challenge_proof(changed,ec.generate_private_key(ec.SECP256R1()) if case=='handshake-invalid-key' else private)
            payload=dict(challenge_id=challenge.challenge_id,proof=base64.urlsafe_b64encode(proof).rstrip(b'=').decode())
            if case=='handshake-mismatch':payload['challenge_id']='AAAAAAAAAAAAAAAAAAAAAA'
            if case=='handshake-expired':clock.set_time(wall_ms=1_800_000_060_000,monotonic_ms=61000)
            if case=='gap-activation-send-loss':a.send_failure_request='prove'
            original=host.activate_connection
            observed=[]
            if case=='handshake-proof-reentry':
                original_complete=host._connections.login._complete_for_connection
                def complete(**kwargs):
                    try:host._connections.invoke('connection_prove',record.lease,record.token,kwargs['challenge_id'],kwargs['proof_bytes'])
                    except Exception:pass
                    return original_complete(**kwargs)
                host._connections.login._complete_for_connection=complete
            if case in {'handshake-lost-login-ack','gap-lost-activation-ack'}:
                from jarvis.bot.phone_admission_store import StoreUnavailable
                original_request=host._anchor._request
                def lose(kind,payload,expected):
                    operation=host._anchor._grant_operation
                    target='session.login' if case=='handshake-lost-login-ack' else 'service.authorize'
                    if kind=='child.grant.release' and operation==target:
                        host._anchor._send(kind,payload,correlation_id=str(uuid.uuid4()))
                        host._anchor.close();raise StoreUnavailable('fixture lost ACK')
                    return original_request(kind,payload,expected)
                host._anchor._request=lose
            if case.startswith('gap-'):
                def activate(lease,token,rid):
                    admission=record.admission
                    assert type(admission.login_incarnation) is str
                    # Exact committed provenance is compared, never manufactured.
                    with sqlite3.connect(host._database_path) as db:
                        actual=db.execute('SELECT login_incarnation FROM phone_remote_sessions WHERE session_id=?',(admission.session_id,)).fetchone()[0]
                    assert admission.login_incarnation==actual
                    assert not host._connections.login._consume_admission(dataclasses.replace(admission))
                    observed.append(admission)
                    if case=='gap-close':host.close_connection(lease,token)
                    elif case=='gap-feature':host.set_enabled(False)
                    elif case=='gap-revoke':host.signout(identity=binding_context.identity,session_id=admission.session_id,owner_id=admission.owner_id)
                    elif case=='gap-timer':assert host._connections.expire_handshake(lease,token,epoch)
                    elif case=='gap-deadline':clock.set_time(wall_ms=1_800_000_060_000,monotonic_ms=record.handshake_deadline)
                    elif case=='gap-lost-activation-ack':pass
                    elif case=='gap-stale-timer':
                        result=original(lease,token,rid)
                        assert not host._connections.expire_handshake(lease,token,epoch)
                        assert not record.cancel.is_set()
                        return result
                    return original(lease,token,rid)
                binding_context=next(r.context for r in host._connections.records.values() if r.state=='active')
                host.activate_connection=activate
            denied=await a.exchange(handshake('auth.prove',payload,'prove'))
            host.activate_connection=original
            if case=='handshake-replay':
                assert denied['status']=='ok'
                denied=await a.exchange(handshake('auth.prove',payload,'replayed'))
                assert denied.get('type')=='websocket.close'
            if case=='gap-stale-timer':
                assert denied['status']=='ok';assert (await a.exchange(wire()))['status']=='ok'
            else:assert denied.get('status')!='ok',denied
            if case.startswith('gap-'):assert len(observed)==1
    if case!='gap-stale-timer':assert denied.get('status')!='ok',denied
    await a.close()
    if c is not None:await c.close()
    if case in {'handshake-lost-login-ack','gap-lost-activation-ack'}:
        assert host._fenced
        assert not host._connections.login._admissions
    elif case!='gap-feature':
        assert (await b.exchange(wire(rid='surviving-handshake')))['status']=='ok'
        assert not host._fenced
    await b.close()
    report['phase_case']=case


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ProofConnectionHandshakeProcessTests(unittest.TestCase):
    run_case=ProofConnectionProcessTests.run_case

    def test_closed_handshake_invalid_proof_and_phase_never_affect_survivor(self):
        for case in ('prove-first','unknown-selector','repeat-challenge','mismatch','invalid-key','expired',
                     'wrong-service_id','wrong-host_id','wrong-authority_generation','wrong-expires_at_ms',
                     'cross-proof','proof-reentry','replay'):
            with self.subTest(case=case):self.run_case('handshake-'+case)

    def test_actual_admission_provenance_fresh_activation_and_timer_arbitration(self):
        for case in ('close','feature','revoke','timer','deadline','stale-timer','activation-send-loss'):
            with self.subTest(case=case):self.run_case('gap-'+case)


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ProofConnectionIdentityPublicationProcessTests(unittest.TestCase):
    run_case=ProofConnectionProcessTests.run_case
    def test_each_captured_binding_field_is_enforced_before_effect(self):
        for field in ('owner_id','device_id','grant_id','session_id','login_incarnation','host_id',
                      'host_generation','grant_generation','process_epoch','scopes'):
            with self.subTest(field=field):self.run_case('binding-'+field)

    def test_receipt_terminal_withholding_reused_session_overflow_and_send_loss(self):
        for case in ('receipt-source-change','receipt-terminal-reentry','receipt-reused-session',
                     'transport-overflow','transport-send-loss','handshake-lost-login-ack','gap-lost-activation-ack',
                     'receipt-protected','receipt-capability-revoke'):
            with self.subTest(case=case):self.run_case(case)


async def _connection_review_case(case,host,clock,private,report):
    import asyncio,time
    from tests.unit.test_phone_remote_connection import InMemoryProofClient,wire,handshake
    from jarvis.bot.phone_admission_store import StoreUnavailable
    a=InMemoryProofClient(host)
    if case.startswith('review-admission-'):
        control=case.removeprefix('review-admission-');observed=[];proof_task=None
        original_open=host.open_connection;original_claim=host.claim_connection_reply
        try:
            if control=='accept':
                def open_then_drain(token):
                    lease=original_open(token)
                    observed.append(host.quiesce(str(uuid.uuid4())))
                    return lease
                host.open_connection=open_then_drain
                async def send(event):
                    a.transcript.append(event);await a.outgoing.put(event)
                a.task=asyncio.create_task(a.app({'type':'websocket','path':'/ws/phone-remote'},a.incoming.get,send))
                await a.incoming.put({'type':'websocket.connect'})
            else:
                if control=='activation':await a.start()
                else:await a.login(private)
                if control=='positive':
                    assert (await a.exchange(wire(rid='claim-drain')))['status']=='ok'
                    assert not host._closed
                    await a.close();return
                target='prove' if control=='activation' else 'claim-drain'
                def claim_then_drain(*args):
                    value=original_claim(*args)
                    if type(value) is str and json.loads(value)['request_id']==target:
                        observed.append(host.quiesce(str(uuid.uuid4())))
                    return value
                host.claim_connection_reply=claim_then_drain
                if control=='activation':proof_task=asyncio.create_task(a.prove(await a.challenge(),private))
                else:await a.incoming.put({'type':'websocket.receive','text':wire(rid=target)})
            # No additional inbound frame or disconnect may be necessary.
            await asyncio.wait_for(asyncio.shield(a.task),.75)
            assert observed and observed[0]['drained'] and host._closed
            assert not host._connections.records
            assert sum(e['type']=='websocket.close' for e in a.transcript)==1
            if control=='accept':assert not any(e['type']=='websocket.accept' for e in a.transcript)
            else:
                assert not any(e.get('type')=='websocket.send' and json.loads(e['text']).get('request_id')==target for e in a.transcript)
        finally:
            host.open_connection=original_open;host.claim_connection_reply=original_claim
            if proof_task is not None:
                proof_task.cancel()
                try:await proof_task
                except asyncio.CancelledError:pass
            if a.task is not None:await a.close()
    elif case.startswith('review-clock-'):
        wall,mono=clock.snapshot()
        if case=='review-clock-setter':
            await a.start()
            try:clock.login.set_time(wall_ms=wall,monotonic_ms=mono+100000)
            except StoreUnavailable:pass
            answer=await a.exchange(handshake('auth.challenge',dict(device_id='d-channel',grant_id='g-channel')))
            assert answer.get('status')!='ok','divergent login image issued a challenge'
        else:
            if case=='review-clock-paired':clock.set_time(wall_ms=wall,monotonic_ms=mono+100000)
            await a.start();challenge=await a.challenge()
            if case=='review-clock-barrier':
                root=pathlib.Path(host._database_path).parent
                entered,release,value=root/'review-entered',root/'review-release',root/'review-clock.json'
                release.touch();value.write_text(json.dumps(dict(wall_ms=wall,monotonic_ms=mono+100000)))
                clock.login._verification_barrier=(str(entered),str(release),str(value))
            answer=await a.prove(challenge,private)
            if case=='review-clock-barrier':
                assert answer.get('status')!='ok','verification barrier extended the paired deadline'
                assert not host._connections.login._admissions and host._fenced
            else:
                assert answer['status']=='ok'
                r=next(iter(host._connections.records.values()))
                assert r.monotonic_deadline_ms==mono+100000+43200000
                clock.set_time(wall_ms=1,monotonic_ms=r.monotonic_deadline_ms-1)
                assert (await a.exchange(wire()))['status']=='ok'
                clock.set_time(wall_ms=1,monotonic_ms=r.monotonic_deadline_ms)
                assert (await a.exchange(wire(rid='exact-expiry'))).get('status')!='ok'
        await a.close()
    elif case.startswith('review-phase-'):
        await a.login(private)
        control=case.removeprefix('review-phase-')
        if control=='business':
            denied=await a.exchange(wire('session.status',{'unexpected':'auth.challenge'},'malformed-business'))
            assert denied['reason']=='malformed_request'
            assert (await a.exchange(wire(rid='business-survivor')))['status']=='ok'
        else:
            variants={
                'challenge':handshake('auth.challenge',dict(device_id='d-channel',grant_id='g-channel'),'again'),
                'prove':handshake('auth.prove',dict(challenge_id='AAAAAAAAAAAAAAAAAAAAAA',proof='eA'),'again'),
                'bad-challenge':handshake('auth.challenge',{},'again'),
                'bad-prove':handshake('auth.prove',{'proof':False},'again'),
                'namespace':json.dumps({'operation':'auth.challenge','payload':None}),
                'duplicate': '{"protocol":"mortimer.phone-connection.v1","protocol":"other","operation":"nope"}',
            }
            denied=await a.exchange(variants[control]);assert denied.get('type')=='websocket.close',denied
            await a.task;assert not host._connections.records
        await a.close()
        b=InMemoryProofClient(host);await b.login(private)
        assert (await b.exchange(wire()))['status']=='ok';await b.close()
    elif case=='review-terminal-send':
        await a.login(private)
        arrived,release=threading.Event(),threading.Event()
        original_close=host._connections.close_all
        def paused_close():
            arrived.set();assert release.wait(3)
            original_close()
        host._connections.close_all=paused_close
        drain=asyncio.create_task(asyncio.to_thread(host.quiesce,str(uuid.uuid4())))
        try:
            assert await asyncio.to_thread(arrived.wait,2)
            assert (await asyncio.wait_for(drain,2))['drained']
            assert host._closed and host._connections.records
            before=len(a.transcript)
            answer=await a.exchange(wire(rid='after-terminal-drain'))
            assert answer.get('type')=='websocket.close',answer
            assert not any(e.get('type')=='websocket.send' for e in a.transcript[before:])
        finally:
            release.set();host._connections.close_all=original_close
            await a.close()
    elif case.startswith('review-send-'):
        control=case.removeprefix('review-send-')
        phase,retirement=control.split(':')
        entered,release,cancelled,cleanup=asyncio.Event(),asyncio.Event(),asyncio.Event(),asyncio.Event()
        matches={'accept':lambda e:e['type']=='websocket.accept',
                 'challenge':lambda e:e.get('type')=='websocket.send' and json.loads(e['text']).get('request_id')=='challenge',
                 'error':lambda e:e.get('type')=='websocket.send' and json.loads(e['text']).get('request_id')=='bad',
                 'activation':lambda e:e.get('type')=='websocket.send' and json.loads(e['text']).get('request_id')=='prove',
                 'active':lambda e:e.get('type')=='websocket.send' and json.loads(e['text']).get('request_id')=='blocked-status'}
        async def hook(event):
            if not matches[phase](event):return
            entered.set()
            try:await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                while not cleanup.is_set():
                    try:await cleanup.wait()
                    except asyncio.CancelledError:continue
                raise
        a.send_hook=hook;client_call=None;drain_task=None
        original_timer=host._connections.timer
        if retirement=='timer':
            def timer(*args):
                epoch,_=original_timer(*args);return epoch,time.monotonic()+.15
            host._connections.timer=timer
        try:
            if phase=='accept':client_call=asyncio.create_task(a.start())
            else:
                await a.start()
                if phase=='challenge':
                    await a.incoming.put({'type':'websocket.receive','text':handshake('auth.challenge',dict(device_id='d-channel',grant_id='g-channel'))})
                elif phase=='error':await a.incoming.put({'type':'websocket.receive','text':handshake('auth.challenge',{},'bad')})
                else:
                    challenge=await a.challenge()
                    if phase=='activation':client_call=asyncio.create_task(a.prove(challenge,private))
                    else:
                        assert (await a.prove(challenge,private))['status']=='ok'
                        await a.incoming.put({'type':'websocket.receive','text':wire(rid='blocked-status')})
            assert await asyncio.wait_for(entered.wait(),2)
            if retirement=='positive':
                release.set()
                event=await asyncio.wait_for(a.outgoing.get(),2);assert matches[phase](event)
                assert (await a.exchange(wire(rid='after-send')))['status']=='ok'
            else:
                if retirement=='disconnect':await a.incoming.put({'type':'websocket.disconnect','code':1000})
                elif retirement=='overflow':
                    for n in range(3):await a.incoming.put({'type':'websocket.receive','text':wire(rid='overflow-'+str(n))})
                elif retirement=='cancel':a.task.cancel();a.task.cancel()
                elif retirement=='owner':
                    r=next(iter(host._connections.records.values()))
                    await asyncio.to_thread(host.close_connection,r.lease,r.token)
                elif retirement=='drain':
                    drain_task=asyncio.create_task(asyncio.to_thread(host.quiesce,str(uuid.uuid4())))
                assert await asyncio.wait_for(cancelled.wait(),.5),'retirement did not cancel owned send'
                assert host._connections.records,'lease removed before pending send joined'
                assert not a.task.done()
                if drain_task is not None:assert not drain_task.done(),'drain ignored owned send cleanup'
                a.task.cancel();a.task.cancel()
                cleanup.set()
                try:await asyncio.wait_for(asyncio.shield(a.task),2)
                except asyncio.CancelledError:pass
                if drain_task is not None:assert (await asyncio.wait_for(drain_task,2))['drained']
                assert not host._connections.records
                assert not any(matches[phase](e) for e in a.transcript),'retired send delivered late'
        finally:
            host._connections.timer=original_timer
            cleanup.set();release.set()
            if client_call is not None:
                client_call.cancel()
                try:await client_call
                except (asyncio.CancelledError,AssertionError):pass
            if a.task is not None:
                try:await a.close()
                except asyncio.CancelledError:pass
        assert not host._fenced
    else:raise AssertionError(case)
    report['review_control']=case


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ConnectionReviewRegressionProcessTests(unittest.TestCase):
    run_case=ProofConnectionProcessTests.run_case
    def test_paired_login_clock_cannot_extend_deadlines(self):
        for case in ('setter','barrier','paired'):
            with self.subTest(case=case):self.run_case('review-clock-'+case)

    def test_owned_blocked_sends_settle_before_lease_removal(self):
        for case in ('accept:disconnect','challenge:disconnect','error:disconnect','activation:disconnect',
                     'active:disconnect','challenge:timer','active:overflow','active:cancel','active:owner','active:drain','active:positive'):
            with self.subTest(case=case):self.run_case('review-send-'+case)

    def test_reserved_authentication_namespace_is_terminal_only_after_activation(self):
        for case in ('challenge','prove','bad-challenge','bad-prove','namespace','duplicate','business'):
            with self.subTest(case=case):self.run_case('review-phase-'+case)


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ConnectionTerminalSendProcessTests(unittest.TestCase):
    run_case=ProofConnectionProcessTests.run_case
    def test_no_application_send_after_drain_even_before_registry_cleanup(self):
        self.run_case('review-terminal-send')


@unittest.skipUnless(os.environ.get('PHONE_REMOTE_AUTHORITY_OWNER_BIN'),'requires offline native owner')
class ConnectionSendAdmissionOutcomeProcessTests(unittest.TestCase):
    run_case=ProofConnectionProcessTests.run_case
    def test_failed_send_admission_closes_without_another_inbound_frame(self):
        for control in ('claim','accept','activation','positive'):
            with self.subTest(control=control):self.run_case('review-admission-'+control)
