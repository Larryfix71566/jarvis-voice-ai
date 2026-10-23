"""S0 executable specification only: no production imports or real admission.

Run: python3 -m unittest discover -s tests/unit -p test_phone_admission_contract.py
The v1 fixture is a candidate oracle until independent clause review is recorded.
No model in this file is imported by product code.
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


class AdmissionModel:
    """Pure in-memory authority and symbolic peer model, deliberately not a service."""
    FIELDS = {
        "advance": {"time"}, "issue": {"ticket", "session", "digest", "kind", "peer"},
        "consume": {"ticket", "session", "owner", "grant", "digest", "peer", "kind"},
        "command": {"peer", "owner", "action", "protocol"},
        "emit": {"peer", "sink", "classification", "provenance", "source_allowed"},
        "revoke_session": {"session", "notify"}, "revoke_grant": {"grant", "notify"},
        "begin": {"grant", "scope"}, "commit": set(), "finalize": set(),
        "login": {"grant", "session"}, "restart": set(), "snapshot": {"name"},
        "restore": {"name"}, "anchor": {"state"}, "disconnect": {"peer"},
        "availability": {"available"}, "probe_network": set(), "probe_process": set(),
        "probe_runtime": set(),
    }

    def __init__(self, constants, mutation=None):
        self.constants = constants
        self.mutation = mutation
        self.now = 0
        self.epoch = 1
        self.anchor_epoch = 1
        self.anchor_state = "stable"
        self.process = 1
        self.available = True
        self.pending = None
        self.grants = {g: {"owner": owner, "enabled": True,
                           "scope": ["voice", "read", "action"]}
                       for g, owner in (("A", "owner-a"), ("B", "owner-b"))}
        self.sessions = {}
        self.peers = {}
        for sid, gid, pid in (("a1", "A", "p1"), ("a2", "A", "p2"), ("b1", "B", "p3")):
            self.sessions[sid] = {"grant": gid, "generation": 0, "epoch": 1,
                                  "process": 1, "enabled": True}
            self.peers[pid] = self.new_peer(sid)
        self.tickets = {}
        self.invalidated = set()
        self.snapshots = {}
        self.emissions = []
        self.commands = []
        self.closures = []

    def binding(self, sid):
        session = self.sessions[sid]
        gid = session["grant"]
        return {"session": sid, "grant": gid, "owner": self.grants[gid]["owner"],
                "generation": session["generation"], "epoch": session["epoch"],
                "process": session["process"]}

    def new_peer(self, sid):
        return {"binding": self.binding(sid), "closed": False, "connected": True,
                "checked": self.now}

    def time_value(self, value):
        # All event times are offsets from named fixture constants, never wall time.
        if not isinstance(value, dict) or set(value) != {"constant", "offset"}:
            raise ValueError("bad fake-clock expression")
        return self.constants[value["constant"]] + value["offset"]

    def close(self, pid, reason):
        peer = self.peers[pid]
        if not peer["closed"]:
            peer["closed"] = True
            self.closures.append({"peer": pid, "at": self.now, "reason": reason})

    def authority(self, binding):
        if self.anchor_state != "stable" and self.mutation != "ignore_anchor":
            return "authority-" + self.anchor_state
        if self.epoch != self.anchor_epoch and self.mutation != "ignore_anchor":
            return "authority-mismatch"
        if not self.available:
            return "authority-unavailable"
        session = self.sessions.get(binding["session"])
        grant = self.grants.get(binding["grant"])
        if (not session or not grant or not session["enabled"] or not grant["enabled"]
                or binding["process"] != self.process
                or binding["generation"] != session["generation"]):
            return "authority-stale"
        if self.mutation != "ignore_global" and (binding["epoch"] != self.epoch
                                                  or session["epoch"] != self.epoch):
            return "authority-stale"
        return None

    @staticmethod
    def result(reason="ok", admitted=True):
        return {"admitted": admitted, "reason": reason}

    def deny(self, reason):
        return self.result(reason, False)

    def peer_authority(self, pid):
        peer = self.peers.get(pid)
        if not peer or peer["closed"]:
            return "peer-closed"
        error = self.authority(peer["binding"])
        if error:
            if error != "authority-unavailable" or self.now - peer["checked"] >= self.constants["auth_freshness_s"]:
                if self.mutation != "network_grace":
                    self.close(pid, error)
            return error
        if not peer["connected"]:
            return "disconnected"
        peer["checked"] = self.now
        return None

    def step(self, event):
        if not isinstance(event, dict):
            return self.deny("malformed")
        kind = event.get("type")
        if kind not in self.FIELDS or set(event) - (self.FIELDS.get(kind, set()) | {"type"}):
            return self.deny("malformed")
        try:
            return self._step(kind, event)
        except (KeyError, TypeError, ValueError):
            return self.deny("malformed")

    def _step(self, kind, e):
        if kind == "advance":
            target = self.time_value(e["time"])
            if target < self.now:
                return self.deny("clock-backwards")
            # Observe the deadline itself, even if the requested fake jump crosses it.
            for pid, peer in self.peers.items():
                deadline = peer["checked"] + self.constants["auth_freshness_s"]
                if not peer["closed"] and self.authority(peer["binding"]) and deadline <= target:
                    if self.mutation != "network_grace":
                        previous = self.now
                        self.now = max(previous, deadline)
                        self.close(pid, self.authority(peer["binding"]))
                        self.now = previous
            self.now = target
            return self.result()
        if kind == "issue":
            sid = e["session"]
            binding = self.binding(sid)
            error = self.authority(binding)
            if error:
                return self.deny(error)
            if "voice" not in self.grants[binding["grant"]]["scope"]:
                return self.deny("scope")
            if e["ticket"] in self.tickets or e["ticket"] in self.invalidated:
                return self.deny("ticket-exists")
            ticket_kind = e.get("kind", "offer")
            if ticket_kind not in ("offer", "update"):
                return self.deny("malformed")
            if ticket_kind == "update":
                pid = e["peer"]
                error = self.peer_authority(pid)
                if error or self.peers[pid]["binding"] != binding:
                    return self.deny(error or "binding-mismatch")
            self.tickets[e["ticket"]] = {"binding": binding, "digest": e["digest"],
                                         "kind": ticket_kind, "peer": e.get("peer"),
                                         "expires": self.now + self.constants["ticket_ttl_s"], "used": False}
            return self.result()
        if kind == "consume":
            tid = e["ticket"]
            if tid in self.invalidated:
                return self.deny("ticket-invalidated")
            ticket = self.tickets.get(tid)
            if not ticket:
                return self.deny("ticket-unknown")
            if ticket["used"] and self.mutation != "allow_replay":
                return self.deny("ticket-replay")
            if self.now >= ticket["expires"]:
                return self.deny("ticket-expired")
            bound = ticket["binding"]
            if any(e[k] != bound[k] for k in ("session", "owner", "grant")) or e["digest"] != ticket["digest"]:
                return self.deny("binding-mismatch")
            if e.get("kind", "offer") != ticket["kind"]:
                return self.deny("binding-mismatch")
            error = self.authority(bound)
            if error:
                return self.deny(error)
            if ticket["kind"] == "update":
                if e["peer"] != ticket["peer"]:
                    return self.deny("binding-mismatch")
                error = self.peer_authority(e["peer"])
                if error:
                    return self.deny(error)
            elif e["peer"] in self.peers:
                return self.deny("peer-exists")
            ticket["used"] = True
            if ticket["kind"] == "offer":
                self.peers[e["peer"]] = self.new_peer(bound["session"])
            return self.result()
        if kind in ("command", "emit"):
            pid = e["peer"]
            error = self.peer_authority(pid)
            if error:
                return self.deny(error)
            bound = self.peers[pid]["binding"]
            scopes = self.grants[bound["grant"]]["scope"]
            if kind == "command":
                if type(e["protocol"]) is not int or e["protocol"] != 1 or e["action"] != "fixture-action":
                    return self.deny("protocol")
                if e.get("owner", bound["owner"]) != bound["owner"] and self.mutation != "trust_client":
                    return self.deny("binding-mismatch")
                if "action" not in scopes:
                    return self.deny("scope")
                self.commands.append({"peer": pid, "owner": bound["owner"]})
            else:
                if e["sink"] not in ("event", "text", "audio-symbol"):
                    return self.deny("provider-input-denied")
                if self.mutation != "unknown_ordinary" and (e.get("classification") != "ordinary"
                        or e.get("provenance") is not True or e.get("source_allowed") is not True):
                    return self.deny("classification")
                if ("voice" if e["sink"] == "audio-symbol" else "read") not in scopes:
                    return self.deny("scope")
                self.emissions.append({"peer": pid, "sink": e["sink"], "at": self.now})
            return self.result()
        if kind == "revoke_session":
            sid = e["session"]
            self.sessions[sid]["enabled"] = False
            self.sessions[sid]["generation"] += 1
            if e.get("notify", True):
                for pid, peer in self.peers.items():
                    if peer["binding"]["session"] == sid:
                        self.close(pid, "authority-stale")
            return self.result()
        if kind == "revoke_grant":
            self.grants[e["grant"]]["enabled"] = False
            self.epoch += 1
            self.anchor_epoch = self.epoch
            if e.get("notify", True):
                for pid in self.peers:
                    self.close(pid, "authority-stale")
            return self.result()
        if kind == "begin":
            if self.pending is not None or self.anchor_state != "stable":
                return self.deny("authority-pending")
            gid = e["grant"]
            scope = e["scope"]
            if not isinstance(scope, list) or not set(scope) <= set(self.grants[gid]["scope"]):
                return self.deny("scope")
            self.pending = {"grant": gid, "scope": list(scope), "committed": False}
            self.anchor_epoch += 1
            self.anchor_state = "pending"
            return self.result()
        if kind == "commit":
            if self.pending is None:
                return self.deny("no-transition")
            self.grants[self.pending["grant"]]["scope"] = self.pending["scope"]
            self.epoch = self.anchor_epoch
            self.pending["committed"] = True
            return self.result()
        if kind == "finalize":
            if self.pending is None or not self.pending["committed"]:
                return self.deny("no-commit")
            self.anchor_state = "stable"
            self.pending = None
            return self.result()
        if kind == "login":
            gid, sid = e["grant"], e["session"]
            # Check host consistency without creating or reviving a session first.
            if self.anchor_state != "stable":
                return self.deny("authority-" + self.anchor_state)
            if self.epoch != self.anchor_epoch and self.mutation != "ignore_anchor":
                return self.deny("authority-mismatch")
            if not self.available or not self.grants[gid]["enabled"]:
                return self.deny("authority-stale")
            if sid in self.sessions:
                return self.deny("session-exists")
            self.sessions[sid] = {"grant": gid, "generation": 0, "epoch": self.epoch,
                                  "process": self.process, "enabled": True}
            return self.result()
        if kind == "restart":
            self.process += 1
            self.invalidated.update(self.tickets)
            self.tickets.clear()
            self.sessions.clear()
            for pid in self.peers:
                self.close(pid, "restart")
            return self.result()
        if kind == "snapshot":
            self.snapshots[e["name"]] = copy.deepcopy((self.epoch, self.grants, self.sessions))
            return self.result()
        if kind == "restore":
            # Adversarial stale DB appearance, NOT the authorized restore procedure.
            self.epoch, self.grants, self.sessions = copy.deepcopy(self.snapshots[e["name"]])
            return self.result()
        if kind == "anchor":
            if e["state"] not in ("missing", "pending"):
                return self.deny("malformed")
            self.anchor_state = e["state"]
            return self.result()
        if kind == "disconnect":
            self.peers[e["peer"]]["connected"] = False
            return self.result()
        if kind == "availability":
            if type(e["available"]) is not bool:
                return self.deny("malformed")
            self.available = e["available"]
            return self.result()
        if kind == "probe_network":
            socket.socket()
        if kind == "probe_process":
            subprocess.Popen(["S0-MUST-NEVER-EXECUTE"])
        if kind == "probe_runtime":
            __import__("jarvis")
        raise AssertionError("isolation probe unexpectedly returned")

    def view(self):
        return {"epoch": self.epoch, "anchor_epoch": self.anchor_epoch,
                "anchor_state": self.anchor_state, "process": self.process,
                "closed": sorted(pid for pid, p in self.peers.items() if p["closed"]),
                "emissions": copy.deepcopy(self.emissions), "commands": copy.deepcopy(self.commands),
                "closures": copy.deepcopy(self.closures),
                "grants": copy.deepcopy(self.grants),
                "bindings": {pid: copy.deepcopy(peer["binding"]) for pid, peer in self.peers.items()}}


def run_case(case, constants, mutation=None):
    model = AdmissionModel(constants, mutation)
    with isolated_harness():
        for item in case["steps"]:
            actual = model.step(item["event"])
            if actual != item["expected"]:
                raise AssertionError(f'{case["id"]}: {item["event"]}: {actual} != {item["expected"]}')
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
        cls.fixture = json.loads(FIXTURE.read_text())

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

    def test_negative_isolation_probes(self):
        for event in self.fixture["isolation_probes"]:
            with self.subTest(event=event), isolated_harness():
                with self.assertRaises(PermissionError):
                    AdmissionModel(self.fixture["constants"]).step(event)


if __name__ == "__main__":
    unittest.main()
