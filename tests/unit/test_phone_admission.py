"""Focused tests for the offline phone-admission policy boundary."""
import json
from pathlib import Path
import unittest
import copy

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission import PhoneAdmissionCore


FIXTURE = Path(__file__).parents[1] / "fixtures/phone_admission_contract/v1.json"


def constants():
    return json.loads(FIXTURE.read_text())["constants"]


def identity(user_id="owner-a", name="verified-test"):
    return ClientIdentity(name=name, user_id=user_id)


def issue_event():
    return {"type": "issue", "ticket": "t1", "session": "a1", "digest": "offer"}


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


class PhoneAdmissionBoundaryTests(unittest.TestCase):
    def make_core(self, *, feature_enabled=True):
        grants, sessions, peers = fixture_state()
        return PhoneAdmissionCore(constants(), feature_enabled=feature_enabled,
                                  initial_grants=grants, initial_sessions=sessions,
                                  initial_peers=peers)

    def test_admission_requires_verified_identity_and_denies_without_mutation(self):
        core = self.make_core()
        event = issue_event()
        before = copy.deepcopy(core.__dict__)

        self.assertEqual(core.step(event), {"admitted": False, "reason": "identity-required"})
        self.assertEqual(core.__dict__, before)
        self.assertEqual(core.step(event, identity=object()),
                         {"admitted": False, "reason": "identity-invalid"})
        self.assertEqual(core.__dict__, before)
        self.assertEqual(core.step(event, identity=identity(name=" ")),
                         {"admitted": False, "reason": "identity-invalid"})
        self.assertEqual(core.__dict__, before)
        self.assertEqual(core.step(event, identity=identity()), {"admitted": True, "reason": "ok"})

    def test_verified_user_must_match_session_for_ticket_command_output_and_login(self):
        core = self.make_core()
        wrong_user = identity("owner-b")
        correct_user = identity()

        self.assertEqual(core.step(issue_event(), identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertEqual(core.step(issue_event(), identity=correct_user),
                         {"admitted": True, "reason": "ok"})
        consume = {"type": "consume", "ticket": "t1", "session": "a1", "owner": "owner-a",
                   "grant": "A", "digest": "offer", "peer": "p4"}
        self.assertEqual(core.step(consume, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertFalse(core.tickets["t1"]["used"])
        self.assertEqual(core.step(consume, identity=correct_user), {"admitted": True, "reason": "ok"})

        command = {"type": "command", "peer": "p1", "owner": "owner-a",
                   "action": "fixture-action", "protocol": 1}
        self.assertEqual(core.step(command, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertEqual(core.commands, [])
        output = {"type": "emit", "peer": "p1", "sink": "text", "classification": "ordinary",
                  "provenance": True, "source_allowed": True}
        self.assertEqual(core.step(output, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertEqual(core.emissions, [])
        login = {"type": "login", "grant": "A", "session": "a-new"}
        self.assertEqual(core.step(login, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertNotIn("a-new", core.sessions)

    def test_feature_off_refuses_every_admission_event(self):
        core = self.make_core(feature_enabled=False)
        principal = identity()
        events = [
            issue_event(),
            {"type": "consume", "ticket": "unknown", "session": "a1", "owner": "owner-a",
             "grant": "A", "digest": "offer", "peer": "p4"},
            {"type": "command", "peer": "p1", "action": "fixture-action", "protocol": 1},
            {"type": "emit", "peer": "p1", "sink": "text"},
            {"type": "login", "grant": "A", "session": "a-new"},
        ]
        before = copy.deepcopy(core.__dict__)
        for event in events:
            with self.subTest(event=event):
                self.assertEqual(core.step(event, identity=principal),
                                 {"admitted": False, "reason": "feature-off"})
        self.assertEqual(core.__dict__, before)

    def test_feature_switch_must_be_an_explicit_boolean(self):
        with self.assertRaisesRegex(ValueError, "explicit bool"):
            PhoneAdmissionCore(constants(), feature_enabled=1, initial_grants={},
                               initial_sessions={}, initial_peers={})

    def test_initial_peer_state_cannot_reference_an_unknown_session(self):
        grants, sessions, peers = fixture_state()
        peers["p4"] = "missing-session"
        with self.assertRaisesRegex(ValueError, "in-memory authority state"):
            PhoneAdmissionCore(constants(), feature_enabled=True, initial_grants=grants,
                               initial_sessions=sessions, initial_peers=peers)

    def test_peer_authority_requires_current_session_grant_and_owner_binding(self):
        core = self.make_core()
        binding = copy.deepcopy(core.peers["p1"]["binding"])

        core.sessions["a1"]["grant"] = "B"
        self.assertEqual(core.authority(binding), "authority-stale")
        core.sessions["a1"]["grant"] = "A"

        core.grants["A"]["owner"] = "owner-b"
        self.assertEqual(core.authority(binding), "authority-stale")

    def test_restored_session_id_reuse_cannot_transfer_old_peer_or_ticket_authority(self):
        grants, _, _ = fixture_state()
        core = PhoneAdmissionCore(constants(), feature_enabled=True, initial_grants=grants,
                                  initial_sessions={}, initial_peers={})
        alice = identity("owner-a")
        bob = identity("owner-b")

        self.assertEqual(core.step({"type": "snapshot", "name": "empty"}),
                         {"admitted": True, "reason": "ok"})
        self.assertEqual(core.step({"type": "login", "grant": "A", "session": "reused"},
                                   identity=alice), {"admitted": True, "reason": "ok"})

        for ticket, peer in (("old-command", "old-command-peer"),
                             ("old-output", "old-output-peer"),
                             ("old-unused", None)):
            issue = {"type": "issue", "ticket": ticket, "session": "reused",
                     "digest": ticket}
            self.assertEqual(core.step(issue, identity=alice), {"admitted": True, "reason": "ok"})
            if peer is not None:
                consume = {"type": "consume", "ticket": ticket, "session": "reused",
                           "owner": "owner-a", "grant": "A", "digest": ticket,
                           "peer": peer}
                self.assertEqual(core.step(consume, identity=alice),
                                 {"admitted": True, "reason": "ok"})

        self.assertEqual(core.step({"type": "restore", "name": "empty"}),
                         {"admitted": True, "reason": "ok"})
        self.assertEqual(core.step({"type": "login", "grant": "B", "session": "reused"},
                                   identity=bob), {"admitted": True, "reason": "ok"})

        command = {"type": "command", "peer": "old-command-peer",
                   "action": "fixture-action", "protocol": 1}
        output = {"type": "emit", "peer": "old-output-peer", "sink": "text",
                  "classification": "ordinary", "provenance": True,
                  "source_allowed": True}
        stale_ticket = {"type": "consume", "ticket": "old-unused", "session": "reused",
                        "owner": "owner-a", "grant": "A", "digest": "old-unused",
                        "peer": "stale-ticket-peer"}
        for event in (command, output, stale_ticket):
            with self.subTest(event=event):
                self.assertEqual(core.step(event, identity=alice),
                                 {"admitted": False, "reason": "authority-stale"})
        self.assertEqual(core.commands, [])
        self.assertEqual(core.emissions, [])
        self.assertFalse(core.tickets["old-unused"]["used"])

        # A new Bob session and a separate, unrelated Bob session remain usable.
        self.assertEqual(core.step({"type": "login", "grant": "B", "session": "unrelated"},
                                   identity=bob), {"admitted": True, "reason": "ok"})
        for session, ticket, peer in (("reused", "fresh-bob", "fresh-bob-peer"),
                                      ("unrelated", "other-bob", "other-bob-peer")):
            issue = {"type": "issue", "ticket": ticket, "session": session,
                     "digest": ticket}
            self.assertEqual(core.step(issue, identity=bob), {"admitted": True, "reason": "ok"})
            consume = {"type": "consume", "ticket": ticket, "session": session,
                       "owner": "owner-b", "grant": "B", "digest": ticket,
                       "peer": peer}
            self.assertEqual(core.step(consume, identity=bob),
                             {"admitted": True, "reason": "ok"})
            fresh_command = {"type": "command", "peer": peer,
                             "action": "fixture-action", "protocol": 1}
            fresh_output = {"type": "emit", "peer": peer, "sink": "text",
                            "classification": "ordinary", "provenance": True,
                            "source_allowed": True}
            self.assertEqual(core.step(fresh_command, identity=bob),
                             {"admitted": True, "reason": "ok"})
            self.assertEqual(core.step(fresh_output, identity=bob),
                             {"admitted": True, "reason": "ok"})


if __name__ == "__main__":
    unittest.main()
