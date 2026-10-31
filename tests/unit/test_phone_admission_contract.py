"""Run the immutable S0 v1 vectors through the offline admission policy core.

The fixture remains synthetic: this verifies policy invariants only and does not
prove persistence, routes, host-anchor recovery, media egress, or live access.
"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import os
import socket
import subprocess
import builtins
from contextlib import ExitStack, contextmanager

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission import PhoneAdmissionCore

FIXTURE = Path(__file__).parents[1] / "fixtures/phone_admission_contract/v1.json"


@contextmanager
def isolated_harness():
    """Block effects before invoking even deliberately hostile harness events."""
    def refuse(*args, **kwargs):
        raise PermissionError("S0 forbids network/process/runtime access")

    original_import = builtins.__import__

    def bounded_import(name, *args, **kwargs):
        if name == "jarvis" or name.startswith("jarvis."):
            return refuse()
        return original_import(name, *args, **kwargs)

    with ExitStack() as stack:
        for module, names in ((socket, ("socket", "create_connection", "getaddrinfo")),
                              (subprocess, ("Popen", "run", "call", "check_call", "check_output")),
                              (os, ("system", "fork", "posix_spawn", "posix_spawnp", "execve"))):
            for name in names:
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, refuse))
        stack.enter_context(patch.object(builtins, "__import__", bounded_import))
        yield


def decode_probe(value):
    """Explicit test-only representation; the model never interprets this marker."""
    if isinstance(value, dict):
        if set(value) == {"$nonfinite"}:
            return {"nan": float("nan"), "positive-infinity": float("inf"),
                    "negative-infinity": float("-inf")}[value["$nonfinite"]]
        return {key: decode_probe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_probe(item) for item in value]
    return value


def load_fixture(text):
    def reject_constant(token):
        raise ValueError("Nonstandard JSON constant: " + token)
    return json.loads(text, parse_constant=reject_constant)


def fixture_state():
    grants = {
        "A": {"owner": "owner-a", "enabled": True, "scope": ["voice", "read", "action"]},
        "B": {"owner": "owner-b", "enabled": True, "scope": ["voice", "read", "action"]},
    }
    sessions = {
        "a1": {"grant": "A", "generation": 0, "epoch": 1, "process": 1, "enabled": True},
        "a2": {"grant": "A", "generation": 0, "epoch": 1, "process": 1, "enabled": True},
        "b1": {"grant": "B", "generation": 0, "epoch": 1, "process": 1, "enabled": True},
    }
    return grants, sessions, {"p1": "a1", "p2": "a2", "p3": "b1"}


def fixture_core(constants, *, feature_enabled=True):
    grants, sessions, peers = fixture_state()
    return PhoneAdmissionCore(constants, feature_enabled=feature_enabled,
                              initial_grants=grants, initial_sessions=sessions,
                              initial_peers=peers)


def fixture_identity(core, event):
    """Supply a synthetic verified principal from model state, never payload claims."""
    kind = event.get("type") if type(event) is dict else None
    owner = "owner-a"
    if kind == "issue":
        session_id = event.get("session")
        session = core.sessions.get(session_id) if type(session_id) is str else None
        if session:
            owner = core.grants[session["grant"]]["owner"]
    elif kind == "consume":
        ticket_id = event.get("ticket")
        ticket = core.tickets.get(ticket_id) if type(ticket_id) is str else None
        if ticket:
            owner = ticket["binding"]["owner"]
    elif kind in ("command", "emit"):
        peer_id = event.get("peer")
        peer = core.peers.get(peer_id) if type(peer_id) is str else None
        if peer:
            owner = peer["binding"]["owner"]
    elif kind == "login":
        grant_id = event.get("grant")
        grant = core.grants.get(grant_id) if type(grant_id) is str else None
        if grant:
            owner = grant["owner"]
    return ClientIdentity(name="s0-fixture", user_id=owner)


def exercise_forbidden_probe(event):
    """Exercise fixture isolation probes outside the production policy API."""
    kind = event.get("type")
    if kind == "probe_network":
        socket.socket()
    elif kind == "probe_process":
        subprocess.Popen(["S0-MUST-NEVER-EXECUTE"])
    elif kind == "probe_runtime":
        __import__("jarvis")
    else:
        raise AssertionError(f"unknown isolation probe: {kind!r}")


class MutationProbeCore(PhoneAdmissionCore):
    """Test-only faulty variants; production policy has no mutation switches."""

    def __init__(self, constants, mutation):
        grants, sessions, peers = fixture_state()
        super().__init__(constants, feature_enabled=True, initial_grants=grants,
                         initial_sessions=sessions, initial_peers=peers)
        self.test_mutation = mutation

    def step(self, event, *, identity=None):
        mutation = self.test_mutation
        event_type = event.get("type") if type(event) is dict else None

        if mutation == "trust_client" and event_type == "command" and type(event.get("owner")) is str:
            event = dict(event)
            event.pop("owner")
        if mutation == "unknown_ordinary" and event_type == "emit":
            event = dict(event, classification="ordinary", provenance=True, source_allowed=True)
        if mutation == "allow_replay" and event_type == "consume":
            ticket = self.tickets.get(event.get("ticket"))
            if ticket and ticket["used"]:
                ticket["used"] = False
                try:
                    return super().step(event, identity=identity)
                finally:
                    ticket["used"] = True
        if mutation == "ignore_global" and event_type in ("command", "emit"):
            peer = self.peers.get(event.get("peer"))
            if peer:
                binding = peer["binding"]
                session = self.sessions.get(binding["session"])
                old_binding_epoch = binding["epoch"]
                old_session_epoch = session["epoch"] if session else None
                binding["epoch"] = self.epoch
                if session:
                    session["epoch"] = self.epoch
                try:
                    return super().step(event, identity=identity)
                finally:
                    binding["epoch"] = old_binding_epoch
                    if session:
                        session["epoch"] = old_session_epoch
        if mutation == "ignore_session_fence" and event_type in ("consume", "command", "emit"):
            session_id = event.get("session")
            if event_type in ("command", "emit"):
                peer = self.peers.get(event.get("peer"))
                session_id = peer["binding"]["session"] if peer else None
            had_fence = type(session_id) is str and session_id in self.session_fences
            old_fence = self.session_fences.pop(session_id, None) if had_fence else None
            try:
                return super().step(event, identity=identity)
            finally:
                if had_fence:
                    self.session_fences[session_id] = old_fence
        if mutation == "network_grace":
            original_close = self.close
            self.close = lambda peer, reason: None
            try:
                result = super().step(event, identity=identity)
            finally:
                self.close = original_close
            return result
        if mutation == "ignore_anchor" and event_type == "restore":
            result = super().step(event, identity=identity)
            if result["admitted"]:
                self.anchor_epoch = self.epoch
                self.anchor_state = "stable"
            return result
        return super().step(event, identity=identity)


def run_case(case, constants, mutation=None):
    model = (fixture_core(constants) if mutation is None
             else MutationProbeCore(constants, mutation))
    with isolated_harness():
        for item in case["steps"]:
            before = copy.deepcopy(model.__dict__) if item.get("unchanged") else None
            event = decode_probe(item["event"])
            actual = model.step(event, identity=fixture_identity(model, event))
            if actual != item["expected"]:
                raise AssertionError(f'{case["id"]}: {item["event"]}: {actual} != {item["expected"]}')
            if item.get("unchanged") and model.__dict__ != before:
                raise AssertionError(f'{case["id"]}: denial changed model state')
        actual = model.view()
        def resolve(value):
            if isinstance(value, dict):
                if set(value) == {"constant", "offset"}:
                    return model.time_value(value)
                return {k: resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [resolve(v) for v in value]
            return value

        for key, expected in case["final"].items():
            expected = resolve(expected)
            if actual[key] != expected:
                raise AssertionError(f'{case["id"]}: {key}: {actual[key]} != {expected}')
    return model


class PhoneAdmissionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture(FIXTURE.read_text())

    def test_versioned_vectors(self):
        self.assertEqual(self.fixture["version"], 1)
        self.assertEqual({c["group"] for c in self.fixture["cases"]}, {f"S0-0{i}" for i in range(1, 7)})
        for case in self.fixture["cases"]:
            with self.subTest(vector=case["id"]):
                self.assertTrue(case["clauses"])
                self.assertTrue(case["acceptance"])
                run_case(case, self.fixture["constants"])

    def test_mutations_are_sensitivity_only(self):
        cases = {c["id"]: c for c in self.fixture["cases"]}
        for item in self.fixture["sensitivity"]:
            with self.subTest(mutation=item["mutation"]):
                with self.assertRaises(AssertionError):
                    run_case(cases[item["case"]], self.fixture["constants"], item["mutation"])

    def test_clock_constant_domain(self):
        probes = self.fixture["input_domain_probes"]
        with isolated_harness():
            for key in self.fixture["constants"]:
                for value in probes["invalid_constant_values"]:
                    with self.subTest(constant=key, value=value):
                        constants = {**self.fixture["constants"], key: decode_probe(value)}
                        with self.assertRaises(ValueError):
                            fixture_core(constants)
            probe = probes["overflow_probe"]
            model = fixture_core({**self.fixture["constants"], probe["constant"]: probe["value"]})
            before = copy.deepcopy(model.__dict__)
            self.assertEqual(model.step({"type": "advance", "time": {
                "constant": probe["constant"], "offset": probe["offset"]}}),
                {"admitted": False, "reason": "malformed"})
            self.assertEqual(model.__dict__, before)
            model = fixture_core({**self.fixture["constants"], "ticket_ttl_s": probe["value"]})
            self.assertEqual(model.step({"type": "advance", "time": {
                "constant": "ticket_ttl_s", "offset": 0}}), {"admitted": True, "reason": "ok"})
            before = copy.deepcopy(model.__dict__)
            event = {"type": "issue", "ticket": "overflow", "session": "a1", "digest": "d"}
            self.assertEqual(model.step(event, identity=fixture_identity(model, event)),
                             {"admitted": False, "reason": "malformed"})
            self.assertEqual(model.__dict__, before)
            for token in probes["nonstandard_json_tokens"]:
                with self.subTest(json_token=token), self.assertRaises(ValueError):
                    load_fixture('{"value": ' + token + '}')


    def test_negative_isolation_probes(self):
        for event in self.fixture["isolation_probes"]:
            with self.subTest(event=event), isolated_harness():
                with self.assertRaises(PermissionError):
                    exercise_forbidden_probe(event)


if __name__ == "__main__":
    unittest.main()
