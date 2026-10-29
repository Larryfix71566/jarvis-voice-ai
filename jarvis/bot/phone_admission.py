"""Deterministic in-memory phone-session admission policy.

This module is a policy core only. It owns no listener, route, credential,
persistent store, host anchor, provider, or media sink. Callers must pass the
immutable ClientIdentity returned by the existing bearer verification boundary
for admission-facing operations. The session fence here is an executable
invariant, not a production persistence design. Its event names and symbolic
action/output labels belong to the synthetic S0 contract, not a wire protocol.
Administrative transitions are trusted fixture controls, not public requests.
"""
from __future__ import annotations

import copy
import math
from jarvis.auth import ClientIdentity


class PhoneAdmissionCore:
    """Pure in-memory policy, deliberately not a service or persistence layer."""
    ADMISSION_EVENTS = frozenset({"issue", "consume", "command", "emit", "login"})
    FIELDS = {
        "advance": {"time"}, "issue": {"ticket", "session", "digest", "kind", "peer"},
        "consume": {"ticket", "session", "owner", "grant", "digest", "peer", "kind"},
        "command": {"peer", "owner", "action", "protocol"},
        "emit": {"peer", "sink", "classification", "provenance", "source_allowed"},
        "revoke_session": {"session", "notify"}, "revoke_grant": {"grant", "notify"},
        "begin": {"grant", "scope"}, "commit": set(), "finalize": set(),
        "login": {"grant", "session"}, "restart": set(), "snapshot": {"name"},
        "restore": {"name"}, "anchor": {"state"}, "disconnect": {"peer"},
        "availability": {"available"},
    }

    REQUIRED = {
        "advance": {"time"}, "issue": {"ticket", "session", "digest"},
        "consume": {"ticket", "session", "owner", "grant", "digest", "peer"},
        "command": {"peer", "action", "protocol"}, "emit": {"peer", "sink"},
        "revoke_session": {"session"}, "revoke_grant": {"grant"},
        "begin": {"grant", "scope"}, "login": {"grant", "session"},
        "snapshot": {"name"}, "restore": {"name"}, "anchor": {"state"},
        "disconnect": {"peer"}, "availability": {"available"},
    }
    IDENTIFIERS = {"ticket", "session", "digest", "peer", "owner", "grant",
                   "kind", "action", "sink", "name", "state"}
    CONSTANT_NAMES = {"ticket_ttl_s", "auth_freshness_s", "reconnect_reservation_s", "network_gap_s"}

    @staticmethod
    def finite_number(value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            return False

    def __init__(
        self,
        constants: dict[str, int | float],
        *,
        feature_enabled: bool,
        initial_grants: dict[str, dict[str, object]],
        initial_sessions: dict[str, dict[str, object]],
        initial_peers: dict[str, str],
    ) -> None:
        if (type(constants) is not dict or set(constants) != self.CONSTANT_NAMES
                or any(not self.finite_number(v) or v <= 0 for v in constants.values())):
            raise ValueError("S0 constants must be positive finite numbers")
        if type(feature_enabled) is not bool:
            raise ValueError("feature_enabled must be an explicit bool")
        if not self.valid_initial_state(initial_grants, initial_sessions, initial_peers):
            raise ValueError("invalid in-memory authority state")
        self.constants = dict(constants)
        self.feature_enabled = feature_enabled
        self.now = 0
        self.epoch = 1
        self.anchor_epoch = 1
        self.anchor_state = "stable"
        self.process = 1
        self.available = True
        self.pending = None
        self.grants = copy.deepcopy(initial_grants)
        self.sessions = copy.deepcopy(initial_sessions)
        # Synthetic per-session revocation floor, deliberately outside snapshots.
        # This represents the contract invariant only, not a production storage layout.
        self.session_fences = {}
        self.peers = {}
        for pid, sid in initial_peers.items():
            self.peers[pid] = self.new_peer(sid)
        self.tickets = {}
        self.invalidated = set()
        self.snapshots = {}
        self.emissions = []
        self.commands = []
        self.closures = []

    @classmethod
    def valid_initial_state(
        cls,
        grants: object,
        sessions: object,
        peers: object,
    ) -> bool:
        if type(grants) is not dict or type(sessions) is not dict or type(peers) is not dict:
            return False
        for grant_id, grant in grants.items():
            if (type(grant_id) is not str or not grant_id.strip() or type(grant) is not dict
                    or set(grant) != {"owner", "enabled", "scope"}
                    or type(grant["owner"]) is not str or not grant["owner"].strip()
                    or type(grant["enabled"]) is not bool or type(grant["scope"]) is not list
                    or any(type(scope) is not str or not scope.strip() for scope in grant["scope"])):
                return False
        for session_id, session in sessions.items():
            if (type(session_id) is not str or not session_id.strip() or type(session) is not dict
                    or set(session) != {"grant", "generation", "epoch", "process", "enabled"}
                    or type(session["grant"]) is not str or session["grant"] not in grants
                    or any(type(session[key]) is not int or session[key] < 0
                           for key in ("generation", "epoch", "process"))
                    or type(session["enabled"]) is not bool):
                return False
        return all(type(peer_id) is str and bool(peer_id.strip())
                   and type(session_id) is str and session_id in sessions
                   for peer_id, session_id in peers.items())

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
        name, offset = value["constant"], value["offset"]
        if type(name) is not str or name not in self.constants or not self.finite_number(offset):
            raise ValueError("bad fake-clock domain")
        target = self.constants[name] + offset
        if not self.finite_number(target):
            raise ValueError("non-finite fake-clock result")
        return target

    def close(self, pid, reason):
        peer = self.peers[pid]
        if not peer["closed"]:
            peer["closed"] = True
            self.closures.append({"peer": pid, "at": self.now, "reason": reason})

    def authority(self, binding):
        if self.anchor_state != "stable":
            return "authority-" + self.anchor_state
        if self.epoch != self.anchor_epoch:
            return "authority-mismatch"
        if not self.available:
            return "authority-unavailable"
        session = self.sessions.get(binding["session"])
        grant = self.grants.get(binding["grant"])
        if (not session or not grant or not session["enabled"] or not grant["enabled"]
                or binding["process"] != self.process
                or binding["generation"] != session["generation"]
                or binding["generation"] < self.session_fences.get(binding["session"], 0)):
            return "authority-stale"
        if binding["epoch"] != self.epoch or session["epoch"] != self.epoch:
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
                self.close(pid, error)
            return error
        if not peer["connected"]:
            return "disconnected"
        peer["checked"] = self.now
        return None

    def stable_authority(self):
        """Ordinary mutations are not recovery/reverification operations."""
        if self.anchor_state != "stable":
            return "authority-" + self.anchor_state
        if self.epoch != self.anchor_epoch:
            return "authority-mismatch"
        if not self.available:
            return "authority-unavailable"
        return None

    def transition_authority(self):
        """Only the exact pending transition may commit/finalize its own state."""
        if self.anchor_state != "pending":
            return "authority-" + self.anchor_state if self.anchor_state == "missing" else "authority-mismatch"
        expected_epoch = self.pending["target_epoch"] if self.pending["committed"] else self.pending["base_epoch"]
        expected_state = self.pending["after"] if self.pending["committed"] else self.pending["before"]
        if (self.anchor_epoch != self.pending["target_epoch"] or self.epoch != expected_epoch
                or (self.grants, self.sessions) != expected_state):
            return "authority-mismatch"
        if not self.available:
            return "authority-unavailable"
        return None

    def valid_event(self, event):
        if type(event) is not dict or type(event.get("type")) is not str:
            return False
        kind = event["type"]
        if kind not in self.FIELDS or set(event) - (self.FIELDS[kind] | {"type"}):
            return False
        if not self.REQUIRED.get(kind, set()) <= set(event):
            return False
        for name in self.IDENTIFIERS & set(event):
            if type(event[name]) is not str or not event[name].strip():
                return False
        for name in ("notify", "available"):
            if name in event and type(event[name]) is not bool:
                return False
        if "scope" in event and (type(event["scope"]) is not list
                or any(type(v) is not str or not v.strip() for v in event["scope"])):
            return False
        if kind == "issue" and event.get("kind") == "update" and "peer" not in event:
            return False
        return True

    @staticmethod
    def identity_owner(identity: object) -> tuple[str | None, str | None]:
        """Return a valid verified principal or a fail-closed denial reason."""
        if identity is None:
            return None, "identity-required"
        if type(identity) is not ClientIdentity:
            return None, "identity-invalid"
        if (type(identity.name) is not str or not identity.name.strip()
                or type(identity.user_id) is not str or not identity.user_id.strip()):
            return None, "identity-invalid"
        return identity.user_id, None

    def step(self, event: object, *, identity: ClientIdentity | None = None) -> dict[str, bool | str]:
        # Validate shape, required identities and control fields before any mutation.
        if not self.valid_event(event):
            return self.deny("malformed")
        kind = event["type"]
        if kind in self.ADMISSION_EVENTS:
            if not self.feature_enabled:
                return self.deny("feature-off")
            _, identity_error = self.identity_owner(identity)
            if identity_error:
                return self.deny(identity_error)
        try:
            return self._step(kind, event, identity)
        except (KeyError, TypeError, ValueError, OverflowError):
            return self.deny("malformed")

    def _step(self, kind: str, e: dict[str, object], identity: ClientIdentity | None):
        if kind == "advance":
            target = self.time_value(e["time"])
            if target < self.now:
                return self.deny("clock-backwards")
            # Observe the deadline itself, even if the requested fake jump crosses it.
            deadlines = {pid: peer["checked"] + self.constants["auth_freshness_s"]
                         for pid, peer in self.peers.items() if not peer["closed"]}
            if any(not self.finite_number(value) for value in deadlines.values()):
                return self.deny("malformed")
            for pid, peer in self.peers.items():
                deadline = deadlines.get(pid, target + 1)
                if not peer["closed"] and self.authority(peer["binding"]) and deadline <= target:
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
            principal, _ = self.identity_owner(identity)
            if principal != binding["owner"]:
                return self.deny("binding-mismatch")
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
            expires = self.now + self.constants["ticket_ttl_s"]
            if not self.finite_number(expires):
                return self.deny("malformed")
            self.tickets[e["ticket"]] = {"binding": binding, "digest": e["digest"],
                                         "kind": ticket_kind, "peer": e.get("peer"),
                                         "expires": expires, "used": False}
            return self.result()
        if kind == "consume":
            tid = e["ticket"]
            if tid in self.invalidated:
                return self.deny("ticket-invalidated")
            ticket = self.tickets.get(tid)
            if not ticket:
                return self.deny("ticket-unknown")
            if ticket["used"]:
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
            principal, _ = self.identity_owner(identity)
            if principal != bound["owner"]:
                return self.deny("binding-mismatch")
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
            principal, _ = self.identity_owner(identity)
            if principal != bound["owner"]:
                return self.deny("binding-mismatch")
            if kind == "command":
                if type(e["protocol"]) is not int or e["protocol"] != 1 or e["action"] != "fixture-action":
                    return self.deny("protocol")
                if e.get("owner", bound["owner"]) != bound["owner"]:
                    return self.deny("binding-mismatch")
                if "action" not in scopes:
                    return self.deny("scope")
                self.commands.append({"peer": pid, "owner": bound["owner"]})
            else:
                if e["sink"] not in ("event", "text", "audio-symbol"):
                    return self.deny("provider-input-denied")
                if (e.get("classification") != "ordinary"
                        or e.get("provenance") is not True or e.get("source_allowed") is not True):
                    return self.deny("classification")
                if ("voice" if e["sink"] == "audio-symbol" else "read") not in scopes:
                    return self.deny("scope")
                self.emissions.append({"peer": pid, "sink": e["sink"], "at": self.now})
            return self.result()
        if kind == "revoke_session":
            error = self.stable_authority()
            if error:
                return self.deny(error)
            sid = e["session"]
            next_generation = max(self.sessions[sid]["generation"],
                                  self.session_fences.get(sid, 0)) + 1
            self.sessions[sid]["enabled"] = False
            self.sessions[sid]["generation"] = next_generation
            self.session_fences[sid] = next_generation
            if e.get("notify", True):
                for pid, peer in self.peers.items():
                    if peer["binding"]["session"] == sid:
                        self.close(pid, "authority-stale")
            return self.result()
        if kind == "revoke_grant":
            error = self.stable_authority()
            if error:
                return self.deny(error)
            self.grants[e["grant"]]["enabled"] = False
            self.epoch += 1
            self.anchor_epoch = self.epoch
            if e.get("notify", True):
                for pid in self.peers:
                    self.close(pid, "authority-stale")
            return self.result()
        if kind == "begin":
            error = self.stable_authority()
            if error:
                return self.deny(error)
            if self.pending is not None:
                return self.deny("authority-pending")
            gid = e["grant"]
            scope = e["scope"]
            if not isinstance(scope, list) or not set(scope) <= set(self.grants[gid]["scope"]):
                return self.deny("scope")
            self.pending = {"grant": gid, "scope": list(scope), "committed": False,
                            "base_epoch": self.epoch, "target_epoch": self.anchor_epoch + 1,
                            "before": copy.deepcopy((self.grants, self.sessions)), "after": None}
            self.anchor_epoch += 1
            self.anchor_state = "pending"
            return self.result()
        if kind == "commit":
            if self.pending is None:
                return self.deny("no-transition")
            error = self.transition_authority()
            if error:
                return self.deny(error)
            self.grants[self.pending["grant"]]["scope"] = list(self.pending["scope"])
            self.epoch = self.anchor_epoch
            self.pending["committed"] = True
            self.pending["after"] = copy.deepcopy((self.grants, self.sessions))
            return self.result()
        if kind == "finalize":
            if self.pending is None:
                return self.deny("no-commit")
            error = self.transition_authority()
            if error:
                return self.deny(error)
            if not self.pending["committed"]:
                return self.deny("no-commit")
            self.anchor_state = "stable"
            self.pending = None
            return self.result()
        if kind == "login":
            gid, sid = e["grant"], e["session"]
            # Check host consistency without creating or reviving a session first.
            if self.anchor_state != "stable":
                return self.deny("authority-" + self.anchor_state)
            if self.epoch != self.anchor_epoch:
                return self.deny("authority-mismatch")
            if not self.available or not self.grants[gid]["enabled"]:
                return self.deny("authority-stale")
            if sid in self.sessions:
                return self.deny("session-exists")
            principal, _ = self.identity_owner(identity)
            if principal != self.grants[gid]["owner"]:
                return self.deny("binding-mismatch")
            self.sessions[sid] = {"grant": gid, "generation": self.session_fences.get(sid, 0), "epoch": self.epoch,
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
            # The per-session revocation floor is outside the rollbackable snapshot.
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
        raise AssertionError("unhandled admission event")

    def view(self):
        return {"epoch": self.epoch, "anchor_epoch": self.anchor_epoch,
                "anchor_state": self.anchor_state, "process": self.process,
                "session_fences": copy.deepcopy(self.session_fences),
                "closed": sorted(pid for pid, p in self.peers.items() if p["closed"]),
                "emissions": copy.deepcopy(self.emissions), "commands": copy.deepcopy(self.commands),
                "closures": copy.deepcopy(self.closures),
                "grants": copy.deepcopy(self.grants),
                "bindings": {pid: copy.deepcopy(peer["binding"]) for pid, peer in self.peers.items()}}
